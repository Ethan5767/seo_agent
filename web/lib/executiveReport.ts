/**
 * The client-facing Executive Report, built from the scan or refused.
 *
 * What this replaces: a printable, client-addressed deliverable assembled
 * entirely from literals - "Technical Health Score: 94 / 100 (Grade A)",
 * "AI / AEO Engine Readiness: 92%", "Core Web Vitals: PASSED (LCP 1.8s | INP
 * 82ms | CLS 0.02)", "Est. Organic Traffic Value: $2,439 / mo (+14.2% MoM)", a
 * hardcoded audit date, keyword fallbacks naming a city nobody had scanned, and
 * a section titled "AUTONOMOUS REMEDIATIONS DEPLOYED" listing five fixes that
 * never ran. It rendered identically for every client, scanned or not.
 *
 * The feature stays; the invention goes. Rules this module holds to:
 *
 *   1. Every figure traces to a row or a count the scanner produced.
 *   2. No scan, no document. `build` returns null and the screen says why.
 *   3. Applied remediations are not knowable here. The cycle's changelog.json,
 *      written by wf-site-remediate, is the only record of what was applied,
 *      and this screen does not read it - so the section is gone rather than
 *      reworded.
 *   4. A figure the report does not carry (organic traffic value, a month-over-
 *      month delta) is omitted, never estimated.
 */

/*
 * Runtime imports carry the ".ts" extension so Node can load this module
 * directly in `node --test` (it strips the types but resolves the path
 * literally). `allowImportingTsExtensions` in tsconfig.json is what makes the
 * same specifier legal to tsc and the bundler.
 */
import { derivePriorities, hasFindings, type DerivedPriority, type ReportRow, type ScanReport } from "./priorities.ts";
import { derivePillars, type Pillar } from "./pillars.ts";
import { anyVitalMeasured, deriveCoreWebVitals, type CoreWebVitals } from "./webVitals.ts";
import { rowsForView, viewById } from "./reportViews.ts";

export interface ExecutiveKeyword {
  /** The scanner's own `what` for the keyword row. */
  what: string;
  detail: string;
}

export interface ExecutiveReport {
  client: string;
  domain: string;
  agency: string;
  /** Generated at export time, or the scan's own timestamp when it carries one. */
  date: string;
  /** report.score, as `assemble` computed it. Null when the report omits it. */
  healthScore: number | null;
  counts: { error: number; warn: number; info: number; ok: number };
  /** Every row the scan produced, and the subset that passed. */
  checksTotal: number;
  checksPassing: number;
  pillars: Pillar[];
  vitals: CoreWebVitals;
  vitalsMeasured: boolean;
  priorities: DerivedPriority[];
  keywords: ExecutiveKeyword[];
  markdown: string;
}

export interface ExecutiveInput {
  report: ScanReport | null | undefined;
  client: string;
  domain: string;
  agency: string;
  /** Injected so the date is testable; defaults to export time. */
  now?: Date;
}

/** Keys in a report that are not groups of rows. */
const NON_GROUP_KEYS = new Set(["score", "counts", "cost", "log", "cycle", "url", "site_url"]);

/** Severity tallies counted off the rows themselves, for a report with no `counts`. */
function tallyReport(report: ScanReport | null | undefined) {
  const t = { error: 0, warn: 0, info: 0, ok: 0 };
  if (!report || typeof report !== "object") return t;
  for (const [key, value] of Object.entries(report)) {
    if (NON_GROUP_KEYS.has(key) || !Array.isArray(value)) continue;
    for (const row of value as ReportRow[]) {
      if (!row || typeof row !== "object") continue;
      const s = row.severity;
      if (s === "error" || s === "warn" || s === "info" || s === "ok") t[s] += 1;
    }
  }
  return t;
}

/** Keyword rows the scan really produced. No fallback terms, ever. */
function keywordRows(report: ScanReport | null | undefined): ExecutiveKeyword[] {
  const out: ExecutiveKeyword[] = [];
  for (const id of ["organic-rankings", "serp-positions", "keyword-overview"]) {
    const view = viewById(id);
    if (!view) continue;
    for (const row of rowsForView(report, view) as ReportRow[]) {
      const what = (row.what || "").trim();
      if (!what) continue;
      out.push({ what, detail: (row.detail || "").trim() });
      if (out.length >= 5) return out;
    }
  }
  return out;
}

