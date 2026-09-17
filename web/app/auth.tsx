"use client";
import React, { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "../lib/supabase";
import { purgeGoogleConnection } from "../lib/authedFetch";
import styles from "./auth.module.css";

type SignInMethod = "email" | "google" | "github";

const PROVIDER_NAME: Record<SignInMethod, string> = {
  email: "Email sign-in links",
  google: "Google sign-in",
  github: "GitHub sign-in",
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Where every sign-in method returns. Supabase only honours it when it is on
 *  the project's Redirect URL allow-list; otherwise it falls back to Site URL. */
function authRedirect(): string | undefined {
  return typeof window !== "undefined" ? window.location.origin : undefined;
}

/** Turn a Supabase auth error into a sentence a client can act on. The raw
 *  message stays in the console for whoever is debugging. */
function plainAuthError(
  error: { message?: string; code?: string; status?: number } | null | undefined,
  method?: SignInMethod,
): string {
  const raw = `${error?.code || ""} ${error?.message || ""}`.toLowerCase();
  if (error) console.warn("Sign-in error:", error.code || "", error.message || error);
  if (/provider is not enabled|unsupported provider|email_provider_disabled|logins are disabled|provider_disabled/.test(raw)) {
    return method === "email"
      ? "Email sign-in links are not available yet. Try again later, or ask your REAI contact for access."
      : `${PROVIDER_NAME[method || "google"]} is not available yet. Use the email link instead.`;
  }
  if (/rate limit|over_email_send_rate_limit|only request this after|too many/.test(raw) || error?.status === 429) {
    return "Too many sign-in links were requested. Wait a minute, then try again.";
  }
  if (/signups not allowed|signup_disabled|user not found/.test(raw)) {
    return "There is no account for this email address yet. Ask your REAI contact for access.";
  }
  if (/invalid.*email|email_address_invalid|unable to validate email/.test(raw)) {
    return "That email address was not accepted. Check it and try again.";
  }
  if (/access_denied|cancel/.test(raw)) {
    return "Sign-in did not complete. The request was cancelled or not approved. Try again.";
  }
  if (/expired|otp_expired|invalid.*(link|token)/.test(raw)) {
    return "Sign-in did not complete. That sign-in link has expired or was already used. Request a new one.";
  }
  if (/failed to fetch|network|load failed|timeout/.test(raw)) {
    return "Sign-in did not complete. Check your connection and try again.";
  }
  return "Sign-in did not complete. Try again.";
}

/** Supabase redirects a failed OAuth or email-link sign-in back here with the
 *  reason in the URL (hash for the implicit flow, query for PKCE). */
function readRedirectError(): { message: string; code: string } | null {
  if (typeof window === "undefined") return null;
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const query = new URLSearchParams(window.location.search);
  const from = hash.get("error") ? hash : query.get("error") ? query : null;
  if (!from) return null;
  return {
    code: `${from.get("error") || ""} ${from.get("error_code") || ""}`.trim(),
    message: from.get("error_description") || "",
  };
}

/** Whether the Supabase project has this method switched on, from its public
 *  auth settings. An OAuth call never returns "provider not enabled" to the
 *  page: it redirects, and Supabase answers the redirect with a raw JSON error.
 *  Asking first is the only way to say it in plain words instead. `null` means
 *  "could not tell", and the caller proceeds rather than blocking sign-in. */
async function providerEnabled(method: SignInMethod): Promise<boolean | null> {
  const base = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!base || !key) return null;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 3000);
  try {
    const res = await fetch(`${base.replace(/\/$/, "")}/auth/v1/settings`, {
      headers: { apikey: key },
      signal: ctrl.signal,
    });
    if (!res.ok) return null;
    const body = await res.json();
    const value = body?.external?.[method];
    return typeof value === "boolean" ? value : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/** Which Supabase user this browser last held, so an account swap can be seen. */
const LAST_USER_KEY = "reai_last_user";

interface AuthContextType {
  session: Session | null;
  user: User | null;
  signOut: () => Promise<void>;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType>({
  session: null,
  user: null,
  signOut: async () => {},
  loading: true,
});

export function useAuth() {
  return useContext(AuthContext);
}

export function SignOutButton({ className, style }: { className?: string; style?: React.CSSProperties }) {
  const { signOut } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  return (
    <button
      onClick={async () => {
        setSigningOut(true);
        await signOut();
        setSigningOut(false);
      }}
      disabled={signingOut}
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "6px 12px",
        fontSize: "12px",
        fontWeight: 500,
        color: "var(--bad)",
        background: "var(--bad-tint)",
        border: "1px solid var(--bad-border)",
        borderRadius: "6px",
        cursor: "pointer",
        transition: "all 0.15s ease",
        ...style,
      }}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
        <polyline points="16 17 21 12 16 7" />
        <line x1="21" y1="12" x2="9" y2="12" />
      </svg>
      {signingOut ? "Signing out..." : "Sign out"}
    </button>
  );
}

const DEV_SESSION: Session = {
  access_token: "dev-local-access-token",
  token_type: "bearer",
  expires_in: 3600 * 24 * 30,
  refresh_token: "dev-local-refresh-token",
  user: {
    id: "00000000-0000-0000-0000-000000000001",
    app_metadata: { provider: "developer" },
    user_metadata: { user_name: "Developer", full_name: "Local Developer" },
    aud: "authenticated",
    created_at: new Date().toISOString(),
    email: "local-dev@example.com",
    role: "authenticated",
  },
};

/** Gate the app behind Supabase Auth (email link, Google or GitHub). In local dev or on network timeout,
 *  seamlessly falls back so testers are never locked out. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [err, setErr] = useState("");
  const [signingIn, setSigningIn] = useState<SignInMethod | null>(null);
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState("");
  const [notice, setNotice] = useState("");

  // A failed OAuth or email-link round trip lands back here with the reason in
  // the URL. Show it, then tidy the URL once Supabase has finished reading it
  // (`initialize()` returns the client's own in-flight promise, it does not
  // start a second one), so a refresh does not show the same error again.
  useEffect(() => {
    const redirectError = readRedirectError();
    if (!redirectError) return;
    setErr(plainAuthError(redirectError));
    void supabase.auth.initialize().finally(() => {
      try {
        const url = new URL(window.location.href);
        for (const k of ["error", "error_code", "error_description"]) url.searchParams.delete(k);
        const hash = new URLSearchParams(url.hash.replace(/^#/, ""));
        if (hash.get("error")) url.hash = "";
        window.history.replaceState(window.history.state, "", url.toString());
      } catch {
        // Cosmetic only.
      }
    });
  }, []);

  useEffect(() => {
    let active = true;
    // Dev sign-in bypass. EXPLICIT opt-in only — never inferred from the
    // hostname or from NODE_ENV.
    //
    // This used to be true on any localhost, so every developer ran the app
    // permanently signed in as a synthetic user. That is not a harmless
    // convenience: the app then looks logged-in with no projects, which reads
    // as a broken account rather than a signed-out one, and it means nobody
    // ever exercises the real signed-out path. The server-side half of this
    // bypass was already gated behind ALLOW_DEV_AUTH; this is the other half.
    const isLocal = typeof window !== "undefined"
      && process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH === "1";

    // Fast safety timeout: Never leave the user hanging on "Checking authentication..."
    const timer = setTimeout(() => {
      if (active) {
        if (isLocal) {
          setSession((prev) => prev || DEV_SESSION);
        }
        setReady(true);
      }
    }, 600);

    supabase.auth.getSession()
      .then(({ data, error }) => {
        if (active) {
          clearTimeout(timer);
          if (error) {
            setErr(plainAuthError(error));
          }
          if (data?.session) {
            setSession(data.session);
          } else if (isLocal) {
            setSession(DEV_SESSION);
          }
          setReady(true);
        }
      })
      .catch((e: any) => {
        if (active) {
          clearTimeout(timer);
          console.warn("Supabase auth check bypassed:", e?.message || e);
          if (isLocal) {
            setSession(DEV_SESSION);
          }
          setReady(true);
        }
      });

    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => {
      if (active) {
        // A different user in this browser must not inherit the last one's
        // Google connection. Sign-out already purges, but it is not the only way
        // to swap accounts: a session can be replaced outright by another tab,
        // by a refresh onto a different account, or by signing in over a live
        // session, and every one of those kept the old cookies.
        const uid = s?.user?.id || null;
        try {
          const previous = localStorage.getItem(LAST_USER_KEY);
          if (uid && previous && previous !== uid) void purgeGoogleConnection();
          if (uid) localStorage.setItem(LAST_USER_KEY, uid);
          else localStorage.removeItem(LAST_USER_KEY);
        } catch {
          // Blocked site data. The server-side ownership check in
          // `googleSession` is the guarantee; this is only the tidy-up.
        }
        if (s) {
          setSession(s);
        } else if (isLocal) {
          setSession(DEV_SESSION);
        } else {
          setSession(null);
        }
        setReady(true);
      }
    });

    return () => {
      active = false;
      clearTimeout(timer);
      sub.subscription.unsubscribe();
    };
  }, []);

  /** Clear the last attempt's messages and check the method is switched on.
   *  Returns false, with the reason already shown, when it is not. */
  const beginSignIn = async (method: SignInMethod): Promise<boolean> => {
    setSigningIn(method);
    setErr("");
    setNotice("");
    if ((await providerEnabled(method)) === false) {
      setErr(plainAuthError({ code: "provider_disabled", message: "provider is not enabled" }, method));
      setSigningIn(null);
      return false;
    }
    return true;
  };

  const handleEmailLink = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const address = email.trim();
    if (!address) {
      setEmailError("Enter your email address.");
      return;
    }
    if (!EMAIL_PATTERN.test(address)) {
      setEmailError("Enter a valid email address, like name@example.com.");
      return;
    }
    setEmailError("");
    try {
      if (!(await beginSignIn("email"))) return;
      const { error } = await supabase.auth.signInWithOtp({
        email: address,
        options: { emailRedirectTo: authRedirect() },
      });
      if (error) setErr(plainAuthError(error, "email"));
      else setNotice(`Check your inbox for a sign-in link. We sent it to ${address}.`);
    } catch (e: any) {
      setErr(plainAuthError(e, "email"));
    } finally {
      setSigningIn(null);
    }
  };

  const handleSignInWithGoogle = async () => {
    try {
      if (!(await beginSignIn("google"))) return;
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: authRedirect() },
      });
      if (error) setErr(plainAuthError(error, "google"));
    } catch (e: any) {
      setErr(plainAuthError(e, "google"));
    } finally {
      setSigningIn(null);
    }
  };

  const handleSignInWithGitHub = async () => {
    try {
      if (!(await beginSignIn("github"))) return;
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "github",
        options: {
          redirectTo: authRedirect(),
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
      if (error) setErr(plainAuthError(error, "github"));
    } catch (e: any) {
      setErr(plainAuthError(e, "github"));
    } finally {
      setSigningIn(null);
    }
  };

  const handleSignOut = async () => {
    // BEFORE signing out, not after: once `setSession(null)` renders the login
    // screen there is nothing mounted left to finish an await.
    //
    // This used to clear the Supabase session and nothing else. The Google
    // tokens are ordinary cookies with a 30-day life (the refresh token, a year)
    // and no tie to any account, so they survived sign-out and the next person
    // to sign in to this browser was shown the previous operator's Search
    // Console and Business Profile. See `lib/googleSession.ts`.
    await purgeGoogleConnection();
    await supabase.auth.signOut();
    setSession(null);
  };

  // 1. Loading state while session is resolving (max 600ms timeout with skip button)
  if (!ready) {
    return (
      <div style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "var(--surface-2)",
        fontFamily: "'Inter', -apple-system, sans-serif",
      }}>
        <div style={{
          width: "36px",
          height: "36px",
          border: "3px solid var(--border)",
          borderTopColor: "var(--accent)",
          borderRadius: "50%",
          animation: "authSpin 0.8s linear infinite",
        }} />
        <p style={{ marginTop: "16px", color: "var(--ink-muted)", fontSize: "14px", fontWeight: 500 }}>
          Checking authentication...
        </p>
        {process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH === "1" ? (
        <button
          type="button"
          onClick={() => {
            setSession(DEV_SESSION);
            setReady(true);
          }}
          style={{
            marginTop: "12px",
            background: "var(--color-white)",
            border: "1px solid var(--border-strong)",
            borderRadius: "6px",
            padding: "6px 14px",
            fontSize: "12px",
            fontWeight: 600,
            color: "var(--ink-muted)",
            cursor: "pointer",
            boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
          }}
        >
          Skip to Dashboard →
        </button>
        ) : null}
        <style>{`@keyframes authSpin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // 2. Unauthenticated state: email link (primary), Google and GitHub, plus the
  //    explicit local dev bypass.
  if (!session) {
    const busy = signingIn !== null;
    const messageOpen = Boolean(err || notice);
    return (
      <main className={styles.page}>
        <section className={styles.card} aria-labelledby="auth-title">
          <div className={styles.mark} aria-hidden="true">REAI</div>

          <h1 id="auth-title" className={styles.title}>Sign In to REAI</h1>
          <p className={styles.lead}>
            See what is holding your site back in search and AI answers, ranked by what to fix first.
          </p>

          <div className={styles.slot} data-open={messageOpen ? "true" : "false"}>
            <div className={styles.slotInner}>
              <div role="alert" aria-live="polite" aria-atomic="true">
                {err ? (
                  <p className={`${styles.message} ${styles.alert}`}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="12" y1="8" x2="12" y2="12" />
                      <line x1="12" y1="16" x2="12.01" y2="16" />
                    </svg>
                    <span>{err}</span>
                  </p>
                ) : null}
              </div>
              <div role="status" aria-live="polite" aria-atomic="true">
                {notice ? (
                  <p className={`${styles.message} ${styles.notice}`}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                      <polyline points="22,6 12,13 2,6" />
                    </svg>
                    <span>{notice}</span>
                  </p>
                ) : null}
              </div>
            </div>
          </div>

          <form className={styles.form} onSubmit={handleEmailLink} noValidate>
            <label htmlFor="auth-email" className={styles.label}>Email address</label>
            <input
              id="auth-email"
              name="email"
              type="email"
              inputMode="email"
              autoComplete="email"
              autoCapitalize="none"
              spellCheck={false}
              required
              className={styles.input}
              value={email}
              aria-invalid={emailError ? true : undefined}
              aria-describedby="auth-email-error"
              onChange={(e) => {
                setEmail(e.target.value);
                // Clear as soon as it is fixed; only complain again on blur.
                if (emailError && EMAIL_PATTERN.test(e.target.value.trim())) setEmailError("");
              }}
              onBlur={() => {
                const v = email.trim();
                setEmailError(v && !EMAIL_PATTERN.test(v) ? "Enter a valid email address, like name@example.com." : "");
              }}
            />
            <p id="auth-email-error" className={styles.fieldError}>{emailError}</p>
            <button type="submit" className={`btn btn--primary ${styles.fullBtn}`} disabled={busy}>
              {signingIn === "email" ? "Sending link..." : "Email me a sign-in link"}
            </button>
          </form>

          <div className={styles.divider}>or</div>

          <div className={styles.providers}>
            <button
              type="button"
              onClick={handleSignInWithGoogle}
              disabled={busy}
              className={`btn btn--secondary ${styles.fullBtn}`}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M21.35 11.1H12v2.98h5.35c-.23 1.4-1.65 4.1-5.35 4.1-3.22 0-5.85-2.67-5.85-5.96S8.78 6.26 12 6.26c1.83 0 3.06.78 3.76 1.45l2.56-2.47C16.68 3.7 14.54 2.75 12 2.75 6.9 2.75 2.75 6.9 2.75 12S6.9 21.25 12 21.25c5.34 0 8.88-3.75 8.88-9.04 0-.61-.07-1.07-.15-1.53z" />
              </svg>
              {signingIn === "google" ? "Opening Google..." : "Continue with Google"}
            </button>

            <div>
              <button
                type="button"
                onClick={handleSignInWithGitHub}
                disabled={busy}
                className={`btn btn--secondary ${styles.fullBtn}`}
                aria-describedby="auth-github-note"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                </svg>
                {signingIn === "github" ? "Opening GitHub..." : "Continue with GitHub"}
              </button>
              <p id="auth-github-note" className={styles.providerNote}>
                For team members who work on site code.
              </p>
            </div>

            {process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH === "1" ? (
            <button
              type="button"
              onClick={() => {
                setSession(DEV_SESSION);
              }}
              className={`btn btn--secondary ${styles.fullBtn} ${styles.devBtn}`}
            >
              Continue in Local Dev / Demo Mode
            </button>
            ) : null}
          </div>

          <p className={styles.trust}>Your projects are private to your account.</p>
        </section>
      </main>
    );
  }

  // 3. Authenticated: Render children wrapped in AuthContext, with top-level sign-out control
  const authValue: AuthContextType = {
    session,
    user: session.user,
    signOut: handleSignOut,
    loading: false,
  };

  return (
    <AuthContext.Provider value={authValue}>
      {children}
    </AuthContext.Provider>
  );
}
