/**
 * How the Google OAuth flow stores what it gets back, and how it proves the
 * callback it is handling is the one it started.
 *
 * Four defects this module exists to close, all in the same flow:
 *
 * 1. THE ACCESS TOKENS WERE READABLE BY PAGE SCRIPT. `gsc_access_token` and
 *    `gbp_secondary_access_token` were set `httpOnly: false`. They are bearer
 *    credentials for the client's Search Console and Google Business Profile —
 *    a listing anyone can see is a listing anyone with the token can edit. One
 *    XSS anywhere in the app, one bad dependency, one browser extension with
 *    host permissions, and they leave. Nothing ever read them from the browser:
 *    `document.cookie` appears nowhere in this codebase, and connection state
 *    comes from `/api/auth/google/status`, a server route. The flag bought
 *    nothing and cost everything.
 *
 * 2. NO STATE NONCE. `state` was `service:::returnTo` — a value an attacker can
 *    write out in full. With no unguessable component tied to the browser that
 *    began the flow, a victim's browser can be walked through a callback the
 *    victim never started, and the attacker's Google account gets bound into the
 *    victim's session. The state is now a random 32-byte nonce, compared against
 *    an httpOnly cookie, and the callback refuses when they disagree.
 *
 * 3. THE REDIRECT TARGET CAME OUT OF `state`. `destination` was read from the
 *    attacker-writable half of the state string and interpolated as
 *    `${origin}${destination}`. `destination = "@evil.com"` makes
 *    `https://app.example.com@evil.com`, whose host is evil.com — an open
 *    redirect off the back of a successful sign-in. Service and return-path now
 *    travel in httpOnly cookies, and `safeReturnPath` refuses anything that is
 *    not a single-slash-rooted local path anyway, on both sides of the flow.
 *
 * 4. NO `secure` FLAG. Every cookie here now sets it outside development, so
 *    none of them can be sent over plain HTTP.
 */

import type { NextRequest } from "next/server";

/** Production means HTTPS. Localhost dev over http:// still has to work. */
const isProd = process.env.NODE_ENV === "production";

type CookieOpts = {
  path: string;
  httpOnly: boolean;
  sameSite: "lax" | "strict";
  secure: boolean;
  maxAge: number;
};

/**
 * The options every OAuth cookie gets.
 *
 * `httpOnly` is not a parameter. There is no cookie in this flow that page
 * script has any business reading: a token is a credential, an email is PII, and
 * "connected" is a fact the status route already reports. Making it an argument
 * is how one of them ends up false again.
 */
export function oauthCookie(maxAgeSeconds: number): CookieOpts {
  return {
    path: "/",
    httpOnly: true,
    sameSite: "lax", // the callback is a top-level cross-site GET; strict drops it
    secure: isProd,
    maxAge: maxAgeSeconds,
  };
}

export const THIRTY_DAYS = 3600 * 24 * 30;
export const ONE_YEAR = 3600 * 24 * 365;
/** The window between the redirect out and the callback back. */
export const FLOW_TTL = 600;

/** A 256-bit nonce, hex. `crypto` is the Web Crypto global on every runtime. */
export function newStateNonce(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Constant-time compare. The window is small and the value single-use, so a
 * timing oracle here is a stretch — but a comparison that returns early on the
 * first differing character is free to avoid.
 */
export function nonceMatches(a: string | undefined, b: string | undefined): boolean {
  if (!a || !b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/**
 * A local path we are willing to send a browser to after sign-in, or null.
 *
 * Rooted at exactly one slash. `//evil.com` and `/\evil.com` are both read as
 * protocol-relative by browsers; `@evil.com` and `https://evil.com` change the
 * host once interpolated after an origin. Everything that is not plainly a path
 * on this site is refused, and the caller falls back to its own default.
 */
export function safeReturnPath(value: string | null | undefined): string | null {
  if (typeof value !== "string" || value.length === 0 || value.length > 512) return null;
  if (!value.startsWith("/")) return null;
  if (value.startsWith("//") || value.startsWith("/\\")) return null;
  if (/[\x00-\x1f\x7f]/.test(value)) return null;
  // No scheme, no authority, no credentials — a path, a query and a fragment.
  if (/[\\]/.test(value) || value.includes("://") || value.includes("@")) return null;
  // Never bounce back into the flow itself, or the loop never terminates.
  if (value.startsWith("/api/auth")) return null;
  return value;
}

/** The two services this flow can be started for. Anything else is "unified". */
export function safeService(value: string | null | undefined): "unified" | "gbp_secondary" {
  return value === "gbp_secondary" ? "gbp_secondary" : "unified";
}

/** Cookie names, in one place, so a delete cannot miss one. */
export const FLOW_COOKIES = [
  "google_oauth_state",
  "google_auth_return_to",
  "google_auth_service",
] as const;

export const PRIMARY_COOKIES = [
  "gsc_access_token",
  "gsc_refresh_token",
  "gsc_user_email",
  "gsc_connected",
  "gbp_connected",
] as const;

export const SECONDARY_COOKIES = [
  "gbp_secondary_access_token",
  "gbp_secondary_refresh_token",
  "gbp_secondary_user_email",
  "gbp_secondary_connected",
] as const;

/** Origin check for a state-changing POST that carries no CSRF token of its own. */
export function sameOriginPost(req: NextRequest): boolean {
  const origin = req.headers.get("origin");
  if (!origin) return false; // a same-origin fetch sends it; a form post from elsewhere does too
  try {
    return new URL(origin).origin === req.nextUrl.origin;
  } catch {
    return false;
  }
}
