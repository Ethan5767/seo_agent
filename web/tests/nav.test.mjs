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
    const content = /content: "([^"]+)"/.exec(rest);

    let destination;
    if (content) destination = `content:${content[1]}`;
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
  // Semrush product names in a competing product are a legal exposure, not a
  // style question. Kept as a test so they cannot come back by copy-paste.
  const source = navSectionsSource();
  for (const mark of ["Sensor", "SEOquake", "Semrush Rank"]) {
    assert.equal(
      source.includes(`label: "${mark}"`),
      false,
      `"${mark}" is a Semrush trademark and must not appear as a nav label`,
    );
  }
});
