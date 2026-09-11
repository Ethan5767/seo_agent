// Pure score-trend helpers for the history dashboard. No network, no Supabase —
// given a client's scans (any order), produce sparkline points and the latest
// delta. Kept dependency-free so it's unit-testable offline (no paid calls).

export type ScanLite = {
  id: string;
  created_at: string;
  url?: string;
  score: number | null;
  counts?: Record<string, number> | null;
  cost?: number | null;
};

export type Trend = {
  points: number[];          // scores oldest→newest, nulls dropped
  latest: number | null;     // newest score (null if none)
  previous: number | null;   // score before latest (null if <2)
  delta: number | null;      // latest - previous (null if <2)
  direction: "up" | "down" | "flat" | "none";
};

/** Oldest→newest score series + latest-vs-previous delta. Input may be in any
 *  order; scans with a null score are excluded from points/delta (an errored or
 *  empty-selection scan shouldn't fake a trend). */
export function scoreTrend(scans: ScanLite[]): Trend {
  const ordered = [...(scans || [])].sort(
    (a, b) => Date.parse(a.created_at) - Date.parse(b.created_at),
  );
  const points = ordered
    .map((s) => s.score)
    .filter((n): n is number => typeof n === "number");
  const latest = points.length ? points[points.length - 1] : null;
  const previous = points.length >= 2 ? points[points.length - 2] : null;
  const delta = latest !== null && previous !== null ? latest - previous : null;
  const direction: Trend["direction"] =
    delta === null ? "none" : delta > 0 ? "up" : delta < 0 ? "down" : "flat";
  return { points, latest, previous, delta, direction };
}

/** SVG polyline points for a sparkline, scaled into a w×h box. Scores are 0-100,
 *  so the y-axis is fixed to that range (a flat 100 line reads as full height,
 *  not autoscaled to look jagged). Empty/one-point series → "". */
export function sparklinePath(points: number[], w = 120, h = 28): string {
  if (!points || points.length < 2) return "";
  const n = points.length;
  const stepX = w / (n - 1);
  return points
    .map((v, i) => {
      const clamped = Math.max(0, Math.min(100, v));
      const y = h - (clamped / 100) * h;
      return `${(i * stepX).toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}
