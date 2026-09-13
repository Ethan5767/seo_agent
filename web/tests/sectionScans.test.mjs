import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * "If SEO, when audit only audit about SEO."
 *
 * Every scan used to run all 25 tools, so pressing Scan on the Local page spent
 * money on backlinks and rank tracking and then showed five local rows.
 */
const { SECTION_SCANS, sectionById, toolsForSection, sectionCost } =
  await import("../lib/sectionScans.ts");

/** The real tool list, read from the scanner rather than restated here. */
const PY = readFileSync(new URL("../../pipeline/scanner/server.py", import.meta.url), "utf8");
const TOOLS = [...PY.matchAll(/Tool\("([^"]+)",\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"/g)]
  .map((m) => ({ label: m[1], key: m[2], category: m[3], group: m[4] }));

test("the scanner actually has tools to read", () => {
  assert.ok(TOOLS.length > 20, `parsed only ${TOOLS.length} tools from server.py`);
});

test("every category a section claims exists in the scanner", () => {
  // The map is product knowledge; a typo in it silently scans nothing.
  const real = new Set(TOOLS.map((t) => t.category));
  for (const s of SECTION_SCANS) {
    for (const c of s.categories) {
      assert.ok(real.has(c), `${s.id} claims category "${c}", which no tool declares`);
    }
  }
});

test("every section resolves to at least one real tool", () => {
  for (const s of SECTION_SCANS) {
    const keys = toolsForSection(s.id, TOOLS);
    assert.ok(keys && keys.length > 0, `${s.id} would scan nothing`);
  }
});

test("a section scan is always a strict subset of the full scan", () => {
  // No section may reach a tool the full scan would not run, or "scan this
  // section" could produce a finding "scan everything" would miss.
  const all = new Set(TOOLS.map((t) => t.key));
  for (const s of SECTION_SCANS) {
    for (const k of toolsForSection(s.id, TOOLS) ?? []) {
      assert.ok(all.has(k), `${s.id} would run "${k}", which is not a real tool`);
    }
  }
});

test("no two sections fight over the same tool", () => {
  // Overlap is not wrong in principle, but an unintended overlap means an
  // operator pays twice for one answer.
  const owner = new Map();
  for (const s of SECTION_SCANS) {
    for (const k of toolsForSection(s.id, TOOLS) ?? []) {
      assert.ok(!owner.has(k), `"${k}" is claimed by both ${owner.get(k)} and ${s.id}`);
      owner.set(k, s.id);
    }
  }
});

test("an unloaded tool list scans nothing rather than everything", () => {
  // null, not []. An empty set reads to build_report as "run nothing", and a
  // scan that ran nothing must never look like a scan that found nothing.
  for (const v of [null, undefined, []]) {
    assert.equal(toolsForSection("SEO", v), null);
    assert.equal(sectionCost("SEO", v), null);
  }
  assert.equal(toolsForSection("NoSuchSection", TOOLS), null);
});

test("the cost of a section scan is named before it runs", () => {
  // A scoped scan is mostly an argument about money.
  const seo = sectionCost("SEO", TOOLS);
  assert.ok(seo.free > 0, "the SEO section should be mostly free");

  const traffic = sectionCost("Traffic", TOOLS);
  assert.ok(traffic.paid.length > 0, "keywords and rankings are paid; say so");
  assert.equal(traffic.free, 0);

  const ai = sectionCost("AI", TOOLS);
  assert.ok(ai.free >= 1, "AEO structure checks are free");
});

test("the free sections really are free", () => {
  // Content and AEO should cost nothing per scan beyond the page fetch, which
  // is what makes them safe to run on every cycle.
  for (const id of ["Content"]) {
    const c = sectionCost(id, TOOLS);
    assert.equal(c.paid.length, 0, `${id} has a paid tool: ${c.paid.map((t) => t.key)}`);
  }
});

test("every section says what it looks at, in words an operator reads", () => {
  for (const s of SECTION_SCANS) {
    assert.ok(s.scope.length > 30, `${s.id}: the scope line is too thin to be useful`);
    assert.ok(sectionById(s.id), `${s.id} is not findable by id`);
  }
});


/* ── every screen knows its own section, and is wired ────────────────────── */

