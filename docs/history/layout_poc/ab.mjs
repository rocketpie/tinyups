#!/usr/bin/env node
// A/B the placement model on a *neutral* start.
//
// A force-model change must be judged on a start that carries no opinions: the
// same scatter (or the same engine output) for every config, N runs, and one row
// per config.  A hand placement (hardware/layout_poc/placements/) is *not* a
// neutral start — it is half-solved by a human, its pins encode that human's
// intent, and a force that "wins" from there may simply be agreeing with them;
// the tool warns when you point it at one.
//
// The model itself (and the metrics) come from web/public/model.js — the same
// module the browser UI runs, so a row here is reproducible in the UI.
//
//   node ab.mjs                                   # scatter start, 3 seeds, base tuning
//   node ab.mjs --runs 5 --config "host off:HOST_STR=0" \
//               --config "host 1.5/5:HOST_STR=1.5,HOST_D=5"
//   node ab.mjs --start build/layout/pos-gv-sfdp.json   # engine output as the start
//   node ab.mjs --tuning hardware/layout_poc/params.json # start from the tracked tuning
//
// Options:
//   --start scatter|<file.json>  neutral start (default scatter; place-*.json warns)
//   --runs N                     independent seeds per config (default 3)
//   --seed N                     first seed; runs use seed, seed+1, … (default 20260101)
//   --iters N                    override ITERS (ticks for alpha -> 0.001)
//   --config "name:K=V,K=V"      one config per flag (default: "base")
//   --tuning file.json           load {params:{…}} as the base values (default DEFAULTS)
//   --keep-pins                  honour the start file's pin flags (default: anchors only)
//   --json out.json              also write the raw result
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as M from "./web/public/model.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
const GRAPH = path.join(ROOT, "build", "layout", "graph.json");

const opt = { start: "scatter", runs: 3, seed: 20260101, iters: null,
  configs: [], tuning: null, json: null, keepPins: false };
