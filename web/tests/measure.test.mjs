import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Measure screen invariants.
 *
 * The screen twice shipped invented data that read as measurement: 19
 * hardcoded rows rendering as passed security and crawler checks, and six
 * "Resolved" remediation entries describing fixes that were never applied.
 * Both are worse than a blank screen, because both assert something false
 * about a client's site.
 */

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DASHBOARD = readFileSync(
  path.resolve(__dirname, "..", "app", "ReaiDashboard.tsx"),
  "utf8",
);

// The Measure screen now lives in its own component. Markup that moved is
// guarded where it lives now; absence assertions cover both files, so a
// fixture cannot come back by being pasted into either one.
const MEASURE_PATH = path.resolve(
  __dirname,
  "..",
  "components",
  "dashboard",
  "MeasureScreen.tsx",
);
const MEASURE = existsSync(MEASURE_PATH) ? readFileSync(MEASURE_PATH, "utf8") : "";
const BOTH = DASHBOARD + "\n" + MEASURE;

// The derivations the screen now reads from. Node strips the type annotations
// itself, so the modules under test are imported directly.
const { derivePillars } = await import("../lib/pillars.ts");
const { deriveCoreWebVitals } = await import("../lib/webVitals.ts");
const { buildExecutiveReport } = await import("../lib/executiveReport.ts");

/**
 * Source with every comment removed.
 *
 * An absence assertion over raw source is two-sided: a fixture can hide in a
 * comment and pass a "must contain" test (which is how an earlier test in this
 * file went green), and a comment that QUOTES a deleted fixture - as the ones
 * recording what was removed do - fails a "must not contain" test even though
 * no such claim renders. Strip the comments and both problems go away: what is
 * left is what ships to a client's screen.
 */
function stripComments(src) {
  const out = [];
  let inBlock = false;
  for (const line of src.split("\n")) {
    const t = line.trim();
    if (inBlock) {
      if (t.includes("*/")) inBlock = false;
      out.push("");
      continue;
    }
    // A whole-line comment: "//", a JSX "{/*", a "/*" or a "*" continuation.
    if (t.startsWith("//") || t.startsWith("*")) {
      out.push("");
      continue;
    }
    if (t.startsWith("{/*") || t.startsWith("/*")) {
      if (!t.includes("*/")) inBlock = true;
      out.push("");
      continue;
    }
    out.push(line);
  }
  return out.join("\n");
}

const DASHBOARD_CODE = stripComments(DASHBOARD);
const MEASURE_CODE = stripComments(MEASURE);
const BOTH_CODE = DASHBOARD_CODE + "\n" + MEASURE_CODE;

/** A report shaped exactly like pipeline/scanner/audit.py `assemble` returns. */
const SCANNED = {
  seo: [
    { code: "health.title_missing", what: "title missing", why: "w", fix: "f", detail: "3 URLs", severity: "error" },
    { code: "health.desc_length", what: "meta description too short", why: "w", fix: "f", detail: "1 URL", severity: "warn" },
    { code: "health.h1_count", what: "one h1 per page", why: "w", fix: "passing", detail: "", severity: "ok" },
  ],
  perf: [
    { code: "crux.lcp", what: "LCP 1800 (p75)", why: "w", fix: "passing", detail: "good", severity: "ok" },
    { code: "crux.inp", what: "INP 82 (p75)", why: "w", fix: "passing", detail: "good", severity: "ok" },
    { code: "crux.cls", what: "CLS 0.02 (p75)", why: "w", fix: "passing", detail: "good", severity: "ok" },
  ],
  aeo: [
    { code: "aeo.crawler_blocked", what: "GPTBot blocked in robots.txt", why: "w", fix: "f", detail: "GPTBot", severity: "error" },
  ],
  score: 61,
  counts: { error: 2, warn: 1, info: 0, ok: 4 },
};

