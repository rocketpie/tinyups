// TinyUPS — interactive placement UI.
//
// The board is drawn as a graph: components are courtyard rectangles, nets are
// edges coloured/weighted by required trace width (IPC-2221, see extract.py).
// The placement engine is d3-force — the *same* model as
// hardware/layout_poc/engines/d3force.mjs — running live in the browser.  Every
// parameter that engine reads is exposed on the left and can be tuned while it
// runs.
//
// Dragging a part pins it (fx/fy) so the engine treats it as fixed and solves
// the rest around it; right-click releases it again.
import * as d3 from "d3-force";

const NS = "http://www.w3.org/2000/svg";
const svg = document.getElementById("board");
const viewport = document.getElementById("viewport");
const layerEdges = document.getElementById("edges");
const layerNodes = document.getElementById("nodes");
const boardRect = document.getElementById("boardRect");
const gridRect = document.getElementById("gridRect");
const tooltip = document.getElementById("tooltip");
const statusEl = document.getElementById("status");
const $ = (s) => document.querySelector(s);

// ---------------------------------------------------------------------------
// Engine parameters.  Labels/units/help are what the UI shows; the keys are the
// exact names engines/d3force.mjs reads from the environment, so a run of the
// PoC and a session here are tunable to the same config.
// ---------------------------------------------------------------------------
const PARAM_SPEC = [
  { key: "SIG_STR", label: "Signal trace link force", min: 0, max: 5, step: 0.01, d: 0.1, group: "links",
    help: "Link strength for a zero-width (signal) net. Low = signals barely pull." },
  { key: "POW_STR", label: "Power trace link force", min: 0, max: 60, step: 0.1, d: 10, group: "links",
    help: "Link strength a full-width (WREF) power trace reaches. High = the power path collapses into a tight spine." },
  { key: "WREF", label: "Reference width (mm)", min: 1, max: 25, step: 0.01, d: 18.71, group: "links",
    help: "Trace width treated as 'full power' — the IPC-2221 width of a 20 A net." },
  { key: "D0", label: "Link rest distance (mm)", min: 0, max: 40, step: 0.5, d: 2, group: "links",
    help: "Base preferred link length (a signal connection wants to be this long)." },
  { key: "DK", label: "Link distance per width (mm)", min: 0, max: 40, step: 0.5, d: 2, group: "links",
    help: "Extra preferred length for a wide trace: D0 + DK·(width/WREF)." },
  { key: "DMAX", label: "Max link distance (mm)", min: 1, max: 80, step: 1, d: 26, group: "links",
    help: "Cap on the preferred link length." },
  { key: "LINK_ITER", label: "Link solver iterations", min: 1, max: 8, step: 1, d: 2, group: "links",
    help: "d3 forceLink constraint iterations per tick (stiffer convergence)." },
  { key: "CHARGE", label: "Repulsion strength", min: 0, max: 300, step: 1, d: 30, group: "spread",
    help: "Many-body repulsion (forceManyBody). The PoC's adopted run uses 30." },
  { key: "CHARGE_SIZE", label: "Repulsion scales with part size", type: "check", d: false, group: "spread",
    help: "Off = a constant charge; on = bigger parts push harder." },
  { key: "CHARGE_MAX", label: "Repulsion range (mm)", min: 5, max: 200, step: 5, d: 40, group: "spread",
    help: "distanceMax: beyond this a part feels no repulsion." },
  { key: "COLLIDE_PAD", label: "Courtyard clearance (mm)", min: 0, max: 5, step: 0.1, d: 1.0, group: "spread",
    help: "Required gap between courtyards (the collision force's +N)." },
  { key: "RECT_COLLIDE", label: "Rectangular courtyard collision", type: "check", d: true, group: "spread",
    help: "On = resolve courtyard AABB overlaps directly (like legalize.py); off = d3 circle collision (exactly the PoC)." },
  { key: "CENTER_X", label: "Pull to board centre X", min: 0, max: 1, step: 0.01, d: 0.15, group: "spread",
    help: "Constant force towards the board centre (X)." },
  { key: "CENTER_Y", label: "Pull to board centre Y", min: 0, max: 1, step: 0.01, d: 0.05, group: "spread",
    help: "Constant force towards the board centre (Y)." },
  { key: "BOUND", label: "Board keep-in force", min: 0, max: 400, step: 5, d: 60, group: "spread",
    help: "How hard the board edge pushes parts back inside." },
  { key: "MAX_V", label: "Max move per tick (mm)", min: 0.5, max: 30, step: 0.5, d: 3, group: "solver",
    help: "Velocity clamp. With the link distance/strength actually wired in (see README), d3-force diverges on a dense start — a 2-part net gets weight 1 and up to POW_STR. Clamping tames it." },
  { key: "VEL_DECAY", label: "Velocity decay", min: 0, max: 0.95, step: 0.05, d: 0.4, group: "solver",
    help: "d3's velocityDecay (0.4 = its default): how much speed is lost each tick." },
  { key: "ITERS", label: "Run length (alpha decay)", min: 100, max: 6000, step: 100, d: 1200, group: "solver",
    help: "Ticks for alpha to fall to ~0.001 — the 'solve' budget." },
  { key: "SEED", label: "Scatter seed", min: 1, max: 999999, step: 1, d: 12345, group: "solver",
    help: "RNG seed used by 'Scatter' for the starting positions." },
];

