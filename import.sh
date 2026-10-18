#!/bin/bash
# run this on the working copy side.
# resets the working copy to the master state
# node_modules is never synced.
set -e
cd "$(dirname "$0")"
src="${GIT_WORKSPACE_ROOT:?export GIT_WORKSPACE_ROOT first}/$(basename "$PWD")"
[ "$PWD" != "$(readlink -f "$src")" ] || {
    echo "import.sh: refusing to sync $src onto itself (src == dst)" >&2; exit 1; }

# export.sh does not sync .git. 
# any commit in the container is about to be discarded.
if command -v git >/dev/null && [ -e .git/HEAD ]; then
    head=$(git -C . rev-parse --verify -q HEAD 2>/dev/null || true)
    [ -z "$head" ] || git -C "$src" cat-file -e "$head" 2>/dev/null ||
        echo "import.sh: note: ./.git holds commits master does not; rsync --delete drops them." >&2
fi

rsync -a --delete --exclude=node_modules --info=progress2 "$src/" ./
