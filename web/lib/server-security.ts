import { NextRequest, NextResponse } from "next/server";
import { createClient, SupabaseClient } from "@supabase/supabase-js";
import dns from "node:dns/promises";
import net from "node:net";

// ── Environment Configuration ──
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://hmvkpeouplkbimocbjis.supabase.co";
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "";

// Server-side auth verifier client using anon key
const authVerifierClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

export interface AuthenticatedUser {
  id: string;
  email?: string;
  role?: string;
}

export interface AuthResult {
  user: AuthenticatedUser | null;
  error: string | null;
  token?: string;
}

/**
 * Extracts and validates the authenticated Supabase user from the request.
 * Checks Authorization Bearer header, then common Supabase session cookies.
 * In development, allows x-dev-user-id header for automated tests and offline dev.
 */
export async function authenticateRequest(req: Request | NextRequest): Promise<AuthResult> {
  const authHeader = req.headers.get("authorization") || req.headers.get("Authorization");
  let token: string | undefined;

  if (authHeader && authHeader.toLowerCase().startsWith("bearer ")) {
    token = authHeader.slice(7).trim();
  }

  // Check cookies if header is absent
  if (!token && "cookies" in req) {
    const nextReq = req as NextRequest;
    const cookieToken =
      nextReq.cookies.get("sb-access-token")?.value ||
      nextReq.cookies.get("supabase-auth-token")?.value;
    if (cookieToken) token = cookieToken;
  }

  // Parse raw Cookie header if needed
  if (!token) {
    const rawCookie = req.headers.get("cookie") || "";
    const match = rawCookie.match(/sb-[a-z0-9]+-auth-token=([^;]+)/i) ||
                  rawCookie.match(/sb-access-token=([^;]+)/i);
    if (match && match[1]) {
      try {
        const decoded = decodeURIComponent(match[1]);
        if (decoded.startsWith("[") || decoded.startsWith("{")) {
          const parsed = JSON.parse(decoded);
          token = Array.isArray(parsed) ? parsed[0] : (parsed.access_token || parsed);
        } else {
          token = decoded;
        }
      } catch {
        token = match[1];
      }
    }
  }

  if (token) {
    try {
      const { data, error } = await authVerifierClient.auth.getUser(token);
      if (!error && data?.user) {
        return {
          user: {
            id: data.user.id,
            email: data.user.email,
            role: data.user.role,
          },
          error: null,
          token,
        };
      }
    } catch {
      // Token verification failed
    }
  }

  // Local development fallback. Gated on an EXPLICIT opt-in, never inferred from
  // NODE_ENV (B-066).
  //
  // This used to read `process.env.NODE_ENV !== "production"`, which fails OPEN:
  // any container started without NODE_ENV explicitly set — a plain `node
  // server.js`, a compose file missing one line, a preview deploy — turned every
  // route unauthenticated, and the caller chose their own user id via the
  // `x-dev-user-id` header. It compounded downstream: the dev path returns no
  // token, so `getScopedDb` fell through to the SERVICE ROLE key, which ignores
  // Row Level Security entirely, leaving `.eq("user_id", ...)` — populated from
  // that same attacker-supplied header — as the only tenant boundary. There is no
  // middleware.ts, so this function is the only authentication in the product.
  //
  // ALLOW_DEV_AUTH must be set deliberately, and is refused in production even
  // then, so a stray value in a deployed env cannot re-open it.
  const isDev = process.env.ALLOW_DEV_AUTH === "1" && process.env.NODE_ENV !== "production";
  if (isDev) {
    const devHeaderUserId = req.headers.get("x-dev-user-id");
    return {
      user: {
        id: devHeaderUserId?.trim() || "00000000-0000-0000-0000-000000000001",
        email: "local-dev@example.com",
      },
      error: null,
    };
  }

  return {
    user: null,
    error: "Unauthorized: Missing or invalid Supabase authentication token.",
  };
}

