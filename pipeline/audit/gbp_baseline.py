#!/usr/bin/env python3
"""Capture current map-pack baseline for new city spokes.

Writes docs/gbp-baseline-[YYYY-MM-DD].md with client + URL + primary keyword
for each new spoke. Actual DataForSEO pulls happen via MCP in the calling agent.
This script writes the stub; the agent fills in ranks.

Usage: python3 gbp-baseline.py [PROJECT_DIR] "keyword1 -- /url1" "keyword2 -- /url2" ...
"""
import sys
from datetime import date
from pathlib import Path
from pipeline.lib.common import load_config


def main():
    if len(sys.argv) < 3:
        print('Usage: gbp-baseline.py [PROJECT_DIR] "keyword -- /url" ...', file=sys.stderr); sys.exit(1)
    project = Path(sys.argv[1])
    cfg = load_config(str(project))
    entries = sys.argv[2:]

    today = date.today().isoformat()
    out = [f"# GBP Map-Pack Baseline — {today}", "", f"Client: {cfg['client']}", f"Primary metro: {cfg.get('primary_metro', 'N/A')}", "", "| URL | Keyword | Map-Pack Rank | Notes |", "|-----|---------|---------------|-------|"]
    for entry in entries:
        if " -- " not in entry:
            print(f"[SKIP] Bad format: {entry}"); continue
        kw, url = entry.split(" -- ", 1)
        out.append(f"| {url.strip()} | {kw.strip()} | TODO | Fill via DataForSEO MCP |")
    out.append("")
    out.append(f"Run via MCP: mcp__dataforseo-mcp__business_data_business_listings_search")
    out.append(f"Client domain: {cfg['domain']}")

    target = project / "docs" / f"gbp-baseline-{today}.md"
    target.write_text("\n".join(out))
    print(f"[OK] Wrote {target}")
    print(f"[NEXT] Agent must call DataForSEO MCP and fill TODO ranks.")


if __name__ == "__main__":
    main()
