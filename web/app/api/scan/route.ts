// Server-side proxy to the Python backend (wf-scan-web). Runs on the Next
// server, so the browser never talks to the Python port directly — no CORS,
// and the backend URL stays server-side. Set PYTHON_API to override the default.
import { NextRequest, NextResponse } from "next/server";

const PYTHON_API = process.env.PYTHON_API || "http://127.0.0.1:8765";

export async function POST(req: NextRequest) {
  const body = await req.text();
  try {
    const res = await fetch(`${PYTHON_API}/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const data = await res.text();
    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    return NextResponse.json(
      { error: `backend unreachable at ${PYTHON_API} — is wf-scan-web running? (${e})` },
      { status: 200 },
    );
  }
}
