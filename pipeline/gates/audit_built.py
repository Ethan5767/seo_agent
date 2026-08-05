#!/usr/bin/env python3
"""Audit the built output after build — full 30-point per-page checklist.

Checks per-page HTML + cross-file repo state (sitemap, llms, routes, prerender).

Usage: python3 audit-built.py [PROJECT_DIR] [BUILD_DIR] [url1] [url2] ...
"""
import sys, re
from datetime import date
from pathlib import Path
from pipeline.lib import baseline as bl
from pipeline.lib.common import load_config, audit_log_dir

GATE = "audit_built"


class _Args:
    """audit-built predates argparse in this suite and reads sys.argv directly.
    Rather than restructure its CLI, pull the two baseline flags out of argv and
    hand the rest to the existing positional parsing untouched."""

    def __init__(self, argv):
        self.baseline = None
        self.emit_findings = None
        self.rest = []
        i = 0
        while i < len(argv):
            a = argv[i]
            if a in ("--baseline", "--emit-findings") and i + 1 < len(argv):
                setattr(self, a[2:].replace("-", "_"), argv[i + 1])
                i += 2
                continue
            if a.startswith("--baseline=") or a.startswith("--emit-findings="):
                k, v = a.split("=", 1)
                setattr(self, k[2:].replace("-", "_"), v)
                i += 1
                continue
            self.rest.append(a)
            i += 1


def read_built(base: Path, url_path: str) -> str:
    # Normalize a full <loc> URL (https://host/path/) to a root-relative path so
    # quality-gate.yml can feed the raw sitemap <loc> values (Defect #1a, 2026-07-19).
    up = re.sub(r"^https?://[^/]+", "", url_path)
    candidates = [
        base / up.strip("/") / "index.html",
        base / (up.strip("/") + ".html"),
    ]
    for c in candidates:
        if c.exists(): return c.read_text()
    return ""


