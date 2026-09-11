/**
 * Core Web Vitals, read from the scan instead of guessed from a score.
 *
 * What this replaces: the dashboard derived an LCP time, an INP time and a CLS
 * figure from the Lighthouse *performance score* -
 *
 *     lcp.val = lhPerfNum < 50 ? "3.8s" : lhPerfNum < 80 ? "2.4s" : "1.6s"
 *
 * - with the score itself defaulting to "46/100" when no scan had run. A
 * Lighthouse score is not an LCP time, and a bucket can never produce a
 * millisecond figure. Those numbers rendered next to the words "Core Web
 * Vitals" as if a browser had measured them.
 *
 * The scanner emits the real p75 for each metric (pipeline/scanner/audit.py
 * `perf_rows`, from providers.crux_metrics) as rows coded `crux.lcp`,
 * `crux.inp`, `crux.cls`, with the verdict in `detail` and the severity already
 * mapped. When CrUX has no field data, or no scan has run, there is no number,
 * and this returns an em dash with "Not measured" rather than inventing one.
 */

import type { ReportRow, ScanReport } from "./priorities";

export type VitalKey = "lcp" | "inp" | "cls";

export interface VitalReading {
  /** The measured p75, or an em dash. Never a value derived from a bucket. */
  val: string;
  /** "Good" | "Needs Work" | "Poor" | "Not measured". */
  status: string;
  /** A design token, never a raw hex. */
  color: string;
  target: string;
  measured: boolean;
}

export type CoreWebVitals = Record<VitalKey, VitalReading>;

/** Google's "good" thresholds, quoted as targets only - never as readings. */
const TARGETS: Record<VitalKey, string> = {
  lcp: "≤ 2.5s",
  inp: "≤ 200ms",
  cls: "≤ 0.10",
};

const NOT_MEASURED: VitalReading = {
  val: "—",
  status: "Not measured",
  color: "var(--ink-muted)",
  target: "",
  measured: false,
};

function statusFor(row: ReportRow): { status: string; color: string } {
  if (row.severity === "ok") return { status: "Good", color: "var(--ok)" };
  if (row.severity === "warn") return { status: "Needs Work", color: "var(--warn)" };
  if (row.severity === "error") return { status: "Poor", color: "var(--bad)" };
  return { status: "Not measured", color: "var(--ink-muted)" };
}

/**
 * The p75 the row carries, formatted in the metric's own unit.
 *
 * `perf_rows` writes `what` as "LCP 2100 (p75)"; `crux_findings` writes
 * `detail` as "p75=2100 (good <= 2500)". Both hold the same measured number, so
 * either is read, and nothing is produced when neither parses.
 */
export function readP75(key: VitalKey, row: ReportRow): string | null {
  const what = typeof row.what === "string" ? row.what : "";
  const detail = typeof row.detail === "string" ? row.detail : "";
  const fromWhat = what.match(/\b(?:LCP|INP|CLS)\s+([0-9]*\.?[0-9]+)/i);
  const fromDetail = detail.match(/p75\s*=\s*([0-9]*\.?[0-9]+)/i);
  const raw = fromWhat?.[1] ?? fromDetail?.[1];
  if (raw === undefined) return null;
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  // Unit conversion of a measured value, not a re-estimate: CrUX reports LCP
  // and INP in milliseconds and CLS unitless.
  if (key === "cls") return String(n);
  if (key === "lcp") return n >= 1000 ? `${(n / 1000).toFixed(1)}s` : `${Math.round(n)}ms`;
  return `${Math.round(n)}ms`;
}

/** Keys in a report that are not groups of rows. */
const NON_GROUP_KEYS = new Set(["score", "counts", "cost", "log", "cycle", "url", "site_url"]);

/**
 * Every `crux.*` row in the report, whichever tool group carries it.
 *
 * Walked here rather than through rowsForView so this module has no runtime
 * import - the same reason lib/priorities.ts has none.
 */
function cruxRows(report: ScanReport | null | undefined): ReportRow[] {
  if (!report || typeof report !== "object") return [];
  const out: ReportRow[] = [];
  for (const [key, value] of Object.entries(report)) {
    if (NON_GROUP_KEYS.has(key) || !Array.isArray(value)) continue;
    for (const row of value as ReportRow[]) {
      if (row && typeof row === "object" && typeof row.code === "string" && row.code.startsWith("crux.")) {
        out.push(row);
      }
    }
  }
  return out;
}

/**
 * The three vitals as the scan measured them.
 *
 * Reads the same `crux.*` rows the Core Web Vitals report view shows, so the
 * card and the table can never disagree.
 */
export function deriveCoreWebVitals(report: ScanReport | null | undefined): CoreWebVitals {
  const rows = cruxRows(report);
  const out: CoreWebVitals = {
    lcp: { ...NOT_MEASURED, target: TARGETS.lcp },
    inp: { ...NOT_MEASURED, target: TARGETS.inp },
    cls: { ...NOT_MEASURED, target: TARGETS.cls },
  };

  for (const key of ["lcp", "inp", "cls"] as VitalKey[]) {
    // `crux.lcp` carries the reading for every verdict; `crux.lcp_above_good`
    // only appears when it failed. Prefer the first, fall back to the second.
    const exact = rows.find((r) => r.code === `crux.${key}`);
    const above = rows.find((r) => r.code === `crux.${key}_above_good`);
    const row = exact ?? above;
    if (!row) continue;
    const val = readP75(key, row);
    if (val === null) continue;
    const { status, color } = statusFor(row);
    // A row with no recognised verdict is a row that judged nothing.
    if (!row.severity || status === "Not measured") continue;
    out[key] = { val, status, color, target: TARGETS[key], measured: true };
  }
  return out;
}

/** True when at least one vital was actually measured. */
export function anyVitalMeasured(v: CoreWebVitals): boolean {
  return v.lcp.measured || v.inp.measured || v.cls.measured;
}
