"""Extra technical on-page checks — free, single-page, no engine dependency.

These are the SOP's page-level technical items that `measure.check_page` does
not cover: mobile viewport, lang, HTTPS, Open Graph / Twitter cards, favicon,
rendering (SSR vs CSR — is the content visible to crawlers at all), sitemap
presence, and a structured-data inventory. Pure: given the fetched HTML (+ the
sitemap text the server fetched), return report rows in the same shape as
audit.py, so the UI renders them identically. Every check shows pass or fail.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit


from pipeline.lib.common import visible_text_ratio  # canonical home; re-exported
from pipeline.scanner.rows import make_row

from pipeline.lib.html import sitemap_locs
_row = make_row("tech")


def _present(html: str, pattern: str) -> bool:
    return re.search(pattern, html, re.IGNORECASE) is not None


def tech_rows(url: str, html: str, status: int, sitemap: str | None,
              psi_doc: dict | None = None) -> list[dict]:
    rows: list[dict] = []

    # HTTPS
    if url.lower().startswith("https://"):
        rows.append(_row("HTTPS", "ok", "The page is served securely over HTTPS.", "passing"))
    else:
        rows.append(_row("HTTPS", "error",
                         "Google flags non-HTTPS pages as not secure and ranks them lower.",
                         "Serve the site over HTTPS with a valid certificate."))

    # Mobile viewport
    if _present(html, r'<meta[^>]*name=["\']viewport["\']'):
        rows.append(_row("Mobile viewport", "ok",
                         "A viewport meta tag is set — the page adapts to phones.", "passing"))
    else:
        rows.append(_row("Mobile viewport", "error",
                         "Without a viewport tag the page renders desktop-width on phones; Google uses mobile-first indexing.",
                         'Add <meta name="viewport" content="width=device-width, initial-scale=1">.'))

    # lang attribute
    if _present(html, r'<html[^>]*\blang='):
        rows.append(_row("Language declared", "ok",
                         "The <html lang> attribute helps search engines and screen readers.", "passing"))
    else:
        rows.append(_row("Language declared", "warn",
                         "No <html lang> — search engines and screen readers can't tell the page's language.",
                         'Add a lang attribute, e.g. <html lang="en">.'))

    # Open Graph completeness
    og = [t for t in ("og:title", "og:description", "og:image")
          if _present(html, rf'property=["\']{t}["\']')]
    if len(og) == 3:
        rows.append(_row("Open Graph tags", "ok",
                         "og:title, og:description and og:image are all set — clean link previews.", "passing"))
    else:
        missing = [t for t in ("og:title", "og:description", "og:image") if t not in og]
        rows.append(_row("Open Graph tags", "warn",
                         "Incomplete Open Graph tags make shared links look broken on social and chat.",
                         f"Add the missing tag(s): {', '.join(missing)}.", detail=f"missing {len(missing)}"))

    # Twitter card
    if _present(html, r'name=["\']twitter:card["\']'):
        rows.append(_row("Twitter/X card", "ok", "A twitter:card tag is set for rich previews on X.", "passing"))
    else:
        rows.append(_row("Twitter/X card", "warn",
                         "No twitter:card — links shared on X show a plain URL, not a rich card.",
                         'Add <meta name="twitter:card" content="summary_large_image">.'))

    # Favicon
    if _present(html, r'<link[^>]*rel=["\'][^"\']*icon'):
        rows.append(_row("Favicon", "ok", "A favicon is declared.", "passing"))
    else:
        rows.append(_row("Favicon", "warn", "No favicon — the browser tab and results show a blank icon.",
                         'Add <link rel="icon" href="/favicon.ico">.'))

    # Rendering: SSR vs CSR (Hybrid Tier B + Tier C)
    words, ratio = visible_text_ratio(html)
    raw_elements = len(re.findall(r'<[a-zA-Z0-9]+', html))
    raw_links = len(re.findall(r'<a\b[^>]*\bhref=', html, re.IGNORECASE))

    # Tier B: Measured against Google Lighthouse rendered DOM when available
    lr = (psi_doc or {}).get("lighthouseResult") or {}
    audits = lr.get("audits") or {}
    dom_val = (audits.get("dom-size-insight", {}).get("numericValue")
               or audits.get("dom-size", {}).get("numericValue"))
    link_audit = audits.get("link-text") or {}
    link_items = (link_audit.get("details") or {}).get("items")
    rendered_links = len(link_items) if isinstance(link_items, list) else 0

    # PageSpeed does not expose the full rendered text node count, but it does
    # expose every link Lighthouse inspected.  That makes links the only direct
    # raw-vs-rendered content count available without adding a browser.  Do not
    # promote an element-count proxy to a confirmed content gap.
    if dom_val is not None and isinstance(link_items, list):
        dom_elements = int(dom_val)
        added_link_share = ((rendered_links - raw_links) / rendered_links
                            if rendered_links else 0)
        has_measured_gap = rendered_links > raw_links and added_link_share > 0.5
        if has_measured_gap:
            rows.append(_row(
                "Rendering (crawler-visible content)", "error",
                f"Google PageSpeed rendered {rendered_links} links in headless Chrome, but raw HTML contains only "
                f"{raw_links} ({added_link_share:.0%} added by JavaScript). The rendered DOM has {dom_elements} "
                f"elements while the raw response has {raw_elements} and {words} words. Essential links are generated "
                "via JavaScript, making them invisible to raw HTML crawlers.",
                "Pre-render or server-side render (SSR/SSG) the page so raw HTML crawlers receive complete content.",
                detail="confirmed content gap — measured"
            ))
        else:
            rows.append(_row(
                "Rendering (crawler-visible content)", "ok",
                "The content is present in raw HTML and matches the rendered DOM — crawlers can read it without executing JavaScript.",
                "passing", detail=f"{words} words"
            ))
    else:
        # Tier C: Heuristic empty-shell detection on raw HTML
        spa_patterns = [
            r'<div[^>]*\bid=["\'](root|app|__next)["\'][^>]*>\s*</div>',
            r'<div[^>]*\bid=["\'](root|app|__next)["\'][^>]*>\s*<!--.*?-->\s*</div>',
            r'<main[^>]*\bid=["\'](root|app)["\'][^>]*>\s*</main>',
        ]
        is_spa_shell = any(re.search(p, html, re.IGNORECASE | re.DOTALL) for p in spa_patterns)
        has_scripts = bool(re.search(r'<script\b', html, re.IGNORECASE))
        has_noscript_warning = bool(re.search(r'<noscript\b[^>]*>.*?(enable|javascript|browser).*?</noscript>',
                                               html, re.IGNORECASE | re.DOTALL))
        is_csr_heuristic = has_scripts and words < 100 and (is_spa_shell or has_noscript_warning)

        if is_csr_heuristic:
            sev = "warn" if (words >= 30 and not is_spa_shell) else "error"
            rows.append(_row(
                "Rendering (crawler-visible content)", sev,
                f"The raw HTML contains only {words} words and matches an empty client-side application shell. "
                "Search and AI crawlers that do not execute JavaScript will see a blank or minimal page.",
                "Serve the content server-side (SSR/SSG) so it is present in the HTML on first load.",
                detail="likely CSR shell — heuristic"
            ))
        else:
            rows.append(_row(
                "Rendering (crawler-visible content)", "ok",
                "The content is present in the raw HTML — crawlers and AI bots can read it on first load.",
                "passing", detail=f"{words} words"
            ))

    # Sitemap
    # Counted through the shared parser, not by counting opening tags: an empty
    # `<loc></loc>` names no URL, and a sitemap of ten of them reported "10 URLs
    # so crawlers can find every page" over a sitemap that lists nothing.
    sitemap_urls = sitemap_locs(sitemap)
    if sitemap_urls:
        n = len(sitemap_urls)
        rows.append(_row("XML sitemap", "ok", f"A sitemap.xml is served ({n} URLs) so crawlers can find every page.",
                         "passing", detail=f"{n} URLs"))
    else:
        rows.append(_row("XML sitemap", "warn",
                         "No sitemap.xml found — crawlers may miss pages that aren't well linked.",
                         "Publish /sitemap.xml listing every indexable URL."))

    # Structured-data inventory (informational — what schema exists)
    types = sorted(set(re.findall(r'"@type"\s*:\s*"([^"]+)"', html)))
    if types:
        rows.append(_row("Structured data found", "ok",
                         f"Schema types present: {', '.join(types)}.", "passing",
                         detail=", ".join(types)))
    else:
        rows.append(_row("Structured data found", "warn",
                         "No structured data (JSON-LD) at all — search and AI engines get no machine-readable facts.",
                         "Add relevant schema.org JSON-LD (LocalBusiness, Breadcrumb, etc.)."))

    return rows


# ── Video snippets (SOP Measure: video/multimedia audit) — a DataForSEO gap ──

_VIDEO_ID = re.compile(
    r"(?:youtube\.com/embed/|youtu\.be/|youtube\.com/watch\?v=)([A-Za-z0-9_-]{6,})",
    re.IGNORECASE)


def find_video_ids(html: str) -> list[str]:
    """Embedded YouTube video ids on the page (dedup, order preserved)."""
    seen = []
    for vid in _VIDEO_ID.findall(html or ""):
        if vid not in seen:
            seen.append(vid)
    return seen


#: These rows belong to the VIDEO tool, not to Technical. The module-level
#: `_row` above is bound to "tech" because most of this file is technical
#: checks, and `video_rows` inherited that prefix purely by living here.
#:
#: B-093: the consequence was invisible in the only case anyone tested. A page
#: with NO video never reaches this function - `youtube.video_rows_full` answers
#: that case with its own `video.`-stamped row and returns before calling in. The
#: moment a page actually HAD a video the row arrived as `tech.video_snippets`,
#: and two things silently stopped working:
#:
#:   * the Video report view filters on `video.`, so it showed only the metadata
#:     row - or nothing at all when there was no API key - and printed "Run a
#:     scan" over a scan that had already run;
#:   * `recommendations.py` keys this finding as `video.video_snippets`, with a
#:     comment stating that prefix, so its remediation never fired.
#:
#: The one case the tool exists for was the broken one.
_video_row = make_row("video")


def video_rows(html: str) -> list[dict]:
    """One row: are embedded videos backed by VideoObject schema (rich-snippet
    eligible)? No video = nothing to optimise (pass)."""
    ids = find_video_ids(html)
    has_native = "<video" in (html or "").lower()
    if not ids and not has_native:
        return [_video_row("Video snippets", "ok",
                     "No embedded video on this page — nothing to optimise.", "passing")]
    has_schema = '"@type":"VideoObject"' in (html or "").replace(" ", "").replace("'", '"')
    n = len(ids) or 1
    if has_schema:
        return [_video_row("Video snippets", "ok",
                     f"{n} video(s) with VideoObject schema — eligible for rich video results and AI citation.",
                     "passing", detail=f"{n} video(s)")]
    return [_video_row("Video snippets", "warn",
                 f"{n} embedded video(s) but no VideoObject schema — Google/AI can't show a rich video snippet.",
                 "add VideoObject JSON-LD (name, description, thumbnailUrl, uploadDate, duration) per video",
                 detail=f"{n} video(s)")]


#: Local signals we can read from the page itself, for free, on every scan.
#:
#: B-096 removed four directory tiles that claimed "Synced" for Apple Maps, Bing
#: Places, Waze and YellowPages - none of which publishes a read API, so no tool
#: can verify them at any price. Removing a lie leaves a gap, and the honest way
#: to fill it is with signals that ARE readable: the page is already fetched, so
#: these cost nothing and need no credential.
#:
#: They are deliberately about the SITE, not about a directory listing. What a
#: third-party directory says is between the client and that directory; what the
#: client's own page says is ours to check and ours to fix.
_local_row = make_row("local")

_MAPS_EMBED_RE = re.compile(
    r"<iframe[^>]+src=[\"'][^\"']*(?:google\.[a-z.]+/maps/embed|maps\.google\.[a-z.]+)", re.IGNORECASE)
_TEL_RE = re.compile(r'href=[\"\']tel:([^\"\']+)', re.IGNORECASE)
_POSTAL_RE = re.compile(r'"@type"\s*:\s*"PostalAddress"', re.IGNORECASE)
_GEO_RE = re.compile(r'"@type"\s*:\s*"GeoCoordinates"', re.IGNORECASE)
_OPENING_RE = re.compile(r'"openingHours(?:Specification)?"\s*:', re.IGNORECASE)


def local_rows(html: str) -> list[dict]:
    """Local-intent signals on the page. Free, and true of the page we fetched.

    Every row is derived from the HTML in hand. Nothing here asks a directory
    what it thinks, because four of the six directories this product used to
    display cannot be asked.
    """
    h = html or ""
    rows: list[dict] = []

    has_map = _MAPS_EMBED_RE.search(h) is not None
    rows.append(_local_row(
        "Google Maps embed", "ok" if has_map else "warn",
        "A Google Maps embed is on the page, which confirms a physical location and gives visitors directions."
        if has_map else
        "No Google Maps embed found. A map is the clearest signal to a visitor - and to Google - that this is a real place.",
        "passing" if has_map else "embed the Google Maps iframe for the business location on the contact page"))

    tel = _TEL_RE.search(h)
    rows.append(_local_row(
        "Click-to-call link", "ok" if tel else "warn",
        "A tel: link is present, so a phone tap dials directly." if tel else
        "No tel: link. A phone number that is only text cannot be tapped to dial on a phone, which is where most local searches happen.",
        "passing" if tel else "wrap the phone number in a tel: link",
        detail=(tel.group(1).strip()[:40] if tel else "")))

    has_addr = _POSTAL_RE.search(h) is not None
    rows.append(_local_row(
        "Address in structured data", "ok" if has_addr else "warn",
        "A PostalAddress is declared in JSON-LD, so search engines can read the address as an address rather than guessing at text."
        if has_addr else
        "No PostalAddress in the page's structured data. Search engines have to infer the address from prose, which they often get wrong.",
        "passing" if has_addr else "add a PostalAddress to the LocalBusiness JSON-LD"))

    has_geo = _GEO_RE.search(h) is not None
    rows.append(_local_row(
        "Geo coordinates", "ok" if has_geo else "info",
        "GeoCoordinates are declared, which is what 'near me' matching reads."
        if has_geo else
        "No GeoCoordinates in the structured data. Optional, but it is the most direct input to 'near me' proximity matching.",
        "passing" if has_geo else "add GeoCoordinates (latitude, longitude) to the LocalBusiness JSON-LD"))

    has_hours = _OPENING_RE.search(h) is not None
    rows.append(_local_row(
        "Opening hours", "ok" if has_hours else "warn",
        "Opening hours are declared in structured data, so Google can show open/closed state in results."
        if has_hours else
        "No opening hours in structured data. Google cannot show an open/closed state, which is what a local searcher is usually checking.",
        "passing" if has_hours else "add openingHoursSpecification to the LocalBusiness JSON-LD"))

    return rows


# ── Internal link structure (SOP Measure) — page-level anchor quality ────────

_A_FULL = re.compile(r'<a\b([^>]*)>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_HREF = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_REL = re.compile(r'rel=["\']([^"\']*)["\']', re.IGNORECASE)
_MAIN = re.compile(r'<(main|article)\b[^>]*>.*?</\1>', re.IGNORECASE | re.DOTALL)
_IMG = re.compile(r'<img\b[^>]*>', re.IGNORECASE)
_IMG_ALT = re.compile(r'\balt=["\'][^"\']+["\']', re.IGNORECASE)  # non-empty alt
_GENERIC_ANCHORS = {"click here", "read more", "here", "learn more", "more",
                    "this", "read", "link", "click", "see more", "go", "next", "continue"}


def internal_link_rows(url: str, html: str) -> list[dict]:
    """Page-level internal-link health: count, anchor quality, whether links sit
    in the main content vs boilerplate nav, nofollow waste, exact-match
    over-optimisation, outbound-authority leak and image-link context. Site-wide
    structure (orphans, broken links) is DataForSEO Site Health's job — this is
    the single-page view."""
    html = html or ""
    host = urlsplit(url).netloc
    here = (urlsplit(url).path or "/").rstrip("/") or "/"
    content_spans = [(m.start(), m.end()) for m in _MAIN.finditer(html)]

    def in_content(pos):
        return any(s <= pos <= e for s, e in content_spans)

    internal = external = nofollow = self_ref = in_content_n = img_no_alt = 0
    generic, descriptive, exact = [], 0, {}
    for m in _A_FULL.finditer(html):
        attrs, inner = m.group(1), m.group(2)
        href_m = _HREF.search(attrs)
        if not href_m:
            continue
        href = href_m.group(1).strip()
        if href.startswith(("mailto:", "tel:", "#", "javascript:", "data:")):
            continue
        is_internal = href.startswith("/") or (host and host in href) or not href.startswith("http")
        if not is_internal:
            external += 1
            continue
        internal += 1
        if in_content(m.start()):
            in_content_n += 1
        rel = (_REL.search(attrs).group(1).lower() if _REL.search(attrs) else "")
        if "nofollow" in rel:
            nofollow += 1
        if (urlsplit(href).path or "/").rstrip("/") == here or href in ("/", "", here):
            self_ref += 1
        text = re.sub(r"<[^>]+>", "", inner).strip().lower()
        if not text:
            imgs = _IMG.findall(inner)
            if imgs and not any(_IMG_ALT.search(i) for i in imgs):
                img_no_alt += 1
            generic.append("(image)" if imgs else "(empty)")
        elif text in _GENERIC_ANCHORS or text.startswith("http"):
            generic.append(text)
        else:
            if len(text.split()) >= 2:
                descriptive += 1
            exact[text] = exact.get(text, 0) + 1

    rows = []
    # 1. count — dead end, healthy, or bloated
    if not internal:
        rows.append(_row("Internal links", "warn",
                         "No internal links on this page — a dead end for crawlers and authority.",
                         "add contextual links to related pages", detail="0 links"))
    else:
        too_many = internal > 150
        rows.append(_row("Internal links", "warn" if too_many else "ok",
                         f"{internal} internal link(s) — excessive linking dilutes authority per link." if too_many
                         else f"{internal} internal link(s) — they spread ranking authority and guide crawlers.",
                         "trim to the meaningful links" if too_many else "passing", detail=f"{internal} links"))
    # 2. anchor text quality
    if generic:
        rows.append(_row("Anchor text quality", "warn",
                         f"{len(generic)} non-descriptive anchor(s) (click here / empty / image / naked URL) — they carry no keyword signal.",
                         "use descriptive anchor text naming the target page's topic", detail=f"{len(generic)} weak"))
    # 3. contextual (in-content) links vs boilerplate — only when a main/article exists
    if content_spans and internal:
        rows.append(_row("Contextual links", "ok" if in_content_n else "warn",
                         f"{in_content_n} internal link(s) sit inside the main content — contextual links carry more weight than nav." if in_content_n
                         else "Every internal link is in nav/footer boilerplate — none in the main content.",
                         "passing" if in_content_n else "add in-content links from the body copy to related pages",
                         detail=f"{in_content_n} in content"))
    # 4. descriptive ratio
    if internal >= 5:
        ratio = descriptive / internal
        if ratio < 0.5:
            rows.append(_row("Descriptive anchors", "warn",
                             f"Only {round(ratio * 100)}% of internal links use descriptive (multi-word) anchors.",
                             "write anchors that name the target page's topic", detail=f"{round(ratio * 100)}%"))
    # 5. exact-match over-optimisation
    spammy = [(t, n) for t, n in exact.items() if n >= 6]
    if spammy:
        t, n = max(spammy, key=lambda x: x[1])
        rows.append(_row("Anchor over-optimization", "warn",
                         f'The exact anchor "{t}" is repeated {n} times — looks manipulative to Google.',
                         "vary anchor text naturally", detail=f'"{t}" ×{n}'))
    # 6. nofollow on internal links
    if nofollow:
        rows.append(_row("Nofollow internal links", "warn",
                         f"{nofollow} internal link(s) are rel=nofollow — that wastes crawl budget and blocks authority flow.",
                         "remove nofollow from internal links", detail=f"{nofollow} nofollow"))
    # 7. self-referencing
    if self_ref >= 3:
        rows.append(_row("Self-referencing links", "info",
                         f"{self_ref} link(s) point back to this same page — redundant, minor crawl waste.",
                         "link to other pages instead", detail=f"{self_ref}"))
    # 8. outbound authority leak
    if internal and external > internal:
        rows.append(_row("Outbound links", "warn",
                         f"{external} external vs {internal} internal link(s) — more links leave the site than stay, leaking authority.",
                         "add more internal links or trim external ones", detail=f"{external} ext / {internal} int"))
    # 9. image-link context
    if img_no_alt:
        rows.append(_row("Image link context", "warn",
                         f"{img_no_alt} image link(s) have no alt/anchor text — Google gets no context for where they go.",
                         "add descriptive alt text to linked images", detail=f"{img_no_alt}"))
    return rows
