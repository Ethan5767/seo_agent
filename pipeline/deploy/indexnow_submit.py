#!/usr/bin/env python3
"""
indexnow-submit.py — submit changed URLs to IndexNow (Bing + Yandex).

IndexNow is a single ping that notifies participating search engines (Bing,
Yandex, Seznam, etc.) that URLs changed. Google does NOT participate, and its
old sitemap-ping endpoint was deprecated in 2023 (it 404s) — so we never ping
Google here. Google is covered via Search Console + the generated sitemap.

How IndexNow auth works: you host a key file at
    https://<host>/<key>.txt
whose body is exactly the key. Then you POST the key + the changed URLs to an
IndexNow endpoint; the engine fetches your key file to confirm ownership.
Submitting to ONE participating endpoint shares the submission with the others,
but we post to both Bing and Yandex directly for redundancy.

Exit codes:
    0  at least one endpoint accepted (HTTP 200/202), or dry-run
    1  all endpoints failed / hard error

Usage:
    indexnow-submit.py --host northstar.com --key <KEY> \
        --base-url https://northstar.com \
        --urls "https://northstar.com/a/ https://northstar.com/b/"

    # dry run (prints the payload, sends nothing):
    indexnow-submit.py --host northstar.com --key <KEY> \
        --base-url https://northstar.com --urls "..." --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

# Participating IndexNow endpoints. Posting to one shares with all, but we hit
# both for redundancy. NOTE: no Google endpoint exists — by design.
ENDPOINTS = [
    "https://api.indexnow.org/indexnow",
    "https://www.bing.com/indexnow",
    "https://yandex.com/indexnow",
]


def parse_urls(raw: str) -> list[str]:
    """Accept newline- or whitespace-separated URLs; dedupe, keep order."""
    if not raw:
        return []
    parts = raw.replace("\n", " ").replace("\r", " ").split()
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def host_of(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).netloc.lower()


def main() -> int:
    ap = argparse.ArgumentParser(description="Submit changed URLs to IndexNow.")
    ap.add_argument("--host", required=True,
                    help="Bare host the key file is served from, e.g. northstar.com")
    ap.add_argument("--key", required=True,
                    help="IndexNow key (also hosted at https://<host>/<key>.txt)")
    ap.add_argument("--base-url", required=True,
                    help="Prod base URL, used as the sole submission if --urls empty")
    ap.add_argument("--urls", default="",
                    help="Newline/space separated absolute URLs that changed")
    ap.add_argument("--key-location", default="",
                    help="Optional explicit keyLocation URL; default https://<host>/<key>.txt")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the payload and exit 0 without sending")
    args = ap.parse_args()

    host = args.host.strip().lower()
    urls = parse_urls(args.urls)

    if not urls:
        # Nothing explicit changed — submit the base URL so the cycle still pings.
        base = args.base_url.strip()
        if base:
            urls = [base if base.endswith("/") else base + "/"]

    if not urls:
        print("indexnow: no URLs to submit; nothing to do.")
        return 0

    # Safety: every URL must be on the same host as the key file, or IndexNow
    # rejects the whole batch (403). Drop foreign-host URLs loudly.
    clean: list[str] = []
    for u in urls:
        if host_of(u) == host:
            clean.append(u)
        else:
            print(f"indexnow: WARNING dropping off-host URL (host!={host}): {u}",
                  file=sys.stderr)
    if not clean:
        print(f"indexnow: no URLs match host {host}; nothing valid to submit.",
              file=sys.stderr)
        return 1
    urls = clean

    key_location = args.key_location.strip() or f"https://{host}/{args.key}.txt"

    payload = {
        "host": host,
        "key": args.key,
        "keyLocation": key_location,
        "urlList": urls,
    }
    body = json.dumps(payload).encode("utf-8")

    # Never print the key. Redact for logs.
    safe_payload = dict(payload)
    safe_payload["key"] = "***"
    safe_payload["keyLocation"] = key_location.replace(args.key, "***")
    print("indexnow payload (key redacted):")
    print(json.dumps(safe_payload, indent=2))
    print(f"indexnow: submitting {len(urls)} URL(s) to {len(ENDPOINTS)} endpoint(s)")

    if args.dry_run:
        print("indexnow: --dry-run set; not sending.")
        return 0

    successes = 0
    for endpoint in ENDPOINTS:
        req = urllib.request.Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "meridian-ci-indexnow/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                code = resp.status
                # 200 = accepted, 202 = accepted/queued. Both are success.
                if code in (200, 202):
                    successes += 1
                    print(f"  {endpoint} -> HTTP {code} OK")
                else:
                    print(f"  {endpoint} -> HTTP {code} (unexpected)")
        except urllib.error.HTTPError as e:
            # 422 = unknown URLs, 403 = key/host mismatch, 429 = too many requests.
            print(f"  {endpoint} -> HTTP {e.code} {e.reason}")
        except Exception as e:  # noqa: BLE001
            print(f"  {endpoint} -> ERROR {e}")

    if successes == 0:
        print("indexnow: ALL endpoints failed.", file=sys.stderr)
        return 1

    print(f"indexnow: {successes}/{len(ENDPOINTS)} endpoint(s) accepted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
