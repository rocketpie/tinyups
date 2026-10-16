#!/bin/bash
# run this on the working copy side.
# resets the working copy to the master state
# .git and node_modules are never synced.
set -e
cd "$(dirname "$0")"
src="${GIT_WORKSPACE_ROOT:?export GIT_WORKSPACE_ROOT first}/$(basename "$PWD")"
[ "$PWD" != "$(readlink -f "$src")" ] || {
    echo "import.sh: refusing to sync $src onto itself (src == dst)" >&2; exit 1; }
rsync -a --delete --exclude=.git --exclude=node_modules --info=progress2 "$src/" ./
