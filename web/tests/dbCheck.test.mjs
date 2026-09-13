import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * The drift checker must stay read-only and must keep probing from outside.
 *
 * B-091 is the reason the anon probe exists. The policy on `traffic_snapshots`
 * was present, was named `traffic_snapshots_owner`, and granted every row to
 * everybody. Reading the schema file would have called it fine; only asking the
 * database with the PUBLIC key showed 170 of 170 rows coming back.
 */
const SRC = readFileSync(new URL("../scripts/db-check.mjs", import.meta.url), "utf8");
const CODE = SRC.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

test("the checker never writes", () => {
  // It runs against a live production database. A tool that can only read is a
  // tool nobody has to think twice about running.
  //
  // Asserted on what it EXECUTES, not on substrings: the script parses
  // supabase-schema.sql, so the literal "alter table" appears inside a regex
  // and a naive grep flags it. That false positive is the whole reason this
  // test states the rule as "no method other than GET, and no subprocess".
  assert.ok(!/method\s*:/.test(CODE),
    "every fetch must be a plain GET; a `method:` option means it can write");
  for (const bad of ["child_process", "execSync", "spawn(", "unlink", "writeFileSync"]) {
    assert.ok(!CODE.includes(bad), `db-check reaches for ${bad}`);
  }
  // The only two verbs it may use.
  const calls = CODE.match(/fetch\(/g) || [];
  assert.ok(calls.length > 0 && calls.length <= 3, "unexpected number of network calls");
});

test("it asks the database with the PUBLIC key, not just the schema file", () => {
  // Reading supabase-schema.sql alone would have passed B-091.
  assert.match(CODE, /anonRowCount/);
  assert.match(CODE, /head\(ANON/);
  assert.match(CODE, /RLS is not protecting a per-user table/);
});

test("any row returned to the anon key on a per-user table is a failure", () => {
  assert.match(CODE, /anon > 0/);
  assert.match(CODE, /cols\.has\("user_id"\)/,
    "only tables that carry per-user data are probed");
});

test("it distinguishes cannot-check from in-sync", () => {
  // Exit 0 must mean "asked, and it is fine" - never "could not ask". Same rule
  // the gates run on: a check that scanned nothing must not report a pass.
  assert.match(CODE, /process\.exit\(2\)/, "missing credentials must not exit 0");
  assert.match(CODE, /schema read failed/);
});

test("drift exits non-zero so CI can fail on it", () => {
  assert.match(CODE, /process\.exit\(1\)/);
  assert.match(CODE, /In sync\. No migrations outstanding\./);
});

test("it is reachable as an npm script", () => {
  // B-007: a tool nobody can run is not shipped.
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.equal(pkg.scripts["db:check"], "node scripts/db-check.mjs");
});
