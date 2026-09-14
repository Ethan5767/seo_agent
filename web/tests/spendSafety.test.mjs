import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * Spend safety in the browser, found by the 2026-09-14 review once DataForSEO
 * could run live: generic scan buttons spent on paid tools with no cost shown,
 * and a second press during a scan started a second paid scan.
 */
const app = readFileSync(new URL("../app/ScannerApp.tsx", import.meta.url), "utf8");

test("the generic scan selection is free tools only", () => {
  const i = app.indexOf('authedFetch("/api/tools")');
  const effect = app.slice(i, i + 1600);
  assert.match(effect, /setSelected\(new Set\(t\.filter\(\(x\) => x\.group === "free"\)/);
  assert.doesNotMatch(effect, /available !== false\)\.map/);
});

test("run() refuses to start while a scan is in flight, and always releases", () => {
  const start = app.indexOf("async function run(overrideUrl?: string, overrideTools?: string[], overrideCrawlPages?: number) {");
  const body = app.slice(start, app.indexOf("\n  }\n", start));
  const guard = body.indexOf("if (scanInFlight.current) return;");
  assert.ok(guard > 0, "no in-flight guard");
  assert.ok(guard < body.indexOf("setBusy(true)"), "guard must run before any state changes");
  assert.match(body, /finally \{\s*scanInFlight\.current = false;/);
});
