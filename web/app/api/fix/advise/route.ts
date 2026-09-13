import { spawn } from "node:child_process";
import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";
import { buildFixPrompt, FIX_SYSTEM_PROMPT } from "@/lib/fixAdvisor";

/**
 * Findings in, the actual fix out.
 *
 * The automation claim rests on this. Every screen could already tell you what
 * was wrong and then stopped, leaving the operator to go and do it by hand -
 * which is the definition of not automated.
 *
 * Runs on the Claude Code CLI, not the API: everything else in this product that
 * reaches a model shells out to `claude` (`pipeline/audit/remediate.py`,
 * `pipeline/audit/seed_queries.py`, `/api/content/generate`), so it runs on the
 * operator's subscription rather than a separately metered account.
 *
 * `--allowedTools ""` because this returns TEXT. It must not touch a
 * filesystem: editing a repo is remediation's lane, and that runs inside a
 * declared tier with the gates watching. A route that can both read findings and
 * write files is a different security question entirely.
 */
export const runtime = "nodejs";

const ALLOWED_TOOLS = "";
const TIMEOUT_MS = 180_000;

export async function POST(req: NextRequest) {
  const auth = await authenticateRequest(req);
  if (!auth.user) {
    return NextResponse.json({ error: auth.error || "Sign in to generate fixes." }, { status: 401 });
  }

  // A model call per request. Tighter than the read-only routes.
  const limit = checkRateLimit(`fix-advise:${auth.user.id}`, 10, 60_000);
  if (!limit.allowed) {
    return NextResponse.json(
      { error: `Too many fix requests. Retry in ${limit.retryAfterSeconds}s.` },
      { status: 429, headers: { "Retry-After": String(limit.retryAfterSeconds) } },
    );
  }

  const parsed = await readJsonBodyWithLimit<any>(req, 256 * 1024);
  if (parsed.errorResponse) return parsed.errorResponse;
  const body = parsed.data ?? {};

  const built = buildFixPrompt(body.findings, {
    business: typeof body.business === "string" ? body.business : undefined,
    domain: typeof body.domain === "string" ? body.domain : undefined,
    facts: body.facts && typeof body.facts === "object" ? body.facts : undefined,
  });

  // No findings is a refusal, not an empty answer. A fix plan for a site nobody
  // measured is this session's whole bug class, with a model's fluency on top.
  if ("error" in built) {
    return NextResponse.json({ error: built.error }, { status: 400 });
  }

  // STDIN, not argv: the prompt opens with a markdown document and the CLI's
  // option parser reads a leading `---` as a malformed flag. Learned the same
  // way in remediate.run_agent, whose comment says so.
  const prompt = `${FIX_SYSTEM_PROMPT}\n\n---\n\n${built.prompt}`;

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
              ? "The `claude` CLI is not on PATH. This product drafts through the Claude subscription, not an API key."
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
        // Closing the tab kills the model run rather than leaving it going with
        // nobody reading.
        child.kill("SIGTERM");
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Findings-Count": String(built.count),
      },
    });
  } catch (err: any) {
    return NextResponse.json({ error: err?.message || "Could not start the Claude CLI." }, { status: 500 });
  }
}
