import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const {
  safeReturnPath, safeService, newStateNonce, nonceMatches, oauthCookie,
  PRIMARY_COOKIES, SECONDARY_COOKIES, FLOW_COOKIES,
} = await import("../lib/oauthCookies.ts");

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
/** Source with comments removed. These files DOCUMENT the strings they no longer
 *  contain, so a grep over the raw text matches the explanation and reports the
 *  defect as still present. */
const code = (f) => read(f).replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
const START = read("app/api/auth/google/route.ts");
const START_CODE = code("app/api/auth/google/route.ts");
const CALLBACK = read("app/api/auth/google/callback/route.ts");
const CALLBACK_CODE = code("app/api/auth/google/callback/route.ts");
const SAVE = read("app/api/auth/google/save-token/route.ts");
const STATUS_CODE = code("app/api/auth/google/status/route.ts");

/* ── the redirect target ─────────────────────────────────────────────────── */

test("only a plainly local path is an acceptable return destination", () => {
  for (const good of ["/profile", "/local-seo?x=1", "/a/b#c"]) {
    assert.equal(safeReturnPath(good), good);
  }
});

test("nothing that can change the host survives", () => {
  // Each of these was reachable: `destination` came out of the attacker-writable
  // half of `state` and was interpolated as `${origin}${destination}`.
  const attacks = [
    "@evil.com",              // https://app.example.com@evil.com -> host evil.com
    "//evil.com",             // protocol-relative
    "/\\evil.com",            // browsers read \\ as //
    "https://evil.com",
    "javascript:alert(1)",
    "/a\\b",
    "/x\r\nSet-Cookie: a=b",
    "",
  ];
  for (const bad of attacks) {
    assert.equal(safeReturnPath(bad), null, `must refuse: ${JSON.stringify(bad)}`);
  }
});

test("the flow never bounces back into itself", () => {
  assert.equal(safeReturnPath("/api/auth/google"), null);
});

test("a non-string or oversized path is refused rather than coerced", () => {
  for (const bad of [null, undefined, 42, {}, "/" + "a".repeat(600)]) {
    assert.equal(safeReturnPath(bad), null);
  }
});

test("the service is one of two values, whatever the query says", () => {
  assert.equal(safeService("gbp_secondary"), "gbp_secondary");
  for (const other of ["unified", "", null, undefined, "../admin", "GBP_SECONDARY"]) {
    assert.equal(safeService(other), "unified");
  }
});

/* ── the nonce ───────────────────────────────────────────────────────────── */

test("the nonce is 256 bits of hex and never repeats", () => {
  const seen = new Set();
  for (let i = 0; i < 200; i++) {
    const n = newStateNonce();
    assert.match(n, /^[0-9a-f]{64}$/);
    assert.ok(!seen.has(n), "a repeated nonce is not a nonce");
    seen.add(n);
  }
});

test("a missing, short or wrong nonce never matches", () => {
  const n = newStateNonce();
  assert.equal(nonceMatches(n, n), true);
  assert.equal(nonceMatches(n, undefined), false);
  assert.equal(nonceMatches(undefined, n), false);
  assert.equal(nonceMatches("", ""), false, "two empties must not read as a match");
  assert.equal(nonceMatches(n, n.slice(0, -1)), false);
  assert.equal(nonceMatches(n, "f".repeat(64)), false);
});

/* ── the cookies ─────────────────────────────────────────────────────────── */

test("every OAuth cookie is httpOnly, and it is not a parameter", () => {
  const opts = oauthCookie(60);
  assert.equal(opts.httpOnly, true);
  assert.equal(opts.path, "/");
  assert.equal(opts.sameSite, "lax");
  assert.equal(opts.maxAge, 60);
  assert.equal(oauthCookie.length, 1, "httpOnly must not be an argument any caller can flip");
});

