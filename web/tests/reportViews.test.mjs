import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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

test("every view's codes are emitted somewhere in the scanner", () => {
  const scanner = ["dataforseo.py", "audit.py", "onpage_audit.py", "checks.py", "extra_checks.py",
     "lighthouse.py", "source_audit.py"]
    .map((f) => {
      try {
        return readFileSync(path.join(REPO, "pipeline", "scanner", f), "utf8");
      } catch {
        return "";
      }
    })
    .join("\n");
  assert.ok(scanner.length > 0, "could not read the scanner sources");

  for (const view of REPORT_VIEWS) {
    for (const code of view.codes) {
      const needle = code.endsWith(".") ? code : `"${code}"`;
      assert.ok(
        scanner.includes(needle),
        `view '${view.id}' lists code '${code}', which no scanner module emits`
      );
    }
  }
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

  const competitors = rowsForView(REPORT, viewById("compare-domains"));
  assert.deepEqual(competitors.map((r) => r.what), ["rival.com"]);
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
  assert.equal(counts["compare-domains"], 1);
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
