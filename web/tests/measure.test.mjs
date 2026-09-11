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
