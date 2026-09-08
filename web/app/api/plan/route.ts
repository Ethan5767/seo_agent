// Server-side proxy to the Python backend's POST /plan — runs the ratchet over
// two findings lists. Same reasoning as /api/scan: the browser never talks to
// the Python port directly.
import { NextRequest, NextResponse } from "next/server";

const PYTHON_API = process.env.PYTHON_API || "http://127.0.0.1:8765";

export async function POST(req: NextRequest) {
  const body = await req.text();
  try {
    const res = await fetch(`${PYTHON_API}/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    return new NextResponse(res.body, {
      status: res.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-cache" },
    });
  } catch (e) {
    return NextResponse.json(
      { error: `backend unreachable at ${PYTHON_API} (${e})`, worklist: [], resolved: [], counts: {} },
      { status: 200 },
    );
  }
}
