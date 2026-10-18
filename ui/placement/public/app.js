// TinyUPS — interactive placement UI.
//
// The board is drawn as a graph: components are courtyard rectangles, nets are
// edges coloured/weighted by required trace width (IPC-2221, see extract.py).
// The placement engine is d3-force (the model lives in public/model.js),
// running live in the browser.  Every parameter that engine reads is exposed
// on the left and can be tuned while it runs.
//
// Dragging a part pins it (fx/fy) so the engine treats it as fixed and solves
// the rest around it; right-click releases it again.
import * as M from "./model.js";

const DEFAULTS = M.DEFAULTS;   // one truth for values

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
// exact names the force model (public/model.js) reads.
// ---------------------------------------------------------------------------
const PARAM_SPEC = [
  { key: "SIG_STR", label: "Signal trace link force", min: 0, max: 5, step: 0.01, d: DEFAULTS.SIG_STR, group: "links",
    help: "Link strength for a zero-width (signal) net. Low = signals barely pull." },
  { key: "POW_STR", label: "Power trace link force", min: 0, max: 60, step: 0.1, d: DEFAULTS.POW_STR, group: "links",
    help: "Link strength a full-width (WREF) power trace reaches. High = the power path collapses into a tight spine." },
  { key: "WREF", label: "Reference width (mm)", min: 1, max: 25, step: 0.01, d: DEFAULTS.WREF, group: "links",
    help: "Trace width treated as 'full power' in the force model (1 oz IPC-2221: 18.71 mm for 20 A). The board's real 2 oz requirement is 9.4 mm and is shown per net in the inspector." },
  { key: "D0", label: "Link rest distance (mm)", min: 0, max: 40, step: 0.5, d: DEFAULTS.D0, group: "links",
    help: "Base preferred link length (a signal connection wants to be this long)." },
  { key: "DK", label: "Link distance per width (mm)", min: 0, max: 40, step: 0.5, d: DEFAULTS.DK, group: "links",
    help: "Extra preferred length for a wide trace: D0 + DK·(width/WREF)." },
  { key: "DMAX", label: "Max link distance (mm)", min: 1, max: 80, step: 1, d: DEFAULTS.DMAX, group: "links",
    help: "Cap on the preferred link length." },
  { key: "LINK_ITER", label: "Link solver iterations", min: 1, max: 8, step: 1, d: DEFAULTS.LINK_ITER, group: "links",
    help: "d3 forceLink constraint iterations per tick (stiffer convergence)." },
  { key: "CHARGE", label: "Repulsion strength", min: 0, max: 300, step: 1, d: DEFAULTS.CHARGE, group: "spread",
    help: "Many-body repulsion (forceManyBody). The PoC's adopted run uses 30." },
  { key: "CHARGE_SIZE", label: "Repulsion scales with part size", type: "check", d: DEFAULTS.CHARGE_SIZE, group: "spread",
    help: "Off = a constant charge; on = bigger parts push harder." },
  { key: "CHARGE_MAX", label: "Repulsion range (mm)", min: 5, max: 200, step: 5, d: DEFAULTS.CHARGE_MAX, group: "spread",
    help: "distanceMax: beyond this a part feels no repulsion." },
  { key: "COLLIDE_PAD", label: "Courtyard clearance (mm)", min: 0, max: 5, step: 0.1, d: DEFAULTS.COLLIDE_PAD, group: "spread",
    help: "Required gap between courtyards (the collision force's +N)." },
  { key: "RECT_COLLIDE", label: "Rectangular courtyard collision", type: "check", d: DEFAULTS.RECT_COLLIDE, group: "spread",
    help: "On = resolve courtyard AABB overlaps directly (like legalize.py); off = d3 circle collision (exactly the PoC)." },
  { key: "CENTER_X", label: "Pull to board centre X", min: 0, max: 1, step: 0.01, d: DEFAULTS.CENTER_X, group: "spread",
    help: "Constant force towards the board centre (X)." },
  { key: "CENTER_Y", label: "Pull to board centre Y", min: 0, max: 1, step: 0.01, d: DEFAULTS.CENTER_Y, group: "spread",
    help: "Constant force towards the board centre (Y)." },
  { key: "BOUND", label: "Board keep-in force", min: 0, max: 400, step: 5, d: DEFAULTS.BOUND, group: "spread",
    help: "How hard the board edge pushes parts back inside." },
  { key: "HOST_STR", label: "Belongs-to force (small part → its IC)", min: 0, max: 20, step: 0.5, d: DEFAULTS.HOST_STR, group: "host",
    help: "Every small part (R/C/D/L) is pulled onto a ring around the IC it belongs to. Which IC: the one it shares the most *specific* net with (a 2-pad boot cap counts 1.0, a 12-pad rail 0.09); a tie (a bulk cap on a rail) goes to the nearest IC. 0 = off. Without it a controller's parts are held only by the nets, and a net's pull is toward its own centroid — which is why they drift to the middle." },
  { key: "HOST_D", label: "Belongs-to ring (mm)", min: 1, max: 30, step: 0.5, d: DEFAULTS.HOST_D, group: "host",
    help: "Preferred distance from the host: farther and the small part is pulled in, closer and it is pushed out. Only the small part moves — the controller stays put and its parts fan out around it." },
  { key: "HOST_POWER", label: "Belongs-to also for power-flagged parts", type: "check", d: DEFAULTS.HOST_POWER, group: "host",
    help: "Off = only the small parts that are *not* on the power path get a host ring. On = every small passive does, including the passives the power chain runs through (sense resistors, snubbers) — which can kink the input→output flow (the `axisR` metric)." },
  { key: "MAX_V", label: "Max move per tick (mm)", min: 0.5, max: 30, step: 0.5, d: DEFAULTS.MAX_V, group: "solver",
    help: "Velocity clamp. With the link distance/strength actually wired in (see README), d3-force diverges on a dense start — a 2-part net gets weight 1 and up to POW_STR. Clamping tames it." },
  { key: "VEL_DECAY", label: "Velocity decay", min: 0, max: 0.95, step: 0.05, d: DEFAULTS.VEL_DECAY, group: "solver",
    help: "d3's velocityDecay (0.4 = its default): how much speed is lost each tick." },
  { key: "ITERS", label: "Run length (alpha decay)", min: 100, max: 6000, step: 100, d: DEFAULTS.ITERS, group: "solver",
    help: "Ticks for alpha to fall to ~0.001 — the 'solve' budget." },
  { key: "SEED", label: "Scatter seed", min: 1, max: 999999, step: 1, d: DEFAULTS.SEED, group: "solver",
    help: "RNG seed used by 'Scatter' for the starting positions." },
];

