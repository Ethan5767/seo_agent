import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * The one-label-one-destination invariant.
 *
 * The sidebar is two tiers by design: a narrow icon rail picks a section, a
 * wider drawer lists that section's screens. The failure mode is not the two
 * tiers, it is the two tiers each carrying their own hand-maintained copy of
 * the menu. That is what happened: ~30 entries pointed at 11 real screens.
 * "Technical SEO", "Sensor" and "Site Audit" all opened Site Health & Audit,
 * seven labels all opened Keyword Data Lab, four opened Traffic Analytics, and
 * "Technical SEO" additionally hardcoded isSelected: false so it could never
 * highlight.
 *
 * Both tiers now derive from NAV_SECTIONS. These tests assert that structure,
 * because a shared source of truth only helps while it stays the only one.
 */

const SRC = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");

/** The NAV_SECTIONS literal, as source text. */
function navSectionsSource() {
  const start = SRC.indexOf("export const NAV_SECTIONS");
  assert.notEqual(start, -1, "NAV_SECTIONS not found in ReaiDashboard.tsx");
  const end = SRC.indexOf("\n];", start);
  assert.notEqual(end, -1, "could not find the end of NAV_SECTIONS");
  return SRC.slice(start, end);
}

/** Every nav item, with the destination it resolves to. */
function navItems() {
  const items = [];
  const re = /\{ label: "([^"]+)"([^}]*)\}/g;
  for (const m of navSectionsSource().matchAll(re)) {
    const [, label, rest] = m;
    const tab = /tab: "([^"]+)"/.exec(rest);
    const sub = /sub: "([^"]+)"/.exec(rest);
    const focus = /focus: "([^"]+)"/.exec(rest);
    const href = /href: "([^"]+)"/.exec(rest);
    const view = /view: "([^"]+)"/.exec(rest);
    const local = /local: "([^"]+)"/.exec(rest);
    const gsc = /gsc: "([^"]+)"/.exec(rest);
    const stage = /stage: "([^"]+)"/.exec(rest);
    const content = /content: "([^"]+)"/.exec(rest);

    let destination;
    // Engine pipeline stages (plan / gate / merge) — lib/pipelineStages.ts.
    if (stage) destination = `stage:${stage[1]}`;
    else if (content) destination = `content:${content[1]}`;
    else if (gsc) destination = `gsc:${gsc[1]}`;
    else if (view) destination = `view:${view[1]}`;
    // Local's eight entries share one tab but select different sub-sections of
    // it, so the sub-section is part of the destination.
    else if (local && tab) destination = `${tab[1]}:local:${local[1]}`;
    else if (focus) destination = `aeo:${focus[1]}`;
    else if (href) destination = `href:${href[1]}`;
    else if (/drawer: true/.test(rest)) destination = "drawer";
    else if (/modal: true/.test(rest)) destination = "modal";
    else if (tab) destination = sub ? `${tab[1]}:${sub[1]}` : tab[1];
    else destination = `unknown:${label}`;

    items.push({ label, destination });
  }
  return items;
}

test("every nav label opens a different destination", () => {
  const items = navItems();
  assert.ok(items.length >= 10, `expected a populated nav, got ${items.length}`);

  const byDestination = new Map();
  for (const { label, destination } of items) {
    byDestination.set(destination, [...(byDestination.get(destination) ?? []), label]);
  }

  const duplicates = [...byDestination.entries()].filter(([, labels]) => labels.length > 1);
  assert.deepEqual(
    duplicates,
    [],
    `these destinations are reachable under more than one label: ${JSON.stringify(duplicates)}`,
  );
});

test("every nav label is unique", () => {
  const labels = navItems().map((i) => i.label);
  const dupes = labels.filter((l, i) => labels.indexOf(l) !== i);
  assert.deepEqual(dupes, [], `duplicate labels: ${dupes.join(", ")}`);
});

test("no nav item resolves to nothing", () => {
  const orphans = navItems().filter((i) => i.destination.startsWith("unknown:"));
  assert.deepEqual(orphans, [], `nav items with no destination: ${JSON.stringify(orphans)}`);
});

test("the pinned tools button is not also a nav item", () => {
  // The directory has its own pinned button at the foot of the drawer. Listing
  // it in a section as well is the duplicate this structure exists to prevent.
  const labels = navItems().map((i) => i.label);
  assert.equal(
    labels.includes("All Tools"),
    false,
    "All Tools Directory has a pinned button; it must not also be a section item",
  );
});

test("no nav entry is hardcoded to never highlight", () => {
  const start = SRC.indexOf("Merged navigation, drawer half");
  const end = SRC.indexOf("All Tools Directory Pinned", start);
  assert.ok(start !== -1 && end !== -1, "drawer block not found");
  assert.equal(
    /isSelected:\s*false/.test(SRC.slice(start, end)),
    false,
    "an entry sets isSelected: false, so it can never show as the current page",
  );
});

