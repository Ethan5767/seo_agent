import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";
import { scannerPost, PYTHON_API, ScannerUnconfigured } from "@/lib/scannerFetch";
import { classifyWithClaude, heuristicClass, type PlanClass } from "@/lib/planClassify";

// classifyWithClaude spawns the `claude` CLI, which needs the Node runtime; the
// edge runtime has no child_process. Same as /api/fix/advise.
export const runtime = "nodejs";

const SEV_RANK: Record<string, number> = { error: 2, warn: 1, info: 0, ok: 0 };
const ACTIONABLE = new Set(["error", "warn"]);

// The tier/impact split used to be two keyword-matching functions here
// (`getFindingTier`/`getFindingImpact`) that decided "anything with `title` is
// T1" from a substring. That logic now lives in `lib/planClassify.heuristicClass`
// as the DETERMINISTIC FALLBACK, kept for when Claude is unreachable. When the
// `claude` CLI is available, `classifyWithClaude` reads each finding's evidence
// and returns a grounded tier, impact, agent-can-take verdict and a one-line
// whatToDo. `classifiedBy` on the response records which one ran.
function getFindingTier(code: string, what: string, category: string): { tier: number; tierLabel: string } {
  const { tier, tierLabel } = heuristicClass(code, what, category, "warn");
  return { tier, tierLabel };
}

function getFindingImpact(severity: string, code: string): { impact: PlanClass["impact"]; priorityScore: number } {
  const { impact, priorityScore } = heuristicClass(code, "", "", severity);
  return { impact, priorityScore };
}

// Overlay Claude's classification onto a worklist item, keyed by code. Recomputes
// inScope/selectedForSprint from the CLASSIFIED tier and the agent-can-take
// verdict, so a Claude call actually changes what the sprint picks up.
function applyClass(item: any, cls: PlanClass | undefined, clientTier: number): any {
  if (!cls) return item;
  const inScope = cls.tier <= clientTier && cls.agentCanTake !== false;
  return {
    ...item,
    tier: cls.tier,
    tierLabel: cls.tierLabel,
    impact: cls.impact,
    priorityScore: cls.priorityScore,
    agentCanTake: cls.agentCanTake,
    whatToDo: cls.whatToDo,
    reason: cls.reason,
    // The grounded line becomes the fix the developer brief renders, when present.
    fix: cls.whatToDo || item.fix,
    why: cls.reason || item.why,
    inScope,
    selectedForSprint: inScope,
  };
}

function generateModelABrief(domain: string, business: string, worklist: any[]): string {
  const dateStr = new Date().toISOString().split("T")[0];
  let md = `# SEO/AEO IMPLEMENTATION BRIEF (MODEL A)
**Client:** ${business || domain}
**Website:** https://${domain}
**Cycle:** ${dateStr}
**Status:** Approved for Client Developer Execution
**Prepared by:** SEO/AEO Pipeline Autonomous Agent

---

## Executive Summary
This document contains the prioritized, peer-reviewed implementation steps for your technical team. 
Every change has been evaluated for maximum search engine rankings (SEO) and modern AI engine visibility (AEO).

---

## Prioritized Implementation Checklist

`;

  worklist.forEach((item, idx) => {
    md += `### ${idx + 1}. [${item.tierLabel}] ${item.what}
- **Impact Level:** ${item.impact} (${item.severity.toUpperCase()})
- **Target File / Location:** ${item.targetFile ? `\`${item.targetFile}\`` : "_Not known from the scan. The finding is on the live page; locate the source that renders it._"}
- **Why It Matters:** ${item.why || "_No reason recorded for this finding._"}
- **Recommended Action:** ${item.fix || "_No fix recorded for this finding._"}

\`\`\`html
<!-- Proposed Fix / Target Code -->
${item.detail || `<!-- Apply fix for ${item.code} -->`}
\`\`\`

- [ ] Implemented by Developer
- [ ] Staging Verified

---

`;
  });

  md += `## Verification & Sign-Off
Once these changes are deployed to your staging environment, our automated pipeline will re-scan the site to verify resolution and update your monthly Progress Report.
`;
  return md;
}