// --- persistence ------------------------------------------------------------
// Two stores, on purpose:
//   * the *tuning* (parameter values + row order) lives in the tracked repo
//     file ui/placement/params.json, written by this UI on every change
//     — it is reviewable and revertable with git;
//   * purely local view state (toggles, the seed you were on, save name) stays
//     in this browser.
// Placement data is neither: that is what "Save" writes to
// build/layout/interactive-<name>.json.
const LS = {
  ui: "tinyups.place.ui.v1",
  legacyParams: "tinyups.place.params.v1",     // pre-repo-file session store
  legacyOrder: "tinyups.place.paramorder.v1",
};
const loadJSON = (key, fb) => {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fb; }
  catch { return fb; }
};
const storeJSON = (key, v) => { try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* private mode */ } };
const dropLS = (key) => { try { localStorage.removeItem(key); } catch { /* ignore */ } };

const S = {
  graph: null, board: { w: 150, h: 140 },
  nodes: [], edges: [], byId: new Map(),
  feedback: null, showIssues: true, showClearance: true, paramsCollapsed: false,
  padNets: true, padEdges: [], padLayer: null,
  issueFilter: { unrouted: true, clearance: true, channel: true },
  params: {}, paramOrder: [], paramSource: "defaults", model: null,
  repo: { file: "ui/placement/params.json", exists: false, values: 0 },
  repoState: "idle",
  sim: null, linkForce: null, chargeForce: null,
  xForce: null, yForce: null, collideForce: null, collideType: null,
  seedName: null, seedData: null,
  view: { k: 1, x: 0, y: 0 },
  hover: null, selected: null,
  onlyDraw: true, showLabels: true,
  paused: false, lastMetrics: 0, savedFile: null,
  scatterFixed: false,
};

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const fmt = (v, d = 1) => (v == null || Number.isNaN(v) ? "–" : (+v).toFixed(d));

// geometry + extents come from the shared model (KiCad Y-DOWN frame)
const { setExtents, padXY, isFixed } = M;

// --- load -------------------------------------------------------------------
async function boot() {
  const [graph, seeds, repo, feedback] = await Promise.all([
    fetch("/graph.json").then((r) => r.json()),
    fetch("/api/seeds").then((r) => r.json()),
    fetch("/api/params").then((r) => r.json()).catch(() => null),
    fetch("/api/route-feedback").then((r) => r.ok ? r.json() : null).catch(() => null),
  ]);
  S.graph = graph;
  S.board = graph.board;
  S.feedback = feedback;
  renderRoute();
  if (repo && repo.params) {
    S.repo = { file: repo.file || S.repo.file, exists: !!repo.exists,
      values: Object.keys(repo.params).length };
    S.repoData = { params: repo.params, order: repo.order };
  }
  buildLegend();

  const sel = $("#seed");
  const qs = new URLSearchParams(location.search).get("seed");
  for (const s of seeds.seeds) {
    const o = document.createElement("option");
    o.value = s.name;
    o.textContent = `${s.name}  ·  ${s.engine}  ·  ${s.n} parts` +
      (s.tracked ? "  ·  saved" : "");
    if (s.name === (qs || seeds.default)) o.selected = true;
    sel.appendChild(o);
  }
  buildParams();                 // params + order must exist before the sim is built
  restoreUI(qs || seeds.default); // seed + toggles from the last session
  S.seedName = sel.value;
  await loadSeed(S.seedName, !!qs);
  bindEvents();
  fitView();
  setStatus("ready");
}

// Which parameters to run: PoC defaults < the seed file's params < your last
// session in this browser.  Position data is never restored implicitly.
function restoreUI(defSeed) {
  const ui = loadJSON(LS.ui, {}) || {};
  const sel = $("#seed");
  const want = ui.seed || defSeed;
  if ([...sel.options].some((o) => o.value === want)) sel.value = want;
  S.onlyDraw = ui.onlyDraw !== false; $("#onlyDraw").checked = S.onlyDraw;
  S.showLabels = ui.showLabels !== false; $("#showLabels").checked = S.showLabels;
  S.showClearance = ui.showClearance !== false; $("#showClearance").checked = S.showClearance;
  S.padNets = ui.padNets !== false; $("#padNets").checked = S.padNets;
  S.showIssues = ui.showIssues !== false; $("#showIssues").checked = S.showIssues;
  S.paramsCollapsed = ui.paramsCollapsed === true;
  applyParamsCollapse();
  if (ui.issueFilter && typeof ui.issueFilter === "object") {
    for (const k of ["unrouted", "clearance", "channel"]) {
      if (ui.issueFilter[k] === false) S.issueFilter[k] = false;
    }
  }
  S.scatterFixed = ui.scatterFixed === true; $("#scatterFixed").checked = S.scatterFixed;
  if (ui.saveName) $("#saveName").value = ui.saveName;
}

function saveUI() {
  storeJSON(LS.ui, {
    seed: S.seedName, onlyDraw: S.onlyDraw, showLabels: S.showLabels,
    showClearance: S.showClearance, showIssues: S.showIssues,
    paramsCollapsed: S.paramsCollapsed, issueFilter: S.issueFilter, padNets: S.padNets,
    scatterFixed: S.scatterFixed, saveName: $("#saveName").value,
  });
}

async function loadSeed(name, force = false) {
  S.seedName = name;
  const data = await fetch("/api/seed?name=" + encodeURIComponent(name)).then((r) => r.json());
  S.seedData = data;
  applySeedParams(data, force);
  syncParamInputs();
  updateParamNote();
  S.nodes = S.graph.nodes.map((gn) => {
    const p = data.positions[gn.id] || { x: S.board.w / 2, y: S.board.h / 2, angle: 0 };
    const n = { ...gn, x: p.x, y: p.y, angle: p.angle || 0, pinned: false };
    // The two power terminals are *pinned*, but the seed decides where they are:
    // the graph's anchor is the hand floorplan's position ("XT60 — back centre")
    // and is only the fallback for a seed that has no position for them.  Taking
    // it as the position silently discarded a moved terminal on every load (and
    // fabricated courtyard overlaps the file did not have) — docs/history/0004.
    if (gn.anchor && !data.positions[gn.id]) { n.x = gn.anchor[0]; n.y = gn.anchor[1]; }
    setExtents(n);
    if (gn.anchor || (p.pin && !gn.anchor)) { n.fx = n.x; n.fy = n.y; }
    if (p.pin && !gn.anchor) n.pinned = true;
    return n;
  });
  S.byId = new Map(S.nodes.map((n) => [n.id, n]));
  M.assignHosts(S.nodes, S.graph, S.byId, { includePower: S.params.HOST_POWER });
  S.edges = S.graph.edges.map((e) => ({ ...e }));   // strings; forceLink rewrites to refs
  S.selected = null;
  $("#boardInfo").textContent =
    `${S.board.w} × ${S.board.h} mm · ${S.nodes.length} parts · ${S.edges.length} edges · seed ${name}`;
  boardRect.setAttribute("width", S.board.w); boardRect.setAttribute("height", S.board.h);
  gridRect.setAttribute("width", S.board.w); gridRect.setAttribute("height", S.board.h);
  buildScene();
  buildPadNets();
  buildIssues();
  buildSim();
  applyHighlight();
  renderPins();
  renderInspect();
  draw();
  renderMetrics();
  saveUI();
  setStatus(`seed ${name}`);
}

