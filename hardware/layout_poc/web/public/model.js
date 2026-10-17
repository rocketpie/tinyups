// TinyUPS placement model — the one place the force model and the metrics live.
//
// Imported by:
//   * web/public/app.js   the browser UI (solves live while you drag)
//   * ../../ab.mjs        the headless A/B runner
//   * (and by the headless engine, when it is ported — RESUME step 1)
//
// The browser resolves "d3-force" through the page's import map, node through
// hardware/layout_poc/node_modules: same code, same numbers, no second copy to
// drift.  Everything here takes `params` (P) explicitly and reads it *live*, so
// the UI can move a slider while the solver runs.  Geometry is the KiCad
// Y-DOWN board frame, matching render.py.
//
// The model: components are nodes (courtyard rectangles), kept nets are cliques
// of width-weighted springs, plus repulsion, a centre pull, a board keep-in, a
// courtyard collision, a velocity clamp — and the "belongs-to" ring that holds
// a small part beside the IC it serves (ADR-0012, docs/history/0005).
import * as d3 from "d3-force";

// Parameter defaults.  The UI's PARAM_SPEC supplies label/min/max/help and takes
// the value from here, so a UI session and a tool run share one truth; the
// tracked tuning lives in hardware/layout_poc/params.json (ADR-0010).
export const DEFAULTS = {
  SIG_STR: 0.1, POW_STR: 10, WREF: 18.71,
  D0: 2, DK: 2, DMAX: 26, LINK_ITER: 2,
  CHARGE: 30, CHARGE_SIZE: false, CHARGE_MAX: 40,
  COLLIDE_PAD: 1.0, RECT_COLLIDE: true,
  CENTER_X: 0.15, CENTER_Y: 0.05, BOUND: 60,
  HOST_STR: 1.5, HOST_D: 5, HOST_POWER: false,
  MAX_V: 3, VEL_DECAY: 0.4, ITERS: 1200, SEED: 12345,
};

export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

// --- geometry (KiCad Y-DOWN board frame) -----------------------------------
export const rot = (p, a) => {
  const c = Math.cos((a * Math.PI) / 180), s = Math.sin((a * Math.PI) / 180);
  return [p[0] * c + p[1] * s, -p[0] * s + p[1] * c];
};
export const cornersRel = (n) => {
  const [bx, by, bw, bh] = n.bbox;
  return [[bx, by], [bx + bw, by], [bx + bw, by + bh], [bx, by + bh]].map((p) => rot(p, n.angle));
};
// courtyard extents around the node origin: half-extents (hx, hy) and centre
// offset (cx, cy) of the rotated courtyard AABB
export function setExtents(n) {
  const pts = cornersRel(n);
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  n._pts = pts;
  n.hx = (Math.max(...xs) - Math.min(...xs)) / 2;
  n.hy = (Math.max(...ys) - Math.min(...ys)) / 2;
  n.cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  n.cy = (Math.min(...ys) + Math.max(...ys)) / 2;
}
export const padXY = (n, pad) => { const [rx, ry] = rot([pad.dx, pad.dy], n.angle); return [n.x + rx, n.y + ry]; };
export const isFixed = (n) => n.anchor != null || n.fx != null;
export const aabb = (n) => ({
  x0: n.x + n.cx - n.hx, y0: n.y + n.cy - n.hy,
  x1: n.x + n.cx + n.hx, y1: n.y + n.cy + n.hy,
});

// --- link model -------------------------------------------------------------
// d3 caches every force accessor at initialize() time; the accessors below read
// P live and the caller re-sets them (applyParamsToSim) to make a slider effect
// mid-run.  forceLink.distance()/strength() must actually be called — the PoC
// engine set per-link *properties* and d3 ignored them
// (docs/history/0002-d3force-inert-link-params.md).
export const linkDistance = (d, P) => Math.min(P.DMAX, P.D0 + P.DK * (d.width / P.WREF));
export const linkStrength = (d, P) =>
  d.weight * (P.SIG_STR + (P.POW_STR - P.SIG_STR) * Math.pow(d.width / P.WREF, 1.2));
export const chargeStrength = (d, P) => -P.CHARGE * (P.CHARGE_SIZE ? Math.max(d.w, d.h) : 1);
export const collideRadius = (d, P) => 0.5 * Math.hypot(d.w, d.h) + P.COLLIDE_PAD;

// --- forces -----------------------------------------------------------------
export function forceBounds(P, board) {
  let nodes = [];
  function force(alpha) {
    const m = 2, B = P.BOUND;
    for (const n of nodes) {
      if (isFixed(n)) continue;
      if (n.x + n.cx - n.hx < m) n.vx += B * alpha;
      if (n.x + n.cx + n.hx > board.w - m) n.vx -= B * alpha;
      if (n.y + n.cy - n.hy < m) n.vy += B * alpha;
      if (n.y + n.cy + n.hy > board.h - m) n.vy -= B * alpha;
    }
  }
  force.initialize = (n) => { nodes = n; };
  return force;
}

