import type { ClientWithStats, ScanRow, RemediationRow } from "@/lib/db";

export type ReaiTab =
  | "Overview"
  | "Traffic Analytics"
  | "Organic Research"
  | "Keyword Gap"
  | "Backlink Gap"
  | "Keyword Data Lab"
  | "Keyword Magic Tool"
  | "Data Lab & Backlinks"
  | "Backlink Audit"
  | "Site Health & Audit"
  | "Auto-Fix Engine"
  | "On-Page SEO"
  | "SERP Optimizer"
  | "Local SEO & GBP"
  | "AI & AEO Lab"
  | "All Tools Directory";

export type NavSubTab =
  // SEO Foundations
  | "Technical SEO"
  | "On-Page SEO"
  | "Content"
  | "Keywords & Rankings"
  | "Links"
  | "Local SEO"
  // AI Search Visibility (AEO)
  | "AI Readiness"
  | "AI Citations"
  | "Schema & Entities"
  | "Answer Content"
  | "AI Crawler Access"
  // Fix & Improve
  | "Priority Actions"
  | "Auto-Fix Review"
  | "Content Opportunities"
  | "Change History"
  // Reports & Settings
  | "Reports"
  | "Google Search Console"
  | "Integrations"
  | "Project Settings";

export const TAB_ROUTES: Record<ReaiTab, string> = {
  "Overview": "/",
  "Traffic Analytics": "/traffic-analytics",
  "Organic Research": "/organic-research",
  "Keyword Gap": "/keyword-gap",
  "Backlink Gap": "/backlink-gap",
  "Keyword Data Lab": "/keyword-data-lab",
  "Keyword Magic Tool": "/keyword-magic-tool",
  "Data Lab & Backlinks": "/backlink-analytics",
  "Backlink Audit": "/backlink-audit",
  "Site Health & Audit": "/site-audit",
  "Auto-Fix Engine": "/auto-fix",
  "On-Page SEO": "/on-page-seo",
  "SERP Optimizer": "/serp-preview",
  "Local SEO & GBP": "/local-seo",
  "AI & AEO Lab": "/ai-aeo",
  "All Tools Directory": "/tools",
};

export const ROUTE_TO_TAB: Record<string, ReaiTab> = {
  "/": "Overview",
  "/overview": "Overview",
  "/traffic-analytics": "Traffic Analytics",
  "/traffic": "Traffic Analytics",
  "/organic-research": "Organic Research",
  "/keyword-gap": "Keyword Gap",
  "/backlink-gap": "Backlink Gap",
  "/keyword-data-lab": "Keyword Data Lab",
  "/ranked-keywords": "Keyword Data Lab",
  "/keyword-magic-tool": "Keyword Magic Tool",
  "/keyword-magic": "Keyword Magic Tool",
  "/backlink-analytics": "Data Lab & Backlinks",
  "/backlinks": "Data Lab & Backlinks",
  "/backlink-audit": "Backlink Audit",
  "/site-audit": "Site Health & Audit",
  "/audit": "Site Health & Audit",
  "/auto-fix": "Auto-Fix Engine",
  "/autofix": "Auto-Fix Engine",
  "/remediation": "Auto-Fix Engine",
  "/on-page-seo": "On-Page SEO",
  "/onpage": "On-Page SEO",
  "/serp-preview": "SERP Optimizer",
  "/serp": "SERP Optimizer",
  "/local-seo": "Local SEO & GBP",
  "/local": "Local SEO & GBP",
  "/gbp": "Local SEO & GBP",
  "/ai-aeo": "AI & AEO Lab",
  "/aeo": "AI & AEO Lab",
  "/tools": "All Tools Directory",
};

export type DataStatusBadge =
  | "Estimated"
  | "Demo data"
  | "Needs Google Search Console connection"
  | "Not yet verified"
  | "Live verified";

export interface TechnicalDetailBlock {
  title: string;
  category: "JSON-LD" | "Crawler Rules" | "Lighthouse Diagnostics" | "Content Analysis" | "HTTP & Headers";
  summary: string;
  codeSnippet?: string;
  metrics?: Record<string, string | number>;
}

export interface PriorityItem {
  id: string;
  title: string;
  category: "SEO" | "AI Search" | "SEO + AI";
  severity: "critical" | "warning" | "info";
  problem: string;
  whyItMatters: string;
  recommendedAction: string;
  actionLabel: string; // e.g. "Review fix", "Review schema", "Create brief"
  actionTab?: ReaiTab;
  actionSubTab?: NavSubTab;
  expectedOutcome: string;
  source: string; // e.g. "Site Audit", "AI Crawler Probe"
  confidence: "High" | "Medium" | "Estimated";
  isAutoFixable: boolean;
  technicalDetails: TechnicalDetailBlock;
}

/**
 * Re-exported from `lib/journey`, which owns both the step shape and the rules
 * that assign a status to one. Two definitions would let a status exist here
 * that nothing can derive.
 */
export type { JourneyStep as ProjectJourneyStep } from "../../lib/journey";