// --- simulation -------------------------------------------------------------
// The model itself (links, repulsion, centre pull, keep-in, collision, clamp,
// belongs-to ring) lives in model.js, shared with render.py's metric set.
function buildSim() {
  if (S.sim) S.sim.stop();
  const m = M.buildSim(S.nodes, S.edges, S.board, S.params);
  S.model = m; S.sim = m.sim;
  S.linkForce = m.link; S.chargeForce = m.charge;
  S.xForce = m.cx; S.yForce = m.cy; S.collideForce = m.collide;
  S.collideType = m.collideType;
  S.sim.on("tick", onTick).on("end", () => setStatus("settled"));
}

function applyParams(settle = true) {
  if (!S.sim || !S.model) return;
  M.applyParamsToSim(S.model, S.params);
  S.collideForce = S.model.collide; S.collideType = S.model.collideType;
  if (settle) reheat(Math.max(S.sim.alpha(), 0.6));
}

// Explicit "run it": the buttons that mean "start the solver again" (Solve,
// Scatter, Reset, Resume) clear the pause and reheat.
function solve(alpha = 1) {
  if (!S.sim) return;
  S.paused = false; updatePauseBtn();
  reheat(alpha);
}

// Implicit reheat: an edit to the placement (a drag, a pin/unpin, a parameter
// change) lets the solver settle *if it is running*.
function reheat(alpha = 1) {
  if (!S.sim || S.paused) return;
  S.sim.alpha(Math.max(alpha, 0.05)).restart();
  setStatus("solving…");
}

function onTick() {
  draw();
  const now = performance.now();
  if (now - S.lastMetrics > 120) {
    S.lastMetrics = now;
    renderMetrics();
    // A moving part can slide out from under a stationary cursor while the
    // solver runs; re-test the hover so the dim does not get stuck.
    if (!hoverStillValid()) { S.hover = null; tooltip.hidden = true; applyHighlight(); }
  }
}

let lastPointer = { x: -1, y: -1 };
function hoverStillValid() {
  if (!S.hover) return true;
  const el = document.elementFromPoint(lastPointer.x, lastPointer.y);
  const g = el && el.closest ? el.closest(".node") : null;
  return !!g && g.dataset.id === S.hover;
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

// Pad-level ratsnest: the router's view of a net (pad → pad), amp-coloured and
// sized by the required 2 oz width.  The force model keeps using the part-level
// springs; this only changes what the board draws.
const REQ_REF = 9.36;                 // 20 A on 2 oz outer (IPC-2221)
function buildPadNets() {
  let layer = document.getElementById("padnets");
  if (!layer) {
    layer = document.createElementNS(NS, "g");
    layer.id = "padnets";
    viewport.insertBefore(layer, layerNodes);
  }
  S.padLayer = layer;
  layer.replaceChildren();
  S.padEdges = M.padEdges(S.nodes, S.graph);
  for (const e of S.padEdges) {
    const el = document.createElementNS(NS, "line");
    el.setAttribute("class", "padnet");
    el.setAttribute("stroke", color(e.current));
    const sw = 0.12 + 0.95 * Math.pow(Math.min(1, e.required / REQ_REF), 0.6);
    el.setAttribute("stroke-width", sw.toFixed(3));
    el._op = 0.28 + 0.72 * Math.sqrt(Math.min(1, e.required / REQ_REF));
    el.setAttribute("stroke-opacity", el._op);
    e._el = el;
    layer.appendChild(el);
  }
  applyNetDisplay();
  drawPadNets();
}
function drawPadNets() {
  if (!S.padLayer) return;
  for (const e of S.padEdges) {
    if (!e._el) continue;
    const a = padXY(e.a.n, e.a.p), b = padXY(e.b.n, e.b.p);
    e._el.setAttribute("x1", a[0].toFixed(2)); e._el.setAttribute("y1", a[1].toFixed(2));
    e._el.setAttribute("x2", b[0].toFixed(2)); e._el.setAttribute("y2", b[1].toFixed(2));
  }
}
function applyNetDisplay() {
  if (S.padLayer) S.padLayer.style.display = S.padNets ? "" : "none";
  layerEdges.style.display = S.padNets ? "none" : "";
  applyHighlight();
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
  drawPads();
  drawIssues();
  drawPadNets();
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
    n._el.classList.toggle("selected", n.id === S.selected);
    n._text.style.display = S.showLabels ? "" : "none";
  }
}

// Selection is *sticky* (it fills the inspect panel), so changing it must not
// leave anything behind: re-style, refresh the panel and the pads, redraw.
function setSelected(id) {
  S.selected = id;
  styleNodes(); renderInspect(); updatePinButtons(); applyHighlight(); draw();
}

// Dim everything that is not the hovered part's neighbourhood.  Only *hover*
// dims — hovering is transient, so moving the cursor away brings the board
// back.  A selected part gets an outline instead of a fade (see style.css), so
// a single click no longer leaves the whole board dimmed.
function applyHighlight() {
  const h = S.hover;
  for (const e of S.edges) {
    const el = e._el; if (!el) continue;
    el.style.display = (!S.onlyDraw || e.draw) ? "" : "none";
    const touches = h && (e.source.id === h || e.target.id === h);
    el.setAttribute("stroke-opacity", touches ? Math.min(1, el._op + 0.5)
      : (h ? el._op * 0.12 : el._op));
    el.setAttribute("stroke-width",
      (0.12 + 0.95 * Math.pow(e.width / 18.71, 0.6)) * (touches ? 1.6 : 1));
  }
  for (const e of S.padEdges) {
    const el = e._el; if (!el) continue;
    const touches = h && (e.a.n.id === h || e.b.n.id === h);
    el.setAttribute("stroke-opacity", touches ? Math.min(1, el._op + 0.5)
      : (h ? el._op * 0.12 : el._op));
  }
  for (const n of S.nodes) {
    n._el.style.opacity = h && n.id !== h && !touchesNode(h, n.id) ? 0.45 : 1;
  }
}
function touchesNode(h, id) {
  return S.edges.some((e) =>
    (e.source.id === h && e.target.id === id) || (e.target.id === h && e.source.id === id));
}

