"use client";

import React from "react";
import type { ProjectJourneyStep } from "./types";

interface ProjectJourneyProps {
  currentStep?: number; // 1 to 6
  onStepClick?: (stepId: number) => void;
  hasClient?: boolean;
  hasGsc?: boolean;
  hasScan?: boolean;
}

export function ProjectJourney({
  currentStep = 4,
  onStepClick,
  hasClient = true,
  hasGsc = false,
  hasScan = true,
}: ProjectJourneyProps) {
  const steps: ProjectJourneyStep[] = [
    { id: 1, label: "Create Project", description: "Set domain & targets", status: hasClient ? "completed" : "current" },
    { id: 2, label: "Connect Google / Add Site", description: "Search Console & domain", status: hasGsc ? "completed" : hasClient ? "current" : "upcoming" },
    { id: 3, label: "Run Audit", description: "SEO & AI scan", status: hasScan ? "completed" : "upcoming" },
    { id: 4, label: "Review Top Priorities", description: "Top actionable items", status: currentStep === 4 ? "current" : currentStep > 4 ? "completed" : "upcoming" },
    { id: 5, label: "Review or Apply Fixes", description: "Staged fixes & schema", status: currentStep === 5 ? "current" : currentStep > 5 ? "completed" : "upcoming" },
    { id: 6, label: "Track Results Over Time", description: "Rankings & visibility", status: currentStep === 6 ? "current" : "upcoming" },
  ];

  return (
    <nav
      aria-label="Project Setup Journey"
      style={{
        background: "#ffffff",
        border: "1px solid #e2e8f0",
        borderRadius: 8,
        padding: "12px 16px",
        marginBottom: 16,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "#475569" }}>
            Project Journey
          </span>
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              padding: "2px 8px",
              borderRadius: 12,
              background: "#eff6ff",
              color: "#1d4ed8",
              border: "1px solid #bfdbfe",
            }}
          >
            Stage {currentStep} of 6: {steps.find((s) => s.id === currentStep)?.label || "Active"}
          </span>
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
          Next: <strong style={{ color: "#0f172a" }}>{steps.find((s) => s.id === currentStep + 1)?.label || "Ongoing Tracking"}</strong>
        </div>
      </div>

      {/* Steps List */}
      <ol
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
          gap: 8,
          alignItems: "center",
        }}
      >
        {steps.map((step) => {
          const isCompleted = step.status === "completed";
          const isCurrent = step.status === "current";

          return (
            <li
              key={step.id}
              onClick={() => onStepClick?.(step.id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 8px",
                borderRadius: 6,
                background: isCurrent ? "#f8fafc" : "transparent",
                border: isCurrent ? "1px solid #cbd5e1" : "1px solid transparent",
                cursor: onStepClick ? "pointer" : "default",
                transition: "all 0.15s ease",
              }}
            >
              <div
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 12,
                  fontWeight: 700,
                  flexShrink: 0,
                  background: isCompleted ? "#059669" : isCurrent ? "#2563eb" : "#f1f5f9",
                  color: isCompleted || isCurrent ? "#ffffff" : "var(--ink-muted)",
                  border: isCompleted || isCurrent ? "none" : "1px solid #cbd5e1",
                }}
              >
                {isCompleted ? "✓" : step.id}
              </div>
              <div style={{ overflow: "hidden" }}>
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: isCurrent ? 700 : isCompleted ? 600 : 500,
                    color: isCurrent ? "#1e293b" : isCompleted ? "#334155" : "var(--ink-muted)",
                    whiteSpace: "nowrap",
                    textOverflow: "ellipsis",
                    overflow: "hidden",
                  }}
                >
                  {step.label}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