/**
 * Returns a Supabase client scoped to the authenticated user's credentials.
 * If user token is available, uses the anon key with user's Authorization header (RLS).
 * Otherwise falls back to service role key with strict server-side user_id filtering.
 *
 * B-066: that fallback is the second half of the auth-bypass chain. The service
 * role ignores Row Level Security completely, so when it is reached the ONLY
 * tenant boundary left is whatever `.eq("user_id", ...)` each route remembers to
 * apply — and a route that forgets returns the whole table. It is reached
 * whenever `token` is absent, which was exactly the state the dev fallback
 * produced. The dev path is now opt-in (see `authenticateRequest`), and this
 * function refuses the service-role path in production so the two failures can
 * never line up again.
 */
export function getScopedDb(user: AuthenticatedUser, token?: string): SupabaseClient {
  if (!token && process.env.NODE_ENV === "production") {
    throw new Error(
      "getScopedDb: refusing to fall back to the service-role key for a request " +
      "carrying no user token. Row Level Security would be bypassed."
    );
  }
  if (token && SUPABASE_ANON_KEY) {
    return createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      global: {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    });
  }

  // Server-role key (service role key must stay strictly server-side)
  const key = SUPABASE_SERVICE_ROLE_KEY || SUPABASE_ANON_KEY;
  return createClient(SUPABASE_URL, key);
}

// ── Rate Limiter (In-Memory Sliding Window) ──
/**
 * IN-MEMORY RATE LIMITER SPECIFICATION & ARCHITECTURAL BOUND:
 *
 * This rate limiter tracks timestamps inside a Node.js process-local `Map`.
 *
 * SINGLE-INSTANCE BOUND:
 * In single-server and local-development environments, this sliding window gives
 * microsecond-level zero-latency burst and DoS protection per tenant / IP.
 *
 * HORIZONTAL CLUSTER LIMITATION:
 * Because the state is stored in memory, each Node process / worker instance
 * tracks its own rate-limit window. Across horizontally auto-scaled instances,
 * limits are applied per-instance rather than globally.
 * To scale globally across distributed containers, wire an external store
 * (e.g. Redis / Upstash KV or Supabase RPC). Do not simulate distributed
 * guarantees in local memory.
 */
interface RateLimitRecord {
  timestamps: number[];
}
const rateLimitMap = new Map<string, RateLimitRecord>();

// Clean up old entries every 5 minutes
if (typeof setInterval !== "undefined") {
  setInterval(() => {
    const now = Date.now();
    for (const [key, record] of rateLimitMap.entries()) {
      record.timestamps = record.timestamps.filter((ts) => now - ts < 60_000);
      if (record.timestamps.length === 0) {
        rateLimitMap.delete(key);
      }
    }
  }, 300_000);
}

export function checkRateLimit(
  identifier: string,
  limit: number = 20,
  windowMs: number = 60_000
): { allowed: boolean; retryAfterSeconds: number; remaining: number } {
  const now = Date.now();
  let record = rateLimitMap.get(identifier);
  if (!record) {
    record = { timestamps: [] };
    rateLimitMap.set(identifier, record);
  }

  // Remove timestamps outside the sliding window
  record.timestamps = record.timestamps.filter((ts) => now - ts < windowMs);

  if (record.timestamps.length >= limit) {
    const oldest = record.timestamps[0];
    const retryAfterSeconds = Math.max(1, Math.ceil((oldest + windowMs - now) / 1000));
    return { allowed: false, retryAfterSeconds, remaining: 0 };
  }

  record.timestamps.push(now);
  return {
    allowed: true,
    retryAfterSeconds: 0,
    remaining: limit - record.timestamps.length,
  };
}

// ── Request Size Limiter ──

/**
 * Reads and parses JSON from request body while enforcing a strict maximum byte size.
 * Rejects requests larger than maxBytes with HTTP 413 (Payload Too Large).
 * Rejects invalid JSON syntax with HTTP 400 (Bad Request).
 */