// Clamp |v| so a stiff link cannot throw a part across the board in one tick.
export function forceLimit(P) {
  let nodes = [];
  function force() {
    const v = P.MAX_V;
    for (const n of nodes) {
      if (isFixed(n)) continue;
      n.vx = clamp(n.vx || 0, -v, v);
      n.vy = clamp(n.vy || 0, -v, v);
    }
  }
  force.initialize = (n) => { nodes = n; };
  return force;
}

// Rectangular courtyard collision: pushes AABB pairs apart along the axis of
// least penetration — the interactive cousin of legalize.py's relaxation.
export function forceRectCollide(P) {
  let nodes = [];
  function force() {
    const pad = P.COLLIDE_PAD;
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        if (isFixed(a) && isFixed(b)) continue;
        const dx = (a.x + a.cx) - (b.x + b.cx);
        const dy = (a.y + a.cy) - (b.y + b.cy);
        const ox = a.hx + b.hx + pad - Math.abs(dx);
        const oy = a.hy + b.hy + pad - Math.abs(dy);
        if (ox <= 0 || oy <= 0) continue;
        if (ox < oy) {
          const s = dx >= 0 ? 1 : -1, m = 0.5 * ox;
          if (!isFixed(a)) a.x += s * m;
          if (!isFixed(b)) b.x -= s * m;
        } else {
          const s = dy >= 0 ? 1 : -1, m = 0.5 * oy;
          if (!isFixed(a)) a.y += s * m;
          if (!isFixed(b)) b.y -= s * m;
        }
      }
    }
  }
  force.initialize = (n) => { nodes = n; };
  return force;
}

export function makeCollide(P) {
  if (P.RECT_COLLIDE) return forceRectCollide(P);
  return d3.forceCollide().radius((d) => collideRadius(d, P)).iterations(3);
}

// --- the "belongs-to" (host) force ------------------------------------------
// A decoupling cap or bias resistor belongs *beside the IC it serves*, and the
// netlist only says so through a *specific* net: a 2-pad boot cap is worth 1.0,
// a 12-pad supply rail 0.09 — and GND, the one net that would tie every small
// part to its IC, is a plane and is dropped.  So score every IC by the
// specificity of the shared nets, take the best, and break a tie (a bulk cap
// sharing GND + the rail with all of them equally) by proximity.  The force is
// a ring around that host and one-sided: only the small part moves, so a
// controller keeps its position while its parts fan around it.
// Rationale + measurements: ADR-0012, docs/history/0005.
export function assignHosts(nodes, graph, byId, opts = {}) {
  const includePower = !!opts.includePower;
  const members = new Map();
  for (const e of graph.edges) {
    const s = typeof e.source === "object" ? e.source.id : e.source;
    const t = typeof e.target === "object" ? e.target.id : e.target;
    if (!members.has(e.net)) members.set(e.net, new Set());
    members.get(e.net).add(s); members.get(e.net).add(t);
  }
  for (const n of nodes) {
    n.host = null; n.hostScore = 0;
    if (!"RCDL".includes(n.kind)) continue;              // only small passives
    if (n.power && !includePower) continue;              // (see HOST_POWER)
    const score = new Map();
    for (const pad of n.pads || []) {
      const mem = members.get(pad.net);
      if (!mem || mem.size < 2) continue;
      for (const r of mem) {
        const ic = byId.get(r);
        if (!ic || ic.kind !== "U" || r === n.id) continue;
        score.set(r, (score.get(r) || 0) + 1 / (mem.size - 1));
      }
    }
    let best = null, bestScore = 0, bestD = Infinity;
    for (const [r, sc] of score) {
      const h = byId.get(r);
      const d = Math.hypot(n.x - h.x, n.y - h.y);
      if (sc > bestScore + 1e-9 || (Math.abs(sc - bestScore) < 1e-9 && d < bestD)) {
        best = r; bestScore = sc; bestD = d;
      }
    }
    if (!best) {                                         // nothing specific → nearest IC
      for (const h of nodes) {
        if (h.kind !== "U" || h.id === n.id) continue;
        const d = Math.hypot(n.x - h.x, n.y - h.y);
        if (d < bestD) { best = h.id; bestD = d; }
      }
    }
    n.host = best; n.hostScore = bestScore;
  }
}

