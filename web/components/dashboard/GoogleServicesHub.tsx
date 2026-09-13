"use client";

import React, { useState, useEffect } from "react";

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
    analytics: { connected: boolean };
  };
  secondaryGbp: {
    connected: boolean;
    email: string | null;
  };
}

interface GoogleServicesHubProps {
  compact?: boolean;
  onStatusChange?: (status: GoogleServiceStatus) => void;
}

export function GoogleServicesHub({ compact = false, onStatusChange }: GoogleServicesHubProps) {
  const [status, setStatus] = useState<GoogleServiceStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showSecondaryConfig, setShowSecondaryConfig] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [justConnectedMsg, setJustConnectedMsg] = useState<string | null>(null);
  const [currentPath, setCurrentPath] = useState("/profile");

  useEffect(() => {
    if (typeof window !== "undefined") {
      setCurrentPath(window.location.pathname);
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get("connected") === "google_unified") {
        setJustConnectedMsg("Google Services connected successfully! Search Console, Analytics & Business Profile are active.");
        setTimeout(() => setJustConnectedMsg(null), 6000);
      } else if (urlParams.get("connected") === "gbp_secondary") {
        setJustConnectedMsg("Secondary Google Account for Local Business Profile connected successfully!");
        setTimeout(() => setJustConnectedMsg(null), 6000);
      }
    }
  }, []);

  const fetchStatus = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/auth/google/status");
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
      await fetch(`/api/auth/google/status?service=${service}`, { method: "DELETE" });
      await fetchStatus();
    } finally {
      setIsDisconnecting(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: "16px 18px", background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13, color: "var(--ink-muted)" }}>
        Checking Google services status...
      </div>
    );
  }

  const isConnected = status?.connected;
  const primaryEmail = status?.userEmail;
  const gbpAccount = status?.services?.businessProfile?.accountEmail || primaryEmail;
  const isGbpSecondary = status?.secondaryGbp?.connected;

  return (
    <div
      style={{
        background: "#ffffff",
        borderRadius: 10,
        border: "1px solid #e2e8f0",
        padding: compact ? "16px" : "20px 24px",
        boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14, flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: "#4285f4",
              color: "#ffffff",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 800,
              fontSize: 16,
            }}
          >
            G
          </div>
          <div>
            <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: 0 }}>
              Google Services Hub
            </h3>
            <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "2px 0 0" }}>
              Unified Google Search Console, Google Analytics & Google Business Profile (Maps)
            </p>
          </div>
        </div>

        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            padding: "3px 8px",
            borderRadius: 12,
            background: isConnected ? "#dcfce7" : "#f1f5f9",
            color: isConnected ? "#166534" : "var(--ink-muted)",
            border: `1px solid ${isConnected ? "#bbf7d0" : "#e2e8f0"}`,
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
          }}
        >
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: isConnected ? "#22c55e" : "#94a3b8" }} />
          {isConnected ? "Connected" : "Disconnected"}
        </span>
      </div>

      {/* Connection Success Banner */}
      {justConnectedMsg && (
        <div style={{ background: "#dcfce7", border: "1px solid #bbf7d0", padding: "10px 14px", borderRadius: 6, color: "#166534", fontSize: 12.5, fontWeight: 600, marginBottom: 14, display: "flex", alignItems: "center", gap: 6 }}>
          <span>🎉</span>
          <span>{justConnectedMsg}</span>
        </div>
      )}

      {/* Case 1: NOT CONNECTED (Single Master Button) */}
      {!isConnected ? (
        <div style={{ background: "#f8fafc", padding: "16px 18px", borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <p style={{ fontSize: 13, color: "#475569", margin: "0 0 14px", lineHeight: 1.5 }}>
            Connect your Google account to automatically sync verified organic search traffic, rankings, Google Maps local reviews, and analytics in one step.
          </p>

          <a
            href={`/api/auth/google?return_to=${encodeURIComponent(currentPath)}`}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              background: "#0f172a",
              color: "#ffffff",
              borderRadius: 6,
              padding: "9px 18px",
              fontSize: 13,
              fontWeight: 600,
              textDecoration: "none",
              boxShadow: "0 1px 2px rgba(0,0,0,0.08)",
            }}
          >
            <span>🚀</span>
            <span>Connect Google Services</span>
          </a>
        </div>
      ) : (
        /* Case 2: CONNECTED (Unified Status Breakdown) */
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "#f8fafc", padding: "10px 14px", borderRadius: 6, border: "1px solid #e2e8f0", marginBottom: 14 }}>
            <div style={{ fontSize: 12.5, color: "#334155" }}>
              Primary Account: <strong style={{ color: "#0f172a" }}>{primaryEmail}</strong>
            </div>
            <button
              type="button"
              onClick={() => handleDisconnect("primary")}
              disabled={isDisconnecting}
              style={{
                background: "none",
                border: "none",
                color: "#dc2626",
                fontSize: 12,
                fontWeight: 600,
                cursor: isDisconnecting ? "wait" : "pointer",
                padding: 0,
                textDecoration: "underline",
              }}
            >
              Disconnect
            </button>
          </div>

          {/* Connected Services Grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10, marginBottom: 16 }}>
            {/* Search Console */}
            <div style={{ background: "#ffffff", padding: "12px", borderRadius: 6, border: "1px solid #e2e8f0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontSize: 12.5, fontWeight: 700, color: "#1e293b" }}>Search Console</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#166534" }}>✓ Active</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                {status.sites.length > 0 ? `${status.sites.length} verified site(s)` : "Domain linked"}
              </div>
            </div>

            {/* Google Business Profile */}
            <div style={{ background: "#ffffff", padding: "12px", borderRadius: 6, border: "1px solid #e2e8f0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontSize: 12.5, fontWeight: 700, color: "#1e293b" }}>Business Profile (Local)</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#166534" }}>✓ Active</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                Account: {isGbpSecondary ? `Secondary (${gbpAccount})` : "Primary Account"}
              </div>
            </div>

            {/* Google Analytics */}
            <div style={{ background: "#ffffff", padding: "12px", borderRadius: 6, border: "1px solid #e2e8f0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontSize: 12.5, fontWeight: 700, color: "#1e293b" }}>Analytics 4 (GA4)</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#166534" }}>✓ Active</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                Traffic & conversions synced
              </div>
            </div>
          </div>

          {/* Subtle Secondary Account Override (For Agencies / Multi-account Owners) */}
          <div style={{ borderTop: "1px solid #f1f5f9", paddingTop: 12 }}>
            <button
              type="button"
              onClick={() => setShowSecondaryConfig((v) => !v)}
              style={{
                background: "none",
                border: "none",
                color: "var(--ink-muted)",
                fontSize: 12,
                cursor: "pointer",
                padding: 0,
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
              }}
            >
              <span>{showSecondaryConfig ? "▲" : "▼"}</span>
              <span>Need a separate Google account for Local Business Profile (Google Maps)?</span>
            </button>

            {showSecondaryConfig && (
              <div style={{ marginTop: 10, padding: 12, background: "#f8fafc", borderRadius: 6, border: "1px solid #e2e8f0", fontSize: 12 }}>
                <div style={{ fontWeight: 600, color: "#1e293b", marginBottom: 4 }}>
                  Secondary Account for Google Business Profile
                </div>
                <p style={{ color: "var(--ink-muted)", margin: "0 0 10px", lineHeight: 1.4 }}>
                  If the store owner manages Google Maps reviews and business hours under their personal email, link their account here without affecting your Search Console connection.
                </p>

                {isGbpSecondary ? (
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ color: "#166534", fontWeight: 600 }}>
                      ✓ Connected as {status.secondaryGbp.email}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleDisconnect("gbp_secondary")}
                      style={{
                        background: "none",
                        border: "none",
                        color: "#dc2626",
                        fontSize: 12,
                        cursor: "pointer",
                        textDecoration: "underline",
                      }}
                    >
                      Disconnect Secondary
                    </button>
                  </div>
                ) : (
                  <a
                    href={`/api/auth/google?service=gbp_secondary&return_to=${encodeURIComponent(currentPath)}`}
                    style={{
                      display: "inline-block",
                      background: "#2563eb",
                      color: "#ffffff",
                      padding: "6px 12px",
                      borderRadius: 4,
                      fontSize: 12,
                      fontWeight: 600,
                      textDecoration: "none",
                    }}
                  >
                    Link Store Owner's Google Account →
                  </a>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
