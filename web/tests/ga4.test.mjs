import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * GA4 and the Google token refresh.
 *
 * The sign-in asked for Analytics permission and the status route called any
 * connection "analytics connected", yet nothing read GA4. And no route ever
 * used the refresh token, so every Google read died an hour after connecting.
 */

const G = await import("../lib/ga4.ts");
const T = await import("../lib/googleToken.ts");
const src = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

function fakeFetch(routes) {
  const calls = [];
  const impl = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    for (const [pattern, reply] of routes) {
      if (String(url).includes(pattern)) {
        const { status = 200, body } = typeof reply === "function" ? reply(String(url), init) : reply;
        return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      }
    }
    return new Response("{}", { status: 404 });
  };
  return { impl, calls };
}

const SUMMARIES = {
  accountSummaries: [
    {
      account: "accounts/1", displayName: "Orienda",
      propertySummaries: [
        { property: "properties/111", displayName: "Hospital site" },
        { property: "properties/222", displayName: "Old blog" },
      ],
    },
  ],
};

test("properties are listed and matched to the project by web stream, www or not", async () => {
  const { impl } = fakeFetch([
    ["accountSummaries", { body: SUMMARIES }],
    ["properties/111/dataStreams", { body: { dataStreams: [{ type: "WEB_DATA_STREAM", webStreamData: { defaultUri: "https://www.oriendainternationalhospital.com.kh" } }] } }],
    ["properties/222/dataStreams", { body: { dataStreams: [{ type: "WEB_DATA_STREAM", webStreamData: { defaultUri: "https://blog.example.com" } }] } }],
  ]);
  const r = await G.listGa4Properties("tok", "oriendainternationalhospital.com.kh", impl);
  assert.equal(r.ok, true);
  assert.deepEqual(r.properties.map((p) => p.id), ["111", "222"]);
  assert.equal(r.matchedId, "111");
});

test("no matching stream means no property chosen, never a guess from the display name", async () => {
  const { impl } = fakeFetch([
    ["accountSummaries", { body: { accountSummaries: [{ displayName: "A", propertySummaries: [{ property: "properties/9", displayName: "oriendainternationalhospital.com.kh" }] }] } }],
    ["dataStreams", { body: { dataStreams: [] } }],
  ]);
  const r = await G.listGa4Properties("tok", "oriendainternationalhospital.com.kh", impl);
  assert.equal(r.ok, true);
  assert.equal(r.matchedId, null);
});

test("Google's refusals become one actionable sentence, not Google's body", async () => {
  const disabled = { error: { code: 403, status: "PERMISSION_DENIED", message: "Google Analytics Admin API has not been used in project 734214844525", details: [{ reason: "SERVICE_DISABLED" }] } };
  const { impl } = fakeFetch([["accountSummaries", { status: 403, body: disabled }]]);
  const r = await G.listGa4Properties("tok", "x.com", impl);
  assert.equal(r.ok, false);
  assert.match(r.error, /Admin API is not enabled/);
  assert.doesNotMatch(r.error, /734214844525/);

  const scope = { error: { status: "PERMISSION_DENIED", details: [{ reason: "ACCESS_TOKEN_SCOPE_INSUFFICIENT" }] } };
  assert.match(G.ga4ErrorMessage(403, scope, "Google Analytics Data API"), /tick the Google Analytics box/);
  assert.match(G.ga4ErrorMessage(401, null, "Google Analytics Data API"), /Connect Google again/);
  assert.match(G.ga4ErrorMessage(403, null, "Google Analytics Data API"), /no access to that GA4 property/);
});

const BATCH = {
  reports: [
    { metricHeaders: ["activeUsers", "newUsers", "sessions", "engagedSessions", "engagementRate", "screenPageViews", "keyEvents"].map((name) => ({ name })),
      rows: [{ metricValues: ["812", "640", "1034", "577", "0.558", "2210", "31"].map((value) => ({ value })) }] },
    { dimensionHeaders: [{ name: "date" }], metricHeaders: [{ name: "activeUsers" }, { name: "sessions" }],
      rows: [{ dimensionValues: [{ value: "20260913" }], metricValues: [{ value: "30" }, { value: "41" }] }] },
    { dimensionHeaders: [{ name: "sessionDefaultChannelGroup" }], metricHeaders: ["sessions", "activeUsers", "engagementRate", "keyEvents"].map((name) => ({ name })),
      rows: [{ dimensionValues: [{ value: "Organic Search" }], metricValues: ["600", "480", "0.61", "20"].map((value) => ({ value })) }] },
    { dimensionHeaders: [{ name: "landingPagePlusQueryString" }], metricHeaders: [{ name: "sessions" }], rows: [] },
    {},
  ],
};

