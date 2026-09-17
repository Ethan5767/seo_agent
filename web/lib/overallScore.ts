/**
 * The Overall SEO Score: four pillars, severity-weighted, one formula.
 *
 * Two defects in the old headline number are fixed here, both reported by the
 * operator (2026-09-16) and both confirmed in the code:
 *
 *   1. **Every check counted equally.** `health_score` is `ok / (ok+warn+error)`,
 *      so a missing `<title>` and a missing `apple-touch-icon` moved the number
 *      by the same 100/n. Checks now carry a weight (see CHECK_WEIGHTS) and the
 *      score is the share of WEIGHT that passed.
 *
 *   2. **A pillar nobody measured is not a pillar scoring zero.** An unmeasured
 *      pillar is never averaged in as 0 and never silently dropped: the Overall
 *      Score is withheld until every pillar has run, and the card says which
 *      ones are still missing. This is the same rule the engine holds itself to
 *      (exit 4 — a gate that scanned nothing must not report a pass).
 *
 * Info rows are facts, not verdicts, so they are outside both halves of the
 * fraction — the rule `health_score` already follows.
 */

import type { ReportRow, ScanReport, Severity } from "./priorities";

/* ── Check weights ──────────────────────────────────────────────────────────
 * Importance of the CHECK, not the outcome: a passed critical check earns its
 * full weight, a failed one loses it. Keyed by the codes the scanner really
 * emits (extracted from a live run, 2026-09-16), with MEDIUM as the default so
 * a new check is never silently worth nothing.
 */
export const CRITICAL = 10;
export const HIGH = 5;
export const MEDIUM = 2;
export const LOW = 1;

export const CHECK_WEIGHTS: Record<string, number> = {
  // Critical — blocks indexing, crawling, or the connection itself.
  "health.noindex_present": CRITICAL,
  "headers.x-robots-tag": CRITICAL,
  "health.title_missing": CRITICAL,
  "health.canonical_mismatch": CRITICAL,
  "onpage.single_canonical": CRITICAL,
  "tech.https": CRITICAL,
  "hygiene.soft_404": CRITICAL,
  "redirect.loop": CRITICAL,
  "redirect.https_upgrade": CRITICAL,
  "aeo.crawler_blocked": CRITICAL,

  // High — real ranking or trust impact.
  "health.desc_missing": HIGH,
  "health.h1_count": HIGH,
  "health.thin_content": HIGH,
  "onpage.single_title": HIGH,
  "onpage.single_meta_description": HIGH,
  "onpage.mixed_content": HIGH,
  "onpage.meta_refresh": HIGH,
  "tech.mobile_viewport": HIGH,
  "tech.xml_sitemap": HIGH,
  "tech.rendering_(crawler-visible_content)": HIGH,
  "valid.sitemap_valid": HIGH,
  "schema.structured_data": HIGH,
  "redirect.chain": HIGH,
  "redirect.temporary": HIGH,
  "site.broken_internal_link": HIGH,
  "site.duplicate_page_titles": HIGH,
  "site.orphan_page": HIGH,
  "security.ssl_expiry": HIGH,
  "health.img_alt_missing": HIGH,

  // Low — cosmetic or best practice. Everything unlisted is MEDIUM.
  "onpage.apple_touch_icon": LOW,
  "tech.favicon": LOW,
  "tech.twitter/x_card": LOW,
  "onpage.legacy_meta_keywords": LOW,
  "onpage.inline_styles": LOW,
  "onpage.url_case": LOW,
  "onpage.url_underscores": LOW,
  "onpage.url_length": LOW,
  "onpage.iframe_count": LOW,
};

export function weightOf(code: string): number {
  return CHECK_WEIGHTS[code] ?? MEDIUM;
}

/* ── Pillars ────────────────────────────────────────────────────────────────
 * Each pillar is a set of report groups. Weights sum to 100 and live here, in
 * one place, so they can be tuned as the industry shifts (AEO in particular).
 */
export interface PillarDef {
  key: "technical" | "content" | "backlinks" | "aeo";
  title: string;
  weight: number;
  groups: string[];
  /** Said out loud on the card when the pillar has not run. */
  howToMeasure: string;
}

