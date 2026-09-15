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
 * WHAT SHIPS, AND WHY THE OTHER FOUR ARE GONE.
 *
 *   Google Business Profile   CHECKABLE  - DataForSEO Business Data (paid), or
 *                                          Google's own API via OAuth (free,
 *                                          but Google must allowlist the app)
 *   On-page local signals     CHECKABLE  - free, from the HTML already fetched:
 *                                          Maps embed, click-to-call, address,
 *                                          geo coordinates, opening hours
 *                                          (`local.*` rows from the scanner)
 *   Yelp                      BUILDABLE  - Yelp Fusion API, free tier, read
 *                                          only. Not built; needs a key.
 *
 *   Bing Places               NO API     - management only, no public read
 *   Apple Business Connect    NO API     - management only, no public read
 *   Waze                      NO API     - listings come from Google data
 *   YellowPages               NO API     - scraping only, and unreliable
 *
 * Those last four were first shown honestly as "No public API", then REMOVED on
 * the operator's call: a tile that can only ever say "nobody can check this" is
 * four-sixths of a screen spent on things no one can act on.
 *
 * The list is kept here on purpose. It is the answer to "why is Bing missing",
 * and without it the next person to ask will add the tiles back - which is
 * exactly how six fabricated "Synced" badges got here in the first place.
 *
 * Removing a lie leaves a gap. `local.*` is what fills it: five signals that
 * cost nothing, need no credential, and are true of the page we fetched. What a
 * third-party directory says is between the client and that directory. What the
 * client's own page says is ours to check, and ours to fix.
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
  /** A line icon name from components/dashboard/Icon.tsx. */
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

/** The free, page-derived local signals. Same three-state rule as the rest. */
function pageVerdict(rows: LocalRow[]): "ok" | "problem" | null {
  const local = rows.filter((r) => (r.code || "").startsWith("local."));
  if (local.length === 0) return null;
  // `info` is a fact, not a verdict - geo coordinates are optional, so an
  // absent one must not make the whole tile read as a failure.
  const graded = local.filter((r) => r.severity !== "info");
  if (graded.length === 0) return null;
  return graded.every((r) => r.severity === "ok") ? "ok" : "problem";
}

export function deriveDirectories(rows: LocalRow[] | null | undefined): Directory[] {
  const list = Array.isArray(rows) ? rows.filter((r) => r && typeof r === "object") : [];
  const google = gbpVerdict(list);
  const page = pageVerdict(list);

  // Bing Places, Apple Business Connect, Waze and YellowPages were removed
  // outright on the operator's call: a tile that can only ever say "no public
  // API" is four-sixths of a screen spent on things nobody can do anything
  // about. The reason is kept in this module's docstring so a future session
  // cannot "restore" them as green tiles - which is exactly how they got here.
  return [
    {
      name: "Google Business Profile",
      icon: "pin",
      state: google === null ? "unchecked" : google,
      note:
        google === null
          ? "Run a scan with the Local tool, or connect Google, to read the live profile."
          : google === "ok"
            ? "Profile read: rating, category and NAP all present."
            : "The profile is missing something. See the checklist below.",
    },
    {
      name: "On-page local signals",
      icon: "map",
      state: page === null ? "unchecked" : page,
      note:
        page === null
          ? "Free with every scan: Maps embed, click-to-call, address, geo coordinates and opening hours."
          : page === "ok"
            ? "Map embed, click-to-call and structured address, geo and hours all present."
            : "Something a local searcher looks for is missing from the page. See the checklist below.",
    },
    {
      name: "Yelp",
      icon: "star",
      state: "not-built",
      note: "Checkable through the Yelp Fusion API (free, read-only). Not built yet - it needs an API key.",
    },
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
    case "ok": return "var(--ok)";
    case "problem": return "var(--warn)";
    default: return "var(--ink-muted)"; // never green for something nobody measured
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
  return `${ok}/${checkable.length} verified`;
}
