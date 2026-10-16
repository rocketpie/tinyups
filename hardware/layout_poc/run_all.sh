#!/usr/bin/env bash
# Run every PoC layout engine and render each to build/layout/*.png|svg.
#
#   ./run_all.sh              # all engines
#   ./run_all.sh d3force      # just one
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd ../.. && pwd)"
OUT="$ROOT/build/layout"
PY=/opt/eda/venv/bin/python
mkdir -p "$OUT"

only="${1:-all}"
run() { [ "$only" = all ] || [ "$only" = "$1" ]; }

render() {          # render() <name>
  $PY legalize.py "$OUT/pos-$1.json" "$OUT/leg-$1.json" >/dev/null
  $PY render.py "$OUT/leg-$1.json" "$OUT/$1.png" --label
  $PY render.py "$OUT/leg-$1.json" "$OUT/$1.svg"
}

if run d3force; then
  ITERS="${ITERS:-1200}" CHARGE="${CHARGE:-30}" \
    node engines/d3force.mjs "$OUT/graph.json" "$OUT/raw-d3force.json"
  $PY fitpos.py "$OUT/raw-d3force.json" "$OUT/pos-d3force.json" --keep-scale >/dev/null
  render d3force
fi

if run d3force-incr; then
  node engines/d3force_incremental.mjs "$OUT/graph.json" "$OUT/raw-d3force-incr.json"
  $PY fitpos.py "$OUT/raw-d3force-incr.json" "$OUT/pos-d3force-incr.json" --keep-scale >/dev/null
  render d3force-incr
fi

if run dagre; then
  RANKDIR="${RANKDIR:-LR}" node engines/dagre.mjs "$OUT/graph.json" "$OUT/raw-dagre.json"
  $PY fitpos.py "$OUT/raw-dagre.json" "$OUT/pos-dagre.json" >/dev/null
  render dagre
fi

if run elk; then
  DIRECTION="${DIRECTION:-RIGHT}" node engines/elk.mjs "$OUT/graph.json" "$OUT/raw-elk.json"
  $PY fitpos.py "$OUT/raw-elk.json" "$OUT/pos-elk.json" >/dev/null
  render elk
fi

if run graphviz; then
  for eng in sfdp neato dot; do
    GV_ENGINE=$eng $PY engines/graphviz.py "$OUT/graph.json" "$OUT/raw-gv-$eng.json" $eng
    $PY fitpos.py "$OUT/raw-gv-$eng.json" "$OUT/pos-gv-$eng.json" >/dev/null
    render gv-$eng
  done
fi
