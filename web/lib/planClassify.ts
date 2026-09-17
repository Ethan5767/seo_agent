import { spawn } from "node:child_process";

/**
 * planClassify — turn a raw finding into a plan classification.
 *
 * TWO PATHS, ONE SHAPE.
 * ---------------------
 * `heuristicClass` is the deterministic keyword fallback that used to be the
 * only thing the Plan route had: it reads substrings of the code and decides a
 * tier and an impact ("anything mentioning schema is T3", "anything with
 * `title` is T1"). It is fast, offline, and dumb — it cannot argue from the
 * finding's own evidence, and it cannot write a fix.
 *
 * `classifyWithClaude` sends the whole worklist to the operator's Claude (the
 * `claude` CLI on their subscription, the same rail `/api/fix/advise` and
 * `/api/content/generate` use) and gets back a per-finding tier, impact, an
 * agent-can-take verdict, and a grounded one-line "what to do". It returns null
 * on ANY failure — no CLI, bad JSON, timeout, non-zero exit — so the caller
 * falls back to the heuristic and the plan never breaks. Claude is an upgrade to
 * the classification, never a dependency of it.
 *
 * Both produce the same {@link PlanClass} shape, so the route overlays one over
 * the other field-for-field.
 */

export type Impact = "Critical Blocker" | "High Impact" | "Medium" | "Quick Win";

export interface PlanClass {
  tier: number;
  tierLabel: string;
  impact: Impact;
  priorityScore: number;
  /** Claude's verdict: is this a mechanical fix an agent can apply in-tier. */
  agentCanTake?: boolean;
  /** One grounded, actionable line. Unknown facts come back as `[confirm: ...]`. */
  whatToDo?: string;
  /** Short why-this-tier/impact, for the reader of the item. */
  reason?: string;
}

const TIER_LABELS: Record<number, string> = {
  1: "T1: Copy Only",
  2: "T2: Content",
  3: "T3: Full Scope",
};

export function tierLabel(tier: number): string {
  return TIER_LABELS[tier] || TIER_LABELS[3];
}

// ── the deterministic fallback (the old getFindingTier / getFindingImpact) ────

export function heuristicClass(
  code: string,
  what: string,
  category: string,
  severity: string,
): PlanClass {
  const c = (code + " " + what + " " + category).toLowerCase();

  let tier = 3;
  if (
    c.includes("title") || c.includes("description") || c.includes("meta") ||
    c.includes("alt") || c.includes("h1") || c.includes("h2") ||
    c.includes("heading") || c.includes("copy")
  ) {
    tier = 1;
  } else if (
    c.includes("content") || c.includes("article") || c.includes("blog") ||
    c.includes("faq") || c.includes("eeat") || c.includes("bio") ||
    c.includes("author") || c.includes("entity")
  ) {
    tier = 2;
  }

  const lc = code.toLowerCase();
  let impact: Impact = "Quick Win";
  let priorityScore = 40;
  if (lc.includes("robots") || lc.includes("500") || lc.includes("404") || lc.includes("noindex")) {
    impact = "Critical Blocker";
    priorityScore = 100;
  } else if (severity === "error" || lc.includes("title") || lc.includes("lcp") || lc.includes("canonical")) {
    impact = "High Impact";
    priorityScore = 80;
  } else if (lc.includes("schema") || lc.includes("alt") || lc.includes("inp") || lc.includes("cls")) {
    impact = "Medium";
    priorityScore = 60;
  }

  return { tier, tierLabel: tierLabel(tier), impact, priorityScore };
}

// ── the Claude path ───────────────────────────────────────────────────────────

export interface ClassifyContext {
  clientTier: number;
  domain: string;
  business: string;
}

interface FindingLike {
  code?: string;
  what?: string;
  why?: string;
  fix?: string;
  detail?: string;
  category?: string;
  severity?: string;
  status?: string; // lane
  location?: string;
  url?: string;
}

const IMPACTS: Impact[] = ["Critical Blocker", "High Impact", "Medium", "Quick Win"];
const IMPACT_SCORE: Record<Impact, number> = {
  "Critical Blocker": 100,
  "High Impact": 80,
  "Medium": 60,
  "Quick Win": 40,
};

const TIMEOUT_MS = 90_000;

