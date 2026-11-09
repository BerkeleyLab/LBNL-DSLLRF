"""
Check the DAC PVs of a running IOC through Channel Access, with a DAC n -> ADC n loopback cable on every channel
(as on the ZCU208 test setup). Runs on any host that reaches the IOC; needs pyepics (a project dependency).

Checks are chosen from the PVs the IOC has:
- every IOC with `DAC:IWF` (shared waveform): a 1 us pulse written to all DACs arrives on every ADC, with the
  same width and start on all channels;
- IOCs with one waveform generator per DAC (`DAC{n}:mode`, `DAC:apply`, e.g. mimo-5g-zcu208-ioc):
  1. mode and CW values are staged: no effect until `DAC:apply`, then `DAC{n}:mode:RBV` follows;
  2. a CW phase / amplitude step on one DAC moves only its ADC (+90 deg, half amplitude);
  3. per-DAC phases 45 deg * n on one apply;
  4. NCO phase repeatability (informational): per-ADC phase change after setting the mixers to 0 and back;
  5. per-DAC waveform: a 1 us pulse on one DAC only;
  6. loop mode: the free-running loop moves the pulse between captures; single mode keeps it in place.
With --no-loopback only the PV-level checks run (staging and mode readbacks).

The DAC and ADC mixers are set to --rf-mhz, so each ADC sees its DAC at baseband in DSP:ADC{n}:AWF / PWF; phases
and amplitudes are compared with a baseline (cable and NCO phases differ per channel). The IOC state (mixers, modes,
CW values, shared waveform) is restored at the end, also after a failure.

    python3 mimo_mts/tests/test_ioc_dac.py [--prefix MIMO_5G_ZCU208] [--rf-mhz 200] [--channel 3] [--no-loopback]
"""

import argparse
import sys
import time
from typing import Any

import numpy as np


def _import_epics() -> Any:
    try:
        import epics  # pyright: ignore[reportMissingImports]
    except ImportError:
        epics = None
    if not hasattr(epics, "PV"):  # also catches the repository's epics/ folder (Phoebus screens) found instead
        sys.exit("test_ioc_dac.py needs pyepics: pip install pyepics")
    return epics


def wrap_deg(x):
    return (np.asarray(x) + 180) % 360 - 180


class IocDacCheck:
    def __init__(self, prefix, settle_s=1.5, timeout_s=5.0):
        self.epics: Any = _import_epics()  # pyepics (not the repository's epics/ screens folder)
        self.prefix = prefix
        self.settle_s = settle_s
        self.timeout_s = timeout_s
        self.results = []
        self._pvs = {}
        self.t_dsp = np.zeros(0)  # DSP:TWF, read in main()

    # --- Channel Access helpers ---
    def pv(self, name):
        if name not in self._pvs:
            self._pvs[name] = self.epics.PV(f"{self.prefix}:{name}", connection_timeout=self.timeout_s)
        return self._pvs[name]

    def exists(self, name):
        return self.pv(name).wait_for_connection(timeout=self.timeout_s)

    def get(self, name, as_string=False):
        value = self.pv(name).get(timeout=self.timeout_s, as_string=as_string, use_monitor=False)
        if value is None:
            raise RuntimeError(f"{self.prefix}:{name}: no value (IOC running? prefix right?)")
        return value

    def put(self, name, value):
        if not self.pv(name).put(value, wait=True, timeout=self.timeout_s):
            raise RuntimeError(f"{self.prefix}:{name}: put timed out")

    def settle(self, n=1):
        """Wait for fresh captures after a change (the IOC triggers every 0.5 s by default)."""
        time.sleep(n * self.settle_s)

    def report(self, name, ok, detail=""):
        self.results.append((name, ok))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{': ' + detail if detail else ''}")

    def info(self, text):
        print(f"  {text}")

    # --- measurements from the decimated ADC waveforms ---
    def count_channels(self, fmt, n_max=16):
        n = 0
        while n < n_max and self.exists(fmt.format(n)):
            n += 1
        return n

    def adc_wave(self, ch):
        """Complex baseband of ADC ch (DSP:ADC{ch}:AWF / PWF) and its time axis in ns."""
        a = np.asarray(self.get(f"DSP:ADC{ch}:AWF"), dtype=float)
        p = np.asarray(self.get(f"DSP:ADC{ch}:PWF"), dtype=float)
        n = min(a.size, p.size, self.t_dsp.size)
        return self.t_dsp[:n], a[:n] * np.exp(1j * np.radians(p[:n]))

    def phasors(self, chans, t0_ns=400.0):
        """Mean complex amplitude of each ADC after t0_ns (CW: the whole capture after the loopback latency)."""
        out = []
        for ch in chans:
            t, z = self.adc_wave(ch)
            out.append(z[t >= t0_ns].mean())
        return np.array(out)

    def pulse(self, ch):
        """(start ns, width ns) of the part of the ADC amplitude above half its maximum, or None if there is none."""
        t, z = self.adc_wave(ch)
        a = np.abs(z)
        if a.max() < 50:
            return None
        on = np.flatnonzero(a > 0.5 * a.max())
        return t[on[0]], t[on[-1]] - t[on[0]] + (t[1] - t[0])

    def phase_stability(self, chans, n_captures=4, t0_ns=400.0):
        """
        Per channel: phase slope within one capture (deg/us, a frequency offset between DAC and ADC mixers shows here)
        and the spread of the capture phase over n_captures (drift or NCO phase changes between captures).
        """
        phases = []
        slopes = {}
        for k in range(n_captures):
            if k:
                self.settle()
            row = []
            for ch in chans:
                t, z = self.adc_wave(ch)
                sel = t >= t0_ns
                row.append(np.degrees(np.angle(z[sel].mean())))
                if k == 0:
                    ph = np.degrees(np.unwrap(np.angle(z[sel])))
                    slopes[ch] = np.polyfit(t[sel] / 1e3, ph, 1)[0]
            phases.append(row)
        phases = np.array(phases)
        spread = np.ptp(np.degrees(np.unwrap(np.radians(phases), axis=0)), axis=0)
        return {ch: (slopes[ch], spread[i]) for i, ch in enumerate(chans)}


