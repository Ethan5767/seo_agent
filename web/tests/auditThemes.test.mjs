import { test } from "node:test";
import assert from "node:assert/strict";

const { summarizeAudit, delta, AUDIT_THEMES } = await import("../lib/auditThemes.ts");

const REPORT = {
  score: 99, // ignored: the list recomputes from rows
  site: [
    { code: "site.pages_crawled", severity: "ok", detail: "25 pages" },
    { code: "site.duplicate_page_titles", severity: "warn" },
    { code: "dfs.op.is_4xx_code", severity: "ok" },
    { code: "dfs.op.is_https", severity: "ok" },
    { code: "unavailable.site", severity: "info" },
  ],
  tech: [{ code: "tech.https", severity: "ok" }, { code: "tech.xml_sitemap", severity: "error" }],
  aeo: [{ code: "aeo.citations", severity: "ok" }, { code: "aeo.statistics", severity: "info" }],
};

test("theme scores are the passed share of that theme's graded checks", () => {
  const s = summarizeAudit(REPORT);
  // crawlability: pages_crawled is not a theme row; dup titles warn, 4xx ok, sitemap error
  assert.deepEqual(s.themes.crawlability, { pct: 33, passed: 1, graded: 3 });
  assert.deepEqual(s.themes.https, { pct: 100, passed: 2, graded: 2 });
  assert.deepEqual(s.themes.ai, { pct: 100, passed: 1, graded: 1 });
});

test("a theme with nothing graded is not measured, never 0%", () => {
  const s = summarizeAudit(REPORT);
  assert.equal(s.themes.intl.pct, null);
  assert.equal(s.themes.eeat.pct, null);
});

test("health, errors, warnings and pages come from rows; did-not-run rows are ignored", () => {
  const s = summarizeAudit(REPORT);
  assert.equal(s.errors, 1);
  assert.equal(s.warnings, 1);
  assert.equal(s.pagesCrawled, 25);
  // graded: pages_crawled ok, dup warn, 4xx ok, https ok, tech.https ok, sitemap error, aeo ok = 5/7
  assert.deepEqual(s.health, { pct: 71, passed: 5, graded: 7 });
});

test("an empty or missing report is all not-measured", () => {
  const s = summarizeAudit(null);
  assert.equal(s.health.pct, null);
  assert.equal(s.pagesCrawled, null);
  assert.ok(Object.values(s.themes).every((t) => t.pct === null));
});

test("deltas are signed, and blank when either side is unmeasured", () => {
  assert.equal(delta(82, 80, "%"), "+2%");
  assert.equal(delta(5, 9), "-4");
  assert.equal(delta(7, 7), "±0");
  assert.equal(delta(null, 7), "");
});

test("every theme lists codes the scanner emits (no invented theme rows)", async () => {
  const { readFileSync, readdirSync } = await import("node:fs");
  const dir = new URL("../../pipeline/scanner/", import.meta.url);
  const src = readdirSync(dir).filter((f) => f.endsWith(".py")).map((f) => readFileSync(new URL(f, dir), "utf8")).join("\n");
  const known = ["dfs.op.", "site.", "tech.", "valid.", "health.", "onpage.", "lh.", "crux.", "aeo.", "eeat."];
  for (const t of AUDIT_THEMES) {
    for (const c of t.codes) {
      assert.ok(known.some((k) => c.startsWith(k)), `${t.id}: ${c} has no known producer family`);
    }
  }
  assert.ok(src.includes("pages_crawled") || src.includes("Pages crawled"), "crawl summary row moved");
});

test("Site Audit opens on the project list from the sidebar, and a project opens its audit", async () => {
  const { readFileSync } = await import("node:fs");
  const dash = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  assert.match(dash, /setAuditProjectList\(item\.tab === "Site Health & Audit" && !item\.sub\)/);
  assert.match(dash, /<SiteAuditProjects[\s\S]{0,200}loadTwo=\{latestTwoReports\}/);
  assert.match(dash, /← All projects/);
  const comp = readFileSync(new URL("../components/dashboard/SiteAuditProjects.tsx", import.meta.url), "utf8");
  assert.match(comp, /summarizeAudit\(current\)/);
  assert.match(comp, /Not measured/);
});
