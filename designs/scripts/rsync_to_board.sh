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
# Copies what git considers the working tree: tracked files and untracked files that .gitignore
# does not exclude, plus .git. Ignored files (sim_build/, _xilinx/, .venv, caches, ...) and the
# bedrock submodule (RTL for building overlays only) stay local. Built overlays reach the board through
# mimo_mts/overlays/<board>/; board overlays are never deleted, and only replaced by newer
# local files (the replaced file is kept as <name>.prev). Nothing on the board is deleted.
set -euo pipefail

if [[ $# -lt 1 || $1 == -h || $1 == --help ]]; then
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
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

command -v git >/dev/null || { echo "git is not installed" >&2; exit 1; }

# Files of the working tree as git sees it, NUL-separated: untracked but not ignored, and tracked.
# Submodules (bedrock) appear as a single directory entry and arrive as an empty, uninitialized
# submodule: the board only runs Python, it does not build RTL.
working_tree_files() {
    git ls-files -z --others --exclude-standard
    git ls-files -z
}

echo "Syncing $repo/ -> $user@$board_ip:$dest (files git does not ignore; then .git; then overlays)"
# --ignore-missing-args: tracked files deleted in the working tree are skipped, not an error
working_tree_files | rsync -avz --from0 --files-from=- --ignore-missing-args "$@" \
    ./ "$user@$board_ip:$dest"
rsync -az --exclude '/modules/' "$@" .git/ "$user@$board_ip:${dest%/}/.git/"

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
