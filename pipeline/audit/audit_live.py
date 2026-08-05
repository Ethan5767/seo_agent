#!/usr/bin/env python3
"""Run full SEO scorecard against live URLs. Writes pass files + summary.

Usage: python3 audit-live.py [PROJECT_DIR] [url1] [url2] ...
       URLs can be absolute or site-relative paths.
Exit 0 = all pass. Non-zero = failures logged.
"""
import sys, re, time
from datetime import date
from pathlib import Path
from pipeline.lib.common import load_config, audit_log_dir, curl, curl_status


def audit_url(url: str, cfg: dict) -> dict:
    html = curl(url)
    checks = {}
    # 1. status
    checks["status_200"] = curl_status(url) == 200
    # 2. title
    t = re.search(r"<title[^>]*>([^<]+)</title>", html)
    title = t.group(1) if t else ""
    checks["title_present"] = bool(title)
    checks["title_length_30_60"] = 30 <= len(title) <= 60
    # 3. meta desc
    d = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html)
    desc = d.group(1) if d else ""
    checks["desc_present"] = bool(desc)
    checks["desc_length_120_160"] = 120 <= len(desc) <= 160
    # 4. H1 (count opening tags — handles nested spans inside h1)
    h1s = re.findall(r"<h1[^>]*>", html)
    checks["h1_exactly_one"] = len(h1s) == 1
    # Extract H1 text for downstream checks (strips nested tags)
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    h1_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h1_match.group(1))).strip() if h1_match else ""
    # 5. canonical
    c = re.search(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"', html)
    checks["canonical_self_ref"] = bool(c) and url.rstrip("/") in c.group(1)
    # 6. noindex absent
    checks["no_noindex"] = "noindex" not in html.lower()
    # 7. OG image
    checks["og_image"] = bool(re.search(r'<meta[^>]*property="og:image"', html))
    # 8. schema
    types = set(re.findall(r'"@type":"([^"]+)"', html))
    required_schema = cfg.get("schema_type", "LocalBusiness")
    checks["schema_business"] = required_schema in types
    checks["schema_faq"] = "FAQPage" in types
    checks["schema_breadcrumb"] = "BreadcrumbList" in types
    # 9. pricing / forbidden
    # Strip script blocks (Next.js RSC payload tokens like $1, $L8, $undefined trigger false positives),
    # then strip priceRange schema literals, then run forbidden_phrases regexes.
    body = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'"priceRange":"[^"]*"', '', body)
    forbidden_hits = 0
    forbidden_matches = []
    for rule in cfg.get("forbidden_phrases", []):
        m = re.search(rule["pattern"], body)
        if m:
            forbidden_hits += 1
            forbidden_matches.append((rule["pattern"], m.group()[:80]))
    checks["no_forbidden_phrases"] = forbidden_hits == 0
    # 10. phone
    tel = cfg["nap"]["phone_tel"]
    phone_display = cfg["nap"]["phone"]
    checks["tel_link"] = f"tel:{tel}" in html
    checks["phone_visible"] = phone_display in html
    # 11. GA4
    ga = cfg.get("ga4_id")
    checks["ga4_present"] = bool(ga and ga in html)
    # 12. images with alt
    imgs = re.findall(r"<img[^>]*>", html)
    missing_alt = [i for i in imgs if not re.search(r'\salt="[^"]+"', i)]
    checks["images_have_alt"] = len(imgs) > 0 and len(missing_alt) == 0
    # 13. word count
    text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    word_count = len(text.split())
    checks["words_500_plus"] = word_count >= 500
    return {"checks": checks, "title": title, "desc": desc, "words": word_count, "schema_types": sorted(types)}


def main():
    if len(sys.argv) < 3:
        print("Usage: audit-live.py [PROJECT_DIR] [url...]", file=sys.stderr); sys.exit(1)
    project = Path(sys.argv[1])
    url_args = sys.argv[2:]
    cfg = load_config(str(project))
    domain = cfg["domain"]
    urls = []
    for u in url_args:
        if u.startswith("http"): urls.append(u.rstrip("/") + "/")
        else: urls.append(f"https://{domain}/{u.strip('/')}/")

    log_dir = audit_log_dir(str(project), date.today().isoformat())
    results, failures = [], []
    for url in urls:
        r = audit_url(url, cfg)
        r["url"] = url
        results.append(r)
        fails = [k for k, v in r["checks"].items() if not v]
        if fails: failures.append((url, fails))

    summary = ["# Live Audit — " + date.today().isoformat(), ""]
    summary.append(f"URLs tested: {len(urls)}")
    summary.append(f"Pass: {len(urls) - len(failures)} | Fail: {len(failures)}")
    summary.append("")
    for r in results:
        pass_count = sum(1 for v in r["checks"].values() if v)
        total = len(r["checks"])
        summary.append(f"## {r['url']}")
        summary.append(f"{pass_count}/{total} | {r['words']}w | title={len(r['title'])}c | desc={len(r['desc'])}c")
        for k, v in r["checks"].items():
            summary.append(f"  {'✓' if v else '✗'} {k}")
        summary.append("")
    (log_dir / "audit-live.md").write_text("\n".join(summary))

    for url, fails in failures:
        print(f"[FAIL] {url}: {', '.join(fails)}")
    if failures:
        print(f"\n{len(failures)} URLs have failures. See {log_dir}/audit-live.md")
        sys.exit(4)
    print(f"\n[OK] {len(urls)}/{len(urls)} URLs pass all checks. See {log_dir}/audit-live.md")


if __name__ == "__main__":
    main()
