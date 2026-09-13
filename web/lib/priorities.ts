/**
 * Turn a real scan report into the ranked priority list the Overview shows.
 *
 * This replaces a hardcoded three-item fixture ("Fix 8 pages missing a title",
 * "+10-18% CTR", "Severity Weight 9.5") that rendered identically for every
 * client, scanned or not. Everything below is derived from rows the scanner
 * actually produced; nothing is invented. Where the report says nothing, this
 * returns nothing, and the UI says so.
 *
 * Report shape (pipeline/scanner/audit.py `assemble`):
 *   { <toolKey>: Row[], score: number, counts: {error,warn,info,ok} }
 * Row shape (`_row`):
 *   { code, what, why, fix, detail, severity, pages? }
 */

export type Severity = "error" | "warn" | "info" | "ok";

export interface ReportRow {
  code?: string;
  what?: string;
  why?: string;
  fix?: string;
  detail?: string;
  severity?: Severity;
  pages?: string[];
}

export interface ScanReport {
  score?: number;
  counts?: Partial<Record<Severity, number>>;
  [toolKey: string]: unknown;
}

export interface DerivedPriority {
  id: string;
  title: string;
  category: "SEO" | "AI Search" | "SEO + AI";
  severity: "critical" | "warning" | "info";
  problem: string;
  whyItMatters: string;
  recommendedAction: string;
  actionLabel: string;
  expectedOutcome: string;
  source: string;
  confidence: "High" | "Medium" | "Estimated";
  isAutoFixable: boolean;
  affectedPages: string[];
  technicalDetails: {
    title: string;
    category: string;
    summary: string;
    codeSnippet?: string;
    metrics: Record<string, string | number>;
  };
}

/** Keys in the report that are not groups of finding rows. */
const NON_GROUP_KEYS = new Set(["score", "counts", "cost", "log", "cycle", "url", "site_url"]);

/**
 * Which tool group produced a finding, in the product's own words.
 * Unknown keys fall back to the key itself rather than a guess.
 */
const GROUP_LABELS: Record<string, string> = {
  site: "Site Audit",
  health: "Site Audit",
  aeo: "AI Visibility",
  ai: "AI Visibility",
  schema: "Schema & Entities",
  crawlers: "AI Crawler Access",
  keywords: "Keywords",
  rankings: "Keywords",
  backlinks: "Backlinks",
  gbp: "Local Presence",
  lh_perf: "Core Web Vitals",
  lh_seo: "Core Web Vitals",
  lh_a11y: "Core Web Vitals",
  lh_best: "Core Web Vitals",
  src: "Source Code",
  links: "Internal Links",
  crux: "Core Web Vitals",
};

/** Groups whose findings are about answer engines rather than classic search. */
const AI_GROUPS = new Set(["aeo", "ai", "schema", "crawlers"]);

/**
 * Only `health.*` codes have machine-checkable acceptance in the remediation
 * rail (pipeline/audit/plan.py ACTIONS), so only they may claim auto-fixability.
 * Claiming it elsewhere would promise a fix the rail cannot make.
 */
function isAutoFixable(code: string | undefined): boolean {
  return Boolean(code && code.startsWith("health."));
}

function categoryFor(groupKey: string): DerivedPriority["category"] {
  if (AI_GROUPS.has(groupKey)) return "AI Search";
  if (groupKey === "schema") return "SEO + AI";
  return "SEO";
}

function severityFor(rowSeverity: Severity | undefined): DerivedPriority["severity"] {
  if (rowSeverity === "error") return "critical";
  if (rowSeverity === "warn") return "warning";
  return "info";
}

/** Sentence-case a scanner code's `what` ("title missing" -> "Title missing"). */
function titleCase(what: string): string {
  const s = what.trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/**
 * A headline for the finding that names the scale when the scanner measured it.
 * The scanner puts affected pages on `row.pages` (pipeline/scanner/multipage.py),
 * so a count here is a real count, never an estimate.
 */
function headlineFor(row: ReportRow): string {
  const base = titleCase(row.what || row.code || "Unnamed finding");
  const n = row.pages?.length ?? 0;
  return n > 1 ? `${base} — ${n} pages` : base;
}

/**
 * Ranked priorities from a report. Errors before warnings; within a severity,
 * findings the remediation rail can actually fix come first, then the ones
 * affecting the most pages.
 *
 * Returns [] for a missing, empty or unscanned report. That empty list is the
 * honest answer and the UI renders an empty state for it.
 */
export function derivePriorities(report: ScanReport | null | undefined, limit = 6): DerivedPriority[] {
  if (!report || typeof report !== "object") return [];

  const found: Array<{ row: ReportRow; groupKey: string }> = [];
  for (const [groupKey, value] of Object.entries(report)) {
    if (NON_GROUP_KEYS.has(groupKey) || !Array.isArray(value)) continue;
    for (const row of value as ReportRow[]) {
      if (!row || typeof row !== "object") continue;
      // "ok" is a passing check and "info" is context; neither is a priority.
      if (row.severity !== "error" && row.severity !== "warn") continue;
      found.push({ row, groupKey });
    }
  }

  found.sort((a, b) => {
    const sev = (r: ReportRow) => (r.severity === "error" ? 0 : 1);
    if (sev(a.row) !== sev(b.row)) return sev(a.row) - sev(b.row);
    const fix = (r: ReportRow) => (isAutoFixable(r.code) ? 0 : 1);
    if (fix(a.row) !== fix(b.row)) return fix(a.row) - fix(b.row);
    return (b.row.pages?.length ?? 0) - (a.row.pages?.length ?? 0);
  });

  return found.slice(0, limit).map(({ row, groupKey }, index) => {
    const source = GROUP_LABELS[groupKey] ?? groupKey;
    const pages = Array.isArray(row.pages) ? row.pages : [];
    const autoFixable = isAutoFixable(row.code);

    const metrics: Record<string, string | number> = {
      "Finding code": row.code || "(none)",
      Severity: row.severity === "error" ? "Error" : "Warning",
      "Detected by": source,
    };
    if (pages.length) metrics["Affected URLs"] = pages.length;

    return {
      id: row.code ? `priority-${row.code}` : `priority-${groupKey}-${index}`,
      title: headlineFor(row),
      category: categoryFor(groupKey),
      severity: severityFor(row.severity),
      problem: row.detail || row.what || "The scanner flagged this check.",
      // `why` and `fix` come from pipeline/scanner/recommend.py, which is the
      // product's own copy for this code. No invented impact numbers.
      whyItMatters: row.why || "",
      recommendedAction: row.fix || "",
      actionLabel: autoFixable ? "Review fix" : "Open details",
      expectedOutcome: autoFixable
        ? "The remediation rail can stage this change for review."
        : "Needs a manual change; the rail has no automated acceptance for this check.",
      source,
      // The scanner measured it, so the finding is not an estimate. What we
      // never claim is a predicted outcome.
      confidence: "High",
      isAutoFixable: autoFixable,
      affectedPages: pages,
      technicalDetails: {
        title: titleCase(row.what || row.code || "Finding"),
        category: source,
        summary: row.detail || "No further detail recorded for this check.",
        metrics,
      },
    };
  });
}

/** True when a report exists and actually carries finding rows. */
export function hasFindings(report: ScanReport | null | undefined): boolean {
  if (!report || typeof report !== "object") return false;
  return Object.entries(report).some(
    ([key, value]) => !NON_GROUP_KEYS.has(key) && Array.isArray(value) && value.length > 0,
  );
}
