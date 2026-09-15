"use client";

import React, { useState, useEffect } from "react";
import { authedFetch, purgeGoogleConnection } from "@/lib/authedFetch";
import { Panel } from "./Panel";
import styles from "./LocalPresence.module.css";

interface GoogleServiceStatus {
  connected: boolean;
  userEmail: string | null;
  sites: string[];
  services: {
    searchConsole: { connected: boolean; properties: string[]; error?: string };
    // null = nothing has asked Google whether this account has locations. The
    // status route used to answer `true` unconditionally with the comment
    // "Auto-probed" beside it.
    businessProfile: { connected: boolean; accountEmail: string | null; isSecondary: boolean; hasLocations: boolean | null };
    analytics: { connected: boolean; error?: string };
  };
  secondaryGbp: {
    connected: boolean;
    email: string | null;
  };
}

type CardState = "ok" | "failed" | "unchecked";
// A word, never a glyph alone: StatusMark draws the icon beside it.
const BADGE_TEXT: Record<CardState, string> = { ok: "Working", failed: "Not working", unchecked: "Not checked" };

/** Status as an icon plus a word, on the shared `.sev` classes (DESIGN.md §2.5). */
function StatusMark({ state, word }: { state: "ok" | "bad" | "none"; word: string }) {
  const cls = state === "ok" ? "sev sev--ok" : state === "bad" ? "sev sev--error" : "sev";
  return (
    <span className={cls} style={{ whiteSpace: "normal" }}>
      <span className="sev__glyph" aria-hidden="true">
        <svg className={styles.glyphIcon} width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          {state === "ok" ? <polyline points="20 6 9 17 4 12" />
            : state === "bad" ? <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>
            : <line x1="6" y1="12" x2="18" y2="12" />}
        </svg>
      </span>
      {word}
    </span>
  );
}

/** The panel title with Google's "G" mark (a third-party mark keeps its colour). */
function GoogleTitle() {
  return (
    <span className={styles.titleWithMark}>
      <span className={styles.gMark} aria-hidden="true">G</span>
      Google Services
    </span>
  );
}

/** What each Google service actually answered, from `/api/auth/google/status`. */
export function serviceCards(status: GoogleServiceStatus, isGbpSecondary: boolean, gbpAccount: string | null | undefined) {
  const gsc = status.services.searchConsole;
  const ga = status.services.analytics;
  const gbp = status.services.businessProfile;
  return [
    {
      name: "Search Console",
      state: (gsc.connected ? "ok" : "failed") as CardState,
      detail: gsc.connected
        ? `${status.sites.length} site(s) this account can read`
        : gsc.error || "Google did not accept this connection. Disconnect, then connect again.",
    },
    {
      name: "Business Profile (Local)",
      // Nothing asks Google about locations at connect time (hasLocations stays null).
      state: (gbp.hasLocations === true ? "ok" : gbp.hasLocations === false ? "failed" : "unchecked") as CardState,
      detail: gbp.hasLocations === false
        ? "This account has no Business Profile locations."
        : `Checked when you open Local. Account: ${isGbpSecondary ? `Secondary (${gbpAccount})` : "Primary"}`,
    },
    {
      name: "Analytics 4 (GA4)",
      state: (ga.connected ? "ok" : "failed") as CardState,
      detail: ga.connected
        ? "Google Analytics answered. Open Traffic → GA4 Overview."
        : ga.error || "Google did not accept this connection. Disconnect, then connect again.",
    },
  ];
}

interface GoogleServicesHubProps {
  /** Accepted for existing callers. The panel is compact at every size now. */
  compact?: boolean;
  onStatusChange?: (status: GoogleServiceStatus) => void;
}

