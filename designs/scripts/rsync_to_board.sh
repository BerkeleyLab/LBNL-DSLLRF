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
# mimo_mts/overlays/<board>/.
set -euo pipefail

if [[ $# -lt 1 || $1 == -h || $1 == --help ]]; then
    sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
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

echo "Syncing $repo/ -> $user@$board_ip:$dest"
cd "$repo"
rsync -avz \
    --include '.git/' \
    --exclude '.*/' \
    --exclude '*.egg-info' \
    --exclude '__pycache__/' \
    --exclude '*_xilinx*/' \
    "$@" \
    ./ "$user@$board_ip:$dest"