const S = {
  graph: null, board: { w: 150, h: 140 },
  nodes: [], edges: [], byId: new Map(),
  params: {}, sim: null, linkForce: null, chargeForce: null,
  xForce: null, yForce: null, collideForce: null, collideType: null,
  seedName: null, seedData: null,
  view: { k: 1, x: 0, y: 0 },
  hover: null, selected: null,
  onlyDraw: true, showLabels: true,
  paused: false, lastMetrics: 0, savedFile: null,
};

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const fmt = (v, d = 1) => (v == null || Number.isNaN(v) ? "–" : (+v).toFixed(d));

// --- geometry (KiCad Y-DOWN board frame; same convention as render.py) ------
const rot = (p, a) => {
  const c = Math.cos((a * Math.PI) / 180), s = Math.sin((a * Math.PI) / 180);
  return [p[0] * c + p[1] * s, -p[0] * s + p[1] * c];
};
const cornersRel = (n) => {
  const [bx, by, bw, bh] = n.bbox;
  return [[bx, by], [bx + bw, by], [bx + bw, by + bh], [bx, by + bh]].map((p) => rot(p, n.angle));
};
function setExtents(n) {
  const pts = cornersRel(n);
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  n._pts = pts;
  n.hx = (Math.max(...xs) - Math.min(...xs)) / 2;
  n.hy = (Math.max(...ys) - Math.min(...ys)) / 2;
  n.cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  n.cy = (Math.min(...ys) + Math.max(...ys)) / 2;
}
const padXY = (n, pad) => { const [rx, ry] = rot([pad.dx, pad.dy], n.angle); return [n.x + rx, n.y + ry]; };
const isFixed = (n) => n.anchor != null || n.fx != null;

// --- load -------------------------------------------------------------------
async function boot() {
  const [graph, seeds] = await Promise.all([
    fetch("/graph.json").then((r) => r.json()),
    fetch("/api/seeds").then((r) => r.json()),
  ]);
  S.graph = graph;
  S.board = graph.board;
  buildLegend();

  const sel = $("#seed");
  const qs = new URLSearchParams(location.search).get("seed");
  for (const s of seeds.seeds) {
    const o = document.createElement("option");
    o.value = s.name;
    o.textContent = `${s.name}  ·  ${s.engine}  ·  ${s.n} parts`;
    if (s.name === (qs || seeds.default)) o.selected = true;
    sel.appendChild(o);
  }
  S.seedName = sel.value;
  buildParams();                 // params must exist before the sim is built
  await loadSeed(S.seedName);
  bindEvents();
  fitView();
  setStatus("ready");
}

async function loadSeed(name) {
  S.seedName = name;
  const data = await fetch("/api/seed?name=" + encodeURIComponent(name)).then((r) => r.json());
  S.seedData = data;
  S.nodes = S.graph.nodes.map((gn) => {
    const p = data.positions[gn.id] || { x: S.board.w / 2, y: S.board.h / 2, angle: 0 };
    const n = { ...gn, x: p.x, y: p.y, angle: p.angle || 0, pinned: false };
    if (gn.anchor) { n.x = gn.anchor[0]; n.y = gn.anchor[1]; }
    setExtents(n);
    if (gn.anchor || (p.pin && !gn.anchor)) { n.fx = n.x; n.fy = n.y; }
    if (p.pin && !gn.anchor) n.pinned = true;
    return n;
  });
  S.byId = new Map(S.nodes.map((n) => [n.id, n]));
  S.edges = S.graph.edges.map((e) => ({ ...e }));   // strings; forceLink rewrites to refs
  S.selected = null;
  $("#boardInfo").textContent =
    `${S.board.w} × ${S.board.h} mm · ${S.nodes.length} parts · ${S.edges.length} edges · seed ${name}`;
  boardRect.setAttribute("width", S.board.w); boardRect.setAttribute("height", S.board.h);
  gridRect.setAttribute("width", S.board.w); gridRect.setAttribute("height", S.board.h);
  buildScene();
  buildSim();
  applyHighlight();
  renderPins();
  renderInspect();
  draw();
  renderMetrics();
  setStatus(`seed ${name}`);
}