export function GoogleServicesHub({ onStatusChange }: GoogleServicesHubProps) {
  const [status, setStatus] = useState<GoogleServiceStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showSecondaryConfig, setShowSecondaryConfig] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [justConnectedMsg, setJustConnectedMsg] = useState<string | null>(null);
  const [currentPath, setCurrentPath] = useState("/profile");
  const secondaryId = `gbp-secondary-${React.useId().replace(/:/g, "")}`;

  useEffect(() => {
    if (typeof window !== "undefined") {
      setCurrentPath(window.location.pathname);
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get("connected") === "google_unified") {
        setJustConnectedMsg("Google sign-in finished. Each card below shows what Google answered.");
        setTimeout(() => setJustConnectedMsg(null), 6000);
      } else if (urlParams.get("connected") === "gbp_secondary") {
        setJustConnectedMsg("Secondary Google sign-in finished. Open Local to see what Business Profile answered.");
        setTimeout(() => setJustConnectedMsg(null), 6000);
      }
    }
  }, []);

  const fetchStatus = async () => {
    try {
      setLoading(true);
      const res = await authedFetch("/api/auth/google/status");
      const data = await res.json();
      setStatus(data);
      onStatusChange?.(data);
    } catch {
      setStatus({
        connected: false,
        userEmail: null,
        sites: [],
        services: {
          searchConsole: { connected: false, properties: [] },
          businessProfile: { connected: false, accountEmail: null, isSecondary: false, hasLocations: null },
          analytics: { connected: false },
        },
        secondaryGbp: { connected: false, email: null },
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleDisconnect = async (service: "primary" | "gbp_secondary" | "all") => {
    try {
      setIsDisconnecting(true);
      if (service === "primary" || service === "all") {
        // Goes through the shared purge so the BROWSER's half is cleared too -
        // the selected property, the account email and the traffic source all
        // live in localStorage and used to outlive the disconnect.
        await purgeGoogleConnection();
      } else {
        await authedFetch(`/api/auth/google/status?service=${service}`, { method: "DELETE" });
      }
      await fetchStatus();
    } finally {
      setIsDisconnecting(false);
    }
  };

  if (loading) {
    return (
      <Panel title={<GoogleTitle />}>
        <p className={styles.serviceDetail} role="status">Checking Google services status...</p>
      </Panel>
    );
  }

  const isConnected = status?.connected;
  const primaryEmail = status?.userEmail;
  const gbpAccount = status?.services?.businessProfile?.accountEmail || primaryEmail;
  const isGbpSecondary = status?.secondaryGbp?.connected;

  return (
    <Panel
      title={<GoogleTitle />}
      subtitle="Search Console, Google Analytics and Google Business Profile (Maps) through one sign-in"
    >
      {/* Connection Success Banner */}
      {justConnectedMsg && (
        <p role="status" className={`${styles.notice} ${styles.noticeOk}`}>
          {justConnectedMsg}
        </p>
      )}

      {/* Case 1: NOT CONNECTED (Single Master Button) */}
      {!isConnected ? (
        <div className={styles.actionRow}>
          <StatusMark state="none" word="Not connected" />
          <p className={styles.serviceDetail} style={{ flex: "1 1 260px" }}>
            Connect your Google account to sync verified organic search traffic, rankings, Google Maps reviews and analytics in one step.
          </p>
          <a
            href={`/api/auth/google?return_to=${encodeURIComponent(currentPath)}`}
            className={`btn btn--primary ${styles.wrapBtn} ${styles.blockNarrow}`}
          >
            Connect Google Services
          </a>
        </div>
      ) : (
        /* Case 2: CONNECTED (Unified Status Breakdown) */
        <>
          <div className={styles.actionRow}>
            <StatusMark state="ok" word="Connected" />
            <span className={styles.serviceDetail}>
              Primary account: <strong className={styles.email} style={{ color: "var(--ink)" }}>{primaryEmail}</strong>
            </span>
            <div className={styles.actionEnd}>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={() => handleDisconnect("primary")}
                disabled={isDisconnecting}
                style={{ color: "var(--bad)" }}
              >
                {isDisconnecting ? "Disconnecting..." : "Disconnect"}
              </button>
            </div>
          </div>

          {/* Connected Services Grid. Each badge is the result of asking Google
              just now, never a constant: these three read a fixed Active badge for any
              connection, including one whose token Google no longer accepts. */}
          <ul className={styles.serviceGrid} style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {serviceCards(status!, Boolean(isGbpSecondary), gbpAccount).map((card) => (
              <li key={card.name} className={styles.serviceCard}>
                <div className={styles.serviceHead}>
                  <span>{card.name}</span>
                  <StatusMark state={card.state === "ok" ? "ok" : card.state === "failed" ? "bad" : "none"} word={BADGE_TEXT[card.state]} />
                </div>
                <p className={styles.serviceDetail}>{card.detail}</p>
              </li>
            ))}
          </ul>

          {/* Subtle Secondary Account Override (For Agencies / Multi-account Owners) */}
          <div style={{ borderTop: "1px solid var(--border)", paddingTop: "var(--space-2)" }}>
            <button
              type="button"
              className={styles.disclosure}
              aria-expanded={showSecondaryConfig}
              aria-controls={secondaryId}
              onClick={() => setShowSecondaryConfig((v) => !v)}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="6 9 12 15 18 9" />
              </svg>
              <span>Need a separate Google account for Local Business Profile (Google Maps)?</span>
            </button>

            {showSecondaryConfig && (
              <div id={secondaryId} className={styles.card} style={{ marginTop: "var(--space-2)" }}>
                <h4 className={styles.cardTitle}>Secondary Account for Google Business Profile</h4>
                <p className={styles.serviceDetail}>
                  If the store owner manages Google Maps reviews and business hours under their personal email, link their account here without affecting your Search Console connection.
                </p>

                {isGbpSecondary ? (
                  <div className={styles.actionRow}>
                    <StatusMark state="ok" word={`Connected as ${status!.secondaryGbp.email}`} />
                    <div className={styles.actionEnd}>
                      <button
                        type="button"
                        className="btn btn--secondary btn--sm"
                        onClick={() => handleDisconnect("gbp_secondary")}
                        style={{ color: "var(--bad)" }}
                      >
                        Disconnect Secondary
                      </button>
                    </div>
                  </div>
                ) : (
                  <div>
                    <a
                      href={`/api/auth/google?service=gbp_secondary&return_to=${encodeURIComponent(currentPath)}`}
                      className={`btn btn--secondary btn--sm ${styles.wrapBtn}`}
                    >
                      Link Store Owner&apos;s Google Account
                    </a>
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}
