#!/usr/bin/env node
/**
 * Is the live database what `supabase-schema.sql` says it is?
 *
 * "I think there are a lot more migrations to run" is a question nobody should
 * have to guess at, and the honest answer is usually narrower than the fear.
 * This compares, table by table and column by column, and it also probes RLS
 * from OUTSIDE with the public anon key - which is the only test that would
 * have caught B-091, where the policy existed, was named "owner", and granted
 * every row to everybody.
 *
 *   node scripts/db-check.mjs
 *
 * Exit 0 in sync · 1 drift found · 2 could not check.
 *
 * Read-only. It never writes and never runs DDL.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");

function env() {
  const out = {};
  for (const f of [".env.local", ".env"]) {
    try {
      for (const line of readFileSync(join(root, f), "utf8").split("\n")) {
        const m = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim());
        if (m && !out[m[1]]) out[m[1]] = m[2].trim().replace(/^["']|["']$/g, "");
      }
    } catch { /* absent is fine */ }
  }
  return out;
}

const E = env();
const URL_ = E.NEXT_PUBLIC_SUPABASE_URL;
const ANON = E.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const SVC = E.SUPABASE_SERVICE_ROLE_KEY;

if (!URL_ || !ANON || !SVC) {
  console.error("db-check: need NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY.");
  process.exit(2);
}

const head = (key, extra = {}) => ({ apikey: key, Authorization: `Bearer ${key}`, ...extra });

/** Columns the schema file declares, per table, including later ALTER ADDs. */
function declared() {
  const sql = readFileSync(join(root, "supabase-schema.sql"), "utf8");
  const tables = new Map();
  for (const m of sql.matchAll(/create table if not exists public\.(\w+)\s*\(([\s\S]*?)\n\);/g)) {
    const cols = new Set();
    for (const line of m[2].split("\n")) {
      const c = /^\s*(\w+)\s+(uuid|text|int|integer|numeric|jsonb|boolean|timestamptz|bigint|real|double)/.exec(line);
      if (c) cols.add(c[1]);
    }
    tables.set(m[1], cols);
  }
  for (const m of sql.matchAll(/alter table public\.(\w+)\s+add column if not exists (\w+)/g)) {
    tables.get(m[1])?.add(m[2]);
  }
  return tables;
}

async function liveColumns() {
  const res = await fetch(`${URL_}/rest/v1/`, {
    headers: head(SVC, { Accept: "application/openapi+json" }),
  });
  if (!res.ok) throw new Error(`schema read failed: HTTP ${res.status}`);
  const spec = await res.json();
  const out = new Map();
  for (const [name, def] of Object.entries(spec.definitions || {})) {
    out.set(name, new Set(Object.keys(def.properties || {})));
  }
  return out;
}

/** What the PUBLIC key can read. Anything above zero on a per-user table is a leak. */
async function anonRowCount(table) {
  const res = await fetch(`${URL_}/rest/v1/${table}?select=*&limit=1`, {
    headers: head(ANON, { Prefer: "count=exact" }),
  });
  if (!res.ok) return null;
  const m = /\/(\d+|\*)$/.exec(res.headers.get("content-range") || "");
  return m ? (m[1] === "*" ? 0 : Number(m[1])) : null;
}

const want = declared();
let live;
try {
  live = await liveColumns();
} catch (e) {
  console.error(`db-check: ${e.message}`);
  process.exit(2);
}

const problems = [];
console.log("TABLE                  SCHEMA      ANON READ");
for (const [table, cols] of [...want].sort()) {
  if (!live.has(table)) {
    problems.push(`${table}: table is missing from the database`);
    console.log(`${table.padEnd(22)} MISSING`);
    continue;
  }
  const gap = [...cols].filter((c) => !live.get(table).has(c));
  const anon = cols.has("user_id") ? await anonRowCount(table) : null;
  if (gap.length) problems.push(`${table}: missing column(s) ${gap.join(", ")}`);
  if (anon !== null && anon > 0) {
    problems.push(
      `${table}: the PUBLIC anon key reads ${anon} row(s) - RLS is not protecting a per-user table`,
    );
  }
  const anonCell = anon === null ? "n/a" : anon > 0 ? `${anon} ROWS - LEAK` : "0 (ok)";
  console.log(`${table.padEnd(22)} ${(gap.length ? `MISSING ${gap.length} COL` : "ok").padEnd(11)} ${anonCell}`);
}

console.log("");
if (problems.length === 0) {
  console.log("In sync. No migrations outstanding.");
  process.exit(0);
}
console.log(`${problems.length} problem(s):`);
for (const p of problems) console.log(`  - ${p}`);
console.log("\nApply the files in web/migrations/ through the Supabase SQL editor, then re-run.");
process.exit(1);
