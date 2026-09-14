import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webDir = path.resolve(__dirname, "..");

test("Navigation & UX: Dashboard does not contain confusing jargon labels", () => {
  const dashboardPath = path.join(webDir, "app", "ReaiDashboard.tsx");
  const content = fs.readFileSync(dashboardPath, "utf-8");

  const forbiddenTerms = [
    "AEO SEO",
    "AI Engine Citations Matrix",
    "Citation Extractability",
    "Entity Alignment",
    "Autonomous Flow",
  ];

  for (const term of forbiddenTerms) {
    assert.ok(
      !content.includes(term),
      `Found confusing label '${term}' in ReaiDashboard.tsx`
    );
  }
});

test("Navigation & UX: Sidebar contains the merged navigation groups", () => {
  const dashboardPath = path.join(webDir, "app", "ReaiDashboard.tsx");
  const content = fs.readFileSync(dashboardPath, "utf-8");

  // Post-merge group set. "SEO Foundations", "Fix & Improve" and
  // "Reports & Settings" were groups whose members mostly pointed at screens
  // another group already listed; see tests/nav.test.mjs.
  const expectedGroups = [
    "Dashboard",
    "Site Health",
    "Research",
    "Backlinks",
    "AI Visibility",
    "Fixes",
    "Workspace",
    "All Tools Directory",
  ];

  for (const group of expectedGroups) {
    assert.ok(
      content.includes(group),
      `Expected navigation group '${group}' not found in ReaiDashboard.tsx`
    );
  }
});

/**
 * The nav labels only, so a match in page copy cannot pass this by accident.
 * Both sidebar tiers render from NAV_SECTIONS, so that literal is the nav.
 */
function navLabels() {
  const dashboardPath = path.join(webDir, "app", "ReaiDashboard.tsx");
  const content = fs.readFileSync(dashboardPath, "utf-8");
  const start = content.indexOf("export const NAV_SECTIONS");
  const end = content.indexOf("\n];", start);
  assert.ok(start !== -1 && end !== -1, "NAV_SECTIONS not found");
  return [...content.slice(start, end).matchAll(/label: "([^"]+)"/g)].map((m) => m[1]);
}

/** The always-present Workspace footer, which sits outside the rail sections. */
function workspaceLabels() {
  const dashboardPath = path.join(webDir, "app", "ReaiDashboard.tsx");
  const content = fs.readFileSync(dashboardPath, "utf-8");
  const start = content.indexOf("Workspace (always present)");
  const end = content.indexOf("All Tools Directory Pinned", start);
  assert.ok(start !== -1 && end !== -1, "Workspace footer not found");
  return [...content.slice(start, end).matchAll(/label: "([^"]+)"/g)].map((m) => m[1]);
}

test("Navigation & UX: every SEO foundation screen stays reachable after the merge", () => {
  // The old "SEO Foundations" group listed six labels, four of which opened a
  // screen another group already listed. The screens did not go away; they are
  // reached under one name each now. Asserted against the nav block rather than
  // the whole file, because strings like "Local SEO" and "Content" also appear
  // in page copy and would pass a whole-file search without any nav entry.
  const labels = navLabels();
  const expected = [
    "Site Audit",      // was "Technical SEO" + "Site Audit" + "Sensor"
    "Page Optimizer",  // was "On-Page SEO" + "On Page SEO Checker" + "Topic Research"
    "SERP Preview",    // was "Content" + "SEO Writing Assistant"
    "Keyword Overview", // was "Keywords & Rankings" + 6 other aliases
    "Backlinks",       // was "Links" + "Referring Domains" + "Backlink Audit"
    "Local Presence",  // one entry, one page: the eight sub-sections live on
                       // that screen's own tab bar, not in the sidebar
  ];

  for (const item of expected) {
    assert.ok(
      labels.includes(item),
      `Expected nav entry '${item}' missing. Nav is: ${labels.join(", ")}`
    );
  }
});

test("Navigation & UX: AI Search Visibility (AEO) sub-items are present", () => {
  const dashboardPath = path.join(webDir, "app", "ReaiDashboard.tsx");
  const content = fs.readFileSync(dashboardPath, "utf-8");

  const aeoItems = [
    "AI Readiness",
    "AI Citations",
    "Schema & Entities",
    "Answer Content",
    "AI Crawler Access",
  ];

  for (const item of aeoItems) {
    assert.ok(
      content.includes(item),
      `Expected AEO item '${item}' not found in ReaiDashboard.tsx`
    );
  }
});