test("no route sets an OAuth cookie outside the policy", () => {
  // `gsc_access_token` and `gbp_secondary_access_token` are bearer credentials
  // for a client's Search Console and Business Profile. They were readable by
  // any script on the page.
  for (const [name, src] of [["callback", CALLBACK], ["start", START], ["save-token", SAVE]]) {
    assert.ok(!/httpOnly:\s*false/.test(src), `${name}: an OAuth cookie is exposed to page script`);
    const sets = src.match(/cookieStore\.set\(/g) ?? [];
    const policy = src.match(/oauthCookie\(/g) ?? [];
    assert.equal(sets.length, policy.length,
      `${name}: ${sets.length} cookie writes but ${policy.length} go through oauthCookie`);
  }
});

test("disconnect clears every cookie the flow can set", () => {
  const all = [...PRIMARY_COOKIES, ...SECONDARY_COOKIES, ...FLOW_COOKIES];
  assert.ok(all.includes("gsc_refresh_token"), "the refresh token outlives the access token; it must be listed");
  assert.equal(new Set(all).size, all.length, "a duplicated name means one list is drifting");
  for (const name of ["gsc_access_token", "gbp_secondary_access_token", "google_oauth_state"]) {
    assert.ok(all.includes(name), `${name} would survive a disconnect`);
  }
});

/* ── the flow ────────────────────────────────────────────────────────────── */

test("state carries the nonce and nothing an attacker can act on", () => {
  assert.ok(/searchParams\.set\("state", nonce\)/.test(START),
    "state must be the nonce alone; service and returnTo belong in httpOnly cookies");
  assert.ok(!/:::/.test(START_CODE) && !/:::/.test(CALLBACK_CODE),
    "the old service:::returnTo state encoding is gone");
});

test("the callback refuses before spending the authorization code", () => {
  const nonceAt = CALLBACK.indexOf("nonceMatches(");
  const exchangeAt = CALLBACK.indexOf("oauth2.googleapis.com/token");
  assert.ok(nonceAt !== -1 && nonceAt < exchangeAt,
    "check the state before the token exchange, not after");
  assert.match(CALLBACK, /state_mismatch/);
});

test("the callback reads the destination from our cookie, never from the URL", () => {
  assert.ok(!/searchParams\.get\("state"\)[\s\S]{0,200}decodeURIComponent/.test(CALLBACK));
  assert.ok(/cookieStore\.get\("google_auth_return_to"\)/.test(CALLBACK));
  assert.ok(/safeReturnPath\(/.test(CALLBACK), "the cookie value is still validated");
});

test("the nonce is single-use", () => {
  assert.ok(/for \(const c of FLOW_COOKIES\) cookieStore\.delete\(c\)/.test(CALLBACK),
    "flow cookies must be cleared so a callback cannot be replayed");
});

/* ── save-token was open to the internet ─────────────────────────────────── */

test("manual credential entry requires a signed-in operator, same origin, rate limited", () => {
  // `save_credentials` writes this deployment's OAuth client secret. Anyone able
  // to POST could point the next Connect click at their own OAuth app.
  const authAt = SAVE.indexOf("authenticateRequest");
  const writeAt = SAVE.indexOf("cookieStore.set(");
  assert.ok(authAt !== -1 && authAt < writeAt, "authenticate before writing any cookie");
  assert.ok(/sameOriginPost\(request\)/.test(SAVE), "a cookie-authenticated POST needs a CSRF answer");
  assert.ok(/checkRateLimit\(/.test(SAVE));
  assert.ok(/readJsonBodyWithLimit/.test(SAVE), "an unbounded JSON body is a free memory spike");
});

test("Google's error body is not echoed back to the caller", () => {
  assert.ok(!/await\s+testRes\.text\(\)/.test(SAVE),
    "echoing Google's response makes this route a token-probing oracle");
});

/* ── the status route states only what it knows ──────────────────────────── */

test("an account with no email shows no email", () => {
  assert.ok(!/connected@google\.account/.test(STATUS_CODE),
    "a placeholder address is indistinguishable from a real one to the operator");
});

test("locations are not claimed by a route that never asked", () => {
  assert.ok(!/hasLocations:\s*true/.test(STATUS_CODE));
  assert.match(STATUS_CODE, /hasLocations:\s*null/);
});
