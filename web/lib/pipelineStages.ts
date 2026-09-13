/**
 * The engine's stages, as the UI's own model of them.
 *
 * The product IS a pipeline — repo + domain in, gated pull request out — and
 * until now the sidebar did not say so. Measure had a screen, "Review Fixes"
 * had a screen, and the stages that decide whether work actually reaches a
 * client's site had no first-class place at all. The old "Pipeline" section was
 * a lid over two unrelated links; these four stages replace it.
 *
 * Each stage declares where its data comes from, because they are not in the
 * same state and pretending otherwise is how a dashboard starts lying:
 *
 *   plan   — live. `planState` carries worklist + lane counts; /api/plan wired.
 *   fix    — live. The Auto-Fix Engine screen already exists.
 *   gate   — live once the client's repo is connected. The 19 gates ARE the
 *            pull request's check runs, so reading them is reading the verdict.
 *            Merging lives on this screen too: merge is a button, not a stage —
 *            you look at what the gates said and then you act on it, and
 *            splitting that across two screens only adds a click between the
 *            evidence and the decision.
 *
 * `connected: false` is a promise about what a screen must NOT do. A stage with
 * no result renders its `absent` copy — never a zero, never a green tick. A gate
 * result nobody fetched must not look like a gate result that passed; that is
 * the rule the engine already applies to itself (exit 4, cannot judge).
 */

export type StageId = "plan" | "fix" | "gate";

export type PipelineStage = {
  id: StageId;
  label: string;
  /** Position in the run, 1-based, for the stepper. */
  step: number;
  /** One line: what this stage decides. */
  purpose: string;
  /** Does the web tier receive this stage's RESULT for a given run? */
  connected: boolean;
  /** Shown when there is no result. For unconnected stages, says why. */
  absent: string;
  /** What produces the data, named so an operator can go look. */
  source: string;
};

export const PIPELINE_STAGES: PipelineStage[] = [
  {
    id: "plan",
    label: "Plan",
    step: 1,
    purpose:
      "Sorts this cycle's findings against the last one — resolved, persisting, new, regression — and decides which the agent may attempt.",
    connected: true,
    absent:
      "No plan for this cycle yet. Run a scan, then Plan, to sort findings into lanes and build the worklist.",
    source: "wf-site-plan → worklist.json",
  },
  {
    id: "fix",
    label: "Fix",
    step: 2,
    purpose:
      "Claude Code edits the client's repo inside the tier, one work item at a time, and every change is measured from the git diff rather than trusted.",
    connected: true,
    absent:
      "Nothing has been fixed in this cycle yet. Plan first, then run the fixer — it will only attempt items inside the client's declared tier.",
    source: "wf-site-remediate → changelog.json",
  },
  {
    id: "gate",
    label: "Gate & Merge",
    step: 3,
    purpose:
      "19 checks run on the pull request the agent opened, and merging happens here. A red gate makes the merge impossible, not merely discouraged.",
    connected: true,
    absent:
      "No pull requests open for this client. The agent opens one when it has fixes to propose; connect the client's repository if you expect to see something here.",
    source: "the client repo's check runs, via GitHub",
  },
];

export function stage(id: StageId): PipelineStage {
  const found = PIPELINE_STAGES.find((s) => s.id === id);
  if (!found) throw new Error(`unknown pipeline stage: ${id}`);
  return found;
}

/* ── Gate roster ────────────────────────────────────────────────────────────
 * The gates the reusable workflow actually invokes, in run order, mirrored from
 * .github/workflows/quality-gate.reusable.yml. This is engine truth, not run
 * truth: it says what WILL run, never what did.
 *
 * `phase` matters to a reader. PRE gates judge the diff and the source before
 * anything is built; OUT gates judge the built HTML tree. An OUT gate with no
 * tree to read reports "cannot judge" (exit 4) rather than passing — the rule
 * that B-018 and B-027 were both filed under.
 */
export type GatePhase = "PRE" | "OUT";
export type GateSpec = { name: string; phase: GatePhase; blocks: string };

