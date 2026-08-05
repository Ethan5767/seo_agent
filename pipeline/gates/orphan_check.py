#!/usr/bin/env python3
"""
orphan-check.py — THE Acme bug as a build-time impossibility.

Lesson 5 + the live-site scar: a page can exist in the sitemap (and be crawled
by Google) while NO other page links to it. Google sees an "orphan": indexed,
but with zero internal PageRank flow and no crawl path. On Acme this was only
ever caught reactively, by a monthly manual audit. This gate turns it into a
hard, deterministic build-time check.

What it asserts, against a built static-export `./out` directory:
    every URL in the sitemap has >= 1 inbound internal <a href> link
    from somewhere in the built HTML.

How it works (fully deterministic, no network):
    1. Parse out/sitemap.xml (or out/sitemap/*.xml, or out/sitemap.txt) for
       <loc> URLs. These are the canonical "must be reachable" set.
    2. Walk every out/**/*.html and extract every <a href="..."> target.
    3. Normalize both sides to a canonical site path (strip scheme+host, drop
       query/fragment, trailingSlash-aware) and intersect.
    4. Any sitemap path with no inbound link is an ORPHAN → exit 1 + list it.

Notes:
    - Self-links count as inbound (global nav/footer links a page to itself),
      which is correct: if a page links to itself via the global chrome, that
      same chrome links it from every other page too. The real orphan bug is a
      page that lives in NO nav/footer/body of ANY page — exactly what this
      catches.
    - Asset hrefs (_next, css, js, images, fonts) normalize to paths with file
      extensions and simply never match a sitemap page path; they are harmless.
    - The homepage "/" is included in the check by default. Pass --allow-root
      to exempt it if a given template intentionally has no inbound "/" link
      (rare; the logo usually links to "/").

Exit codes:
    0  every sitemap URL has >= 1 inbound internal link
    1  one or more orphans found, OR sitemap/out not found

Usage:
    orphan-check.py --out /tmp/acme/out
    orphan-check.py --out ./out --allow-root
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote

LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>", re.IGNORECASE)
# A path whose final segment contains a dot is treated as a file (asset), not a
# trailing-slash page route.
HAS_EXT_RE = re.compile(r"/[^/]*\.[^/]+$")


def canonical_path(url: str, known_hosts: set[str]) -> str | None:
    """Reduce a sitemap loc or an <a href> to a comparable site path.

    Returns None for things that are not internal page references
    (mailto:, tel:, #fragment, javascript:, external hosts).
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    low = url.lower()
    if low.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return None
    if url.startswith("#"):
        return None

    parts = urlsplit(url)
    # External absolute URL to a different host → not internal.
    if parts.scheme in ("http", "https"):
        host = parts.netloc.lower()
        # strip leading www. for comparison
        host_norm = host[4:] if host.startswith("www.") else host
        hosts_norm = {h[4:] if h.startswith("www.") else h for h in known_hosts}
        if host_norm not in hosts_norm:
            return None

    path = parts.path
    if not path:
        path = "/"
    path = unquote(path)

    # Drop query + fragment (urlsplit already separated them).
    # trailingSlash-aware: ensure a trailing slash on directory-style routes,
    # leave file-style paths (with an extension) untouched.
    if path != "/" and not path.endswith("/") and not HAS_EXT_RE.search(path):
        path = path + "/"
    if not path.startswith("/"):
        path = "/" + path
    return path


class HrefExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        for k, v in attrs:
            if k.lower() == "href" and v:
                self.hrefs.append(v)


def parse_sitemap(out_dir: str) -> tuple[list[str], set[str]]:
    """Return (loc_urls, hosts_seen). Looks for xml sitemaps then a txt fallback."""
    candidates: list[str] = []
    for pat in ("sitemap.xml", os.path.join("sitemap", "*.xml"), "sitemap-*.xml"):
        candidates.extend(sorted(glob.glob(os.path.join(out_dir, pat))))
    locs: list[str] = []
    hosts: set[str] = set()
    for f in candidates:
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        for m in LOC_RE.finditer(text):
            u = m.group(1).strip()
            locs.append(u)
            host = urlsplit(u).netloc.lower()
            if host:
                hosts.add(host)
    if not locs:
        # txt fallback (one URL per line)
        txt = os.path.join(out_dir, "sitemap.txt")
        if os.path.exists(txt):
            with open(txt, encoding="utf-8") as fh:
                for line in fh:
                    u = line.strip()
                    if u.startswith("http"):
                        locs.append(u)
                        host = urlsplit(u).netloc.lower()
                        if host:
                            hosts.add(host)
    # de-dupe preserving order
    seen = set()
    uniq = []
    for u in locs:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq, hosts


def collect_inbound_links(out_dir: str, known_hosts: set[str]) -> set[str]:
    targets: set[str] = set()
    for path in glob.glob(os.path.join(out_dir, "**", "*.html"), recursive=True):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                html = fh.read()
        except OSError:
            continue
        p = HrefExtractor()
        try:
            p.feed(html)
        except Exception:
            # Malformed markup: fall back to a regex sweep so we never miss links.
            for m in re.finditer(r'href\s*=\s*"([^"]*)"', html):
                p.hrefs.append(m.group(1))
        for href in p.hrefs:
            cp = canonical_path(href, known_hosts)
            if cp is not None:
                targets.add(cp)
    return targets


def main() -> int:
    ap = argparse.ArgumentParser(description="Assert every sitemap URL has an inbound internal link.")
    ap.add_argument("--out", default="./out", help="Path to the built static-export directory (default ./out)")
    ap.add_argument("--allow-root", action="store_true", help="Exempt the homepage '/' from the inbound-link requirement")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    if not os.path.isdir(out_dir):
        print(f"ERROR: out dir not found: {out_dir}", file=sys.stderr)
        return 1

    locs, hosts = parse_sitemap(out_dir)
    if not locs:
        print(f"ERROR: no sitemap URLs found under {out_dir} (looked for sitemap.xml, sitemap/*.xml, sitemap.txt)", file=sys.stderr)
        return 1

    sitemap_paths = []
    seen = set()
    for u in locs:
        cp = canonical_path(u, hosts)
        if cp and cp not in seen:
            seen.add(cp)
            sitemap_paths.append(cp)

    inbound = collect_inbound_links(out_dir, hosts)

    orphans = []
    for cp in sitemap_paths:
        if args.allow_root and cp == "/":
            continue
        if cp not in inbound:
            orphans.append(cp)

    print(f"orphan-check: {len(sitemap_paths)} sitemap URLs, {len(inbound)} distinct internal link targets")
    if orphans:
        print(f"FAIL: {len(orphans)} orphan page(s) — in sitemap, but ZERO inbound internal links:")
        for o in sorted(orphans):
            print(f"  ORPHAN  {o}")
        return 1
    print("PASS: every sitemap URL has >= 1 inbound internal link.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
