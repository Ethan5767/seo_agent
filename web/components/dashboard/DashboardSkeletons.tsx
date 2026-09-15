import React from "react";

export function SkeletonBox({
  width = "100%",
  height = 20,
  borderRadius = 6,
  style,
  className = "",
}: {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  style?: React.CSSProperties;
  className?: string;
}) {
  // The paint + animation live entirely in the .reai-shimmer class (tokens.css),
  // which reduced-motion downgrades to a static tint. This element only carries
  // its own dimensions; it never re-specifies the gradient the class already owns.
  return (
    <div
      className={`reai-shimmer ${className}`}
      style={{ width, height, borderRadius, display: "block", ...style }}
    />
  );
}

// ── Report view skeleton ──
// Mirrors the real report screen exactly: the ReportStats strip (four joined
// count cells) above the ReportTable (Status · Pages · Issue · Fix columns), so
// the swap from loading to loaded moves nothing. Shown while a scan runs and no
// rows have arrived yet, in place of a strip of zeroes over an empty table.
export function ReportViewSkeleton({ rows = 8 }: { rows?: number }) {
  const cols = "6.5rem 5rem 1fr 1fr";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      {/* count strip — matches ReportStats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(8rem, 1fr))", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", background: "var(--surface)", overflow: "hidden" }}>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} style={{ padding: "var(--space-3) var(--space-4)", borderRight: i < 3 ? "1px solid var(--border)" : 0, display: "flex", flexDirection: "column", gap: 10 }}>
            <SkeletonBox width={54} height={11} borderRadius={4} />
            <SkeletonBox width={38} height={22} borderRadius={5} />
          </div>
        ))}
      </div>

      {/* findings table — matches ReportTable head + rows */}
      <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-md)", overflow: "hidden", background: "var(--surface)" }}>
        <div style={{ display: "grid", gridTemplateColumns: cols, gap: "var(--space-3)", padding: "var(--space-3) var(--space-4)", background: "var(--surface-2)", borderBottom: "1px solid var(--border-strong)" }}>
          {[46, 40, 60, 40].map((w, i) => (
            <SkeletonBox key={i} width={w} height={10} borderRadius={3} />
          ))}
        </div>
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} style={{ display: "grid", gridTemplateColumns: cols, gap: "var(--space-3)", alignItems: "start", padding: "var(--space-3) var(--space-4)", borderBottom: r < rows - 1 ? "1px solid var(--border)" : 0 }}>
            <SkeletonBox width={58} height={20} borderRadius={6} />
            <SkeletonBox width={34} height={13} borderRadius={4} />
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <SkeletonBox width={`${55 + (r * 7) % 35}%`} height={13} borderRadius={4} />
              <SkeletonBox width={`${35 + (r * 11) % 30}%`} height={10} borderRadius={3} />
            </div>
            <SkeletonBox width={`${45 + (r * 9) % 40}%`} height={13} borderRadius={4} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 1. Overview Skeleton ──
