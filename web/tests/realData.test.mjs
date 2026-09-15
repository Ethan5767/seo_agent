import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * Screens that showed invented data as if measured (sweep of 2026-09-15).
 *
 * Each assertion names a literal that was on screen for every client. The
 * operator's rule: every number, badge and status comes from a real source, or
 * the screen says it was not measured.
 */

const src = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
/** Source with comments removed, so a comment explaining a removal does not trip the check. */
const code = (p) => src(p).replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1").replace(/\{\/\*[\s\S]*?\*\/\}/g, "");

test("Local: no fixture geo-grid, roofing copy, invented hours or verification ticks", () => {
  const lbm = code("components/dashboard/LocalBusinessManager.tsx");
  for (const lit of [
    "78% Map Pack Dominance", "#2.6", "Austin", "roof repair near me", "RoofingContractor",
    '"US"', "Matches Google Maps 100%", "Lat/Long coordinates synced", "Click-to-call schema verified",
    "+40%", "local crew", "homeowners", "https://example.com", '"08:00"', "Demo Data", "Real-Time Google Maps",
  ]) {
    assert.ok(!lbm.includes(lit), `LocalBusinessManager still renders ${lit}`);
  }
});

test("Local: reviews and posts are read in the shape the routes send", () => {
  const lbm = code("components/dashboard/LocalBusinessManager.tsx");
  const reviewsRoute = src("app/api/local-seo/reviews/route.ts");
  for (const field of ["reviewer", "starRating", "reply"]) {
    assert.match(reviewsRoute, new RegExp(`${field}:`));
    assert.match(lbm, new RegExp(`rev\\.${field}|r\\.${field}`), `UI does not read ${field}`);
  }
  assert.doesNotMatch(lbm, /rev\.authorName|rev\.replyText|post\.viewsCount/);
  assert.match(lbm, /setInsights\(insRes\)/, "insights.metrics must be the route's metrics, not metrics.metrics");
  assert.doesNotMatch(lbm, /method: "PUT"/, "the business route has no PUT");
});

test("Local: Google's hours are converted, and a day Google does not list gets no default", async () => {
  // starsOf / hoursFromGoogle are pure and exported; exercise them through a tiny
  // extraction rather than importing the TSX component.
  const lbm = src("components/dashboard/LocalBusinessManager.tsx");
  const body = lbm.slice(lbm.indexOf("const STAR_WORDS"), lbm.indexOf("type SubTab"));
  const js = body
    .replace(/export function/g, "function")
    .replace(/: Record<string, number>/g, "")
    .replace(/\(rating: string \| number \| null \| undefined\): number \| null/, "(rating)")
    .replace(/\(t: any\)/, "(t)")
    .replace(/\(periods: any\): Record<string, BusinessHours>/, "(periods)")
    .replace(/const out: Record<string, BusinessHours> = \{\};/, "const out = {};");
  const { starsOf, hoursFromGoogle } = new Function(`${js}; return { starsOf, hoursFromGoogle };`)();
  assert.equal(starsOf("FIVE"), 5);
  assert.equal(starsOf("STAR_RATING_UNSPECIFIED"), null);
  assert.equal(starsOf(null), null);
  const h = hoursFromGoogle([{ openDay: "MONDAY", openTime: { hours: 7 }, closeDay: "MONDAY", closeTime: { hours: 17, minutes: 30 } }]);
  assert.deepEqual(h, { monday: { open: "07:00", close: "17:30", isClosed: false } });
  assert.deepEqual(hoursFromGoogle(null), {});
});