test("Navigation & UX: Fixes sub-items are present", () => {
  const dashboardPath = path.join(webDir, "app", "ReaiDashboard.tsx");
  const content = fs.readFileSync(dashboardPath, "utf-8");

  // The old "Fix & Improve" group listed four entries over two destinations:
  // "Priority Actions" opened Overview (the Dashboard entry already there) and
  // "Content Opportunities" opened Keyword Gap (now reached as "Competitor
  // Gap"). Both were aliases, so the merged group carries the two entries that
  // actually go somewhere of their own. See tests/nav.test.mjs for the
  // one-label-one-destination invariant this is the other half of.
  const fixesItems = ["Review Fixes", "Change History"];

  for (const item of fixesItems) {
    assert.ok(
      content.includes(item),
      `Expected Fixes item '${item}' not found in ReaiDashboard.tsx`
    );
  }

  // Priority actions lost its duplicate nav entry, not its home: the component
  // still renders on the Overview screen, which is what made the nav entry a
  // duplicate in the first place.
  assert.ok(
    /<PriorityActions/.test(content),
    "PriorityActions must still render on the Overview screen"
  );
});

test("Navigation & UX: account links live on the rail, not in a drawer group", () => {
  const dashboardPath = path.join(webDir, "app", "ReaiDashboard.tsx");
  const content = fs.readFileSync(dashboardPath, "utf-8");

  // The Workspace group was removed from the drawer: Integrations and Profile
  // are account-level rather than project reports, so they sit at the foot of
  // the rail. "New Project" went entirely, because the project card at the top
  // of the drawer already carries a "+ New".
  assert.ok(
    !content.includes("Workspace (always present)"),
    "the Workspace drawer group must not come back"
  );

  const railStart = content.indexOf("Account-level destinations");
  assert.notEqual(railStart, -1, "the rail footer block is missing");
  const railBlock = content.slice(railStart, railStart + 1400);

  // The Google integration page was removed at the operator's request
  // (2026-09-14); Google is connected from the top-bar button instead.
  assert.ok(!content.includes("/integrations/google"), "the removed integrations page must not be linked");
  assert.ok(railBlock.includes('href: "/profile"'), "Profile & Account must be on the rail");

  // Both must go to the real pages, not a tab.
  assert.ok(
    content.includes('window.location.href = item.href'),
    "rail account links must navigate to their real routes"
  );
});

test("Navigation & UX: Overview communicates product principle clearly", () => {
  const dashboardPath = path.join(webDir, "app", "ReaiDashboard.tsx");
  const content = fs.readFileSync(dashboardPath, "utf-8");

  assert.ok(
    content.includes("SEO is the foundation. AI Search Visibility builds on good SEO."),
    "Product principle callout missing in Overview"
  );
  assert.ok(
    content.includes("does not guarantee citations, rankings, or traffic"),
    "Disclaimer about ranking/citation guarantees missing"
  );
});

test("Priority Actions: renders findings from the scan, never a fixture", () => {
  const compPath = path.join(webDir, "components", "dashboard", "PriorityActions.tsx");
  assert.ok(fs.existsSync(compPath), "PriorityActions.tsx must exist");
  const content = fs.readFileSync(compPath, "utf-8");

  // This component used to ship three hardcoded findings that rendered for
  // every client whether or not a scan had run, with invented impact numbers.
  // They are derived from the report now; see lib/priorities.ts and
  // tests/priorities.test.mjs.
  for (const fixture of [
    "Fix 8 pages missing a title",
    "Add business schema",
    "Improve FAQ answers on 3 pages",
    "DEFAULT_PRIORITIES",
    "Severity Weight",
  ]) {
    assert.ok(
      !content.includes(fixture),
      `Hardcoded priority fixture '${fixture}' must not return to PriorityActions.tsx`
    );
  }

  // `priorities` is required, so the component cannot silently fall back.
  assert.ok(
    /priorities: PriorityItem\[\];/.test(content),
    "priorities must be a required prop, not an optional with a default"
  );

  // Progressive disclosure is still the contract for each item.
  for (const section of ["Problem:", "Why it matters:", "Expected outcome:", "Source:", "Confidence:"]) {
    assert.ok(content.includes(section), `${section} section must be present`);
  }
  assert.ok(content.includes("View Technical Details"), "Technical Details trigger must be present");

  // An empty report must produce an honest empty state, not an empty column.
  assert.ok(
    content.includes("Nothing measured yet"),
    "an empty priority list must render an explicit empty state"
  );
});

