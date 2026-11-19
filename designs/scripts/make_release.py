"""
Collect the overlays built in a CI pipeline and publish them as a GitLab release (run by the release_overlays job on a
tag pipeline).

The synthesis jobs leave designs/<BOARD>/<overlay>/_xilinx/<overlay>.{bit,hwh} and <overlay>_report.json (from
vivado_reports.py). This script copies them to release/<board>/ (the layout of mimo_mts/overlays/<board>/), writes
SHA256SUMS and release notes with the timing of each overlay, and creates the release for $CI_COMMIT_TAG with a link to
every file in the job's artifacts. Standard library only.

    python3 designs/scripts/make_release.py                 # in CI (uses the CI_* variables)
    python3 designs/scripts/make_release.py --dry-run       # locally: collect and print, do not publish
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "release"


def collect():
    """Copy every built overlay to release/<board>/; returns a list of (board, overlay, files, report)."""
    found = []
    for bit in sorted(ROOT.glob("designs/*/*/_xilinx/*.bit")):
        overlay = bit.stem
        board = bit.parents[2].name
        hwh = bit.with_suffix(".hwh")
        if bit.parent.parent.name != overlay or not hwh.exists():
            continue
        dest = OUT / board.lower()
        dest.mkdir(parents=True, exist_ok=True)
        files = []
        for src in (bit, hwh, bit.parent / f"{overlay}_report.json"):
            if src.exists():
                shutil.copy2(src, dest / src.name)
                files.append(dest / src.name)
        report = None
        if (dest / f"{overlay}_report.json").exists():
            report = json.loads((dest / f"{overlay}_report.json").read_text())
        found.append((board, overlay, files, report))
    return found


def checksums(found):
    lines = []
    for _, _, files, _ in found:
        for f in files:
            lines.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(OUT)}")
    (OUT / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def notes(found, tag):
    rows = ["| Board | Overlay | Timing | WNS [ns] | WHS [ns] |", "|---|---|---|---|---|"]
    for board, overlay, _, report in found:
        t = (report or {}).get("timing", {})
        met = {True: "met", False: "**FAILED**"}.get(t.get("met"), "no report")
        rows.append(f"| {board} | `{overlay}` | {met} | {t.get('wns_ns', '')} | {t.get('whs_ns', '')} |")
    return (
        f"Overlays built by CI for `{tag}`. Copy `<board>/<overlay>.{{bit,hwh}}` to `mimo_mts/overlays/<board>/` on "
        "the board (see README). `SHA256SUMS` lists the file checksums; `<overlay>_report.json` holds timing, "
        "utilization and power.\n\n" + "\n".join(rows) + "\n"
    )


def publish(found, tag, description):
    api, project, job_id = os.environ["CI_API_V4_URL"], os.environ["CI_PROJECT_ID"], os.environ["CI_JOB_ID"]
    base = f"{os.environ['CI_PROJECT_URL']}/-/jobs/{job_id}/artifacts"
    links = [{"name": "All overlays (zip)", "url": f"{base}/download", "link_type": "package"}]
    for _, _, files, _ in found:
        for f in files:
            rel = f.relative_to(OUT)
            links.append({"name": str(rel), "url": f"{base}/raw/release/{rel}", "link_type": "other"})
    links.append({"name": "SHA256SUMS", "url": f"{base}/raw/release/SHA256SUMS", "link_type": "other"})
    body = {"name": tag, "tag_name": tag, "description": description, "assets": {"links": links}}
    req = urllib.request.Request(
        f"{api}/projects/{project}/releases",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "JOB-TOKEN": os.environ["CI_JOB_TOKEN"]},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"release {tag} created: HTTP {resp.status}")


def main():
    parser = argparse.ArgumentParser(description="Collect CI-built overlays and publish a GitLab release.")
    parser.add_argument("--dry-run", action="store_true", help="collect and print the notes, do not publish")
    args = parser.parse_args()

    if OUT.exists():
        shutil.rmtree(OUT)
    found = collect()
    if not found:
        print("no built overlays found under designs/*/*/_xilinx/", file=sys.stderr)
        return 1
    checksums(found)
    tag = os.environ.get("CI_COMMIT_TAG", "untagged")
    description = notes(found, tag)
    (OUT / "RELEASE_NOTES.md").write_text(description)
    print(description)
    if not args.dry_run:
        publish(found, tag, description)
    return 0


if __name__ == "__main__":
    sys.exit(main())
