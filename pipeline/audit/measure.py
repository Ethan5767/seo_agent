#!/usr/bin/env python3
"""Live-site measurement. Returns typed Findings instead of printing a summary.

Ported from audit_live.py: the same check logic, re-expressed as lib/baseline.py
Findings so plan.py (phase 3) can fingerprint them by content and partition them
into RESOLVED / PERSISTING / NEW / REGRESSION.

The split at check_page/check_url is the testable seam: check_page touches no
network and no filesystem, so the whole suite runs offline.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from pipeline.audit.providers import (crux_findings, dataforseo_findings,
                                      gsc_findings, serp_findings)
from pipeline.lib.baseline import Finding, assign_ordinals, sort_findings
from pipeline.lib.common import curl, curl_status, load_config

GATE = "site_health"
SCHEMA = "site-health/1"

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
    # No FAQPage check here on purpose (B-022). Google retired FAQ rich results on
    # 2026-05-07: they stopped appearing in Search that day, Rich Results Test and
    # the Search Console report went in June 2026, the API data in August. The
    # markup is still valid Schema.org and harmless to carry, but it can no longer
    # earn anything — so the finding was unfixable-by-value. A perfect site
    # collected one per page, every cycle, and the ratchet re-filed them as
    # PERSISTING forever. On lee it was 19 of 114 work items and, once that client
    # went to T3, real money spent writing markup for a dead feature.
    # `schema_business_missing` and `schema_breadcrumb_missing` both still back
    # live features and stay.
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
    #
    # `alt=""` is NOT missing alt text: it is the WCAG marker for a decorative
    # image, and flagging it inverts the standard. The old test was
    # `alt="[^"]+"`, which failed on the empty string — on leeserie.com that
    # emitted 1158 of 1272 findings (B-009), all of them false, and buried every
    # real one. Only an ABSENT alt attribute is a defect.
    for img in re.findall(r"<img[^>]*>", html):
        if not re.search(r"\salt=", img):
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


def urls_or_refuse(cfg: dict, url_args: list, limit: int | None) -> tuple:
    """(urls, exit_code) — discover_urls with its two failures already mapped
    onto the exit codes every caller reports: 19 nothing is measurable, 2 the
    input was not a sitemap. exit_code 0 means urls is usable.

    Shared because the mapping is the contract, not a detail: wf-seed-queries
    borrowed `discover_urls` bare and turned an unreachable sitemap — the most
    likely first-run failure — into a traceback and exit 1.
    """
    try:
        return discover_urls(cfg, url_args, limit), 0
    except Unreachable as e:
        print(f"[REFUSED] {e}", file=sys.stderr)
        return [], 19
    except UsageError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return [], 2


# ── the CLI ──────────────────────────────────────────────────────────────────

# Checks that cannot run without a config value. Skipping one silently is the
# failure mode where a green report means "not measured" rather than "fine", so
# every skip is named on stderr.
_CONFIG_GATED = (
    ("nap.phone_tel", "health.tel_link_missing", lambda c: (c.get("nap") or {}).get("phone_tel")),
    ("nap.phone", "health.phone_missing", lambda c: (c.get("nap") or {}).get("phone")),
    ("ga4_id", "health.ga4_missing", lambda c: c.get("ga4_id")),
    ("forbidden_phrases", "health.forbidden_phrase", lambda c: c.get("forbidden_phrases")),
)


def _warn_unmeasurable(cfg: dict) -> None:
    for key, code, get in _CONFIG_GATED:
        if not get(cfg):
            print(f"[WARN] {code} not measured: {key} is unset in docs/client-config.yml",
                  file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-site-health",
        description="Measure a live site and write typed findings for the ratchet.")
    ap.add_argument("--project", required=True, help="client repo root")
    ap.add_argument("--url", action="append", default=[], metavar="PATH",
                    help="measure exactly these URLs instead of the live sitemap")
    ap.add_argument("--limit", type=int, help="stop after N URLs")
    # Phase 6 providers. Off by default: two of the three need an account and one
    # of them costs money, so measuring with them is a decision, not a default.
    ap.add_argument("--with-crux", action="store_true",
                    help="field Core Web Vitals from CrUX (needs CRUX_API_KEY)")
    ap.add_argument("--with-gsc", action="store_true",
                    help="impressions, CTR and cannibalization (needs GSC_ACCESS_TOKEN)")
    ap.add_argument("--with-dataforseo", action="store_true",
                    help="crawl-wide broken pages, depth and duplicates (PAID; needs "
                         "DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD)")
    ap.add_argument("--max-crawl-pages", type=int, default=100,
                    help="DataForSEO crawl ceiling (billed per page)")
    ap.add_argument("--with-serp", action="store_true",
                    help="rank and absence for the config's seed_queries (PAID; "
                         "needs BRIGHTDATA_API_KEY / BRIGHTDATA_SERP_ZONE)")
    args = ap.parse_args()

    cfg = load_config(args.project)
    _warn_unmeasurable(cfg)

    urls, refused = urls_or_refuse(cfg, args.url, args.limit)
    if refused:
        return refused

    findings, checked, unreachable = [], 0, 0
    for url in urls:
        page_findings, reachable = check_url(url, cfg)
        if reachable:
            checked += 1
            findings.extend(page_findings)
        else:
            unreachable += 1
            print(f"[WARN] unreachable: {url}", file=sys.stderr)

    if checked == 0:
        print(f"[REFUSED] all {unreachable} URLs unreachable: nothing was measured, "
              f"so no findings file was written", file=sys.stderr)
        return 19

    # Providers run only after the HTTP pass proved the site is reachable. Their
    # status strings are written into the artifact: a provider that returned
    # nothing because it was never asked must not read as a provider that
    # returned nothing because the site is clean.
    providers: dict = {}
    if args.with_crux:
        # ponytail: origin-level only — one request instead of one per URL. CrUX
        # has no record for most individual pages on a small site anyway. Pass
        # `urls` here if per-page field CWV ever earns the request budget.
        found, providers["crux"] = crux_findings(cfg["domain"])
        findings.extend(found)
    if args.with_gsc:
        found, providers["gsc"] = gsc_findings(cfg["domain"], urls)
        findings.extend(found)
    if args.with_dataforseo:
        found, providers["dataforseo"] = dataforseo_findings(cfg["domain"],
                                                             max_pages=args.max_crawl_pages)
        findings.extend(found)
    if args.with_serp:
        found, providers["serp"] = serp_findings(cfg["domain"],
                                                 cfg.get("seed_queries"))
        findings.extend(found)
    for name, status in providers.items():
        print(f"[{name}] {status}", file=sys.stderr)

    out_dir = Path(args.project) / "docs" / "audit" / date.today().strftime("%Y-%m")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "findings.json"
    doc = {
        "schema": SCHEMA,
        "generated": date.today().isoformat(),
        "domain": cfg["domain"],
        "urls_checked": checked,
        "urls_unreachable": unreachable,
        # {} when no provider was asked for; a status string per provider that was.
        "providers": providers,
        # sort_findings + sorted keys: the artifact must be byte-identical across
        # two runs over an unchanged site, or every run produces a noise diff.
        "findings": [dict(f.to_json(), fingerprint=f.fingerprint)
                     for f in sort_findings(findings)],
    }
    out_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")

    print(f"[OK] {checked} URLs measured, {len(findings)} findings -> {out_path}")
    warn_dominant_code(findings)
    return 1 if findings else 0


# One check owning most of a report is the shape a false positive makes. B-009
# was exactly this: 91% of a run was a single broken regex, and nothing in the
# output said so — the operator read "1272 findings" as 1272 problems. This does
# not judge the check, it just refuses to let one code hide behind a total.
DOMINANCE_SHARE = 0.5


def warn_dominant_code(findings: list) -> None:
    if len(findings) < 20:            # too few for a share to mean anything
        return
    counts = {}
    for f in findings:
        counts[f.code] = counts.get(f.code, 0) + 1
    code, n = max(counts.items(), key=lambda kv: kv[1])
    if n / len(findings) >= DOMINANCE_SHARE:
        print(f"[WARN] {code} is {n}/{len(findings)} ({n / len(findings):.0%}) of this run. "
              f"One check carrying a report is how a false positive looks — verify it "
              f"against the live HTML before planning work from these numbers.",
              file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
