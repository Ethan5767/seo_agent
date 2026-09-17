"""Response headers, the live redirect chain, soft-404s and the TLS certificate.

Everything here reads what an HTTP response says about itself rather than what
the HTML says. None of it was checkable until `common.curl_full`: `curl -sL`
returned the body alone, so a security header, an `X-Robots-Tag`, a cache or
compression header and every redirect hop were invisible, and a missing page
answering 200 read exactly like a live one.

Pure by construction: rows come from a headers dict / a redirect chain, and the
two checks that must ask the origin something new (`entry_point_rows`,
`soft_404_rows`) take their fetcher as an argument, like every other free check
module here.
"""
from __future__ import annotations

import os
import socket
import ssl
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from pipeline.scanner.rows import make_row

_mk = {p: make_row(p) for p in ("headers", "redirect", "hygiene", "security")}


def _row(prefix: str, code: str, what: str, severity: str, why: str, fix: str, detail: str = "") -> dict:
    """A row whose `code` is stated, not slugged from its title.

    The ratchet matches findings across scans by code, so a reworded title would
    otherwise retire a finding and open a new one in its place.
    """
    r = _mk[prefix](what, severity, why, fix, detail)
    r["code"] = f"{prefix}.{code}"
    return r


def _hdr(code, what, severity, why, fix, detail=""):
    return _row("headers", code, what, severity, why, fix, detail)


def _redir(code, what, severity, why, fix, detail=""):
    return _row("redirect", code, what, severity, why, fix, detail)


def _hyg(code, what, severity, why, fix, detail=""):
    return _row("hygiene", code, what, severity, why, fix, detail)


def _sec(code, what, severity, why, fix, detail=""):
    return _row("security", code, what, severity, why, fix, detail)

# Header -> (row title, why it matters, what a good value looks like).
SECURITY_HEADERS = [
    ("strict-transport-security", "hsts", "HSTS",
     "Strict-Transport-Security tells browsers to reach this site over HTTPS only, which closes the "
     "first insecure request an attacker can intercept.",
     "add Strict-Transport-Security with a max-age of at least 6 months"),
    ("content-security-policy", "content_security_policy", "Content Security Policy",
     "A Content-Security-Policy limits where scripts may load from, which is the main defence against "
     "an injected script running on the page.",
     "add a Content-Security-Policy, starting in report-only mode"),
    ("x-content-type-options", "x-content-type-options", "X-Content-Type-Options",
     "X-Content-Type-Options: nosniff stops a browser guessing a file's type and running it as script.",
     "send X-Content-Type-Options: nosniff"),
    ("x-frame-options", "x-frame-options", "X-Frame-Options",
     "X-Frame-Options (or a CSP frame-ancestors rule) stops another site framing these pages to "
     "trick a visitor into clicking something.",
     "send X-Frame-Options: DENY or SAMEORIGIN"),
    ("referrer-policy", "referrer-policy", "Referrer-Policy",
     "Referrer-Policy controls how much of the current URL is handed to other sites a visitor clicks "
     "through to.",
     "send Referrer-Policy: strict-origin-when-cross-origin"),
]

# Six months, the floor for preload lists and the usual advice.
HSTS_MIN_AGE = 15_552_000


def _max_age(value: str) -> int:
    for part in (value or "").split(";"):
        part = part.strip().lower()
        if part.startswith("max-age="):
            try:
                return int(part.split("=", 1)[1])
            except ValueError:
                return 0
    return 0


