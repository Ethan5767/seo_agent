import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
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
 * Content drafting, through Claude.
 *
 * Streams so a long draft cannot hit an HTTP timeout, and so the operator sees
 * text arriving rather than a spinner. The response is plain text, not JSON:
 * the client appends chunks straight into the editor.
 *
 * No DataForSEO, no cost against the scan budget. The only inputs are what the
 * operator typed and keyword rows the last scan already paid for.
 */

// Long-form drafts, streamed, so there is room to finish a thought.
const MAX_TOKENS = 16000;

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

  // An unset key is a configuration gap, not a failure to hide behind a
  // generic 500. Say which variable is missing.
  if (!process.env.ANTHROPIC_API_KEY) {
    return NextResponse.json(
      {
        error:
          "Content tools need ANTHROPIC_API_KEY in the web environment. The pipeline's Claude Code runs on its own credentials; this route calls the API directly and needs its own key.",
      },
      { status: 501 },
    );
  }

  const context: ContentContext = {
    domain: typeof body?.context?.domain === "string" ? body.context.domain : undefined,
    business: typeof body?.context?.business === "string" ? body.context.business : undefined,
    keywords: Array.isArray(body?.context?.keywords)
      ? body.context.keywords.filter((k: unknown) => typeof k === "string").slice(0, 30)
      : undefined,
  };

  const client = new Anthropic();

  try {
    const stream = client.messages.stream({
      model: "claude-opus-5",
      max_tokens: MAX_TOKENS,
      // The system prompt is identical on every request, so caching it means
      // only the operator's own input is billed at full rate.
      system: [
        {
          type: "text",
          text: CONTENT_SYSTEM_PROMPT,
          cache_control: { type: "ephemeral" },
        },
      ],
      thinking: { type: "adaptive" },
      messages: [{ role: "user", content: tool.buildPrompt(values, context) }],
    });

    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      async start(controller) {
        try {
          for await (const event of stream) {
            if (
              event.type === "content_block_delta" &&
              event.delta.type === "text_delta"
            ) {
              controller.enqueue(encoder.encode(event.delta.text));
            }
          }
          const final = await stream.finalMessage();
          // A safety decline arrives as a 200 with stop_reason "refusal", so it
          // has to be checked rather than assumed away.
          if (final.stop_reason === "refusal") {
            controller.enqueue(
              encoder.encode(
                "\n\n_Claude declined this request. Rephrase the brief, or write this section by hand._",
              ),
            );
          }
        } catch (err: any) {
          controller.enqueue(
            encoder.encode(`\n\n_Generation failed: ${err?.message || "unknown error"}_`),
          );
        } finally {
          controller.close();
        }
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
    if (err instanceof Anthropic.AuthenticationError) {
      return NextResponse.json(
        { error: "ANTHROPIC_API_KEY was rejected. Check the key in the web environment." },
        { status: 401 },
      );
    }
    if (err instanceof Anthropic.RateLimitError) {
      return NextResponse.json(
        { error: "Claude is rate limiting this key. Try again shortly." },
        { status: 429 },
      );
    }
    if (err instanceof Anthropic.APIConnectionError) {
      return NextResponse.json(
        { error: "Could not reach the Claude API. Check network access." },
        { status: 502 },
      );
    }
    return NextResponse.json(
      { error: err?.message || "Generation failed." },
      { status: 500 },
    );
  }
}
