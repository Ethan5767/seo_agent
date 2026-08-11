#!/usr/bin/env python3
"""snapshot.py — crawl a rendered site into the static tree the gates already read.

    wf-render-snapshot --project . --base-url https://pr-34.acme.pages.dev
                       [--out ./out] [--url /path/ ...] [--limit N]

WHY THIS EXISTS (v3 sharp edge #4)
----------------------------------
Nine gates read the BUILT HTML: `acceptance_check`, `em_dash_check`,
`check_headings`, `capsule_check`, `noncommodity_check`, `fingerprint_check`,
`forbidden_sweep` (built mode), `orphan_check`, `parity_check`. They find it by
globbing `<BUILD_DIR>/**/*.html`.

A client with no static export emits no such tree. `lee-series-web` is
`nextjs-16-app-router` with no `output: 'export'`, so `./out` never exists,
`.github/actions/build-site` exits 1, and all nine gates are SKIPPED. The whole
OUT half of the suite — including `forbidden_sweep`, which is
`NEVER_BASELINEABLE` for legal exposure — cannot run on that client at all.

The obvious fixes are both wrong. Asking the client to statically export means
rewriting their rendering architecture to suit our gates. Pointing
`build_output_dir` at `.next` is worse: it produces a directory that EXISTS and
holds no route tree, which is the one shape that makes the gates scan nothing and
report **green** rather than refusing.

The rendered HTML already exists — it is the Cloudflare preview deployment, which
`preview.reusable.yml` resolves on every PR and exposes as `preview_url`. So this
crawls it into `<out>/<path>/index.html`, and the nine gates run unchanged.

**That is the point.** The alternative was teaching nine gates a second way to find
a page. `quality-gate.reusable.yml` says every OUT gate is deliberately
FRAMEWORK-BLIND — "it scans whatever BUILD_DIR points at" — and this keeps that
true: one step produces the tree, and nothing downstream learns a new concept.

A SNAPSHOT OF NOTHING IS NOT A CLEAN SITE
-----------------------------------------
Exit 19 when no page was fetched, and the run writes no tree at all. An empty
`--out` directory would let every gate glob zero files and pass, which is the
precise failure this module was written to remove.

Exit: 0 pages written · 2 usage · 19 REFUSED (nothing fetched, nothing written)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from pipeline.audit.measure import discover_urls
from pipeline.lib.common import curl, curl_final_host, curl_status, load_config

SCHEMA = "render-snapshot/1"
MANIFEST = "snapshot.json"
REFUSED_EXIT = 19
USAGE_EXIT = 2


class SnapshotError(RuntimeError):
    """Usage failure — nothing to crawl, or nowhere to write it."""


def route_for(url: str) -> str:
    """The site path a URL maps to, normalised the way the gates derive routes."""
    path = urlsplit(url).path or "/"
    if not path.startswith("/"):
        path = "/" + path
    return path if path.endswith("/") else path + "/"


def dest_for(out: Path, route: str) -> Path:
    """`<out>/<route>/index.html`.

    `index.html` under a directory, never `<route>.html`: `parity_check` and
    `orphan_check` derive a route from `<dir>/index.html`, and `noncommodity_check`
    globs for `index.html` specifically. Writing the flat form would produce a tree
    those three cannot read — a snapshot that satisfies some gates and silently
    starves others.
    """
    rel = route.strip("/")
    return (out / rel / "index.html") if rel else (out / "index.html")


# Files the gates read out of the build tree that are NOT routes. A static export
# emits them at the root; a crawl has to ask for them by name. Missing one is not
# fatal here — `parity_check` and `robots_aicrawler_check` each have their own
# verdict for an absent file, and that verdict is theirs to give, not ours to
# pre-empt by refusing the whole snapshot.
ROOT_ASSETS = ("sitemap.xml", "robots.txt", "llms.txt")


def fetch_root_assets(base: str, out: Path) -> list:
    """Pull the non-route files, returning the names that landed."""
    got = []
    for name in ROOT_ASSETS:
        url = f"{base}/{name}"
        if curl_status(url) != 200:
            print(f"[warn] {name} not served at {url} — the gates that read it will "
                  f"say so themselves", file=sys.stderr)
            continue
        body = curl(url, cache_bust=False)
        if not body.strip():
            continue
        (out / name).write_text(body)
        got.append(name)
        print(f"[ok] {name} -> {name}  ({len(body)} bytes)")
    return got


def snapshot(project, base_url: str, out: Path, urls: list, limit=None) -> dict:
    """Crawl and write. Returns the manifest; raises SnapshotError if nothing landed."""
    cfg = load_config(str(project))
    base = base_url.rstrip("/")

    # The sitemap is read from the LIVE domain (it lists the client's real routes),
    # but every page is fetched from `base_url` — the candidate build. Reading the
    # candidate's own sitemap would let a PR that dropped a route also drop it from
    # the set of routes being judged.
    paths = [route_for(u) for u in discover_urls(cfg, urls, limit)]

    # An auth wall answers 200 for every route, from a different host (B-037).
    # Vercel Deployment Protection redirects to `vercel.com/sso-api`, Cloudflare
    # Access to `<team>.cloudflareaccess.com`, Netlify to its own password form —
    # and `curl -L` follows all of them, so a walled deployment crawls cleanly
    # into 26 copies of a login page that every OUT gate then judges as the site.
    # That is strictly worse than the empty tree this crawler already refuses:
    # green over nothing at least has an empty directory to notice.
    #
    # Checked once, on the first route, before anything is written. Compared by
    # HOST, so a host-relative redirect (trailing-slash policy, locale prefix) is
    # untouched — the crawler must keep following those.
    want_host = urlsplit(base).netloc.lower()
    landed = curl_final_host(base + (paths[0] if paths else "/"))
    if landed and landed != want_host:
        raise SnapshotError(
            f"{base} redirects to a different host ({landed}). That is an auth wall or "
            f"an interstitial, not the site — every route would answer 200 with the same "
            f"login page, and the OUT gates would judge that instead of the deployment. "
            f"Nothing was written. If this is Vercel Deployment Protection, either turn it "
            f"off for this project or supply a protection-bypass secret; the equivalent "
            f"exists for Cloudflare Access and Netlify.")

    written, failed = [], []
    for route in dict.fromkeys(paths):
        url = base + route
        status = curl_status(url)
        html = curl(url) if status == 200 else ""
        if status != 200 or not html.strip():
            failed.append({"route": route, "status": status})
            print(f"[WARN] {url} -> {status or 'unreachable'}", file=sys.stderr)
            continue
        target = dest_for(out, route)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html)
        written.append(route)
        print(f"[ok] {route} -> {target.relative_to(out)}  ({len(html)} bytes)")

    if not written:
        raise SnapshotError(
            f"no page was fetched from {base} ({len(failed)} attempted). Nothing was "
            f"written: an empty build dir makes every OUT gate glob zero files and "
            f"report green, which is worse than not running them.")

    assets = fetch_root_assets(base, out)

    return {
        "schema": SCHEMA,
        "generated": date.today().isoformat(),
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_url": base,
        "domain": cfg.get("domain"),
        # Named so a human reading the tree knows it came from a crawl of a
        # deployment rather than from a local build. The two are not the same
        # evidence, and a gate verdict over one should not be filed as the other.
        "source": "crawl",
        "routes": sorted(written),
        "root_assets": sorted(assets),
        "failed": failed,
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass

    ap = argparse.ArgumentParser(
        prog="wf-render-snapshot",
        description="Crawl a rendered deployment into the static HTML tree the gates read.")
    ap.add_argument("--project", required=True, help="client repo root")
    ap.add_argument("--base-url", required=True,
                    help="the rendered deployment to crawl, e.g. a Cloudflare preview URL")
    ap.add_argument("--out", default="./out",
                    help="where to write the tree (default: ./out — what BUILD_DIR expects)")
    ap.add_argument("--url", action="append", default=[], metavar="PATH",
                    help="crawl exactly these paths instead of the live sitemap")
    ap.add_argument("--limit", type=int, help="stop after N routes")
    ap.add_argument("--clean", action="store_true",
                    help="remove --out first, so a stale page from an earlier run "
                         "cannot be judged as part of this one")
    args = ap.parse_args()

    if not args.base_url.startswith(("http://", "https://")):
        print("[ERROR] --base-url must be an absolute http(s) URL", file=sys.stderr)
        return USAGE_EXIT

    out = Path(args.out)
    if args.clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    try:
        manifest = snapshot(args.project, args.base_url, out, args.url, args.limit)
    except SnapshotError as exc:
        print(f"[REFUSED] {exc}", file=sys.stderr)
        return REFUSED_EXIT
    except Exception as exc:                      # unreachable sitemap, bad config
        print(f"[ERROR] {exc}", file=sys.stderr)
        return USAGE_EXIT

    (out / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"\n[OK] {len(manifest['routes'])} route(s) captured from "
          f"{manifest['base_url']} -> {out}"
          + (f", {len(manifest['failed'])} failed" if manifest["failed"] else ""))
    if manifest["failed"]:
        print(f"[WARN] {len(manifest['failed'])} route(s) did not answer 200. The gates "
              f"will judge only what was captured — read this list before trusting a "
              f"green suite.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
