// PoC engine: d3-force-incremental.
//
// Instead of relaxing the whole graph at once (which lets the power path wander
// — e.g. 1R7, wired straight to the input, ending up at the bottom of the
// board), grow the placement along the power flow:
//
//   * the two power terminals stay pinned: 1J1 (XT60 input, top) and
//     5J2 (XT30 output, bottom) — they are the poles the chain spans between;
//   * power components are added ONE BY ONE in `power_order` (BFS from the
//     input over the rail nets), each seeded next to its already-placed
//     neighbours, with a short relax after every addition;
//   * everything else joins afterwards and the whole design relaxes freely.
//
// Because a part only ever "meets" the graph once its upstream neighbour is on
// the board, the power chain is built link by link from the input to the
// output rather than all at once.
//
// Usage: node engines/d3force_incremental.mjs <graph.json> <out.json>
import fs from "node:fs";
import * as d3 from "d3-force";

const [graphPath, outPath] = process.argv.slice(2);
const G = JSON.parse(fs.readFileSync(graphPath, "utf8"));
const B = G.board;

const P = (k, d) => (process.env[k] !== undefined ? +process.env[k] : d);
const TICKS_STEP = P("TICKS_STEP", 45);    // relax after each addition
const TICKS_TAIL = P("TICKS_TAIL", 60);    // relax after each signal part
const TICKS_END = P("TICKS_END", 900);     // free relax at the end
const CHARGE = P("CHARGE", 4);
const CHARGE_SIZE = process.env.CHARGE_SIZE === "1";   // scale repulsion by part size?
const CENTER_X = P("CENTER_X", 0.15);
const CENTER_Y = P("CENTER_Y", 0.05);
const D0 = P("D0", 2.0);
const DK = P("DK", 2.0);
const DMAX = P("DMAX", 26);
// signal nets pull weakly, the 20 A power path ~50x harder: the power parts
// collapse into a tight spine, the small traces just hang off it.
const SIG_STR = P("SIG_STR", 0.1);
const POW_STR = P("POW_STR", 10.0);
const BOUND = P("BOUND", 60);
const SEED = P("SEED", 20260516);
const WREF = 18.71;

let s = SEED >>> 0;
const rnd = () => ((s = (s + 0x6d2b79f5) >>> 0),
  (((s ^ (s >>> 15)) * (s | 1)) >>> 0) % 4294967296 / 4294967296);
const jit = (m) => (rnd() - 0.5) * m;

const inAnchor = G.nodes.find((n) => n.id === G.io.in)?.anchor ?? [B.w / 2, 10];
const outAnchor = G.nodes.find((n) => n.id === G.io.out)?.anchor ?? [B.w / 2, B.h - 10];
const order = G.power_order.filter((r) => G.nodes.some((n) => n.id === r));
const orderSet = new Set(order);

// flow position from the input (extract.py): 0 at the input, 1 at the output.
// Used to *seed* each power part along the input -> output axis.  Without this a
// spring tree simply folds up instead of spanning the board; the springs then
// only fine-tune the chain.
const flowOf = new Map(G.nodes.map((n) => [n.id, n.flow]));
const axisY = (id) => {
  const f = flowOf.get(id);
  if (f === null || f === undefined) return (inAnchor[1] + outAnchor[1]) / 2;
  return inAnchor[1] + f * (outAnchor[1] - inAnchor[1]);
};

// The chain must span input -> output, so its two ends are *pinned*: the first
// power part sits just inside the input, the last just inside the output.
const firstPower = order[0];
const lastPower = order[order.length - 1];
const seedIn = [inAnchor[0], inAnchor[1] + 16];
const seedOut = [outAnchor[0], outAnchor[1] - 16];

// every node starts parked at the input; inactive nodes are frozen there so
// they neither repel nor attract until their turn comes.
const nodes = G.nodes.map((n) => ({
  id: n.id, w: n.w, h: n.h,
  x: inAnchor[0] + jit(6), y: inAnchor[1] + jit(6),
  active: false,
}));
const N = new Map(nodes.map((n) => [n.id, n]));

const linkCount = {};
for (const e of G.edges) linkCount[e.net] = (linkCount[e.net] || 0) + 1;
const specs = G.edges.map((e) => ({
  source: e.source, target: e.target,
  distance: Math.min(DMAX, D0 + DK * (e.width / WREF)),
  strength: (1 / linkCount[e.net])
    * (SIG_STR + (POW_STR - SIG_STR) * (e.width / WREF) ** 1.2),
  ok: false,
}));
const neigh = new Map();
for (const e of specs) {
  if (!neigh.has(e.source)) neigh.set(e.source, []);
  if (!neigh.has(e.target)) neigh.set(e.target, []);
  neigh.get(e.source).push(e.target);
  neigh.get(e.target).push(e.source);
}

const act = (id) => N.get(id).active;