export function OverviewSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px 18px", minHeight: 96, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <SkeletonBox width={85 + (i * 12) % 30} height={12} borderRadius={4} />
              <SkeletonBox width={48} height={18} borderRadius={10} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 12 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <SkeletonBox width={100 + (i * 16) % 40} height={26} borderRadius={6} />
                <SkeletonBox width={75 + (i * 10) % 30} height={11} borderRadius={4} />
              </div>
              <SkeletonBox width={68} height={26} borderRadius={4} />
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 14 }}>
        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "20px 22px", display: "flex", flexDirection: "column", gap: 16, minHeight: 330 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <SkeletonBox width={180} height={16} borderRadius={4} />
            <SkeletonBox width={90} height={28} borderRadius={6} />
          </div>
          <SkeletonBox width="100%" height={230} borderRadius={6} />
        </div>

        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "20px 22px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 330 }}>
          <SkeletonBox width={140} height={16} borderRadius={4} />
          <div style={{ display: "flex", justifyContent: "center", padding: "12px 0" }}>
            <SkeletonBox width={110} height={110} borderRadius="50%" />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <SkeletonBox width="100%" height={14} borderRadius={4} />
            <SkeletonBox width="80%" height={14} borderRadius={4} />
          </div>
        </div>
      </div>

      {/* Core Web Vitals Row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {[1, 2, 3].map((k) => (
          <div key={k} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px 18px", display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <SkeletonBox width={60} height={12} borderRadius={4} />
              <SkeletonBox width={45} height={16} borderRadius={8} />
            </div>
            <SkeletonBox width={90} height={22} borderRadius={4} />
            <SkeletonBox width="100%" height={8} borderRadius={4} />
          </div>
        ))}
      </div>

      {/* SERP Rankings Table */}
      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between" }}>
          <SkeletonBox width={160} height={15} borderRadius={4} />
          <SkeletonBox width={100} height={15} borderRadius={4} />
        </div>
        {[1, 2, 3, 4, 5].map((r) => (
          <div key={r} style={{ padding: "14px 18px", borderBottom: r === 5 ? "none" : "1px solid var(--surface-3)", display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr", alignItems: "center" }}>
            <SkeletonBox width={140 + r * 15} height={14} borderRadius={4} />
            <SkeletonBox width={50} height={14} borderRadius={4} />
            <SkeletonBox width={60} height={14} borderRadius={4} />
            <SkeletonBox width={70} height={22} borderRadius={6} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 2. Site Audit Skeleton ──
export function SiteAuditSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Sub-tab & CTA bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: 12, borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <SkeletonBox width={160} height={32} borderRadius={6} />
          <SkeletonBox width={180} height={32} borderRadius={6} />
          <SkeletonBox width={140} height={32} borderRadius={6} />
        </div>
        <SkeletonBox width={180} height={32} borderRadius={6} />
      </div>

      {/* Top Split: Donut + Error summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 12 }}>
        <div style={{ background: "var(--surface)", padding: "20px", borderRadius: 8, border: "1px solid var(--border)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12 }}>
          <SkeletonBox width={96} height={96} borderRadius="50%" />
          <SkeletonBox width={120} height={14} borderRadius={4} />
          <SkeletonBox width={80} height={11} borderRadius={4} />
        </div>

        <div style={{ background: "var(--surface)", padding: "18px 20px", borderRadius: 8, border: "1px solid var(--border)", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
            {[1, 2, 3, 4].map((j) => (
              <div key={j} style={{ padding: "12px 14px", borderRadius: 6, background: "var(--surface-2)", border: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 6 }}>
                <SkeletonBox width={60} height={12} borderRadius={4} />
                <SkeletonBox width={45} height={24} borderRadius={4} />
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <SkeletonBox width="50%" height={28} borderRadius={6} />
            <SkeletonBox width="50%" height={28} borderRadius={6} />
          </div>
        </div>
      </div>

      {/* 3 Issue Category Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {[1, 2, 3].map((c) => (
          <div key={c} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px 18px", display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <SkeletonBox width={110} height={14} borderRadius={4} />
              <SkeletonBox width={36} height={16} borderRadius={8} />
            </div>
            <SkeletonBox width="100%" height={8} borderRadius={4} />
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
              <SkeletonBox width={80} height={11} borderRadius={4} />
              <SkeletonBox width={50} height={11} borderRadius={4} />
            </div>
          </div>
        ))}
      </div>

      {/* Diagnostic Checklist Table */}
      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between" }}>
          <SkeletonBox width={180} height={16} borderRadius={4} />
          <SkeletonBox width={120} height={28} borderRadius={6} />
        </div>
        {[1, 2, 3, 4, 5, 6].map((row) => (
          <div key={row} style={{ padding: "14px 18px", borderBottom: row === 6 ? "none" : "1px solid var(--surface-3)", display: "grid", gridTemplateColumns: "3fr 1fr 1fr 120px", alignItems: "center", gap: 12 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <SkeletonBox width={160 + row * 20} height={14} borderRadius={4} />
              <SkeletonBox width={220} height={11} borderRadius={3} />
            </div>
            <SkeletonBox width={70} height={18} borderRadius={10} />
            <SkeletonBox width={60} height={14} borderRadius={4} />
            <SkeletonBox width={110} height={28} borderRadius={6} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 3. Auto-Fix Engine Skeleton ──
export function AutoFixSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* 4 Workflow Steps */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {[1, 2, 3, 4].map((s) => (
          <div key={s} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <SkeletonBox width={22} height={22} borderRadius="50%" />
              <SkeletonBox width={90} height={13} borderRadius={4} />
            </div>
            <SkeletonBox width={120} height={11} borderRadius={3} />
            <SkeletonBox width={80} height={10} borderRadius={3} />
          </div>
        ))}
      </div>

      {/* Advantage Dark Banner */}
      <div style={{ background: "#0f172a", borderRadius: 8, padding: "16px 20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, width: "65%" }}>
          <SkeletonBox width={140} height={14} borderRadius={4} style={{ background: "#334155" }} />
          <SkeletonBox width="90%" height={12} borderRadius={4} style={{ background: "#1e293b" }} />
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <SkeletonBox width={120} height={34} borderRadius={6} style={{ background: "#334155" }} />
          <SkeletonBox width={140} height={34} borderRadius={6} style={{ background: "#334155" }} />
        </div>
      </div>

      {/* 2-Column Split: File Tree + Code Diff Studio */}
      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 12, alignItems: "start" }}>
        {/* Left Files List */}
        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "14px", display: "flex", flexDirection: "column", gap: 8 }}>
          <SkeletonBox width={110} height={13} borderRadius={4} />
          {[1, 2, 3, 4].map((f) => (
            <div key={f} style={{ padding: "10px", borderRadius: 6, background: f === 1 ? "#eff6ff" : "var(--surface-2)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <SkeletonBox width={130} height={12} borderRadius={3} />
              <SkeletonBox width={36} height={14} borderRadius={4} />
            </div>
          ))}
        </div>

        {/* Right Code Diff Canvas */}
        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
          <div style={{ padding: "12px 16px", background: "var(--surface-2)", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <SkeletonBox width={180} height={14} borderRadius={4} />
            <SkeletonBox width={90} height={24} borderRadius={4} />
          </div>
          <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: 8, background: "#0f172a" }}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((line) => (
              <div key={line} style={{ display: "flex", gap: 12, alignItems: "center" }}>
                <SkeletonBox width={28} height={12} borderRadius={3} style={{ background: "#1e293b" }} />
                <SkeletonBox width={120 + (line * 37) % 240} height={12} borderRadius={3} style={{ background: line % 3 === 0 ? "#14532d" : line % 3 === 1 ? "#7f1d1d" : "#1e293b" }} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── 4. Traffic Analytics Skeleton ──
export function TrafficAnalyticsSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Integration Bar */}
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <SkeletonBox width={180} height={18} borderRadius={4} />
          <SkeletonBox width={130} height={14} borderRadius={4} />
        </div>
        <SkeletonBox width={160} height={28} borderRadius={6} />
      </div>

      {/* 5 KPI Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }}>
        {[1, 2, 3, 4, 5].map((c) => (
          <div key={c} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px 18px", minHeight: 96, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <SkeletonBox width={70} height={11} borderRadius={4} />
              <SkeletonBox width={45} height={14} borderRadius={4} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
              <div>
                <SkeletonBox width={85} height={24} borderRadius={4} />
                <SkeletonBox width={60} height={10} borderRadius={3} style={{ marginTop: 4 }} />
              </div>
              <SkeletonBox width={50} height={22} borderRadius={4} />
            </div>
          </div>
        ))}
      </div>

      {/* Trend & Device Split */}
      <div style={{ display: "grid", gridTemplateColumns: "1.7fr 1fr", gap: 12 }}>
        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <SkeletonBox width={150} height={15} borderRadius={4} />
            <SkeletonBox width={80} height={24} borderRadius={4} />
          </div>
          <SkeletonBox width="100%" height={190} borderRadius={6} />
        </div>

        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "18px 20px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <SkeletonBox width={120} height={15} borderRadius={4} />
          <div style={{ display: "flex", justifyContent: "center", padding: "10px 0" }}>
            <SkeletonBox width={100} height={100} borderRadius="50%" />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <SkeletonBox width="100%" height={12} borderRadius={3} />
            <SkeletonBox width="80%" height={12} borderRadius={3} />
          </div>
        </div>
      </div>

      {/* Geographic Country Distribution Table */}
      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)" }}>
          <SkeletonBox width={190} height={14} borderRadius={4} />
        </div>
        {[1, 2, 3, 4].map((g) => (
          <div key={g} style={{ padding: "12px 18px", borderBottom: g === 4 ? "none" : "1px solid var(--surface-3)", display: "grid", gridTemplateColumns: "2fr 1fr 1fr 2fr", alignItems: "center" }}>
            <SkeletonBox width={120} height={13} borderRadius={3} />
            <SkeletonBox width={45} height={13} borderRadius={3} />
            <SkeletonBox width={55} height={13} borderRadius={3} />
            <SkeletonBox width="80%" height={8} borderRadius={3} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 5. Keyword Magic Tool Skeleton ──
export function KeywordMagicSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Search Input Bar & Match Pills */}
      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", gap: 10 }}>
          <SkeletonBox width="85%" height={36} borderRadius={6} />
          <SkeletonBox width="15%" height={36} borderRadius={6} />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {[1, 2, 3, 4].map((p) => (
            <SkeletonBox key={p} width={75} height={26} borderRadius={14} />
          ))}
        </div>
      </div>

      {/* 4 Metric Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {[1, 2, 3, 4].map((m) => (
          <div key={m} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 6 }}>
            <SkeletonBox width={85} height={11} borderRadius={4} />
            <SkeletonBox width={110} height={24} borderRadius={4} />
            <SkeletonBox width={90} height={10} borderRadius={3} />
          </div>
        ))}
      </div>

      {/* 2-Column Split: Clusters Sidebar + Keyword Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 12, alignItems: "start" }}>
        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "14px", display: "flex", flexDirection: "column", gap: 8 }}>
          <SkeletonBox width={100} height={13} borderRadius={4} />
          {[1, 2, 3, 4, 5, 6].map((cl) => (
            <div key={cl} style={{ padding: "8px 10px", borderRadius: 6, background: cl === 1 ? "#1e293b" : "var(--surface-2)", display: "flex", justifyContent: "space-between" }}>
              <SkeletonBox width={70} height={12} borderRadius={3} style={{ background: cl === 1 ? "#334155" : undefined }} />
              <SkeletonBox width={24} height={12} borderRadius={3} style={{ background: cl === 1 ? "#334155" : undefined }} />
            </div>
          ))}
        </div>

        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
          <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between" }}>
            <SkeletonBox width={140} height={14} borderRadius={4} />
            <SkeletonBox width={80} height={14} borderRadius={4} />
          </div>
          {[1, 2, 3, 4, 5, 6].map((kr) => (
            <div key={kr} style={{ padding: "14px 18px", borderBottom: kr === 6 ? "none" : "1px solid var(--surface-3)", display: "grid", gridTemplateColumns: "2.5fr 1fr 1fr 1fr 80px", alignItems: "center", gap: 10 }}>
              <SkeletonBox width={140 + kr * 18} height={13} borderRadius={3} />
              <SkeletonBox width={50} height={13} borderRadius={3} />
              <SkeletonBox width={45} height={13} borderRadius={3} />
              <SkeletonBox width={55} height={13} borderRadius={3} />
              <SkeletonBox width={65} height={24} borderRadius={6} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── 6. Keyword Data Lab Skeleton ──
export function KeywordDataLabSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* 4 Standard KPI Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <SkeletonBox width={80} height={11} borderRadius={4} />
              <SkeletonBox width={45} height={14} borderRadius={4} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
              <div>
                <SkeletonBox width={90} height={24} borderRadius={4} />
                <SkeletonBox width={65} height={10} borderRadius={3} style={{ marginTop: 4 }} />
              </div>
              <SkeletonBox width={54} height={22} borderRadius={4} />
            </div>
          </div>
        ))}
      </div>

      {/* Filter Toolbar */}
      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <SkeletonBox width={260} height={32} borderRadius={6} />
        <div style={{ display: "flex", gap: 8 }}>
          <SkeletonBox width={100} height={32} borderRadius={6} />
          <SkeletonBox width={90} height={32} borderRadius={6} />
        </div>
      </div>

      {/* Keywords Table */}
      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
        {[1, 2, 3, 4, 5, 6, 7].map((row) => (
          <div key={row} style={{ padding: "14px 18px", borderBottom: row === 7 ? "none" : "1px solid var(--surface-3)", display: "grid", gridTemplateColumns: "3fr 1fr 1fr 1fr 1fr 90px", alignItems: "center", gap: 10 }}>
            <SkeletonBox width={150 + row * 15} height={14} borderRadius={4} />
            <SkeletonBox width={60} height={18} borderRadius={10} />
            <SkeletonBox width={40} height={14} borderRadius={4} />
            <SkeletonBox width={55} height={14} borderRadius={4} />
            <SkeletonBox width={45} height={14} borderRadius={4} />
            <SkeletonBox width={80} height={26} borderRadius={6} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 7. Organic Research Skeleton ──
export function OrganicResearchSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 12 }}>
        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "18px 20px" }}>
          <SkeletonBox width={160} height={15} borderRadius={4} />
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 14 }}>
            {[1, 2, 3, 4, 5].map((p) => (
              <div key={p} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <SkeletonBox width={60} height={11} borderRadius={3} />
                  <SkeletonBox width={30} height={11} borderRadius={3} />
                </div>
                <SkeletonBox width="100%" height={7} borderRadius={3} />
              </div>
            ))}
          </div>
        </div>

        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "18px 20px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <SkeletonBox width={140} height={15} borderRadius={4} />
          <div style={{ display: "flex", justifyContent: "center", padding: "10px 0" }}>
            <SkeletonBox width={100} height={100} borderRadius="50%" />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <SkeletonBox width="100%" height={12} borderRadius={3} />
            <SkeletonBox width="80%" height={12} borderRadius={3} />
          </div>
        </div>
      </div>

      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)" }}>
          <SkeletonBox width={170} height={15} borderRadius={4} />
        </div>
        {[1, 2, 3, 4, 5, 6].map((row) => (
          <div key={row} style={{ padding: "14px 18px", borderBottom: row === 6 ? "none" : "1px solid var(--surface-3)", display: "grid", gridTemplateColumns: "3fr 1fr 1fr 1fr 1fr", alignItems: "center" }}>
            <SkeletonBox width={140 + row * 18} height={14} borderRadius={4} />
            <SkeletonBox width={60} height={18} borderRadius={10} />
            <SkeletonBox width={45} height={14} borderRadius={4} />
            <SkeletonBox width={55} height={14} borderRadius={4} />
            <SkeletonBox width={45} height={14} borderRadius={4} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 8. SERP Optimizer Skeleton ──
export function SerpOptimizerSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Top Banner & Device Switcher */}
      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "14px 18px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <SkeletonBox width={140} height={18} borderRadius={4} />
          <SkeletonBox width={220} height={13} borderRadius={4} />
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <SkeletonBox width={110} height={30} borderRadius={6} />
          <SkeletonBox width={100} height={30} borderRadius={6} />
        </div>
      </div>

      {/* Split: Left Real SERP Snippet Box + Right Live Meta Form */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 14, alignItems: "start" }}>
        <div style={{ background: "var(--surface)", borderRadius: 10, border: "1px solid var(--border)", padding: "20px", display: "flex", flexDirection: "column", gap: 14 }}>
          <SkeletonBox width={120} height={14} borderRadius={4} />
          <div style={{ padding: "16px", background: "var(--surface-2)", borderRadius: 8, border: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <SkeletonBox width={24} height={24} borderRadius="50%" />
              <SkeletonBox width={140} height={12} borderRadius={3} />
            </div>
            <SkeletonBox width="85%" height={20} borderRadius={4} />
            <SkeletonBox width="100%" height={36} borderRadius={4} />
          </div>
        </div>

        <div style={{ background: "var(--surface)", borderRadius: 10, border: "1px solid var(--border)", padding: "20px", display: "flex", flexDirection: "column", gap: 16 }}>
          <SkeletonBox width={140} height={16} borderRadius={4} />
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <SkeletonBox width={80} height={12} borderRadius={3} />
            <SkeletonBox width="100%" height={36} borderRadius={6} />
            <SkeletonBox width="100%" height={6} borderRadius={3} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <SkeletonBox width={100} height={12} borderRadius={3} />
            <SkeletonBox width="100%" height={70} borderRadius={6} />
            <SkeletonBox width="100%" height={6} borderRadius={3} />
          </div>
          <SkeletonBox width="100%" height={38} borderRadius={8} />
        </div>
      </div>
    </div>
  );
}

// ── 9. All Tools Directory Skeleton ──
export function AllToolsDirectorySkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Header Banner */}
      <div style={{ background: "#1e293b", borderRadius: 8, padding: "18px 22px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <SkeletonBox width={160} height={14} borderRadius={4} style={{ background: "#334155" }} />
          <SkeletonBox width={260} height={20} borderRadius={4} style={{ background: "#334155" }} />
        </div>
        <SkeletonBox width={130} height={36} borderRadius={6} style={{ background: "#334155" }} />
      </div>

      {/* Filter & Search Bar */}
      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
        <SkeletonBox width="100%" height={34} borderRadius={6} />
        <div style={{ display: "flex", gap: 8 }}>
          {[1, 2, 3, 4, 5, 6].map((p) => (
            <SkeletonBox key={p} width={80 + p * 8} height={26} borderRadius={14} />
          ))}
        </div>
      </div>

      {/* 3-Column Grid of 9 Tool Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((item) => (
          <div key={item} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 120 }}>
            <div style={{ display: "flex", gap: 10 }}>
              <SkeletonBox width={34} height={34} borderRadius={6} />
              <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
                <SkeletonBox width="80%" height={14} borderRadius={4} />
                <SkeletonBox width="100%" height={11} borderRadius={3} />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
              <SkeletonBox width={65} height={16} borderRadius={8} />
              <SkeletonBox width={60} height={24} borderRadius={4} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 10. Gap Skeleton (Keyword Gap & Backlink Gap) ──
export function GapSkeleton({ isBacklink = false }: { isBacklink?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Competitor Inputs Row */}
      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "14px 16px", display: "grid", gridTemplateColumns: "repeat(3, 1fr) 140px", gap: 10 }}>
        <SkeletonBox width="100%" height={34} borderRadius={6} />
        <SkeletonBox width="100%" height={34} borderRadius={6} />
        <SkeletonBox width="100%" height={34} borderRadius={6} />
        <SkeletonBox width="100%" height={34} borderRadius={6} />
      </div>

      {/* 4 Gap Summary Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {[1, 2, 3, 4].map((g) => (
          <div key={g} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 6 }}>
            <SkeletonBox width={80} height={11} borderRadius={4} />
            <SkeletonBox width={90} height={22} borderRadius={4} />
          </div>
        ))}
      </div>

      {/* Table */}
      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
        {[1, 2, 3, 4, 5, 6].map((r) => (
          <div key={r} style={{ padding: "14px 18px", borderBottom: r === 6 ? "none" : "1px solid var(--surface-3)", display: "grid", gridTemplateColumns: "2.5fr 1fr 1fr 1fr 80px", alignItems: "center", gap: 10 }}>
            <SkeletonBox width={140 + r * 15} height={13} borderRadius={3} />
            <SkeletonBox width={45} height={13} borderRadius={3} />
            <SkeletonBox width={45} height={13} borderRadius={3} />
            <SkeletonBox width={45} height={13} borderRadius={3} />
            <SkeletonBox width={70} height={22} borderRadius={6} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 11. On-Page SEO Skeleton ──
export function OnPageSeoSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Target URL Tabs */}
      <div style={{ display: "flex", gap: 8, background: "var(--surface)", padding: "10px 14px", borderRadius: 8, border: "1px solid var(--border)" }}>
        <SkeletonBox width={90} height={28} borderRadius={6} />
        <SkeletonBox width={160} height={28} borderRadius={6} />
        <SkeletonBox width={120} height={28} borderRadius={6} />
        <SkeletonBox width={140} height={28} borderRadius={6} />
      </div>

      {/* 4 Metric Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {[1, 2, 3, 4].map((m) => (
          <div key={m} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 6 }}>
            <SkeletonBox width={90} height={11} borderRadius={4} />
            <SkeletonBox width={110} height={24} borderRadius={4} />
            <SkeletonBox width={80} height={10} borderRadius={3} />
          </div>
        ))}
      </div>

      {/* Split: Entities Table + AI Content Draft */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 12, alignItems: "start" }}>
        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
          <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)" }}>
            <SkeletonBox width={160} height={14} borderRadius={4} />
          </div>
          {[1, 2, 3, 4, 5].map((e) => (
            <div key={e} style={{ padding: "12px 18px", borderBottom: e === 5 ? "none" : "1px solid var(--surface-3)", display: "grid", gridTemplateColumns: "2fr 1fr 1fr", alignItems: "center" }}>
              <SkeletonBox width={120 + e * 10} height={13} borderRadius={3} />
              <SkeletonBox width={45} height={13} borderRadius={3} />
              <SkeletonBox width={60} height={18} borderRadius={8} />
            </div>
          ))}
        </div>

        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "18px", display: "flex", flexDirection: "column", gap: 10 }}>
          <SkeletonBox width={140} height={15} borderRadius={4} />
          <SkeletonBox width="100%" height={120} borderRadius={6} />
          <SkeletonBox width={120} height={32} borderRadius={6} />
        </div>
      </div>
    </div>
  );
}

// ── 12. Local SEO Skeleton ──
export function LocalSeoSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {[1, 2, 3].map((l) => (
          <div key={l} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px 18px", display: "flex", flexDirection: "column", gap: 8 }}>
            <SkeletonBox width={120} height={12} borderRadius={4} />
            <SkeletonBox width={70} height={24} borderRadius={4} />
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "18px" }}>
          <SkeletonBox width={160} height={14} borderRadius={4} />
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 14 }}>
            {[1, 2, 3, 4].map((ci) => (
              <SkeletonBox key={ci} width="100%" height={24} borderRadius={4} />
            ))}
          </div>
        </div>

        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "18px" }}>
          <SkeletonBox width={180} height={14} borderRadius={4} />
          <SkeletonBox width="100%" height={160} borderRadius={6} style={{ marginTop: 14 }} />
        </div>
      </div>
    </div>
  );
}