export function forceHost(P, byId) {
  let nodes = [];
  function force(alpha) {
    const STR = P.HOST_STR, D = P.HOST_D;
    if (!STR) return;
    for (const n of nodes) {
      if (isFixed(n) || !n.host) continue;
      const h = byId.get(n.host); if (!h) continue;
      const dx = (n.x + n.cx) - (h.x + h.cx), dy = (n.y + n.cy) - (h.y + h.cy);
      const L = Math.hypot(dx, dy) || 1e-6;
      const f = STR * (L - D) * alpha;
      n.vx -= (dx / L) * f;
      n.vy -= (dy / L) * f;
    }
  }
  force.initialize = (n) => { nodes = n; };
  return force;
}

// --- simulation -------------------------------------------------------------
// Build the full model over `nodes`/`edges` (edge endpoints may still be ids —
// forceLink resolves them).  Returns the pieces so a caller can re-set the
// accessors (applyParamsToSim) or swizzle the collision force when the user
// flips RECT_COLLIDE.
export function buildSim(nodes, edges, board, params) {
  const P = params;
  const link = d3.forceLink(edges).id((d) => d.id)
    .distance((d) => linkDistance(d, P))
    .strength((d) => linkStrength(d, P))
    .iterations(P.LINK_ITER);
  const charge = d3.forceManyBody()
    .strength((d) => chargeStrength(d, P))
    .distanceMax(P.CHARGE_MAX);
  const cx = d3.forceX(board.w / 2).strength(P.CENTER_X);
  const cy = d3.forceY(board.h / 2).strength(P.CENTER_Y);
  const collide = makeCollide(P);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const sim = d3.forceSimulation(nodes)
    .force("link", link)
    .force("charge", charge)
    .force("centerx", cx)
    .force("centery", cy)
    .force("host", forceHost(P, byId))
    .force("bounds", forceBounds(P, board))
    .force("collide", collide)
    .force("limit", forceLimit(P))
    .alphaDecay(1 - Math.pow(0.001, 1 / P.ITERS))
    .velocityDecay(P.VEL_DECAY);
  sim.stop();
  return { sim, link, charge, cx, cy, collide, collideType: P.RECT_COLLIDE };
}

// Re-set every cached accessor + the two simulation-level constants.  This is
// what makes a slider effective mid-run (d3 caches at initialize()).
export function applyParamsToSim(m, P) {
  m.link.distance((d) => linkDistance(d, P)).strength((d) => linkStrength(d, P)).iterations(P.LINK_ITER);
  m.charge.strength((d) => chargeStrength(d, P)).distanceMax(P.CHARGE_MAX);
  m.cx.strength(P.CENTER_X);
  m.cy.strength(P.CENTER_Y);
  m.sim.velocityDecay(P.VEL_DECAY).alphaDecay(1 - Math.pow(0.001, 1 / P.ITERS));
  if (P.RECT_COLLIDE !== m.collideType) {
    m.collide = makeCollide(P);
    m.collideType = P.RECT_COLLIDE;
    m.sim.force("collide", m.collide);
  } else if (m.collide && !P.RECT_COLLIDE) {
    m.collide.radius((d) => collideRadius(d, P)).iterations(3);
  }
}