/** The scan's own timestamp when the report carries one, else export time. */
function reportDate(report: ScanReport | null | undefined, now: Date): string {
  const stamp = report && typeof report === "object"
    ? (report as Record<string, unknown>)["scanned_at"] ?? (report as Record<string, unknown>)["created_at"]
    : undefined;
  if (typeof stamp === "string") {
    const parsed = new Date(stamp);
    if (!Number.isNaN(parsed.getTime())) return parsed.toISOString().slice(0, 10);
  }
  return now.toISOString().slice(0, 10);
}

function vitalsLine(v: CoreWebVitals): string | null {
  const parts = (["lcp", "inp", "cls"] as const)
    .filter((k) => v[k].measured)
    .map((k) => `${k.toUpperCase()} ${v[k].val} (${v[k].status})`);
  return parts.length ? parts.join(" | ") : null;
}

/**
 * The markdown the Copy Summary button puts on the clipboard.
 *
 * Built from the same fields the panel renders, so the copy and the printed
 * page can never state different numbers.
 */
export function executiveMarkdown(r: ExecutiveReport): string {
  const lines: string[] = [
    "# Executive SEO & AEO Report",
    `Client: ${r.client}${r.domain ? ` (${r.domain})` : ""}`,
    `Agency: ${r.agency}`,
    `Report Date: ${r.date}`,
    "",
    "## 1. Measured Health",
  ];

  if (r.healthScore !== null) lines.push(`- Technical Health Score: ${r.healthScore} / 100`);
  lines.push(
    `- Checks: ${r.checksPassing} passing of ${r.checksTotal} that ran ` +
      `(${r.counts.error} error${r.counts.error === 1 ? "" : "s"}, ` +
      `${r.counts.warn} warning${r.counts.warn === 1 ? "" : "s"})`,
  );
  const cwv = vitalsLine(r.vitals);
  lines.push(cwv ? `- Core Web Vitals (CrUX field data): ${cwv}` : "- Core Web Vitals: not measured on this scan");

  lines.push("", "## 2. Pillar Results");
  for (const p of r.pillars) {
    lines.push(
      p.measured
        ? `- ${p.title}: ${p.score === null ? "no graded checks" : `${p.score}% passing`} — ${p.status}`
        : `- ${p.title}: not measured`,
    );
  }

  if (r.priorities.length) {
    lines.push("", "## 3. Top Findings");
    r.priorities.forEach((p, i) => {
      lines.push(`${i + 1}. [${p.severity}] ${p.title} — ${p.source}`);
      if (p.recommendedAction) lines.push(`   Fix: ${p.recommendedAction}`);
    });
  }

  if (r.keywords.length) {
    lines.push("", `## ${r.priorities.length ? 4 : 3}. Tracked Keywords`);
    for (const k of r.keywords) lines.push(`- ${k.what}${k.detail ? ` (${k.detail})` : ""}`);
  }

  lines.push(
    "",
    `Every figure above is read from the scan of ${r.domain || r.client} on ${r.date}. ` +
      "Figures the scan did not measure are omitted rather than estimated.",
    `Prepared by ${r.agency}.`,
  );
  return lines.join("\n");
}

/**
 * The report, or null when no scan has run.
 *
 * Null is the whole point: with no findings there is nothing to certify to a
 * client, so the caller must refuse to produce a document rather than fill it
 * with plausible numbers.
 */
export function buildExecutiveReport(input: ExecutiveInput): ExecutiveReport | null {
  const { report, client, domain, agency, now } = input;
  if (!hasFindings(report)) return null;

  const rawCounts = (report as ScanReport).counts ?? {};
  let counts = {
    error: Number(rawCounts.error ?? 0) || 0,
    warn: Number(rawCounts.warn ?? 0) || 0,
    info: Number(rawCounts.info ?? 0) || 0,
    ok: Number(rawCounts.ok ?? 0) || 0,
  };
  // A report written without `counts` still has rows; count those rather than
  // reporting zero checks over a scan that plainly ran.
  if (counts.error + counts.warn + counts.info + counts.ok === 0) counts = tallyReport(report);
  const checksTotal = counts.error + counts.warn + counts.info + counts.ok;
  const score = (report as ScanReport).score;
  const vitals = deriveCoreWebVitals(report);

  const built: ExecutiveReport = {
    client,
    domain,
    agency,
    date: reportDate(report, now ?? new Date()),
    healthScore: typeof score === "number" && Number.isFinite(score) ? score : null,
    counts,
    checksTotal,
    checksPassing: counts.ok,
    pillars: derivePillars(report),
    vitals,
    vitalsMeasured: anyVitalMeasured(vitals),
    priorities: derivePriorities(report, 5),
    keywords: keywordRows(report),
    markdown: "",
  };
  built.markdown = executiveMarkdown(built);
  return built;
}
