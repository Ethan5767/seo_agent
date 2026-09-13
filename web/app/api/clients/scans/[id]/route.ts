import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, getScopedDb } from "@/lib/server-security";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    if (!id) return NextResponse.json({ error: "Missing scan ID" }, { status: 400 });

    const auth = await authenticateRequest(req);
    if (!auth.user) {
      return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });
    }

    const db = getScopedDb(auth.user, auth.token);

    const { data, error } = await db
      .from("scans")
      .select("id, client_id, score, counts, cost, created_at, url, report")
      .eq("id", id)
      .eq("user_id", auth.user.id)
      .single();

    if (error || !data) {
      return NextResponse.json({ error: error?.message || "Scan not found" }, { status: 404 });
    }

    return NextResponse.json({ ok: true, scan: data, report: data.report });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
