import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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
      !DASHBOARD.includes(f),
      `Hardcoded check row '${f}' must not come back: it renders as a passed check that was never run`,
    );
  }
});

test("check rows are built only from the report", () => {
  // The catKey literal was the shape of the hardcoded array. Rows must come
  // from report groups, not from an inline list.
  assert.equal(
    /\{ catKey: "\w+", what: "/.test(DASHBOARD),
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
      !DASHBOARD.includes(f),
      `'${f}' claims a fix was applied that never ran`,
    );
  }
});

test("the progress sub-tab derives its entries, with no inline literal", () => {
  assert.equal(
    /const issueDiffAudit = \[\s*\{/.test(DASHBOARD),
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
      !DASHBOARD.includes(f),
      `'${f}' asserts a recovery outcome nothing measured`,
    );
  }
});

test("the empty remediation table explains why it is empty", () => {
  // Check that the component conditionally renders based on issueDiffAudit.length === 0,
  // which guards both the empty state and the actual table. If someone deletes the
  // empty-state JSX but leaves the comment string, this assertion catches it.
  assert.ok(
    /issueDiffAudit\.length\s*===\s*0\s*\?\s*\(\s*[\s\S]*?No data here yet/.test(DASHBOARD),
    "must render empty state with 'No data here yet' when issueDiffAudit is empty (check the ternary conditional)",
  );
  // Also verify the table rendering branch exists in the same ternary.
  assert.ok(
    /issueDiffAudit\.length\s*===\s*0\s*\?[\s\S]*?:\s*\([\s\S]*?\.map\(\s*\(\s*diff/.test(DASHBOARD),
    "must have a table rendering branch that maps over issueDiffAudit items",
  );
});

test("all_checks renders through the shared table", () => {
  const start = DASHBOARD.indexOf('auditSubTab === "all_checks"');
  assert.notEqual(start, -1, "the all_checks block is missing");
  const block = DASHBOARD.slice(start, start + 4000);
  assert.ok(block.includes("<ReportTable"), "all_checks must use ReportTable");
  assert.ok(block.includes("<ReportStats"), "all_checks must show the count strip");
  assert.equal(
    /const isErr = r\.severity === "error"/.test(block),
    false,
    "bespoke severity row markup must be gone",
  );
});
