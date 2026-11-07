#!/usr/bin/env bash
# Synchronize this repository's working tree to a PYNQ board, so the board can run the
# current code and overlays without internet access or a git pull.
#
# Usage: rsync_to_board.sh <board_ip> [user] [dest_dir] [extra rsync options...]
#   user      default: xilinx
#   dest_dir  default: ~/jupyter_notebooks/pynq_llrf/
#   e.g. rsync_to_board.sh 192.168.2.99 xilinx '~/jupyter_notebooks/pynq_llrf/' --dry-run
#
# Works from any directory: the source is always the repository containing this script.
# Not copied: dot-directories except .git (e.g. .venv, .ruff_cache), *.egg-info, __pycache__,
# and Vivado build directories (*_xilinx*/). Built overlays reach the board through
# mimo_mts/overlays/<board>/; board overlays are never deleted, and only replaced by newer
# local files (the replaced file is kept as <name>.prev).
set -euo pipefail

if [[ $# -lt 1 || $1 == -h || $1 == --help ]]; then
    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
fi

board_ip=$1
user=${2:-xilinx}
dest=${3:-'~/jupyter_notebooks/pynq_llrf/'}
shift $(($# < 3 ? $# : 3))

command -v rsync >/dev/null || { echo "rsync is not installed (e.g. sudo apt install rsync)" >&2; exit 1; }

# Repository root: two levels above designs/scripts/, checked so we never sync the wrong tree
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
if [[ ! -f $repo/dir_list.mk || ! -d $repo/mimo_mts || ! -d $repo/designs ]]; then
    echo "error: $repo does not look like the pynq_llrf repository" >&2
    exit 1
fi

cd "$repo"

echo "Syncing $repo/ -> $user@$board_ip:$dest (code; overlays in a second pass)"
rsync -avz \
    --include '.git/' \
    --exclude '.*/' \
    --exclude '*.egg-info' \
    --exclude '__pycache__/' \
    --exclude '*_xilinx*/' \
    --exclude '/mimo_mts/overlays/' \
    "$@" \
    ./ "$user@$board_ip:$dest"

# Overlays (.bit/.hwh/.dtbo) on the board may be newer than local ones (e.g. CI builds copied
# there). Never delete them (no --delete), replace one only when the local file is newer
# (--update), and keep the replaced file as <name>.prev (--backup).
overlays_dest="${dest%/}/mimo_mts/overlays/"
echo "Syncing overlays -> $user@$board_ip:$overlays_dest (newer files only, replaced ones kept as *.prev)"
rsync -avz --update --backup --suffix=.prev \
    --exclude '__pycache__/' \
    --exclude '*.prev' \
    "$@" \
    mimo_mts/overlays/ "$user@$board_ip:$overlays_dest"
