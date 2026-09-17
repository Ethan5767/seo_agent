import { spawn } from "node:child_process";
import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";

/**
 * Brainstorm the plan with Claude — as a conversation, the way the Superpowers
 * "brainstorming" skill works.
 *
 * The rest of the Plan stage decides, per finding, a tier and whether the agent
 * can take it (`/api/plan` + `lib/planClassify`). This is the "so what do we
 * actually do this cycle" DIALOGUE: Claude asks the operator one question at a
 * time (goals, time budget, who does the work, priorities), proposes a couple of
 * approaches with trade-offs, and converges on an agreed plan of attack. It is
 * turn-based, not a one-shot report — the client sends the running transcript and
 * gets the next message back.
 *
 * Same rail as `/api/fix/advise` and `/api/content/generate`: the `claude` CLI on
 * the operator's subscription (ambient auth), `--allowedTools ""` because it
 * returns TEXT and must never touch a filesystem. Each turn is streamed. The CLI
 * is single-shot, so the whole transcript is replayed in the prompt each turn —
 * that is how the conversation keeps its memory.
 */
export const runtime = "nodejs";

const ALLOWED_TOOLS = "";
const TIMEOUT_MS = 180_000;

// A worklist item, trimmed to what a strategist needs. Anything else is noise in
// the prompt.
interface Item {
  code?: string;
  what?: string;
  status?: string; // lane: NEW / PERSISTING / REGRESSION
  impact?: string;
  tierLabel?: string;
  inScope?: boolean;
  agentCanTake?: boolean;
  whatToDo?: string;
  fix?: string;
  location?: string;
  url?: string;
  note?: string;
}

// The brainstorming method (from the Superpowers "brainstorming" skill),
// specialised to a remediation cycle. Claude is a facilitator, not a report
// generator: it drives a short dialogue toward an agreed plan.
const SYSTEM_PROMPT = `You are a senior SEO/AEO strategist running a BRAINSTORM with the operator to decide how to spend ONE remediation cycle. You are given the planned worklist from a live-site scan. Work like a good design conversation, not a report.

METHOD (follow it)
- Ask ONE question at a time. Never a wall of questions. Prefer multiple choice (A/B/C) so it is fast to answer.
- Understand before proposing: the operator's goal this cycle, how much time/effort they have, who does the work (the agent vs a person), and what they care most about moving.
- After you understand enough, propose 2-3 approaches with trade-offs and say which you recommend and why.
- Converge. When the operator has chosen a direction, output the agreed plan under a heading "## Cycle Plan" — a short ranked list of what to tackle, in order, each with one line of why, plus a short "Needs a person" list for items the agent cannot take. Then stop.
- Be decisive and brief. This is a working chat: two to four short paragraphs or a tight list per turn, never more.

GROUNDING
- Everything you say must trace to the worklist below or to what the operator tells you. Do not invent findings, traffic numbers, or facts about the business. If you need a fact you were not given, ask for it or write [confirm: ...].
- Prefer items that are in-tier AND the agent can take (fast, verifiable, reversible) when recommending what to do first, unless the operator steers otherwise.
- No em dashes in the prose.

OPENING
- If there is no conversation yet, open with ONE short line orienting the operator (how many items, the rough split of quick wins vs high-impact vs needs-a-person), then ask your FIRST question. Do not dump the whole plan up front.`;

interface Msg { role: "user" | "assistant"; content: string; }

function buildPrompt(
  items: Item[],
  ctx: { domain: string; business: string; tier: number; goal?: string },
  messages: Msg[],
): string {
  const rows = items.map((i) => ({
    code: i.code || "",
    what: i.what || "",
    lane: i.status || "",
    impact: i.impact || "",
    tier: i.tierLabel || "",
    inTier: i.inScope !== false,
    agentCanTake: i.agentCanTake,
    whatToDo: i.whatToDo || i.fix || "",
    page: i.location || i.url || "",
    note: i.note || "",
  }));

  // The CLI is single-shot, so the running transcript is replayed each turn.
  const transcript = messages.length
    ? messages.map((m) => `${m.role === "user" ? "OPERATOR" : "YOU"}: ${m.content}`).join("\n\n")
    : "(no messages yet — open per the OPENING rule)";

  return `${SYSTEM_PROMPT}

---

CLIENT
  business: ${ctx.business}
  domain:   ${ctx.domain}
  tier:     T${ctx.tier}
  goal:     ${ctx.goal || "organic + AI-engine visibility"}

WORKLIST (${rows.length} items):
${JSON.stringify(rows, null, 2)}

---

CONVERSATION SO FAR:
${transcript}

---

Write only YOUR next message. Follow the METHOD: one question at a time, or the "## Cycle Plan" if the operator has converged.`;
}

