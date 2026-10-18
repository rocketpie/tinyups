// PoC engine: dagre — the layered engine behind mermaid flowcharts.
//
// mermaid's `flowchart` renderer is dagre (Sugiyama-style layered layout) with
// straight/bezier edges.  We drive dagre directly (no browser needed) with the
// same graph: components = nodes, nets = links, edge weight = trace width so
// the wide power nets pull their parts onto adjacent ranks.
//
// Usage: node engines/dagre.mjs <graph.json> <out.json>
import fs from "node:fs";
import dagre from "@dagrejs/dagre";

const [graphPath, outPath] = process.argv.slice(2);
const G = JSON.parse(fs.readFileSync(graphPath, "utf8"));
const P = (k, d) => (process.env[k] !== undefined ? +process.env[k] : d);

const RANKDIR = process.env.RANKDIR || "LR";
const NODESEP = P("NODESEP", 8);
const RANKSEP = P("RANKSEP", 26);
const WREF = 18.71;

const g = new dagre.graphlib.Graph({ multigraph: true });
g.setGraph({
  rankdir: RANKDIR,
  nodesep: NODESEP,
  ranksep: RANKSEP,
  ranker: "network-simplex",
  marginx: 5,
  marginy: 5,
});
g.setDefaultEdgeLabel(() => ({}));

for (const n of G.nodes) g.setNode(n.id, { width: n.w, height: n.h });

for (const [i, e] of G.edges.entries()) {
  // wide nets: high weight (adjacent ranks), short minlen
  const weight = e.weight * (1 + 8 * (e.width / WREF) ** 1.2);
  const minlen = e.width > 6 ? 1 : 2;
  g.setEdge(e.source, e.target, { weight, minlen, width: e.width }, "e" + i);
}

dagre.layout(g);
const positions = {};
for (const n of G.nodes) {
  const c = g.node(n.id);
  positions[n.id] = { x: c.x, y: c.y, angle: 0 };
}
fs.writeFileSync(outPath, JSON.stringify({
  engine: "dagre",
  params: { RANKDIR, NODESEP, RANKSEP },
  positions,
}, null, 1));
console.log(`dagre: ${g.nodeCount()} nodes, ${g.edgeCount()} edges, rankdir ${RANKDIR} -> ${outPath}`);