export const OVERALL_PILLARS: PillarDef[] = [
  {
    key: "technical", title: "Technical", weight: 35,
    groups: ["seo", "onpage", "tech", "headers", "schema", "validate", "internal", "site"],
    howToMeasure: "Run the on-page audit",
  },
  {
    key: "content", title: "Content", weight: 35,
    groups: ["content", "eeat"],
    howToMeasure: "Run the Content and E-E-A-T tools",
  },
  {
    key: "backlinks", title: "Backlinks", weight: 20,
    groups: ["backlinks", "backlink_overview", "backlink_gap"],
    howToMeasure: "Run Backlink Overview (DataForSEO, paid)",
  },
  {
    key: "aeo", title: "AEO", weight: 10,
    groups: ["aeo", "ai"],
    howToMeasure: "Run the AI visibility tools",
  },
];

export interface PillarScore {
  key: PillarDef["key"];
  title: string;
  weight: number;
  /** null when the pillar produced no gradeable row: not measured, not zero. */
  score: number | null;
  measured: boolean;
  howToMeasure: string;
  passedWeight: number;
  totalWeight: number;
  /** Failing checks, heaviest first — what actually moved the number. */
  deductions: Array<{ code: string; what: string; severity: Severity; weight: number; group: string }>;
}

export interface OverallScore {
  /** null until every pillar has run. Never a partial average dressed as total. */
  score: number | null;
  pillars: PillarScore[];
  measuredCount: number;
  pillarCount: number;
  /** One line under the headline, e.g. "Technical 82 · Content not measured · …". */
  breakdown: string;
  /** The heaviest failing checks across measured pillars, worst first. */
  topDeductions: PillarScore["deductions"];
}

const GRADED: Severity[] = ["ok", "warn", "error"];

function rowsOf(report: ScanReport | null | undefined, group: string): ReportRow[] {
  const rows = (report as Record<string, unknown> | null | undefined)?.[group];
  return Array.isArray(rows) ? (rows as ReportRow[]) : [];
}

export function pillarScore(report: ScanReport | null | undefined, def: PillarDef): PillarScore {
  let passedWeight = 0;
  let totalWeight = 0;
  const deductions: PillarScore["deductions"] = [];

  for (const group of def.groups) {
    for (const row of rowsOf(report, group)) {
      const severity = row?.severity as Severity;
      // Info rows report a fact rather than a verdict, and an "unavailable.*"
      // row means the tool did not run — neither is a check the site failed.
      if (!GRADED.includes(severity) || String(row?.code ?? "").startsWith("unavailable.")) continue;
      const weight = weightOf(String(row.code ?? ""));
      totalWeight += weight;
      if (severity === "ok") passedWeight += weight;
      else deductions.push({
        code: String(row.code ?? ""), what: String(row.what ?? row.code ?? ""),
        severity, weight, group,
      });
    }
  }

  deductions.sort((a, b) => b.weight - a.weight || (a.severity === "error" ? -1 : 1));
  return {
    key: def.key, title: def.title, weight: def.weight, howToMeasure: def.howToMeasure,
    measured: totalWeight > 0,
    score: totalWeight > 0 ? Math.round((100 * passedWeight) / totalWeight) : null,
    passedWeight, totalWeight, deductions,
  };
}

export function overallScore(report: ScanReport | null | undefined): OverallScore {
  const pillars = OVERALL_PILLARS.map((def) => pillarScore(report, def));
  const measured = pillars.filter((p) => p.measured);

  // Option A, deliberately: no Overall Score until every pillar has run. A
  // partial composite reads as a verdict on the whole site, and the pillars
  // nobody measured are exactly the ones a client would assume were fine.
  const complete = measured.length === pillars.length;
  const score = complete
    ? Math.round(pillars.reduce((sum, p) => sum + (p.score ?? 0) * p.weight, 0) /
                 pillars.reduce((sum, p) => sum + p.weight, 0))
    : null;

  const breakdown = pillars
    .map((p) => (p.measured ? `${p.title} ${p.score}` : `${p.title} not measured`))
    .join(" · ");

  const topDeductions = measured
    .flatMap((p) => p.deductions)
    .sort((a, b) => b.weight - a.weight || (a.severity === "error" ? -1 : 1))
    .slice(0, 8);

  return { score, pillars, measuredCount: measured.length, pillarCount: pillars.length, breakdown, topDeductions };
}
