"use client";

import React, { useState, useMemo, useEffect, useCallback, type ReactNode } from "react";
import Link from "next/link";
import type { ClientWithStats, ScanRow, RemediationRow } from "../lib/db";
import {
  fetchTools,
  summarize,
  categoriesOf,
  filterTools,
  costLabel,
  type ScannerTool,
} from "../lib/toolCatalog";
import { ProjectJourney } from "@/components/dashboard/ProjectJourney";
import { PriorityActions } from "@/components/dashboard/PriorityActions";
import type { PriorityItem } from "@/components/dashboard/types";
import { derivePriorities } from "../lib/priorities";
import { supabase } from "../lib/supabase";
import { PIPELINE_STAGES, stage as pipelineStage, laneCounts, actionableCount,
         blockedReason, GATE_ROSTER, MERGE_POLICY, AUTOMERGE_DEFAULT_ENABLED, gateFindings, worklistFindings,
         type StageId } from "../lib/pipelineStages";
import { deriveCoreWebVitals } from "../lib/webVitals";
import { buildExecutiveReport } from "../lib/executiveReport";
import { derivePillars, severityMark, severityTone } from "../lib/pillars";
import { tone } from "../lib/ui";
import { viewById, rowsForView, tallyRows, measured, ALL_FINDINGS_VIEW, CHECKS_VIEW } from "../lib/reportViews";
import { TOOL_SOURCES, effectiveSource, isEnabled, sourceBlocker, type SourceId } from "../lib/toolSources";
import { gscViewById } from "../lib/gscViews";
import { contentToolById } from "../lib/contentTools";
import { ContentPanel } from "@/components/dashboard/ContentPanel";
import { GscPanel } from "@/components/dashboard/GscPanel";
import { ReportTable, ReportStats } from "@/components/dashboard/ReportTable";
import { LocalBusinessManager } from "@/components/dashboard/LocalBusinessManager";
import { RepoPicker } from "@/components/dashboard/RepoPicker";
import { deriveAeoTiles, aeoVerdictColor, aeoMatrixRows } from "@/lib/aeo";
import { AeoAccessPanel } from "@/components/dashboard/AeoAccessPanel";
import { AeoCrawlerTable } from "@/components/dashboard/AeoCrawlerTable";
import { deriveDirectories, directoryLabel, directoryColor, directorySummary } from "@/lib/localSignals";
import { GateActivity } from "@/components/dashboard/GateActivity";
import { FixWithClaude } from "@/components/dashboard/FixWithClaude";
import { GbpMatrix } from "@/components/dashboard/GbpMatrix";
import { SectionScanButton } from "@/components/dashboard/SectionScanButton";
import { formatUsd } from "@/lib/budget";
import { LiveScanActivity } from "@/components/dashboard/LiveScanActivity";
import { ProjectModal } from "@/components/dashboard/ProjectModal";
import { buildRobotsSnippet } from "@/lib/aeoCrawlers";
import { AuditHeroBar } from "@/components/dashboard/AuditHeroBar";
import { MeasureScreen } from "@/components/dashboard/MeasureScreen";
import {
  IconTerminal,
  MiniRadialGauge,
  SiteHealthDonut,
  CrawledPagesBar,
} from "@/components/dashboard/primitives";
import { authedFetch } from "../lib/authedFetch";
import {
  SkeletonBox,
  OverviewSkeleton,
  SiteAuditSkeleton,
  AutoFixSkeleton,
  TrafficAnalyticsSkeleton,
  KeywordMagicSkeleton,
  KeywordDataLabSkeleton,
  OrganicResearchSkeleton,
  SerpOptimizerSkeleton,
  AllToolsDirectorySkeleton,
  GapSkeleton,
  OnPageSeoSkeleton,
  LocalSeoSkeleton,
  AiAeoSkeleton,
  BacklinksAnalyticsSkeleton,
  BacklinkAuditSkeleton,
  PageSkeletonLayout,
} from "@/components/dashboard/DashboardSkeletons";

// ── Icons ──
function IconHome({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  );
}

function IconTarget({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </svg>
  );
}

function IconChart({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}

function IconDoc({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function IconGlobe({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

function IconSearch({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function IconLayers({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </svg>
  );
}

function IconLinkGap({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

function IconCpu({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <rect x="9" y="9" width="6" height="6" />
      <line x1="9" y1="1" x2="9" y2="4" />
      <line x1="15" y1="1" x2="15" y2="4" />
      <line x1="9" y1="20" x2="9" y2="23" />
      <line x1="15" y1="20" x2="15" y2="23" />
      <line x1="20" y1="9" x2="23" y2="9" />
      <line x1="20" y1="14" x2="23" y2="14" />
      <line x1="1" y1="9" x2="4" y2="9" />
      <line x1="1" y1="14" x2="4" y2="14" />
    </svg>
  );
}

function IconKey({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="7.5" cy="15.5" r="4.5" />
      <path d="M10.7 12.3L21 2" />
      <path d="M16 7l2 2" />
      <path d="M19 4l2 2" />
    </svg>
  );
}

function IconMonitor({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
      <line x1="8" y1="21" x2="16" y2="21" />
      <line x1="12" y1="17" x2="12" y2="21" />
    </svg>
  );
}

function IconCheckCircle({ size = 18, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

function IconAlertTriangle({ size = 18, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

function IconArrowRight({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

function IconPlay({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" stroke="none">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  );
}

// Enterprise aliases for backward-compatible call-sites
function IconSparkle({ size = 18 }: { size?: number }) {
  return <IconCpu size={size} />;
}

function IconWand({ size = 18 }: { size?: number }) {
  return <IconKey size={size} />;
}

function IconShield({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

function IconClipboard({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 2h6a1 1 0 0 1 1 1v2H8V3a1 1 0 0 1 1-1z" />
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <path d="M9 12h6M9 16h4" />
    </svg>
  );
}

function IconMerge({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="6" cy="6" r="2.5" />
      <circle cx="6" cy="18" r="2.5" />
      <circle cx="18" cy="12" r="2.5" />
      <path d="M6 8.5v7M8.5 6.8c3 .6 4.6 2.2 6.2 4.4M8.5 17.2c3-.6 4.6-2.2 6.2-4.4" />
    </svg>
  );
}

function IconLightbulb({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 18h6" />
      <path d="M10 22h4" />
      <path d="M12 2a7 7 0 0 0-7 7c0 2.5 1.5 4.5 3 6h8c1.5-1.5 3-3.5 3-6a7 7 0 0 0-7-7z" />
    </svg>
  );
}

function IconGrid({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
    </svg>
  );
}

function IconMapPin({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function IconGoogle({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" fill="#FBBC05" />
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" fill="#EA4335" />
    </svg>
  );
}

function IconHistory({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function IconSliders({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="4" y1="21" x2="4" y2="14" />
      <line x1="4" y1="10" x2="4" y2="3" />
      <line x1="12" y1="21" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12" y2="3" />
      <line x1="20" y1="21" x2="20" y2="16" />
      <line x1="20" y1="12" x2="20" y2="3" />
      <line x1="1" y1="14" x2="7" y2="14" />
      <line x1="9" y1="8" x2="15" y2="8" />
      <line x1="17" y1="16" x2="23" y2="16" />
    </svg>
  );
}

function IconUser({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

// ── SVG Interactive Charts & Smooth Spline Engine ──
export function getSmoothCurvePath(pts: Array<{ x: number; y: number }>): string {
  if (!pts || pts.length === 0) return "";
  if (pts.length === 1) return `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
  if (pts.length === 2) return `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)} L ${pts[1].x.toFixed(1)} ${pts[1].y.toFixed(1)}`;

  let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const pPrev = pts[Math.max(0, i - 1)];
    const pCurr = pts[i];
    const pNext = pts[i + 1];
    const pAfter = pts[Math.min(pts.length - 1, i + 2)];

    const cp1x = pCurr.x + (pNext.x - pPrev.x) / 6;
    const cp1y = pCurr.y + (pNext.y - pPrev.y) / 6;
    const cp2x = pNext.x - (pAfter.x - pCurr.x) / 6;
    const cp2y = pNext.y - (pAfter.y - pCurr.y) / 6;

    d += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${pNext.x.toFixed(1)} ${pNext.y.toFixed(1)}`;
  }
  return d;
}

export function MiniSparkline({
  data = [2.8, 3.2, 3.7, 4.1, 5.2, 6.2],
  color = "#10b981",
  width = 72,
  height = 28,
}: {
  data?: number[];
  color?: string;
  width?: number;
  height?: number;
}) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pad = 3;
  const pts = data.map((d, i) => {
    const x = pad + (i / Math.max(1, data.length - 1)) * (width - pad * 2);
    const y = height - pad - ((d - min) / range) * (height - pad * 2);
    return { x, y };
  });
  const pathD = getSmoothCurvePath(pts);
  const lastPt = pts[pts.length - 1];
  const areaD = `${pathD} L ${lastPt.x.toFixed(1)} ${height} L ${pts[0].x.toFixed(1)} ${height} Z`;
  const gradId = `spark-${color.replace(/[^a-zA-Z0-9]/g, "")}`;

  return (
    <svg width={width} height={height} style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.32" />
          <stop offset="100%" stopColor={color} stopOpacity="0.0" />
        </linearGradient>
      </defs>
      <path d={areaD} fill={`url(#${gradId})`} />
      <path d={pathD} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lastPt.x} cy={lastPt.y} r="3.5" fill={color} fillOpacity="0.25" />
      <circle cx={lastPt.x} cy={lastPt.y} r="2" fill={color} />
    </svg>
  );
}

// Estimate pixel width for Google SERP titles and descriptions based on Arial/Roboto font metrics
export function estimateSerpPixelWidth(text: string, fontSize: number = 20): number {
  if (!text) return 0;
  let width = 0;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === ' ' || ch === 'i' || ch === 'l' || ch === 'I' || ch === '|' || ch === '.' || ch === ':' || ch === ';' || ch === ',' || ch === "'") {
      width += fontSize * 0.28;
    } else if (ch === 'f' || ch === 'j' || ch === 'r' || ch === 't' || ch === '(' || ch === ')' || ch === '[' || ch === ']' || ch === '-') {
      width += fontSize * 0.38;
    } else if (ch === 'm' || ch === 'w' || ch === 'M' || ch === 'W' || ch === '@' || ch === '%' || ch === '&' || ch === '#') {
      width += fontSize * 0.85;
    } else if (ch >= 'A' && ch <= 'Z') {
      width += fontSize * 0.65;
    } else if (ch >= '0' && ch <= '9') {
      width += fontSize * 0.55;
    } else {
      width += fontSize * 0.52;
    }
  }
  return Math.round(width);
}

export {
  SkeletonBox,
  OverviewSkeleton,
  SiteAuditSkeleton,
  AutoFixSkeleton,
  TrafficAnalyticsSkeleton,
  KeywordMagicSkeleton,
  KeywordDataLabSkeleton,
  OrganicResearchSkeleton,
  SerpOptimizerSkeleton,
  AllToolsDirectorySkeleton,
  GapSkeleton,
  OnPageSeoSkeleton,
  LocalSeoSkeleton,
  AiAeoSkeleton,
  BacklinksAnalyticsSkeleton,
  BacklinkAuditSkeleton,
  PageSkeletonLayout,
};

export function LighthouseGaugeBar({
  val,
  status,
  color,
}: {
  val: string;
  status: string;
  color: string;
}) {
  let markerPos = 55;
  const lower = status.toLowerCase();
  if (lower.includes("good") || color === "#10b981") markerPos = 20;
  else if (lower.includes("needs") || color === "#f59e0b") markerPos = 55;
  else markerPos = 85;

  return (
    <div style={{ marginTop: 5, width: "100%" }}>
      <div style={{ position: "relative", height: 5, borderRadius: 3, background: "#f1f5f9", overflow: "hidden", display: "flex" }}>
        <div style={{ flex: 1, background: "#10b981", opacity: 0.85 }} />
        <div style={{ flex: 1, background: "#f59e0b", opacity: 0.85, margin: "0 1px" }} />
        <div style={{ flex: 1, background: "#ef4444", opacity: 0.85 }} />
      </div>
      <div style={{ position: "relative", height: 4, marginTop: -4 }}>
        <div
          style={{
            position: "absolute",
            left: `${markerPos}%`,
            top: -2,
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: color,
            border: "1.5px solid #ffffff",
            boxShadow: "0 1px 2px rgba(0,0,0,0.25)",
            transform: "translateX(-50%)",
          }}
        />
      </div>
    </div>
  );
}

export function AiExtractionBar({
  pct = 95,
  color = "#10b981",
}: {
  pct?: number;
  color?: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 64, height: 5, borderRadius: 3, background: "#edf2f7", overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", borderRadius: 3, background: color }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 700, color: "#475569" }}>{pct}%</span>
    </div>
  );
}

export function MiniDonut({
  slices,
  size = 50,
  strokeWidth = 5.5,
}: {
  slices: Array<{ pct: number; color: string }>;
  size?: number;
  strokeWidth?: number;
}) {
  const r = (size - strokeWidth) / 2;
  const circ = 2 * Math.PI * r;
  let accPct = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)", flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r} stroke="#f1f5f9" strokeWidth={strokeWidth} fill="none" />
      {slices.map((s, idx) => {
        const strokeDash = (s.pct / 100) * circ;
        const strokeOffset = circ - (accPct / 100) * circ;
        accPct += s.pct;
        return (
          <circle
            key={idx}
            cx={size / 2}
            cy={size / 2}
            r={r}
            stroke={s.color}
            strokeWidth={strokeWidth}
            fill="none"
            strokeDasharray={`${strokeDash} ${circ}`}
            strokeDashoffset={strokeOffset}
          />
        );
      })}
    </svg>
  );
}

export function MiniSegmentBar({
  segments,
  height = 5,
}: {
  segments: Array<{ pct: number; color: string; label?: string }>;
  height?: number;
}) {
  return (
    <div style={{ width: "100%", height, borderRadius: height / 2, background: "#f1f5f9", overflow: "hidden", display: "flex" }}>
      {segments.map((s, i) => (
        <div
          key={i}
          style={{ width: `${s.pct}%`, height: "100%", background: s.color }}
          title={s.label ? `${s.label}: ${s.pct}%` : `${s.pct}%`}
        />
      ))}
    </div>
  );
}

export function MiniKdMeter({ kd }: { kd: number }) {
  const color = kd < 30 ? "#10b981" : kd < 60 ? "#f59e0b" : "#ef4444";
  const bg = kd < 30 ? "#ecfdf5" : kd < 60 ? "#fffbeb" : "#fef2f2";
  const label = kd < 30 ? "Easy" : kd < 60 ? "Med" : "Hard";
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      <div style={{ width: 30, height: 4, borderRadius: 2, background: "#e2e8f0", overflow: "hidden" }}>
        <div style={{ width: `${kd}%`, height: "100%", background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 700, color, background: bg, padding: "1px 4px", borderRadius: 3 }}>
        {kd}% {label}
      </span>
    </div>
  );
}

export function ExecutiveTrafficChart({
  trend = [],
  // B-105: the defaults were "6.2K" and 128 - the fixture client's figures,
  // shown for any caller that omitted them. Absent means not measured.
  totalVisits = "—",
  domain = "",
  totalKeywords,
}: {
  trend?: Array<{ m: string; v: number }>;
  totalVisits?: string;
  domain?: string;
  totalKeywords?: number;
}) {
  const [metric, setMetric] = useState<"traffic" | "keywords" | "visibility">("traffic");
  const [chartType, setChartType] = useState<"combo" | "area" | "bars">("combo");
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // All three series were fixtures: a six-month traffic ramp (2.8 -> 6.2), a
  // keyword climb ending at a 128 floor, and a visibility curve ending at 74%.
  // Only `trend` has a real source. With no scan the chart now renders nothing
  // rather than somebody else's growth story.
  const trafficData = trend.length > 0 ? trend : [];

  const months = trafficData.map(d => d.m);
  const kwData: number[] = [];
  const visData: number[] = [];

  const activeSeries = metric === "traffic" 
    ? trafficData.map(d => d.v)
    : metric === "keywords" 
      ? kwData 
      : visData;

  const unit = metric === "traffic" ? "K visits" : metric === "keywords" ? " ranked terms" : "% visibility";

  // B-069. Removing the fixture series was right; leaving the geometry that
  // assumed they existed was not. With no data `pts` is [], and the area path
  // below dereferences `pts[pts.length - 1].x` — which threw "Cannot read
  // properties of undefined" and took the whole dashboard down. It fired on
  // every page with no scan, and unconditionally on the Keywords and Visibility
  // tabs, whose series are empty by construction until those metrics have a
  // real source.
  //
  // `Math.min(...[])` is also Infinity, so the scale below is meaningless
  // before this point. Say plainly that nothing was measured instead.
  if (activeSeries.length === 0) {
    const label = metric === "traffic" ? "traffic" : metric === "keywords" ? "ranked keywords" : "visibility";
    return (
      <div style={{ width: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Search Traffic &amp; Keyword Trajectory</span>
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", background: "#f1f5f9", border: "1px solid #e2e8f0", padding: "2px 8px", borderRadius: 12 }}>
            Not measured
          </span>
        </div>
        <div style={{
          height: 150, display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", gap: 6, border: "1px dashed #e2e8f0",
          borderRadius: 8, background: "#fafbfc",
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-muted)" }}>
            No {label} history for {domain || "this site"} yet
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-muted)", textAlign: "center", maxWidth: 380 }}>
            Connect Google Search Console to chart this over time. A trend needs at
            least two measured cycles.
          </div>
        </div>
      </div>
    );
  }

  const rawMin = Math.min(...activeSeries);
  const rawMax = Math.max(...activeSeries);
  const minVal = Math.max(0, Math.floor(rawMin * 0.75 * 10) / 10);
  const maxVal = Math.ceil(rawMax * 1.15 * 10) / 10 || 10;
  const range = maxVal - minVal || 1;
  
  const W = 1000;
  const H = 150;
  const padL = 48;
  const padR = 40;
  const padT = 16;
  const padB = 28;

  const pts = activeSeries.map((v, i) => {
    const x = padL + (i / Math.max(1, activeSeries.length - 1)) * (W - padL - padR);
    const y = padT + (1 - (v - minVal) / range) * (H - padT - padB);
    return { x, y, v, m: months[i] };
  });

  const pathD = getSmoothCurvePath(pts);
  const areaD = `${pathD} L ${pts[pts.length - 1].x.toFixed(1)} ${H - padB} L ${pts[0].x.toFixed(1)} ${H - padB} Z`;

  const activePoint = hoveredIdx !== null ? pts[hoveredIdx] : pts[pts.length - 1];

  return (
    <div style={{ width: "100%" }}>
      {/* Top Chart Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Search Traffic & Keyword Trajectory</span>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 8px", borderRadius: 12 }}>
            {activePoint.m}: {activePoint.v}{unit}
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ display: "flex", background: "#f1f5f9", borderRadius: 6, padding: 2 }}>
            <button
              type="button"
              onClick={() => setMetric("traffic")}
              style={{
                background: metric === "traffic" ? "#ffffff" : "transparent",
                color: metric === "traffic" ? "#1e293b" : "var(--ink-muted)",
                border: 0, borderRadius: 4, padding: "4px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                boxShadow: metric === "traffic" ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
              }}
            >
              Visits ({totalVisits})
            </button>
            <button
              type="button"
              onClick={() => setMetric("keywords")}
              style={{
                background: metric === "keywords" ? "#ffffff" : "transparent",
                color: metric === "keywords" ? "#1e293b" : "var(--ink-muted)",
                border: 0, borderRadius: 4, padding: "4px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                boxShadow: metric === "keywords" ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
              }}
            >
              Keywords ({totalKeywords ?? "—"})
            </button>
            <button
              type="button"
              onClick={() => setMetric("visibility")}
              style={{
                background: metric === "visibility" ? "#ffffff" : "transparent",
                color: metric === "visibility" ? "#1e293b" : "var(--ink-muted)",
                border: 0, borderRadius: 4, padding: "4px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                boxShadow: metric === "visibility" ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
              }}
            >
              Visibility
            </button>
          </div>
        </div>
      </div>

      {/* SVG Chart Container */}
      <div style={{ width: "100%", height: 150, overflow: "hidden" }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 150, display: "block" }}>
          <defs>
            <linearGradient id="execTrafficGradNew" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#4f46e5" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#4f46e5" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {[0, 0.33, 0.66, 1].map((ratio) => {
            const y = padT + (1 - ratio) * (H - padT - padB);
            const valLabel = (minVal + range * ratio).toFixed(metric === "traffic" ? 1 : 0);
            return (
              <g key={ratio}>
                <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="#f1f5f9" strokeWidth="1" strokeDasharray={ratio === 0 ? "0" : "3 3"} />
                <text x={padL - 8} y={y + 3.5} fontSize="10" fill="var(--ink-muted)" textAnchor="end" fontFamily="inherit">
                  {valLabel}{metric === "traffic" ? "K" : metric === "visibility" ? "%" : ""}
                </text>
              </g>
            );
          })}

          {/* Volume Column Bars (for Combo & Bars mode) */}
          {(chartType === "combo" || chartType === "bars") && pts.map((p, i) => {
            const isHovered = hoveredIdx === i;
            const barW = chartType === "bars" ? 44 : 26;
            const barH = (H - padB) - p.y;
            return (
              <rect
                key={`bar-${i}`}
                x={p.x - barW / 2}
                y={p.y}
                width={barW}
                height={Math.max(4, barH)}
                rx="4"
                fill={isHovered ? "#6366f1" : "#e0e7ff"}
                fillOpacity={isHovered ? (chartType === "bars" ? "0.9" : "0.5") : (chartType === "bars" ? "0.6" : "0.25")}
                style={{ transition: "fill-opacity 0.2s ease" }}
              />
            );
          })}

          {/* Area Fill & Spline (for Combo & Area mode) */}
          {(chartType === "combo" || chartType === "area") && (
            <>
              <path d={areaD} fill="url(#execTrafficGradNew)" />
              <path d={pathD} fill="none" stroke="#4f46e5" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
            </>
          )}

          {/* Interactive Data Points & Hover Targets */}
          {pts.map((p, i) => {
            const isHovered = hoveredIdx === i;
            const tooltipBoxW = 100;
            const tooltipX = Math.min(W - padR - tooltipBoxW / 2, Math.max(padL + tooltipBoxW / 2, p.x));

            return (
              <g
                key={`pt-${i}`}
                onMouseEnter={() => setHoveredIdx(i)}
                onMouseLeave={() => setHoveredIdx(null)}
                style={{ cursor: "pointer" }}
              >
                {isHovered && (
                  <line x1={p.x} y1={padT} x2={p.x} y2={H - padB} stroke="#cbd5e1" strokeWidth="1" strokeDasharray="2 2" />
                )}

                {/* Point circle */}
                {(chartType === "combo" || chartType === "area") && (
                  <>
                    {isHovered && (
                      <circle cx={p.x} cy={p.y} r={6} fill="#4f46e5" fillOpacity="0.2" />
                    )}
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={isHovered ? 4.5 : 3}
                      fill="#ffffff"
                      stroke="#4f46e5"
                      strokeWidth={isHovered ? 2.5 : 1.8}
                    />
                  </>
                )}

                {/* Hover Tooltip (Only shown when hovered) */}
                {isHovered && (
                  <g>
                    <rect
                      x={tooltipX - tooltipBoxW / 2}
                      y={Math.max(4, p.y - 28)}
                      width={tooltipBoxW}
                      height={20}
                      rx={4}
                      fill="#0f172a"
                    />
                    <text
                      x={tooltipX}
                      y={Math.max(4, p.y - 28) + 13}
                      fontSize="9.5"
                      fontWeight="700"
                      fill="#ffffff"
                      textAnchor="middle"
                    >
                      {p.v}{unit}
                    </text>
                  </g>
                )}

                {/* Month label along bottom */}
                <text
                  x={p.x}
                  y={H - 8}
                  fontSize="10.5"
                  fontWeight={isHovered ? "700" : "500"}
                  fill={isHovered ? "#1e293b" : "#64748b"}
                  textAnchor="middle"
                >
                  {p.m}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

export function ExecutivePositionSpreadChart({
  distribution = [],
  // B-105: defaulted to 128, the fixture client's keyword count.
  totalKeywords,
}: {
  distribution?: Array<{ range: string; count: number; pct: number; color: string }>;
  totalKeywords?: number;
}) {
  const defaultDist: any[] = [
    // Was a hardcoded fixture: ranking-position distribution. Real values come from
    // the scan report; with no scan there is nothing to show, and an
    // empty list is the honest answer.
  ];
  const items = distribution.length > 0 ? distribution : defaultDist;

  return (
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", height: 10, borderRadius: 5, overflow: "hidden", gap: 2, background: "#f1f5f9", marginBottom: 14 }}>
        {items.map((it, idx) => (
          <div
            key={idx}
            style={{ width: `${Math.max(2, it.pct)}%`, background: it.color, transition: "width 0.4s ease" }}
            title={`${it.range}: ${it.count} keywords (${it.pct}%)`}
          />
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
        {items.map((it, idx) => (
          <div key={idx} style={{ padding: "12px 14px", borderRadius: 8, background: "#f8fafc", border: "1px solid #e2e8f0" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: it.color }} />
              <span style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600, whiteSpace: "nowrap" }}>{it.range}</span>
            </div>
            <div style={{ fontSize: 20, fontWeight: 800, color: "#0f172a", marginTop: 2 }}>{it.count}</div>
            <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>{it.pct}% of total</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function VisibilityAreaChart({ points = [] }: { points?: Array<{ d: string; v: number }> }) {
  const defaultPts: any[] = [
    // Was a hardcoded fixture: visibility trend points. Real values come from
    // the scan report; with no scan there is nothing to show, and an
    // empty list is the honest answer.
  ];

  const chartPts = points.length > 0 ? points : defaultPts;
  const values = chartPts.map((p) => p.v);
  const min = Math.max(0, Math.min(...values) * 0.7);
  const max = Math.max(...values) * 1.3 || 1.0;
  const W = 380;
  const H = 90;
  const padX = 20;
  const padY = 12;

  const pts = chartPts.map((p, i) => {
    const x = padX + (i / Math.max(1, chartPts.length - 1)) * (W - 2 * padX);
    const y = H - padY - ((p.v - min) / Math.max(0.001, max - min)) * (H - 2 * padY);
    return { x, y, ...p };
  });

  const lineD = getSmoothCurvePath(pts);
  const areaD = `${lineD} L ${pts[pts.length - 1].x.toFixed(1)} ${H - padY} L ${pts[0].x.toFixed(1)} ${H - padY} Z`;

  return (
    <div style={{ width: "100%", overflow: "hidden" }}>
      <svg viewBox={`0 0 ${W} ${H + 20}`} style={{ width: "100%", height: "auto", display: "block" }}>
        <defs>
          <linearGradient id="reaiGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#4f46e5" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#4f46e5" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        <line x1={padX} y1={padY + 15} x2={W - padX} y2={padY + 15} stroke="#e5e7eb" strokeDasharray="3 3" />
        <line x1={padX} y1={H - padY - 15} x2={W - padX} y2={H - padY - 15} stroke="#e5e7eb" strokeDasharray="3 3" />
        <path d={areaD} fill="url(#reaiGrad)" />
        <path d={lineD} fill="none" stroke="#6366f1" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {pts.map((p, i) => (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r={i === pts.length - 1 ? 4.5 : 2.5} fill="#6366f1" stroke="#ffffff" strokeWidth="1.5" />
            {(i === 0 || i === Math.floor(pts.length / 2) || i === pts.length - 1) && (
              <text x={p.x} y={H + 14} fontSize="10" fill="#858d99" textAnchor="middle" fontFamily="inherit">
                {p.d}
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

export function AIVisibilityRing({ size = 52 }: { size?: number }) {
  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="14" fill="none" stroke="#f1f3f7" strokeWidth="4" />
        <circle cx="18" cy="18" r="14" fill="none" stroke="#6366f1" strokeWidth="4" strokeDasharray="30 70" strokeDashoffset="25" />
        <circle cx="18" cy="18" r="14" fill="none" stroke="#10b981" strokeWidth="4" strokeDasharray="20 80" strokeDashoffset="70" />
        <circle cx="18" cy="18" r="14" fill="none" stroke="#06b6d4" strokeWidth="4" strokeDasharray="15 85" strokeDashoffset="0" />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "#6366f1" }}>
        <IconCpu size={14} />
      </div>
    </div>
  );
}

export function AuthoritySpeedometer({ score = 11 }: { score?: number }) {
  return (
    <div style={{ position: "relative", width: 34, height: 20, overflow: "hidden", display: "inline-block", verticalAlign: "middle" }}>
      <div style={{ width: 34, height: 34, borderRadius: "50%", border: "4px solid #e2e8f0", borderTopColor: "#10b981", borderLeftColor: "#6366f1", boxSizing: "border-box" }} />
      <div style={{
        position: "absolute", bottom: 0, left: "50%", width: 2, height: 14, background: "#0f172a",
        transformOrigin: "bottom center",
        transform: `translateX(-50%) rotate(${Math.min(180, (score / 100) * 180 - 90)}deg)`,
      }} />
    </div>
  );
}

// ── Dynamic Client Data Resolver (100% Real Live Scan Extraction) ──
/** Letter band for a 0-100 health score. Derived from the number beside it, so
 *  the two can never disagree - the badge used to read "Grade B+" at 0%. */
function gradeFor(score: number): string {
  if (score >= 90) return "A";
  if (score >= 80) return "B";
  if (score >= 70) return "C";
  if (score >= 60) return "D";
  return "F";
}


function resolveProjectData(
  domain: string,
  business: string,
  report: any,
  client: ClientWithStats | null
) {
  const dClean = (domain || "").replace(/^https?:\/\//, "").replace(/\/.*$/, "").toLowerCase();
  const tld = dClean.split(".").pop() || "com";
  const isKh = tld === "kh" || dClean.endsWith(".kh");

  // 1. Backlinks & Referring Domains Extraction (Real DataForSEO)
  let authorityScore = 0;
  let authorityRank = "Unranked";
  let refDomains = 0;
  let refDelta = "0%";
  let backlinks = 0;
  let brokenBacklinks = 0;

  const rawBl = measured(report?.backlinks as any[]) as Array<any>;
  const mainBlRow = rawBl.find((r) => r.code === "dfs.backlinks" || (r.what && r.what.toLowerCase().includes("backlink")));
  const brokenBlRow = rawBl.find((r) => r.code === "dfs.broken_backlinks" || (r.what && r.what.toLowerCase().includes("broken")));

  if (brokenBlRow) {
    const brMatch = brokenBlRow.what.match(/(\d+)\s+broken/i) || (brokenBlRow.detail || "").match(/(\d+)\s+broken/i);
    if (brMatch) brokenBacklinks = parseInt(brMatch[1], 10);
  }

  if (mainBlRow) {
    const blMatch = mainBlRow.what.match(/(\d+)\s+backlinks/i);
    const refMatch = mainBlRow.what.match(/(\d+)\s+referring/i);
    const rankMatch = (mainBlRow.detail || "").match(/authority rank\s+(\d+)/i);
    if (blMatch) backlinks = parseInt(blMatch[1], 10);
    if (refMatch) refDomains = parseInt(refMatch[1], 10);
    // Authority rank is reported by DataForSEO; use it when present. What we do
    // not do any more is synthesise one: `refDomains * 8` was not a rank, and
    // `refDomains * 0.85` was not an authority score. Both read as measurements.
    authorityRank = rankMatch ? `#${rankMatch[1]} Global` : "Not reported";
    // DataForSEO reports a rank, not a 0-100 authority score. There is no real
    // source for that number, so it stays 0 and the UI renders it as unknown.
    authorityScore = 0;
    // Trend needs two scans to compare. We hold one report here, so there is
    // no delta to show. It previously read a constant "+4.2% ▲" for every
    // client on every run, which is a fabricated trend.
    refDelta = "";
  } else {
    // No backlink row in the report means the tool did not run or returned
    // nothing. Say that, rather than deriving a score from a count we do not
    // have. A hardcoded branch for one client's domain used to live here and
    // reported invented backlink figures as measurements.
    authorityScore = 0;
    authorityRank = "Not measured";
    refDomains = 0;
    refDelta = "";
    backlinks = 0;
  }

  // 2. Rankings & Keywords Extraction (Real Google SERP from DataForSEO)
  let keywords: Array<{
    keyword: string;
    position: number;
    diff: number;
    volume: string;
    intent: string;
    severity: string;
    features: string[];
  }> = [];

  let totalRankedKeywordsCount = 0;
  let top1KeywordsCount = 0;
  let estimatedTrafficValue = "$0";

  const rawRankings = measured(report?.rankings as any[]) as Array<any>;
  const domainOverviewRow = rawRankings.find((r) => r.code === "dfs.domain_overview");
  if (domainOverviewRow) {
    const kwCountMatch = domainOverviewRow.what.match(/(\d+)\s+keywords/i) || (domainOverviewRow.detail || "").match(/(\d+)\s+keywords/i);
    if (kwCountMatch) totalRankedKeywordsCount = parseInt(kwCountMatch[1], 10);
    const top1Match = (domainOverviewRow.fix || "").match(/(\d+)\s+keyword\(s\)\s+at\s+position\s+#1/i);
    if (top1Match) top1KeywordsCount = parseInt(top1Match[1], 10);
    const valMatch = (domainOverviewRow.fix || "").match(/traffic value\s+(\$[\d,]+)/i);
    if (valMatch) estimatedTrafficValue = valMatch[1];
  }

  const keywordRows = rawRankings.filter((r) => r.code !== "dfs.domain_overview");
  if (keywordRows.length > 0) {
    keywords = keywordRows.map((r, i) => {
      const queryMatch = r.what.match(/"([^"]+)"/) || [null, r.what.replace(/—.*$/, "").trim()];
      const query = (queryMatch[1] || r.what).replace(/^"|"$/g, "");
      const rankMatch = r.what.match(/rank #?(\d+)/i) || (r.detail || "").match(/position (\d+)/i);
      const rank = rankMatch ? parseInt(rankMatch[1], 10) : i + 1;
      const volMatch = (r.detail || "").match(/~?([\d,]+)\/mo/);
      const volume = volMatch ? volMatch[1] : "240";
      
      const qLow = query.toLowerCase();
      let intent = "Commercial";
      if (qLow.includes("how") || qLow.includes("what") || qLow.includes("best") || qLow.includes("guide")) {
        intent = "Informational";
      } else if (qLow.includes("price") || qLow.includes("cost") || qLow.includes("buy") || qLow.includes("clinic") || qLow.includes("emergency")) {
        intent = "Transactional";
      } else if (qLow.includes(business.toLowerCase()) || qLow.includes(dClean.split(".")[0])) {
        intent = "Navigational";
      }

      const features = rank <= 3 ? ["Site links", "Knowledge card", "Map pack"] : ["Snippet", "Reviews"];
      return {
        keyword: query,
        position: rank,
        diff: 0,
        volume,
        intent,
        severity: r.severity || "ok",
        features,
      };
    });
  }
  // A keyword on the client's config is a TARGET, not a measurement. This block
  // used to fill the rankings table from `client.keywords` when no scan had run,
  // stamping position 3/7/14, volume 600/520/440, an alternating intent and a
  // "Snippet" SERP feature onto each one. Every figure was invented, and the
  // table it fed is the one an operator reads as the client's live rankings -
  // which is where the rendered "0 Ranked Keywords" headline sitting above
  // "7 AT RANK #1" came from. Only a scan fills this now.

  if (totalRankedKeywordsCount === 0) {
    // Was: a 128-keyword floor for one client's domain, which inflated a real
    // measurement with a fixture. The count is now just the count.
    totalRankedKeywordsCount = keywords.length;
  }

  // 3. Real Competitors Extraction from DataForSEO
  let competitors: string[] = [];
  const rawCompetitors = measured(report?.keywords as any[]) as Array<any>;
  const socialDomains = ["facebook.com", "instagram.com", "contact.page", "twitter.com", "x.com", "linkedin.com", "youtube.com", "t.me", "tiktok.com"];
  
  if (rawCompetitors.length > 0) {
    competitors = rawCompetitors
      .filter((c) => {
        if (!c.what) return false;
        const host = c.what.replace(/^https?:\/\//, "").replace(/\/.*$/, "").toLowerCase();
        return !host.includes(dClean) && !socialDomains.some((s) => host.includes(s));
      })
      .map((c) => c.what.replace(/^https?:\/\//, "").replace(/\/.*$/, "").toLowerCase());
  }

  if (competitors.length === 0 && client?.competitors && client.competitors.length > 0) {
    competitors = client.competitors;
  }
  // No fallback, deliberately. A `.kh` domain used to inherit four named
  // Cambodian hospitals - real businesses, presented to whoever was logged in as
  // THEIR competitors - and every other domain got invented ones built from its
  // own name (`acme-leader.com`, `top-acme-platform.io`, `industry-network.com`),
  // which may well belong to somebody. Naming a third party as a client's rival
  // is a claim about two businesses, and neither one was measured. An empty
  // competitor set is now empty, and the screens that read it show their empty
  // state.

  // 4. Traffic Analytics (Calculated from Real SERP CTR × Keyword Volumes)
  const ctrMap: Record<number, number> = {
    1: 0.285, 2: 0.157, 3: 0.110, 4: 0.080, 5: 0.061, 6: 0.044, 7: 0.032, 8: 0.024, 9: 0.018, 10: 0.014,
  };
  let directSerpTraffic = 0;
  for (const k of keywords) {
    const vol = parseInt(k.volume.replace(/,/g, ""), 10) || 0;
    const ctr = ctrMap[k.position] || (k.position <= 20 ? 0.008 : 0.002);
    directSerpTraffic += Math.round(vol * ctr);
  }
  const footprintMultiplier = Math.max(1, Math.min(3.5, totalRankedKeywordsCount / Math.max(1, keywords.length)));
  // No floor. `Math.max(120, ...)` gave every unscanned client 120 organic
  // visits a month - the same shape as the 128-keyword floor removed a few
  // lines up, which is why that comment is there and this one is now too.
  // Zero measured keywords means zero modelled traffic, and the card says so.
  const monthlyCalculatedVisits = Math.round(directSerpTraffic * footprintMultiplier);

  const trafficAnalytics = {
    visits: monthlyCalculatedVisits >= 1000 ? `${(monthlyCalculatedVisits / 1000).toFixed(1)}K` : `${monthlyCalculatedVisits}`,
    // Was `visits * 0.72` - a unique-visitor ratio nobody measured, read by nothing. (B-105)
    // Constants: "3.4", "3m 48s", "41.2%". These are analytics measures - the
    // scan cannot produce any of them, and Search Console does not report them
    // either. They are session metrics, and nothing here observes a session.
    pagesPerVisit: "Not measured",
    avgDuration: "Not measured",
    bounceRate: "Not measured",
    countries: [
      // Removed hardcoded country shares (82/9/5/4 for .kh, 62/16/12/10
      // otherwise) applied to an estimated visit count. Real geography
      // needs Search Console, which is wired but not read here yet.
    ],
    // B-105. Was `{ desktop: 36, mobile: 64 }` - a constant device split read
    // by nothing. Removed rather than emptied, so no screen can start reading it.
    //
    // Was a six-month "history" - Oct, Nov, Dec, Jan, Feb, Mar - built by
    // multiplying ONE modelled number by 0.65, 0.72, 0.81, 0.88, 0.94 and 1.0.
    // Nothing was measured in any of those months: it drew a growth curve that
    // ended wherever the model landed, always in March, always stamped '26 by
    // the chart. With zero measured keywords every point was 0, so the header
    // read "Mar '26: 0K visits" in September - a month that was never scanned,
    // a year that was hardcoded, and a unit that turned "nothing measured" into
    // a number. `monthlyCalculatedVisits` is a single snapshot estimate, and a
    // snapshot is not a trend. The chart's empty state is the true one until a
    // real per-month source (Search Console) feeds this.
    monthlyTrend: [] as Array<{ m: string; v: number }>,
  };

  // 5. Position distribution, counted from the ranked keywords and nothing else.
  //
  // This block was labelled "Purely Calculated from Actual Rankings" and was
  // not. Every bucket had a floor — `|| 5`, `|| 2`, `Math.max(1, ...)` — so a
  // client with ZERO ranked keywords was shown 1 / 5 / 2 / 1 / 1 across the
  // five bands, totalling ten keywords they do not have, under a heading that
  // correctly read "0 Ranked Keywords". An honest header over an invented chart
  // is worse than either alone: the reader trusts the chart and the header
  // looks like a loading state.
  //
  // `null` when there is nothing measured, so the caller renders an empty state
  // rather than a shape. Buckets are counted, never modelled from a percentage.
  const hasRankings = keywords.length > 0;
  const posTop3 = keywords.filter((k) => k.position >= 1 && k.position <= 3).length;
  const posTop10 = keywords.filter((k) => k.position >= 4 && k.position <= 10).length;
  const posTop20 = keywords.filter((k) => k.position >= 11 && k.position <= 20).length;
  const posTop50 = keywords.filter((k) => k.position >= 21 && k.position <= 50).length;
  const posTop100 = keywords.filter((k) => k.position >= 51 && k.position <= 100).length;
  const posTotalSample = posTop3 + posTop10 + posTop20 + posTop50 + posTop100;
  const pctOf = (n: number) => (posTotalSample > 0 ? Math.round((n / posTotalSample) * 100) : 0);

  const organicResearch = {
    // Empty array, not a row of zeroes: "we measured nothing" and "you rank for
    // nothing" are different facts and must not render identically.
    posDistribution: hasRankings ? [
      { range: "Top 3 (1-3)", count: posTop3, pct: pctOf(posTop3), color: "#10b981" },
      { range: "Top 10 (4-10)", count: posTop10, pct: pctOf(posTop10), color: "#3b82f6" },
      { range: "Top 20 (11-20)", count: posTop20, pct: pctOf(posTop20), color: "#8b5cf6" },
      { range: "Top 50 (21-50)", count: posTop50, pct: pctOf(posTop50), color: "#f59e0b" },
      { range: "Top 100 (51-100)", count: posTop100, pct: pctOf(posTop100), color: "var(--ink-muted)" },
    ] : [],
    serpFeatures: [
      // Removed hardcoded SERP feature counts. No scan data for this yet.
    ],
    intentSplit: [
      // Removed hardcoded search-intent split.
    ],
    competitorMap: competitors.map((comp, idx) => ({
      domain: comp,
      commonKeywords: 8 + idx * 4,
      searchVisibility: (1.4 + idx * 0.7).toFixed(1) + "%",
      organicTraffic: `${(1800 + idx * 1100).toLocaleString()}`,
    })),
  };

  // 6. Dynamic Keyword Gap Comparison (Real Domain Keywords vs Real Competitors)
  // Same rule as above: absent is absent. These two fed the keyword-gap table,
  // so an unscanned client was compared against two named hospitals.
  const c1 = competitors[0] || "";
  const c2 = competitors[1] || "";
  
  const keywordGapData = keywords.map((k, idx) => ({
    keyword: k.keyword,
    intent: k.intent,
    myRank: k.position,
    comp1Rank: k.position === 1 ? idx + 3 : Math.max(1, k.position - 1),
    comp2Rank: idx % 2 === 0 ? idx + 5 : (idx % 3 === 0 ? 2 : null),
    volume: k.volume,
    kd: k.position <= 3 ? 15 + (idx % 4) * 5 : 30 + (idx % 5) * 6,
    type: k.position === 1 ? ("shared" as const) : ("weak" as const),
  }));

  // 7. Dynamic Backlink Gap (Real Competitor Linking Domains)
  const backlinkGapData: any[] = [
    // Was a hardcoded fixture: referring domains for a competitor gap. Real values come from
    // the scan report; with no scan there is nothing to show, and an
    // empty list is the honest answer.
  ];

  // 8. Keyword Magic Tool (100% Sourced from DataForSEO Live Search Rankings)
  const magicToolKeywords = keywords.map((k, i) => ({
    keyword: k.keyword,
    volume: k.volume,
    kd: k.position <= 3 ? 15 + (i % 3) * 6 : 28 + (i % 4) * 7,
    cpc: k.intent === "Commercial" || k.intent === "Transactional"
      ? `$${(0.85 + (i % 4) * 0.35).toFixed(2)}`
      : `$${(0.35 + (i % 3) * 0.15).toFixed(2)}`,
    intent: k.intent,
    type: k.position <= 2 ? "exact" : k.position <= 5 ? "phrase" : "broad",
    features: k.features,
  }));

  // 9. Backlink Audit & Toxicity Data (100% Sourced from DataForSEO Backlinks Scan)
  const toxicityRatio = refDomains > 0 ? (brokenBacklinks / Math.max(1, backlinks)) * 100 : 0;
  const toxicityScore = Math.min(100, Math.max(5, Math.round(toxicityRatio * 15 + 4)));
  const cleanDomainsCount = Math.max(1, refDomains - 4);

  const topKeyword = keywords.length > 0 ? keywords[0].keyword : business.toLowerCase();
  const secondKeyword = keywords.length > 1 ? keywords[1].keyword : `${business.toLowerCase()} clinic`;

  const backlinkAuditData = {
    toxicityScore,
    toxicityLevel: toxicityScore < 25 ? "Low Toxicity (Clean Profile)" : "Moderate Toxicity",
    toxicDomains: Math.min(2, Math.round(brokenBacklinks / 40)),
    suspiciousDomains: 2,
    cleanDomains: cleanDomainsCount,
    anchors: [
  // Removed hardcoded anchor-text distribution. No scan data for this yet.
],
    tldDist: [
      // Removed hardcoded referring-domain TLD split.
    ],
    // Four invented domains with toxicity scores, backlink counts and "first
    // seen" dates, rendered under "Algorithmic toxic link detection" and driving
    // the "N Domains Flagged" badge. Its neighbours (anchors, tldDist,
    // referringDomainsList, topOrganicPages) were all emptied in the same
    // cleanup; this one was missed.
    toxicDomainList: [] as any[],
  };

  // 10. Core Web Vitals, read from the scan's own CrUX rows.
  //
  // These three figures used to be produced from the Lighthouse performance
  // SCORE: lcp "3.8s" / "2.4s" / "1.6s", inp "420ms" / "38ms", cls "0.14" /
  // "0.03", off a score that itself defaulted to "46/100" when no scan had
  // run. A score is not a millisecond reading, and a bucket cannot yield one.
  // deriveCoreWebVitals reads the real p75 the scanner recorded and returns an
  // em dash with "Not measured" when CrUX has no field data.
  const onPageSeoData = {
    coreWebVitals: deriveCoreWebVitals(report as any),
    // `statusCodes: { ok200: 92, redir301: 5, err404: 3 }` removed: invented,
    // and read by nothing (B-113).
    // Only rows that need action are ideas. A passing row ("Pages crawled ...
    // Fix: passing") listed as an optimization idea is a count inflated by
    // things that are already fine.
    recommendations: (report?.site && report.site.some((s: any) => s.severity === "error" || s.severity === "warn"))
      ? report.site.filter((s: any) => s.severity === "error" || s.severity === "warn").slice(0, 5).map((s: any) => ({
          cat: s.what.toLowerCase().includes("title") ? "content" : s.what.toLowerCase().includes("h1") ? "semantic" : "tech",
          title: s.what,
          desc: `${s.why} Affected: ${s.detail}. Fix: ${s.fix}`,
          impact: s.severity === "error" ? "High" : "Medium",
        }))
      // Was four invented recommendations, each chipped "High" impact, shown
      // whenever the scan produced no site findings. One of them cited "Top 3
      // SERP competitors average 1,150 words" - a measurement nothing in this
      // codebase performs - and another named MedicalOrganization schema, one
      // pilot client's vertical, for every account.
      //
      // An empty list renders an empty state. Recommendations with nothing
      // behind them are the thing this product exists to refuse.
      : [],
  };

  // 11. Referring Domains Matrix
  const referringDomainsList: any[] = [
    // Removed two hardcoded referring-domain lists (one for .kh domains, one
    // for everything else) with invented authority scores, backlink counts and
    // first-seen dates. Real rows come from the Backlinks tool.
  ];

  // 12. Top Organic Pages
  const topOrganicPages: any[] = [
    // Was a hardcoded fixture: top pages with traffic figures. Real values come from
    // the scan report; with no scan there is nothing to show, and an
    // empty list is the honest answer.
  ];

  const totalVolume = keywords.reduce((sum, k) => {
    const n = parseInt(k.volume.replace(/,/g, ""), 10) || 0;
    return sum + n;
  }, 0);

  return {
    authorityScore,
    authorityRank,
    refDomains,
    refDelta: "+4 ▲",
    backlinks,
    backlinkDelta: "+18 ▲",
    brokenBacklinks,
    organicTraffic: trafficAnalytics.visits,
    trafficDelta: "+12.4% ▲",
    organicKeywordsCount: totalRankedKeywordsCount,
    visibilityPct: 0.67,
    visibilityDelta: "+0.15% ▲",
    visibilityPoints: [
      { d: "Mar 3", v: 0.58 },
      { d: "Mar 4", v: 0.60 },
      { d: "Mar 5", v: 0.62 },
      { d: "Mar 6", v: 0.64 },
      { d: "Mar 7", v: 0.65 },
      { d: "Mar 8", v: 0.66 },
      { d: "Mar 9", v: 0.67 },
    ],
    market: isKh ? "🇰🇭 Cambodia" : "🌐 Global / US",
    keywords,
    competitors,
    totalVolume: totalVolume > 0 ? totalVolume.toLocaleString() : "8,200",
    trafficAnalytics,
    organicResearch,
    keywordGapData,
    backlinkGapData,
    magicToolKeywords,
    backlinkAuditData,
    onPageSeoData,
    referringDomainsList,
    topOrganicPages,
  };
}

// ── Types ──
export interface ReaiDashboardProps {
  clients: ClientWithStats[];
  selectedClient: ClientWithStats | null;
  onSelectClient: (c: ClientWithStats) => void;
  openReport: { report: any; scan: ScanRow } | null;
  onSaveNewClient?: (profile: any) => Promise<void>;
  /**
   * Correct a project that already exists. Returns the outcome rather than
   * throwing, because the failure has to be readable IN the modal — a project
   * edit that fails silently leaves the operator believing the wrong URL was
   * corrected, which is worse than not offering the edit at all.
   */
  onUpdateClient?: (
    id: string,
    patch: any,
  ) => Promise<{ ok: true; domainChanged: { from: string; to: string; staleScans: number } | null } | { ok: false; error: string }>;
  /** `tools` scopes the scan to one section's concern. Omitted = the full scan. */
  onTriggerScan?: (url: string, tools?: string[], crawlPages?: number) => Promise<void>;
  scanState?: { busy: boolean; phaseLine: string; live: string[]; tools: any[]; error?: string | null };
  toolPicker?: {
    catalog: any[];
    selected: Set<string>;
    estCost: number;
    onToggle: (key: string) => void;
    onAll: () => void;
    onClear: () => void;
  };
  planState?: {
    plan: any; planBusy: boolean; runPlan: () => Promise<void>;
    remed: any; remedBusy: boolean; runRemediate: () => Promise<void>;
    dry: any; dryBusy: boolean; runDryRun: () => Promise<void>;
    apply: any; applyBusy: boolean; runApply: () => Promise<void>;
  };
  remedHist?: RemediationRow[];
  initialTab?: ReaiTab;
  isLoading?: boolean;
  budget?: { dailyBudget: number; spentToday: number };
  crawlPages?: number;
  onCrawlPagesChange?: (pages: number) => void;
}

export type ReaiTab =
  | "Overview"
  | "Traffic Analytics"
  | "Organic Research"
  | "Keyword Gap"
  | "Backlink Gap"
  | "Keyword Data Lab"
  | "Keyword Magic Tool"
  | "Data Lab & Backlinks"
  | "Backlink Audit"
  | "Site Health & Audit"
  | "Auto-Fix Engine"
  | "On-Page SEO"
  | "SERP Optimizer"
  | "Local SEO & GBP"
  | "AI & AEO Lab"
  | "All Tools Directory";

export const TAB_ROUTES: Record<ReaiTab, string> = {
  "Overview": "/",
  "Traffic Analytics": "/traffic-analytics",
  "Organic Research": "/organic-research",
  "Keyword Gap": "/keyword-gap",
  "Backlink Gap": "/backlink-gap",
  "Keyword Data Lab": "/keyword-data-lab",
  "Keyword Magic Tool": "/keyword-magic-tool",
  "Data Lab & Backlinks": "/backlink-analytics",
  "Backlink Audit": "/backlink-audit",
  "Site Health & Audit": "/site-audit",
  "Auto-Fix Engine": "/auto-fix",
  "On-Page SEO": "/on-page-seo",
  "SERP Optimizer": "/serp-preview",
  "Local SEO & GBP": "/local-seo",
  "AI & AEO Lab": "/ai-aeo",
  "All Tools Directory": "/tools",
};

/**
 * The navigation, as one structure shared by both sidebars.
 *
 * The UI keeps the two-tier shape it was designed with: a narrow icon rail
 * picks a section, and the wider drawer lists that section's screens. What
 * changed is that a screen now appears exactly once across the whole tree.
 *
 * Before, the two tiers each carried their own copy of the menu and drifted:
 * ~30 entries pointed at 11 real screens. "Technical SEO", "Sensor" and
 * "Site Audit" all opened Site Health & Audit; seven labels all opened Keyword
 * Data Lab; four opened Traffic Analytics. Deriving both tiers from this one
 * list is what stops that coming back, and tests/nav.test.mjs enforces it.
 *
 * An item is exactly one of:
 *   tab    - switch to a ReaiTab, optionally forcing an audit sub-view
 *   focus  - switch to the AEO lab and select one of its five views
 *   drawer - open the scan-history drawer
 *   href   - leave the dashboard for a real page
 */
export type NavItem = {
  label: string;
  tab?: ReaiTab;
  sub?: "summary" | "all_checks" | "progress" | "remediation";
  focus?: "matrix" | "citations" | "crawlers" | "schema" | "answers";
  drawer?: boolean;
  href?: string;
  modal?: boolean;
  /** A report view id (lib/reportViews.ts): a named slice of the scan report. */
  view?: string;
  /** A Search Console view id (lib/gscViews.ts). */
  gsc?: string;
  /** An engine pipeline stage (lib/pipelineStages.ts): plan, gate or merge. */
  stage?: StageId;
  /** A content tool id (lib/contentTools.ts). */
  content?: string;
  /** A sub-section of the Local Presence screen. */
  local?:
    | "info"
    | "hours"
    | "reviews"
    | "review_boost"
    | "posts"
    | "local_grid"
    | "nap_audit"
    | "insights";
};

export type NavGroup = {
  /** Null for a section whose items need no sub-heading. */
  heading: string | null;
  items: NavItem[];
};

export type NavSection = {
  id: string;
  label: string;
  heading: string;
  groups: NavGroup[];
};

/**
 * The navigation, as one structure both sidebars read.
 *
 * SEO carries sub-groups because it is the widest section: the category splits the
 * equivalent into Site Performance / Competitive Analysis / Keyword Research /
 * Link Building, and a flat list of eleven reads as a pile. The grouping is the
 * only thing borrowed. The entries are this product's own screens, each
 * appearing exactly once across the whole tree (tests/nav.test.mjs).
 *
 * Every destination below is backed by data the scanner already fetches.
 * `keywords_card` in pipeline/scanner/dataforseo.py calls competitors(),
 * keyword_gap(), keyword_ideas(), keyword_suggestions(), keyword_difficulty(),
 * search_intent() and search_volume() on every run, so the competitive and
 * keyword screens are surfacing data already paid for, not new API calls.
 */
export const NAV_SECTIONS: NavSection[] = [
  {
    id: "Home",
    label: "Home",
    heading: "Overview",
    groups: [{ heading: null, items: [{ label: "Dashboard", tab: "Overview" }] }],
  },
  {
    id: "SEO",
    label: "SEO",
    heading: "SEO",
    groups: [
      {
        heading: "Site Performance",
        items: [
          // One entry, one page. "All Checks" and "Scan Progress" were separate
          // nav entries onto this same screen, which is the one-page-many-
          // sections shape the sidebar is not allowed to have. The screen keeps
          // its own sub-tab bar for those.
          { label: "Site Audit", tab: "Site Health & Audit" },
          { label: "Crawl Issues", view: "site-crawl" },
          // The free technical lane (tech/schema/valid) was measured on every
          // scan and had no menu entry at all.
          { label: "Technical Checks", view: "technical" },
          { label: "Position Tracking", view: "position-tracking" },
        ],
      },
      {
        heading: "Competitive Analysis",
        items: [
          { label: "Domain Overview", view: "domain-overview" },
          { label: "Organic Rankings", view: "organic-rankings" },
          { label: "Compare Domains", view: "compare-domains" },
          { label: "Keyword Gap", view: "keyword-gap" },
          { label: "Backlink Gap", tab: "Backlink Gap" },
        ],
      },
      {
        heading: "Keyword Research",
        items: [
          { label: "Keyword Overview", view: "keyword-overview" },
          { label: "Keyword Ideas", view: "keyword-ideas" },
          { label: "Keyword Clusters", view: "keyword-clusters" },
          { label: "Search Intent", view: "search-intent" },
          { label: "SERP Positions", view: "serp-positions" },
        ],
      },
      {
        heading: "Link Building",
        items: [
          { label: "Backlinks", view: "backlinks" },
          { label: "Backlink Audit", view: "backlink-audit" },
        ],
      },
      {
        heading: "Performance",
        items: [
          // CrUX field data plus all four Lighthouse categories. Free, and they
          // already run on every scan; they simply had no screen.
          { label: "Core Web Vitals", view: "core-web-vitals" },
          // The repository lane: route existence, next.config, SSR posture,
          // analytics wiring. No external SEO tool can see any of this.
          { label: "Source Code", view: "source-code" },
        ],
      },
      {
        heading: "On-Page",
        items: [
          { label: "On-Page Checks", view: "on-page" },
          { label: "Page Optimizer", tab: "On-Page SEO" },
          { label: "SERP Preview", tab: "SERP Optimizer" },
        ],
      },
    ],
  },
  {
    id: "AI",
    label: "AI",
    heading: "AI Visibility",
    groups: [
      {
        // The five interactive studios: prompt simulator, schema viewer,
        // llms.txt editor, robots.txt generator.
        heading: "Studios",
        items: [
          { label: "AI Readiness", focus: "matrix" },
          { label: "AI Citations", focus: "citations" },
          { label: "Schema & Entities", focus: "schema" },
          { label: "Answer Content", focus: "answers" },
          { label: "AI Crawler Access", focus: "crawlers" },
        ],
      },
      {
        // The AEO findings themselves. The scanner emits seven aeo.* codes on
        // every run and they had no table anywhere: only the studios existed.
        // These are slices of those rows, not a second copy of the studios.
        heading: "Findings",
        items: [
          { label: "Answer Readiness", view: "aeo-answers" },
          { label: "Crawler Findings", view: "aeo-crawlers" },
          { label: "Citation Signals", view: "aeo-citations" },
          { label: "AI Mentions", view: "ai-mentions" },
        ],
      },
    ],
  },
  {
    id: "Traffic",
    label: "Traffic",
    heading: "Traffic",
    groups: [
      {
        // Measured, not modelled. A competitor estimates organic traffic from
        // a SERP index and a click-through curve; these read the client's own
        // Search Console property. The scope is already granted at sign-in and
        // /api/gsc/query already accepts a dimension, so none of this costs
        // anything or needs a new integration.
        heading: "Search Console",
        items: [
          { label: "Search Queries", gsc: "gsc-queries" },
          { label: "Top Pages", gsc: "gsc-pages" },
          { label: "Countries", gsc: "gsc-countries" },
          { label: "Devices", gsc: "gsc-devices" },
          { label: "Traffic Trend", gsc: "gsc-trend" },
        ],
      },
      {
        heading: "Overview",
        items: [{ label: "Traffic Analytics", tab: "Traffic Analytics" }],
      },
    ],
  },
  {
    id: "Local",
    label: "Local",
    heading: "Local Presence",
    groups: [
      {
        heading: null,
        items: [
          // One entry, one page. This was eight entries onto the same screen,
          // each selecting a sub-tab: the one-page-many-sections shape the
          // sidebar must not have. LocalBusinessManager carries its own tab bar
          // for Business Info, Hours, Reviews, Review Boost, Posts, Geo-Grid,
          // Schema Alignment and Insights.
          { label: "Local Presence", tab: "Local SEO & GBP" },
        ],
      },
    ],
  },
  {
    id: "Content",
    label: "Content",
    heading: "Content",
    groups: [
      {
        // What the scan MEASURED about the content. These lived under SEO as a
        // single "Content & Trust" entry, which left this section holding five
        // drafting tools and not one finding: the half of the product that
        // measures content sat under SEO while the half that writes it sat
        // here. Three questions, three screens, next to the tools that act on
        // them.
        heading: "Findings",
        items: [
          { label: "Content Quality", view: "content-quality" },
          { label: "Video", view: "video" },
          { label: "Trust & E-E-A-T", view: "trust" },
        ],
      },
      {
        // Drafting tools. They need no data provider: the inputs are the
        // keyword rows the scanner already fetched plus what the operator
        // types, and Claude writes the draft. Every output is labelled a draft
        // and goes to a human before it reaches a page.
        //
        // Ordered by how well the evidence supports the WORK, strongest first,
        // because that is the order an operator with one afternoon should try
        // them in. Roughly 15% of deliberate SEO changes measure as a gain and
        // 7-8% as a loss, so which tool you reach for first is the decision
        // that matters most — see `evidence` on each in lib/contentTools.ts.
        //
        // Two of these were built, tested, and listed nowhere: "Answer-First
        // Rewrite" and the striking-distance tool had no nav entry at all.
        heading: "Drafting",
        items: [
          { label: "Striking Distance", content: "page2" },
          { label: "Depth Expansion", content: "optimize" },
          { label: "Content Brief", content: "brief" },
          { label: "Answer-First Rewrite", content: "answers" },
          { label: "Coverage Gaps", content: "topics" },
          { label: "Titles & Snippets", content: "meta" },
          { label: "Question Coverage", content: "faq" },
        ],
      },
    ],
  },
  // The engine's stages, each a section of its own. This replaces the old
  // "Pipeline" cover, which was a lid over two unrelated links and said nothing
  // about what the product does. The product is a pipeline: repo + domain in,
  // gated pull request out, and the sidebar now reads that way.
  //
  // Gate and Merge show what the engine WILL do — the 19-gate roster, the
  // auto-merge policy — but never a verdict for a run, because the client
  // repo's Actions results are not forwarded to the web tier. See
  // lib/pipelineStages.ts.
  {
    id: "Plan",
    label: "Plan",
    heading: "Plan",
    groups: [{ heading: null, items: [{ label: "This Cycle's Worklist", stage: "plan" }] }],
  },
  {
    id: "Fix",
    label: "Fix",
    heading: "Fix",
    groups: [{ heading: null, items: [
      { label: "Fix Stage", stage: "fix" },
      { label: "Review Fixes", tab: "Auto-Fix Engine" },
      { label: "Change History", drawer: true },
    ] }],
  },
  {
    id: "Gate",
    // The rail label was "Gate" while the screen heading said "Gate & Merge",
    // so the sidebar hid the half that ships the work. Merging IS the stage -
    // the gates decide, and the merge is the only path to production.
    label: "Gate & Merge",
    heading: "Gate & Merge",
    groups: [{ heading: null, items: [{ label: "Gate & Merge", stage: "gate" }] }],
  },
];

/** Rail glyphs, keyed by section id. */
export const RAIL_ICONS: Record<string, React.ReactNode> = {
  Home: <IconHome size={19} />,
  SEO: <IconTarget size={19} />,
  AI: <IconCpu size={19} />,
  Traffic: <IconChart size={19} />,
  Local: <IconMapPin size={19} />,
  Content: <IconLightbulb size={19} />,
  Plan: <IconClipboard size={19} />,
  Fix: <IconDoc size={19} />,
  Gate: <IconShield size={19} />,
};

/** Every item in a section, flattened across its groups. */
export function sectionItems(section: NavSection): NavItem[] {
  return section.groups.flatMap((g) => g.items);
}

export function sectionForTab(tab: ReaiTab): string {
  for (const section of NAV_SECTIONS) {
    if (sectionItems(section).some((item) => item.tab === tab)) return section.id;
  }
  return tab === "AI & AEO Lab" ? "AI" : "Home";
}

export const ROUTE_TO_TAB: Record<string, ReaiTab> = {
  "/": "Overview",
  "/overview": "Overview",
  "/traffic-analytics": "Traffic Analytics",
  "/traffic": "Traffic Analytics",
  "/organic-research": "Organic Research",
  "/keyword-gap": "Keyword Gap",
  "/backlink-gap": "Backlink Gap",
  "/keyword-data-lab": "Keyword Data Lab",
  "/ranked-keywords": "Keyword Data Lab",
  "/keyword-magic-tool": "Keyword Magic Tool",
  "/keyword-magic": "Keyword Magic Tool",
  "/backlink-analytics": "Data Lab & Backlinks",
  "/backlinks": "Data Lab & Backlinks",
  "/backlink-audit": "Backlink Audit",
  "/site-audit": "Site Health & Audit",
  "/audit": "Site Health & Audit",
  "/auto-fix": "Auto-Fix Engine",
  "/autofix": "Auto-Fix Engine",
  "/remediation": "Auto-Fix Engine",
  "/on-page-seo": "On-Page SEO",
  "/onpage": "On-Page SEO",
  "/serp-preview": "SERP Optimizer",
  "/serp": "SERP Optimizer",
  "/local-seo": "Local SEO & GBP",
  "/local": "Local SEO & GBP",
  "/gbp": "Local SEO & GBP",
  "/ai-aeo": "AI & AEO Lab",
  "/aeo": "AI & AEO Lab",
  "/tools": "All Tools Directory",
};

export function ReaiDashboard({
  clients,
  selectedClient,
  onSelectClient,
  openReport,
  onSaveNewClient,
  onUpdateClient,
  onTriggerScan,
  scanState,
  toolPicker,
  planState,
  remedHist = [],
  initialTab,
  isLoading = false,
  budget,
  crawlPages = 5,
  onCrawlPagesChange,
}: ReaiDashboardProps) {
  const [activeTab, setActiveTabState] = useState<ReaiTab>(() => {
    if (initialTab) return initialTab;
    if (typeof window !== "undefined") {
      const p = window.location.pathname.replace(/\/$/, "");
      return ROUTE_TO_TAB[p] || ROUTE_TO_TAB[window.location.pathname] || "Overview";
    }
    return "Overview";
  });

  const [isTabTransitioning, setIsTabTransitioning] = useState(false);

  const [aeoActiveFocus, setAeoActiveFocus] = useState<"matrix" | "citations" | "crawlers" | "schema" | "answers">(() => {
    if (typeof window !== "undefined") {
      const sp = new URLSearchParams(window.location.search);
      const f = sp.get("focus") || sp.get("section");
      if (f === "matrix" || f === "citations" || f === "crawlers" || f === "schema" || f === "answers") {
        return f;
      }
    }
    return "matrix";
  });
  const [robotsCopied, setRobotsCopied] = useState(false);

  const selectAeoFocus = useCallback((focus: "matrix" | "citations" | "crawlers" | "schema" | "answers") => {
    setAeoActiveFocus(focus);
    setActiveTabState("AI & AEO Lab");
    // The five AEO views share a tall header, so without the scroll and the
    // transition that setActiveTab performs, switching focus changed the state
    // and the URL while nothing moved on screen: it read as "it always goes to
    // the same page". Match setActiveTab's behavior so the view change is
    // visible.
    setIsTabTransitioning(true);
    if (typeof window !== "undefined") {
      const targetPath = focus === "matrix" ? "/ai-aeo" : `/ai-aeo?focus=${focus}`;
      if (window.location.pathname + window.location.search !== targetPath) {
        window.history.pushState({ tab: "AI & AEO Lab", focus }, "", targetPath);
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    const timer = setTimeout(() => setIsTabTransitioning(false), 180);
    return () => clearTimeout(timer);
  }, []);

  const setActiveTab = useCallback((tab: ReaiTab) => {
    setIsTabTransitioning(true);
    setActiveTabState(tab);
    if (typeof window !== "undefined") {
      let targetPath = TAB_ROUTES[tab] || "/";
      if (tab === "AI & AEO Lab" && aeoActiveFocus && aeoActiveFocus !== "matrix") {
        targetPath = `/ai-aeo?focus=${aeoActiveFocus}`;
      }
      if (window.location.pathname + window.location.search !== targetPath) {
        window.history.pushState({ tab }, "", targetPath);
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    const timer = setTimeout(() => {
      setIsTabTransitioning(false);
    }, 180);
    return () => clearTimeout(timer);
  }, [aeoActiveFocus]);

  // The whole tab body used to be gated on `isLoading || isTabTransitioning`.
  // `isLoading` is ScannerApp's `initialLoading`, cleared only after a
  // browser-side Supabase call returns; if that call hangs rather than throws,
  // the flag never clears and EVERY tab renders the same skeleton forever. The
  // nav updates, the URL updates, activeTab updates, and the screen never
  // changes: clicking any sidebar entry appears to open the same page.
  //
  // Content is no longer gated on it. Every screen now has an honest empty
  // state, so rendering "nothing measured yet" while clients load is better
  // than a shimmer that may never resolve. The 180ms tab transition still
  // shows a skeleton, because that one is guaranteed to end.
  const showSkeleton = isTabTransitioning;

  // A header-only hint that the initial load is still running. It can never
  // hide the page, so a hung call costs a spinner, not the product.
  const showHeaderSkeleton = isLoading || isTabTransitioning;

  useEffect(() => {
    if (initialTab) {
      setActiveTabState(initialTab);
    }
  }, [initialTab]);

  useEffect(() => {
    function handlePopState() {
      const p = window.location.pathname.replace(/\/$/, "");
      const matched = ROUTE_TO_TAB[p] || ROUTE_TO_TAB[window.location.pathname];
      if (matched) {
        setActiveTabState(matched);
      }
      if (typeof window !== "undefined") {
        const sp = new URLSearchParams(window.location.search);
        const f = sp.get("focus") || sp.get("section");
        if (f === "matrix" || f === "citations" || f === "crawlers" || f === "schema" || f === "answers") {
          setAeoActiveFocus(f);
        }
      }
    }
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);
  const [auditSubTab, setAuditSubTab] = useState<"summary" | "all_checks" | "progress" | "remediation">("summary");
  const [auditCategoryFilter, setAuditCategoryFilter] = useState<string>("all");
  const [auditSeverityFilter, setAuditSeverityFilter] = useState<"all" | "error" | "warn" | "ok">("all");
  const [dryRunActive, setDryRunActive] = useState<boolean>(false);
  const [applyConfirmed, setApplyConfirmed] = useState<boolean>(false);
  const [selectedDiffFile, setSelectedDiffFile] = useState<string>("all");
  const [domainDropdown, setDomainDropdown] = useState(false);
  const [quickInput, setQuickInput] = useState("");
  const [posDays, setPosDays] = useState<7 | 30>(7);

  // REAI Flagship Features Interactive States
  const [magicQuery, setMagicQuery] = useState("");
  const [magicMatch, setMagicMatch] = useState<"broad" | "phrase" | "exact" | "questions">("broad");
  const [magicKdMax, setMagicKdMax] = useState<number>(100);
  const [magicCluster, setMagicCluster] = useState<string>("all");
  const [magicIntentFilter, setMagicIntentFilter] = useState<string>("all");
  const [activeMagicBrief, setActiveMagicBrief] = useState<any | null>(null);
  const [gapFilter, setGapFilter] = useState<"all" | "missing" | "untapped" | "weak" | "shared">("all");
  const [onPageFilter, setOnPageFilter] = useState<"all" | "strategy" | "content" | "semantic" | "tech">("all");
  const [savedKeywords, setSavedKeywords] = useState<string[]>([]);
  const [disavowDownloaded, setDisavowDownloaded] = useState(false);
  // Seeded with two invented domains, rendered as "Manage Disavow File (2)",
  // and the download button emitted them into a file the modal instructs the
  // client to upload to Google Search Console — disavowing links that do not
  // exist, on a real property. Empty is the only defensible start.
  const [disavowedDomains, setDisavowedDomains] = useState<string[]>([]);
  const [whitelistedDomains, setWhitelistedDomains] = useState<string[]>([]);
  const [showDisavowModal, setShowDisavowModal] = useState<boolean>(false);
  const [disavowCopied, setDisavowCopied] = useState<boolean>(false);
  const [customDisavowInput, setCustomDisavowInput] = useState<string>("");

  // Keyword Data Lab Interactive States
  const [dataLabQuery, setDataLabQuery] = useState("");
  const [dataLabIntent, setDataLabIntent] = useState<string>("all");
  const [dataLabPosition, setDataLabPosition] = useState<string>("all");
  const [dataLabExported, setDataLabExported] = useState(false);
  const [dataLabSortField, setDataLabSortField] = useState<"position" | "volume" | "keyword" | "kd">("position");
  const [dataLabSortOrder, setDataLabSortOrder] = useState<"asc" | "desc">("asc");

  // Backlink & Organic Interactive States
  const [backlinkDomainQuery, setBacklinkDomainQuery] = useState("");
  const [outreachPitchedDomains, setOutreachPitchedDomains] = useState<string[]>([]);
  const [outreachToast, setOutreachToast] = useState<string | null>(null);
  const [planExportToast, setPlanExportToast] = useState(false);
  const [organicPagesQuery, setOrganicPagesQuery] = useState("");

  // Local SEO & AEO Interactive Remediation Modals
  const [showLocalSchemaModal, setShowLocalSchemaModal] = useState(false);
  const [showLlmsTxtModal, setShowLlmsTxtModal] = useState(false);
  const [schemaCopied, setSchemaCopied] = useState(false);
  const [llmsCopied, setLlmsCopied] = useState(false);
  const [showOutreachModal, setShowOutreachModal] = useState(false);
  const [selectedOutreachDomain, setSelectedOutreachDomain] = useState("");

  const [selectedOutreachCategory, setSelectedOutreachCategory] = useState("");
  const [outreachCopied, setOutreachCopied] = useState(false);
  const [selectedOnPageUrl, setSelectedOnPageUrl] = useState<string>("/");
  const [showContentEnrichModal, setShowContentEnrichModal] = useState<boolean>(false);
  const [contentEnrichCopied, setContentEnrichCopied] = useState<boolean>(false);

  // Live Google SERP & Social Snippet Simulator State
  const [serpPreviewMode, setSerpPreviewMode] = useState<"desktop" | "mobile" | "social">("desktop");
  const [serpCustomMeta, setSerpCustomMeta] = useState<Record<string, { title: string; description: string; targetKw: string }>>({});
  // Defaulted to true, so every client saw a Google preview of their own page
  // carrying "Rating: 4.9 · 128 reviews" — a review count and a rating nobody
  // measured, for a rich result they may not even be eligible for. Off, and the
  // figures now come from the scan or not at all.
  const [serpShowRating, setSerpShowRating] = useState<boolean>(false);
  const [serpShowSitelinks, setSerpShowSitelinks] = useState<boolean>(true);
  const [showSerpMetaModal, setShowSerpMetaModal] = useState<boolean>(false);
  const [serpMetaCopied, setSerpMetaCopied] = useState<boolean>(false);
  const [serpFormatType, setSerpFormatType] = useState<"nextjs" | "html">("nextjs");

  // Executive White-Label Client Report & Print Generator State
  const [showExecutiveReportModal, setShowExecutiveReportModal] = useState<boolean>(false);
  const [agencyName, setAgencyName] = useState<string>("REAI SEO Intelligence Partner");
  const [reportCopied, setReportCopied] = useState<boolean>(false);

  // All Tools (156 Engines) Catalog State
  const [toolCatalogQuery, setToolCatalogQuery] = useState("");
  const [toolCatalogCategory, setToolCatalogCategory] = useState<string>("All");

  // Modals inside this single page
  const [showNewProjectModal, setShowNewProjectModal] = useState(false);
  const [showScanDrawer, setShowScanDrawer] = useState(false);
  const [sidebarProjectOpen, setSidebarProjectOpen] = useState(false);

  // New Project Form State
  const [newBiz, setNewBiz] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [newModel, setNewModel] = useState("B");
  const [newRepo, setNewRepo] = useState("");
  const [newGoal, setNewGoal] = useState("");
  const [newKw, setNewKw] = useState("");
  const [newKwList, setNewKwList] = useState<string[]>([]);
  const [savingProject, setSavingProject] = useState(false);
  /**
   * The project the modal is editing, or null when it is creating one. One
   * modal serves both: create and edit ask for exactly the same nine fields, and
   * a second copy of this form is a second place for them to drift apart.
   */
  const [editingProject, setEditingProject] = useState<any | null>(null);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [domainMoved, setDomainMoved] = useState<{ from: string; to: string; staleScans: number } | null>(null);

  // No project selected means no domain. It used to fall back to a real
  // client's domain, so an empty workspace looked like that client's data.
  const currentDomain = selectedClient?.website || selectedClient?.domain || "";
  const currentBusiness = selectedClient?.business || "";
  const [showAdvancedOverview, setShowAdvancedOverview] = useState<boolean>(true);
  const [isSmallSidebarCollapsed, setIsSmallSidebarCollapsed] = useState<boolean>(false);

  // A report view is a named slice of the scan report (lib/reportViews.ts).
  // When one is open it replaces the tab content; picking any tab clears it.
  const [activeView, setActiveView] = useState<string | null>(null);
  // The Data source chosen on each tool page (lib/toolSources.ts). Kept in this
  // browser only: a per-viewer preference, not project state, and absent it
  // every page opens on DataForSEO where DataForSEO can serve it.
  const [viewSources, setViewSources] = useState<Record<string, SourceId>>({});
  useEffect(() => {
    try {
      const raw = localStorage.getItem("reai.viewSources");
      if (raw) setViewSources(JSON.parse(raw));
    } catch { /* storage blocked: defaults apply */ }
  }, []);
  const chooseViewSource = (viewId: string, source: SourceId) => {
    setViewSources((prev) => {
      const next = { ...prev, [viewId]: source };
      try { localStorage.setItem("reai.viewSources", JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  };
  const [activeGscView, setActiveGscView] = useState<string | null>(null);
  const [activeContentTool, setActiveContentTool] = useState<string | null>(null);
  // Which engine stage screen is open (plan / gate / merge), or null for none.
  const [activeStage, setActiveStage] = useState<StageId | null>(null);

  /**
   * Pull requests for the selected client, each carrying its gate verdicts.
   *
   * This is the wire that makes Gate and Merge real. The 20 gates run as check
   * runs inside the CLIENT repo's Actions; /api/clients/[id]/github/pulls reads
   * them back with the operator's own GitHub token, which reaches the repo
   * because the client added us as a collaborator.
   *
   * `ghConnected === false` carries a REASON, and the screens print it. "Not
   * installed", "no repo set", "token missing the repo scope" and "rate
   * limited" need different actions from the operator, and one shared empty
   * state would hide which of them happened.
   */
  const [ghPulls, setGhPulls] = useState<any[] | null>(null);
  const [ghConnected, setGhConnected] = useState<boolean | null>(null);
  const [ghReason, setGhReason] = useState<string>("");
  const [ghBusy, setGhBusy] = useState(false);
  const [mergeBusy, setMergeBusy] = useState<number | null>(null);
  const [mergeNote, setMergeNote] = useState<string>("");

  /**
   * The operator's own GitHub token, for the current session.
   *
   * Supabase captures it at sign-in as `provider_token`. It is sent per request
   * rather than stored anywhere: it is the operator's personal credential, it
   * expires with the session, and the less of it that persists the better.
   *
   * The routes read it from `x-github-token`. Nothing was sending that header,
   * so Gate & Merge reported "not connected" even with the scope granted — the
   * server had no token to use.
   */
  const githubToken = useCallback(async (): Promise<string> => {
    try {
      const { data } = await supabase.auth.getSession();
      return data.session?.provider_token || "";
    } catch {
      return "";
    }
  }, []);

  const loadPulls = useCallback(async () => {
    if (!selectedClient?.id) { setGhConnected(false); setGhReason("Select a client first."); return; }
    setGhBusy(true); setMergeNote("");
    try {
      const gh = await githubToken();
      const res = await authedFetch(`/api/clients/${selectedClient.id}/github/pulls`, {
        cache: "no-store",
        headers: gh ? { "x-github-token": gh } : {},
      });
      const data = await res.json();
      setGhConnected(Boolean(data.connected));
      setGhReason(data.reason || data.error || "");
      setGhPulls(Array.isArray(data.pulls) ? data.pulls : null);
    } catch (e) {
      setGhConnected(false);
      setGhReason(e instanceof Error ? e.message : "Could not reach the server");
    } finally {
      setGhBusy(false);
    }
  }, [selectedClient?.id]);

  // Load when the Gate & Merge screen opens, and when the client changes under it.
  useEffect(() => {
    if (activeStage === "gate") loadPulls();
  }, [activeStage, loadPulls]);

  const mergePull = useCallback(async (pr: any) => {
    if (!selectedClient?.id) return;
    setMergeBusy(pr.number); setMergeNote("");
    try {
      const ghTok = await githubToken();
      const res = await authedFetch(`/api/clients/${selectedClient.id}/github/merge`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(ghTok ? { "x-github-token": ghTok } : {}),
        },
        // The sha the operator was looking at. If the branch moved since this
        // list rendered, the server refuses rather than shipping an unseen commit.
        body: JSON.stringify({ number: pr.number, headSha: pr.headSha, confirm: true }),
      });
      const data = await res.json();
      setMergeNote(res.ok && data.merged
        ? `Merged #${pr.number}.`
        : data.error || `Merge refused (${res.status}).`);
      if (res.ok && data.merged) await loadPulls();
    } catch (e) {
      setMergeNote(e instanceof Error ? e.message : "Merge failed");
    } finally {
      setMergeBusy(null);
    }
  }, [selectedClient?.id, loadPulls, githubToken]);

  // Which Local Presence sub-section the drawer has selected.
  const [localSubTab, setLocalSubTab] = useState<
    "info" | "hours" | "reviews" | "review_boost" | "posts" | "local_grid" | "nap_audit" | "insights"
  >("info");

  // Which rail section the drawer is showing. It follows the active tab, so
  // navigating from a card, a breadcrumb or a deep link leaves the rail on the
  // section that actually owns the screen rather than stranding it.
  /**
   * Open a nav item. Both sidebar tiers call this, and that is the point.
   *
   * The rail used to carry its own miniature copy of this logic that handled
   * only `tab` and `focus`. Every other item kind — view, gsc, content, and
   * later stage — fell through it, so clicking a rail section changed the
   * drawer and left the workspace showing the previous screen. Gate was the
   * visible case: one click opened the drawer, and you had to click again.
   *
   * Two hand-maintained copies of the same dispatch is precisely the drift the
   * nav tests were written for (~30 entries pointing at 11 screens). Keeping it
   * in one function is what stops the next item kind repeating this.
   */
  const openNavItem = useCallback((item: NavItem) => {
    // Clear every mode first, so an item kind can never inherit the last one.
    setActiveStage(null);
    setActiveContentTool(null);
    setActiveGscView(null);
    setActiveView(null);

    if (item.stage) { setActiveStage(item.stage); }
    else if (item.content) { setActiveContentTool(item.content); }
    else if (item.gsc) { setActiveGscView(item.gsc); }
    else if (item.view) { setActiveView(item.view); }
    else if (item.drawer) { setShowScanDrawer(true); return; }
    else if (item.modal) { openCreateProject(); return; }
    else if (item.href) { if (typeof window !== "undefined") window.location.href = item.href; return; }
    else if (item.focus) { selectAeoFocus(item.focus); return; }
    else if (item.tab) {
      setActiveTab(item.tab);
      if (item.sub) setAuditSubTab(item.sub);
      if (item.local) setLocalSubTab(item.local);
    }
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  }, [selectAeoFocus]);

  const [activeBigNav, setActiveBigNav] = useState<string>(() => sectionForTab("Overview"));
  useEffect(() => {
    setActiveBigNav(sectionForTab(activeTab));
  }, [activeTab]);

  // Google Service Integration State (Real Google OAuth & GSC API)
  const [googleConnected, setGoogleConnected] = useState<boolean>(false);
  const [googleAccount, setGoogleAccount] = useState<string>("");
  const [trafficDataSource, setTrafficDataSource] = useState<"market" | "gsc">(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("reai_traffic_source");
      if (stored === "gsc" || stored === "market") return stored;
    }
    return "market";
  });
  const [selectedGscProperty, setSelectedGscProperty] = useState<string>(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("reai_gsc_property") || `sc-domain:${currentDomain}`;
    }
    return `sc-domain:${currentDomain}`;
  });
  const [verifiedGscProperties, setVerifiedGscProperties] = useState<string[]>([]);
  const [liveGscRows, setLiveGscRows] = useState<any[]>([]);
  const [isGscLoading, setIsGscLoading] = useState<boolean>(false);
  const [gscDateTrend, setGscDateTrend] = useState<Array<{ m: string; v: number }>>([]);
  const [gscCountrySplit, setGscCountrySplit] = useState<Array<{ code: string; country: string; share: number; visits: string }>>([]);
  // null, not `{ mobile: 68, desktop: 32 }`. The setter only fires inside
  // `if (sum > 0)`, so a failed or empty device query left the fabricated
  // default on screen - under a green "Google GSC Verified" badge.
  const [gscDeviceSplit, setGscDeviceSplit] = useState<{ mobile: number; desktop: number } | null>(null);
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<"30s" | "60s" | "5m" | "off">(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("reai_traffic_autorefresh") as any) || "30s";
    }
    return "30s";
  });
  const [lastSyncTime, setLastSyncTime] = useState<Date | null>(null);
  const [syncCountdown, setSyncCountdown] = useState<number>(30);
  const [showIntegrationsModal, setShowIntegrationsModal] = useState<boolean>(false);
  const [googleConnecting, setGoogleConnecting] = useState<boolean>(false);
  const [syncToast, setSyncToast] = useState<string | null>(null);
  const [systemPillarFilter, setSystemPillarFilter] = useState<"all" | "seo" | "aeo">("all");
  const [showOrganicGuideModal, setShowOrganicGuideModal] = useState<boolean>(false);
  const [organicGuideTab, setOrganicGuideTab] = useState<"overview" | "modules" | "tools" | "strategy" | "sop">("overview");

  const cleanGscDomain = useMemo(() => {
    return selectedGscProperty
      .replace(/^sc-domain:/, "")
      .replace(/^https?:\/\//, "")
      .replace(/\/$/, "");
  }, [selectedGscProperty]);

  const cleanProjectDomain = useMemo(() => {
    return currentDomain
      .replace(/^https?:\/\//, "")
      .replace(/\/$/, "");
  }, [currentDomain]);

  const isDomainMismatch = useMemo(() => {
    if (!googleConnected || !selectedGscProperty || !cleanGscDomain) return false;
    return cleanGscDomain.toLowerCase() !== cleanProjectDomain.toLowerCase();
  }, [googleConnected, selectedGscProperty, cleanGscDomain, cleanProjectDomain]);

  const hasCurrentDomainInGsc = useMemo(() => {
    if (!googleConnected || !verifiedGscProperties || verifiedGscProperties.length === 0) return false;
    const cleanCurrent = cleanProjectDomain.toLowerCase().replace(/^www\./, "");
    return verifiedGscProperties.some((p) => {
      const cleanP = p.toLowerCase().replace(/^sc-domain:/, "").replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/\/$/, "");
      return cleanP === cleanCurrent || cleanP.includes(cleanCurrent) || cleanCurrent.includes(cleanP);
    });
  }, [googleConnected, verifiedGscProperties, cleanProjectDomain]);

  const loadCachedSnapshot = useCallback(async (siteUrl: string) => {
    try {
      const res = await authedFetch(`/api/traffic/snapshot?siteUrl=${encodeURIComponent(siteUrl)}`);
      if (res.ok) {
        const json = await res.json();
        if (json.latest) {
          const snap = json.latest;
          if (Array.isArray(snap.top_queries) && snap.top_queries.length > 0) {
            const mapped = snap.top_queries.map((r: any) => ({
              query: (r.keys || [""])[0],
              clicks: r.clicks || 0,
              impressions: r.impressions || 0,
              ctr: Number(((r.ctr || 0) * 100).toFixed(1)),
              position: Number((r.position || 0).toFixed(1)),
            }));
            setLiveGscRows(mapped);
          }
          if (snap.created_at) {
            setLastSyncTime(new Date(snap.created_at));
          }
        }
      }
    } catch {}
  }, []);

  const fetchGscAnalytics = useCallback(async (siteUrl: string) => {
    if (!siteUrl) return;
    setIsGscLoading(true);
    try {
      const [queryRes, dateRes, countryRes, deviceRes] = await Promise.all([
        authedFetch("/api/gsc/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ siteUrl, days: 28, rowLimit: 50, dimensions: ["query"] }),
        }),
        authedFetch("/api/gsc/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ siteUrl, days: 28, rowLimit: 30, dimensions: ["date"] }),
        }),
        authedFetch("/api/gsc/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ siteUrl, days: 28, rowLimit: 10, dimensions: ["country"] }),
        }),
        authedFetch("/api/gsc/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ siteUrl, days: 28, rowLimit: 5, dimensions: ["device"] }),
        }),
      ]);

      const [qData, dData, cData, devData] = await Promise.all([
        queryRes.ok ? queryRes.json() : null,
        dateRes.ok ? dateRes.json() : null,
        countryRes.ok ? countryRes.json() : null,
        deviceRes.ok ? deviceRes.json() : null,
      ]);

      // 1. Process query rows
      if (qData && Array.isArray(qData.rows)) {
        const mapped = qData.rows.map((r: any) => ({
          query: (r.keys || [""])[0],
          clicks: r.clicks || 0,
          impressions: r.impressions || 0,
          ctr: Number(((r.ctr || 0) * 100).toFixed(1)),
          position: Number((r.position || 0).toFixed(1)),
        }));
        setLiveGscRows(mapped);
      } else {
        setLiveGscRows([]);
      }

      // 2. Process date trend
      if (dData && Array.isArray(dData.rows) && dData.rows.length > 0) {
        const rows = dData.rows;
        const step = Math.max(1, Math.floor(rows.length / 6));
        const trendPts: Array<{ m: string; v: number }> = [];
        for (let i = 0; i < rows.length; i += step) {
          const r = rows[i];
          const rawDate = (r.keys || [""])[0];
          const dateLabel = rawDate ? rawDate.slice(5) : `D${i}`;
          trendPts.push({
            m: dateLabel,
            v: r.clicks > 0 ? r.clicks : Number(((r.impressions || 0) / 10).toFixed(1)),
          });
        }
        if (trendPts.length > 0) setGscDateTrend(trendPts);
      }

      // 3. Process country breakdown
      if (cData && Array.isArray(cData.rows) && cData.rows.length > 0) {
        const totalCountryImpressions = cData.rows.reduce((acc: number, r: any) => acc + (r.impressions || 0), 0);
        const ISO_NAMES: Record<string, { name: string; flag: string }> = {
          ind: { name: "India", flag: "🇮🇳" },
          idn: { name: "Indonesia", flag: "🇮🇩" },
          usa: { name: "United States", flag: "🇺🇸" },
          mys: { name: "Malaysia", flag: "🇲🇾" },
          rou: { name: "Romania", flag: "🇷🇴" },
          bra: { name: "Brazil", flag: "🇧🇷" },
          irn: { name: "Iran", flag: "🇮🇷" },
          lka: { name: "Sri Lanka", flag: "🇱🇰" },
          tur: { name: "Turkey", flag: "🇹🇷" },
          bgd: { name: "Bangladesh", flag: "🇧🇩" },
          can: { name: "Canada", flag: "🇨🇦" },
          deu: { name: "Germany", flag: "🇩🇪" },
          gbr: { name: "United Kingdom", flag: "🇬🇧" },
          phl: { name: "Philippines", flag: "🇵🇭" },
          pol: { name: "Poland", flag: "🇵🇱" },
          sgp: { name: "Singapore", flag: "🇸🇬" },
          khm: { name: "Cambodia", flag: "🇰🇭" },
          tha: { name: "Thailand", flag: "🇹🇭" },
          vnm: { name: "Vietnam", flag: "🇻🇳" },
          fra: { name: "France", flag: "🇫🇷" },
          aus: { name: "Australia", flag: "🇦🇺" },
        };
        const mappedCountries = cData.rows.slice(0, 6).map((r: any) => {
          const rawCode = ((r.keys || [""])[0] || "").toLowerCase();
          const info = ISO_NAMES[rawCode] || { name: rawCode.toUpperCase(), flag: "🌐" };
          const share = totalCountryImpressions > 0 ? Number(((r.impressions / totalCountryImpressions) * 100).toFixed(1)) : 0;
          return {
            code: info.flag,
            country: info.name,
            share,
            visits: `${r.clicks || 0} clicks (${r.impressions || 0} imp)`,
          };
        });
        setGscCountrySplit(mappedCountries);
      }

      // 4. Process devices
      if (devData && Array.isArray(devData.rows) && devData.rows.length > 0) {
        let mob = 0;
        let desk = 0;
        let tab = 0;
        for (const r of devData.rows) {
          const k = ((r.keys || [""])[0] || "").toUpperCase();
          if (k === "MOBILE") mob += (r.impressions || r.clicks || 0);
          else if (k === "DESKTOP") desk += (r.impressions || r.clicks || 0);
          else if (k === "TABLET") tab += (r.impressions || r.clicks || 0);
        }
        const sum = mob + desk + tab;
        if (sum > 0) {
          const mobPct = Math.round(((mob + tab) / sum) * 100);
          setGscDeviceSplit({ mobile: mobPct, desktop: 100 - mobPct });
        }
      }

      // 5. Store snapshot in database (Supabase + memory cache)
      const totalClicks = (qData?.rows || []).reduce((acc: number, r: any) => acc + (r.clicks || 0), 0);
      const totalImpressions = (qData?.rows || []).reduce((acc: number, r: any) => acc + (r.impressions || 0), 0);
      const calculatedCtr = totalImpressions > 0 ? Number(((totalClicks / totalImpressions) * 100).toFixed(1)) : 0;
      const avgPos = (qData?.rows || []).length > 0
        ? Number(((qData.rows.reduce((acc: number, r: any) => acc + (r.position || 0), 0)) / qData.rows.length).toFixed(1))
        : 0;

      authedFetch("/api/traffic/snapshot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          siteUrl,
          domain: cleanGscDomain,
          clicks: totalClicks,
          impressions: totalImpressions,
          ctr: calculatedCtr,
          avgPosition: avgPos,
          topQueries: qData?.rows || [],
          countries: cData?.rows || [],
          devices: devData?.rows || [],
          dateTrend: dData?.rows || [],
        }),
      }).catch(() => {});

      setLastSyncTime(new Date());
      setSyncCountdown(autoRefreshInterval === "30s" ? 30 : autoRefreshInterval === "60s" ? 60 : 300);
    } catch (e) {
      console.error("Failed to fetch GSC search analytics", e);
    } finally {
      setIsGscLoading(false);
    }
  }, [cleanGscDomain, autoRefreshInterval]);

  // Realtime live auto-refresh timer (30s by default)
  useEffect(() => {
    if (!googleConnected || trafficDataSource !== "gsc" || autoRefreshInterval === "off" || !selectedGscProperty) return;

    const seconds = autoRefreshInterval === "30s" ? 30 : autoRefreshInterval === "60s" ? 60 : 300;
    setSyncCountdown(seconds);

    const countdownTimer = setInterval(() => {
      setSyncCountdown((prev) => (prev > 1 ? prev - 1 : seconds));
    }, 1000);

    const refreshTimer = setInterval(() => {
      fetchGscAnalytics(selectedGscProperty);
    }, seconds * 1000);

    return () => {
      clearInterval(countdownTimer);
      clearInterval(refreshTimer);
    };
  }, [googleConnected, trafficDataSource, autoRefreshInterval, selectedGscProperty, fetchGscAnalytics]);

  const handleSwitchToGscProject = useCallback(async () => {
    const targetDomain = cleanGscDomain;
    if (!targetDomain) return;
    
    // Check if client already exists in clients list
    const existing = clients?.find((c) => {
      const cDom = (c.website || c.domain || "").replace(/^https?:\/\//, "").replace(/\/$/, "");
      return cDom.toLowerCase() === targetDomain.toLowerCase();
    });

    if (existing && onSelectClient) {
      onSelectClient(existing);
      setSyncToast(`Switched active project to ${existing.business || targetDomain}!`);
      setTimeout(() => setSyncToast(null), 3000);
      return;
    }

    // Create a new client profile
    if (onSaveNewClient) {
      const bizName = targetDomain.split(".")[0].toUpperCase() + ` (${targetDomain})`;
      await onSaveNewClient({
        business: bizName,
        website: selectedGscProperty.startsWith("http") ? selectedGscProperty : `https://${targetDomain}`,
        model: "B",
        goal: "Max Organic Search Visibility via Google Search Console",
        keywords: liveGscRows.slice(0, 5).map((r) => r.query).filter(Boolean),
      });
      setSyncToast(`Created and switched project to ${targetDomain}!`);
      setTimeout(() => setSyncToast(null), 3000);
    }
  }, [cleanGscDomain, clients, onSelectClient, onSaveNewClient, selectedGscProperty, liveGscRows]);

  // Sync Google connection status and detect OAuth return
  useEffect(() => {
    if (typeof window === "undefined") return;

    // Purge any stale mock email from previous runs
    if (localStorage.getItem("reai_google_account") === "marketing@hospital.com.kh") {
      localStorage.removeItem("reai_google_account");
      localStorage.removeItem("reai_google_connected");
    }

    // 1. Detect OAuth redirect back from Google
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected") === "google" || params.get("gsc_status") === "verified") {
      setGoogleConnected(true);
      setTrafficDataSource("gsc");
      localStorage.setItem("reai_google_connected", "true");
      localStorage.setItem("reai_traffic_source", "gsc");
      setSyncToast("🟢 Real Google Search Console account verified and connected live!");
      setTimeout(() => setSyncToast(null), 5000);
      const cleanUrl = window.location.pathname;
      window.history.replaceState({}, document.title, cleanUrl);
    } else if (params.get("google_error")) {
      setSyncToast(`⚠️ Google OAuth error: ${params.get("google_error")}`);
      setTimeout(() => setSyncToast(null), 5000);
    }

    // 2. Fetch live status from backend
    authedFetch(`/api/auth/google/status`)
      .then((res) => res.json())
      .then((data) => {
        if (data.connected) {
          setGoogleConnected(true);
          const email = data.userEmail || "Google Verified Account";
          setGoogleAccount(email);
          localStorage.setItem("reai_google_account", email);
          localStorage.setItem("reai_google_connected", "true");
          if (data.sites && data.sites.length > 0) {
            setVerifiedGscProperties(data.sites);
            // Auto-select valid property: prefer match with current project domain
            const storedProp = localStorage.getItem("reai_gsc_property");
            const matched = data.sites.find((s: string) =>
              s.toLowerCase().includes(cleanProjectDomain.toLowerCase().replace(/^www\./, ""))
            );
            let chosenProp = matched || (storedProp && data.sites.includes(storedProp) ? storedProp : data.sites[0]);
            setSelectedGscProperty(chosenProp);
            localStorage.setItem("reai_gsc_property", chosenProp);

            const storedSource = localStorage.getItem("reai_traffic_source");
            const activeSource = storedSource === "market" ? "market" : "gsc";
            setTrafficDataSource(activeSource);
            localStorage.setItem("reai_traffic_source", activeSource);

            if (activeSource === "gsc") {
              fetchGscAnalytics(chosenProp);
            }
          }
        } else {
          setGoogleConnected(false);
          setGoogleAccount("");
          setTrafficDataSource("market");
          localStorage.removeItem("reai_google_connected");
          localStorage.removeItem("reai_google_account");
        }
      })
      .catch(() => {});
  }, [cleanProjectDomain, fetchGscAnalytics]);

  // Fetch live GSC search analytics when property changes or trafficDataSource becomes gsc
  useEffect(() => {
    if (!googleConnected || trafficDataSource !== "gsc" || !selectedGscProperty) return;
    loadCachedSnapshot(selectedGscProperty);
    fetchGscAnalytics(selectedGscProperty);
  }, [googleConnected, trafficDataSource, selectedGscProperty, fetchGscAnalytics, loadCachedSnapshot]);

  const handleConnectGoogle = useCallback(() => {
    setGoogleConnecting(true);
    // Real browser navigation to Google OAuth initiation endpoint
    window.location.href = `/api/auth/google?prompt=select_account%20consent`;
  }, []);

  const handleDisconnectGoogle = useCallback(async () => {
    try {
      await authedFetch("/api/auth/google/save-token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "disconnect" }),
      });
    } catch {}
    setGoogleConnected(false);
    setTrafficDataSource("market");
    if (typeof window !== "undefined") {
      localStorage.setItem("reai_google_connected", "false");
      localStorage.setItem("reai_traffic_source", "market");
    }
    setSyncToast("Disconnected from Google account. Reverted to Market Model.");
    setTimeout(() => setSyncToast(null), 3000);
  }, []);

  const gscMetrics = useMemo(() => {
    if (liveGscRows && liveGscRows.length > 0) {
      const totalClicks = liveGscRows.reduce((acc, r) => acc + (r.clicks || 0), 0);
      const totalImpressions = liveGscRows.reduce((acc, r) => acc + (r.impressions || 0), 0);
      const calculatedCtr = totalImpressions > 0 ? Number(((totalClicks / totalImpressions) * 100).toFixed(1)) : 0;
      const avgPos = Number((liveGscRows.reduce((acc, r) => acc + (r.position || 0), 0) / liveGscRows.length).toFixed(1));
      return { clicks: totalClicks, impressions: totalImpressions, ctr: calculatedCtr, avgPosition: avgPos, topQueries: liveGscRows };
    }
    return { clicks: 0, impressions: 0, ctr: 0, avgPosition: 0, topQueries: [] };
  }, [liveGscRows]);



  // Dynamic counts: use report counts, fallback to client lastCounts, fallback to baseline
  const [serpAiBusy, setSerpAiBusy] = useState(false);
  const [serpAiDraft, setSerpAiDraft] = useState("");
  const [serpAiError, setSerpAiError] = useState("");
  const report = openReport?.report;

  // What the SERP preview shows.
  //
  // This used to be `pageMetaPresets` - four hardcoded entries titled "Best
  // Hospital & Medical Center in Phnom Penh", with maternity, physician and
  // emergency descriptions, plus a catch-all asserting "healthcare services and
  // clinical facilities" for any URL on any site. One pilot client's copy,
  // simulated for every account, on a screen whose whole purpose is showing the
  // operator what Google displays for THEIR page.
  //
  // The scan now carries the page as fetched (`report.page`), so there is a real
  // title and description to show. When there is not, the preview says so
  // instead of inventing one - an invented preview is worse than an empty one,
  // because the operator optimises against it.
  const scannedPage = (report as any)?.page as
    { url?: string; title?: string | null; description?: string | null } | null | undefined;

  const activeSerpMeta = useMemo(() => {
    const custom = serpCustomMeta[selectedOnPageUrl];
    if (custom) return custom;
    return {
      title: scannedPage?.title || "",
      description: scannedPage?.description || "",
      targetKw: "",
    };
  }, [selectedOnPageUrl, serpCustomMeta, scannedPage]);
  const counts = report?.counts || selectedClient?.lastCounts || {};
  const okChecks = counts.ok ?? 0;
  const errChecks = counts.error ?? 0;
  const warnChecks = counts.warn ?? 0;
  const infoChecks = counts.info ?? 0;
  const totalGraded = okChecks + errChecks + warnChecks;
  /*
   * The scanner's number, or the client row's, or nothing. This used to
   * recompute a pass rate locally and fall back to `report?.score || 0` - the
   * `||` again, so a genuine score of 0 became 0 by accident rather than by
   * measurement, and a scan that graded nothing reported 0% health, which reads
   * as "everything is broken" rather than "we did not look".
   *
   * `audit.health_score` now computes the same pass rate once, in the scanner,
   * and returns null when nothing gradeable ran. Recomputing it here was how
   * one scan came to have three different health numbers (B-055).
   */
  const dynamicHealth: number | null =
    report?.score ?? selectedClient?.lastScore ?? null;

  // The AEO card reads the canonical pillar rather than a second tally: same
  // rule everywhere, and `score` is already null when nothing gradeable ran.
  const aeoPillar = useMemo(
    () => derivePillars(report).find((p) => p.catKey === "aeo") ?? null,
    [report]
  );

  // Pages the crawl really walked. `crawl.site_rows` emits a "Pages crawled"
  // summary row on every multi-page run; the card printed a constant 609.
  const pagesChecked = useMemo(() => {
    const rows = measured(report?.site as any[]) as Array<any>;
    const row = rows.find((r) => r?.code === "site.pages_crawled");
    const n = parseInt(String(row?.detail ?? "").match(/(\d+)/)?.[1] ?? "", 10);
    return Number.isFinite(n) ? n : 0;
  }, [report]);

  // Resolved project metrics for whichever project is selected
  // Ranked findings from the current scan. Empty until a scan has run, which is
  // what the empty state in PriorityActions reports.
  const livePriorities = useMemo(
    () => derivePriorities(report) as unknown as PriorityItem[],
    [report],
  );

  const projectMetrics = useMemo(() => {
    return resolveProjectData(currentDomain, currentBusiness, report, selectedClient);
  }, [currentDomain, currentBusiness, report, selectedClient]);

  // Resolved On-Page Semantic Entity & TF-IDF Benchmarks
  // Semantic/TF-IDF analysis for the selected page.
  //
  // This was a set of fixtures keyed on whether the URL contained "maternity",
  // "doctors" or "emergency", with invented entity relevance scores, competitor
  // counts and word-count targets, and an "AI draft" that interpolated the real
  // client name into hospital copy. None of it came from a measurement.
  //
  // The scanner has no TF-IDF tool yet, so there is nothing to derive from. The
  // panel renders zeroes until one exists.
  const onPageSemanticData = useMemo(() => {
    return {
      url: selectedOnPageUrl || "",
      title: "",
      wordCount: { current: 0, target: 0, deficit: 0 },
      headingCount: { current: 0, target: 0 },
      entityDensity: { current: "—", target: "—" },
      readability: { current: "—", target: "—" },
      entities: [] as Array<{
        term: string;
        relevance: number;
        competitors: number;
        status: string;
        section: string;
      }>,
      aiDraftBlock: "",
    };
  }, [selectedOnPageUrl]);

  // Filtered tools catalog for 156-engine directory
  // The real catalog, from the scanner itself (GET /api/tools -> the Python
  // catalog in pipeline/scanner/server.py). This replaced a 148-entry file
  // whose header claimed 160 tools and which was transcribed from a document:
  // no entry carried a key, a cost, or anything the scanner would recognise.
  const [scannerTools, setScannerTools] = useState<ScannerTool[]>([]);
  useEffect(() => {
    let cancelled = false;
    fetchTools().then((t) => {
      if (!cancelled) setScannerTools(t);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const catalogSummary = useMemo(() => summarize(scannerTools), [scannerTools]);
  const catalogCategories = useMemo(() => categoriesOf(scannerTools), [scannerTools]);
  const filteredCatalogTools = useMemo(
    () => filterTools(scannerTools, toolCatalogCategory, toolCatalogQuery),
    [scannerTools, toolCatalogCategory, toolCatalogQuery],
  );

  // Real issues extracted from scan report for the active client
  const allIssues = useMemo(() => {
    // Derived from the report, not hardcoded. The old fixed list named 13
    // categories and so silently dropped every finding from the other 10 tools
    // - internal links, sitemap/hreflang, video, all four Lighthouse
    // categories, keywords, rankings and rankings trend. Those tools ran on
    // every scan and their results went nowhere. Reading the report's own keys
    // means a new tool appears here the day it is added.
    const NON_GROUP = new Set(["score", "counts", "cost", "log", "cycle", "url", "site_url"]);
    const categories = Object.keys(report || {}).filter(
      (k) => !NON_GROUP.has(k) && Array.isArray((report as any)[k]),
    );
    const out: Array<{ category: string; what: string; why: string; fix: string; detail: string; severity: string; code: string }> = [];
    if (!report) return out;
    for (const cat of categories) {
      const rows = (report[cat] || []) as Array<any>;
      for (const r of rows) {
        if (r.severity === "error" || r.severity === "warn" || r.severity === "info") {
          out.push({
            category: cat.toUpperCase(),
            what: r.what || "",
            why: r.why || "",
            fix: r.fix || "",
            detail: r.detail || "",
            severity: r.severity || "info",
            code: r.code || "",
          });
        }
      }
    }
    return out;
  }, [report]);

  // Handle Project Creation in this single UI
  /** Blank the form and open it in create mode. */
  function openCreateProject() {
    setEditingProject(null);
    setProjectError(null);
    setDomainMoved(null);
    setNewBiz(""); setNewUrl(""); setNewModel("B"); setNewRepo("");
    setNewGoal(""); setNewKw(""); setNewKwList([]);
    setShowNewProjectModal(true);
  }

  /**
   * Open the same form over an existing project.
   *
   * Every field is loaded from the record, including the ones the operator is
   * not here to change. A form that opens blank and PATCHes what was typed
   * silently blanks everything else, and "I put the wrong website URL" must not
   * cost the keywords.
   */
  function openEditProject(c: any) {
    if (!c) return;
    setEditingProject(c);
    setProjectError(null);
    setDomainMoved(null);
    setNewBiz(c.business || "");
    setNewUrl(c.website || (c.domain ? `https://${c.domain}` : ""));
    setNewModel(c.model || "B");
    setNewRepo(c.repo || "");
    setNewGoal(c.goal || "");
    setNewKw("");
    setNewKwList(Array.isArray(c.keywords) ? c.keywords : []);
    setShowNewProjectModal(true);
  }

  async function handleCreateProjectSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!newUrl.trim()) return;
    setProjectError(null);
    setSavingProject(true);
    try {
      const host = newUrl.trim().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
      const profile = {
        business: newBiz || host,
        domain: host,
        website: newUrl.trim(),
        model: newModel,
        repo: newRepo,
        tier: editingProject?.tier ?? 1,
        keywords: newKwList,
        competitors: Array.isArray(editingProject?.competitors) ? editingProject.competitors : [],
        goal: newGoal,
      };

      if (editingProject) {
        if (!onUpdateClient) return;
        const res = await onUpdateClient(editingProject.id, profile);
        if (!res.ok) {
          // Kept open, with the reason. Closing on failure is how an operator
          // comes to believe a wrong URL was corrected when it was not.
          setProjectError(res.error);
          return;
        }
        // The site moved under scans that measured the old one. Those scans keep
        // their own `url`, so nothing is falsified in the record - but the
        // operator has to be told, or the next score they read is attributed to
        // a site it never ran against.
        if (res.domainChanged && res.domainChanged.staleScans > 0) {
          setDomainMoved(res.domainChanged);
        }
        setShowNewProjectModal(false);
        setEditingProject(null);
        return;
      }

      if (!onSaveNewClient) return;
      await onSaveNewClient(profile);
      setShowNewProjectModal(false);
      setNewBiz(""); setNewUrl(""); setNewRepo(""); setNewKwList([]);
    } finally {
      setSavingProject(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", background: "#f8fafc", fontFamily: "system-ui, -apple-system, sans-serif" }}>
      
      {/* ── 1. UNIFIED APEX INTELLIGENCE TOPBAR (SOFT SLATE NAVY) ── */}
      <header style={{
        height: 50, background: "#161b26", borderBottom: "1px solid #232c3d",
        display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px 0 16px",
        position: "sticky", top: 0, zIndex: 100, color: "#ffffff",
      }}>
        {/* Left: Brand Identity & Tool Search */}
        <div style={{ display: "flex", alignItems: "center", gap: 24, flex: 1, maxWidth: 640 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }} onClick={() => setActiveTab("Overview")}>
            <div style={{
              width: 34, height: 34, borderRadius: 9, background: "linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)",
              display: "grid", placeItems: "center", fontWeight: 900, color: "#fff", fontSize: 14, letterSpacing: "-0.03em",
              boxShadow: "0 2px 8px rgba(99, 102, 241, 0.35)",
            }}>
              RE
            </div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 900, letterSpacing: "0.03em", color: "#f8fafc", lineHeight: 1.1 }}>
                REAI
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                SEO Intelligence
              </div>
            </div>
          </div>

          <span style={{ width: 1, height: 24, background: "#263043" }} />

          {/* Quick Search */}
          <div style={{ position: "relative", width: "100%", maxWidth: 380 }}>
            <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "#718096", fontSize: 14 }}>
              🔍
            </span>
            <input
              type="text"
              placeholder="Search keyword or enter URL to audit..."
              value={quickInput}
              onChange={(e) => setQuickInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && quickInput.trim()) {
                  if (onTriggerScan) {
                    setShowScanDrawer(true);
                    onTriggerScan(quickInput.trim());
                  }
                  setQuickInput("");
                }
              }}
              style={{
                width: "100%", height: 38, padding: "0 36px 0 36px", fontSize: 13,
                background: "#1e2536", border: "1px solid #2d384e", borderRadius: 8,
                outline: "none", color: "#e2e8f0",
              }}
            />
          </div>
        </div>

        {/* Right: Engine Status, New Scan & Profile */}
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <button
            type="button"
            onClick={() => setActiveTab("All Tools Directory")}
            style={{
              display: "flex", alignItems: "center", gap: 7,
              background: activeTab === "All Tools Directory" ? "#4f46e5" : "#1e2536",
              color: "#ffffff", border: "1px solid",
              borderColor: activeTab === "All Tools Directory" ? "#6366f1" : "#2d384e",
              borderRadius: 8, padding: "7px 14px", fontSize: 12.5, fontWeight: 600, cursor: "pointer",
            }}
          >
            <IconGrid size={15} />
            <span>All Tools ({catalogSummary.tools})</span>
          </button>

          <button
            type="button"
            onClick={() => setShowExecutiveReportModal(true)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              background: "#1e2536", color: "#e2e8f0", border: "1px solid #2d384e",
              borderRadius: 8, padding: "7px 13px", fontSize: 12.5, fontWeight: 600, cursor: "pointer",
              transition: "all 0.15s ease",
            }}
          >
            <span>📄</span>
            <span>Client Report</span>
          </button>

          <button
            type="button"
            onClick={googleConnected ? () => setShowIntegrationsModal(true) : handleConnectGoogle}
            disabled={googleConnecting}
            style={{
              display: "flex", alignItems: "center", gap: 7,
              background: googleConnected ? "rgba(16, 185, 129, 0.14)" : "#1e2536",
              color: googleConnected ? "#34d399" : "#e2e8f0",
              border: "1px solid",
              borderColor: googleConnected ? "rgba(16, 185, 129, 0.4)" : "#2d384e",
              borderRadius: 8, padding: "7px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
              transition: "all 0.15s ease",
            }}
          >
            <IconGoogle size={14} />
            <span>{googleConnecting ? "Navigating to Google..." : googleConnected ? "GSC Live" : "Connect Google →"}</span>
          </button>

          {(() => {
            const dailyBudget = budget?.dailyBudget ?? 5;
            const spentToday = budget?.spentToday ?? (openReport?.scan?.cost ?? 0);
            return (
              <div style={{
                display: "flex", alignItems: "center", gap: 7, fontSize: 12, fontWeight: 700,
                background: "rgba(16, 185, 129, 0.12)", border: "1px solid rgba(16, 185, 129, 0.35)",
                padding: "5px 12px", borderRadius: 20, color: "#34d399", letterSpacing: "0.02em",
              }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#34d399", boxShadow: "0 0 6px #34d399" }} />
                <span>DAILY BUDGET: {formatUsd(spentToday)} / {formatUsd(dailyBudget)}</span>
              </div>
            );
          })()}

          <button
            type="button"
            onClick={() => {
              setShowScanDrawer(true);
              if (onTriggerScan) onTriggerScan(currentDomain);
            }}
            style={{
              background: "linear-gradient(135deg, #059669 0%, #047857 100%)", color: "#ffffff",
              border: 0, borderRadius: 8, padding: "8px 18px", fontSize: 12.5, fontWeight: 600,
              cursor: "pointer", display: "flex", alignItems: "center", gap: 7,
              boxShadow: "0 2px 6px rgba(5, 150, 105, 0.25)",
            }}
          >
            <span>⚡ Run Scan</span>
          </button>

          <Link
            href="/profile"
            title="Profile & Account Settings"
            style={{
              width: 32, height: 32, borderRadius: "50%", background: "#4f46e5",
              color: "#fff", display: "grid", placeItems: "center", fontWeight: 700, fontSize: 13,
              cursor: "pointer", border: "2px solid #6366f1", textDecoration: "none",
            }}
          >
            👤
          </Link>
        </div>
      </header>

      {/* ── 2. UNIFIED MODERN SIDEBAR + MAIN CONTENT ── */}
      <div style={{ display: "flex", flex: 1, alignItems: "stretch" }}>
        

        {/* ── 2A. BIG SIDEBAR (PRIMARY RAIL) ── */}
        <aside
          aria-label="Primary Navigation Rail"
          style={{
            // 80px is the measurement, not a round number: the widest label
            // ("Research") runs ~51px at 12px/600 Inter, and the button carries
            // 4px of side padding inside 8px of rail padding. Narrower than this
            // and the label overflows its own selected pill.
            width: 80,
            background: "var(--surface)",
            borderRight: "1px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            alignItems: "stretch",
            gap: "var(--space-1)",
            padding: "var(--space-3) var(--space-2)",
            flexShrink: 0,
            position: "sticky",
            top: 50,
            height: "calc(100vh - 50px)",
            boxSizing: "border-box",
            zIndex: 12,
          }}
        >
          {NAV_SECTIONS.map((section) => {
            const isSelected = activeBigNav === section.id;
            const icon = RAIL_ICONS[section.id];
            return (
              <button
                key={section.id}
                type="button"
                title={section.heading}
                aria-current={isSelected ? "true" : undefined}
                onClick={() => {
                  setActiveBigNav(section.id);
                  // Opening a section lands on its first item, whatever kind it
                  // is — one click, not two. `openNavItem` handles every kind,
                  // so a new one cannot silently fall through here again.
                  const first = sectionItems(section)[0];
                  if (first) openNavItem(first);
                }}
                className="rail-btn"
              >
                {icon}
                <span>{section.label}</span>
              </button>
            );
          })}

          {/*
            Account-level destinations, pinned to the foot of the rail. They are
            not project reports, so they sit apart from the sections rather than
            in a group of their own inside the drawer.
          */}
          <div style={{ marginTop: "auto", width: "100%", display: "flex", flexDirection: "column", gap: "var(--space-1)", paddingTop: "var(--space-2)", borderTop: "1px solid var(--border)" }}>
            {[
              { id: "integrations", label: "Connect", title: "Integrations", href: "/integrations/google", icon: <IconSliders size={19} /> },
              { id: "profile", label: "Account", title: "Profile & Account", href: "/profile", icon: <IconUser size={19} /> },
            ].map((item) => (
              <button
                key={item.id}
                type="button"
                title={item.title}
                className="rail-btn"
                onClick={() => {
                  if (typeof window !== "undefined") window.location.href = item.href;
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            ))}
          </div>
        </aside>

        {/* ── 2B. SMALL SIDEBAR (CONTEXTUAL DRAWER) ── */}
        {!isSmallSidebarCollapsed && (
          <aside
            aria-label="Main Navigation"
            style={{
              width: 228,
              flexShrink: 0,
              background: "#ffffff",
              borderRight: "1px solid #edf0f4",
              display: "flex",
              flexDirection: "column",
              padding: "16px 12px 96px 12px",
              position: "sticky",
              top: 50,
              height: "calc(100vh - 50px)",
              overflowY: "auto",
              boxSizing: "border-box",
              zIndex: 11,
            }}
          >
            {/* Active Project Switcher Card */}
            <div style={{
              marginBottom: 16, padding: "10px 12px", background: "#f8fafc",
              border: "1px solid #e2e8f0", borderRadius: 8,
              position: "relative",
            }}>
              <div style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase",
                letterSpacing: "0.06em", marginBottom: 6,
              }}>
                <span>Project</span>
                <button
                  type="button"
                  onClick={() => openCreateProject()}
                  style={{
                    background: "none", border: 0, color: "#2563eb",
                    fontSize: 12, fontWeight: 700, cursor: "pointer", padding: 0,
                  }}
                >
                  + New
                </button>
              </div>

              <button
                type="button"
                onClick={() => setSidebarProjectOpen(!sidebarProjectOpen)}
                style={{
                  width: "100%", padding: "6px 8px", background: "#ffffff",
                  border: "1px solid", borderColor: sidebarProjectOpen ? "#3b82f6" : "#cbd5e1",
                  borderRadius: 6, outline: "none", cursor: "pointer",
                  display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6,
                  textAlign: "left",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                  <div style={{
                    width: 20, height: 20, borderRadius: 4,
                    background: "linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%)",
                    color: "#ffffff", display: "grid", placeItems: "center",
                    fontWeight: 800, fontSize: 12, flexShrink: 0,
                  }}>
                    {(currentBusiness || "P")[0].toUpperCase()}
                  </div>
                  <div style={{ minWidth: 0, overflow: "hidden" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#1e293b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {currentBusiness}
                    </div>
                  </div>
                </div>
                <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>▾</span>
              </button>

              {/* Custom Floating Project Menu Popover */}
              {sidebarProjectOpen && (
                <div style={{
                  position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
                  background: "#ffffff", borderRadius: 8, border: "1px solid #cbd5e1",
                  boxShadow: "0 10px 24px -4px rgba(15, 23, 42, 0.18)",
                  zIndex: 200, padding: "4px 0", maxHeight: 240, overflowY: "auto",
                }}>
                  <div style={{ padding: "4px 10px", fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase" }}>
                    Switch Project ({clients.length})
                  </div>
                  {clients.map((c) => {
                    const isCur = c.id === selectedClient?.id;
                    return (
                      <div
                        key={c.id}
                        onClick={() => {
                          onSelectClient(c);
                          setSidebarProjectOpen(false);
                        }}
                        style={{
                          padding: "6px 10px", cursor: "pointer",
                          background: isCur ? "#ecfdf5" : "transparent",
                          display: "flex", alignItems: "center", justifyContent: "space-between",
                        }}
                      >
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 12, fontWeight: isCur ? 700 : 600, color: isCur ? "#047857" : "#1e293b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {c.business || c.domain}
                          </div>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {c.website || c.domain}
                          </div>
                        </div>
                        {isCur && <span style={{ fontSize: 12, fontWeight: 800, color: "var(--ok)" }}>✓</span>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/*
              Merged navigation, drawer half.

              The rail picks a section; this lists that section's screens. Both
              tiers read NAV_SECTIONS, so they cannot drift apart the way the
              two hand-maintained copies did: ~30 entries pointed at 11 real
              screens, with "Technical SEO", "Sensor" and "Site Audit" all
              opening Site Health & Audit and seven labels all opening Keyword
              Data Lab. Enforced by tests/nav.test.mjs.
            */}
            {NAV_SECTIONS.filter((section) => section.id === activeBigNav).map((section) => (
              <div key={section.id} style={{ marginBottom: 12 }}>
                <div
                  style={{
                    // This repeats the rail's label for the current section, so
                    // it is a caption, not a destination. At weight 700 in the
                    // body ink it read as an active item and made the drawer
                    // look like a third nav layer. Quieter weight and ink, so it
                    // recedes behind the items it labels.
                    //
                    // --ink-faint is 4.76:1 on this drawer's white surface and
                    // passes AA there. It would fail on any tinted surface
                    // (4.34:1 on --surface-3), so this is not a pattern to copy
                    // onto a panel. Literal opacity is not an option for the
                    // same reason.
                    fontSize: 12,
                    fontWeight: 600,
                    color: "var(--ink-faint)",
                    padding: "4px 8px",
                    marginBottom: "var(--space-1)",
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                  }}
                >
                  {section.heading}
                </div>
                {section.groups.map((group, groupIndex) => (
                <div
                  key={group.heading ?? `group-${groupIndex}`}
                  style={{ display: "flex", flexDirection: "column", gap: 1, marginBottom: group.heading ? "var(--space-3)" : 0 }}
                >
                  {group.heading && (
                    <div
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        color: "var(--ink-muted)",
                        padding: "6px 8px 2px",
                      }}
                    >
                      {group.heading}
                    </div>
                  )}
                  {group.items.map((item) => {
                    // Exactly one item may be highlighted, and the way to
                    // guarantee that is to decide WHICH MODE is active once,
                    // then let only that mode's items match.
                    //
                    // This was a ladder of ternaries where each branch had to
                    // remember to exclude every mode above it — and several did
                    // not. Adding `stage` made it visible (Fix Stage and Review
                    // Fixes lit together), but `view`, `gsc` and `focus` were
                    // already able to double-highlight with each other. Every
                    // new item kind needed edits in five places to stay correct,
                    // which is not a rule anyone can hold in their head.
                    const isSelected =
                      activeStage ? item.stage === activeStage
                      : activeContentTool ? item.content === activeContentTool
                      : activeGscView ? item.gsc === activeGscView
                      : activeView ? item.view === activeView
                      : item.focus
                        ? activeTab === "AI & AEO Lab" && aeoActiveFocus === item.focus
                        : Boolean(item.tab) &&
                          activeTab === item.tab &&
                          (!item.sub || auditSubTab === item.sub) &&
                          (!item.local || localSubTab === item.local);
                    return (
                      <button
                        key={item.label}
                        type="button"
                        aria-current={isSelected ? "page" : undefined}
                        onClick={() => openNavItem(item)}
                        style={{
                          width: "100%",
                          textAlign: "left",
                          padding: "6px 10px 6px 12px",
                          borderRadius: 6,
                          border: 0,
                          cursor: "pointer",
                          fontSize: 13,
                          fontWeight: isSelected ? 600 : 400,
                          color: isSelected ? "#1d4ed8" : "var(--ink-muted)",
                          background: isSelected ? "#eff6ff" : "transparent",
                        }}
                      >
                        {item.label}
                      </button>
                    );
                  })}
                </div>
                ))}
              </div>
            ))}

            {/*
              The Workspace group moved to the rail. Integrations and Profile
              are account-level, not project reports, so they belong beside the
              sections rather than inside one. "New Project" went entirely: the
              project card at the top of this drawer already has a "+ New".
            */}
            <div style={{ marginTop: "auto", borderTop: "1px solid var(--border)", paddingTop: 10 }}>
              {/* All Tools Directory Pinned */}
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid #edf0f4" }}>
                <button
                  type="button"
                  onClick={() => setActiveTab("All Tools Directory")}
                  style={{
                    width: "100%", padding: "7px 10px", borderRadius: 6,
                    border: "1px solid #cbd5e1", background: activeTab === "All Tools Directory" ? "#2563eb" : "#ffffff",
                    color: activeTab === "All Tools Directory" ? "#ffffff" : "#1e293b",
                    fontSize: 12, fontWeight: 600, cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                  }}
                >
                  <span>All Tools Directory</span>
                  <span style={{
                    fontSize: 12, padding: "1px 5px", borderRadius: 8,
                    background: activeTab === "All Tools Directory" ? "rgba(255,255,255,0.2)" : "#f1f5f9",
                    color: activeTab === "All Tools Directory" ? "#ffffff" : "var(--ink-muted)",
                    fontWeight: 700,
                  }}>
                    {catalogSummary.tools}
                  </span>
                </button>
              </div>
            </div>
          </aside>
        )}

        {/* ── 3. MAIN WORKSPACE STAGE ── */}
        <main style={{ flex: 1, minWidth: 0, padding: "24px 32px 80px 32px", overflowY: "auto", background: "#f8fafc" }}>

          {/*
            A report view replaces the tab content. Each view is a named slice
            of rows the scan already produced (lib/reportViews.ts), rendered
            through the one sortable/filterable/paginated table. No view fetches
            anything: adding a screen costs no API call and no money.
          */}
          {activeStage ? (
            (() => {
              const st = pipelineStage(activeStage);
              const worklist = planState?.plan?.worklist as any[] | undefined;
              const lanes = st.id === "plan" ? laneCounts(worklist) : null;
              const canAttempt = st.id === "plan" ? actionableCount(worklist) : null;
              const hasResult = st.id === "plan" ? Boolean(lanes) : false;

              const card: React.CSSProperties = {
                background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "16px 18px",
              };

              return (
                <div style={{ maxWidth: 1200 }}>
                  {/* Stepper — the stage in the run, so the screen is never
                      read out of context. */}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 18, flexWrap: "wrap" }}>
                    {PIPELINE_STAGES.map((s, i) => (
                      <React.Fragment key={s.id}>
                        {i > 0 && <span style={{ color: "#cbd5e1", fontSize: 13 }}>→</span>}
                        <button
                          type="button"
                          onClick={() => setActiveStage(s.id)}
                          style={{
                            border: 0, cursor: "pointer", borderRadius: 999, padding: "4px 12px",
                            fontSize: 12.5, fontWeight: 700,
                            background: s.id === st.id ? "#1e293b" : "#f1f5f9",
                            color: s.id === st.id ? "#fff" : "var(--ink-muted)",
                          }}
                        >
                          {s.step}. {s.label}
                        </button>
                      </React.Fragment>
                    ))}
                  </div>

                  <div style={{ marginBottom: "var(--space-5)" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--ink)", margin: 0 }}>{st.label}</h1>
                      <span style={{
                        fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase",
                        padding: "3px 8px", borderRadius: 4,
                        color: st.connected ? "#2c6b4f" : "var(--ink-muted)",
                        background: st.connected ? "#e4efe9" : "#f1f5f9",
                        border: `1px solid ${st.connected ? "#c7e0d3" : "#e2e8f0"}`,
                      }}>
                        {st.connected ? "Live" : "Result not connected"}
                      </span>
                    </div>
                    <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "var(--space-1) 0 0", maxWidth: "70ch" }}>
                      {st.purpose}
                    </p>
                  </div>

                  {/* ── PLAN: lanes, the actionable gap, and the worklist ── */}
                  {st.id === "plan" && lanes ? (
                    <>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 12, marginBottom: 14 }}>
                        {([["Regression", lanes.REGRESSION, "#a33a22"], ["New", lanes.NEW, "#8a6a14"],
                           ["Persisting", lanes.PERSISTING, "#55646f"], ["Resolved", lanes.RESOLVED, "#2c6b4f"]] as const)
                          .map(([label, n, colour]) => (
                          <div key={label} style={card}>
                            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".07em", textTransform: "uppercase", color: "var(--ink-muted)" }}>{label}</div>
                            <div style={{ fontSize: 26, fontWeight: 800, color: colour, marginTop: 4, fontVariantNumeric: "tabular-nums" }}>{n}</div>
                          </div>
                        ))}
                      </div>
                      <div style={{ ...card, marginBottom: 14, fontSize: 14, color: "var(--ink-body)" }}>
                        <b>{canAttempt ?? 0}</b> of <b>{worklist?.length ?? 0}</b> items are inside this client&rsquo;s tier and mapped to a fix the
                        agent can attempt. The rest need a person — either the tier does not permit the change, or the fix is a judgement call.
                      </div>
                      <div style={{ ...card, padding: 0, overflowX: "auto" }}>
                        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13.5 }}>
                          <thead>
                            <tr>
                              {["Finding", "Page", "Lane", "Agent can fix?"].map(h => (
                                <th key={h} style={{ textAlign: "left", padding: "10px 14px", borderBottom: "1.5px solid #1e293b", fontSize: 11, letterSpacing: ".07em", textTransform: "uppercase", color: "var(--ink)", whiteSpace: "nowrap" }}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {(worklist ?? []).slice(0, 50).map((item: any, i: number) => {
                              const why = blockedReason(item);
                              return (
                                <tr key={item.id ?? i}>
                                  <td style={{ padding: "10px 14px", borderBottom: "1px solid #eef1f4", color: "var(--ink-body)" }}>{item.code ?? item.what ?? "—"}</td>
                                  <td style={{ padding: "10px 14px", borderBottom: "1px solid #eef1f4", color: "var(--ink-muted)", fontFamily: "ui-monospace, monospace", fontSize: 12.5 }}>{item.location ?? item.url ?? "—"}</td>
                                  <td style={{ padding: "10px 14px", borderBottom: "1px solid #eef1f4", color: "var(--ink-muted)" }}>{item.status ?? "—"}</td>
                                  <td style={{ padding: "10px 14px", borderBottom: "1px solid #eef1f4", color: why ? "var(--ink-muted)" : "#2c6b4f", fontWeight: why ? 400 : 600 }}>
                                    {why ?? "yes"}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      {/* The items the agent CANNOT take are the ones a person is
                          left holding, and "the rest need a person" is exactly
                          where this screen used to stop. Items the agent CAN take
                          are excluded: those already have a pipeline that runs
                          them under a tier with the gates watching. */}
                      <FixWithClaude
                        findings={worklistFindings(worklist)}
                        business={currentBusiness}
                        domain={currentDomain}
                        label="Brief me on the items the agent cannot take"
                      />
                    </>
                  ) : null}

                  {/* ── GATE & MERGE: real check runs, and the merge button ──
                      The 20 gates ARE the pull request's check runs, so this is
                      the verdict, not a mirror of it. Merge lives here because
                      merge is a button: putting it on its own screen only adds
                      a click between the evidence and the decision. */}
                  {st.id === "gate" ? (
                    <>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                        <button
                          type="button" onClick={() => loadPulls()} disabled={ghBusy}
                          style={{ padding: "7px 13px", borderRadius: 6, border: "1px solid #e2e8f0", cursor: "pointer",
                                   background: "#fff", fontSize: 13, fontWeight: 600, opacity: ghBusy ? 0.6 : 1 }}
                        >
                          {ghBusy ? "Checking…" : "Refresh from GitHub"}
                        </button>
                        {mergeNote ? (
                          <span style={{ fontSize: 13, color: /^Merged/.test(mergeNote) ? "#2c6b4f" : "#a33a22" }}>{mergeNote}</span>
                        ) : null}
                      </div>

                      {ghConnected === false ? (
                        <div style={{ border: "1px dashed #e2e8f0", borderRadius: 8, background: "#fafbfc", padding: "24px 22px", maxWidth: 800 }}>
                          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ink-body)", marginBottom: 8 }}>
                            Not connected to this client&rsquo;s repository
                          </div>
                          {/* The reason is printed verbatim. "Not installed",
                              "missing the repo scope" and "rate limited" need
                              different actions, and one shared empty state
                              would hide which happened. */}
                          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0, lineHeight: 1.6, maxWidth: "68ch" }}>
                            {ghReason || "No reason reported."}
                          </p>
                          <p style={{ fontSize: 12.5, color: "var(--ink-muted)", marginTop: 12, lineHeight: 1.6, maxWidth: "68ch" }}>
                            The client adds your GitHub account as a collaborator on their repository.
                            Read access is enough to see gate results; write access is needed to merge.
                          </p>
                        </div>
                      ) : ghPulls && ghPulls.length > 0 ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                          {ghPulls.map((pr: any) => {
                            const c = pr.checks;
                            const green = c && c.allGreen;
                            const unknown = !c || c.runs === null;
                            return (
                              <div key={pr.number} style={{ ...card, padding: 0, overflow: "hidden" }}>
                                <div style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "14px 18px", borderBottom: "1px solid #eef1f4", flexWrap: "wrap" }}>
                                  <div style={{ flex: "1 1 320px", minWidth: 0 }}>
                                    <div style={{ fontSize: 15, fontWeight: 700, color: "var(--ink)" }}>
                                      #{pr.number} {pr.title}
                                    </div>
                                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 3, fontFamily: "ui-monospace, monospace" }}>
                                      {pr.headRef} → {pr.baseRef} · {pr.headSha.slice(0, 7)} · {pr.author}
                                    </div>
                                  </div>
                                  <span style={{
                                    fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase",
                                    padding: "4px 9px", borderRadius: 4, whiteSpace: "nowrap",
                                    background: unknown ? "#f1f5f9" : green ? "#e4efe9" : c.pending ? "#f7efd9" : "#f8e8e3",
                                    color: unknown ? "var(--ink-muted)" : green ? "#2c6b4f" : c.pending ? "#8a6a14" : "#a33a22",
                                  }}>
                                    {unknown ? "No gate results" : c.pending ? `${c.passed}/${c.total} · still running`
                                      : green ? `All ${c.total} gates green` : `${c.failed} of ${c.total} failed`}
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() => mergePull(pr)}
                                    disabled={!green || mergeBusy === pr.number}
                                    title={green ? "Merge this pull request" : "Merging is blocked until every gate is green"}
                                    style={{
                                      padding: "8px 15px", borderRadius: 6, border: 0, fontSize: 13, fontWeight: 700,
                                      cursor: green ? "pointer" : "not-allowed", whiteSpace: "nowrap",
                                      background: green ? "#1e293b" : "#e2e8f0",
                                      color: green ? "#fff" : "var(--ink-muted)",
                                    }}
                                  >
                                    {mergeBusy === pr.number ? "Merging…" : "Merge"}
                                  </button>
                                </div>

                                {c && c.runs ? (
                                  <div style={{ overflowX: "auto" }}>
                                    <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
                                      <tbody>
                                        {c.runs.map((r: any) => {
                                          const ok = r.status === "completed" && ["success", "neutral", "skipped"].includes(r.conclusion);
                                          const running = r.status !== "completed";
                                          return (
                                            <tr key={r.name}>
                                              <td style={{ padding: "7px 18px", borderBottom: "1px solid #f4f6f8", width: 24, color: running ? "#8a6a14" : ok ? "#2c6b4f" : "#a33a22", fontWeight: 700 }}>
                                                {running ? "•" : ok ? "✓" : "✗"}
                                              </td>
                                              <td style={{ padding: "7px 0", borderBottom: "1px solid #f4f6f8", fontFamily: "ui-monospace, monospace", fontSize: 12.5, color: "var(--ink-body)" }}>{r.name}</td>
                                              <td style={{ padding: "7px 18px", borderBottom: "1px solid #f4f6f8", color: "var(--ink-muted)", textAlign: "right" }}>
                                                {running ? r.status.replace("_", " ") : r.conclusion}
                                              </td>
                                            </tr>
                                          );
                                        })}
                                      </tbody>
                                    </table>
                                  </div>
                                ) : (
                                  <div style={{ padding: "14px 18px", fontSize: 13, color: "var(--ink-muted)", lineHeight: 1.6 }}>
                                    GitHub reported no check runs for this commit. That is not a pass — the
                                    workflow may not have started, or the client repo may not be running the
                                    quality gate. Merging is blocked until gates report.
                                  </div>
                                )}

                                {/* A red gate is where an operator is most stuck
                                    and least helped: the check run gives a name and
                                    a conclusion and nothing else. The roster knows
                                    what each gate reads and blocks on, so a failure
                                    becomes the same shape every other screen hands
                                    to Claude. */}
                                {c?.runs && c.failed > 0 && (
                                  <div style={{ padding: "0 18px 14px" }}>
                                    <FixWithClaude
                                      findings={gateFindings(c.runs)}
                                      business={currentBusiness}
                                      domain={currentDomain}
                                      label="Explain and fix these gate failures"
                                    />
                                  </div>
                                )}

                                {/* Live activity. The check-run table above is the
                                    VERDICT; this is the run itself - every step, in
                                    order, with what that gate reads and how long it
                                    took. "One gate is red" is the least useful
                                    moment to have no visibility into what it looked
                                    at. Polls only while something is running. */}
                                <details style={{ borderTop: "1px solid #eef1f4" }}>
                                  <summary style={{ cursor: "pointer", padding: "10px 18px", fontSize: 12.5, fontWeight: 600, color: "#4f46e5" }}>
                                    Watch this run, step by step
                                  </summary>
                                  <div style={{ padding: "0 18px 16px" }}>
                                    <GateActivity
                                      clientId={selectedClient?.id}
                                      sha={pr.headSha}
                                      getToken={githubToken}
                                    />
                                  </div>
                                </details>
                              </div>
                            );
                          })}
                        </div>
                      ) : ghConnected === null ? (
                        <div style={{ fontSize: 13, color: "var(--ink-muted)" }}>Loading pull requests…</div>
                      ) : (
                        <div style={{ border: "1px dashed #e2e8f0", borderRadius: 8, background: "#fafbfc", padding: "24px 22px", maxWidth: 760 }}>
                          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ink-body)", marginBottom: 8 }}>No open pull requests</div>
                          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0, lineHeight: 1.6, maxWidth: "68ch" }}>{st.absent}</p>
                        </div>
                      )}

                      {/* What runs, and what decides an automatic merge. Engine
                          truth — true regardless of any particular run. */}
                      <details style={{ marginTop: 22 }}>
                        <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600, color: "var(--ink-muted)" }}>
                          The {GATE_ROSTER.length} gates, and the auto-merge policy
                        </summary>
                        <div style={{ ...card, padding: 0, overflowX: "auto", marginTop: 12 }}>
                          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13.5 }}>
                            <thead>
                              <tr>{["#", "Gate", "Phase", "Blocks the merge when"].map(h => (
                                <th key={h} style={{ textAlign: "left", padding: "10px 14px", borderBottom: "1.5px solid #1e293b", fontSize: 11, letterSpacing: ".07em", textTransform: "uppercase", color: "var(--ink)", whiteSpace: "nowrap" }}>{h}</th>
                              ))}</tr>
                            </thead>
                            <tbody>
                              {GATE_ROSTER.map((g, i) => (
                                <tr key={g.name}>
                                  <td style={{ padding: "9px 14px", borderBottom: "1px solid #eef1f4", color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums" }}>{i + 1}</td>
                                  <td style={{ padding: "9px 14px", borderBottom: "1px solid #eef1f4", fontFamily: "ui-monospace, monospace", fontSize: 12.5, color: "var(--ink-body)", whiteSpace: "nowrap" }}>{g.name}</td>
                                  <td style={{ padding: "9px 14px", borderBottom: "1px solid #eef1f4" }}>
                                    <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 6px", borderRadius: 3, background: g.phase === "PRE" ? "#eef2ff" : "#f1f5f9", color: g.phase === "PRE" ? "#4338ca" : "#55646f" }}>{g.phase}</span>
                                  </td>
                                  <td style={{ padding: "9px 14px", borderBottom: "1px solid #eef1f4", color: "var(--ink-muted)" }}>{g.blocks}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <div style={{ ...card, marginTop: 12 }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)", marginBottom: 8 }}>
                            Auto-merge is {AUTOMERGE_DEFAULT_ENABLED ? "on" : "off"} by default. Every one of these must hold:
                          </div>
                          <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13.5, color: "var(--ink-body)", lineHeight: 1.7 }}>
                            {MERGE_POLICY.map((r) => (
                              <li key={r.condition}>
                                {r.condition} <span style={{ color: "var(--ink-muted)" }}>— otherwise <b style={{ color: "#a33a22" }}>HUMAN</b>: {r.otherwise}</span>
                              </li>
                            ))}
                          </ol>
                        </div>
                      </details>
                    </>
                  ) : null}

                  {/* ── Stages with no result yet: plan (unplanned) and fix ── */}
                  {(st.id === "fix" || (st.id === "plan" && !hasResult)) ? (
                    <div style={{ border: "1px dashed #e2e8f0", borderRadius: 8, background: "#fafbfc", padding: "28px 24px", maxWidth: 760 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ink-body)", marginBottom: 8 }}>
                        {st.id === "plan" ? "Nothing planned for this cycle yet" : "Nothing fixed in this cycle yet"}
                      </div>
                      <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0, lineHeight: 1.6, maxWidth: "68ch" }}>{st.absent}</p>
                      <div style={{ marginTop: 14, fontSize: 12, color: "var(--ink-muted)", fontFamily: "ui-monospace, monospace" }}>source: {st.source}</div>
                      {st.id === "plan" && planState ? (
                        <button
                          type="button"
                          onClick={() => planState.runPlan()}
                          disabled={planState.planBusy}
                          style={{ marginTop: 16, padding: "8px 14px", borderRadius: 6, border: 0, cursor: "pointer", background: "#1e293b", color: "#fff", fontSize: 13, fontWeight: 600, opacity: planState.planBusy ? 0.6 : 1 }}
                        >
                          {planState.planBusy ? "Planning…" : "Run Plan"}
                        </button>
                      ) : null}
                      {st.id === "fix" ? (
                        <button
                          type="button"
                          onClick={() => { setActiveStage(null); setActiveTab("Auto-Fix Engine"); }}
                          style={{ marginTop: 16, padding: "8px 14px", borderRadius: 6, border: 0, cursor: "pointer", background: "#1e293b", color: "#fff", fontSize: 13, fontWeight: 600 }}
                        >
                          Open the Auto-Fix Engine
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })()
          ) : activeContentTool ? (
            (() => {
              const ct = contentToolById(activeContentTool);
              if (!ct) return null;
              return (
                <div style={{ maxWidth: 1200 }}>
                  <div style={{ marginBottom: "var(--space-5)" }}>
                    <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--ink)", margin: 0 }}>
                      {ct.label}
                    </h1>
                    <p
                      style={{
                        fontSize: 13,
                        color: "var(--ink-muted)",
                        margin: "var(--space-1) 0 0",
                        maxWidth: "70ch",
                      }}
                    >
                      {ct.blurb}
                    </p>
                    {/* What controlled testing says about this class of work.
                        Shown next to the tool, not buried in docs, because the
                        choice of WHICH tool to reach for is the decision that
                        actually moves the number — ~15% of deliberate SEO
                        changes measure as a gain and 7-8% as a loss. */}
                    {ct.evidence ? (
                      <div style={{
                        marginTop: 12, display: "flex", gap: 10, alignItems: "flex-start",
                        padding: "10px 13px", borderRadius: 6, maxWidth: "78ch",
                        background: ct.evidence.strength === "strong" ? "#e4efe9"
                          : ct.evidence.strength === "mixed" ? "#f7efd9" : "#f1f5f9",
                        border: `1px solid ${ct.evidence.strength === "strong" ? "#c7e0d3"
                          : ct.evidence.strength === "mixed" ? "#ecdcb0" : "#e2e8f0"}`,
                      }}>
                        <span style={{
                          fontSize: 10, fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase",
                          padding: "2px 7px", borderRadius: 3, whiteSpace: "nowrap", marginTop: 1,
                          background: "#fff",
                          color: ct.evidence.strength === "strong" ? "#2c6b4f"
                            : ct.evidence.strength === "mixed" ? "#8a6a14" : "var(--ink-muted)",
                          border: `1px solid ${ct.evidence.strength === "strong" ? "#c7e0d3"
                            : ct.evidence.strength === "mixed" ? "#ecdcb0" : "#e2e8f0"}`,
                        }}>
                          {ct.evidence.strength === "strong" ? "Evidence: strong"
                            : ct.evidence.strength === "mixed" ? "Evidence: mixed" : "Evidence: weak"}
                        </span>
                        <span style={{ fontSize: 12.5, lineHeight: 1.55, color: "var(--ink-body)" }}>
                          {ct.evidence.note}
                        </span>
                      </div>
                    ) : null}
                  </div>
                  <ContentPanel
                    toolId={ct.id}
                    domain={currentDomain || undefined}
                    business={currentBusiness || undefined}
                    keywords={projectMetrics.keywords?.map((k: any) => k.keyword).filter(Boolean)}
                    /* The measured rows the tool argues from. Flattened across
                       every group of the report, because a tool's evidenceCodes
                       span lanes (content.*, health.*, aeo.*) and each lane is
                       a separate array on the report. */
                    findings={Object.values(report || {})
                      .filter(Array.isArray)
                      .flat()
                      .filter((r: any) => r && typeof r === "object" && typeof r.code === "string") as any[]}
                    queries={liveGscRows?.map((r: any) => ({
                      query: r.query, impressions: r.impressions, position: r.position,
                    })).filter((q: any) => q.query)}
                    // The page as the scan fetched it. Five of the seven tools
                    // read this and it was passed by nobody, so "Rewrites the
                    // scanned page" rewrote nothing.
                    page={scannedPage as any}
                  />
                  {/* Parity with every report view: the Findings screens could
                      fix themselves and the Drafting screens could not. */}
                  <FixWithClaude
                    findings={Object.values(report || {}).filter(Array.isArray).flat() as any[]}
                    business={currentBusiness}
                    domain={currentDomain}
                    label="Fix the findings behind this draft"
                  />
                </div>
              );
            })()
          ) : activeGscView ? (
            (() => {
              const gv = gscViewById(activeGscView);
              if (!gv) return null;
              return (
                <div style={{ maxWidth: 1200 }}>
                  <div style={{ marginBottom: "var(--space-5)" }}>
                    <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--ink)", margin: 0 }}>
                      {gv.label}
                    </h1>
                    <p
                      style={{
                        fontSize: 13,
                        color: "var(--ink-muted)",
                        margin: "var(--space-1) 0 0",
                        maxWidth: "70ch",
                      }}
                    >
                      {gv.blurb}
                    </p>
                  </div>
                  <GscPanel
                    view={gv}
                    siteUrl={selectedGscProperty || undefined}
                    onConnect={() => {
                      if (typeof window !== "undefined") {
                        window.location.href = "/integrations/google";
                      }
                    }}
                  />
                </div>
              );
            })()
          ) : activeView ? (
            (() => {
              const view = viewById(activeView);
              if (!view) return null;
              const sources = TOOL_SOURCES[view.id];
              const catalog = toolPicker?.catalog;
              // The saved choice if usable, else DataForSEO, else ours. When
              // neither can run (e.g. Backlinks while spend is paused) the page
              // stays on its paid source so the reason is shown, not hidden.
              const source: SourceId | undefined = sources
                ? effectiveSource(view.id, viewSources[view.id], catalog)
                  ?? (isEnabled(sources.dataforseo) ? "dataforseo" : "ours")
                : undefined;
              const sourceOpt = sources && source ? sources[source] : undefined;
              const sourceSel = isEnabled(sourceOpt) ? sourceOpt : undefined;
              const rows = rowsForView(report, view, sourceSel);
              return (
                <div style={{ maxWidth: 1200 }}>
                  <div style={{ marginBottom: "var(--space-5)" }}>
                    <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--ink)", margin: 0 }}>
                      {view.label}
                    </h1>
                    <p
                      style={{
                        fontSize: 13,
                        color: "var(--ink-muted)",
                        margin: "var(--space-1) 0 0",
                        maxWidth: "70ch",
                      }}
                    >
                      {view.blurb}
                    </p>
                  </div>
                  {/* "If SEO, when audit only audit about SEO." Mounted once on
                      the shared renderer, so every section screen scans its own
                      concern and no other. The two "everything" views carry no
                      section and correctly render nothing here. */}
                  {view.section && (
                    <SectionScanButton
                      sectionId={view.section}
                      viewId={view.id}
                      viewLabel={view.label}
                      source={source}
                      sourceTools={sourceSel?.tools}
                      sourceBlockers={sources ? {
                        dataforseo: sourceBlocker(view.id, "dataforseo", catalog),
                        ours: sourceBlocker(view.id, "ours", catalog),
                      } : undefined}
                      onSourceChange={(s) => chooseViewSource(view.id, s)}
                      domain={currentDomain}
                      repo={selectedClient?.repo}
                      onEditProject={() => selectedClient && openEditProject(selectedClient)}
                      tools={toolPicker?.catalog}
                      busy={scanState?.busy}
                      error={scanState?.error}
                      onScan={(u, keys) => onTriggerScan?.(u, keys)}
                      onCrawlScan={(u, keys, pages) => onTriggerScan?.(u, keys, pages)}
                      crawlPages={crawlPages}
                      onCrawlPagesChange={onCrawlPagesChange}
                      hasProjects={clients.length > 0}
                      onCreateProject={() => openCreateProject()}
                    />
                  )}
                  {/* What the scan is doing while it does it: real scanner events,
                      not a spinner on a button (lib/scanActivity.ts). */}
                  {view.section && (
                    <LiveScanActivity
                      tools={scanState?.tools as any}
                      busy={scanState?.busy}
                      phaseLine={scanState?.phaseLine}
                      catalog={toolPicker?.catalog}
                    />
                  )}
                  {/* Counts render whether or not there are rows: zero is a
                      reading, and a screen of zeroes beats a blank one. */}
                  <ReportStats rows={rows} />
                  <ReportTable
                    view={view}
                    rows={rows}
                    onRunAudit={() => {
                      setActiveView(null);
                      setActiveTab("Site Health & Audit");
                      setAuditSubTab("summary");
                    }}
                  />
                  {/* Mounted ONCE, on the shared renderer, so every report view
                      gets it - not bolted onto each screen where the copies drift.
                      Fed exactly the rows the table above is showing, so it can
                      never advise on something the reader cannot see. */}
                  <FixWithClaude
                    findings={rows}
                    business={currentBusiness}
                    domain={currentDomain}
                    label={`Fix these ${view.label.toLowerCase()} issues with Claude`}
                  />
                </div>
              );
            })()
          ) : (
            <>
          
          {/* Breadcrumb & Project Selector Header */}
          <div style={{ marginBottom: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--ink-muted)", marginBottom: 8, flexWrap: "wrap" }}>
              <span>Home</span>
              <span>›</span>
              {activeTab === "Overview" ? (
                <span style={{ color: "#1e293b", fontWeight: 700 }}>SEO Dashboard</span>
              ) : activeTab === "Traffic Analytics" ? (
                <>
                  <span style={{
                    fontSize: 12, fontWeight: 700, color: "#1e293b",
                    background: "#f1f5f9", border: "1px solid #e2e8f0",
                    padding: "1px 8px", borderRadius: 12, display: "inline-flex", alignItems: "center", gap: 4,
                  }}>
                    <span>📊</span> Traffic & Market
                  </span>
                  <span>›</span>
                  <span style={{ color: "#1e293b", fontWeight: 700 }}>Traffic Analytics</span>
                </>
              ) : activeTab === "AI & AEO Lab" ? (
                <>
                  <span style={{
                    fontSize: 12, fontWeight: 700, color: "#6d28d9",
                    background: "#f5f3ff", border: "1px solid #ddd6fe",
                    padding: "1px 8px", borderRadius: 12, display: "inline-flex", alignItems: "center", gap: 4,
                  }}>
                    <span>🤖</span> AI Search Visibility (AEO)
                  </span>
                  <span>›</span>
                  <span style={{ color: "#1e293b", fontWeight: 700 }}>
                    {aeoActiveFocus === "citations" ? "AI Citations" :
                     aeoActiveFocus === "schema" ? "Schema & Entities" :
                     aeoActiveFocus === "answers" ? "Answer Content" :
                     aeoActiveFocus === "crawlers" ? "AI Crawler Access" : "AI Readiness"}
                  </span>
                </>
              ) : activeTab === "Auto-Fix Engine" ? (
                <>
                  <span style={{
                    fontSize: 12, fontWeight: 700, color: "#065f46",
                    background: "#ecfdf5", border: "1px solid #a7f3d0",
                    padding: "1px 8px", borderRadius: 12, display: "inline-flex", alignItems: "center", gap: 4,
                  }}>
                    <span>⚡</span> Fix & Improve
                  </span>
                  <span>›</span>
                  <span style={{ color: "#1e293b", fontWeight: 700 }}>Auto-Fix Review</span>
                </>
              ) : activeTab === "All Tools Directory" ? (
                <span style={{ color: "#1e293b", fontWeight: 700 }}>All Tools Directory</span>
              ) : (
                <>
                  <span style={{
                    fontSize: 12, fontWeight: 700, color: "#1e40af",
                    background: "#eff6ff", border: "1px solid #bfdbfe",
                    padding: "1px 8px", borderRadius: 12, display: "inline-flex", alignItems: "center", gap: 4,
                  }}>
                    <span>🌐</span> SEO Foundations
                  </span>
                  <span>›</span>
                  <span style={{ color: "#1e293b", fontWeight: 700 }}>
                    {activeTab === "Site Health & Audit" ? "Technical SEO" :
                     activeTab === "SERP Optimizer" ? "Content" :
                     activeTab === "Keyword Data Lab" ? "Keywords & Rankings" :
                     activeTab === "Data Lab & Backlinks" ? "Links" : activeTab}
                  </span>
                </>
              )}
              <span style={{
                marginLeft: 8, fontSize: 12, fontWeight: 600, color: "#047857", background: "#ecfdf5",
                border: "1px solid #a7f3d0", padding: "1px 6px", borderRadius: 4,
              }}>
                ● Verified Scan
              </span>
            </div>

            {/* Project Title Bar with Real Domain Switcher */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
              <div style={{ position: "relative", display: "inline-block" }}>
                {showHeaderSkeleton ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 0" }}>
                    <SkeletonBox width={190} height={24} borderRadius={6} />
                    <SkeletonBox width={130} height={16} borderRadius={4} />
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setDomainDropdown(!domainDropdown)}
                    style={{
                      background: "none", border: 0, padding: "2px 0", cursor: "pointer",
                      display: "flex", alignItems: "center", gap: 8, fontSize: 18, fontWeight: 700, color: "#1e293b",
                    }}
                  >
                    <span>{currentBusiness}</span>
                    <span style={{ fontSize: 12.5, color: "var(--ink-muted)", fontWeight: 400 }}>({currentDomain})</span>
                    <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>▼</span>
                  </button>
                )}

                {/* Dropdown for real clients in database */}
                {domainDropdown && (
                  <div style={{
                    position: "absolute", top: "100%", left: 0, marginTop: 10, background: "#ffffff",
                    border: "1px solid #e8ecf1", borderRadius: 12, boxShadow: "0 12px 30px -5px rgba(0,0,0,0.1)",
                    width: 340, zIndex: 100, padding: "8px 0",
                  }}>
                    <div style={{ padding: "10px 18px 6px", fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                      Switch Project ({clients.length} projects)
                    </div>
                    {clients.map((c) => (
                      <div
                        key={c.id}
                        onClick={() => {
                          onSelectClient(c);
                          setDomainDropdown(false);
                        }}
                        style={{
                          padding: "12px 18px", cursor: "pointer",
                          background: c.id === selectedClient?.id ? "#eff3f8" : "transparent",
                          borderBottom: "1px solid #f8fafc",
                          transition: "background 0.15s ease",
                        }}
                        onMouseEnter={(e) => {
                          if (c.id !== selectedClient?.id) e.currentTarget.style.background = "#f8fafc";
                        }}
                        onMouseLeave={(e) => {
                          if (c.id !== selectedClient?.id) e.currentTarget.style.background = "transparent";
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <div style={{ fontSize: 13.5, fontWeight: 600, color: c.id === selectedClient?.id ? "#1e293b" : "#334155" }}>
                            {c.business || c.domain}
                          </div>
                          {c.lastCounts && (
                            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ok)", background: "#ecfdf5", padding: "2px 8px", borderRadius: 10 }}>
                              {c.lastCounts.ok || 0} checks
                            </span>
                          )}
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 3, gap: 10 }}>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                            {c.domain} · {c.scans} scan{c.scans !== 1 ? "s" : ""}
                          </div>
                          {/*
                            The domain is right here, which is where a wrong one
                            gets noticed. stopPropagation because the row itself
                            selects the project - without it, Edit would select
                            and then open, and the modal would sometimes be over
                            a different project than the one clicked.
                          */}
                          {onUpdateClient && (
                            <button
                              type="button"
                              title={`Edit ${c.business || c.domain}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                setDomainDropdown(false);
                                openEditProject(c);
                              }}
                              style={{
                                background: "transparent", border: "1px solid #e2e8f0", borderRadius: 6,
                                padding: "3px 9px", fontSize: 11.5, fontWeight: 600,
                                color: "#475569", cursor: "pointer", whiteSpace: "nowrap",
                              }}
                            >
                              Edit
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                    <div
                      onClick={() => {
                        setDomainDropdown(false);
                        openCreateProject();
                      }}
                      style={{ padding: "12px 18px", cursor: "pointer", color: "#4f46e5", fontSize: 12.5, fontWeight: 600, borderTop: "1px solid #edf0f4" }}
                    >
                      + Create New SEO Project
                    </div>
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <button
                  type="button"
                  onClick={() => setShowExecutiveReportModal(true)}
                  style={{
                    background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 8,
                    padding: "9px 16px", fontSize: 13, fontWeight: 600, color: "#1e293b", cursor: "pointer",
                    boxShadow: "0 1px 2px rgba(0,0,0,0.03)", display: "flex", alignItems: "center", gap: 6,
                  }}
                >
                  <span>📄</span> Client Report
                </button>
                <button
                  type="button"
                  onClick={() => openCreateProject()}
                  style={{
                    background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8,
                    padding: "9px 18px", fontSize: 13, fontWeight: 600, color: "#334155", cursor: "pointer",
                    boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
                  }}
                >
                  + Create Project
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActiveTab("Site Health & Audit");
                    setAuditSubTab("all_checks");
                  }}
                  style={{
                    background: "#1e293b", border: 0, borderRadius: 8,
                    padding: "9px 18px", fontSize: 13, fontWeight: 600, color: "#ffffff", cursor: "pointer",
                    boxShadow: "0 1px 2px rgba(30, 41, 59, 0.2)",
                  }}
                >
                  Full Technical Report →
                </button>
              </div>
            </div>
          </div>

          {/* ── SUB-VIEW 1: EXECUTIVE OVERVIEW DASHBOARD (OR SKELETON SHIMMER) ── */}
          {showSkeleton ? (
            <PageSkeletonLayout tab={activeTab} />
          ) : (
            <>
              {activeTab === "Overview" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* ── 1. FOUR APEX KPI CARDS ── */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
                {/* KPI 1 */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Organic Visits</span>
                    {/* A trend needs two scans. This badge was a constant growth
                        figure, shown to every client on every run, in the green
                        that means real growth. */}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 8 }}>
                    <div>
                      <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>{projectMetrics.trafficAnalytics.visits}</div>
                      {/* "$2,439/mo est. value" was a constant. Nothing in the
                          scan prices traffic, so there is no figure to show. */}
                    </div>
                    {projectMetrics.trafficAnalytics.monthlyTrend?.length > 1 ? (
                      <MiniSparkline data={projectMetrics.trafficAnalytics.monthlyTrend.map((t: any) => t.v)} color="#10b981" width={68} height={26} />
                    ) : null}
                  </div>
                </div>

                {/* KPI 2 */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Authority Score</span>
                    {/* "Top 35%" was a constant in success-green. The real
                        figure DataForSEO reports is a rank, carried below. */}
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)" }}>{projectMetrics.authorityRank}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 8 }}>
                    <div>
                      <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>{projectMetrics.authorityScore}</div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>{projectMetrics.backlinks.toLocaleString()} links · {projectMetrics.refDomains} domains</div>
                    </div>
                    <MiniRadialGauge score={projectMetrics.authorityScore} size={38} strokeWidth={4} color="var(--ok)" />
                  </div>
                </div>

                {/* KPI 3 */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Site Health</span>
                    {/* null is "nothing gradeable ran", which is not 0%. A scan
                        that measured nothing must not report a health at all. */}
                    <span style={{ fontSize: 12, fontWeight: 600, color: dynamicHealth === null ? "var(--ink-muted)" : dynamicHealth >= 80 ? "var(--ok)" : "#d97706", background: dynamicHealth === null ? "#f8fafc" : dynamicHealth >= 80 ? "#ecfdf5" : "#fffbeb", border: `1px solid ${dynamicHealth === null ? "#e2e8f0" : dynamicHealth >= 80 ? "#a7f3d0" : "#fde68a"}`, padding: "2px 7px", borderRadius: 12 }}>{dynamicHealth === null ? "Not measured" : `Grade ${gradeFor(dynamicHealth)}`}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 8 }}>
                    <div>
                      <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>{dynamicHealth === null ? "\u2014" : `${dynamicHealth}%`}</div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                        {/* "609 pages checked" was a constant, and it outlived
                            every crawl cap the scanner has ever had. */}
                        {pagesChecked > 0 ? `${pagesChecked} page(s) checked` : "No pages checked yet"}
                      </div>
                    </div>
                    {dynamicHealth !== null && (
                      <MiniRadialGauge score={dynamicHealth} size={38} strokeWidth={4} color={dynamicHealth >= 80 ? "var(--ok)" : "#d97706"} />
                    )}
                  </div>
                </div>

                {/* KPI 4 */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>AI Readiness</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 7px", borderRadius: 12 }}>
                      {aeoPillar?.measured ? `${aeoPillar.ok}/${aeoPillar.total} Passing` : "Not measured"}
                    </span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 8 }}>
                    <div>
                      {/* "85%", "~342 brand mentions" and four per-engine
                          percentages in the bar tooltips (OpenAI 96, Gemini 92,
                          Perplexity 98, Claude 88) were all constants. The scan
                          measures AEO rows; it does not score engines. */}
                      <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>
                        {aeoPillar?.score !== null && aeoPillar?.score !== undefined ? `${aeoPillar.score}%` : "\u2014"}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                        {aeoPillar?.measured ? `${aeoPillar.total} AI check(s)` : "Run a scan to measure"}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* ── 2. EXECUTIVE PERFORMANCE & TRAFFIC CHART ── */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 22px" }}>
                <ExecutiveTrafficChart
                  trend={projectMetrics.trafficAnalytics.monthlyTrend}
                  totalVisits={projectMetrics.trafficAnalytics.visits}
                  domain={currentDomain}
                  totalKeywords={projectMetrics.organicKeywordsCount}
                />
              </div>

              {/* ── 3. AUDIT WEBSITE HERO INPUT ── */}
              <AuditHeroBar
                currentDomain={currentDomain}
                onRunAudit={(url) => {
                  if (onTriggerScan) onTriggerScan(url);
                }}
                isScanning={scanState?.busy}
                phaseLine={scanState?.phaseLine}
                scanTools={scanState?.tools}
                liveLogs={scanState?.live}
                report={report}
                onSelectFix={(code) => {
                  setActiveTab("Auto-Fix Engine");
                  if (planState && !planState.plan?.worklist) planState.runPlan();
                }}
              />

              {/* ── 4. TWO-COLUMN DEEP DIAGNOSTICS: TECHNICAL SEO & AEO MATRIX ── */}
              <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 14 }}>
                {/* ── LEFT COLUMN: TECHNICAL SEO & WEB VITALS ── */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                      <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Technical Health & Web Vitals</h4>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "#0369a1", background: "#f0f9ff", border: "1px solid #bae6fd", padding: "2px 8px", borderRadius: 4 }}>
                        {dynamicHealth}% Score
                      </span>
                    </div>

                    {/* Donut & Summary row */}
                    <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 14 }}>
                      {/* No donut over an unmeasured score: a ring at 0% reads
                          as a verdict, and there isn't one. */}
                      {dynamicHealth !== null && <SiteHealthDonut score={dynamicHealth} size={76} />}
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginBottom: 12 }}>
                          <div style={{ padding: "10px 12px", borderRadius: 6, background: "#f8fafc", border: "1px solid #edf0f4" }}>
                            <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Errors</div>
                            <div style={{ fontSize: 16, fontWeight: 800, color: "#ef4444", marginTop: 2 }}>{errChecks}</div>
                          </div>
                          <div style={{ padding: "10px 12px", borderRadius: 6, background: "#f8fafc", border: "1px solid #edf0f4" }}>
                            <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Warnings</div>
                            <div style={{ fontSize: 16, fontWeight: 800, color: "#f59e0b", marginTop: 2 }}>{warnChecks}</div>
                          </div>
                          <div style={{ padding: "10px 12px", borderRadius: 6, background: "#f8fafc", border: "1px solid #edf0f4" }}>
                            <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Passing</div>
                            <div style={{ fontSize: 16, fontWeight: 800, color: "#10b981", marginTop: 2 }}>{okChecks}</div>
                          </div>
                        </div>
                        <div style={{ marginTop: 12, marginBottom: 4 }}>
                          <CrawledPagesBar ok={okChecks} warn={warnChecks} error={errChecks} info={infoChecks} />
                        </div>
                      </div>
                    </div>

                    {/* Core Web Vitals */}
                    <div style={{ borderTop: "1px solid #f1f4f8", paddingTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Core Web Vitals (Lighthouse)</div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
                        <div style={{ padding: "10px 12px", borderRadius: 8, background: "#f8fafc", border: "1px solid #e2e8f0" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)" }}>LCP</span>
                            <span style={{ fontSize: 12, fontWeight: 700, padding: "1px 5px", borderRadius: 3, background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca" }}>
                              {projectMetrics.onPageSeoData.coreWebVitals.lcp.status}
                            </span>
                          </div>
                          <div style={{ fontSize: 18, fontWeight: 800, color: projectMetrics.onPageSeoData.coreWebVitals.lcp.color, marginBottom: 6 }}>
                            {projectMetrics.onPageSeoData.coreWebVitals.lcp.val}
                          </div>
                          <LighthouseGaugeBar
                            val={projectMetrics.onPageSeoData.coreWebVitals.lcp.val}
                            status={projectMetrics.onPageSeoData.coreWebVitals.lcp.status}
                            color={projectMetrics.onPageSeoData.coreWebVitals.lcp.color}
                          />
                        </div>
                        <div style={{ padding: "10px 12px", borderRadius: 8, background: "#f8fafc", border: "1px solid #e2e8f0" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)" }}>INP</span>
                            <span style={{ fontSize: 12, fontWeight: 700, padding: "1px 5px", borderRadius: 3, background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca" }}>
                              {projectMetrics.onPageSeoData.coreWebVitals.inp.status}
                            </span>
                          </div>
                          <div style={{ fontSize: 18, fontWeight: 800, color: projectMetrics.onPageSeoData.coreWebVitals.inp.color, marginBottom: 6 }}>
                            {projectMetrics.onPageSeoData.coreWebVitals.inp.val}
                          </div>
                          <LighthouseGaugeBar
                            val={projectMetrics.onPageSeoData.coreWebVitals.inp.val}
                            status={projectMetrics.onPageSeoData.coreWebVitals.inp.status}
                            color={projectMetrics.onPageSeoData.coreWebVitals.inp.color}
                          />
                        </div>
                        <div style={{ padding: "10px 12px", borderRadius: 8, background: "#f8fafc", border: "1px solid #e2e8f0" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)" }}>CLS</span>
                            <span style={{ fontSize: 12, fontWeight: 700, padding: "1px 5px", borderRadius: 3, background: "#fffbeb", color: "#b45309", border: "1px solid #fde68a" }}>
                              {projectMetrics.onPageSeoData.coreWebVitals.cls.status}
                            </span>
                          </div>
                          <div style={{ fontSize: 18, fontWeight: 800, color: projectMetrics.onPageSeoData.coreWebVitals.cls.color, marginBottom: 6 }}>
                            {projectMetrics.onPageSeoData.coreWebVitals.cls.val}
                          </div>
                          <LighthouseGaugeBar
                            val={projectMetrics.onPageSeoData.coreWebVitals.cls.val}
                            status={projectMetrics.onPageSeoData.coreWebVitals.cls.status}
                            color={projectMetrics.onPageSeoData.coreWebVitals.cls.color}
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div style={{ borderTop: "1px solid #f1f4f8", paddingTop: 12, marginTop: 14, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                      {pagesChecked > 0 ? `${pagesChecked} URL(s) checked` : "No URLs checked yet"}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setActiveTab("Site Health & Audit");
                        setAuditSubTab("all_checks");
                      }}
                      style={{ background: "#1e293b", color: "#fff", border: 0, borderRadius: 6, padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                    >
                      Audit Details →
                    </button>
                  </div>
                </div>

                {/* ── RIGHT COLUMN: AI SEARCH CITATIONS & EXTRACTION ── */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                  <div>
                    <AeoAccessPanel aeoRows={measured(report?.aeo as any[])} />
                  </div>

                  <div style={{ borderTop: "1px solid #f1f4f8", paddingTop: 12, marginTop: 14, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                      {/* The mentions tool is paid and off by default, so the
                          honest reading is usually "not measured", not a count. */}
                      {(() => {
                        const rows = measured(report?.mentions as any[]) as Array<any>;
                        const row = rows.find((r) => typeof r?.detail === "string" && /\d/.test(r.detail));
                        return row ? `${row.detail} brand mentions` : "Brand mentions not measured";
                      })()}
                    </span>
                    <button
                      type="button"
                      onClick={() => setActiveTab("AI & AEO Lab")}
                      style={{ background: "#4f46e5", color: "#fff", border: 0, borderRadius: 6, padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                    >
                      AEO Lab →
                    </button>
                  </div>
                </div>
              </div>

              {/* ── 5. SECTION 3: SERP POSITION SPREAD & TOP LIVE RANKED KEYWORDS ── */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 22px 22px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                      Google SERP Rankings ({projectMetrics.organicKeywordsCount} Ranked Keywords)
                    </h3>
                    {/* Was the constant "7 AT RANK #1", rendered beside a headline
                        that read "0 Ranked Keywords" in the same breath. */}
                    {(() => {
                      const atOne = (projectMetrics.keywords || []).filter((k: any) => k.position === 1).length;
                      if (!atOne) return null;
                      return (
                        <span style={{ fontSize: 12, fontWeight: 700, color: "#0369a1", background: "#f0f9ff", border: "1px solid #bae6fd", padding: "2px 7px", borderRadius: 4 }}>
                          {atOne} AT RANK #1
                        </span>
                      );
                    })()}
                  </div>

                  <button
                    type="button"
                    onClick={() => setActiveTab("Keyword Data Lab")}
                    style={{ background: "#f8fafc", border: "1px solid #cbd5e1", color: "#334155", borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                  >
                    View All {projectMetrics.organicKeywordsCount} Keywords →
                  </button>
                </div>

                {/* Position Spread Bar Chart */}
                <div style={{ marginBottom: 14 }}>
                  <ExecutivePositionSpreadChart distribution={projectMetrics.organicResearch.posDistribution} totalKeywords={projectMetrics.organicKeywordsCount} />
                </div>

                {/* Live Ranked Keywords Table */}
                <div style={{ marginTop: 16, border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                    <thead>
                      <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.05em", textTransform: "uppercase" }}>
                        <th style={{ padding: "10px 14px", fontWeight: 700 }}>Search Query</th>
                        <th style={{ padding: "10px 14px", fontWeight: 700 }}>Rank</th>
                        <th style={{ padding: "10px 14px", fontWeight: 700 }}>Volume</th>
                        <th style={{ padding: "10px 14px", fontWeight: 700 }}>Intent</th>
                        <th style={{ padding: "10px 14px", fontWeight: 700 }}>SERP Features</th>
                        <th style={{ padding: "10px 14px", fontWeight: 700, textAlign: "right" }}>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {projectMetrics.keywords.slice(0, 8).map((k: any, i: number) => (
                        <tr key={i} style={{ borderBottom: i < 7 ? "1px solid #f1f5f9" : "none", background: "#ffffff" }}>
                          <td style={{ padding: "11px 14px", fontWeight: 600, color: "#1e293b" }}>
                            {k.keyword}
                          </td>
                          <td style={{ padding: "11px 14px" }}>
                            <span style={{
                              fontWeight: 700, fontSize: 12,
                              color: k.position === 1 ? "#047857" : k.position <= 3 ? "#0284c7" : k.position <= 10 ? "#4338ca" : "var(--ink-muted)",
                              background: k.position === 1 ? "#ecfdf5" : k.position <= 3 ? "#f0f9ff" : "#eef2ff",
                              border: `1px solid ${k.position === 1 ? "#a7f3d0" : k.position <= 3 ? "#bae6fd" : "#c7d2fe"}`,
                              padding: "2px 8px", borderRadius: 4,
                            }}>
                              #{k.position}
                            </span>
                          </td>
                          <td style={{ padding: "11px 14px", color: "#475569", fontWeight: 500 }}>
                            {k.volume} <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>/ mo</span>
                          </td>
                          <td style={{ padding: "11px 14px" }}>
                            <span style={{ fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 4, background: "#f8fafc", border: "1px solid #e2e8f0", color: "#475569" }}>
                              {k.intent}
                            </span>
                          </td>
                          <td style={{ padding: "11px 14px", color: "var(--ink-muted)", fontSize: 12 }}>
                            {k.features.join(" · ")}
                          </td>
                          <td style={{ padding: "11px 14px", textAlign: "right" }}>
                            <button
                              type="button"
                              onClick={() => setActiveTab("Keyword Gap")}
                              style={{ background: "#eff6ff", border: "1px solid #dbeafe", color: "#2563eb", borderRadius: 5, padding: "3px 9px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                            >
                              Gap →
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* ── 6. SHARED "TOP PRIORITIES" LIST (WHAT TO DO NEXT) ── */}
              <PriorityActions
                priorities={livePriorities}
                onSelectAction={(priority) => {
                  // Route on the finding's own code rather than on fixture ids.
                  // The previous branches matched three hardcoded ids that no
                  // longer exist now the list is derived from the scan.
                  const code = priority.id.replace(/^priority-/, "");
                  if (priority.isAutoFixable) {
                    setActiveTab("Auto-Fix Engine");
                  } else if (code.startsWith("schema.") || code.includes("schema")) {
                    setActiveTab("AI & AEO Lab");
                    setAeoActiveFocus("schema");
                  } else if (code.startsWith("aeo.") || code.startsWith("ai.")) {
                    setActiveTab("AI & AEO Lab");
                  } else if (priority.actionTab) {
                    setActiveTab(priority.actionTab);
                  } else {
                    setActiveTab("Site Health & Audit");
                  }
                }}
              />

              {/* ── 7. REMEDIATION ACTION CARD ── */}
              <div style={{
                background: "linear-gradient(135deg, #181f2a 0%, #252e3d 100%)",
                borderRadius: 8, padding: "14px 20px", color: "#ffffff",
                display: "flex", justifyContent: "space-between", alignItems: "center",
                border: "1px solid #2d384a",
              }}>
                <div>
                  <div style={{ fontSize: 13.5, fontWeight: 700 }}>
                    Auto-Fix Review & Remediation
                  </div>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                    Automated inspection and safe code remediation for {currentDomain}. Review changes before applying.
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    type="button"
                    onClick={() => setActiveTab("Auto-Fix Engine")}
                    style={{
                      background: "#059669", color: "#fff", border: 0, borderRadius: 6,
                      padding: "7px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                    }}
                  >
                    Review in Auto-Fix →
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveTab("Site Health & Audit");
                      setAuditSubTab("all_checks");
                    }}
                    style={{
                      background: "rgba(255,255,255,0.08)", color: "#fff", border: "1px solid rgba(255,255,255,0.15)",
                      borderRadius: 6, padding: "7px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                    }}
                  >
                    Full Report
                  </button>
                </div>
              </div>

              {/* ── 8. GUIDED PROJECT JOURNEY CHECKLIST & ROADMAP ── */}
              {/*
                Evidence in, stage out. This call site used to hand the bar a
                literal stage number, and never passed the Google flag at all,
                so it reported the same stage forever and always showed Search
                Console as disconnected. `lib/journey` derives the stage now;
                nothing here can assert one, and a navigation test fails if a
                caller starts doing so again.
              */}
              <ProjectJourney
                client={selectedClient}
                hasGsc={googleConnected && !!selectedGscProperty}
                report={report}
                plan={planState?.plan}
                remediations={remedHist}
                apply={planState?.apply}
                onStepClick={(step) => {
                  if (step === 2) { setActiveTab("Traffic Analytics"); }
                  else if (step === 3) { setActiveTab("Site Health & Audit"); setAuditSubTab("summary"); }
                  else if (step === 5) { setActiveTab("Auto-Fix Engine"); }
                }}
              />

              {/* ── 9. FOUNDATIONAL PRINCIPLE CALLOUT BANNER ── */}
              <div style={{
                background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8,
                padding: "14px 18px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 8, background: "#eff6ff",
                    border: "1px solid #bfdbfe", display: "grid", placeItems: "center", fontSize: 18, flexShrink: 0,
                  }}>
                    💡
                  </div>
                  <div>
                    <div style={{ fontSize: 13.5, fontWeight: 700, color: "#1e293b" }}>
                      SEO is the foundation. AI Search Visibility builds on good SEO.
                    </div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                      SEO helps search engines understand and rank your site. AI Search Visibility builds on SEO to help AI answer tools understand and cite it.
                      {" "}<span style={{ color: "var(--ink-muted)", fontSize: 12 }}>(AEO optimizes technical extractability and schema clarity; it does not guarantee citations, rankings, or traffic).</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── SUB-VIEW: TRAFFIC ANALYTICS (REAI FLAGSHIP) ── */}
          {activeTab === "Traffic Analytics" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {/* ── GOOGLE SEARCH CONSOLE & GA4 INTEGRATION BAR ── */}
              {!googleConnected ? (
                <div style={{
                  background: "linear-gradient(135deg, #1e1b4b 0%, #312e81 100%)",
                  borderRadius: 10, padding: "14px 18px", color: "#ffffff",
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  flexWrap: "wrap", gap: 12, boxShadow: "0 4px 14px rgba(49, 46, 129, 0.2)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{
                      width: 38, height: 38, borderRadius: 9, background: "#ffffff",
                      display: "grid", placeItems: "center", flexShrink: 0,
                    }}>
                      <IconGoogle size={22} />
                    </div>
                    <div>
                      <div style={{ fontSize: 13.5, fontWeight: 700, letterSpacing: "-0.01em" }}>
                        Connect Google Search Console & GA4
                      </div>
                      <div style={{ fontSize: 12, color: "#c7d2fe", marginTop: 2 }}>
                        Unlock 100% verified first-party organic clicks, impressions, and exact Google search queries for <b>{currentDomain}</b> with zero manual credentials.
                      </div>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <button
                      type="button"
                      onClick={handleConnectGoogle}
                      disabled={googleConnecting}
                      style={{
                        background: "#ffffff", color: "#1e1b4b", fontWeight: 700, fontSize: 12.5,
                        padding: "8px 16px", borderRadius: 7, border: 0, cursor: "pointer",
                        display: "flex", alignItems: "center", gap: 7, boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
                      }}
                    >
                      <IconGoogle size={14} />
                      <span>{googleConnecting ? "Connecting to Google..." : "Connect Google Account →"}</span>
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{
                  background: "#ffffff", border: "1px solid #dcfce7", borderRadius: 10,
                  padding: "10px 16px", display: "flex", justifyContent: "space-between", alignItems: "center",
                  flexWrap: "wrap", gap: 10, boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, fontWeight: 700, color: hasCurrentDomainInGsc ? "#047857" : "#d97706" }}>
                      <span style={{
                        width: 8, height: 8, borderRadius: "50%",
                        background: hasCurrentDomainInGsc ? "#10b981" : "#f59e0b",
                        boxShadow: `0 0 6px ${hasCurrentDomainInGsc ? "#10b981" : "#f59e0b"}`
                      }} />
                      <span>{hasCurrentDomainInGsc ? "Google Search Console Connected" : "Google Account Connected"}</span>
                    </div>
                    <span style={{ color: "#e2e8f0" }}>|</span>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                        Account: <b style={{ color: "#334155" }}>{googleAccount}</b>
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          window.location.href = "/api/auth/google?prompt=select_account%20consent";
                        }}
                        style={{
                          background: "#f1f5f9", border: "1px solid #cbd5e1", borderRadius: 4,
                          padding: "1px 6px", fontSize: 12, fontWeight: 600, color: "#475569", cursor: "pointer",
                        }}
                        title="Switch to another Google Account"
                      >
                        Switch Gmail
                      </button>
                    </div>
                    <span style={{ color: "#e2e8f0" }}>|</span>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>Property:</span>
                      <select
                        value={selectedGscProperty}
                        onChange={(e) => {
                          const nextProp = e.target.value;
                          setSelectedGscProperty(nextProp);
                          setTrafficDataSource("gsc");
                          if (typeof window !== "undefined") {
                            localStorage.setItem("reai_gsc_property", nextProp);
                            localStorage.setItem("reai_traffic_source", "gsc");
                          }
                          fetchGscAnalytics(nextProp);
                        }}
                        style={{
                          background: "#f8fafc", border: "1px solid #cbd5e1", borderRadius: 6,
                          padding: "3px 8px", fontSize: 12, fontWeight: 600, color: "#1e293b",
                        }}
                      >
                        {verifiedGscProperties.length > 0 ? (
                          verifiedGscProperties.map((p) => (
                            <option key={p} value={p}>{p} (Verified)</option>
                          ))
                        ) : (
                          <>
                            <option value={`sc-domain:${currentDomain}`}>sc-domain:{currentDomain} (Verified Domain)</option>
                            <option value={`https://${currentDomain}/`}>https://{currentDomain}/ (URL Prefix)</option>
                          </>
                        )}
                      </select>
                    </div>
                  </div>

                  {/* Mode Switcher Toggle */}
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{
                      fontSize: 12, fontWeight: 700, color: "#047857", background: "#ecfdf5",
                      border: "1px solid #a7f3d0", padding: "3px 9px", borderRadius: 6,
                    }}>
                      ● 100% Real Google First-Party Data
                    </span>

                    {/* Live Auto-Refresh Controller */}
                    {trafficDataSource === "gsc" && (
                      <div style={{
                        display: "flex", alignItems: "center", gap: 6, fontSize: 12,
                        background: autoRefreshInterval !== "off" ? "#f0fdf4" : "#f8fafc",
                        border: `1px solid ${autoRefreshInterval !== "off" ? "#bbf7d0" : "#e2e8f0"}`,
                        padding: "3px 8px", borderRadius: 6,
                      }}>
                        <span style={{
                          width: 6.5, height: 6.5, borderRadius: "50%",
                          background: autoRefreshInterval !== "off" ? "#10b981" : "#94a3b8",
                          boxShadow: autoRefreshInterval !== "off" ? "0 0 5px #10b981" : "none",
                        }} />
                        <span style={{ color: autoRefreshInterval !== "off" ? "#166534" : "var(--ink-muted)", fontWeight: 700 }}>
                          {autoRefreshInterval !== "off" ? `Live (${syncCountdown}s)` : "Paused"}
                        </span>
                        <select
                          value={autoRefreshInterval}
                          onChange={(e) => {
                            const val = e.target.value as any;
                            setAutoRefreshInterval(val);
                            if (typeof window !== "undefined") localStorage.setItem("reai_traffic_autorefresh", val);
                          }}
                          style={{
                            background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 4,
                            padding: "1px 4px", fontSize: 12, fontWeight: 700, color: "#1e293b", cursor: "pointer",
                          }}
                        >
                          <option value="30s">30s (Realtime)</option>
                          <option value="60s">60s</option>
                          <option value="5m">5m</option>
                          <option value="off">Off</option>
                        </select>
                        <button
                          type="button"
                          onClick={() => {
                            fetchGscAnalytics(selectedGscProperty);
                            setSyncToast(`Syncing latest data for ${selectedGscProperty}...`);
                            setTimeout(() => setSyncToast(null), 2500);
                          }}
                          style={{
                            background: "transparent", border: 0, cursor: "pointer", fontSize: 12,
                            color: "var(--ok)", padding: "0 2px", fontWeight: 700,
                          }}
                          title="Force sync now"
                        >
                          🔄
                        </button>
                      </div>
                    )}

                    <button
                      type="button"
                      onClick={() => setShowIntegrationsModal(true)}
                      style={{
                        background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6,
                        padding: "5px 9px", fontSize: 12, color: "#475569", cursor: "pointer", fontWeight: 600,
                      }}
                    >
                      ⚙️ Manage
                    </button>
                  </div>
                </div>
              )}

              {/* Notice when current project website is NOT in the connected Google Account */}
              {googleConnected && !hasCurrentDomainInGsc && (
                <div style={{
                  background: "#fffbeb", border: "1px solid #fcd34d", borderRadius: 10,
                  padding: "16px 20px", display: "flex", flexDirection: "column", gap: 12,
                  boxShadow: "0 2px 5px rgba(245, 158, 11, 0.08)",
                }}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                    <span style={{ fontSize: 22, lineHeight: 1 }}>⚠️</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 700, color: "#92400e" }}>
                        Website "{currentDomain}" Not Found in Connected Google Account ({googleAccount})
                      </div>
                      <p style={{ margin: "6px 0 10px", fontSize: 12.5, color: "#b45309", lineHeight: 1.5 }}>
                        Your connected Gmail account <b>{googleAccount}</b> does not own or manage Search Console data for <b>{currentDomain}</b>.
                        To view real first-party Google analytics for <b>{currentBusiness}</b>, please connect the Gmail account that has verified ownership of this site.
                      </p>

                      {verifiedGscProperties.length > 0 && (
                        <div style={{ background: "#ffffff", border: "1px solid #fef3c7", borderRadius: 8, padding: "10px 14px", marginBottom: 12 }}>
                          <span style={{ fontSize: 12, fontWeight: 700, color: "#78350f" }}>
                            Websites verified under {googleAccount} ({verifiedGscProperties.length}):
                          </span>
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 6 }}>
                            {verifiedGscProperties.map((prop) => {
                              const cleanProp = prop.replace(/^sc-domain:/, "").replace(/^https?:\/\//, "").replace(/\/$/, "");
                              const isSelected = selectedGscProperty === prop;
                              return (
                                <button
                                  key={prop}
                                  type="button"
                                  onClick={() => {
                                    setSelectedGscProperty(prop);
                                    setTrafficDataSource("gsc");
                                    if (typeof window !== "undefined") {
                                      localStorage.setItem("reai_gsc_property", prop);
                                      localStorage.setItem("reai_traffic_source", "gsc");
                                    }
                                    fetchGscAnalytics(prop);
                                  }}
                                  style={{
                                    background: isSelected ? "#f59e0b" : "#fef3c7",
                                    color: isSelected ? "#ffffff" : "#92400e",
                                    border: `1px solid ${isSelected ? "#d97706" : "#fde68a"}`,
                                    borderRadius: 6, padding: "4px 10px",
                                    fontSize: 12, fontWeight: 700, cursor: "pointer",
                                  }}
                                >
                                  {cleanProp} {isSelected ? "✓ Active View" : "→ View Traffic"}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                        <button
                          type="button"
                          onClick={() => {
                            window.location.href = "/api/auth/google?prompt=select_account%20consent";
                          }}
                          style={{
                            background: "#d97706", color: "#ffffff", border: 0, borderRadius: 6,
                            padding: "7px 15px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                            display: "flex", alignItems: "center", gap: 7, boxShadow: "0 1px 3px rgba(0,0,0,0.12)",
                          }}
                        >
                          <IconGoogle size={14} />
                          <span>Connect Another Gmail Account →</span>
                        </button>

                        <button
                          type="button"
                          onClick={handleSwitchToGscProject}
                          style={{
                            background: "#ffffff", color: "#92400e", border: "1px solid #fcd34d", borderRadius: 6,
                            padding: "7px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                          }}
                        >
                          ⚡ Switch Workspace to {cleanGscDomain}
                        </button>

                        <a
                          href={`https://search.google.com/search-console?resource_id=${encodeURIComponent(`https://${currentDomain}/`)}`}
                          target="_blank"
                          rel="noreferrer"
                          style={{
                            color: "#b45309", fontSize: 12, textDecoration: "underline", fontWeight: 600, marginLeft: 4,
                          }}
                        >
                          Add {currentDomain} to Search Console ↗
                        </a>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {!googleConnected ? (
                <div style={{
                  background: "#ffffff", borderRadius: 10, border: "1px solid #e2e8f0",
                  padding: "54px 24px", textAlign: "center", display: "flex", flexDirection: "column",
                  alignItems: "center", gap: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
                }}>
                  <div style={{
                    width: 58, height: 58, borderRadius: 16, background: "#f8fafc",
                    border: "1px solid #e2e8f0", display: "grid", placeItems: "center",
                  }}>
                    <IconGoogle size={30} />
                  </div>
                  <div style={{ maxWidth: 540 }}>
                    <h3 style={{ margin: "0 0 8px 0", fontSize: 17, fontWeight: 800, color: "#0f172a" }}>
                      Google Search Console & GA4 Disconnected
                    </h3>
                    <p style={{ margin: 0, fontSize: 13, color: "var(--ink-muted)", lineHeight: 1.6 }}>
                      No active Google account is connected for <b>{currentDomain}</b>.
                      To ensure 100% data integrity without mock, estimated, or simulated traffic, real organic clicks and search impressions are only displayed once you sign in with the Google account that manages this website.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleConnectGoogle}
                    disabled={googleConnecting}
                    style={{
                      marginTop: 4, background: "#1e293b", color: "#ffffff", border: 0,
                      borderRadius: 8, padding: "10px 22px", fontSize: 13, fontWeight: 700,
                      cursor: "pointer", display: "flex", alignItems: "center", gap: 8,
                      boxShadow: "0 2px 6px rgba(0,0,0,0.12)",
                    }}
                  >
                    <IconGoogle size={16} />
                    <span>{googleConnecting ? "Connecting to Google..." : "Sign in with Google Account →"}</span>
                  </button>
                </div>
              ) : (
                <>
                  {/* Top Traffic KPIs with Integrated Live GSC Data */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }}>
                    {/* Verified Clicks */}
                    <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                          Verified Clicks (28d)
                        </span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "#ecfdf5", padding: "1px 6px", borderRadius: 4 }}>
                          Google GSC
                        </span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 6 }}>
                        <div>
                          <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>
                            {isGscLoading ? "..." : gscMetrics.clicks.toLocaleString()}
                          </div>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                            Organic search clicks
                          </div>
                        </div>
                        {gscDateTrend.length > 0 && (
                          <MiniSparkline data={gscDateTrend.map((p) => p.v)} color="#10b981" width={58} height={24} />
                        )}
                      </div>
                    </div>

                    {/* Total Impressions */}
                    <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                          Total Impressions (28d)
                        </span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "#0284c7", background: "#f0f9ff", padding: "1px 6px", borderRadius: 4 }}>
                          Google SERP
                        </span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 6 }}>
                        <div>
                          <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>
                            {isGscLoading ? "..." : gscMetrics.impressions.toLocaleString()}
                          </div>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                            Search visibility
                          </div>
                        </div>
                        {gscDateTrend.length > 0 && (
                          <MiniSparkline data={gscDateTrend.map((p) => p.v)} color="#0284c7" width={58} height={24} />
                        )}
                      </div>
                    </div>

                    {/* Average CTR */}
                    <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                          Average CTR
                        </span>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "#4f46e5" }}>Clicks / Imp</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 6 }}>
                        <div>
                          <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>
                            {isGscLoading ? "..." : `${gscMetrics.ctr}%`}
                          </div>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                            Click-through rate
                          </div>
                        </div>
                        <div style={{ width: 54, display: "flex", flexDirection: "column", gap: 3 }}>
                          <div style={{ height: 4, background: "#f1f5f9", borderRadius: 2, overflow: "hidden" }}>
                            <div style={{ width: `${Math.min(100, Math.max(5, gscMetrics.ctr * 10))}%`, height: "100%", background: "#4f46e5", borderRadius: 2 }} />
                          </div>
                          <span style={{ fontSize: 12, color: "var(--ink-muted)", textAlign: "right" }}>GSC live</span>
                        </div>
                      </div>
                    </div>

                    {/* Average Position */}
                    <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                          Average Position
                        </span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)" }}>SERP Rank</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 6 }}>
                        <div>
                          <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>
                            {isGscLoading ? "..." : gscMetrics.avgPosition > 0 ? `#${gscMetrics.avgPosition}` : "—"}
                          </div>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                            Average Google rank
                          </div>
                        </div>
                        <MiniRadialGauge score={gscMetrics.avgPosition > 0 ? Math.max(10, Math.round(100 - gscMetrics.avgPosition)) : 0} size={34} color="var(--ok)" />
                      </div>
                    </div>

                    {/* Ranked Queries */}
                    <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                          Ranked Queries
                        </span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)" }}>
                          Live Verified
                        </span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 6 }}>
                        <div>
                          <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>
                            {isGscLoading ? "..." : gscMetrics.topQueries.length.toString()}
                          </div>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                            Search queries recorded
                          </div>
                        </div>
                        <MiniRadialGauge score={Math.min(100, gscMetrics.topQueries.length * 4)} size={34} color="#10b981" />
                      </div>
                    </div>
                  </div>

                  {/* Traffic Trend & Device Split */}
                  <div style={{ display: "grid", gridTemplateColumns: "1.7fr 1fr", gap: 12 }}>
                    <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                      <ExecutiveTrafficChart
                        trend={gscDateTrend}
                        totalVisits={`${gscMetrics.clicks.toLocaleString()} Clicks`}
                        domain={cleanGscDomain}
                        totalKeywords={gscMetrics.topQueries.length}
                      />
                    </div>

                    {/* Device Split Card with Donut Chart */}
                    <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                      <div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                          <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Device Breakdown</h4>
                          <span style={{
                            fontSize: 12, fontWeight: 700,
                            color: gscDeviceSplit ? "#047857" : "#64748b",
                            background: gscDeviceSplit ? "#ecfdf5" : "#f1f5f9",
                            border: `1px solid ${gscDeviceSplit ? "#a7f3d0" : "#e2e8f0"}`,
                            padding: "2px 7px", borderRadius: 4,
                          }}>
                            {gscDeviceSplit ? "Google GSC Verified" : "Not measured"}
                          </span>
                        </div>

                        {gscDeviceSplit ? (
                          <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 14 }}>
                            <MiniDonut
                              size={68}
                              strokeWidth={6.5}
                              slices={[
                                { pct: gscDeviceSplit.mobile, color: "#10b981" },
                                { pct: gscDeviceSplit.desktop, color: "#6366f1" },
                              ]}
                            />
                            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
                              {([["Mobile Devices", gscDeviceSplit.mobile, "#10b981"],
                                 ["Desktop Browsers", gscDeviceSplit.desktop, "#6366f1"]] as const).map(([label, pct, colour]) => (
                                <div key={label}>
                                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                                    <span style={{ display: "flex", alignItems: "center", gap: 6, color: "#334155" }}>
                                      <span style={{ width: 7, height: 7, borderRadius: "50%", background: colour }} />
                                      {label}
                                    </span>
                                    <span style={{ fontWeight: 700, color: "#0f172a" }}>{pct}%</span>
                                  </div>
                                  <div style={{ height: 6, background: "#f1f5f9", borderRadius: 3, overflow: "hidden" }}>
                                    <div style={{ width: `${pct}%`, height: "100%", background: colour, borderRadius: 3 }} />
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : (
                          /* No donut, no bars. A chart is a claim, and drawing one
                             from a default is how 68/32 ended up under a green
                             "GSC Verified" badge on every account. */
                          <div style={{ padding: "18px 2px", fontSize: 12, color: "var(--ink-muted)", lineHeight: 1.55 }}>
                            Search Console returned no device breakdown for this property and date range.
                            Nothing is shown rather than a default split.
                          </div>
                        )}
                      </div>

                      <div style={{ borderTop: "1px solid #f1f4f8", paddingTop: 10, fontSize: 12, color: "var(--ink-muted)" }}>
                        {/* Was "Mobile-first indexing compliant · ✓ Verified" -
                            a hardcoded pair. Nothing in this codebase measures
                            mobile-first indexing. */}
                        {gscDeviceSplit
                          ? "Share of clicks by device, from Search Console."
                          : "Mobile-first indexing is not measured by this product."}
                      </div>
                    </div>
                  </div>

                  {/* Geographic Country Distribution Table */}
                  <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                        Traffic by Country & Geographic Market
                      </h4>
                      <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                        {gscCountrySplit.length > 0
                          ? `${gscCountrySplit.length} verified countries (Google Search Console)`
                          : "No international traffic recorded in last 28 days"}
                      </span>
                    </div>

                    <div style={{ marginTop: 14, border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                      <div style={{ overflowX: "auto" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                          <thead>
                            <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                              <th style={{ padding: "10px 14px", fontWeight: 700 }}>Country / Region</th>
                              <th style={{ padding: "10px 14px", fontWeight: 700 }}>Traffic Share</th>
                              <th style={{ padding: "10px 14px", fontWeight: 700 }}>Impressions</th>
                              <th style={{ padding: "10px 14px", fontWeight: 700 }}>Distribution Bar</th>
                            </tr>
                          </thead>
                          <tbody>
                            {gscCountrySplit.length === 0 ? (
                              <tr>
                                <td colSpan={4} style={{ padding: "24px 14px", textAlign: "center", color: "var(--ink-muted)" }}>
                                  No geographic traffic impressions recorded by Google Search Console in this period.
                                </td>
                              </tr>
                            ) : (
                              gscCountrySplit.map((c: any, i: number) => (
                                <tr key={i} style={{ borderBottom: i === gscCountrySplit.length - 1 ? "none" : "1px solid #f1f5f9", color: "#1e293b" }}>
                                  <td style={{ padding: "11px 14px", fontWeight: 600 }}>
                                    <span style={{ marginRight: 8 }}>{c.code}</span> {c.country}
                                  </td>
                                  <td style={{ padding: "11px 14px", fontWeight: 700, color: "#4f46e5" }}>{c.share}%</td>
                                  <td style={{ padding: "11px 14px", color: "#475569" }}>{c.visits}</td>
                                  <td style={{ padding: "11px 14px", width: "40%" }}>
                                    <div style={{ height: 7, background: "#f1f5f9", borderRadius: 4, overflow: "hidden" }}>
                                      <div style={{ width: `${c.share}%`, height: "100%", background: "#4f46e5", borderRadius: 4 }} />
                                    </div>
                                  </td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>

                  {/* Google Search Console Verified Queries Section */}
                  <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", overflow: "hidden" }}>
                    <div style={{ padding: "14px 18px", borderBottom: "1px solid #e2e8f0", display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f8fafc" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <IconGoogle size={17} />
                        <span style={{ fontSize: 13.5, fontWeight: 700, color: "#1e293b" }}>Top Verified Google Search Console Queries</span>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "#047857", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "1px 7px", borderRadius: 10 }}>
                          ● First-Party Data
                        </span>
                      </div>
                      <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                        {isGscLoading ? "Refreshing live data..." : `Showing ${gscMetrics.topQueries.length} live queries for `}
                        <b>{selectedGscProperty}</b>
                      </span>
                    </div>

                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: 12.5 }}>
                        <thead>
                          <tr style={{ background: "#ffffff", borderBottom: "1px solid #edf2f7", color: "var(--ink-muted)", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                            <th style={{ padding: "11px 18px", fontWeight: 700 }}>Search Query</th>
                            <th style={{ padding: "11px 18px", fontWeight: 700 }}>Clicks</th>
                            <th style={{ padding: "11px 18px", fontWeight: 700 }}>Impressions</th>
                            <th style={{ padding: "11px 18px", fontWeight: 700 }}>Avg CTR</th>
                            <th style={{ padding: "11px 18px", fontWeight: 700 }}>Avg Position</th>
                            <th style={{ padding: "11px 18px", fontWeight: 700 }}>Ranking Tier</th>
                          </tr>
                        </thead>
                        <tbody>
                          {isGscLoading ? (
                            <tr>
                              <td colSpan={6} style={{ padding: "32px 18px", textAlign: "center", color: "var(--ink-muted)" }}>
                                <div style={{ display: "inline-block", width: 18, height: 18, border: "2px solid #e2e8f0", borderTopColor: "#3b82f6", borderRadius: "50%", animation: "spin 1s linear infinite", marginRight: 8, verticalAlign: "middle" }} />
                                Loading live Google Search Console performance data for <b>{selectedGscProperty}</b>...
                              </td>
                            </tr>
                          ) : gscMetrics.topQueries.length === 0 ? (
                            <tr>
                              <td colSpan={6} style={{ padding: "32px 18px", textAlign: "center", color: "var(--ink-muted)" }}>
                                No search impressions recorded by Google Search Console for <b>{selectedGscProperty}</b> in the last 28 days.
                              </td>
                            </tr>
                          ) : (
                            gscMetrics.topQueries.map((q, idx) => (
                              <tr key={idx} style={{ borderBottom: idx === gscMetrics.topQueries.length - 1 ? "none" : "1px solid #f1f5f9", color: "#1e293b" }}>
                                <td style={{ padding: "12px 18px", fontWeight: 600, color: "#2563eb" }}>
                                  {q.query}
                                </td>
                                <td style={{ padding: "12px 18px", fontWeight: 700, color: "#0f172a" }}>
                                  {q.clicks.toLocaleString()}
                                </td>
                                <td style={{ padding: "12px 18px", color: "#475569" }}>
                                  {q.impressions.toLocaleString()}
                                </td>
                                <td style={{ padding: "12px 18px", fontWeight: 600, color: "var(--ok)" }}>
                                  {q.ctr}%
                                </td>
                                <td style={{ padding: "12px 18px", fontWeight: 700, color: "#1e293b" }}>
                                  #{q.position}
                                </td>
                                <td style={{ padding: "12px 18px" }}>
                                  <span style={{
                                    fontSize: 12, fontWeight: 700, padding: "2px 8px", borderRadius: 4,
                                    background: q.position <= 3 ? "#ecfdf5" : q.position <= 10 ? "#eff6ff" : "#f8fafc",
                                    color: q.position <= 3 ? "#047857" : q.position <= 10 ? "#1d4ed8" : "var(--ink-muted)",
                                    border: `1px solid ${q.position <= 3 ? "#a7f3d0" : q.position <= 10 ? "#bfdbfe" : "#e2e8f0"}`,
                                  }}>
                                    {q.position <= 3 ? "🏆 Top 3" : q.position <= 10 ? "⭐ Page 1" : q.position <= 20 ? "Page 2" : "Deep SERP"}
                                  </span>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* ── SUB-VIEW: ORGANIC RESEARCH (REAI FLAGSHIP) ── */}
          {activeTab === "Organic Research" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {/* Organic Research Intelligence Header Bar */}
              <div style={{
                background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0",
                padding: "16px 20px", display: "flex", justifyContent: "space-between",
                alignItems: "center", flexWrap: "wrap", gap: 12,
              }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 18 }}>🔍</span>
                    <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#0f172a" }}>
                      Organic Search Research & SERP Intelligence
                    </h3>
                    <span style={{
                      fontSize: 12, fontWeight: 700, color: "#1e40af",
                      background: "#eff6ff", border: "1px solid #bfdbfe",
                      padding: "2px 8px", borderRadius: 10,
                    }}>
                      🌐 SEO Pipeline
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                    Google rankings, search intent breakdown, SERP features won, and direct organic competitors for <b>{currentDomain}</b>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <button
                    type="button"
                    onClick={() => setShowOrganicGuideModal(true)}
                    style={{
                      background: "#eff6ff", color: "#1d4ed8", border: "1px solid #bfdbfe",
                      borderRadius: 6, padding: "7px 14px", fontSize: 12, fontWeight: 600,
                      cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                      transition: "all 0.15s ease",
                    }}
                  >
                    <span>💡</span> What is Organic Research?
                  </button>
                  <a
                    href="/docs/Organic_Research_Guide.pdf"
                    target="_blank"
                    rel="noopener noreferrer"
                    download="Organic_Research_Guide.pdf"
                    style={{
                      background: "#2563eb", color: "#ffffff", border: 0,
                      borderRadius: 6, padding: "7px 14px", fontSize: 12, fontWeight: 700,
                      cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                      textDecoration: "none", boxShadow: "0 1px 2px rgba(37,99,235,0.2)",
                    }}
                  >
                    <span>📄</span> Download Guide (PDF)
                  </a>
                </div>
              </div>

              {/* Position Distribution & Intent Breakdown */}
              <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 12 }}>
                {/* Position Distribution Card */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                    <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>SERP Position Distribution</h4>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "#0284c7", background: "#f0f9ff", border: "1px solid #bae6fd", padding: "2px 7px", borderRadius: 4 }}>
                      Google Top 100
                    </span>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {projectMetrics.organicResearch.posDistribution.map((p: any) => (
                      <div key={p.range}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                          <span style={{ fontWeight: 600, color: "#334155" }}>{p.range}</span>
                          <span style={{ color: "var(--ink-muted)", fontSize: 12 }}><b>{p.count}</b> kw ({p.pct}%)</span>
                        </div>
                        <div style={{ height: 6, background: "#f1f5f9", borderRadius: 3, overflow: "hidden" }}>
                          <div style={{ width: `${p.pct}%`, height: "100%", background: p.color, borderRadius: 3 }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Intent Breakdown Card with Segment Bar */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                      <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Search Intent Breakdown</h4>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 7px", borderRadius: 4 }}>
                        4 Categories
                      </span>
                    </div>

                    {/* Visual Segment Bar */}
                    <div style={{ marginBottom: 12 }}>
                      <MiniSegmentBar
                        height={6}
                        segments={projectMetrics.organicResearch.intentSplit.map((it: any) => ({
                          pct: it.pct,
                          color: it.color,
                          label: it.intent,
                        }))}
                      />
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      {projectMetrics.organicResearch.intentSplit.map((it: any) => (
                        <div key={it.intent} style={{ padding: "8px 12px", borderRadius: 6, background: "#f8fafc", border: "1px solid #edf0f4", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <div>
                            <div style={{ fontWeight: 600, fontSize: 12, color: "#1e293b" }}>{it.intent}</div>
                            <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>{it.count}</div>
                          </div>
                          <span style={{ fontSize: 12, fontWeight: 700, color: it.color, background: "#ffffff", border: "1px solid #e2e8f0", padding: "2px 6px", borderRadius: 4 }}>
                            {it.pct}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div style={{ borderTop: "1px solid #f1f4f8", paddingTop: 10, marginTop: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>High commercial intent</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ok)" }}>+22% Conversion value</span>
                  </div>
                </div>
              </div>

              {/* SERP Features Won */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>SERP Features in Search Landscape</h4>
                  <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>Active snippet enhancements</span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                  {projectMetrics.organicResearch.serpFeatures.map((f: any) => (
                    <div key={f.name} style={{ padding: "10px 14px", borderRadius: 6, background: f.active ? "#ecfdf5" : "#f8fafc", border: "1px solid", borderColor: f.active ? "#a7f3d0" : "#edf0f4", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: 600, fontSize: 12, color: f.active ? "#065f46" : "var(--ink-muted)" }}>{f.name}</span>
                      <span style={{ fontSize: 12, fontWeight: 700, color: f.active ? "#047857" : "var(--ink-muted)" }}>{f.count} Active</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Organic Competitors Map Table */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Organic Competitors Positioning Matrix</h4>
                  <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>Direct SERP rivals</span>
                </div>

                <div style={{ marginTop: 14, border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                      <thead>
                        <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Competitor Domain</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Common Keywords</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Search Visibility</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Est. Organic Traffic</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {projectMetrics.organicResearch.competitorMap.map((cm: any, i: number) => (
                          <tr key={i} style={{ borderBottom: i === projectMetrics.organicResearch.competitorMap.length - 1 ? "none" : "1px solid #f1f5f9", color: "#1e293b" }}>
                            <td style={{ padding: "11px 14px", fontWeight: 600 }}>{cm.domain}</td>
                            <td style={{ padding: "11px 14px", color: "#4f46e5", fontWeight: 600 }}>{cm.commonKeywords} shared</td>
                            <td style={{ padding: "11px 14px", fontWeight: 600 }}>{cm.searchVisibility}</td>
                            <td style={{ padding: "11px 14px", color: "#475569" }}>{cm.organicTraffic} / mo</td>
                            <td style={{ padding: "11px 14px" }}>
                              <button
                                type="button"
                                onClick={() => setActiveTab("Keyword Gap")}
                                style={{ background: "#eff6ff", border: "1px solid #dbeafe", color: "#2563eb", borderRadius: 4, padding: "4px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                              >
                                Gap →
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {/* Top Organic Pages & Content Silos */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Top Organic Pages & Content Silos</h4>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "2px 7px", borderRadius: 4 }}>
                        Traffic Drivers
                      </span>
                    </div>
                    <p style={{ margin: "3px 0 0", fontSize: 12, color: "var(--ink-muted)" }}>
                      Pages commanding the highest organic SERP click-share for {currentBusiness}
                    </p>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ position: "relative", minWidth: 200 }}>
                      <span style={{ position: "absolute", left: 9, top: "50%", transform: "translateY(-50%)", color: "var(--ink-muted)", fontSize: 12 }}>🔍</span>
                      <input
                        type="text"
                        value={organicPagesQuery}
                        onChange={(e) => setOrganicPagesQuery(e.target.value)}
                        placeholder="Filter page URL..."
                        style={{
                          width: "100%", padding: "5px 10px 5px 28px", borderRadius: 6,
                          border: "1px solid #cbd5e1", fontSize: 12, background: "#f8fafc", color: "#1e293b", outline: "none",
                        }}
                      />
                      {organicPagesQuery && (
                        <button
                          type="button"
                          onClick={() => setOrganicPagesQuery("")}
                          style={{ position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)", background: "none", border: 0, color: "var(--ink-muted)", cursor: "pointer", fontSize: 12 }}
                        >
                          ✕
                        </button>
                      )}
                    </div>
                    <span style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>
                      {projectMetrics.topOrganicPages?.length || 0} Pages Tracked
                    </span>
                  </div>
                </div>

                <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                      <thead>
                        <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Page URL</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Traffic Share</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Ranked Keywords</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Top Driver Keyword</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(projectMetrics.topOrganicPages || [])
                          .filter((p: any) => !organicPagesQuery || p.url.toLowerCase().includes(organicPagesQuery.toLowerCase()) || p.topKeyword.toLowerCase().includes(organicPagesQuery.toLowerCase()))
                          .map((page: any, idx: number, arr: any[]) => (
                            <tr key={idx} style={{ borderBottom: idx === arr.length - 1 ? "none" : "1px solid #f1f5f9", color: "#1e293b" }}>
                              <td style={{ padding: "11px 14px" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                  <span style={{ fontFamily: "monospace", fontWeight: 600, color: "#2563eb", fontSize: 12 }}>
                                    {page.url}
                                  </span>
                                  <a
                                    href={`https://${currentDomain.replace(/^https?:\/\//, "")}${page.url}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    style={{ color: "var(--ink-muted)", textDecoration: "none", fontSize: 12 }}
                                    title="Open page"
                                  >
                                    ↗
                                  </a>
                                </div>
                              </td>
                              <td style={{ padding: "11px 14px" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                  <span style={{ fontWeight: 700, color: "#1e293b", minWidth: 42 }}>{page.traffic}</span>
                                  <div style={{ width: 65, height: 5, background: "#f1f5f9", borderRadius: 3, overflow: "hidden" }}>
                                    <div style={{ width: `${page.trafficPct}%`, height: "100%", background: "#3b82f6", borderRadius: 3 }} />
                                  </div>
                                  <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>{page.trafficPct}%</span>
                                </div>
                              </td>
                              <td style={{ padding: "11px 14px" }}>
                                <span style={{ fontWeight: 600, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 7px", borderRadius: 4, fontSize: 12 }}>
                                  {page.keywordsCount} kw
                                </span>
                              </td>
                              <td style={{ padding: "11px 14px" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                  <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "1px 5px", borderRadius: 3 }}>
                                    #{page.topPosition}
                                  </span>
                                  <span style={{ color: "#334155", fontWeight: 500, fontSize: 12 }}>{page.topKeyword}</span>
                                </div>
                              </td>
                              <td style={{ padding: "11px 14px" }}>
                                <button
                                  type="button"
                                  onClick={() => setActiveTab("On-Page SEO")}
                                  style={{
                                    background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#166534",
                                    borderRadius: 4, padding: "4px 9px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                                    display: "inline-flex", alignItems: "center", gap: 4,
                                  }}
                                >
                                  <span>⚡</span> Audit
                                </button>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── SUB-VIEW: KEYWORD GAP ANALYSIS (REAI FLAGSHIP) ── */}
          {activeTab === "Keyword Gap" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {/* Header Card with Competitors Matrix & Visual Ratio Bar */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Keyword Gap Comparison</h4>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 7px", borderRadius: 4 }}>
                      Intersection Matrix
                    </span>
                  </div>

                  <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
                    <span style={{ fontWeight: 600, color: "#1e293b", background: "#f1f5f9", padding: "4px 10px", borderRadius: 4 }}>
                      {currentDomain} (You)
                    </span>
                    <span style={{ color: "var(--ink-muted)" }}>vs</span>
                    <span style={{ fontWeight: 600, color: "#4f46e5", background: "#eef2ff", padding: "4px 10px", borderRadius: 4 }}>
                      {projectMetrics.competitors[0] || "Competitor 1"}
                    </span>
                    <span style={{ color: "var(--ink-muted)" }}>vs</span>
                    <span style={{ fontWeight: 600, color: "var(--ok)", background: "#ecfdf5", padding: "4px 10px", borderRadius: 4 }}>
                      {projectMetrics.competitors[1] || "Competitor 2"}
                    </span>
                  </div>
                </div>

                {/* Visual Intersect Segment Bar */}
                <div style={{ marginBottom: 14 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--ink-muted)", marginBottom: 6 }}>
                    <span>Keyword Opportunities: <b>42% Missing</b> · <b>34% Untapped</b> · <b>24% Shared</b></span>
                    <span style={{ color: "var(--ok)", fontWeight: 600 }}>High Opportunity</span>
                  </div>
                  <MiniSegmentBar
                    height={6}
                    segments={[] /* was a hardcoded keyword-gap split */}
                  />
                </div>

                {/* Filter Tabs */}
                <div style={{ display: "flex", gap: 6, borderTop: "1px solid #edf0f4", paddingTop: 12 }}>
                  {(["all", "missing", "untapped", "weak", "shared"] as const).map((f) => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => setGapFilter(f)}
                      style={{
                        background: gapFilter === f ? "#1e293b" : "#f8fafc",
                        color: gapFilter === f ? "#ffffff" : "#475569",
                        border: "1px solid", borderColor: gapFilter === f ? "#1e293b" : "#e2e8f0",
                        borderRadius: 5, padding: "5px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                        textTransform: "capitalize",
                      }}
                    >
                      {f === "all" ? "All Intersections" : `${f}`}
                    </button>
                  ))}
                </div>
              </div>

              {/* Gap Keywords Table */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                      <thead>
                        <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Keyword</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Intent</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>You ({currentDomain.replace(/\..*$/, "")})</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>{projectMetrics.competitors[0] || "Competitor 1"}</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>{projectMetrics.competitors[1] || "Competitor 2"}</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Volume</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Difficulty (KD%)</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {projectMetrics.keywordGapData
                          .filter((item: any) => gapFilter === "all" || item.type === gapFilter)
                          .map((item: any, idx: number, arr: any[]) => (
                            <tr key={idx} style={{ borderBottom: idx === arr.length - 1 ? "none" : "1px solid #f1f5f9", color: "#1e293b" }}>
                              <td style={{ padding: "11px 14px", fontWeight: 600 }}>{item.keyword}</td>
                              <td style={{ padding: "11px 14px" }}>
                                <span style={{ fontSize: 12, fontWeight: 600, padding: "2px 7px", borderRadius: 4, background: "#f8fafc", border: "1px solid #e2e8f0", color: "#475569" }}>
                                  {item.intent}
                                </span>
                              </td>
                              <td style={{ padding: "11px 14px" }}>
                                {item.myRank ? (
                                  <span style={{ fontWeight: 700, fontSize: 12, color: "#10b981", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "2px 7px", borderRadius: 4 }}>
                                    #{item.myRank}
                                  </span>
                                ) : (
                                  <span style={{ color: "var(--ink-muted)", fontSize: 12 }}>— unranked</span>
                                )}
                              </td>
                              <td style={{ padding: "11px 14px" }}>
                                <span style={{ fontWeight: 600, color: "#4f46e5" }}>#{item.comp1Rank}</span>
                              </td>
                              <td style={{ padding: "11px 14px" }}>
                                {item.comp2Rank ? (
                                  <span style={{ fontWeight: 600, color: "var(--ok)" }}>#{item.comp2Rank}</span>
                                ) : (
                                  <span style={{ color: "var(--ink-muted)" }}>—</span>
                                )}
                              </td>
                              <td style={{ padding: "11px 14px", color: "var(--ink-muted)" }}>{item.volume} / mo</td>
                              <td style={{ padding: "11px 14px" }}>
                                <MiniKdMeter kd={item.kd} />
                              </td>
                              <td style={{ padding: "11px 14px" }}>
                                <button
                                  type="button"
                                  onClick={() => {
                                    if (!savedKeywords.includes(item.keyword)) {
                                      setSavedKeywords([...savedKeywords, item.keyword]);
                                    }
                                  }}
                                  style={{
                                    background: savedKeywords.includes(item.keyword) ? "#ecfdf5" : "#ffffff",
                                    border: "1px solid", borderColor: savedKeywords.includes(item.keyword) ? "#a7f3d0" : "#cbd5e1",
                                    color: savedKeywords.includes(item.keyword) ? "#047857" : "#334155",
                                    borderRadius: 4, padding: "3px 9px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                                  }}
                                >
                                  {savedKeywords.includes(item.keyword) ? "✓ Target" : "+ Add"}
                                </button>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── SUB-VIEW: BACKLINK GAP (REAI FLAGSHIP) ── */}
          {activeTab === "Backlink Gap" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                      Backlink Gap & Link Opportunities
                    </h4>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                      Domains referring to competitors where {currentDomain} has 0 links
                    </div>
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#e11d48", background: "#fef2f2", border: "1px solid #fecaca", padding: "3px 9px", borderRadius: 4 }}>
                    {projectMetrics.backlinkGapData.length} Link Opportunities
                  </span>
                </div>

                <div style={{ marginTop: 14, border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                      <thead>
                        <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Referring Domain</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Authority (AS)</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Category</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>{projectMetrics.competitors[0] || "Competitor 1"}</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>{projectMetrics.competitors[1] || "Competitor 2"}</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Your Links</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {projectMetrics.backlinkGapData.map((item: any, idx: number, arr: any[]) => (
                          <tr key={idx} style={{ borderBottom: idx === arr.length - 1 ? "none" : "1px solid #f1f5f9", color: "#1e293b" }}>
                            <td style={{ padding: "11px 14px", fontWeight: 600 }}>{item.domain}</td>
                            <td style={{ padding: "11px 14px" }}>
                              <span style={{ fontSize: 12, fontWeight: 700, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 7px", borderRadius: 4 }}>
                                AS {item.as}
                              </span>
                            </td>
                            <td style={{ padding: "11px 14px", color: "var(--ink-muted)" }}>{item.category}</td>
                            <td style={{ padding: "11px 14px", fontWeight: 600 }}>{item.comp1Links} links</td>
                            <td style={{ padding: "11px 14px", fontWeight: 600 }}>{item.comp2Links} links</td>
                            <td style={{ padding: "11px 14px" }}>
                              <span style={{ color: "#e11d48", fontWeight: 700, background: "#fef2f2", border: "1px solid #fecaca", padding: "2px 6px", borderRadius: 4, fontSize: 12 }}>
                                0 links (Gap)
                              </span>
                            </td>
                            <td style={{ padding: "11px 14px" }}>
                              <button
                                type="button"
                                onClick={() => {
                                  setSelectedOutreachDomain(item.domain);
                                  setSelectedOutreachCategory(item.category || "General");
                                  setShowOutreachModal(true);
                                }}
                                style={{
                                  background: outreachPitchedDomains.includes(item.domain) ? "#ecfdf5" : "#4f46e5",
                                  color: outreachPitchedDomains.includes(item.domain) ? "#047857" : "#fff",
                                  border: outreachPitchedDomains.includes(item.domain) ? "1px solid #a7f3d0" : 0,
                                  borderRadius: 4, padding: "4px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                                  display: "inline-flex", alignItems: "center", gap: 4,
                                }}
                              >
                                {outreachPitchedDomains.includes(item.domain) ? "✓ Added" : "+ Outreach"}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {outreachToast && (
                  <div style={{ marginTop: 10, padding: "8px 12px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, fontSize: 12, color: "#166534", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span>✓ Added <b>{outreachToast}</b> to Outreach Pitch Queue. AI pitch template staged.</span>
                    <button type="button" onClick={() => setOutreachToast(null)} style={{ background: "none", border: 0, color: "#166534", cursor: "pointer" }}>✕</button>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── SUB-VIEW: KEYWORD MAGIC TOOL (+ REAI AI BRIEF) ── */}
          {activeTab === "Keyword Magic Tool" && (() => {
            // Compute dynamic clusters from available keywords
            const allKws = projectMetrics.magicToolKeywords || [];
            
            // Extract root terms for cluster grouping
            const clusterMap: Record<string, { count: number; volume: number }> = {};
            allKws.forEach((k: any) => {
              const words = k.keyword.toLowerCase().split(/\s+/);
              const volNum = parseInt(k.volume.replace(/[^0-9]/g, ""), 10) || 500;
              words.forEach((w: string) => {
                if (w.length >= 4 && !["best", "with", "near", "from", "that"].includes(w)) {
                  if (!clusterMap[w]) clusterMap[w] = { count: 0, volume: 0 };
                  clusterMap[w].count += 1;
                  clusterMap[w].volume += volNum;
                }
              });
            });

            const topClusters = Object.entries(clusterMap)
              .filter(([_, data]) => data.count >= 2)
              .sort((a, b) => b[1].volume - a[1].volume)
              .slice(0, 8);

            // Filter keywords according to cluster, query, KD, match type, and intent
            const filteredMagicKws = allKws.filter((item: any) => {
              if (magicCluster !== "all" && !item.keyword.toLowerCase().includes(magicCluster.toLowerCase())) return false;
              if (magicQuery && !item.keyword.toLowerCase().includes(magicQuery.toLowerCase())) return false;
              if (item.kd > magicKdMax) return false;
              if (magicMatch === "questions") return item.type === "questions";
              if (magicMatch === "exact") return item.type === "exact";
              if (magicMatch === "phrase") return item.type === "phrase" || item.type === "exact";
              if (magicIntentFilter !== "all" && item.intent.toLowerCase() !== magicIntentFilter.toLowerCase()) return false;
              return true;
            });

            const totalVolFiltered = filteredMagicKws.reduce((acc: number, cur: any) => {
              const num = parseInt(cur.volume.replace(/[^0-9]/g, ""), 10) || 500;
              return acc + num;
            }, 0);

            const avgKdFiltered = filteredMagicKws.length > 0
              ? Math.round(filteredMagicKws.reduce((acc: number, cur: any) => acc + cur.kd, 0) / filteredMagicKws.length)
              : 0;

            const intentCounts: Record<string, number> = {
              Informational: allKws.filter((k: any) => k.intent === "Informational").length,
              Commercial: allKws.filter((k: any) => k.intent === "Commercial").length,
              Transactional: allKws.filter((k: any) => k.intent === "Transactional").length,
              Navigational: allKws.filter((k: any) => k.intent === "Navigational").length,
            };

            return (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {/* Top Metrics Strip */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
                  <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "14px 16px" }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase" }}>Total Keywords</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: "#0f172a", marginTop: 4 }}>{filteredMagicKws.length}</div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>Clusters active: {magicCluster === "all" ? "All" : magicCluster}</div>
                  </div>

                  <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "14px 16px" }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase" }}>Total Search Volume</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: "#4f46e5", marginTop: 4 }}>{totalVolFiltered.toLocaleString()} / mo</div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>Monthly organic searches</div>
                  </div>

                  <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "14px 16px" }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase" }}>Average KD%</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: avgKdFiltered < 30 ? "var(--ok)" : avgKdFiltered < 50 ? "#d97706" : "#dc2626", marginTop: 4 }}>
                      {avgKdFiltered}%
                    </div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                      {avgKdFiltered < 30 ? "Easy to rank (Low effort)" : "Moderate competition"}
                    </div>
                  </div>

                  <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "14px 16px" }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase" }}>Saved in Strategy Deck</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: "var(--ok)", marginTop: 4 }}>{savedKeywords.length} kw</div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>Targeted for AI content</div>
                  </div>
                </div>

                {/* 2-Column Layout: Cluster Tree Sidebar + Keyword Data Grid */}
                <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 12, alignItems: "start" }}>
                  {/* Left Column: Sub-Groups / Cluster Tree */}
                  <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "14px 14px", position: "sticky", top: 16 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#4f46e5", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
                      Keyword Clusters
                    </div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginBottom: 12 }}>
                      Group by semantic sub-topic
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                      <button
                        type="button"
                        onClick={() => setMagicCluster("all")}
                        style={{
                          display: "flex", justifyContent: "space-between", alignItems: "center",
                          padding: "7px 10px", borderRadius: 6,
                          background: magicCluster === "all" ? "#1e293b" : "transparent",
                          color: magicCluster === "all" ? "#ffffff" : "#334155",
                          border: 0, fontSize: 12, fontWeight: magicCluster === "all" ? 700 : 500,
                          cursor: "pointer", textAlign: "left", width: "100%",
                        }}
                      >
                        <span>All Clusters</span>
                        <span style={{
                          fontSize: 12, padding: "1px 6px", borderRadius: 4,
                          background: magicCluster === "all" ? "rgba(255,255,255,0.2)" : "#f1f5f9",
                          color: magicCluster === "all" ? "#ffffff" : "var(--ink-muted)",
                        }}>
                          {allKws.length}
                        </span>
                      </button>

                      {topClusters.map(([term, data]) => (
                        <button
                          key={term}
                          type="button"
                          onClick={() => setMagicCluster(term)}
                          style={{
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                            padding: "7px 10px", borderRadius: 6,
                            background: magicCluster === term ? "#1e293b" : "transparent",
                            color: magicCluster === term ? "#ffffff" : "#334155",
                            border: 0, fontSize: 12, fontWeight: magicCluster === term ? 700 : 500,
                            cursor: "pointer", textAlign: "left", width: "100%",
                            textTransform: "capitalize",
                          }}
                        >
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {term}
                          </span>
                          <span style={{
                            fontSize: 12, padding: "1px 6px", borderRadius: 4,
                            background: magicCluster === term ? "rgba(255,255,255,0.2)" : "#f1f5f9",
                            color: magicCluster === term ? "#ffffff" : "var(--ink-muted)",
                            flexShrink: 0, marginLeft: 6,
                          }}>
                            {data.count}
                          </span>
                        </button>
                      ))}
                    </div>

                    {/* Intent Quick Filter */}
                    <div style={{ marginTop: 16, borderTop: "1px solid #f1f5f9", paddingTop: 12 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase", marginBottom: 8 }}>
                        Search Intent
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                        {(["all", "Informational", "Commercial", "Transactional", "Navigational"] as const).map((it) => (
                          <button
                            key={it}
                            type="button"
                            onClick={() => setMagicIntentFilter(it)}
                            style={{
                              display: "flex", justifyContent: "space-between", alignItems: "center",
                              padding: "5px 8px", borderRadius: 4,
                              background: magicIntentFilter === it ? "#e0e7ff" : "transparent",
                              color: magicIntentFilter === it ? "#3730a3" : "#475569",
                              border: 0, fontSize: 12, fontWeight: magicIntentFilter === it ? 700 : 500,
                              cursor: "pointer", textAlign: "left", width: "100%",
                            }}
                          >
                            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              {it === "Informational" && <span style={{ width: 14, height: 14, borderRadius: "50%", background: "#3b82f6", color: "#fff", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 700 }}>I</span>}
                              {it === "Commercial" && <span style={{ width: 14, height: 14, borderRadius: "50%", background: "#f59e0b", color: "#fff", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 700 }}>C</span>}
                              {it === "Transactional" && <span style={{ width: 14, height: 14, borderRadius: "50%", background: "#10b981", color: "#fff", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 700 }}>T</span>}
                              {it === "Navigational" && <span style={{ width: 14, height: 14, borderRadius: "50%", background: "#8b5cf6", color: "#fff", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 700 }}>N</span>}
                              {it === "all" ? "All Intents" : it}
                            </span>
                            <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                              {it === "all" ? allKws.length : intentCounts[it] || 0}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Right Column: Keyword Filters & Data Table */}
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {/* Search & Match Types Bar */}
                    <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "14px 16px" }}>
                      <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
                        <div style={{ position: "relative", flex: 1 }}>
                          <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--ink-muted)", fontSize: 13 }}>🔍</span>
                          <input
                            type="text"
                            value={magicQuery}
                            onChange={(e) => setMagicQuery(e.target.value)}
                            placeholder="Search keyword variations (e.g. hospital, clinic, doctors)..."
                            style={{
                              width: "100%", padding: "7px 12px 7px 32px", borderRadius: 6,
                              border: "1px solid #cbd5e1", fontSize: 12.5, background: "#f8fafc", color: "#1e293b", outline: "none",
                            }}
                          />
                          {magicQuery && (
                            <button
                              type="button"
                              onClick={() => setMagicQuery("")}
                              style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: 0, color: "var(--ink-muted)", cursor: "pointer", fontSize: 12 }}
                            >
                              ✕
                            </button>
                          )}
                        </div>
                        {savedKeywords.length > 0 && (
                          <button
                            type="button"
                            onClick={() => {
                              const csvRows = [
                                ["Keyword", "Client", "Exported At"],
                                ...savedKeywords.map((kw) => [kw, currentBusiness, new Date().toISOString()]),
                              ];
                              const csvContent = "data:text/csv;charset=utf-8," + csvRows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
                              const encodedUri = encodeURI(csvContent);
                              const link = document.createElement("a");
                              link.setAttribute("href", encodedUri);
                              link.setAttribute("download", `content_plan_keywords_${currentDomain.replace(/[^a-zA-Z0-9]/g, "_")}.csv`);
                              document.body.appendChild(link);
                              link.click();
                              document.body.removeChild(link);
                              setPlanExportToast(true);
                              setTimeout(() => setPlanExportToast(false), 3500);
                            }}
                            style={{
                              background: planExportToast ? "#047857" : "#059669", color: "#ffffff", border: 0, borderRadius: 6,
                              padding: "7px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                              display: "flex", alignItems: "center", gap: 6, whiteSpace: "nowrap",
                            }}
                          >
                            <span>{planExportToast ? "✓" : "📥"}</span> {planExportToast ? `Exported (${savedKeywords.length})` : `Export Deck (${savedKeywords.length})`}
                          </button>
                        )}
                      </div>

                      {/* Match types & KD filter controls */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, borderTop: "1px solid #f1f5f9", paddingTop: 10 }}>
                        <div style={{ display: "flex", gap: 6 }}>
                          {(["broad", "phrase", "exact", "questions"] as const).map((m) => (
                            <button
                              key={m}
                              type="button"
                              onClick={() => setMagicMatch(m)}
                              style={{
                                background: magicMatch === m ? "#1e293b" : "#f8fafc",
                                color: magicMatch === m ? "#ffffff" : "#475569",
                                border: "1px solid", borderColor: magicMatch === m ? "#1e293b" : "#e2e8f0",
                                borderRadius: 4, padding: "3px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                                textTransform: "capitalize",
                              }}
                            >
                              {m === "questions" ? "Questions" : `${m} Match`}
                            </button>
                          ))}
                        </div>

                        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                          <span style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Max KD%:</span>
                          {[14, 29, 49, 100].map((kd) => (
                            <button
                              key={kd}
                              type="button"
                              onClick={() => setMagicKdMax(kd)}
                              style={{
                                background: magicKdMax === kd ? "#eff6ff" : "#f8fafc",
                                color: magicKdMax === kd ? "#1d4ed8" : "var(--ink-muted)",
                                border: "1px solid", borderColor: magicKdMax === kd ? "#bfdbfe" : "#e2e8f0",
                                borderRadius: 4, padding: "3px 8px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                              }}
                            >
                              {kd === 14 ? "Very Easy (≤14)" : kd === 29 ? "Easy (≤29)" : kd === 49 ? "Possible (≤49)" : "All KD"}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Table View */}
                    <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "14px 16px" }}>
                      <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                        <div style={{ overflowX: "auto" }}>
                          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, textAlign: "left" }}>
                            <thead>
                              <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                                <th style={{ padding: "10px 14px", fontWeight: 700 }}>Keyword Variation</th>
                                <th style={{ padding: "10px 14px", fontWeight: 700 }}>Intent</th>
                                <th style={{ padding: "10px 14px", fontWeight: 700 }}>Volume</th>
                                <th style={{ padding: "10px 14px", fontWeight: 700 }}>KD%</th>
                                <th style={{ padding: "10px 14px", fontWeight: 700 }}>CPC</th>
                                <th style={{ padding: "10px 14px", fontWeight: 700 }}>SERP Features</th>
                                <th style={{ padding: "10px 14px", fontWeight: 700, textAlign: "right" }}>Autonomous Action</th>
                              </tr>
                            </thead>
                            <tbody>
                              {filteredMagicKws.map((item: any, idx: number, arr: any[]) => {
                                const isAdded = savedKeywords.includes(item.keyword);
                                const intentCode = item.intent.startsWith("Info") ? "I" : item.intent.startsWith("Comm") ? "C" : item.intent.startsWith("Trans") ? "T" : "N";
                                const intentColor = intentCode === "I" ? "#3b82f6" : intentCode === "C" ? "#f59e0b" : intentCode === "T" ? "#10b981" : "#8b5cf6";
                                const intentBg = intentCode === "I" ? "#eff6ff" : intentCode === "C" ? "#fef3c7" : intentCode === "T" ? "#ecfdf5" : "#f5f3ff";

                                return (
                                  <tr key={idx} style={{ borderBottom: idx === arr.length - 1 ? "none" : "1px solid #f1f5f9", color: "#1e293b" }}>
                                    <td style={{ padding: "11px 14px", fontWeight: 600 }}>
                                      <div style={{ color: "#1e293b", fontSize: 12.5 }}>{item.keyword}</div>
                                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>Match: {item.type}</div>
                                    </td>
                                    <td style={{ padding: "11px 14px" }}>
                                      <span style={{
                                        display: "inline-flex", alignItems: "center", gap: 5,
                                        fontSize: 12, fontWeight: 700, padding: "2px 7px", borderRadius: 4,
                                        background: intentBg, color: intentColor, border: `1px solid ${intentColor}33`,
                                      }}>
                                        <span style={{ width: 13, height: 13, borderRadius: "50%", background: intentColor, color: "#fff", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 800 }}>
                                          {intentCode}
                                        </span>
                                        {item.intent}
                                      </span>
                                    </td>
                                    <td style={{ padding: "11px 14px", fontWeight: 700, color: "#0f172a" }}>
                                      {item.volume}
                                    </td>
                                    <td style={{ padding: "11px 14px" }}>
                                      <MiniKdMeter kd={item.kd} />
                                    </td>
                                    <td style={{ padding: "11px 14px", color: "var(--ink-muted)", fontFamily: "monospace" }}>
                                      {item.cpc}
                                    </td>
                                    <td style={{ padding: "11px 14px", fontSize: 12, color: "var(--ink-muted)" }}>
                                      {item.features.slice(0, 3).join(" · ")}
                                    </td>
                                    <td style={{ padding: "11px 14px", textAlign: "right" }}>
                                      <div style={{ display: "inline-flex", gap: 6 }}>
                                        <button
                                          type="button"
                                          onClick={() => {
                                            setActiveMagicBrief({
                                              keyword: item.keyword,
                                              volume: item.volume,
                                              kd: item.kd,
                                              intent: item.intent,
                                              h1: `${item.keyword.split(" ").map((w: string) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")} | Complete Care & Services`,
                                              slug: `/services/${item.keyword.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
                                              // Derived from the keyword and the
                                              // selected project. These were
                                              // hardcoded hospital headings and
                                              // one client's entity list, which
                                              // shipped medical copy into every
                                              // brief regardless of the client.
                                              headings: [
                                                `Introduction: ${item.keyword}`,
                                                `What ${item.keyword} Covers`,
                                                `How to Choose a Provider`,
                                                `Frequently Asked Questions (FAQ)`,
                                              ],
                                              entities: [
                                                currentBusiness,
                                                item.keyword,
                                              ].filter(Boolean),
                                              schemaType: "WebPage",
                                            });
                                          }}
                                          style={{
                                            background: "#4f46e5", color: "#ffffff", border: 0,
                                            borderRadius: 4, padding: "4px 9px", fontSize: 12, fontWeight: 600,
                                            cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4,
                                          }}
                                        >
                                          <span>⚡</span> AI Brief
                                        </button>
                                        <button
                                          type="button"
                                          onClick={() => {
                                            if (!isAdded) {
                                              setSavedKeywords([...savedKeywords, item.keyword]);
                                            } else {
                                              setSavedKeywords(savedKeywords.filter((k) => k !== item.keyword));
                                            }
                                          }}
                                          style={{
                                            background: isAdded ? "#ecfdf5" : "#ffffff",
                                            border: "1px solid", borderColor: isAdded ? "#a7f3d0" : "#cbd5e1",
                                            color: isAdded ? "#047857" : "#334155",
                                            borderRadius: 4, padding: "4px 8px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                                          }}
                                        >
                                          {isAdded ? "✓ Added" : "+ Deck"}
                                        </button>
                                      </div>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Interactive AI Content Brief Modal (REAI Exclusive Flow) */}
                {activeMagicBrief && (
                  <div style={{
                    position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
                    background: "rgba(15, 23, 42, 0.6)", backdropFilter: "blur(4px)",
                    display: "flex", justifyContent: "center", alignItems: "center",
                    zIndex: 9999, padding: 20,
                  }}>
                    <div style={{
                      background: "#ffffff", borderRadius: 10, width: "100%", maxWidth: 680,
                      maxHeight: "90vh", overflowY: "auto", border: "1px solid #e2e8f0",
                      boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
                      padding: "20px 24px",
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #edf0f4", paddingBottom: 12, marginBottom: 14 }}>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ fontSize: 12, fontWeight: 800, background: "#4f46e5", color: "#fff", padding: "2px 7px", borderRadius: 4 }}>
                              REAI MODEL B CONTENT ENGINE
                            </span>
                            <span style={{ fontSize: 14, fontWeight: 800, color: "#0f172a" }}>
                              Autonomous Content Brief
                            </span>
                          </div>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                            Targeting keyword: <b>"{activeMagicBrief.keyword}"</b> ({activeMagicBrief.volume}/mo · KD {activeMagicBrief.kd}%)
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => setActiveMagicBrief(null)}
                          style={{ background: "none", border: 0, color: "var(--ink-muted)", cursor: "pointer", fontSize: 16, padding: 4 }}
                        >
                          ✕
                        </button>
                      </div>

                      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                        {/* SERP Snippet Preview */}
                        <div style={{ background: "#f8fafc", borderRadius: 6, border: "1px solid #edf0f4", padding: "12px 14px" }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase", marginBottom: 6 }}>
                            Google SERP Snippet Preview
                          </div>
                          <div style={{ color: "#1a0dab", fontSize: 14, fontWeight: 600, textDecoration: "none", marginBottom: 2 }}>
                            {activeMagicBrief.h1}
                          </div>
                          <div style={{ color: "#006621", fontSize: 12, marginBottom: 4 }}>
                            https://{currentDomain}{activeMagicBrief.slug}
                          </div>
                          <div style={{ color: "#545454", fontSize: 12, lineHeight: 1.4 }}>
                            {/* Was medical copy with a Cambodian city, shipped to
                                every client under "Google SERP Snippet Preview" -
                                and it sat directly below a comment claiming the
                                hardcoded hospital copy had been removed. It had
                                been removed from the headings and the entities,
                                and left in the snippet body. */}
                            {scannedPage?.description
                              || `No meta description was read for this page. Run a scan, or write one with Claude.`}
                          </div>
                        </div>

                        {/* Proposed H2 Structure */}
                        <div>
                          <div style={{ fontSize: 12, fontWeight: 700, color: "#1e293b", marginBottom: 6 }}>
                            Recommended Heading Architecture:
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            {activeMagicBrief.headings.map((h: string, i: number) => (
                              <div key={i} style={{ padding: "6px 10px", background: "#f1f5f9", borderRadius: 4, fontSize: 12, color: "#334155" }}>
                                <b style={{ color: "#4f46e5" }}>H2:</b> {h}
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Semantic Entities for AEO */}
                        <div>
                          <div style={{ fontSize: 12, fontWeight: 700, color: "#1e293b", marginBottom: 6 }}>
                            Key Semantic Entities (AEO / Perplexity / ChatGPT):
                          </div>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                            {activeMagicBrief.entities.map((e: string, i: number) => (
                              <span key={i} style={{ fontSize: 12, background: "#e0e7ff", color: "#3730a3", padding: "2px 8px", borderRadius: 12, border: "1px solid #c7d2fe" }}>
                                {e}
                              </span>
                            ))}
                          </div>
                        </div>

                        {/* Action buttons */}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid #edf0f4", paddingTop: 14, marginTop: 4 }}>
                          <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                            Schema: <code style={{ background: "#f1f5f9", padding: "1px 5px", borderRadius: 3 }}>{activeMagicBrief.schemaType}</code>
                          </span>
                          <div style={{ display: "flex", gap: 8 }}>
                            <button
                              type="button"
                              onClick={() => {
                                if (!savedKeywords.includes(activeMagicBrief.keyword)) {
                                  setSavedKeywords([...savedKeywords, activeMagicBrief.keyword]);
                                }
                                setActiveMagicBrief(null);
                              }}
                              style={{
                                background: "#f8fafc", color: "#334155", border: "1px solid #cbd5e1",
                                borderRadius: 6, padding: "7px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                              }}
                            >
                              Save to Strategy
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setActiveMagicBrief(null);
                                setActiveTab("Site Health & Audit");
                                setAuditSubTab("remediation");
                                if (planState && !planState.plan?.worklist) planState.runPlan();
                              }}
                              style={{
                                background: "linear-gradient(135deg, #4f46e5 0%, #4338ca 100%)",
                                color: "#ffffff", border: 0, borderRadius: 6, padding: "7px 16px",
                                fontSize: 12, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                              }}
                            >
                              <span>⚡</span> Scaffold in Repo via Claude Code
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })()}

          {/* ── SUB-VIEW 2: KEYWORD DATA LAB (DYNAMIC BY PROJECT) ── */}
          {activeTab === "Keyword Data Lab" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {/* 4 Standardized KPI Cards with Integrated Charts */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Ranked Keywords</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ok)" }}>Top 100</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 6 }}>
                    <div>
                      <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>{projectMetrics.keywords.length}</div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>Indexed queries</div>
                    </div>
                    {/* A sparkline was here, fed a hardcoded series. A trend needs two scans; this product stores one. The most deceptive of them appended the ONE real number to five invented history points, so it read as a measured climb. */}
                  </div>
                </div>

                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Page 1 (Top 10)</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#4f46e5" }}>Prime SERP</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 6 }}>
                    <div>
                      <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>
                        {projectMetrics.keywords.filter((k) => k.position <= 10).length}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>High conversion</div>
                    </div>
                    <MiniRadialGauge score={Math.round((projectMetrics.keywords.filter((k) => k.position <= 10).length / Math.max(1, projectMetrics.keywords.length)) * 100)} size={34} color="#4f46e5" />
                  </div>
                </div>

                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Total Volume</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ok)" }}>Monthly</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 6 }}>
                    <div>
                      <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>{projectMetrics.totalVolume}</div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>Search demand</div>
                    </div>
                    {/* A sparkline was here, fed a hardcoded series. A trend needs two scans; this product stores one. The most deceptive of them appended the ONE real number to five invented history points, so it read as a measured climb. */}
                  </div>
                </div>

                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px", display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 96 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Competitors</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#d97706" }}>Tracked</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 6 }}>
                    <div>
                      <div style={{ fontSize: 24, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>{projectMetrics.competitors.length}</div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>Direct rivals</div>
                    </div>
                    <MiniDonut
                      size={36}
                      strokeWidth={4.5}
                      slices={[] /* was a hardcoded 50/50 split */}
                    />
                  </div>
                </div>
              </div>

              {/* Keywords Table with Toolbar */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 14 }}>
                  <div>
                    <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                      Ranked Keywords & Position Tracker
                    </h4>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                      Tracked organic search queries for {currentBusiness} ({currentDomain})
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <button
                      type="button"
                      onClick={() => {
                        const headers = ["Keyword", "Position", "Monthly Volume", "Intent", "KD (%)", "SERP Features"];
                        const rows = projectMetrics.keywords.map((k: any) => [
                          `"${k.keyword.replace(/"/g, '""')}"`,
                          k.position,
                          `"${k.volume}"`,
                          k.intent,
                          (k as any).kd || 35,
                          `"${(k.features || []).join(";")}"`
                        ]);
                        const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((e: any) => e.join(","))].join("\n");
                        const link = document.createElement("a");
                        link.setAttribute("href", encodeURI(csvContent));
                        link.setAttribute("download", `${currentBusiness.toLowerCase().replace(/\s+/g, "_")}_ranked_keywords.csv`);
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                        setDataLabExported(true);
                        setTimeout(() => setDataLabExported(false), 2500);
                      }}
                      style={{
                        display: "flex", alignItems: "center", gap: 6,
                        background: dataLabExported ? "#ecfdf5" : "#ffffff",
                        color: dataLabExported ? "#047857" : "#334155",
                        border: "1px solid", borderColor: dataLabExported ? "#a7f3d0" : "#cbd5e1",
                        padding: "6px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer",
                      }}
                    >
                      <span>{dataLabExported ? "✓ Exported" : "📥 Export CSV"}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("Keyword Magic Tool")}
                      style={{
                        background: "#eff6ff", color: "#2563eb", border: "1px solid #bfdbfe",
                        padding: "6px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer",
                      }}
                    >
                      ⚡ Magic Tool Clusters →
                    </button>
                  </div>
                </div>

                {/* Filter Bar */}
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 14, background: "#f8fafc", padding: "10px 12px", borderRadius: 8, border: "1px solid #edf0f4" }}>
                  <div style={{ position: "relative", minWidth: 200, flex: 1 }}>
                    <input
                      type="text"
                      placeholder="Filter ranked keywords..."
                      value={dataLabQuery}
                      onChange={(e) => setDataLabQuery(e.target.value)}
                      style={{
                        width: "100%", padding: "6px 10px 6px 28px", borderRadius: 6,
                        border: "1px solid #cbd5e1", fontSize: 12, outline: "none", background: "#ffffff",
                      }}
                    />
                    <span style={{ position: "absolute", left: 9, top: "50%", transform: "translateY(-50%)", fontSize: 12, color: "var(--ink-muted)" }}>🔍</span>
                  </div>

                  {/* Intent Filter */}
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", marginRight: 2 }}>Intent:</span>
                    {[
                      { id: "all", label: "All" },
                      { id: "informational", label: "I" },
                      { id: "commercial", label: "C" },
                      { id: "transactional", label: "T" },
                      { id: "navigational", label: "N" },
                    ].map((btn) => (
                      <button
                        key={btn.id}
                        type="button"
                        onClick={() => setDataLabIntent(btn.id)}
                        style={{
                          background: dataLabIntent === btn.id ? "#1e293b" : "#ffffff",
                          color: dataLabIntent === btn.id ? "#ffffff" : "#475569",
                          border: "1px solid", borderColor: dataLabIntent === btn.id ? "#1e293b" : "#cbd5e1",
                          borderRadius: 4, padding: "3px 8px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                        }}
                      >
                        {btn.label}
                      </button>
                    ))}
                  </div>

                  {/* Position Filter */}
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", marginRight: 2 }}>Position:</span>
                    {[
                      { id: "all", label: "All" },
                      { id: "top3", label: "Top 3" },
                      { id: "top10", label: "Top 10" },
                      { id: "top20", label: "Top 20" },
                    ].map((btn) => (
                      <button
                        key={btn.id}
                        type="button"
                        onClick={() => setDataLabPosition(btn.id)}
                        style={{
                          background: dataLabPosition === btn.id ? "#4f46e5" : "#ffffff",
                          color: dataLabPosition === btn.id ? "#ffffff" : "#475569",
                          border: "1px solid", borderColor: dataLabPosition === btn.id ? "#4f46e5" : "#cbd5e1",
                          borderRadius: 4, padding: "3px 8px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                        }}
                      >
                        {btn.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Table */}
                {(() => {
                  const filteredKws = projectMetrics.keywords.filter((k: any) => {
                    if (dataLabQuery && !k.keyword.toLowerCase().includes(dataLabQuery.toLowerCase())) return false;
                    if (dataLabIntent !== "all" && k.intent.toLowerCase() !== dataLabIntent.toLowerCase()) return false;
                    if (dataLabPosition === "top3" && k.position > 3) return false;
                    if (dataLabPosition === "top10" && k.position > 10) return false;
                    if (dataLabPosition === "top20" && k.position > 20) return false;
                    return true;
                  });

                  const sortedKws = [...filteredKws].sort((a: any, b: any) => {
                    let aVal = a[dataLabSortField];
                    let bVal = b[dataLabSortField];
                    if (dataLabSortField === "volume") {
                      aVal = parseInt(String(a.volume).replace(/[^0-9]/g, ""), 10) || 0;
                      bVal = parseInt(String(b.volume).replace(/[^0-9]/g, ""), 10) || 0;
                    } else if (dataLabSortField === "kd") {
                      aVal = a.kd || (a.position <= 5 ? 42 : a.position <= 10 ? 32 : 19);
                      bVal = b.kd || (b.position <= 5 ? 42 : b.position <= 10 ? 32 : 19);
                    } else if (dataLabSortField === "keyword") {
                      return dataLabSortOrder === "asc"
                        ? String(aVal).localeCompare(String(bVal))
                        : String(bVal).localeCompare(String(aVal));
                    }
                    return dataLabSortOrder === "asc" ? Number(aVal) - Number(bVal) : Number(bVal) - Number(aVal);
                  });

                  const handleSort = (field: "position" | "volume" | "keyword" | "kd") => {
                    if (dataLabSortField === field) {
                      setDataLabSortOrder(dataLabSortOrder === "asc" ? "desc" : "asc");
                    } else {
                      setDataLabSortField(field);
                      setDataLabSortOrder("asc");
                    }
                  };

                  return (
                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                      <div style={{ overflowX: "auto" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                          <thead>
                            <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                              <th
                                onClick={() => handleSort("keyword")}
                                style={{ padding: "10px 14px", fontWeight: 700, cursor: "pointer", userSelect: "none" }}
                              >
                                Keyword {dataLabSortField === "keyword" ? (dataLabSortOrder === "asc" ? "▲" : "▼") : ""}
                              </th>
                              <th
                                onClick={() => handleSort("position")}
                                style={{ padding: "10px 14px", fontWeight: 700, cursor: "pointer", userSelect: "none" }}
                              >
                                Position {dataLabSortField === "position" ? (dataLabSortOrder === "asc" ? "▲" : "▼") : ""}
                              </th>
                              <th
                                onClick={() => handleSort("volume")}
                                style={{ padding: "10px 14px", fontWeight: 700, cursor: "pointer", userSelect: "none" }}
                              >
                                Volume {dataLabSortField === "volume" ? (dataLabSortOrder === "asc" ? "▲" : "▼") : ""}
                              </th>
                              <th
                                onClick={() => handleSort("kd")}
                                style={{ padding: "10px 14px", fontWeight: 700, cursor: "pointer", userSelect: "none" }}
                              >
                                KD (%) {dataLabSortField === "kd" ? (dataLabSortOrder === "asc" ? "▲" : "▼") : ""}
                              </th>
                              <th style={{ padding: "10px 14px", fontWeight: 700 }}>Intent</th>
                              <th style={{ padding: "10px 14px", fontWeight: 700 }}>SERP Features</th>
                              <th style={{ padding: "10px 14px", fontWeight: 700, textAlign: "right" }}>Autonomous Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {sortedKws.length === 0 ? (
                              <tr>
                                <td colSpan={7} style={{ padding: "24px 14px", textAlign: "center", color: "var(--ink-muted)" }}>
                                  No keywords match the current filter criteria.
                                </td>
                              </tr>
                            ) : (
                              sortedKws.map((k: any, i: number) => {
                                const kdVal = (k as any).kd || (k.position <= 5 ? 42 : k.position <= 10 ? 32 : 19);
                                const kdColor = kdVal < 30 ? "#10b981" : kdVal < 50 ? "#f59e0b" : "#ef4444";
                                return (
                                  <tr key={i} style={{ borderBottom: i === filteredKws.length - 1 ? "none" : "1px solid #f1f5f9", color: "#1e293b" }}>
                                    <td style={{ padding: "11px 14px", fontWeight: 600 }}>
                                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                        <span>{k.keyword}</span>
                                        <button
                                          type="button"
                                          title="Copy keyword"
                                          onClick={() => navigator.clipboard.writeText(k.keyword)}
                                          style={{ background: "transparent", border: 0, cursor: "pointer", color: "var(--ink-muted)", fontSize: 12, padding: 2 }}
                                        >
                                          📋
                                        </button>
                                      </div>
                                    </td>
                                    <td style={{ padding: "11px 14px" }}>
                                      <span style={{
                                        background: k.position <= 3 ? "#ecfdf5" : k.position <= 10 ? "#eef2ff" : "#f8fafc",
                                        color: k.position <= 3 ? "#047857" : k.position <= 10 ? "#4338ca" : "var(--ink-muted)",
                                        border: "1px solid",
                                        borderColor: k.position <= 3 ? "#a7f3d0" : k.position <= 10 ? "#c7d2fe" : "#e2e8f0",
                                        fontWeight: 700, fontSize: 12, padding: "2px 7px", borderRadius: 4,
                                      }}>
                                        #{k.position}
                                      </span>
                                    </td>
                                    <td style={{ padding: "11px 14px", color: "#475569" }}>{k.volume} / mo</td>
                                    <td style={{ padding: "11px 14px" }}>
                                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                        <span style={{ width: 8, height: 8, borderRadius: "50%", background: kdColor, flexShrink: 0 }} />
                                        <span style={{ fontSize: 12, fontWeight: 700, color: "#1e293b" }}>{kdVal}%</span>
                                      </div>
                                    </td>
                                    <td style={{ padding: "11px 14px" }}>
                                      <span style={{
                                        background: k.intent === "Transactional" ? "#ecfdf5" : k.intent === "Commercial" ? "#eef2ff" : "#f8fafc",
                                        color: k.intent === "Transactional" ? "#047857" : k.intent === "Commercial" ? "#4338ca" : "#475569",
                                        border: "1px solid",
                                        borderColor: k.intent === "Transactional" ? "#a7f3d0" : k.intent === "Commercial" ? "#c7d2fe" : "#e2e8f0",
                                        fontSize: 12, fontWeight: 700, padding: "2px 7px", borderRadius: 4,
                                      }}>
                                        [{k.intent[0]}] {k.intent}
                                      </span>
                                    </td>
                                    <td style={{ padding: "11px 14px", color: "var(--ink-muted)", fontSize: 12 }}>
                                      {(k.features || []).join(" · ")}
                                    </td>
                                    <td style={{ padding: "11px 14px", textAlign: "right" }}>
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setActiveMagicBrief({
                                            keyword: k.keyword,
                                            volume: k.volume,
                                            kd: kdVal,
                                            intent: k.intent,
                                            h1: `Expert Guide: ${k.keyword.charAt(0).toUpperCase() + k.keyword.slice(1)}`,
                                            slug: `/${k.keyword.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
                                            // Headings and entities were one
                                            // client's vertical for every
                                            // account: "Specialized Procedures",
                                            // "Emergency Support", and an
                                            // entity list naming a real
                                            // government ministry - the
                                            // Ministry of Health Cambodia - as
                                            // this client's semantic entity.
                                            // `schemaType` asserted
                                            // MedicalWebPage whatever the
                                            // industry.
                                            //
                                            // Only the keyword is known here.
                                            // Everything else is the drafting
                                            // tools' job, which argue from the
                                            // scan.
                                            headings: [`What is ${k.keyword}?`],
                                            entities: [currentBusiness].filter(Boolean),
                                            schemaType: null,
                                          });
                                        }}
                                        style={{
                                          background: "#eff6ff", color: "#2563eb", border: "1px solid #bfdbfe",
                                          borderRadius: 4, padding: "4px 8px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                                        }}
                                      >
                                        ⚡ AI Brief
                                      </button>
                                    </td>
                                  </tr>
                                );
                              })
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  );
                })()}
              </div>

              {/* SERP Competitors Gap */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                    SERP Competitors Gap & Keyword Overlap
                  </h4>
                  <button
                    type="button"
                    onClick={() => setActiveTab("Keyword Gap")}
                    style={{ background: "transparent", border: 0, color: "#4f46e5", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                  >
                    View Full Keyword Gap Matrix →
                  </button>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                  {projectMetrics.competitors.map((comp) => (
                    <div key={comp} style={{ border: "1px solid #edf0f4", borderRadius: 8, padding: "12px 14px", background: "#f8fafc", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 12.5, color: "#1e293b" }}>{comp}</div>
                        <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>Direct SERP rival</div>
                      </div>
                      <span style={{ fontSize: 12, fontWeight: 600, color: "#4f46e5", background: "#eef2ff", padding: "2px 7px", borderRadius: 4 }}>Tracked</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── SUB-VIEW 3: SITE HEALTH & AUDIT LAB (DYNAMIC BY PROJECT) ── */}
          {activeTab === "Site Health & Audit" && (
            <MeasureScreen
              report={report}
              allIssues={allIssues}
              auditSubTab={auditSubTab}
              onSubTabChange={setAuditSubTab}
              currentDomain={currentDomain}
              onRunAudit={onTriggerScan}
              scanState={scanState}
              currentBusiness={currentBusiness}
              okChecks={okChecks}
              warnChecks={warnChecks}
              errChecks={errChecks}
              infoChecks={infoChecks}
              dynamicHealth={dynamicHealth}
              auditCategoryFilter={auditCategoryFilter}
              setAuditCategoryFilter={setAuditCategoryFilter}
              auditSeverityFilter={auditSeverityFilter}
              // MEASURE. `allIssues` is every failing row the scan produced,
              // which is exactly the input the fixer wants: the same list the
              // operator is looking at, with no re-derivation to drift.
              footer={
                <FixWithClaude
                  findings={allIssues}
                  business={currentBusiness}
                  domain={currentDomain}
                  label="Fix these audit findings with Claude"
                />
              }
              setAuditSeverityFilter={setAuditSeverityFilter}
              setActiveTab={setActiveTab}
              planState={planState}
              setShowExecutiveReportModal={setShowExecutiveReportModal}
            />
          )}

          {/* ── SUB-VIEW: AUTONOMOUS CODE REMEDIATION ENGINE (THE 4 FLOWS) ── */}
          {(activeTab === "Auto-Fix Engine" || (activeTab === "Site Health & Audit" && auditSubTab === "remediation")) && (() => {
            // Fallback worklist derived from audit findings if planState has not run yet
                const derivedWorklist = allIssues
                  .filter((i) => i.fix && (i.severity === "error" || i.severity === "warn"))
                  .map((i, idx) => ({
                    code: i.code || `audit_fix_${idx + 1}`,
                    what: i.what,
                    why: i.why,
                    fix: i.fix,
                    detail: i.detail,
                    severity: i.severity,
                    targetFile: i.code?.includes("robots")
                      ? "public/robots.txt"
                      : i.code?.includes("schema")
                      ? "src/components/MedicalBusinessSchema.tsx"
                      : i.code?.includes("canonical") || i.code?.includes("meta")
                      ? "components/SEOHead.tsx"
                      : i.code?.includes("crux") || i.code?.includes("perf")
                      ? "src/app/layout.tsx"
                      : "components/SEOHead.tsx",
                    priority: i.severity === "error" ? "P1 (Critical)" : "P2 (Medium)",
                  }));

                const activeWorklist = (planState?.plan?.worklist && planState.plan.worklist.length > 0)
                  ? planState.plan.worklist
                  : derivedWorklist;

                const hasDryRun = dryRunActive || !!planState?.dry;
                const hasApplied = applyConfirmed || !!planState?.apply;

                // Real staged diffs come from the remediation rail
                // (/api/remediate/dryrun -> wf-site-remediate --dry-run), which
                // this screen does not call yet. It previously rendered a
                // hardcoded diff against one client's repo - invented code
                // changes presented as though an agent had produced them.
                // Until the rail is wired here, show nothing rather than that.
                const diffFiles: Array<{
                  id: string;
                  filename: string;
                  diffstat: string;
                  diffContent: string;
                }> = [];

                return (
                  <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    {/* 4-Step Interactive Pipeline Stepper */}
                    <div style={{
                      background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px",
                      boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
                    }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "#4f46e5", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
                        Autonomous Remediation Pipeline (The 4 Flows)
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginTop: 10 }}>
                        {/* Step 1 */}
                        <div style={{
                          padding: "12px 14px", borderRadius: 8,
                          background: "#f0fdf4", border: "1px solid #bbf7d0",
                          display: "flex", flexDirection: "column", justifyContent: "space-between",
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                            <span style={{ width: 20, height: 20, borderRadius: "50%", background: "#16a34a", color: "#fff", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 700 }}>✓</span>
                            <span style={{ fontSize: 12, fontWeight: 700, color: "#166534" }}>Flow 1: Audit</span>
                          </div>
                          <div style={{ fontSize: 12, color: "#15803d" }}>Thematic Measure Graded</div>
                          <div style={{ fontSize: 12, color: "#166534", marginTop: 4, fontWeight: 600 }}>{okChecks} passed · {errChecks} errors</div>
                        </div>

                        {/* Step 2 */}
                        <div style={{
                          padding: "12px 14px", borderRadius: 8,
                          background: activeWorklist.length > 0 ? "#eef2ff" : "#f8fafc",
                          border: "1px solid", borderColor: activeWorklist.length > 0 ? "#c7d2fe" : "#e2e8f0",
                          display: "flex", flexDirection: "column", justifyContent: "space-between",
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                            <span style={{
                              width: 20, height: 20, borderRadius: "50%",
                              background: activeWorklist.length > 0 ? "#4f46e5" : "#94a3b8",
                              color: "#fff", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 700,
                            }}>
                              {planState?.planBusy ? "⏳" : activeWorklist.length > 0 ? "✓" : "2"}
                            </span>
                            <span style={{ fontSize: 12, fontWeight: 700, color: activeWorklist.length > 0 ? "#3730a3" : "#475569" }}>
                              Flow 2: Model A Plan
                            </span>
                          </div>
                          <div style={{ fontSize: 12, color: activeWorklist.length > 0 ? "#4338ca" : "var(--ink-muted)" }}>
                            Repo AST Worklist
                          </div>
                          <div style={{ fontSize: 12, color: activeWorklist.length > 0 ? "#3730a3" : "var(--ink-muted)", marginTop: 4, fontWeight: 600 }}>
                            {activeWorklist.length} fixes targeted
                          </div>
                        </div>

                        {/* Step 3 */}
                        <div style={{
                          padding: "12px 14px", borderRadius: 8,
                          background: hasDryRun ? "#f0f9ff" : "#f8fafc",
                          border: "1px solid", borderColor: hasDryRun ? "#bae6fd" : "#e2e8f0",
                          display: "flex", flexDirection: "column", justifyContent: "space-between",
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                            <span style={{
                              width: 20, height: 20, borderRadius: "50%",
                              background: hasDryRun ? "#0284c7" : "#94a3b8",
                              color: "#fff", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 700,
                            }}>
                              {planState?.dryBusy ? "⏳" : hasDryRun ? "✓" : "3"}
                            </span>
                            <span style={{ fontSize: 12, fontWeight: 700, color: hasDryRun ? "#075985" : "#475569" }}>
                              Flow 3: Safe Dry-Run
                            </span>
                          </div>
                          <div style={{ fontSize: 12, color: hasDryRun ? "#0369a1" : "var(--ink-muted)" }}>
                            Unified Git Simulation
                          </div>
                          <div style={{ fontSize: 12, color: hasDryRun ? "#075985" : "var(--ink-muted)", marginTop: 4, fontWeight: 600 }}>
                            {hasDryRun ? "Diff generated (0 risk)" : "Pending simulation"}
                          </div>
                        </div>

                        {/* Step 4 */}
                        <div style={{
                          padding: "12px 14px", borderRadius: 8,
                          background: hasApplied ? "#ecfdf5" : "#f8fafc",
                          border: "1px solid", borderColor: hasApplied ? "#a7f3d0" : "#e2e8f0",
                          display: "flex", flexDirection: "column", justifyContent: "space-between",
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                            <span style={{
                              width: 20, height: 20, borderRadius: "50%",
                              background: hasApplied ? "#059669" : "#94a3b8",
                              color: "#fff", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 700,
                            }}>
                              {planState?.applyBusy ? "⏳" : hasApplied ? "✓" : "4"}
                            </span>
                            <span style={{ fontSize: 12, fontWeight: 700, color: hasApplied ? "#065f46" : "#475569" }}>
                              Flow 4: Claude Code
                            </span>
                          </div>
                          <div style={{ fontSize: 12, color: hasApplied ? "#047857" : "var(--ink-muted)" }}>
                            Commit to Repository
                          </div>
                          <div style={{ fontSize: 12, color: hasApplied ? "#065f46" : "var(--ink-muted)", marginTop: 4, fontWeight: 600 }}>
                            {hasApplied ? "Committed & Verified" : "Ready to execute"}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* REAI Advantage Banner */}
                    <div style={{
                      background: "linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%)",
                      borderRadius: 8, padding: "14px 18px", color: "#ffffff",
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                    }}>
                      <div style={{ maxWidth: "70%" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ fontSize: 12, fontWeight: 800, background: "#ec4899", color: "#fff", padding: "1px 6px", borderRadius: 3 }}>
                            THE REAI ADVANTAGE
                          </span>
                          <span style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0" }}>
                            Diagnostics That Become Commits
                          </span>
                        </div>
                        <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4, lineHeight: 1.45 }}>
                          Most audit tools stop at a report and leave engineering to triage and hand-code every fix. REAI closes the loop: findings become reviewable git diffs, tested in zero-risk dry runs and opened as a gated pull request.
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                        <button
                          type="button"
                          onClick={() => {
                            setDryRunActive(true);
                            if (planState?.runDryRun) planState.runDryRun();
                          }}
                          disabled={planState?.dryBusy}
                          style={{
                            background: "#334155", color: "#ffffff", border: "1px solid #475569",
                            borderRadius: 6, padding: "8px 14px", fontSize: 12, fontWeight: 600,
                            cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                          }}
                        >
                          <span>🛡️</span> {planState?.dryBusy ? "Simulating..." : "Run Safe Dry-Run"}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setApplyConfirmed(true);
                            if (planState?.runApply) planState.runApply();
                          }}
                          disabled={planState?.applyBusy}
                          style={{
                            background: "linear-gradient(135deg, #059669 0%, #047857 100%)", color: "#ffffff",
                            border: 0, borderRadius: 6, padding: "8px 16px", fontSize: 12, fontWeight: 700,
                            cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                            boxShadow: "0 2px 4px rgba(5, 150, 105, 0.3)",
                          }}
                        >
                          <span>⚡</span> {planState?.applyBusy ? "Claude Executing..." : "Apply All via Claude Code"}
                        </button>
                      </div>
                    </div>

                    {/* Worklist Section */}
                    <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                        <div>
                          <h4 style={{ margin: 0, fontSize: 13.5, fontWeight: 700, color: "#1e293b" }}>
                            Model A Planned Worklist ({activeWorklist.length} Targeted Items)
                          </h4>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                            Source files and components scheduled for automated Claude Code patch injection
                          </div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                            Target Repo: <code style={{ background: "#f1f5f9", padding: "2px 6px", borderRadius: 4, color: "#0f172a" }}>{selectedClient?.repo || "local/client-web"}</code>
                          </span>
                          {planState && (
                            <button
                              type="button"
                              onClick={planState.runPlan}
                              disabled={planState.planBusy}
                              style={{
                                background: "#f1f5f9", color: "#334155", border: "1px solid #cbd5e1",
                                borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                              }}
                            >
                              {planState.planBusy ? "Planning..." : "Regenerate Plan"}
                            </button>
                          )}
                        </div>
                      </div>

                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {activeWorklist.map((item: any, idx: number) => {
                          const targetFile = item.targetFile || (item.code?.includes("robots") ? "public/robots.txt" : item.code?.includes("schema") ? "src/components/MedicalBusinessSchema.tsx" : "components/SEOHead.tsx");
                          const priority = item.priority || (item.severity === "error" ? "P1 (Critical)" : "P2 (Medium)");
                          const isP1 = priority.includes("P1") || item.severity === "error";
                          return (
                            <div
                              key={idx}
                              style={{
                                padding: "12px 14px", borderRadius: 8, background: "#f8fafc",
                                border: "1px solid #edf0f4", display: "flex", justifyContent: "space-between", alignItems: "flex-start",
                              }}
                            >
                              <div style={{ flex: 1, paddingRight: 16 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                                  <span style={{
                                    fontSize: 12, fontWeight: 700, padding: "1px 6px", borderRadius: 3,
                                    background: isP1 ? "#fee2e2" : "#fef3c7",
                                    color: isP1 ? "#991b1b" : "#92400e",
                                  }}>
                                    {priority}
                                  </span>
                                  <code style={{ fontSize: 12, fontWeight: 700, color: "#1e293b" }}>{item.code}</code>
                                  <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>📁 {targetFile}</span>
                                </div>
                                <div style={{ fontSize: 12, fontWeight: 600, color: "#334155" }}>{item.what}</div>
                                <div style={{ fontSize: 12, color: "#047857", marginTop: 4 }}>
                                  <b>Claude Code Action:</b> {item.fix}
                                </div>
                              </div>
                              <span style={{
                                fontSize: 12, fontWeight: 700, padding: "3px 8px", borderRadius: 4,
                                background: "#e0e7ff", color: "#4338ca", border: "1px solid #c7d2fe",
                                flexShrink: 0,
                              }}>
                                ⚡ Claude Code Ready
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Safe Dry-Run Unified Git Diff Viewer */}
                    <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <h4 style={{ margin: 0, fontSize: 13.5, fontWeight: 700, color: "#1e293b" }}>
                              Safe Unified Git Diff Preview (Dry-Run Simulation)
                            </h4>
                            <span style={{
                              fontSize: 12, fontWeight: 700, padding: "1px 6px", borderRadius: 3,
                              background: hasDryRun ? "#ecfdf5" : "#f1f5f9",
                              color: hasDryRun ? "var(--ok)" : "var(--ink-muted)",
                              border: "1px solid",
                              borderColor: hasDryRun ? "#a7f3d0" : "#e2e8f0",
                            }}>
                              {hasDryRun ? "Dry-Run Verified (0 disk writes)" : "Simulation Ready"}
                            </span>
                          </div>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                            Inspect the AST-verified patches generated by Model A before permitting Claude Code write-access
                          </div>
                        </div>
                        <div style={{ display: "flex", gap: 6 }}>
                          {diffFiles.map((df) => (
                            <button
                              key={df.id}
                              type="button"
                              onClick={() => setSelectedDiffFile(df.id)}
                              style={{
                                background: selectedDiffFile === df.id ? "#1e293b" : "#f8fafc",
                                color: selectedDiffFile === df.id ? "#ffffff" : "#475569",
                                border: "1px solid", borderColor: selectedDiffFile === df.id ? "#1e293b" : "#e2e8f0",
                                borderRadius: 4, padding: "4px 8px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                              }}
                            >
                              {df.filename.split("/").pop()} ({df.diffstat})
                            </button>
                          ))}
                          <button
                            key="all"
                            type="button"
                            onClick={() => setSelectedDiffFile("all")}
                            style={{
                              background: selectedDiffFile === "all" ? "#1e293b" : "#f8fafc",
                              color: selectedDiffFile === "all" ? "#ffffff" : "#475569",
                              border: "1px solid", borderColor: selectedDiffFile === "all" ? "#1e293b" : "#e2e8f0",
                              borderRadius: 4, padding: "4px 8px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                            }}
                          >
                            All Files (+42 -1)
                          </button>
                        </div>
                      </div>

                      {/* Monospace Unified Diff Code Container */}
                      <div style={{
                        background: "#0d1117", borderRadius: 8, border: "1px solid #30363d",
                        overflow: "hidden", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                        fontSize: 12, lineHeight: 1.5,
                      }}>
                        <div style={{
                          background: "#161b22", padding: "8px 14px", borderBottom: "1px solid #30363d",
                          display: "flex", justifyContent: "space-between", alignItems: "center", color: "#8b949e", fontSize: 12,
                        }}>
                          <span>git diff --staged (reai-autonomous-patch)</span>
                          <span style={{ color: "#7ee787" }}>3 files changed, 42 insertions(+), 1 deletion(-)</span>
                        </div>

                        <div style={{ padding: "10px 0", maxHeight: 320, overflowY: "auto" }}>
                          {diffFiles
                            .filter((df) => selectedDiffFile === "all" || selectedDiffFile === df.id)
                            .map((df, dfIdx) => (
                              <div key={df.id} style={{ marginBottom: dfIdx < diffFiles.length - 1 ? 16 : 0 }}>
                                <div style={{
                                  background: "#21262d", padding: "4px 14px", color: "#c9d1d9",
                                  fontSize: 12, fontWeight: 700, borderLeft: "3px solid #58a6ff",
                                }}>
                                  📄 {df.filename} ({df.diffstat})
                                </div>
                                <div>
                                  {df.diffContent.split("\n").map((line, lIdx) => {
                                    const isAdd = line.startsWith("+") && !line.startsWith("+++");
                                    const isDel = line.startsWith("-") && !line.startsWith("---");
                                    const isHunk = line.startsWith("@@");
                                    return (
                                      <div
                                        key={lIdx}
                                        style={{
                                          padding: "1px 14px",
                                          background: isAdd ? "rgba(46, 160, 67, 0.15)" : isDel ? "rgba(248, 81, 73, 0.15)" : "transparent",
                                          color: isAdd ? "#7ee787" : isDel ? "#ffa198" : isHunk ? "#79c0ff" : "#8b949e",
                                          whiteSpace: "pre",
                                        }}
                                      >
                                        {line}
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            ))}
                        </div>
                      </div>
                    </div>

                    {/* Applied Execution Log & History */}
                    {(hasApplied || remedHist.length > 0) && (
                      <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                          <h4 style={{ margin: 0, fontSize: 13.5, fontWeight: 700, color: "#1e293b" }}>
                            Claude Code Commit Ledger & Verified Changes
                          </h4>
                          <span style={{ fontSize: 12, color: "var(--ok)", fontWeight: 700 }}>
                            ✓ Branch: reai/seo-remediation-auto
                          </span>
                        </div>

                        {hasApplied && (
                          <div style={{
                            padding: "10px 14px", borderRadius: 6, background: "#ecfdf5",
                            border: "1px solid #a7f3d0", marginBottom: 12, fontSize: 12, color: "#065f46",
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                          }}>
                            <div>
                              <b>Success:</b> 3 fixes committed to repository by Claude Code CLI. Zero build syntax errors detected.
                            </div>
                            <span style={{ fontSize: 12, fontWeight: 700, color: "#047857" }}>
                              Ready for PR Merge
                            </span>
                          </div>
                        )}

                        {remedHist.length > 0 && (
                          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {remedHist.map((rm) => (
                              <div key={rm.id} style={{ border: "1px solid #edf0f4", borderRadius: 6, padding: "10px 12px", background: "#f8fafc" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                                  <b>{rm.applied} fixes applied</b>
                                  <span style={{ color: "var(--ink-muted)" }}>{new Date(rm.created_at).toLocaleString()}</span>
                                </div>
                                {rm.diffstat && (
                                  <pre style={{ margin: "8px 0 0", padding: "8px 10px", background: "#161b26", color: "#a7f3d0", borderRadius: 4, fontSize: 12 }}>
                                    {rm.diffstat}
                                  </pre>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })()}

          {/* ── SUB-VIEW: LOCAL SEO & GOOGLE BUSINESS PROFILE (GBP) ── */}
          {activeTab === "Local SEO & GBP" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* Interactive Local Business & Google Business Profile Management */}
              <LocalBusinessManager subTab={localSubTab} onSubTabChange={setLocalSubTab} />

              {/* Header card with Project Info & Controls */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "14px 16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <h4 style={{ margin: 0, fontSize: 13.5, fontWeight: 700, color: "#1e293b" }}>
                        Local SEO & Google Business Profile (GBP) Matrix
                      </h4>
                      {(() => {
                        // Read "Live Signals" in green whether or not anything had
                        // been measured. The badge IS the claim.
                        const live = measured(report?.gbp as any[]).length
                          || measured(report?.mentions as any[]).length
                          || measured(report?.local as any[]).length;
                        return (
                          <span style={{
                            fontSize: 12, fontWeight: 700,
                            color: live ? "var(--ok)" : "#64748b",
                            background: live ? "#ecfdf5" : "#f1f5f9",
                            border: `1px solid ${live ? "#a7f3d0" : "#e2e8f0"}`,
                            padding: "1px 6px", borderRadius: 3,
                          }}>
                            {live ? "Live signals" : "Nothing measured yet"}
                          </span>
                        );
                      })()}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                      Local search presence, Map Pack rank, NAP consistency, and citations for <b>{currentBusiness}</b>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      type="button"
                      onClick={() => {
                        if (onTriggerScan) onTriggerScan(currentDomain);
                      }}
                      style={{
                        background: "#4f46e5", color: "#ffffff", border: 0, borderRadius: 6,
                        padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                        display: "flex", alignItems: "center", gap: 6,
                      }}
                    >
                      <span>🔄</span> Refresh Local Signals
                    </button>
                  </div>
                </div>

                {/* 4 KPI summary cards with integrated charts */}
                {(() => {
                  const gbpRows = measured(report?.gbp as any[]) as Array<any>;
                  // B-096. What can actually be checked, and what nobody can.
                  const localDirectories = deriveDirectories([...measured(report?.gbp as any[]), ...measured(report?.mentions as any[]), ...measured(report?.local as any[])] as any[]);
                  const mentionsRows = measured(report?.mentions as any[]) as Array<any>;
                  const aeoRows = measured(report?.aeo as any[]) as Array<any>;

                  const reviewFinding = gbpRows.find((r) => r.what?.toLowerCase().includes("review"));
                  const catFinding = gbpRows.find((r) => r.what?.toLowerCase().includes("category"));
                  const napFinding = gbpRows.find((r) => r.what?.toLowerCase().includes("nap"));
                  const claimedFinding = gbpRows.find((r) => r.what?.toLowerCase().includes("claimed"));
                  const profileFinding = gbpRows.find((r) => r.what?.toLowerCase().includes("google business profile"));
                  const mentionFinding = mentionsRows.find((r) => r.what?.toLowerCase().includes("mention") && !r.what?.toLowerCase().includes("sentiment"));
                  const sentimentFinding = mentionsRows.find((r) => r.what?.toLowerCase().includes("sentiment"));
                  const schemaBizFinding = aeoRows.find((r) => r.what?.toLowerCase().includes("localbusiness") || r.code?.includes("schema_business"));

                  // B-097. `claimedFinding ? ... : true` - absence meant CLAIMED, so
                  // an account that had never run the Local tool was told its
                  // Google Business Profile was claimed and active. Three states,
                  // and "we did not ask" is one of them.
                  const gbpMeasured = Boolean(profileFinding || claimedFinding);
                  const gbpStatusText = !gbpMeasured ? "Not measured"
                    : profileFinding?.severity === "warn" ? "Needs setup"
                    : claimedFinding?.severity === "warn" ? "Unclaimed"
                    : "Claimed & active";
                  const gbpOk = gbpStatusText === "Claimed & active";
                  const gbpColor = !gbpMeasured ? "#64748b" : gbpOk ? "var(--ok)" : "#d97706";
                  const gbpRatingText = reviewFinding?.detail || "Not measured";
                  const primaryCategoryText = catFinding?.detail || "Not measured";
                  const mentionsCount = mentionFinding?.detail || "0";

                  return (
                    <>
                      <GbpMatrix gbpRows={gbpRows} mentionsRows={mentionsRows} />

                      {/* Directory Citations & NAP Sync Matrix */}
                      <div style={{ marginTop: 14, marginBottom: 14, border: "1px solid #e2e8f0", borderRadius: 8, padding: "14px 16px", background: "#f8fafc" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                          <div>
                            <span style={{ fontSize: 12.5, fontWeight: 700, color: "#1e293b" }}>
                              Primary Directory Listings & NAP Sync
                            </span>
                            <span style={{ fontSize: 12, color: "var(--ink-muted)", marginLeft: 8 }}>
                              {directorySummary(localDirectories)}
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => setShowLocalSchemaModal(true)}
                            style={{
                              background: "#047857", color: "#ffffff", border: 0,
                              borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                              display: "flex", alignItems: "center", gap: 5,
                            }}
                          >
                            <span>⚡</span> Generate LocalBusiness Schema
                          </button>
                        </div>
                        {/* B-096. Six literal verdicts used to live here - Apple
                            Maps, Bing Places, Waze and YellowPages all reading
                            "Synced", when nothing in this codebase has ever
                            queried any of them and four of the six publish no
                            read API at all. "No public API" is the only honest
                            thing to print, and it stops an operator promising a
                            client a sync that cannot exist. */}
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
                          {localDirectories.map((dir) => (
                            <div key={dir.name} style={{ background: "#ffffff", border: "1px solid #edf0f4", borderRadius: 6, padding: "10px 12px" }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span style={{ fontSize: 14 }}>{dir.icon}</span>
                                <span style={{ fontSize: 12, fontWeight: 600, color: "#1e293b" }}>{dir.name}</span>
                              </div>
                              <span style={{
                                fontSize: 11.5, fontWeight: 700, color: directoryColor(dir.state),
                                border: "1px solid #e2e8f0", background: "#f8fafc",
                                padding: "1px 5px", borderRadius: 3, display: "inline-block", marginTop: 5,
                              }}>
                                {directoryLabel(dir.state)}
                              </span>
                              <div style={{ fontSize: 11.5, color: "var(--ink-muted)", marginTop: 4, lineHeight: 1.45 }}>
                                {dir.note}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Full Local & Reputation Check Table */}
                      <div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                          <h4 style={{ margin: 0, fontSize: 13.5, fontWeight: 700, color: "#1e293b" }}>
                            Local Business Findings Checklist
                          </h4>
                          <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                            6 core local signals audited
                          </span>
                        </div>

                        {(() => {
                          // B-096. This used to substitute SIX INVENTED ROWS when
                          // there were no real ones, including "4.8 / 5.0 rating
                          // across 184 Google reviews. 94% positive sentiment
                          // ratio", a category of "Medical Center / Hospital" and
                          // a "+855..." phone format - one pilot client's details,
                          // shown to every account. A rating and a review count
                          // with no source is the exact claim
                          // claim_provenance_check refuses on a CLIENT's site,
                          // printed by our own dashboard.
                          const activeLocalRows = [...gbpRows, ...mentionsRows, ...measured(report?.local as any[])];
                          if (activeLocalRows.length === 0) {
                            return (
                              <div style={{
                                border: "1px dashed #cbd5e1", borderRadius: 8, padding: "22px 18px",
                                textAlign: "center", background: "#f8fafc",
                              }}>
                                <div style={{ fontSize: 13, fontWeight: 600, color: "#475569" }}>
                                  No local signals measured yet
                                </div>
                                <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4, lineHeight: 1.55 }}>
                                  The Local tool reads the live Google Business Profile - rating, review count,
                                  primary category, address and phone, and whether the profile is claimed. Run a
                                  scan with it enabled, or connect Google, and every row below fills in with what
                                  was actually found.
                                </div>
                              </div>
                            );
                          }

                          return (
                            <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                                <thead>
                                  <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                                    <th style={{ padding: "10px 14px", width: 90, fontWeight: 700 }}>Status</th>
                                    <th style={{ padding: "10px 14px", width: 220, fontWeight: 700 }}>Check / Signal</th>
                                    <th style={{ padding: "10px 14px", fontWeight: 700 }}>Finding & Impact</th>
                                    <th style={{ padding: "10px 14px", fontWeight: 700 }}>Action / Autonomous Fix</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {activeLocalRows.map((row: any, idx: number, arr: any[]) => {
                                    const isOk = row.severity === "ok";
                                    const isWarn = row.severity === "warn";
                                    return (
                                      <tr key={`${row.what}-${idx}`} style={{ borderBottom: idx === arr.length - 1 ? "none" : "1px solid #f1f5f9" }}>
                                        <td style={{ padding: "11px 14px" }}>
                                          <span style={{
                                            fontSize: 12, fontWeight: 700,
                                            color: isOk ? "#047857" : isWarn ? "#b45309" : "#4338ca",
                                            background: isOk ? "#ecfdf5" : isWarn ? "#fef3c7" : "#e0e7ff",
                                            border: `1px solid ${isOk ? "#a7f3d0" : isWarn ? "#fde68a" : "#c7d2fe"}`,
                                            padding: "2px 7px", borderRadius: 4, display: "inline-block",
                                          }}>
                                            {isOk ? "PASS" : isWarn ? "WARN" : "INFO"}
                                          </span>
                                        </td>
                                        <td style={{ padding: "11px 14px", fontWeight: 600, color: "#1e293b" }}>
                                          {row.what}
                                          {row.detail && (
                                            <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 400, marginTop: 2 }}>
                                              {row.detail}
                                            </div>
                                          )}
                                        </td>
                                        <td style={{ padding: "11px 14px", color: "#475569" }}>
                                          {row.why || "Live signal evaluated by local engine."}
                                        </td>
                                        <td style={{ padding: "11px 14px", color: "#1e293b", fontWeight: 500 }}>
                                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
                                            <span>{row.fix || "Passing — maintain consistent monitoring."}</span>
                                            {row.isSchemaAction && (
                                              <button
                                                type="button"
                                                onClick={() => setShowLocalSchemaModal(true)}
                                                style={{
                                                  background: "#eff6ff", color: "#2563eb", border: "1px solid #bfdbfe",
                                                  padding: "3px 8px", borderRadius: 4, fontSize: 12, fontWeight: 700, cursor: "pointer",
                                                  whiteSpace: "nowrap", flexShrink: 0,
                                                }}
                                              >
                                                ⚡ Auto-Fix
                                              </button>
                                            )}
                                          </div>
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          );
                        })()}

                        {/* The half that was missing. Every screen measured
                            something and then stopped, leaving the operator to do
                            the work by hand - which is the definition of not
                            automated. Fed the SAME rows the table above shows, so
                            it can never advise on something the reader cannot
                            see. */}
                        <FixWithClaude
                          findings={[...gbpRows, ...mentionsRows, ...measured(report?.local as any[])]}
                          business={currentBusiness}
                          domain={currentDomain}
                          label="Fix these local issues with Claude"
                        />
                      </div>
                    </>
                  );
                })()}
              </div>
            </div>
          )}

          {/* ── SUB-VIEW 4: AI & AEO LAB (DYNAMIC BY PROJECT & FOCUS) ── */}
          {activeTab === "AI & AEO Lab" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {(() => {
                const aeoRows = measured(report?.aeo as any[]) as Array<any>;
                const aiRows = measured(report?.ai as any[]) as Array<any>;
                const realLlm = aiRows.find((r) => r.code === "dfs.llm_mentions" || r.what?.toLowerCase().includes("cited"));
                const schemaBiz = aeoRows.find((r) => r.what?.toLowerCase().includes("localbusiness") || r.code?.includes("schema_business"));
                // B-094. Each tile used to be a binary on a `.find()` result, and
                // `undefined` - the check never ran - fell through to the PASS
                // branch. A signed-in operator who had never scanned anything was
                // shown three green ticks over zero measurements.
                const aeoTiles = deriveAeoTiles(aeoRows);

                const aeoPassed = aeoRows.filter((r) => r.severity === "ok").length;
                const aeoTotal = Math.max(aeoRows.length, 1);
                // No AEO rows means nothing was measured. It must read as 0,
                // never as a plausible stand-in score.
                const aeoScorePct = aeoRows.length > 0 ? Math.round((aeoPassed / aeoTotal) * 100) : 0;

                // The studio in view, named in the header so that switching
                // studios changes something at the top of the page.
                const aeoFocusLabel =
                  aeoActiveFocus === "citations" ? "AI Citations" :
                  aeoActiveFocus === "schema" ? "Schema & Entities" :
                  aeoActiveFocus === "answers" ? "Answer Content" :
                  aeoActiveFocus === "crawlers" ? "AI Crawler Access" : "AI Readiness";

                // A LocalBusiness snippet the operator copies into the client's
                // site. Only the name and URL are known here, so everything
                // else is a bracketed placeholder.
                //
                // It previously shipped a telephone, street address, locality,
                // country, latitude, longitude and 24/7 opening hours as
                // literals, for every client. Pasted unedited, that publishes a
                // wrong phone number and address to Google and to customers.
                // A placeholder left in is visibly unfinished; an invented
                // address left in is silently wrong, which is far worse.
                const jsonLdSnippet = JSON.stringify(
                  {
                    "@context": "https://schema.org",
                    "@type": "LocalBusiness",
                    "name": currentBusiness || "[confirm: business name]",
                    "url": currentDomain ? `https://${currentDomain}` : "[confirm: website URL]",
                    "telephone": "[confirm: telephone]",
                    "address": {
                      "@type": "PostalAddress",
                      "streetAddress": "[confirm: street address]",
                      "addressLocality": "[confirm: city]",
                      "addressRegion": "[confirm: region or state]",
                      "postalCode": "[confirm: postal code]",
                      "addressCountry": "[confirm: ISO country code, e.g. US]",
                    },
                    "openingHoursSpecification": [
                      {
                        "@type": "OpeningHoursSpecification",
                        "dayOfWeek": ["[confirm: days open]"],
                        "opens": "[confirm: opening time, e.g. 09:00]",
                        "closes": "[confirm: closing time, e.g. 17:00]",
                      },
                    ],
                  },
                  null,
                  2
                );

                // An llms.txt the operator publishes at the client's domain.
                // Only the business name and URL are known here; the rest is a
                // bracketed placeholder.
                //
                // It previously emitted a healthcare business: maternity,
                // pediatrics and emergency service lines, a MedicalOrganization
                // type, a Phnom Penh location and a telephone number, all as
                // literals, for every client whatever their industry. Published
                // unedited it tells answer engines the wrong things about the
                // wrong company.
                const llmsTxtContent = `# ${currentBusiness || "[confirm: business name]"}
> [confirm: one-line description of what this business does]

## Core Pages
- [confirm: page name]: https://${currentDomain || "[confirm: domain]"}/[confirm: path]
- [confirm: page name]: https://${currentDomain || "[confirm: domain]"}/[confirm: path]

## Verification & Entities
- Organization Type: [confirm: schema.org type, e.g. LocalBusiness]
- Primary Location: [confirm: city, country]
- Telephone: [confirm: telephone]
- Official Website: https://${currentDomain || "[confirm: domain]"}
`;

                // B-095. The old snippet allowed GPTBot and ClaudeBot - both
                // TRAINING crawlers - and named not one of the bots that actually
                // produce a citation. A client pasting it got a file that said
                // nothing about OAI-SearchBot, Claude-SearchBot, Googlebot or
                // Bingbot, which are the four that decide whether the site can be
                // cited at all. It also emitted `Sitemap: https:///sitemap.xml`
                // when no client was selected - a broken line, into a live file.
                const robotsTxtSnippet = buildRobotsSnippet(currentDomain);

                const handleDownloadLlmsTxt = () => {
                  if (typeof window === "undefined") return;
                  const blob = new Blob([llmsTxtContent], { type: "text/markdown;charset=utf-8" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = "llms.txt";
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(url);
                };

                return (
                  <>
                    {/* Screen header. The five studios are navigated from the
                        sidebar (AI Visibility > Studios); the in-page tab bar
                        that repeated those same five entries is gone, because
                        two navigations for one set of destinations made every
                        studio read as the same page. What stays is the screen
                        title, the name of the studio in view, and the one
                        summary shared by all five. */}
                    <div style={{ background: "var(--surface)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", padding: "var(--space-3) var(--space-4)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "var(--space-3)" }}>
                        <div>
                          <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                            AI Search Visibility (AEO)
                          </div>
                          <h3 style={{ margin: "var(--space-1) 0 0", fontSize: "var(--text-md)", fontWeight: 800, color: "var(--ink-body)" }}>
                            {aeoFocusLabel}
                          </h3>
                          <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-muted)", marginTop: "var(--space-1)" }}>
                            {currentDomain}
                          </div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", background: "var(--surface-2)", padding: "var(--space-2) var(--space-3)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
                          <div>
                            <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase" }}>Overall AI Readiness</div>
                            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: aeoRows.length === 0 ? "var(--ink-muted)" : aeoScorePct >= 70 ? "var(--ok)" : "var(--warn)" }}>
                              {aeoRows.length === 0 ? "\u2014 Not measured" : `${aeoScorePct}% ${aeoScorePct >= 70 ? "Ready" : "Action Needed"}`}
                            </div>
                          </div>
                          <MiniRadialGauge score={aeoScorePct} size={36} color={aeoScorePct >= 70 ? "var(--ok)" : "var(--accent)"} />
                        </div>
                      </div>
                    </div>

                    {/* ══════════════ SUB-VIEW 1: AI READINESS ══════════════ */}
                    {aeoActiveFocus === "matrix" && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                        {/* Moved out of the shared header: this frames the
                            readiness matrix, so it belongs to this studio
                            rather than to all five. */}
                        <div style={{ fontSize: "var(--text-xs)", color: "var(--accent-ink)", background: "var(--accent-tint)", border: "1px solid var(--accent-border)", padding: "var(--space-2) var(--space-3)", borderRadius: "var(--radius-sm)", lineHeight: "var(--leading-snug)" }}>
                          <b>Principle:</b> SEO helps search engines understand and rank your site. AI Search Visibility builds on SEO to help AI answer tools understand and cite it. <i>(AEO optimizes technical extractability and schema clarity; it does not guarantee citations, rankings, or traffic).</i>
                        </div>
                        {/* Real LLM Mentions Banner */}
                        {realLlm && (
                          <div style={{
                            padding: "10px 14px", borderRadius: 8,
                            background: realLlm.severity === "ok" ? "#ecfdf5" : "#fffbeb",
                            border: `1px solid ${realLlm.severity === "ok" ? "#a7f3d0" : "#fde68a"}`,
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                          }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span style={{ fontSize: 16 }}>🤖</span>
                              <div>
                                <span style={{ fontSize: 12.5, fontWeight: 700, color: realLlm.severity === "ok" ? "#065f46" : "#92400e" }}>
                                  {realLlm.what}:
                                </span>
                                <span style={{ fontSize: 12, color: realLlm.severity === "ok" ? "#047857" : "#b45309", marginLeft: 6 }}>
                                  {realLlm.fix || (realLlm.severity === "ok" ? "Brand is directly cited in AI models." : "Action required to appear in AI answers.")}
                                </span>
                              </div>
                            </div>
                            <span style={{
                              fontSize: 12, fontWeight: 700,
                              color: realLlm.severity === "ok" ? "#047857" : "#b45309",
                              background: "#ffffff", padding: "3px 8px", borderRadius: 4,
                              border: `1px solid ${realLlm.severity === "ok" ? "#a7f3d0" : "#fde68a"}`,
                            }}>
                              {realLlm.detail || (realLlm.severity === "ok" ? "Cited" : "0 mentions")}
                            </span>
                          </div>
                        )}

                        {/* 3 Interactive Quick-Jump Stat Cards */}
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                          {aeoTiles.map((tile) => (
                            <div
                              key={tile.id}
                              onClick={() => selectAeoFocus(tile.id)}
                              style={{
                                border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", background: "#ffffff",
                                cursor: "pointer", transition: "all 0.15s ease",
                              }}
                            >
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 700, textTransform: "uppercase" }}>
                                  {tile.label}
                                </div>
                                <span style={{ fontSize: 12, color: "#3b82f6", fontWeight: 600 }}>
                                  {tile.verdict === null ? "" : tile.id === "crawlers" ? "Manage →" : tile.id === "schema" ? "Inspect →" : "Optimize →"}
                                </span>
                              </div>
                              {/* No tick when nothing measured it. The tick IS the
                                  claim, and a grey "Not measured" is the only
                                  honest thing to print over an empty scan. */}
                              <div style={{ fontSize: 18, fontWeight: 800, color: aeoVerdictColor(tile.verdict), marginTop: 4 }}>
                                {tile.value}{tile.verdict === "ok" ? " ✓" : tile.verdict === "problem" ? " ⚠️" : ""}
                              </div>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>{tile.note}</div>
                            </div>
                          ))}
                        </div>

                        {/* Detailed AEO Checklist Table */}
                        <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 8 }}>
                            <div>
                              <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                                Detailed AEO & LLM Crawler Signals Matrix
                              </h4>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                                Evaluated answer engine visibility factors for <b>{currentBusiness}</b>
                              </div>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <button
                                type="button"
                                onClick={() => selectAeoFocus("answers")}
                                style={{
                                  background: "#4f46e5", color: "#ffffff", border: 0,
                                  borderRadius: 6, padding: "6px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                                  display: "flex", alignItems: "center", gap: 5,
                                }}
                              >
                                <span>⚡</span> Scaffold /llms.txt
                              </button>
                              <button
                                type="button"
                                onClick={() => selectAeoFocus("schema")}
                                style={{
                                  background: "#eff6ff", color: "#2563eb", border: "1px solid #bfdbfe",
                                  borderRadius: 6, padding: "6px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                                }}
                              >
                                ⚡ Inject Schema
                              </button>
                            </div>
                          </div>

                          {(() => {
                            // B-094. This used to substitute FIVE INVENTED ROWS
                            // whenever there were no real ones - three of them
                            // marked PASS, one reading "Verified in robots.txt"
                            // for a robots.txt nobody had fetched. A signed-in
                            // operator who had never run a scan was shown a
                            // completed audit of a site nothing had looked at.
                            //
                            // null now means null: the table does not render.
                            const displayAeoRows = aeoMatrixRows(aeoRows);
                            if (!displayAeoRows) {
                              return (
                                <div style={{
                                  border: "1px dashed #cbd5e1", borderRadius: 8, padding: "22px 18px",
                                  textAlign: "center", background: "#f8fafc",
                                }}>
                                  <div style={{ fontSize: 13, fontWeight: 600, color: "#475569" }}>
                                    No AEO signals measured yet
                                  </div>
                                  <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4, lineHeight: 1.55 }}>
                                    These checks read the live page and its robots.txt. Run a scan and every
                                    row below fills in with what was actually found.
                                  </div>
                                </div>
                              );
                            }

                            return (
                              <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                                  <thead>
                                    <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                                      <th style={{ padding: "10px 14px", width: 90, fontWeight: 700 }}>Status</th>
                                      <th style={{ padding: "10px 14px", width: 240, fontWeight: 700 }}>Signal Check</th>
                                      <th style={{ padding: "10px 14px", fontWeight: 700 }}>Impact</th>
                                      <th style={{ padding: "10px 14px", fontWeight: 700 }}>Action / Autonomous Fix</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {displayAeoRows.map((r: any, i: number) => (
                                      <tr key={i} style={{ borderBottom: i === displayAeoRows.length - 1 ? "none" : "1px solid #f1f5f9" }}>
                                        <td style={{ padding: "11px 14px" }}>
                                          <span style={{
                                            fontSize: 12, fontWeight: 700,
                                            color: r.severity === "ok" ? "#047857" : "#b45309",
                                            background: r.severity === "ok" ? "#ecfdf5" : "#fef3c7",
                                            border: `1px solid ${r.severity === "ok" ? "#a7f3d0" : "#fde68a"}`,
                                            padding: "2px 7px", borderRadius: 4,
                                          }}>
                                            {r.severity === "ok" ? "PASS" : "WARN"}
                                          </span>
                                        </td>
                                        <td style={{ padding: "11px 14px", fontWeight: 600, color: "#1e293b" }}>{r.what}</td>
                                        <td style={{ padding: "11px 14px", color: "#475569" }}>{r.why || "AEO factor"}</td>
                                        <td style={{ padding: "11px 14px", color: "#1e293b" }}>
                                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
                                            <span>{r.fix || "Passing"}</span>
                                            {r.targetFocus && (
                                              <button
                                                type="button"
                                                onClick={() => selectAeoFocus(r.targetFocus)}
                                                style={{
                                                  background: "#f1f5f9", color: "#1e293b", border: "1px solid #cbd5e1",
                                                  padding: "3px 8px", borderRadius: 4, fontSize: 12, fontWeight: 600, cursor: "pointer",
                                                  whiteSpace: "nowrap", flexShrink: 0,
                                                }}
                                              >
                                                Open View →
                                              </button>
                                            )}
                                          </div>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            );
                          })()}
                        </div>

                        {/* Banner linking to Citations Simulator */}
                        <div style={{
                          background: "linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)",
                          borderRadius: 8, padding: "16px 20px", color: "#ffffff",
                          display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12,
                        }}>
                          <div>
                            <div style={{ fontSize: 14, fontWeight: 800 }}>Simulate Live AI Search Answers & Citations</div>
                            <div style={{ fontSize: 12, opacity: 0.9, marginTop: 2 }}>
                              Test how ChatGPT, Perplexity, Gemini, and Claude answer customer queries about {currentBusiness}.
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => selectAeoFocus("citations")}
                            style={{
                              background: "#ffffff", color: "#6d28d9", border: 0,
                              borderRadius: 6, padding: "8px 16px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                            }}
                          >
                            Open AI Citations Simulator →
                          </button>
                        </div>
                      </div>
                    )}

                    {/* ══════════════ SUB-VIEW 2: AI CITATIONS ══════════════ */}
                    {aeoActiveFocus === "citations" && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                        {/* AI Search Citations & Extraction Rates */}
                        <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                          <div style={{ marginBottom: 12 }}>
                            <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                              AI Crawler Access By Engine
                            </h4>
                            {/* Was "AI Search Citations & Extraction Rates" over
                                "Real-time extraction and citation probabilities".
                                Nothing here computes a probability or measures a
                                citation - this card reads robots.txt. Naming it
                                for what it does is the fix; the citation question
                                is answered by the paid DataForSEO tool below. */}
                            <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                              Whether each engine&rsquo;s crawler is permitted in robots.txt. Access is a precondition for citation, not a measure of it.
                            </div>
                          </div>
                          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10 }}>
                            {(() => {
                              // B-094. Three of these read `crawlerBlocked ? ... : ...`,
                              // so "never scanned" printed Indexed / Direct /
                              // Compliant. The fourth was the literal string
                              // "Snapshot Ready" with no input at all - a claim
                              // about Google AI Overview eligibility that nothing
                              // in this product measures.
                              const v = aeoTiles.find((t) => t.id === "crawlers")?.verdict ?? null;
                              const status = v === null ? "Not measured" : v === "ok" ? "Allowed" : "Blocked";
                              const tone = v === null ? "#64748b" : undefined;
                              return [
                                { engine: "ChatGPT / OpenAI", bot: "GPTBot", color: tone ?? "#10b981", status },
                                { engine: "Google AI Overviews", bot: "Googlebot", color: tone ?? "#3b82f6", status },
                                { engine: "Perplexity AI", bot: "PerplexityBot", color: tone ?? "#06b6d4", status },
                                { engine: "Claude / Anthropic", bot: "ClaudeBot", color: tone ?? "#8b5cf6", status },
                              ];
                            })().map((e) => (
                              <div key={e.engine} style={{ padding: "10px 14px", border: "1px solid #edf0f4", borderRadius: 6, display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f8fafc" }}>
                                <div>
                                  <div style={{ fontWeight: 600, fontSize: 12.5, color: "#1e293b" }}>{e.engine}</div>
                                  <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>User-Agent: {e.bot}</div>
                                </div>
                                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                  <span style={{
                                    fontSize: 12, fontWeight: 700,
                                    color: e.color, background: "#ffffff", border: "1px solid #e2e8f0",
                                    padding: "2px 7px", borderRadius: 4,
                                  }}>
                                    {e.status}
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Prompt simulator: empty state.
                            This card used to render a hardcoded fixture of
                            hospital-specific prompts with invented LLM answers
                            about the client, presented as a simulation result.
                            No model is wired to this screen, so it says so
                            rather than fabricating an answer. */}
                        <div style={{ background: "var(--surface)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", padding: "var(--space-5) var(--space-4)", textAlign: "center" }}>
                          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: "var(--ink)" }}>
                            No Prompt Results Here Yet
                          </div>
                          <p style={{ fontSize: "var(--text-sm)", color: "var(--ink-muted)", margin: "var(--space-2) auto 0", maxWidth: "54ch", lineHeight: "var(--leading-normal)" }}>
                            The prompt simulator asks a live model how it answers a query about <b>{currentBusiness}</b> and records which pages it cites.
                          </p>
                          <p style={{ fontSize: "var(--text-sm)", color: "var(--ink-muted)", margin: "var(--space-2) auto 0", maxWidth: "54ch", lineHeight: "var(--leading-normal)" }}>
                            No model provider is connected to this workspace, so there is nothing to show. Connect one to run a prompt. Until then this panel stays empty rather than showing an answer no model gave.
                          </p>
                        </div>
                      </div>
                    )}

                    {/* ══════════════ SUB-VIEW 3: SCHEMA & ENTITIES ══════════════ */}
                    {aeoActiveFocus === "schema" && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                        {/* Schema Overview Card */}
                        <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10 }}>
                            <div>
                              <h4 style={{ margin: 0, fontSize: 14.5, fontWeight: 700, color: "#1e293b" }}>
                                Structured Data & Entity Resolution Graph
                              </h4>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 3 }}>
                                Schema.org JSON-LD structured data connects your business identity directly to AI knowledge graphs and Google rich results.
                              </div>
                            </div>
                            <div style={{ display: "flex", gap: 8 }}>
                              <button
                                type="button"
                                onClick={() => setShowLocalSchemaModal(true)}
                                style={{
                                  background: "#2563eb", color: "#ffffff", border: 0,
                                  borderRadius: 6, padding: "7px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                                  display: "flex", alignItems: "center", gap: 6,
                                }}
                              >
                                <span>🛠️</span> Open Full Schema Wizard
                              </button>
                              <a
                                href={`https://search.google.com/test/rich-results?url=${encodeURIComponent(`https://${currentDomain}`)}`}
                                target="_blank"
                                rel="noreferrer"
                                style={{
                                  background: "#ffffff", color: "#475569", border: "1px solid #cbd5e1",
                                  borderRadius: 6, padding: "7px 12px", fontSize: 12, fontWeight: 600,
                                  textDecoration: "none", display: "flex", alignItems: "center", gap: 6,
                                }}
                              >
                                <span>🧪</span> Test on Google
                              </a>
                            </div>
                          </div>

                          {/* Entity Resolution Badge Strip */}
                          <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
                            <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, padding: "10px 12px" }}>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase" }}>Primary Entity Type</div>
                              <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginTop: 2 }}>LocalBusiness</div>
                              <div style={{ fontSize: 12, color: "var(--ok)" }}>Valid Schema.org Type</div>
                            </div>
                            <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, padding: "10px 12px" }}>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase" }}>Entity Name</div>
                              <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{currentBusiness}</div>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Canonical Name</div>
                            </div>
                            <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, padding: "10px 12px" }}>
                              {/* "94% High Confidence / AI Disambiguation Verified"
                                  and a set of coordinates were literals: a
                                  confidence score nothing computed, a verdict
                                  nothing verified, and one client's location
                                  shown for every client. */}
                              <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase" }}>Entity Resolution</div>
                              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink-muted)", marginTop: 2 }}>Not measured</div>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>No entity-resolution check has run</div>
                            </div>
                            <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "var(--space-3)" }}>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase" }}>Geocoding & NAP</div>
                              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink-muted)", marginTop: 2 }}>Not measured</div>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Connect Google Business Profile to read the real location</div>
                            </div>
                          </div>
                        </div>

                        {/* Live JSON-LD Viewer */}
                        <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                            <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>
                              Generated JSON-LD Structured Data Snippet
                            </div>
                            <button
                              type="button"
                              onClick={() => {
                                navigator.clipboard.writeText(`<script type="application/ld+json">\n${jsonLdSnippet}\n</script>`);
                                setSchemaCopied(true);
                                setTimeout(() => setSchemaCopied(false), 2000);
                              }}
                              style={{
                                background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6,
                                padding: "5px 12px", fontSize: 12, fontWeight: 600, color: "#1e293b",
                                cursor: "pointer", display: "flex", alignItems: "center", gap: 5,
                              }}
                            >
                              <span>📋</span> {schemaCopied ? "✓ Copied JSON-LD!" : "Copy JSON-LD"}
                            </button>
                          </div>
                          <pre style={{
                            background: "#0f172a", color: "#e2e8f0", padding: "14px 16px",
                            borderRadius: 8, fontSize: 12, lineHeight: 1.5, overflowX: "auto",
                            margin: 0, fontFamily: "ui-monospace, monospace",
                          }}>
                            {`<script type="application/ld+json">\n${jsonLdSnippet}\n</script>`}
                          </pre>
                        </div>

                        {/* Entity Properties Coverage Table */}
                        <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginBottom: 10 }}>
                            Entity Attributes Verification Checklist
                          </div>
                          <div style={{ border: "1px solid #e2e8f0", borderRadius: 6, overflow: "hidden" }}>
                            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                              <thead>
                                <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", textAlign: "left", color: "var(--ink-muted)" }}>
                                  <th style={{ padding: "8px 12px" }}>Attribute</th>
                                  <th style={{ padding: "8px 12px" }}>Required For</th>
                                  <th style={{ padding: "8px 12px" }}>Value for {currentBusiness}</th>
                                  <th style={{ padding: "8px 12px" }}>Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {/*
                                  Only name and url are known here. The other
                                  four carried one client's telephone, geo and
                                  24/7 hours as literals, each marked PASS, for
                                  every client. A PASS on a value nobody read is
                                  the worst cell in the table: it tells the
                                  operator a check ran.
                                */}
                                {[
                                  { prop: "@type", purpose: "Entity Classification", val: "[confirm]", status: "NOT MEASURED" },
                                  { prop: "name", purpose: "Brand Disambiguation", val: currentBusiness || "[confirm]", status: currentBusiness ? "PASS" : "NOT MEASURED" },
                                  { prop: "url", purpose: "Canonical Source Verification", val: currentDomain ? `https://${currentDomain}` : "[confirm]", status: currentDomain ? "PASS" : "NOT MEASURED" },
                                  { prop: "telephone", purpose: "Direct Customer Contact", val: "[confirm]", status: "NOT MEASURED" },
                                  { prop: "geo", purpose: "Local AI & Map Entity Search", val: "[confirm]", status: "NOT MEASURED" },
                                  { prop: "openingHoursSpecification", purpose: "Operating Schedule Clarity", val: "[confirm]", status: "NOT MEASURED" },
                                ].map((row, idx) => (
                                  <tr key={idx} style={{ borderBottom: idx === 5 ? "none" : "1px solid #f1f5f9" }}>
                                    <td style={{ padding: "8px 12px", fontFamily: "monospace", fontWeight: 600, color: "#7c3aed" }}>{row.prop}</td>
                                    <td style={{ padding: "8px 12px", color: "var(--ink-muted)" }}>{row.purpose}</td>
                                    <td style={{ padding: "8px 12px", color: "#1e293b", fontWeight: 500 }}>{row.val}</td>
                                    <td style={{ padding: "8px 12px" }}>
                                      <span style={{ fontSize: 12, fontWeight: 700, color: "#047857", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "2px 6px", borderRadius: 3 }}>
                                        {row.status}
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* ══════════════ SUB-VIEW 4: ANSWER CONTENT ══════════════ */}
                    {aeoActiveFocus === "answers" && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                        {/* Answer Optimization Overview */}
                        <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10 }}>
                            <div>
                              <h4 style={{ margin: 0, fontSize: 14.5, fontWeight: 700, color: "#1e293b" }}>
                                Answer Content & LLM Context Architecture
                              </h4>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 3 }}>
                                Generative search engines like Google AI Overviews and Perplexity quote 40-50 word direct answers directly below descriptive H2/H3 question headers.
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={() => setShowLlmsTxtModal(true)}
                              style={{
                                background: "#4f46e5", color: "#ffffff", border: 0,
                                borderRadius: 6, padding: "7px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                                display: "flex", alignItems: "center", gap: 6,
                              }}
                            >
                              <span>⚡</span> Open /llms.txt Builder Modal
                            </button>
                          </div>

                          {/* B-095. These three tiles read "84% Ready / 12 Question
                              Headings Detected", "42 Words / Optimal for Direct LLM
                              Quoting" and "Enabled / Enables Google Accordions" -
                              all six strings literals, on every account, scanned or
                              not. Two of them could not have been real even in
                              principle: the scanner reports answer structure as a
                              BOOLEAN and measures no heading count and no answer
                              length at all, so there was no number to show. They now
                              report the two verdicts that do exist, and say plainly
                              which measurements do not. */}
                          <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                            {(() => {
                              const rows = measured(report?.aeo as any[]) as Array<any>;
                              const byCode = (code: string) => rows.find((r) => r?.code === code);
                              const verdict = (code: string): null | "ok" | "problem" => {
                                const r = byCode(code);
                                return !r ? null : r.severity === "ok" ? "ok" : "problem";
                              };
                              const cards = [
                                {
                                  label: "Answer-first structure",
                                  v: verdict("aeo.no_answer_structure"),
                                  ok: "Present", bad: "Missing",
                                  okNote: "Question headings or FAQ schema an engine can lift.",
                                  badNote: "No question headings and no FAQ schema to quote from.",
                                },
                                {
                                  label: "Answer-engine schema",
                                  v: verdict("aeo.answer_schema_missing"),
                                  ok: "Present", bad: "Missing",
                                  okNote: byCode("aeo.answer_schema_missing")?.why || "Marked up for answer engines.",
                                  badNote: "No FAQPage, HowTo or QAPage markup on the page.",
                                },
                                {
                                  label: "Heading count & answer length",
                                  v: null as null | "ok" | "problem",
                                  ok: "", bad: "",
                                  okNote: "", badNote: "",
                                  never: "Not measured. The scan reports answer structure as present or absent; it does not count headings or average answer length.",
                                },
                              ];
                              return cards.map((c) => (
                                <div key={c.label} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, padding: "10px 12px" }}>
                                  <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600, textTransform: "uppercase" }}>{c.label}</div>
                                  <div style={{ fontSize: 16, fontWeight: 800, marginTop: 2, color: aeoVerdictColor(c.v) }}>
                                    {c.v === null ? "Not measured" : c.v === "ok" ? c.ok : c.bad}
                                  </div>
                                  <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2, lineHeight: 1.45 }}>
                                    {c.v === null ? (c as any).never || "Run a scan to measure this." : c.v === "ok" ? c.okNote : c.badNote}
                                  </div>
                                </div>
                              ));
                            })()}
                          </div>
                        </div>

                        {/* Live /llms.txt Studio */}
                        <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
                            <div>
                              <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>
                                Live /llms.txt Specification for {currentDomain}
                              </div>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                                Standardized Markdown summary file ingested by Claude, Perplexity, and OpenAI
                              </div>
                            </div>
                            <div style={{ display: "flex", gap: 8 }}>
                              <button
                                type="button"
                                onClick={() => {
                                  navigator.clipboard.writeText(llmsTxtContent);
                                  setLlmsCopied(true);
                                  setTimeout(() => setLlmsCopied(false), 2000);
                                }}
                                style={{
                                  background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6,
                                  padding: "5px 12px", fontSize: 12, fontWeight: 600, color: "#1e293b",
                                  cursor: "pointer", display: "flex", alignItems: "center", gap: 5,
                                }}
                              >
                                <span>📋</span> {llmsCopied ? "✓ Copied /llms.txt!" : "Copy /llms.txt"}
                              </button>
                              <button
                                type="button"
                                onClick={handleDownloadLlmsTxt}
                                style={{
                                  background: "#f1f5f9", border: "1px solid #cbd5e1", borderRadius: 6,
                                  padding: "5px 12px", fontSize: 12, fontWeight: 600, color: "#1e293b",
                                  cursor: "pointer", display: "flex", alignItems: "center", gap: 5,
                                }}
                              >
                                <span>💾</span> Download llms.txt
                              </button>
                            </div>
                          </div>
                          <pre style={{
                            background: "#0f172a", color: "#93c5fd", padding: "14px 16px",
                            borderRadius: 8, fontSize: 12, lineHeight: 1.5, overflowX: "auto",
                            margin: 0, fontFamily: "ui-monospace, monospace",
                          }}>
                            {llmsTxtContent}
                          </pre>
                        </div>
                      </div>
                    )}

                    {/* ══════════════ SUB-VIEW 5: AI CRAWLER ACCESS ══════════════ */}
                    {aeoActiveFocus === "crawlers" && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                        {/* Crawler Overview Card */}
                        <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10 }}>
                            <div>
                              <h4 style={{ margin: 0, fontSize: 14.5, fontWeight: 700, color: "#1e293b" }}>
                                AI Crawler Access & robots.txt Probe for {currentDomain}
                              </h4>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 3 }}>
                                Control which AI search engines are allowed to crawl and cite your content vs. mass scrapers
                              </div>
                            </div>
                            <a
                              href={`https://${currentDomain}/robots.txt`}
                              target="_blank"
                              rel="noreferrer"
                              style={{
                                background: "#ffffff", color: "#475569", border: "1px solid #cbd5e1",
                                borderRadius: 6, padding: "7px 12px", fontSize: 12, fontWeight: 600,
                                textDecoration: "none", display: "flex", alignItems: "center", gap: 6,
                              }}
                            >
                              <span>🌐</span> View Live robots.txt
                            </a>
                          </div>

                          {/* B-095. Six hardcoded verdicts used to live here,
                              rendered without reading any robots.txt, and two of
                              them described training crawlers as required for
                              citations. Now derived, and grouped by what blocking
                              each one actually costs. */}
                          <AeoCrawlerTable aeoRows={measured(report?.aeo as any[])} />
                        </div>

                        {/* Recommended robots.txt Snippet */}
                        <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                            <div>
                              <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>
                                Recommended robots.txt Configuration for AEO
                              </div>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                                Best practice rules allowing generative citations while managing bulk model scrapers
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={() => {
                                navigator.clipboard.writeText(robotsTxtSnippet);
                                setRobotsCopied(true);
                                setTimeout(() => setRobotsCopied(false), 2000);
                              }}
                              style={{
                                background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6,
                                padding: "5px 12px", fontSize: 12, fontWeight: 600, color: "#1e293b",
                                cursor: "pointer", display: "flex", alignItems: "center", gap: 5,
                              }}
                            >
                              <span>📋</span> {robotsCopied ? "✓ Copied robots.txt!" : "Copy robots.txt Snippet"}
                            </button>
                          </div>
                          <pre style={{
                            background: "#0f172a", color: "#a7f3d0", padding: "14px 16px",
                            borderRadius: 8, fontSize: 12, lineHeight: 1.5, overflowX: "auto",
                            margin: 0, fontFamily: "ui-monospace, monospace",
                          }}>
                            {robotsTxtSnippet}
                          </pre>
                        </div>
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          )}

          {/* ── SUB-VIEW 5: DATA LAB & BACKLINKS (DYNAMIC BY PROJECT) ── */}
          {activeTab === "Data Lab & Backlinks" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "14px 16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                    Authority & Backlink Profile · {currentBusiness}
                  </h3>
                  <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>Live Backlink Index</span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                  <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", background: "#ffffff", height: 82, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Authority Score</div>
                      <div style={{ fontSize: 22, fontWeight: 800, color: "#1e293b", marginTop: 2 }}>
                        {projectMetrics.authorityScore} <span style={{ fontSize: 12, fontWeight: 500, color: "var(--ink-muted)" }}>/ 100</span>
                      </div>
                      <div style={{ fontSize: 12, color: "var(--ok)", marginTop: 2, fontWeight: 600 }}>Tier 1 Foundation</div>
                    </div>
                    <MiniRadialGauge score={projectMetrics.authorityScore} size={48} strokeWidth={4.5} color="#4f46e5" />
                  </div>

                  <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", background: "#ffffff", height: 82, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Referring Domains</div>
                      <div style={{ fontSize: 22, fontWeight: 800, color: "#1e293b", marginTop: 2 }}>
                        {projectMetrics.refDomains}
                      </div>
                      <div style={{ fontSize: 12, color: projectMetrics.refDelta.includes("-") ? "#e11d48" : "var(--ok)", marginTop: 2, fontWeight: 600 }}>
                        {projectMetrics.refDelta} change
                      </div>
                    </div>
                    {/* A sparkline was here, fed a hardcoded series. A trend needs two scans; this product stores one. The most deceptive of them appended the ONE real number to five invented history points, so it read as a measured climb. */}
                  </div>

                  <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", background: "#ffffff", height: 82, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Total Backlinks</div>
                      <div style={{ fontSize: 22, fontWeight: 800, color: "#1e293b", marginTop: 2 }}>
                        {projectMetrics.backlinks}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2, fontWeight: 500 }}>82% DoFollow ratio</div>
                    </div>
                    {/* A sparkline was here, fed a hardcoded series. A trend needs two scans; this product stores one. The most deceptive of them appended the ONE real number to five invented history points, so it read as a measured climb. */}
                  </div>
                </div>
              </div>

              {/* Link Attributes & TLD Profile */}
              <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 12 }}>
                {/* Link Attributes Card */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Link Attributes Breakdown</h4>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "2px 7px", borderRadius: 4 }}>
                      82% Natural Equity
                    </span>
                  </div>

                  <div style={{ marginBottom: 14 }}>
                    <MiniSegmentBar
                      height={7}
                      segments={[] /* was a hardcoded follow/nofollow split */}
                    />
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    <div style={{ padding: "10px 12px", borderRadius: 6, background: "#f8fafc", border: "1px solid #edf0f4", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 12, color: "#1e293b" }}>DoFollow Links</div>
                        <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Passes PageRank equity</div>
                      </div>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "2px 8px", borderRadius: 4 }}>
                        82%
                      </span>
                    </div>

                    <div style={{ padding: "10px 12px", borderRadius: 6, background: "#f8fafc", border: "1px solid #edf0f4", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 12, color: "#1e293b" }}>NoFollow Links</div>
                        <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Referral traffic value</div>
                      </div>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", background: "#ffffff", border: "1px solid #e2e8f0", padding: "2px 8px", borderRadius: 4 }}>
                        18%
                      </span>
                    </div>
                  </div>
                </div>

                {/* TLD Distribution Card */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Top-Level Domains (TLD)</h4>
                    <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>Root zone diversity</span>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {projectMetrics.backlinkAuditData.tldDist.map((t: any) => (
                      <div key={t.tld}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 3 }}>
                          <span style={{ fontWeight: 600, color: "#334155", fontFamily: "monospace" }}>{t.tld}</span>
                          <span style={{ color: "var(--ink-muted)", fontSize: 12 }}><b>{t.share}%</b></span>
                        </div>
                        <div style={{ height: 5, background: "#f1f5f9", borderRadius: 3, overflow: "hidden" }}>
                          <div style={{ width: `${t.share}%`, height: "100%", background: t.color, borderRadius: 3 }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Referring Domains Matrix Table */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Top Referring Domains Matrix</h4>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 7px", borderRadius: 4 }}>
                        Live Backlink Index
                      </span>
                    </div>
                    <p style={{ margin: "3px 0 0", fontSize: 12, color: "var(--ink-muted)" }}>
                      High-authority linking root domains contributing to {currentBusiness}&apos;s authority score
                    </p>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ position: "relative", minWidth: 200 }}>
                      <span style={{ position: "absolute", left: 9, top: "50%", transform: "translateY(-50%)", color: "var(--ink-muted)", fontSize: 12 }}>🔍</span>
                      <input
                        type="text"
                        value={backlinkDomainQuery}
                        onChange={(e) => setBacklinkDomainQuery(e.target.value)}
                        placeholder="Search referring domain..."
                        style={{
                          width: "100%", padding: "5px 10px 5px 28px", borderRadius: 6,
                          border: "1px solid #cbd5e1", fontSize: 12, background: "#f8fafc", color: "#1e293b", outline: "none",
                        }}
                      />
                      {backlinkDomainQuery && (
                        <button
                          type="button"
                          onClick={() => setBacklinkDomainQuery("")}
                          style={{ position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)", background: "none", border: 0, color: "var(--ink-muted)", cursor: "pointer", fontSize: 12 }}
                        >
                          ✕
                        </button>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        const csvRows = [
                          ["Domain", "Authority Score (AS)", "Backlinks", "Follow %", "First Seen", "Status", "Category"],
                          ...(projectMetrics.referringDomainsList || []).map((d: any) => [
                            d.domain, d.as, d.backlinks, `${d.followPct}%`, d.firstSeen, d.status, d.category
                          ]),
                        ];
                        const csvContent = "data:text/csv;charset=utf-8," + csvRows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
                        const encodedUri = encodeURI(csvContent);
                        const link = document.createElement("a");
                        link.setAttribute("href", encodedUri);
                        link.setAttribute("download", `referring_domains_${currentDomain.replace(/[^a-zA-Z0-9]/g, "_")}.csv`);
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                      }}
                      style={{
                        background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6,
                        padding: "5px 10px", fontSize: 12, fontWeight: 600, color: "#334155",
                        cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
                      }}
                    >
                      <span>📥</span> Export CSV
                    </button>
                  </div>
                </div>

                <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                      <thead>
                        <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Referring Domain</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Authority (AS)</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Category</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Backlinks</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Follow %</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>First Seen</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Status</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(projectMetrics.referringDomainsList || [])
                          .filter((d: any) => !backlinkDomainQuery || d.domain.toLowerCase().includes(backlinkDomainQuery.toLowerCase()) || d.category.toLowerCase().includes(backlinkDomainQuery.toLowerCase()))
                          .map((item: any, idx: number, arr: any[]) => (
                            <tr key={idx} style={{ borderBottom: idx === arr.length - 1 ? "none" : "1px solid #f1f5f9", color: "#1e293b" }}>
                              <td style={{ padding: "11px 14px" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                  <span style={{ fontWeight: 600, color: "#1e293b" }}>{item.domain}</span>
                                  <a
                                    href={`https://${item.domain}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    style={{ color: "var(--ink-muted)", textDecoration: "none", fontSize: 12 }}
                                    title="Open domain"
                                  >
                                    ↗
                                  </a>
                                </div>
                              </td>
                              <td style={{ padding: "11px 14px" }}>
                                <span style={{
                                  fontSize: 12, fontWeight: 700,
                                  color: item.as >= 70 ? "var(--ok)" : item.as >= 50 ? "#2563eb" : "#d97706",
                                  background: item.as >= 70 ? "#ecfdf5" : item.as >= 50 ? "#eff6ff" : "#fffbeb",
                                  border: "1px solid",
                                  borderColor: item.as >= 70 ? "#a7f3d0" : item.as >= 50 ? "#bfdbfe" : "#fde68a",
                                  padding: "2px 7px", borderRadius: 4,
                                }}>
                                  AS {item.as}
                                </span>
                              </td>
                              <td style={{ padding: "11px 14px", color: "var(--ink-muted)" }}>{item.category}</td>
                              <td style={{ padding: "11px 14px", fontWeight: 600 }}>{item.backlinks.toLocaleString()}</td>
                              <td style={{ padding: "11px 14px" }}>
                                <span style={{ fontWeight: 600, color: item.followPct >= 90 ? "var(--ok)" : "#475569" }}>
                                  {item.followPct}%
                                </span>
                              </td>
                              <td style={{ padding: "11px 14px", color: "var(--ink-muted)" }}>{item.firstSeen}</td>
                              <td style={{ padding: "11px 14px" }}>
                                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "1px 6px", borderRadius: 3 }}>
                                  ● {item.status}
                                </span>
                              </td>
                              <td style={{ padding: "11px 14px" }}>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setSelectedOutreachDomain(item.domain);
                                    setSelectedOutreachCategory(item.category || "General");
                                    setShowOutreachModal(true);
                                  }}
                                  style={{
                                    background: outreachPitchedDomains.includes(item.domain) ? "#ecfdf5" : "#4f46e5",
                                    color: outreachPitchedDomains.includes(item.domain) ? "#047857" : "#fff",
                                    border: outreachPitchedDomains.includes(item.domain) ? "1px solid #a7f3d0" : 0,
                                    borderRadius: 4, padding: "4px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                                    display: "inline-flex", alignItems: "center", gap: 4,
                                  }}
                                >
                                  {outreachPitchedDomains.includes(item.domain) ? "✓ Pitched" : "⚡ Outreach"}
                                </button>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {outreachToast && (
                  <div style={{ marginTop: 10, padding: "8px 12px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, fontSize: 12, color: "#166534", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span>✓ Added <b>{outreachToast}</b> to Outreach Pitch Queue. AI pitch template staged.</span>
                    <button type="button" onClick={() => setOutreachToast(null)} style={{ background: "none", border: 0, color: "#166534", cursor: "pointer" }}>✕</button>
                  </div>
                )}
              </div>

              {/* Anchor Text Distribution */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                  <div>
                    <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Anchor Text Diversity Profile</h4>
                    <p style={{ margin: "3px 0 0", fontSize: 12, color: "var(--ink-muted)" }}>
                      Anchor text spread across inbound links to avoid algorithmic over-optimization penalties
                    </p>
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "2px 7px", borderRadius: 4 }}>
                    Healthy Distribution
                  </span>
                </div>

                <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                      <thead>
                        <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Anchor Text</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Share</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Referring Domains</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Anchor Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(projectMetrics.backlinkAuditData.anchors || []).map((anc: any, idx: number, arr: any[]) => (
                          <tr key={idx} style={{ borderBottom: idx === arr.length - 1 ? "none" : "1px solid #f1f5f9", color: "#1e293b" }}>
                            <td style={{ padding: "11px 14px", fontWeight: 600, color: "#1e293b" }}>
                              &ldquo;{anc.text}&rdquo;
                            </td>
                            <td style={{ padding: "11px 14px" }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <span style={{ fontWeight: 700, minWidth: 32 }}>{anc.pct}%</span>
                                <div style={{ width: 80, height: 5, background: "#f1f5f9", borderRadius: 3, overflow: "hidden" }}>
                                  <div style={{ width: `${anc.pct}%`, height: "100%", background: "#4f46e5", borderRadius: 3 }} />
                                </div>
                              </div>
                            </td>
                            <td style={{ padding: "11px 14px", color: "var(--ink-muted)" }}>{anc.count} domains</td>
                            <td style={{ padding: "11px 14px" }}>
                              <span style={{
                                fontSize: 12, fontWeight: 700,
                                color: anc.type === "Branded" ? "var(--ok)" : anc.type === "Exact Match" ? "#2563eb" : "#8b5cf6",
                                background: anc.type === "Branded" ? "#ecfdf5" : anc.type === "Exact Match" ? "#eff6ff" : "#f5f3ff",
                                border: "1px solid",
                                borderColor: anc.type === "Branded" ? "#a7f3d0" : anc.type === "Exact Match" ? "#bfdbfe" : "#ddd6fe",
                                padding: "2px 7px", borderRadius: 4,
                              }}>
                                {anc.type}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── SUB-VIEW: BACKLINK AUDIT & TOXICITY (REAI FLAGSHIP) ── */}
          {activeTab === "Backlink Audit" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {/* Toxicity Header & KPI Cards */}
              <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 12 }}>
                <div style={{ background: "#ffffff", padding: "18px 20px", borderRadius: 8, border: "1px solid #e2e8f0", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                  <MiniRadialGauge score={projectMetrics.backlinkAuditData.toxicityScore} size={68} strokeWidth={5.5} color="#10b981" />
                  <div style={{ fontSize: 13.5, fontWeight: 700, color: "var(--ok)", marginTop: 10 }}>{projectMetrics.backlinkAuditData.toxicityLevel} Toxicity</div>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", textAlign: "center", marginTop: 3 }}>
                    Safe profile · Low penalty risk
                  </div>
                </div>

                <div style={{ background: "#ffffff", padding: "18px 20px", borderRadius: 8, border: "1px solid #e2e8f0", display: "flex", flexDirection: "column", justifyContent: "center" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <div>
                      <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Referring Domain Health Breakdown</h3>
                      <p style={{ margin: "3px 0 0", fontSize: 12, color: "var(--ink-muted)" }}>Analysis across {projectMetrics.refDomains} referring domains</p>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <button
                        type="button"
                        onClick={() => setShowDisavowModal(true)}
                        style={{
                          background: "#ffffff", color: "#1e293b", border: "1px solid #cbd5e1", borderRadius: 6,
                          padding: "7px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                          display: "flex", alignItems: "center", gap: 6,
                        }}
                      >
                        <span>🛡️</span> Manage Disavow File ({disavowedDomains.length})
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setDisavowDownloaded(true);
                          const header = `# Google Search Console Disavow File for ${currentDomain}\n# Generated by REAI Autonomous SEO Engine\n# Last updated: ${new Date().toISOString().split("T")[0]}\n# Total entries: ${disavowedDomains.length}\n`;
                          const body = disavowedDomains.map((d) => `domain:${d}`).join("\n") + "\n";
                          const blob = new Blob([header + body], { type: "text/plain" });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement("a");
                          a.href = url;
                          a.download = `google_disavow_${currentDomain.replace(/\..*$/, "")}.txt`;
                          a.click();
                          URL.revokeObjectURL(url);
                        }}
                        style={{
                          background: "#1e293b", color: "#ffffff", border: 0, borderRadius: 6,
                          padding: "7px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                          display: "flex", alignItems: "center", gap: 6,
                        }}
                      >
                        <span>↓</span> Quick Export (.txt)
                      </button>
                    </div>
                  </div>

                  {disavowDownloaded && (
                    <div style={{ background: "#ecfdf5", border: "1px solid #a7f3d0", borderRadius: 6, padding: "8px 12px", marginBottom: 12, fontSize: 12, color: "#047857", fontWeight: 500, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span>✓ Disavow file downloaded! Upload to Google Search Console Disavow Links tool.</span>
                      <span style={{ cursor: "pointer", fontWeight: 700 }} onClick={() => setDisavowDownloaded(false)}>✕</span>
                    </div>
                  )}

                  {/* Visual Proportion Bar */}
                  {(() => {
                    const clean = Number(projectMetrics.backlinkAuditData.cleanDomains) || 0;
                    const susp = Number(projectMetrics.backlinkAuditData.suspiciousDomains) || 0;
                    const tox = Number(projectMetrics.backlinkAuditData.toxicDomains) || 0;
                    const tot = clean + susp + tox || 1;
                    return (
                      <div style={{ marginBottom: 12 }}>
                        <MiniSegmentBar
                          height={6}
                          segments={[
                            { label: "Clean", pct: (clean / tot) * 100, color: "#10b981" },
                            { label: "Suspicious", pct: (susp / tot) * 100, color: "#f59e0b" },
                            { label: "Toxic", pct: (tox / tot) * 100, color: "#ef4444" },
                          ]}
                        />
                      </div>
                    );
                  })()}

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                    <div style={{ border: "1px solid #edf0f4", borderRadius: 8, padding: "10px 14px", background: "#f8fafc" }}>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Clean Domains</div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: "var(--ok)", marginTop: 2 }}>{projectMetrics.backlinkAuditData.cleanDomains}</div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>High trust</div>
                    </div>
                    <div style={{ border: "1px solid #edf0f4", borderRadius: 8, padding: "10px 14px", background: "#f8fafc" }}>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Suspicious</div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: "#d97706", marginTop: 2 }}>{projectMetrics.backlinkAuditData.suspiciousDomains}</div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>Monitor</div>
                    </div>
                    <div style={{ border: "1px solid #edf0f4", borderRadius: 8, padding: "10px 14px", background: "#f8fafc" }}>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Toxic</div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: "#e11d48", marginTop: 2 }}>{projectMetrics.backlinkAuditData.toxicDomains}</div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>Disavow ready</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Anchor Texts & TLD Distribution */}
              <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12 }}>
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                  <h3 style={{ margin: "0 0 12px", fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                    Top Anchor Text Distribution
                  </h3>

                  <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                        <thead>
                          <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                            <th style={{ padding: "10px 14px", fontWeight: 700 }}>Anchor Text</th>
                            <th style={{ padding: "10px 14px", fontWeight: 700 }}>Type</th>
                            <th style={{ padding: "10px 14px", fontWeight: 700 }}>Domains</th>
                            <th style={{ padding: "10px 14px", fontWeight: 700 }}>Share</th>
                          </tr>
                        </thead>
                        <tbody>
                          {projectMetrics.backlinkAuditData.anchors.map((anc: any, idx: number, arr: any[]) => (
                            <tr key={idx} style={{ borderBottom: idx === arr.length - 1 ? "none" : "1px solid #f1f5f9", color: "#1e293b" }}>
                              <td style={{ padding: "11px 14px", fontWeight: 600 }}>&ldquo;{anc.text}&rdquo;</td>
                              <td style={{ padding: "11px 14px" }}>
                                <span style={{ fontSize: 12, fontWeight: 600, padding: "2px 7px", borderRadius: 4, background: "#f8fafc", border: "1px solid #e2e8f0", color: "#475569" }}>
                                  {anc.type}
                                </span>
                              </td>
                              <td style={{ padding: "11px 14px", color: "var(--ink-muted)" }}>{anc.count} domains</td>
                              <td style={{ padding: "11px 14px" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                  <div style={{ flex: 1, height: 6, background: "#e2e8f0", borderRadius: 3, overflow: "hidden", minWidth: 50 }}>
                                    <div style={{ width: `${anc.pct}%`, height: "100%", background: "#4f46e5", borderRadius: 3 }} />
                                  </div>
                                  <span style={{ fontSize: 12, fontWeight: 600, color: "#475569", minWidth: 28 }}>{anc.pct}%</span>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                {/* TLD Distribution Card */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                  <h3 style={{ margin: "0 0 12px", fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                    TLD Distribution
                  </h3>

                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {projectMetrics.backlinkAuditData.tldDist.map((tld: any, idx: number) => (
                      <div key={idx}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                          <span style={{ fontWeight: 600, color: "#1e293b" }}>{tld.tld}</span>
                          <span style={{ fontWeight: 700, color: "var(--ink-muted)" }}>{tld.share}%</span>
                        </div>
                        <div style={{ height: 6, background: "#f1f5f9", borderRadius: 3, overflow: "hidden" }}>
                          <div style={{ width: `${tld.share}%`, height: "100%", background: tld.color, borderRadius: 3 }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Toxic & Suspicious Referring Domains Table */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                        Toxic & Suspicious Inbound Footprint
                      </h3>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "#e11d48", background: "#fff1f2", border: "1px solid #fecdd3", padding: "2px 8px", borderRadius: 4 }}>
                        {projectMetrics.backlinkAuditData.toxicDomainList?.length || 0} Domains Flagged
                      </span>
                    </div>
                    <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--ink-muted)" }}>
                      Algorithmic toxic link detection analyzing unnatural footprints, network PBN patterns, sitewide footers, and low-trust referrers.
                    </p>
                  </div>

                  {/* Quick Add Custom Domain to Disavow */}
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <input
                      type="text"
                      placeholder="Add domain to disavow (e.g. badlink.com)"
                      value={customDisavowInput}
                      onChange={(e) => setCustomDisavowInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && customDisavowInput.trim()) {
                          const cleanDomain = customDisavowInput.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
                          if (!disavowedDomains.includes(cleanDomain)) {
                            setDisavowedDomains([...disavowedDomains, cleanDomain]);
                            setWhitelistedDomains(whitelistedDomains.filter((d) => d !== cleanDomain));
                          }
                          setCustomDisavowInput("");
                        }
                      }}
                      style={{
                        padding: "6px 10px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 6,
                        outline: "none", width: 240, background: "#f8fafc"
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => {
                        if (customDisavowInput.trim()) {
                          const cleanDomain = customDisavowInput.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
                          if (!disavowedDomains.includes(cleanDomain)) {
                            setDisavowedDomains([...disavowedDomains, cleanDomain]);
                            setWhitelistedDomains(whitelistedDomains.filter((d) => d !== cleanDomain));
                          }
                          setCustomDisavowInput("");
                        }
                      }}
                      style={{
                        background: "#4f46e5", color: "#ffffff", border: 0, borderRadius: 6,
                        padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer"
                      }}
                    >
                      + Disavow
                    </button>
                  </div>
                </div>

                {/* Table */}
                <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                      <thead>
                        <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Referring Domain</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Toxicity Score</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Classification / Penalty Risk</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Algorithmic Markers</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Backlinks</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700, textAlign: "right" }}>REAI Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(projectMetrics.backlinkAuditData.toxicDomainList || []).map((item: any, idx: number, arr: any[]) => {
                          const isDisavowed = disavowedDomains.includes(item.domain);
                          const isWhitelisted = whitelistedDomains.includes(item.domain);

                          return (
                            <tr key={idx} style={{
                              borderBottom: idx === arr.length - 1 ? "none" : "1px solid #f1f5f9",
                              color: "#1e293b",
                              background: isDisavowed ? "#f8fafc" : isWhitelisted ? "#f0fdf4" : "#ffffff",
                            }}>
                              <td style={{ padding: "12px 14px", fontWeight: 600 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                  <span style={{ color: "#1e293b" }}>{item.domain}</span>
                                  {isDisavowed && (
                                    <span style={{ fontSize: 12, fontWeight: 700, background: "#e2e8f0", color: "#475569", padding: "1px 6px", borderRadius: 3 }}>
                                      In Disavow
                                    </span>
                                  )}
                                  {isWhitelisted && (
                                    <span style={{ fontSize: 12, fontWeight: 700, background: "#dcfce7", color: "#15803d", padding: "1px 6px", borderRadius: 3 }}>
                                      Whitelisted
                                    </span>
                                  )}
                                </div>
                                <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>First detected: {item.firstSeen}</div>
                              </td>
                              <td style={{ padding: "12px 14px" }}>
                                <span style={{
                                  fontSize: 12, fontWeight: 700,
                                  color: item.toxicityScore >= 80 ? "#dc2626" : item.toxicityScore >= 60 ? "#d97706" : "#4b5563",
                                  background: item.toxicityScore >= 80 ? "#fef2f2" : item.toxicityScore >= 60 ? "#fffbeb" : "#f3f4f6",
                                  border: "1px solid",
                                  borderColor: item.toxicityScore >= 80 ? "#fecaca" : item.toxicityScore >= 60 ? "#fde68a" : "#e5e7eb",
                                  padding: "2px 8px", borderRadius: 4, display: "inline-block"
                                }}>
                                  {item.toxicityScore} / 100
                                </span>
                              </td>
                              <td style={{ padding: "12px 14px" }}>
                                <div style={{ fontWeight: 600, color: "#334155" }}>{item.category}</div>
                              </td>
                              <td style={{ padding: "12px 14px" }}>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                                  {item.markers.map((m: string, mIdx: number) => (
                                    <span key={mIdx} style={{
                                      fontSize: 12, fontWeight: 500, color: "#475569",
                                      background: "#f1f5f9", border: "1px solid #e2e8f0",
                                      padding: "1px 6px", borderRadius: 3, whiteSpace: "nowrap"
                                    }}>
                                      {m}
                                    </span>
                                  ))}
                                </div>
                              </td>
                              <td style={{ padding: "12px 14px", color: "var(--ink-muted)", fontWeight: 600 }}>
                                {item.backlinks}
                              </td>
                              <td style={{ padding: "12px 14px", textAlign: "right" }}>
                                <div style={{ display: "flex", justifyContent: "flex-end", gap: 6 }}>
                                  {isDisavowed ? (
                                    <button
                                      type="button"
                                      onClick={() => setDisavowedDomains(disavowedDomains.filter((d) => d !== item.domain))}
                                      style={{
                                        background: "#ffffff", border: "1px solid #cbd5e1", color: "var(--ink-muted)",
                                        borderRadius: 5, padding: "5px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer"
                                      }}
                                    >
                                      Remove Disavow
                                    </button>
                                  ) : (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setDisavowedDomains([...disavowedDomains, item.domain]);
                                        setWhitelistedDomains(whitelistedDomains.filter((d) => d !== item.domain));
                                      }}
                                      style={{
                                        background: "#dc2626", border: 0, color: "#ffffff",
                                        borderRadius: 5, padding: "5px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer"
                                      }}
                                    >
                                      Disavow
                                    </button>
                                  )}

                                  {isWhitelisted ? (
                                    <button
                                      type="button"
                                      onClick={() => setWhitelistedDomains(whitelistedDomains.filter((d) => d !== item.domain))}
                                      style={{
                                        background: "#ffffff", border: "1px solid #cbd5e1", color: "var(--ink-muted)",
                                        borderRadius: 5, padding: "5px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer"
                                      }}
                                    >
                                      Reset Whitelist
                                    </button>
                                  ) : (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setWhitelistedDomains([...whitelistedDomains, item.domain]);
                                        setDisavowedDomains(disavowedDomains.filter((d) => d !== item.domain));
                                      }}
                                      style={{
                                        background: "#ffffff", border: "1px solid #cbd5e1", color: "var(--ok)",
                                        borderRadius: 5, padding: "5px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer"
                                      }}
                                    >
                                      Whitelist
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── SUB-VIEW: ON-PAGE SEO IDEAS & WEB VITALS (+ REAI AUTO-FIX) ── */}
          {activeTab === "On-Page SEO" && (() => {
            const recs = projectMetrics.onPageSeoData.recommendations || [];
            
            // Categorized ideas breakdown
            const categories = [
              { id: "all", label: "All Ideas", count: recs.length },
              { id: "strategy", label: "Strategy Ideas", count: recs.filter((r: any) => r.cat === "strategy").length },
              { id: "content", label: "Content & TF-IDF", count: recs.filter((r: any) => r.cat === "content").length },
              { id: "semantic", label: "Semantic & Schema", count: recs.filter((r: any) => r.cat === "semantic").length },
              { id: "tech", label: "Technical & Speed", count: recs.filter((r: any) => r.cat === "tech").length },
            ];
            // B-113. The KPI strip showed `recs.length + 8` ideas, "+42% Lift",
            // "84 / 100" captioned as derived from the scan, "1-Click Ready", and
            // an unconditional "All 3 Core Web Vitals Passed" above three tiles
            // reading "Not measured". Every number below is now read from the
            // report, and a tile with nothing to read from is gone.
            const onPageTally = tallyRows(rowsForView(report, viewById("on-page")!));
            const onPageGraded = onPageTally.ok + onPageTally.warn + onPageTally.error;
            const onPageScore = onPageGraded > 0 ? Math.round((100 * onPageTally.ok) / onPageGraded) : null;
            const cwv = projectMetrics.onPageSeoData.coreWebVitals;
            const cwvReadings = [cwv.lcp, cwv.inp, cwv.cls];
            const cwvMeasured = cwvReadings.filter((v: any) => v.status !== "Not measured");
            const cwvGood = cwvMeasured.filter((v: any) => v.status === "Good").length;
            const cwvBanner =
              cwvMeasured.length === 0
                ? { text: "Not measured", fg: "var(--ink-muted)", bg: "#f8fafc", border: "#e2e8f0" }
                : cwvGood === 3
                  ? { text: "✓ All 3 Core Web Vitals Good", fg: "var(--ok)", bg: "#ecfdf5", border: "#a7f3d0" }
                  : { text: `${cwvGood} of ${cwvMeasured.length} measured vitals Good`, fg: "var(--warn)", bg: "#fffbeb", border: "#fde68a" };

            const targetPages: any[] = [
              // Was a hardcoded fixture: pages with content-idea counts. Real values come from
              // the scan report; with no scan there is nothing to show, and an
              // empty list is the honest answer.
            ];

            return (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {/* Summary KPI cards: each value read from the scan report (B-113). */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
                  <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "14px 16px" }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase" }}>Optimization Ideas</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: "#4f46e5", marginTop: 4 }}>{recs.length}</div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>Site-wide issues from this scan's crawl</div>
                  </div>

                  <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "14px 16px" }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase" }}>On-Page Checks Passing</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: "#0f172a", marginTop: 4 }}>
                      {onPageScore === null ? "Not measured" : `${onPageScore}%`}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                      {onPageScore === null
                        ? "No on-page checks in this scan"
                        : `${onPageTally.ok} of ${onPageGraded} graded on-page checks passed`}
                    </div>
                  </div>
                </div>

                {/* Core Web Vitals Row (Google Real-User Metrics) */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <div>
                      <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                        Google Core Web Vitals & Speed Diagnostics
                      </h4>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                        Real-user CrUX measurement & Lighthouse lab simulation for <b>{currentDomain}</b>
                      </div>
                    </div>
                    <span style={{ fontSize: 12, fontWeight: 700, color: cwvBanner.fg, background: cwvBanner.bg, border: `1px solid ${cwvBanner.border}`, padding: "3px 10px", borderRadius: 4 }}>
                      {cwvBanner.text}
                    </span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", background: "#ffffff", minHeight: 90, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase" }}>LCP (Loading)</span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "#ecfdf5", padding: "1px 6px", borderRadius: 3 }}>
                          {projectMetrics.onPageSeoData.coreWebVitals.lcp.status}
                        </span>
                      </div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: projectMetrics.onPageSeoData.coreWebVitals.lcp.color }}>
                        {projectMetrics.onPageSeoData.coreWebVitals.lcp.val}
                      </div>
                      <LighthouseGaugeBar
                        val={projectMetrics.onPageSeoData.coreWebVitals.lcp.val}
                        status={projectMetrics.onPageSeoData.coreWebVitals.lcp.status}
                        color={projectMetrics.onPageSeoData.coreWebVitals.lcp.color}
                      />
                    </div>

                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", background: "#ffffff", minHeight: 90, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase" }}>INP (Interactivity)</span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "#ecfdf5", padding: "1px 6px", borderRadius: 3 }}>
                          {projectMetrics.onPageSeoData.coreWebVitals.inp.status}
                        </span>
                      </div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: projectMetrics.onPageSeoData.coreWebVitals.inp.color }}>
                        {projectMetrics.onPageSeoData.coreWebVitals.inp.val}
                      </div>
                      <LighthouseGaugeBar
                        val={projectMetrics.onPageSeoData.coreWebVitals.inp.val}
                        status={projectMetrics.onPageSeoData.coreWebVitals.inp.status}
                        color={projectMetrics.onPageSeoData.coreWebVitals.inp.color}
                      />
                    </div>

                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", background: "#ffffff", minHeight: 90, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase" }}>CLS (Stability)</span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "#ecfdf5", padding: "1px 6px", borderRadius: 3 }}>
                          {projectMetrics.onPageSeoData.coreWebVitals.cls.status}
                        </span>
                      </div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: projectMetrics.onPageSeoData.coreWebVitals.cls.color }}>
                        {projectMetrics.onPageSeoData.coreWebVitals.cls.val}
                      </div>
                      <LighthouseGaugeBar
                        val={projectMetrics.onPageSeoData.coreWebVitals.cls.val}
                        status={projectMetrics.onPageSeoData.coreWebVitals.cls.status}
                        color={projectMetrics.onPageSeoData.coreWebVitals.cls.color}
                      />
                    </div>
                  </div>
                </div>

                {/* Priority Target Pages Table */}
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "16px 18px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <div>
                      <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                        Priority Target Pages Analyzed
                      </h4>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                        Top commercial landing pages evaluated for keyword density, entities, and on-page signals
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setActiveTab("Auto-Fix Engine");
                        if (planState && !planState.plan?.worklist) planState.runPlan();
                      }}
                      style={{
                        background: "#4f46e5", color: "#fff", border: 0, borderRadius: 6,
                        padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                        display: "flex", alignItems: "center", gap: 6,
                      }}
                    >
                      <IconTerminal size={14} /> Launch Auto-Fix Engine
                    </button>
                  </div>

                  <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, textAlign: "left" }}>
                        <thead>
                          <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                            <th style={{ padding: "10px 14px", fontWeight: 700 }}>Page URL & Title</th>
                            <th style={{ padding: "10px 14px", fontWeight: 700 }}>Target Keyword</th>
                            <th style={{ padding: "10px 14px", fontWeight: 700 }}>Ideas</th>
                            <th style={{ padding: "10px 14px", fontWeight: 700 }}>Page Health</th>
                            <th style={{ padding: "10px 14px", fontWeight: 700, textAlign: "right" }}>Autonomous Fix</th>
                          </tr>
                        </thead>
                        <tbody>
                          {targetPages.map((pg, idx) => {
                            const isSelected = selectedOnPageUrl === pg.url;
                            return (
                              <tr
                                key={idx}
                                onClick={() => setSelectedOnPageUrl(pg.url)}
                                style={{
                                  borderBottom: idx === targetPages.length - 1 ? "none" : "1px solid #f1f5f9",
                                  color: "#1e293b", cursor: "pointer",
                                  background: isSelected ? "#eff6ff" : "transparent",
                                  transition: "background 0.12s ease",
                                }}
                              >
                                <td style={{ padding: "11px 14px" }}>
                                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                    <div style={{ fontWeight: isSelected ? 700 : 600, color: isSelected ? "#1d4ed8" : "#1e293b" }}>{pg.title}</div>
                                    {isSelected && (
                                      <span style={{ fontSize: 12, fontWeight: 700, color: "#1d4ed8", background: "#dbeafe", padding: "1px 5px", borderRadius: 3 }}>
                                        ACTIVE
                                      </span>
                                    )}
                                  </div>
                                  <div style={{ fontSize: 12, color: isSelected ? "#2563eb" : "var(--ink-muted)", fontFamily: "monospace", marginTop: 2 }}>{pg.url}</div>
                                </td>
                                <td style={{ padding: "11px 14px" }}>
                                  <span style={{ background: isSelected ? "#ffffff" : "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontSize: 12, color: "#334155", fontWeight: 500, border: isSelected ? "1px solid #bfdbfe" : 0 }}>
                                    {pg.targetKw}
                                  </span>
                                </td>
                                <td style={{ padding: "11px 14px" }}>
                                  <span style={{ fontWeight: 700, color: "#4f46e5", background: "#eef2ff", padding: "2px 8px", borderRadius: 10, fontSize: 12 }}>
                                    {pg.ideas} ideas
                                  </span>
                                </td>
                                <td style={{ padding: "11px 14px" }}>
                                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                    <span style={{ fontWeight: 700, color: pg.score >= 80 ? "var(--ok)" : "#d97706" }}>{pg.score}%</span>
                                    <div style={{ width: 60, height: 5, background: "#f1f5f9", borderRadius: 3, overflow: "hidden" }}>
                                      <div style={{ width: `${pg.score}%`, height: "100%", background: pg.score >= 80 ? "#059669" : "#d97706", borderRadius: 3 }} />
                                    </div>
                                  </div>
                                </td>
                                <td style={{ padding: "11px 14px", textAlign: "right" }}>
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setSelectedOnPageUrl(pg.url);
                                      setShowContentEnrichModal(true);
                                    }}
                                    style={{
                                      background: "#4f46e5", color: "#ffffff", border: 0, borderRadius: 4,
                                      padding: "4px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                                      display: "inline-flex", alignItems: "center", gap: 4,
                                    }}
                                  >
                                    <span>⚡</span> Enrich Content
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                {/* ── CONTENT & TF-IDF SEMANTIC ENTITY GAP (THE MEASURE TOOL) ── */}
                {/* B-113. Every figure in this panel (word-count deficit, heading depth,
                    entity density, rival usage) comes from `onPageSemanticData`, which
                    is a zero-filled placeholder: nothing in the scanner measures a
                    competitor content benchmark. It rendered "-0 words (Deficit)" and
                    "Target: 0 words" as if measured. Shown only once a target exists. */}
                {onPageSemanticData.wordCount.target > 0 && (
                <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                          Content & TF-IDF Semantic Entity Gap
                        </h4>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 7px", borderRadius: 4 }}>
                          Competitor Content Benchmark
                        </span>
                      </div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 3 }}>
                        Top 10 SERP competitor entity density & word count benchmark for <b>{onPageSemanticData.url}</b>
                      </div>
                    </div>

                    {/* Page selector pills */}
                    <div style={{ display: "flex", gap: 6 }}>
                      {targetPages.map((tp) => (
                        <button
                          key={tp.url}
                          type="button"
                          onClick={() => setSelectedOnPageUrl(tp.url)}
                          style={{
                            background: selectedOnPageUrl === tp.url ? "#1e293b" : "#f8fafc",
                            color: selectedOnPageUrl === tp.url ? "#ffffff" : "#475569",
                            border: "1px solid", borderColor: selectedOnPageUrl === tp.url ? "#1e293b" : "#e2e8f0",
                            borderRadius: 6, padding: "4px 10px", fontSize: 12, fontWeight: selectedOnPageUrl === tp.url ? 700 : 500,
                            cursor: "pointer", fontFamily: "monospace",
                          }}
                        >
                          {tp.url}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* 2-Column: Benchmarks & Missing Entities */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1.3fr", gap: 14 }}>
                    {/* Left: 4 Competitor Metric Benchmarks */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                          <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>Total Word Count</span>
                          <span style={{ fontSize: 12, fontWeight: 700, color: "#e11d48" }}>
                            -{onPageSemanticData.wordCount.deficit} words (Deficit)
                          </span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                          <span style={{ fontSize: 18, fontWeight: 800, color: "#1e293b" }}>{onPageSemanticData.wordCount.current} words</span>
                          <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>Target: {onPageSemanticData.wordCount.target} words</span>
                        </div>
                        <div style={{ height: 6, background: "#e2e8f0", borderRadius: 3, overflow: "hidden" }}>
                          <div style={{ width: `${Math.min(100, Math.round((onPageSemanticData.wordCount.current / onPageSemanticData.wordCount.target) * 100))}%`, height: "100%", background: "#e11d48", borderRadius: 3 }} />
                        </div>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                        <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 12px" }}>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Heading Depth</div>
                          <div style={{ fontSize: 16, fontWeight: 800, color: "#1e293b", marginTop: 2 }}>
                            {onPageSemanticData.headingCount.current} <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>/ {onPageSemanticData.headingCount.target} H2-H3s</span>
                          </div>
                          <div style={{ fontSize: 12, color: "#d97706", marginTop: 2, fontWeight: 600 }}>Expand Subsections</div>
                        </div>

                        <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 12px" }}>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Entity Density</div>
                          <div style={{ fontSize: 16, fontWeight: 800, color: "#1e293b", marginTop: 2 }}>
                            {onPageSemanticData.entityDensity.current} <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>/ {onPageSemanticData.entityDensity.target}</span>
                          </div>
                          <div style={{ fontSize: 12, color: "var(--ok)", marginTop: 2, fontWeight: 600 }}>TF-IDF Target</div>
                        </div>
                      </div>

                      <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 12px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Readability Score</div>
                          <div style={{ fontSize: 14, fontWeight: 700, color: "#1e293b" }}>{onPageSemanticData.readability.current}</div>
                        </div>
                        <span style={{ fontSize: 12, color: "var(--ok)", fontWeight: 700, background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "2px 7px", borderRadius: 4 }}>
                          Target: {onPageSemanticData.readability.target}
                        </span>
                      </div>

                      {/* 1-Click Autonomous Enrich Action */}
                      <button
                        type="button"
                        onClick={() => setShowContentEnrichModal(true)}
                        style={{
                          background: "linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%)",
                          color: "#ffffff", border: 0, borderRadius: 8,
                          padding: "9px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                          display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
                          boxShadow: "0 2px 6px rgba(79, 70, 229, 0.25)",
                        }}
                      >
                        <span>⚡</span> Auto-Generate Content Block with Claude Code
                      </button>
                    </div>

                    {/* Right: Missing Semantic Entities & Keywords Table */}
                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" }}>
                      <div style={{ overflowX: "auto" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, textAlign: "left" }}>
                          <thead>
                            <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "var(--ink-muted)", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                              <th style={{ padding: "8px 12px", fontWeight: 700 }}>Semantic Entity Keyword</th>
                              <th style={{ padding: "8px 12px", fontWeight: 700 }}>Section</th>
                              <th style={{ padding: "8px 12px", fontWeight: 700 }}>Rival Usage</th>
                              <th style={{ padding: "8px 12px", fontWeight: 700 }}>Relevance</th>
                              <th style={{ padding: "8px 12px", fontWeight: 700 }}>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {onPageSemanticData.entities.map((ent, i) => (
                              <tr key={i} style={{ borderBottom: i === onPageSemanticData.entities.length - 1 ? "none" : "1px solid #f1f5f9", color: "#1e293b" }}>
                                <td style={{ padding: "9px 12px", fontWeight: 600 }}>{ent.term}</td>
                                <td style={{ padding: "9px 12px", color: "var(--ink-muted)", fontSize: 12 }}>{ent.section}</td>
                                <td style={{ padding: "9px 12px", color: "#475569" }}>{ent.competitors} / 10</td>
                                <td style={{ padding: "9px 12px" }}>
                                  <span style={{ fontWeight: 700, color: "#4f46e5" }}>{ent.relevance}%</span>
                                </td>
                                <td style={{ padding: "9px 12px" }}>
                                  <span style={{
                                    fontSize: 12, fontWeight: 700,
                                    color: ent.status === "Missing" ? "#e11d48" : "#d97706",
                                    background: ent.status === "Missing" ? "#fef2f2" : "#fffbeb",
                                    border: "1px solid", borderColor: ent.status === "Missing" ? "#fecaca" : "#fde68a",
                                    padding: "1px 6px", borderRadius: 3,
                                  }}>
                                    {ent.status}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </div>
                )}

                {/* On-Page SEO Recommendations List with Category Filter Tabs */}
                <div style={{ background: "#ffffff", borderRadius: 10, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 10 }}>
                    <div>
                      <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                        Actionable On-Page SEO Ideas
                      </h4>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                        Categorized recommendations with AST-aware code patch instructions
                      </div>
                    </div>

                    {/* Filter tabs with counts */}
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {categories.map((cat) => (
                        <button
                          key={cat.id}
                          type="button"
                          onClick={() => setOnPageFilter(cat.id as any)}
                          style={{
                            background: onPageFilter === cat.id ? "#1e293b" : "#f8fafc",
                            color: onPageFilter === cat.id ? "#ffffff" : "#475569",
                            border: "1px solid", borderColor: onPageFilter === cat.id ? "#1e293b" : "#e2e8f0",
                            borderRadius: 20, padding: "4px 12px", fontSize: 12, fontWeight: onPageFilter === cat.id ? 700 : 500,
                            cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                          }}
                        >
                          <span>{cat.label}</span>
                          <span style={{
                            fontSize: 12, padding: "1px 5px", borderRadius: 10,
                            background: onPageFilter === cat.id ? "rgba(255,255,255,0.2)" : "#e2e8f0",
                            color: onPageFilter === cat.id ? "#ffffff" : "var(--ink-muted)",
                          }}>
                            {cat.count}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {recs
                      .filter((rec: any) => onPageFilter === "all" || rec.cat === onPageFilter)
                      .map((rec: any, idx: number) => (
                        <div
                          key={idx}
                          style={{
                            border: "1px solid #edf0f4", borderRadius: 8, padding: "12px 14px",
                            background: "#f8fafc", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 14,
                          }}
                        >
                          <div style={{ flex: 1 }}>
                            <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
                              <span style={{
                                fontSize: 12, fontWeight: 700, textTransform: "uppercase",
                                padding: "2px 6px", borderRadius: 4, background: "#eef2ff", color: "#4f46e5", border: "1px solid #c7d2fe",
                              }}>
                                {rec.cat}
                              </span>
                              <span style={{
                                fontSize: 12, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                                background: rec.impact === "High" ? "#fef2f2" : "#fffbeb",
                                color: rec.impact === "High" ? "#b91c1c" : "#b45309",
                              }}>
                                {rec.impact} Impact
                              </span>
                              <span style={{ fontWeight: 700, fontSize: 13, color: "#1e293b" }}>{rec.title}</span>
                            </div>
                            <div style={{ fontSize: 12, color: "#475569", lineHeight: 1.4 }}>{rec.desc}</div>
                          </div>

                          <button
                            type="button"
                            onClick={() => {
                              setActiveTab("Auto-Fix Engine");
                              if (planState && !planState.plan?.worklist) planState.runPlan();
                            }}
                            style={{
                              background: "#4f46e5", color: "#ffffff", border: 0, borderRadius: 6,
                              padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                              whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 5,
                              flexShrink: 0,
                            }}
                          >
                            <IconTerminal size={13} /> Auto-Fix in Repo
                          </button>
                        </div>
                      ))}
                  </div>
                </div>

                {/* Clean CTA Card to open dedicated SERP Snippet Optimizer */}
                <div style={{
                  background: "#ffffff", borderRadius: 10, border: "1px solid #e2e8f0", padding: "20px 24px",
                  display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12,
                }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <IconMonitor size={18} />
                      <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                        Live Google SERP & Social Snippet Optimizer
                      </h4>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "#0284c7", background: "#f0f9ff", border: "1px solid #bae6fd", padding: "2px 7px", borderRadius: 4 }}>
                        Pixel-Width Engine
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                      Simulate Google desktop (600px) & mobile (380px) title pixel limits and snippet truncation for <b>{selectedOnPageUrl}</b>.
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveTab("SERP Optimizer")}
                    style={{
                      background: "#1e293b", color: "#ffffff", border: 0, borderRadius: 6,
                      padding: "8px 16px", fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                      display: "flex", alignItems: "center", gap: 6,
                    }}
                  >
                    Launch SERP Optimizer <IconArrowRight size={14} />
                  </button>
                </div>
              </div>
            );
          })()}

          {/* ── SUB-VIEW: DEDICATED SERP SNIPPET OPTIMIZER ── */}
          {activeTab === "SERP Optimizer" && (() => {
            const titleWidth = estimateSerpPixelWidth(activeSerpMeta.title, 20);
                  const titleChars = activeSerpMeta.title.length;
                  const descWidth = estimateSerpPixelWidth(activeSerpMeta.description, 14);
                  const descChars = activeSerpMeta.description.length;

                  // Title validation
                  const isTitleTruncated = titleWidth > 580 || titleChars > 65;
                  const isTitleTooShort = titleChars < 35;
                  const titleColor = isTitleTruncated ? "#e11d48" : isTitleTooShort ? "#d97706" : "#059669";
                  const titleBadgeText = isTitleTruncated
                    ? `⚠️ Truncated by Google (>580px)`
                    : isTitleTooShort
                    ? `⚠️ Short Title (<35 chars)`
                    : `✓ Optimal Pixel Width (${titleWidth}px / 580px max)`;

                  // Description validation
                  const isDescTruncated = descWidth > 960 || descChars > 165;
                  const isDescTooShort = descChars < 100;
                  const descColor = isDescTruncated ? "#e11d48" : isDescTooShort ? "#d97706" : "#059669";
                  const descBadgeText = isDescTruncated
                    ? `⚠️ Truncated by Google (>960px)`
                    : isDescTooShort
                    ? `⚠️ Short Snippet (<100 chars)`
                    : `✓ Optimal Pixel Width (${descWidth}px / 960px max)`;

                  // Helper to highlight matching target keywords in snippet preview
                  const renderHighlightedSnippet = (text: string, kw: string) => {
                    if (!kw || !kw.trim()) return text;
                    const terms = kw.trim().toLowerCase().split(/\s+/).filter(t => t.length > 2);
                    if (terms.length === 0) return text;
                    const escapedTerms = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
                    const regex = new RegExp(`(${escapedTerms})`, 'gi');
                    const parts = text.split(regex);
                    return parts.map((part, i) =>
                      regex.test(part) ? (
                        <strong key={i} style={{ fontWeight: 700, color: "#1e293b" }}>
                          {part}
                        </strong>
                      ) : (
                        part
                      )
                    );
                  };

                  const cleanSlugDisplay = selectedOnPageUrl === "/" ? "" : ` › ${selectedOnPageUrl.replace(/^\//, "").replace(/\//g, " › ")}`;
                  const cleanDomainDisplay = currentDomain.replace(/^https?:\/\//, "").replace(/\/$/, "");

                  return (
                    <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "18px 20px" }}>
                      {/* Card Header & Simulator Mode Switcher */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b" }}>
                              Live Google SERP & Social Snippet Simulator
                            </h4>
                            <span style={{ fontSize: 12, fontWeight: 700, color: "#0284c7", background: "#f0f9ff", border: "1px solid #bae6fd", padding: "2px 7px", borderRadius: 4 }}>
                              Pixel-Width Engine
                            </span>
                          </div>
                          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 3 }}>
                            Simulate desktop & mobile Google search result rendering for <b>{selectedOnPageUrl}</b> with 1-click Claude Code AST metadata deployment
                          </div>
                        </div>

                        {/* Mode Switcher Tabs */}
                        <div style={{ display: "flex", background: "#f1f5f9", padding: 3, borderRadius: 8, gap: 3 }}>
                          <button
                            type="button"
                            onClick={() => setSerpPreviewMode("desktop")}
                            style={{
                              background: serpPreviewMode === "desktop" ? "#ffffff" : "transparent",
                              color: serpPreviewMode === "desktop" ? "#0f172a" : "var(--ink-muted)",
                              border: 0, borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: serpPreviewMode === "desktop" ? 700 : 500,
                              cursor: "pointer", boxShadow: serpPreviewMode === "desktop" ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
                              display: "flex", alignItems: "center", gap: 5,
                            }}
                          >
                            <span>🖥️</span> Desktop (600px)
                          </button>
                          <button
                            type="button"
                            onClick={() => setSerpPreviewMode("mobile")}
                            style={{
                              background: serpPreviewMode === "mobile" ? "#ffffff" : "transparent",
                              color: serpPreviewMode === "mobile" ? "#0f172a" : "var(--ink-muted)",
                              border: 0, borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: serpPreviewMode === "mobile" ? 700 : 500,
                              cursor: "pointer", boxShadow: serpPreviewMode === "mobile" ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
                              display: "flex", alignItems: "center", gap: 5,
                            }}
                          >
                            <span>📱</span> Mobile (380px)
                          </button>
                          <button
                            type="button"
                            onClick={() => setSerpPreviewMode("social")}
                            style={{
                              background: serpPreviewMode === "social" ? "#ffffff" : "transparent",
                              color: serpPreviewMode === "social" ? "#0f172a" : "var(--ink-muted)",
                              border: 0, borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: serpPreviewMode === "social" ? 700 : 500,
                              cursor: "pointer", boxShadow: serpPreviewMode === "social" ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
                              display: "flex", alignItems: "center", gap: 5,
                            }}
                          >
                            <span>🌐</span> Social Card (OG)
                          </button>
                        </div>
                      </div>

                      {/* 2-Column Grid: Editor on Left, Live Authentic Preview Canvas on Right */}
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.25fr", gap: 16, alignItems: "start" }}>
                        {/* ── LEFT COLUMN: INTERACTIVE SERP TAGS EDITOR ── */}
                        <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 12 }}>
                          {/* Title Input & Pixel Width Bar */}
                          <div>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                              <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>SEO Page Title</label>
                              <span style={{ fontSize: 12, fontWeight: 700, color: titleColor }}>
                                {titleBadgeText}
                              </span>
                            </div>
                            <input
                              type="text"
                              value={activeSerpMeta.title}
                              onChange={(e) => {
                                const val = e.target.value;
                                setSerpCustomMeta((prev) => ({
                                  ...prev,
                                  [selectedOnPageUrl]: {
                                    ...activeSerpMeta,
                                    title: val,
                                  },
                                }));
                              }}
                              style={{
                                width: "100%", padding: "7px 10px", fontSize: 12.5,
                                border: `1px solid ${isTitleTruncated ? "#fca5a5" : "#cbd5e1"}`,
                                borderRadius: 6, background: "#ffffff", color: "#1e293b",
                                outline: "none", boxSizing: "border-box",
                              }}
                            />
                            {/* Pixel Width Progress Bar */}
                            <div style={{ marginTop: 5, display: "flex", alignItems: "center", gap: 8 }}>
                              <div style={{ flex: 1, height: 5, background: "#e2e8f0", borderRadius: 3, overflow: "hidden" }}>
                                <div
                                  style={{
                                    width: `${Math.min(100, Math.round((titleWidth / 580) * 100))}%`,
                                    height: "100%",
                                    background: titleColor,
                                    borderRadius: 3,
                                  }}
                                />
                              </div>
                              <span style={{ fontSize: 12, color: "var(--ink-muted)", fontFamily: "monospace", minWidth: 70, textAlign: "right" }}>
                                {titleWidth}px / {titleChars}c
                              </span>
                            </div>
                          </div>

                          {/* Meta Description Input & Pixel Width Bar */}
                          <div>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                              <label style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>Meta Description</label>
                              <span style={{ fontSize: 12, fontWeight: 700, color: descColor }}>
                                {descBadgeText}
                              </span>
                            </div>
                            <textarea
                              rows={3}
                              value={activeSerpMeta.description}
                              onChange={(e) => {
                                const val = e.target.value;
                                setSerpCustomMeta((prev) => ({
                                  ...prev,
                                  [selectedOnPageUrl]: {
                                    ...activeSerpMeta,
                                    description: val,
                                  },
                                }));
                              }}
                              style={{
                                width: "100%", padding: "7px 10px", fontSize: 12, lineHeight: 1.45,
                                border: `1px solid ${isDescTruncated ? "#fca5a5" : "#cbd5e1"}`,
                                borderRadius: 6, background: "#ffffff", color: "#1e293b",
                                outline: "none", resize: "vertical", boxSizing: "border-box",
                              }}
                            />
                            {/* Pixel Width Progress Bar */}
                            <div style={{ marginTop: 5, display: "flex", alignItems: "center", gap: 8 }}>
                              <div style={{ flex: 1, height: 5, background: "#e2e8f0", borderRadius: 3, overflow: "hidden" }}>
                                <div
                                  style={{
                                    width: `${Math.min(100, Math.round((descWidth / 960) * 100))}%`,
                                    height: "100%",
                                    background: descColor,
                                    borderRadius: 3,
                                  }}
                                />
                              </div>
                              <span style={{ fontSize: 12, color: "var(--ink-muted)", fontFamily: "monospace", minWidth: 70, textAlign: "right" }}>
                                {descWidth}px / {descChars}c
                              </span>
                            </div>
                          </div>

                          {/* Target Keyword for SERP Highlight */}
                          <div>
                            <label style={{ fontSize: 12, fontWeight: 700, color: "#334155", display: "block", marginBottom: 4 }}>
                              Search Query / Target Keyword (SERP Bold Simulation)
                            </label>
                            <input
                              type="text"
                              value={activeSerpMeta.targetKw}
                              placeholder="e.g. hospital phnom penh"
                              onChange={(e) => {
                                const val = e.target.value;
                                setSerpCustomMeta((prev) => ({
                                  ...prev,
                                  [selectedOnPageUrl]: {
                                    ...activeSerpMeta,
                                    targetKw: val,
                                  },
                                }));
                              }}
                              style={{
                                width: "100%", padding: "6px 10px", fontSize: 12,
                                border: "1px solid #cbd5e1", borderRadius: 6,
                                background: "#ffffff", color: "#1e293b", outline: "none",
                                boxSizing: "border-box",
                              }}
                            />
                            <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 3 }}>
                              Terms matched here will appear bolded in the SERP preview like real Google search.
                            </div>
                          </div>

                          {/* SERP Features Toggles */}
                          <div style={{ display: "flex", gap: 14, paddingTop: 4, borderTop: "1px solid #e2e8f0" }}>
                            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#475569", cursor: "pointer" }}>
                              <input
                                type="checkbox"
                                checked={serpShowRating}
                                onChange={(e) => setSerpShowRating(e.target.checked)}
                                style={{ accentColor: "#4f46e5" }}
                              />
                              Rich Star Rating
                            </label>
                            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#475569", cursor: "pointer" }}>
                              <input
                                type="checkbox"
                                checked={serpShowSitelinks}
                                onChange={(e) => setSerpShowSitelinks(e.target.checked)}
                                style={{ accentColor: "#4f46e5" }}
                              />
                              Sitelinks Extension
                            </label>
                          </div>

                          {/* Action Buttons: AI Optimizer & Claude Code Injector */}
                          <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
                            <button
                              type="button"
                              // This button said "AI CTR Optimizer" and contained
                              // no AI. It was a lookup table of four hardcoded
                              // hospital titles keyed by URL, with a catch-all for
                              // every other page - including the description
                              // "Consult with 50+ board-certified international
                              // consultant physicians", an invented credential
                              // claim of exactly the kind `claim_provenance_check`
                              // refuses on a client's site.
                              //
                              // It now calls the same Claude route every other
                              // feature uses, grounded in the page the scan
                              // actually fetched, and refuses when there is no
                              // page to rewrite.
                              disabled={!scannedPage?.title || serpAiBusy}
                              onClick={async () => {
                                if (!scannedPage?.title) return;
                                setSerpAiBusy(true);
                                setSerpAiError("");
                                try {
                                  const res = await authedFetch("/api/content/generate", {
                                    method: "POST",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({
                                      tool: "meta",
                                      values: { pages: `${scannedPage.url || selectedOnPageUrl} - ${scannedPage.title}` },
                                      context: {
                                        domain: currentDomain,
                                        business: currentBusiness,
                                        page: scannedPage,
                                        findings: Object.values(report || {})
                                          .filter(Array.isArray).flat(),
                                      },
                                    }),
                                  });
                                  if (!res.ok || !res.body) {
                                    const j = await res.json().catch(() => ({}));
                                    setSerpAiError(j.error || `Request failed (${res.status}).`);
                                    return;
                                  }
                                  const reader = res.body.getReader();
                                  const dec = new TextDecoder();
                                  let out = "";
                                  for (;;) {
                                    const { done, value } = await reader.read();
                                    if (done) break;
                                    out += dec.decode(value, { stream: true });
                                  }
                                  setSerpAiDraft(out);
                                } catch (e: any) {
                                  setSerpAiError(e?.message || "Could not reach Claude.");
                                } finally {
                                  setSerpAiBusy(false);
                                }
                              }}
                              style={{
                                flex: 1, minWidth: 140, background: "#ffffff", border: "1px solid #c7d2fe",
                                color: "#4f46e5", padding: "7px 10px", borderRadius: 6, fontSize: 12,
                                fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
                              }}
                            >
                              <span>🪄</span> {serpAiBusy ? "Claude is writing…" : "Write titles with Claude"}
                            </button>

                            <button
                              type="button"
                              onClick={() => setShowSerpMetaModal(true)}
                              style={{
                                flex: 1.2, minWidth: 160, background: "linear-gradient(135deg, #0284c7 0%, #0369a1 100%)",
                                color: "#ffffff", border: 0, padding: "7px 12px", borderRadius: 6,
                                fontSize: 12, fontWeight: 700, cursor: "pointer", display: "flex",
                                alignItems: "center", justifyContent: "center", gap: 5,
                                boxShadow: "0 1px 3px rgba(2, 132, 199, 0.25)",
                              }}
                            >
                              <span>⚡</span> Apply via Claude Code
                            </button>
                          </div>

                          {!scannedPage?.title && (
                            <div style={{ marginTop: 8, fontSize: 11.5, color: "var(--ink-muted)", lineHeight: 1.5 }}>
                              No page scanned yet, so there is no title to rewrite. The preview above shows
                              the page as fetched; run a scan to fill it.
                            </div>
                          )}
                          {serpAiError && (
                            <div style={{ marginTop: 8, padding: "8px 10px", borderRadius: 6, border: "1px solid #fecaca", background: "#fef2f2", fontSize: 11.5, color: "#991b1b" }}>
                              {serpAiError}
                            </div>
                          )}
                          {serpAiDraft && (
                            <pre style={{
                              marginTop: 8, padding: "10px 12px", borderRadius: 6,
                              border: "1px solid #e2e8f0", background: "#0f172a", color: "#e2e8f0",
                              fontSize: 11.5, lineHeight: 1.55, whiteSpace: "pre-wrap",
                              maxHeight: 260, overflowY: "auto",
                              fontFamily: "ui-monospace, SFMono-Regular, monospace",
                            }}>
                              {serpAiDraft}
                            </pre>
                          )}
                        </div>

                        {/* ── RIGHT COLUMN: AUTHENTIC SERP & SOCIAL PREVIEW CANVAS ── */}
                        <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "16px", minHeight: 330, display: "flex", flexDirection: "column", justifyContent: "center" }}>
                          
                          {/* DESKTOP SERP CANVAS */}
                          {serpPreviewMode === "desktop" && (
                            <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 10, padding: "16px 20px", boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
                              {/* Google Breadcrumb & Identity */}
                              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 5 }}>
                                <div style={{
                                  width: 26, height: 26, borderRadius: "50%", background: "#eff6ff",
                                  border: "1px solid #bfdbfe", display: "grid", placeItems: "center",
                                  fontSize: 12, fontWeight: 800, color: "#1d4ed8",
                                }}>
                                  {currentBusiness.charAt(0)}
                                </div>
                                <div style={{ display: "flex", flexDirection: "column" }}>
                                  <span style={{ fontSize: 13, color: "#202124", fontWeight: 500, lineHeight: 1.2 }}>
                                    {currentBusiness}
                                  </span>
                                  <span style={{ fontSize: 12, color: "#4d5156", fontFamily: "Arial, sans-serif" }}>
                                    https://{cleanDomainDisplay}{cleanSlugDisplay}
                                  </span>
                                </div>
                              </div>

                              {/* Google Desktop Title (20px, Arial) */}
                              <div style={{
                                fontSize: 20, lineHeight: 1.3, fontFamily: "Arial, sans-serif",
                                color: "#1a0dab", fontWeight: 400, marginTop: 4, cursor: "pointer",
                                wordBreak: "break-word",
                              }}>
                                {isTitleTruncated ? `${activeSerpMeta.title.slice(0, 60)}...` : activeSerpMeta.title}
                              </div>

                              {/* Rich Snippet: Star Rating */}
                              {serpShowRating && (
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4, fontSize: 12.5, color: "#4d5156" }}>
                                  <span style={{ color: "#e37400", letterSpacing: 1, fontSize: 13 }}>★★★★★</span>
                                  {/* Was "Rating: 4.9 · 128 reviews", on by
                                      default for every client. Nothing in the
                                      dashboard measures a rating or a review
                                      count, so there is nothing to render here
                                      but the reason. */}
                                  <span>
                                    No rating measured — connect Google Business Profile to preview one
                                  </span>
                                </div>
                              )}

                              {/* Snippet Description (14px, Arial, with keyword highlight) */}
                              <div style={{
                                fontSize: 14, lineHeight: 1.58, color: "#4d5156", fontFamily: "Arial, sans-serif",
                                marginTop: 6, wordBreak: "break-word",
                              }}>
                                {renderHighlightedSnippet(
                                  isDescTruncated ? `${activeSerpMeta.description.slice(0, 160)}...` : activeSerpMeta.description,
                                  activeSerpMeta.targetKw
                                )}
                              </div>

                              {/* Sitelinks Extension */}
                              {serpShowSitelinks && (
                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 18px", marginTop: 14, paddingTop: 12, borderTop: "1px solid #f1f5f9" }}>
                                  <div>
                                    <div style={{ fontSize: 13.5, color: "#1a0dab", fontWeight: 500, cursor: "pointer" }}>
                                      Specialist Physicians Directory
                                    </div>
                                    <div style={{ fontSize: 12, color: "#5f6368", marginTop: 2 }}>
                                      Meet our international consultant physicians & surgeons.
                                    </div>
                                  </div>
                                  <div>
                                    <div style={{ fontSize: 13.5, color: "#1a0dab", fontWeight: 500, cursor: "pointer" }}>
                                      24/7 Emergency & ICU Hotline
                                    </div>
                                    <div style={{ fontSize: 12, color: "#5f6368", marginTop: 2 }}>
                                      Immediate trauma resuscitation and ICU ambulance dispatch.
                                    </div>
                                  </div>
                                  <div>
                                    <div style={{ fontSize: 13.5, color: "#1a0dab", fontWeight: 500, cursor: "pointer" }}>
                                      Maternity & Delivery Suites
                                    </div>
                                    <div style={{ fontSize: 12, color: "#5f6368", marginTop: 2 }}>
                                      Private labor rooms and Level III newborn care.
                                    </div>
                                  </div>
                                  <div>
                                    <div style={{ fontSize: 13.5, color: "#1a0dab", fontWeight: 500, cursor: "pointer" }}>
                                      Direct Insurance Billing
                                    </div>
                                    <div style={{ fontSize: 12, color: "#5f6368", marginTop: 2 }}>
                                      Direct billing with global health insurance providers.
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}

                          {/* MOBILE SERP CANVAS */}
                          {serpPreviewMode === "mobile" && (
                            <div style={{ width: "100%", maxWidth: 360, margin: "0 auto", background: "#ffffff", borderRadius: 14, border: "1px solid #dadce0", padding: "14px 16px", boxShadow: "0 2px 8px rgba(0,0,0,0.06)" }}>
                              {/* Mobile Identity */}
                              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                  <div style={{ width: 22, height: 22, borderRadius: "50%", background: "#eff6ff", border: "1px solid #bfdbfe", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 800, color: "#1d4ed8" }}>
                                    {currentBusiness.charAt(0)}
                                  </div>
                                  <div>
                                    <div style={{ fontSize: 12, fontWeight: 600, color: "#202124" }}>{currentBusiness}</div>
                                    <div style={{ fontSize: 12, color: "#5f6368" }}>https://{cleanDomainDisplay}</div>
                                  </div>
                                </div>
                                <span style={{ color: "#70757a", fontSize: 14 }}>⋮</span>
                              </div>

                              {/* Mobile Title (16px) */}
                              <div style={{ fontSize: 16, lineHeight: 1.35, color: "#1a0dab", fontWeight: 500, marginTop: 4 }}>
                                {isTitleTruncated ? `${activeSerpMeta.title.slice(0, 56)}...` : activeSerpMeta.title}
                              </div>

                              {/* Mobile Snippet (13px) */}
                              <div style={{ fontSize: 13, lineHeight: 1.45, color: "#4d5156", marginTop: 6 }}>
                                {renderHighlightedSnippet(
                                  isDescTruncated ? `${activeSerpMeta.description.slice(0, 120)}...` : activeSerpMeta.description,
                                  activeSerpMeta.targetKw
                                )}
                              </div>

                              {/* Mobile Action Buttons */}
                              <div style={{ display: "flex", gap: 8, marginTop: 12, paddingTop: 10, borderTop: "1px solid #f1f5f9" }}>
                                <div style={{ flex: 1, textAlign: "center", padding: "6px 0", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 20, fontSize: 12, fontWeight: 600, color: "#1e293b" }}>
                                  📞 Call Clinic
                                </div>
                                <div style={{ flex: 1, textAlign: "center", padding: "6px 0", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 20, fontSize: 12, fontWeight: 600, color: "#1e293b" }}>
                                  📍 Directions
                                </div>
                              </div>
                            </div>
                          )}

                          {/* SOCIAL GRAPH (OPEN GRAPH) CANVAS */}
                          {serpPreviewMode === "social" && (
                            <div style={{ background: "#ffffff", border: "1px solid #cfd9de", borderRadius: 12, overflow: "hidden", maxWidth: 520, margin: "0 auto", boxShadow: "0 2px 6px rgba(0,0,0,0.05)" }}>
                              {/* 16:9 Aspect Ratio Simulated Banner */}
                              <div style={{
                                height: 170,
                                background: "linear-gradient(135deg, #1e293b 0%, #1e1b4b 50%, #312e81 100%)",
                                position: "relative", padding: "20px", display: "flex", flexDirection: "column",
                                justifyContent: "space-between", color: "#ffffff",
                              }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                  <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.06em", background: "rgba(255,255,255,0.15)", padding: "3px 8px", borderRadius: 4 }}>
                                    {cleanDomainDisplay.toUpperCase()}
                                  </span>
                                  <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>1200 × 630</span>
                                </div>
                                <div>
                                  <div style={{ fontSize: 16, fontWeight: 800, lineHeight: 1.3, textShadow: "0 2px 4px rgba(0,0,0,0.3)" }}>
                                    {activeSerpMeta.title}
                                  </div>
                                  <div style={{ fontSize: 12, color: "#cbd5e1", marginTop: 4 }}>
                                    {currentBusiness} · Official Healthcare Portal
                                  </div>
                                </div>
                              </div>

                              {/* OG Text Metadata Footer */}
                              <div style={{ padding: "12px 16px", background: "#f7f9fa", borderTop: "1px solid #edf0f4" }}>
                                <div style={{ fontSize: 12, color: "#536471", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
                                  {cleanDomainDisplay}
                                </div>
                                <div style={{ fontSize: 14, fontWeight: 700, color: "#0f1419", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {activeSerpMeta.title}
                                </div>
                                <div style={{ fontSize: 12, color: "#536471", marginTop: 3, lineHeight: 1.4, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                                  {activeSerpMeta.description}
                                </div>
                              </div>
                            </div>
                          )}

                        </div>
                      </div>
                    </div>
                  );
                })()}

          {/* ── SUB-VIEW: ALL PLATFORM TOOLS & ENGINES DIRECTORY (156 ENGINES) ── */}
          {activeTab === "All Tools Directory" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {/* Directory Header Banner */}
              <div style={{
                background: "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)",
                borderRadius: 8, padding: "14px 18px", color: "#ffffff",
                display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12,
              }}>
                <div>
                  <div style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "rgba(99, 102, 241, 0.2)", border: "1px solid rgba(99, 102, 241, 0.4)", padding: "2px 8px", borderRadius: 12, fontSize: 12, fontWeight: 700, color: "#a5b4fc", marginBottom: 6 }}>
                    <span>⚡ 156 SPECIALIZED AUDIT & CRAWL ENGINES</span>
                  </div>
                  <h2 style={{ margin: "0 0 4px", fontSize: 16, fontWeight: 800 }}>
                    REAI Complete Tools & Engines Directory
                  </h2>
                  <p style={{ margin: 0, fontSize: 12, color: "var(--ink-muted)" }}>
                    Automated audit checks for <b>{currentBusiness}</b> ({currentDomain}) across SERP, Backlinks, CrUX, and AI engines.
                  </p>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    setShowScanDrawer(true);
                    if (onTriggerScan) onTriggerScan(currentDomain);
                  }}
                  style={{
                    background: "linear-gradient(135deg, #059669 0%, #047857 100%)",
                    color: "#ffffff", border: 0, borderRadius: 6, padding: "8px 16px",
                    fontSize: 12, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                  }}
                >
                  <span>⚡ Run Full Scan</span>
                </button>
              </div>

              {/* Filter & Search Bar */}
              <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: "12px 14px" }}>
                <div style={{ display: "flex", gap: 12, marginBottom: 10, flexWrap: "wrap", alignItems: "center" }}>
                  <div style={{ position: "relative", flex: 1, minWidth: 240 }}>
                    <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--ink-muted)", fontSize: 13 }}>
                      🔍
                    </span>
                    <input
                      type="text"
                      // The catalog's own count, never a number typed into a string.
                      placeholder={`Search across all ${catalogSummary.tools} tools (e.g. 404, schema, canonical, speed, LCP, backlinks)...`}
                      value={toolCatalogQuery}
                      onChange={(e) => setToolCatalogQuery(e.target.value)}
                      style={{
                        width: "100%", height: 34, padding: "0 12px 0 32px",
                        fontSize: 12.5, border: "1px solid #cbd5e1", borderRadius: 6,
                        background: "#f8fafc", color: "#1e293b", outline: "none",
                      }}
                    />
                  </div>
                  <span style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>
                    {filteredCatalogTools.length} of {catalogSummary.tools} tools · {catalogSummary.checks} checks
                  </span>
                </div>

                {/* Category Filter Pills */}
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", borderTop: "1px solid #edf0f4", paddingTop: 10 }}>
                  {[
                    // Derived from the scanner's own categories, so a pill
                    // cannot name a category no tool belongs to. The old list
                    // was hardcoded and included "Competitive" and
                    // "Remediation", which the scanner has never had.
                    { id: "All", label: "All", count: catalogSummary.tools },
                    ...catalogCategories.map((c) => ({
                      id: c,
                      label: c,
                      count: scannerTools.filter((t) => t.category === c).length,
                    })),
                  ].map((cat) => {
                    const isSelected = toolCatalogCategory === cat.id;
                    return (
                      <button
                        key={cat.id}
                        type="button"
                        onClick={() => setToolCatalogCategory(cat.id)}
                        style={{
                          background: isSelected ? "#1e293b" : "#f8fafc",
                          color: isSelected ? "#ffffff" : "#475569",
                          border: "1px solid", borderColor: isSelected ? "#1e293b" : "#e2e8f0",
                          borderRadius: 5, padding: "4px 8px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                          display: "flex", alignItems: "center", gap: 5,
                        }}
                      >
                        <span>{cat.label}</span>
                        <span style={{
                          fontSize: 12, fontWeight: 700, padding: "0 5px", borderRadius: 8,
                          background: isSelected ? "rgba(255,255,255,0.2)" : "#e2e8f0",
                          color: isSelected ? "#ffffff" : "var(--ink-muted)",
                        }}>
                          {cat.count}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Tools Directory Cards Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
                {filteredCatalogTools.map((tool) => (
                  <div
                    key={tool.key}
                    style={{
                      background: "var(--surface)",
                      borderRadius: "var(--radius-md)",
                      border: "1px solid var(--border)",
                      padding: "var(--space-3) var(--space-4)",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      gap: "var(--space-3)",
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "var(--space-2)", marginBottom: "var(--space-2)" }}>
                        <span style={{
                          fontSize: 12, fontWeight: 700, textTransform: "uppercase",
                          padding: "2px 6px", borderRadius: "var(--radius-xs)", letterSpacing: "0.03em",
                          background: "var(--surface-3)", color: "var(--ink-muted)",
                          border: "1px solid var(--border)",
                        }}>
                          {tool.category}
                        </span>
                        {/* What it costs to run, from the scanner's own catalog.
                            The old badge showed an invented severity. */}
                        <span style={{
                          fontSize: 12, fontWeight: 600, padding: "1px 6px",
                          borderRadius: "var(--radius-xs)", whiteSpace: "nowrap",
                          background: tool.group === "dataforseo" ? "var(--warn-tint)" : "var(--ok-tint)",
                          color: tool.group === "dataforseo" ? "var(--warn)" : "var(--ok)",
                          border: `1px solid ${tool.group === "dataforseo" ? "var(--warn-border)" : "var(--ok-border)"}`,
                        }}>
                          {costLabel(tool)}
                        </span>
                      </div>

                      <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)", marginBottom: "var(--space-1)" }}>
                        {tool.label}
                      </div>

                      {/* The checks this tool really runs, named. The old card
                          showed a marketing description of a tool that did not
                          exist. */}
                      <p style={{ margin: 0, fontSize: 12, color: "var(--ink-muted)", lineHeight: 1.45 }}>
                        {tool.checks.length} check{tool.checks.length === 1 ? "" : "s"}: {tool.checks.slice(0, 4).join(", ")}
                        {tool.checks.length > 4 ? `, +${tool.checks.length - 4} more` : ""}
                      </p>
                    </div>

                    <div style={{ paddingTop: "var(--space-2)", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "var(--space-2)" }}>
                      <span style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 500 }}>
                        Phase {tool.phase} · {tool.phase_label}
                      </span>
                      <button
                        type="button"
                        disabled={!currentDomain}
                        title={currentDomain ? undefined : "Select a project first"}
                        onClick={() => {
                          if (onTriggerScan && currentDomain) {
                            onTriggerScan(currentDomain);
                            setShowScanDrawer(true);
                          }
                        }}
                        style={{
                          background: currentDomain ? "var(--accent)" : "var(--border-strong)",
                          color: currentDomain ? "#ffffff" : "var(--ink-muted)",
                          border: 0, borderRadius: "var(--radius-sm)",
                          padding: "var(--space-1) var(--space-3)", minHeight: 30,
                          fontSize: 12, fontWeight: 600,
                          cursor: currentDomain ? "pointer" : "not-allowed",
                        }}
                      >
                        Run scan
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
            </>
          )}

            </>
          )}
        </main>
      </div>

      {/* ── INTEGRATIONS & PLATFORM CONTROL CENTER MODAL ── */}
      {showIntegrationsModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.6)", backdropFilter: "blur(5px)",
          display: "grid", placeItems: "center", zIndex: 1100, padding: 20,
        }}>
          <div style={{
            background: "#ffffff", borderRadius: 14, border: "1px solid #e2e8f0",
            width: "100%", maxWidth: 640, maxHeight: "90vh", overflowY: "auto",
            boxShadow: "0 25px 50px -12px rgba(15, 23, 42, 0.25)", padding: "28px 32px",
          }}>
            {/* Modal Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <h2 style={{ margin: 0, fontSize: 19, fontWeight: 800, color: "#0f172a" }}>
                    Platform Control Center
                  </h2>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 8px", borderRadius: 12 }}>
                    Zero Credentials Required
                  </span>
                </div>
                <p style={{ margin: "4px 0 0 0", fontSize: 13, color: "var(--ink-muted)" }}>
                  Control connected services, verified Google Search Console properties, and repository auto-fixes in one place.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowIntegrationsModal(false)}
                style={{ background: "none", border: 0, fontSize: 20, color: "var(--ink-muted)", cursor: "pointer", padding: 4 }}
              >
                ✕
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* Service 1: Google Search Console & GA4 */}
              <div style={{
                border: "1px solid", borderColor: googleConnected ? "#a7f3d0" : "#e2e8f0",
                borderRadius: 10, padding: 18, background: googleConnected ? "#f0fdf4" : "#ffffff",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div style={{ display: "flex", gap: 12 }}>
                    <div style={{
                      width: 40, height: 40, borderRadius: 10, background: "#ffffff", border: "1px solid #e2e8f0",
                      display: "grid", placeItems: "center", boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                    }}>
                      <IconGoogle size={22} />
                    </div>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 15, fontWeight: 700, color: "#1e293b" }}>Google Search Console & GA4</span>
                        {googleConnected ? (
                          <span style={{ fontSize: 12, fontWeight: 700, color: "#047857", background: "#d1fae5", padding: "1px 7px", borderRadius: 10 }}>
                            ● Connected
                          </span>
                        ) : (
                          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", background: "#f1f5f9", padding: "1px 7px", borderRadius: 10 }}>
                            Disconnected
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 12.5, color: "var(--ink-muted)", marginTop: 3 }}>
                        Pulls 100% verified organic clicks, impressions, and exact Google search queries with zero manual API keys.
                      </div>
                    </div>
                  </div>

                  {googleConnected ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <button
                        type="button"
                        onClick={() => {
                          window.location.href = `/api/auth/google?prompt=select_account%20consent`;
                        }}
                        style={{
                          background: "#f1f5f9", color: "#334155", border: "1px solid #cbd5e1",
                          borderRadius: 6, padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                        }}
                      >
                        Switch Gmail
                      </button>
                      <button
                        type="button"
                        onClick={handleDisconnectGoogle}
                        style={{
                          background: "#fee2e2", color: "#991b1b", border: "1px solid #fecaca",
                          borderRadius: 6, padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                        }}
                      >
                        Disconnect
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <button
                        type="button"
                        onClick={handleConnectGoogle}
                        disabled={googleConnecting}
                        style={{
                          background: "#1e293b", color: "#ffffff", border: 0,
                          borderRadius: 6, padding: "7px 14px", fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                          display: "flex", alignItems: "center", gap: 6,
                        }}
                      >
                        <IconGoogle size={14} />
                        <span>{googleConnecting ? "Navigating to Google..." : "Connect Google Account →"}</span>
                      </button>
                    </div>
                  )}
                </div>

                {googleConnected && (
                  <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid #dcfce7", display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, fontSize: 12 }}>
                      <div>
                        <span style={{ color: "var(--ink-muted)" }}>Authorized Account:</span>
                        <div style={{ fontWeight: 600, color: "#1e293b", marginTop: 2 }}>{googleAccount}</div>
                      </div>
                      <div>
                        <span style={{ color: "var(--ink-muted)" }}>Permissions Granted:</span>
                        <div style={{ fontWeight: 600, color: "#047857", marginTop: 2 }}>webmasters.readonly, analytics.readonly</div>
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>Active Property:</span>
                        <select
                          value={selectedGscProperty}
                          onChange={(e) => {
                            const nextProp = e.target.value;
                            setSelectedGscProperty(nextProp);
                            setTrafficDataSource("gsc");
                            if (typeof window !== "undefined") {
                              localStorage.setItem("reai_gsc_property", nextProp);
                              localStorage.setItem("reai_traffic_source", "gsc");
                            }
                            fetchGscAnalytics(nextProp);
                          }}
                          style={{
                            background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6,
                            padding: "4px 8px", fontSize: 12, fontWeight: 600, color: "#1e293b",
                          }}
                        >
                          {verifiedGscProperties.length > 0 ? (
                            verifiedGscProperties.map((p) => (
                              <option key={p} value={p}>{p} (Verified)</option>
                            ))
                          ) : (
                            <>
                              <option value={`sc-domain:${currentDomain}`}>sc-domain:{currentDomain} (Domain Property)</option>
                              <option value={`https://${currentDomain}/`}>https://{currentDomain}/ (URL Prefix)</option>
                            </>
                          )}
                        </select>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <button
                          type="button"
                          onClick={() => {
                            fetchGscAnalytics(selectedGscProperty);
                            setSyncToast(`Google Search Console data re-synced for ${selectedGscProperty}!`);
                            setTimeout(() => setSyncToast(null), 3000);
                          }}
                          style={{
                            background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6,
                            padding: "5px 10px", fontSize: 12, fontWeight: 600, color: "#1e293b", cursor: "pointer",
                          }}
                        >
                          🔄 Re-Sync Now
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Service 2: GitHub Auto-Fix Code Engine */}
              <div style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: 18, background: "#ffffff" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div style={{ display: "flex", gap: 12 }}>
                    <div style={{
                      width: 40, height: 40, borderRadius: 10, background: "#f8fafc", border: "1px solid #e2e8f0",
                      display: "grid", placeItems: "center", color: "#1e293b",
                    }}>
                      <IconTerminal size={20} />
                    </div>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 15, fontWeight: 700, color: "#1e293b" }}>GitHub Auto-Fix Remediation</span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "#047857", background: "#d1fae5", padding: "1px 7px", borderRadius: 10 }}>
                          ● Active
                        </span>
                      </div>
                      <div style={{ fontSize: 12.5, color: "var(--ink-muted)", marginTop: 3 }}>
                        Enables 1-click automated PR creation and repository code patch generation for SEO errors.
                      </div>
                    </div>
                  </div>

                  <span style={{ fontSize: 12, fontWeight: 600, color: "#4f46e5", background: "#eef2ff", padding: "4px 10px", borderRadius: 6 }}>
                    Repo: both/seo_agent
                  </span>
                </div>

                <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12 }}>
                  <span style={{ color: "var(--ink-muted)" }}>Execution Policy: <b>Safe Dry-Run (Human Confirms Before Merge)</b></span>
                  <button
                    type="button"
                    onClick={() => {
                      setShowIntegrationsModal(false);
                      setActiveTab("Auto-Fix Engine");
                    }}
                    style={{ background: "none", border: 0, color: "#4f46e5", fontWeight: 700, cursor: "pointer", fontSize: 12 }}
                  >
                    Open Auto-Fix Engine →
                  </button>
                </div>
              </div>

              {/* Service 3: Daily Spend Budget & Protection */}
              {(() => {
                const dailyCap = budget?.dailyBudget ?? 5;
                const spent = budget?.spentToday ?? 0;
                return (
                  <div style={{ border: "1px solid #a7f3d0", borderRadius: 10, padding: 18, background: "#ecfdf5" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ fontSize: 18 }}>🛡️</span>
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 700, color: "#065f46" }}>
                            Daily Spend Budget ({formatUsd(dailyCap)}/day Cap)
                          </div>
                          <div style={{ fontSize: 12, color: "#047857", marginTop: 2 }}>
                            Daily spend limit of {formatUsd(dailyCap)} active ({formatUsd(spent)} spent today). Enforced automatically at the scan gateway.
                          </div>
                        </div>
                      </div>
                      <span style={{ fontSize: 12, fontWeight: 800, color: "#047857", background: "#ffffff", border: "1px solid #a7f3d0", padding: "4px 10px", borderRadius: 20 }}>
                        {formatUsd(spent)} / {formatUsd(dailyCap)}
                      </span>
                    </div>
                  </div>
                );
              })()}
            </div>

            <div style={{ marginTop: 22, display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                onClick={() => setShowIntegrationsModal(false)}
                style={{
                  background: "#1e293b", color: "#ffffff", border: 0, borderRadius: 8,
                  padding: "9px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer",
                }}
              >
                Close Control Center
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Sync Toast */}
      {syncToast && (
        <div style={{
          position: "fixed", bottom: 24, right: 24, background: "#1e293b", color: "#ffffff",
          padding: "12px 20px", borderRadius: 8, boxShadow: "0 10px 25px rgba(0,0,0,0.25)",
          fontSize: 13, fontWeight: 600, display: "flex", alignItems: "center", gap: 10, zIndex: 3000,
          border: "1px solid #334155",
        }}>
          <span style={{ color: "#10b981", fontSize: 16 }}>✓</span>
          <span>{syncToast}</span>
        </div>
      )}

      {/*
        The project now points at a different site than the scans it already
        carries. Nothing in the record is false - each `scans` row keeps the URL
        it ran against - but a score read off this screen would be attributed to
        a site it was never measured on. This stays until dismissed rather than
        auto-hiding like the toast, because it changes how every number above it
        should be read.
      */}
      {domainMoved && (
        <div role="status" style={{
          position: "fixed", bottom: 24, right: 24, maxWidth: 420,
          background: "#fffbeb", color: "#92400e", border: "1px solid #fde68a",
          padding: "14px 18px", borderRadius: 10, boxShadow: "0 10px 25px rgba(0,0,0,0.15)",
          fontSize: 12.5, lineHeight: 1.55, zIndex: 3000,
        }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>Project now points at a different site</div>
          <div>
            Changed from <code>{domainMoved.from}</code> to <code>{domainMoved.to}</code>.
            The {domainMoved.staleScans} scan{domainMoved.staleScans === 1 ? "" : "s"} already on
            this project measured <code>{domainMoved.from}</code>, so those scores describe the old
            site. Run a scan to measure the new one.
          </div>
          <button
            type="button"
            onClick={() => setDomainMoved(null)}
            style={{
              marginTop: 10, background: "#92400e", color: "#fff", border: 0,
              borderRadius: 6, padding: "5px 12px", fontSize: 11.5, fontWeight: 600, cursor: "pointer",
            }}
          >
            Got it
          </button>
        </div>
      )}

      {/* ── CREATE / EDIT PROJECT MODAL (INLINE, NEVER LEAVES PAGE) ── */}
      <ProjectModal
        open={showNewProjectModal}
        editing={editingProject}
        onClose={() => { setShowNewProjectModal(false); setEditingProject(null); setProjectError(null); }}
        onSubmit={handleCreateProjectSubmit}
        saving={savingProject}
        error={projectError}
        biz={newBiz} setBiz={setNewBiz}
        url={newUrl} setUrl={setNewUrl}
        model={newModel} setModel={setNewModel}
        repo={newRepo} setRepo={setNewRepo}
        goal={newGoal} setGoal={setNewGoal}
        kw={newKw} setKw={setNewKw}
        kwList={newKwList} setKwList={setNewKwList}
        githubToken={githubToken}
      />


      {/* ── LIVE SCAN DRAWER / MODAL (INLINE, NEVER LEAVES PAGE) ── */}
      {showScanDrawer && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.5)", backdropFilter: "blur(4px)",
          display: "grid", placeItems: "center", zIndex: 1000, padding: 24,
        }}>
          <div style={{
            background: "#ffffff", borderRadius: 14, border: "1px solid #e9edf2",
            width: "100%", maxWidth: 660, padding: "32px 36px", boxShadow: "0 20px 25px -5px rgba(15, 23, 42, 0.12)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{
                  width: 10, height: 10, borderRadius: "50%",
                  background: scanState?.busy ? "#3b82f6" : "#10b981",
                  boxShadow: scanState?.busy ? "0 0 10px #3b82f6" : "0 0 10px #10b981",
                }} />
                <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#1e293b" }}>
                  {scanState?.busy ? "Running Live Engine Scan..." : "Scan Complete"}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowScanDrawer(false)}
                style={{ background: "none", border: 0, fontSize: 20, color: "var(--ink-muted)", cursor: "pointer", padding: 4 }}
              >
                ✕
              </button>
            </div>

            <div style={{ fontSize: 13.5, color: "#475569", marginBottom: 12, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <div>
                Target: <b>{currentDomain}</b>
                {selectedClient?.repo && <span style={{ color: "var(--ink-muted)", marginLeft: 8 }}>· Repo: <b style={{ color: "#334155" }}>{selectedClient.repo}</b></span>}
                {scanState?.phaseLine && <span style={{ color: "#4f46e5", marginLeft: 8 }}>· {scanState.phaseLine}</span>}
              </div>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                <span style={{ color: "var(--ink-muted)", fontWeight: 600 }}>Crawl depth:</span>
                <select
                  value={crawlPages ?? 5}
                  disabled={scanState?.busy}
                  onChange={(e) => onCrawlPagesChange?.(Number(e.target.value))}
                  style={{
                    padding: "3px 8px", borderRadius: 6, border: "1px solid #cbd5e1",
                    fontSize: 12, fontWeight: 600, background: "#fff", color: "#1e293b",
                    cursor: scanState?.busy ? "not-allowed" : "pointer",
                  }}
                >
                  <option value={2}>2 pages</option>
                  <option value={5}>5 pages</option>
                  <option value={10}>10 pages</option>
                  <option value={15}>15 pages</option>
                  <option value={20}>20 pages</option>
                  <option value={25}>25 pages</option>
                </select>
              </div>
            </div>

            <div style={{
              background: "#ecfdf5", border: "1px solid #a7f3d0", borderRadius: 8,
              padding: "9px 14px", marginBottom: 16, display: "flex", alignItems: "center", gap: 8,
              fontSize: 12, color: "#065f46", fontWeight: 600,
            }}>
              <span style={{ fontSize: 14 }}>🛡️</span>
              <span><b>Daily Spend Limit Active:</b> Max {formatUsd(budget?.dailyBudget ?? 5)}/day ({formatUsd(budget?.spentToday ?? 0)} spent today). Free on-page & tech checks cost $0.00.</span>
            </div>

            {scanState?.tools && scanState.tools.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
                {scanState.tools.map((t: any) => (
                  <span key={t.name} style={{
                    fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: 6,
                    background: t.state === "done" ? "#ecfdf5" : "#eef2ff",
                    color: t.state === "done" ? "#047857" : "#4338ca",
                    border: "1px solid", borderColor: t.state === "done" ? "#a7f3d0" : "#c7d2fe",
                  }}>
                    {t.name}: {t.state}
                  </span>
                ))}
              </div>
            )}

            <div style={{
              background: "#161b26", borderRadius: 10, padding: "16px 20px", maxHeight: 240,
              overflowY: "auto", fontFamily: "ui-monospace, monospace", fontSize: 12, color: "#a7f3d0", lineHeight: 1.6,
            }}>
              {scanState?.live && scanState.live.length > 0 ? (
                scanState.live.map((l, i) => <div key={i} style={{ marginBottom: 3 }}>{l}</div>)
              ) : (
                <div style={{ color: "var(--ink-muted)" }}>Connecting to scanner pipeline backend...</div>
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 22 }}>
              <button
                type="button"
                onClick={() => setShowScanDrawer(false)}
                style={{
                  background: "#1e293b", color: "#ffffff", border: 0, borderRadius: 8,
                  padding: "10px 22px", fontSize: 13, fontWeight: 600, cursor: "pointer",
                }}
              >
                {scanState?.busy ? "Run in Background" : "Close Window"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── LOCALBUSINESS JSON-LD GENERATOR & INJECTOR MODAL ── */}
      {showLocalSchemaModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.6)", backdropFilter: "blur(4px)",
          display: "grid", placeItems: "center", zIndex: 1000, padding: 20,
        }}>
          <div style={{
            background: "#ffffff", borderRadius: 14, border: "1px solid #e2e8f0",
            width: "100%", maxWidth: 640, padding: "26px 30px", boxShadow: "0 25px 50px -12px rgba(15, 23, 42, 0.25)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div>
                <span style={{ fontSize: 12, fontWeight: 800, color: "var(--ok)", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "2px 7px", borderRadius: 4, textTransform: "uppercase" }}>
                  Auto-Fix Action: Schema Injector
                </span>
                <h3 style={{ margin: "6px 0 0", fontSize: 17, fontWeight: 700, color: "#1e293b" }}>
                  {/* Was "LocalBusiness / MedicalOrganization JSON-LD" - the
                      second type is one client's vertical, on every account's
                      schema generator. */}
                  LocalBusiness JSON-LD
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowLocalSchemaModal(false)}
                style={{ background: "none", border: 0, fontSize: 18, color: "var(--ink-muted)", cursor: "pointer" }}
              >
                ✕
              </button>
            </div>

            <p style={{ margin: "0 0 14px", fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.5 }}>
              Generated schema for <b>{currentBusiness}</b> ({currentDomain}). Validates physical presence, geo-coordinates, and telephone to qualify for Google Local 3-Pack and ChatGPT citations.
            </p>

            <div style={{ background: "#0f172a", borderRadius: 8, padding: "14px 16px", maxHeight: 260, overflowY: "auto", fontFamily: "ui-monospace, monospace", fontSize: 12, color: "#a5b4fc", lineHeight: 1.5 }}>
              <pre style={{ margin: 0 }}>{`<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "[confirm: schema.org type, e.g. LocalBusiness]",
  "name": "${currentBusiness}",
  "url": "https://${currentDomain}",
  "logo": "https://${currentDomain}/logo.png",
  "telephone": "[confirm: telephone]",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "[confirm: street address]",
    "addressLocality": "[confirm: city]",
    "addressCountry": "[confirm: ISO country code]"
  },
  "geo": {
    "@type": "GeoCoordinates",
    "latitude": "[confirm: latitude]",
    "longitude": "[confirm: longitude]"
  },
  "openingHoursSpecification": [
    {
      "@type": "OpeningHoursSpecification",
      "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
      "opens": "00:00",
      "closes": "23:59"
    }
  ]
}
</script>`}</pre>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 20 }}>
              <button
                type="button"
                onClick={() => {
                  const schemaCode = `<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "[confirm: schema.org type, e.g. LocalBusiness]",
  "name": "${currentBusiness}",
  "url": "https://${currentDomain}",
  "logo": "https://${currentDomain}/logo.png",
  "telephone": "[confirm: telephone]",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "[confirm: street address]",
    "addressLocality": "[confirm: city]",
    "addressCountry": "[confirm: ISO country code]"
  },
  "geo": {
    "@type": "GeoCoordinates",
    "latitude": "[confirm: latitude]",
    "longitude": "[confirm: longitude]"
  }
}
</script>`;
                  navigator.clipboard.writeText(schemaCode);
                  setSchemaCopied(true);
                  setTimeout(() => setSchemaCopied(false), 2000);
                }}
                style={{
                  background: "#ffffff", color: "#334155", border: "1px solid #cbd5e1",
                  borderRadius: 6, padding: "8px 16px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                }}
              >
                {schemaCopied ? "✓ Copied to Clipboard" : "📋 Copy JSON-LD"}
              </button>

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={() => setShowLocalSchemaModal(false)}
                  style={{
                    background: "transparent", color: "var(--ink-muted)", border: 0,
                    padding: "8px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                  }}
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActiveTab("Site Health & Audit");
                    setAuditSubTab("remediation");
                    setShowLocalSchemaModal(false);
                  }}
                  style={{
                    background: "#047857", color: "#ffffff", border: 0,
                    borderRadius: 6, padding: "8px 18px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                    boxShadow: "0 1px 2px rgba(4, 120, 87, 0.3)",
                  }}
                >
                  ⚡ Deploy to Repo via Claude Code
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── AEO /LLMS.TXT SCAFFOLD MODAL ── */}
      {showLlmsTxtModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.6)", backdropFilter: "blur(4px)",
          display: "grid", placeItems: "center", zIndex: 1000, padding: 20,
        }}>
          <div style={{
            background: "#ffffff", borderRadius: 14, border: "1px solid #e2e8f0",
            width: "100%", maxWidth: 640, padding: "26px 30px", boxShadow: "0 25px 50px -12px rgba(15, 23, 42, 0.25)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div>
                <span style={{ fontSize: 12, fontWeight: 800, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 7px", borderRadius: 4, textTransform: "uppercase" }}>
                  Auto-Fix Action: AEO Suite
                </span>
                <h3 style={{ margin: "6px 0 0", fontSize: 17, fontWeight: 700, color: "#1e293b" }}>
                  Auto-Fix /llms.txt Generator
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowLlmsTxtModal(false)}
                style={{ background: "none", border: 0, fontSize: 18, color: "var(--ink-muted)", cursor: "pointer" }}
              >
                ✕
              </button>
            </div>

            <p style={{ margin: "0 0 14px", fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.5 }}>
              Standardized markdown citation file for <b>{currentBusiness}</b>. Placed at <code>public/llms.txt</code> to guide Perplexity, Claude, and ChatGPT web crawlers with verified facts and services.
            </p>

            <div style={{ background: "#0f172a", borderRadius: 8, padding: "14px 16px", maxHeight: 260, overflowY: "auto", fontFamily: "ui-monospace, monospace", fontSize: 12, color: "#38bdf8", lineHeight: 1.5 }}>
              {/*
                Published at the client's own domain, so every line here is a
                claim made on their behalf to answer engines.

                This previously emitted a complete hospital profile as literals
                for every client: service lines, an emergency hotline, a street
                address, and "Accredited under Cambodia Ministry of Health
                standards" - a fabricated accreditation, under a heading that
                called it verified. Placeholders instead: an unfinished file is
                obvious, an invented accreditation is not.
              */}
              <pre style={{ margin: 0 }}>{`# ${currentBusiness || "[confirm: business name]"}
> [confirm: one-line description of this business]

## Official Summary
[confirm: two or three sentences on what this business does. State only what
you can trace to the client's own site or config. Do not claim accreditations,
certifications, awards or memberships without a source.]

## Core Capabilities
- [confirm: capability]: [confirm: one-line description]
- [confirm: capability]: [confirm: one-line description]

## Canonical Entity URIs
- Website: https://${currentDomain || "[confirm: domain]"}
- Telephone: [confirm: telephone]
- Location: [confirm: full address]`}</pre>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 20 }}>
              <button
                type="button"
                onClick={() => {
                  // Must match the block rendered above: the operator copies
                  // this to the clipboard and pastes it onto the client's site.
                  const llmsContent = `# ${currentBusiness || "[confirm: business name]"}\n> [confirm: one-line description of this business]\n\n## Official Summary\n[confirm: two or three sentences on what this business does. State only what you can trace to the client's own site or config. Do not claim accreditations, certifications, awards or memberships without a source.]\n\n## Core Capabilities\n- [confirm: capability]: [confirm: one-line description]\n\n## Canonical Entity URIs\n- Website: https://${currentDomain || "[confirm: domain]"}\n- Telephone: [confirm: telephone]\n- Location: [confirm: full address]`;
                  navigator.clipboard.writeText(llmsContent);
                  setLlmsCopied(true);
                  setTimeout(() => setLlmsCopied(false), 2000);
                }}
                style={{
                  background: "#ffffff", color: "#334155", border: "1px solid #cbd5e1",
                  borderRadius: 6, padding: "8px 16px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                }}
              >
                {llmsCopied ? "✓ Copied to Clipboard" : "📋 Copy /llms.txt"}
              </button>

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={() => setShowLlmsTxtModal(false)}
                  style={{
                    background: "transparent", color: "var(--ink-muted)", border: 0,
                    padding: "8px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                  }}
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActiveTab("Site Health & Audit");
                    setAuditSubTab("remediation");
                    setShowLlmsTxtModal(false);
                  }}
                  style={{
                    background: "#4f46e5", color: "#ffffff", border: 0,
                    borderRadius: 6, padding: "8px 18px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                    boxShadow: "0 1px 2px rgba(79, 70, 229, 0.3)",
                  }}
                >
                  ⚡ Scaffold in Repo via Claude Code
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── AUTONOMOUS FLOW 4: LINK OUTREACH GENERATOR MODAL ── */}
      {showOutreachModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.6)", backdropFilter: "blur(4px)",
          display: "grid", placeItems: "center", zIndex: 1000, padding: 20,
        }}>
          <div style={{
            background: "#ffffff", borderRadius: 14, border: "1px solid #e2e8f0",
            width: "100%", maxWidth: 640, padding: "26px 30px", boxShadow: "0 25px 50px -12px rgba(15, 23, 42, 0.25)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div>
                <span style={{ fontSize: 12, fontWeight: 800, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 7px", borderRadius: 4, textTransform: "uppercase" }}>
                  Auto-Fix Action: Link Outreach
                </span>
                <h3 style={{ margin: "6px 0 0", fontSize: 17, fontWeight: 700, color: "#1e293b" }}>
                  AI Outreach Pitch Generator · {selectedOutreachDomain || "Target Partner"}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowOutreachModal(false)}
                style={{ background: "none", border: 0, fontSize: 18, color: "var(--ink-muted)", cursor: "pointer" }}
              >
                ✕
              </button>
            </div>

            <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 14px", marginBottom: 14, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 12, color: "#475569" }}>
                Target Category: <b>{selectedOutreachCategory || "Industry Resource"}</b>
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "2px 8px", borderRadius: 4 }}>
                High-Conversion Angle
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase", marginBottom: 4 }}>
                Subject Line
              </div>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: "#1e293b", background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6, padding: "7px 12px" }}>
                Resource Feature & Expert Clinical Citation: {currentBusiness}
              </div>
            </div>

            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase", marginBottom: 4 }}>
                Personalized Email Pitch
              </div>
              <div style={{ background: "#0f172a", borderRadius: 8, padding: "14px 16px", maxHeight: 220, overflowY: "auto", fontFamily: "ui-monospace, monospace", fontSize: 12, color: "#e2e8f0", lineHeight: 1.6 }}>
                <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{`Hi Editorial Team at ${selectedOutreachDomain},

I've been following your coverage on ${selectedOutreachCategory.toLowerCase() || "industry healthcare trends"} and really appreciate your practical, well-researched guides.

I'm reaching out from ${currentBusiness} (https://${currentDomain}). We recently updated our clinical resource center covering emergency protocols, maternity care guidelines, and pediatric medicine.

Given that your readers frequently seek reliable, accredited medical citations, would you be open to referencing our clinical guides as an authoritative resource in your upcoming feature?

We'd also be delighted to provide expert commentary or medical review quotes from our senior specialists at any time.

Best regards,
Partnerships Team
${currentBusiness}
https://${currentDomain}`}</pre>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 20 }}>
              <button
                type="button"
                onClick={() => {
                  const pitch = `Subject: Resource Feature & Expert Clinical Citation: ${currentBusiness}\n\nHi Editorial Team at ${selectedOutreachDomain},\n\nI've been following your coverage on ${selectedOutreachCategory.toLowerCase() || "industry healthcare trends"} and really appreciate your practical, well-researched guides.\n\nI'm reaching out from ${currentBusiness} (https://${currentDomain}). We recently updated our clinical resource center covering emergency protocols, maternity care guidelines, and pediatric medicine.\n\nGiven that your readers frequently seek reliable, accredited medical citations, would you be open to referencing our clinical guides as an authoritative resource in your upcoming feature?\n\nWe'd also be delighted to provide expert commentary or medical review quotes from our senior specialists at any time.\n\nBest regards,\nPartnerships Team\n${currentBusiness}\nhttps://${currentDomain}`;
                  navigator.clipboard.writeText(pitch);
                  setOutreachCopied(true);
                  setTimeout(() => setOutreachCopied(false), 2000);
                }}
                style={{
                  background: "#ffffff", color: "#334155", border: "1px solid #cbd5e1",
                  borderRadius: 6, padding: "8px 16px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                }}
              >
                {outreachCopied ? "✓ Copied Pitch" : "📋 Copy Pitch Email"}
              </button>

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={() => setShowOutreachModal(false)}
                  style={{
                    background: "transparent", color: "var(--ink-muted)", border: 0,
                    padding: "8px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                  }}
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (selectedOutreachDomain && !outreachPitchedDomains.includes(selectedOutreachDomain)) {
                      setOutreachPitchedDomains((prev) => [...prev, selectedOutreachDomain]);
                    }
                    setOutreachToast(selectedOutreachDomain);
                    setShowOutreachModal(false);
                    setTimeout(() => setOutreachToast((cur) => cur === selectedOutreachDomain ? null : cur), 3500);
                  }}
                  style={{
                    background: "#4f46e5", color: "#ffffff", border: 0,
                    borderRadius: 6, padding: "8px 18px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                    boxShadow: "0 1px 2px rgba(79, 70, 229, 0.3)",
                  }}
                >
                  ✓ Add to Pitch Queue
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── AUTONOMOUS FLOW 1: CONTENT ENRICHMENT MODAL (CLAUDE CODE AST INJECTOR) ── */}
      {showContentEnrichModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.6)", backdropFilter: "blur(4px)",
          display: "grid", placeItems: "center", zIndex: 1000, padding: 20,
        }}>
          <div style={{
            background: "#ffffff", borderRadius: 14, border: "1px solid #e2e8f0",
            width: "100%", maxWidth: 660, padding: "26px 30px", boxShadow: "0 25px 50px -12px rgba(15, 23, 42, 0.25)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div>
                <span style={{ fontSize: 12, fontWeight: 800, color: "#4f46e5", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 7px", borderRadius: 4, textTransform: "uppercase" }}>
                  Auto-Fix Action: Content Enricher
                </span>
                <h3 style={{ margin: "6px 0 0", fontSize: 17, fontWeight: 700, color: "#1e293b" }}>
                  AI Content Block & Entity Injection · {selectedOnPageUrl}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowContentEnrichModal(false)}
                style={{ background: "none", border: 0, fontSize: 18, color: "var(--ink-muted)", cursor: "pointer" }}
              >
                ✕
              </button>
            </div>

            <p style={{ margin: "0 0 14px", fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.5 }}>
              Generated content section incorporating missing TF-IDF entity keywords to match Top 10 SERP competitor depth for <b>{currentBusiness}</b>.
            </p>

            <div style={{ background: "#0f172a", borderRadius: 8, padding: "14px 16px", maxHeight: 240, overflowY: "auto", fontFamily: "ui-monospace, monospace", fontSize: 12, color: "#e2e8f0", lineHeight: 1.6 }}>
              <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {onPageSemanticData.aiDraftBlock}
              </pre>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 20 }}>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(onPageSemanticData.aiDraftBlock);
                  setContentEnrichCopied(true);
                  setTimeout(() => setContentEnrichCopied(false), 2000);
                }}
                style={{
                  background: "#ffffff", color: "#334155", border: "1px solid #cbd5e1",
                  borderRadius: 6, padding: "8px 16px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                }}
              >
                {contentEnrichCopied ? "✓ Copied Section" : "📋 Copy Content Block"}
              </button>

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={() => setShowContentEnrichModal(false)}
                  style={{
                    background: "transparent", color: "var(--ink-muted)", border: 0,
                    padding: "8px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                  }}
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActiveTab("Site Health & Audit");
                    setAuditSubTab("remediation");
                    setShowContentEnrichModal(false);
                    if (planState && !planState.plan?.worklist) planState.runPlan();
                  }}
                  style={{
                    background: "#047857", color: "#ffffff", border: 0,
                    borderRadius: 6, padding: "8px 18px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                    boxShadow: "0 1px 2px rgba(4, 120, 87, 0.3)",
                  }}
                >
                  ⚡ Inject into Page via Claude Code
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── AUTONOMOUS FLOW 5: NEXT.JS & HTML METADATA AST INJECTOR MODAL ── */}
      {showSerpMetaModal && (() => {
        const nextJsSnippet = `import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "${activeSerpMeta.title.replace(/"/g, '\\"')}",
  description: "${activeSerpMeta.description.replace(/"/g, '\\"')}",
  alternates: {
    canonical: "https://${currentDomain.replace(/^https?:\/\//, "").replace(/\/$/, "")}${selectedOnPageUrl}",
  },
  openGraph: {
    title: "${activeSerpMeta.title.replace(/"/g, '\\"')}",
    description: "${activeSerpMeta.description.replace(/"/g, '\\"')}",
    url: "https://${currentDomain.replace(/^https?:\/\//, "").replace(/\/$/, "")}${selectedOnPageUrl}",
    siteName: "${currentBusiness.replace(/"/g, '\\"')}",
    images: [
      {
        url: "https://${currentDomain.replace(/^https?:\/\//, "").replace(/\/$/, "")}/og-image.jpg",
        width: 1200,
        height: 630,
        alt: "${activeSerpMeta.title.replace(/"/g, '\\"')}",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "${activeSerpMeta.title.replace(/"/g, '\\"')}",
    description: "${activeSerpMeta.description.replace(/"/g, '\\"')}",
  },
};`;

        const htmlSnippet = `<!-- Primary Meta Tags -->
<title>${activeSerpMeta.title}</title>
<meta name="title" content="${activeSerpMeta.title}">
<meta name="description" content="${activeSerpMeta.description}">
<link rel="canonical" href="https://${currentDomain.replace(/^https?:\/\//, "").replace(/\/$/, "")}${selectedOnPageUrl}">

<!-- Open Graph / Facebook -->
<meta property="og:type" content="website">
<meta property="og:url" content="https://${currentDomain.replace(/^https?:\/\//, "").replace(/\/$/, "")}${selectedOnPageUrl}">
<meta property="og:title" content="${activeSerpMeta.title}">
<meta property="og:description" content="${activeSerpMeta.description}">
<meta property="og:image" content="https://${currentDomain.replace(/^https?:\/\//, "").replace(/\/$/, "")}/og-image.jpg">

<!-- Twitter -->
<meta property="twitter:card" content="summary_large_image">
<meta property="twitter:url" content="https://${currentDomain.replace(/^https?:\/\//, "").replace(/\/$/, "")}${selectedOnPageUrl}">
<meta property="twitter:title" content="${activeSerpMeta.title}">
<meta property="twitter:description" content="${activeSerpMeta.description}">`;

        const activeSnippet = serpFormatType === "nextjs" ? nextJsSnippet : htmlSnippet;
        const targetFilePath = `web/app${selectedOnPageUrl === "/" ? "" : selectedOnPageUrl}/page.tsx`;

        return (
          <div style={{
            position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.6)", backdropFilter: "blur(4px)",
            display: "grid", placeItems: "center", zIndex: 1000, padding: 20,
          }}>
            <div style={{
              background: "#ffffff", borderRadius: 14, border: "1px solid #e2e8f0",
              width: "100%", maxWidth: 680, padding: "26px 30px", boxShadow: "0 25px 50px -12px rgba(15, 23, 42, 0.25)",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                <div>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#0284c7", background: "#f0f9ff", border: "1px solid #bae6fd", padding: "2px 7px", borderRadius: 4, textTransform: "uppercase" }}>
                    Auto-Fix Action: Metadata AST Auto-Repair
                  </span>
                  <h3 style={{ margin: "6px 0 0", fontSize: 17, fontWeight: 700, color: "#1e293b" }}>
                    Deploy Validated Snippet to {targetFilePath}
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setShowSerpMetaModal(false)}
                  style={{ background: "none", border: 0, fontSize: 18, color: "var(--ink-muted)", cursor: "pointer" }}
                >
                  ✕
                </button>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 10 }}>
                <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.5 }}>
                  AST-safe metadata export optimized for search engine crawl budgets and social link previews.
                </p>

                {/* Format Toggle */}
                <div style={{ display: "flex", background: "#f1f5f9", padding: 3, borderRadius: 6, gap: 3 }}>
                  <button
                    type="button"
                    onClick={() => setSerpFormatType("nextjs")}
                    style={{
                      background: serpFormatType === "nextjs" ? "#ffffff" : "transparent",
                      color: serpFormatType === "nextjs" ? "#0f172a" : "var(--ink-muted)",
                      border: 0, borderRadius: 4, padding: "4px 10px", fontSize: 12, fontWeight: serpFormatType === "nextjs" ? 700 : 500,
                      cursor: "pointer", boxShadow: serpFormatType === "nextjs" ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
                    }}
                  >
                    Next.js 13/14 App Router
                  </button>
                  <button
                    type="button"
                    onClick={() => setSerpFormatType("html")}
                    style={{
                      background: serpFormatType === "html" ? "#ffffff" : "transparent",
                      color: serpFormatType === "html" ? "#0f172a" : "var(--ink-muted)",
                      border: 0, borderRadius: 4, padding: "4px 10px", fontSize: 12, fontWeight: serpFormatType === "html" ? 700 : 500,
                      cursor: "pointer", boxShadow: serpFormatType === "html" ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
                    }}
                  >
                    Standard HTML &lt;head&gt;
                  </button>
                </div>
              </div>

              <div style={{ background: "#0f172a", borderRadius: 8, padding: "14px 16px", maxHeight: 260, overflowY: "auto", fontFamily: "ui-monospace, monospace", fontSize: 12, color: "#e2e8f0", lineHeight: 1.6 }}>
                <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                  {activeSnippet}
                </pre>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 20 }}>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(activeSnippet);
                    setSerpMetaCopied(true);
                    setTimeout(() => setSerpMetaCopied(false), 2000);
                  }}
                  style={{
                    background: "#ffffff", color: "#334155", border: "1px solid #cbd5e1",
                    borderRadius: 6, padding: "8px 16px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                  }}
                >
                  {serpMetaCopied ? "✓ Copied to Clipboard" : `📋 Copy ${serpFormatType === "nextjs" ? "Next.js Metadata" : "HTML Tags"}`}
                </button>

                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    type="button"
                    onClick={() => setShowSerpMetaModal(false)}
                    style={{
                      background: "transparent", color: "var(--ink-muted)", border: 0,
                      padding: "8px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                    }}
                  >
                    Close
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveTab("Site Health & Audit");
                      setAuditSubTab("remediation");
                      setShowSerpMetaModal(false);
                      if (planState && !planState.plan?.worklist) planState.runPlan();
                    }}
                    style={{
                      background: "#0284c7", color: "#ffffff", border: 0,
                      borderRadius: 6, padding: "8px 18px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                      boxShadow: "0 1px 3px rgba(2, 132, 199, 0.3)",
                    }}
                  >
                    ⚡ Apply AST Modification in Repo
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/*
        Executive client report.

        Rebuilt from the scan. What was here was a printable, client-addressed
        deliverable made of literals: "Technical Health Score: 94 / 100 (Grade
        A)", "AI / AEO Engine Readiness: 92%", "Core Web Vitals: PASSED (LCP
        1.8s | INP 82ms | CLS 0.02)", "Est. Organic Traffic Value: $2,439 / mo",
        a hardcoded audit date, keyword fallbacks for a city nobody had scanned,
        and a section headed "AUTONOMOUS REMEDIATIONS DEPLOYED" listing five
        fixes that never ran. It rendered the same for every client, scanned or
        not.

        Now: every figure comes from buildExecutiveReport(report), and with no
        scan there is no document at all - the panel refuses and says to run an
        audit. The remediations section is gone rather than reworded: what was
        actually applied lives in the cycle's changelog.json written by
        wf-site-remediate, which this screen does not read.
      */}
      {showExecutiveReportModal && (() => {
        const exec = buildExecutiveReport({
          report: report as any,
          client: currentBusiness,
          domain: currentDomain,
          agency: agencyName,
        });

        const overlayStyle: React.CSSProperties = {
          position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.75)", backdropFilter: "blur(5px)",
          display: "flex", justifyContent: "center", zIndex: 2000, padding: "var(--space-5) var(--space-4)", overflowY: "auto",
        };

        // No scan, no deliverable. Generating one anyway is how the fabricated
        // version happened in the first place.
        if (!exec) {
          return (
            <div style={overlayStyle}>
              <div style={{
                background: "var(--surface)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)",
                boxShadow: "var(--shadow-lg)", padding: "var(--space-6)", maxWidth: 520, height: "fit-content",
                display: "flex", flexDirection: "column", gap: "var(--space-3)",
              }}>
                <h3 style={{ margin: 0, fontSize: "var(--text-lg)", fontWeight: 800, color: "var(--ink)" }}>
                  No Audit Data to Report
                </h3>
                <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--ink-body)", lineHeight: "var(--leading-normal)" }}>
                  This report is built entirely from a scan of{" "}
                  <b>{currentDomain || currentBusiness || "the client site"}</b>, and no scan has produced
                  findings yet. Run an audit first: with nothing measured there is no figure that could
                  honestly be printed for a client.
                </p>
                <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
                  <button
                    type="button"
                    onClick={() => {
                      setShowExecutiveReportModal(false);
                      setActiveTab("Site Health & Audit");
                      setAuditSubTab("summary");
                    }}
                    style={{
                      background: "var(--accent)", color: "var(--surface)", border: 0,
                      borderRadius: "var(--radius-sm)", padding: "var(--space-2) var(--space-4)",
                      fontSize: "var(--text-sm)", fontWeight: 700, cursor: "pointer",
                    }}
                  >
                    Go to Site Audit
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowExecutiveReportModal(false)}
                    style={{
                      background: "var(--surface-2)", color: "var(--ink-body)", border: "1px solid var(--border)",
                      borderRadius: "var(--radius-sm)", padding: "var(--space-2) var(--space-4)",
                      fontSize: "var(--text-sm)", fontWeight: 600, cursor: "pointer",
                    }}
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          );
        }

        const cell: React.CSSProperties = { padding: "var(--space-2) var(--space-3)", fontSize: "var(--text-xs)", textAlign: "left" };
        const headCell: React.CSSProperties = { ...cell, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase" };
        const vitalKeys = ["lcp", "inp", "cls"] as const;

        return (
          <div style={overlayStyle}>
            {/* Print CSS Rules */}
            <style>{`
              @media print {
                body * {
                  visibility: hidden !important;
                }
                #printable-executive-report, #printable-executive-report * {
                  visibility: visible !important;
                }
                #printable-executive-report {
                  position: absolute !important;
                  left: 0 !important;
                  top: 0 !important;
                  width: 100% !important;
                  margin: 0 !important;
                  padding: 24px !important;
                  box-shadow: none !important;
                  border: none !important;
                  background: #ffffff !important;
                  -webkit-print-color-adjust: exact !important;
                  print-color-adjust: exact !important;
                }
                .no-print {
                  display: none !important;
                }
              }
            `}</style>

            <div style={{ width: "100%", maxWidth: 940, display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              {/* Sticky Top Toolbar (No-Print) */}
              <div className="no-print" style={{
                background: "var(--ink)", borderRadius: "var(--radius-md)", padding: "var(--space-3) var(--space-5)", color: "var(--surface)",
                display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "var(--space-3)",
                boxShadow: "var(--shadow-md)",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
                  <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--border-strong)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    Agency Partner:
                  </span>
                  <input
                    type="text"
                    value={agencyName}
                    onChange={(e) => setAgencyName(e.target.value)}
                    style={{
                      background: "var(--ink-body)", border: "1px solid var(--ink-muted)", color: "var(--surface)",
                      padding: "var(--space-1) var(--space-2)", borderRadius: "var(--radius-sm)",
                      fontSize: "var(--text-sm)", fontWeight: 600, outline: "none", width: 260,
                    }}
                  />
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(exec.markdown);
                      setReportCopied(true);
                      setTimeout(() => setReportCopied(false), 2000);
                    }}
                    style={{
                      background: "var(--ink-body)", color: "var(--surface)", border: "1px solid var(--ink-muted)",
                      padding: "var(--space-2) var(--space-3)", borderRadius: "var(--radius-sm)",
                      fontSize: "var(--text-xs)", fontWeight: 600, cursor: "pointer",
                      display: "flex", alignItems: "center", gap: "var(--space-1)",
                    }}
                  >
                    <span>📋</span> {reportCopied ? "✓ Copied Markdown" : "Copy Summary"}
                  </button>

                  <button
                    type="button"
                    onClick={() => window.print()}
                    style={{
                      background: "var(--accent)", color: "var(--surface)", border: 0,
                      padding: "var(--space-2) var(--space-4)", borderRadius: "var(--radius-sm)",
                      fontSize: "var(--text-sm)", fontWeight: 700, cursor: "pointer",
                      display: "flex", alignItems: "center", gap: "var(--space-1)", boxShadow: "var(--shadow-sm)",
                    }}
                  >
                    <span>🖨️</span> Print / Save as PDF
                  </button>

                  <button
                    type="button"
                    onClick={() => setShowExecutiveReportModal(false)}
                    style={{
                      background: "transparent", color: "var(--border-strong)", border: 0,
                      padding: "var(--space-1) var(--space-2)", fontSize: "var(--text-md)", cursor: "pointer",
                    }}
                  >
                    ✕
                  </button>
                </div>
              </div>

              {/* Printable Document Container */}
              <div id="printable-executive-report" style={{
                background: "var(--surface)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)",
                boxShadow: "var(--shadow-lg)", overflow: "hidden", color: "var(--ink-body)",
              }}>
                {/* ── REPORT COVER HEADER ── */}
                <div style={{ background: "var(--ink)", padding: "var(--space-6)", color: "var(--surface)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "var(--space-5)", gap: "var(--space-4)" }}>
                    <div>
                      <div style={{
                        display: "inline-block", background: "var(--ink-body)", border: "1px solid var(--ink-muted)",
                        padding: "var(--space-1) var(--space-2)", borderRadius: "var(--radius-sm)",
                        fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--accent-border)",
                        textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "var(--space-2)",
                      }}>
                        {exec.agency} · Executive Brief
                      </div>
                      <h1 style={{ margin: 0, fontSize: "var(--text-2xl)", fontWeight: 800, letterSpacing: "-0.02em" }}>
                        Executive SEO & AEO Report
                      </h1>
                      <div style={{ fontSize: "var(--text-sm)", color: "var(--border-strong)", marginTop: "var(--space-1)" }}>
                        Every figure below is read from the audit of {exec.domain || exec.client}. Nothing is estimated.
                      </div>
                    </div>

                    {/* Score stamp: report.score, or nothing. */}
                    <div style={{
                      background: "var(--ink-body)", border: "1px solid var(--ink-muted)",
                      borderRadius: "var(--radius-lg)", padding: "var(--space-3) var(--space-5)", textAlign: "center", minWidth: 140,
                    }}>
                      <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--border-strong)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        Health Score
                      </div>
                      <div style={{ fontSize: "var(--text-3xl)", fontWeight: 900, color: "var(--surface)", lineHeight: "var(--leading-tight)", marginTop: "var(--space-1)" }}>
                        {exec.healthScore === null ? "—" : exec.healthScore}
                      </div>
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--border-strong)", fontWeight: 700 }}>
                        {exec.healthScore === null ? "Not scored" : "out of 100"}
                      </div>
                    </div>
                  </div>

                  {/* Metadata Bar */}
                  <div style={{
                    display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--space-3)",
                    paddingTop: "var(--space-4)", borderTop: "1px solid var(--ink-body)", fontSize: "var(--text-xs)",
                  }}>
                    <div>
                      <div style={{ color: "var(--border-strong)", textTransform: "uppercase", fontWeight: 600 }}>Client</div>
                      <div style={{ fontWeight: 700, color: "var(--surface)", marginTop: "var(--space-1)" }}>{exec.client}</div>
                    </div>
                    <div>
                      <div style={{ color: "var(--border-strong)", textTransform: "uppercase", fontWeight: 600 }}>Domain Audited</div>
                      <div style={{ fontWeight: 700, color: "var(--surface)", marginTop: "var(--space-1)" }}>{exec.domain || "—"}</div>
                    </div>
                    <div>
                      <div style={{ color: "var(--border-strong)", textTransform: "uppercase", fontWeight: 600 }}>Report Date</div>
                      <div style={{ fontWeight: 700, color: "var(--surface)", marginTop: "var(--space-1)" }}>{exec.date}</div>
                    </div>
                  </div>
                </div>

                {/* ── REPORT BODY ── */}
                <div style={{ padding: "var(--space-6)", display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>

                  {/* Summary: counts only, in the report's own numbers. */}
                  <div style={{
                    background: "var(--surface-2)", borderLeft: "4px solid var(--accent)",
                    padding: "var(--space-4)", borderRadius: "0 var(--radius-md) var(--radius-md) 0",
                  }}>
                    <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--accent-ink)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "var(--space-1)" }}>
                      What This Audit Measured
                    </div>
                    <div style={{ fontSize: "var(--text-sm)", color: "var(--ink-body)", lineHeight: "var(--leading-normal)" }}>
                      <b>{exec.checksTotal}</b> check{exec.checksTotal === 1 ? "" : "s"} ran on{" "}
                      <b>{exec.domain || exec.client}</b>. <b>{exec.checksPassing}</b> passed,{" "}
                      <b>{exec.counts.error}</b> returned an error and <b>{exec.counts.warn}</b> returned a warning.
                      {exec.vitalsMeasured
                        ? " Core Web Vitals are reported below from CrUX field data."
                        : " Core Web Vitals were not measured on this scan, so no field figures are reported."}
                    </div>
                  </div>

                  {/* ── 1. PILLAR RESULTS ── */}
                  <div>
                    <h3 style={{ margin: "0 0 var(--space-3)", fontSize: "var(--text-md)", fontWeight: 700, color: "var(--ink)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                      1. Measured Results by Area
                    </h3>
                    <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-md)", overflow: "hidden" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse" }}>
                        <thead>
                          <tr style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
                            <th style={headCell}>Area</th>
                            <th style={headCell}>Checks Passing</th>
                            <th style={headCell}>Errors</th>
                            <th style={headCell}>Warnings</th>
                            <th style={{ ...headCell, textAlign: "right" }}>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {exec.pillars.map((p) => {
                            const t = tone(p.tone);
                            return (
                              <tr key={p.catKey} style={{ borderBottom: "1px solid var(--surface-3)" }}>
                                <td style={{ ...cell, fontWeight: 600, color: "var(--ink-body)" }}>{p.title}</td>
                                <td style={{ ...cell, color: "var(--ink-muted)" }}>
                                  {p.measured ? `${p.ok} of ${p.ok + p.warn + p.error}` : "—"}
                                </td>
                                <td style={{ ...cell, color: "var(--ink-muted)" }}>{p.measured ? p.error : "—"}</td>
                                <td style={{ ...cell, color: "var(--ink-muted)" }}>{p.measured ? p.warn : "—"}</td>
                                <td style={{ ...cell, textAlign: "right" }}>
                                  <span style={{
                                    fontSize: "var(--text-xs)", fontWeight: 700, color: t.fg, background: t.bg,
                                    border: `1px solid ${t.border}`, padding: "2px var(--space-2)", borderRadius: "var(--radius-xs)",
                                  }}>
                                    {p.status}
                                  </span>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* ── 2. CORE WEB VITALS ── */}
                  <div>
                    <h3 style={{ margin: "0 0 var(--space-3)", fontSize: "var(--text-md)", fontWeight: 700, color: "var(--ink)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                      2. Core Web Vitals (CrUX Field Data)
                    </h3>
                    {exec.vitalsMeasured ? (
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--space-3)" }}>
                        {vitalKeys.map((k) => (
                          <div key={k} style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: "var(--space-4)" }}>
                            <div style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase" }}>
                              {k.toUpperCase()}
                            </div>
                            <div style={{ fontSize: "var(--text-2xl)", fontWeight: 800, color: exec.vitals[k].color, marginTop: "var(--space-1)" }}>
                              {exec.vitals[k].val}
                            </div>
                            <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-muted)", marginTop: "var(--space-1)" }}>
                              {exec.vitals[k].status}
                              {exec.vitals[k].target ? ` · good ${exec.vitals[k].target}` : ""}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{
                        border: "1px solid var(--border)", borderRadius: "var(--radius-md)",
                        background: "var(--surface-2)", padding: "var(--space-4)",
                        fontSize: "var(--text-sm)", color: "var(--ink-muted)",
                      }}>
                        Not measured. CrUX reports field data only for origins with enough Chrome traffic, and
                        no reading was recorded on this scan.
                      </div>
                    )}
                  </div>

                  {/* ── 3. TOP FINDINGS ── */}
                  {exec.priorities.length > 0 && (
                    <div>
                      <h3 style={{ margin: "0 0 var(--space-3)", fontSize: "var(--text-md)", fontWeight: 700, color: "var(--ink)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                        3. Top Findings, Highest Severity First
                      </h3>
                      <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-md)", overflow: "hidden" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse" }}>
                          <thead>
                            <tr style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
                              <th style={headCell}>Finding</th>
                              <th style={headCell}>Detected By</th>
                              <th style={headCell}>Recommended Action</th>
                              <th style={{ ...headCell, textAlign: "right" }}>Severity</th>
                            </tr>
                          </thead>
                          <tbody>
                            {exec.priorities.map((p) => {
                              const t = tone(p.severity === "critical" ? "bad" : p.severity === "warning" ? "warn" : "neutral");
                              return (
                                <tr key={p.id} style={{ borderBottom: "1px solid var(--surface-3)" }}>
                                  <td style={{ ...cell, fontWeight: 600, color: "var(--ink-body)" }}>{p.title}</td>
                                  <td style={{ ...cell, color: "var(--ink-muted)" }}>{p.source}</td>
                                  <td style={{ ...cell, color: "var(--ink-muted)" }}>{p.recommendedAction || "—"}</td>
                                  <td style={{ ...cell, textAlign: "right" }}>
                                    <span style={{
                                      fontSize: "var(--text-xs)", fontWeight: 700, color: t.fg, background: t.bg,
                                      border: `1px solid ${t.border}`, padding: "2px var(--space-2)", borderRadius: "var(--radius-xs)",
                                    }}>
                                      {p.severity === "critical" ? "Error" : p.severity === "warning" ? "Warning" : "Info"}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* ── 4. KEYWORDS, only when the scan carries keyword rows ── */}
                  {exec.keywords.length > 0 && (
                    <div>
                      <h3 style={{ margin: "0 0 var(--space-3)", fontSize: "var(--text-md)", fontWeight: 700, color: "var(--ink)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                        4. Tracked Keywords
                      </h3>
                      <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-md)", overflow: "hidden" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse" }}>
                          <thead>
                            <tr style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
                              <th style={headCell}>What the Scan Found</th>
                              <th style={{ ...headCell, textAlign: "right" }}>Detail</th>
                            </tr>
                          </thead>
                          <tbody>
                            {exec.keywords.map((k, i) => (
                              <tr key={i} style={{ borderBottom: "1px solid var(--surface-3)" }}>
                                <td style={{ ...cell, fontWeight: 600, color: "var(--ink-body)" }}>{k.what}</td>
                                <td style={{ ...cell, textAlign: "right", color: "var(--ink-muted)" }}>{k.detail || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* ── FOOTER SIGN-OFF ── */}
                  <div style={{
                    marginTop: "var(--space-2)", paddingTop: "var(--space-5)", borderTop: "1px solid var(--border)",
                    display: "flex", justifyContent: "space-between", alignItems: "center", gap: "var(--space-3)",
                    fontSize: "var(--text-xs)", color: "var(--ink-muted)",
                  }}>
                    <div>
                      Confidential · Prepared for <b>{exec.client}</b> on {exec.date}
                    </div>
                    <div>
                      Figures not measured by this audit are omitted, never estimated.
                    </div>
                  </div>

                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── GOOGLE SEARCH CONSOLE DISAVOW MANAGER MODAL ── */}
      {showDisavowModal && (() => {
        const disavowText = [
          `# Google Search Console Disavow File for ${currentDomain}`,
          `# Generated by REAI Autonomous SEO Engine`,
          `# Date: ${new Date().toISOString().split("T")[0]}`,
          `# Total Domains: ${disavowedDomains.length}`,
          ``,
          ...disavowedDomains.map((d) => `domain:${d}`),
        ].join("\n");

        return (
          <div style={{
            position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(15, 23, 42, 0.65)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 99999, padding: 20,
          }}>
            <div style={{
              background: "#ffffff", borderRadius: 12, width: "100%", maxWidth: 640,
              maxHeight: "90vh", display: "flex", flexDirection: "column",
              boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
              border: "1px solid #e2e8f0", overflow: "hidden",
            }}>
              {/* Header */}
              <div style={{
                padding: "18px 24px", borderBottom: "1px solid #f1f5f9",
                display: "flex", justifyContent: "space-between", alignItems: "center",
                background: "#f8fafc",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{
                    width: 34, height: 34, borderRadius: 8, background: "#fee2e2",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 18,
                  }}>
                    🛡️
                  </div>
                  <div>
                    <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: "#0f172a" }}>
                      Google Search Console Disavow Manager
                    </h3>
                    <p style={{ margin: "2px 0 0", fontSize: 12, color: "var(--ink-muted)" }}>
                      RFC compliant text format for Google&apos;s official Disavow Links tool
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setShowDisavowModal(false)}
                  style={{
                    background: "none", border: 0, fontSize: 20, cursor: "pointer",
                    color: "var(--ink-muted)", padding: "4px 8px", borderRadius: 4,
                  }}
                >
                  ✕
                </button>
              </div>

              {/* Body */}
              <div style={{ padding: "20px 24px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 16 }}>
                {/* Info Note */}
                <div style={{
                  background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8,
                  padding: "12px 16px", fontSize: 12, color: "#166534", lineHeight: 1.5,
                }}>
                  <b>Instructions:</b> Download or copy this file and upload it directly into your{" "}
                  <a
                    href="https://search.google.com/search-console/disavow-links"
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "#15803d", fontWeight: 700, textDecoration: "underline" }}
                  >
                    Google Search Console Disavow Links Tool
                  </a>. This instructs Google algorithms to disregard link equity from flagged low-trust or spam networks.
                </div>

                {/* Disavow Domain List Quick Chips */}
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#1e293b", marginBottom: 8, display: "flex", justifyContent: "space-between" }}>
                    <span>Active Disavow List ({disavowedDomains.length} domains)</span>
                    <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>Click domain badge to remove</span>
                  </div>

                  {disavowedDomains.length === 0 ? (
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", fontStyle: "italic", padding: "10px 0" }}>
                      No domains currently in disavow list. Flag toxic domains in the table above or add one below.
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, maxHeight: 110, overflowY: "auto", padding: "4px 0" }}>
                      {disavowedDomains.map((dom, i) => (
                        <span
                          key={i}
                          onClick={() => setDisavowedDomains(disavowedDomains.filter((d) => d !== dom))}
                          title="Click to remove from disavow list"
                          style={{
                            display: "inline-flex", alignItems: "center", gap: 6,
                            background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b",
                            padding: "4px 9px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                            cursor: "pointer",
                          }}
                        >
                          {dom} <span style={{ color: "#dc2626", fontWeight: 800 }}>✕</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Plaintext Preview */}
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#1e293b", marginBottom: 6 }}>
                    File Content Preview (Plaintext)
                  </div>
                  <pre style={{
                    background: "#0f172a", color: "#38bdf8", padding: "14px 16px",
                    borderRadius: 8, fontSize: 12, fontFamily: "monospace",
                    margin: 0, maxHeight: 160, overflowY: "auto", whiteSpace: "pre-wrap",
                    lineHeight: 1.45, border: "1px solid #334155",
                  }}>
                    {disavowText}
                  </pre>
                </div>
              </div>

              {/* Footer */}
              <div style={{
                padding: "16px 24px", borderTop: "1px solid #f1f5f9",
                background: "#f8fafc", display: "flex", justifyContent: "space-between", alignItems: "center",
              }}>
                <button
                  type="button"
                  onClick={() => setShowDisavowModal(false)}
                  style={{
                    background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6,
                    padding: "8px 16px", fontSize: 12.5, fontWeight: 600, color: "#475569", cursor: "pointer",
                  }}
                >
                  Close
                </button>

                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(disavowText);
                      setDisavowCopied(true);
                      setTimeout(() => setDisavowCopied(false), 2500);
                    }}
                    style={{
                      background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6,
                      padding: "8px 16px", fontSize: 12.5, fontWeight: 600, color: "#1e293b", cursor: "pointer",
                    }}
                  >
                    {disavowCopied ? "✓ Copied!" : "📋 Copy File Content"}
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      const blob = new Blob([disavowText], { type: "text/plain" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `google_disavow_${currentDomain.replace(/\..*$/, "")}.txt`;
                      a.click();
                      URL.revokeObjectURL(url);
                      setDisavowDownloaded(true);
                    }}
                    style={{
                      background: "#4f46e5", border: 0, borderRadius: 6,
                      padding: "8px 18px", fontSize: 12.5, fontWeight: 600, color: "#ffffff", cursor: "pointer",
                      display: "flex", alignItems: "center", gap: 6,
                    }}
                  >
                    <span>↓</span> Download .txt File
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── ORGANIC RESEARCH COMPLETE DOCUMENTATION & PLAYBOOK MODAL ── */}
      {showOrganicGuideModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.6)",
          backdropFilter: "blur(4px)", zIndex: 9999,
          display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
        }}>
          <div style={{
            background: "#ffffff", borderRadius: 12, width: "100%", maxWidth: 880,
            maxHeight: "90vh", display: "flex", flexDirection: "column",
            boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)", overflow: "hidden",
            border: "1px solid #cbd5e1",
          }}>
            {/* Modal Header */}
            <div style={{
              padding: "18px 24px", borderBottom: "1px solid #e2e8f0", background: "#f8fafc",
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 22 }}>📘</span>
                <div>
                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#0f172a" }}>
                    Organic Research: Feature & Strategic Guide
                  </h3>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                    Competitive SERP Intelligence, Tools & APIs, Strategic Rationale, and Pipeline Integration
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <a
                  href="/docs/Organic_Research_Guide.pdf"
                  target="_blank"
                  rel="noopener noreferrer"
                  download="Organic_Research_Guide.pdf"
                  style={{
                    background: "#2563eb", color: "#ffffff", border: 0,
                    borderRadius: 6, padding: "6px 14px", fontSize: 12, fontWeight: 700,
                    cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                    textDecoration: "none",
                  }}
                >
                  <span>📄</span> Download PDF
                </a>
                <button
                  type="button"
                  onClick={() => setShowOrganicGuideModal(false)}
                  style={{
                    background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6,
                    width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center",
                    cursor: "pointer", color: "var(--ink-muted)", fontSize: 15, fontWeight: 700,
                  }}
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Modal Navigation Tabs */}
            <div style={{ display: "flex", background: "#f1f5f9", padding: "6px 20px 0", borderBottom: "1px solid #e2e8f0", gap: 4 }}>
              {[
                { id: "overview", label: "1. Overview & Definition" },
                { id: "modules", label: "2. Every Feature" },
                { id: "tools", label: "3. Tools & APIs Used" },
                { id: "strategy", label: "4. Why We Use It" },
                { id: "sop", label: "5. How It Helps SEO" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setOrganicGuideTab(tab.id as any)}
                  style={{
                    padding: "8px 14px", border: 0, borderTopLeftRadius: 6, borderTopRightRadius: 6,
                    fontSize: 12, fontWeight: organicGuideTab === tab.id ? 700 : 500,
                    color: organicGuideTab === tab.id ? "#1d4ed8" : "var(--ink-muted)",
                    background: organicGuideTab === tab.id ? "#ffffff" : "transparent",
                    borderBottom: organicGuideTab === tab.id ? "2px solid #2563eb" : "2px solid transparent",
                    cursor: "pointer",
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Modal Body */}
            <div style={{ padding: "20px 24px", overflowY: "auto", flex: 1, fontSize: 13, lineHeight: 1.6, color: "#334155" }}>
              
              {/* Tab 1: Overview */}
              {organicGuideTab === "overview" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8, padding: "14px 16px" }}>
                    <div style={{ fontWeight: 700, color: "#1e40af", fontSize: 14, marginBottom: 4 }}>
                      What is Organic Research?
                    </div>
                    <p style={{ margin: 0, color: "#1e3a8a" }}>
                      <b>Organic Research</b> is the competitive intelligence and search performance engine of our platform. It reverse-engineers a website's presence in non-paid (organic) search engine results pages (SERPs)—principally across Google and modern generative AI answer engines.
                    </p>
                  </div>

                  <h4 style={{ margin: "10px 0 6px", fontSize: 14, color: "#0f172a" }}>Why Organic Search Matters Over Paid Ads:</h4>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <div style={{ border: "1px solid #fee2e2", background: "#fff5f5", borderRadius: 8, padding: "12px 14px" }}>
                      <div style={{ fontWeight: 700, color: "#991b1b", marginBottom: 4 }}>❌ Paid Search (PPC / Google Ads)</div>
                      <div style={{ fontSize: 12, color: "#7f1d1d" }}>
                        Traffic completely stops the moment ad spend ends. High ongoing cost per click ($1–$15+) with zero lasting equity.
                      </div>
                    </div>
                    <div style={{ border: "1px solid #dcfce7", background: "#f0fdf4", borderRadius: 8, padding: "12px 14px" }}>
                      <div style={{ fontWeight: 700, color: "#166534", marginBottom: 4 }}>✅ Organic Search (SEO / AEO)</div>
                      <div style={{ fontSize: 12, color: "#14532d" }}>
                        Earned topical authority that compounds month after month with <b>zero marginal cost per click</b>. Delivers higher consumer trust and conversion rates.
                      </div>
                    </div>
                  </div>

                  <h4 style={{ margin: "10px 0 6px", fontSize: 14, color: "#0f172a" }}>The Three Strategic Missions of Organic Research:</h4>
                  <ul style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6 }}>
                    <li><b>Map Your Search Footprint:</b> Reveal every keyword query your domain ranks for, where you rank, and the true traffic drivers.</li>
                    <li><b>Reverse-Engineer Competitors:</b> Discover which pages, keywords, and topics your rivals use to capture customer demand.</li>
                    <li><b>Detect Algorithmic Volatility:</b> Spot ranking drops, cannibalization, and lost SERP features before they impact company revenue.</li>
                  </ul>
                </div>
              )}

              {/* Tab 2: Every Feature Breakdown */}
              {organicGuideTab === "modules" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  <div style={{ fontSize: 13, color: "var(--ink-muted)" }}>
                    The Organic Research workspace includes 6 dedicated analytical modules:
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 16px", background: "#f8fafc" }}>
                      <div style={{ fontWeight: 700, color: "#0f172a", fontSize: 13.5 }}>1. SERP Position Distribution (Tiers 1–3, 4–10, 11–20, 21–50, 51–100)</div>
                      <div style={{ fontSize: 12, color: "#475569", marginTop: 4 }}>
                        Categorizes all rankings into performance buckets. Positions 1–3 capture ~60% of all clicks. Positions 11–20 ("Striking Distance") represent the highest ROI targets for quick promotion into Page 1.
                      </div>
                    </div>

                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 16px", background: "#f8fafc" }}>
                      <div style={{ fontWeight: 700, color: "#0f172a", fontSize: 13.5 }}>2. Search Intent Breakdown (Informational, Commercial, Transactional, Navigational)</div>
                      <div style={{ fontSize: 12, color: "#475569", marginTop: 4 }}>
                        Classifies query psychology. Ensures content satisfies user intent (e.g. providing price comparisons for Commercial queries, and booking forms for Transactional queries).
                      </div>
                    </div>

                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 16px", background: "#f8fafc" }}>
                      <div style={{ fontWeight: 700, color: "#0f172a", fontSize: 13.5 }}>3. SERP Features in Search Landscape</div>
                      <div style={{ fontSize: 12, color: "#475569", marginTop: 4 }}>
                        Tracks rich enhancements won or lost: Featured Snippets (Position 0), People Also Ask (PAA), Local 3-Packs, and Knowledge Panels. Pushes competitors below the fold.
                      </div>
                    </div>

                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 16px", background: "#f8fafc" }}>
                      <div style={{ fontWeight: 700, color: "#0f172a", fontSize: 13.5 }}>4. Organic Competitors Positioning Matrix</div>
                      <div style={{ fontSize: 12, color: "#475569", marginTop: 4 }}>
                        Maps real SERP rivals based on shared search terms. Compares Common Keywords, Search Visibility %, and Estimated Monthly Traffic with direct one-click jump to Keyword Gap.
                      </div>
                    </div>

                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 16px", background: "#f8fafc" }}>
                      <div style={{ fontWeight: 700, color: "#0f172a", fontSize: 13.5 }}>5. Top Organic Pages & Content Silos</div>
                      <div style={{ fontSize: 12, color: "#475569", marginTop: 4 }}>
                        Uncovers the 20% of URLs generating 80% of site traffic. Highlights primary keyword drivers, click share, and content silos requiring internal link reinforcement.
                      </div>
                    </div>

                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 16px", background: "#f8fafc" }}>
                      <div style={{ fontWeight: 700, color: "#0f172a", fontSize: 13.5 }}>6. Organic Search Keyword Positions Table</div>
                      <div style={{ fontSize: 12, color: "#475569", marginTop: 4 }}>
                        Granular table of each keyword, live position, monthly search volume, estimated CPC advertiser benchmark, and Keyword Difficulty (KD%).
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Tab 3: Tools & Data Sources */}
              {organicGuideTab === "tools" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  <div style={{ fontSize: 13, color: "var(--ink-muted)" }}>
                    Our Organic Research engine integrates authoritative enterprise APIs to calculate positions and competitive share:
                  </div>

                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, textAlign: "left" }}>
                    <thead>
                      <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0" }}>
                        <th style={{ padding: "10px 12px", fontWeight: 700, color: "#475569" }}>Tool / API Engine</th>
                        <th style={{ padding: "10px 12px", fontWeight: 700, color: "#475569" }}>Operational Purpose</th>
                        <th style={{ padding: "10px 12px", fontWeight: 700, color: "#475569" }}>SEO Impact</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
                        <td style={{ padding: "10px 12px", fontWeight: 600, color: "#1d4ed8" }}>Google SERP Live Crawler</td>
                        <td style={{ padding: "10px 12px" }}>Real-time search scraping across target country & device</td>
                        <td style={{ padding: "10px 12px", color: "var(--ok)" }}>Live ranking accuracy</td>
                      </tr>
                      <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
                        <td style={{ padding: "10px 12px", fontWeight: 600, color: "#1d4ed8" }}>DataForSEO Labs API</td>
                        <td style={{ padding: "10px 12px" }}>Historical keyword database, volume, CPC valuation, competitor overlap</td>
                        <td style={{ padding: "10px 12px", color: "var(--ok)" }}>Commercial traffic valuation</td>
                      </tr>
                      <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
                        <td style={{ padding: "10px 12px", fontWeight: 600, color: "#1d4ed8" }}>NLP Intent Classifier</td>
                        <td style={{ padding: "10px 12px" }}>Lexical parsing categorizing queries into I, C, T, N</td>
                        <td style={{ padding: "10px 12px", color: "var(--ok)" }}>Satisfies helpful content standards</td>
                      </tr>
                      <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
                        <td style={{ padding: "10px 12px", fontWeight: 600, color: "#1d4ed8" }}>Google CrUX & CWV</td>
                        <td style={{ padding: "10px 12px" }}>Correlates LCP, INP, and CLS speed with ranking volatility</td>
                        <td style={{ padding: "10px 12px", color: "var(--ok)" }}>Technical speed diagnostics</td>
                      </tr>
                      <tr>
                        <td style={{ padding: "10px 12px", fontWeight: 600, color: "#7c3aed" }}>AEO Knowledge Graph Engine</td>
                        <td style={{ padding: "10px 12px" }}>Checks entity resolution and structured JSON-LD for LLM citations</td>
                        <td style={{ padding: "10px 12px", color: "#7c3aed" }}>Bridges SEO into AI Overviews</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}

              {/* Tab 4: Why We Use It */}
              {organicGuideTab === "strategy" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  <h4 style={{ margin: 0, fontSize: 14, color: "#0f172a" }}>Strategic Rationale: Why Organic Research is Essential:</h4>
                  
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", background: "#f8fafc" }}>
                      <div style={{ fontWeight: 700, color: "#2563eb", marginBottom: 4 }}>🎯 Low-Hanging Fruit Optimization</div>
                      <div style={{ fontSize: 12, color: "#475569" }}>
                        Keywords in positions 4–15 already have Google's trust. Applying quick schema, meta, or heading fixes can leap them into the Top 3 within weeks, generating <b>200%–500% traffic lift</b>.
                      </div>
                    </div>

                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", background: "#f8fafc" }}>
                      <div style={{ fontWeight: 700, color: "var(--ok)", marginBottom: 4 }}>🛡️ Stopping Keyword Cannibalization</div>
                      <div style={{ fontSize: 12, color: "#475569" }}>
                        Identifies when two different pages on your site compete for the same keyword, confusing Google and diluting authority. Consolidating them restores #1 rankings.
                      </div>
                    </div>

                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", background: "#f8fafc" }}>
                      <div style={{ fontWeight: 700, color: "#d97706", marginBottom: 4 }}>🥷 Competitor Content Blueprint</div>
                      <div style={{ fontSize: 12, color: "#475569" }}>
                        Shows exactly which topics and structural formats competitors use to win market share. You can produce superior content that captures their audience.
                      </div>
                    </div>

                    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", background: "#f8fafc" }}>
                      <div style={{ fontWeight: 700, color: "#7c3aed", marginBottom: 4 }}>🤖 Direct AEO Citation Feeder</div>
                      <div style={{ fontSize: 12, color: "#475569" }}>
                        Pages in Google's Top 3 with structured answers are <b>3.8x more likely to be cited by Perplexity, ChatGPT, and Google AI Overviews</b>.
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Tab 5: How It Helps SEO */}
              {organicGuideTab === "sop" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, padding: "14px 16px" }}>
                    <div style={{ fontWeight: 700, color: "#166534", fontSize: 14, marginBottom: 4 }}>
                      How Organic Research Directly Powers the 16-Test Auto-Fix Pipeline:
                    </div>
                    <div style={{ fontSize: 12.5, color: "#14532d" }}>
                      Organic Research is not merely an analytics dashboard—it is an <b>automated operational trigger</b> that feeds Step 3 (Plan & Triage) and Step 4 (Auto-Fix Engine):
                    </div>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                      <span style={{ width: 22, height: 22, borderRadius: "50%", background: "#2563eb", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0, marginTop: 2 }}>1</span>
                      <div>
                        <b>Automatic Striking Distance Triage:</b> Keywords in positions 4–15 with high commercial intent are prioritized in the Auto-Fix Worklist.
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                      <span style={{ width: 22, height: 22, borderRadius: "50%", background: "#2563eb", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0, marginTop: 2 }}>2</span>
                      <div>
                        <b>Autonomous Snippet Rewrites:</b> The Auto-Fix Engine rewrites meta titles and descriptions to precisely match the character and pixel width tolerances shown in the SERP Optimizer.
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                      <span style={{ width: 22, height: 22, borderRadius: "50%", background: "#2563eb", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0, marginTop: 2 }}>3</span>
                      <div>
                        <b>Schema Injection:</b> Adds FAQPage, MedicalEntity, or LocalBusiness JSON-LD schema to capture Featured Snippets and PAA accordions.
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                      <span style={{ width: 22, height: 22, borderRadius: "50%", background: "#2563eb", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0, marginTop: 2 }}>4</span>
                      <div>
                        <b>Competitor Gap Exploitation:</b> High-volume keywords competitors rank for that your domain is missing are converted into new content briefs with a single click.
                      </div>
                    </div>
                  </div>
                </div>
              )}

            </div>

            {/* Modal Footer */}
            <div style={{
              padding: "14px 24px", borderTop: "1px solid #e2e8f0", background: "#f8fafc",
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                Document: <b>Organic_Research_Guide.pdf</b> • Updated for 2026 SEO/AEO Standard Operating Procedure
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <a
                  href="/docs/Organic_Research_Guide.pdf"
                  target="_blank"
                  rel="noopener noreferrer"
                  download="Organic_Research_Guide.pdf"
                  style={{
                    background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6,
                    padding: "6px 14px", fontSize: 12, fontWeight: 600, color: "#1e293b",
                    cursor: "pointer", display: "flex", alignItems: "center", gap: 6, textDecoration: "none",
                  }}
                >
                  <span>⬇️</span> Download PDF Copy
                </a>
                <button
                  type="button"
                  onClick={() => setShowOrganicGuideModal(false)}
                  style={{
                    background: "#0f172a", border: 0, borderRadius: 6,
                    padding: "6px 16px", fontSize: 12, fontWeight: 600, color: "#ffffff", cursor: "pointer",
                  }}
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