// ── 13. AI & AEO Lab Skeleton ──
export function AiAeoSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {[1, 2, 3].map((a) => (
          <div key={a} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px 18px", display: "flex", flexDirection: "column", gap: 8 }}>
            <SkeletonBox width={110} height={12} borderRadius={4} />
            <SkeletonBox width={65} height={24} borderRadius={4} />
          </div>
        ))}
      </div>

      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "18px", display: "flex", flexDirection: "column", gap: 12 }}>
        <SkeletonBox width={200} height={16} borderRadius={4} />
        <SkeletonBox width="100%" height={80} borderRadius={6} />
        <SkeletonBox width={140} height={32} borderRadius={6} />
      </div>
    </div>
  );
}

// ── 14. Backlinks Analytics & Audit Skeletons ──
export function BacklinksAnalyticsSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {[1, 2, 3, 4].map((b) => (
          <div key={b} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px 18px", display: "flex", flexDirection: "column", gap: 8 }}>
            <SkeletonBox width={85} height={12} borderRadius={4} />
            <SkeletonBox width={95} height={24} borderRadius={4} />
          </div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12 }}>
        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "18px", height: 260 }}>
          <SkeletonBox width="100%" height="100%" borderRadius={6} />
        </div>
        <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "18px", height: 260 }}>
          <SkeletonBox width="100%" height="100%" borderRadius={6} />
        </div>
      </div>
      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
        {[1, 2, 3, 4, 5].map((r) => (
          <div key={r} style={{ padding: "12px 18px", borderBottom: r === 5 ? "none" : "1px solid var(--surface-3)", display: "grid", gridTemplateColumns: "2.5fr 1fr 1fr 1fr", alignItems: "center" }}>
            <SkeletonBox width={160} height={14} borderRadius={4} />
            <SkeletonBox width={45} height={14} borderRadius={4} />
            <SkeletonBox width={55} height={14} borderRadius={4} />
            <SkeletonBox width={65} height={14} borderRadius={4} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function BacklinkAuditSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "14px 18px" }}>
        <SkeletonBox width={260} height={16} borderRadius={4} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {[1, 2, 3].map((t) => (
          <div key={t} style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px", display: "flex", flexDirection: "column", gap: 6 }}>
            <SkeletonBox width={80} height={11} borderRadius={4} />
            <SkeletonBox width={60} height={22} borderRadius={4} />
          </div>
        ))}
      </div>
      <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden" }}>
        {[1, 2, 3, 4, 5].map((row) => (
          <div key={row} style={{ padding: "14px 18px", borderBottom: row === 5 ? "none" : "1px solid var(--surface-3)", display: "grid", gridTemplateColumns: "3fr 1fr 1fr 90px", alignItems: "center" }}>
            <SkeletonBox width={180} height={14} borderRadius={4} />
            <SkeletonBox width={50} height={18} borderRadius={10} />
            <SkeletonBox width={60} height={14} borderRadius={4} />
            <SkeletonBox width={80} height={26} borderRadius={6} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Smart Page-Specific Skeleton Dispatcher ──
export function PageSkeletonLayout({ tab }: { tab?: string }) {
  switch (tab) {
    case "Site Health & Audit":
      return <SiteAuditSkeleton />;
    case "Auto-Fix Engine":
      return <AutoFixSkeleton />;
    case "Traffic Analytics":
      return <TrafficAnalyticsSkeleton />;
    case "Organic Research":
      return <OrganicResearchSkeleton />;
    case "Keyword Gap":
    case "Backlink Gap":
      return <GapSkeleton isBacklink={tab === "Backlink Gap"} />;
    case "Keyword Data Lab":
      return <KeywordDataLabSkeleton />;
    case "Keyword Magic Tool":
      return <KeywordMagicSkeleton />;
    case "Data Lab & Backlinks":
      return <BacklinksAnalyticsSkeleton />;
    case "Backlink Audit":
      return <BacklinkAuditSkeleton />;
    case "On-Page SEO":
      return <OnPageSeoSkeleton />;
    case "SERP Optimizer":
      return <SerpOptimizerSkeleton />;
    case "Local SEO & GBP":
      return <LocalSeoSkeleton />;
    case "AI & AEO Lab":
      return <AiAeoSkeleton />;
    case "All Tools Directory":
      return <AllToolsDirectorySkeleton />;
    case "Overview":
    default:
      return <OverviewSkeleton />;
  }
}
