/**
 * Site Audit project-list metrics, Semrush-style: one row per project with
 * Site Health, errors, warnings and a score per theme (Crawlability, HTTPS,
 * International SEO, Site Performance, Internal Linking, AI Search, E-E-A-T).
 *
 * Every number is read from a saved scan report. A theme score is the share of
 * that theme's GRADED checks (ok / warn / error) that passed; info rows and
 * "did not run" rows are not graded. A theme with no graded check in the report
 * is `null`, shown as "Not measured", never 0% and never a guess.
 *
 * Theme membership is an explicit list of the codes the scanner actually emits
 * (taken from saved scans, 2026-09-14), so a percentage can be traced to rows.
 */

import { isNotRun } from "./reportViews.ts";

type Row = { code?: unknown; severity?: unknown; detail?: unknown };
type Report = Record<string, unknown> | null | undefined;

export type AuditTheme = { id: string; label: string; codes: string[] };

/** Entries ending in "." match a whole family (e.g. "aeo."). */
export const AUDIT_THEMES: AuditTheme[] = [
  {
    id: "crawlability", label: "Crawlability",
    codes: [
      "dfs.op.is_4xx_code", "dfs.op.is_5xx_code", "dfs.op.is_broken", "dfs.op.is_redirect", "dfs.op.is_orphan_page",
      "dfs.op.canonical", "dfs.op.canonical_chain", "dfs.op.canonical_to_broken", "dfs.op.canonical_to_redirect",
      "dfs.op.recursive_canonical", "site.duplicate_page_titles", "site.duplicate_meta_descriptions",
      "site.broken_internal_link", "site.orphan_page", "tech.xml_sitemap", "valid.sitemap_valid",
      "health.noindex_present", "health.canonical_mismatch", "tech.rendering_(crawler-visible_content)",
      "onpage.single_canonical",
    ],
  },
  {
    id: "https", label: "HTTPS",
    codes: ["tech.https", "dfs.op.is_https", "dfs.op.is_http", "dfs.op.https_to_http_links",
            "onpage.mixed_content", "onpage.external_link_safety", "eeat.https"],
  },
  {
    id: "intl", label: "Int. SEO",
    codes: ["valid.hreflang_set", "onpage.hreflang", "tech.language_declared"],
  },
  {
    id: "performance", label: "Site Performance",
    codes: ["lh.lighthouse_performance", "crux.", "dfs.op.high_loading_time", "dfs.op.high_waiting_time",
            "dfs.op.has_render_blocking_resources", "dfs.op.size_greater_than_3mb", "dfs.op.no_content_encoding",
            "onpage.render-blocking_scripts", "onpage.dom_size", "onpage.image_dimensions"],
  },
  {
    id: "linking", label: "Internal Linking",
    codes: ["tech.internal_links", "tech.anchor_text_quality", "tech.contextual_links", "tech.anchor_over-optimization",
            "tech.self-referencing_links", "site.broken_internal_link", "dfs.op.is_orphan_page",
            "onpage.empty_links", "onpage.link_volume", "lh.links_do_not_have_descriptive_text"],
  },
  { id: "ai", label: "AI Search Health", codes: ["aeo."] },
  { id: "eeat", label: "E-E-A-T", codes: ["eeat."] },
];

const NON_GROUP = new Set(["score", "counts", "cost", "log", "cycle", "url", "site_url", "page", "graded", "score_version"]);

function rowsOf(report: Report): Row[] {
  if (!report || typeof report !== "object") return [];
  const out: Row[] = [];
  const seen = new Set<string>();
  for (const [k, v] of Object.entries(report)) {
    if (NON_GROUP.has(k) || !Array.isArray(v)) continue;
    for (const r of v as Row[]) {
      if (!r || typeof r !== "object" || isNotRun(r as any)) continue;
      const key = `${String(r.code)}::${String((r as any).what ?? "")}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(r);
    }
  }
  return out;
}

const matches = (code: string, pattern: string) => (pattern.endsWith(".") ? code.startsWith(pattern) : code === pattern);

export type Share = { pct: number | null; passed: number; graded: number };

function share(rows: Row[]): Share {
  const graded = rows.filter((r) => r.severity === "ok" || r.severity === "warn" || r.severity === "error");
  const passed = graded.filter((r) => r.severity === "ok").length;
  return { pct: graded.length ? Math.round((100 * passed) / graded.length) : null, passed, graded: graded.length };
}

export type AuditSummary = {
  health: Share;
  errors: number;
  warnings: number;
  pagesCrawled: number | null;
  themes: Record<string, Share>;
};

export function summarizeAudit(report: Report): AuditSummary {
  const rows = rowsOf(report);
  const themes: Record<string, Share> = {};
  for (const t of AUDIT_THEMES) {
    themes[t.id] = share(rows.filter((r) => typeof r.code === "string" && t.codes.some((p) => matches(r.code as string, p))));
  }
  const crawled = rows.find((r) => r.code === "site.pages_crawled");
  const n = crawled ? parseInt(String(crawled.detail ?? ""), 10) : NaN;
  return {
    health: share(rows),
    errors: rows.filter((r) => r.severity === "error").length,
    warnings: rows.filter((r) => r.severity === "warn").length,
    pagesCrawled: Number.isFinite(n) ? n : null,
    themes,
  };
}

/** "+3", "-2", "±0", or "" when either side was not measured. */
export function delta(current: number | null | undefined, previous: number | null | undefined, unit = ""): string {
  if (current == null || previous == null) return "";
  const d = current - previous;
  return d === 0 ? `±0${unit}` : `${d > 0 ? "+" : ""}${d}${unit}`;
}