const { REPORT_VIEWS, ALL_FINDINGS_VIEW, CHECKS_VIEW } = await import("../lib/reportViews.ts");
const readSrc = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
const DASH = readSrc("app/ReaiDashboard.tsx");

test("every nav-reachable view declares its section", () => {
  // Without it the screen cannot scope its own scan, and silently falls back to
  // showing no button at all.
  for (const v of REPORT_VIEWS) {
    assert.ok(v.section, `view "${v.id}" has no section`);
    assert.ok(sectionById(v.section), `view "${v.id}" claims unknown section "${v.section}"`);
  }
});

test("the everything views belong to no section, deliberately", () => {
  // They show the whole scan, so scoping a scan from them is a contradiction.
  assert.equal(ALL_FINDINGS_VIEW.section, undefined);
  assert.equal(CHECKS_VIEW.section, undefined);
});

test("every section that owns a view can actually run a scan", () => {
  // A section with screens but no tools would render a dead button.
  const owning = new Set(REPORT_VIEWS.map((v) => v.section));
  for (const id of owning) {
    assert.ok(toolsForSection(id, TOOLS)?.length, `${id} owns screens but scans nothing`);
  }
});

test("the section scanner is mounted once, on the shared renderer", () => {
  // Once, not per screen: bolting a button onto each is how copies drift.
  assert.equal((DASH.match(/<SectionScanButton/g) ?? []).length, 1);
  assert.match(DASH, /sectionId=\{view\.section\}/);
  assert.match(DASH, /onScan=\{\(u, keys\) => onTriggerScan\?\.\(u, keys\)\}/);
});

test("a scoped scan reaches the scanner as a tool list", () => {
  // The seam already existed: build_report(..., selected=...) and the route's
  // `tools` field. This is one optional argument, not a second scan path.
  const app = readSrc("app/ScannerApp.tsx");
  assert.match(app, /run\(overrideUrl\?: string, overrideTools\?: string\[\]\)/);
  assert.match(app, /tools: overrideTools \?\? \[\.\.\.selected\]/);
  assert.match(app, /handleTriggerScan\(targetUrl: string, toolKeys\?: string\[\]\)/);
});

test("the button refuses rather than falling back to a full scan", () => {
  // A "safe" fallback to everything would quietly reinstate the behaviour this
  // replaces - and spend the money it exists to save.
  const btn = readSrc("components/dashboard/SectionScanButton.tsx");
  assert.match(btn, /const ready = Boolean\(keys && keys\.length\)/);
  assert.match(btn, /disabled=\{!ready \|\| busy\}/);
});

test("a project is required before anything can be audited", () => {
  // An audit runs against a specific site, and a project is what carries the
  // domain. Three states kept apart on purpose: "no projects at all" and "none
  // selected" need different actions, and the previous behaviour collapsed both
  // into one disabled button whose reason was only visible on hover.
  const btn = readSrc("components/dashboard/SectionScanButton.tsx");
  assert.match(btn, /if \(!hasProjects\)/);
  assert.match(btn, /Create a project before auditing/);
  assert.match(btn, /onClick=\{onCreateProject\}/, "the create button must be wired");
  assert.match(btn, /if \(!domain\)/);
  assert.match(btn, /Select a project<\/b> to scan/s);
  // The no-project branch must come first: with no projects, "select one" is
  // advice the operator cannot act on.
  assert.ok(btn.indexOf("if (!hasProjects)") < btn.indexOf("if (!domain)"));
});

test("the precondition is wired to the real project list and the real modal", () => {
  // B-007: a state nobody can reach is not shipped.
  assert.match(DASH, /hasProjects=\{clients\.length > 0\}/);
  // openCreateProject() rather than a raw setState: it also blanks the form and
  // clears `editingProject`, so "Create" after an "Edit" cannot silently reopen
  // — and overwrite — the project that was last edited.
  assert.match(DASH, /onCreateProject=\{\(\) => openCreateProject\(\)\}/);
  assert.match(DASH, /function openCreateProject\(\)/);
});

test("the paid tools are named before the click, not totalled", () => {
  // A total hides which tool is expensive, and that is the decision being made.
  const btn = readSrc("components/dashboard/SectionScanButton.tsx");
  assert.match(btn, /paid\.map\(/);
  assert.match(btn, /all free/);
});
