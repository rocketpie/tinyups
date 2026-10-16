// PoC engine: Eclipse Layout Kernel (ELK) via elkjs — open-source layered
// layout with *orthogonal* edge routing (the open equivalent of yFiles' and
// yFiles' orthogonal layout).  ELK returns both node coordinates and the
// bend points of the orthogonal edge routes, so the result is not just a
// placement but a routing sketch.
//
// Usage: node engines/elk.mjs <graph.json> <out.json>
import fs from "node:fs";
import ELK from "elkjs/lib/elk.bundled.js";

const [graphPath, outPath] = process.argv.slice(2);
const G = JSON.parse(fs.readFileSync(graphPath, "utf8"));
const P = (k, d) => (process.env[k] !== undefined ? +process.env[k] : d);

const DIRECTION = process.env.DIRECTION || "RIGHT";
const NODE_NODE = P("NODE_NODE", 8);         // mm between nodes in a layer
const NODE_LAYER = P("NODE_LAYER", 24);      // mm between layers
const WREF = 18.71;

const linkCount = {};
for (const e of G.edges) linkCount[e.net] = (linkCount[e.net] || 0) + 1;

const children = G.nodes.map((n) => ({
  id: n.id, width: Math.max(n.w, 2), height: Math.max(n.h, 2),
}));
const edges = [];
for (const [i, e] of G.edges.entries()) {
  const per = 1 / linkCount[e.net];
  edges.push({
    id: "e" + i, sources: [e.source], targets: [e.target],
    // ELK uses `weight` only via priority; we encode the width in the label
    // and in the priority so wide nets get straighter, earlier routes.
    layouts: {},
    labels: [],
    width: e.width,
    priority: Math.round(per * (1 + 8 * (e.width / WREF) ** 1.2) * 100),
  });
}

const graph = {
  id: "root",
  layoutOptions: {
    "elk.algorithm": "layered",
    "elk.direction": DIRECTION,
    "elk.edgeRouting": "ORTHOGONAL",
    "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
    "elk.layered.nodePlacement.bk.fixedAlignment": "BALANCED",
    "elk.layered.cycleBreaking.strategy": "GREEDY",
    "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
    "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
    "elk.spacing.nodeNode": String(NODE_NODE),
    "elk.layered.spacing.nodeNodeBetweenLayers": String(NODE_LAYER),
    "elk.spacing.edgeNode": "4",
    "elk.spacing.edgeEdge": "2",
    "elk.padding": "[top=5,left=5,bottom=5,right=5]",
    "elk.separateConnectedComponents": "false",
  },
  children,
  edges,
};

const elk = new ELK();
const res = await elk.layout(graph);

const positions = {};
for (const c of res.children) {
  positions[c.id] = { x: c.x + c.width / 2, y: c.y + c.height / 2, angle: 0 };
}
const routes = [];
for (const e of res.edges || []) {
  const pts = [];
  for (const s of e.sections || []) {
    pts.push([s.startPoint.x, s.startPoint.y]);
    for (const b of s.bendPoints || []) pts.push([b.x, b.y]);
    pts.push([s.endPoint.x, s.endPoint.y]);
  }
  if (pts.length) {
    const orig = edges.find((x) => x.id === e.id);
    routes.push({ edge: e.id, width: orig ? orig.width : 0.25, points: pts });
  }
}
fs.writeFileSync(outPath, JSON.stringify({
  engine: "elk",
  params: { DIRECTION, NODE_NODE, NODE_LAYER },
  positions, routes,
}, null, 1));
console.log(`elk: ${res.children.length} nodes, ${routes.length} orthogonal routes, `
  + `size ${Math.round(res.width)}x${Math.round(res.height)} -> ${outPath}`);
