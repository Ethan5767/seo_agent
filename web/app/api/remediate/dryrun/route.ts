// Server-side proxy to the Python backend's POST /remediate/dryrun — bridges the
// worklist into the pipeline shape and runs wf-site-remediate --dry-run (streams
// the fix prompts, EDITS NOTHING). Same reasoning as /api/remediate.
import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";
import { scannerPost, PYTHON_API, ScannerUnconfigured } from "@/lib/scannerFetch";


export async function POST(req: NextRequest) {
  const auth = await authenticateRequest(req);
  if (!auth.user) {
    return NextResponse.json({ ok: false, error: auth.error || "Unauthorized" }, { status: 401 });
  }

  const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown-ip";
  const rl = checkRateLimit(`remediate-dryrun:${auth.user.id || clientIp}`, 15, 60_000);
  if (!rl.allowed) {
    return NextResponse.json(
      { ok: false, error: `Rate limit exceeded. Please retry after ${rl.retryAfterSeconds} seconds.` },
      { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } }
    );
  }

  const { data: bodyData, errorResponse } = await readJsonBodyWithLimit<any>(req, 1024 * 1024);
  if (errorResponse) {
    return errorResponse;
  }
  const body = JSON.stringify(bodyData || {});
  try {
    const res = await scannerPost("/remediate/dryrun", body);
    return new NextResponse(res.body, {
      status: res.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-cache" },
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof ScannerUnconfigured ? e.message : `backend unreachable at ${PYTHON_API} (${e})`, items: [], unbridged: [], prompts: [] },
      { status: 200 },
    );
  }
}