test("Project Journey: Step-by-step 6-stage guidance is present", async () => {
  // Asserts the exported steps, not the text of a file. The labels moved to
  // `lib/journey` when the bar stopped deciding its own stage, and a grep over
  // the component would have gone on passing against a comment.
  const { JOURNEY_STEPS } = await import("../lib/journey.ts");
  assert.deepEqual(
    JOURNEY_STEPS.map((s) => s.label),
    [
      "Create Project",
      "Connect Google / Add Site",
      "Run Audit",
      "Review Top Priorities",
      "Review or Apply Fixes",
      "Track Results Over Time",
    ]
  );
});

test("Project Journey: no caller may assert a stage the evidence does not support", () => {
  // The whole defect: `currentStep={4}` hardcoded at both call sites, and
  // Overview also passing `hasClient={true} hasScan={true}`, so an empty
  // account read "Stage 4 of 6" with three steps ticked green. The prop no
  // longer exists; this fails if anything reintroduces a literal stage.
  for (const file of ["app/ReaiDashboard.tsx", "components/dashboard/Overview.tsx"]) {
    const content = fs.readFileSync(path.join(webDir, file), "utf-8");
    for (const banned of [/currentStep=\{\d/, /hasClient=\{true\}/, /hasScan=\{true\}/]) {
      assert.ok(
        !banned.test(content),
        `${file} asserts a journey stage (${banned}) instead of passing evidence`
      );
    }
  }
});

test("Language System: Standardized vocabulary enforced across dashboard components", () => {
  const compDir = path.join(webDir, "components", "dashboard");
  const forbiddenJargon = [
    "Technical Intelligence Matrix",
    "AEO Lab / AI Engine Matrix",
    "Autonomous Flow",
    "Diagnostics Matrix",
    "Data Provenance",
    "Citation Likelihood",
  ];

  const files = fs.readdirSync(compDir).filter((f) => f.endsWith(".tsx"));
  for (const file of files) {
    const fileContent = fs.readFileSync(path.join(compDir, file), "utf-8");
    for (const term of forbiddenJargon) {
      assert.ok(
        !fileContent.includes(term),
        `Found forbidden term '${term}' in components/dashboard/${file}`
      );
    }
  }
});

test("Component Decomposition: every dashboard component is actually rendered", () => {
  // This used to assert a list of filenames existed. A file existing proves
  // nothing: six of the components it required rendered nowhere at all, while
  // the CHANGELOG claimed decomposition had shipped. Asserting that each is
  // rendered is the property that was actually wanted.
  const compDir = path.join(webDir, "components", "dashboard");
  const sources = [
    fs.readFileSync(path.join(webDir, "app", "ReaiDashboard.tsx"), "utf-8"),
    fs.readFileSync(path.join(webDir, "app", "ScannerApp.tsx"), "utf-8"),
    ...fs
      .readdirSync(compDir)
      .filter((f) => f.endsWith(".tsx"))
      .map((f) => fs.readFileSync(path.join(compDir, f), "utf-8")),
  ].join("\n");

  // A component file is one exporting a component named after the file.
  // `primitives.tsx` is a module of shared icons imported by name, not a
  // component, so it is not expected to appear as `<primitives`.
  const components = fs
    .readdirSync(compDir)
    .filter((f) => f.endsWith(".tsx"))
    .map((f) => f.replace(/\.tsx$/, ""))
    .filter((c) => {
      const src = fs.readFileSync(path.join(compDir, `${c}.tsx`), "utf-8");
      return new RegExp(`export (function|const) ${c}\\b`).test(src);
    });

  assert.ok(components.length > 0, "no dashboard components found");

  const dead = components.filter((c) => {
    // Count renders outside the component's own file.
    const own = fs.readFileSync(path.join(compDir, `${c}.tsx`), "utf-8");
    const elsewhere = sources.split(own).join("");
    return !elsewhere.includes(`<${c}`);
  });

  assert.deepEqual(
    dead,
    [],
    `these components are rendered nowhere - wire them or delete them: ${dead.join(", ")}`
  );
});

test("Google Services Hub: Unified single connect and secondary account options exist", () => {
  const hubPath = path.join(webDir, "components", "dashboard", "GoogleServicesHub.tsx");
  assert.ok(fs.existsSync(hubPath), "GoogleServicesHub.tsx must exist");
  const content = fs.readFileSync(hubPath, "utf-8");

  assert.ok(content.includes("Connect Google Services"), "Single master connect button must exist");
  assert.ok(content.includes("Search Console"), "Search console breakdown must exist");
  assert.ok(content.includes("Business Profile"), "Business profile breakdown must exist");
  assert.ok(content.includes("gbp_secondary"), "Secondary GBP account override must be supported");
});

test("Privacy & Trust: Personal email address is absent across web codebase", () => {
  const user = "vnheksony";
  const domain = "gmail.com";
  const forbiddenEmail = `${user}@${domain}`;

  function scanDir(dir) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.name === "node_modules" || entry.name === ".next" || entry.name === ".git" || entry.name === "tests") {
        continue;
      }
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        scanDir(fullPath);
      } else if (/\.(tsx|ts|jsx|js|mjs|json|html|css|md)$/.test(entry.name)) {
        const fileContent = fs.readFileSync(fullPath, "utf-8");
        assert.ok(
          !fileContent.includes(forbiddenEmail),
          `Found forbidden email in ${fullPath}`
        );
      }
    }
  }

  scanDir(webDir);
});

