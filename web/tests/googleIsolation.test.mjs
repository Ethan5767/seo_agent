import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

/**
 * One operator's Google data must never reach another's session.
 *
 * The reported symptom: sign in with a different account, see the same
 * Search Console data. The cause was that the Google connection lived entirely
 * in cookies - which belong to a BROWSER, not to a signed-in user - while
 * sign-out cleared only the Supabase session and not one of the six routes
 * reading those cookies authenticated the caller.
 */

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
const code = (f) =>
  read(f).replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");

/** Every route that can reach a Google access token. */
const GOOGLE_ROUTES = [
  "app/api/auth/google/status/route.ts",
  "app/api/gsc/query/route.ts",
  "app/api/local-seo/business/route.ts",
  "app/api/local-seo/insights/route.ts",
  "app/api/local-seo/posts/route.ts",
  "app/api/local-seo/reviews/route.ts",
];

const TOKEN_COOKIES = ["gsc_access_token", "gsc_refresh_token", "gbp_secondary_access_token"];

/* ── the token is never read without knowing whose it is ─────────────────── */

test("no route reads a Google token cookie directly", () => {
  // Reading the jar is the bug. A route that does it has no idea whose token it
  // found, which is precisely how account B was served account A's properties.
  for (const f of GOOGLE_ROUTES) {
    const src = code(f);
    for (const c of TOKEN_COOKIES) {
      assert.ok(
        !new RegExp(`cookieStore\\.get\\(\\s*["']${c}|jar\\.get\\(\\s*["']${c}`).test(src),
        `${f} reads ${c} straight from the jar; use googleSession(request)`,
      );
    }
  }
});

