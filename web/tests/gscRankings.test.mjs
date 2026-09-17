import { test } from "node:test";
import assert from "node:assert/strict";

/** GSC-as-rankings-source: converter + prefer-Google resolver. */
const G = await import("../lib/gscRankings.ts");

test("a GSC query row becomes a ranked-keyword row with real clicks/impressions", () => {
  const row = G.gscQueryToRankingRow({ keys: ["hospital phnom penh"], position: 7.4, clicks: 12, impressions: 340, ctr: 0.035 });
  assert.equal(row.code, "dfs.ranked_keyword");
  assert.match(row.what, /rank #7/);
  assert.equal(row.metrics.source, "gsc");
  assert.equal(row.metrics.position, 7.4);
  assert.equal(row.metrics.rank, 7);
  assert.equal(row.metrics.clicks, 12);
  assert.equal(row.metrics.volume, null); // GSC has no volume
});

test("rows with no keyword are dropped and results sort by best position", () => {
  const rows = G.gscQueriesToRankingRows([
    { keys: ["b term"], position: 9 },
    { keys: [""], position: 1 },      // no keyword -> dropped
    { keys: ["a term"], position: 2 },
  ]);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].metrics.keyword, "a term"); // position 2 first
});

test("resolver prefers Google when it has rows", () => {
  const r = G.resolveRankingRows({
    gscRows: [{ keys: ["kw"], position: 3 }],
    dfsRows: [{ code: "dfs.ranked_keyword", what: "dfs" }],
  });
  assert.equal(r.source, "gsc");
  assert.equal(r.rows[0].metrics.source, "gsc");
});

test("resolver falls back to DataForSEO when GSC is empty", () => {
  const r = G.resolveRankingRows({ gscRows: [], dfsRows: [{ code: "dfs.ranked_keyword", what: "dfs kw" }] });
  assert.equal(r.source, "dataforseo");
  assert.equal(r.rows[0].what, "dfs kw");
});

test("resolver reports none when neither source has rows", () => {
  const r = G.resolveRankingRows({ gscRows: [], dfsRows: [] });
  assert.equal(r.source, "none");
  assert.equal(r.rows.length, 0);
  assert.equal(G.rankingSourceLabel("none"), "Not connected");
});