export async function readJsonBodyWithLimit<T = any>(
  req: Request | NextRequest,
  maxBytes: number = 1024 * 1024 // default 1 MB
): Promise<{ data?: T; errorResponse?: NextResponse }> {
  // 1. Fast reject via Content-Length header before buffering stream
  const contentLength = req.headers.get("content-length");
  if (contentLength) {
    const len = parseInt(contentLength, 10);
    if (!isNaN(len) && len > maxBytes) {
      return {
        errorResponse: NextResponse.json(
          { error: `Payload Too Large: Request body size (${len} bytes) exceeds the ${maxBytes} byte limit.` },
          { status: 413 }
        ),
      };
    }
  }

  // 2. Read body text and enforce byte count limit
  try {
    const rawText = await req.text();
    const actualBytes = Buffer.byteLength(rawText, "utf8");
    if (actualBytes > maxBytes) {
      return {
        errorResponse: NextResponse.json(
          { error: `Payload Too Large: Request body size (${actualBytes} bytes) exceeds the ${maxBytes} byte limit.` },
          { status: 413 }
        ),
      };
    }

    if (!rawText || rawText.trim().length === 0) {
      return { data: {} as T };
    }

    const data = JSON.parse(rawText) as T;
    return { data };
  } catch (err: any) {
    return {
      errorResponse: NextResponse.json(
        { error: `Invalid JSON payload: ${err?.message || "Malformed request body"}` },
        { status: 400 }
      ),
    };
  }
}

// ── SSRF & Target URL Validation ──

export interface UrlValidationResult {
  valid: boolean;
  reason?: string;
  normalizedUrl?: string;
}

/**
 * Checks whether an IPv4 or IPv6 address belongs to private, loopback, link-local,
 * cloud metadata, multicast, broadcast, or reserved networks.
 */
