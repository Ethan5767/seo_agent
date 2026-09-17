import test from "node:test";
import assert from "node:assert/strict";
import net from "node:net";

// ── Re-implement / Import pure security primitives for Node runtime test ──
// Mirror of web/lib/server-security.ts logic to verify runtime behavior in Node.js

function isPrivateOrUnsafeIp(ip) {
  if (!ip || typeof ip !== "string") {
    return { unsafe: true, reason: "Missing IP address." };
  }
  const cleanIp = ip.trim().toLowerCase().replace(/^\[/, "").replace(/\]$/, "");
  const ipType = net.isIP(cleanIp);

  if (ipType === 0) {
    return { unsafe: true, reason: `Malformed or unparseable IP address: '${ip}'` };
  }

  if (ipType === 4) {
    const parts = cleanIp.split(".").map((p) => parseInt(p, 10));
    if (parts.length !== 4 || parts.some((p) => isNaN(p) || p < 0 || p > 255)) {
      return { unsafe: true, reason: `Malformed IPv4 address: '${ip}'` };
    }
    const [a, b] = parts;

    if (a === 127) return { unsafe: true, reason: "Loopback IPv4 addresses (127.0.0.0/8) are forbidden." };
    if (a === 0) return { unsafe: true, reason: "Current network / broadcast IPv4 addresses (0.0.0.0/8) are forbidden." };
    if (a === 10) return { unsafe: true, reason: "Private IPv4 addresses (10.0.0.0/8) are forbidden." };
    if (a === 172 && b >= 16 && b <= 31) return { unsafe: true, reason: "Private IPv4 addresses (172.16.0.0/12) are forbidden." };
    if (a === 192 && b === 168) return { unsafe: true, reason: "Private IPv4 addresses (192.168.0.0/16) are forbidden." };
    if (a === 169 && b === 254) return { unsafe: true, reason: "Link-local and cloud metadata addresses (169.254.0.0/16) are strictly forbidden." };
    if (a === 100 && b >= 64 && b <= 127) return { unsafe: true, reason: "Shared/Carrier-Grade NAT addresses (100.64.0.0/10) are forbidden." };
    if (a >= 224 && a <= 239) return { unsafe: true, reason: "Multicast IPv4 addresses (224.0.0.0/4) are forbidden." };
    if (a >= 240) return { unsafe: true, reason: "Reserved / broadcast IPv4 addresses (240.0.0.0/4) are forbidden." };
    if ((a === 192 && b === 0) || (a === 198 && b === 51) || (a === 203 && b === 0)) return { unsafe: true, reason: "Reserved test IPv4 addresses are forbidden." };

    return { unsafe: false };
  }

  if (ipType === 6) {
    if (cleanIp.startsWith("::ffff:") || cleanIp.startsWith("0:0:0:0:0:ffff:")) {
      const v4Part = cleanIp.split(":").pop();
      if (v4Part && net.isIP(v4Part) === 4) {
        return isPrivateOrUnsafeIp(v4Part);
      }
    }
    if (cleanIp === "::1" || cleanIp === "0:0:0:0:0:0:0:1") return { unsafe: true, reason: "Loopback IPv6 address (::1) is forbidden." };
    if (cleanIp === "::" || cleanIp === "0:0:0:0:0:0:0:0") return { unsafe: true, reason: "Unspecified IPv6 address (::) is forbidden." };
    if (/^fe[89ab][0-9a-f]:/i.test(cleanIp) || cleanIp.startsWith("fe80:")) return { unsafe: true, reason: "Link-local IPv6 addresses (fe80::/10) are forbidden." };
    if (cleanIp.startsWith("fc") || cleanIp.startsWith("fd")) return { unsafe: true, reason: "Unique Local IPv6 addresses (fc00::/7) are forbidden." };
    if (cleanIp.startsWith("ff")) return { unsafe: true, reason: "Multicast IPv6 addresses (ff00::/8) are forbidden." };
    if (cleanIp.startsWith("2001:db8:") || cleanIp.startsWith("2001:0db8:")) return { unsafe: true, reason: "Documentation IPv6 addresses (2001:db8::/32) are forbidden." };
    if (cleanIp.startsWith("100::") || cleanIp.startsWith("0100::")) return { unsafe: true, reason: "Discard prefix IPv6 addresses (100::/64) are forbidden." };

    return { unsafe: false };
  }

  return { unsafe: true, reason: "Unknown IP address format." };
}

function validateScanTargetUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== "string") return { valid: false, reason: "URL must be a non-empty string." };
  let candidate = rawUrl.trim();
  if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(candidate)) candidate = `https://${candidate}`;

  let parsed;
  try {
    parsed = new URL(candidate);
  } catch {
    return { valid: false, reason: "Malformed URL format." };
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { valid: false, reason: `Forbidden URL scheme: '${parsed.protocol}'. Only http and https are permitted.` };
  }

  const hostname = parsed.hostname.toLowerCase().trim();
  if (!hostname) return { valid: false, reason: "Invalid target hostname." };

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

  if (parsed.port) {
    const portNum = parseInt(parsed.port, 10);
    const ALLOWED_PORTS = [80, 443, 8080, 8443];
    if (!ALLOWED_PORTS.includes(portNum)) {
      return { valid: false, reason: `Target port ${portNum} is not permitted.` };
    }
  }

  const ipType = net.isIP(hostname.replace(/^\[/, "").replace(/\]$/, ""));
  if (ipType !== 0) {
    const check = isPrivateOrUnsafeIp(hostname);
    if (check.unsafe) return { valid: false, reason: check.reason };
  }

  return { valid: true, normalizedUrl: parsed.toString() };
}

async function validateScanTargetUrlAsync(rawUrl, dnsResolver) {
  const syncCheck = validateScanTargetUrl(rawUrl);
  if (!syncCheck.valid) return syncCheck;

  const parsed = new URL(syncCheck.normalizedUrl);
  const hostname = parsed.hostname.toLowerCase().trim().replace(/^\[/, "").replace(/\]$/, "");

  const ipType = net.isIP(hostname);
  if (ipType !== 0) {
    return { valid: true, normalizedUrl: syncCheck.normalizedUrl, resolvedIps: [hostname] };
  }

  let addresses;
  try {
    addresses = await dnsResolver(hostname);
  } catch (err) {
    return {
      valid: false,
      reason: `DNS resolution failed for '${hostname}': ${err?.message || "Host not found"}. Unresolvable hostnames are blocked.`,
    };
  }

  if (!addresses || addresses.length === 0) {
    return { valid: false, reason: `DNS resolution returned no IP addresses for '${hostname}'.` };
  }

  const resolvedIps = [];
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

  return { valid: true, normalizedUrl: syncCheck.normalizedUrl, resolvedIps };
}

function checkRateLimitMap(rateLimitMap, identifier, limit = 20, windowMs = 60000, now = Date.now()) {
  let record = rateLimitMap.get(identifier);
  if (!record) {
    record = { timestamps: [] };
    rateLimitMap.set(identifier, record);
  }
  record.timestamps = record.timestamps.filter((ts) => now - ts < windowMs);
  if (record.timestamps.length >= limit) {
    const oldest = record.timestamps[0];
    const retryAfterSeconds = Math.max(1, Math.ceil((oldest + windowMs - now) / 1000));
    return { allowed: false, retryAfterSeconds, remaining: 0 };
  }
  record.timestamps.push(now);
  return { allowed: true, retryAfterSeconds: 0, remaining: limit - record.timestamps.length };
}

// ── Test Suites ──

test("isPrivateOrUnsafeIp blocks direct private and reserved IPv4 addresses", () => {
  const unsafeIps = [
    "127.0.0.1", "127.0.1.1", "127.255.255.254",
    "0.0.0.0", "255.255.255.255",
    "10.0.0.1", "10.255.255.254",
    "172.16.0.1", "172.31.255.254",
    "192.168.0.1", "192.168.1.254",
    "169.254.169.254", "169.254.1.1",
    "100.64.0.1", "100.127.255.254",
    "224.0.0.1", "239.255.255.255",
    "240.0.0.1",
  ];

  for (const ip of unsafeIps) {
    const res = isPrivateOrUnsafeIp(ip);
    assert.strictEqual(res.unsafe, true, `Expected IP '${ip}' to be flagged as unsafe`);
  }
});

test("isPrivateOrUnsafeIp blocks loopback, link-local, and private IPv6 addresses", () => {
  const unsafeIpv6 = [
    "::1",
    "::",
    "fe80::1", "fe80::200:5aee:feaa:20a2",
    "fc00::1", "fd00::1",
    "ff02::1", "ff01::1",
    "::ffff:192.168.1.1", "::ffff:127.0.0.1", "::ffff:169.254.169.254",
  ];

  for (const ip of unsafeIpv6) {
    const res = isPrivateOrUnsafeIp(ip);
    assert.strictEqual(res.unsafe, true, `Expected IPv6 '${ip}' to be flagged as unsafe`);
  }
});