// --- pads and the "belongs-to" line of the selected part --------------------
function drawPads() {
  let layer = document.getElementById("pads");
  if (!layer) { layer = document.createElementNS(NS, "g"); layer.id = "pads"; viewport.appendChild(layer); }
  layer.replaceChildren();
  const n = S.selected ? S.byId.get(S.selected) : null; if (!n) return;
  const h = n.host ? S.byId.get(n.host) : null;
  if (h) {                                  // show who it belongs to
    const l = document.createElementNS(NS, "line");
    l.setAttribute("x1", fmt(n.x + n.cx, 2)); l.setAttribute("y1", fmt(n.y + n.cy, 2));
    l.setAttribute("x2", fmt(h.x + h.cx, 2)); l.setAttribute("y2", fmt(h.y + h.cy, 2));
    l.setAttribute("class", "hostlink");
    layer.appendChild(l);
  }
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

// --- route feedback (from the last routed board) ----------------------------
// A routed board + its DRC report are turned into build/layout/route-feedback.json
// by hardware/route_feedback.py (make route).  The markers are *historical*:
// they are the router's verdict on the placement that was routed.  When an item
// names a reference/pad we anchor the marker to that pad in the live placement;
// a track item keeps its absolute coordinate.  Moving parts therefore moves the
// endpoints that we can identify, but the real answer is a fresh `make route`.
function issueXY(item) {
  if (!item) return null;
  if (item.ref) {
    const n = S.byId.get(item.ref);
    if (!n) return [item.x, item.y];
    const p = item.pad ? (n.pads || []).find((q) => q.num === item.pad) : null;
    return p ? padXY(n, p) : [n.x + n.cx, n.y + n.cy];
  }
  return [item.x, item.y];
}

function issueTitle(kind, a, b) {
  const one = (it) => it ? `${it.ref ? it.ref + (it.pad ? `.${it.pad}` : "") + " " : ""}` +
    `${it.net ? it.net + " " : ""}${it.kind || ""}` : "?";
  return `${kind}: ${one(a)} ↔ ${one(b)}`;
}

function buildIssues() {
  let layer = document.getElementById("issues");
  if (!layer) {
    layer = document.createElementNS(NS, "g");
    layer.id = "issues";
    viewport.appendChild(layer);
    layer.addEventListener("click", (ev) => {
      const el = ev.target.closest(".issue-unrouted,.issue-clearance,.issue-channel");
      const ref = el && el.dataset.ref;
      if (ref && S.byId.has(ref)) setSelected(ref);
    });
  }
  S.issuesLayer = layer;
  layer.replaceChildren();
  layer.style.display = S.showIssues ? "" : "none";
  const f = S.feedback; if (!f) return;

  const add = (el, a, b, title) => {
    el._a = a; el._b = b;
    el.dataset.issue = el.dataset.kind;
    if (a && a.ref && S.byId.has(a.ref)) el.dataset.ref = a.ref;
    else if (b && b.ref && S.byId.has(b.ref)) el.dataset.ref = b.ref;
    const t = document.createElementNS(NS, "title");
    t.textContent = title || issueTitle(el.dataset.kind || "", a, b);
    el.appendChild(t);
    layer.appendChild(el);
  };
  // A clearance violation between two adjacent QFN pads is a ~0.4 mm segment:
  // invisible at board zoom.  Draw a ring on each item, plus the line for the
  // spread-out cases.
  const addRing = (a, b, title) => {
    const el = document.createElementNS(NS, "circle");
    el.setAttribute("class", "issue-clearance");
    el.dataset.kind = "clearance";
    el._one = a || b;
    el.dataset.issue = "clearance";
    if (a && a.ref && S.byId.has(a.ref)) el.dataset.ref = a.ref;
    else if (b && b.ref && S.byId.has(b.ref)) el.dataset.ref = b.ref;
    const t = document.createElementNS(NS, "title");
    t.textContent = title;
    el.appendChild(t);
    layer.appendChild(el);
  };

  for (const u of f.unrouted || []) {
    const el = document.createElementNS(NS, "line");
    el.setAttribute("class", "issue-unrouted");
    el.dataset.kind = "unrouted";
    add(el, u.a, u.b);
  }
  for (const c of f.clearance || []) {
    const title = `clearance ${fmt(c.actual_mm, 2)} mm (needs ${fmt(c.required_mm, 2)}) · ` +
      issueTitle("clearance", c.a, c.b);
    const el = document.createElementNS(NS, "line");
    el.setAttribute("class", "issue-clearance");
    el.dataset.kind = "clearance";
    add(el, c.a, c.b, title);
    addRing(c.a, c.b, title);
    addRing(c.b, c.a, title);
  }
  for (const c of f.power_channels || []) {
    if (c.ok || !c.pinch) continue;
    const el = document.createElementNS(NS, "circle");
    el.setAttribute("class", "issue-channel");
    el.dataset.kind = "channel";
    el.dataset.issue = "channel";
    el._p = [c.pinch.x, c.pinch.y];
    el.dataset.ref = "";
    const t = document.createElementNS(NS, "title");
    t.textContent = `power channel ${c.net}: ${c.channel_mm} of ${c.required_mm} mm`;
    el.appendChild(t);
    layer.appendChild(el);
  }
  drawIssues();
  applyIssueFilter();
}

// Legend rows toggle a marker class, so a board with 284 unrouted connections
// can still show its 21 clearance violations.
function applyIssueFilter() {
  if (S.issuesLayer) {
    for (const el of S.issuesLayer.children) {
      const k = el.dataset.issue;
      if (k) el.style.display = S.issueFilter[k] === false ? "none" : "";
    }
  }
  for (const row of document.querySelectorAll("#routeLegend .rowline")) {
    row.classList.toggle("off", S.issueFilter[row.dataset.issue] === false);
  }
}

function drawIssues() {
  if (!S.issuesLayer) return;
  for (const el of S.issuesLayer.children) {
    if (el._one) {                              // clearance ring on one item
      const p = issueXY(el._one);
      if (!p) continue;
      el.setAttribute("cx", p[0].toFixed(2));
      el.setAttribute("cy", p[1].toFixed(2));
      el.setAttribute("r", "0.9");
    } else if (el._a && el._b) {                // unrouted / clearance line
      const a = issueXY(el._a), b = issueXY(el._b);
      if (!a || !b) continue;
      el.setAttribute("x1", a[0].toFixed(2)); el.setAttribute("y1", a[1].toFixed(2));
      el.setAttribute("x2", b[0].toFixed(2)); el.setAttribute("y2", b[1].toFixed(2));
    } else if (el._p) {                         // power-channel ring
      el.setAttribute("cx", el._p[0].toFixed(2));
      el.setAttribute("cy", el._p[1].toFixed(2));
      el.setAttribute("r", "1.4");
    }
  }
}

function renderRoute() {
  const f = S.feedback;
  const summary = $("#routeSummary"), table = $("#routeNets"), note = $("#routeNote");
  const legend = $("#routeLegend");
  if (!summary) return;
  if (!f) {
    summary.innerHTML = "no route feedback yet — run <code>make route</code> " +
      "(it writes <code>build/layout/route-feedback.json</code>).";
    table.innerHTML = ""; note.textContent = ""; legend.innerHTML = "";
    return;
  }
  const s = f.summary || {};
  $("#routeTag").textContent = (s.tracks ? "last route · " : "applied board · ") +
    (f.board || "?").split("/").pop();
  summary.innerHTML =
    `<b>${s.unrouted || 0}</b> unrouted · <b>${s.clearance || 0}</b> clearance · ` +
    `${s.power_channels_short || 0} power channel short<br>` +
    `${s.tracks || 0} tracks · ${s.vias || 0} vias · min trace ` +
    `${s.min_track_mm == null ? "–" : s.min_track_mm + " mm"} · ` +
    `routed ${s.routed_length_mm == null ? "–" : s.routed_length_mm + " mm"}`;
  legend.innerHTML =
    `<div class="rowline" data-issue="unrouted" title="click to show / hide">` +
    `<span class="sw-unrouted"></span>` +
    `<span>${s.unrouted || 0} unrouted connection${s.unrouted === 1 ? "" : "s"} ` +
    `(red dashed)</span></div>` +
    `<div class="rowline" data-issue="clearance" title="click to show / hide">` +
    `<span class="sw-clearance"></span>` +
    `<span>${s.clearance || 0} clearance violation${s.clearance === 1 ? "" : "s"} ` +
    `(amber)</span></div>` +
    `<div class="rowline" data-issue="channel" title="click to show / hide">` +
    `<span class="sw-channel"></span>` +
    `<span>${s.power_channels_short || 0} power channel short ` +
    `(magenta ring)</span></div>`;
  applyIssueFilter();
  const ch = f.power_channels || [];
  table.innerHTML = ch.length ? ch.map((c) =>
    `<tr class="${c.ok ? "" : "bad"}"><td>${c.net}</td>` +
    `<td>${fmt(c.channel_mm, 1)} / ${fmt(c.required_mm, 1)} mm</td></tr>`).join("") : "";
  note.innerHTML = `channel = measured pour width / IPC-2221 2 oz requirement. ` +
    `Markers are the ${s.tracks ? "last route" : "applied board DRC"}'s verdict; ` +
    `they follow named parts, but only a fresh <code>make route</code> answers a ` +
    `moved placement.`;
}

// --- metrics ----------------------------------------------------------------
// The metric set lives in model.js (the same numbers the UI shows); render.py computes
// the same set in python for the boards it renders.
function metrics() {
  return M.metrics(S.nodes, S.edges, S.graph, S.board, S.byId);
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
    ["min pad clearance", m.clearance.min == null ? "–" : `${fmt(m.clearance.min, 2)} mm`,
      m.clearance.min == null ? "" : m.clearance.min < 0.2 ? "bad" : "good"],
    ["parts < 0.2 mm", m.clearance.tight, m.clearance.tight ? "bad" : "good"],
    ["power path (mm)", fmt(m.path, 0), ""],
    ["straightness", fmt(m.straight, 2), ""],
    ["flow axisR", fmt(m.axis_r, 2), m.axis_r > 0.4 ? "good" : ""],
    ["in / out (mm)", `${fmt(m.d_in, 0)} / ${fmt(m.d_out, 0)}`, ""],
  ];
  // The "fan" per controller — the thing the belongs-to force is for: how far
  // its small parts sit (d), whether they are all on the centre side (bias) and
  // how much room they have (spacing).  These are the same numbers the headless renderer reports.
  for (const [ref, f] of Object.entries(m.fan || {})) {
    rows.push([`${ref} fan · d/bias/sp`, `${fmt(f.d, 1)} / ${fmt(f.bias, 2)} / ${fmt(f.spacing, 1)}`,
      f.bias < 0.25 && f.d < 25 ? "good" : ""]);
  }
  $("#metrics").innerHTML = rows.map(([k, v, cls]) =>
    `<tr class="${cls}"><td>${k}</td><td>${v}</td></tr>`).join("");
  for (const n of S.nodes) {
    if (!n._el) continue;
    n._el.classList.toggle("tight", S.showClearance && n.clear != null);
    n._el.classList.toggle("overlap", S.showClearance && !!n.overlap);
  }
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
    '<span class="hint">none — drag a part to pin it, or use Pin selected</span>';
  updatePinButtons();
}

