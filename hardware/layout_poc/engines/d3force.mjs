// PoC engine: d3-force.
//
// Components -> nodes, nets -> links (MST decomposition from extract.py; GND is
// already dropped there — it is a plane).  Link "springiness" is driven by the
// required trace width: a 20 A net pulls hard and holds its parts far apart, a
// signal net barely pulls.  The two power terminals are pinned (fx/fy) and a
// bounds force keeps parts on the board; collision keeps courtyards apart.
//
// Usage: node engines/d3force.mjs <graph.json> <out.json>
import fs from "node:fs";
import * as d3 from "d3-force";

const [graphPath, outPath] = process.argv.slice(2);
const G = JSON.parse(fs.readFileSync(graphPath, "utf8"));
const B = G.board;

// --- tunables (env) -------------------------------------------------------
const P = (k, d) => (process.env[k] !== undefined ? +process.env[k] : d);
const ITERS = P("ITERS", 1200);
const CHARGE = P("CHARGE", 22);          // repulsion * part size
const D0 = P("D0", 6);                   // link rest length base (mm)
const DK = P("DK", 2.6);                 // + DK * sqrt(width)
const DMAX = P("DMAX", 26);
const BASE_STR = P("BASE_STR", 0.18);
const NORM = P("NORM", 3.0);              // per-net weight before /links
const WREF = P("WREF", 18.71);           // width of the 20 A nets (mm)
const BOUND = P("BOUND", 60);
const SEED = P("SEED", 12345);

// deterministic RNG (mulberry32) so runs reproduce
let s = SEED >>> 0;
const rnd = () => ((s = (s + 0x6d2b79f5) >>> 0),
  (((s ^ (s >>> 15)) * (s | 1)) >>> 0) % 4294967296 / 4294967296);

const byId = new Map(G.nodes.map((n) => [n.id, n]));

// lay the nodes out in a loose grid first, anchors where they belong
const nodes = G.nodes.map((n, i) => {
  const o = {
    id: n.id, w: n.w, h: n.h, kind: n.kind, power: n.power,
    x: 20 + (i % 12) * 9 + rnd() * 4,
    y: 20 + Math.floor(i / 12) * 9 + rnd() * 4,
  };
  if (n.anchor) { o.fx = n.anchor[0]; o.fy = n.anchor[1]; }
  return o;
});
const N = new Map(nodes.map((n) => [n.id, n]));

// A net's total spring weight is split over its MST edges, so a many-pad net
// does not outweigh a 2-pad signal net just by having more edges (the standard
// HPWL clique-normalisation).  GND is already gone: it is a plane (extract.py).
const linkCount = {};
for (const e of G.edges) linkCount[e.net] = (linkCount[e.net] || 0) + 1;
const links = G.edges
  .map((e) => {
    const w = e.width;
    const per = 1 / linkCount[e.net];
    return {
      source: e.source, target: e.target, width: w, current: e.current,
      distance: Math.min(DMAX, D0 + DK * Math.sqrt(w)),
      strength: per * Math.min(0.95, NORM * (BASE_STR + 0.8 * (w / WREF) ** 1.1)),
    };
  });

function forceBounds(alpha) {
  const m = 2;
  for (const n of nodes) {
    if (n.fx !== undefined) continue;
    const hw = n.w / 2, hh = n.h / 2;
    if (n.x - hw < m) n.vx += BOUND * alpha;
    if (n.x + hw > B.w - m) n.vx -= BOUND * alpha;
    if (n.y - hh < m) n.vy += BOUND * alpha;
    if (n.y + hh > B.h - m) n.vy -= BOUND * alpha;
  }
}

const sim = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(links).id((d) => d.id).iterations(2))
  .force("charge", d3.forceManyBody()
    .strength((d) => -CHARGE * Math.max(d.w, d.h))
    .distanceMax(40))
  .force("collide", d3.forceCollide()
    .radius((d) => 0.5 * Math.hypot(d.w, d.h) + 1.0)
    .iterations(3))
  .force("x", d3.forceX(B.w / 2).strength(0.02))
  .force("y", d3.forceY(B.h / 2).strength(0.02))
  .force("bounds", forceBounds)
  .stop();

for (let i = 0; i < ITERS; i++) sim.tick();

const positions = {};
for (const n of nodes) positions[n.id] = {
  x: Math.round(n.x * 100) / 100,
  y: Math.round(n.y * 100) / 100,
  angle: 0,
};
fs.writeFileSync(outPath, JSON.stringify({
  engine: "d3-force",
  params: { ITERS, CHARGE, D0, DK, BASE_STR, SEED },
  positions,
}, null, 1));
console.log(`d3-force: ${nodes.length} nodes, ${links.length} links, ${ITERS} ticks -> ${outPath}`);
