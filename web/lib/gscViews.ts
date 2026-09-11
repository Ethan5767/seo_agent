/**
 * Search Console views.
 *
 * These are the screens a competitor charges for and models: their "Organic
 * Traffic Insights", "Top Pages" and "Position Tracking" are estimates derived
 * from a SERP index and a click-through curve. This reads the client's own
 * Search Console instead, so the figures are measured rather than modelled -
 * real clicks, real impressions, real average position.
 *
 * The `webmasters.readonly` scope is already requested at sign-in and
 * `/api/gsc/query` already accepts a `dimensions` array, so every view below
 * costs nothing and needs no new integration.
 */

export interface GscColumn {
  key: "keys" | "clicks" | "impressions" | "ctr" | "position";
  label: string;
  numeric?: boolean;
  width?: string;
}

export interface GscView {
  id: string;
  label: string;
  /** Search Console dimension to group by. */
  dimension: "query" | "page" | "country" | "device" | "date";
  blurb: string;
  /** Column header for the dimension itself. */
  keyLabel: string;
  emptyHint: string;
}

/** Metric columns are the same for every dimension; only the key column differs. */
export const GSC_METRIC_COLUMNS: GscColumn[] = [
  { key: "clicks", label: "Clicks", numeric: true, width: "8rem" },
  { key: "impressions", label: "Impressions", numeric: true, width: "9rem" },
  { key: "ctr", label: "CTR", numeric: true, width: "7rem" },
  { key: "position", label: "Avg position", numeric: true, width: "9rem" },
];

export const GSC_VIEWS: GscView[] = [
  {
    id: "gsc-queries",
    label: "Search Queries",
    dimension: "query",
    keyLabel: "Query",
    blurb:
      "The searches that actually brought people to this site, with real clicks and impressions from Search Console. Not an estimate.",
    emptyHint:
      "Connect Google and pick this project's Search Console property to load the last 28 days.",
  },
  {
    id: "gsc-pages",
    label: "Top Pages",
    dimension: "page",
    keyLabel: "Page",
    blurb: "Which pages earn the clicks, ranked by measured traffic over the last 28 days.",
    emptyHint:
      "Connect Google and pick this project's Search Console property to load the last 28 days.",
  },
  {
    id: "gsc-countries",
    label: "Countries",
    dimension: "country",
    keyLabel: "Country",
    blurb: "Where the traffic comes from, measured rather than apportioned by a share model.",
    emptyHint:
      "Connect Google and pick this project's Search Console property to load the last 28 days.",
  },
  {
    id: "gsc-devices",
    label: "Devices",
    dimension: "device",
    keyLabel: "Device",
    blurb: "Desktop, mobile and tablet split, with position by device.",
    emptyHint:
      "Connect Google and pick this project's Search Console property to load the last 28 days.",
  },
  {
    id: "gsc-trend",
    label: "Traffic Trend",
    dimension: "date",
    keyLabel: "Date",
    blurb: "Daily clicks and impressions over the last 28 days.",
    emptyHint:
      "Connect Google and pick this project's Search Console property to load the last 28 days.",
  },
];

export function gscViewById(id: string): GscView | undefined {
  return GSC_VIEWS.find((v) => v.id === id);
}

/** A Search Console row, as the API returns it. */
export interface GscRow {
  keys?: string[];
  clicks?: number;
  impressions?: number;
  ctr?: number;
  position?: number;
}

export interface GscTotals {
  rows: number;
  clicks: number;
  impressions: number;
  /** Weighted by impressions, not a mean of means. */
  ctr: number;
  /** Weighted by impressions, so a high-volume term counts for more. */
  position: number;
}

/**
 * Totals for the count strip.
 *
 * Returns zeroes for a missing or empty set, so an unconnected screen reads as
 * measured-at-zero rather than blank. CTR and position are impression-weighted:
 * averaging the per-row averages would let a single impression on one query
 * swing the figure as hard as ten thousand on another.
 */
export function gscTotals(rows: GscRow[] | null | undefined): GscTotals {
  const out: GscTotals = { rows: 0, clicks: 0, impressions: 0, ctr: 0, position: 0 };
  if (!Array.isArray(rows) || rows.length === 0) return out;

  let weightedPosition = 0;
  for (const r of rows) {
    if (!r || typeof r !== "object") continue;
    const impressions = Number(r.impressions ?? 0);
    out.rows += 1;
    out.clicks += Number(r.clicks ?? 0);
    out.impressions += impressions;
    weightedPosition += Number(r.position ?? 0) * impressions;
  }

  out.ctr = out.impressions > 0 ? out.clicks / out.impressions : 0;
  out.position = out.impressions > 0 ? weightedPosition / out.impressions : 0;
  return out;
}

/** Format a Search Console value for display. Never invents a figure. */
export function formatGscValue(key: GscColumn["key"], value: unknown): string {
  if (key === "keys") {
    return Array.isArray(value) ? value.join(" · ") : String(value ?? "");
  }
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "0";
  if (key === "ctr") return `${(n * 100).toFixed(1)}%`;
  if (key === "position") return n.toFixed(1);
  return n.toLocaleString();
}
