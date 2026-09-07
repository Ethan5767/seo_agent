"use client";
import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "../lib/supabase";

/** Gate the app behind Supabase GitHub OAuth. Renders children only when signed
 *  in; otherwise a single "Sign in with GitHub" button. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setReady(true); });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  if (!ready) return <main><p>Loading…</p></main>;

  if (!session) {
    const signIn = async () => {
      setErr("…");
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "github",
        options: {
          // `repo` = permission to read/write the user's repos (Model B pushes/PRs).
          // `read:user` + `user:email` = identity. Supabase exposes the GitHub
          // token as session.provider_token after login (session-lived).
          scopes: "repo read:user user:email",
          redirectTo: typeof window !== "undefined" ? window.location.origin : undefined,
        },
      });
      if (error) setErr(error.message);
    };
    return (
      <main style={{ maxWidth: 380 }}>
        <h1>SEO / AEO Pipeline</h1>
        <p style={{ color: "#666" }}>Sign in to continue.</p>
        <button onClick={signIn}
          style={{ padding: ".7rem 1.2rem", background: "#24292f", color: "#fff", border: 0, borderRadius: 6, cursor: "pointer", fontSize: 15 }}>
          Sign in with GitHub
        </button>
        {err && err !== "…" && <p style={{ color: "#a60" }}>{err}</p>}
      </main>
    );
  }

  const who = session.user.email || session.user.user_metadata?.user_name || "signed in";
  return (
    <>
      <div style={{ textAlign: "right", padding: ".5rem 1rem", color: "#666", fontSize: 13 }}>
        {who} · <a style={{ color: "#1a5", cursor: "pointer" }} onClick={() => supabase.auth.signOut()}>sign out</a>
      </div>
      {children}
    </>
  );
}
