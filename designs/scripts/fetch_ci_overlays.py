#!/usr/bin/env python3
"""
Download overlays built by a GitLab CI pipeline into mimo_mts/overlays/<board>/.

For every successful synthesis job of the pipeline, extract <overlay>.bit and <overlay>.hwh from its
artifacts (designs/<BOARD>/<overlay>/_xilinx/) to mimo_mts/overlays/<board in lowercase>/, the paths used
by mimo_mts/config.py. A local file that is replaced is kept as <name>.prev; identical files are skipped.
Can be re-run while the pipeline is still building. Then sync to a board with `make rsync`.

Usage: fetch_ci_overlays.py <pipeline_id> [--dry-run] [--host gitlab.lbl.gov] [--project llrf-projects/pynq_llrf]
Needs `glab`, authenticated to the GitLab host (glab auth login --hostname <host>).
"""

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[2]
OVERLAY_DIR = REPO / "mimo_mts" / "overlays"
# designs/<BOARD>/<overlay>/_xilinx/<overlay>.(bit|hwh)
MEMBER = re.compile(r"^designs/(?P<board>[^/]+)/(?P<overlay>[^/]+)/_xilinx/(?P=overlay)\.(?P<ext>bit|hwh)$")


def glab_api(host: str, endpoint: str) -> bytes:
    result = subprocess.run(["glab", "api", "--hostname", host, endpoint], capture_output=True, check=False)
    if result.returncode != 0:
        sys.exit(f"glab api {endpoint} failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Download CI-built overlays into mimo_mts/overlays/<board>/.")
    parser.add_argument("pipeline", type=int, help="pipeline id, e.g. from the MR's Pipelines tab")
    parser.add_argument("-n", "--dry-run", action="store_true", help="only list what would be written")
    parser.add_argument("--host", default="gitlab.lbl.gov")
    parser.add_argument("--project", default="llrf-projects/pynq_llrf")
    args = parser.parse_args()

    if shutil.which("glab") is None:
        sys.exit("glab is not installed (https://gitlab.com/gitlab-org/cli)")
    if not (REPO / "dir_list.mk").is_file() or not OVERLAY_DIR.is_dir():
        sys.exit(f"{REPO} does not look like the pynq_llrf repository")

    project = quote(args.project, safe="")
    jobs = json.loads(glab_api(args.host, f"projects/{project}/pipelines/{args.pipeline}/jobs?per_page=100"))
    synth = [j for j in jobs if j["name"].startswith("bitfile_synthesis")]
    if not synth:
        sys.exit(f"pipeline {args.pipeline}: no synthesis jobs")

    written = 0
    for job in sorted(synth, key=lambda j: j["name"]):
        has_archive = any(a["file_type"] == "archive" for a in job.get("artifacts", []))
        if job["status"] != "success" or not has_archive:
            print(f"{'skip':8s}{job['name']}: {job['status']}")
            continue
        archive = zipfile.ZipFile(io.BytesIO(glab_api(args.host, f"projects/{project}/jobs/{job['id']}/artifacts")))
        members = [(m, MEMBER.match(m)) for m in archive.namelist()]
        members = [(m, match) for m, match in members if match]
        if not members:
            print(f"{'skip':8s}{job['name']}: no .bit/.hwh in artifacts")
        for name, match in members:
            dest = OVERLAY_DIR / match["board"].lower() / f"{match['overlay']}.{match['ext']}"
            data = archive.read(name)
            if dest.exists() and md5(dest.read_bytes()) == md5(data):
                print(f"{'same':8s}{dest.relative_to(REPO)}")
                continue
            action = "update" if dest.exists() else "new"
            print(f"{action:8s}{dest.relative_to(REPO)}  ({job['name']}, job {job['id']})")
            if args.dry_run:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest.replace(dest.with_name(dest.name + ".prev"))
            dest.write_bytes(data)
            written += 1

    print(f"{written} file(s) written to {OVERLAY_DIR.relative_to(REPO)}/" + (" (dry run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
