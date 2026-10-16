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
const CHARGE = P("CHARGE", 4);          // repulsion (constant — collision does
const CHARGE_SIZE = process.env.CHARGE_SIZE === "1";   // the real spacing)
const CENTER_X = P("CENTER_X", 0.15);
const CENTER_Y = P("CENTER_Y", 0.05);
const D0 = P("D0", 2.0);                 // link rest length base (mm)
const DK = P("DK", 2.0);                 // + DK * (width / WREF): wide nets need
                                         // a little room, NOT a lot of length —
                                         // the power path must stay SHORT
const DMAX = P("DMAX", 26);
// spring strength by trace width.  A signal net gets SIG_STR, a 20 A net gets
// POW_STR, so the power path pulls ~50x harder than the small traces and
// collapses into a tight spine instead of a ring.
const SIG_STR = P("SIG_STR", 0.1);
const POW_STR = P("POW_STR", 10.0);
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
      distance: Math.min(DMAX, D0 + DK * (w / WREF)),
      strength: per * (SIG_STR + (POW_STR - SIG_STR) * (w / WREF) ** 1.2),
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
    .strength((d) => -CHARGE * (CHARGE_SIZE ? Math.max(d.w, d.h) : 1))
    .distanceMax(40))
  .force("collide", d3.forceCollide()
    .radius((d) => 0.5 * Math.hypot(d.w, d.h) + 1.0)
    .iterations(3))
  .force("x", d3.forceX(B.w / 2).strength(CENTER_X))
  .force("y", d3.forceY(B.h / 2).strength(CENTER_Y))
  .force("bounds", forceBounds)
  .alphaDecay(1 - Math.pow(0.001, 1 / ITERS))   // keep the forces alive for
  .stop();                                      // the whole run, not just ~300

for (let i = 0; i < ITERS; i++) sim.tick();

const positions = {};
for (const n of nodes) positions[n.id] = {
  x: Math.round(n.x * 100) / 100,
  y: Math.round(n.y * 100) / 100,
  angle: 0,
};
fs.writeFileSync(outPath, JSON.stringify({
  engine: "d3-force",
  params: { ITERS, CHARGE, D0, DK, SIG_STR, POW_STR, CENTER_X, SEED },
  positions,
}, null, 1));
console.log(`d3-force: ${nodes.length} nodes, ${links.length} links, ${ITERS} ticks -> ${outPath}`);
