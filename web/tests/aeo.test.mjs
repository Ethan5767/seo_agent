import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * A check that scanned nothing must never report a pass.
 *
 * That rule is enforced in the engine - `forbidden_sweep` and `audit_ssr` exit 4
 * for "cannot judge" rather than green-over-empty (B-018, B-027). B-094 is the
 * same rule broken in the UI, which is where it actually reaches a person: the
 * AI Search Visibility screen showed three green ticks and a five-row PASS/WARN
 * matrix to an operator who had never run a scan.
 */

const { deriveAeoTiles, aeoVerdictColor, aeoMatrixRows } = await import("../lib/aeo.ts");

const code = (f) =>
  readFileSync(new URL(`../${f}`, import.meta.url), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/^\s*\/\/.*$/gm, "");

const DASH = code("app/ReaiDashboard.tsx");

/* ── nothing measured is not a pass ──────────────────────────────────────── */

test("an unscanned account gets no verdict on any tile", () => {
  for (const rows of [null, undefined, [], [null, "junk", 42]]) {
    for (const tile of deriveAeoTiles(rows)) {
      assert.equal(tile.verdict, null, `${tile.label} claimed a verdict over nothing`);
      assert.equal(tile.value, "Not measured");
    }
  }
});

test("no tick, no green, when nothing was measured", () => {
  // The tick IS the claim. Rendering one over an empty scan is the bug.
  for (const tile of deriveAeoTiles([])) {
    assert.ok(!/[✓✔]/.test(tile.value), `${tile.label} shows a tick with no data`);
  }
  assert.equal(aeoVerdictColor(null), "#64748b", "grey, never the pass green");
  assert.notEqual(aeoVerdictColor(null), aeoVerdictColor("ok"));
});

test("every unmeasured tile says what would produce a verdict", () => {
  for (const tile of deriveAeoTiles([])) {
    assert.match(tile.note, /Run a scan/i, `${tile.label}: a dead end with no next step`);
  }
});

/* ── measured rows produce real verdicts ─────────────────────────────────── */

test("a clean row passes and a failing row does not", () => {
  const ok = deriveAeoTiles([{ code: "aeo.crawler_access", what: "AI crawlers", severity: "ok" }]);
  const crawlers = ok.find((t) => t.id === "crawlers");
  assert.equal(crawlers.verdict, "ok");
  assert.equal(crawlers.value, "Allowed");

  const bad = deriveAeoTiles([{ code: "aeo.crawler_access", what: "AI crawlers", severity: "warn" }]);
  assert.equal(bad.find((t) => t.id === "crawlers").verdict, "problem");
  assert.equal(bad.find((t) => t.id === "crawlers").value, "Blocked");
});

test("one failing row among passes is still a problem", () => {
  const tiles = deriveAeoTiles([
    { what: "AI crawler access", severity: "ok" },
    { what: "PerplexityBot", severity: "warn" },
  ]);
  assert.equal(tiles.find((t) => t.id === "crawlers").verdict, "problem",
    "a tile is only green when every row under it is");
});

test("an unrecognised severity is not treated as a pass", () => {
  // Only the literal "ok" passes. A typo, a new severity, or a missing field
  // must not fall through to green.
  for (const severity of ["error", "critical", "", undefined, "OK", "pass"]) {
    const tiles = deriveAeoTiles([{ what: "AI crawlers", severity }]);
    assert.notEqual(tiles.find((t) => t.id === "crawlers").verdict, "ok",
      `severity ${JSON.stringify(severity)} passed`);
  }
});

test("a tile with no matching row stays unmeasured even when other rows exist", () => {
  // The original bug's exact shape: `.find()` returns undefined and the binary
  // falls through to the happy branch. A scan that measured crawlers but not
  // schema must not certify the schema.
  const tiles = deriveAeoTiles([{ code: "aeo.crawler_access", what: "AI crawlers", severity: "ok" }]);
  assert.equal(tiles.find((t) => t.id === "answers").verdict, null);
  assert.equal(tiles.find((t) => t.id === "answers").value, "Not measured");
});

/* ── the matrix ──────────────────────────────────────────────────────────── */

test("no rows means no table, not a substitute table", () => {
  for (const rows of [null, undefined, [], [null]]) {
    assert.equal(aeoMatrixRows(rows), null);
  }
  assert.deepEqual(aeoMatrixRows([{ what: "x", severity: "ok" }]), [{ what: "x", severity: "ok" }]);
});

test("the invented fallback rows are gone from the dashboard", () => {
  // Five hardcoded rows, three marked PASS, including "Verified in robots.txt"
  // for a robots.txt nobody had fetched.
  for (const invented of [
    "Perplexity AI Indexability",
    "Verified in robots.txt",
    "llms.txt Answer File Missing",
    "LocalBusiness Schema Entity Graph",
    "Direct Answer H2 / FAQ Headings",
  ]) {
    assert.ok(!DASH.includes(invented), `the fabricated row "${invented}" is still rendered`);
  }
});

test("the dashboard renders tiles from the derivation, not from find-or-pass", () => {
  assert.match(DASH, /deriveAeoTiles\(aeoRows\)/);
  assert.ok(!/crawlerBlocked \?/.test(DASH),
    "a falsy `.find()` result must not decide a verdict");
});

/* ── the per-engine grid ─────────────────────────────────────────────────── */

test("no engine is claimed ready by a hardcoded string", () => {
  // "Google AI Overviews" carried the literal status "Snapshot Ready" with no
  // input at all - a claim about AI Overview eligibility nothing here measures.
  assert.ok(!DASH.includes("Snapshot Ready"));
  for (const s of ['status: "Indexed"', 'status: "Direct"', 'status: "Compliant"']) {
    assert.ok(!DASH.includes(s), `${s} is a verdict with no measurement behind it`);
  }
});

test("the engine card is named for what it reads", () => {
  // It reads robots.txt. It was titled "AI Search Citations & Extraction Rates"
  // over "Real-time extraction and citation probabilities" - none of which it
  // computes.
  assert.ok(!DASH.includes("Real-time extraction and citation probabilities"));
  assert.match(DASH, /AI Crawler Access By Engine/);
  assert.match(DASH, /Access is a precondition for citation, not a measure of it/);
});
