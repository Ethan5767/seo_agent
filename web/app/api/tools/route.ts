// Server-side proxy to the Python backend's GET /tools — the tool catalog the
// Measure checklist renders. Same reasoning as /api/scan: the browser never
// talks to the Python port directly. Set PYTHON_API to override the default.
import { NextResponse } from "next/server";

const PYTHON_API = process.env.PYTHON_API || "http://127.0.0.1:8765";

export async function GET() {
  try {
    const res = await fetch(`${PYTHON_API}/tools`, { cache: "no-store" });
    return new NextResponse(res.body, {
      status: res.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-cache" },
    });
  } catch (e) {
    return NextResponse.json(
      { error: `backend unreachable at ${PYTHON_API} — is wf-scan-web running? (${e})`, tools: [] },
      { status: 200 },
    );
  }
}
