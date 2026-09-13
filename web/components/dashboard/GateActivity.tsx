"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { GATE_ROSTER } from "@/lib/pipelineStages";
import { authedFetch } from "@/lib/authedFetch";

/**
 * Watch the gates run, step by step, without leaving this app.
 *
 * The Gate screen could show a verdict and nothing else, which is the least
 * useful moment to have no visibility: "one gate is red" tells an operator
 * nothing about what it looked at, how far the run got, or whether it is even
 * still going. GitHub's jobs API carries every step with its own status and
 * timestamps - the same feed you would watch on github.com.
 *
 * Two rules this follows, both borrowed from the engine:
 *
 *   `jobs === null` is "nothing has reported", NOT "finished with no steps". A
 *   workflow that never started and a workflow that ran clean must not render
 *   the same way.
 *
 *   Each step is annotated with what that gate actually checks and where it
 *   looks - PRE reads the diff and the source, OUT reads the built HTML tree,
 *   CHAIN reads the JSON artifacts the PR carries. A step name alone
 *   ("forbidden-sweep") tells a non-engineer nothing.
 */

type Step = {
  name: string; status: string; conclusion: string | null;
  number: number; startedAt: string | null; completedAt: string | null; seconds: number | null;
};
type Job = {
  id: number; name: string; status: string; conclusion: string | null;
  startedAt: string | null; completedAt: string | null; htmlUrl: string;
  runnerName: string | null; steps: Step[];
};

const PHASE_WHERE: Record<string, string> = {
  PRE: "reads the pull request diff and the source tree",
  OUT: "reads the built HTML, page by page",
  CHAIN: "reads the JSON artifacts the pull request carries",
};

/** Match a workflow step name back to the gate roster. */
function gateFor(stepName: string) {
  const n = stepName.toLowerCase();
  return GATE_ROSTER.find((g) => n.includes(g.name.toLowerCase()))
    ?? GATE_ROSTER.find((g) => n.includes(g.name.split(" ")[0].toLowerCase()));
}

function dot(step: Step): { color: string; label: string; pulse: boolean } {
  if (step.status !== "completed") {
    return step.status === "in_progress"
      ? { color: "#2563eb", label: "Running", pulse: true }
      : { color: "#94a3b8", label: "Queued", pulse: false };
  }
  switch (step.conclusion) {
    case "success": return { color: "#047857", label: "Passed", pulse: false };
    case "skipped": return { color: "#94a3b8", label: "Skipped", pulse: false };
    case "neutral": return { color: "#64748b", label: "Neutral", pulse: false };
    case "cancelled": return { color: "#64748b", label: "Cancelled", pulse: false };
    default: return { color: "#dc2626", label: "Failed", pulse: false };
  }
}