export function isPrivateOrUnsafeIp(ip: string): { unsafe: boolean; reason?: string } {
  if (!ip || typeof ip !== "string") {
    return { unsafe: true, reason: "Missing IP address." };
  }
  const cleanIp = ip.trim().toLowerCase().replace(/^\[/, "").replace(/\]$/, "");
  const ipType = net.isIP(cleanIp);

  if (ipType === 0) {
    return { unsafe: true, reason: `Malformed or unparseable IP address: '${ip}'` };
  }

  // ── IPv4 Checks ──
  if (ipType === 4) {
    const parts = cleanIp.split(".").map((p) => parseInt(p, 10));
    if (parts.length !== 4 || parts.some((p) => isNaN(p) || p < 0 || p > 255)) {
      return { unsafe: true, reason: `Malformed IPv4 address: '${ip}'` };
    }
    const [a, b] = parts;

    // Loopback (127.0.0.0/8)
    if (a === 127) {
      return { unsafe: true, reason: "Loopback IPv4 addresses (127.0.0.0/8) are forbidden." };
    }
    // Current network / Broadcast (0.0.0.0/8)
    if (a === 0) {
      return { unsafe: true, reason: "Current network / broadcast IPv4 addresses (0.0.0.0/8) are forbidden." };
    }
    // Private RFC 1918: 10.0.0.0/8
    if (a === 10) {
      return { unsafe: true, reason: "Private IPv4 addresses (10.0.0.0/8) are forbidden." };
    }
    // Private RFC 1918: 172.16.0.0/12 (172.16.0.0 - 172.31.255.255)
    if (a === 172 && b >= 16 && b <= 31) {
      return { unsafe: true, reason: "Private IPv4 addresses (172.16.0.0/12) are forbidden." };
    }
    // Private RFC 1918: 192.168.0.0/16
    if (a === 192 && b === 168) {
      return { unsafe: true, reason: "Private IPv4 addresses (192.168.0.0/16) are forbidden." };
    }
    // Link-Local & Cloud Metadata (169.254.0.0/16, including 169.254.169.254)
    if (a === 169 && b === 254) {
      return { unsafe: true, reason: "Link-local and cloud metadata addresses (169.254.0.0/16) are strictly forbidden." };
    }
    // Carrier-Grade NAT (100.64.0.0/10: 100.64.0.0 - 100.127.255.255)
    if (a === 100 && b >= 64 && b <= 127) {
      return { unsafe: true, reason: "Shared/Carrier-Grade NAT addresses (100.64.0.0/10) are forbidden." };
    }
    // Multicast (224.0.0.0/4: 224.0.0.0 - 239.255.255.255)
    if (a >= 224 && a <= 239) {
      return { unsafe: true, reason: "Multicast IPv4 addresses (224.0.0.0/4) are forbidden." };
    }
    // Reserved / Future use (240.0.0.0/4, includes 255.255.255.255 broadcast)
    if (a >= 240) {
      return { unsafe: true, reason: "Reserved / broadcast IPv4 addresses (240.0.0.0/4) are forbidden." };
    }
    // Documentation / Test Networks (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24)
    if ((a === 192 && b === 0) || (a === 198 && b === 51) || (a === 203 && b === 0)) {
      return { unsafe: true, reason: "Reserved test IPv4 addresses are forbidden." };
    }

    return { unsafe: false };
  }

  // ── IPv6 Checks ──
  if (ipType === 6) {
    // Check for IPv4-mapped IPv6 (e.g. ::ffff:192.168.1.1)
    if (cleanIp.startsWith("::ffff:") || cleanIp.startsWith("0:0:0:0:0:ffff:")) {
      const v4Part = cleanIp.split(":").pop();
      if (v4Part && net.isIP(v4Part) === 4) {
        return isPrivateOrUnsafeIp(v4Part);
      }
    }

    // Loopback (::1)
    if (cleanIp === "::1" || cleanIp === "0:0:0:0:0:0:0:1") {
      return { unsafe: true, reason: "Loopback IPv6 address (::1) is forbidden." };
    }
    // Unspecified (::)
    if (cleanIp === "::" || cleanIp === "0:0:0:0:0:0:0:0") {
      return { unsafe: true, reason: "Unspecified IPv6 address (::) is forbidden." };
    }
    // Link-local (fe80::/10: fe80 to febf)
    if (/^fe[89ab][0-9a-f]:/i.test(cleanIp) || cleanIp.startsWith("fe80:")) {
      return { unsafe: true, reason: "Link-local IPv6 addresses (fe80::/10) are forbidden." };
    }
    // Unique Local (fc00::/7: fc00 to fdff)
    if (cleanIp.startsWith("fc") || cleanIp.startsWith("fd")) {
      return { unsafe: true, reason: "Unique Local IPv6 addresses (fc00::/7) are forbidden." };
    }
    // Multicast (ff00::/8)
    if (cleanIp.startsWith("ff")) {
      return { unsafe: true, reason: "Multicast IPv6 addresses (ff00::/8) are forbidden." };
    }
    // Documentation (2001:db8::/32)
    if (cleanIp.startsWith("2001:db8:") || cleanIp.startsWith("2001:0db8:")) {
      return { unsafe: true, reason: "Documentation IPv6 addresses (2001:db8::/32) are forbidden." };
    }
    // Discard prefix (100::/64)
    if (cleanIp.startsWith("100::") || cleanIp.startsWith("0100::")) {
      return { unsafe: true, reason: "Discard prefix IPv6 addresses (100::/64) are forbidden." };
    }

    return { unsafe: false };
  }

  return { unsafe: true, reason: "Unknown IP address format." };
}

/**
 * Fast synchronous URL format and policy check:
 * Validates protocol, port, syntax, and literal IP bounds.
 */
export function validateScanTargetUrl(rawUrl: string): UrlValidationResult {
  if (!rawUrl || typeof rawUrl !== "string") {
    return { valid: false, reason: "URL must be a non-empty string." };
  }

  let parsed: URL;
  try {
    let candidate = rawUrl.trim();
    if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(candidate)) {
      candidate = `https://${candidate}`;
    }
    parsed = new URL(candidate);
  } catch {
    return { valid: false, reason: "Malformed URL format." };
  }

  // 1. Protocol validation
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { valid: false, reason: `Forbidden URL scheme: '${parsed.protocol}'. Only http and https are permitted.` };
  }

  const hostname = parsed.hostname.toLowerCase().trim();

  // 2. Reject empty or local domain names
  if (!hostname || hostname.length === 0) {
    return { valid: false, reason: "Invalid target hostname." };
  }

  if (
    hostname === "localhost" ||
    hostname.endsWith(".localhost") ||
    hostname.endsWith(".local") ||
    hostname.endsWith(".internal") ||
    hostname.endsWith(".lan") ||
    hostname.endsWith(".arpa") ||
    hostname.endsWith(".invalid") ||
    hostname === "metadata.google.internal" ||
    hostname === "instance-data"
  ) {
    return { valid: false, reason: "Requests to localhost, local domains, or cloud metadata endpoints are strictly prohibited." };
  }

  // 3. Port check (prevent port scanning)
  if (parsed.port) {
    const portNum = parseInt(parsed.port, 10);
    const ALLOWED_PORTS = [80, 443, 8080, 8443];
    if (!ALLOWED_PORTS.includes(portNum)) {
      return { valid: false, reason: `Target port ${portNum} is not permitted. Only standard web ports (80, 443, 8080, 8443) are allowed.` };
    }
  }

  // 4. Literal IP check
  const ipType = net.isIP(hostname.replace(/^\[/, "").replace(/\]$/, ""));
  if (ipType !== 0) {
    const check = isPrivateOrUnsafeIp(hostname);
    if (check.unsafe) {
      return { valid: false, reason: check.reason };
    }
  }

  return {
    valid: true,
    normalizedUrl: parsed.toString(),
  };
}

