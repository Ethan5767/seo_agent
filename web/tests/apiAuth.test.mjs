import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

/**
 * Every call to our own API carries the session. No exceptions, enforced here.
 *
 * This bug shipped three times before it was understood as a class:
 *
 *   ContentPanel      plain fetch → every content tool 401'd in production
 *   RepoPicker        plain fetch → "Unauthorized: Missing or invalid Supabase
 *                     authentication token", and no repositories listed
 *   13 more sites     found only by grepping for it
 *
 * The cause is structural, not careless. The Supabase session lives in
 * `localStorage`, so a bare `fetch` carries no identity and every route guarded
 * by `authenticateRequest` answers 401 — and 401 renders as an empty list, which
 * looks like "you have none" rather than "we did not ask properly".
 *
 * Patching call sites does not fix a class. This test does: a bare
 * `fetch("/api/…")` anywhere in client code fails the build, so the wrong thing
 * is no longer possible rather than merely currently absent.
 */
const root = new URL("../", import.meta.url);

function clientSources(dir) {
  const out = [];
  for (const e of readdirSync(new URL(dir + "/", root), { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name === ".next") continue;
    // app/api/** is server code: a route calling another service is not a
    // browser fetch and has no session to attach.
    if (`${dir}/${e.name}`.startsWith("app/api")) continue;
    if (e.isDirectory()) out.push(...clientSources(`${dir}/${e.name}`));
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(`${dir}/${e.name}`);
  }
  return out;
}

const SOURCES = [...clientSources("app"), ...clientSources("components")];
const read = (f) => readFileSync(new URL(f, root), "utf8");
const strip = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\{\/\*[\s\S]*?\*\/\}/g, "").replace(/^\s*\/\/.*$/gm, "");

test("no client code reaches our API with a bare fetch", () => {
  const offenders = [];
  for (const f of SOURCES) {
    strip(read(f)).split("\n").forEach((line, i) => {
      // `authedFetch(` also matches `fetch(`, so require a non-identifier before it.
      if (/(?<![A-Za-z])fetch\(\s*[`"']\/api\//.test(line)) {
        offenders.push(`${f}:${i + 1}  ${line.trim().slice(0, 80)}`);
      }
    });
  }
  assert.deepEqual(offenders, [],
    "a bare fetch to our own API sends no session, and the 401 renders as an empty screen");
});

test("authedFetch is the only thing that attaches the session", () => {
  const helper = strip(read("lib/authedFetch.ts"));
  assert.match(helper, /supabase\.auth\.getSession\(\)/);
  assert.match(helper, /Authorization/);
  // It must survive having no session: signed-out is a normal state, and the
  // route answers "sign in" rather than this throwing where nobody catches it.
  assert.match(helper, /catch/);
});

test("every route that authenticates is reached only through authedFetch", () => {
  // The pairing that matters: if a route guards with authenticateRequest, no
  // caller may skip the header. Asserted by construction via the first test;
  // this one proves the guard exists on the routes we depend on.
  for (const r of [
    "app/api/github/repos/route.ts",
    "app/api/content/generate/route.ts",
    "app/api/fix/advise/route.ts",
    "app/api/plan/route.ts",
  ]) {
    assert.match(strip(read(r)), /authenticateRequest/, `${r} has no auth guard`);
  }
});