function pin(n) { if (n.anchor != null) return; n.pinned = true; n.fx = n.x; n.fy = n.y; }
function unpin(n) { if (n.anchor != null) return; n.pinned = false; n.fx = null; n.fy = null; }
function unpinAll() { for (const n of S.nodes) unpin(n); styleNodes(); renderPins(); reheat(0.8); }

// Pin / unpin the *selected* part in place.  A drag also pins, but this is the
// explicit "fix this one where it is" action (and the counterpart to unpin).
function pinSelected() {
  const n = S.selected ? S.byId.get(S.selected) : null;
  if (!n || n.pinned || n.anchor != null) return;
  pin(n);
  styleNodes(); renderPins(); renderInspect(); reheat(0.5);
}
function unpinSelected() {
  const n = S.selected ? S.byId.get(S.selected) : null;
  if (!n || n.anchor != null) return;
  unpin(n);
  styleNodes(); renderPins(); renderInspect(); reheat(0.8);
}
function updatePinButtons() {
  const pinBtn = $("#pinSel"), unpinBtn = $("#unpinSel");
  const cw = $("#rotCW"), ccw = $("#rotCCW");
  if (!pinBtn || !unpinBtn) return;
  const n = S.selected ? S.byId.get(S.selected) : null;
  pinBtn.disabled = !n || n.pinned || n.anchor != null;
  unpinBtn.disabled = !n || (!n.pinned && n.anchor == null);
  if (cw) cw.disabled = !n;
  if (ccw) ccw.disabled = !n;
}

// Rotate the selected part in place.  A part is rotated about its origin, the
// pads move with it, and a pinned/anchored part stays at its x/y.  The solver
// is only nudged: the user may want to look before the collision force reacts.
function rotateSelected(delta) {
  const n = S.selected ? S.byId.get(S.selected) : null;
  if (!n) return;
  n.angle = ((n.angle + delta) % 360 + 360) % 360;
  setExtents(n);
  const poly = n._el && n._el.querySelector(".courtyard");
  if (poly) poly.setAttribute("points", n._pts.map((p) => p.join(",")).join(" "));
  const t = n._el && n._el.querySelector("text");
  if (t) { t.setAttribute("x", fmt(n.cx, 2)); t.setAttribute("y", fmt(n.cy, 2)); }
  draw();
  renderMetrics();
  renderInspect();
  reheat(0.3);
}

