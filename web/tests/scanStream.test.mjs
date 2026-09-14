import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * The scan stream reader.
 *
 * `run()` in ScannerApp split the body on newlines, kept the last partial line
 * in a buffer and never parsed it, and never looked at `res.ok`. Every refusal
 * `/api/scan` sends is one JSON object with no trailing newline (401, 400, 429
 * budget, 429 rate limit, and "backend unreachable"), so all of them sat in the
 * buffer and were dropped: the run ended, `data.error` stayed null, and the
 * operator saw nothing happen. B-104's symptom, reachable five more ways.
 */

const { readScanStream } = await import("../lib/scanStream.ts");
const __dirname = path.dirname(fileURLToPath(import.meta.url));

function ndjson(lines, { status = 200, headers = {}, trailingNewline = true } = {}) {
  const body = lines.map((l) => JSON.stringify(l)).join("\n") + (trailingNewline ? "\n" : "");
  return new Response(body, {
    status,
    headers: { "Content-Type": "application/x-ndjson", ...headers },
  });
}

async function collect(res) {
  const events = [];
  const out = await readScanStream(res, (ev) => events.push(ev));
  return { events, ...out };
}

test("a normal stream delivers every event and no error", async () => {
  const { events, error } = await collect(ndjson([
    { log: "Opened the page" },
    { tool: "On-page SEO", state: "done", rows: [] },
    { result: { audit: { score: 90 } } },
  ]));
  assert.equal(error, null);
  assert.equal(events.length, 3);
  assert.equal(events[2].result.audit.score, 90);
});

test("the last line is parsed even without a trailing newline", async () => {
  const { events, error } = await collect(ndjson(
    [{ log: "a" }, { result: { audit: {} } }], { trailingNewline: false },
  ));
  assert.equal(error, null);
  assert.ok(events.some((e) => e.result), "the final result line was dropped");
});

for (const [status, msg] of [
  [401, "Unauthorized"],
  [400, "Rejected scan target: private address"],
  [429, "Daily scan budget reached. Paid tools are paused until tomorrow (UTC)."],
  [503, "backend unreachable at http://127.0.0.1:8765 — is wf-scan-web running?"],
]) {
  test(`a ${status} JSON refusal becomes the error`, async () => {
    const res = new Response(JSON.stringify({ error: msg }), {
      status, headers: { "Content-Type": "application/json" },
    });
    const { error, events } = await collect(res);
    assert.equal(error, msg);
    assert.equal(events.length, 0);
  });
}

test("a 200 carrying a plain JSON error is still an error", async () => {
  // The route answered 200 for an unreachable backend until this change; a
  // deployed older route must not regress to silence.
  const res = new Response(JSON.stringify({ error: "SCAN_TOKEN is not set" }), {
    status: 200, headers: { "Content-Type": "application/json" },
  });
  const { error } = await collect(res);
  assert.equal(error, "SCAN_TOKEN is not set");
});

test("a non-JSON error body is reported with its status", async () => {
  const res = new Response("<html>Bad Gateway</html>", { status: 502 });
  const { error } = await collect(res);
  assert.match(error, /502/);
});

test("a malformed line does not throw, and a stream with no result says so", async () => {
  const res = new Response('{"log":"a"}\nnot json\n', {
    status: 200, headers: { "Content-Type": "application/x-ndjson" },
  });
  const { error, events } = await collect(res);
  assert.equal(events.length, 1);
  assert.match(error, /without a result/);
});

test("an error event in the stream is surfaced", async () => {
  const { error } = await collect(ndjson([{ error: "select at least one tool to run" }]));
  assert.equal(error, "select at least one tool to run");
});

test("budget-skipped tools are read from the header", async () => {
  const { blockedTools, error } = await collect(ndjson(
    [{ result: { audit: {} } }], { headers: { "X-Scan-Blocked-Tools": "rank_trend,keywords" } },
  ));
  assert.equal(error, null);
  assert.deepEqual(blockedTools, ["rank_trend", "keywords"]);
});

test("ScannerApp reads the scan through readScanStream, not a hand-rolled loop", () => {
  // Implemented is not wired (B-007): assert the call site.
  const src = readFileSync(path.join(__dirname, "..", "app", "ScannerApp.tsx"), "utf8");
  const run = src.slice(src.indexOf("async function run(overrideUrl?: string, overrideTools?: string[], overrideCrawlPages?: number)"));
  const body = run.slice(0, run.indexOf("\n  }\n"));
  assert.match(body, /readScanStream\(/);
  assert.doesNotMatch(body, /res\.body!\.getReader\(\)/);
});

test("our free on-page rows are never labelled as DataForSEO", () => {
  const src = readFileSync(path.join(__dirname, "..", "app", "ScannerApp.tsx"), "utf8");
  const fn = src.slice(src.indexOf("function sourceOf("), src.indexOf("function Rows("));
  const dfsLine = fn.split("\n").find((l) => /return\s+"DataForSEO/.test(l));
  assert.ok(dfsLine, "sourceOf lost its DataForSEO branch");
  assert.doesNotMatch(dfsLine, /health\./, "health.* is the free On-page SEO tool");
});
