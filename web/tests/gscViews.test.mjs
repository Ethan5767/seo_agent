import { test } from "node:test";
import assert from "node:assert/strict";

/**
 * Search Console views: measured figures, not modelled ones.
 *
 * The arithmetic is worth testing because the obvious version is wrong.
 * Averaging per-row CTR or position gives one impression on an obscure query
 * the same weight as ten thousand on a head term, which quietly overstates
 * position on every site with a long tail.
 */

const { GSC_VIEWS, gscViewById, gscTotals, formatGscValue } = await import("../lib/gscViews.ts");

test("view ids, labels and dimensions are coherent", () => {
  const ids = GSC_VIEWS.map((v) => v.id);
  const labels = GSC_VIEWS.map((v) => v.label);
  assert.equal(new Set(ids).size, ids.length, "duplicate view id");
  assert.equal(new Set(labels).size, labels.length, "duplicate view label");
  for (const v of GSC_VIEWS) {
    assert.ok(v.blurb.length > 0, `${v.id} has no blurb`);
    assert.ok(v.emptyHint.length > 0, `${v.id} has no empty hint`);
    assert.ok(v.keyLabel.length > 0, `${v.id} has no key column label`);
    assert.ok(gscViewById(v.id), `${v.id} is not findable`);
  }
});

test("one view per Search Console dimension, no repeats", () => {
  const dims = GSC_VIEWS.map((v) => v.dimension);
  assert.equal(new Set(dims).size, dims.length, "two views share a dimension");
});

test("totals are zero when nothing is loaded", () => {
  for (const empty of [null, undefined, []]) {
    assert.deepEqual(gscTotals(empty), {
      rows: 0,
      clicks: 0,
      impressions: 0,
      ctr: 0,
      position: 0,
    });
  }
});

test("clicks and impressions are summed", () => {
  const t = gscTotals([
    { clicks: 10, impressions: 100, position: 5 },
    { clicks: 5, impressions: 50, position: 9 },
  ]);
  assert.equal(t.rows, 2);
  assert.equal(t.clicks, 15);
  assert.equal(t.impressions, 150);
});

test("CTR is computed from the totals, not averaged per row", () => {
  // Per-row CTRs are 50% and 1%. A naive mean gives 25.5%; the true rate is
  // 11/1010 = 1.09%.
  const t = gscTotals([
    { clicks: 1, impressions: 2 },
    { clicks: 10, impressions: 1008 },
  ]);
  assert.equal(t.clicks / t.impressions, t.ctr);
  assert.ok(t.ctr < 0.02, `expected ~1%, got ${(t.ctr * 100).toFixed(2)}%`);
});

test("average position is weighted by impressions", () => {
  // One impression at position 1, a thousand at position 50. A plain mean says
  // 25.5, which would read as a healthy site. The weighted figure is ~49.95.
  const t = gscTotals([
    { clicks: 1, impressions: 1, position: 1 },
    { clicks: 2, impressions: 1000, position: 50 },
  ]);
  assert.ok(t.position > 49, `expected ~49.95, got ${t.position}`);
});

test("zero impressions cannot divide by zero", () => {
  const t = gscTotals([{ clicks: 0, impressions: 0, position: 0 }]);
  assert.equal(t.ctr, 0);
  assert.equal(t.position, 0);
  assert.equal(t.rows, 1);
});

test("malformed rows are skipped without throwing", () => {
  const t = gscTotals([null, 7, "x", { clicks: 3, impressions: 10, position: 4 }]);
  assert.equal(t.rows, 1);
  assert.equal(t.clicks, 3);
});

test("values format without inventing anything", () => {
  assert.equal(formatGscValue("keys", ["roof repair"]), "roof repair");
  assert.equal(formatGscValue("keys", ["mobile", "USA"]), "mobile · USA");
  assert.equal(formatGscValue("clicks", 1234), "1,234");
  assert.equal(formatGscValue("ctr", 0.0432), "4.3%");
  assert.equal(formatGscValue("position", 4.27), "4.3");
  // Missing values read as zero, never as a dash that hides a real zero.
  assert.equal(formatGscValue("clicks", undefined), "0");
  assert.equal(formatGscValue("position", null), "0.0");
  assert.equal(formatGscValue("clicks", "not-a-number"), "0");
});
