#!/usr/bin/env bash
# Render the placement graph as a real mermaid flowchart (SVG + PNG).
#
# mermaid's flowchart renderer is dagre; we also drive dagre directly
# (engines/dagre.mjs) so the layout insight is available without a browser.
# This script uses mermaid-cli + a Chromium shipped as an npm tarball.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd ../.. && pwd)"
OUT="$ROOT/build/layout"
PY=/opt/eda/venv/bin/python

$PY mermaid.py "$OUT/graph.json" "$OUT/graph.mmd"
node engines/mmconf.mjs > /tmp/opencode/mm-puppeteer.json
node_modules/.bin/mmdc -p /tmp/opencode/mm-puppeteer.json \
  -i "$OUT/graph.mmd" -o "$OUT/mermaid.svg" -t dark
echo "wrote $OUT/mermaid.svg"
