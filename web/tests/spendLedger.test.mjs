import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const L = await import("../lib/spendLedger.ts");
const NOW = Date.parse("2026-09-15T10:00:00Z");

test("an in-flight scan counts at once, so a concurrent scan cannot slip past the cap", () => {
  L._resetLedger();
  L.reserve("u1", 0.53, NOW);
  assert.equal(L.effectiveSpent("u1", 4.5, NOW), 4.5 + 0.53);
});

test("a finished scan counts its real cost, and is not double counted once saved", () => {
  L._resetLedger();
  const id = L.reserve("u1", 0.53, NOW);
  L.settle(id, 0.2056, true);
  assert.equal(L.effectiveSpent("u1", 0, NOW), 0.2056);        // browser never saved it
  assert.equal(L.effectiveSpent("u1", 0.2056, NOW), 0.2056);   // browser saved it: max, not sum
});

test("an abandoned scan keeps its full estimate: the scanner may still be billing", () => {
  L._resetLedger();
  const id = L.reserve("u1", 0.53, NOW);
  L.settle(id, 0.006, false);
  assert.equal(L.effectiveSpent("u1", 0, NOW), 0.53);
});

test("users and days are separate", () => {
  L._resetLedger();
  L.settle(L.reserve("u1", 1, NOW), 1, true);
  assert.equal(L.effectiveSpent("u2", 0, NOW), 0);
  assert.equal(L.effectiveSpent("u1", 0, NOW + 24 * 3600 * 1000), 0);
});

test("costs are read from finished-tool events only", () => {
  assert.equal(L.costInLine('{"tool":"Backlinks","state":"done","cost":0.024}'), 0.024);
  assert.equal(L.costInLine('{"tool":"Backlinks","state":"progress","detail":{"cost":0.024},"cost":0}'), 0);
  assert.equal(L.costInLine("not json"), 0);
});

test("/api/scan admits against the ledger and settles from the stream", () => {
  const route = readFileSync(new URL("../app/api/scan/route.ts", import.meta.url), "utf8");
  assert.match(route, /effectiveSpent\(/);
  assert.match(route, /reserve\(/);
  assert.match(route, /meterStream\(res\.body, ledgerId\)/);
});


function ndjson(lines) {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(c) {
      for (const l of lines) c.enqueue(enc.encode(JSON.stringify(l) + "\n"));
      c.close();
    },
  });
}

test("a stream read to the end settles the real reported cost, bytes unchanged", async () => {
  L._resetLedger();
  const id = L.reserve("u9", 0.53, Date.now());
  const events = [
    { tool: "Site Health (DataForSEO)", state: "progress", status: "x", detail: { cost: 0.9 }, cost: 0 },
    { tool: "Site Health (DataForSEO)", state: "done", cost: 0.0015 },
    { tool: "Keywords (DataForSEO)", state: "done", cost: 0.2041 },
    { result: { audit: {} } },
  ];
  const out = await new Response(L.meterStream(ndjson(events), id)).text();
  assert.equal(out.trim().split("\n").length, 4);
  assert.equal(Number(L.effectiveSpent("u9", 0).toFixed(4)), 0.2056);
});

test("a client that cancels mid-stream leaves the full estimate counted", async () => {
  L._resetLedger();
  const id = L.reserve("u8", 0.53, Date.now());
  const stream = L.meterStream(ndjson([{ tool: "A", state: "done", cost: 0.006 }, { tool: "B", state: "running" }]), id);
  const reader = stream.getReader();
  await reader.read();
  await reader.cancel("tab closed");
  assert.equal(L.effectiveSpent("u8", 0), 0.53);
});
