import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Report views turn row codes the scanner already emits into screens.
 *
 * The rule they exist to enforce: a nav entry must be backed by rows the
 * scanner really produces. A view whose codes no tool emits would be the alias
 * problem one layer down - a menu item that always opens an empty screen.
 */

const { REPORT_VIEWS, viewById, rowsForView, viewCounts, tallyRows } = await import("../lib/reportViews.ts");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "..", "..");

/**
 * Both directions of the same rule, over every scanner module on disk.
 *
 * The module list used to be typed out here. That is the failure this file
 * exists to prevent, one level up: a new scanner module would simply not be
 * read, both tests would pass over nothing, and the green would mean nothing.
 * `CLAUDE.md`: a gate that scanned nothing must never report a pass.
 */
function scannerSources() {
  const dir = path.join(REPO, "pipeline", "scanner");
  const files = readdirSync(dir).filter((f) => f.endsWith(".py") && f !== "__init__.py");
  assert.ok(files.length >= 10, `only ${files.length} scanner modules found - wrong path?`);
  return files.map((f) => readFileSync(path.join(dir, f), "utf8")).join("\n");
}

/**
 * Every code the scanner stamps, found at the places a row is BUILT rather than
 * by guessing at which strings look like codes. A prefix family ends in "." and
 * stands for the whole family.
 */
