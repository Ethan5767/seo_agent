// Server-side proxy to the Python backend (wf-scan-web). Runs on the Next
// server, so the browser never talks to the Python port directly — no CORS,
// and the backend URL stays server-side. Set PYTHON_API to override the default.
import { NextRequest, NextResponse } from "next/server";
import {
  authenticateRequest,
  getScopedDb,
  checkRateLimit,
  validateScanTargetUrlAsync,
  sanitizeScanOptions,
  readJsonBodyWithLimit,
} from "@/lib/server-security";
import { applyBudget, dailyBudgetUsd } from "@/lib/budget";
import { scannerPost, PYTHON_API, ScannerUnconfigured } from "@/lib/scannerFetch";


/**
 * What a user has already spent on scans today (UTC).
 *
 * `scans.cost` is written on every run, so the ledger already exists and no
 * migration is needed. RLS scopes the rows to the caller, so this is their own
 * spend and nobody else's.
 *
 * A failure here must not silently widen the cap: if the spend cannot be read,
 * it is reported as the full budget, which admits free tools and no paid ones.
 */
async function spentTodayUsd(
  db: ReturnType<typeof getScopedDb>,
  budget: number,
): Promise<{ spent: number; degraded: boolean }> {
  const since = new Date();
  since.setUTCHours(0, 0, 0, 0);
  try {
    const { data, error } = await db
      .from("scans")
      .select("cost")
      .gte("created_at", since.toISOString());
    if (error || !Array.isArray(data)) {
      return { spent: budget, degraded: true };
    }
    const spent = data.reduce(
      (sum: number, row: { cost?: number | string | null }) => sum + Number(row?.cost ?? 0),
      0,
    );
    return { spent: Number.isFinite(spent) ? spent : budget, degraded: !Number.isFinite(spent) };
  } catch {
    return { spent: budget, degraded: true };
  }
}

export async function GET(req: NextRequest) {
  const auth = await authenticateRequest(req);
  if (!auth.user) {
    return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });
  }
  const budget = dailyBudgetUsd();
  const db = getScopedDb(auth.user, auth.token);
  const { spent, degraded } = await spentTodayUsd(db, budget);
  return NextResponse.json({
    budget,
    spentToday: spent,
    remaining: Math.max(0, budget - spent),
    degraded,
  });
}

export async function POST(req: NextRequest) {
  // 1. Authenticate user
  const auth = await authenticateRequest(req);
  if (!auth.user) {
    return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });
  }

  // 2. Abuse protection: Rate limiting (15 scans per minute per user/IP)
  const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown-ip";
  const rateLimitKey = `scan:${auth.user.id || clientIp}`;
  const rl = checkRateLimit(rateLimitKey, 15, 60_000);
  if (!rl.allowed) {
    return NextResponse.json(
      { error: `Scan rate limit exceeded. Please retry after ${rl.retryAfterSeconds} seconds.` },
      { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } }
    );
  }

  // 3. Body validation with request size limit (capped at 256 KB)
  const { data: parsedBody, errorResponse } = await readJsonBodyWithLimit<any>(req, 256 * 1024);
  if (errorResponse) {
    return errorResponse;
  }
  let parsed = parsedBody;

  if (!parsed || typeof parsed !== "object" || !parsed.url) {
    return NextResponse.json({ error: "Scan request requires a valid 'url' target." }, { status: 400 });
  }

  // Validate URL with DNS-aware resolution to prevent SSRF and DNS rebinding
  const urlCheck = await validateScanTargetUrlAsync(parsed.url);
  if (!urlCheck.valid) {
    return NextResponse.json({ error: `Rejected scan target: ${urlCheck.reason}` }, { status: 400 });
  }
  parsed.url = urlCheck.normalizedUrl;

  // Cap crawl depth and page count to prevent resource exhaustion
  parsed = sanitizeScanOptions(parsed);

  // Spend cap. This replaced a blanket filter that stripped every paid tool on
  // every request, which held the bill at zero and also kept eight of the
  // twenty-three tools permanently dark - the eight behind every competitive
  // and keyword screen. A full paid run is about $0.52; the cap is a daily
  // ceiling, not a ban.
  const budget = dailyBudgetUsd();
  const { spent, degraded } = await spentTodayUsd(getScopedDb(auth.user, auth.token), budget);
  const decision = applyBudget(
    Array.isArray(parsed.tools) ? parsed.tools : undefined,
    spent,
    budget,
  );

  if (Array.isArray(parsed.tools)) {
    parsed.tools = decision.allowed;
    // Every paid tool was dropped and nothing free was asked for: the run would
    // do nothing, so say why instead of streaming an empty result.
    if (decision.allowed.length === 0 && decision.blocked.length > 0) {
      return NextResponse.json(
        {
          error:
            decision.reason ||
            "Daily scan budget reached. Paid tools are paused until tomorrow (UTC).",
          budget: { spentToday: spent, budget, remaining: decision.remaining, blocked: decision.blocked },
        },
        { status: 429 },
      );
    }
  } else if (decision.blocked.length > 0) {
    // No explicit selection and the full paid set does not fit. Leave `tools`
    // absent rather than sending an empty array: the scanner rejects `[]`
    // outright ("select at least one tool to run"), because a zero-tool run
    // must never report a clean score. With no selection it runs its free
    // tools and skips the paid group, which is exactly the wanted behaviour.
    delete parsed.tools;
  }

  const bodyToSend = JSON.stringify(parsed);

  try {
    const res = await scannerPost("/scan", bodyToSend);
    // Pass the ndjson stream straight through so the browser gets live events.
    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        "Content-Type": "application/x-ndjson",
        "Cache-Control": "no-cache",
        // The UI reads these to explain a partial run instead of silently
        // returning fewer findings than the user selected.
        "X-Scan-Budget-Usd": String(budget),
        "X-Scan-Spent-Today-Usd": spent.toFixed(4),
        "X-Scan-Estimated-Cost-Usd": String(decision.estimatedCost),
        "X-Scan-Blocked-Tools": decision.blocked.join(","),
        ...(degraded ? { "X-Scan-Budget-Degraded": "1" } : {}),
      },
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof ScannerUnconfigured ? e.message : `backend unreachable at ${PYTHON_API} — is wf-scan-web running? (${e})` },
      // 503, not 200: a success status on a failed scan is what let the browser
      // read this refusal as an empty stream and show nothing at all.
      { status: 503 },
    );
  }
}
