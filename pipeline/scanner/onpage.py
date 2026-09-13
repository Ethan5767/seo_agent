"""Deep single-page on-page checks — pure, offline, free.

The 28 checks `Measure_Checks.docx` specifies under "Our on-page deep (single
page) — onpage.py". The module did not exist: the spec listed it, `MODULES.md`
counted it, and nothing had been written, so URL structure, DOM weight,
pagination hygiene and mixed content were measured by nothing at all.

Scope discipline, because this module sits next to three others that could each
claim the same ground:

  * `audit.seo_rows`      — the universal checklist (title, description, H1,
                            canonical, indexability). Presence and correctness.
  * `extra_checks`        — site-level technical posture (HTTPS, viewport,
                            sitemap, rendering).
  * `onpage_audit`        — DataForSEO's site-wide crawl. Paid, many pages.
  * **this module**       — everything else you can see in ONE page's HTML and
                            its URL, that the others do not already judge.

So there is deliberately no title-length or H1-count check here: `seo_rows`
owns those, and two checks over one fact is how a finding comes to wear two
names (B-049).

Every check reads only `url` and `html`. No network, no config, no clock, which
is what makes the whole module testable from a string.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from pipeline.scanner.rows import make_row

_row = make_row("onpage")

# ── thresholds, named so a reader can argue with them ───────────────────────
#: Google's own guidance is that shorter URLs are not a ranking factor; long
#: ones are a usability and truncation problem, so this is generous.
URL_MAX_LEN = 115
#: Lighthouse warns above 1,500 nodes and errors above 3,000.
DOM_WARN_NODES = 1500
DOM_ERROR_NODES = 3000
#: Above this, a page is a link farm to a crawler and a maze to a reader.
LINK_WARN_COUNT = 150
#: Chrome's own agentic-browsing audits flag heavy iframe use.
IFRAME_WARN_COUNT = 5
#: Left-in filler that reached production. Matched case-insensitively, word-ish.
PLACEHOLDER_RE = re.compile(
    r"\b(lorem ipsum|dolor sit amet|insert (?:text|copy|content) here"
    r"|your (?:text|copy|company name) here|tbd|todo|coming soon"
    r"|placeholder text|xxx+)\b", re.IGNORECASE)
#: Elements HTML5 dropped. `<center>`/`<font>` still render, which is why they
#: survive in templates nobody has touched since 2011.
DEPRECATED_TAGS = ("center", "font", "marquee", "blink", "big", "strike",
                   "tt", "frameset", "frame", "applet", "acronym")


def _tags(html: str, name: str) -> list[str]:
    return re.findall(rf"<{name}\b[^>]*>", html or "", re.IGNORECASE)


def _count(html: str, name: str) -> int:
    return len(_tags(html, name))


def _head(html: str) -> str:
    """The <head>, or the whole document when it has none.

    A page with no <head> element still carries meta tags, and judging them
    against an empty string would report every one of them missing. Use
    `_strict_head` instead wherever the check is about a tag's POSITION rather
    than its presence: this fallback made a `<script>` at the end of <body>
    count as render-blocking, which is the opposite of the truth.
    """
    return _strict_head(html) if _strict_head(html) is not None else (html or "")


def _strict_head(html: str) -> str | None:
    """The <head> contents, or None when the document has no <head> element."""
    m = re.search(r"<head\b[^>]*>(.*?)</head>", html or "", re.S | re.I)
    return m.group(1) if m else None


# ── 1-4, 20-21, 27-28: head hygiene ─────────────────────────────────────────

def _head_rows(html: str) -> list[dict]:
    head, rows = _head(html), []

    charset = re.search(r'<meta[^>]+charset=', head, re.I)
    rows.append(_row("Charset", "ok" if charset else "warn",
                     "A character encoding is declared, so browsers do not have to guess it."
                     if charset else
                     "No charset declared. Browsers guess the encoding, and a wrong guess garbles the text.",
                     "passing" if charset else 'add <meta charset="utf-8"> as the first thing in <head>'))

    doctype = re.match(r"\s*<!doctype\s+html\s*>", html or "", re.I)
    rows.append(_row("Doctype", "ok" if doctype else "warn",
                     "An HTML5 doctype is declared."
                     if doctype else
                     "No HTML5 doctype at the top of the document, which puts browsers into quirks mode.",
                     "passing" if doctype else "add <!doctype html> as the very first line"))

    n_title = _count(head, "title")
    rows.append(_row("Single title", "ok" if n_title == 1 else "warn",
                     "Exactly one <title>." if n_title == 1 else
                     f"{n_title} <title> tags. Search engines pick one and it may not be yours.",
                     "passing" if n_title == 1 else "keep exactly one <title>",
                     detail=f"{n_title} found"))

    descs = [t for t in _tags(head, "meta") if re.search(r'name=["\']?description', t, re.I)]
    rows.append(_row("Single meta description", "ok" if len(descs) == 1 else "warn",
                     "Exactly one meta description." if len(descs) == 1 else
                     f"{len(descs)} meta descriptions. Google will choose, or write its own.",
                     "passing" if len(descs) == 1 else "keep exactly one meta description",
                     detail=f"{len(descs)} found"))

    canons = [t for t in _tags(head, "link") if re.search(r'rel=["\']?canonical', t, re.I)]
    rows.append(_row("Single canonical", "ok" if len(canons) <= 1 else "error",
                     "One canonical, or none." if len(canons) <= 1 else
                     f"{len(canons)} canonical tags. Conflicting canonicals are ignored outright, so the page has none.",
                     "passing" if len(canons) <= 1 else "keep exactly one canonical",
                     detail=f"{len(canons)} found"))

    refresh = [t for t in _tags(head, "meta") if re.search(r'http-equiv=["\']?refresh', t, re.I)]
    rows.append(_row("Meta refresh", "ok" if not refresh else "warn",
                     "No meta refresh redirect." if not refresh else
                     "A meta refresh redirect. Search engines treat it as a weak signal and it hijacks the back button.",
                     "passing" if not refresh else "use a 301 redirect at the server instead"))

    keywords = [t for t in _tags(head, "meta") if re.search(r'name=["\']?keywords', t, re.I)]
    rows.append(_row("Legacy meta keywords", "ok" if not keywords else "info",
                     "No meta keywords tag, which no search engine has used for over a decade."
                     if not keywords else
                     "A meta keywords tag is present. Harmless, but it tells competitors what you are targeting.",
                     "passing" if not keywords else "remove it; nothing reads it"))

    touch = re.search(r'rel=["\']?apple-touch-icon', head, re.I)
    rows.append(_row("Apple touch icon", "ok" if touch else "info",
                     "An apple-touch-icon is declared for home-screen bookmarks."
                     if touch else
                     "No apple-touch-icon. A page saved to an iOS home screen gets a blurred screenshot instead of a logo.",
                     "passing" if touch else 'add <link rel="apple-touch-icon" href="/apple-touch-icon.png">'))
    return rows


# ── 14-17: the URL itself ───────────────────────────────────────────────────

def _url_rows(url: str) -> list[dict]:
    parts = urlsplit(url or "")
    path, rows = parts.path or "/", []

    rows.append(_row("URL length", "ok" if len(url or "") <= URL_MAX_LEN else "info",
                     f"URL is {len(url or '')} characters."
                     + ("" if len(url or "") <= URL_MAX_LEN else
                        " Long URLs get truncated in results and are hard to share."),
                     "passing" if len(url or "") <= URL_MAX_LEN else "shorten the path",
                     detail=f"{len(url or '')} chars"))

    under = "_" in path
    rows.append(_row("URL underscores", "ok" if not under else "info",
                     "The path uses hyphens rather than underscores." if not under else
                     "Underscores in the path. Google treats a hyphen as a word separator and an underscore as a joiner.",
                     "passing" if not under else "use hyphens between words"))

    upper = any(c.isupper() for c in path)
    rows.append(_row("URL case", "ok" if not upper else "warn",
                     "The path is lowercase." if not upper else
                     "Uppercase letters in the path. Paths are case-sensitive, so /About and /about are two pages that can split signals.",
                     "passing" if not upper else "serve lowercase paths and redirect the mixed-case form"))

    params = parse_qs(parts.query)
    rows.append(_row("URL parameters", "ok" if len(params) <= 2 else "warn",
                     "No parameter sprawl in the URL." if len(params) <= 2 else
                     f"{len(params)} query parameters. Each one multiplies the URLs a crawler has to treat as distinct.",
                     "passing" if len(params) <= 2 else "canonicalise the parameter forms to one URL",
                     detail=", ".join(sorted(params)) if params else ""))
    return rows


# ── 5-13, 18-19, 22-26: the body ────────────────────────────────────────────

def _body_rows(url: str, html: str) -> list[dict]:
    h, rows = html or "", []
    https_page = (urlsplit(url or "").scheme == "https")

    # 5. Mixed content — only a defect on an HTTPS page.
    insecure = re.findall(r'(?:src|href)=["\']http://[^"\']+', h, re.I)
    if https_page:
        rows.append(_row("Mixed content", "ok" if not insecure else "error",
                         "Every subresource is loaded over HTTPS." if not insecure else
                         f"{len(insecure)} resource(s) loaded over plain HTTP on an HTTPS page. Browsers block or downgrade these, so the page renders incomplete.",
                         "passing" if not insecure else "serve every resource over https://",
                         detail=f"{len(insecure)} resource(s)" if insecure else ""))
    else:
        rows.append(_row("Mixed content", "info",
                         "The page itself is not served over HTTPS, so mixed content does not apply yet.",
                         "serve the page over HTTPS first"))

    # 6. External link safety — target=_blank without noopener.
    blanks = [a for a in _tags(h, "a") if re.search(r'target=["\']?_blank', a, re.I)]
    unsafe = [a for a in blanks if not re.search(r"noopener|noreferrer", a, re.I)]
    rows.append(_row("External link safety", "ok" if not unsafe else "warn",
                     "Every new-tab link carries rel=noopener." if not unsafe else
                     f"{len(unsafe)} link(s) open a new tab without rel=\"noopener\", which lets the opened page script this one.",
                     "passing" if not unsafe else 'add rel="noopener noreferrer" to target="_blank" links',
                     detail=f"{len(unsafe)} of {len(blanks)}" if blanks else ""))

    # 7. Render-blocking scripts — in <head>, no async/defer. Position is the
    # whole point, so this uses the STRICT head: no <head> element means no
    # head-blocking scripts, and a tag at the end of <body> is not one.
    head = _strict_head(h) or ""
    blocking = [s for s in re.findall(r"<script\b[^>]*>", head, re.I)
                if re.search(r"\bsrc=", s, re.I) and not re.search(r"\b(async|defer|type=[\"']module)", s, re.I)]
    rows.append(_row("Render-blocking scripts", "ok" if not blocking else "warn",
                     "No blocking scripts in <head>." if not blocking else
                     f"{len(blocking)} script(s) in <head> with neither async nor defer. The browser stops parsing until each one downloads.",
                     "passing" if not blocking else "add defer, or move the tag to the end of <body>",
                     detail=f"{len(blocking)} script(s)" if blocking else ""))

    # 8. Image dimensions — width/height prevent layout shift.
    imgs = _tags(h, "img")
    sized = [i for i in imgs if re.search(r"\bwidth=", i, re.I) and re.search(r"\bheight=", i, re.I)]
    if imgs:
        missing = len(imgs) - len(sized)
        rows.append(_row("Image dimensions", "ok" if not missing else "warn",
                         "Every image declares width and height, so nothing shifts as they load."
                         if not missing else
                         f"{missing} of {len(imgs)} images have no width/height. The page reflows as each one arrives, which is what Cumulative Layout Shift measures.",
                         "passing" if not missing else "set width and height on every <img>",
                         detail=f"{missing} of {len(imgs)}" if missing else f"{len(imgs)} images"))
    else:
        rows.append(_row("Image dimensions", "info", "No images on the page.", "no action needed"))

    # 9. Deprecated HTML.
    found = sorted({t for t in DEPRECATED_TAGS if _count(h, t)})
    rows.append(_row("Deprecated HTML", "ok" if not found else "warn",
                     "No deprecated HTML elements." if not found else
                     f"Deprecated elements still in the markup: {', '.join(found)}. They render, but they signal a template nobody has revisited.",
                     "passing" if not found else "replace them with CSS and semantic elements",
                     detail=", ".join(found)))

    # 10. DOM size.
    nodes = len(re.findall(r"<[a-zA-Z][^>]*>", h))
    sev = "error" if nodes > DOM_ERROR_NODES else "warn" if nodes > DOM_WARN_NODES else "ok"
    rows.append(_row("DOM size", sev,
                     f"About {nodes} elements."
                     + ("" if sev == "ok" else
                        " A large DOM costs memory, slows style recalculation and is a direct Core Web Vitals drag."),
                     "passing" if sev == "ok" else "flatten the markup and paginate long lists",
                     detail=f"~{nodes} elements"))

    # 11. Link volume.
    links = _count(h, "a")
    rows.append(_row("Link volume", "ok" if links <= LINK_WARN_COUNT else "warn",
                     f"{links} links on the page."
                     + ("" if links <= LINK_WARN_COUNT else
                        " Past roughly this many, each link passes less weight and the page reads as a directory."),
                     "passing" if links <= LINK_WARN_COUNT else "cut the navigation and footer link count",
                     detail=f"{links} links"))

    # 12. hreflang — self-reference is the commonest omission.
    tags = [t for t in _tags(_head(h), "link") if re.search(r"hreflang=", t, re.I)]
    if not tags:
        rows.append(_row("hreflang", "info",
                         "No hreflang tags. Only needed if the site serves more than one language or region.",
                         "no action needed for a single-locale site"))
    else:
        langs = [re.search(r'hreflang=["\']?([\w-]+)', t, re.I).group(1).lower() for t in tags]
        has_self = any(re.search(re.escape(url or ""), t) for t in tags) if url else False
        rows.append(_row("hreflang", "ok" if has_self else "warn",
                         f"{len(tags)} hreflang tags, including a self-reference."
                         if has_self else
                         f"{len(tags)} hreflang tags but none points back at this URL. Google requires the set to be self-referential or it ignores the whole set.",
                         "passing" if has_self else "add an hreflang entry for this page's own URL",
                         detail=", ".join(sorted(set(langs)))[:60]))

    # 13. Semantic <main>.
    n_main = _count(h, "main")
    rows.append(_row("Semantic main", "ok" if n_main == 1 else "warn",
                     "Exactly one <main>, so the primary content is machine-identifiable."
                     if n_main == 1 else
                     ("No <main> element. Crawlers, screen readers and answer engines have to infer where the content is."
                      if n_main == 0 else f"{n_main} <main> elements; there must be exactly one."),
                     "passing" if n_main == 1 else "wrap the primary content in a single <main>",
                     detail=f"{n_main} found"))

    # 18. Subheadings.
    h2 = _count(h, "h2")
    rows.append(_row("Subheadings", "ok" if h2 >= 2 else "warn",
                     f"{h2} <h2> sections." if h2 >= 2 else
                     f"{h2} <h2> heading(s). Without subheadings the page is one block, which is hard to skim and hard for an answer engine to lift a section from.",
                     "passing" if h2 >= 2 else "break the content into titled sections",
                     detail=f"{h2} h2"))

    # 19. Heading order — a level skipped on the way down.
    levels = [int(m) for m in re.findall(r"<h([1-6])\b", h, re.I)]
    # Adjacent pairs; the second list is short by one by design.
    skips = [(a, b) for a, b in zip(levels, levels[1:], strict=False) if b > a + 1]
    rows.append(_row("Heading order", "ok" if not skips else "warn",
                     "Heading levels descend without skipping." if not skips else
                     f"{len(skips)} place(s) where a heading level is skipped, e.g. h{skips[0][0]} straight to h{skips[0][1]}. Screen readers announce the outline, and a gap reads as a missing section.",
                     "passing" if not skips else "descend one level at a time",
                     detail=f"{len(skips)} skip(s)" if skips else ""))

    # 22. Placeholder text left in.
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", h, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    hits = sorted({m.group(0).lower() for m in PLACEHOLDER_RE.finditer(text)})
    rows.append(_row("Placeholder text", "ok" if not hits else "error",
                     "No placeholder or filler text in the copy." if not hits else
                     f"Filler text is live on the page: {', '.join(hits[:3])}. It reads as unfinished to a visitor and to Google.",
                     "passing" if not hits else "replace it with real copy",
                     detail=", ".join(hits[:3])))

    # 23. Flash.
    flash = _count(h, "embed") + len(re.findall(r"\.swf\b", h, re.I)) \
        + len([o for o in _tags(h, "object") if re.search(r"flash", o, re.I)])
    rows.append(_row("Flash", "ok" if not flash else "error",
                     "No Flash content." if not flash else
                     "Flash content. No browser has run Flash since 2020, so this is invisible to every visitor.",
                     "passing" if not flash else "replace it with HTML5 video or remove it"))

    # 24. Iframe count.
    iframes = _count(h, "iframe")
    rows.append(_row("Iframe count", "ok" if iframes <= IFRAME_WARN_COUNT else "warn",
                     f"{iframes} iframe(s)." if iframes <= IFRAME_WARN_COUNT else
                     f"{iframes} iframes. Each one is a separate document to fetch and render, and their content is not part of this page for search.",
                     "passing" if iframes <= IFRAME_WARN_COUNT else "lazy-load them or cut the count",
                     detail=f"{iframes} iframes"))

    # 25. Inline styles.
    inline = len(re.findall(r"\sstyle=[\"'][^\"']+[\"']", h, re.I))
    rows.append(_row("Inline styles", "ok" if inline <= 20 else "info",
                     f"{inline} inline style attributes." if inline <= 20 else
                     f"{inline} inline style attributes. They cannot be cached or overridden, so the page ships its CSS on every request.",
                     "passing" if inline <= 20 else "move the rules into a stylesheet",
                     detail=f"{inline} attributes"))

    # 26. Empty links — an anchor with no text and no accessible name.
    empties = [m for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", h, re.S | re.I)
               if not re.sub(r"<[^>]+>", "", m.group(2)).strip()
               and not re.search(r"aria-label=|title=", m.group(1), re.I)
               and not re.search(r"<img\b[^>]*\balt=[\"'][^\"']+", m.group(2), re.I)]
    rows.append(_row("Empty links", "ok" if not empties else "warn",
                     "Every link has text or an accessible name." if not empties else
                     f"{len(empties)} link(s) with no text and no label. A screen reader announces them as \"link\", and a crawler learns nothing about the destination.",
                     "passing" if not empties else "add link text, or an aria-label for icon links",
                     detail=f"{len(empties)} link(s)" if empties else ""))
    return rows


def onpage_rows(url: str, html: str) -> list[dict]:
    """All 28 deep on-page checks, pass or fail, in spec order."""
    return _head_rows(html) + _url_rows(url) + _body_rows(url, html)
