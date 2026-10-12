#!/bin/bash
cd "$(dirname "$0")"
rsync -a --delete --exclude=.git "${GIT_WORKSPACE_ROOT:?}/$(basename "$PWD")/" .
