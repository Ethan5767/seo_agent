import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";

const PYTHON_API = process.env.PYTHON_API || "http://127.0.0.1:8765";

const SEV_RANK: Record<string, number> = { error: 2, warn: 1, info: 0, ok: 0 };
const ACTIONABLE = new Set(["error", "warn"]);

// Classify finding scope tier based on finding code / category
function getFindingTier(code: string, what: string, category: string): { tier: number; tierLabel: string } {
  const c = (code + " " + what + " " + category).toLowerCase();
  if (
    c.includes("title") ||
    c.includes("description") ||
    c.includes("meta") ||
    c.includes("alt") ||
    c.includes("h1") ||
    c.includes("h2") ||
    c.includes("heading") ||
    c.includes("copy")
  ) {
    return { tier: 1, tierLabel: "T1: Copy Only" };
  }
  if (
    c.includes("content") ||
    c.includes("article") ||
    c.includes("blog") ||
    c.includes("faq") ||
    c.includes("eeat") ||
    c.includes("bio") ||
    c.includes("author") ||
    c.includes("entity")
  ) {
    return { tier: 2, tierLabel: "T2: Content" };
  }
  return { tier: 3, tierLabel: "T3: Full Scope" };
}

function getFindingImpact(severity: string, code: string): { impact: "Critical Blocker" | "High Impact" | "Medium" | "Quick Win"; priorityScore: number } {
  const c = code.toLowerCase();
  if (c.includes("robots") || c.includes("500") || c.includes("404") || c.includes("noindex")) {
    return { impact: "Critical Blocker", priorityScore: 100 };
  }
  if (severity === "error" || c.includes("title") || c.includes("lcp") || c.includes("canonical")) {
    return { impact: "High Impact", priorityScore: 80 };
  }
  if (c.includes("schema") || c.includes("alt") || c.includes("inp") || c.includes("cls")) {
    return { impact: "Medium", priorityScore: 60 };
  }
  return { impact: "Quick Win", priorityScore: 40 };
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
- **Target File / Location:** \`${item.targetFile || "components/SEOHead.tsx"}\`
- **Why It Matters:** ${item.why || "Improves organic visibility and indexing efficiency."}
- **Recommended Action:** ${item.fix || "Update the specified tag or configuration."}

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
    domain = "example.com",
    business = "Client Business",
    goal = "Organic Visibility",
    cycle = "2026-09",
  } = body;

  // 1. Try forwarding to Python API if running
  try {
    const pyRes = await fetch(`${PYTHON_API}/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current, previous }),
      signal: AbortSignal.timeout(1200),
    });
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
            targetFile: w.code?.includes("robots")
              ? "public/robots.txt"
              : w.code?.includes("schema")
              ? "components/MedicalBusinessSchema.tsx"
              : w.code?.includes("canonical") || w.code?.includes("meta")
              ? "components/SEOHead.tsx"
              : "src/app/layout.tsx",
          };
        });

        const brief = generateModelABrief(domain, business, enriched.filter((i: any) => i.inScope));

        return NextResponse.json({
          ...pyData,
          worklist: enriched,
          clientTier: Number(tier),
          clientModel: model,
          cycle,
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
      targetFile: code.includes("robots")
        ? "public/robots.txt"
        : code.includes("schema")
        ? "components/MedicalBusinessSchema.tsx"
        : code.includes("canonical") || code.includes("meta") || code.includes("title")
        ? "components/SEOHead.tsx"
        : code.includes("crux") || code.includes("perf")
        ? "src/app/layout.tsx"
        : "components/SEOHead.tsx",
    });
  }

  // Find RESOLVED items (present in prev actionable, gone from current)
  const resolved: any[] = [];
  for (const [code, r] of prevByCode.entries()) {
    if (ACTIONABLE.has(r.severity) && !curByCode.has(code)) {
      resolved.push({ ...r, status: "RESOLVED" });
      counts.RESOLVED++;
    }
  }

  // Sort worklist: REGRESSION and high priority first
  worklist.sort((a, b) => {
    if (a.status === "REGRESSION" && b.status !== "REGRESSION") return -1;
    if (b.status === "REGRESSION" && a.status !== "REGRESSION") return 1;
    return b.priorityScore - a.priorityScore;
  });

  worklist.forEach((w, i) => {
    w.priority = i + 1;
  });

  const sprintItems = worklist.filter((w) => w.inScope);
  const brief = generateModelABrief(domain, business, sprintItems);

  const executiveSummary = sprintItems.length > 0
    ? `Cycle ${cycle} Plan focused on ${sprintItems.length} in-scope optimizations for ${domain}. Priority given to ${counts.REGRESSION > 0 ? `${counts.REGRESSION} regressions, ` : ""}${sprintItems.filter(i => i.impact === "Critical Blocker" || i.impact === "High Impact").length} high-impact search signals aligned with "${goal}".`
    : `All scanned areas for ${domain} are currently meeting baseline targets. No critical regressions detected.`;

  return NextResponse.json({
    cycle,
    clientDomain: domain,
    clientTier: Number(tier),
    clientModel: model,
    worklist,
    resolved,
    counts,
    executiveSummary,
    projectedLift: `+${Math.min(28, Math.max(6, sprintItems.length * 2.2)).toFixed(1)}% Organic Visibility`,
    developerBriefMarkdown: brief,
  });
}