test("no hardcoded check rows claim a check passed", () => {
  const fixtures = [
    "HTTPS SSL/TLS 256-Bit Certificate",
    "Zero Mixed Active Content",
    "HTTP Strict Transport Security (HSTS)",
    "LLM Web Crawler Permissions",
    "Robots.txt Crawl Directives",
    "XML Sitemap Hierarchy & Format",
    "Self-Referencing Canonical Tags",
    "HTTP 4xx Dead Link Check",
    "Direct-Answer Entity Extraction",
    "BreadcrumbList JSON-LD Trails",
  ];
  for (const f of fixtures) {
    assert.ok(
      !BOTH.includes(f),
      `Hardcoded check row '${f}' must not come back: it renders as a passed check that was never run`,
    );
  }
});

test("check rows are built only from the report", () => {
  // The catKey literal was the shape of the hardcoded array. Rows must come
  // from report groups, not from an inline list.
  assert.equal(
    /\{ catKey: "\w+", what: "/.test(BOTH),
    false,
    "an inline check-row literal is present; rows must be derived from the report",
  );
});

test("no remediation is reported as applied without evidence", () => {
  const fixtures = [
    "Auto-injected Next.js 14 Metadata API",
    "All 25 Pages Optimized",
    "3 Pages Missing Title",
  ];
  for (const f of fixtures) {
    assert.ok(
      !BOTH.includes(f),
      `'${f}' claims a fix was applied that never ran`,
    );
  }
});

test("the progress sub-tab derives its entries, with no inline literal", () => {
  assert.equal(
    /const issueDiffAudit = \[\s*\{/.test(BOTH),
    false,
    "issueDiffAudit must not be an inline literal of invented remediations",
  );
});

test("no fabricated crawl-to-crawl recovery figures render", () => {
  const fixtures = [
    "+26% Health Recovery",
    "Crawl-to-Crawl Recovery Delta",
    "+26 pts",
    "68% → 94% Grade A",
    "-24 Errors",
    "100% Critical Errs Resolved",
    "-14 Warnings",
    "78% Reduction",
  ];
  for (const f of fixtures) {
    assert.ok(
      !BOTH.includes(f),
      `'${f}' asserts a recovery outcome nothing measured`,
    );
  }
});

test("the empty remediation table explains why it is empty", () => {
  // Check that the component conditionally renders based on issueDiffAudit.length === 0,
  // which guards both the empty state and the actual table. If someone deletes the
  // empty-state JSX but leaves the comment string, this assertion catches it.
  assert.ok(
    /issueDiffAudit\.length\s*===\s*0\s*\?\s*\(\s*[\s\S]*?No data here yet/.test(MEASURE),
    "must render empty state with 'No data here yet' when issueDiffAudit is empty (check the ternary conditional)",
  );
  // Also verify the table rendering branch exists in the same ternary.
  assert.ok(
    /issueDiffAudit\.length\s*===\s*0\s*\?[\s\S]*?:\s*\([\s\S]*?\.map\(\s*\(\s*diff/.test(MEASURE),
    "must have a table rendering branch that maps over issueDiffAudit items",
  );
});

test("all_checks renders through the shared table", () => {
  // Bound the region by the NEXT sub-tab marker, never by a byte count: a
  // character-offset window asserts formatting, so one line added above the
  // table would turn this red with no defect present.
  const start = MEASURE.indexOf('auditSubTab === "all_checks"');
  assert.notEqual(start, -1, "the all_checks block is missing");
  const end = MEASURE.indexOf('auditSubTab === "progress"', start);
  assert.notEqual(end, -1, "the progress sub-tab marker that bounds all_checks is missing");
  const block = MEASURE.slice(start, end);

  assert.ok(/<ReportTable\b/.test(block), "all_checks must render ReportTable");
  assert.ok(/<ReportStats\b/.test(block), "all_checks must render ReportStats");
  assert.ok(
    /view=\{CHECKS_VIEW\}/.test(block),
    "all_checks must pass CHECKS_VIEW as the view",
  );
  assert.equal(
    /const isErr = r\.severity === "error"/.test(block),
    false,
    "bespoke severity row markup must be gone",
  );
});

test("a filtered-to-empty all_checks table does not claim there is no data", () => {
  const start = MEASURE.indexOf('auditSubTab === "all_checks"');
  const end = MEASURE.indexOf('auditSubTab === "progress"', start);
  const block = MEASURE.slice(start, end);

  // Rows filtered to nothing is not the same as nothing measured. Handing
  // ReportTable an empty array renders "No data here yet" plus a button that
  // starts a scan the operator pays for.
  assert.ok(
    /filteredChecks\.length === 0 && allCategoryRows\.length > 0/.test(block),
    "all_checks must distinguish a filtered-empty table from an unscanned site",
  );
  assert.ok(
    /setAuditCategoryFilter\("all"\)/.test(block) &&
      /setAuditSeverityFilter\("all"\)/.test(block),
    "the filtered-empty state must offer a way to clear the filter",
  );
});

test("the Measure screen lives in its own file", () => {
  const p = path.resolve(__dirname, "..", "components", "dashboard", "MeasureScreen.tsx");
  assert.ok(existsSync(p), "MeasureScreen.tsx must exist");
  assert.ok(
    DASHBOARD.includes("<MeasureScreen"),
    "ReaiDashboard must render MeasureScreen rather than inline markup",
  );
});

test("the dashboard shrank below 13,000 lines", () => {
  // Not an arbitrary number: AGENTS.md Rule 1 is 1,000 lines, and this is the
  // first extraction toward it. The check exists so the file cannot grow back.
  const lines = DASHBOARD.split("\n").length;
  assert.ok(lines < 13000, `ReaiDashboard.tsx is ${lines} lines; extraction did not land`);
});

/* ──────────────────────────────────────────────────────────────────────────
   The pillar cards on the summary sub-tab.

   Six cards each carried a list of green-ticked bullets - "SSL/TLS 256-bit
   active", "HSTS header enabled", "0 orphan URLs detected", "MedicalBusiness
   JSON-LD" (a healthcare schema asserted for every client) - that named checks
   nothing had run. The same claims had already been deleted from the All Checks
   sub-tab for being fabricated. The cards also scored 0 while painted with the
   pass colour, and one badge read "AI Ready" over an unmeasured pillar.
   ────────────────────────────────────────────────────────────────────────── */

/** The pillar-card region, bounded by markers rather than a byte count. */
function pillarBlock() {
  const start = MEASURE.indexOf("Pillar cards.");
  assert.notEqual(start, -1, "the pillar-card region is missing");
  const end = MEASURE.indexOf("Audited Findings.", start);
  assert.notEqual(end, -1, "the marker that bounds the pillar region is missing");
  return MEASURE.slice(start, end);
}

test("the comment stripper keeps code and drops only comments", () => {
  // Without this, every absence assertion below could pass by stripping too
  // much. A stripper that ate the markup would make them all vacuous.
  for (const sentinel of ["derivePillars(report)", "severityMark(it.severity)"]) {
    assert.ok(MEASURE_CODE.includes(sentinel), `stripComments removed live code: ${sentinel}`);
  }
  for (const sentinel of ["buildExecutiveReport({", "No Audit Data to Report"]) {
    assert.ok(DASHBOARD_CODE.includes(sentinel), `stripComments removed live code: ${sentinel}`);
  }
  // And it really does remove a comment that quotes a deleted fixture.
  assert.ok(DASHBOARD.includes("SCORE: lcp"), "the record of what was removed is gone from the source");
  assert.equal(DASHBOARD_CODE.includes("SCORE: lcp"), false, "stripComments left a comment behind");
  assert.equal(
    stripComments('const a = 1; // "3.8s"\nconst b = 2;\n/* "94/100"\n   more */\nconst c = 3;\n')
      .includes("94/100"),
    false,
    "a block comment must be stripped whole",
  );
});

test("pillar bullets are report rows, not written-in claims", () => {
  const fixtures = [
    "SSL/TLS 256-bit active",
    "Zero mixed content",
    "HSTS header enabled",
    "Secure redirection",
    "Robots.txt compliant",
    "Sitemap.xml indexed",
    "Canonical tags enforced",
    "0 4xx crawl errors",
    "Click depth ≤ 3 for key pages",
    "0 orphan URLs detected",
    "Balanced equity flow",
    "Descriptive anchor text",
    "BreadcrumbList valid",
    "OpenGraph meta present",
    "Twitter Card schema",
    "GPTBot / ClaudeBot unblocked",
    "Direct answer citations",
    "Semantic markdown structure",
    "Perplexity search ready",
    "Mobile asset caching",
  ];
  for (const f of fixtures) {
    assert.ok(
      !BOTH_CODE.includes(f),
      `pillar bullet '${f}' must not come back: it asserts a check that never ran`,
    );
  }
});

test("no healthcare schema is claimed for every client", () => {
  // The worst of the six pillar bullets: an industry-specific claim rendered
  // whatever the client sells. Scoped to the screens this covers - the
  // Auto-Fix target-file fallback still guesses a medical component path for
  // any schema finding, which is a separate fabrication in the bug ledger.
  assert.ok(
    !/MedicalBusiness/.test(MEASURE_CODE),
    "'MedicalBusiness' names a healthcare schema for clients that are not healthcare",
  );
  assert.ok(
    !/MedicalBusiness/.test(stripComments(execBlock())),
    "the client-facing export must not claim a healthcare schema",
  );
});

test("the pillar cards are derived, with no inline items literal", () => {
  const block = pillarBlock();
  assert.ok(
    /derivePillars\(report\)/.test(block),
    "the pillar cards must be built from derivePillars(report)",
  );
  // The literal shape of the fabrication: an `items:` array of strings next to
  // a hardcoded `status:`/`score:`.
  assert.equal(
    /items:\s*\[\s*[`"']/.test(block),
    false,
    "an inline bullet-list literal is present; bullets must come from report rows",
  );
  assert.equal(
    /status:\s*"(?!Not measured")/.test(block) || /score:\s*\d/.test(block),
    false,
    "a card must not carry a hardcoded status or score",
  );
});

test("no pillar is styled as a pass over an unmeasured score", () => {
  const block = pillarBlock();
  // Colour comes from the pillar's own tone, never a fixed token per card.
  assert.ok(/tone\(m\.tone\)/.test(block), "pillar colour must follow the derived tone");
  assert.equal(
    /(bg|background|color|border):\s*"(var\(--ok\)|var\(--ok-tint\)|var\(--ok-border\))"/.test(block),
    false,
    "a pillar card must not hardcode the pass colour",
  );
  // A score that does not exist renders an em dash, never 0% in green.
  assert.ok(
    /m\.score === null \? "—"/.test(block),
    "an unmeasured pillar must render an em dash rather than a 0% bar",
  );
  assert.equal(
    /"AI Ready"/.test(BOTH_CODE),
    false,
    "'AI Ready' was a hardcoded pass badge over a pillar nothing measured",
  );
});

test("derivePillars reports nothing measured for an unscanned report", () => {
  for (const empty of [null, undefined, {}, { score: 100, counts: {} }]) {
    const pillars = derivePillars(empty);
    assert.equal(pillars.length, 6, "every pillar is still named, with no data");
    for (const p of pillars) {
      assert.equal(p.measured, false, `${p.catKey} must not claim a measurement`);
      assert.equal(p.score, null, `${p.catKey} must have no score, not a zero styled as one`);
      assert.equal(p.status, "Not measured");
      assert.equal(p.tone, "neutral", `${p.catKey} must not be tinted as a pass`);
      assert.deepEqual(p.items, [], `${p.catKey} must list no bullets`);
    }
  }
});

test("every pillar bullet traces to a row the scanner produced", () => {
  const pillars = derivePillars(SCANNED);
  const rowWhats = new Set(
    Object.entries(SCANNED)
      .filter(([k, v]) => Array.isArray(v))
      .flatMap(([, v]) => v.map((r) => r.what.charAt(0).toUpperCase() + r.what.slice(1))),
  );
  for (const p of pillars) {
    for (const item of p.items) {
      assert.ok(
        rowWhats.has(item.label),
        `pillar bullet '${item.label}' is not any row the report carries`,
      );
    }
  }

  const seo = pillars.find((p) => p.catKey === "seo");
  assert.equal(seo.measured, true);
  assert.equal(seo.score, 33, "1 of 3 graded rows passed");
  assert.equal(seo.tone, "bad", "a pillar holding an error is not tinted as a pass");
  assert.equal(seo.items[0].severity, "error", "the error sorts first");

  const perf = pillars.find((p) => p.catKey === "perf");
  assert.equal(perf.score, 100);
  assert.equal(perf.tone, "ok");

  const tech = pillars.find((p) => p.catKey === "tech");
  assert.equal(tech.measured, false, "a group with no rows stays unmeasured");
});

/* ──────────────────────────────────────────────────────────────────────────
   Core Web Vitals.

   The dashboard derived LCP/INP/CLS figures from the Lighthouse performance
   SCORE ("3.8s" / "2.4s" / "1.6s" off a bucket, with the score defaulting to
   "46/100" when nothing had run) and rendered them as measurements.
   ────────────────────────────────────────────────────────────────────────── */

test("web vitals are never derived from a Lighthouse score bucket", () => {
  assert.equal(
    /lhPerfNum\s*[<=)]/.test(DASHBOARD_CODE),
    false,
    "the score-bucket variable is back; a score cannot produce a millisecond reading",
  );
  for (const f of ['"3.8s"', '"2.4s"', '"1.6s"', '"420ms"', '"38ms"', '"0.14"', '"0.03"', '"46/100"']) {
    assert.ok(
      !DASHBOARD_CODE.includes(f),
      `${f} was a Core Web Vitals figure invented from a score bucket`,
    );
  }
  assert.ok(
    /deriveCoreWebVitals\(/.test(DASHBOARD),
    "the dashboard must read vitals through deriveCoreWebVitals",
  );
});

test("deriveCoreWebVitals reads the scan, or reports nothing", () => {
  const measured = deriveCoreWebVitals(SCANNED);
  assert.equal(measured.lcp.val, "1.8s", "the p75 the scanner recorded, in its own unit");
  assert.equal(measured.lcp.status, "Good");
  assert.equal(measured.inp.val, "82ms");
  assert.equal(measured.cls.val, "0.02");
  assert.equal(measured.lcp.measured, true);

  // A Lighthouse score present and no CrUX row is still no field reading.
  const lhOnly = { lh_perf: [{ code: "lh.perf", what: "Performance", detail: "46/100", severity: "warn" }] };
  for (const v of Object.values(deriveCoreWebVitals(lhOnly))) {
    assert.equal(v.measured, false, "a Lighthouse score is not a Core Web Vital reading");
    assert.equal(v.val, "—");
    assert.equal(v.status, "Not measured");
  }
  for (const v of Object.values(deriveCoreWebVitals(null))) {
    assert.equal(v.val, "—");
  }
});

/* ──────────────────────────────────────────────────────────────────────────
   The Executive Report export.

   A printable, client-addressed deliverable assembled from literals: a 94/100
   "Grade A" health score, 92% AI readiness, PASSED vitals, an estimated
   traffic value, a hardcoded date, keyword fallbacks for a city nobody had
   scanned, and five "autonomous remediations deployed" that never ran.
   ────────────────────────────────────────────────────────────────────────── */

function execBlock() {
  const start = DASHBOARD.indexOf("showExecutiveReportModal && (() =>");
  assert.notEqual(start, -1, "the executive report modal is missing");
  const end = DASHBOARD.indexOf("GOOGLE SEARCH CONSOLE DISAVOW MANAGER MODAL", start);
  assert.notEqual(end, -1, "the marker that bounds the executive report modal is missing");
  return DASHBOARD.slice(start, end);
}

test("the executive report carries no invented figure", () => {
  const block = execBlock();
  const fixtures = [
    "Technical Health Score: 94",
    "Grade A",
    "AI / AEO Engine Readiness",
    "Est. Organic Traffic Value",
    "$2,439",
    "+14.2%",
    "September 10, 2026",
    "hospital phnom penh",
    "maternity clinic phnom penh",
    "emergency doctor 24/7",
    "AUTONOMOUS REMEDIATIONS DEPLOYED",
    "Passing 52 of 55 checks",
    "4/4 AI engines verified",
    "6.2k/mo",
    "Grade A · Optimal",
    "3 Core Web Vitals",
    "Ready for Review",
    "8 Pitches Queued",
  ];
  const code = stripComments(block);
  for (const f of fixtures) {
    assert.ok(!code.includes(f), `'${f}' is a figure or claim nothing measured`);
  }
  // A remediation section cannot be honest here: what was applied lives in the
  // cycle's changelog.json, which this screen does not read.
  assert.equal(/REMEDIATIONS/i.test(code), false, "the remediations section must be gone");
  // The date is generated, never typed.
  assert.equal(
    /(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d\d/.test(code),
    false,
    "a hardcoded report date is present",
  );
});

test("the executive report modal builds from the report and refuses without one", () => {
  const block = execBlock();
  assert.ok(
    /buildExecutiveReport\(\{/.test(block),
    "the modal must build its content from buildExecutiveReport",
  );
  assert.ok(
    /if \(!exec\) \{/.test(block),
    "the modal must branch on a missing report rather than render a document",
  );
  const refusal = block.slice(block.indexOf("if (!exec) {"));
  assert.ok(
    /No Audit Data to Report/.test(refusal),
    "the refusal must say plainly that there is nothing to report",
  );
});

test("buildExecutiveReport refuses to produce a document with no scan", () => {
  for (const empty of [null, undefined, {}, { score: 92, counts: { ok: 5 } }]) {
    assert.equal(
      buildExecutiveReport({ report: empty, client: "Acme", domain: "acme.test", agency: "Studio" }),
      null,
      "a report with no findings must yield no document at all",
    );
  }
});

test("every figure in the executive report comes from the scan", () => {
  const built = buildExecutiveReport({
    report: SCANNED,
    client: "Acme",
    domain: "acme.test",
    agency: "Studio",
    now: new Date("2026-09-11T10:00:00Z"),
  });
  assert.notEqual(built, null);
  assert.equal(built.healthScore, SCANNED.score, "the score is the report's own");
  assert.equal(built.checksPassing, SCANNED.counts.ok);
  assert.equal(built.checksTotal, 7, "every counted row, no more");
  assert.equal(built.date, "2026-09-11", "the date is generated at export time");
  assert.equal(built.vitalsMeasured, true);
  assert.equal(built.vitals.lcp.val, "1.8s");

  // The markdown states only what the object holds.
  assert.ok(built.markdown.includes("Technical Health Score: 61 / 100"));
  assert.ok(built.markdown.includes("4 passing of 7"));
  assert.equal(/Grade [A-F]/.test(built.markdown), false, "no grade is invented from the score");
  assert.equal(/\$/.test(built.markdown), false, "no money figure: the report carries none");
  assert.equal(/REMEDIATION/i.test(built.markdown), false, "no applied-fix claims");
});

test("the keyword line is omitted rather than filled with a fallback", () => {
  const noKeywords = buildExecutiveReport({
    report: SCANNED,
    client: "Acme",
    domain: "acme.test",
    agency: "Studio",
    now: new Date("2026-09-11T10:00:00Z"),
  });
  assert.deepEqual(noKeywords.keywords, [], "no keyword rows means no keywords");
  assert.equal(/Tracked Keywords/.test(noKeywords.markdown), false, "the section is omitted entirely");
  assert.equal(/phnom penh/i.test(noKeywords.markdown), false, "no fallback term may appear");

  const withKeywords = buildExecutiveReport({
    report: {
      ...SCANNED,
      rankings: [
        { code: "dfs.ranked_keyword", what: "acme widgets — position 4", detail: "vol 320/mo", severity: "info" },
      ],
    },
    client: "Acme",
    domain: "acme.test",
    agency: "Studio",
    now: new Date("2026-09-11T10:00:00Z"),
  });
  assert.equal(withKeywords.keywords.length, 1);
  assert.equal(withKeywords.keywords[0].what, "acme widgets — position 4");
  assert.ok(withKeywords.markdown.includes("acme widgets — position 4"));
});

test("the findings table shows how many pages each finding affects", () => {
  /*
   * `merge_by_code` has attached affected URLs to every multi-page row since
   * the free crawl shipped, and `onpage_audit` attaches them per DataForSEO
   * flag. Nothing rendered them. Every competitor puts this count on the row:
   * it is the difference between "canonical mismatch" and "canonical mismatch
   * on 340 pages", and it is what lets a list be read by consequence rather
   * than by severity label alone.
   */
  const src = readFileSync(
    path.resolve(__dirname, "..", "components", "dashboard", "ReportTable.tsx"), "utf8");

  assert.ok(/function affected\(/.test(src), "no affected-pages helper");
  assert.ok(/Array\.isArray\(pages\)/.test(src),
    "the count must come from the row's own pages list, not be inferred");
  assert.ok(/label="Pages"/.test(src), "no Pages column header");
  assert.ok(/sortKey === "affected"/.test(src),
    "the column must be sortable: consequence is the useful ordering");

  // The column appears only where the data does. A single-page scan getting a
  // column of em dashes is worse than no column at all.
  assert.ok(/const anyAffected/.test(src), "column is not conditional on the data");
  assert.ok(/\{anyAffected &&/.test(src), "header/cell not gated on anyAffected");
});

test("a pillar card shows the distribution, not the average twice", () => {
  /*
   * The bar used to be filled to the score, which restates the number beside it
   * and hides the shape: 60% passing looks identical whether the other 40% is
   * all notices or all server errors. Sitebulb never shows an average without
   * its spread, and that is the right rule - the average is what you report,
   * the spread is what you act on.
   */
  const src = readFileSync(
    path.resolve(__dirname, "..", "components", "dashboard", "MeasureScreen.tsx"), "utf8");

  assert.ok(!/width: `\$\{m\.score \?\? 0\}%`/.test(src),
    "the bar is filled to the score again, which just repeats the number above it");
  for (const sev of ["m.error", "m.warn", "m.info", "m.ok"]) {
    assert.ok(src.includes(sev), `the distribution must include ${sev}`);
  }
  // Colour alone must not carry it: WCAG 1.4.1, and it has to survive
  // greyscale printing in a client report.
  assert.ok(/error, \$\{m\.warn\} warning/.test(src),
    "segments must be labelled in text, not only coloured");
});


// ── ExecutiveTrafficChart empty series (B-069) ───────────────────────────────
//
// The de-fabrication pass removed the fixture series and left the maths that
// assumed they were populated. `pts` becomes [], and `pts[pts.length - 1].x`
// throws "Cannot read properties of undefined (reading 'x')" — so the Keywords
// and Visibility tabs, whose arrays are unconditionally empty, crashed the whole
// dashboard, and so did any page with no scan behind it.
//
// Removing invented data is only half the job; the empty state is the other half.

test("the traffic chart renders an empty state instead of throwing", () => {
  const src = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  const body = src.slice(src.indexOf("export function ExecutiveTrafficChart"));
  const fn = body.slice(0, body.indexOf("\nexport "));

  // Strip comments first. A comment explaining the bug legitimately quotes the
  // very expression we are checking the position of, and matching that prose
  // instead of the code is how this assertion lies to you.
  const code = fn
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  assert.ok(/activeSeries\.length\s*===\s*0/.test(code) || /pts\.length\s*===\s*0/.test(code),
    "no early return for an empty series — pts[pts.length-1] will throw");

  const guardPos = Math.min(
    ...[/activeSeries\.length\s*===\s*0/, /pts\.length\s*===\s*0/]
      .map(re => { const m = code.match(re); return m ? code.indexOf(m[0]) : Infinity; }));
  const derefPos = code.indexOf("pts[pts.length - 1].x");
  assert.ok(derefPos === -1 || guardPos < derefPos,
    "the empty-series guard must come BEFORE pts[pts.length - 1] is dereferenced");
});

test("the chart does not compute a range from an empty series", () => {
  const src = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  const body = src.slice(src.indexOf("export function ExecutiveTrafficChart"));
  const fn = body.slice(0, body.indexOf("\nexport "));
  assert.ok(!/Math\.min\(\.\.\.activeSeries\)(?![\s\S]{0,400}activeSeries\.length)/.test(fn)
    || /activeSeries\.length\s*===\s*0/.test(fn),
    "Math.min(...[]) is Infinity — guard the empty case before computing the scale");
});