def pulse_iq(chk, length_ns, level=16000, name="DAC:TWF"):
    """I (constant `level` for length_ns, then 0) and Q (0) at the DAC complex rate, as long as the DAC waveform."""
    t = np.asarray(chk.get(name), dtype=float)
    i = np.where(t < length_ns, level, 0).astype(np.int16)
    return i, np.zeros_like(i)


def check_shared_waveform(chk, chans, length_ns=1000.0):
    """DAC:IWF writes every DAC: the pulse must arrive on every ADC with the same width and start."""
    i, q = pulse_iq(chk, length_ns)
    chk.put("DAC:QWF", q)
    chk.put("DAC:IWF", i)
    chk.settle(2)
    res = {ch: chk.pulse(ch) for ch in chans}
    missing = [ch for ch, r in res.items() if r is None]
    if missing:
        chk.report("shared waveform on every ADC", False, f"no pulse on ADC {missing} (cables? DAC enabled?)")
        return
    starts = np.array([res[ch][0] for ch in chans])
    widths = np.array([res[ch][1] for ch in chans])
    ok = np.all(np.abs(widths - length_ns) < 50) and np.ptp(starts) < 20
    chk.report(
        "shared waveform on every ADC",
        ok,
        f"widths {np.round(widths).astype(int).tolist()} ns (expected {length_ns:.0f}), "
        f"starts {np.round(starts).astype(int).tolist()} ns",
    )


def set_modes(chk, n_dac, mode, apply=True):
    for ch in range(n_dac):
        chk.put(f"DAC{ch}:mode", mode)
    if apply:
        chk.put("DAC:apply", 1)