test("a batch report parses into totals, a dated series and rows with numbers", async () => {
  const { impl, calls } = fakeFetch([[":batchRunReports", { body: BATCH }]]);
  const r = await G.runGa4Report("tok", "111", 28, impl);
  assert.equal(r.ok, true);
  assert.equal(r.totals.activeUsers, 812);
  assert.equal(r.totals.engagementRate, 0.558);
  assert.equal(r.totals.keyEvents, 31);
  assert.deepEqual(r.daily[0], { date: "2026-09-13", activeUsers: 30, sessions: 41 });
  assert.equal(r.channels[0].sessionDefaultChannelGroup, "Organic Search");
  assert.equal(r.channels[0].sessions, 600);
  assert.deepEqual(r.landingPages, []);
  assert.deepEqual(r.organicLandingPages, []);
  assert.match(calls[0].url, /properties\/111:batchRunReports$/);
  const sent = JSON.parse(calls[0].init.body);
  assert.equal(sent.requests.length, 5, "GA4 batchRunReports accepts at most 5");
  assert.equal(sent.requests[4].dimensionFilter.filter.stringFilter.value, "Organic Search");
  assert.equal(calls[0].init.headers.Authorization, "Bearer tok");
});

test("an empty GA4 report is zeros, not an error", () => {
  const r = G.parseBatch({ reports: [{}, {}, {}, {}, {}] }, "1", 28);
  assert.equal(r.totals.sessions, 0);
  assert.deepEqual(r.daily, []);
});

/* ── token refresh ─────────────────────────────────────────────────────── */

test("a token is refreshed when expired or when its expiry was never recorded", () => {
  const now = 1_000_000_000_000;
  assert.equal(T.needsRefresh(0, now), true);
  assert.equal(T.needsRefresh(NaN, now), true);
  assert.equal(T.needsRefresh(now + 30_000, now), true, "inside the skew window");
  assert.equal(T.needsRefresh(now + 10 * 60_000, now), false);
});

test("a refresh exchanges the refresh token and reports the new expiry", async () => {
  const now = 1_000_000_000_000;
  const { impl, calls } = fakeFetch([["oauth2.googleapis.com/token", { body: { access_token: "new", expires_in: 3599 } }]]);
  const r = await T.refreshAccessToken("1//r", "id", "secret", impl, now);
  assert.deepEqual(r, { ok: true, accessToken: "new", expiresAt: now + 3599_000 });
  const form = new URLSearchParams(String(calls[0].init.body));
  assert.equal(form.get("grant_type"), "refresh_token");
  assert.equal(form.get("refresh_token"), "1//r");
});

test("a revoked refresh token is a failure the caller can fall back from, not a throw", async () => {
  const { impl } = fakeFetch([["oauth2.googleapis.com/token", { status: 400, body: { error: "invalid_grant" } }]]);
  assert.deepEqual(await T.refreshAccessToken("1//r", "id", "secret", impl), { ok: false, error: "invalid_grant" });
  assert.equal((await T.refreshAccessToken("", "id", "secret", impl)).ok, false);
  assert.equal((await T.refreshAccessToken("1//r", "", "", impl)).ok, false);
});

test("googleSession refreshes only an owned connection, and the callback records expiry", () => {
  const session = src("lib/googleSession.ts");
  const owned = session.slice(session.lastIndexOf("} else if (owner !== auth.user.id)"));
  assert.match(owned, /liveToken\(jar, PRIMARY_TOKEN, gscToken\)/);
  assert.ok(session.indexOf("liveToken(jar, PRIMARY_TOKEN") > session.indexOf('return { state: "foreign"'),
    "refresh must come after the ownership checks");
  const cb = src("app/api/auth/google/callback/route.ts");
  assert.match(cb, /"gsc_token_expires_at", expiresAt/);
  assert.match(cb, /"gbp_secondary_token_expires_at", expiresAt/);
  const pasted = src("app/api/auth/google/save-token/route.ts");
  assert.match(pasted, /delete\("gsc_refresh_token"\)/, "a pasted token must not be refreshed into an older connection's account");
});

test("the status route probes Analytics instead of assuming it, and GA4 is on the dashboard", () => {
  const status = src("app/api/auth/google/status/route.ts");
  assert.doesNotMatch(status, /connected: Boolean\(token\),\s*\n\s*}/);
  assert.match(status, /analyticsadmin\.googleapis\.com/);
  const dash = src("app/ReaiDashboard.tsx");
  assert.match(dash, /gsc: "ga4-overview"/);
  assert.match(dash, /const GA4_VIEW_ID = "ga4-overview"/);
  assert.match(dash, /<Ga4Panel domain=\{currentDomain\}/);
  for (const r of ["app/api/ga4/properties/route.ts", "app/api/ga4/report/route.ts"]) {
    assert.match(src(r), /googleSession\(request\)/, `${r} must resolve whose token it is`);
  }
  assert.match(src("components/dashboard/Ga4Panel.tsx"), /authedFetch\(/);
});
