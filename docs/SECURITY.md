# REAI Security Architecture & Guardrails

This document details the multi-tenant isolation, abuse prevention, and operational security boundaries of the REAI platform and Python pipeline.

---

## 1. Authentication Model

Authentication is anchored by **Supabase Auth** on the frontend and verified server-side on API routes.

* **Frontend (`AuthGate` in `web/app/auth.tsx`):**
  * Genuinely gates the dashboard: shows a loading state while resolving sessions, prompts for GitHub OAuth sign-in when unauthenticated, and mounts the dashboard only for authenticated sessions.
  * Provides a visible session indicator with a working sign-out action (`supabase.auth.signOut()`).
* **Backend Verification (`web/lib/server-security.ts`):**
  * Validates the Supabase JWT Bearer token extracted from `Authorization: Bearer <token>` or `sb-*-auth-token` session cookies.
  * In non-production/local development, allows controlled test sessions via `x-dev-user-id` to facilitate offline testing.

### Route Authentication Scope
* **Authenticated Endpoints:**
  * `POST /api/scan`: Scan execution.
  * `POST /api/plan`: SOP triage ratchet & implementation brief generation.
  * `POST /api/remediate`: Worklist classification.
  * `POST /api/remediate/dryrun`: Dry-run fix prompt generation.
  * `POST /api/remediate/apply`: Claude Code repository patch execution.
  * `GET, POST /api/clients`: Client profile listing and registration.
  * `GET, POST /api/clients/[id]/scans`: Client scan history and scan result persistence.
  * `GET /api/clients/scans/[id]`: Individual scan report retrieval.
  * `GET, POST /api/traffic/snapshot`: Search performance and GSC snapshot persistence.
* **Public Utility & OAuth Flow Endpoints (Unauthenticated by Design):**
  * `GET /api/tools`: Public read-only catalog of available audit scanner tools.
  * `GET /api/auth/google`, `GET /api/auth/google/callback`, `GET /api/auth/google/status`, `POST /api/auth/google/save-token`: OAuth handshakes and Google Search Console cookie management.
  * `POST /api/gsc/query`: Authenticated via Google OAuth cookie (`gsc_access_token`).

---

## 2. Tenant Ownership & Row-Level Security (RLS)

* Every client, scan, tool breakdown, finding, metric record, and traffic snapshot is bound to a `user_id`.
* The server eliminates hardcoded tenant IDs. Queries and mutations strictly enforce `.eq("user_id", auth.user.id)`.
* Cross-tenant access is rejected with `404 Not Found` (to avoid leaking resource existence) or `401 Unauthorized`.

---

## 3. SSRF & Abuse Protection

Scanning external URLs introduces Server-Side Request Forgery (SSRF) risks. The scanning pipeline enforces strict multi-layer validation before any socket is opened:

1. **Protocol Whitelist:** Only `http:` and `https:` schemes are permitted. Schemes such as `file:`, `ftp:`, `gopher:`, `javascript:`, and `data:` are rejected with HTTP 400.
2. **Port Whitelist:** Only standard web traffic ports (`80`, `443`, `8080`, `8443`) are allowed. Database, administrative, and internal service ports (`22`, `3306`, `5432`, `6379`, etc.) are blocked.
3. **Restricted Hostnames:** Hostnames such as `localhost`, `*.local`, `*.internal`, `*.lan`, `metadata.google.internal`, and `instance-data` are rejected.
4. **Direct IP Blocking:** Direct IP literals pointing to private or reserved subnets are blocked immediately:
   * Loopback: `127.0.0.0/8`, `::1`
   * RFC 1918 Private: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
   * Cloud Metadata & Link-Local: `169.254.0.0/16`, `fe80::/10`
   * Carrier-Grade NAT: `100.64.0.0/10`
   * Multicast & Reserved: `224.0.0.0/4`, `240.0.0.0/4`, `ff00::/8`
   * IPv6 Unique Local: `fc00::/7`
   * IPv4-mapped IPv6: `::ffff:x.x.x.x` (validated against IPv4 rules)
5. **DNS-Aware Resolution & Anti-Rebinding:**
   * Target domain hostnames are resolved via DNS (`dns.promises.lookup`) prior to dispatching scans.
   * If DNS resolution fails (`ENOTFOUND`, timeout, etc.), the request **fails closed** and is rejected.
   * If **any** resolved IP address matches a private, loopback, or metadata subnet, the entire request is rejected with HTTP 400.

---

## 4. Request Body Size Limits

To prevent memory exhaustion and buffer overflow DoS attacks, API endpoints enforce strict body size limits before parsing JSON:

| Endpoint | Max Size Limit | Rejection Status |
|---|---|---|
| `POST /api/scan` | 256 KB | HTTP 413 (Payload Too Large) |
| `POST /api/clients` | 512 KB | HTTP 413 (Payload Too Large) |
| `POST /api/traffic/snapshot` | 512 KB | HTTP 413 (Payload Too Large) |
| `POST /api/plan` | 1 MB | HTTP 413 (Payload Too Large) |
| `POST /api/clients/[id]/scans` | 1 MB | HTTP 413 (Payload Too Large) |
| `POST /api/remediate/*` | 1 MB | HTTP 413 (Payload Too Large) |

Oversized requests are rejected immediately either via `Content-Length` inspection or stream byte counting without buffering the remaining payload into memory.

---

## 5. Rate Limiting & Single-Instance Limitation

* All resource-intensive and state-changing endpoints enforce sliding-window rate limits:
  * `POST /api/scan`: 15 scans / min per user/IP.
  * `POST /api/plan`: 30 triage runs / min per user/IP.
  * `POST /api/remediate`: 20 runs / min.
  * `POST /api/remediate/dryrun`: 15 runs / min.
  * `POST /api/remediate/apply`: 10 runs / min.
  * `POST /api/clients`: 30 writes / min.
  * `POST /api/clients/[id]/scans`: 30 writes / min.
  * `POST /api/traffic/snapshot`: 30 writes / min.

### Architectural Constraint (Single-Instance In-Memory Bound):
The default rate limiter is implemented in process-local memory (`Map<string, RateLimitRecord>`).
* **Single-Server / Local Dev:** Provides zero-latency burst and DoS protection with zero third-party dependencies.
* **Horizontal Clusters:** In multi-container or serverless deployments, each Node.js process manages its own in-memory table. Rate limits apply per instance rather than globally.
* **Production Recommendation:** For horizontally autoscaled deployments, replace the in-memory map with a shared key-value store (e.g. Redis / Upstash KV or Supabase RPC).
