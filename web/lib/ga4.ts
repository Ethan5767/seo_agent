/**
 * Google Analytics 4, read from the operator's own connected account.
 *
 * The sign-in has asked for `analytics.readonly` since the Google connection was
 * built, and `/api/auth/google/status` reported `analytics.connected: true` for
 * any connected account, but nothing ever called an Analytics API. This module
 * is that missing half: list the GA4 properties the account can see, pick the
 * one whose web stream is the project's domain, and read a 28-day report.
 *
 * Pure parsers plus fetchers that take the token and a `fetch`, so all of it is
 * tested with recorded Google responses and no network.
 */

const ADMIN = "https://analyticsadmin.googleapis.com/v1beta";
const DATA = "https://analyticsdata.googleapis.com/v1beta";

/** Data streams are read for at most this many properties when matching a domain. */
export const MAX_STREAM_LOOKUPS = 25;

export type Ga4Property = {
  /** Numeric id, e.g. "123456789". */
  id: string;
  displayName: string;
  account: string;
  /** Web stream URLs, when read. */
  webUris: string[];
};

export type Ga4Failure = { ok: false; status: number; error: string };

export type Ga4Totals = {
  activeUsers: number;
  newUsers: number;
  sessions: number;
  engagedSessions: number;
  engagementRate: number;
  screenPageViews: number;
  keyEvents: number;
};

export type Ga4Row = Record<string, string | number>;

export type Ga4Report = {
  propertyId: string;
  startDate: string;
  endDate: string;
  totals: Ga4Totals;
  daily: Ga4Row[];
  channels: Ga4Row[];
  landingPages: Ga4Row[];
  organicLandingPages: Ga4Row[];
};

const TOTAL_METRICS = [
  "activeUsers", "newUsers", "sessions", "engagedSessions", "engagementRate", "screenPageViews", "keyEvents",
] as const;
const ROW_METRICS = ["sessions", "activeUsers", "engagementRate", "keyEvents"];

/* ── errors ─────────────────────────────────────────────────────────────── */

/**
 * One actionable sentence for a failed Google call.
 *
 * Google's body is not passed through (it can name accounts and properties);
 * only its machine-readable reason is used to pick what the operator must do.
 */
export function ga4ErrorMessage(status: number, doc: any, api: "Google Analytics Admin API" | "Google Analytics Data API"): string {
  const reasons: string[] = (doc?.error?.details || []).map((d: any) => d?.reason).filter(Boolean);
  const gstatus = doc?.error?.status || "";
  if (reasons.includes("SERVICE_DISABLED") || reasons.includes("API_KEY_SERVICE_BLOCKED")) {
    return `${api} is not enabled in the Google Cloud project. Enable it in APIs & Services → Library, wait a few minutes, then reload.`;
  }
  if (reasons.includes("ACCESS_TOKEN_SCOPE_INSUFFICIENT") || (gstatus === "PERMISSION_DENIED" && /scope/i.test(doc?.error?.message || ""))) {
    return "This Google connection has no Analytics permission. Connect Google again and tick the Google Analytics box.";
  }
  if (status === 401) return "The Google connection expired. Connect Google again.";
  if (status === 403) return "This Google account has no access to that GA4 property.";
  if (status === 429) return "Google Analytics quota reached for now. Try again in a few minutes.";
  return `${api} returned HTTP ${status}.`;
}

async function getJson(fetchImpl: typeof fetch, url: string, token: string, init: RequestInit = {}) {
  const res = await fetchImpl(url, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(init.headers || {}) },
    cache: "no-store",
    signal: AbortSignal.timeout(20_000),
  });
  let doc: any = null;
  try {
    doc = await res.json();
  } catch {
    doc = null;
  }
  return { ok: res.ok, status: res.status, doc };
}

/* ── properties ─────────────────────────────────────────────────────────── */

