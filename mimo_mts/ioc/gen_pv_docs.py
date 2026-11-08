"""
Generate the PV tables of doc/PVs.md from the IOC code, off-board.

Each IOC class is built against a stand-in overlay (no PYNQ hardware; the board-only modules xrfdc/xrfclk and the
LBL208 PMBus devices are faked), its records are written out with softioc's WriteRecords, and the records are rendered
as one table: channel numbers are collapsed into patterns (ADC{n}) and a column lists the IOC classes that have
each PV. The tables replace the text between the GENERATED markers in PVs.md.

    python -m mimo_mts.ioc.gen_pv_docs            # update PVs.md
    python -m mimo_mts.ioc.gen_pv_docs --check    # exit 1 if PVs.md is out of date (CI)
    python -m mimo_mts.ioc.gen_pv_docs --list AlsMimo5GZCU208   # full PV names of one IOC (compare with dbl())
"""

import argparse
import json
import os
import re
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
PVS_MD = ROOT / "doc" / "PVs.md"
BEGIN = "<!-- BEGIN GENERATED PV TABLES: python -m mimo_mts.ioc.gen_pv_docs -->"
END = "<!-- END GENERATED PV TABLES -->"


def install_board_stubs():
    """Fake the board-only modules so the IOC code imports off-board."""
    for name in ("xrfdc", "xrfclk"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__file__ = f"/nonexistent/{name}.py"
            sys.modules[name] = mod
    xrfdc: Any = sys.modules["xrfdc"]
    for i, name in enumerate(
        ("MIXER_MODE_R2C", "MIXER_MODE_C2C", "MIXER_MODE_C2R", "MIXER_MODE_R2R", "MIXER_TYPE_FINE",
         "MIXER_TYPE_COARSE", "COARSE_MIX_OFF", "EVNT_SRC_SYSREF", "EVNT_SRC_TILE", "MIXER_SCALE_1P0")
    ):  # fmt: skip
        if not hasattr(xrfdc, name):
            setattr(xrfdc, name, i + 1)


class FakeReg(int):
    """A register value: 0, accepts field reads and writes (``reg.dac_enable = 1``)."""

    def __getattr__(self, name):
        return FakeReg(0)


class FakeRegisterMap:
    def __getattr__(self, name):
        return FakeReg(0)

    def __setattr__(self, name, value):
        pass


class FakeAdcCal:
    def __init__(self, n):
        self.channels = list(range(n))

    def is_frozen(self, adc_ch=None):
        return dict.fromkeys(self.channels, False)

    def freeze(self, adc_ch=None):
        return dict.fromkeys(self.channels, True)

    def restore(self, path):
        return dict.fromkeys(self.channels, [])


class FakeOverlay:
    """The parts of MimoMtsOverlay that MimoMtsIoc reads while building its records."""

    def __init__(self, ol_name):
        from mimo_mts.config import ol_configs

        self.ol_info = ol_configs[ol_name]
        self.board = self.ol_info["board"]
        rates = self.ol_info.get("sampling_rate_hz", {})
        self.adc_sampling_rate = rates.get("adc", 4e9)
        self.dac_sampling_rate = rates.get("dac", 4e9)
        regs = json.loads((ROOT / "designs/ip/rtl/axil_rf_control.json").read_text())
        self.rf_control = types.SimpleNamespace(register_map=FakeRegisterMap(), _registers=regs, tx_gain=1.0)
        mixer = self.ol_info["rfdc"]["mixer"]
        for key in ("adc_mixer_nco_freq_mhz", "adc_mixer_nco_nyquist", "adc_mixer_nco_phase",
                    "dac_mixer_nco_freq_mhz", "dac_mixer_nco_nyquist", "dac_mixer_nco_phase"):  # fmt: skip
            setattr(self, key, mixer[key])
        self.adc_cal = FakeAdcCal(self.board.n_adcs)
        self.dac_player = np.zeros(2048, dtype=np.int16)
        self._n_samples = 1024 * self.ol_info["ioc"]["decimation"]

    @property
    def mixer_cfg(self):
        keys = ("adc_mixer_nco_freq_mhz", "adc_mixer_nco_nyquist", "adc_mixer_nco_phase",
                "dac_mixer_nco_freq_mhz", "dac_mixer_nco_nyquist", "dac_mixer_nco_phase")  # fmt: skip
        return {k: getattr(self, k) for k in keys}

    def capture_adc_iq_buf(self, i_buffer=None, q_buffer=None):
        shape = (self.board.n_adcs, self._n_samples)
        return np.zeros(shape, np.int16), np.zeros(shape, np.int16)

    def write_dac_iq_buf(self, i_buffer, q_buffer):
        pass

    def restart_adc_tiles(self):
        pass

    def free(self):
        pass


def ioc_classes():
    """(IOC class, entry point) for every IOC of pyproject.toml."""
    from mimo_mts.ioc import app_iocs as a

    return [
        (a.AlsLlrfZCU208, "llrf-zcu208-ioc"),
        (a.AlsLlrfLBL208, "llrf-lbl208-ioc"),
        (a.MimoZCU208, "mimo-zcu208-ioc"),
        (a.AlsMimo5GZCU208, "mimo5g-zcu208-ioc"),
        (a.MimoLBL208, "mimo-lbl208-ioc"),
        (a.MimoZCU216, "mimo-zcu216-ioc"),
    ]


def build_records(cls):
    """Build one IOC class off-board; returns {name: (record type, fields)} without the IOC prefix."""
    from softioc import builder

    from mimo_mts.ioc import app_iocs

    # LBL208 telemetry devices: fakes that report every sensor of the driver as supported
    class FakeMcrps:
        UNITS = app_iocs.McrpsDevice.UNITS
        supported_sensors = list(UNITS)

        def __init__(self, *a, **k):
            pass

    class FakeMax:
        def __init__(self, *a, **k):
            pass

        def enable_fan(self, *a, **k):
            pass

    saved = (app_iocs.SMBus, app_iocs.McrpsDevice, app_iocs.Max31785)
    app_iocs.SMBus = lambda *a, **k: None  # type: ignore[assignment]
    app_iocs.McrpsDevice = FakeMcrps  # type: ignore[assignment,misc]
    app_iocs.Max31785 = FakeMax  # type: ignore[assignment,misc]
    try:
        board = "ZCU216" if "ZCU216" in cls.__name__ else "ZCU208"
        os.environ["BOARD"] = board
        ioc = _construct(cls)
        builder.ClearRecords()
        ioc.create_ioc()
        with tempfile.NamedTemporaryFile("r", suffix=".db") as f:
            builder.WriteRecords(f.name)
            text = Path(f.name).read_text()
        builder.ClearRecords()
        return ioc.prefix, ioc.ol_name, parse_db(text, ioc.prefix)
    finally:
        app_iocs.SMBus, app_iocs.McrpsDevice, app_iocs.Max31785 = saved


def _construct(cls):
    """Instantiate an IOC class with a FakeOverlay for its overlay configuration."""
    # Each class picks its overlay with kwargs.setdefault("ol_name", ...) or a keyword default: read it from the code.
    import inspect

    src = inspect.getsource(cls.__init__)
    m = re.search(r'ol_name\s*=\s*"([A-Z0-9_]+)"', src) or re.search(r'"ol_name",\s*"([A-Z0-9_]+)"', src)
    if not m:
        raise RuntimeError(f"{cls.__name__}: cannot find its overlay name")
    name = m.group(1)
    return cls(ol=FakeOverlay(name), ol_name=name, adc_cal_file="/nonexistent/adc_cal.json")


RECORD_RE = re.compile(r'record\((\w+),\s*"([^"]+)"\)\s*\{(.*?)\n\}', re.S)
FIELD_RE = re.compile(r'field\((\w+),\s*"([^"]*)"\)')


def parse_db(text, prefix):
    records = {}
    for rtype, name, body in RECORD_RE.findall(text):
        fields = dict(FIELD_RE.findall(body))
        records[name.removeprefix(prefix + ":")] = (rtype, fields)
    return records


def pattern(name):
    """Collapse channel numbers: ADC3 -> ADC{n}, DAC3 -> DAC{n}, chassis_fan_speed_2 -> chassis_fan_speed_{i}."""
    name = re.sub(r"\b(ADC|DAC)\d+", r"\1{n}", name)
    return re.sub(r"chassis_fan_speed_\d+", "chassis_fan_speed_{i}", name)


GROUPS = [
    ("Time axes and waveforms", r"^(ADC|DSP):TWF$|WF$"),
    ("Pulse statistics", r"pulse_stat"),
    ("RF control (`axil_rf_control` registers)", r"^rf_control:"),
    ("RFDC mixers", r"^rfdc_mixer:"),
    ("RF-ADC calibration", r"^adc_cal:"),
    ("Telemetry (LBL208)", r"^pmbus:"),
]


def render(builds):
    """Markdown for the generated part of PVs.md."""
    all_classes = [b["cls"] for b in builds]
    rows: dict[str, dict] = {}
    for b in builds:
        for name, (rtype, fields) in b["records"].items():
            key = pattern(name)
            row = rows.setdefault(key, {"type": rtype, "fields": fields, "classes": [], "count": {}})
            if b["cls"] not in row["classes"]:
                row["classes"].append(b["cls"])
            row["count"][b["cls"]] = row["count"].get(b["cls"], 0) + 1
            if "{" in key:  # a generic description for the pattern
                d = re.sub(r"\b(ADC|DAC)\d+", r"\1{n}", fields.get("DESC", ""))
                row["fields"] = {**fields, "DESC": re.sub(r"Chassis fan \d+", "Chassis fan {i}", d)}

    out = [BEGIN, ""]
    out.append("### IOCs\n")
    out.append("| IOC class | Entry point | Overlay | Prefix `$P` | ADCs / DACs | Records |")
    out.append("|---|---|---|---|---|---|")
    for b in builds:
        out.append(
            f"| `{b['cls']}` | `{b['entry']}` | `{b['ol_name']}` | `{b['prefix']}` | {b['n_adc']} / {b['n_dac']} "
            f"| {len(b['records'])} |"
        )
    out.append("")
    out.append(
        "`{n}` is the ADC or DAC channel (0 to ADCs − 1 or DACs − 1 of the IOC), `{i}` the chassis fan (1, 2). "
        "All names start with `$P:`. Every IOC also has the standard `devIocStats` records under `$P:ioc`."
    )
    out.append("")
    used = set()
    for title, regex in GROUPS:
        keys = [k for k in rows if re.search(regex, k) and k not in used]
        if not keys:
            continue
        used.update(keys)
        out.append(f"### {title}\n")
        out.append("| PV | Type | Description | Units | IOCs |")
        out.append("|---|---|---|---|---|")
        for k in sorted(keys, key=lambda k: (k.replace(":RBV", ""), k.endswith(":RBV"))):
            r = rows[k]
            f = r["fields"]
            iocs = "all" if r["classes"] == all_classes else ", ".join(f"`{c}`" for c in r["classes"])
            egu = f.get("EGU", "")
            out.append(f"| `{k}` | {r['type']} | {f.get('DESC', '')} | {egu} | {iocs} |")
        out.append("")
    rest = [k for k in rows if k not in used]
    if rest:
        raise RuntimeError(f"PVs not in any group, add a group: {rest}")
    out.append(END)
    return "\n".join(out)


def generate():
    install_board_stubs()
    builds = []
    for cls, entry in ioc_classes():
        prefix, ol_name, records = build_records(cls)
        from mimo_mts.config import ol_configs

        board = ol_configs[ol_name]["board"]
        builds.append(
            {
                "cls": cls.__name__,
                "entry": entry,
                "prefix": prefix,
                "ol_name": ol_name,
                "records": records,
                "n_adc": board.n_adcs,
                "n_dac": board.n_dacs,
            }
        )
    return render(builds)


def main():
    parser = argparse.ArgumentParser(description="Generate or check the PV tables of doc/PVs.md.")
    parser.add_argument("--check", action="store_true", help="exit 1 if PVs.md is out of date, do not write")
    parser.add_argument("--list", metavar="IOC_CLASS", help="print the full PV names of one IOC class and exit")
    args = parser.parse_args()

    if args.list:
        install_board_stubs()
        cls = next((c for c, _ in ioc_classes() if c.__name__ == args.list), None)
        if cls is None:
            print(f"unknown IOC class {args.list}; one of {[c.__name__ for c, _ in ioc_classes()]}", file=sys.stderr)
            return 2
        prefix, _, records = build_records(cls)
        print("\n".join(sorted(f"{prefix}:{name}" for name in records)))
        return 0

    tables = generate()
    doc = PVS_MD.read_text()
    if BEGIN in doc and END in doc:
        new = doc[: doc.index(BEGIN)] + tables + doc[doc.index(END) + len(END) :]
    else:
        new = doc.rstrip("\n") + "\n\n## PV reference (generated)\n\n" + tables + "\n"
    if args.check:
        if new != doc:
            print("doc/PVs.md is out of date: run python -m mimo_mts.ioc.gen_pv_docs", file=sys.stderr)
            return 1
        print("PVs.md is up to date")
        return 0
    PVS_MD.write_text(new)
    print(f"wrote {PVS_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