for (let i = 0; i < process.argv.length - 2; i++) {
  const a = process.argv[2 + i];
  const next = () => process.argv[2 + ++i];
  if (a === "--start") opt.start = next();
  else if (a === "--runs") opt.runs = +next();
  else if (a === "--seed") opt.seed = +next();
  else if (a === "--iters") opt.iters = +next();
  else if (a === "--config") opt.configs.push(next());
  else if (a === "--tuning") opt.tuning = next();
  else if (a === "--json") opt.json = next();
  else if (a === "--keep-pins") opt.keepPins = true;
  else if (a === "--help" || a === "-h") { console.log(fs.readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").slice(1, 34).join("\n")); process.exit(0); }
  else { console.error(`unknown option ${a} (--help)`); process.exit(2); }
}

if (!fs.existsSync(GRAPH)) {
  console.error(`no ${path.relative(ROOT, GRAPH)} — run 'make layout' or extract.py first`);
  process.exit(1);
}
const G = JSON.parse(fs.readFileSync(GRAPH, "utf8"));

// base values: model defaults < the tracked tuning (or --tuning)
const base = { ...M.DEFAULTS };
if (opt.tuning) {
  const j = JSON.parse(fs.readFileSync(path.resolve(ROOT, opt.tuning), "utf8"));
  Object.assign(base, j.params || j);
}

// configs: "name:KEY=VAL,KEY=VAL"; a bare "KEY=VAL" gets the name "base"
function parseConfig(spec) {
  const i = spec.indexOf(":");
  const name = i > 0 ? spec.slice(0, i) : "base";
  const body = i > 0 ? spec.slice(i + 1) : spec;
  const over = {};
  for (const kv of body.split(",").map((x) => x.trim()).filter(Boolean)) {
    const [k, v] = kv.split("=");
    if (!(k in M.DEFAULTS)) { console.error(`unknown parameter ${k}`); process.exit(2); }
    over[k] = M.DEFAULTS[k] === false || M.DEFAULTS[k] === true ? (v === "1" || v === "true") : +v;
  }
  return { name, over };
}
const configs = (opt.configs.length ? opt.configs : ["base"]).map(parseConfig);

// --- the start --------------------------------------------------------------
const START_ABS = opt.start === "scatter" ? null : path.resolve(ROOT, opt.start);
let startPos = null;
if (START_ABS) {
  if (!fs.existsSync(START_ABS)) { console.error(`no such start file: ${opt.start}`); process.exit(1); }
  startPos = JSON.parse(fs.readFileSync(START_ABS, "utf8")).positions;
  if (opt.start.includes("placements/")) {
    console.error(`! ${opt.start} is a hand placement — a biased start.`);
    console.error("  Prefer --start scatter or an engine output; the numbers below are not a fair test.");
  }
}

function makeNodes(start) {
  const nodes = G.nodes.map((gn) => {
    const s = start ? start[gn.id] : null;
    const n = { ...gn, x: s ? s.x : 0, y: s ? s.y : 0, angle: (s && s.angle) || 0, pinned: false };
    M.setExtents(n);
    if (gn.anchor) {                       // terminals are always fixed
      if (!s) { n.x = gn.anchor[0]; n.y = gn.anchor[1]; }
      n.fx = n.x; n.fy = n.y;
    } else if (s && s.pin && opt.keepPins) {
      n.pinned = true; n.fx = n.x; n.fy = n.y;
    }
    return n;
  });
  return nodes;
}

function runOnce(cfg, seed) {
  const P = { ...base, ...cfg.over };
  if (opt.iters) P.ITERS = opt.iters;
  const nodes = makeNodes(startPos);
  if (!startPos) {                         // neutral start: the UI's own scatter
    P.SEED = seed;
    M.scatterPositions(nodes, G.board, seed);
    P.SEED = seed;
  }
  const byId = new Map(nodes.map((n) => [n.id, n]));
  M.assignHosts(nodes, G, byId, { includePower: P.HOST_POWER });
  const edges = G.edges.map((e) => ({ ...e }));
  const m = M.buildSim(nodes, edges, G.board, P);
  let ticks = 0;
  const budget = P.ITERS * 3;
  while (m.sim.alpha() > 0.001 && ticks < budget) { m.sim.tick(); ticks++; }
  const met = M.metrics(nodes, edges, G, G.board, byId);
  met.ticks = ticks;
  met.params = P;
  return met;
}

// --- run + report -----------------------------------------------------------
const ctrls = G.nodes.filter((n) => n.kind === "U").map((n) => n.id);
const f = (v, d = 1) => (v == null ? "–" : v.toFixed(d));
const agg = (v) => v.length ? { mean: v.reduce((a, b) => a + b, 0) / v.length, min: Math.min(...v), max: Math.max(...v) } : { mean: 0, min: 0, max: 0 };

const out = { start: opt.start, runs: opt.runs, seed: opt.seed, base, results: [] };
console.log(`A/B · start ${opt.start === "scatter" ? "scatter (uniform, neutral)" : opt.start}` +
  `${opt.keepPins ? " + its pins" : ""} · ${opt.runs} seed(s) from ${opt.seed}` +
  (opt.iters ? ` · ITERS ${opt.iters}` : "") + "\n");
console.log("| config | HPWL mm | wire mm | ovl | off | path | axisR | " +
  ctrls.map((c) => `${c} d/bias/sp`).join(" | ") + " |");
console.log("| --- | --- | --- | --- | --- | --- | --- | " + ctrls.map(() => "---").join(" | ") + " |");

for (const cfg of configs) {
  const runs = [];
  for (let r = 0; r < opt.runs; r++) runs.push(runOnce(cfg, opt.seed + r));
  const A = (key) => agg(runs.map((m) => m[key]));
  const hpwl = A("hpwl"), wire = A("wire"), path_ = A("path"), axis = A("axis_r");
  const ovl = runs.reduce((a, m) => a + m.overlap, 0);
  const off = runs.reduce((a, m) => a + m.outside, 0);
  const fanCells = ctrls.map((c) => {
    const vals = runs.map((m) => m.fan[c]).filter(Boolean);
    if (!vals.length) return "–";
    const d = agg(vals.map((v) => v.d)), b = agg(vals.map((v) => v.bias)), s = agg(vals.map((v) => v.spacing));
    return `${f(d.mean)}/${f(b.mean, 2)}/${f(s.mean)}`;
  });
  console.log(`| ${cfg.name} | ${f(hpwl.mean, 0)}${opt.runs > 1 ? ` (${f(hpwl.min, 0)}–${f(hpwl.max, 0)})` : ""}` +
    ` | ${f(wire.mean, 0)} | ${ovl} | ${off} | ${f(path_.mean, 0)} | ${f(axis.mean, 2)} | ` +
    fanCells.join(" | ") + " |");
  out.results.push({
    config: cfg.name, overrides: cfg.over,
    hpwl, wire, path: path_, axis_r: axis, overlap: ovl, outside: off,
    fan: Object.fromEntries(ctrls.filter((c) => runs[0].fan[c]).map((c) => [c,
      { d: agg(runs.map((m) => m.fan[c].d)), bias: agg(runs.map((m) => m.fan[c].bias)),
        spacing: agg(runs.map((m) => m.fan[c].spacing)) }])),
    perRun: runs.map((m) => ({ hpwl: m.hpwl, wire: m.wire, overlap: m.overlap, outside: m.outside, ticks: m.ticks })),
  });
}
console.log(`\nd/bias/sp per controller = mean distance of its small parts (mm) · inward bias ` +
  `(+1 = all of them on the centre side) · spacing (mm). Lower d and bias, higher spacing = ` +
  `the parts fan around the controller instead of crowding the middle.`);
if (opt.json) {
  const p = path.resolve(ROOT, opt.json);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(out, null, 1) + "\n");
  console.log(`raw results → ${path.relative(ROOT, p)}`);
}