test("every Google route resolves the caller before using a token", () => {
  for (const f of GOOGLE_ROUTES) {
    const src = code(f);
    const viaSession = /googleSession\(/.test(src);
    const viaGbp = /gbpContext\(\s*request\s*\)/.test(src);
    assert.ok(viaSession || viaGbp, `${f} never establishes whose connection this is`);
  }
});

test("gbpContext cannot be called without a request", () => {
  // It used to take no arguments and read the jar, so all four local-seo routes
  // inherited the leak from one function.
  const gbp = code("lib/gbp.ts");
  assert.match(gbp, /export async function gbpContext\(req: NextRequest\)/);
  assert.ok(!/const jar = await cookies\(\)/.test(gbp), "gbp.ts still reads the cookie jar itself");
  for (const f of GOOGLE_ROUTES.filter((x) => x.includes("local-seo"))) {
    assert.match(code(f), /gbpContext\(request\)/, `${f} must pass the request through`);
  }
});

/* ── ownership ───────────────────────────────────────────────────────────── */

const SESSION = code("lib/googleSession.ts");

test("a connection belonging to another account is deleted, not merely hidden", () => {
  // Hiding it leaves a live 30-day token in a browser its owner has walked away
  // from, waiting for them to sign back in.
  const foreign = SESSION.slice(SESSION.indexOf('owner !== auth.user.id'));
  assert.match(foreign, /delete\(name\)/, "a foreign connection must be cleared from the jar");
  assert.match(foreign, /state: "foreign"/);
});

test("an unauthenticated request reveals nothing and destroys nothing", () => {
  // Two failure modes to avoid at once: answering it (the leak), and treating it
  // as a foreign connection (a forgotten bearer would log the real owner out).
  const block = SESSION.slice(SESSION.indexOf("if (!auth.user)"), SESSION.indexOf("if (!connected)"));
  assert.match(block, /state: "unauthenticated"/);
  assert.ok(!/delete\(/.test(block), "a missing bearer must not disconnect the real owner");
});

test("tokens are returned only in the owned state", () => {
  const owned = SESSION.slice(SESSION.indexOf('state: "owned"'));
  assert.match(owned, /gscToken,/);
  for (const state of ["unauthenticated", "not_connected", "foreign"]) {
    const at = SESSION.indexOf(`state: "${state}"`);
    const line = SESSION.slice(at, SESSION.indexOf("\n", at) + 120);
    assert.ok(/EMPTY/.test(line) || !/gscToken:\s*[a-z]/.test(line),
      `${state} must not carry a token`);
  }
});

test("the owner marker is cleared along with the tokens", () => {
  const { ALL_GOOGLE_COOKIES } = { ALL_GOOGLE_COOKIES: null };
  // Asserted against the source rather than imported, because importing a module
  // that pulls in next/headers needs a request scope.
  assert.match(SESSION, /export const ALL_GOOGLE_COOKIES = \[\s*\n?\s*\.\.\.PRIMARY_COOKIES, \.\.\.SECONDARY_COOKIES, \.\.\.FLOW_COOKIES, OWNER_COOKIE,/);
});

/* ── the browser's half ──────────────────────────────────────────────────── */

test("signing out disconnects Google, before the session is torn down", () => {
  const auth = code("app/auth.tsx");
  const purgeAt = auth.indexOf("purgeGoogleConnection()");
  const signOutAt = auth.indexOf("supabase.auth.signOut()");
  assert.ok(purgeAt !== -1, "sign-out must purge the Google connection");
  assert.ok(purgeAt < signOutAt,
    "purge first: once setSession(null) renders the login screen nothing is left to await");
});

test("swapping accounts without signing out also purges", () => {
  // Not a hypothetical: another tab, a refresh onto a different account, or
  // signing in over a live session all replace the session without a sign-out.
  const auth = code("app/auth.tsx");
  const sub = auth.slice(auth.indexOf("onAuthStateChange"));
  assert.match(sub, /previous !== uid/);
  assert.match(sub, /purgeGoogleConnection\(\)/);
});

test("the purge clears the browser's own memory of the connection", () => {
  const helper = code("lib/authedFetch.ts");
  for (const k of ["reai_google_account", "reai_gsc_property", "reai_traffic_source"]) {
    assert.ok(helper.includes(k), `${k} survives sign-out into the next account`);
  }
  assert.match(helper, /removeItem/);
  assert.match(helper, /service=all/, "the server half must be cleared too");
});

test("a failed disconnect still clears the local half", () => {
  // Signing out with no network must not leave the previous account's property
  // selected and its email in the header.
  const helper = read("lib/authedFetch.ts");
  const body = helper.slice(helper.indexOf("export async function purgeGoogleConnection"));
  assert.equal((body.match(/try \{/g) || []).length, 2,
    "the network call and the localStorage clear need separate try blocks");
});

/* ── the client actually sends the session ───────────────────────────────── */

const CALLERS = [
  "app/ReaiDashboard.tsx",
  "app/integrations/google/page.tsx",
  "components/dashboard/GoogleServicesHub.tsx",
  "components/dashboard/LocalBusinessManager.tsx",
  "components/dashboard/GscPanel.tsx",
];

test("no client calls a Google route with a bare fetch", () => {
  // The session lives in localStorage, so a bare fetch carries no identity and
  // the route can only 401. Every one of these has to go through authedFetch.
  const bad = [];
  for (const f of CALLERS) {
    for (const line of code(f).split("\n")) {
      if (/\bfetch\(\s*["'`]\/api\/(gsc\/query|auth\/google\/status|local-seo\/)/.test(line)
          && !/authedFetch\(/.test(line)) {
        bad.push(`${f}: ${line.trim()}`);
      }
    }
  }
  assert.deepEqual(bad, [], "these reach a Google route without the caller's session");
});

test("authedFetch attaches the Supabase access token", () => {
  const helper = code("lib/authedFetch.ts");
  assert.match(helper, /supabase\.auth\.getSession\(\)/);
  assert.match(helper, /headers\.set\("Authorization", `Bearer \$\{token\}`\)/);
});

/* ── nothing else grew a copy of the hole ────────────────────────────────── */

function walk(dir) {
  const out = [];
  for (const e of readdirSync(new URL(`../${dir}`, import.meta.url), { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name === ".next") continue;
    if (e.isDirectory()) out.push(...walk(`${dir}/${e.name}`));
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(`${dir}/${e.name}`);
  }
  return out;
}

test("only googleSession and the OAuth writers touch the token cookies", () => {
  const allowed = new Set([
    "lib/googleSession.ts",
    "lib/oauthCookies.ts",
    "app/api/auth/google/callback/route.ts",
    "app/api/auth/google/save-token/route.ts",
  ]);
  const offenders = [];
  for (const f of [...walk("app"), ...walk("lib"), ...walk("components")]) {
    if (allowed.has(f)) continue;
    const src = code(f);
    for (const c of TOKEN_COOKIES) {
      if (src.includes(`"${c}"`)) offenders.push(`${f} -> ${c}`);
    }
  }
  assert.deepEqual(offenders, [],
    "a Google token cookie is named outside the session layer; that is how this bug happened");
});