// --- simulation -------------------------------------------------------------
// d3-force caches each force's strength/distance/radius arrays at initialize
// time, so every accessor pulls from S.params *live* and `applyParams` re-sets
// the accessor to force a recompute.
const linkDistance = (d) => Math.min(S.params.DMAX, S.params.D0 + S.params.DK * (d.width / S.params.WREF));
const linkStrength = (d) => d.weight * (S.params.SIG_STR + (S.params.POW_STR - S.params.SIG_STR) * Math.pow(d.width / S.params.WREF, 1.2));
const chargeStrength = (d) => -S.params.CHARGE * (S.params.CHARGE_SIZE ? Math.max(d.w, d.h) : 1);
const collideRadius = (d) => 0.5 * Math.hypot(d.w, d.h) + S.params.COLLIDE_PAD;

function forceBounds() {
  let nodes = [];
  function force(alpha) {
    const m = 2, B = S.params.BOUND;
    for (const n of nodes) {
      if (isFixed(n)) continue;
      const hw = n.hx, hh = n.hy;
      if (n.x + n.cx - hw < m) n.vx += B * alpha;
      if (n.x + n.cx + hw > S.board.w - m) n.vx -= B * alpha;
      if (n.y + n.cy - hh < m) n.vy += B * alpha;
      if (n.y + n.cy + hh > S.board.h - m) n.vy -= B * alpha;
    }
  }
  force.initialize = (n) => { nodes = n; };
  return force;
}