export function GateActivity({
  clientId, sha, getToken,
}: {
  clientId: string | null | undefined;
  sha: string | null | undefined;
  getToken: () => Promise<string>;
}) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [running, setRunning] = useState(false);
  const [runUrl, setRunUrl] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    if (!clientId || !sha) return;
    setBusy(true);
    try {
      const token = await getToken();
      const res = await authedFetch(`/api/clients/${clientId}/github/activity?sha=${encodeURIComponent(sha)}`, {
        cache: "no-store",
        headers: token ? { "x-github-token": token } : {},
      });
      const data = await res.json();
      setJobs(Array.isArray(data.jobs) ? data.jobs : null);
      setRunning(Boolean(data.running));
      setRunUrl(data.runUrl ?? null);
      setReason(data.reason || data.error || "");
    } catch (e: any) {
      setJobs(null);
      setReason(e?.message || "Could not reach GitHub.");
    } finally {
      setBusy(false);
    }
  }, [clientId, sha, getToken]);

  useEffect(() => { void load(); }, [load]);

  // Poll only while something is actually running. A finished run is a finished
  // run; polling it forever burns the operator's GitHub rate limit for nothing.
  useEffect(() => {
    if (!running) return;
    timer.current = setTimeout(() => { void load(); }, 5000);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [running, jobs, load]);

  if (!clientId || !sha) {
    return (
      <div style={box}>
        <div style={muted}>Select a pull request to watch its gates run.</div>
      </div>
    );
  }

  if (jobs === null) {
    return (
      <div style={box}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "#475569" }}>
          {busy ? "Asking GitHub what is running..." : "No workflow run for this commit"}
        </div>
        <div style={{ ...muted, marginTop: 4 }}>
          {reason ||
            "Either the quality gate has not started yet, or this client's repository does not call it. The workflow is `quality-gate.yml`, copied from `.github/examples/`."}
        </div>
        {!busy && (
          <button type="button" onClick={load} style={linkBtn}>Check again</button>
        )}
      </div>
    );
  }

  const allSteps = jobs.flatMap((j) => j.steps);
  const done = allSteps.filter((s) => s.status === "completed").length;

  return (
    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, background: "#fff", overflow: "hidden" }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "11px 14px", borderBottom: "1px solid #f1f5f9", background: "#f8fafc", gap: 10, flexWrap: "wrap",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {running && <span style={pulseDot} />}
          <span style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>
            {running ? "Gates running" : "Gate run finished"}
          </span>
          <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
            {done}/{allSteps.length} steps
          </span>
        </div>
        {runUrl && (
          <a href={runUrl} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11.5, color: "#4f46e5", fontWeight: 600 }}>
            Raw log on GitHub →
          </a>
        )}
      </div>

      {jobs.map((job) => (
        <div key={job.id}>
          <div style={{ padding: "9px 14px", background: "#fbfcfe", borderBottom: "1px solid #f1f5f9" }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>{job.name}</span>
            {job.runnerName && (
              <span style={{ fontSize: 11.5, color: "var(--ink-muted)", marginLeft: 8 }}>
                on {job.runnerName}
              </span>
            )}
          </div>
          {job.steps.map((step) => {
            const d = dot(step);
            const gate = gateFor(step.name);
            return (
              <div key={`${job.id}-${step.number}`} style={{ display: "flex", gap: 10, padding: "9px 14px", borderBottom: "1px solid #f8fafc" }}>
                <span style={{
                  width: 8, height: 8, borderRadius: "50%", background: d.color, marginTop: 5, flexShrink: 0,
                  animation: d.pulse ? "gatePulse 1.1s ease-in-out infinite" : undefined,
                }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 600, color: "#1e293b" }}>{step.name}</span>
                    <span style={{ fontSize: 11.5, fontWeight: 700, color: d.color, whiteSpace: "nowrap" }}>
                      {d.label}{step.seconds !== null ? ` · ${step.seconds}s` : ""}
                    </span>
                  </div>
                  {/* What this gate checks, and where it looks. A step name on its
                      own means nothing to whoever has to act on a red run. */}
                  {gate && (
                    <div style={{ fontSize: 11.5, color: "var(--ink-muted)", marginTop: 2, lineHeight: 1.45 }}>
                      {PHASE_WHERE[gate.phase]} · blocks when {gate.blocks}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ))}
      <style>{"@keyframes gatePulse{0%,100%{opacity:1}50%{opacity:.25}}"}</style>
    </div>
  );
}

const box: React.CSSProperties = {
  border: "1px dashed #cbd5e1", borderRadius: 8, padding: "20px 18px", background: "#f8fafc",
};
const muted: React.CSSProperties = { fontSize: 12, color: "var(--ink-muted)", lineHeight: 1.55 };
const linkBtn: React.CSSProperties = {
  background: "none", border: "none", padding: 0, marginTop: 8,
  fontSize: 11.5, color: "#4f46e5", cursor: "pointer", fontWeight: 600,
};
const pulseDot: React.CSSProperties = {
  width: 8, height: 8, borderRadius: "50%", background: "#2563eb",
  animation: "gatePulse 1.1s ease-in-out infinite", display: "inline-block",
};