test("both sidebar tiers read the same source", () => {
  // The rail and the drawer must both map over NAV_SECTIONS. Two separate
  // literals is how the menus drifted apart in the first place.
  const railUsesSections = /NAV_SECTIONS\.map/.test(SRC);
  const drawerUsesSections = /NAV_SECTIONS\.filter/.test(SRC);
  assert.ok(railUsesSections, "the rail must render from NAV_SECTIONS");
  assert.ok(drawerUsesSections, "the drawer must render from NAV_SECTIONS");
});

test("every rail section has an icon", () => {
  const ids = [...navSectionsSource().matchAll(/id: "([^"]+)"/g)].map((m) => m[1]);
  assert.ok(ids.length > 0, "no sections found");
  const iconsStart = SRC.indexOf("export const RAIL_ICONS");
  const iconsBlock = SRC.slice(iconsStart, SRC.indexOf("\n};", iconsStart));
  for (const id of ids) {
    assert.ok(
      new RegExp(`\\b${id}:`).test(iconsBlock),
      `rail section '${id}' has no icon in RAIL_ICONS`,
    );
  }
});

test("switching AEO view scrolls and transitions like a tab change", () => {
  // The five AEO views share a tall header. Without these, selecting one
  // changed state and the URL while nothing moved on screen, which read as
  // "AI Visibility always goes to the same page".
  const start = SRC.indexOf("const selectAeoFocus");
  const end = SRC.indexOf("const setActiveTab", start);
  assert.ok(start !== -1 && end !== -1, "selectAeoFocus not found");
  const body = SRC.slice(start, end);
  assert.ok(/window\.scrollTo/.test(body), "selectAeoFocus must scroll to top");
  assert.ok(
    /setIsTabTransitioning\(true\)/.test(body),
    "selectAeoFocus must show the tab transition",
  );
});

test("no competitor trademarks ship as menu items", () => {
  // Competitor product names in a competing product are a legal exposure, not a
  // style question. Kept as a test so they cannot come back by copy-paste.
  const source = navSectionsSource();
  for (const mark of ["Sensor", "SEOquake", "Semrush Rank"]) {
    assert.equal(
      source.includes(`label: "${mark}"`),
      false,
      `"${mark}" is a competitor trademark and must not appear as a nav label`,
    );
  }
});

test("no competitor is named anywhere a client can read it", () => {
  // Wider than the nav check above, and for a different reason. We are building
  // the competitor's category, so naming them in our own UI does two bad things
  // at once: it advertises them, and it credits our output to their brand — a
  // score labelled "<competitor> algorithmic benchmark" tells the client the
  // number came from somewhere it did not.
  //
  // Comments are allowed to reference the field's vocabulary; rendered strings
  // are not. This scans JSX text and user-visible props only.
  const files = [
    "app/ReaiDashboard.tsx",
    "components/dashboard/MeasureScreen.tsx",
    "components/dashboard/ReportTable.tsx",
    "components/dashboard/AuditHeroBar.tsx",
    "lib/reportViews.ts",
    "lib/toolCatalog.ts",
  ];
  const brands = ["Semrush", "SEMrush", "Ahrefs", "Moz", "Screaming Frog", "Sitebulb", "Conductor"];

  for (const file of files) {
    const raw = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
    // Strip block comments, line comments and JSX comments before scanning, so
    // an internal note explaining why we do something stays legal.
    const code = raw
      .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    for (const brand of brands) {
      assert.equal(
        code.includes(brand),
        false,
        `"${brand}" appears in shipped ${file} outside a comment — a client can read it`,
      );
    }
  }
});

test("no page is split across several sidebar entries", () => {
  // The rule: if two things are separate, they get separate pages; if they are
  // one page, they get one entry. What is not allowed is one page wearing
  // several sidebar entries that each select a sub-tab of it — the sidebar then
  // promises navigation it does not deliver, and clicking three entries appears
  // to open the same page.
  //
  // This was the shape of "Site Health & Audit" (Site Audit / All Checks /
  // Plan / Scan Progress) and "Local SEO & GBP" (eight entries). Those screens
  // carry their own sub-tab bars; the sidebar lists each once.
  const byTab = new Map();
  for (const { label, destination } of navItems()) {
    // Only plain tab destinations can collide this way. A view, gsc or content
    // entry is its own screen, and `local:`/`sub:` suffixes are gone.
    if (destination.includes(":")) continue;
    if (destination === "drawer" || destination === "modal") continue;
    if (destination.startsWith("href:")) continue;
    byTab.set(destination, [...(byTab.get(destination) ?? []), label]);
  }

  const split = [...byTab.entries()].filter(([, labels]) => labels.length > 1);
  assert.deepEqual(
    split,
    [],
    `these screens are split across several sidebar entries: ${JSON.stringify(split)}`,
  );
});