// Clamp |v| so a stiff link cannot throw a part across the board in one tick.
function forceLimit() {
  let nodes = [];
  function force() {
    const v = S.params.MAX_V;
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
// least penetration.  This is the interactive cousin of legalize.py's relaxation
// — real courtyards, not the d3 circle proxy.
function forceRectCollide() {
  let nodes = [];
  function force() {
    const pad = S.params.COLLIDE_PAD;
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
function makeCollide() {
  S.collideType = S.params.RECT_COLLIDE;
  if (S.params.RECT_COLLIDE) return forceRectCollide();
  return d3.forceCollide()
    .radius((d) => 0.5 * Math.hypot(d.w, d.h) + S.params.COLLIDE_PAD)
    .iterations(3);
}

function buildSim() {
  if (S.sim) S.sim.stop();
  const p = S.params, B = S.board;
  const link = d3.forceLink(S.edges).id((d) => d.id)
    .distance(linkDistance).strength(linkStrength).iterations(p.LINK_ITER);
  const charge = d3.forceManyBody()
    .strength(chargeStrength).distanceMax(p.CHARGE_MAX);
  const cx = d3.forceX(B.w / 2).strength(p.CENTER_X);
  const cy = d3.forceY(B.h / 2).strength(p.CENTER_Y);
  const collide = makeCollide();
  S.sim = d3.forceSimulation(S.nodes)
    .force("link", link)
    .force("charge", charge)
    .force("centerx", cx)
    .force("centery", cy)
    .force("bounds", forceBounds())
    .force("collide", collide)
    .force("limit", forceLimit())
    .alphaDecay(1 - Math.pow(0.001, 1 / p.ITERS))
    .velocityDecay(p.VEL_DECAY)
    .on("tick", onTick)
    .on("end", () => setStatus("settled"));
  S.linkForce = link; S.chargeForce = charge;
  S.xForce = cx; S.yForce = cy; S.collideForce = collide;
  S.sim.stop();
}

function applyParams(reheat = true) {
  const p = S.params;
  if (!S.sim) return;
  // Re-set each accessor: d3 caches strengths/distances/radii at initialize time,
  // so this is what makes a moved slider actually change the force.
  S.linkForce.distance(linkDistance).strength(linkStrength).iterations(p.LINK_ITER);
  S.chargeForce.strength(chargeStrength).distanceMax(p.CHARGE_MAX);
  S.xForce.strength(p.CENTER_X);
  S.yForce.strength(p.CENTER_Y);
  S.sim.velocityDecay(p.VEL_DECAY).alphaDecay(1 - Math.pow(0.001, 1 / p.ITERS));
  if (p.RECT_COLLIDE !== S.collideType) {
    S.collideForce = makeCollide();
    S.sim.force("collide", S.collideForce);
  } else if (S.collideForce && !p.RECT_COLLIDE) {
    S.collideForce.radius(collideRadius).iterations(3);
  }
  if (reheat) solve(Math.max(S.sim.alpha(), 0.6));
}

function solve(alpha = 1) {
  if (!S.sim) return;
  S.paused = false; updatePauseBtn();
  S.sim.alpha(Math.max(alpha, 0.05)).restart();
  setStatus("solving…");
}

function onTick() {
  draw();
  const now = performance.now();
  if (now - S.lastMetrics > 120) { S.lastMetrics = now; renderMetrics(); }
}

// --- scene ------------------------------------------------------------------
function buildScene() {
  layerEdges.replaceChildren();
  layerNodes.replaceChildren();
  for (const e of S.edges) {
    const el = document.createElementNS(NS, "line");
    el.setAttribute("class", "edge");
    el.setAttribute("stroke", color(e.current));
    const sw = 0.12 + 0.95 * Math.pow(e.width / 18.71, 0.6);
    el.setAttribute("stroke-width", sw.toFixed(3));
    el._op = 0.28 + 0.72 * Math.sqrt(Math.min(1, e.width / 18.71));
    el.setAttribute("stroke-opacity", el._op);
    e._el = el;
    layerEdges.appendChild(el);
  }
  for (const n of S.nodes) {
    const g = document.createElementNS(NS, "g");
    g.setAttribute("class", "node");
    g.dataset.id = n.id;
    const poly = document.createElementNS(NS, "polygon");
    poly.setAttribute("class", "courtyard");
    poly.setAttribute("points", n._pts.map((p) => `${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" "));
    poly.setAttribute("fill", fill(n));
    poly.setAttribute("fill-opacity", n.power ? "0.62" : "0.78");
    g.appendChild(poly);
    const t = document.createElementNS(NS, "text");
    t.setAttribute("x", fmt(n.cx, 2)); t.setAttribute("y", fmt(n.cy, 2));
    t.setAttribute("text-anchor", "middle");
    t.setAttribute("dominant-baseline", "central");
    t.setAttribute("font-size", Math.max(1.5, Math.min(n.w, n.h) * 0.5).toFixed(2));
    t.setAttribute("font-family", "ui-monospace, monospace");
    t.textContent = n.label || n.id;
    g.appendChild(t);
    n._el = g; n._text = t;
    layerNodes.appendChild(g);
  }
  styleNodes();
}

function draw() {
  for (const e of S.edges) {
    const el = e._el; if (!el) continue;
    const s = e.source, t = e.target;
    if (!s || !t || s.x === undefined) continue;
    el.setAttribute("x1", s.x.toFixed(2)); el.setAttribute("y1", s.y.toFixed(2));
    el.setAttribute("x2", t.x.toFixed(2)); el.setAttribute("y2", t.y.toFixed(2));
  }
  for (const n of S.nodes) {
    if (n._el) n._el.setAttribute("transform", `translate(${n.x.toFixed(2)},${n.y.toFixed(2)})`);
  }
  if (S.selected) drawPads();
}

function color(c) {
  if (c >= 15) return "#d62728";
  if (c >= 5) return "#ff7f0e";
  if (c >= 1) return "#e6c700";
  if (c > 0) return "#9aa0a6";
  return "#c8cdd2";
}
function fill(n) {
  if (n.anchor != null) return "#ffd400";
  if (n.kind === "J") return "#c8a2ff";
  return n.power ? "#ff3b3b" : "#2d6cdf";
}

function styleNodes() {
  for (const n of S.nodes) {
    n._el.classList.toggle("pinned", n.pinned);
    n._el.classList.toggle("terminal", n.anchor != null);
    n._text.style.display = S.showLabels ? "" : "none";
  }
}

// dim everything that is not the hovered/selected part's neighbourhood
function applyHighlight() {
  const h = S.hover || S.selected;
  for (const e of S.edges) {
    const el = e._el; if (!el) continue;
    el.style.display = (!S.onlyDraw || e.draw) ? "" : "none";
    const touches = h && (e.source.id === h || e.target.id === h);
    el.setAttribute("stroke-opacity", touches ? Math.min(1, el._op + 0.5)
      : (h ? el._op * 0.12 : el._op));
    el.setAttribute("stroke-width",
      (0.12 + 0.95 * Math.pow(e.width / 18.71, 0.6)) * (touches ? 1.6 : 1));
  }
  for (const n of S.nodes) {
    n._el.style.opacity = h && n.id !== h && !touchesNode(h, n.id) ? 0.35 : 1;
  }
}
function touchesNode(h, id) {
  return S.edges.some((e) =>
    (e.source.id === h && e.target.id === id) || (e.target.id === h && e.source.id === id));
}

// --- pads of the selected part ---------------------------------------------
function drawPads() {
  let layer = document.getElementById("pads");
  if (!layer) { layer = document.createElementNS(NS, "g"); layer.id = "pads"; viewport.appendChild(layer); }
  layer.replaceChildren();
  const n = S.byId.get(S.selected); if (!n) return;
  for (const p of n.pads) {
    const [x, y] = padXY(n, p);
    const c = document.createElementNS(NS, "circle");
    c.setAttribute("cx", x.toFixed(2)); c.setAttribute("cy", y.toFixed(2));
    c.setAttribute("r", "0.55");
    c.setAttribute("class", "pad");
    c.setAttribute("fill", p.net ? color((S.graph.nets[p.net] || {}).current || 0) : "#666");
    layer.appendChild(c);
  }
}

// --- metrics ----------------------------------------------------------------
function metrics() {
  const m = {};
  const netPts = new Map();
  for (const n of S.nodes) {
    for (const p of n.pads) {
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
    m.hpwl_w += d * ((S.graph.nets[net] || {}).width || 0.25);
  }
  m.wire = 0; m.wire_w = 0;
  for (const e of S.edges) {
    if (!e.draw) continue;
    const d = Math.hypot(e.source.x - e.target.x, e.source.y - e.target.y);
    m.wire += d; m.wire_w += d * e.width;
  }
  const boxes = S.nodes.map((n) => ({
    id: n.id, x0: n.x + n.cx - n.hx, y0: n.y + n.cy - n.hy,
    x1: n.x + n.cx + n.hx, y1: n.y + n.cy + n.hy,
  }));
  m.overlap = 0;
  for (let i = 0; i < boxes.length; i++)
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      if (!(a.x1 <= b.x0 || b.x1 <= a.x0 || a.y1 <= b.y0 || b.y1 <= a.y0)) m.overlap++;
    }
  m.outside = boxes.filter((b) => b.x0 < 0 || b.y0 < 0 || b.x1 > S.board.w || b.y1 > S.board.h).length;

  const order = S.graph.power_order.filter((r) => S.byId.has(r));
  m.path = 0;
  for (let i = 0; i + 1 < order.length; i++) {
    const a = S.byId.get(order[i]), b = S.byId.get(order[i + 1]);
    m.path += Math.hypot(a.x - b.x, a.y - b.y);
  }
  const pin = S.byId.get(S.graph.io.in), pout = S.byId.get(S.graph.io.out);
  const span = pin && pout ? Math.hypot(pout.x - pin.x, pout.y - pin.y) : 0;
  m.straight = span ? m.path / span : 0;
  m.d_in = pin && order.length ? Math.hypot(S.byId.get(order[0]).x - pin.x, S.byId.get(order[0]).y - pin.y) : 0;
  m.d_out = pout && order.length ? Math.hypot(S.byId.get(order[order.length - 1]).x - pout.x, S.byId.get(order[order.length - 1]).y - pout.y) : 0;
  // flow-ordered? correlation of flow position with position along the in->out axis
  m.axis_r = 0;
  if (pin && pout && order.length > 2) {
    const ux = pout.x - pin.x, uy = pout.y - pin.y, nrm = Math.hypot(ux, uy) || 1;
    const fs = [], us = [];
    for (const r of order) {
      const n = S.byId.get(r); if (n.flow == null) continue;
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
  return m;
}

function renderMetrics() {
  const m = metrics();
  const rows = [
    ["parts", S.nodes.length, ""],
    ["HPWL (mm)", fmt(m.hpwl, 0), ""],
    ["weighted HPWL", fmt(m.hpwl_w, 0), ""],
    ["wire (mm)", fmt(m.wire, 0), ""],
    ["overlaps", m.overlap, m.overlap === 0 ? "good" : "bad"],
    ["off-board", m.outside, m.outside === 0 ? "good" : "bad"],
    ["power path (mm)", fmt(m.path, 0), ""],
    ["straightness", fmt(m.straight, 2), ""],
    ["flow axisR", fmt(m.axis_r, 2), m.axis_r > 0.4 ? "good" : ""],
    ["in / out (mm)", `${fmt(m.d_in, 0)} / ${fmt(m.d_out, 0)}`, ""],
  ];
  $("#metrics").innerHTML = rows.map(([k, v, cls]) =>
    `<tr class="${cls}"><td>${k}</td><td>${v}</td></tr>`).join("");
  const a = S.sim ? S.sim.alpha() : 0;
  setStatus(`${S.paused ? "paused" : "alpha " + a.toFixed(3)} · ${S.pinnedCount()} pinned`);
}

// --- pins -------------------------------------------------------------------
S.pinnedCount = () => S.nodes.filter((n) => n.pinned).length;
function renderPins() {
  const pins = S.nodes.filter((n) => n.pinned || n.anchor != null);
  $("#pinCount").textContent = pins.length;
  $("#pins").innerHTML = pins.map((n) =>
    `<span class="pin ${n.anchor != null ? "terminal" : ""}" data-id="${n.id}"
      title="${n.anchor != null ? "terminal — always fixed" : "click to unpin"}">${n.id}</span>`).join("") ||
    '<span class="hint">none — drag a part to pin it</span>';
}

function pin(n) { if (n.anchor != null) return; n.pinned = true; n.fx = n.x; n.fy = n.y; }
function unpin(n) { if (n.anchor != null) return; n.pinned = false; n.fx = null; n.fy = null; }
function unpinAll() { for (const n of S.nodes) unpin(n); styleNodes(); renderPins(); solve(0.8); }

// --- inspect ----------------------------------------------------------------
function renderInspect() {
  const n = S.selected ? S.byId.get(S.selected) : null;
  if (!n) { $("#inspBody").innerHTML = '<span class="hint">nothing selected</span>'; return; }
  const nets = [...new Set(n.pads.filter((p) => p.net).map((p) => p.net))]
    .map((net) => {
      const g = S.graph.nets[net] || {};
      return `<tr><td>${net}</td><td>${fmt(g.current || 0, 1)} A · ${fmt(g.width || 0.25, 2)} mm</td></tr>`;
    }).join("");
  $("#inspBody").innerHTML = `
    <div class="row"><b>${n.label || n.id}</b> <span class="tag">${n.kind}${n.power ? " · power" : ""}</span></div>
    <div class="hint">${n.value || ""}<br>${n.fp || ""}</div>
    <table id="metrics" style="margin-top:6px">
      <tr><td>position</td><td>${fmt(n.x)}, ${fmt(n.y)} mm</td></tr>
      <tr><td>courtyard</td><td>${fmt(n.w)} × ${fmt(n.h)} mm</td></tr>
      <tr><td>rotation</td><td>${n.angle}° (seed)</td></tr>
      <tr><td>pinned</td><td>${n.pinned ? "yes" : n.anchor != null ? "terminal" : "no"}</td></tr>
    </table>
    <table id="metrics" style="margin-top:6px">${nets}</table>`;
}

// --- interaction ------------------------------------------------------------
let drag = null, pan = null;
function toMM(ev) {
  const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
  return pt.matrixTransform(viewport.getScreenCTM().inverse());
}

function bindEvents() {
  svg.addEventListener("pointerdown", (ev) => {
    if (ev.button === 2) return;
    const g = ev.target.closest(".node");
    if (g) {
      const n = S.byId.get(g.dataset.id);
      S.selected = n.id; S.hover = n.id;
      applyHighlight(); renderInspect(); draw();
      drag = { n, moved: false, sx: ev.clientX, sy: ev.clientY };
      svg.setPointerCapture(ev.pointerId);
      svg.classList.add("readonly");
    } else {
      pan = { sx: ev.clientX, sy: ev.clientY, vx: S.view.x, vy: S.view.y };
      svg.setPointerCapture(ev.pointerId);
      svg.classList.add("panning");
    }
  });

  svg.addEventListener("pointermove", (ev) => {
    if (drag) {
      const mm = toMM(ev);
      if (!drag.moved && Math.hypot(ev.clientX - drag.sx, ev.clientY - drag.sy) > 2) {
        drag.moved = true;
        pin(drag.n);
        styleNodes(); renderPins();
        if (S.sim) S.sim.alphaTarget(0.3).restart();
      }
      if (drag.moved) {
        drag.n.fx = clamp(mm.x, 0, S.board.w);
        drag.n.fy = clamp(mm.y, 0, S.board.h);
        drag.n.x = drag.n.fx; drag.n.y = drag.n.fy;
        drag.n._el.classList.add("dragging");
        draw(); if (!S.sim) renderMetrics();
      }
      return;
    }
    if (pan) {
      S.view.x = pan.vx + (ev.clientX - pan.sx);
      S.view.y = pan.vy + (ev.clientY - pan.sy);
      applyView();
    }
  });

  const end = () => {
    if (drag) {
      drag.n._el.classList.remove("dragging");
      if (S.sim) S.sim.alphaTarget(0);       // let it settle, part stays pinned
      drag = null;
    }
    pan = null;
    svg.classList.remove("panning", "readonly");
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);

  svg.addEventListener("pointerover", (ev) => {
    const g = ev.target.closest(".node"); if (!g) return;
    S.hover = g.dataset.id; applyHighlight(); showTip(ev, g.dataset.id);
  });
  svg.addEventListener("pointerout", (ev) => {
    const g = ev.target.closest(".node"); if (!g) return;
    S.hover = null; applyHighlight(); tooltip.hidden = true;
  });
  svg.addEventListener("pointermove", (ev) => {
    if (S.hover && !drag && !pan) showTip(ev, S.hover);
    if (!S.hover) tooltip.hidden = true;
  });

  svg.addEventListener("contextmenu", (ev) => {
    const g = ev.target.closest(".node"); if (!g) return;
    ev.preventDefault();
    const n = S.byId.get(g.dataset.id);
    if (n.pinned) unpin(n); else pin(n);
    styleNodes(); renderPins(); solve(0.8);
  });

  svg.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const before = toMM(ev);
    S.view.k = clamp(S.view.k * Math.exp(-ev.deltaY * 0.0012), 0.4, 16);
    const after = toMM(ev);
    const k = S.view.k;
    S.view.x += (after.x - before.x) * k;
    S.view.y += (after.y - before.y) * k;
    applyView();
  }, { passive: false });

  $("#pins").addEventListener("click", (ev) => {
    const el = ev.target.closest(".pin"); if (!el) return;
    const n = S.byId.get(el.dataset.id); unpin(n);
    styleNodes(); renderPins(); solve(0.8);
  });

  $("#seed").addEventListener("change", () => loadSeed($("#seed").value));
  $("#load").addEventListener("click", () => loadSeed($("#seed").value));
  $("#solve").addEventListener("click", () => solve(1));
  $("#pause").addEventListener("click", () => {
    S.paused = !S.paused;
    if (S.paused) S.sim.stop(); else S.sim.restart();
    updatePauseBtn();
  });
  $("#reset").addEventListener("click", resetToSeed);
  $("#scatter").addEventListener("click", scatter);
  $("#fit").addEventListener("click", fitView);
  $("#unpin").addEventListener("click", unpinAll);
  $("#onlyDraw").addEventListener("change", (e) => { S.onlyDraw = e.target.checked; applyHighlight(); });
  $("#showLabels").addEventListener("change", (e) => { S.showLabels = e.target.checked; styleNodes(); });
  $("#save").addEventListener("click", save);
  $("#apply").addEventListener("click", apply);
  window.addEventListener("resize", fitView);
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { S.selected = null; S.hover = null; applyHighlight(); renderInspect(); }
  });
}

function showTip(ev, id) {
  const n = S.byId.get(id);
  tooltip.innerHTML = `${n.label || id} · ${n.value || ""}<br>${fmt(n.x)}, ${fmt(n.y)} mm${n.pinned ? " · pinned" : ""}`;
  tooltip.hidden = false;
  const r = svg.getBoundingClientRect();
  tooltip.style.left = (ev.clientX - r.left + 14) + "px";
  tooltip.style.top = (ev.clientY - r.top + 14) + "px";
}

function updatePauseBtn() { $("#pause").textContent = S.paused ? "▶ Resume" : "⏸ Pause"; }

function resetToSeed() {
  const data = S.seedData;
  for (const n of S.nodes) {
    const p = data.positions[n.id]; if (!p) continue;
    n.x = p.x; n.y = p.y; n.angle = p.angle || 0; setExtents(n);
    n.pinned = false; n.fx = null; n.fy = null;
    if (n.anchor) { n.x = n.anchor[0]; n.y = n.anchor[1]; n.fx = n.x; n.fy = n.y; }
    if (p.pin) { n.pinned = true; n.fx = n.x; n.fy = n.y; }
    n._el.setAttribute("transform", `translate(${n.x},${n.y})`);
    n._el.querySelector(".courtyard").setAttribute("points", n._pts.map((q) => q.join(",")).join(" "));
    n._el.querySelector("text").setAttribute("x", fmt(n.cx, 2));
    n._el.querySelector("text").setAttribute("y", fmt(n.cy, 2));
  }
  styleNodes(); renderPins(); draw(); solve(1);
}

function mulberry32(a) { return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function scatter() {
  const rnd = mulberry32(S.params.SEED);
  S.nodes.forEach((n, i) => {
    if (n.anchor) return;
    n.x = 20 + (i % 12) * 9 + rnd() * 4;
    n.y = 20 + Math.floor(i / 12) * 9 + rnd() * 4;
    unpin(n);
  });
  styleNodes(); renderPins(); solve(1);
}

function fitView() {
  const r = svg.getBoundingClientRect(), pad = 30;
  const k = Math.min((r.width - pad * 2) / S.board.w, (r.height - pad * 2) / S.board.h);
  S.view.k = k;
  S.view.x = (r.width - S.board.w * k) / 2;
  S.view.y = (r.height - S.board.h * k) / 2;
  applyView();
}
function applyView() {
  viewport.setAttribute("transform", `translate(${S.view.x.toFixed(1)},${S.view.y.toFixed(1)}) scale(${S.view.k.toFixed(4)})`);
}

// --- params UI --------------------------------------------------------------
function buildParams() {
  for (const p of PARAM_SPEC) S.params[p.key] = p.d;
  const host = $("#params");
  host.replaceChildren();
  for (const p of PARAM_SPEC) {
    const wrap = document.createElement("div");
    wrap.className = "param";
    wrap.dataset.key = p.key;
    if (p.type === "check") {
      wrap.innerHTML = `<label class="switch">
        <input type="checkbox" data-key="${p.key}" ${p.d ? "checked" : ""}> ${p.label}</label>
        <div class="help">${p.help}</div>`;
    } else {
      wrap.innerHTML = `<div class="lbl"><span class="name">${p.label}</span>
        <span class="key">${p.key}</span></div>
        <div class="ctl">
          <input type="range" data-key="${p.key}" min="${p.min}" max="${p.max}" step="${p.step}" value="${p.d}">
          <input type="number" data-key="${p.key}" min="${p.min}" max="${p.max}" step="${p.step}" value="${p.d}">
        </div><div class="help">${p.help}</div>`;
    }
    host.appendChild(wrap);
  }
  host.addEventListener("input", (ev) => {
    const key = ev.target.dataset.key; if (!key) return;
    const spec = PARAM_SPEC.find((p) => p.key === key);
    const v = spec.type === "check" ? ev.target.checked : +ev.target.value;
    S.params[key] = v;
    for (const el of host.querySelectorAll(`[data-key="${key}"]`)) {
      if (el.type === "checkbox") el.checked = v; else el.value = v;
    }
    applyParams(true);
  });
  const reset = document.createElement("button");
  reset.textContent = "↺ Parameter defaults";
  reset.style.marginTop = "4px";
  reset.addEventListener("click", () => {
    for (const p of PARAM_SPEC) S.params[p.key] = p.d;
    for (const el of host.querySelectorAll("[data-key]")) {
      const spec = PARAM_SPEC.find((p) => p.key === el.dataset.key);
      if (el.type === "checkbox") el.checked = spec.d; else el.value = spec.d;
    }
    applyParams(true);
  });
  host.appendChild(reset);
  $("#engineNote").innerHTML =
    "engine = <b>d3-force 3.0.0</b> (vendored, runs in this tab). " +
    "Link distance = D0 + DK·(width/WREF); link strength = weight·(SIG_STR + " +
    "(POW_STR−SIG_STR)·(width/WREF)<sup>1.2</sup>) — both wired via " +
    "forceLink.distance()/strength(). <i>engines/d3force.mjs never calls those, " +
    "so in the PoC's headless run D0/DK/DMAX and SIG_STR/POW_STR were inert " +
    "(d3 defaults: 30 mm, 1/degree).</i>";
}

function buildLegend() {
  $("#legend").innerHTML = `
    <span class="lg"><span class="box" style="background:#ff3b3b"></span>power part</span>
    <span class="lg"><span class="box" style="background:#2d6cdf"></span>signal part</span>
    <span class="lg"><span class="box" style="background:#c8a2ff"></span>connector</span>
    <span class="lg"><span class="box" style="background:#ffd400"></span>pinned terminal</span>
    <span class="lg"><span class="sw" style="background:#d62728;height:4px"></span>≥15 A</span>
    <span class="lg"><span class="sw" style="background:#ff7f0e;height:3px"></span>5 A</span>
    <span class="lg"><span class="sw" style="background:#e6c700;height:2px"></span>1 A</span>
    <span class="lg"><span class="sw" style="background:#9aa0a6;height:1px"></span>signal</span>`;
}

// --- write back -------------------------------------------------------------
async function save() {
  const name = ($("#saveName").value || "baseline").replace(/[^\w.-]/g, "");
  const positions = {};
  const pinned = [];
  for (const n of S.nodes) {
    positions[n.id] = { x: +n.x.toFixed(2), y: +n.y.toFixed(2), angle: n.angle };
    if (n.pinned || n.anchor != null) { positions[n.id].pin = true; pinned.push(n.id); }
  }
  const r = await fetch("/api/save", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, seed: S.seedName, params: S.params, pinned, positions }),
  });
  const j = await r.json();
  S.savedFile = j.file;
  $("#apply").disabled = false;
  $("#io").textContent = j.ok ? `saved ${j.file}\n${j.apply}` : "error: " + JSON.stringify(j);
}

async function apply() {
  if (!S.savedFile) return;
  $("#io").textContent = "running apply.py + KiCad DRC…";
  $("#apply").disabled = true;
  try {
    const r = await fetch("/api/apply", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: S.savedFile }),
    });
    const j = await r.json();
    $("#io").textContent = (j.ok ? "DRC done → " + j.board + "\n\n" : "failed\n") +
      (j.stdout || "") + (j.stderr || "");
  } finally { $("#apply").disabled = false; }
}

function setStatus(msg) { statusEl.textContent = msg; }

// Expose the state for debugging / power users from the console.
S.metrics = metrics; S.renderMetrics = renderMetrics; S.draw = draw; S.solve = solve;
globalThis.place = S;

boot().catch((e) => {
  setStatus("error: " + e.message);
  console.error(e);
});
