import { test } from "node:test";
import assert from "node:assert/strict";

/** GBP-as-local-source: converter + prefer-Google resolver. */
const G = await import("../lib/gbpLocal.ts");

test("a complete GBP location yields passing local rows", () => {
  const rows = G.gbpLocationToLocalRows({
    businessName: "Orienda Hospital", primaryCategory: "Hospital",
    phone: "+855 23 000 000", address: { street: "St 1", city: "Phnom Penh" },
    regularHours: { periods: [] }, verifiedOnGoogle: true,
  });
  const byCode = Object.fromEntries(rows.map((r) => [r.code, r]));
  assert.equal(byCode["gbp.category"].severity, "ok");
  assert.equal(byCode["gbp.nap"].severity, "ok");
  assert.equal(byCode["gbp.verified"].severity, "ok");
  assert.equal(byCode["gbp.category"].metrics.source, "gbp");
});

test("missing category / unverified profile warn", () => {
  const rows = G.gbpLocationToLocalRows({ businessName: "X", verifiedOnGoogle: false });
  const byCode = Object.fromEntries(rows.map((r) => [r.code, r]));
  assert.equal(byCode["gbp.category"].severity, "warn");
  assert.equal(byCode["gbp.verified"].severity, "warn");
  assert.equal(byCode["gbp.nap"].severity, "warn"); // only 1/4 NAP parts
});

test("resolver prefers GBP, falls back to DFS, else none", () => {
  const withGbp = G.resolveLocalRows({ gbpLocation: { primaryCategory: "Cafe" }, dfsRows: [{ code: "gbp.reviews" }] });
  assert.equal(withGbp.source, "gbp");

  const fallback = G.resolveLocalRows({ gbpLocation: null, dfsRows: [{ code: "gbp.reviews", what: "3★" }] });
  assert.equal(fallback.source, "dataforseo");
  assert.equal(fallback.rows[0].what, "3★");

  const none = G.resolveLocalRows({ gbpLocation: null, dfsRows: [] });
  assert.equal(none.source, "none");
  assert.equal(G.localSourceLabel("gbp"), "Google Business Profile");
});