function emittedCodes(src) {
  const codes = new Set();
  const add = (re, fn) => {
    for (const m of src.matchAll(re)) codes.add(fn(m));
  };
  const CODE = "[a-z_]+\\.[a-z_0-9.]*[a-z_0-9]";
  add(/make_row\("([a-z_]+)"\)/g, (m) => `${m[1]}.`);          // rows.make_row
  add(/"code":\s*f"([a-z_]+\.(?:[a-z_0-9]+\.)*)\{/g, (m) => m[1]); // f-string code
  add(new RegExp(`"code":\\s*"(${CODE})"`, "g"), (m) => m[1]); // dict literal
  // The row helpers that take the code as their first argument, and the
  // code-keyed copy tables (`"dfs.broken_links": ("...", ...)`).
  // `\\s*` because a multi-line call puts the code on the line after the paren.
  add(new RegExp(`\\b_(?:row|pass_row|kw_row|check)\\(\\s*"(${CODE})"`, "g"), (m) => m[1]);
  add(new RegExp(`^\\s*"(${CODE})":\\s*[({]`, "gm"), (m) => m[1]);
  return codes;
}

/**
 * Canaries. If a refactor breaks one of the patterns above, the extraction
 * quietly returns less and every coverage assertion below passes over the gap.
 * These are stamped by four different mechanisms, so a silent extraction
 * failure cannot survive all of them.
 */
const MUST_FIND = [
  "aeo.crawler_blocked", "dfs.backlinks", "tech.", "src.", "health.title_missing",
];

/**
 * Families deliberately not on a sectioned screen, each with its reason.
 * An entry here is a decision on the record, not an omission.
 */
const UNSECTIONED = {
  src: "Source code checks are hidden: every tool checks the live domain (operator, 2026-09-14).",
  gbp: "Local Presence renders GBP through its own panel and API, not the row tables.",
  mention:
    "Web brand mentions (the paid Reputation tool) have no sectioned screen yet; "
    + "they show on the combined audit list. Open gap, recorded rather than hidden.",
};

test("the code extraction still finds what it is supposed to find", () => {
  const codes = emittedCodes(scannerSources());
  for (const canary of MUST_FIND) {
    assert.ok(codes.has(canary), `extraction lost '${canary}' - a row-builder pattern has drifted`);
  }
  assert.ok(codes.size > 30, `expected the scanner's codes, found ${codes.size}`);
});

test("every view's codes are emitted somewhere in the scanner", () => {
  // No view may invent a code: a screen with no backing row is the alias
  // problem one layer down, a menu item that always opens empty.
  const codes = [...emittedCodes(scannerSources())];
  for (const view of REPORT_VIEWS) {
    for (const code of view.codes) {
      // A prefix view is backed if ANY real code falls under it - either the
      // family itself is stamped (`make_row("tech")`) or a member of it is
      // registered (`health.title_missing`, which `measure` emits from outside
      // this directory).
      const backed = code.endsWith(".")
        ? codes.some((c) => c === code || c.startsWith(code))
        : codes.includes(code);
      assert.ok(
        backed,
        `view '${view.id}' lists code '${code}', which no scanner module emits`
      );
    }
  }
});

/**
 * The reverse direction, and the one that actually slipped.
 *
 * Nothing proved that a code the scanner emits reaches a screen. So when the
 * AEO pass added `aeo.training_crawler_blocked`, `aeo.answer_schema_missing`
 * and `aeo.article_author_missing`, the scanner measured all three on every run
 * and the three AEO screens showed none of them - B-007's shape, where a
 * finished module was called by nothing.
 */
test("every code the scanner emits reaches a screen", () => {
  const claimed = [...REPORT_VIEWS.flatMap((v) => v.codes)];
  const isClaimed = (code) =>
    claimed.some((c) => (c.endsWith(".") ? code.startsWith(c) : c === code));

  const orphans = [...emittedCodes(scannerSources())]
    // `unavailable.<tool>` reaches screens through VIEW_TOOLS, not a view's
    // code list; the test below proves every tool has such a screen.
    .filter((code) => code !== "unavailable.")
    .filter((code) => !UNSECTIONED[code.split(".")[0]] && !isClaimed(code))
    .sort();

  assert.deepEqual(
    orphans,
    [],
    "these codes are measured on every scan and appear on no screen: " + orphans.join(", ")
  );
});

test("view ids and labels are unique", () => {
  const ids = REPORT_VIEWS.map((v) => v.id);
  const labels = REPORT_VIEWS.map((v) => v.label);
  assert.equal(new Set(ids).size, ids.length, "duplicate view id");
  assert.equal(new Set(labels).size, labels.length, "duplicate view label");
});

test("no two views claim the same code", () => {
  // Overlap would put the same rows on two screens, which is how the old menu
  // ended up with seven labels over one destination.
  const owner = new Map();
  for (const view of REPORT_VIEWS) {
    for (const code of view.codes) {
      assert.equal(
        owner.has(code),
        false,
        `code '${code}' is claimed by both '${owner.get(code)}' and '${view.id}'`
      );
      owner.set(code, view.id);
    }
  }
});

test("every view declares columns and an empty hint", () => {
  for (const view of REPORT_VIEWS) {
    assert.ok(view.columns.length > 0, `${view.id} has no columns`);
    assert.ok(view.blurb.length > 0, `${view.id} has no blurb`);
    assert.ok(view.emptyHint.length > 0, `${view.id} has no empty hint`);
  }
});

const REPORT = {
  keywords: [
    { code: "dfs.keyword_gap", what: "roof repair austin", detail: "pos 4", why: "competitor ranks", severity: "info" },
    { code: "dfs.keyword_gap", what: "metal roofing", detail: "pos 7", why: "competitor ranks", severity: "info" },
    { code: "dfs.competitor", what: "rival.com", detail: "62 shared terms", why: "same SERP", severity: "info" },
  ],
  compare: [
    { code: "dfs.compare_domain", domain: "acme.com", what: "acme.com (you): 120 keywords", severity: "info" },
    { code: "dfs.compare_domain", domain: "rival.com", competitor: "rival.com", what: "rival.com: 300 keywords", severity: "info" },
    { code: "dfs.keyword_idea", what: "gutter replacement", detail: "vol 190", why: "related", severity: "info" },
  ],
  backlinks: [
    { code: "dfs.backlinks", what: "referring domains", detail: "48", why: "authority", severity: "info" },
    { code: "dfs.broken_backlinks", what: "broken backlinks", detail: "87 broken", why: "lost equity", fix: "redirect", severity: "warn" },
  ],
  site: [
    { code: "health.title_missing", what: "title missing", detail: "3 URLs", fix: "add titles", severity: "error" },
  ],
  score: 87,
  counts: { error: 1, warn: 1, info: 4, ok: 0 },
};

test("a view returns only its own rows", () => {
  const gap = rowsForView(REPORT, viewById("keyword-gap"));
  assert.equal(gap.length, 2);
  assert.ok(gap.every((r) => r.code === "dfs.keyword_gap"));

  const compared = rowsForView(REPORT, viewById("compare-domains"));
  assert.deepEqual(compared.map((r) => r.domain ?? r.what), ["rival.com", "acme.com", "rival.com"]);
});

test("a competitor's rows show only on comparison pages", () => {
  const withRival = {
    rankings: [
      { code: "dfs.domain_overview", what: "120 keywords", severity: "info" },
      { code: "dfs.domain_overview", competitor: "rival.com", what: "rival.com: 300 keywords", severity: "info" },
      { code: "dfs.ranked_keyword", competitor: "rival.com", what: "rival.com: \"x\" — rank #1", severity: "info" },
    ],
  };
  assert.deepEqual(rowsForView(withRival, viewById("domain-overview")).map((r) => r.what), ["120 keywords"]);
  assert.deepEqual(rowsForView(withRival, viewById("organic-rankings")), []);
});

test("a prefix view matches the whole family", () => {
  const onPage = rowsForView(REPORT, viewById("on-page"));
  assert.equal(onPage.length, 1);
  assert.equal(onPage[0].code, "health.title_missing");
});

test("a view with several codes gathers all of them", () => {
  const audit = rowsForView(REPORT, viewById("backlink-audit"));
  assert.equal(audit.length, 1, "only broken_backlinks is present in this report");
});

test("rows repeated across groups are de-duplicated", () => {
  const doubled = {
    keywords: REPORT.keywords,
    merged: REPORT.keywords, // the multipage merge re-emits rows
  };
  const gap = rowsForView(doubled, viewById("keyword-gap"));
  assert.equal(gap.length, 2, "the same code+what must not appear twice");
});

test("an unscanned report yields nothing, and does not throw", () => {
  for (const view of REPORT_VIEWS) {
    assert.deepEqual(rowsForView(null, view), []);
    assert.deepEqual(rowsForView({}, view), []);
    assert.deepEqual(rowsForView({ site: "not-an-array" }, view), []);
    assert.deepEqual(rowsForView({ site: [null, 7, "x"] }, view), []);
  }
});

test("viewCounts reports a number for every view", () => {
  const counts = viewCounts(REPORT);
  assert.equal(Object.keys(counts).length, REPORT_VIEWS.length);
  assert.equal(counts["keyword-gap"], 2);
  assert.equal(counts["compare-domains"], 3);
  assert.equal(counts["position-tracking"], 0);
});

test("tallyRows reports zeroes rather than nothing", () => {
  // The point of the count strip: an unscanned screen shows 0, not a blank.
  for (const empty of [null, undefined, [], {}]) {
    const t = tallyRows(empty);
    assert.deepEqual(t, { total: 0, error: 0, warn: 0, info: 0, ok: 0 });
  }
});

test("tallyRows counts each severity", () => {
  const t = tallyRows([
    { severity: "error" }, { severity: "error" },
    { severity: "warn" },
    { severity: "ok" },
    { severity: "info" },
  ]);
  assert.deepEqual(t, { total: 5, error: 2, warn: 1, info: 1, ok: 1 });
});

test("tallyRows never loses a row to an unknown severity", () => {
  const t = tallyRows([{ severity: "error" }, { severity: "bogus" }, {}]);
  assert.equal(t.total, 3, "every row counts toward the total");
  assert.equal(t.error, 1);
  assert.equal(t.warn + t.info + t.ok, 0);
});

test("tallyRows skips malformed entries without throwing", () => {
  const t = tallyRows([null, 42, "x", { severity: "warn" }]);
  assert.equal(t.total, 1);
  assert.equal(t.warn, 1);
});


/**
 * A tool that cannot run files `unavailable.<tool>`. That row is only visible on
 * a view the tool backs, so every scanner tool must back at least one view, or
 * its refusal is measured and shown nowhere.
 */
test("every scanner tool's 'did not run' row reaches a screen", async () => {
  // The tool pages read TOOL_SOURCES, so that is the table to check.
  const { TOOL_SOURCES, isEnabled } = await import("../lib/toolSources.ts");
  const server = readFileSync(path.join(REPO, "pipeline", "scanner", "server.py"), "utf8");
  const keys = [...server.matchAll(/Tool\("[^"]+", "([^"]+)"/g)].map((m) => m[1]);
  assert.ok(keys.length > 20, "could not parse the scanner tool list");
  const backed = new Set(Object.values(TOOL_SOURCES).flatMap((s) =>
    ["dataforseo", "ours"].flatMap((k) => (isEnabled(s[k]) ? s[k].tools : []))));
  // gbp renders in Local Presence's own panel; mentions has no screen yet (see UNSECTIONED).
  const exempt = new Set(["gbp", "mentions", "source"]);
  const orphans = keys.filter((k) => !backed.has(k) && !exempt.has(k));
  assert.deepEqual(orphans, [], "tools whose refusal would show on no screen: " + orphans.join(", "));
});

test("a view shows the 'did not run' row of its own tool, and only its own", async () => {
  const backlinks = viewById("backlinks");
  const report = {
    backlinks: [{ code: "unavailable.backlinks", what: "Backlinks did not run", why: "paused by DATAFORSEO_PAUSE_SPEND=1", fix: "", severity: "info" }],
    keywords: [{ code: "unavailable.keywords", what: "Keywords did not run", why: "x", fix: "", severity: "info" }],
  };
  const { TOOL_SOURCES } = await import("../lib/toolSources.ts");
  const rows = rowsForView(report, backlinks, TOOL_SOURCES.backlinks.dataforseo);
  assert.deepEqual(rows.map((r) => r.code), ["unavailable.backlinks"]);
  // No source = a caller that wants measurements (the Executive Report).
  assert.deepEqual(rowsForView(report, backlinks), []);
});

test("every reason a card filed survives, not just the first", async () => {
  const { TOOL_SOURCES } = await import("../lib/toolSources.ts");
  const report = { keywords: [
    { code: "unavailable.keywords", what: "Keywords did not run", why: "needs a competitor", severity: "info" },
    { code: "unavailable.keywords", what: "Keywords did not run", why: "no target keywords", severity: "info" },
  ] };
  const rows = rowsForView(report, viewById("keyword-overview"), TOOL_SOURCES["keyword-overview"].dataforseo);
  assert.deepEqual(rows.map((r) => r.why), ["needs a competitor", "no target keywords"]);
});

test("measured() drops every kind of 'did not run' row", async () => {
  const { measured } = await import("../lib/reportViews.ts");
  const rows = [
    { code: "unavailable.rankings", what: "Rankings did not run" },
    { code: "rankings.not_measured", what: "Not measured" },
    { code: "dfs.ranked_keyword", what: '"roofing" — rank #4' },
  ];
  assert.deepEqual(measured(rows).map((r) => r.code), ["dfs.ranked_keyword"]);
});
