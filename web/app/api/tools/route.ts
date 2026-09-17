// Server-side proxy to the Python backend's GET /tools — the tool catalog the
// Measure checklist renders. Same reasoning as /api/scan: the browser never
// talks to the Python port directly. Set PYTHON_API to override the default.
import { NextResponse } from "next/server";
import { PYTHON_API, scannerGet } from "@/lib/scannerFetch";


export async function GET() {
  try {
    const res = await scannerGet("/tools");
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