test("Tools Directory: the catalog comes from the scanner, not a fixture", () => {
  // `app/toolsCatalogData.ts` declared 160 tools in its header, held 148
  // entries, and was transcribed from a document. No entry carried a key, a
  // cost, or anything the scanner would recognise, so nothing in it could be
  // run and nothing said which of the 23 real tools it corresponded to.
  const fixture = path.join(webDir, "app", "toolsCatalogData.ts");
  assert.ok(!fs.existsSync(fixture), "the fabricated tool catalog must not return");

  const dashboard = fs.readFileSync(path.join(webDir, "app", "ReaiDashboard.tsx"), "utf-8");
  assert.ok(
    !dashboard.includes("ALL_PLATFORM_TOOLS"),
    "the dashboard must not read the fabricated catalog"
  );
  assert.ok(
    dashboard.includes("fetchTools"),
    "the directory must read the scanner's own catalog via /api/tools"
  );

  // The real module exists and is the single source.
  const lib = path.join(webDir, "lib", "toolCatalog.ts");
  assert.ok(fs.existsSync(lib), "lib/toolCatalog.ts must exist");
  const libSrc = fs.readFileSync(lib, "utf-8");
  assert.ok(libSrc.includes("/api/tools"), "the catalog must be fetched from /api/tools");
});

test("Local Business Manager: Comprehensive Google profile and maps management is present", () => {
  const compPath = path.join(webDir, "components", "dashboard", "LocalBusinessManager.tsx");
  assert.ok(fs.existsSync(compPath), "LocalBusinessManager.tsx must exist");
  const content = fs.readFileSync(compPath, "utf-8");

  // Core management capabilities:
  assert.ok(content.includes("Business Info & NAP"), "Business info tab must exist");
  assert.ok(content.includes("Operating & Holiday Hours"), "Operating hours tab must exist");
  assert.ok(content.includes("Reviews & AI Reply"), "Reviews & AI reply tab must exist");
  assert.ok(content.includes("Google Maps Posts"), "Google Maps posts tab must exist");
  assert.ok(content.includes("Website Schema Alignment"), "NAP consistency and schema tab must exist");
  assert.ok(content.includes("Local Performance & Insights"), "Local performance insights tab must exist");

  // AI review reply engine:
  assert.ok(content.includes("generate_ai_reply"), "AI reply generation action must be supported");
  assert.ok(content.includes("Post Reply to Google Maps"), "Google Maps reply submission must be supported");

  // Holiday and regular hours:
  assert.ok(content.includes("Special Hours"), "Holiday / special hours must be configurable");
  assert.ok(content.includes("Add Closure"), "Add closure button must be present");
});

