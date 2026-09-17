"""URL canonical consistency checks derived from crawled URLs."""
from __future__ import annotations

from urllib.parse import urlsplit
from pipeline.scanner.rows import make_row

_row = make_row("url")

def url_quality_rows(urls: set[str] | list[str]) -> list[dict]:
    vals = sorted({u for u in urls if u})
    if not vals:
        return []
    parsed = [urlsplit(u) for u in vals]
    hosts = {p.netloc.lower() for p in parsed}
    schemes = {p.scheme.lower() for p in parsed}
    if len(hosts) > 1:
        return [_row("URL host consistency", "warn", f"Crawl contains {len(hosts)} host variants.",
                     "Choose one canonical host and redirect all other host variants.", detail=", ".join(sorted(hosts)))]
    rows = []
    if len(schemes) > 1:
        rows.append(_row("URL protocol consistency", "warn", "Both HTTP and HTTPS URLs were discovered.",
                         "Redirect HTTP to HTTPS and use HTTPS in canonicals and sitemaps."))
    slash_variants = {p.path.rstrip("/") or "/" for p in parsed}
    if any(p.path.endswith("/") for p in parsed) and any(not p.path.endswith("/") for p in parsed if p.path != "/"):
        rows.append(_row("Trailing slash consistency", "warn", "Trailing-slash and non-trailing-slash URL forms coexist.",
                         "Pick one slash policy and redirect the other form."))
    if any("index.html" in p.path.lower() for p in parsed):
        rows.append(_row("index.html URLs", "warn", "index.html URL variants were discovered.",
                         "Redirect index.html to the directory URL and use one canonical form."))
    if any(any(c.isupper() for c in p.path) for p in parsed):
        rows.append(_row("URL case consistency", "warn", "Uppercase path URLs were discovered.",
                         "Use lowercase hyphen-separated paths and redirect case variants."))
    return rows
