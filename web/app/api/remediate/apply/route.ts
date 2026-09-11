// Server-side proxy to the Python backend's POST /remediate/apply — the REAL
// edit-run: Claude Code (Claude subscription) edits the client repo, then we read
// back changelog.json + git diff. Irreversible; the backend demands confirm:true
// and refuses without `claude` on PATH.
import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";

const PYTHON_API = process.env.PYTHON_API || "http://127.0.0.1:8765";

export async function POST(req: NextRequest) {
  const auth = await authenticateRequest(req);
  if (!auth.user) {
    return NextResponse.json({ ok: false, error: auth.error || "Unauthorized" }, { status: 401 });
  }

  const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown-ip";
  const rl = checkRateLimit(`remediate-apply:${auth.user.id || clientIp}`, 10, 60_000);
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
    const res = await fetch(`${PYTHON_API}/remediate/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    // The backend streams newline-delimited JSON: {"log": "..."} per line as
    // Claude writes it, then one {"result": {...}}. Pass it through unbuffered
    // so the browser can render progress. It used to be declared
    // "application/json", which told the client to wait for a complete document
    // — an apply can run for half an hour, so the operator saw a dead screen
    // and could not tell a working run from a hung one.
    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        "Content-Type": "application/x-ndjson",
        "Cache-Control": "no-cache",
        // Stops a proxy buffering the stream back into one response.
        "X-Accel-Buffering": "no",
      },
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: `backend unreachable at ${PYTHON_API} (${e})` },
      { status: 200 },
    );
  }
}
