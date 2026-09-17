#!/usr/bin/env python3
"""run.py — wf-outreach: qualify domains, maintain the link bank, draft content.

    wf-outreach --project <repo> --qualify candidates.txt
        run the 4-point safety check over each domain in the file (one per line,
        # comments allowed) and upsert every verdict into the link bank.

    wf-outreach --project <repo> --draft example.com
        generate tier-appropriate outreach copy for one already-banked domain and
        store it on that domain's bank entry.

Both can be passed together. NEITHER sends anything — the outreach email itself is
a human step (SOP §12). Off entirely unless docs/client-config.yml declares
`outreach.enabled: true`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.lib.common import load_config
from pipeline.outreach import content, linkbank, qualify


def _read_domains(path: str) -> list:
    lines = Path(path).read_text().splitlines()
    return [d.strip() for d in lines if d.strip() and not d.lstrip().startswith("#")]


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-outreach",
        description="Backlink outreach: qualify domains, bank them, draft tiered "
                    "content. Never sends — outreach is a human step.")
    ap.add_argument("--project", required=True, help="client repo root")
    ap.add_argument("--qualify", metavar="FILE",
                    help="newline-delimited candidate domains to qualify and bank")
    ap.add_argument("--max-domains", type=int, default=20,
                    help="stop after this many candidates (each is a paid DataForSEO call; default 20)")
    ap.add_argument("--max-usd", type=float, default=1.00,
                    help="stop before total DataForSEO spend would pass this (default 1.00)")
    ap.add_argument("--draft", metavar="DOMAIN",
                    help="draft outreach content for one banked domain")
    args = ap.parse_args()

    cfg = load_config(args.project)
    oc = cfg.get("outreach") if isinstance(cfg.get("outreach"), dict) else {}
    if not oc.get("enabled"):
        print("[WARN] outreach.enabled is false in docs/client-config.yml — nothing "
              "to do. Set it true to use wf-outreach.", file=sys.stderr)
        return 0
    tier = oc.get("tier", 1)
    topics = oc.get("topics") or []

    if args.qualify:
        domains = _read_domains(args.qualify)
        # B-124: each candidate is a paid DataForSEO call. Cap the count and the
        # spend, and print what each one cost. The spend cap stops BEFORE a call
        # whose typical cost (the largest seen so far) would pass it.
        spent, done, largest = 0.0, 0, 0.0
        for dom in domains:
            if done >= args.max_domains:
                print(f"[STOP] stopped at --max-domains {args.max_domains} "
                      f"({len(domains) - done} candidate(s) not checked)")
                break
            if done and spent + largest > args.max_usd:
                print(f"[STOP] stopped at --max-usd ${args.max_usd:.2f} "
                      f"(spent ${spent:.4f}; {len(domains) - done} candidate(s) not checked)")
                break
            v = qualify.qualify_domain(dom)
            cost = float(v.get("cost") or 0.0)
            spent += cost
            largest = max(largest, cost)
            done += 1
            linkbank.upsert(args.project, {
                "domain": dom, "verdict": v["verdict"], "tier": tier,
                "checks": v["checks"], "reasons": v["reasons"], "status": "qualified",
            })
            summary = "; ".join(v["reasons"]) or v.get("status", "")
            print(f"[qualify] {dom}: {v['verdict']} — {summary} · ${cost:.4f}")
        print(f"[OK] qualified {done} domain(s), DataForSEO spend ${spent:.4f} -> {linkbank.bank_path(args.project)}")

    if args.draft:
        bank = linkbank.load(args.project)
        if args.draft not in bank.get("domains", {}):
            print(f"[ERROR] {args.draft} is not in the link bank — qualify it first.",
                  file=sys.stderr)
            return 2
        try:
            text = content.draft(args.draft, tier=tier, topics=topics)
        except (RuntimeError, FileNotFoundError, OSError) as exc:
            print(f"[SKIP] draft for {args.draft}: claude unavailable ({exc})",
                  file=sys.stderr)
            return 0
        linkbank.upsert(args.project, {"domain": args.draft, "draft": text,
                                       "status": "drafted"})
        print(f"[OK] draft stored for {args.draft}\n\n{text[:800]}")

    if not args.qualify and not args.draft:
        print("[INFO] nothing to do — pass --qualify <file> and/or --draft <domain>.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
