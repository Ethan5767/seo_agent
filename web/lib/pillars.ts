/**
 * The six pillar cards on the Measure screen's summary sub-tab.
 *
 * They used to be six literals. Each carried a list of bullets rendered with a
 * green tick - "SSL/TLS 256-bit active", "HSTS header enabled",
 * "MedicalBusiness JSON-LD", "0 orphan URLs detected" - that asserted a passed
 * check on a client's site that nothing had ever run. The same claims had
 * already been deleted from the All Checks sub-tab for being fabricated, and
 * one of them named a healthcare schema for every client whatever their
 * industry. The cards also scored 0 while styled with the pass colour.
 *
 * Every field below comes from rows the scanner produced. A pillar with no rows
 * reports "Not measured" and carries a neutral tone, so a zero is never dressed
 * as a pass.
 *
 * Report shape (pipeline/scanner/audit.py `assemble`): { <toolKey>: Row[], ... }.
 * A pillar's `catKey` IS the tool group key, which is also what the All Checks
 * filter chips key on - so "Inspect ... Checks" lands on exactly the rows the
 * card counted.
 */

import type { ReportRow, ScanReport, Severity } from "./priorities";
import type { StatusTone } from "./ui";

export interface PillarItem {
  /** The row's own `what`, never a written-in claim. */
  label: string;
  severity: Severity;
  /** The row's `detail`, when it has one. */
  detail: string;
}

export interface Pillar {
  /** Tool group key in the report; also the All Checks filter key. */
  catKey: string;
  title: string;
  /** True when the group produced at least one row. */
  measured: boolean;
  /** Share of gradeable rows that passed, or null when nothing gradeable ran. */
  score: number | null;
  /** Plain words for the badge: never "AI Ready" over an unmeasured pillar. */
  status: string;
  tone: StatusTone;
  items: PillarItem[];
  total: number;
  ok: number;
  warn: number;
  error: number;
  info: number;
}

/**
 * Labels match the All Checks category chips exactly, so a card and the filter
 * it opens name the same thing.
 */
export const PILLAR_DEFS: Array<{ catKey: string; title: string }> = [
  { catKey: "seo", title: "Crawlability & SEO" },
  { catKey: "tech", title: "Security & HTTPS" },
  { catKey: "perf", title: "Core Web Vitals & Speed" },
  { catKey: "site", title: "Architecture & Linking" },
  { catKey: "schema", title: "Structured Data (Schema)" },
  { catKey: "aeo", title: "AEO & LLM Search Readiness" },
];

/** Errors first, then warnings, then context, then passes. */
const SEVERITY_ORDER: Record<string, number> = { error: 0, warn: 1, info: 2, ok: 3 };

function rowsOf(report: ScanReport | null | undefined, key: string): ReportRow[] {
  if (!report || typeof report !== "object") return [];
  const value = (report as Record<string, unknown>)[key];
  if (!Array.isArray(value)) return [];
  return (value as ReportRow[]).filter((r) => r && typeof r === "object");
}

/** Sentence-case a scanner `what` without rewording it. */
function label(row: ReportRow): string {
  const s = (row.what || row.code || "").trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "Unnamed check";
}

export function derivePillars(
  report: ScanReport | null | undefined,
  itemsPerPillar = 4,
): Pillar[] {
  return PILLAR_DEFS.map(({ catKey, title }) => {
    const rows = rowsOf(report, catKey);
    let ok = 0, warn = 0, error = 0, info = 0;
    for (const row of rows) {
      if (row.severity === "ok") ok += 1;
      else if (row.severity === "warn") warn += 1;
      else if (row.severity === "error") error += 1;
      else if (row.severity === "info") info += 1;
    }

    // "info" rows are context (a skipped provider, a note), not a verdict, so
    // they are excluded from the pass ratio rather than counted as failures.
    const graded = ok + warn + error;
    const score = graded > 0 ? Math.round((ok / graded) * 100) : null;
    const issues = warn + error;

    let status: string;
    let tone: StatusTone;
    if (rows.length === 0) {
      status = "Not measured";
      tone = "neutral";
    } else if (graded === 0) {
      status = "Context only";
      tone = "neutral";
    } else if (error > 0) {
      status = `${issues} Issue${issues === 1 ? "" : "s"} Found`;
      tone = "bad";
    } else if (warn > 0) {
      status = `${issues} Warning${issues === 1 ? "" : "s"}`;
      tone = "warn";
    } else {
      status = `${ok} Check${ok === 1 ? "" : "s"} Passing`;
      tone = "ok";
    }

    const items = [...rows]
      .sort(
        (a, b) =>
          (SEVERITY_ORDER[a.severity ?? ""] ?? 9) - (SEVERITY_ORDER[b.severity ?? ""] ?? 9),
      )
      .slice(0, itemsPerPillar)
      .map((row) => ({
        label: label(row),
        severity: (row.severity ?? "info") as Severity,
        detail: typeof row.detail === "string" ? row.detail : "",
      }));

    return {
      catKey,
      title,
      measured: rows.length > 0,
      score,
      status,
      tone,
      items,
      total: rows.length,
      ok,
      warn,
      error,
      info,
    };
  });
}

/** The glyph that goes with a row's severity. Colour never carries it alone. */
export function severityMark(severity: Severity | undefined): string {
  if (severity === "ok") return "✓";
  if (severity === "warn") return "!";
  if (severity === "error") return "✕";
  return "·";
}

/** Tone for a row's severity, so an item is never green over a failure. */
export function severityTone(severity: Severity | undefined): StatusTone {
  if (severity === "ok") return "ok";
  if (severity === "warn") return "warn";
  if (severity === "error") return "bad";
  return "neutral";
}
