"use client";

import React, { useState } from "react";
import { Icon } from "@/components/dashboard/Icon";
import type { ReaiTab, NavSubTab, PriorityItem } from "./types";
import { ProjectJourney } from "./ProjectJourney";
import { PriorityActions } from "./PriorityActions";
import { derivePriorities } from "../../lib/priorities";
import { AuditHeroBar } from "./AuditHeroBar";
import { OverallScoreCard } from "./OverallScoreCard";

interface OverviewProps {
  onNavigate: (tab: ReaiTab, subTab?: NavSubTab) => void;
  onSelectPriorityAction?: (item: PriorityItem) => void;
  domain?: string;
  hasGsc?: boolean;
  onRunAudit?: (url: string) => void;
  isScanning?: boolean;
  phaseLine?: string;
  scanTools?: any[];
  liveLogs?: string[];
  report?: any;
  /** Journey evidence. Passed through, never assumed - see lib/journey. */
  client?: { scans?: number } | null;
  plan?: { worklist?: unknown[] } | null;
  remediations?: unknown[] | null;
}

export function Overview({
  onNavigate,
  onSelectPriorityAction,
  domain = "",
  hasGsc = false,
  onRunAudit,
  isScanning = false,
  phaseLine,
  scanTools = [],
  liveLogs = [],
  report,
  client = null,
  plan = null,
  remediations = null,
}: OverviewProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const rows = Object.values(report || {}).flatMap((v) => Array.isArray(v) ? v as any[] : []);
  const health = typeof report?.score === "number" ? report.score : null;
  const errors = rows.filter((r: any) => r?.severity === "error").length;
  const aeoRows = rows.filter((r: any) => String(r?.code || "").startsWith("aeo."));

  return (
    <div style={{ maxWidth: "100%", paddingBottom: 40 }}>
      {/* 1. PROJECT JOURNEY PROGRESS BAR */}
      <ProjectJourney
        client={client}
        hasGsc={hasGsc}
        report={report}
        plan={plan}
        remediations={remediations}
        onStepClick={(step) => {
          if (step === 2) onNavigate("Traffic Analytics", "Google Search Console");
          if (step === 3) onNavigate("Site Health & Audit");
          if (step === 5) onNavigate("Auto-Fix Engine", "Auto-Fix Review");
        }}
      />

      {/* 2. PROMINENT AUDIT SEARCH HERO */}
      <div style={{ marginBottom: 20 }}>
        <AuditHeroBar
          currentDomain={domain}
          onRunAudit={(url) => {
            if (onRunAudit) onRunAudit(url);
            else onNavigate("Site Health & Audit");
          }}
          isScanning={isScanning}
          phaseLine={phaseLine}
          scanTools={scanTools}
          liveLogs={liveLogs}
          pages={5}
          onPagesChange={() => {}}
        />
      </div>

      {/* 3. OVERALL SEO SCORE — four pillars, weighted, with its own breakdown. */}
      <div style={{ marginBottom: 20 }}>
        <OverallScoreCard
          report={report}
          onRunPillar={(key) => {
            if (key === "technical") onNavigate("Site Health & Audit");
            else if (key === "content") onNavigate("On-Page SEO", "Content");
            else if (key === "backlinks") onNavigate("Backlink Audit");
            else onNavigate("AI & AEO Lab");
          }}
        />
      </div>

      {/* 4. PRODUCT PRINCIPLE CALLOUT */}
      <div
        style={{
          background: "var(--ok-tint)",
          border: "1px solid var(--ok-border)",
          borderRadius: 8,
          padding: "12px 16px",
          marginBottom: 20,
          display: "flex",
          alignItems: "flex-start",
          gap: 12,
        }}
      >
        <Icon name="bulb" size={18} />
        <div>
          <div style={{ fontSize: 13.5, fontWeight: 700, color: "var(--ok)" }}>
            SEO is the foundation. AI Search Visibility builds on good SEO.
          </div>
          <div style={{ fontSize: 12, color: "var(--ok)", marginTop: 2 }}>
            SEO helps traditional search engines index and rank your pages. AI Search Visibility ensures AI answer engines (SearchGPT, Perplexity, Gemini) can accurately parse and cite your site.
            {" "}<span style={{ color: "var(--ok)", opacity: 0.8 }}>(Note: Technical optimizations improve extractability and schema clarity; they do not guarantee citations, rankings, or traffic).</span>
          </div>
        </div>
      </div>

      {/* 3. TWO PRIMARY STATUS CARDS ("IS MY SITE OKAY?") */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16, marginBottom: 24 }}>
        {/* Card 1: SEO Foundations */}
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "18px 20px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
        >
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
              <div>
                <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--ink)", margin: 0 }}>
                  SEO Foundations
                </h3>
                <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                  Site health, crawlability, and Google rankings
                </div>
              </div>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  padding: "2px 6px",
                  borderRadius: 4,
                  background: "var(--surface-3)",
                  color: "var(--ink-muted)",
                  border: "1px solid var(--border)",
                }}
              >
                {health === null ? "Not measured" : "Measured"}
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "baseline", gap: 10, margin: "14px 0" }}>
              <div style={{ fontSize: 36, fontWeight: 800, color: "var(--ok)", lineHeight: 1 }}>
                {health === null ? "—" : health}
              </div>
              <div style={{ fontSize: 13, color: "var(--ink-muted)" }}>
                / 100 Health Score
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
              <div style={{ background: "var(--surface-2)", padding: "8px 10px", borderRadius: 6 }}>
                <span style={{ color: "var(--ink-muted)" }}>Critical Issues: </span>
                <strong style={{ color: "var(--bad)" }}>{health === null ? "—" : errors}</strong>
              </div>
              <div style={{ background: "var(--surface-2)", padding: "8px 10px", borderRadius: 6 }}>
                <span style={{ color: "var(--ink-muted)" }}>Ranked Keywords: </span>
                <strong style={{ color: "var(--ink)" }}>—</strong>
              </div>
            </div>
          </div>

          <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid var(--surface-3)" }}>
            <button
              type="button"
              onClick={() => onNavigate("Site Health & Audit")}
              style={{
                width: "100%",
                padding: "8px 12px",
                background: "var(--surface-2)",
                color: "var(--ink-body)",
                border: "1px solid var(--border-strong)",
                borderRadius: 6,
                fontSize: 12.5,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              View Technical SEO Details →
            </button>
          </div>
        </div>

        {/* Card 2: AI Search Visibility (AEO) */}
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "18px 20px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
        >
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
              <div>
                <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--ink)", margin: 0 }}>
                  AI Search Visibility (AEO)
                </h3>
                <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                  Readiness for SearchGPT, Perplexity & AI Overviews
                </div>
              </div>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  padding: "2px 6px",
                  borderRadius: 4,
                  background: "var(--warn-tint)",
                  color: "var(--warn)",
                  border: "1px solid var(--warn-border)",
                }}
              >
                Estimated
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "baseline", gap: 10, margin: "14px 0" }}>
              <div style={{ fontSize: 36, fontWeight: 800, color: "var(--accent)", lineHeight: 1 }}>
                {aeoRows.length ? `${Math.round((aeoRows.filter((r: any) => r.severity === "ok").length / aeoRows.length) * 100)}%` : "—"}
              </div>
              <div style={{ fontSize: 13, color: "var(--ink-muted)" }}>
                AI Answer Readiness
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
              <div style={{ background: "var(--surface-2)", padding: "8px 10px", borderRadius: 6 }}>
                <span style={{ color: "var(--ink-muted)" }}>AI Crawlers: </span>
                <strong style={{ color: "var(--ink-muted)" }}>Not measured</strong>
              </div>
              <div style={{ background: "var(--surface-2)", padding: "8px 10px", borderRadius: 6 }}>
                <span style={{ color: "var(--ink-muted)" }}>Schema Clarity: </span>
                <strong style={{ color: "var(--ink-muted)" }}>Not measured</strong>
              </div>
            </div>
          </div>

          <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid var(--surface-3)" }}>
            <button
              type="button"
              onClick={() => onNavigate("AI & AEO Lab", "AI Readiness")}
              style={{
                width: "100%",
                padding: "8px 12px",
                background: "var(--accent-tint)",
                color: "var(--accent)",
                border: "1px solid var(--accent-border)",
                borderRadius: 6,
                fontSize: 12.5,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Explore AI Visibility →
            </button>
          </div>
        </div>
      </div>

      {/* 4. TOP PRIORITIES (THE REAL CENTER OF THE PRODUCT) */}
      <PriorityActions
        priorities={derivePriorities(report) as unknown as PriorityItem[]}
        onSelectAction={(priority) => {
          if (onSelectPriorityAction) {
            onSelectPriorityAction(priority);
          } else if (priority.actionTab) {
            onNavigate(priority.actionTab, priority.actionSubTab);
          }
        }}
      />

      {/* 5. PROGRESSIVE DISCLOSURE: ADVANCED DIAGNOSTICS TOGGLE */}
      <div style={{ marginTop: 24, textAlign: "center" }}>
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border-strong)",
            borderRadius: 20,
            padding: "8px 18px",
            fontSize: 12.5,
            fontWeight: 600,
            color: "var(--ink-muted)",
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
          }}
        >
          {showAdvanced ? "Hide Advanced Analytics & Technical Details ▲" : "Show Advanced Analytics & Technical Details ▼"}
        </button>
      </div>

      {/* Collapsible Advanced Analytics */}
      {showAdvanced && (
        <div
          style={{
            marginTop: 20,
            padding: 20,
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <h4 style={{ fontSize: 14, fontWeight: 700, color: "var(--ink)", margin: 0 }}>
              Advanced Technical Diagnostics & Traffic Distributions
            </h4>
            <span
              style={{
                fontSize: 12,
                padding: "2px 6px",
                borderRadius: 4,
                background: "var(--warn-tint)",
                color: "var(--warn)",
                fontWeight: 600,
              }}
            >
              Needs Google Search Console connection for live precision
            </span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14, fontSize: 12.5 }}>
            <div style={{ background: "var(--surface-2)", padding: 14, borderRadius: 6 }}>
              <div style={{ fontWeight: 600, color: "var(--ink-body)", marginBottom: 6 }}>Core Web Vitals (CrUX)</div>
              <div style={{ color: "var(--ink-muted)" }}>Largest Contentful Paint (LCP): <strong>Not measured</strong></div>
              <div style={{ color: "var(--ink-muted)" }}>Interaction to Next Paint (INP): <strong>Not measured</strong></div>
              <div style={{ color: "var(--ink-muted)" }}>Cumulative Layout Shift (CLS): <strong>Not measured</strong></div>
            </div>

            <div style={{ background: "var(--surface-2)", padding: 14, borderRadius: 6 }}>
              <div style={{ fontWeight: 600, color: "var(--ink-body)", marginBottom: 6 }}>Crawl Diagnostic Summary</div>
              <div style={{ color: "var(--ink-muted)" }}>Robots.txt: <strong>Not measured</strong></div>
              <div style={{ color: "var(--ink-muted)" }}>XML Sitemap: <strong>Not measured</strong></div>
              <div style={{ color: "var(--ink-muted)" }}>Canonical Tags: <strong>Not measured</strong></div>
            </div>

            <div style={{ background: "var(--surface-2)", padding: 14, borderRadius: 6 }}>
              <div style={{ fontWeight: 600, color: "var(--ink-body)", marginBottom: 6 }}>AI Crawler Status</div>
              <div style={{ color: "var(--ink-muted)" }}>GPTBot: <strong>Not measured</strong></div>
              <div style={{ color: "var(--ink-muted)" }}>ClaudeBot: <strong>Not measured</strong></div>
              <div style={{ color: "var(--ink-muted)" }}>PerplexityBot: <strong>Not measured</strong></div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