def header_rows(headers: dict | None) -> list[dict]:
    """Security, indexing, cache and compression headers of the fetched page."""
    if headers is None:
        # Nothing was read — an origin that answered nothing is not an origin
        # with nothing wrong: `info` keeps it out of the score. An EMPTY dict is
        # a different fact (a response that sent none of these headers), judged
        # below header by header.
        return [_hdr("not_read", "Response headers", "info",
                     "No response headers were read for this page, so nothing here could be judged.",
                     "re-run once the page responds", detail="no response")]

    rows: list[dict] = []
    for key, code, title, why, fix in SECURITY_HEADERS:
        value = headers.get(key, "")
        if key == "x-frame-options" and not value:
            # A CSP that names frame-ancestors does the same job, and is stronger.
            if "frame-ancestors" in headers.get("content-security-policy", ""):
                rows.append(_hdr(code, title, "ok", "Framing is restricted by the Content-Security-Policy's "
                                              "frame-ancestors rule.", "passing", detail="via CSP"))
                continue
        if not value:
            rows.append(_hdr(code, title, "warn", why, fix, detail="header not sent"))
            continue
        if key == "strict-transport-security" and _max_age(value) < HSTS_MIN_AGE:
            rows.append(_hdr(code, title, "warn",
                             f"{why} This one lasts {_max_age(value)} seconds, under the six months "
                             "browsers and preload lists expect.",
                             "raise max-age to at least 15552000", detail=f"max-age={_max_age(value)}"))
            continue
        rows.append(_hdr(code, title, "ok", f"{title} is set.", "passing", detail=value[:120]))

    # X-Robots-Tag: the header twin of the meta robots tag, and just as final.
    xrobots = headers.get("x-robots-tag", "")
    if "noindex" in xrobots.lower():
        rows.append(_hdr("x-robots-tag", "X-Robots-Tag", "error",
                         "The server sends an X-Robots-Tag header telling search engines not to index this "
                         "page. It takes effect whatever the page's HTML says.",
                         "remove noindex from the X-Robots-Tag header for pages that should rank",
                         detail=xrobots[:120]))
    else:
        rows.append(_hdr("x-robots-tag", "X-Robots-Tag", "ok",
                         "No X-Robots-Tag header blocks this page from being indexed."
                         + (f" The header is set to: {xrobots}." if xrobots else ""),
                         "passing", detail=xrobots[:120] or "not sent"))

    encoding = headers.get("content-encoding", "")
    if encoding:
        rows.append(_hdr("compression", "Compression", "ok",
                         f"The page is compressed in transit ({encoding}), so it downloads faster.",
                         "passing", detail=encoding))
    else:
        rows.append(_hdr("compression", "Compression", "warn",
                         "The page is served uncompressed, so every visitor downloads more bytes than they "
                         "need to.",
                         "enable gzip or brotli compression at the server or CDN", detail="no Content-Encoding"))

    cache = headers.get("cache-control", "")
    if cache:
        rows.append(_hdr("cache-control", "Cache-Control", "ok",
                         "The page states how it may be cached, so browsers and the CDN can reuse it.",
                         "passing", detail=cache[:120]))
    else:
        rows.append(_hdr("cache-control", "Cache-Control", "warn",
                         "No Cache-Control header, so caching is left to each browser's guess.",
                         "send an explicit Cache-Control for pages and for static assets",
                         detail="header not sent"))
    return rows


# Statuses that move a request somewhere else.
_REDIRECTS = (301, 302, 303, 307, 308)
_TEMPORARY = (302, 307)


def redirect_rows(url: str, chain: list[dict] | None) -> list[dict]:
    """The hops between `url` and the page that finally answered."""
    chain = chain or []
    if not chain:
        return [_redir("chain", "Redirects", "info",
                       "No response chain was recorded for this URL, so its redirects were not judged.",
                       "re-run once the URL responds", detail="not measured")]

    hops = [h for h in chain if h.get("status") in _REDIRECTS]
    seen: list[str] = []
    looped = False
    for h in chain:
        target = h.get("location") or ""
        if target and target in seen:
            looped = True
        seen.append(target)

    trail = " → ".join(str(h.get("status")) for h in chain)
    if looped:
        return [_redir("loop", "Redirect loop", "error",
                       f"This URL redirects back to somewhere it has already been ({trail}), so no page is "
                       "ever reached.",
                       "break the cycle so the URL resolves to one final page", detail=trail)]

    rows: list[dict] = []
    if len(hops) > 1:
        rows.append(_redir("chain", "Redirect chain", "warn",
                           f"Reaching this page takes {len(hops)} redirects ({trail}). Each hop costs time for "
                           "a visitor and crawl budget for a search engine, and link value is diluted along the way.",
                           "collapse the hops so the first request lands on the final URL",
                           detail=f"{len(hops)} hops: {trail}"))
    elif hops:
        rows.append(_redir("chain", "Redirect chain", "ok",
                           f"This URL reaches its destination in one redirect ({trail}).",
                           "passing", detail=f"1 hop: {trail}"))
    else:
        rows.append(_redir("chain", "Redirect chain", "ok", "This URL answers directly, with no redirect.",
                           "passing", detail="no redirect"))

    temporary = [h for h in hops if h.get("status") in _TEMPORARY]
    if temporary:
        codes = ", ".join(str(h["status"]) for h in temporary)
        rows.append(_redir("temporary", "Temporary redirect", "warn",
                           f"The path to this page uses a temporary redirect ({codes}). A temporary redirect "
                           "tells search engines the move may be undone, so the destination does not inherit "
                           "the original URL's ranking signals.",
                           "use 301 or 308 where the move is permanent", detail=f"{codes} in {trail}"))
    return rows