export async function POST(req: NextRequest) {
  const auth = await authenticateRequest(req);
  if (!auth.user) {
    return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });
  }

  const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown-ip";
  const rl = checkRateLimit(`plan:${auth.user.id || clientIp}`, 30, 60_000);
  if (!rl.allowed) {
    return NextResponse.json(
      { error: `Rate limit exceeded. Please retry after ${rl.retryAfterSeconds} seconds.` },
      { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } }
    );
  }

  const { data: bodyData, errorResponse } = await readJsonBodyWithLimit<any>(req, 1024 * 1024);
  if (errorResponse) {
    return errorResponse;
  }
  const body = bodyData || {};

  const {
    current = [],
    previous = [],
    tier = 1,
    model = "B",
    domain = "",
    business = "",
    goal = "",
    cycle = "",
  } = body;
  if (!String(domain).trim() || !String(business).trim()) {
    return NextResponse.json({ error: "A real project domain and business name are required." }, { status: 400 });
  }

  // Overlay Claude's grounded classification onto a heuristic-classified
  // worklist. Returns ["claude" | "heuristic", worklist]. Any failure inside
  // classifyWithClaude returns null and we keep the heuristic result, so the
  // plan is never blocked on the `claude` CLI being reachable.
  const classify = async (worklist: any[]): Promise<["claude" | "heuristic", any[]]> => {
    if (worklist.length === 0) return ["heuristic", worklist];
    const map = await classifyWithClaude(worklist, { clientTier: Number(tier), domain, business });
    if (!map) return ["heuristic", worklist];
    return ["claude", worklist.map((w) => applyClass(w, map.get(w.code), Number(tier)))];
  };

  // 1. Try forwarding to Python API if running
  try {
    const pyRes = await scannerPost("/plan", { current, previous }, { headerTimeoutMs: 1200 });
    if (pyRes.ok) {
      const pyData = await pyRes.json();
      if (pyData.worklist && pyData.worklist.length > 0) {
        // Enrich Python response with SOP Tiers and Model A/B outputs
        const enriched = pyData.worklist.map((w: any) => {
          const tInfo = getFindingTier(w.code || "", w.what || "", w.category || "");
          const impInfo = getFindingImpact(w.severity || "warn", w.code || "");
          return {
            ...w,
            ...tInfo,
            ...impInfo,
            inScope: tInfo.tier <= Number(tier),
            selectedForSprint: tInfo.tier <= Number(tier),
            // `targetFile` used to GUESS a path from the finding code -
            // "components/SEOHead.tsx", "src/app/layout.tsx", and for anything
            // mentioning schema, "components/MedicalBusinessSchema.tsx" (one
            // pilot client's vertical, for every account). Nothing here reads
            // the client's repository, so every one of those was a file the
            // brief told a developer to edit that may not exist.
            //
            // null is the truth. `wf-site-remediate` knows the real path
            // because it works inside the checkout and measures the git diff;
            // this route does not.
            targetFile: null,
          };
        });

        const [classifiedBy, classified] = await classify(enriched);
        const brief = generateModelABrief(domain, business, classified.filter((i: any) => i.inScope));

        return NextResponse.json({
          ...pyData,
          worklist: classified,
          clientTier: Number(tier),
          clientModel: model,
          cycle,
          classifiedBy,
          developerBriefMarkdown: brief,
        });
      }
    }
  } catch {
    // Python unreachable or timed out; fall through to built-in pure TypeScript SOP planner
  }

  // 2. Pure TypeScript SOP-Compliant Planning & Ratchet Engine
  const curByCode = new Map<string, any>();
  for (const r of current || []) {
    if (!r.code) continue;
    const existing = curByCode.get(r.code);
    if (!existing || (SEV_RANK[r.severity] || 0) > (SEV_RANK[existing.severity] || 0)) {
      curByCode.set(r.code, r);
    }
  }

  const prevByCode = new Map<string, any>();
  for (const r of previous || []) {
    if (!r.code) continue;
    const existing = prevByCode.get(r.code);
    if (!existing || (SEV_RANK[r.severity] || 0) > (SEV_RANK[existing.severity] || 0)) {
      prevByCode.set(r.code, r);
    }
  }

  const worklist: any[] = [];
  const counts = { NEW: 0, PERSISTING: 0, REGRESSION: 0, RESOLVED: 0, inScope: 0, outOfScope: 0 };

  for (const [code, r] of curByCode.entries()) {
    if (!ACTIONABLE.has(r.severity)) continue;

    const prev = prevByCode.get(code);
    let status = "NEW";
    if (!prev) {
      status = "NEW";
    } else if ((SEV_RANK[r.severity] || 0) > (SEV_RANK[prev.severity] || 0)) {
      status = "REGRESSION";
    } else {
      status = "PERSISTING";
    }

    const tInfo = getFindingTier(code, r.what || "", r.category || "");
    const impInfo = getFindingImpact(r.severity, code);
    const inScope = tInfo.tier <= Number(tier);

    if (inScope) counts.inScope++;
    else counts.outOfScope++;

    if (status === "NEW") counts.NEW++;
    else if (status === "REGRESSION") counts.REGRESSION++;
    else if (status === "PERSISTING") counts.PERSISTING++;

    worklist.push({
      ...r,
      code,
      status,
      ...tInfo,
      ...impInfo,
      inScope,
      selectedForSprint: inScope,
      // See the note on the other targetFile above. A guessed path in a
      // developer brief is worse than no path: it sends someone to a file that
      // may not exist, and reads as though we looked.
      targetFile: null,
    });
  }

  // RESOLVED: an actionable finding last scan that is passing now, or absent
  // while the tool that finds it RAN this scan. A tool that did not run
  // (paused, budget, error, left out of a section scan) cannot resolve its
  // findings; they stay open, marked (B-121, same rule as plan.py).
  const ran = new Set(
    (current || [])
      .filter((r: any) => r?.tool && !String(r?.code || "").startsWith("unavailable."))
      .map((r: any) => r.tool),
  );
  const resolved: any[] = [];
  for (const [code, r] of prevByCode.entries()) {
    if (!ACTIONABLE.has(r.severity)) continue;
    const now = curByCode.get(code);
    if (now) {
      if (!ACTIONABLE.has(now.severity)) {
        resolved.push({ ...r, status: "RESOLVED" });
        counts.RESOLVED++;
      }
      continue;
    }
    if (!r.tool || ran.has(r.tool)) {
      resolved.push({ ...r, status: "RESOLVED" });
      counts.RESOLVED++;
      continue;
    }
    const tInfo = getFindingTier(code, r.what || "", r.category || "");
    const impInfo = getFindingImpact(r.severity, code);
    const inScope = tInfo.tier <= Number(tier);
    if (inScope) counts.inScope++;
    else counts.outOfScope++;
    counts.PERSISTING++;
    worklist.push({
      ...r, code, status: "PERSISTING", ...tInfo, ...impInfo, inScope,
      selectedForSprint: inScope, targetFile: null,
      note: `not re-checked in this scan: ${r.tool} did not run`,
    });
  }

  // Claude overlay before the sort, so the ranking uses the classified
  // priorityScore/impact rather than the heuristic one.
  const [classifiedBy, classifiedWorklist] = await classify(worklist);

  // Sort worklist: REGRESSION and high priority first
  classifiedWorklist.sort((a, b) => {
    if (a.status === "REGRESSION" && b.status !== "REGRESSION") return -1;
    if (b.status === "REGRESSION" && a.status !== "REGRESSION") return 1;
    return b.priorityScore - a.priorityScore;
  });

  classifiedWorklist.forEach((w, i) => {
    w.priority = i + 1;
  });

  const sprintItems = classifiedWorklist.filter((w) => w.inScope);
  const brief = generateModelABrief(domain, business, sprintItems);

  const executiveSummary = sprintItems.length > 0
    ? `Cycle ${cycle} Plan focused on ${sprintItems.length} in-scope optimizations for ${domain}. Priority given to ${counts.REGRESSION > 0 ? `${counts.REGRESSION} regressions, ` : ""}${sprintItems.filter(i => i.impact === "Critical Blocker" || i.impact === "High Impact").length} high-impact search signals aligned with "${goal}".`
    : `All scanned areas for ${domain} are currently meeting baseline targets. No critical regressions detected.`;

  return NextResponse.json({
    cycle,
    clientDomain: domain,
    clientTier: Number(tier),
    clientModel: model,
    worklist: classifiedWorklist,
    resolved,
    counts,
    classifiedBy,
    executiveSummary,
    // `projectedLift` was here: `+${Math.min(28, Math.max(6, sprintItems.length * 2.2))}% Organic Visibility`.
    // A traffic forecast computed from the NUMBER OF TO-DO ITEMS, floored at 6%
    // so an empty plan still promised a gain. It shipped in the client-facing
    // plan response, which makes it the most publishable fabrication in the
    // codebase - a figure a client puts in a deck.
    //
    // Nothing consumes it, and nothing can honestly produce it: forecasting
    // organic lift needs a baseline, a control and a measured outcome, none of
    // which this product has. Removed rather than replaced.
    developerBriefMarkdown: brief,
  });
}
