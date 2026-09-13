import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * Row Level Security is the only thing standing between one customer's data and
 * every other customer, because the anon key is public by design - it ships in
 * the browser bundle, and RLS is what makes that safe.
 *
 * B-091: `traffic_snapshots` had RLS enabled and a policy named
 * `traffic_snapshots_owner` whose body was `using (true) with check (true)`.
 * Enabled-and-named-owner is exactly what a reviewer scanning this file sees, so
 * nothing about it looked wrong. An anonymous read returned 170 of 170 rows,
 * carrying every user's clicks, impressions, average position and the real
 * search queries their visitors typed.
 *
 * These tests read the schema, not the database. A schema that is wrong here is
 * wrong everywhere it is applied.
 */

const SQL = readFileSync(new URL("../supabase-schema.sql", import.meta.url), "utf8");

/** Strip SQL comments so the write-up of a fixed bug is not read as the bug. */
const CODE = SQL.replace(/^\s*--.*$/gm, "");

/** Tables declared in this schema, with whether they carry a user_id column. */
function tables() {
  const out = new Map();
  const re = /create table if not exists public\.(\w+)\s*\(([\s\S]*?)\n\);/g;
  let m;
  while ((m = re.exec(CODE))) out.set(m[1], /\buser_id\s+uuid/.test(m[2]));
  return out;
}

function policies() {
  const out = [];
  const re = /create policy (\w+) on public\.(\w+)\s*\n?\s*for (\w+)([\s\S]*?);/g;
  let m;
  while ((m = re.exec(CODE))) out.push({ name: m[1], table: m[2], cmd: m[3], body: m[4] });
  return out;
}

test("every table that has a user_id enables row level security", () => {
  for (const [name, hasUserId] of tables()) {
    if (!hasUserId) continue;
    assert.ok(
      new RegExp(`alter table public\\.${name}\\s+enable row level security`).test(CODE),
      `${name} carries per-user data with RLS off; the public anon key reads it all`,
    );
  }
});

test("every table that has a user_id has a policy", () => {
  const withPolicy = new Set(policies().map((p) => p.table));
  for (const [name, hasUserId] of tables()) {
    if (!hasUserId) continue;
    assert.ok(withPolicy.has(name), `${name} has RLS on and no policy, so nobody can read it`);
  }
});

test("no policy grants rows it has not checked ownership of", () => {
  // The B-091 shape. `using (true)` on a table with a user_id column is not a
  // relaxed policy, it is no policy, and the name says "owner".
  const bad = policies().filter((p) => /using\s*\(\s*true\s*\)/.test(p.body));
  assert.deepEqual(
    bad.map((p) => `${p.table}.${p.name}`), [],
    "a policy on a per-user table returns every row to every caller",
  );
});

test("every policy on a per-user table keys off auth.uid()", () => {
  const t = tables();
  for (const p of policies()) {
    if (!t.get(p.table)) continue;
    assert.match(
      p.body, /auth\.uid\(\)\s*=\s*user_id/,
      `${p.table}.${p.name} does not compare auth.uid() to user_id`,
    );
  }
});

test("a write policy checks the row it is about to write", () => {
  // `using` filters what you can see; `with check` is what stops you writing a
  // row owned by somebody else. A policy with only `using` lets a caller insert
  // rows under another user's id.
  for (const p of policies()) {
    if (!tables().get(p.table)) continue;
    if (p.cmd !== "all" && !/insert|update/.test(p.cmd)) continue;
    assert.match(p.body, /with check\s*\(\s*auth\.uid\(\)\s*=\s*user_id\s*\)/,
      `${p.table}.${p.name} can see only its own rows but can write rows owned by anyone`);
  }
});

test("user_id is not nullable on a table whose policy compares it", () => {
  // A null user_id is a row nobody owns. All 170 traffic_snapshots rows had one,
  // which is how they became unattributable orphans that no user could see and
  // the anon key could read.
  const re = /create table if not exists public\.(\w+)\s*\(([\s\S]*?)\n\);/g;
  const nullable = [];
  let m;
  while ((m = re.exec(CODE))) {
    const [, name, body] = m;
    const col = body.split("\n").find((l) => /^\s*user_id\s+uuid/.test(l));
    if (!col) continue;
    const altered = new RegExp(`alter table public\\.${name}[\\s\\S]{0,120}?alter column user_id set not null`).test(CODE);
    if (!/not null/.test(col) && !altered) nullable.push(name);
  }
  assert.deepEqual(nullable, [], "a nullable user_id produces rows no policy can match");
});

test("views that join per-user tables run as the caller", () => {
  // A Postgres view runs as its OWNER by default, which silently bypasses the
  // RLS on everything it selects from. `security_invoker` is what keeps the
  // caller's policies applied.
  const re = /create or replace view public\.(\w+)([\s\S]*?)\sas\s/g;
  let m;
  while ((m = re.exec(CODE))) {
    assert.match(m[2], /security_invoker\s*=\s*true/,
      `view ${m[1]} runs as its owner and bypasses RLS on every table it reads`);
  }
});