function buildPrompt(items: FindingLike[], ctx: ClassifyContext): string {
  const findings = items.map((f) => ({
    code: f.code || "",
    what: f.what || "",
    why: f.why || "",
    fix: f.fix || "",
    detail: (f.detail || "").slice(0, 400),
    severity: f.severity || "",
    lane: f.status || "",
    page: f.location || f.url || "",
  }));

  return `You are the planning brain of an SEO/AEO remediation pipeline. You are given the findings from one live-site scan. For EACH finding, decide four things, grounded ONLY in the finding's own evidence.

CLIENT
  business: ${ctx.business}
  domain:   ${ctx.domain}
  tier:     T${ctx.clientTier}  (this is the client's authority ceiling; see the tier ladder below)

THE TIER LADDER — what the agent is ALLOWED to touch, not how hard the fix is
  T1  copy only     edit existing text in place: <title>, meta description, alt text, heading text, on-page wording. No new files, no template/routing/layout/script changes.
  T2  content       T1, plus writing NEW page content into a declared content location.
  T3  full scope    templates, routing, layout, JSON-LD/schema injection, analytics tags, scripts, performance, anything structural.
  Pick the LOWEST tier whose allow-list can actually reach the fix. A tag that lives in a shared layout/head is T3 even if it is "just one line".

IMPACT — one of exactly: ${IMPACTS.join(" | ")}
  Critical Blocker = deindexing / not crawlable / 4xx-5xx / noindex.
  High Impact = title/canonical/LCP and other primary ranking signals.
  Medium = schema, alt text, secondary signals.
  Quick Win = small polish, low individual effect.

agentCanTake (boolean) — TRUE only when ALL hold:
  1. the fix is mechanical and additive/idempotent (re-running it is safe),
  2. its tier is <= the client tier T${ctx.clientTier},
  3. success is verifiable by re-measuring the page (the finding stops firing).
  FALSE for judgement calls (which of several canonicals wins, rewriting for "quality", URL changes that need redirects, creating a Google Business Profile, earning backlinks, anything off-site or requiring facts we do not have).

whatToDo — ONE actionable sentence a developer can execute. Ground it in this finding's evidence.
  DERIVATION ONLY: never invent a number, name, address, rating or URL. If a fact is needed that the finding does not contain, write it as [confirm: what you need]. No em dashes.

reason — a short clause: why this tier and impact.

Return STRICT JSON and nothing else: an array, one object per finding, in the same order:
[{"code": "...", "tier": 1, "impact": "High Impact", "agentCanTake": true, "whatToDo": "...", "reason": "..."}]

FINDINGS:
${JSON.stringify(findings, null, 2)}`;
}

function parseClassJson(raw: string): Array<Record<string, unknown>> | null {
  let text = raw.trim();
  // Strip a ```json fence if the model wrapped it despite the instruction.
  const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) text = fence[1].trim();
  // Otherwise clip to the outermost array.
  if (!text.startsWith("[")) {
    const start = text.indexOf("[");
    const end = text.lastIndexOf("]");
    if (start === -1 || end === -1 || end <= start) return null;
    text = text.slice(start, end + 1);
  }
  try {
    const parsed = JSON.parse(text);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function coerce(row: Record<string, unknown>): PlanClass | null {
  const code = typeof row.code === "string" ? row.code : "";
  if (!code) return null;
  let tier = Number(row.tier);
  if (![1, 2, 3].includes(tier)) tier = 3;
  const impact = IMPACTS.includes(row.impact as Impact) ? (row.impact as Impact) : "Quick Win";
  return {
    tier,
    tierLabel: tierLabel(tier),
    impact,
    priorityScore: IMPACT_SCORE[impact],
    agentCanTake: Boolean(row.agentCanTake),
    whatToDo: typeof row.whatToDo === "string" ? row.whatToDo : undefined,
    reason: typeof row.reason === "string" ? row.reason : undefined,
  };
}

/**
 * Classify the worklist with the operator's Claude, through the `claude` CLI on
 * their subscription (ambient auth, exactly like `/api/fix/advise`). Keyed by
 * finding code so the caller overlays it onto matching items. Returns null on
 * any failure — the caller must fall back to {@link heuristicClass}.
 */
export function classifyWithClaude(
  items: FindingLike[],
  ctx: ClassifyContext,
): Promise<Map<string, PlanClass> | null> {
  if (items.length === 0) return Promise.resolve(null);

  const prompt = buildPrompt(items, ctx);

  return new Promise((resolve) => {
    let child: ReturnType<typeof spawn>;
    try {
      child = spawn("claude", ["-p", "--model", "sonnet", "--allowedTools", ""], {
        stdio: ["pipe", "pipe", "pipe"],
      });
    } catch {
      resolve(null);
      return;
    }

    let stdout = "";
    let settled = false;
    const done = (val: Map<string, PlanClass> | null) => {
      if (settled) return;
      settled = true;
      resolve(val);
    };

    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      done(null);
    }, TIMEOUT_MS);

    child.stdout?.on("data", (c: Buffer) => { stdout += c.toString(); });
    child.stderr?.on("data", () => { /* progress notes; the exit code is the signal */ });

    child.on("error", () => { clearTimeout(timer); done(null); });

    child.on("close", (code: number | null) => {
      clearTimeout(timer);
      if (code !== 0) { done(null); return; }
      const rows = parseClassJson(stdout);
      if (!rows) { done(null); return; }
      const map = new Map<string, PlanClass>();
      for (const row of rows) {
        const cls = coerce(row as Record<string, unknown>);
        if (cls) map.set(String((row as Record<string, unknown>).code), cls);
      }
      done(map.size > 0 ? map : null);
    });

    child.stdin?.on("error", () => { /* died first; close handles it */ });
    child.stdin?.end(prompt);
  });
}