def check_cw(chk, n_dac, chans, ch_step, loopback, tol_deg=1.0, tol_amp=0.02):
    """Staging, a CW step on one DAC, and 45 deg * n on all DACs. Returns the baseline phasors (or None)."""
    rbv0 = [chk.get(f"DAC{ch}:mode:RBV", as_string=True) for ch in range(n_dac)]
    for ch in range(n_dac):
        chk.put(f"DAC{ch}:cw:amp", 0.5)
        chk.put(f"DAC{ch}:cw:phase", 0.0)
    set_modes(chk, n_dac, "CW", apply=False)
    chk.settle()
    rbv = [chk.get(f"DAC{ch}:mode:RBV", as_string=True) for ch in range(n_dac)]
    chk.report("modes staged until DAC:apply", rbv == rbv0, f"mode:RBV {rbv} (before {rbv0})")
    chk.put("DAC:apply", 1)
    chk.settle(2)
    rbv = [chk.get(f"DAC{ch}:mode:RBV", as_string=True) for ch in range(n_dac)]
    chk.report("CW active on all DACs after DAC:apply", all(r == "CW" for r in rbv), f"mode:RBV {rbv}")
    if not loopback:
        return None

    stab = chk.phase_stability(chans)
    for ch in chans:
        slope, spread = stab[ch]
        chk.info(f"ADC{ch} CW phase: slope {slope:+.3f} deg/us within a capture, spread {spread:.2f} deg over captures")
    ok = all(abs(s) * 8 < tol_deg and sp < tol_deg for s, sp in stab.values())
    chk.report("CW phase stable within and between captures", ok, f"tolerance {tol_deg} deg")
    z0 = chk.phasors(chans)

    def compare(name, z, want_deg, want_ratio):
        d = wrap_deg(np.degrees(np.angle(z / z0)))
        r = np.abs(z / z0)
        for k, ch in enumerate(chans):
            ok = abs(wrap_deg(d[k] - want_deg[k])) < tol_deg and abs(r[k] - want_ratio[k]) < tol_amp
            chk.report(
                f"{name}: ADC{ch}",
                ok,
                f"phase {d[k]:+7.2f} deg (expected {wrap_deg(want_deg[k]):+7.1f}), amplitude ratio {r[k]:.3f} "
                f"(expected {want_ratio[k]:.2f})",
            )

    # one DAC: staged (no change), then applied (+90 deg, half amplitude); the others unchanged
    chk.put(f"DAC{ch_step}:cw:phase", 90.0)
    chk.put(f"DAC{ch_step}:cw:amp", 0.25)
    chk.settle()
    compare("CW step staged, before apply", chk.phasors(chans), [0.0] * len(chans), [1.0] * len(chans))
    chk.put("DAC:apply", 1)
    chk.settle(2)
    want_d = [90.0 if ch == ch_step else 0.0 for ch in chans]
    want_r = [0.5 if ch == ch_step else 1.0 for ch in chans]
    compare(f"CW step on DAC{ch_step}", chk.phasors(chans), want_d, want_r)

    # all DACs at once: 45 deg * n
    chk.put(f"DAC{ch_step}:cw:amp", 0.5)
    for ch in range(n_dac):
        chk.put(f"DAC{ch}:cw:phase", 45.0 * ch)
    chk.put("DAC:apply", 1)
    chk.settle(2)
    compare("CW 45 deg * n on one apply", chk.phasors(chans), [45.0 * ch for ch in chans], [1.0] * len(chans))
    for ch in range(n_dac):
        chk.put(f"DAC{ch}:cw:phase", 0.0)
    chk.put("DAC:apply", 1)
    chk.settle(2)
    return z0


def check_nco_repeatability(chk, chans, rf_mhz):
    """Informational: per-ADC CW phase change after setting both mixers to 0 MHz and back (NCO phase at an update)."""
    za = chk.phasors(chans)
    for conv in ("dac", "adc"):
        chk.put(f"rfdc_mixer:{conv}_rf_freq_mhz", 0.0)
    chk.settle()
    for conv in ("dac", "adc"):
        chk.put(f"rfdc_mixer:{conv}_rf_freq_mhz", rf_mhz)
    chk.settle(2)
    d = wrap_deg(np.degrees(np.angle(chk.phasors(chans) / za)))
    chk.info(
        "NCO repeatability (informational): per-ADC phase change after mixers 0 and back: "
        + ", ".join(f"ADC{ch} {d[k]:+.1f}" for k, ch in enumerate(chans))
        + " deg"
    )


def check_per_dac_waveform(chk, n_dac, chans, ch_pulse, has_shared, length_ns=1000.0):
    """Single mode: a 1 us pulse on one DAC only; with a shared waveform the others play it over the whole capture."""
    set_modes(chk, n_dac, "single")
    if has_shared:
        i, q = pulse_iq(chk, 1e9)  # constant over the whole memory on every DAC
        chk.put("DAC:QWF", q)
        chk.put("DAC:IWF", i)
    i, q = pulse_iq(chk, length_ns)
    chk.put(f"DAC{ch_pulse}:QWF", q)
    chk.put(f"DAC{ch_pulse}:IWF", i)
    chk.settle(2)
    res = {ch: chk.pulse(ch) for ch in chans}
    r = res.get(ch_pulse)
    ok = r is not None and abs(r[1] - length_ns) < 50
    chk.report(
        f"DAC{ch_pulse}:IWF pulse on ADC{ch_pulse} only",
        ok,
        f"start {r[0]:.0f} ns, width {r[1]:.0f} ns (expected {length_ns:.0f})" if r else "no pulse",
    )
    if has_shared:
        long_ok = all(res[ch] is not None and res[ch][1] > 5 * length_ns for ch in chans if ch != ch_pulse)
        widths = {ch: (round(res[ch][1]) if res[ch] else None) for ch in chans if ch != ch_pulse}
        chk.report("other DACs keep the shared waveform", long_ok, f"widths (ns) {widths}")
    return r