test("Profile: GitHub status is asked of GitHub, and dead preference toggles are gone", () => {
  const prof = code("app/profile/page.tsx");
  for (const lit of ["Workspace Admin", "GitHub Verified", "✓ Connected", "GitHub OAuth 2.0", "Email Audit Summaries", "Auto-Fix PR Staging"]) {
    assert.ok(!prof.includes(lit), `profile still renders ${lit}`);
  }
  assert.match(prof, /authedFetch\("\/api\/github\/repos"/);
  assert.ok(prof.indexOf('authedFetch("/api/github/repos"') < prof.indexOf("if (loading) {"),
    "the GitHub check is a hook and must run before the loading early return");
});

test("Business Profile tile draws no gauge from a made-up score, and the connect banner claims nothing", () => {
  assert.doesNotMatch(code("components/dashboard/GbpMatrix.tsx"), /score=\{ok \? 100 : 50\}/);
  assert.doesNotMatch(code("components/dashboard/GoogleServicesHub.tsx"), /are active\./);
});

/* ── the dashboard (ReaiDashboard.tsx) ──────────────────────────────────── */

const DASH = () => code("app/ReaiDashboard.tsx");

test("Auto-Fix shows what the remediation rail returned, never a success it did not get", () => {
  const d = DASH();
  for (const lit of [
    "Diff generated (0 risk)", "Committed & Verified", "Dry-Run Verified (0 disk writes)",
    "3 fixes committed", "Ready for PR Merge", "All Files (+42 -1)", "42 insertions(+)",
    "reai/seo-remediation-auto", "MedicalBusinessSchema.tsx", "Claude Code Ready", "local/client-web",
  ]) assert.ok(!d.includes(lit), `Auto-Fix still renders ${lit}`);
  assert.doesNotMatch(d, /setDryRunActive\(true\)|setApplyConfirmed\(true\)/, "a click must not mark a run done");
  assert.match(d, /const hasDryRun = dry\?\.ok === true;/);
  assert.match(d, /const hasApplied = apply\?\.ok === true && !apply\?\.error;/);
  const applyBtn = d.slice(d.indexOf("planState.runDryRun();"), d.indexOf("Apply All via Claude Code"));
  assert.match(applyBtn, /window\.confirm\(/, "apply sends confirm:true, so the button must ask first");
});

test("the old tool screens with computed figures open the report views instead", () => {
  const d = DASH();
  const map = {
    "Organic Research": "organic-rankings", "Keyword Gap": "keyword-gap", "Keyword Magic Tool": "keyword-ideas",
    "Keyword Data Lab": "keyword-overview", "Data Lab & Backlinks": "backlinks", "Backlink Audit": "backlink-audit",
  };
  const views = src("lib/reportViews.ts");
  for (const [tab, view] of Object.entries(map)) {
    assert.ok(d.includes(`"${tab}": "${view}"`), `${tab} is not redirected`);
    assert.ok(views.includes(`id: "${view}"`), `${view} is not a report view`);
  }
  assert.match(d, /useState<string \| null>\(\(\) => LEGACY_TAB_VIEWS\[activeTab\] \?\? null\)/, "a direct URL must land on the view");
  const setTab = d.slice(d.indexOf("const setActiveTab = useCallback"), d.indexOf("setIsTabTransitioning(true);", d.indexOf("const setActiveTab = useCallback")));
  assert.match(setTab, /LEGACY_TAB_VIEWS\[tab\]/, "an in-page button must land on the view too");
});

test("project figures carry no arithmetic stand-ins", () => {
  const d = DASH();
  const fn = d.slice(d.indexOf("function resolveProjectData("), d.indexOf("// ── Types ──"));
  for (const pat of [
    /commonKeywords: 8 \+ idx/, /1800 \+ idx/, /comp1Rank: k\.position === 1/, /kd: k\.position <= 3/,
    /0\.85 \+ \(i % 4\)/, /suspiciousDomains: 2/, /Math\.max\(5, Math\.round\(toxicityRatio/, /refDelta: "\+4/,
    /backlinkDelta: "\+18/, /trafficDelta: "\+12\.4%/, /visibilityPct: 0\.67/, /"Mar 3"/, /: "240"/, /: "8,200"/,
    /\["Site links", "Knowledge card", "Map pack"\]/, /qLow\.includes\("clinic"\)/,
  ]) assert.doesNotMatch(fn, pat);
});

test("Traffic, header and modals claim nothing they did not check", () => {
  const d = DASH();
  for (const lit of [
    '"K visits"', "impressions || 0) / 10", "● Verified Scan", "100% Real Google First-Party Data", "30s (Realtime)",
    "Live Verified", "(Verified Domain)", "156 SPECIALIZED", "webmasters.readonly, analytics.readonly", "Repo: both/seo_agent",
    "● Active", "Scan Complete", "verified and connected live", "re-synced for",
    "24/7 Emergency", "Maternity & Delivery", "Official Healthcare Portal", "Call Clinic", '"opens": "00:00"',
    "clinical resource center", "accredited medical citations", "High-Conversion Angle", "hospital phnom penh",
    "Tier 1 Foundation ", ">Authority Score</span>",
  ]) assert.ok(!d.includes(lit), `dashboard still renders ${lit}`);
  assert.match(d, /function cwvBadgeStyle\(/);
  assert.doesNotMatch(d, /<span style=\{\{ fontSize: 12, fontWeight: 700, padding: "1px 5px", borderRadius: 3, background: "var\(--bad-tint\)"[^\n]*\n\s*\{projectMetrics\.onPageSeoData\.coreWebVitals/);
});

/* ── tool page inputs (operator, 2026-09-15) ────────────────────────────── */

test("a tool page takes the project's domain read-only, and only the inputs its tool reads", () => {
  const panel = code("components/dashboard/CompareInputPanel.tsx");
  assert.match(panel, /aria-label="Project domain"/);
  assert.doesNotMatch(panel, /aria-label="Domain"|type any domain/, "no editable domain box");
  const d = DASH();
  assert.match(d, /COMPETITOR_SLOTS: Record<string, 1 \| 3> = \{ "compare-domains": 3, "backlink-gap": 3, "keyword-gap": 1 \}/);
  for (const v of ["keyword-overview", "keyword-ideas", "keyword-clusters", "search-intent", "serp-positions"]) {
    assert.ok(new RegExp(`"${v}": (undefined|\\d)`).test(d), `${v} has no keyword input`);
  }
  // Keyword Gap's slot count matches keywords_card, which reads the first competitor.
  const dfs = readFileSync(new URL("../../pipeline/scanner/dataforseo.py", import.meta.url), "utf8");
  assert.match(dfs, /competitor = bare_domain\(\(competitor_list or \[""\]\)\[0\]\)/);
});

test("competitors and keywords typed on a page apply to that run only", () => {
  const app = code("app/ScannerApp.tsx");
  const trigger = app.slice(app.indexOf("async function handleTriggerScan(targetUrl: string, toolKeys?: string[], customCrawlPages?: number, competitorsOverride?: string, keywordsOverride?: string[]) {"));
  assert.doesNotMatch(trigger.slice(0, trigger.indexOf("await run(")), /setCompetitors\(/);
  assert.match(app, /keywords: overrideKeywords \?\? kwList/);
});

test("Compare Domains runs the comparison tool, and Domain Overview carries no competitor rows", async () => {
  const { VIEW_TOOLS } = await import("../lib/sectionScans.ts");
  assert.deepEqual(VIEW_TOOLS["compare-domains"], ["compare"]);
  const server = readFileSync(new URL("../../pipeline/scanner/server.py", import.meta.url), "utf8");
  assert.match(server, /dataforseo\.rankings\(c\.domain, c\.keywords\)\)/);
});

test("Crawl Issues is part of Site Audit, not a second page", () => {
  const d = DASH();
  assert.doesNotMatch(d, /label: "Crawl Issues", view: "site-crawl"/);
  assert.match(d, /crawlControls: scanControlsFor\(crawlView as ScannableView, "Site Audit"\)/);
  const m = code("components/dashboard/MeasureScreen.tsx");
  assert.match(m, /\{ id: "crawl", label: "Crawl Issues" \}/);
  assert.match(m, /auditSubTab === "crawl" && crawlIssues/);
});

test("competitors start as one row, and + adds the next up to the tool's limit", () => {
  const panel = code("components/dashboard/CompareInputPanel.tsx");
  assert.match(panel, /setCompetitors\(competitorSlots \? \[defaultCompetitors\[0\] \?\? ""\] : \[\]\)/, "one row to start");
  assert.match(panel, /competitorSlots > 1 && competitors\.length < competitorSlots/, "+ only while under the limit");
  assert.match(panel, /\+ Add competitor/);
});
