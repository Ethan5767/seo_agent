/**
 * Google Business Profile as the Local source — free, first-party, owned.
 *
 * The Local/GBP audit is powered by DataForSEO's `business_data` (`gbp.*` rows:
 * rating, reviews, category, NAP, claimed), which is paid and never-run-live
 * here. When the operator has connected Google and the client's profile, the
 * GBP API gives the same signals for the profile they OWN, for free — and the
 * OAuth here is already scoped for it (`business.manage`).
 *
 * This is the data layer of that switch: turn a normalized GBP location (see
 * `gbp.normalizeLocation`) into the `gbp.*` local rows the Local view already
 * renders, and resolve which source to use (prefer Google when we have the
 * owned profile, else DataForSEO, else none). Screen wiring + provenance badge
 * are G3.
 *
 * Honest scope: the owned-location endpoint carries category, NAP, hours and
 * verification, but NOT rating/review count — those come from the GBP reviews
 * endpoint, which is per-project allowlist-gated (tracked separately). So a
 * GBP-sourced local read leaves reviews to DataForSEO / the allowlist and marks
 * `metrics.source = "gbp"` on the rows it does produce.
 */

import type { ReportRow } from "./priorities";

export type LocalSource = "gbp" | "dataforseo" | "none";

/** The subset of `normalizeLocation`'s output this reads. */
export interface GbpLocation {
  businessName?: string | null;
  primaryCategory?: string | null;
  phone?: string | null;
  address?: { street?: string | null; city?: string | null; state?: string | null; postalCode?: string | null } | null;
  regularHours?: unknown;
  verifiedOnGoogle?: boolean | null;
}

function row(code: string, what: string, severity: string, why: string, fix: string, detail = ""): ReportRow {
  return { code, what, why, fix, severity: severity as ReportRow["severity"], detail, metrics: { source: "gbp" } };
}

/**
 * A normalized GBP location -> `gbp.*` local rows: primary category, NAP
 * completeness, opening hours, and verification. Reviews are deliberately not
 * emitted here (owned endpoint does not carry them).
 */
export function gbpLocationToLocalRows(loc: GbpLocation | null | undefined): ReportRow[] {
  if (!loc) return [];
  const rows: ReportRow[] = [];

  const cat = loc.primaryCategory || "";
  rows.push(cat
    ? row("gbp.category", "Primary category", "ok", `Primary category: ${cat}.`, "passing", cat)
    : row("gbp.category", "Primary category", "warn", "No primary category set — the top local ranking factor.",
          "set the most accurate primary category"));

  const a = loc.address || {};
  const napParts = [loc.businessName, a.street, a.city, loc.phone].filter(Boolean).length;
  rows.push(napParts >= 4
    ? row("gbp.nap", "Name, address, phone", "ok", "Name, address and phone are all present on the profile.", "passing")
    : row("gbp.nap", "Name, address, phone", "warn", "The profile is missing part of its name, address or phone — NAP consistency drives local rank.",
          "complete the business name, full address and primary phone", `${napParts}/4 present`));

  const hasHours = Array.isArray((loc.regularHours as { length?: number })) ||
    Boolean(loc.regularHours && typeof loc.regularHours === "object");
  rows.push(hasHours
    ? row("gbp.hours", "Opening hours", "ok", "Opening hours are set on the profile.", "passing")
    : row("gbp.hours", "Opening hours", "warn", "No opening hours on the profile — they show directly in local results.",
          "add regular opening hours"));

  if (loc.verifiedOnGoogle === true) {
    rows.push(row("gbp.verified", "Verified", "ok", "The profile is verified with Google (Voice of Merchant).", "passing"));
  } else if (loc.verifiedOnGoogle === false) {
    rows.push(row("gbp.verified", "Verified", "warn", "The profile is not verified with Google, so you cannot fully manage it.",
                  "complete Google's verification for this profile"));
  }

  return rows;
}

/**
 * Prefer the owned Google Business Profile when we have it; fall back to the
 * DataForSEO `gbp.*` rows the scan produced; report `none` when neither ran.
 */
export function resolveLocalRows(opts: {
  gbpLocation?: GbpLocation | null;
  dfsRows?: ReportRow[] | null;
}): { rows: ReportRow[]; source: LocalSource } {
  const gbp = gbpLocationToLocalRows(opts.gbpLocation);
  if (gbp.length > 0) return { rows: gbp, source: "gbp" };
  const dfs = Array.isArray(opts.dfsRows) ? opts.dfsRows : [];
  if (dfs.length > 0) return { rows: dfs, source: "dataforseo" };
  return { rows: [], source: "none" };
}

export function localSourceLabel(source: LocalSource): string {
  return source === "gbp" ? "Google Business Profile"
    : source === "dataforseo" ? "DataForSEO"
    : "Not connected";
}