// --- inspect ----------------------------------------------------------------
function renderInspect() {
  const n = S.selected ? S.byId.get(S.selected) : null;
  if (!n) { $("#inspBody").innerHTML = '<span class="hint">nothing selected</span>'; return; }
  const nets = [...new Set(n.pads.filter((p) => p.net).map((p) => p.net))]
    .map((net) => {
      const g = S.graph.nets[net] || {};
      const req = g.required != null ? g.required : g.width;
      const model = g.width != null && g.required != null && Math.abs(g.width - g.required) > 0.01
        ? ` · model ${fmt(g.width, 2)}` : "";
      return `<tr><td>${net}</td><td>${fmt(g.current || 0, 1)} A · req ${fmt(req || 0.25, 2)} mm${model}</td></tr>`;
    }).join("");
  const rf = (S.feedback && S.feedback.parts && S.feedback.parts[n.id]) || null;
  const clear = n.clear == null ? "–" : `${fmt(n.clear, 2)} mm` +
    (n.clearRef ? ` → ${n.clearRef} (${n.clearNet})` : "");
  $("#inspBody").innerHTML = `
    <div class="row"><b>${n.label || n.id}</b> <span class="tag">${n.kind}${n.power ? " · power" : ""}</span></div>
    <div class="hint">${n.value || ""}<br>${n.fp || ""}</div>
    <table id="metrics" style="margin-top:6px">
      <tr><td>position</td><td>${fmt(n.x)}, ${fmt(n.y)} mm</td></tr>
      <tr><td>courtyard</td><td>${fmt(n.w)} × ${fmt(n.h)} mm</td></tr>
      <tr><td>rotation</td><td>${n.angle}°${
        S.seedData && S.seedData.positions[n.id] &&
        Math.abs((S.seedData.positions[n.id].angle || 0) - n.angle) > 0.01
          ? ` (seed ${S.seedData.positions[n.id].angle || 0}°)` : ""}</td></tr>
      <tr><td>pinned</td><td>${n.pinned ? "yes" : n.anchor != null ? "terminal" : "no"}</td></tr>
      <tr class="${n.clear != null ? "bad" : ""}"><td>min pad clearance</td><td>${clear}</td></tr>
      ${rf ? `<tr class="${rf.unrouted + rf.clearance ? "bad" : ""}"><td>last route</td><td>${rf.unrouted} unrouted · ${rf.clearance} clearance${rf.min_clearance_mm != null ? ` · ${fmt(rf.min_clearance_mm, 2)} mm` : ""}</td></tr>` : ""}
      ${n.host ? `<tr><td>belongs to</td><td>${n.host}${n.hostScore ? ` (net score ${fmt(n.hostScore, 2)})` : " (nearest IC)"}</td></tr>` : ""}
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
      S.hover = n.id;
      setSelected(n.id);
      drag = { n, moved: false, sx: ev.clientX, sy: ev.clientY };
      svg.setPointerCapture(ev.pointerId);
      svg.classList.add("readonly");
    } else {
      pan = { sx: ev.clientX, sy: ev.clientY, vx: S.view.x, vy: S.view.y, moved: false };
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
        if (S.sim && !S.paused) S.sim.alphaTarget(0.3).restart();
      }
      if (drag.moved) {
        drag.n.fx = clamp(mm.x, 0, S.board.w);
        drag.n.fy = clamp(mm.y, 0, S.board.h);
        drag.n.x = drag.n.fx; drag.n.y = drag.n.fy;
        drag.n._el.classList.add("dragging");
        draw(); if (!S.sim || S.paused) renderMetrics();
      }
      return;
    }
    if (pan) {
      if (!pan.moved && Math.hypot(ev.clientX - pan.sx, ev.clientY - pan.sy) > 2) pan.moved = true;
      S.view.x = pan.vx + (ev.clientX - pan.sx);
      S.view.y = pan.vy + (ev.clientY - pan.sy);
      applyView();
    }
  });

  const end = () => {
    if (drag) {
      drag.n._el.classList.remove("dragging");
      if (S.sim && !S.paused) S.sim.alphaTarget(0);  // let it settle, part stays pinned
      drag = null;
    }
    if (pan) {
      // A click on empty space (no pan) clears the selection.
      if (!pan.moved) setSelected(null);
      pan = null;
    }
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
  // Leaving the board at all must clear the hover, otherwise the last hovered
  // part keeps dimming everything from a distance.
  svg.addEventListener("pointerleave", () => {
    S.hover = null; tooltip.hidden = true; applyHighlight();
  });
  svg.addEventListener("pointermove", (ev) => {
    lastPointer = { x: ev.clientX, y: ev.clientY };
    if (S.hover && !drag && !pan) showTip(ev, S.hover);
    if (!S.hover) tooltip.hidden = true;
  });

  svg.addEventListener("contextmenu", (ev) => {
    const g = ev.target.closest(".node"); if (!g) return;
    ev.preventDefault();
    const n = S.byId.get(g.dataset.id);
    if (n.pinned) unpin(n); else pin(n);
    styleNodes(); renderPins(); renderInspect(); reheat(0.8);
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
    styleNodes(); renderPins(); renderInspect(); reheat(0.8);
  });

  $("#seed").addEventListener("change", () => loadSeed($("#seed").value, true));
  $("#load").addEventListener("click", () => loadSeed($("#seed").value, true));
  $("#solve").addEventListener("click", () => solve(1));
  $("#pause").addEventListener("click", () => {
    S.paused = !S.paused;
    if (S.paused) S.sim.stop(); else S.sim.restart();
    updatePauseBtn();
    renderMetrics();   // no ticks while stopped, so refresh the status line here
  });
  $("#reset").addEventListener("click", resetToSeed);
  $("#scatter").addEventListener("click", scatter);
  $("#fit").addEventListener("click", fitView);
  $("#unpin").addEventListener("click", unpinAll);
  $("#pinSel").addEventListener("click", pinSelected);
  $("#unpinSel").addEventListener("click", unpinSelected);
  $("#rotCW").addEventListener("click", () => rotateSelected(90));
  $("#rotCCW").addEventListener("click", () => rotateSelected(-90));
  $("#onlyDraw").addEventListener("change", (e) => { S.onlyDraw = e.target.checked; applyHighlight(); saveUI(); });
  $("#showLabels").addEventListener("change", (e) => { S.showLabels = e.target.checked; styleNodes(); saveUI(); });
  $("#showClearance").addEventListener("change", (e) => {
    S.showClearance = e.target.checked;
    for (const n of S.nodes) {
      if (!n._el) continue;
      n._el.classList.toggle("tight", S.showClearance && n.clear != null);
      n._el.classList.toggle("overlap", S.showClearance && !!n.overlap);
    }
    saveUI();
  });
  $("#padNets").addEventListener("change", (e) => {
    S.padNets = e.target.checked;
    applyNetDisplay();
    saveUI();
  });
  $("#showIssues").addEventListener("change", (e) => {
    S.showIssues = e.target.checked;
    if (S.issuesLayer) S.issuesLayer.style.display = S.showIssues ? "" : "none";
    saveUI();
  });
  $("#toggleParams").addEventListener("click", () => {
    S.paramsCollapsed = !S.paramsCollapsed;
    applyParamsCollapse();
    saveUI();
  });
  $("#routeLegend").addEventListener("click", (ev) => {
    const row = ev.target.closest(".rowline");
    const k = row && row.dataset.issue;
    if (!k) return;
    S.issueFilter[k] = S.issueFilter[k] === false;
    applyIssueFilter();
    saveUI();
  });
  $("#scatterFixed").addEventListener("change", (e) => { S.scatterFixed = e.target.checked; saveUI(); });
  $("#save").addEventListener("click", save);
  $("#apply").addEventListener("click", apply);
  window.addEventListener("resize", fitView);
  // Don't lose the last edit if the tab goes away inside the debounce window.
  window.addEventListener("pagehide", () => { if (repoWriteTimer) writeRepo(true); });
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { S.hover = null; applyHighlight(); setSelected(null); }
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

// The engine parameter list is long; collapse the whole Engine body (the view
// toggles, the parameters and the notes) with the button in its heading.
function applyParamsCollapse() {
  const body = $("#engineBody"), btn = $("#toggleParams");
  if (!body || !btn) return;
  body.hidden = S.paramsCollapsed;
  btn.textContent = S.paramsCollapsed ? "▸" : "▾";
  btn.title = (S.paramsCollapsed ? "Expand" : "Collapse") + " the engine parameters";
}

function resetToSeed() {
  const data = S.seedData;
  for (const n of S.nodes) {
    const p = data.positions[n.id]; if (!p) continue;
    n.x = p.x; n.y = p.y; n.angle = p.angle || 0; setExtents(n);
    n.pinned = false; n.fx = null; n.fy = null;
    // the seed's position stands, even for an anchored terminal (see loadSeed)
    if (n.anchor || p.pin) { n.pinned = !n.anchor && !!p.pin; n.fx = n.x; n.fy = n.y; }
    n._el.setAttribute("transform", `translate(${n.x},${n.y})`);
    n._el.querySelector(".courtyard").setAttribute("points", n._pts.map((q) => q.join(",")).join(" "));
    n._el.querySelector("text").setAttribute("x", fmt(n.cx, 2));
    n._el.querySelector("text").setAttribute("y", fmt(n.cy, 2));
  }
  styleNodes(); renderPins(); draw(); solve(1);
}

const randomSeed = () => 1 + Math.floor(Math.random() * 999999);

// Scatter = uniform-random start over the whole board, from the model's shared
// generator   It
// rolls a fresh seed every click and writes it back into SEED, so a start you
// like is reproducible: tick "reuse SEED" and click again.
function scatter() {
  const seed = S.scatterFixed ? Math.round(S.params.SEED) : randomSeed();
  if (!S.scatterFixed) {
    S.params.SEED = seed;
    syncParamInputs();
    scheduleRepoWrite();
  }
  M.scatterPositions(S.nodes, S.board, seed);
  styleNodes(); renderPins(); solve(1);
  setStatus(`scatter · seed ${seed}${S.scatterFixed ? " (fixed)" : ""}`);
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
// The base config is the tracked repo file (ui/placement/params.json).
// Every edit is written back to it, debounced — so git holds the tuning history
// and `git checkout` undoes a bad experiment.  The row order is part of that
// file too: it is how "which knobs matter" is recorded.
const REPO_WRITE_MS = 700;
let repoWriteTimer = null;

function buildParams() {
  for (const p of PARAM_SPEC) S.params[p.key] = p.d;
  const base = (S.repoData && S.repoData.params) || {};
  let fromRepo = 0;
  for (const p of PARAM_SPEC) if (base[p.key] != null) { S.params[p.key] = coerceParam(p, base[p.key]); fromRepo++; }
  if (fromRepo) S.paramSource = "repo";

  // One-time migration of the pre-repo-file session store (localStorage).
  const legacy = loadJSON(LS.legacyParams, null);
  if (!fromRepo && legacy && typeof legacy === "object") {
    let n = 0;
    for (const p of PARAM_SPEC) if (legacy[p.key] != null) { S.params[p.key] = coerceParam(p, legacy[p.key]); n++; }
    if (n) { S.paramSource = "repo"; S.migrated = true; }
  }
  const legacyOrder = loadJSON(LS.legacyOrder, null);
  const order = (S.repoData && S.repoData.order) || (Array.isArray(legacyOrder) ? legacyOrder : null);

  S.paramOrder = [];
  if (Array.isArray(order)) for (const k of order) {
    if (PARAM_SPEC.some((p) => p.key === k) && !S.paramOrder.includes(k)) S.paramOrder.push(k);
  }
  for (const p of PARAM_SPEC) if (!S.paramOrder.includes(p.key)) S.paramOrder.push(p.key);

  const host = $("#params");
  renderParams();
  host.addEventListener("input", onParamInput);
  bindParamDnD(host);
  dropLS(LS.legacyParams); dropLS(LS.legacyOrder);   // one store only
  if (S.migrated) scheduleRepoWrite(0);              // keep what the user had
  $("#engineNote").innerHTML =
    "engine = <b>d3-force 3.0.0</b> (vendored, runs in this tab). " +
    "Link distance = D0 + DK·(width/WREF); link strength = weight·(SIG_STR + " +
    "(POW_STR−SIG_STR)·(width/WREF)<sup>1.2</sup>) — both wired via " +
    "forceLink.distance()/strength(). <i>(The old headless engine never called " +
    "those, so in that run D0/DK/DMAX and SIG_STR/POW_STR were inert — d3 " +
    "defaults: 30 mm, 1/degree.)</i>";
}

const coerceParam = (p, v) => p.type === "check" ? !!v : clamp(+v, p.min, p.max);

function renderParams() {
  const host = $("#params");
  host.replaceChildren();
  for (const key of S.paramOrder) {
    const p = PARAM_SPEC.find((q) => q.key === key);
    if (p) host.appendChild(paramRow(p));
  }
  const row = document.createElement("div");
  row.className = "row";
  row.style.marginTop = "8px";
  const reset = document.createElement("button");
  reset.textContent = "↺ Default values";
  reset.title = "Back to the built-in default values and write that to params.json";
  reset.addEventListener("click", resetParams);
  const dord = document.createElement("button");
  dord.textContent = "↕ Default order";
  dord.title = "Back to the built-in parameter order (drops the override)";
  dord.addEventListener("click", () => {
    S.paramOrder = PARAM_SPEC.map((p) => p.key);
    renderParams();
    scheduleRepoWrite(0);
  });
  row.append(reset, dord);
  host.appendChild(row);
  syncParamInputs();
}

function paramRow(p) {
  const wrap = document.createElement("div");
  wrap.className = "param";
  wrap.dataset.key = p.key;
  if (p.type === "check") {
    wrap.innerHTML = `<div class="lbl handle" draggable="true" title="drag to reorder">
        <span class="grip">⠿</span>
        <label class="switch"><input type="checkbox" data-key="${p.key}"> ${p.label}</label>
      </div><div class="help">${p.help}</div>`;
  } else {
    wrap.innerHTML = `<div class="lbl handle" draggable="true" title="drag to reorder">
        <span class="grip">⠿</span><span class="name">${p.label}</span>
        <span class="key">${p.key}</span>
      </div>
      <div class="ctl">
        <input type="range" data-key="${p.key}" min="${p.min}" max="${p.max}" step="${p.step}">
        <input type="number" data-key="${p.key}" min="${p.min}" max="${p.max}" step="${p.step}">
      </div><div class="help">${p.help}</div>`;
  }
  return wrap;
}

function syncParamInputs() {
  for (const el of document.querySelectorAll("#params [data-key]")) {
    const v = S.params[el.dataset.key];
    if (el.type === "checkbox") el.checked = !!v; else el.value = v;
  }
}

function onParamInput(ev) {
  const key = ev.target.dataset.key; if (!key) return;
  const spec = PARAM_SPEC.find((p) => p.key === key); if (!spec) return;
  const v = spec.type === "check" ? ev.target.checked : clamp(+ev.target.value, spec.min, spec.max);
  S.params[key] = v;
  for (const el of document.querySelectorAll(`#params [data-key="${key}"]`)) {
    if (el.type === "checkbox") el.checked = v; else el.value = v;
  }
  if (S.paramSource !== "repo") { S.paramSource = "repo"; updateParamNote(); }
  scheduleRepoWrite();
  applyParams(true);
}

