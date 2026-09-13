"""Orchestrate the seed engine: gaps.json -> drafts (claude) -> dispatch by tier
-> seed-log.json. Offline-testable via injectable `runner` (claude seam) and
`poster` (green action). MVP uses the stub poster, so a run makes no network
calls and needs no platform accounts — only the claude subscription for drafts.

CLI: wf-seed --gaps gaps.json [--out-dir .] [--drafts-dir ./drafts] [--live]
`--live` is reserved for when real green posters replace the stub; today the stub
is always used and the flag only labels the log's `mode`."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from pipeline.seed.gaps import parse_gaps
from pipeline.seed.generate import draft
from pipeline.seed.posters import PostResult, green_poster, stub_post, write_draft_file
from pipeline.seed.tiers import tier_of

from pipeline.lib.atomic import write_json_atomic


def dispatch(drafts, drafts_dir: str, poster=None) -> list[PostResult]:
    poster = poster or stub_post
    results: list[PostResult] = []
    for d in drafts:
        tier = tier_of(d.gap.platform)
        if tier == "green":
            results.append(poster(d))
        elif tier == "yellow":
            results.append(write_draft_file(d, drafts_dir))
        elif tier == "red":
            results.append(PostResult(platform=d.gap.platform,
                                      status="skipped", detail="never-auto"))
        else:
            results.append(PostResult(platform=d.gap.platform, status="skipped",
                                      detail="unknown platform"))
    return results


def run_seed(gaps_path: str, out_dir: str, drafts_dir: str,
             runner=None, poster=None, live: bool = False,
             publish: bool = False) -> dict:
    with open(gaps_path, encoding="utf-8") as fh:
        rows = json.load(fh)
    gaps, dropped = parse_gaps(rows)

    # Only green/yellow gaps are worth drafting: red is never posted, and an
    # unknown platform falls through to a loud skip. Generating a draft for
    # either wastes a claude call — and asking the model to write a promotional
    # Wikipedia entry (red) correctly gets refused, which would surface as a
    # spurious "generation failed". Skip them before generation, not after.
    pre_skipped: list[PostResult] = []
    to_draft = []
    for g in gaps:
        tier = tier_of(g.platform)
        if tier == "red":
            pre_skipped.append(PostResult(platform=g.platform,
                                          status="skipped", detail="never-auto"))
        elif tier == "unknown":
            pre_skipped.append(PostResult(platform=g.platform,
                                          status="skipped", detail="unknown platform"))
        else:
            to_draft.append(g)

    drafts = []
    for g in to_draft:
        try:
            drafts.append(draft(g, run=runner))
        except Exception as e:  # generation failure ≠ dead run
            dropped.append({"platform": g.platform, "topic": g.topic,
                            "_reason": f"generation failed: {e}"})

    poster = poster or green_poster(live=live, publish=publish)
    results = pre_skipped + dispatch(drafts, drafts_dir, poster=poster)

    counts = {
        "posted": sum(r.status == "posted" for r in results),
        "queued": sum(r.status == "queued" for r in results),
        "skipped": sum(r.status == "skipped" for r in results),
        "dropped": len(dropped),
    }
    log = {
        "mode": "live" if live else "dry-run",
        "counts": counts,
        "results": [asdict(r) for r in results],
        "dropped": dropped,
    }
    os.makedirs(out_dir, exist_ok=True)
    write_json_atomic(os.path.join(out_dir, "seed-log.json"), log, sort_keys=False)
    return log


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Seed brand-mention topics from a gaps.json.")
    ap.add_argument("--gaps", required=True, help="path to gaps.json")
    ap.add_argument("--out-dir", default=".", help="where seed-log.json goes")
    ap.add_argument("--drafts-dir", default="",
                    help="where yellow-tier drafts go (default <out-dir>/drafts)")
    ap.add_argument("--live", action="store_true",
                    help="use real green posters (needs platform creds in env); "
                         "without it, green is the stub")
    ap.add_argument("--publish", action="store_true",
                    help="with --live, publish immediately; default posts an "
                         "unpublished draft to verify first")
    args = ap.parse_args()
    drafts_dir = args.drafts_dir or os.path.join(args.out_dir, "drafts")
    log = run_seed(args.gaps, args.out_dir, drafts_dir,
                   live=args.live, publish=args.publish)
    c = log["counts"]
    print(f"seed [{log['mode']}]: posted={c['posted']} queued={c['queued']} "
          f"skipped={c['skipped']} dropped={c['dropped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
