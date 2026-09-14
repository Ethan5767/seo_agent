/**
 * Spend control for paid scanner tools.
 *
 * `/api/scan` used to strip every paid tool unconditionally ("enforce zero
 * spend"). That kept the bill at zero and also kept eight of the twenty-three
 * tools permanently dark - the eight that back every competitive and keyword
 * screen. A blanket ban is not a budget; this is.
 *
 * A full paid run is about $0.52 (see PAID_TOOL_COSTS). The daily cap is
 * therefore expressed in whole scans as much as in dollars.
 *
 * Costs here mirror `pipeline/scanner/server.py`. `tests/budget.test.mjs`
 * asserts they still match, because a silent drift would let a run exceed the
 * cap it was checked against.
 */

/** Per-run cost in USD, keyed by the scanner's tool key. */
export const PAID_TOOL_COSTS: Record<string, number> = {
  site: 0.006,
  ai: 0.11,
  backlinks: 0.025,
  keywords: 0.18,
  rankings: 0.045,
  rank_trend: 0.13,
  gbp: 0.006,
  mentions: 0.03,
};

/** Every paid tool run once. */
export const FULL_SCAN_COST = Object.values(PAID_TOOL_COSTS).reduce((a, b) => a + b, 0);

/** Default ceiling per user per UTC day. Override with SCAN_DAILY_BUDGET_USD. */
export const DEFAULT_DAILY_BUDGET_USD = 5;

export function dailyBudgetUsd(env: Record<string, string | undefined> = process.env): number {
  const raw = env.SCAN_DAILY_BUDGET_USD;
  if (raw === undefined || raw === "") return DEFAULT_DAILY_BUDGET_USD;
  const n = Number(raw);
  // A malformed or negative value must not silently widen the cap.
  if (!Number.isFinite(n) || n < 0) return DEFAULT_DAILY_BUDGET_USD;
  return n;
}

export function isPaidTool(key: string): boolean {
  return Object.prototype.hasOwnProperty.call(PAID_TOOL_COSTS, key);
}

/** What a requested tool list would cost, counting only paid tools. */
export function estimateCost(tools: readonly string[]): number {
  return tools.reduce((sum, t) => sum + (PAID_TOOL_COSTS[t] ?? 0), 0);
}

export interface BudgetDecision {
  /** Tools that may run, free ones included, in the order requested. */
  allowed: string[];
  /** Paid tools dropped because the cap would be exceeded. */
  blocked: string[];
  /** Estimated cost of `allowed`. */
  estimatedCost: number;
  spentToday: number;
  budget: number;
  remaining: number;
  /** Set when at least one paid tool was dropped. */
  reason?: string;
}

/**
 * Decide which of the requested tools may run.
 *
 * Free tools always run: they cost nothing, so no budget can justify blocking
 * them. Paid tools are admitted in the order requested, cheapest-first within
 * that order is deliberately NOT applied - reordering would silently change
 * which findings a caller gets, and a partial run should be predictable.
 *
 * `requested` of `undefined` or an empty array means "the scanner's default
 * selection", which the scanner resolves; there is nothing to decide here, so
 * the paid set is admitted only if the whole run fits.
 */
export function applyBudget(
  requested: readonly string[] | undefined,
  spentToday: number,
  budget: number,
): BudgetDecision {
  const spent = Number.isFinite(spentToday) && spentToday > 0 ? spentToday : 0;
  const cap = Number.isFinite(budget) && budget > 0 ? budget : 0;
  const remaining = Math.max(0, cap - spent);

  // No explicit selection: admit the full paid set only if it fits whole. A
  // half-run nobody asked for is worse than a free-tools run they can retry.
  if (!requested || requested.length === 0) {
    const fits = FULL_SCAN_COST <= remaining;
    return {
      allowed: [],
      blocked: fits ? [] : Object.keys(PAID_TOOL_COSTS),
      estimatedCost: fits ? FULL_SCAN_COST : 0,
      spentToday: spent,
      budget: cap,
      remaining,
      reason: fits
        ? undefined
        : `Daily scan budget reached: $${spent.toFixed(2)} of $${cap.toFixed(2)} used. ` +
          `Paid tools are paused until tomorrow (UTC). Free tools still run.`,
    };
  }

  const allowed: string[] = [];
  const blocked: string[] = [];
  let running = 0;

  for (const tool of requested) {
    if (!isPaidTool(tool)) {
      allowed.push(tool);
      continue;
    }
    const cost = PAID_TOOL_COSTS[tool];
    if (running + cost <= remaining) {
      allowed.push(tool);
      running += cost;
    } else {
      blocked.push(tool);
    }
  }

  return {
    allowed,
    blocked,
    estimatedCost: Number(running.toFixed(4)),
    spentToday: spent,
    budget: cap,
    remaining: Number(remaining.toFixed(4)),
    reason: blocked.length
      ? `Daily scan budget would be exceeded: $${spent.toFixed(2)} of $${cap.toFixed(2)} ` +
        `already used today. Skipped ${blocked.length} paid tool(s): ${blocked.join(", ")}.`
      : undefined,
  };
}
