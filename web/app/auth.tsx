"use client";
import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "../lib/supabase";

/** Gate the app behind a Supabase login. Renders children only when signed in;
 *  otherwise a minimal email/password sign-in / sign-up form. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setReady(true); });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  if (!ready) return <main><p>Loading…</p></main>;

  if (!session) {
    const run = async (mode: "in" | "up") => {
      setMsg("…");
      const fn = mode === "in"
        ? supabase.auth.signInWithPassword({ email, password: pw })
        : supabase.auth.signUp({ email, password: pw });
      const { error } = await fn;
      setMsg(error ? error.message : (mode === "up" ? "Check your email to confirm, then sign in." : ""));
    };
    return (
      <main style={{ maxWidth: 360 }}>
        <h1>SEO / AEO Pipeline</h1>
        <p style={{ color: "#666" }}>Sign in to continue.</p>
        <input style={{ width: "100%", padding: ".5rem", margin: ".25rem 0" }} placeholder="email"
          value={email} onChange={(e) => setEmail(e.target.value)} />
        <input style={{ width: "100%", padding: ".5rem", margin: ".25rem 0" }} placeholder="password" type="password"
          value={pw} onChange={(e) => setPw(e.target.value)} />
        <div style={{ display: "flex", gap: ".5rem", marginTop: ".5rem" }}>
          <button onClick={() => run("in")} style={{ padding: ".5rem 1rem", background: "#1a5", color: "#fff", border: 0, borderRadius: 6 }}>Sign in</button>
          <button onClick={() => run("up")} style={{ padding: ".5rem 1rem", background: "#eee", border: 0, borderRadius: 6 }}>Sign up</button>
        </div>
        {msg && <p style={{ color: "#a60" }}>{msg}</p>}
      </main>
    );
  }

  return (
    <>
      <div style={{ textAlign: "right", padding: ".5rem 1rem", color: "#666", fontSize: 13 }}>
        {session.user.email} · <a style={{ color: "#1a5", cursor: "pointer" }} onClick={() => supabase.auth.signOut()}>sign out</a>
      </div>
      {children}
    </>
  );
}
