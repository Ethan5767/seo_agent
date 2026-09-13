import { NextRequest, NextResponse } from "next/server";
import { spawn } from "node:child_process";
import {
  authenticateRequest,
  checkRateLimit,
  readJsonBodyWithLimit,
} from "@/lib/server-security";
import {
  CONTENT_SYSTEM_PROMPT,
  contentToolById,
  missingRequired,
  type ContentContext,
} from "@/lib/contentTools";

/**
 * Content drafting, through the Claude Code CLI.
 *
 * **The CLI, not the API.** This route used to call `@anthropic-ai/sdk` with an
 * `ANTHROPIC_API_KEY`, which is a separate metered account. Everything else in
 * this product that reaches a model shells out to `claude` instead -
 * `pipeline/audit/remediate.py:run_agent` and `pipeline/audit/seed_queries.py`
 * both do - so it runs on the operator's Claude subscription and costs nothing
 * per draft. One generator, one account, one place to change the model.
 *
 * Streams so a long draft cannot hit an HTTP timeout, and so the operator sees
 * text arriving rather than a spinner. The response is plain text, not JSON:
 * the client appends chunks straight into the editor.
 *
 * No DataForSEO, nothing against the scan budget. The inputs are the findings
 * and page copy the last scan already produced, plus what the operator typed.
 */

// Spawning a process needs the Node runtime; the edge runtime has no child_process.
export const runtime = "nodejs";

// Drafting only. The agent may not read or write the filesystem from here -
// remediation is the lane that edits a repo, and it runs under a tier with the
// gates watching. This one returns text.
const ALLOWED_TOOLS = "";

// A draft is long but bounded. Past this the request is wedged, not working.
const TIMEOUT_MS = 180_000;

export async function POST(req: NextRequest) {
  const auth = await authenticateRequest(req);
  if (!auth.user) {
    return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });
  }

  // Generation is the expensive call here, so it gets its own limit rather than
  // sharing the scan one.
  const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown-ip";
  const rl = checkRateLimit(`content:${auth.user.id || clientIp}`, 20, 60_000);
  if (!rl.allowed) {
    return NextResponse.json(
      { error: `Too many generations. Retry in ${rl.retryAfterSeconds}s.` },
      { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } },
    );
  }

  const { data: body, errorResponse } = await readJsonBodyWithLimit<any>(req, 256 * 1024);
  if (errorResponse) return errorResponse;

  const tool = contentToolById(String(body?.tool || ""));
  if (!tool) {
    return NextResponse.json({ error: "Unknown content tool." }, { status: 400 });
  }

  const values: Record<string, string> = {};
  for (const field of tool.fields) {
    values[field.name] = String(body?.values?.[field.name] ?? "");
  }

  const missing = missingRequired(tool, values);
  if (missing.length > 0) {
    return NextResponse.json(
      { error: `Fill in: ${missing.join(", ")}.` },
      { status: 400 },
    );
  }

  const context: ContentContext = {
    domain: typeof body?.context?.domain === "string" ? body.context.domain : undefined,
    business: typeof body?.context?.business === "string" ? body.context.business : undefined,
    keywords: Array.isArray(body?.context?.keywords)
      ? body.context.keywords.filter((k: unknown) => typeof k === "string").slice(0, 30)
      : undefined,
    // The scan's own output. These are what make a tool argue from a
    // measurement instead of from whatever was typed into the form.
    page: body?.context?.page && typeof body.context.page === "object" ? body.context.page : undefined,
    findings: Array.isArray(body?.context?.findings)
      ? body.context.findings.filter((f: unknown) => f && typeof f === "object").slice(0, 200)
      : undefined,
    queries: Array.isArray(body?.context?.queries)
      ? body.context.queries.filter((q: any) => q && typeof q.query === "string").slice(0, 200)
      : undefined,
  };

  // The prompt goes on STDIN, not argv: it opens with a markdown document and
  // the CLI's option parser reads a leading `---` as a malformed flag. Learned
  // the same way in remediate.run_agent, whose comment says so.
  const prompt = `${CONTENT_SYSTEM_PROMPT}\n\n---\n\n${tool.buildPrompt(values, context)}`;

  try {
    const child = spawn(
      "claude",
      ["-p", "--model", "sonnet", "--allowedTools", ALLOWED_TOOLS],
      { stdio: ["pipe", "pipe", "pipe"] },
    );

    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        let stderr = "";
        let wrote = false;
        let closed = false;
        const close = () => {
          if (!closed) {
            closed = true;
            controller.close();
          }
        };

        // Closing the tab kills the agent rather than leaving it running with
        // nobody reading - the same reason /remediate/apply streams.
        const timer = setTimeout(() => {
          child.kill("SIGTERM");
          controller.enqueue(encoder.encode("\n\n_Generation timed out after 3 minutes._"));
          close();
        }, TIMEOUT_MS);

        child.stdout.on("data", (chunk: Buffer) => {
          wrote = true;
          controller.enqueue(encoder.encode(chunk.toString()));
        });
        // stderr is kept for the failure message rather than streamed into the
        // draft: CLI progress notes are not content.
        child.stderr.on("data", (chunk: Buffer) => {
          stderr = (stderr + chunk.toString()).slice(-2000);
        });

        child.on("error", (err: NodeJS.ErrnoException) => {
          clearTimeout(timer);
          controller.enqueue(encoder.encode(
            err.code === "ENOENT"
              ? "\n\n_`claude` is not on PATH for the web server. Install the Claude Code CLI and sign in; this product drafts through your Claude subscription, not an API key._"
              : `\n\n_Generation failed: ${err.message}_`,
          ));
          close();
        });

        child.on("close", (code: number | null) => {
          clearTimeout(timer);
          // A non-zero exit having produced nothing is the case worth naming:
          // an empty 200 reads as "Claude had nothing to say".
          if (code !== 0 && !wrote) {
            controller.enqueue(encoder.encode(
              `\n\n_Generation failed (claude exited ${code}). ${stderr.trim().slice(-400) || "No output."}_`,
            ));
          }
          close();
        });

        child.stdin.on("error", () => { /* the child died first; `close` reports it */ });
        child.stdin.end(prompt);
      },
      cancel() {
        child.kill("SIGTERM");
      },
    });

    return new NextResponse(body, {
      status: 200,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-cache",
      },
    });
  } catch (err: any) {
    // Spawn failures that are not ENOENT (no shell, EPERM) land here.
    return NextResponse.json(
      { error: err?.message || "Could not start the Claude CLI." },
      { status: 500 },
    );
  }
}