// --- starts -----------------------------------------------------------------
// Uniform-random scatter over the whole board, from the same generator the UI's
// Scatter button uses — so a headless A/B start is exactly a UI Scatter start.
export function mulberry32(a) {
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function scatterPositions(nodes, board, seed) {
  const rnd = mulberry32(seed);
  for (const n of nodes) {
    if (n.anchor) continue;
    const lox = n.hx - n.cx, hix = board.w - n.hx - n.cx;
    const loy = n.hy - n.cy, hiy = board.h - n.hy - n.cy;
    n.x = lox + rnd() * Math.max(0, hix - lox);
    n.y = loy + rnd() * Math.max(0, hiy - loy);
    n.fx = null; n.fy = null; n.pinned = false;
    if (n.anchor) { n.x = n.anchor[0]; n.y = n.anchor[1]; n.fx = n.x; n.fy = n.y; }
  }
}

// --- metrics ----------------------------------------------------------------
// The metric set the UI shows and the A/B runner scores: pre-route proxies
// (HPWL, drawn wire, courtyard overlaps, off-board) plus the "fan" statistics
// per controller — mean distance of its small parts, their inward bias and
// their spacing.  render.py computes the same set in python.
export function metrics(nodes, edges, graph, board, byId) {
  const m = {};
  const netPts = new Map();
  for (const n of nodes) {
    for (const p of n.pads || []) {
      if (!p.net) continue;
      if (!netPts.has(p.net)) netPts.set(p.net, []);
      netPts.get(p.net).push(padXY(n, p));
    }
  }
  m.hpwl = 0; m.hpwl_w = 0;
  for (const [net, pts] of netPts) {
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const d = (Math.max(...xs) - Math.min(...xs)) + (Math.max(...ys) - Math.min(...ys));
    m.hpwl += d;
    m.hpwl_w += d * ((graph.nets[net] || {}).width || 0.25);
  }
  m.wire = 0; m.wire_w = 0;
  for (const e of edges) {
    if (!e.draw) continue;
    const d = Math.hypot(e.source.x - e.target.x, e.source.y - e.target.y);
    m.wire += d; m.wire_w += d * e.width;
  }
  const boxes = nodes.map(aabb);
  m.overlap = 0;
  for (let i = 0; i < boxes.length; i++)
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      if (!(a.x1 <= b.x0 || b.x1 <= a.x0 || a.y1 <= b.y0 || b.y1 <= a.y0)) m.overlap++;
    }
  m.outside = boxes.filter((b) => b.x0 < 0 || b.y0 < 0 || b.x1 > board.w || b.y1 > board.h).length;

  const order = (graph.power_order || []).filter((r) => byId.has(r));
  m.path = 0;
  for (let i = 0; i + 1 < order.length; i++) {
    const a = byId.get(order[i]), b = byId.get(order[i + 1]);
    m.path += Math.hypot(a.x - b.x, a.y - b.y);
  }
  const pin = byId.get(graph.io.in), pout = byId.get(graph.io.out);
  const span = pin && pout ? Math.hypot(pout.x - pin.x, pout.y - pin.y) : 0;
  m.straight = span ? m.path / span : 0;
  m.d_in = pin && order.length ? Math.hypot(byId.get(order[0]).x - pin.x, byId.get(order[0]).y - pin.y) : 0;
  m.d_out = pout && order.length ? Math.hypot(byId.get(order[order.length - 1]).x - pout.x, byId.get(order[order.length - 1]).y - pout.y) : 0;
  m.axis_r = 0;
  if (pin && pout && order.length > 2) {
    const ux = pout.x - pin.x, uy = pout.y - pin.y, nrm = Math.hypot(ux, uy) || 1;
    const fs = [], us = [];
    for (const r of order) {
      const n = byId.get(r); if (n.flow == null) continue;
      fs.push(n.flow);
      us.push(((n.x - pin.x) * ux + (n.y - pin.y) * uy) / nrm / nrm);
    }
    if (fs.length > 2) {
      const mf = fs.reduce((a, b) => a + b) / fs.length, mu = us.reduce((a, b) => a + b) / us.length;
      let cov = 0, sf = 0, su = 0;
      for (let i = 0; i < fs.length; i++) { cov += (fs[i] - mf) * (us[i] - mu); sf += (fs[i] - mf) ** 2; su += (us[i] - mu) ** 2; }
      m.axis_r = sf && su ? cov / Math.sqrt(sf * su) : 0;
    }
  }
  m.fan = fanStats(nodes, graph, board, byId);
  return m;
}

// Per controller: how its attached small parts sit around it.
//   d    mean distance part → controller (want small: they belong together)
//   bias mean cosine of "part → controller" against "controller → board centre"
//        (+1 = every part on the centre side = dragging to the middle)
//   near share of parts on the centre side; spacing mean nearest-neighbour
//        distance among those parts (want it up: they need room to fan out)
export function fanStats(nodes, graph, board, byId) {
  const adj = new Map();
  for (const e of graph.edges) {
    const s = typeof e.source === "object" ? e.source.id : e.source;
    const t = typeof e.target === "object" ? e.target.id : e.target;
    if (!adj.has(s)) adj.set(s, new Set());
    if (!adj.has(t)) adj.set(t, new Set());
    adj.get(s).add(t); adj.get(t).add(s);
  }
  const ctr = [board.w / 2, board.h / 2];
  const out = {};
  for (const n of nodes) {
    if (n.kind !== "U") continue;
    const sats = [...(adj.get(n.id) || [])].map((r) => byId.get(r))
      .filter((p) => p && "RCDL".includes(p.kind));
    if (!sats.length) continue;
    const toC = [ctr[0] - n.x, ctr[1] - n.y];
    const toCn = Math.hypot(toC[0], toC[1]) || 1;
    let bias = 0, d = 0, spacing = 0, inside = 0;
    for (const s of sats) {
      const v = [s.x - n.x, s.y - n.y], L = Math.hypot(v[0], v[1]) || 1;
      bias += (v[0] / L) * (toC[0] / toCn) + (v[1] / L) * (toC[1] / toCn);
      d += L;
      if (v[0] * toC[0] + v[1] * toC[1] > 0) inside++;
      let best = Infinity;
      for (const o of sats) if (o !== s) best = Math.min(best, Math.hypot(o.x - s.x, o.y - s.y));
      spacing += best;
    }
    const k = sats.length;
    out[n.id] = { k, d: d / k, bias: bias / k, spacing: spacing / k, inside };
  }
  return out;
}