// d3 caches every force's strengths/radii at initialize() time, so an accessor
// that depends on `active` would be frozen at its first (all-inactive) value.
// Re-assigning the forces after each activation re-runs initialize() with the
// current active set.
function resync() {
  const live = specs.filter((e) => act(e.source) && act(e.target));
  sim.force("charge", d3.forceManyBody()
    .strength((d) => (d.active
      ? -CHARGE * (CHARGE_SIZE ? Math.max(d.w, d.h) : 1) : 0))
    .distanceMax(40));
  sim.force("collide", d3.forceCollide()
    .radius((d) => (d.active ? 0.5 * Math.hypot(d.w, d.h) + 1.0 : 0))
    .iterations(3));
  sim.force("x", d3.forceX(B.w / 2).strength((d) => (d.active ? CENTER_X : 0)));
  sim.force("y", d3.forceY(B.h / 2).strength((d) => (d.active ? CENTER_Y : 0)));
  sim.force("link", d3.forceLink(live.map((e) => ({
    source: e.source, target: e.target,
    distance: e.distance, strength: e.strength,
  }))).id((d) => d.id).iterations(2));
}

function forceBounds(alpha) {
  const m = 2;
  for (const n of nodes) {
    if (!n.active || n.fx !== undefined) continue;
    const hw = n.w / 2, hh = n.h / 2;
    if (n.x - hw < m) n.vx += BOUND * alpha;
    if (n.x + hw > B.w - m) n.vx -= BOUND * alpha;
    if (n.y - hh < m) n.vy += BOUND * alpha;
    if (n.y + hh > B.h - m) n.vy -= BOUND * alpha;
  }
}

const sim = d3.forceSimulation(nodes)
  .force("charge", d3.forceManyBody()
    .strength((d) => (d.active ? -CHARGE * Math.max(d.w, d.h) : 0))
    .distanceMax(40))
  .force("collide", d3.forceCollide()
    .radius((d) => (d.active ? 0.5 * Math.hypot(d.w, d.h) + 1.0 : 0))
    .iterations(3))
  .force("x", d3.forceX(B.w / 2).strength((d) => (d.active ? 0.02 : 0)))
  .force("y", d3.forceY(B.h / 2).strength((d) => (d.active ? 0.02 : 0)))
  .force("bounds", forceBounds)
  .force("link", d3.forceLink([]).id((d) => d.id))
  .stop();

function activate(id, seedNear) {
  const n = N.get(id);
  n.active = true;
  const nb = (neigh.get(id) || []).filter(act);
  // lateral position: near the neighbours already on the board (that is what
  // keeps a branch beside the rail it taps); along the axis: at the flow depth.
  if (nb.length && seedNear) {
    n.x = nb.reduce((a, b) => a + N.get(b).x, 0) / nb.length + jit(4);
  } else {
    n.x = B.w / 2 + jit(8);
  }
  const y = axisY(id);
  n.y = (y === undefined ? inAnchor[1] : y) + jit(3);
  if (n.anchor) { n.fx = n.anchor[0]; n.fy = n.anchor[1]; n.x = n.fx; n.y = n.fy; }
  // pin the two ends of the power chain
  if (id === firstPower) { n.fx = seedIn[0]; n.fy = seedIn[1]; n.x = n.fx; n.y = n.fy; }
  if (id === lastPower) { n.fx = seedOut[0]; n.fy = seedOut[1]; n.x = n.fx; n.y = n.fy; }
  return n;
}

// 1. the two terminals, pinned at their anchors (the poles of the chain)
activate(G.io.in, false);
activate(G.io.out, false);
resync();

// 2. the power path, one component at a time, in power-flow order (the first
//    and last are pinned to the two ends of the chain by activate()).
//    Reheat alpha each round: d3 decays it to ~0 after ~300 ticks, which would
//    make every later addition inert.
for (const id of order) {
  activate(id, true);
  resync();
  sim.alpha(0.5);
  for (let i = 0; i < TICKS_STEP; i++) sim.tick();
}

// 3. the rest joins in (any order — they attach to their neighbours)
const tail = G.nodes.map((n) => n.id)
  .filter((id) => !orderSet.has(id) && !N.get(id).active);
for (const id of tail) {
  activate(id, true);
  resync();
  sim.alpha(0.35);
  for (let i = 0; i < TICKS_TAIL; i++) sim.tick();
}

// 4. free relax
sim.alpha(Math.max(sim.alpha(), 0.2));
for (let i = 0; i < TICKS_END; i++) sim.tick();

const positions = {};
for (const n of nodes) {
  const p = {
    x: Math.round(n.x * 100) / 100,
    y: Math.round(n.y * 100) / 100,
    angle: 0,
  };
  if (n.id === firstPower || n.id === lastPower) p.pin = true;
  positions[n.id] = p;
}
fs.writeFileSync(outPath, JSON.stringify({
  engine: "d3-force-incr",
  params: { TICKS_STEP, TICKS_TAIL, TICKS_END, CHARGE, SEED },
  positions,
}, null, 1));
console.log(`d3-force-incr: ${nodes.length} nodes, ${order.length} power parts `
  + `grown in order, ${TICKS_END} tail ticks -> ${outPath}`);
