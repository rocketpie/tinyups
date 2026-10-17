#!/usr/bin/env node
// Interactive placement server (TinyUPS).
//
// A dependency-free Node HTTP server that hosts the browser UI for interactive
// component placement.  It serves:
//
//   /                 the UI (public/index.html + app.js + style.css)
//   /graph.json       build/layout/graph.json (extract.py's placement graph)
//   /api/seeds        the position files it can start from (leg-*/pos-*/raw-*)
//   /api/seed?name=X  one of them
//   /api/save         POST -> write build/layout/interactive-<name>.json
//   /api/apply        POST -> run apply.py on a saved file (+ KiCad DRC)
//   /vendor/<pkg>/... node_modules for the vendored d3-force ES modules
//
// The placement engine itself (d3-force) runs *in the browser*, so the sim is
// live while you drag — the same force model as engines/d3force.mjs.  See
// web/README.md.
//
// Usage: node web/server.mjs            (PORT=4097 HOST=0.0.0.0 by default)
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));      // web/
const POC = path.dirname(HERE);                                 // hardware/layout_poc
const ROOT = path.dirname(path.dirname(POC));                   // repo root
const PUBLIC = path.join(HERE, "public");
const LAYOUT = path.join(ROOT, "build", "layout");
const GRAPH = path.join(LAYOUT, "graph.json");
const NETLIST = path.join(ROOT, "build", "tinyups.net");
const VENDOR = path.join(POC, "node_modules");
const VENDOR_PKGS = new Set(["d3-force", "d3-dispatch", "d3-quadtree", "d3-timer"]);
const PY = process.env.PYTHON || "/opt/eda/venv/bin/python";
const PORT = Number(process.env.PORT || 4097);
const HOST = process.env.HOST || "0.0.0.0";
const DEFAULT_SEED = process.env.SEED || "leg-gv-sfdp";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".map": "application/json; charset=utf-8",
};

const send = (res, code, body, type = "text/plain; charset=utf-8") => {
  res.writeHead(code, { "Content-Type": type, "Cache-Control": "no-store" });
  res.end(body);
};
const sendJSON = (res, code, obj) => send(res, code, JSON.stringify(obj), MIME[".json"]);
const safeName = (s) => /^[A-Za-z0-9._-]+$/.test(s) ? s : null;

// --- graph / seed discovery ------------------------------------------------
function ensureGraph() {
  if (fs.existsSync(GRAPH)) return { ok: true };
  try {
    if (!fs.existsSync(NETLIST)) {
      console.log("graph.json missing, netlist missing -> kicad-cli sch export netlist");
      execFileSync("kicad-cli", ["sch", "export", "netlist", "--output",
        NETLIST, path.join(ROOT, "hardware", "tinyups.kicad_sch")], { stdio: "inherit" });
    }
    console.log("graph.json missing -> extract.py");
    execFileSync(PY, [path.join(POC, "extract.py")], { stdio: "inherit" });
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e.message || e) };
  }
}

function listSeeds() {
  if (!fs.existsSync(LAYOUT)) return [];
  const out = [];
  for (const f of fs.readdirSync(LAYOUT)) {
    if (!/^(leg|pos|raw)-[\w.-]+\.json$/.test(f)) continue;
    const name = f.replace(/\.json$/, "");
    let engine = "?", n = 0;
    try {
      const j = JSON.parse(fs.readFileSync(path.join(LAYOUT, f), "utf8"));
      engine = j.engine || "?";
      n = j.positions ? Object.keys(j.positions).length : 0;
    } catch { /* ignore */ }
    out.push({ name, engine, n, legal: name.startsWith("leg-") });
  }
  // legalised first, then alphabetically
  out.sort((a, b) => (b.legal - a.legal) || a.name.localeCompare(b.name));
  return out;
}

function serveFile(res, file) {
  fs.readFile(file, (err, buf) => {
    if (err) return send(res, 404, "not found");
    send(res, 200, buf, MIME[path.extname(file).toLowerCase()] || "application/octet-stream");
  });
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let s = "";
    req.on("data", (c) => { s += c; if (s.length > 5e6) reject(new Error("body too large")); });
    req.on("end", () => resolve(s));
    req.on("error", reject);
  });
}

