"""Deep on-page checks — Semrush-style technical audit on the fetched HTML.

Everything here is free, synchronous, and pure (HTML in, rows out), so it runs
on the one page we already fetched with no extra request. These are the checks
NOT already covered by seo_rows / tech_rows — charset, doctype, mixed content,
link safety, render-blocking, CLS-risk images, DOM weight, hreflang, etc. —
adding Semrush-audit breadth without another vendor.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit


def _row(what: str, severity: str, why: str, fix: str, detail: str = "") -> dict:
    return {"code": f"op.{what.lower().replace(' ', '_')}", "what": what,
            "why": why, "fix": fix, "detail": detail, "severity": severity}


def _ok(what, why):
    return _row(what, "ok", why, "passing")


def onpage_deep_rows(url: str, html: str, status: int) -> list[dict]:
    h = html or ""
    low = h.lower()
    https = url.lower().startswith("https://")
    rows: list[dict] = []

    # Charset
    rows.append(_ok("Charset", "A <meta charset> is declared.") if re.search(r"<meta[^>]*charset", low)
                else _row("Charset", "warn", "No <meta charset> — browsers may mis-render special characters.",
                          'Add <meta charset="utf-8"> as the first <head> tag.'))

    # Doctype
    rows.append(_ok("Doctype", "A <!DOCTYPE html> is present (standards mode).") if low.lstrip().startswith("<!doctype")
                else _row("Doctype", "warn", "Missing <!DOCTYPE html> — can trigger quirks-mode rendering.",
                          "Add <!DOCTYPE html> at the very top."))

    # Single <title> / single meta description
    if len(re.findall(r"<title[\s>]", low)) > 1:
        rows.append(_row("Single title", "warn", "More than one <title> tag — search engines pick one unpredictably.",
                         "Keep exactly one <title>."))
    if len(re.findall(r'<meta[^>]*name=["\']description["\']', low)) > 1:
        rows.append(_row("Single meta description", "warn", "Multiple meta description tags — conflicting snippets.",
                         "Keep exactly one meta description."))

    # Mixed content (http resources on an https page)
    if https:
        mixed = re.findall(r'(?:src|href)=["\']http://[^"\']+', low)
        if mixed:
            rows.append(_row("Mixed content", "error",
                             f"{len(mixed)} resource(s) loaded over http:// on an https page — browsers block/flag them.",
                             "Serve every asset over https.", detail=f"{len(mixed)} http asset(s)"))
        else:
            rows.append(_ok("Mixed content", "All resources load over https."))

    # target=_blank without rel=noopener (security + tab-nabbing)
    blanks = re.findall(r"<a\b[^>]*target=[\"']_blank[\"'][^>]*>", low)
    unsafe = [a for a in blanks if "noopener" not in a and "noreferrer" not in a]
    if unsafe:
        rows.append(_row("External link safety", "warn",
                         f"{len(unsafe)} target=_blank link(s) without rel=noopener — a security/perf risk.",
                         'Add rel="noopener" to target=_blank links.', detail=f"{len(unsafe)}"))

    # Render-blocking scripts in <head> (no async/defer)
    head = re.search(r"<head[^>]*>(.*?)</head>", h, re.DOTALL | re.IGNORECASE)
    if head:
        head_scripts = re.findall(r"<script\b[^>]*\bsrc=[^>]*>", head.group(1), re.IGNORECASE)
        blocking = [s for s in head_scripts if "async" not in s.lower() and "defer" not in s.lower()]
        if blocking:
            rows.append(_row("Render-blocking scripts", "warn",
                             f"{len(blocking)} script(s) in <head> without async/defer — they delay first paint.",
                             "Add async or defer, or move scripts to the end of <body>.",
                             detail=f"{len(blocking)}"))

    # Images without width/height (layout shift / CLS)
    imgs = re.findall(r"<img\b[^>]*>", low)
    no_dims = [i for i in imgs if not (re.search(r"\bwidth=", i) and re.search(r"\bheight=", i))]
    if imgs:
        if no_dims:
            rows.append(_row("Image dimensions", "warn",
                             f"{len(no_dims)}/{len(imgs)} image(s) missing width/height — causes layout shift (CLS).",
                             "Set width and height on <img> so the browser reserves space.",
                             detail=f"{len(no_dims)} of {len(imgs)}"))
        else:
            rows.append(_ok("Image dimensions", "All images declare width/height (no layout shift)."))

    # Deprecated tags
    dep = [t for t in ("center", "font", "marquee", "blink") if re.search(rf"<{t}\b", low)]
    if dep:
        rows.append(_row("Deprecated HTML", "warn",
                         f"Deprecated tag(s): {', '.join(dep)} — obsolete and bad for accessibility.",
                         "Replace with CSS/semantic HTML.", detail=", ".join(dep)))

    # DOM weight
    elements = len(re.findall(r"<[a-zA-Z]", h))
    if elements > 1500:
        rows.append(_row("DOM size", "warn",
                         f"~{elements} elements — a heavy DOM slows rendering and hurts INP.",
                         "Simplify the markup / paginate long lists.", detail=f"~{elements} nodes"))

    # Link volume
    links = len(re.findall(r"<a\b[^>]*href=", low))
    if links > 100:
        rows.append(_row("Link volume", "warn",
                         f"{links} links on the page — excessive linking dilutes authority per link.",
                         "Trim to the meaningful links.", detail=f"{links} links"))

    # hreflang (multi-region signal — informational)
    if re.search(r'<link[^>]*hreflang=', low):
        rows.append(_ok("hreflang", "hreflang alternates are declared (multi-language/region aware)."))

    # Semantic landmark
    if "<main" not in low:
        rows.append(_row("Semantic <main>", "warn",
                         "No <main> landmark — weaker structure for assistive tech and content extraction.",
                         "Wrap the primary content in <main>."))
    else:
        rows.append(_ok("Semantic <main>", "A <main> landmark marks the primary content."))

    return rows
