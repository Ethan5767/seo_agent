#!/usr/bin/env python3
"""Live-site measurement. Returns typed Findings instead of printing a summary.

Ported from audit_live.py: the same check logic, re-expressed as lib/baseline.py
Findings so plan.py (phase 3) can fingerprint them by content and partition them
into RESOLVED / PERSISTING / NEW / REGRESSION.

The split at check_page/check_url is the testable seam: check_page touches no
network and no filesystem, so the whole suite runs offline.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from pipeline.lib.baseline import Finding, assign_ordinals
from pipeline.lib.common import curl, curl_status

GATE = "site_health"

TITLE_MIN, TITLE_MAX = 30, 60
DESC_MIN, DESC_MAX = 120, 160
THIN_CONTENT_WORDS = 500


def check_page(url: str, html: str, status: int, cfg: dict) -> list:
    """Every check, against one already-fetched page. Pure.

    A check whose config input is unset is SKIPPED, not failed: the pipeline
    cannot measure what was never declared, and emitting the finding on every
    page would be a fabricated result. main() warns about each skip by name.
    """
    path = urlsplit(url).path or "/"
    out: list = []

    def add(code: str, context: str = "", detail: str = "") -> None:
        out.append(Finding(GATE, code, path, context=context, detail=detail))

    if status != 200:
        add("health.status_not_200", detail=f"status={status}")

    # title — missing and out-of-band are mutually exclusive
    t = re.search(r"<title[^>]*>([^<]+)</title>", html)
    title = t.group(1) if t else ""
    if not title:
        add("health.title_missing")
    elif not TITLE_MIN <= len(title) <= TITLE_MAX:
        add("health.title_length", detail=f"len={len(title)}")

    # meta description
    d = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html)
    desc = d.group(1) if d else ""
    if not desc:
        add("health.desc_missing")
    elif not DESC_MIN <= len(desc) <= DESC_MAX:
        add("health.desc_length", detail=f"len={len(desc)}")

    # h1 — count opening tags, which handles nested spans inside the h1
    h1s = re.findall(r"<h1[^>]*>", html)
    if len(h1s) != 1:
        add("health.h1_count", detail=f"count={len(h1s)}")

    # canonical — loose substring comparison, as audit_live.py did
    c = re.search(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"', html)
    if not (c and url.rstrip("/") in c.group(1)):
        add("health.canonical_mismatch", detail=c.group(1) if c else "absent")

    if "noindex" in html.lower():
        add("health.noindex_present")

    if not re.search(r'<meta[^>]*property="og:image"', html):
        add("health.og_image_missing")

    # schema
    types = set(re.findall(r'"@type":"([^"]+)"', html))
    required = cfg.get("schema_type") or "LocalBusiness"
    if required not in types:
        add("health.schema_business_missing", context=required,
            detail=f"found={','.join(sorted(types)) or 'none'}")
    if "FAQPage" not in types:
        add("health.schema_faq_missing")
    if "BreadcrumbList" not in types:
        add("health.schema_breadcrumb_missing")

    # forbidden phrases — strip <script> first (Next RSC flight payloads carry
    # $1 / $L8 tokens that false-positive the dollar rule), then priceRange
    # schema literals. Both strips are inherited from audit_live.py.
    body = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'"priceRange":"[^"]*"', "", body)
    for rule in cfg.get("forbidden_phrases") or []:
        hit = re.search(rule["pattern"], body)
        if hit:
            add("health.forbidden_phrase", context=rule["pattern"], detail=hit.group()[:80])

    nap = cfg.get("nap") or {}
    tel = nap.get("phone_tel")
    if tel and f"tel:{tel}" not in html:
        add("health.tel_link_missing")
    phone = nap.get("phone")
    if phone and phone not in html:
        add("health.phone_missing")

    ga4 = cfg.get("ga4_id")
    if ga4 and ga4 not in html:
        add("health.ga4_missing")

    # images — one finding per offending image, src as the stable identity.
    # A page with no images emits nothing.
    for img in re.findall(r"<img[^>]*>", html):
        if not re.search(r'\salt="[^"]+"', img):
            src = re.search(r'\ssrc="([^"]*)"', img)
            add("health.img_alt_missing", context=src.group(1) if src else img[:80])

    text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    words = len(text.split())
    if words < THIN_CONTENT_WORDS:
        add("health.thin_content", detail=f"words={words}")

    # Disambiguate repeated identical findings on one page, per baseline.py's
    # contract. Without this, two images sharing a src collapse to one fingerprint.
    return assign_ordinals(out)


# ── the network seam ─────────────────────────────────────────────────────────

class Unreachable(RuntimeError):
    """Every source failed. Exit 19 — a run that measured nothing must be red."""


class UsageError(RuntimeError):
    """Bad arguments, or a sitemap that answered but was not a sitemap. Exit 2."""


_LOC_RE = re.compile(r"<loc>\s*([^<\s][^<]*?)\s*</loc>")


def _absolute(u: str, domain: str) -> str:
    """Normalize one URL or site-relative path to an absolute, trailing-slash URL."""
    if u.startswith("http"):
        return u.rstrip("/") + "/"
    path = u.strip("/")
    return f"https://{domain}/{path}/" if path else f"https://{domain}/"


def check_url(url: str, cfg: dict) -> tuple:
    """Fetch one URL and check it. Returns (findings, reachable).

    status 0 is curl's connection-failure signal and means unreachable. A 404 is
    reachable — it is a real measurement, and it becomes a finding.
    """
    status = curl_status(url)
    if status == 0:
        return [], False
    return check_page(url, curl(url), status, cfg), True


def discover_urls(cfg: dict, url_args: list, limit: int | None = None) -> list:
    """Explicit --url arguments when given, otherwise every <loc> in the live
    sitemap. Deduped, order preserved, truncated to `limit`."""
    domain = cfg["domain"]
    if url_args:
        urls = [_absolute(u, domain) for u in url_args]
    else:
        xml = curl(f"https://{domain}/sitemap.xml", cache_bust=False)
        if not xml.strip():
            raise Unreachable(f"https://{domain}/sitemap.xml is unreachable "
                              f"and no --url was given: nothing to measure")
        locs = _LOC_RE.findall(xml)
        if not locs:
            raise UsageError(f"https://{domain}/sitemap.xml answered but contains "
                             f"no <loc> entries: not a sitemap")
        urls = [_absolute(u, domain) for u in locs]
    urls = list(dict.fromkeys(urls))
    return urls[:limit] if limit else urls