def check_loop(chk, ch_pulse, n_captures=4):
    """Loop mode: the whole memory loops freely, so the pulse moves between captures; single mode keeps it fixed."""

    def starts(n):
        out = []
        for k in range(n):
            if k:
                chk.settle()
            r = chk.pulse(ch_pulse)
            out.append(None if r is None else round(r[0]))
        return out

    chk.put(f"DAC{ch_pulse}:mode", "loop")
    chk.put("DAC:apply", 1)
    chk.settle(2)
    rbv = chk.get(f"DAC{ch_pulse}:mode:RBV", as_string=True)
    chk.report(f"DAC{ch_pulse} loop mode active", rbv == "loop", f"mode:RBV {rbv}")
    s = starts(n_captures)
    found = [x for x in s if x is not None]
    moving = None in s or (len(found) > 1 and np.ptp(found) > 100)
    chk.report("loop: pulse position changes between captures", moving, f"pulse starts (ns) {s}")
    chk.put(f"DAC{ch_pulse}:mode", "single")
    chk.put("DAC:apply", 1)
    chk.settle(2)
    s = starts(3)
    fixed = None not in s and np.ptp(s) < 20
    chk.report("single: pulse position fixed", fixed, f"pulse starts (ns) {s}")


def main():
    parser = argparse.ArgumentParser(description="Check the DAC PVs of a running IOC (DAC n -> ADC n loopback).")
    parser.add_argument("--prefix", default="MIMO_5G_ZCU208", help="IOC PV prefix (the overlay name)")
    parser.add_argument("--rf-mhz", type=float, default=200.0, help="DAC and ADC mixer RF frequency")
    parser.add_argument("--channel", type=int, default=3, help="DAC for the single-channel checks")
    parser.add_argument("--settle", type=float, default=1.5, help="seconds to wait for fresh captures")
    parser.add_argument("--no-loopback", action="store_true", help="PV-level checks only (no loopback cables)")
    args = parser.parse_args()

    chk = IocDacCheck(args.prefix, settle_s=args.settle)
    if not chk.exists("DSP:TWF"):
        sys.exit(f"no IOC with prefix {args.prefix} (DSP:TWF not found)")
    chk.t_dsp = np.asarray(chk.get("DSP:TWF"), dtype=float)
    n_adc = chk.count_channels("ADC{}:IWF")
    n_dac = chk.count_channels("rfdc_mixer:DAC{}:rf_freq_mhz")
    has_shared = chk.exists("DAC:IWF")
    per_dac = chk.exists("DAC0:mode") and chk.exists("DAC:apply")
    chans = list(range(min(n_adc, n_dac)))
    ch = min(args.channel, n_dac - 1)
    print(
        f"{args.prefix}: {n_adc} ADCs, {n_dac} DACs, shared DAC waveform: {'yes' if has_shared else 'no'}, "
        f"per-DAC generators: {'yes' if per_dac else 'no'}; loopback DAC n -> ADC n: {not args.no_loopback}"
    )

    # state to restore
    saved_rf = {c: chk.get(f"rfdc_mixer:{c}_rf_freq_mhz:RBV") for c in ("dac", "adc")}
    saved_wfm = {p: np.array(chk.get(f"DAC:{p}WF")) for p in ("I", "Q")} if has_shared else None
    saved_cw = {(n, k): chk.get(f"DAC{n}:cw:{k}") for n in range(n_dac) for k in ("amp", "phase") if per_dac}
    try:
        for c in ("dac", "adc"):
            chk.put(f"rfdc_mixer:{c}_rf_freq_mhz", args.rf_mhz)
        if per_dac:
            set_modes(chk, n_dac, "single")
        chk.settle(2)
        if has_shared and not args.no_loopback:
            check_shared_waveform(chk, chans)
        if per_dac:
            check_cw(chk, n_dac, chans, ch, loopback=not args.no_loopback)
            if not args.no_loopback:
                check_nco_repeatability(chk, chans, args.rf_mhz)
                if check_per_dac_waveform(chk, n_dac, chans, ch, has_shared) is not None:
                    check_loop(chk, ch)
            else:
                set_modes(chk, n_dac, "loop")
                chk.settle()
                rbv = [chk.get(f"DAC{n}:mode:RBV", as_string=True) for n in range(n_dac)]
                chk.report("loop mode active on all DACs", all(r == "loop" for r in rbv), f"mode:RBV {rbv}")
    finally:
        print("  restoring the IOC state")
        if per_dac:
            for (n, k), v in saved_cw.items():
                chk.put(f"DAC{n}:cw:{k}", v)
            set_modes(chk, n_dac, "single")
        if saved_wfm is not None:
            chk.put("DAC:QWF", saved_wfm["Q"])
            chk.put("DAC:IWF", saved_wfm["I"])
        for c, v in saved_rf.items():
            chk.put(f"rfdc_mixer:{c}_rf_freq_mhz", v)

    failed = [name for name, ok in chk.results if not ok]
    print(f"\n{len(chk.results) - len(failed)}/{len(chk.results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
