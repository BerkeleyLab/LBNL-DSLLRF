#!/usr/bin/env python3
"""
Summarize Vivado implementation reports of an overlay build as JSON.

Reads from <...>.runs/impl_1/:
  *_timing_summary_routed.rpt  design timing summary and per-clock (intra-clock) slack
  *_utilization_placed.rpt     used / available / util% for every resource
  *_power_routed.rpt           on-chip power and junction temperature
  *datasheet*.rpt              data sheet: I/O setup/hold, clock-to-out, setup between clocks, ...

Usage: vivado_reports.py <path> [-o report.json] [--junit timing.xml]
  <path> is a design directory (designs/ZCU208/base), its _xilinx/ directory, the impl_1 directory,
  or an unpacked CI artifact containing designs/<BOARD>/<design>/_xilinx/. Prints JSON to stdout
  unless -o is given. --junit writes a JUnit XML test report (one test case: timing met or not, with
  slack and utilization) for GitLab's merge-request test summary. Exit code 0 also when timing fails.
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def find_impl_dir(path: Path) -> Path:
    if list(path.glob("*_timing_summary_routed.rpt")):
        return path
    if (path / "_xilinx").is_dir():  # a design directory: use the current build, not backups like _xilinx.prev
        path = path / "_xilinx"
    found = sorted(path.glob("**/impl_1/*_timing_summary_routed.rpt"))
    if not found:
        sys.exit(f"no impl_1/*_timing_summary_routed.rpt under {path}")
    if len({f.parent for f in found}) > 1:
        sys.exit(f"several builds under {path}; pass one of: {sorted({str(f.parent) for f in found})}")
    return found[0].parent


def report(impl: Path, suffix: str) -> list[str] | None:
    files = sorted(impl.glob(f"*_{suffix}.rpt"))
    return files[0].read_text(errors="replace").splitlines() if files else None


def number(text: str) -> float | int | None:
    """'3.464' -> 3.464, '42019' -> 42019, '<0.01' -> 0.01, '' -> None"""
    text = text.strip().lstrip("<")
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return None


def header_field(lines: list[str], name: str) -> str | None:
    for line in lines[:20]:
        m = re.match(rf"\|\s*{re.escape(name)}\s*:\s*(.*)", line)
        if m:
            return m.group(1).strip()
    return None


def fixed_width_table(lines: list[str], start: int, label: bool) -> list[list[str]]:
    """
    Parse a Vivado fixed-width table whose header is at lines[start] and dashes at lines[start + 1],
    until the first blank line. Returns the header cells followed by the row cells.

    Values are right-aligned so that they end at their column's dashes, and a cell may be empty. With
    label=True the first column is a left-aligned name (e.g. a clock) that can be wider than its dashes,
    so it is read as the row's first word and the value columns start after it.
    """
    spans = [m.span() for m in re.finditer(r"-+", lines[start + 1])]
    ends: list[int | None] = [b for _, b in spans[:-1]] + [None]  # the last column runs to the end of the line
    begins = [0] + [b for _, b in spans[:-1]]

    header = [lines[start][a:b].strip() for a, b in zip(begins, ends, strict=True)]
    table = [header]
    for line in lines[start + 2 :]:
        if not line.strip():
            break
        cells = []
        label_end = 0
        if label:
            name = line.split()[0]
            label_end = line.index(name) + len(name)
            cells.append(name)
        for i in range(1 if label else 0, len(spans)):
            words = line[max(begins[i], label_end) : ends[i]].split()
            cells.append(words[-1] if words else "")
        table.append(cells)
    return table


def section_start(lines: list[str], title: str) -> int | None:
    """Index of the column-header line of a '| <title>' section, or None."""
    for i, line in enumerate(lines):
        if line.strip() == f"| {title}":
            for j in range(i + 1, min(i + 10, len(lines) - 1)):
                header = lines[j].strip()
                if header and header[0] not in "|-" and lines[j + 1].lstrip().startswith("---"):
                    return j
    return None


SLACK_KEYS = {
    "WNS(ns)": "wns_ns",
    "TNS(ns)": "tns_ns",
    "TNS Failing Endpoints": "tns_failing_endpoints",
    "TNS Total Endpoints": "tns_total_endpoints",
    "WHS(ns)": "whs_ns",
    "THS(ns)": "ths_ns",
    "THS Failing Endpoints": "ths_failing_endpoints",
    "THS Total Endpoints": "ths_total_endpoints",
    "WPWS(ns)": "wpws_ns",
    "TPWS(ns)": "tpws_ns",
    "TPWS Failing Endpoints": "tpws_failing_endpoints",
    "TPWS Total Endpoints": "tpws_total_endpoints",
}


def parse_timing(lines: list[str]) -> dict:
    timing: dict = {"met": any("All user specified timing constraints are met." in line for line in lines)}

    i = section_start(lines, "Design Timing Summary")
    if i is not None:
        header, values = fixed_width_table(lines, i, label=False)[:2]
        timing.update({SLACK_KEYS[h]: number(v) for h, v in zip(header, values, strict=True) if h in SLACK_KEYS})

    clocks: dict[str, dict] = {}
    i = section_start(lines, "Clock Summary")
    if i is not None:
        for name, _waveform, period, freq in fixed_width_table(lines, i, label=True)[1:]:
            clocks[name] = {"period_ns": number(period), "freq_mhz": number(freq)}
    i = section_start(lines, "Intra Clock Table")
    if i is not None:
        header, *rows = fixed_width_table(lines, i, label=True)
        for row in rows:
            slack = {SLACK_KEYS[h]: number(v) for h, v in zip(header[1:], row[1:], strict=True) if h in SLACK_KEYS}
            clocks.setdefault(row[0], {}).update({k: v for k, v in slack.items() if v is not None})
    timing["clocks"] = clocks
    return timing


def parse_utilization(lines: list[str]) -> dict:
    """{site type: {used, available, util_pct, section}} from every 'Site Type | Used | ... | Util%' table."""
    util: dict[str, dict] = {}
    section = ""
    header: list[str] | None = None
    for line in lines:
        if re.match(r"^\d+\. \S", line):
            section, header = line.split(". ", 1)[1].strip(), None
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if "Used" in cells and "Available" in cells and "Util%" in cells:
            header = cells
            continue
        if header is None or len(cells) != len(header) or not cells[0]:
            continue
        row = dict(zip(header, cells, strict=True))
        name = cells[0]
        if name not in util:  # keep the first occurrence (later sections repeat some rows)
            util[name] = {
                "used": number(row["Used"]),
                "available": number(row["Available"]),
                "util_pct": number(row["Util%"]),
                "section": section,
            }
    return util


POWER_KEYS = {
    "Total On-Chip Power (W)": "total_w",
    "Dynamic (W)": "dynamic_w",
    "Device Static (W)": "static_w",
    "Junction Temperature (C)": "junction_temp_c",
    "Confidence Level": "confidence",
}


def parse_power(lines: list[str]) -> dict:
    power = {}
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] in POWER_KEYS and POWER_KEYS[cells[0]] not in power:
            value = number(cells[1])
            power[POWER_KEYS[cells[0]]] = value if value is not None else cells[1]
    return power


def parse_datasheet(lines: list[str]) -> dict[str, list[dict]]:
    """
    {section title: [row dict]} from report_datasheet tables. Tables are '+'/'|'-separated with a two-line
    header; header lines are joined per column, and each 'Process Corner' column is named after the value
    column before it. Numeric cells become numbers; cells such as '0.347 (r)' stay text.
    """
    sections: dict[str, list[dict]] = {}
    title = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() and not line.startswith(("|", "-")) and "|" not in line and i + 2 < len(lines):
            title = line.strip()
        if re.match(r"^-+\+", line) and title and i + 3 < len(lines):
            head = [[c.strip() for c in lines[i + k].split("|")] for k in (1, 2)]
            names: list[str] = []
            for top, bottom in zip(*head, strict=False):
                name = f"{top} {bottom}".strip()
                if name == "Process Corner" and names:
                    name = f"{names[-1]} corner"
                names.append(name)
            rows = []
            i += 4  # past the two header lines and the separator below them
            while i < len(lines) and not re.match(r"^-+\+", lines[i]):
                cells = [c.strip() for c in lines[i].split("|")]
                row = {}
                for name, cell in zip(names, cells, strict=False):
                    if name:
                        value = number(cell)
                        row[name] = value if value is not None else (cell or None)
                rows.append(row)
                i += 1
            sections[title] = rows
            title = None
        i += 1
    return sections


def summarize(path: Path) -> dict:
    impl = find_impl_dir(path)
    timing_rpt = report(impl, "timing_summary_routed") or []
    summary: dict = {"impl_dir": str(impl)}
    # designs/<BOARD>/<design>/_xilinx/<design>/<design>.runs/impl_1
    parts = impl.resolve().parts
    if "_xilinx" in parts:
        k = parts.index("_xilinx")
        summary["board"], summary["design"] = parts[k - 2], parts[k - 1]
    summary["device"] = header_field(timing_rpt, "Device")
    summary["tool"] = header_field(timing_rpt, "Tool Version")
    summary["timing"] = parse_timing(timing_rpt)
    util = report(impl, "utilization_placed")
    summary["utilization"] = parse_utilization(util) if util else {}
    power = report(impl, "power_routed")
    summary["power"] = parse_power(power) if power else {}
    datasheet = sorted(impl.glob("*datasheet*.rpt"))
    summary["datasheet"] = parse_datasheet(datasheet[0].read_text(errors="replace").splitlines()) if datasheet else {}
    return summary


UTIL_SUMMARY = ("CLB LUTs", "CLB Registers", "Block RAM Tile", "URAM", "DSPs")


def junit(summary: dict) -> ET.ElementTree:
    """One JUnit test case per build: 'timing' fails when the timing constraints are not met."""
    name = f"{summary.get('board', '?')}/{summary.get('design', '?')}"
    t = summary["timing"]
    slack = f"WNS {t.get('wns_ns')} ns, TNS {t.get('tns_ns')} ns ({t.get('tns_failing_endpoints')} failing), "
    slack += f"WHS {t.get('whs_ns')} ns, WPWS {t.get('wpws_ns')} ns"

    out = [f"{name}: {summary.get('device')}", f"timing: {slack}"]
    for clock, c in t.get("clocks", {}).items():
        if c.get("wns_ns") is not None or c.get("whs_ns") is not None:
            out.append(f"  {clock}: {c.get('freq_mhz')} MHz, WNS {c.get('wns_ns')} ns, WHS {c.get('whs_ns')} ns")
    util = summary.get("utilization", {})
    out.append(
        "utilization: "
        + ", ".join(f"{k} {util[k]['used']} ({util[k]['util_pct']}%)" for k in UTIL_SUMMARY if k in util)
    )
    if summary.get("power"):
        out.append(f"power: {summary['power'].get('total_w')} W")

    suite = ET.Element("testsuite", name=name, tests="1", failures="0" if t["met"] else "1")
    case = ET.SubElement(suite, "testcase", classname=name, name="timing")
    if not t["met"]:
        ET.SubElement(case, "failure", message=f"timing not met: {slack}").text = slack
    ET.SubElement(case, "system-out").text = "\n".join(out)
    return ET.ElementTree(suite)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Vivado implementation reports as JSON.")
    parser.add_argument("path", type=Path, help="design dir, _xilinx/, impl_1/, or unpacked CI artifact")
    parser.add_argument("-o", "--output", type=Path, help="write JSON here instead of stdout")
    parser.add_argument("--junit", type=Path, help="also write a JUnit XML timing test report here")
    args = parser.parse_args()

    summary = summarize(args.path)
    text = json.dumps(summary, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        sys.stdout.write(text)
    if args.junit:
        tree = junit(summary)
        ET.indent(tree)
        tree.write(args.junit, encoding="utf-8", xml_declaration=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
