#!/usr/bin/env python3
"""Update <lastmod> in sitemap.xml for given URLs to today's date.

Usage: python3 update-sitemap-dates.py [PROJECT_DIR] [url-path ...]
Paths are relative (leading slash required).
"""
import sys, re
from datetime import date
from pathlib import Path
from pipeline.lib.common import load_config


def main():
    if len(sys.argv) < 3:
        print("Usage: update-sitemap-dates.py [PROJECT_DIR] [/url ...]", file=sys.stderr); sys.exit(1)
    project = Path(sys.argv[1])
    paths = sys.argv[2:]
    cfg = load_config(str(project))
    sitemap_rel = cfg["repo"]["sitemap"]
    sitemap = project / sitemap_rel
    today = date.today().isoformat()

    # Next.js App Router uses dynamic sitemap (app/sitemap.ts) — lastmod is computed at
    # build time from page metadata, not hand-edited. Manual rewrite would corrupt the
    # TypeScript file.
    if sitemap.suffix in (".ts", ".js", ".mjs"):
        print(f"[SKIP] {sitemap_rel} is a dynamic sitemap ({sitemap.suffix}). Lastmod is generated at build time from page metadata.")
        print(f"[INFO] To update lastmod, edit dateModified on the relevant page data files (cities.ts / services.ts / city-service-overrides.ts) and rebuild.")
        sys.exit(0)

    text = sitemap.read_text()
    updated = 0
    for p in paths:
        p = "/" + p.strip("/") + "/"
        full = f"https://{cfg['domain']}{p}"
        pattern = re.compile(
            rf"(<loc>{re.escape(full)}</loc><lastmod>)[^<]+(</lastmod>)"
        )
        new_text, n = pattern.subn(rf"\g<1>{today}\g<2>", text)
        if n == 0:
            print(f"[WARN] {p} not found in sitemap")
        else:
            text = new_text; updated += 1
            print(f"[OK] {p} → {today}")
    sitemap.write_text(text)
    print(f"\nUpdated {updated}/{len(paths)} lastmod entries.")


if __name__ == "__main__":
    main()
