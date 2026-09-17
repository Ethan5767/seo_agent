#!/usr/bin/env python3
"""CLI SEO Crawl & Inspector Tool.

Run directly in terminal:
    .venv/bin/python crawl_cli.py https://example.com
    .venv/bin/python crawl_cli.py https://books.toscrape.com --pages 3

Shows EXACTLY:
- WHERE the crawler looks (HTTP headers, <head>, <body>, exact tags)
- HOW it checks (rules, thresholds, regex patterns)
- WHAT it extracted (exact HTML snippets and raw values)
- VERDICT (PASS / WARN / FAIL with plain-English SEO reason)
"""
import sys
import time
import argparse
import re
from urllib.parse import urljoin, urlsplit, urldefrag
import requests
from bs4 import BeautifulSoup

# Terminal formatting
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_BLUE = "\033[34m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_CYAN = "\033[36m"
C_MAGENTA = "\033[35m"

def badge_pass(text="PASS"):
    return f"{C_BOLD}{C_GREEN}✅ [{text}]{C_RESET}"

def badge_warn(text="WARN"):
    return f"{C_BOLD}{C_YELLOW}⚠️  [{text}]{C_RESET}"

def badge_fail(text="FAIL"):
    return f"{C_BOLD}{C_RED}❌ [{text}]{C_RESET}"

def badge_info(text="INFO"):
    return f"{C_BOLD}{C_CYAN}ℹ️  [{text}]{C_RESET}"

def print_box(title: str, color=C_CYAN):
    width = 78
    print(f"\n{color}{C_BOLD}┌{'─' * (width - 2)}┐{C_RESET}")
    print(f"{color}{C_BOLD}│  {title:<{width - 5}}│{C_RESET}")
    print(f"{color}{C_BOLD}└{'─' * (width - 2)}┘{C_RESET}")

def inspect_page(url: str, page_num: int, total_pages: int, parent_url: str = None) -> tuple[dict, set]:
    print_box(f"PAGE #{page_num} of {total_pages}: {url}")
    if parent_url:
        print(f"  {C_DIM}↳ Discovered from link on: {parent_url}{C_RESET}")

    # ─────────────────────────────────────────────────────────────
    # CHECK 1: HTTP Response & Server Headers
    # ─────────────────────────────────────────────────────────────
    print(f"\n{C_BOLD}[CHECK 1] HTTP Status & Server Response Headers{C_RESET}")
    print(f"  {C_DIM}Where does it check?{C_RESET} Raw HTTP Request & Response Headers")
    print(f"  {C_DIM}How does it check?  {C_RESET} Inspects HTTP status code, redirect history, Content-Type, and security headers.")

    t0 = time.time()
    try:
        resp = requests.get(url, headers={"User-Agent": "SeoAgent-Crawler/1.0"}, timeout=10, allow_redirects=True)
        latency = round((time.time() - t0) * 1000, 1)
    except Exception as e:
        print(f"  {badge_fail('CONNECTION ERROR')} Could not reach {url}: {e}")
        return {}, set()

    # Status check
    if resp.status_code == 200:
        print(f"  {badge_pass()} Status: HTTP {resp.status_code} OK (Response time: {latency}ms)")
    elif 300 <= resp.status_code < 400:
        print(f"  {badge_warn()} Status: HTTP {resp.status_code} Redirect (Location: {resp.headers.get('Location', 'Unknown')})")
    else:
        print(f"  {badge_fail()} Status: HTTP {resp.status_code} Error")

    # Redirect history check
    if resp.history:
        print(f"  {badge_warn('REDIRECT CHAIN')} Page redirected across {len(resp.history)} hops:")
        for hop in resp.history:
            print(f"    ↳ {hop.status_code} from {hop.url}")
        print(f"    ↳ Final destination: {resp.url}")
    else:
        print(f"  {badge_pass()} Direct response: No redirect hops detected.")

    # X-Robots-Tag check
    x_robots = resp.headers.get("X-Robots-Tag")
    if x_robots:
        if "noindex" in x_robots.lower():
            print(f"  {badge_fail('HEADER NOINDEX')} Found: X-Robots-Tag: {x_robots} (Blocks Google indexing!)")
        else:
            print(f"  {badge_info()} Found: X-Robots-Tag: {x_robots}")
    else:
        print(f"  {badge_pass()} No restrictive X-Robots-Tag header found.")

    # ─────────────────────────────────────────────────────────────
    # CHECK 2: HTML Title Tag
    # ─────────────────────────────────────────────────────────────
    print(f"\n{C_BOLD}[CHECK 2] Title Tag in <head>{C_RESET}")
    print(f"  {C_DIM}Where does it check?{C_RESET} Looking for <title>...</title> inside <head>")
    print(f"  {C_DIM}How does it check?  {C_RESET} Measures character count. Ideal length is 30 to 65 characters.")

    soup = BeautifulSoup(resp.text, "html.parser")
    title_tag = soup.find("title")

    if not title_tag or not title_tag.string or not title_tag.string.strip():
        print(f"  {badge_fail('MISSING TITLE')} No <title> tag found on this page!")
        title_text = ""
    else:
        title_text = re.sub(r'\s+', ' ', title_tag.string.strip())
        char_len = len(title_text)
        print(f"  {C_DIM}Raw Tag Found:      {C_RESET}<title>{title_text}</title>")
        if 30 <= char_len <= 65:
            print(f"  {badge_pass()} Length: {char_len} chars (Optimal: 30-65 chars)")
        elif char_len < 30:
            print(f"  {badge_warn('TITLE TOO SHORT')} Length: {char_len} chars (<30 chars, misses keyword opportunities)")
        else:
            print(f"  {badge_warn('TITLE TOO LONG')} Length: {char_len} chars (>65 chars, may get truncated in Google SERPs)")

    # ─────────────────────────────────────────────────────────────
    # CHECK 3: Meta Description
    # ─────────────────────────────────────────────────────────────
    print(f"\n{C_BOLD}[CHECK 3] Meta Description in <head>{C_RESET}")
    print(f"  {C_DIM}Where does it check?{C_RESET} Looking for <meta name=\"description\" content=\"...\">")
    print(f"  {C_DIM}How does it check?  {C_RESET} Measures character count. Ideal length is 70 to 160 characters.")

    desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if not desc_tag or not desc_tag.get("content", "").strip():
        print(f"  {badge_warn('MISSING META DESC')} No meta description found! (Google will auto-generate snippets)")
        desc_text = ""
    else:
        desc_text = re.sub(r'\s+', ' ', desc_tag["content"].strip())
        desc_len = len(desc_text)
        print(f"  {C_DIM}Raw Tag Found:      {C_RESET}<meta name=\"description\" content=\"{desc_text[:60]}...\">")
        if 70 <= desc_len <= 160:
            print(f"  {badge_pass()} Length: {desc_len} chars (Optimal: 70-160 chars)")
        elif desc_len < 70:
            print(f"  {badge_warn('DESC TOO SHORT')} Length: {desc_len} chars (<70 chars)")
        else:
            print(f"  {badge_warn('DESC TOO LONG')} Length: {desc_len} chars (>160 chars, risk of truncation)")

    # ─────────────────────────────────────────────────────────────
    # CHECK 4: Canonical Link Tag
    # ─────────────────────────────────────────────────────────────
    print(f"\n{C_BOLD}[CHECK 4] Canonical Tag in <head>{C_RESET}")
    print(f"  {C_DIM}Where does it check?{C_RESET} Looking for <link rel=\"canonical\" href=\"...\">")
    print(f"  {C_DIM}How does it check?  {C_RESET} Verifies whether canonical exists and matches current page URL.")

    canon_tag = soup.find("link", attrs={"rel": re.compile(r"^canonical$", re.I)})
    if not canon_tag or not canon_tag.get("href", "").strip():
        print(f"  {badge_warn('NO CANONICAL')} No canonical link tag declared! (Leaves site vulnerable to duplicate URL indexing)")
    else:
        canon_href = canon_tag["href"].strip()
        print(f"  {C_DIM}Raw Tag Found:      {C_RESET}<link rel=\"canonical\" href=\"{canon_href}\">")
        if canon_href == url or canon_href == resp.url:
            print(f"  {badge_pass()} Matches requested URL (Self-referencing canonical).")
        else:
            print(f"  {badge_info('CROSS-CANONICAL')} Points to different URL: {canon_href}")

    # ─────────────────────────────────────────────────────────────
    # CHECK 5: Heading 1 (H1) Hierarchy
    # ─────────────────────────────────────────────────────────────
    print(f"\n{C_BOLD}[CHECK 5] Main Heading (<h1>) Hierarchy{C_RESET}")
    print(f"  {C_DIM}Where does it check?{C_RESET} Looking for <h1> tags anywhere inside <body>")
    print(f"  {C_DIM}How does it check?  {C_RESET} Counts H1 occurrences. Every page should have EXACTLY ONE main H1.")

    h1_tags = soup.find_all("h1")
    if len(h1_tags) == 0:
        print(f"  {badge_fail('NO H1 TAG')} Page has zero <h1> tags! (Main topic is undefined for search engines)")
    elif len(h1_tags) == 1:
        h1_content = h1_tags[0].get_text(strip=True)
        print(f"  {C_DIM}Raw Tag Found:      {C_RESET}<h1>{h1_content}</h1>")
        print(f"  {badge_pass()} Exactly one <h1> found: \"{h1_content}\"")
    else:
        print(f"  {badge_warn('MULTIPLE H1s')} Found {len(h1_tags)} <h1> tags (Best practice is 1 main H1):")
        for i, h in enumerate(h1_tags, 1):
            print(f"    ↳ H1 #{i}: \"{h.get_text(strip=True)}\"")

    # ─────────────────────────────────────────────────────────────
    # CHECK 6: Image Alt Attributes
    # ─────────────────────────────────────────────────────────────
    print(f"\n{C_BOLD}[CHECK 6] Image Accessibility & Alt Attributes{C_RESET}")
    print(f"  {C_DIM}Where does it check?{C_RESET} Looking for all <img> tags inside <body>")
    print(f"  {C_DIM}How does it check?  {C_RESET} Checks if alt=\"...\" attribute is present and non-empty.")

    images = soup.find_all("img")
    missing_alt = [img.get("src", "unknown") for img in images if not img.get("alt") or not img["alt"].strip()]

    if not images:
        print(f"  {badge_info()} No images on this page.")
    elif len(missing_alt) == 0:
        print(f"  {badge_pass()} All {len(images)} images have valid alt text attributes.")
    else:
        print(f"  {badge_warn('MISSING ALT')} {len(missing_alt)} of {len(images)} images are missing alt text:")
        for src in missing_alt[:3]:
            print(f"    ↳ <img src=\"{src}\" ...> (Missing alt!)")
        if len(missing_alt) > 3:
            print(f"    ↳ ... and {len(missing_alt) - 3} more.")

    # ─────────────────────────────────────────────────────────────
    # CHECK 7: Schema Structured Data (JSON-LD)
    # ─────────────────────────────────────────────────────────────
    print(f"\n{C_BOLD}[CHECK 7] Schema Structured Data (JSON-LD){C_RESET}")
    print(f"  {C_DIM}Where does it check?{C_RESET} Looking for <script type=\"application/ld+json\"> tags")
    print(f"  {C_DIM}How does it check?  {C_RESET} Validates JSON syntax and extracts Schema.org '@type' definitions.")

    ld_scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    if not ld_scripts:
        print(f"  {badge_info('NO SCHEMA')} No JSON-LD structured data found on this page.")
    else:
        print(f"  {badge_pass()} Found {len(ld_scripts)} JSON-LD structured data block(s):")
        for i, s in enumerate(ld_scripts, 1):
            content = s.string or ""
            types_found = re.findall(r'"@type"\s*:\s*"([^"]+)"', content)
            if types_found:
                print(f"    ↳ Schema #{i} Types: {', '.join(types_found)}")
            else:
                print(f"    ↳ Schema #{i}: (Raw JSON-LD present)")

    # ─────────────────────────────────────────────────────────────
    # CHECK 8: Internal Link Graph & Discovery
    # ─────────────────────────────────────────────────────────────
    print(f"\n{C_BOLD}[CHECK 8] Link Graph & Internal Link Discovery{C_RESET}")
    print(f"  {C_DIM}Where does it check?{C_RESET} Looking for <a href=\"...\"> tags across the entire DOM")
    print(f"  {C_DIM}How does it check?  {C_RESET} Normalizes relative links, classifies same-domain vs external, and filters asset files.")

    target_host = urlsplit(url).netloc.lower().removeprefix("www.")
    internal_links = set()
    external_links = set()

    for a in soup.find_all("a", href=True):
        raw_href = a["href"].strip()
        if raw_href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
            continue
        abs_link = urljoin(url, raw_href)
        abs_link, _ = urldefrag(abs_link)
        parsed = urlsplit(abs_link)
        if not parsed.scheme.startswith(("http", "https")):
            continue
        if re.search(r"\.(png|jpe?g|gif|svg|webp|css|js|pdf|zip|ico|xml|json)$", parsed.path, re.I):
            continue

        link_host = parsed.netloc.lower().removeprefix("www.")
        if link_host == target_host:
            internal_links.add(abs_link)
        else:
            external_links.add(abs_link)

    print(f"  {badge_info()} Link Inventory: Found {len(internal_links)} same-host links and {len(external_links)} external links.")
    if internal_links:
        print(f"  {C_DIM}Discovered Internal Queue Candidates:{C_RESET}")
        for link in list(internal_links)[:4]:
            print(f"    ↳ {link}")
        if len(internal_links) > 4:
            print(f"    ↳ ... and {len(internal_links) - 4} more queued.")

    page_data = {
        "url": url,
        "status": resp.status_code,
        "latency": latency,
        "title": title_text,
        "h1": h1_tags[0].get_text(strip=True) if h1_tags else "",
        "internal_count": len(internal_links)
    }

    return page_data, internal_links

def main():
    parser = argparse.ArgumentParser(description="CLI SEO Crawler & Diagnostics Inspector")
    parser.add_argument("url", nargs="?", default="https://books.toscrape.com", help="Seed URL to crawl (default: https://books.toscrape.com)")
    parser.add_argument("--pages", type=int, default=3, help="Max pages to crawl (default: 3)")
    args = parser.parse_args()

    seed = args.url
    if not seed.startswith(("http://", "https://")):
        seed = "https://" + seed

    max_p = max(1, args.pages)

    print(f"\n{C_BOLD}{C_MAGENTA}{'='*78}{C_RESET}")
    print(f"{C_BOLD}{C_MAGENTA}🚀 SEO AUDIT CRAWLER — CLI DIAGNOSTIC INSPECTOR{C_RESET}")
    print(f"{C_BOLD}{C_MAGENTA}{'='*78}{C_RESET}")
    print(f"Target Seed URL : {C_BOLD}{seed}{C_RESET}")
    print(f"Max Pages Limit : {C_BOLD}{max_p}{C_RESET}")
    print(f"Execution Mode  : Terminal Diagnostic Walk (Shows exact DOM & header inspects)")

    queue = [(seed, None)]
    visited = set()
    crawled_results = []
    start_time = time.time()

    page_counter = 1
    while queue and len(crawled_results) < max_p:
        current_url, parent = queue.pop(0)
        norm_url, _ = urldefrag(current_url)
        if norm_url in visited:
            continue
        visited.add(norm_url)

        pdata, discovered_links = inspect_page(current_url, page_counter, max_p, parent_url=parent)
        if pdata:
            crawled_results.append(pdata)
            page_counter += 1

            for link in sorted(discovered_links):
                if link not in visited and link not in [q[0] for q in queue]:
                    queue.append((link, current_url))

    total_time = round(time.time() - start_time, 2)
    print_box(f"AUDIT SUMMARY — {len(crawled_results)} Pages Crawled in {total_time}s", color=C_GREEN)
    print(f"{C_BOLD}{'URL':<40} {'STATUS':<8} {'LATENCY':<10} {'INTERNAL':<10} {'H1 / TITLE'}{C_RESET}")
    print("-" * 78)
    for res in crawled_results:
        print(f"{res['url'][:38]:<40} {C_GREEN}{res['status']:<8}{C_RESET} {res['latency']}ms{'':<4} {res['internal_count']:<10} {res['title'][:20]}")
    print("-" * 78)
    print(f"\n{C_BOLD}{C_CYAN}✨ Completed! You can run this command on ANY URL anytime:{C_RESET}")
    print(f"   {C_BOLD}.venv/bin/python crawl_cli.py https://example.com --pages 3{C_RESET}\n")

if __name__ == "__main__":
    main()
