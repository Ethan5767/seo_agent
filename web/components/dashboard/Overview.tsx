"use client";

import React, { useState } from "react";
import type { ReaiTab, NavSubTab, PriorityItem } from "./types";
import { ProjectJourney } from "./ProjectJourney";
import { PriorityActions } from "./PriorityActions";
import { derivePriorities } from "../../lib/priorities";
import { AuditHeroBar } from "./AuditHeroBar";

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
  domain = "example.com",
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
          report={report}
          onSelectFix={(code) => onNavigate("Auto-Fix Engine", "Auto-Fix Review")}
        />
      </div>

      {/* 3. PRODUCT PRINCIPLE CALLOUT */}
      <div
        style={{
          background: "#f0fdf4",
          border: "1px solid #bbf7d0",
          borderRadius: 8,
          padding: "12px 16px",
          marginBottom: 20,
          display: "flex",
          alignItems: "flex-start",
          gap: 12,
        }}
      >
        <span style={{ fontSize: 18, lineHeight: 1 }}>💡</span>
        <div>
          <div style={{ fontSize: 13.5, fontWeight: 700, color: "#166534" }}>
            SEO is the foundation. AI Search Visibility builds on good SEO.
          </div>
          <div style={{ fontSize: 12, color: "#15803d", marginTop: 2 }}>
            SEO helps traditional search engines index and rank your pages. AI Search Visibility ensures AI answer engines (SearchGPT, Perplexity, Gemini) can accurately parse and cite your site.
            {" "}<span style={{ color: "#166534", opacity: 0.8 }}>(Note: Technical optimizations improve extractability and schema clarity; they do not guarantee citations, rankings, or traffic).</span>
          </div>
        </div>
      </div>

      {/* 3. TWO PRIMARY STATUS CARDS ("IS MY SITE OKAY?") */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16, marginBottom: 24 }}>
        {/* Card 1: SEO Foundations */}
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid #e2e8f0",
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
                  border: "1px solid #e2e8f0",
                }}
              >
                Demo data
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "baseline", gap: 10, margin: "14px 0" }}>
              <div style={{ fontSize: 36, fontWeight: 800, color: "var(--ok)", lineHeight: 1 }}>
                88
              </div>
              <div style={{ fontSize: 13, color: "var(--ink-muted)" }}>
                / 100 Health Score
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
              <div style={{ background: "var(--surface-2)", padding: "8px 10px", borderRadius: 6 }}>
                <span style={{ color: "var(--ink-muted)" }}>Critical Issues: </span>
                <strong style={{ color: "#dc2626" }}>2</strong>
              </div>
              <div style={{ background: "var(--surface-2)", padding: "8px 10px", borderRadius: 6 }}>
                <span style={{ color: "var(--ink-muted)" }}>Ranked Keywords: </span>
                <strong style={{ color: "var(--ink)" }}>428</strong>
              </div>
            </div>
          </div>

          <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid #f1f5f9" }}>
            <button
              type="button"
              onClick={() => onNavigate("Site Health & Audit")}
              style={{
                width: "100%",
                padding: "8px 12px",
                background: "var(--surface-2)",
                color: "var(--ink-body)",
                border: "1px solid #cbd5e1",
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
            border: "1px solid #e2e8f0",
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
                  background: "#fef3c7",
                  color: "#92400e",
                  border: "1px solid #fde68a",
                }}
              >
                Estimated
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "baseline", gap: 10, margin: "14px 0" }}>
              <div style={{ fontSize: 36, fontWeight: 800, color: "#7c3aed", lineHeight: 1 }}>
                74%
              </div>
              <div style={{ fontSize: 13, color: "var(--ink-muted)" }}>
                AI Answer Readiness
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
              <div style={{ background: "var(--surface-2)", padding: "8px 10px", borderRadius: 6 }}>
                <span style={{ color: "var(--ink-muted)" }}>AI Crawlers: </span>
                <strong style={{ color: "#166534" }}>Allowed</strong>
              </div>
              <div style={{ background: "var(--surface-2)", padding: "8px 10px", borderRadius: 6 }}>
                <span style={{ color: "var(--ink-muted)" }}>Schema Clarity: </span>
                <strong style={{ color: "#d97706" }}>Needs Review</strong>
              </div>
            </div>
          </div>

          <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid #f1f5f9" }}>
            <button
              type="button"
              onClick={() => onNavigate("AI & AEO Lab", "AI Readiness")}
              style={{
                width: "100%",
                padding: "8px 12px",
                background: "#f5f3ff",
                color: "#6d28d9",
                border: "1px solid #ddd6fe",
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
            border: "1px solid #cbd5e1",
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
            border: "1px solid #e2e8f0",
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
                background: "#fef3c7",
                color: "#92400e",
                fontWeight: 600,
              }}
            >
              Needs Google Search Console connection for live precision
            </span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14, fontSize: 12.5 }}>
            <div style={{ background: "var(--surface-2)", padding: 14, borderRadius: 6 }}>
              <div style={{ fontWeight: 600, color: "var(--ink-body)", marginBottom: 6 }}>Core Web Vitals (CrUX)</div>
              <div style={{ color: "var(--ink-muted)" }}>Largest Contentful Paint (LCP): <strong style={{ color: "#d97706" }}>2.9s (Needs Work)</strong></div>
              <div style={{ color: "var(--ink-muted)" }}>Interaction to Next Paint (INP): <strong style={{ color: "var(--ok)" }}>140ms (Good)</strong></div>
              <div style={{ color: "var(--ink-muted)" }}>Cumulative Layout Shift (CLS): <strong style={{ color: "var(--ok)" }}>0.04 (Good)</strong></div>
            </div>

            <div style={{ background: "var(--surface-2)", padding: 14, borderRadius: 6 }}>
              <div style={{ fontWeight: 600, color: "var(--ink-body)", marginBottom: 6 }}>Crawl Diagnostic Summary</div>
              <div style={{ color: "var(--ink-muted)" }}>Robots.txt: <strong style={{ color: "var(--ok)" }}>Valid & Crawlable</strong></div>
              <div style={{ color: "var(--ink-muted)" }}>XML Sitemap: <strong style={{ color: "var(--ok)" }}>Indexed (142 URLs)</strong></div>
              <div style={{ color: "var(--ink-muted)" }}>Canonical Tags: <strong style={{ color: "var(--ok)" }}>98% Consistent</strong></div>
            </div>

            <div style={{ background: "var(--surface-2)", padding: 14, borderRadius: 6 }}>
              <div style={{ fontWeight: 600, color: "var(--ink-body)", marginBottom: 6 }}>AI Crawler Status</div>
              <div style={{ color: "var(--ink-muted)" }}>GPTBot: <strong style={{ color: "var(--ok)" }}>Allowed</strong></div>
              <div style={{ color: "var(--ink-muted)" }}>ClaudeBot: <strong style={{ color: "var(--ok)" }}>Allowed</strong></div>
              <div style={{ color: "var(--ink-muted)" }}>PerplexityBot: <strong style={{ color: "var(--ok)" }}>Allowed</strong></div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