export type DnsResolver = (hostname: string) => Promise<Array<{ address: string; family: number }>>;

const defaultDnsResolver: DnsResolver = async (hostname: string) => {
  return await dns.lookup(hostname, { all: true });
};

/**
 * DNS-aware URL validator for scanner endpoints.
 * Resolves target hostname via DNS, ensuring no public hostname rebinds or resolves
 * to loopback, private subnets, link-local, or cloud metadata IPs.
 * Fails closed if DNS resolution fails.
 */
export async function validateScanTargetUrlAsync(
  rawUrl: string,
  options?: { dnsResolver?: DnsResolver }
): Promise<UrlValidationResult & { resolvedIps?: string[] }> {
  // 1. Run fast syntax and policy checks
  const syncCheck = validateScanTargetUrl(rawUrl);
  if (!syncCheck.valid) {
    return syncCheck;
  }

  const parsed = new URL(syncCheck.normalizedUrl!);
  const hostname = parsed.hostname.toLowerCase().trim().replace(/^\[/, "").replace(/\]$/, "");

  // 2. Direct IP check: if hostname is an IP literal, it was already verified by syncCheck
  const ipType = net.isIP(hostname);
  if (ipType !== 0) {
    return {
      valid: true,
      normalizedUrl: syncCheck.normalizedUrl,
      resolvedIps: [hostname],
    };
  }

  // 3. DNS-Aware Resolution
  const resolver = options?.dnsResolver || defaultDnsResolver;
  let addresses: Array<{ address: string; family: number }>;
  try {
    addresses = await resolver(hostname);
  } catch (err: any) {
    // Fail closed: if hostname cannot be resolved, reject scan request
    return {
      valid: false,
      reason: `DNS resolution failed for '${hostname}': ${err?.message || "Host not found"}. Unresolvable hostnames are blocked.`,
    };
  }

  if (!addresses || addresses.length === 0) {
    return {
      valid: false,
      reason: `DNS resolution returned no IP addresses for '${hostname}'.`,
    };
  }

  // 4. Verify all resolved IP addresses are safe public IPs
  const resolvedIps: string[] = [];
  for (const entry of addresses) {
    const ip = entry.address;
    resolvedIps.push(ip);
    const check = isPrivateOrUnsafeIp(ip);
    if (check.unsafe) {
      return {
        valid: false,
        reason: `Target hostname '${hostname}' resolves to prohibited IP address (${ip}): ${check.reason}`,
      };
    }
  }

  return {
    valid: true,
    normalizedUrl: syncCheck.normalizedUrl,
    resolvedIps,
  };
}

/**
 * Caps scan options (crawl depth, page limits) to prevent resource exhaustion.
 */
export function sanitizeScanOptions(opts: any = {}) {
  const maxPages = Math.min(Math.max(1, parseInt(opts.maxPages || opts.crawl_pages || 1, 10)), 50);
  const maxDepth = Math.min(Math.max(1, parseInt(opts.depth || 1, 10)), 3);
  return {
    ...opts,
    maxPages,
    crawl_pages: maxPages,
    depth: maxDepth,
  };
}
