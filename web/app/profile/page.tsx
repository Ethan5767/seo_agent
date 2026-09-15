"use client";

import React, { useState, useEffect, Suspense } from "react";
import { Icon } from "@/components/dashboard/Icon";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";
import { GoogleServicesHub } from "@/components/dashboard/GoogleServicesHub";
import { authedFetch } from "@/lib/authedFetch";

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

  // GitHub, as GitHub answered. This card read "✓ Connected" for everyone.
  const [github, setGithub] = useState<{ state: "checking" | "ok" | "failed"; detail: string }>({ state: "checking", detail: "" });

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

  useEffect(() => {
    if (!session) return;
    let active = true;
    authedFetch("/api/github/repos", {
      cache: "no-store",
      headers: session.provider_token ? { "x-github-token": session.provider_token } : {},
    })
      .then((r) => r.json())
      .then((d) => {
        if (!active) return;
        if (d?.connected) setGithub({ state: "ok", detail: `${(d.repos || []).length} repositories readable` });
        else setGithub({ state: "failed", detail: d?.reason || d?.error || "GitHub did not answer." });
      })
      .catch((e) => active && setGithub({ state: "failed", detail: e?.message || "Could not reach GitHub." }));
    return () => {
      active = false;
    };
  }, [session]);

  if (loading) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "var(--surface-2)",
          fontFamily: "'Inter', -apple-system, sans-serif",
        }}
      >
        <div
          style={{
            width: "36px",
            height: "36px",
            border: "3px solid var(--border)",
            borderTopColor: "var(--accent)",
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
  const provider = String(user?.app_metadata?.provider || "");
  const providerLabel = provider === "github" ? "GitHub" : provider === "google" ? "Google" : provider === "email" ? "Email" : provider || "Unknown";
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
        backgroundColor: "var(--surface-2)",
        padding: "32px 20px 80px",
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        color: "var(--ink)",
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
              color: "var(--accent)",
              textDecoration: "none",
              padding: "6px 12px",
              borderRadius: 6,
              background: "var(--color-white)",
              border: "1px solid var(--border)",
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
              background: session ? "var(--ok-tint)" : "var(--warn-tint)",
              color: session ? "var(--ok)" : "var(--warn)",
              border: `1px solid ${session ? "var(--ok-border)" : "var(--warn-border)"}`,
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
                background: session ? "var(--ok)" : "var(--warn)",
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
              backgroundColor: "var(--bad-tint)",
              border: "1px solid var(--bad-border)",
              borderRadius: 8,
              fontSize: 13,
              color: "var(--bad)",
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
              backgroundColor: "var(--ok-tint)",
              border: "1px solid var(--ok-border)",
              borderRadius: 8,
              fontSize: 13,
              color: "var(--ok)",
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
                background: "var(--color-white)",
                borderRadius: 12,
                border: "1px solid var(--border)",
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
                      border: "2px solid var(--border)",
                    }}
                  />
                ) : (
                  <div
                    style={{
                      width: 64,
                      height: 64,
                      borderRadius: "50%",
                      background: "linear-gradient(135deg, var(--accent), var(--accent))",
                      color: "var(--color-white)",
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
                  <h1 style={{ fontSize: 20, fontWeight: 800, color: "var(--ink)", margin: 0 }}>
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
                        background: "var(--surface-3)",
                        color: "var(--ink-muted)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      Signed in with {providerLabel}
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
                      background: "var(--bad-tint)",
                      color: "var(--bad)",
                      border: "1px solid var(--bad-border)",
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
                    <Icon name="logout" />
                    <span>Sign Out</span>
                  </button>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 12, color: "var(--bad)", fontWeight: 600 }}>Confirm sign out?</span>
                    <button
                      type="button"
                      onClick={handleSignOut}
                      disabled={signingOut}
                      style={{
                        background: "var(--bad)",
                        color: "var(--color-white)",
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
                        background: "var(--surface-3)",
                        color: "var(--ink-muted)",
                        border: "1px solid var(--border-strong)",
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
                background: "var(--color-white)",
                borderRadius: 12,
                border: "1px solid var(--border)",
                padding: "24px 28px",
                boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
              }}
            >
              <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--ink)", margin: "0 0 16px" }}>
                Account & Identity
              </h2>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
                <div style={{ background: "var(--surface-2)", padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border)" }}>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>User ID (Tenant UUID)</div>
                  <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--ink)", marginTop: 4, fontFamily: "monospace" }}>
                    {user.id}
                  </div>
                </div>

                <div style={{ background: "var(--surface-2)", padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border)" }}>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Primary Authentication</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)", marginTop: 4 }}>
                    {providerLabel}
                  </div>
                </div>

                <div style={{ background: "var(--surface-2)", padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border)" }}>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>GitHub Handle</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)", marginTop: 4 }}>
                    {metadata.user_name || metadata.preferred_username ? `@${metadata.user_name || metadata.preferred_username}` : "Not signed in with GitHub"}
                  </div>
                </div>

                <div style={{ background: "var(--surface-2)", padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border)" }}>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Session Expiration</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)", marginTop: 4 }}>
                    {session.expires_at ? new Date(session.expires_at * 1000).toLocaleString() : "Active Session"}
                  </div>
                </div>
              </div>
            </div>

            {/* Connected Services */}
            <div
              style={{
                background: "var(--color-white)",
                borderRadius: 12,
                border: "1px solid var(--border)",
                padding: "24px 28px",
                boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
              }}
            >
              <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--ink)", margin: "0 0 16px" }}>
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
                    background: "var(--surface-2)",
                    borderRadius: 8,
                    border: "1px solid var(--border)",
                    flexWrap: "wrap",
                    gap: 10,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ width: 36, height: 36, borderRadius: "50%", background: "var(--ink)", color: "var(--color-white)", display: "grid", placeItems: "center", fontSize: 18 }}>
                      <Icon name="github" size={18} />
                    </div>
                    <div>
                      <div style={{ fontSize: 13.5, fontWeight: 700, color: "var(--ink)" }}>
                        GitHub Integration
                      </div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                        {github.state === "checking" ? "Checking GitHub…" : github.detail}
                      </div>
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: 12, fontWeight: 700, padding: "3px 8px", borderRadius: 4,
                      color: github.state === "ok" ? "var(--ok)" : github.state === "failed" ? "var(--bad)" : "var(--ink-muted)",
                      background: github.state === "ok" ? "var(--ok-tint)" : github.state === "failed" ? "var(--bad-tint)" : "var(--surface-3)",
                    }}
                  >
                    {github.state === "ok" ? "✓ Working" : github.state === "failed" ? "✕ Not working" : "Checking"}
                  </span>
                </div>

                {/* Unified Google Services Hub */}
                <GoogleServicesHub compact={true} />
              </div>
            </div>

            {/* "Email Audit Summaries" and "Auto-Fix PR Staging" toggles were here:
                defaulted on, never saved, and wired to no feature. */}
          </div>
        ) : (
          /* ── CASE 2: SIGNED OUT ── */
          <div
            style={{
              background: "var(--color-white)",
              borderRadius: 12,
              border: "1px solid var(--border)",
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
                background: "linear-gradient(135deg, var(--ink-body), var(--ink))",
                color: "var(--color-white)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 24,
                marginBottom: 16,
              }}
            >
              <Icon name="lock" size={18} />
            </div>

            <h1 style={{ fontSize: 20, fontWeight: 800, color: "var(--ink)", margin: "0 0 8px" }}>
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
                background: "var(--ink)",
                color: "var(--color-white)",
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
        <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "var(--surface-2)" }}>
          <div style={{ color: "var(--ink-muted)", fontSize: 13, fontWeight: 500 }}>Loading profile...</div>
        </div>
      }
    >
      <ProfilePageContent />
    </Suspense>
  );
}
