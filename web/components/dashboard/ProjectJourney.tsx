"use client";

import React from "react";
import { deriveJourney, type JourneyInput } from "../../lib/journey";

/**
 * The six-stage bar. It renders a journey; it does not decide one.
 *
 * Every field below is evidence, passed in by the caller. It used to take
 * `currentStep` and a few booleans, all of which were hardcoded at both call
 * sites - `currentStep={4}`, and `Overview` also passing `hasClient={true}
 * hasScan={true}` - so an empty account read "Stage 4 of 6" with three steps
 * ticked. Taking the evidence instead of the answer is what makes that
 * impossible to reintroduce: there is no step number to hardcode.
 */
interface ProjectJourneyProps extends JourneyInput {
  onStepClick?: (stepId: number) => void;
}

export function ProjectJourney({ onStepClick, ...evidence }: ProjectJourneyProps) {
  const { steps, currentStep, complete } = deriveJourney(evidence);
  const current = steps.find((s) => s.id === currentStep);
  const next = steps.find((s) => s.id > currentStep && s.status !== "completed");

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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, gap: 12, flexWrap: "wrap" }}>
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
              background: complete ? "#ecfdf5" : "#eff6ff",
              color: complete ? "#065f46" : "#1d4ed8",
              border: `1px solid ${complete ? "#a7f3d0" : "#bfdbfe"}`,
            }}
          >
            {complete
              ? "All Stages Complete"
              : `Stage ${currentStep} of ${steps.length}: ${current?.label ?? ""}`}
          </span>
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
          {complete ? (
            <>Now: <strong style={{ color: "#0f172a" }}>Ongoing Tracking</strong></>
          ) : next ? (
            <>Next: <strong style={{ color: "#0f172a" }}>{next.label}</strong></>
          ) : null}
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
              title={step.description}
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
                {isCompleted ? "\u2713" : step.id}
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