def strip_to_text(html: str) -> str:
    text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def audit_page(html: str, url: str, cfg: dict, project: Path, build: Path, all_built_texts: dict) -> dict:
    checks = {}
    t = re.search(r"<title[^>]*>([^<]+)</title>", html)
    title = (t.group(1) if t else "").strip()
    d = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html)
    desc = d.group(1) if d else ""
    # Match H1 even when it contains nested elements (spans, etc.) — common in modern Tailwind layouts.
    h1_matches = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    h1s = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m)).strip() for m in h1_matches]
    canon = re.search(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"', html)
    schema_types = set(re.findall(r'"@type":"([^"]+)"', html))

    # Meta + structure (8)
    # Bands come from the Content Team Operating Standard (2026-07-29) §04 Meta
    # Tags: title 50-60, meta description 130-150, both "never outside". They were
    # 30-60 and 120-160, which passed copy the published standard rejects and — the
    # worse direction — meant a writer following the standard could still be flagged.
    # Overridable per client via a `meta:` config block; the standard is the default.
    _meta = cfg.get("meta") if isinstance(cfg.get("meta"), dict) else {}
    t_lo, t_hi = _meta.get("title_min", 50), _meta.get("title_max", 60)
    d_lo, d_hi = _meta.get("desc_min", 130), _meta.get("desc_max", 150)
    checks[f"1_title_{t_lo}_{t_hi}"] = t_lo <= len(title) <= t_hi
    checks[f"2_desc_{d_lo}_{d_hi}"] = d_lo <= len(desc) <= d_hi
    expected = url if url.startswith("http") else f"https://{cfg['domain']}{url}"
    checks["3_canonical_matches_url"] = bool(canon) and expected.rstrip("/") in canon.group(1)
    checks["4_exactly_one_h1"] = len(h1s) == 1
    # H hierarchy (no skip from H1 → H3)
    all_h = re.findall(r"<h([1-6])[^>]*>", html)
    skip = False
    for i in range(1, len(all_h)):
        if int(all_h[i]) > int(all_h[i-1]) + 1:
            skip = True; break
    checks["5_heading_hierarchy"] = not skip
    checks["6_og_image"] = bool(re.search(r'property="og:image"', html))
    checks["7_twitter_card"] = bool(re.search(r'name="twitter:card"', html))
    checks["8_no_noindex"] = "noindex" not in html.lower()

    # Content (6)
    text = strip_to_text(html)
    words = text.split()
    first_100 = " ".join(words[:100]).lower()
    # Primary keyword detection: use the city/service keywords from target_keywords or URL slug.
    # ANY URL keyword counts as a match — fixes nested-URL bug where /charlotte-nc/matthews/
    # picks "charlotte" as primary, but H1 correctly mentions "matthews" (the deeper segment).
    # Both are valid local keywords for that page.
    url_keywords = [k for k in re.findall(r"[a-z]{4,}", url)
                    if k not in ("html", "index", "https", "http", "www")]
    h1_text = (h1s[0] if h1s else "").lower()
    checks["9_keyword_in_h1"] = bool(url_keywords) and any(k in h1_text for k in url_keywords)
    checks["10_keyword_in_first_100"] = bool(url_keywords) and any(k in first_100 for k in url_keywords)
    # Forbidden phrases (strip schema priceRange convention first).
    # Use `text` (script-stripped) instead of full `html` so Next.js framework
    # serialization markers like $1, $L1, $undefined inside <script> tags do
    # not trigger false positives on the \$[0-9] dollar-amount pattern.
    body = re.sub(r'"priceRange":"[^"]*"', '', text)
    forbidden_hits = [r["pattern"] for r in cfg.get("forbidden_phrases", []) if re.search(r["pattern"], body)]
    checks["11_no_forbidden_phrases"] = len(forbidden_hits) == 0
    # Em dash in body copy (allow in testimonial quotes)
    body_no_quotes = re.sub(r'"[^"]{20,400}"', '', text)
    checks["12_no_em_dashes"] = "—" not in body_no_quotes
    checks["13_words_500_plus"] = len(words) >= 500
    checks["14_size_5kb_plus"] = len(html) >= 5000

    # Schema (6)
    checks["15_graph_format"] = '"@graph"' in html
    checks["16_business_schema"] = cfg.get("schema_type", "LocalBusiness") in schema_types
    checks["17_service_schema"] = "Service" in schema_types
    checks["18_breadcrumb_schema"] = "BreadcrumbList" in schema_types
    q_count = len(re.findall(r'"@type":"Question"', html))
    checks["19_faq_4plus"] = q_count >= 4
    # FAQ answer length. The Content Team Operating Standard (2026-07-29) §02
    # specifies "40 to 60 words each. Two to three lines per answer." This gate
    # used 50-200, which contradicted the published standard in BOTH directions:
    # a compliant 45-word answer FAILED, while a 150-word answer PASSED despite
    # being 2.5x the standard's ceiling. Writers following the rules must not be
    # flagged by the gate that enforces them.
    _faq = cfg.get("faq") if isinstance(cfg.get("faq"), dict) else {}
    f_lo, f_hi = _faq.get("answer_words_min", 40), _faq.get("answer_words_max", 60)
    faq_answers = re.findall(r'"acceptedAnswer":\s*\{[^}]*"text":\s*"([^"]{20,2000})"', html)
    key = f"19b_faq_answers_{f_lo}_{f_hi}w"
    if faq_answers:
        answer_word_counts = [len(a.split()) for a in faq_answers]
        checks[key] = all(f_lo <= w <= f_hi for w in answer_word_counts)
    else:
        checks[key] = True  # no FAQ detected, skip
    gbp = cfg.get("gbp_url", "")
    checks["20_aggregate_rating_gbp"] = "AggregateRating" in schema_types and (not gbp or gbp in html)

    # areaServed geometry (T13). Service-area businesses (roofers, HVAC, etc.) must
    # expose an areaServed on the LocalBusiness/RoofingContractor node so AI search
    # can answer "do you serve <city>?". Only BLOCKS when the client opts in via
    # schema.area_served_required (or a top-level area_served_required flag) — absent
    # keys default False, so this never KeyErrors and never red-gates a client that
    # has not adopted the requirement. When present, a bare-string list PASSES but
    # WARNS (run-#1 safety); GeoCircle/GeoShape/State/City geometry is the clean form.
    warnings = []
    schema_cfg = cfg.get("schema") if isinstance(cfg.get("schema"), dict) else {}
    area_required = bool(schema_cfg.get("area_served_required", cfg.get("area_served_required", False)))
    # Collect every areaServed value blob on the page (multiple nodes possible).
    area_blobs = re.findall(r'"areaServed"\s*:\s*(\[.*?\]|\{.*?\}|"[^"]*")', html, re.DOTALL)
    area_present = False
    for blob in area_blobs:
        b = blob.strip()
        if b in ("[]", '""', "{}"):
            continue
        area_present = True
    has_geometry = any(
        re.search(r'"@type"\s*:\s*"(GeoCircle|GeoShape|State|City|AdministrativeArea|Country)"', b)
        for b in area_blobs
    )
    if area_required:
        checks["31_area_served_present"] = area_present
        if area_present and not has_geometry:
            warnings.append("areaServed is a bare string/list (no GeoCircle/GeoShape/State/City "
                            "geometry) — passes for now, prefer geometry objects.")
    else:
        checks["31_area_served_present"] = True  # not required for this client — skip
        if area_blobs and area_present and not has_geometry:
            warnings.append("areaServed present as bare string/list; add GeoCircle/GeoShape/State/"
                            "City geometry for stronger service-area schema (advisory).")

    # Conversion + links (6)
    tel = cfg["nap"]["phone_tel"]
    checks["21_tel_link_present"] = f"tel:{tel}" in html
    phone_display = cfg["nap"]["phone"]
    # CTA sections: count anchor elements with tel: or "contact" or "quote" — rough but useful
    ctas = len(re.findall(r'<a[^>]*(?:tel:|/contact|quote|Get\s+[A-Z])', html, re.I))
    checks["22_cta_present"] = ctas >= 3
    internal = len(re.findall(r'href="/[^"#]', html))
    checks["23_internal_links_2plus"] = internal >= 2
    imgs = re.findall(r"<img[^>]*>", html)
    bad_alt = [i for i in imgs if not re.search(r'\salt="[^"]{10,125}"', i)]
    checks["24_img_alt_10_125"] = len(imgs) > 0 and len(bad_alt) == 0
    form_email = cfg.get("form_endpoint", "")
    form_tags = re.findall(r'<form[^>]*>', html)
    # Modern React/JS-handled forms commonly omit the action attribute — submission goes
    # through a fetch handler in the bundle. Treat action-less forms as JS-handled (correct).
    forms_with_action = [t for t in form_tags if re.search(r'\saction=', t)]
    if forms_with_action and form_email and form_email != "TODO":
        checks["25_form_endpoint_correct"] = any(form_email in tag for tag in forms_with_action)
    else:
        checks["25_form_endpoint_correct"] = True  # no forms, action-less (JS), or no endpoint configured
    ga = cfg.get("ga4_id", "")
    checks["26_ga4_tag"] = bool(ga and ga != "TODO" and ga in html)

    # Infrastructure (4) — cross-file checks
    repo = cfg.get("repo", {})
    route_file = project / repo.get("route_file", "src/AppRoutes.tsx")
    sitemap_file = project / repo.get("sitemap", "public/sitemap.xml")
    llms_file = project / repo.get("llms_txt", "public/llms.txt")
    prerender_file = project / (repo.get("prerender_config") or "prerender.mjs")

    url_path = url if url.startswith("/") else "/" + url.split("/", 3)[-1]
    url_path = url_path if url_path.endswith("/") else url_path + "/"
    url_nopath = url_path.rstrip("/")

    # Next.js App Router uses dynamic routes (e.g. app/[city]/[service]/page.tsx) — the URL
    # is not a literal string in the route file. For App Router, route presence is proven
    # by the file existing in the build output (we already passed `read_built`).
    framework = repo.get("framework", "")
    nextjs_app = "next" in framework or "app-router" in framework
    if nextjs_app:
        checks["27_route_wired"] = True  # presence in build output is sufficient proof
    elif route_file.exists():
        rt = route_file.read_text()
        checks["27_route_wired"] = url_nopath in rt or url_path in rt
    else:
        checks["27_route_wired"] = False

    # Prefer a real built XML sitemap over a generator SOURCE file (Defect #1b,
    # 2026-07-19): repo.sitemap may point at src/app/sitemap.ts (the Next generator
    # the XML is produced from at build) — only trust it when it's an actual .xml.
    built_sitemap = build / "sitemap.xml"
    if sitemap_file.exists() and sitemap_file.suffix == ".xml":
        sm = sitemap_file.read_text()
        full = f"https://{cfg['domain']}{url_path}"
        checks["28_in_sitemap_recent"] = full.rstrip("/") in sm or full in sm
    elif built_sitemap.exists():
        sm = built_sitemap.read_text()
        full = f"https://{cfg['domain']}{url_path}".rstrip("/")
        checks["28_in_sitemap_recent"] = full in sm or full + "/" in sm
    elif nextjs_app:
        checks["28_in_sitemap_recent"] = True  # generated at build, not present pre-build
    else:
        checks["28_in_sitemap_recent"] = False

    if llms_file.exists():
        ll = llms_file.read_text()
        checks["29_in_llms"] = url_path in ll or url_nopath in ll
    else:
        checks["29_in_llms"] = True  # llms.txt optional for some clients

    if prerender_file.exists():
        pr = prerender_file.read_text()
        # vite prerender uses quoted paths; nextjs auto-generates — skip check
        if repo.get("framework") == "nextjs-app-router":
            checks["30_prerender_wired"] = True
        else:
            checks["30_prerender_wired"] = url_nopath in pr or url_path in pr
    else:
        checks["30_prerender_wired"] = True  # not applicable

    return {"checks": checks, "title": title, "desc": desc, "words": len(words),
            "schema_types": sorted(schema_types), "forbidden_hits": forbidden_hits,
            "warnings": warnings, "text": text}


def main():
    args = _Args(sys.argv[1:])
    if len(args.rest) < 3:
        print("Usage: audit-built.py [PROJECT_DIR] [BUILD_DIR] [url...] "
              "[--baseline PATH]", file=sys.stderr); sys.exit(1)
    project = Path(args.rest[0])
    build = Path(args.rest[1])
    urls = [u if u.endswith("/") else u + "/" for u in args.rest[2:]]
    cfg = load_config(str(project))
    log = audit_log_dir(str(project), date.today().isoformat())

    # First pass: gather all built texts for cross-page uniqueness
    all_texts = {}
    for url in urls:
        html = read_built(build, url)
        if html: all_texts[url] = strip_to_text(html).lower()

    results, failures, titles, descs = [], [], [], []
    for url in urls:
        html = read_built(build, url)
        if not html:
            failures.append((url, ["file_not_found"])); continue
        r = audit_page(html, url, cfg, project, build, all_texts)
        r["url"] = url
        # Cross-page uniqueness via 5-gram overlap. Word-set overlap was naive — common
        # Tailwind chrome + brand text drove 95%+ for any sibling spoke page on a
        # programmatic SEO site even when actual phrase-level content differed.
        page_text = all_texts.get(url, "")
        sibling_overlap_max = 0
        if page_text:
            pw = page_text.split()
            page_5g = set(' '.join(pw[i:i+5]) for i in range(len(pw) - 4))
            if page_5g:
                for other_url, other_text in all_texts.items():
                    if other_url == url or not other_text: continue
                    ow = other_text.split()
                    other_5g = set(' '.join(ow[i:i+5]) for i in range(len(ow) - 4))
                    if not other_5g: continue
                    overlap = len(page_5g & other_5g) / len(page_5g)
                    sibling_overlap_max = max(sibling_overlap_max, overlap)
        # Hub-spoke programmatic SEO intentionally shares Service template content across cities.
        topology = cfg.get("topology", "")
        threshold = 0.90 if "hub-spoke" in topology else 0.60
        r["checks"]["14b_uniqueness_vs_siblings"] = sibling_overlap_max <= threshold
        results.append(r)
        titles.append(r["title"]); descs.append(r["desc"])
        fails = [k for k, v in r["checks"].items() if not v]
        if fails: failures.append((url, fails))

    uniq_titles = len(set(titles)) == len(titles)
    uniq_descs = len(set(descs)) == len(descs)

    # Fingerprint on (gate, check key, page URL). The URL is normalized to a
    # site-relative path so a domain or scheme change in the sitemap does not
    # invalidate the whole baseline. Nothing measured (word counts, title lengths,
    # overlap ratios) enters the fingerprint. The two site-wide uniqueness checks
    # have no single page to blame, so they are located at "(site)".
    findings = []
    for url, fails in failures:
        loc = re.sub(r"^https?://[^/]+", "", url) or "/"
        for k in fails:
            findings.append(bl.Finding(GATE, k, loc))
    if not uniq_titles:
        findings.append(bl.Finding(GATE, "uniq_titles", "(site)",
                                   detail=f"{len(set(titles))}/{len(titles)} distinct"))
    if not uniq_descs:
        findings.append(bl.Finding(GATE, "uniq_descs", "(site)",
                                   detail=f"{len(set(descs))}/{len(descs)} distinct"))

    verdict, early = bl.resolve(GATE, findings, args)
    if early is not None:
        sys.exit(early)

    out = [f"# Built Audit — {date.today().isoformat()}", ""]
    out.append(f"Config: {cfg['client']} | Pages tested: {len(urls)}")
    out.append(f"Pass: {len(urls)-len(failures)} | Fail: {len(failures)}")
    out.append(f"Title uniqueness: {'PASS' if uniq_titles else 'FAIL'} ({len(set(titles))}/{len(titles)})")
    out.append(f"Desc uniqueness:  {'PASS' if uniq_descs else 'FAIL'} ({len(set(descs))}/{len(descs)})")
    out.append("")
    for r in results:
        p = sum(1 for v in r["checks"].values() if v)
        out.append(f"## {r['url']}  {p}/{len(r['checks'])}  words={r['words']}")
        for k, v in r["checks"].items():
            out.append(f"  {'PASS' if v else 'FAIL'}  {k}")
        if r["forbidden_hits"]:
            out.append(f"  forbidden matches: {r['forbidden_hits']}")
        for w in r.get("warnings", []):
            out.append(f"  WARN  {w}")
        out.append("")
    (log / "audit-built.md").write_text("\n".join(out))

    if args.baseline:
        verdict.report()
    if verdict.blocking:
        label = "NEW " if args.baseline else ""
        n_pages = len({f.location for f in verdict.blocking})
        print(f"[FAIL] {len(verdict.blocking)} {label}finding(s) across {n_pages} page(s). "
              f"uniq_titles={uniq_titles} uniq_descs={uniq_descs}")
        by_page = {}
        for f in verdict.blocking:
            by_page.setdefault(f.location, []).append(f.code)
        for loc in sorted(by_page):
            print(f"  {loc}: {by_page[loc][:10]}")
        sys.exit(5)
    if args.baseline:
        print(f"[OK] no new audit-built findings ({len(verdict.preexisting)} pre-existing "
              f"accepted as legacy debt). See {log}/audit-built.md")
        return
    print(f"[OK] All {len(urls)} built pages pass 30-point checklist. See {log}/audit-built.md")


if __name__ == "__main__":
    main()