export const GATE_ROSTER: GateSpec[] = [
  { name: "tier-check", phase: "PRE", blocks: "the diff leaves the client's declared tier, or touches the deny floor" },
  { name: "claim-provenance", phase: "PRE", blocks: "a rating, licence number, year-count or review count with no source" },
  { name: "audit-ssr", phase: "PRE", blocks: "document/window used unguarded where it breaks server rendering" },
  { name: "rules-selftest", phase: "PRE", blocks: "the client's own rule ledger fails its fixtures" },
  { name: "tsc --noEmit", phase: "PRE", blocks: "the change does not typecheck" },
  { name: "check-headings", phase: "OUT", blocks: "a heading that is not Title Case" },
  { name: "orphan-check", phase: "OUT", blocks: "a page no other page links to" },
  { name: "parity-check", phase: "OUT", blocks: "sitemap, routes and llms.txt disagree" },
  { name: "em-dash-check", phase: "OUT", blocks: "an em dash in public-facing copy" },
  { name: "audit-built", phase: "OUT", blocks: "the 30-point built-HTML audit fails" },
  { name: "forbidden-sweep", phase: "OUT", blocks: "a banned phrase reaches the built site (legal)" },
  { name: "robots-aicrawler", phase: "OUT", blocks: "an AI citation crawler is blocked at the edge" },
  { name: "capsule-check", phase: "OUT", blocks: "a long page with no TL;DR capsule" },
  { name: "noncommodity-check", phase: "OUT", blocks: "pages that are near-duplicates of each other" },
  { name: "fingerprint-check", phase: "OUT", blocks: "invisible characters left in the output" },
  { name: "llms-sales-purge", phase: "OUT", blocks: "sales language in llms.txt" },
  { name: "image-budget", phase: "OUT", blocks: "an image over its tier's byte budget" },
  { name: "lcp-hygiene", phase: "OUT", blocks: "a hero image that will hurt LCP or CLS" },
  { name: "acceptance-check", phase: "OUT", blocks: "a fix the agent claimed did not actually land" },
];

/* ── Merge policy ───────────────────────────────────────────────────────────
 * Mirrored from pipeline/lib/automerge.py, whose policy dataclass is frozen so
 * the rails cannot be loosened by a stray assignment. Order matters: this is
 * escalate-when-unsure, and the FIRST condition that fails sends the change to
 * a human.
 */
export type MergeRule = { condition: string; otherwise: string };

export const MERGE_POLICY: MergeRule[] = [
  { condition: "Auto-merge is switched on for this client", otherwise: "auto-merge disabled for this client" },
  { condition: "Gate results exist at all", otherwise: "no gate results — nothing was verified" },
  { condition: "Every gate is green", otherwise: "gate(s) failed" },
  { condition: "The change is tier T1 (copy edits only)", otherwise: "tier not eligible for auto-merge" },
  { condition: "No new page was created", otherwise: "high-risk change (new page)" },
  { condition: "No medical, legal or financial claim in the text", otherwise: "high-risk change (YMYL claim)" },
];

/** Off for the entire fleet unless a client repo opts in. */
export const AUTOMERGE_DEFAULT_ENABLED = false;

/* ── Plan helpers ──────────────────────────────────────────────────────────── */

/** Lane counts for the Plan screen, from a worklist. Absent -> null, never 0. */
export function laneCounts(
  worklist: Array<{ status?: string }> | null | undefined
): { NEW: number; PERSISTING: number; REGRESSION: number; RESOLVED: number } | null {
  if (!Array.isArray(worklist) || worklist.length === 0) return null;
  const counts = { NEW: 0, PERSISTING: 0, REGRESSION: 0, RESOLVED: 0 };
  for (const item of worklist) {
    const key = (item?.status || "").toUpperCase();
    if (key in counts) counts[key as keyof typeof counts] += 1;
  }
  return counts;
}

/**
 * How many worklist items the agent may actually attempt.
 *
 * Reported separately from the total because they are wildly different numbers
 * and the gap is the honest story: a worklist of 40 where the agent can touch 6
 * is a 6-item cycle, and a summary that says 40 sets the wrong expectation.
 */
export function actionableCount(
  worklist: Array<{ tier_blocked?: boolean; human_edit?: boolean; action?: unknown }> | null | undefined
): number | null {
  if (!Array.isArray(worklist) || worklist.length === 0) return null;
  return worklist.filter((i) => i && i.action && !i.tier_blocked && !i.human_edit).length;
}

/** Why each item is not actionable, so the Plan screen can say so per row. */
export function blockedReason(item: {
  tier_blocked?: boolean;
  human_edit?: boolean;
  action?: unknown;
}): string | null {
  if (!item) return null;
  if (item.human_edit) return "briefed for a human editor";
  if (item.tier_blocked) return "above this client's tier";
  if (!item.action) return "no automated fix mapped to this finding";
  return null;
}