// --- request handler -------------------------------------------------------
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const p = decodeURIComponent(url.pathname);

  try {
    if (req.method === "GET" && (p === "/" || p === "/index.html")) {
      return serveFile(res, path.join(PUBLIC, "index.html"));
    }
    if (req.method === "GET" && (p === "/app.js" || p === "/style.css")) {
      return serveFile(res, path.join(PUBLIC, p.slice(1)));
    }
    if (req.method === "GET" && (p === "/graph.json" || p === "/api/graph")) {
      const g = ensureGraph();
      if (!g.ok) return sendJSON(res, 500, { error: "graph not available: " + g.error });
      return serveFile(res, GRAPH);
    }
    if (req.method === "GET" && p === "/api/seeds") {
      return sendJSON(res, 200, { default: DEFAULT_SEED, seeds: listSeeds() });
    }
    if (req.method === "GET" && p === "/api/seed") {
      const name = safeName(url.searchParams.get("name") || DEFAULT_SEED);
      if (!name) return sendJSON(res, 400, { error: "bad name" });
      const f = path.join(LAYOUT, name + ".json");
      if (!f.startsWith(LAYOUT) || !fs.existsSync(f)) {
        return sendJSON(res, 404, { error: "no such seed: " + name });
      }
      return serveFile(res, f);
    }
    if (req.method === "POST" && p === "/api/save") {
      const body = JSON.parse(await readBody(req) || "{}");
      const name = safeName(body.name || "interactive") || "interactive";
      if (!body.positions || typeof body.positions !== "object") {
        return sendJSON(res, 400, { error: "positions required" });
      }
      // Shape is the same as an engine output so render.py / apply.py accept it.
      const out = {
        engine: "interactive",
        seed: body.seed || null,
        params: body.params || {},
        pinned: body.pinned || [],
        positions: body.positions,
        savedAt: new Date().toISOString(),
      };
      const file = path.join(LAYOUT, `interactive-${name}.json`);
      fs.mkdirSync(LAYOUT, { recursive: true });
      fs.writeFileSync(file, JSON.stringify(out, null, 1));
      return sendJSON(res, 200, {
        ok: true, file: path.relative(ROOT, file),
        render: `make place-render F=${path.relative(ROOT, file)}`,
        apply: `make place-apply F=${path.relative(ROOT, file)}`,
      });
    }
    if (req.method === "POST" && p === "/api/apply") {
      const body = JSON.parse(await readBody(req) || "{}");
      const file = path.resolve(ROOT, body.file || "");
      if (!file.startsWith(LAYOUT) || !fs.existsSync(file)) {
        return sendJSON(res, 400, { error: "file must be an existing build/layout/*.json" });
      }
      const out = path.join(LAYOUT, "interactive.kicad_pcb");
      const r = spawnSync(PY, [path.join(POC, "apply.py"), file, out],
        { cwd: ROOT, encoding: "utf8", timeout: 600000, env: process.env });
      return sendJSON(res, r.status === 0 ? 200 : 500, {
        ok: r.status === 0,
        board: path.relative(ROOT, out),
        stdout: r.stdout || "", stderr: r.stderr || "",
      });
    }
    if (req.method === "GET" && p.startsWith("/vendor/")) {
      const rest = p.slice("/vendor/".length);
      const pkg = rest.split("/")[0];
      if (!VENDOR_PKGS.has(pkg)) return send(res, 403, "forbidden package");
      const file = path.resolve(VENDOR, rest);
      if (!file.startsWith(VENDOR + path.sep)) return send(res, 403, "forbidden path");
      return serveFile(res, file);
    }
    return send(res, 404, "not found: " + p);
  } catch (e) {
    return sendJSON(res, 500, { error: String(e.message || e) });
  }
});

server.listen(PORT, HOST, () => {
  const g = ensureGraph();
  console.log(`TinyUPS interactive placement`);
  console.log(`  http://${HOST === "0.0.0.0" ? "localhost" : HOST}:${PORT}/`);
  console.log(`  root   ${ROOT}`);
  console.log(`  graph  ${g.ok ? GRAPH : "UNAVAILABLE (" + g.error + ")"}`);
  console.log(`  seeds  ${listSeeds().length} in build/layout/ (default ${DEFAULT_SEED})`);
});