// --- the tracked tuning file ------------------------------------------------
const orderIsDefault = () => {
  const def = PARAM_SPEC.map((p) => p.key);
  return S.paramOrder.length === def.length && S.paramOrder.every((k, i) => k === def[i]);
};

function scheduleRepoWrite(delay = REPO_WRITE_MS) {
  if (repoWriteTimer) clearTimeout(repoWriteTimer);
  setRepoState("dirty");
  repoWriteTimer = setTimeout(() => writeRepo(), delay);
}

// A PUT; with beacon=true it is the unload path (sendBeacon, POST).
async function writeRepo(beacon = false) {
  if (repoWriteTimer) { clearTimeout(repoWriteTimer); repoWriteTimer = null; }
  const payload = JSON.stringify({
    params: S.params,
    order: orderIsDefault() ? null : S.paramOrder,   // null = no override
  });
  try {
    if (beacon && navigator.sendBeacon) {
      navigator.sendBeacon("/api/params", new Blob([payload], { type: "application/json" }));
      return;
    }
    setRepoState("saving");
    const r = await fetch("/api/params", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: payload,
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || `HTTP ${r.status}`);
    S.repo = { file: j.file, exists: true, values: j.values };
    setRepoState("saved");
  } catch (e) {
    setRepoState("error", String(e.message || e));
  }
}

