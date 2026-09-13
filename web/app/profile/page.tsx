"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";
import { GoogleServicesHub } from "@/components/dashboard/GoogleServicesHub";

function ProfilePageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const errorParam = searchParams.get("error");

  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [signingIn, setSigningIn] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [errorMsg, setErrorMsg] = useState(errorParam || "");
  const [successMsg, setSuccessMsg] = useState("");
  const [confirmSignOut, setConfirmSignOut] = useState(false);

  // Preference toggles
  const [emailAlerts, setEmailAlerts] = useState(true);
  const [autoFixPrs, setAutoFixPrs] = useState(true);

  // Fetch session on load
  useEffect(() => {
    let active = true;

    // Safety timeout: Never hang on loading profile
    const timer = setTimeout(() => {
      if (active) {
        setLoading(false);
      }
    }, 600);

    supabase.auth.getSession()
      .then(({ data, error }) => {
        if (active) {
          clearTimeout(timer);
          if (error) {
            setErrorMsg(error.message);
          }
          setSession(data.session);
          setLoading(false);
        }
      })
      .catch((e: any) => {
        if (active) {
          clearTimeout(timer);
          console.warn("Profile session fetch bypassed:", e?.message || e);
          setLoading(false);
        }
      });

    const { data: authListener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      if (active) {
        setSession(newSession);
        setLoading(false);
      }
    });

    return () => {
      active = false;
      clearTimeout(timer);
      authListener.subscription.unsubscribe();
    };
  }, []);

  const handleSignInWithGitHub = async () => {
    try {
      setSigningIn(true);
      setErrorMsg("");
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "github",
        options: {
          redirectTo: typeof window !== "undefined" ? `${window.location.origin}/profile` : undefined,
          // `repo` is what makes this real. Without it GitHub issues an
          // identity-only token: private client repositories are invisible, the
          // pull-request list is empty, check runs cannot be read and merge is
          // impossible — the whole Gate & Merge screen sits on "not connected"
          // forever with no way for the operator to fix it from inside the app.
          //
          // The client grants access by adding this GitHub account as a
          // collaborator on their repo. `read:org` lets us see repos owned by
          // an organisation rather than a person, which most agencies' clients
          // are.
          //
          // Note `repo` is all-or-nothing: it covers every private repo this
          // account can reach, not just client ones. That is the accepted
          // trade-off for the collaborator model, and the reason to move to a
          // GitHub App per-repo installation once the client count justifies it.
          scopes: "repo read:org",
        },
      });
      if (error) setErrorMsg(error.message);
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to initiate GitHub sign in");
    } finally {
      setSigningIn(false);
    }
  };

  const handleSignOut = async () => {
    try {
      setSigningOut(true);
      setErrorMsg("");
      const { error } = await supabase.auth.signOut();
      if (error) {
        setErrorMsg(error.message);
      } else {
        setSession(null);
        setConfirmSignOut(false);
        setSuccessMsg("You have been successfully signed out.");
      }
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to sign out");
    } finally {
      setSigningOut(false);
    }
  };

  if (loading) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "#f8fafc",
          fontFamily: "'Inter', -apple-system, sans-serif",
        }}
      >
        <div
          style={{
            width: "36px",
            height: "36px",
            border: "3px solid #e2e8f0",
            borderTopColor: "#2563eb",
            borderRadius: "50%",
            animation: "authSpin 0.8s linear infinite",
          }}
        />
        <p style={{ marginTop: "16px", color: "var(--ink-muted)", fontSize: "14px", fontWeight: 500 }}>
          Loading profile...
        </p>
        <style>{`@keyframes authSpin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  const user: User | null = session?.user || null;
  const metadata = user?.user_metadata || {};
  const displayName = metadata.full_name || metadata.name || metadata.user_name || user?.email?.split("@")[0] || "User";
  const email = user?.email || "No email available";
  const avatarUrl = metadata.avatar_url;
  const initials = displayName
    .split(" ")
    .map((n: string) => n[0])
    .join("")
    .substring(0, 2)
    .toUpperCase();

  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "#f8fafc",
        padding: "32px 20px 80px",
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        color: "#0f172a",
      }}
    >
      <div style={{ maxWidth: 840, margin: "0 auto" }}>
        {/* Navigation Breadcrumb & Back */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
          <Link
            href="/"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 13,
              fontWeight: 600,
              color: "#2563eb",
              textDecoration: "none",
              padding: "6px 12px",
              borderRadius: 6,
              background: "#ffffff",
              border: "1px solid #e2e8f0",
              boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
            }}
          >
            ← Back to Dashboard
          </Link>

          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              padding: "4px 10px",
              borderRadius: 12,
              background: session ? "#dcfce7" : "#fef3c7",
              color: session ? "#166534" : "#92400e",
              border: `1px solid ${session ? "#bbf7d0" : "#fde68a"}`,
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: session ? "#22c55e" : "#d97706",
              }}
            />
            {session ? "Authenticated Session" : "Signed Out"}
          </span>
        </div>

        {/* Feedback Messages */}
        {errorMsg && (
          <div
            style={{
              marginBottom: 20,
              padding: "12px 16px",
              backgroundColor: "#fef2f2",
              border: "1px solid #fecaca",
              borderRadius: 8,
              fontSize: 13,
              color: "#b91c1c",
            }}
          >
            {errorMsg}
          </div>
        )}

        {successMsg && (
          <div
            style={{
              marginBottom: 20,
              padding: "12px 16px",
              backgroundColor: "#f0fdf4",
              border: "1px solid #bbf7d0",
              borderRadius: 8,
              fontSize: 13,
              color: "#166534",
            }}
          >
            {successMsg}
          </div>
        )}

        {/* ── CASE 1: SIGNED IN ── */}
        {session && user ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {/* Profile Overview Card */}
            <div
              style={{
                background: "#ffffff",
                borderRadius: 12,
                border: "1px solid #e2e8f0",
                padding: "24px 28px",
                boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: 18,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                {avatarUrl ? (
                  <img
                    src={avatarUrl}
                    alt={displayName}
                    style={{
                      width: 64,
                      height: 64,
                      borderRadius: "50%",
                      objectFit: "cover",
                      border: "2px solid #e2e8f0",
                    }}
                  />
                ) : (
                  <div
                    style={{
                      width: 64,
                      height: 64,
                      borderRadius: "50%",
                      background: "linear-gradient(135deg, #2563eb, #7c3aed)",
                      color: "#ffffff",
                      fontSize: 22,
                      fontWeight: 700,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {initials}
                  </div>
                )}

                <div>
                  <h1 style={{ fontSize: 20, fontWeight: 800, color: "#0f172a", margin: 0 }}>
                    {displayName}
                  </h1>
                  <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "3px 0 0" }}>
                    {email}
                  </p>
                  <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        padding: "2px 8px",
                        borderRadius: 4,
                        background: "#eff6ff",
                        color: "#1d4ed8",
                        border: "1px solid #bfdbfe",
                      }}
                    >
                      Workspace Admin
                    </span>
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        padding: "2px 8px",
                        borderRadius: 4,
                        background: "#f1f5f9",
                        color: "#475569",
                        border: "1px solid #e2e8f0",
                      }}
                    >
                      GitHub Verified
                    </span>
                  </div>
                </div>
              </div>

              {/* Sign Out CTA Button */}
              <div>
                {!confirmSignOut ? (
                  <button
                    type="button"
                    onClick={() => setConfirmSignOut(true)}
                    style={{
                      background: "#fee2e2",
                      color: "#991b1b",
                      border: "1px solid #fecaca",
                      borderRadius: 6,
                      padding: "8px 16px",
                      fontSize: 13,
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <span>🚪</span>
                    <span>Sign Out</span>
                  </button>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 12, color: "#991b1b", fontWeight: 600 }}>Confirm sign out?</span>
                    <button
                      type="button"
                      onClick={handleSignOut}
                      disabled={signingOut}
                      style={{
                        background: "#dc2626",
                        color: "#ffffff",
                        border: "none",
                        borderRadius: 6,
                        padding: "7px 12px",
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: signingOut ? "wait" : "pointer",
                      }}
                    >
                      {signingOut ? "Signing out..." : "Yes, Sign Out"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmSignOut(false)}
                      style={{
                        background: "#f1f5f9",
                        color: "#475569",
                        border: "1px solid #cbd5e1",
                        borderRadius: 6,
                        padding: "7px 12px",
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Account & Identity Details */}
            <div
              style={{
                background: "#ffffff",
                borderRadius: 12,
                border: "1px solid #e2e8f0",
                padding: "24px 28px",
                boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
              }}
            >
              <h2 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 16px" }}>
                Account & Identity
              </h2>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
                <div style={{ background: "#f8fafc", padding: "12px 14px", borderRadius: 8, border: "1px solid #e2e8f0" }}>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>User ID (Tenant UUID)</div>
                  <div style={{ fontSize: 12.5, fontWeight: 700, color: "#0f172a", marginTop: 4, fontFamily: "monospace" }}>
                    {user.id}
                  </div>
                </div>

                <div style={{ background: "#f8fafc", padding: "12px 14px", borderRadius: 8, border: "1px solid #e2e8f0" }}>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Primary Authentication</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", marginTop: 4 }}>
                    GitHub OAuth 2.0
                  </div>
                </div>

                <div style={{ background: "#f8fafc", padding: "12px 14px", borderRadius: 8, border: "1px solid #e2e8f0" }}>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>GitHub Handle</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", marginTop: 4 }}>
                    @{metadata.user_name || metadata.preferred_username || displayName.toLowerCase().replace(/\s+/g, "")}
                  </div>
                </div>

                <div style={{ background: "#f8fafc", padding: "12px 14px", borderRadius: 8, border: "1px solid #e2e8f0" }}>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Session Expiration</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", marginTop: 4 }}>
                    {session.expires_at ? new Date(session.expires_at * 1000).toLocaleString() : "Active Session"}
                  </div>
                </div>
              </div>
            </div>

            {/* Connected Services */}
            <div
              style={{
                background: "#ffffff",
                borderRadius: 12,
                border: "1px solid #e2e8f0",
                padding: "24px 28px",
                boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
              }}
            >
              <h2 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 16px" }}>
                Connected Services & Integrations
              </h2>

              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {/* GitHub */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "14px 16px",
                    background: "#f8fafc",
                    borderRadius: 8,
                    border: "1px solid #e2e8f0",
                    flexWrap: "wrap",
                    gap: 10,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ width: 36, height: 36, borderRadius: "50%", background: "#0f172a", color: "#ffffff", display: "grid", placeItems: "center", fontSize: 18 }}>
                      🐙
                    </div>
                    <div>
                      <div style={{ fontSize: 13.5, fontWeight: 700, color: "#0f172a" }}>
                        GitHub Integration
                      </div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                        Connected as @{metadata.user_name || "user"} • Enables automated PR staging for code fixes
                      </div>
                    </div>
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#166534", background: "#dcfce7", padding: "3px 8px", borderRadius: 4 }}>
                    ✓ Connected
                  </span>
                </div>

                {/* Unified Google Services Hub */}
                <GoogleServicesHub compact={true} />
              </div>
            </div>

            {/* Workspace & Notification Preferences */}
            <div
              style={{
                background: "#ffffff",
                borderRadius: 12,
                border: "1px solid #e2e8f0",
                padding: "24px 28px",
                boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
              }}
            >
              <h2 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 16px" }}>
                Workspace Preferences
              </h2>

              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}>
                  <div>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: "#1e293b" }}>Email Audit Summaries</div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Receive weekly health reports and critical technical alerts</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={emailAlerts}
                    onChange={(e) => setEmailAlerts(e.target.checked)}
                    style={{ width: 18, height: 18, cursor: "pointer" }}
                  />
                </label>

                <div style={{ height: 1, background: "#f1f5f9" }} />

                <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}>
                  <div>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: "#1e293b" }}>Auto-Fix PR Staging</div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Prepare pull requests for review on GitHub when fixes are approved</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={autoFixPrs}
                    onChange={(e) => setAutoFixPrs(e.target.checked)}
                    style={{ width: 18, height: 18, cursor: "pointer" }}
                  />
                </label>
              </div>
            </div>
          </div>
        ) : (
          /* ── CASE 2: SIGNED OUT ── */
          <div
            style={{
              background: "#ffffff",
              borderRadius: 12,
              border: "1px solid #e2e8f0",
              padding: "40px 32px",
              boxShadow: "0 4px 12px rgba(0,0,0,0.05)",
              textAlign: "center",
              maxWidth: 480,
              margin: "40px auto 0",
            }}
          >
            <div
              style={{
                width: 54,
                height: 54,
                borderRadius: 12,
                background: "linear-gradient(135deg, #1e293b, #0f172a)",
                color: "#ffffff",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 24,
                marginBottom: 16,
              }}
            >
              🔒
            </div>

            <h1 style={{ fontSize: 20, fontWeight: 800, color: "#0f172a", margin: "0 0 8px" }}>
              Sign In to Your REAI Account
            </h1>
            <p style={{ fontSize: 13.5, color: "var(--ink-muted)", margin: "0 0 24px", lineHeight: 1.5 }}>
              Sign in with your GitHub account to access saved client scans, continuous SEO/AEO monitoring, and automated remediation PRs.
            </p>

            <button
              type="button"
              onClick={handleSignInWithGitHub}
              disabled={signingIn}
              style={{
                width: "100%",
                padding: "12px 20px",
                background: "#0f172a",
                color: "#ffffff",
                border: "none",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                cursor: signingIn ? "wait" : "pointer",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 10,
                boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
              <span>{signingIn ? "Connecting to GitHub..." : "Continue with GitHub"}</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ProfilePage() {
  return (
    <Suspense
      fallback={
        <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#f8fafc" }}>
          <div style={{ color: "var(--ink-muted)", fontSize: 13, fontWeight: 500 }}>Loading profile...</div>
        </div>
      }
    >
      <ProfilePageContent />
    </Suspense>
  );
}
