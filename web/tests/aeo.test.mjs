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
  assert.equal(aeoVerdictColor(null), "var(--ink-muted)", "grey, never the pass green");
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


/* ── B-095: the crawler table and the snippet ────────────────────────────── */

const {
  CRAWLERS, crawlerStatuses, statusLabel, statusColor, buildRobotsSnippet,
} = await import("../lib/aeoCrawlers.ts");

test("the three crawler classes do not overlap", () => {
  const seen = new Map();
  for (const c of CRAWLERS) {
    assert.ok(!seen.has(c.ua), `${c.ua} is listed twice`);
    seen.set(c.ua, c.klass);
  }
});

test("GPTBot and ClaudeBot are training crawlers, not citation crawlers", () => {
  // The table said "GPTBot - Required for ChatGPT citations" and "ClaudeBot -
  // Required for Claude Search". Both false, and false in the direction that
  // stops a client opting out of model training.
  const by = Object.fromEntries(CRAWLERS.map((c) => [c.ua, c]));
  assert.equal(by["GPTBot"].klass, "training");
  assert.equal(by["ClaudeBot"].klass, "training");
  assert.equal(by["OAI-SearchBot"].klass, "citation");
  assert.equal(by["Claude-SearchBot"].klass, "citation");
});

test("a training crawler's consequence says citations are unaffected", () => {
  for (const c of CRAWLERS.filter((x) => x.klass === "training")) {
    assert.match(c.consequence, /unaffected|Common Crawl/i,
      `${c.ua}: a client must be able to see that blocking this costs no citations`);
  }
});

test("no crawler is claimed allowed or blocked without a scan", () => {
  for (const rows of [null, undefined, [], [{ code: "something.else" }]]) {
    const s = crawlerStatuses(rows);
    for (const c of CRAWLERS) {
      assert.equal(s.get(c.ua) ?? null, null, `${c.ua} claimed a status over no data`);
    }
  }
  assert.equal(statusLabel(null), "Not measured");
});

test("a blocked crawler is read from the row detail, and its siblings are not", () => {
  const s = crawlerStatuses([
    { code: "aeo.crawler_blocked", detail: "PerplexityBot", severity: "warn" },
  ]);
  assert.equal(s.get("PerplexityBot"), "blocked");
  assert.equal(s.get("Googlebot"), "allowed", "the check ran and did not name this one");
  assert.equal(s.get("GPTBot"), null, "the training check produced no row, so it is unmeasured");
});

test("a pass row means every crawler in that class is allowed", () => {
  const s = crawlerStatuses([
    { code: "aeo.crawler_blocked", detail: "", severity: "ok" },
    { code: "aeo.training_crawler_blocked", detail: "", severity: "ok" },
  ]);
  assert.equal(s.get("OAI-SearchBot"), "allowed");
  assert.equal(s.get("GPTBot"), "allowed");
});

test("a missing robots.txt is not an allow", () => {
  // Default-allow is the HTTP reality, but the gate treats a missing robots.txt
  // as a defect rather than a pass, and so does this.
  const s = crawlerStatuses([{ code: "aeo.robots_missing", severity: "warn" }]);
  assert.equal(s.get("OAI-SearchBot"), null);
});

test("user-triggered fetchers are never graded", () => {
  const s = crawlerStatuses([
    { code: "aeo.crawler_blocked", detail: "", severity: "ok" },
    { code: "aeo.training_crawler_blocked", detail: "", severity: "ok" },
  ]);
  for (const c of CRAWLERS.filter((x) => x.klass === "user")) {
    assert.equal(s.get(c.ua), null, `${c.ua}: most vendors say robots.txt may not apply`);
  }
});

test("blocking a training crawler is never coloured as a failure", () => {
  assert.notEqual(statusColor("blocked", "training"), statusColor("blocked", "citation"));
  assert.notEqual(statusColor("blocked", "training"), "var(--bad)");
});

test("the recommended robots.txt allows the bots that actually cite", () => {
  const snip = buildRobotsSnippet("acme.test");
  for (const ua of ["OAI-SearchBot", "Claude-SearchBot", "Googlebot", "Bingbot", "PerplexityBot"]) {
    assert.match(snip, new RegExp(`^User-agent: ${ua}$`, "m"), `${ua} is not allowed in the snippet`);
  }
});

test("the snippet does not decide the training question for the client", () => {
  const snip = buildRobotsSnippet("acme.test");
  for (const ua of ["GPTBot", "ClaudeBot", "Google-Extended", "CCBot"]) {
    assert.match(snip, new RegExp(`^# User-agent: ${ua}$`, "m"), `${ua} must be commented out`);
    assert.ok(!new RegExp(`^User-agent: ${ua}$`, "m").test(snip),
      `${ua} must not be an active directive`);
  }
});

test("no domain means no broken Sitemap line", () => {
  // It used to emit `Sitemap: https:///sitemap.xml` - into a file that goes live.
  for (const d of [null, undefined, "", "   "]) {
    const snip = buildRobotsSnippet(d);
    assert.ok(!snip.includes("https:///"), "a broken URL reached the snippet");
    assert.match(snip, /# Sitemap:/, "say what is missing rather than emitting nothing");
  }
  assert.match(buildRobotsSnippet("https://acme.test/"), /^Sitemap: https:\/\/acme\.test\/sitemap\.xml$/m);
});

test("the invented answer-content metrics are gone", () => {
  for (const s of ["84% Ready", "12 Question Headings Detected", "42 Words",
                   "Optimal for Direct LLM Quoting", "Enables Google Accordions",
                   "Mass scraping protected", "Required for ChatGPT citations"]) {
    assert.ok(!DASH.includes(s), `"${s}" is still rendered with nothing behind it`);
  }
});