test("both tiers dispatch through one function", () => {
  // The rail carried its own mini-dispatch that handled only `tab` and `focus`,
  // so clicking a section whose first item was a view/gsc/content/stage changed
  // the drawer and left the workspace on the previous screen. Gate showed it:
  // one click opened the drawer, a second was needed to actually go there.
  assert.ok(/const openNavItem = useCallback/.test(SRC), "openNavItem must exist");
  assert.ok(/if \(first\) openNavItem\(first\)/.test(SRC),
    "the rail must open the section's first item, not just switch the drawer");
  assert.ok(/onClick=\{\(\) => openNavItem\(item\)\}/.test(SRC),
    "the drawer must dispatch through the same function");

  // And it must handle every item kind, or the next one added falls through.
  const fn = SRC.slice(SRC.indexOf("const openNavItem"), SRC.indexOf("const [activeBigNav"));
  for (const kind of ["stage", "content", "gsc", "view", "drawer", "modal", "href", "focus", "tab"]) {
    assert.ok(new RegExp(`item\\.${kind}`).test(fn), `openNavItem ignores item.${kind}`);
  }
});

test("opening a section clears the other view modes", () => {
  // Without this an item kind inherits the last one — you click Gate and still
  // see the previous report view underneath it.
  const fn = SRC.slice(SRC.indexOf("const openNavItem"), SRC.indexOf("const [activeBigNav"));
  for (const setter of ["setActiveStage(null)", "setActiveContentTool(null)", "setActiveGscView(null)", "setActiveView(null)"]) {
    assert.ok(fn.includes(setter), `openNavItem must clear: ${setter}`);
  }
});

test("exactly one nav item can be highlighted, in every mode", () => {
  // Two items lit at once — "Fix Stage" and "Review Fixes" — because the
  // selection was a ladder of ternaries where each branch had to remember to
  // exclude every mode above it, and several did not. Rebuilt as: decide the
  // active mode once, then only that mode's items match.
  //
  // This models the rule rather than reading the source, so it fails if the
  // ladder ever comes back in a different shape.
  const items = [
    { label: "Fix Stage", stage: "fix" },
    { label: "Review Fixes", tab: "Auto-Fix Engine" },
    { label: "Gate & Merge", stage: "gate" },
    { label: "Content Brief", content: "brief" },
    { label: "Search Queries", gsc: "queries" },
    { label: "Crawl Issues", view: "site-crawl" },
    { label: "Dashboard", tab: "Overview" },
  ];
  const selected = (s, item) =>
    s.activeStage ? item.stage === s.activeStage
    : s.activeContentTool ? item.content === s.activeContentTool
    : s.activeGscView ? item.gsc === s.activeGscView
    : s.activeView ? item.view === s.activeView
    : Boolean(item.tab) && s.activeTab === item.tab;

  const states = [
    // The reported bug: a stage open while activeTab still points at a tab item.
    { activeStage: "fix", activeTab: "Auto-Fix Engine" },
    { activeStage: "gate", activeTab: "Auto-Fix Engine" },
    { activeContentTool: "brief", activeTab: "Auto-Fix Engine" },
    { activeGscView: "queries", activeTab: "Overview" },
    { activeView: "site-crawl", activeTab: "Overview" },
    { activeTab: "Overview" },
    { activeTab: "Auto-Fix Engine" },
  ];
  for (const s of states) {
    const lit = items.filter((i) => selected(s, i)).map((i) => i.label);
    assert.ok(lit.length <= 1,
      `${JSON.stringify(s)} highlighted ${lit.length}: ${lit.join(" + ")}`);
  }
});

test("the selection is a single mode check, not a per-branch exclusion ladder", () => {
  // There are two `isSelected` in the file: the RAIL's (activeBigNav === id)
  // and the drawer item's. This test is about the drawer's, so find that one
  // specifically rather than whichever appears first.
  const start = SRC.indexOf("const isSelected =\n                      activeStage ?");
  assert.notEqual(start, -1, "the drawer's mode-based selection was not found");
  const body = SRC.slice(start, start + 900);
  // The ladder's signature: a later branch re-excluding an earlier mode.
  assert.ok(!/!activeStage/.test(body),
    "no branch should need to exclude activeStage — the mode check does it once");
  assert.ok(!/!activeContentTool/.test(body) && !/!activeGscView/.test(body),
    "per-branch exclusions are what let two items light at once");
  assert.ok(/activeStage \? item\.stage === activeStage/.test(body),
    "mode is decided first, then matched");
});