export async function POST(req: NextRequest) {
  const auth = await authenticateRequest(req);
  if (!auth.user) {
    return NextResponse.json({ error: auth.error || "Sign in to brainstorm." }, { status: 401 });
  }

  // A model call per request. Same budget as the other Claude routes.
  const limit = checkRateLimit(`plan-brainstorm:${auth.user.id}`, 10, 60_000);
  if (!limit.allowed) {
    return NextResponse.json(
      { error: `Too many brainstorms. Retry in ${limit.retryAfterSeconds}s.` },
      { status: 429, headers: { "Retry-After": String(limit.retryAfterSeconds) } },
    );
  }

  const parsed = await readJsonBodyWithLimit<any>(req, 512 * 1024);
  if (parsed.errorResponse) return parsed.errorResponse;
  const body = parsed.data ?? {};

  const items: Item[] = Array.isArray(body.worklist) ? body.worklist.slice(0, 200) : [];
  // No worklist is a refusal, not an empty answer. A strategy for a plan nobody
  // built is exactly the guess-with-a-model's-confidence this product avoids.
  if (items.length === 0) {
    return NextResponse.json(
      { error: "No worklist to brainstorm. Run the audit and build the plan first." },
      { status: 400 },
    );
  }

  // The running conversation. Empty on the first turn — Claude opens with its
  // first question. Trimmed to a sane cap so a long chat cannot blow the prompt.
  const messages: Msg[] = Array.isArray(body.messages)
    ? body.messages
        .filter((m: any) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string")
        .slice(-40)
        .map((m: any) => ({ role: m.role, content: String(m.content).slice(0, 8000) }))
    : [];

  const ctx = {
    domain: (typeof body.domain === "string" ? body.domain : "").replace(/^https?:\/\//, "").replace(/\/.*$/, "") || "the site",
    business: typeof body.business === "string" && body.business ? body.business : "the client",
    tier: Number(body.tier) || 1,
    goal: typeof body.goal === "string" ? body.goal : undefined,
  };

  const prompt = buildPrompt(items, ctx, messages);

  try {
    const child = spawn("claude", ["-p", "--model", "sonnet", "--allowedTools", ALLOWED_TOOLS], {
      stdio: ["pipe", "pipe", "pipe"],
    });

    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        let stderr = "";
        let wrote = false;
        let closed = false;
        const close = () => { if (!closed) { closed = true; controller.close(); } };

        const timer = setTimeout(() => {
          child.kill("SIGTERM");
          controller.enqueue(encoder.encode("\n\n_Timed out after 3 minutes._"));
          close();
        }, TIMEOUT_MS);

        child.stdout.on("data", (chunk: Buffer) => {
          wrote = true;
          controller.enqueue(encoder.encode(chunk.toString()));
        });
        child.stderr.on("data", (chunk: Buffer) => { stderr += chunk.toString(); });

        child.on("error", (err: any) => {
          clearTimeout(timer);
          controller.enqueue(encoder.encode(
            err?.code === "ENOENT"
              ? "The `claude` CLI is not on PATH. This product runs on the Claude subscription, not an API key."
              : `Could not start Claude: ${err?.message || "unknown"}`,
          ));
          close();
        });

        child.on("close", (code) => {
          clearTimeout(timer);
          if (!wrote) {
            controller.enqueue(encoder.encode(
              `Claude produced no output (exit ${code}).${stderr ? ` ${stderr.slice(0, 300)}` : ""}`,
            ));
          }
          close();
        });

        child.stdin.write(prompt);
        child.stdin.end();
      },
      cancel() {
        child.kill("SIGTERM");
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Worklist-Count": String(items.length),
      },
    });
  } catch (err: any) {
    return NextResponse.json({ error: err?.message || "Could not start the Claude CLI." }, { status: 500 });
  }
}