test("Local SEO API Routes: All backend endpoints exist and export valid route handlers", () => {
  const apiRoutes = [
    path.join(webDir, "app", "api", "local-seo", "business", "route.ts"),
    path.join(webDir, "app", "api", "local-seo", "reviews", "route.ts"),
    path.join(webDir, "app", "api", "local-seo", "posts", "route.ts"),
    path.join(webDir, "app", "api", "local-seo", "insights", "route.ts"),
  ];

  for (const routePath of apiRoutes) {
    assert.ok(fs.existsSync(routePath), `API route ${routePath} must exist`);
    const content = fs.readFileSync(routePath, "utf-8");
    assert.ok(content.includes("export async function GET"), `${routePath} must export a GET handler`);
  }
});

test("Audit Hero Bar: Prominent website audit input and clear results flow exist", () => {
  const compPath = path.join(webDir, "components", "dashboard", "AuditHeroBar.tsx");
  assert.ok(fs.existsSync(compPath), "AuditHeroBar.tsx must exist");
  const content = fs.readFileSync(compPath, "utf-8");

  assert.ok(content.includes("Audit Any Website"), "Hero audit header must exist");
  assert.ok(content.includes("Run Audit"), "Run audit button must exist");
  assert.ok(content.includes("Auditing"), "Scanning progress state must exist");
  assert.ok(content.includes("All Checks"), "Issues filter buttons must exist");
  assert.ok(content.includes("Review Fix"), "Direct fix review action must exist");
});

test("AI Search Visibility (AEO): Dedicated sub-views exist and switch dynamically for all 5 sub-topics", () => {
  const dashboardPath = path.join(webDir, "app", "ReaiDashboard.tsx");
  const content = fs.readFileSync(dashboardPath, "utf-8");

  // The five studios are navigated from the sidebar (AI Visibility > Studios).
  // The in-page tab bar that repeated those same five entries is gone: two
  // navigations for one set of destinations made every studio read as the same
  // page, which is what an operator reported. `selectAeoFocus` is still the
  // routing handler, now driven by the sidebar alone.
  assert.ok(content.includes("selectAeoFocus"), "selectAeoFocus routing handler must be defined");
  assert.ok(
    !content.includes('aria-label="AI Search Visibility Sections"'),
    "the in-page tab bar duplicating the sidebar must not come back"
  );

  // Verify all 5 dedicated sub-views
  assert.ok(content.includes('aeoActiveFocus === "matrix"'), "AI Readiness sub-view must exist");
  assert.ok(content.includes('aeoActiveFocus === "citations"'), "AI Citations sub-view must exist");
  assert.ok(content.includes('aeoActiveFocus === "schema"'), "Schema & Entities sub-view must exist");
  assert.ok(content.includes('aeoActiveFocus === "answers"'), "Answer Content sub-view must exist");
  assert.ok(content.includes('aeoActiveFocus === "crawlers"'), "AI Crawler Access sub-view must exist");

  // Switching studio has to change something above the fold, or the five read
  // as one page however different their content is further down.
  assert.ok(content.includes("aeoFocusLabel"), "the header must name the studio in view");

  // Verify dedicated content per sub-view
  assert.ok(content.includes("Detailed AEO & LLM Crawler Signals Matrix"), "Readiness matrix table must exist");
  assert.ok(content.includes("Generated JSON-LD Structured Data Snippet"), "JSON-LD snippet must exist in Schema");
  assert.ok(content.includes("Live /llms.txt Specification"), "/llms.txt studio must exist in Answers");
  assert.ok(content.includes("Recommended robots.txt Configuration for AEO"), "robots.txt recommendations must exist in Crawlers");
});

test("AI Search Visibility (AEO): no fabricated AI answers about the client", () => {
  const dashboardPath = path.join(webDir, "app", "ReaiDashboard.tsx");
  const content = fs.readFileSync(dashboardPath, "utf-8");

  // The prompt simulator shipped a hardcoded fixture of hospital-specific
  // queries with invented model responses, including a summary asserting the
  // client "is widely recognized as a premier private healthcare provider".
  // That fabricates a third-party endorsement and presents it as a simulation
  // result: industry-wrong for any non-healthcare client, and false for all.
  for (const fixture of [
    "Specialized Care Query",
    "premier private healthcare",
    "Emergency & 24/7 Consultation",
    "Specialist Accreditation",
  ]) {
    assert.ok(
      !content.includes(fixture),
      `Fabricated prompt fixture '${fixture}' must not return`
    );
  }

  // Structural guard: the fixture array itself, not just its strings.
  assert.equal(
    /const presetPrompts\s*=\s*\[/.test(content),
    false,
    "the presetPrompts fixture array must not return"
  );
});