function setRepoState(state, err) {
  // Don't rewrite the note on every input event of a slider drag — only when
  // something actually changed.
  const changed = state !== S.repoState || (!!err && err !== S.repoError);
  S.repoState = state;
  if (err) S.repoError = err;
  if (changed) updateParamNote();
}

function resetParams() {
  for (const p of PARAM_SPEC) S.params[p.key] = p.d;
  S.paramSource = "repo";
  syncParamInputs();
  scheduleRepoWrite(0);
  applyParams(true);
}

// A seed file that carries its own engine params (pos-*.json and saved
// interactive-*.json do) configures the run — but only when you *pick* it:
// a plain reload keeps the tracked tuning, and the seed's values stay in the
// session until you change a parameter (then the file records what you run).
function applySeedParams(data, force = false) {
  if (!force || !data || !data.params) return;
  let any = false;
  for (const p of PARAM_SPEC) {
    if (data.params[p.key] != null) { S.params[p.key] = coerceParam(p, data.params[p.key]); any = true; }
  }
  if (any) S.paramSource = "seed";
}

function updateParamNote() {
  const note = $("#paramNote"); if (!note) return;
  const f = `<code>${S.repo.file}</code>`;
  const base = {
    repo: `values from ${f}`,
    defaults: `${f} has no <code>params</code> yet — running the built-in defaults`,
    seed: "values from the seed file — <b>not in the repo file</b> until you change a parameter",
  }[S.paramSource] || S.paramSource;
  const state = {
    dirty: " · writing…",
    saving: " · saving…",
    saved: ` · written (${S.repo.values} values)`,
    error: ` · <b>write failed: ${S.repoError || "?"}</b>`,
    idle: "",
  }[S.repoState] || "";
  note.innerHTML = `${base}${state} · tracked in git, so <code>git checkout
    ${S.repo.file}</code> undoes a bad experiment · <i>drag a row by its ⠿ grip
    to reorder</i>`;
}

// Rows reorder live (the DOM is moved, not re-rendered, so the drag survives);
// the order is read back from the DOM when the drag ends and written to the
// tuning file.
function bindParamDnD(host) {
  let dragKey = null;
  const finish = () => {
    if (!dragKey) return;
    dragKey = null;
    host.querySelectorAll(".param.dragging").forEach((el) => el.classList.remove("dragging"));
    const before = S.paramOrder.join(",");
    S.paramOrder = [...host.querySelectorAll(".param")].map((el) => el.dataset.key);
    if (S.paramOrder.join(",") !== before) scheduleRepoWrite(0);
  };
  host.addEventListener("dragstart", (ev) => {
    const row = ev.target.closest(".param"); if (!row) return;
    dragKey = row.dataset.key;
    row.classList.add("dragging");
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", dragKey);
  });
  host.addEventListener("dragover", (ev) => {
    if (!dragKey) return;
    const over = ev.target.closest(".param");
    if (!over || over.dataset.key === dragKey) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
    const dragged = host.querySelector(`.param[data-key="${dragKey}"]`);
    if (!dragged) return;
    const r = over.getBoundingClientRect();
    const after = ev.clientY > r.top + r.height / 2;
    host.insertBefore(dragged, after ? over.nextSibling : over);
  });
  host.addEventListener("drop", (ev) => { ev.preventDefault(); finish(); });
  host.addEventListener("dragend", finish);
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
  saveUI();
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
    if (j.feedback) await reloadFeedback();
  } finally { $("#apply").disabled = false; }
}

// Re-read build/layout/route-feedback.json after an apply or a route run.  It
// is optional: a missing file just means the panel says "run make route".
async function reloadFeedback() {
  try {
    const r = await fetch("/api/route-feedback");
    S.feedback = r.ok ? await r.json() : null;
  } catch { S.feedback = null; }
  renderRoute();
  buildIssues();
  draw();
}

function setStatus(msg) { statusEl.textContent = msg; }

// Expose the state for debugging / power users from the console.
S.metrics = metrics; S.renderMetrics = renderMetrics; S.draw = draw; S.solve = solve;
S.scatter = scatter; S.resetParams = resetParams; S.saveUI = saveUI; S.setSelected = setSelected;
S.writeRepo = writeRepo; S.LS = LS; S.model = M;   // place.assignHosts(nodes, graph, byId) re-derives hosts
globalThis.place = S;

boot().catch((e) => {
  setStatus("error: " + e.message);
  console.error(e);
});