def _origin(url: str) -> tuple:
    parts = urlsplit(url)
    host = parts.netloc
    bare = host[4:] if host.startswith("www.") else host
    return parts.scheme or "https", host, bare


def entry_point_rows(url: str, fetch=None) -> list[dict]:
    """apex → www and http → https, which no page crawl can see.

    Neither is reachable by following internal links: they are what happens
    before the site is entered at all.
    """
    from pipeline.lib.common import curl_full
    fetch = fetch or curl_full
    scheme, host, bare = _origin(url)
    rows: list[dict] = []

    insecure = urlunsplit(("http", bare, "/", "", ""))
    r = fetch(insecure, cache_bust=False)
    chain = r.get("chain") or []
    upgraded = any(str(h.get("location", "")).startswith("https://") for h in chain)
    if not chain:
        rows.append(_redir("https_upgrade", "HTTPS upgrade", "info",
                           f"{insecure} did not respond, so the HTTP to HTTPS redirect was not judged.",
                           "check the origin answers on port 80", detail="no response"))
    elif upgraded:
        rows.append(_redir("https_upgrade", "HTTPS upgrade", "ok",
                           "Requests to the insecure http:// address are redirected to https://.",
                           "passing", detail=" → ".join(str(h.get("status")) for h in chain)))
    else:
        rows.append(_redir("https_upgrade", "HTTPS upgrade", "error",
                           f"{insecure} serves a page instead of redirecting to https://, so the site is "
                           "reachable over an insecure connection and the same content exists at two addresses.",
                           "redirect all http:// traffic to https:// with a 301",
                           detail=f"answered {r.get('status')} with no upgrade"))

    apex = urlunsplit(("https", bare, "/", "", ""))
    r2 = fetch(apex, cache_bust=False)
    chain2 = r2.get("chain") or []
    moved = [h for h in chain2 if h.get("status") in _REDIRECTS]
    if not chain2:
        rows.append(_redir("apex", "Apex domain", "info",
                           f"{apex} did not respond, so apex to www behaviour was not judged.",
                           "check DNS for the bare domain", detail="no response"))
    elif host.startswith("www.") and not moved:
        rows.append(_redir("apex", "Apex domain", "warn",
                           f"The site is served at {host}, but {apex} answers directly instead of redirecting "
                           "there. The same pages then exist at two hostnames.",
                           "redirect the apex domain to the www hostname with a 301",
                           detail=f"{apex} answered {r2.get('status')}"))
    else:
        rows.append(_redir("apex", "Apex domain", "ok",
                           "The apex domain resolves consistently with the hostname the site is served on.",
                           "passing",
                           detail=" → ".join(str(h.get("status")) for h in chain2) or str(r2.get("status"))))
    return rows


# A path no site publishes. Random so a cached 200 for a previously probed URL
# cannot make a broken 404 handler look correct.
def _absent_path() -> str:
    return f"/this-page-does-not-exist-{os.urandom(4).hex()}"


