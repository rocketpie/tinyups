#!/usr/bin/env bash
# Run every PoC layout engine and render each to build/layout/*.png|svg.
#
#   ./run_all.sh            # all engines
#   ./run_all.sh d3force    # just one
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd ../.. && pwd)"
OUT="$ROOT/build/layout"
PY=/opt/eda/venv/bin/python
mkdir -p "$OUT"

export DROP_GROUND="${DROP_GROUND:-1}"

only="${1:-all}"
run() { [ "$only" = all ] || [ "$only" = "$1" ]; }

if run d3force; then
  ITERS="${ITERS:-1200}" CHARGE="${CHARGE:-30}" \
    node engines/d3force.mjs "$OUT/graph.json" "$OUT/raw-d3force.json"
  $PY fitpos.py "$OUT/raw-d3force.json" "$OUT/pos-d3force.json" >/dev/null
  $PY legalize.py "$OUT/pos-d3force.json" "$OUT/leg-d3force.json" >/dev/null
  $PY render.py "$OUT/leg-d3force.json" "$OUT/d3force.png" --label
  $PY render.py "$OUT/leg-d3force.json" "$OUT/d3force.svg"
fi

if run dagre; then
  RANKDIR="${RANKDIR:-LR}" node engines/dagre.mjs "$OUT/graph.json" "$OUT/raw-dagre.json"
  $PY fitpos.py "$OUT/raw-dagre.json" "$OUT/pos-dagre.json" >/dev/null
  $PY legalize.py "$OUT/pos-dagre.json" "$OUT/leg-dagre.json" >/dev/null
  $PY render.py "$OUT/leg-dagre.json" "$OUT/dagre.png" --label
  $PY render.py "$OUT/leg-dagre.json" "$OUT/dagre.svg"
fi

if run elk; then
  DIRECTION="${DIRECTION:-RIGHT}" node engines/elk.mjs "$OUT/graph.json" "$OUT/raw-elk.json"
  $PY fitpos.py "$OUT/raw-elk.json" "$OUT/pos-elk.json" >/dev/null
  $PY legalize.py "$OUT/pos-elk.json" "$OUT/leg-elk.json" >/dev/null
  $PY render.py "$OUT/leg-elk.json" "$OUT/elk.png" --label
  $PY render.py "$OUT/leg-elk.json" "$OUT/elk.svg"
fi

if run graphviz; then
  for eng in sfdp neato dot; do
    GV_ENGINE=$eng $PY engines/graphviz.py "$OUT/graph.json" "$OUT/raw-gv-$eng.json" $eng
    $PY fitpos.py "$OUT/raw-gv-$eng.json" "$OUT/pos-gv-$eng.json" >/dev/null
    $PY legalize.py "$OUT/pos-gv-$eng.json" "$OUT/leg-gv-$eng.json" >/dev/null
    $PY render.py "$OUT/leg-gv-$eng.json" "$OUT/gv-$eng.png" --label
    $PY render.py "$OUT/leg-gv-$eng.json" "$OUT/gv-$eng.svg"
  done
fi
