"use client";

import React, { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/authedFetch";

/**
 * Choose the client's GitHub repository.
 *
 * ADD CLIENT used to ask the operator to TYPE `owner/repo` into a free-text box
 * while the app was already holding a GitHub token with the `repo` scope. A typo
 * there does not fail where it was made: it writes a client row pointing at a
 * repository that does not exist, and the operator meets it later, on the Gate
 * screen, as "not found" - which reads like a permissions problem rather than a
 * misspelling.
 *
 * Three states, and they are three different facts:
 *
 *   repos === null   we could not ask (no token, GitHub refused, network)
 *   repos === []     we asked, and this account collaborates on nothing
 *   repos.length     the list
 *
 * The first two must never render the same way. An empty dropdown that actually
 * means "we never looked" is the same class of lie as a gate that scanned
 * nothing and reported a pass - the rule the whole engine is built on.
 *
 * Typing a path by hand stays available, because a local checkout is a supported
 * target and no listing will ever contain one.
 */

export type RepoSummary = {
  fullName: string;
  owner: string;
  name: string;
  private: boolean;
  updatedAt: string;
  description: string | null;
  canPush: boolean;
  archived: boolean;
};

/** A small inline badge. The colour repeats the word it prints, so the meaning
 *  survives greyscale and colour-vision deficiency (WCAG 1.4.1). */
function tag(color: string): React.CSSProperties {
  return {
    fontSize: 10, fontWeight: 700, letterSpacing: 0.3, textTransform: "uppercase",
    color, border: `1px solid ${color}33`, background: `${color}14`,
    borderRadius: 4, padding: "1px 5px", whiteSpace: "nowrap",
  };
}

const link: React.CSSProperties = {
  background: "none", border: "none", padding: 0, fontSize: 11.5,
  color: "#4f46e5", cursor: "pointer", fontWeight: 600,
};

const field: React.CSSProperties = {
  width: "100%", padding: "10px 14px", borderRadius: 8, border: "1px solid #e2e8f0",
  fontSize: 13.5, background: "#f8fafc", color: "#1e293b",
};

export function RepoPicker({
  value, onChange, getToken, open, maxRendered = 200,
}: {
  value: string;
  onChange: (repo: string) => void;
  /** The operator's own GitHub OAuth token, fetched per call and never stored. */
  getToken: () => Promise<string>;
  /** Load lazily: this is up to five GitHub calls and most sessions never open the panel. */
  open: boolean;
  maxRendered?: number;
}) {
  const [repos, setRepos] = useState<RepoSummary[] | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [manual, setManual] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setReason("");
    try {
      const token = await getToken();
      const res = await authedFetch("/api/github/repos", {
        cache: "no-store",
        headers: token ? { "x-github-token": token } : {},
      });
      const data = await res.json();
      setRepos(Array.isArray(data.repos) ? data.repos : null);
      setReason(data.reason || data.error || "");
    } catch (e: any) {
      setRepos(null);
      setReason(e?.message || "Could not reach GitHub.");
    } finally {
      setBusy(false);
    }
  }, [getToken]);

  useEffect(() => {
    if (open && repos === null && !busy && !reason) void load();
  }, [open, repos, busy, reason, load]);

  const q = query.trim().toLowerCase();
  const shown = (repos ?? []).filter((r) => !q || r.fullName.toLowerCase().includes(q));

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6, gap: 10 }}>
        <label style={{ fontSize: 12.5, fontWeight: 600, color: "#334155" }}>GitHub Repository</label>
        <button type="button" style={link} onClick={() => { setManual((v) => !v); setQuery(""); }}>
          {manual ? "Pick from my repositories" : "Enter a path by hand"}
        </button>
      </div>

      {manual ? (
        <>
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="owner/repo or a local path"
            style={field}
          />
          <p style={{ margin: "6px 2px 0", fontSize: 11.5, color: "#64748b" }}>
            A local path works too, for a checkout the pipeline runs against directly.
          </p>
        </>
      ) : repos === null ? (
        <div style={{ padding: "12px 14px", borderRadius: 8, border: "1px solid #fde68a", background: "#fffbeb" }}>
          <div style={{ fontSize: 12.5, color: "#92400e", lineHeight: 1.5 }}>
            {busy
              ? "Reading your repositories from GitHub..."
              : reason || "Your repositories have not been loaded yet."}
          </div>
          {!busy && (
            <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
              <button type="button" style={link} onClick={load}>Try again</button>
              <button type="button" style={link} onClick={() => setManual(true)}>Type it instead</button>
            </div>
          )}
        </div>
      ) : (
        <>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search ${repos.length} repositories`}
            style={{ ...field, marginBottom: 8 }}
          />
          <div style={{ maxHeight: 190, overflowY: "auto", border: "1px solid #e2e8f0", borderRadius: 8, background: "#fff" }}>
            {shown.length === 0 ? (
              <div style={{ padding: "14px", fontSize: 12.5, color: "#64748b" }}>
                {repos.length === 0
                  ? "This GitHub account is not a collaborator on any repository."
                  : `No repository matches "${query.trim()}".`}
              </div>
            ) : (
              shown.slice(0, maxRendered).map((r) => (
                <button
                  key={r.fullName}
                  type="button"
                  onClick={() => onChange(r.fullName)}
                  style={{
                    display: "block", width: "100%", textAlign: "left", cursor: "pointer",
                    padding: "9px 12px", border: "none", borderBottom: "1px solid #f1f5f9",
                    background: value === r.fullName ? "#eef2ff" : "transparent",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: value === r.fullName ? 700 : 600, color: "#1e293b" }}>
                      {r.fullName}
                    </span>
                    {r.private && <span style={tag("#64748b")}>Private</span>}
                    {r.archived && <span style={tag("#b45309")}>Archived</span>}
                    {/* Read-only is a NORMAL outcome: a client adds us as a
                        collaborator and may grant read access only. Saying so
                        here stops "merge not permitted" being a surprise three
                        screens later, after the client row is already written. */}
                    {!r.canPush && <span style={tag("#b91c1c")}>Read only</span>}
                  </div>
                  {r.description && (
                    <div style={{ fontSize: 11.5, color: "#64748b", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {r.description}
                    </div>
                  )}
                </button>
              ))
            )}
          </div>
          {reason && <p style={{ margin: "6px 2px 0", fontSize: 11.5, color: "#b45309" }}>{reason}</p>}
          <p style={{ margin: "6px 2px 0", fontSize: 12, color: value ? "#166534" : "#64748b" }}>
            {value ? `Selected: ${value}` : "No repository selected yet."}
          </p>
        </>
      )}
    </div>
  );
}