export function parseAccountSummaries(doc: any): Ga4Property[] {
  const out: Ga4Property[] = [];
  for (const acc of doc?.accountSummaries || []) {
    for (const p of acc?.propertySummaries || []) {
      const id = String(p?.property || "").replace(/^properties\//, "");
      if (!/^\d+$/.test(id)) continue;
      out.push({ id, displayName: p.displayName || id, account: acc.displayName || "", webUris: [] });
    }
  }
  return out;
}

export function parseWebUris(doc: any): string[] {
  return (doc?.dataStreams || [])
    .map((s: any) => s?.webStreamData?.defaultUri)
    .filter((u: unknown): u is string => typeof u === "string" && u.length > 0);
}

export function hostOf(urlOrDomain: string): string {
  return String(urlOrDomain || "")
    .trim()
    .toLowerCase()
    .replace(/^[a-z]+:\/\//, "")
    .replace(/[/?#:].*$/, "")
    .replace(/^www\./, "");
}

/** The property whose web stream is this domain (www or not), or null. Never a guess. */
export function matchProperty(properties: Ga4Property[], domain: string): Ga4Property | null {
  const want = hostOf(domain);
  if (!want) return null;
  return properties.find((p) => p.webUris.some((u) => hostOf(u) === want)) || null;
}

export async function listGa4Properties(
  token: string,
  domain: string,
  fetchImpl: typeof fetch = fetch,
): Promise<{ ok: true; properties: Ga4Property[]; matchedId: string | null } | Ga4Failure> {
  const properties: Ga4Property[] = [];
  let pageToken = "";
  for (let page = 0; page < 10; page++) {
    const url = `${ADMIN}/accountSummaries?pageSize=200${pageToken ? `&pageToken=${encodeURIComponent(pageToken)}` : ""}`;
    const r = await getJson(fetchImpl, url, token);
    if (!r.ok) return { ok: false, status: r.status, error: ga4ErrorMessage(r.status, r.doc, "Google Analytics Admin API") };
    properties.push(...parseAccountSummaries(r.doc));
    pageToken = r.doc?.nextPageToken || "";
    if (!pageToken) break;
  }

  // Streams are what tie a property to a site; the display name is free text.
  await Promise.all(
    properties.slice(0, MAX_STREAM_LOOKUPS).map(async (p) => {
      const r = await getJson(fetchImpl, `${ADMIN}/properties/${p.id}/dataStreams?pageSize=50`, token);
      if (r.ok) p.webUris = parseWebUris(r.doc);
    }),
  );

  return { ok: true, properties, matchedId: domain ? matchProperty(properties, domain)?.id ?? null : null };
}

/* ── report ─────────────────────────────────────────────────────────────── */

export function reportRequests(days: number) {
  const dateRanges = [{ startDate: `${days}daysAgo`, endDate: "yesterday" }];
  const metric = (names: readonly string[]) => names.map((name) => ({ name }));
  const bySessions = [{ metric: { metricName: "sessions" }, desc: true }];
  return [
    { dateRanges, metrics: metric(TOTAL_METRICS) },
    { dateRanges, dimensions: [{ name: "date" }], metrics: metric(["activeUsers", "sessions"]), orderBys: [{ dimension: { dimensionName: "date" } }] },
    { dateRanges, dimensions: [{ name: "sessionDefaultChannelGroup" }], metrics: metric(ROW_METRICS), orderBys: bySessions, limit: 20 },
    { dateRanges, dimensions: [{ name: "landingPagePlusQueryString" }], metrics: metric(ROW_METRICS), orderBys: bySessions, limit: 25 },
    {
      dateRanges,
      dimensions: [{ name: "landingPagePlusQueryString" }],
      metrics: metric(ROW_METRICS),
      dimensionFilter: { filter: { fieldName: "sessionDefaultChannelGroup", stringFilter: { value: "Organic Search" } } },
      orderBys: bySessions,
      limit: 25,
    },
  ];
}

/** One GA4 report as rows keyed by header name; metrics are numbers. */
export function parseReport(report: any): Ga4Row[] {
  const dims: string[] = (report?.dimensionHeaders || []).map((h: any) => h.name);
  const mets: string[] = (report?.metricHeaders || []).map((h: any) => h.name);
  return (report?.rows || []).map((row: any) => {
    const out: Ga4Row = {};
    dims.forEach((d, i) => { out[d] = row?.dimensionValues?.[i]?.value ?? ""; });
    mets.forEach((m, i) => {
      const n = Number(row?.metricValues?.[i]?.value);
      out[m] = Number.isFinite(n) ? n : 0;
    });
    return out;
  });
}

/** "20260914" -> "2026-09-14". */
export function isoDate(yyyymmdd: string): string {
  return /^\d{8}$/.test(yyyymmdd) ? `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6, 8)}` : yyyymmdd;
}

export function parseBatch(doc: any, propertyId: string, days: number, now = Date.now()): Ga4Report {
  const reports = doc?.reports || [];
  const totalsRow = parseReport(reports[0])[0] || {};
  const totals = Object.fromEntries(TOTAL_METRICS.map((m) => [m, Number(totalsRow[m]) || 0])) as Ga4Totals;
  const day = 24 * 3600 * 1000;
  return {
    propertyId,
    startDate: new Date(now - days * day).toISOString().slice(0, 10),
    endDate: new Date(now - day).toISOString().slice(0, 10),
    totals,
    daily: parseReport(reports[1]).map((r) => ({ ...r, date: isoDate(String(r.date)) })),
    channels: parseReport(reports[2]),
    landingPages: parseReport(reports[3]),
    organicLandingPages: parseReport(reports[4]),
  };
}

export async function runGa4Report(
  token: string,
  propertyId: string,
  days: number,
  fetchImpl: typeof fetch = fetch,
): Promise<({ ok: true } & Ga4Report) | Ga4Failure> {
  const r = await getJson(fetchImpl, `${DATA}/properties/${propertyId}:batchRunReports`, token, {
    method: "POST",
    body: JSON.stringify({ requests: reportRequests(days) }),
  });
  if (!r.ok) return { ok: false, status: r.status, error: ga4ErrorMessage(r.status, r.doc, "Google Analytics Data API") };
  return { ok: true, ...parseBatch(r.doc, propertyId, days) };
}
