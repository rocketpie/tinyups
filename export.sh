#!/bin/bash
# run this on the working copy side.
# exports the (modified) working copy to master
# .git and node_modules are never synced.
set -e
cd "$(dirname "$0")"
dst="${GIT_WORKSPACE_ROOT:?export GIT_WORKSPACE_ROOT first}/$(basename "$PWD")"
[ "$PWD" != "$(readlink -f "$dst")" ] || {
    echo "export.sh: refusing to sync $PWD onto itself (src == dst)" >&2; exit 1; }
rsync -a --delete --exclude=.git --exclude=node_modules --info=progress2 ./ "$dst/"