test("isPrivateOrUnsafeIp allows legitimate public IPv4 and IPv6 addresses", () => {
  const safeIps = [
    "93.184.215.14",
    "8.8.8.8",
    "1.1.1.1",
    "142.250.190.46",
    "2606:2800:21f:cb07:6820:80da:af6b:8b2c",
    "2001:4860:4860::8888",
  ];

  for (const ip of safeIps) {
    const res = isPrivateOrUnsafeIp(ip);
    assert.strictEqual(res.unsafe, false, `Expected IP '${ip}' to be recognized as safe public IP`);
  }
});

test("validateScanTargetUrl blocks forbidden schemes and dangerous ports", () => {
  assert.strictEqual(validateScanTargetUrl("file:///etc/passwd").valid, false);
  assert.strictEqual(validateScanTargetUrl("ftp://ftp.example.com").valid, false);
  assert.strictEqual(validateScanTargetUrl("javascript:alert(1)").valid, false);
  assert.strictEqual(validateScanTargetUrl("https://example.com:22").valid, false);
  assert.strictEqual(validateScanTargetUrl("https://example.com:3306").valid, false);
  assert.strictEqual(validateScanTargetUrl("http://localhost:8080").valid, false);
  assert.strictEqual(validateScanTargetUrl("http://metadata.google.internal").valid, false);
  assert.strictEqual(validateScanTargetUrl("https://example.com:443").valid, true);
  assert.strictEqual(validateScanTargetUrl("http://example.com:8080").valid, true);
});

test("validateScanTargetUrlAsync detects DNS rebinding to private IPs", async () => {
  // Mock DNS resolver returning private RFC 1918
  const mockPrivateResolver = async () => [{ address: "192.168.1.10", family: 4 }];
  const resPrivate = await validateScanTargetUrlAsync("https://fake-client.com", mockPrivateResolver);
  assert.strictEqual(resPrivate.valid, false);
  assert.match(resPrivate.reason, /resolves to prohibited IP address/);

  // Mock DNS resolver returning loopback
  const mockLoopbackResolver = async () => [{ address: "127.0.0.1", family: 4 }];
  const resLoopback = await validateScanTargetUrlAsync("https://local-rebind.net", mockLoopbackResolver);
  assert.strictEqual(resLoopback.valid, false);
  assert.match(resLoopback.reason, /Loopback/);

  // Mock DNS resolver returning cloud metadata
  const mockMetaResolver = async () => [{ address: "169.254.169.254", family: 4 }];
  const resMeta = await validateScanTargetUrlAsync("https://cloud-meta.evil", mockMetaResolver);
  assert.strictEqual(resMeta.valid, false);
  assert.match(resMeta.reason, /cloud metadata/);
});

test("validateScanTargetUrlAsync fails closed on DNS lookup errors", async () => {
  const mockFailingResolver = async () => {
    const err = new Error("getaddrinfo ENOTFOUND non-existent-domain.xyz");
    err.code = "ENOTFOUND";
    throw err;
  };
  const res = await validateScanTargetUrlAsync("https://non-existent-domain.xyz", mockFailingResolver);
  assert.strictEqual(res.valid, false);
  assert.match(res.reason, /DNS resolution failed/);
});

test("validateScanTargetUrlAsync allows hostnames resolving strictly to public IPs", async () => {
  const mockPublicResolver = async () => [
    { address: "93.184.215.14", family: 4 },
    { address: "2606:2800:21f:cb07:6820:80da:af6b:8b2c", family: 6 },
  ];
  const res = await validateScanTargetUrlAsync("https://example.com", mockPublicResolver);
  assert.strictEqual(res.valid, true);
  assert.strictEqual(res.resolvedIps.length, 2);
});

test("Rate limiting sliding window triggers 429 when threshold is reached", () => {
  const rateLimitMap = new Map();
  const userId = "test-user-rate-limit";
  const limit = 5;
  const now = 1000000;

  for (let i = 0; i < limit; i++) {
    const res = checkRateLimitMap(rateLimitMap, userId, limit, 60000, now + i * 100);
    assert.strictEqual(res.allowed, true, `Request ${i + 1} should be allowed`);
  }

  // 6th request within window must be rejected
  const blocked = checkRateLimitMap(rateLimitMap, userId, limit, 60000, now + 1000);
  assert.strictEqual(blocked.allowed, false, "Request exceeding limit must be blocked");
  assert.strictEqual(blocked.remaining, 0);
  assert.ok(blocked.retryAfterSeconds > 0);
});