def soft_404_rows(url: str, fetch=None) -> list[dict]:
    """Does a URL that cannot exist actually answer 404?"""
    from pipeline.lib.common import curl_full
    fetch = fetch or curl_full
    scheme, host, _ = _origin(url)
    probe = urlunsplit((scheme, host, _absent_path(), "", ""))
    r = fetch(probe, cache_bust=False)
    status = r.get("status") or 0
    chain = r.get("chain") or []
    hops = [h for h in chain if h.get("status") in _REDIRECTS]

    if status == 0:
        return [_hyg("soft_404", "Missing pages return 404", "info",
                     "The test URL did not respond, so 404 handling was not judged.",
                     "re-run when the origin responds", detail="no response")]
    if status in (404, 410):
        return [_hyg("soft_404", "Missing pages return 404", "ok",
                     f"A URL that does not exist answers {status}, so search engines can drop it.",
                     "passing", detail=f"{status} on {probe}")]
    if hops:
        trail = " → ".join(str(h.get("status")) for h in chain)
        return [_hyg("soft_404", "Missing pages return 404", "error",
                     "A URL that does not exist redirects to a working page instead of answering 404. Search "
                     "engines keep the dead URL in the index and treat the destination as thin, duplicated content.",
                     "answer 404 (or 410) for unknown paths instead of redirecting them",
                     detail=f"{trail} then {status}")]
    return [_hyg("soft_404", "Missing pages return 404", "error",
                 f"A URL that does not exist answers {status} instead of 404, so every mistyped or stale link "
                 "looks like a real page to a search engine.",
                 "return a 404 status for unknown paths, with the error page as the body",
                 detail=f"{status} on {probe}")]


def _probe_cert(host: str, port: int = 443) -> dict:
    """{days, issuer, not_after} for the live certificate, or {error}."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=15) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert() or {}
    except Exception as exc:  # unreachable, refused, handshake failure
        return {"error": f"{type(exc).__name__}: {exc}"}
    raw = cert.get("notAfter")
    if not raw:
        return {"error": "the certificate carried no expiry date"}
    expires = datetime.strptime(raw, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    issuer = ""
    for part in cert.get("issuer", ()):
        for k, v in part:
            if k == "organizationName":
                issuer = v
    return {"days": (expires - datetime.now(timezone.utc)).days,
            "issuer": issuer, "not_after": expires.strftime("%Y-%m-%d %H:%M:%S")}


# Below this, a renewal that has not happened yet is worth saying out loud.
CERT_WARN_DAYS = 21


def ssl_rows(url: str, probe=None) -> list[dict]:
    """The live certificate's expiry. HTTP URLs get no verdict — `tech.https`
    already says the site is not on HTTPS, and a second row would say it twice."""
    scheme, host, _ = _origin(url)
    if scheme != "https":
        return []
    info = (probe or _probe_cert)(host.split(":")[0])
    if info.get("error"):
        return [_sec("ssl_expiry", "SSL certificate expiry", "info",
                     "The certificate could not be read, so its expiry date is unknown.",
                     "check the host is reachable on port 443", detail=info["error"][:160])]
    days, issuer, until = info.get("days", 0), info.get("issuer", ""), info.get("not_after", "")
    who = f" Issued by {issuer}." if issuer else ""
    if days < 0:
        return [_sec("ssl_expiry", "SSL certificate expiry", "error",
                     f"The certificate expired on {until}. Browsers show a full-page security warning before "
                     f"anyone reaches the site.{who}",
                     "renew the certificate now", detail=f"expired {abs(days)} day(s) ago")]
    if days < CERT_WARN_DAYS:
        return [_sec("ssl_expiry", "SSL certificate expiry", "warn",
                     f"The certificate expires on {until}, in {days} day(s). If renewal is manual, the site "
                     f"goes down behind a security warning when it lapses.{who}",
                     "renew it, and automate renewal if it is not already", detail=f"{days} day(s) left")]
    return [_sec("ssl_expiry", "SSL certificate expiry", "ok",
                 f"The certificate is valid until {until}, {days} day(s) away.{who}",
                 "passing", detail=f"{days} day(s) left")]
