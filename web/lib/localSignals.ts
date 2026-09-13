/**
 * Local presence: what this product can actually check, and what it cannot.
 *
 * B-096. The Local screen was almost entirely invented. Six directory tiles read
 * `Google Maps Synced · Apple Maps Synced · Bing Places Synced · Waze Local
 * Synced · Yelp Biz Claimed · YellowPages Format Diff` with a `5/6 Verified
 * Active` badge above them - all literal strings. **Nothing in this codebase has
 * ever queried Apple Maps, Bing Places, Waze or YellowPages**, and for four of
 * the six there is no public API to query.
 *
 * Under it, the findings checklist fell back to six fabricated rows whenever
 * there were no real ones, including:
 *
 *     "4.8 / 5.0 rating across 184 Google reviews. 94% positive sentiment ratio."
 *     "Category: Medical Center / Hospital."
 *     "Sync telephone format with E.164 standardization (+855...)."
 *
 * A rating and a review count with no source is the exact claim
 * `claim_provenance_check` refuses on a client's site, printed by our own
 * dashboard. The category and the country code were one pilot client's, shown to
 * every account.
 *
 * THE HONEST MATRIX. Four of those six directories cannot be checked by anyone,
 * at any price, because they publish no read API:
 *
 *   Google Business Profile   CHECKABLE  - DataForSEO Business Data (paid), or
 *                                          Google's own API via OAuth (free,
 *                                          but Google must allowlist the app)
 *   Yelp                      BUILDABLE  - Yelp Fusion API, free tier, read
 *                                          only. Not built; needs a key.
 *   Bing Places               NO API     - management only, no public read
 *   Apple Business Connect    NO API     - management only, no public read
 *   Waze                      NO API     - listings come from Google data
 *   YellowPages               NO API     - scraping only, and unreliable
 *
 * Saying "no public API" is not a failure to report. It is the only honest thing
 * to say, and it stops an operator promising a client a sync that cannot exist.
 */

export type LocalRow = { code?: string; what?: string; detail?: string; severity?: string; why?: string; fix?: string };

export type DirectoryState =
  /** We can check it and did: the verdict is real. */
  | "ok" | "problem"
  /** We can check it and have not. */
  | "unchecked"
  /** Nobody can check it - the vendor publishes no read API. */
  | "no-api"
  /** We could check it, but the integration is not built yet. */
  | "not-built";

export type Directory = {
  name: string;
  icon: string;
  state: DirectoryState;
  note: string;
};

/** Does any GBP row carry a real verdict? */
function gbpVerdict(rows: LocalRow[]): "ok" | "problem" | null {
  const gbp = rows.filter((r) => (r.code || "").startsWith("gbp."));
  if (gbp.length === 0) return null;
  return gbp.every((r) => r.severity === "ok") ? "ok" : "problem";
}

export function deriveDirectories(rows: LocalRow[] | null | undefined): Directory[] {
  const list = Array.isArray(rows) ? rows.filter((r) => r && typeof r === "object") : [];
  const google = gbpVerdict(list);

  return [
    {
      name: "Google Business Profile",
      icon: "📍",
      state: google === null ? "unchecked" : google,
      note:
        google === null
          ? "Run the Local tool, or connect Google, to read the live profile."
          : google === "ok"
            ? "Profile read: rating, category and NAP all present."
            : "The profile is missing something. See the checklist below.",
    },
    {
      name: "Yelp",
      icon: "⭐",
      state: "not-built",
      note: "Checkable through the Yelp Fusion API (free, read-only). Not built yet - it needs an API key.",
    },
    { name: "Bing Places", icon: "🌐", state: "no-api",
      note: "No public read API. Bing Places is management-only; no tool can verify this listing." },
    { name: "Apple Business Connect", icon: "🍏", state: "no-api",
      note: "No public read API. Apple publishes no way to query a listing's state." },
    { name: "Waze", icon: "🚗", state: "no-api",
      note: "No public API, and Waze listings are sourced from Google data anyway." },
    { name: "YellowPages", icon: "📞", state: "no-api",
      note: "No public API. Only scraping, which is unreliable and not worth reporting on." },
  ];
}

export function directoryLabel(s: DirectoryState): string {
  switch (s) {
    case "ok": return "Verified";
    case "problem": return "Needs work";
    case "unchecked": return "Not checked";
    case "not-built": return "Not built";
    case "no-api": return "No public API";
  }
}

export function directoryColor(s: DirectoryState): string {
  switch (s) {
    case "ok": return "#047857";
    case "problem": return "#d97706";
    default: return "#64748b"; // never green for something nobody measured
  }
}

/**
 * The count above the matrix. `5/6 Verified Active` was a literal; this counts
 * only what was actually checked, and names the denominator honestly.
 */
export function directorySummary(dirs: Directory[]): string {
  const checkable = dirs.filter((d) => d.state === "ok" || d.state === "problem");
  if (checkable.length === 0) return "None checked yet";
  const ok = checkable.filter((d) => d.state === "ok").length;
  const impossible = dirs.filter((d) => d.state === "no-api").length;
  return `${ok}/${checkable.length} verified · ${impossible} cannot be checked by any tool`;
}
