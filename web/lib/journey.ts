/**
 * The project journey: which of the six stages a client has actually reached.
 *
 * This exists because the bar that renders it was decorative. `currentStep={4}`
 * was hardcoded at both call sites, and `Overview` additionally passed
 * `hasClient={true} hasScan={true}`, so an empty account was told it had
 * reached "Stage 4 of 6: Review Top Priorities" with three steps ticked green.
 * A progress indicator that renders a constant is worse than none: it reports
 * progress no one made.
 *
 * Two rules the shape follows:
 *
 * 1. **A stage is completed only where there is evidence for it.** Absence is
 *    never completion. Each step below names the artifact that proves it.
 * 2. **`current` is the lowest INCOMPLETE step, not the furthest reached.** The
 *    stages are not a strict sequence - an audit runs perfectly well without
 *    Search Console connected - so a bar that marched past a skipped step would
 *    stop asking for the one thing still missing.
 *
 * Pure, and total over bad input: every consumer of this renders a header, so a
 * malformed client row must produce an honest "stage 1" rather than a crash.
 */

export interface JourneyStep {
  id: number;
  label: string;
  description: string;
  status: "completed" | "current" | "upcoming";
}

/** The six stages, and the evidence each one requires. */
export const JOURNEY_STEPS: Omit<JourneyStep, "status">[] = [
  { id: 1, label: "Create Project", description: "Set domain & targets" },
  { id: 2, label: "Connect Google / Add Site", description: "Search Console & domain" },
  { id: 3, label: "Run Audit", description: "SEO & AI scan" },
  { id: 4, label: "Review Top Priorities", description: "Top actionable items" },
  { id: 5, label: "Review or Apply Fixes", description: "Staged fixes & schema" },
  { id: 6, label: "Track Results Over Time", description: "Rankings & visibility" },
];

export interface JourneyInput {
  /** The selected client row, if one is selected. */
  client?: { scans?: number } | null;
  /** Whether Search Console is connected for this account. */
  hasGsc?: boolean;
  /** The in-memory scan report, if a scan has been loaded or just run. */
  report?: Record<string, unknown> | null;
  /** Plan output: `{ worklist, resolved, counts }`. */
  plan?: { worklist?: unknown[] } | null;
  /** Rows from the remediation history table. */
  remediations?: unknown[] | null;
  /** The result of a remediation apply run in this session. */
  apply?: unknown;
}

export interface Journey {
  steps: JourneyStep[];
  /** The step to show as active: the lowest incomplete one, or 6 when done. */
  currentStep: number;
  /** True when every stage has its evidence. */
  complete: boolean;
}

/** Rows in a scan report live under per-tool keys; these are not tools. */
const NON_GROUP_KEYS = new Set(["score", "counts", "cost", "url", "domain", "status", "generated_at"]);

/** Does this report contain at least one row a person could act on? */
function reportHasFindings(report: unknown): boolean {
  if (!report || typeof report !== "object") return false;
  for (const [key, value] of Object.entries(report as Record<string, unknown>)) {
    if (NON_GROUP_KEYS.has(key) || !Array.isArray(value)) continue;
    for (const row of value) {
      if (row && typeof row === "object") return true;
    }
  }
  return false;
}

function isNonEmptyArray(v: unknown): boolean {
  return Array.isArray(v) && v.length > 0;
}

export function deriveJourney(input?: JourneyInput | null): Journey {
  const it: JourneyInput = input && typeof input === "object" ? input : {};
  const client = it.client && typeof it.client === "object" ? it.client : null;
  const scans = typeof client?.scans === "number" ? client.scans : 0;

  // A scan counts whether it is in memory or only recorded on the client row:
  // switching clients drops the report, and the work still happened.
  const scanned = reportHasFindings(it.report) || scans > 0;

  const done = [
    !!client,
    !!it.hasGsc,
    scanned,
    // Something to review means real findings - a clean scan has nothing to
    // triage, and claiming otherwise sends the operator to an empty screen.
    reportHasFindings(it.report) || isNonEmptyArray(it.plan?.worklist),
    isNonEmptyArray(it.remediations) || !!it.apply,
    // A trend needs two points. One scan is a reading, not a direction.
    scans >= 2,
  ];

  const firstIncomplete = done.indexOf(false);
  const complete = firstIncomplete === -1;
  const currentStep = complete ? JOURNEY_STEPS.length : firstIncomplete + 1;

  return {
    steps: JOURNEY_STEPS.map((step, i) => ({
      ...step,
      status: done[i] ? "completed" : step.id === currentStep ? "current" : "upcoming",
    })),
    currentStep,
    complete,
  };
}
