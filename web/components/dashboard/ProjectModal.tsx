"use client";

import React from "react";
import { RepoPicker } from "./RepoPicker";

/**
 * Create a project, or correct one that already exists.
 *
 * "I create a project, done — I also want to edit those details too. Example: I
 * put the wrong website URL, so I should be able to edit it."
 *
 * ONE form serves both. Create and edit ask for exactly the same nine fields,
 * and a second copy of this markup is a second place for them to drift apart —
 * which is how a field ends up editable on create and silently unreachable
 * afterwards.
 *
 * Lifted out of `ReaiDashboard.tsx` when adding edit pushed that file back over
 * the 13,000-line ratchet in `tests/measure.test.mjs`. AGENTS.md Rule 1 is 1,000
 * lines; the ratchet is there so the file cannot grow back, and raising it to
 * admit a new feature is exactly the move it exists to refuse.
 */
export function ProjectModal({
  open, editing, onClose, onSubmit, saving, error,
  biz, setBiz, url, setUrl, model, setModel, repo, setRepo,
  goal, setGoal, kw, setKw, kwList, setKwList, githubToken,
}: {
  open: boolean;
  /** The project being corrected, or null when creating one. */
  editing: any | null;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
  saving: boolean;
  /** Why the last save failed. Rendered in place — the modal stays open. */
  error: string | null;
  biz: string; setBiz: (v: string) => void;
  url: string; setUrl: (v: string) => void;
  model: string; setModel: (v: string) => void;
  repo: string; setRepo: (v: string) => void;
  goal: string; setGoal: (v: string) => void;
  kw: string; setKw: (v: string) => void;
  kwList: string[]; setKwList: (v: string[]) => void;
  githubToken: () => Promise<string>;
}) {
  if (!open) return null;
  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.5)", backdropFilter: "blur(4px)",
      display: "grid", placeItems: "center", zIndex: 1000, padding: 24,
    }}>
        <div style={{
          background: "#ffffff", borderRadius: 14, border: "1px solid #e9edf2",
          width: "100%", maxWidth: 560, padding: "32px 36px", boxShadow: "0 20px 25px -5px rgba(15, 23, 42, 0.12)",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 22 }}>
            <h2 style={{ margin: 0, fontSize: 19, fontWeight: 700, color: "#1e293b" }}>
              {editing ? "Edit Project" : "Create SEO Project"}
            </h2>
            <button
              type="button"
              onClick={onClose}
              style={{ background: "none", border: 0, fontSize: 20, color: "var(--ink-muted)", cursor: "pointer", padding: 4 }}
            >
              ✕
            </button>
          </div>

          <form onSubmit={onSubmit}>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                Business Name
              </label>
              <input
                type="text"
                value={biz}
                onChange={(e) => setBiz(e.target.value)}
                placeholder="e.g. Acme Studio"
                style={{ width: "100%", padding: "10px 14px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13.5, background: "#f8fafc", color: "#1e293b" }}
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                Website URL *
              </label>
              <input
                type="text"
                required
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com"
                style={{ width: "100%", padding: "10px 14px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13.5, background: "#f8fafc", color: "#1e293b" }}
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                Remediation Model
              </label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                style={{ width: "100%", padding: "10px 14px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13.5, background: "#f8fafc", color: "#1e293b" }}
              >
                <option value="B">Model B — Claude Code fixes code directly</option>
                <option value="A">Model A — Read-only brief</option>
              </select>
            </div>

            {/* Tools check the live domain only. The repository is used by Fix
                (Model B) and nothing else, so it is tucked away, not asked up front. */}
            {model === "B" && (
              <details style={{ marginBottom: 16 }} open={Boolean(repo)}>
                <summary style={{ fontSize: 12.5, fontWeight: 600, color: "#334155", cursor: "pointer" }}>
                  Advanced: source code repository (optional, used only by Fix)
                </summary>
                <div style={{ marginTop: 10 }}>
                  <RepoPicker
                    value={repo}
                    onChange={setRepo}
                    getToken={githubToken}
                    open={open}
                  />
                </div>
              </details>
            )}

            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                Target Keywords (press Enter to add)
              </label>
              <div style={{ display: "flex", gap: 10 }}>
                <input
                  type="text"
                  value={kw}
                  onChange={(e) => setKw(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      if (kw.trim() && !kwList.includes(kw.trim())) {
                        setKwList([...kwList, kw.trim()]);
                        setKw("");
                      }
                    }
                  }}
                  placeholder="keyword phrase"
                  style={{ flex: 1, padding: "10px 14px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13.5, background: "#f8fafc", color: "#1e293b" }}
                />
                <button
                  type="button"
                  onClick={() => {
                    if (kw.trim() && !kwList.includes(kw.trim())) {
                      setKwList([...kwList, kw.trim()]);
                      setKw("");
                    }
                  }}
                  style={{ padding: "10px 18px", background: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 8, fontSize: 13, fontWeight: 600, color: "#334155", cursor: "pointer" }}
                >
                  Add
                </button>
              </div>
              {kwList.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
                  {kwList.map((k) => (
                    <span key={k} style={{ background: "#eef2ff", color: "#4338ca", border: "1px solid #c7d2fe", fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: 12, display: "inline-flex", alignItems: "center", gap: 5 }}>
                      {k}
                      <span style={{ cursor: "pointer", color: "#b91c1c", marginLeft: 3 }} onClick={() => setKwList(kwList.filter((x) => x !== k))}>×</span>
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div style={{ marginBottom: 22 }}>
              <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                Growth Goal
              </label>
              <input
                type="text"
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="e.g. Increase organic signups"
                style={{ width: "100%", padding: "10px 14px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13.5, background: "#f8fafc", color: "#1e293b" }}
              />
            </div>

            {editing && url.trim() && url.trim() !== (editing.website || "") && (
              <div style={{
                marginBottom: 16, padding: "10px 12px", borderRadius: 8,
                background: "#fffbeb", border: "1px solid #fde68a", color: "#92400e",
                fontSize: 12, lineHeight: 1.5,
              }}>
                <b>This changes the site that gets measured.</b> Scans already on this project
                measured <code>{editing.domain}</code>. They keep the URL they ran against
                and are not rewritten, so past scores stay attached to the old site — the next
                scan is the first one that measures the new one.
              </div>
            )}

            {error && (
              <div role="alert" style={{
                marginBottom: 16, padding: "10px 12px", borderRadius: 8,
                background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b",
                fontSize: 12, lineHeight: 1.5,
              }}>
                <b>Not saved.</b> {error}
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
              <button
                type="button"
                onClick={onClose}
                style={{ background: "#f1f5f9", color: "#475569", border: 0, borderRadius: 8, padding: "10px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving || !url.trim()}
                style={{
                  background: "#4f46e5", color: "#ffffff", border: 0, borderRadius: 8,
                  padding: "10px 22px", fontSize: 13, fontWeight: 600, cursor: "pointer",
                  boxShadow: "0 1px 2px rgba(79, 70, 229, 0.2)",
                }}
              >
                {saving ? (editing ? "Saving..." : "Creating...") : (editing ? "Save Changes" : "Save Project")}
              </button>
            </div>
          </form>
        </div>
      </div>
  );
}
