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
