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

test("no one-click sample buttons start a scan of someone else's site", () => {
  // Operator, 2026-09-14: clicking "wikipedia.org" under "Try quick sample"
  // started a scan immediately and filed it under the open project.
  const hero = readFileSync(new URL("../components/dashboard/AuditHeroBar.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(hero, /Try quick sample/);
  assert.doesNotMatch(hero, /onRunAudit\(preset/);
  assert.doesNotMatch(hero, /currentDomain = "example\.com"/, "a made-up default domain");
});


test("the budget badge shows sub-cent spend instead of rounding it to $0.00", async () => {
  const { formatUsd } = await import("../lib/budget.ts");
  assert.equal(formatUsd(0.0037), "$0.0037");
  assert.equal(formatUsd(0.0008), "$0.0008");
  assert.equal(formatUsd(0.532), "$0.532");
  assert.equal(formatUsd(5), "$5.00");
  assert.equal(formatUsd(0), "$0.00");
  const dash = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  assert.match(dash, /DAILY BUDGET: \{formatUsd\(spentToday\)\}/);
  assert.doesNotMatch(dash, /spentToday\.toFixed\(2\)/);
});
