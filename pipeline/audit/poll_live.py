#!/usr/bin/env python3
"""Poll a URL until its HTML contains a string. For Cloudflare-rebuild waits.

Usage: python3 poll-live.py [URL] [STRING] [max_seconds]
"""
import sys, time
from pipeline.lib.common import curl


def main():
    if len(sys.argv) < 3:
        print("Usage: poll-live.py [URL] [STRING] [max_seconds=300]", file=sys.stderr); sys.exit(1)
    url, needle = sys.argv[1], sys.argv[2]
    max_s = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    start = time.time()
    attempt = 0
    while time.time() - start < max_s:
        attempt += 1
        html = curl(url)
        if needle in html:
            print(f"[OK] Live after {int(time.time()-start)}s ({attempt} attempts)"); return
        time.sleep(15)
    print(f"[TIMEOUT] {needle!r} not found after {max_s}s"); sys.exit(8)


if __name__ == "__main__":
    main()
