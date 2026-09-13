/**
 * The tool catalog, from the scanner.
 *
 * This replaces `app/toolsCatalogData.ts`, which declared 160 tools in its
 * header comment, actually held 148 entries, and was transcribed from a
 * document ("Sourced from Measure_Checks.docx"). None of its entries carried
 * any link to a tool that runs: no key, no implemented flag, nothing the
 * scanner would recognise. It was a wishlist rendered as an inventory, with a
 * count badge on it.
 *
 * The scanner declares what it actually has at `GET /api/tools`, which proxies
 * the Python catalog in `pipeline/scanner/server.py`. That is 23 tools running
 * 117 individual checks across 12 categories. Every one of them executes.
 *
 * The count is a count, never a constant: `summarize()` sums the catalog the
 * scanner returns, so this comment is the only place a number is written down
 * and the UI cannot inherit a stale one. It said 115 while the catalog returned
 * 117 from the day it was written.
 */

export interface ScannerTool {
  /** The scanner's own key, e.g. "seo", "backlinks". */
  key: string;
  label: string;
  category: string;
  /** "free" runs at no cost; "dataforseo" bills; "source" needs a repo. */
  group: "free" | "dataforseo" | "source" | string;
  /** Human-readable cost, e.g. "free" or "~$0.18". */
  cost: string;
  cost_num: number;
  phase: number;
  phase_label: string;
  /** The individual checks this tool runs. */
  checks: string[];
}

export interface CatalogSummary {
  tools: number;
  checks: number;
  categories: number;
  free: number;
  paid: number;
  /** Cost of running every paid tool once. */
  paidCostUsd: number;
}

/** Fetch the real catalog. Returns [] on any failure rather than inventing one. */
export async function fetchTools(): Promise<ScannerTool[]> {
  try {
    const res = await fetch("/api/tools", { cache: "no-store" });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data?.tools) ? (data.tools as ScannerTool[]) : [];
  } catch {
    return [];
  }
}

/** Headline figures for the directory. Counts only, never estimates. */
export function summarize(tools: ScannerTool[] | null | undefined): CatalogSummary {
  const out: CatalogSummary = {
    tools: 0,
    checks: 0,
    categories: 0,
    free: 0,
    paid: 0,
    paidCostUsd: 0,
  };
  if (!Array.isArray(tools)) return out;

  const cats = new Set<string>();
  for (const t of tools) {
    if (!t || typeof t !== "object") continue;
    out.tools += 1;
    out.checks += Array.isArray(t.checks) ? t.checks.length : 0;
    if (t.category) cats.add(t.category);
    if (t.group === "dataforseo") {
      out.paid += 1;
      out.paidCostUsd += Number(t.cost_num) || 0;
    } else {
      out.free += 1;
    }
  }
  out.categories = cats.size;
  out.paidCostUsd = Number(out.paidCostUsd.toFixed(4));
  return out;
}

/** Distinct categories, in the order the scanner lists them. */
export function categoriesOf(tools: ScannerTool[] | null | undefined): string[] {
  if (!Array.isArray(tools)) return [];
  const seen: string[] = [];
  for (const t of tools) {
    if (t?.category && !seen.includes(t.category)) seen.push(t.category);
  }
  return seen;
}

/** Filter by category and a free-text query over label, category and checks. */
export function filterTools(
  tools: ScannerTool[] | null | undefined,
  category: string,
  query: string,
): ScannerTool[] {
  if (!Array.isArray(tools)) return [];
  const q = (query || "").trim().toLowerCase();
  return tools.filter((t) => {
    if (!t || typeof t !== "object") return false;
    if (category && category !== "All" && t.category !== category) return false;
    if (!q) return true;
    const hay = [t.label, t.category, t.cost, ...(t.checks || [])]
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  });
}

/** What a tool costs to run, in words. */
export function costLabel(tool: ScannerTool): string {
  if (tool.group === "source") return "free · needs repo";
  return tool.cost || (tool.cost_num > 0 ? `~$${tool.cost_num}` : "free");
}
