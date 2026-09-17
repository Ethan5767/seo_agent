/**
 * B-104. The scanner refuses any POST without `X-Scan-Token` (B-079). That guard
 * shipped on the Python side and no proxy route was given the token, so every
 * scan, plan and remediate from the web UI was answered 403 — and because the
 * 403 body is one NDJSON-parseable line, the browser read it as a stream event
 * and the run ended with no error anywhere on screen.
 *
 * These tests hold the two halves that let that happen:
 *   1. the transport really attaches the header (proved against a live socket,
 *      not a mock, because the bug was in what went over the wire);
 *   2. no route reaches the scanner any other way.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** Start a throwaway server that records what it was sent. */
async function stub(handler) {
  const seen = [];
  const srv = http.createServer((req, res) => {
    seen.push({ url: req.url, headers: req.headers });
    (handler || ((_q, r) => { r.writeHead(200, { "Content-Type": "application/json" }); r.end("{}"); }))(req, res);
  });
  await new Promise((r) => srv.listen(0, "127.0.0.1", r));
  return {
    seen,
    port: srv.address().port,
    // closeAllConnections, or an unconsumed keep-alive response body holds the
    // socket open and close() never resolves — the test hangs instead of failing.
    close: () => { srv.closeAllConnections(); return new Promise((r) => srv.close(r)); },
  };
}

/**
 * Fresh module instance with `env` applied, and a restore handle.
 *
 * PYTHON_API is read at import time but the token is read per call, so the env
 * has to stay in place for the whole test, not just the import.
 */
async function loadWith(env) {
  const prev = new Map(Object.keys(env).map((k) => [k, process.env[k]]));
  Object.assign(process.env, env);
  const mod = await import(`../lib/scannerFetch.ts?v=${Math.random()}`);
  const restore = () => {
    for (const [k, v] of prev) { if (v === undefined) delete process.env[k]; else process.env[k] = v; }
  };
  return { ...mod, restore };
}

test("the token rides on every scanner POST", async () => {
  const s = await stub();
  const { scannerPost, restore } = await loadWith({
    PYTHON_API: `http://127.0.0.1:${s.port}`,
    SCAN_TOKEN: "secret-under-test",
  });
  try {
    const res = await scannerPost("/scan", { url: "https://example.com" });
    await res.text();
  } finally { restore(); await s.close(); }
  assert.equal(s.seen.length, 1);
  assert.equal(s.seen[0].url, "/scan");
  assert.equal(
    s.seen[0].headers["x-scan-token"],
    "secret-under-test",
    "without this header the scanner answers 403 and the UI shows nothing",
  );
});

test("a missing token is refused here, not sent as an empty string", async () => {
  const { scannerPost, ScannerUnconfigured, restore } = await loadWith({ SCAN_TOKEN: "" });
  try {
  await assert.rejects(
    () => scannerPost("/scan", {}),
    (e) => {
      assert.ok(e instanceof ScannerUnconfigured);
      // The message has to name the fix. A bare 403 sent the operator nowhere.
      assert.match(e.message, /SCAN_TOKEN/);
      assert.match(e.message, /\.env/);
      return true;
    },
    "the guard fails closed on an empty token, so sending '' just reproduces the silent 403",
  );
  } finally { restore(); }
});

test("the header timeout does not abort the body stream", async () => {
  // A scan streams for minutes. The old `AbortSignal.timeout(10000)` covered the
  // whole fetch, so the stream was torn down mid-run with no error.
  const s = await stub((_req, res) => {
    res.writeHead(200, { "Content-Type": "application/x-ndjson" });
    res.write('{"log":"first"}\n');
    setTimeout(() => { res.write('{"log":"late"}\n'); res.end(); }, 250);
  });
  const { scannerPost, restore } = await loadWith({
    PYTHON_API: `http://127.0.0.1:${s.port}`,
    SCAN_TOKEN: "t",
  });
  let body;
  try {
    const res = await scannerPost("/scan", {}, { headerTimeoutMs: 60 });
    // Headers arrived well inside 60ms; the body then takes 4x that long.
    body = await res.text();
  } finally { restore(); await s.close(); }
  assert.match(body, /"late"/, "the body must survive past the header deadline");
});

test("no route reaches the scanner outside the chokepoint", () => {
  const offenders = [];
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) { walk(p); continue; }
      if (!/\.tsx?$/.test(e.name)) continue;
      const src = fs.readFileSync(p, "utf8");
      src.split("\n").forEach((line, i) => {
        if (/fetch\(\s*`\$\{PYTHON_API\}/.test(line)) offenders.push(`${p}:${i + 1}`);
      });
    }
  };
  walk(path.join(WEB, "app"));
  assert.deepEqual(
    offenders,
    [],
    "call scannerPost() instead — a direct fetch carries no X-Scan-Token and is answered 403",
  );
});

test("every scanner POST proxy imports the chokepoint", () => {
  const routes = [
    "app/api/scan/route.ts",
    "app/api/plan/route.ts",
    "app/api/remediate/route.ts",
    "app/api/remediate/dryrun/route.ts",
    "app/api/remediate/apply/route.ts",
  ];
  for (const r of routes) {
    const src = fs.readFileSync(path.join(WEB, r), "utf8");
    assert.match(src, /scannerPost/, `${r} must POST through scannerPost`);
  }
});

test("a scan failure is handed to the dashboard, not left in local state", () => {
  // The failure used to be written into ScannerApp's `data`, which is not a
  // dashboard prop. busy went true, then false, and nothing was drawn.
  const app = fs.readFileSync(path.join(WEB, "app/ScannerApp.tsx"), "utf8");
  assert.match(app, /scanState=\{\{[^}]*error:/s, "scanState must carry the error");

  const dash = fs.readFileSync(path.join(WEB, "app/ReaiDashboard.tsx"), "utf8");
  assert.match(dash, /scanState\?: \{[^}]*error\?: string \| null[^}]*\}/, "the prop type must admit it");
  assert.match(dash, /error=\{scanState\?\.error\}/, "and it must reach the scan button");

  const btn = fs.readFileSync(path.join(WEB, "components/dashboard/SectionScanButton.tsx"), "utf8");
  assert.match(btn, /role="alert"/, "the button must render the failure");
});
