"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { authedFetch } from "@/lib/authedFetch";

function GoogleIntegrationContent() {
  const searchParams = useSearchParams();
  const errorParam = searchParams.get("error");
  const promptParam = searchParams.get("prompt");

  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"token" | "oauth">("token");
  const [status, setStatus] = useState<{
    connected: boolean;
    userEmail?: string | null;
    sites?: string[];
    error?: string;
  }>({ connected: false });

  // Form states
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [directToken, setDirectToken] = useState("");
  const [isVerifyingToken, setIsVerifyingToken] = useState(false);
  const [isConnectingOAuth, setIsConnectingOAuth] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: "success" | "error"; text: string } | null>(
    errorParam ? { type: "error", text: `Google OAuth error: ${errorParam}` } : null
  );

  const fetchStatus = async () => {
    try {
      setLoading(true);
      const res = await authedFetch("/api/auth/google/status");
      const data = await res.json();
      setStatus(data);
    } catch (e: any) {
      setStatus({ connected: false, error: e?.message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleDirectOAuth = () => {
    if (!clientId.trim()) {
      setFeedbackMsg({
        type: "error",
        text: "Please enter your Google Cloud OAuth Client ID (Note: this is NOT an email address. It looks like: 123456789-xyz.apps.googleusercontent.com)",
      });
      return;
    }

    if (clientId.includes("@")) {
      setFeedbackMsg({
        type: "error",
        text: "Invalid Client ID: You entered an email address. A Google OAuth Client ID looks like '1234567890-abcdef.apps.googleusercontent.com'. To connect with your email directly in 1 minute, use Option 1 (Google OAuth Playground Token) below.",
      });
      return;
    }

    setIsConnectingOAuth(true);
    authedFetch("/api/auth/google/save-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "save_credentials",
        clientId: clientId.trim(),
        clientSecret: clientSecret.trim(),
      }),
    })
      .then(() => {
        window.location.href = `/api/auth/google?client_id=${encodeURIComponent(clientId.trim())}`;
      })
      .catch((err) => {
        setIsConnectingOAuth(false);
        setFeedbackMsg({ type: "error", text: err?.message || "Failed to initiate OAuth" });
      });
  };

  const handleVerifyDirectToken = async () => {
    if (!directToken.trim()) {
      setFeedbackMsg({
        type: "error",
        text: "Please paste your Google OAuth / Bearer Access Token (starts with 'ya29.').",
      });
      return;
    }

    setIsVerifyingToken(true);
    setFeedbackMsg(null);

    try {
      const res = await authedFetch("/api/auth/google/save-token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accessToken: directToken.trim() }),
      });
      const data = await res.json();

      if (data.success) {
        setFeedbackMsg({
          type: "success",
          text: `Verified & Connected! Detected ${data.sites?.length || 0} verified Search Console properties for ${data.email || "your account"}.`,
        });
        setDirectToken("");
        await fetchStatus();
      } else {
        setFeedbackMsg({
          type: "error",
          text: data.error || "Token verification failed. Ensure the token has the 'webmasters.readonly' scope.",
        });
      }
    } catch (e: any) {
      setFeedbackMsg({ type: "error", text: e?.message || "Verification request failed" });
    } finally {
      setIsVerifyingToken(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await authedFetch("/api/auth/google/save-token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "disconnect" }),
      });
      await fetchStatus();
      setFeedbackMsg({ type: "success", text: "Disconnected Google Search Console account successfully." });
    } catch (e: any) {
      setFeedbackMsg({ type: "error", text: "Failed to disconnect" });
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      backgroundColor: "#070b14",
      color: "#f8fafc",
      padding: "32px 20px",
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    }}>
      <div style={{ maxWidth: 840, margin: "0 auto", display: "flex", flexDirection: "column", gap: 24 }}>
        
        {/* Top Navigation Bar */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Link
              href="/traffic-analytics"
              style={{
                fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", background: "#131b2e",
                border: "1px solid #1e293b", padding: "6px 14px", borderRadius: 8,
                textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6,
              }}
            >
              ← Back to Traffic Analytics
            </Link>
            <span style={{ color: "#334155" }}>/</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#60a5fa" }}>Google Integration Center</span>
          </div>

          <Link
            href="/"
            style={{
              fontSize: 12, fontWeight: 700, color: "#38bdf8", background: "rgba(56, 189, 248, 0.1)",
              border: "1px solid rgba(56, 189, 248, 0.25)", padding: "6px 14px", borderRadius: 8,
              textDecoration: "none",
            }}
          >
            Open Main Dashboard →
          </Link>
        </div>

        {/* Header Title with Google Logo */}
        <div style={{
          background: "#0f172a", border: "1px solid #1e293b", borderRadius: 16,
          padding: 24, display: "flex", alignItems: "center", gap: 18,
          boxShadow: "0 10px 30px rgba(0, 0, 0, 0.35)",
        }}>
          <div style={{
            width: 52, height: 52, borderRadius: 12, background: "#ffffff",
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
            boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
          }}>
            <svg width="28" height="28" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
            </svg>
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: "#ffffff", letterSpacing: "-0.02em" }}>
              Google Search Console & GA4 Integration
            </h1>
            <p style={{ margin: "6px 0 0 0", fontSize: 13.5, color: "var(--ink-muted)", lineHeight: 1.4 }}>
              Connect your verified Google account to load 100% real first-party search queries, impressions, and CTR into REAI.
            </p>
          </div>
        </div>

        {/* Connected Success Card */}
        {searchParams.get("connected") === "google_unified" && (
          <div style={{
            padding: "20px 24px", borderRadius: 12,
            background: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.3)",
            display: "flex", flexDirection: "column", gap: 14,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 20 }}>🎉</span>
              <div>
                <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#34d399" }}>
                  Google Services Connected Successfully!
                </h3>
                <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--ink-muted)" }}>
                  Your Google Search Console, Google Analytics, and Google Business Profile (Maps) are now actively synced.
                </p>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 4 }}>
              <Link
                href="/local-seo"
                style={{
                  background: "#2563eb", color: "#ffffff", padding: "8px 16px", borderRadius: 6,
                  fontSize: 12.5, fontWeight: 700, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6,
                }}
              >
                <span>🏢</span> Open Local Business & Google Maps
              </Link>
              <Link
                href="/profile"
                style={{
                  background: "#1e293b", color: "#ffffff", padding: "8px 16px", borderRadius: 6,
                  fontSize: 12.5, fontWeight: 700, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6,
                }}
              >
                <span>👤</span> Return to Profile
              </Link>
              <Link
                href="/"
                style={{
                  background: "transparent", color: "var(--ink-muted)", border: "1px solid #334155", padding: "8px 16px", borderRadius: 6,
                  fontSize: 12.5, fontWeight: 600, textDecoration: "none",
                }}
              >
                Go to Main Dashboard →
              </Link>
            </div>
          </div>
        )}

        {/* Feedback Alert */}
        {feedbackMsg && (
          <div style={{
            padding: "14px 18px", borderRadius: 10, fontSize: 13, fontWeight: 600,
            background: feedbackMsg.type === "success" ? "rgba(16, 185, 129, 0.12)" : "rgba(239, 68, 68, 0.12)",
            border: `1px solid ${feedbackMsg.type === "success" ? "rgba(16, 185, 129, 0.35)" : "rgba(239, 68, 68, 0.35)"}`,
            color: feedbackMsg.type === "success" ? "#34d399" : "#f87171",
            display: "flex", alignItems: "center", gap: 10,
          }}>
            <span>{feedbackMsg.type === "success" ? "✓" : "⚠️"}</span>
            <span style={{ flex: 1 }}>{feedbackMsg.text}</span>
          </div>
        )}

        {/* Live Status Card */}
        <div style={{
          background: "#0f172a", border: "1px solid #1e293b", borderRadius: 14,
          padding: 20, boxShadow: "0 4px 20px rgba(0,0,0,0.2)",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{
                width: 12, height: 12, borderRadius: "50%",
                background: status.connected ? "#10b981" : "#64748b",
                boxShadow: status.connected ? "0 0 10px #10b981" : "none",
              }} />
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "#ffffff" }}>
                  Status: {loading ? (
                    <span style={{ color: "var(--ink-muted)" }}>Checking server session...</span>
                  ) : status.connected ? (
                    <span style={{ color: "#34d399" }}>● Connected Live to Google Search Console</span>
                  ) : (
                    <span style={{ color: "#fbbf24" }}>Not Connected Yet</span>
                  )}
                </div>
                <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                  {status.connected
                    ? `Authorized User: ${status.userEmail || "Google Account"} • ${status.sites?.length || 0} verified properties`
                    : "No active Google OAuth credentials currently registered."}
                </div>
              </div>
            </div>

            {status.connected && (
              <div style={{ display: "flex", gap: 8 }}>
                <Link
                  href="/traffic-analytics?connected=google"
                  style={{
                    background: "#059669", color: "#ffffff", fontWeight: 700, fontSize: 12,
                    padding: "8px 16px", borderRadius: 8, textDecoration: "none",
                  }}
                >
                  View GSC Analytics →
                </Link>
                <button
                  type="button"
                  onClick={handleDisconnect}
                  style={{
                    background: "#1e293b", color: "#f87171", border: "1px solid #334155",
                    padding: "8px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: "pointer",
                  }}
                >
                  Disconnect
                </button>
              </div>
            )}
          </div>

          {status.connected && status.sites && status.sites.length > 0 && (
            <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid #1e293b" }}>
              <div style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", color: "var(--ink-muted)", letterSpacing: "0.05em", marginBottom: 8 }}>
                Verified Google Search Console Properties Detected
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {status.sites.map((s) => (
                  <span
                    key={s}
                    style={{
                      background: "rgba(16, 185, 129, 0.12)", border: "1px solid rgba(16, 185, 129, 0.25)",
                      color: "#34d399", padding: "4px 10px", borderRadius: 6, fontSize: 12, fontFamily: "monospace",
                    }}
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Tab Switcher */}
        <div style={{ display: "flex", gap: 4, background: "#0b1120", padding: 4, borderRadius: 10, border: "1px solid #1e293b" }}>
          <button
            type="button"
            onClick={() => setActiveTab("token")}
            style={{
              flex: 1, padding: "10px 16px", borderRadius: 8, border: 0, fontSize: 13, fontWeight: 700,
              cursor: "pointer", transition: "all 0.15s ease",
              background: activeTab === "token" ? "#1e293b" : "transparent",
              color: activeTab === "token" ? "#38bdf8" : "var(--ink-muted)",
              boxShadow: activeTab === "token" ? "0 2px 6px rgba(0,0,0,0.3)" : "none",
            }}
          >
            ⚡ Method 1: Instant Google OAuth Playground Token (Quickest • 1 Min)
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("oauth")}
            style={{
              flex: 1, padding: "10px 16px", borderRadius: 8, border: 0, fontSize: 13, fontWeight: 700,
              cursor: "pointer", transition: "all 0.15s ease",
              background: activeTab === "oauth" ? "#1e293b" : "transparent",
              color: activeTab === "oauth" ? "#38bdf8" : "var(--ink-muted)",
              boxShadow: activeTab === "oauth" ? "0 2px 6px rgba(0,0,0,0.3)" : "none",
            }}
          >
            🏢 Method 2: Google Cloud Console OAuth 2.0 Client App
          </button>
        </div>

        {/* ── METHOD 1: INSTANT OAUTH PLAYGROUND TOKEN ── */}
        {activeTab === "token" && (
          <div style={{
            background: "#0f172a", border: "1px solid #1e293b", borderRadius: 16,
            padding: 24, display: "flex", flexDirection: "column", gap: 18,
          }}>
            <div>
              <div style={{
                display: "inline-block", background: "rgba(16, 185, 129, 0.15)",
                color: "#34d399", border: "1px solid rgba(16, 185, 129, 0.3)",
                padding: "3px 9px", borderRadius: 6, fontSize: 12, fontWeight: 800, textTransform: "uppercase",
              }}>
                Recommended for Fast Testing
              </div>
              <h2 style={{ margin: "8px 0 4px 0", fontSize: 17, fontWeight: 700, color: "#ffffff" }}>
                Connect Instantly with Google OAuth Playground
              </h2>
              <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.5 }}>
                You don&apos;t need to configure a Google Cloud developer project. You can generate an official Google Access Token in 3 clicks:
              </p>
            </div>

            {/* Steps Box */}
            <div style={{
              background: "#070b14", border: "1px solid #1e293b", borderRadius: 10,
              padding: "14px 18px", fontSize: 12.5, color: "#cbd5e1", lineHeight: 1.6,
            }}>
              <ol style={{ margin: 0, paddingLeft: 18 }}>
                <li>
                  Open{" "}
                  <a
                    href="https://developers.google.com/oauthplayground"
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "#38bdf8", fontWeight: 700, textDecoration: "underline" }}
                  >
                    Google OAuth 2.0 Playground ↗
                  </a>
                </li>
                <li>
                  In <b>Step 1 (Select & authorize APIs)</b>, scroll down to <b>Search Console API v3</b> and check:
                  <br />
                  <code style={{ background: "#1e293b", color: "#a5f3fc", padding: "2px 6px", borderRadius: 4, fontSize: 12 }}>
                    https://www.googleapis.com/auth/webmasters.readonly
                  </code>
                </li>
                <li>
                  Click the blue <b>&quot;Authorize APIs&quot;</b> button and sign in with your Google account (<code>you@example.com</code>).
                </li>
                <li>
                  In <b>Step 2</b>, click <b>&quot;Exchange authorization code for tokens&quot;</b>.
                </li>
                <li>
                  Copy the <b>Access token</b> (it begins with <code style={{ color: "#facc15" }}>ya29.</code>) and paste it below!
                </li>
              </ol>
            </div>

            {/* Token Input */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <label style={{ fontSize: 12, fontWeight: 700, color: "#e2e8f0" }}>
                Google Search Console Access Token (starts with ya29...):
              </label>
              <textarea
                rows={2}
                value={directToken}
                onChange={(e) => setDirectToken(e.target.value)}
                placeholder="ya29.a0AfH6SM..."
                style={{
                  width: "100%", background: "#070b14", border: "1px solid #334155",
                  borderRadius: 10, padding: "10px 14px", color: "#ffffff", fontSize: 12,
                  fontFamily: "monospace", boxSizing: "border-box", outline: "none",
                }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
              <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                Pulls live verified queries directly from <code style={{ color: "var(--ink-muted)" }}>searchconsole.googleapis.com</code>.
              </span>
              <button
                type="button"
                onClick={handleVerifyDirectToken}
                disabled={isVerifyingToken || !directToken.trim()}
                style={{
                  background: isVerifyingToken || !directToken.trim() ? "#1e293b" : "#059669",
                  color: isVerifyingToken || !directToken.trim() ? "var(--ink-muted)" : "#ffffff",
                  border: 0, padding: "10px 20px", borderRadius: 8, fontSize: 12.5, fontWeight: 700,
                  cursor: isVerifyingToken || !directToken.trim() ? "not-allowed" : "pointer",
                  boxShadow: "0 2px 8px rgba(0,0,0,0.25)",
                }}
              >
                {isVerifyingToken ? "Verifying with Google..." : "✓ Verify & Connect Token Live"}
              </button>
            </div>
          </div>
        )}

        {/* ── METHOD 2: GOOGLE CLOUD OAUTH CLIENT APP ── */}
        {activeTab === "oauth" && (
          <div style={{
            background: "#0f172a", border: "1px solid #1e293b", borderRadius: 16,
            padding: 24, display: "flex", flexDirection: "column", gap: 18,
          }}>
            <div>
              <div style={{
                display: "inline-block", background: "rgba(59, 130, 246, 0.15)",
                color: "#60a5fa", border: "1px solid rgba(59, 130, 246, 0.3)",
                padding: "3px 9px", borderRadius: 6, fontSize: 12, fontWeight: 800, textTransform: "uppercase",
              }}>
                Production SaaS Mode
              </div>
              <h2 style={{ margin: "8px 0 4px 0", fontSize: 17, fontWeight: 700, color: "#ffffff" }}>
                Google Cloud Console OAuth 2.0 Credentials
              </h2>
              <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.5 }}>
                Enter the <b>Client ID</b> and <b>Client Secret</b> created in your Google Cloud Console project.
              </p>
            </div>

            {/* Note on Client ID format */}
            <div style={{
              background: "rgba(245, 158, 11, 0.1)", border: "1px solid rgba(245, 158, 11, 0.3)",
              borderRadius: 10, padding: "12px 16px", fontSize: 12.5, color: "#fcd34d",
            }}>
              <b>Important Note:</b> The <b>Client ID</b> is <b>NOT your email</b> (e.g. not <code>you@example.com</code>).
              <br />
              It is a generated string that looks like:{" "}
              <code style={{ background: "#1e293b", padding: "1px 6px", borderRadius: 4, color: "#ffffff" }}>
                123456789012-abcdef123456.apps.googleusercontent.com
              </code>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: "#e2e8f0" }}>
                  Google OAuth Client ID:
                </label>
                <input
                  type="text"
                  value={clientId}
                  onChange={(e) => setClientId(e.target.value)}
                  placeholder="1234567890-xxx.apps.googleusercontent.com"
                  style={{
                    background: "#070b14", border: "1px solid #334155", borderRadius: 8,
                    padding: "9px 12px", color: "#ffffff", fontSize: 12, fontFamily: "monospace",
                    boxSizing: "border-box", outline: "none",
                  }}
                />
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: "#e2e8f0" }}>
                  Google Client Secret:
                </label>
                <input
                  type="password"
                  value={clientSecret}
                  onChange={(e) => setClientSecret(e.target.value)}
                  placeholder="GOCSPX-xxxxxxxxxxxx"
                  style={{
                    background: "#070b14", border: "1px solid #334155", borderRadius: 8,
                    padding: "9px 12px", color: "#ffffff", fontSize: 12, fontFamily: "monospace",
                    boxSizing: "border-box", outline: "none",
                  }}
                />
              </div>
            </div>

            <div style={{
              background: "#070b14", border: "1px solid #1e293b", borderRadius: 8,
              padding: "10px 14px", fontSize: 12, color: "var(--ink-muted)",
            }}>
              Redirect URI registered in Google Cloud Console must be:{" "}
              <code style={{ color: "#38bdf8", fontWeight: 700 }}>http://localhost:3000/api/auth/google/callback</code>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                onClick={handleDirectOAuth}
                disabled={isConnectingOAuth}
                style={{
                  background: "#2563eb", color: "#ffffff", border: 0, padding: "10px 22px",
                  borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: "pointer",
                  display: "flex", alignItems: "center", gap: 8,
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24">
                  <path fill="#ffffff" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                  <path fill="#ffffff" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path fill="#ffffff" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                  <path fill="#ffffff" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                </svg>
                {isConnectingOAuth ? "Navigating to Google..." : "Authorize & Navigate to Google →"}
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

export default function GoogleIntegrationPage() {
  return (
    <Suspense fallback={
      <div style={{
        minHeight: "100vh",
        backgroundColor: "#070b14",
        color: "var(--ink-muted)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "'Inter', sans-serif",
      }}>
        Loading Google Integration Center...
      </div>
    }>
      <GoogleIntegrationContent />
    </Suspense>
  );
}
