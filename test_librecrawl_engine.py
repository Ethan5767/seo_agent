#!/usr/bin/env python3
"""LibreCrawl Core SEO Engine — Complete Multi-Page Crawler & System Auditor.

Features:
1. Robots.txt audit (full directives, sitemap declarations, disallow rules).
2. Complete Sitemap discovery & full URL extraction (zero truncation).
3. Dynamic multi-page concurrent crawl loop across site pages (sitemap + discovered internal links).
4. Deep page-level DOM extraction (Title, Meta, H1/H2, Canonical, Links, Images, Schema).
5. LibreCrawl IssueDetector audit (100+ rules across 12 categories).
6. Cross-page duplicate title/description detection (IssueDetector.detect_duplication_issues).
7. Orphan page discovery (pages in sitemap without inbound internal links).
8. Real-time untruncated system logs streamed to stdout and saved to librecrawl_system.log.
"""
import sys
import os
import time
import argparse
import threading
from queue import Queue, Empty
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup

# Add LibreCrawl src to Python path
sys.path.insert(0, os.path.abspath("vendor/LibreCrawl/src"))

from core.seo_extractor import SEOExtractor
from core.issue_detector import IssueDetector
from core.sitemap_parser import SitemapParser

# Terminal Colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_CYAN = "\033[36m"
C_MAGENTA = "\033[35m"
C_BLUE = "\033[34m"

class DualLogger:
    """Writes formatted output to both stdout (with colors) and a log file (plain text)."""
    def __init__(self, filepath="librecrawl_system.log"):
        self.filepath = filepath
        self.file = open(filepath, "w", encoding="utf-8")
        self.lock = threading.Lock()

    def log(self, text="", file_text=None):
        with self.lock:
            print(text)
            sys.stdout.flush()
            if file_text is None:
                import re
                file_text = re.sub(r'\033\[[0-9;]*m', '', text)
            self.file.write(file_text + "\n")
            self.file.flush()

    def close(self):
        self.file.close()

def parse_args():
    parser = argparse.ArgumentParser(description="LibreCrawl Open-Source SEO Engine Live Auditor")
    parser.add_argument("url", nargs="?", default="https://www.oriendainternationalhospital.com.kh/en",
                        help="Target start URL (default: https://www.oriendainternationalhospital.com.kh/en)")
    parser.add_argument("--pages", "-n", default="50",
                        help="Number of pages to crawl: e.g. 20, 50, 100, 606, 800, or 'all' (default: 50)")
    parser.add_argument("--workers", "-w", type=int, default=8,
                        help="Concurrent worker threads (default: 8)")
    parser.add_argument("--timeout", "-t", type=int, default=12,
                        help="HTTP request timeout in seconds (default: 12)")
    parser.add_argument("--check-images", action="store_true",
                        help="Perform live HTTP HEAD checks on all page images to detect broken images (takes longer)")
    parser.add_argument("--log", default="librecrawl_system.log",
                        help="Output log file path (default: librecrawl_system.log)")
    return parser.parse_args()

def extract_clean_links(soup, page_url, base_domain):
    """Extract all valid internal URLs from page DOM to discover new paths."""
    internal_links = set()
    base_clean = base_domain.replace("www.", "").lower()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full_url = urljoin(page_url, href)
        full_url = full_url.split("#")[0]
        parsed = urlparse(full_url)
        if parsed.scheme in ("http", "https"):
            dom_clean = parsed.netloc.replace("www.", "").lower()
            if dom_clean == base_clean:
                internal_links.add(full_url)
    return internal_links

def main():
    args = parse_args()
    logger = DualLogger(args.log)

    target_url = args.url
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    parsed_target = urlparse(target_url)
    base_origin = f"{parsed_target.scheme}://{parsed_target.netloc}"
    base_domain = parsed_target.netloc

    logger.log(f"\n{C_BOLD}{C_MAGENTA}{'='*90}{C_RESET}")
    logger.log(f"{C_BOLD}{C_MAGENTA}🔥 LIBRECRAWL CORE SEO ENGINE — COMPLETE MULTI-PAGE AUDIT & SYSTEM LOG{C_RESET}")
    logger.log(f"{C_BOLD}{C_MAGENTA}{'='*90}{C_RESET}")
    logger.log(f"Target URL   : {C_BOLD}{target_url}{C_RESET}")
    logger.log(f"Base Domain  : {C_BOLD}{base_domain}{C_RESET}")
    logger.log(f"Crawl Limit  : {C_BOLD}{args.pages} pages{C_RESET}")
    logger.log(f"Workers      : {C_BOLD}{args.workers} concurrent threads{C_RESET}")
    logger.log(f"System Log   : {C_BOLD}{os.path.abspath(args.log)}{C_RESET}")
    logger.log(f"{C_DIM}Engine       : LibreCrawl Open-Source (Screaming Frog Core in Python){C_RESET}")
    logger.log(f"{C_BOLD}{C_MAGENTA}{'='*90}{C_RESET}\n")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "LibreCrawl-SEO-Auditor/1.0 (Compatible; ScreamingFrogSEOSpider)"
    })

    # ─────────────────────────────────────────────────────────────
    # STEP 1: ROBOTS.TXT AUDIT
    # ─────────────────────────────────────────────────────────────
    logger.log(f"{C_BOLD}{C_BLUE}[STEP 1/4] ROBOTS.TXT DISCOVERY & DIRECTIVES AUDIT{C_RESET}")
    robots_url = f"{base_origin}/robots.txt"
    robots_content = ""
    try:
        r_resp = session.get(robots_url, timeout=args.timeout)
        if r_resp.status_code == 200:
            logger.log(f"  {C_BOLD}{C_GREEN}✅ robots.txt FOUND:{C_RESET} {robots_url} (HTTP 200 OK, {len(r_resp.text)} bytes)")
            robots_content = r_resp.text.strip()
            logger.log(f"  {C_BOLD}--- Directives in robots.txt (All Rules) ---{C_RESET}")
            for line in robots_content.splitlines():
                if line.strip():
                    logger.log(f"     {C_DIM}↳ {line.strip()}{C_RESET}")
        else:
            logger.log(f"  {C_BOLD}{C_YELLOW}⚠️  robots.txt returned HTTP {r_resp.status_code}{C_RESET}")
    except Exception as e:
        logger.log(f"  {C_BOLD}{C_RED}❌ robots.txt fetch error:{C_RESET} {e}")

    # ─────────────────────────────────────────────────────────────
    # STEP 2: SITEMAP DISCOVERY & ALL SITEMAP URLS EXTRACTION
    # ─────────────────────────────────────────────────────────────
    logger.log(f"\n{C_BOLD}{C_BLUE}[STEP 2/4] SITEMAP DISCOVERY & XML PARSING (SitemapParser){C_RESET}")
    sitemap_parser = SitemapParser(session, base_origin, timeout=args.timeout)
    sitemap_urls = []
    try:
        raw_sitemaps = sitemap_parser.discover_sitemaps(target_url)
        # Deduplicate while preserving order
        seen = set()
        for u in raw_sitemaps:
            u_norm = u.strip()
            if u_norm and u_norm not in seen:
                seen.add(u_norm)
                sitemap_urls.append(u_norm)
        
        logger.log(f"  {C_BOLD}{C_GREEN}✅ Sitemaps Discovered:{C_RESET} Found {len(sitemap_urls)} unique URLs inside sitemap index.")
        
        # Save all sitemap URLs to file
        with open("sitemap_discovered_urls.txt", "w", encoding="utf-8") as sf:
            for su in sitemap_urls:
                sf.write(su + "\n")
        logger.log(f"  {C_DIM}Saved all {len(sitemap_urls)} sitemap URLs to 'sitemap_discovered_urls.txt'{C_RESET}")

        # Print all sitemap URLs without any truncation
        logger.log(f"\n  {C_BOLD}--- All Discovered Sitemap URLs ({len(sitemap_urls)} total) ---{C_RESET}")
        for idx, u in enumerate(sitemap_urls, 1):
            logger.log(f"  [{idx:>3}/{len(sitemap_urls)}] {u}")

    except Exception as e:
        logger.log(f"  {C_BOLD}{C_YELLOW}⚠️  Sitemap discovery notice:{C_RESET} {e}")

    # ─────────────────────────────────────────────────────────────
    # STEP 3: DYNAMIC MULTI-PAGE LIVE CRAWL & DEEP ISSUE DETECTION
    # ─────────────────────────────────────────────────────────────
    logger.log(f"\n{C_BOLD}{C_BLUE}[STEP 3/4] MULTI-PAGE LIVE CRAWL & DEEP DOM / SEO AUDIT{C_RESET}")

    crawl_q = Queue()
    enqueued_urls = set()
    queue_lock = threading.Lock()

    def add_url_to_queue(u):
        with queue_lock:
            if u not in enqueued_urls:
                enqueued_urls.add(u)
                crawl_q.put(u)
                return True
        return False

    # Seed queue with target URL and all sitemap URLs
    add_url_to_queue(target_url)
    for su in sitemap_urls:
        add_url_to_queue(su)

    # Determine crawl limit
    if args.pages.lower() == "all":
        max_crawl_pages = len(enqueued_urls)
    else:
        try:
            max_crawl_pages = int(args.pages)
        except ValueError:
            max_crawl_pages = 50

    logger.log(f"  Queue Size       : {len(enqueued_urls)} URLs initially discovered")
    logger.log(f"  Target Pages     : Up to {max_crawl_pages} pages will be crawled and audited\n")

    crawled_count = 0
    claimed_count = 0
    count_lock = threading.Lock()
    all_results = []
    all_issues_summary = []
    inbound_links_graph = {}  # target_url -> set of source_urls
    graph_lock = threading.Lock()
    image_status_cache = {}
    image_cache_lock = threading.Lock()

    active_workers = 0
    active_lock = threading.Lock()
    stop_flag = threading.Event()

    def worker_loop():
        nonlocal crawled_count, claimed_count, active_workers
        while not stop_flag.is_set():
            with count_lock:
                if claimed_count >= max_crawl_pages:
                    stop_flag.set()
                    break
                claimed_count += 1
                curr_num = claimed_count

            try:
                url = crawl_q.get(timeout=1.5)
            except Empty:
                with active_lock:
                    if active_workers == 0 and crawl_q.empty():
                        stop_flag.set()
                        break
                with count_lock:
                    claimed_count -= 1
                time.sleep(0.1)
                continue

            with active_lock:
                active_workers += 1

            t_start = time.time()
            try:
                resp = session.get(url, timeout=args.timeout, allow_redirects=True)
                elapsed_ms = (time.time() - t_start) * 1000
                status_code = resp.status_code
                content_type = resp.headers.get("Content-Type", "")
                size = len(resp.content)
                html_text = resp.text
            except Exception as e:
                elapsed_ms = (time.time() - t_start) * 1000
                status_code = 0
                content_type = ""
                size = 0
                html_text = ""
                error_str = str(e)
                res = SEOExtractor.create_empty_result(url, 0, 0, error=error_str)
                issues = [{
                    "url": url,
                    "type": "error",
                    "category": "Connection",
                    "issue": "Request Failed",
                    "details": f"Could not connect to URL: {error_str}"
                }]
                discovered_links = set()
            else:
                soup = BeautifulSoup(html_text, "html.parser")
                res = SEOExtractor.create_empty_result(url, depth=0, status_code=status_code)
                res["content_type"] = content_type
                res["response_time"] = elapsed_ms
                res["size"] = size

                if "html" in content_type.lower():
                    SEOExtractor.extract_basic_seo_data(soup, res)
                    SEOExtractor.extract_meta_tags(soup, res)
                    SEOExtractor.extract_opengraph_tags(soup, res)
                    SEOExtractor.extract_twitter_tags(soup, res)
                    SEOExtractor.extract_json_ld(soup, res)
                    SEOExtractor.extract_images(soup, url, res)
                    SEOExtractor.extract_link_counts(soup, res, base_domain)
                    SEOExtractor.extract_hreflang(soup, res)
                    SEOExtractor.extract_schema_org(soup, res)

                    # Optional deep check: Live HTTP HEAD verification on every image URL
                    if args.check_images and res.get("images"):
                        broken_imgs = []
                        img_urls = [img.get("src") for img in res["images"] if img.get("src") and img.get("src").startswith(("http://", "https://"))]
                        
                        def check_one_img(i_url):
                            with image_cache_lock:
                                if i_url in image_status_cache:
                                    return i_url, image_status_cache[i_url]
                            try:
                                h_resp = session.head(i_url, timeout=4, allow_redirects=True)
                                st = h_resp.status_code
                            except Exception:
                                st = 0
                            with image_cache_lock:
                                image_status_cache[i_url] = st
                            return i_url, st

                        with ThreadPoolExecutor(max_workers=10) as img_pool:
                            for i_url, st in img_pool.map(check_one_img, img_urls):
                                if st == 0 or st >= 400:
                                    broken_imgs.append({"url": i_url, "status": st})
                        res["broken_images"] = broken_imgs

                # Run LibreCrawl IssueDetector
                detector = IssueDetector()
                detector.detect_issues(res)
                issues = detector.detected_issues

                # Discover new internal links
                discovered_links = extract_clean_links(soup, url, base_domain)

            # Update link graph
            with graph_lock:
                for dl in discovered_links:
                    if dl not in inbound_links_graph:
                        inbound_links_graph[dl] = set()
                    inbound_links_graph[dl].add(url)
                    # Dynamically enqueue newly discovered internal links
                    if len(enqueued_urls) < max_crawl_pages * 2:
                        add_url_to_queue(dl)

            with count_lock:
                crawled_count += 1
                all_results.append(res)
                all_issues_summary.extend(issues)

            with active_lock:
                active_workers -= 1
            crawl_q.task_done()

            # Status badge
            if status_code == 200:
                code_badge = f"{C_GREEN}{status_code} OK{C_RESET}"
            elif 300 <= status_code < 400:
                code_badge = f"{C_CYAN}{status_code} Redirect{C_RESET}"
            elif 400 <= status_code < 500:
                code_badge = f"{C_RED}{status_code} Not Found{C_RESET}"
            elif status_code >= 500:
                code_badge = f"{C_RED}{status_code} Server Error{C_RESET}"
            else:
                code_badge = f"{C_RED}Failed / Error{C_RESET}"

            # Build complete atomic log block for this page to prevent any multithread interleaving
            block_lines = []
            block_lines.append(f"{C_BOLD}{'='*90}{C_RESET}")
            block_lines.append(f"{C_BOLD}[PAGE {curr_num}/{max_crawl_pages}]{C_RESET} {C_CYAN}{url}{C_RESET}")
            block_lines.append(f"{C_DIM}{'-'*90}{C_RESET}")
            block_lines.append(f"  HTTP Status      : {code_badge} ({elapsed_ms:.1f} ms, {size:,} bytes)")
            
            if res.get("title"):
                block_lines.append(f"  Page Title       : {C_BOLD}{res.get('title')}{C_RESET}")
            else:
                block_lines.append(f"  Page Title       : {C_RED}(Missing Title Tag){C_RESET}")

            if res.get("meta_description"):
                block_lines.append(f"  Meta Description : {res.get('meta_description')}")
            else:
                block_lines.append(f"  Meta Description : {C_YELLOW}(Missing Meta Description){C_RESET}")

            if res.get("h1"):
                block_lines.append(f"  Main H1 Heading  : {res.get('h1')}")
            else:
                block_lines.append(f"  Main H1 Heading  : {C_YELLOW}(Missing H1 Heading){C_RESET}")

            block_lines.append(f"  Canonical URL    : {res.get('canonical_url') or '(None declared)'}")
            block_lines.append(f"  Word Count       : {res.get('word_count', 0)} words | Language: {res.get('lang') or '(None)'}")
            block_lines.append(f"  Links on Page    : {res.get('internal_links', 0)} internal, {res.get('external_links', 0)} external")
            block_lines.append(f"  Images Found     : {len(res.get('images', []))} images")
            block_lines.append(f"  Structured Data  : {len(res.get('json_ld', []))} JSON-LD schema blocks")

            # Print EVERY detected issue with full details (NO TRUNCATION)
            if issues:
                block_lines.append(f"\n  {C_BOLD}👉 Issues Found on this Page ({len(issues)}):{C_RESET}")
                for iss in issues:
                    sev = iss.get("type", "warning").upper()
                    cat = iss.get("category", "SEO")
                    name = iss.get("issue", "Issue")
                    det = iss.get("details", "")

                    if sev == "ERROR":
                        sev_str = f"{C_RED}[ERROR  ]{C_RESET}"
                    elif sev in ("WARN", "WARNING"):
                        sev_str = f"{C_YELLOW}[WARNING]{C_RESET}"
                    else:
                        sev_str = f"{C_CYAN}[NOTICE ]{C_RESET}"

                    block_lines.append(f"    {sev_str} [{cat:<12}] {C_BOLD}{name}{C_RESET}: {det}")
            else:
                block_lines.append(f"  {C_GREEN}✅ No SEO issues detected on this page.{C_RESET}")

            block_lines.append("")

            # Log the entire page block atomically
            logger.log("\n".join(block_lines))

    threads = []
    for _ in range(args.workers):
        t = threading.Thread(target=worker_loop, daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    # ─────────────────────────────────────────────────────────────
    # STEP 4: CROSS-PAGE DE-DUPLICATION & ORPHAN PAGE DETECTION
    # ─────────────────────────────────────────────────────────────
    logger.log(f"\n{C_BOLD}{C_BLUE}[STEP 4/4] CROSS-PAGE DUPLICATION & ORPHAN PAGE ANALYSIS{C_RESET}")
    logger.log(f"{C_BOLD}{'-'*90}{C_RESET}")

    # Cross-page duplicate detection via IssueDetector
    global_detector = IssueDetector()
    logger.log(f"  Running LibreCrawl Duplicate Content & Title Detection across {len(all_results)} crawled pages...")
    global_detector.detect_duplication_issues(all_results)
    dup_issues = global_detector.detected_issues

    if dup_issues:
        logger.log(f"  {C_BOLD}{C_YELLOW}⚠️  Found {len(dup_issues)} Cross-Page Duplication Issues:{C_RESET}")
        for diss in dup_issues:
            logger.log(f"    {C_YELLOW}[DUPLICATE]{C_RESET} {diss.get('url')}")
            logger.log(f"       ↳ {diss.get('issue')}: {diss.get('details')}")
    else:
        logger.log(f"  {C_GREEN}✅ No severe cross-page duplicate content or titles detected.{C_RESET}")

    # Orphan page detection across the crawled set
    crawled_urls_set = {r.get('url') for r in all_results}
    orphan_pages = []
    for u in crawled_urls_set:
        inbound = inbound_links_graph.get(u, set())
        if len(inbound) == 0 and u != target_url:
            orphan_pages.append(u)

    logger.log(f"\n  Orphan Page Detection (Crawled pages with 0 inbound internal links from other crawled pages):")
    if orphan_pages:
        logger.log(f"  {C_BOLD}{C_YELLOW}⚠️  Found {len(orphan_pages)} Orphan Pages in Crawled Set:{C_RESET}")
        for op in orphan_pages:
            logger.log(f"    {C_YELLOW}[ORPHAN]{C_RESET} {op}")
    else:
        logger.log(f"  {C_GREEN}✅ No orphan pages detected within crawled graph.{C_RESET}")

    # ─────────────────────────────────────────────────────────────
    # FINAL SUMMARY REPORT
    # ─────────────────────────────────────────────────────────────
    logger.log(f"\n{C_BOLD}{C_MAGENTA}{'='*90}{C_RESET}")
    logger.log(f"{C_BOLD}{C_MAGENTA}📊 LIBRECRAWL AUDIT SUMMARY & METRICS{C_RESET}")
    logger.log(f"{C_BOLD}{C_MAGENTA}{'='*90}{C_RESET}")
    logger.log(f"Total Discovered URLs : {C_BOLD}{len(enqueued_urls)}{C_RESET}")
    logger.log(f"Total Pages Crawled   : {C_BOLD}{len(all_results)}{C_RESET}")
    
    total_errors = sum(1 for iss in all_issues_summary if iss.get("type") == "error")
    total_warnings = sum(1 for iss in all_issues_summary if iss.get("type") in ("warning", "warn"))
    total_notices = sum(1 for iss in all_issues_summary if iss.get("type") == "notice")
    
    logger.log(f"Total Issues Detected : {C_BOLD}{len(all_issues_summary)}{C_RESET} ("
               f"{C_RED}{total_errors} Errors{C_RESET}, "
               f"{C_YELLOW}{total_warnings} Warnings{C_RESET}, "
               f"{C_CYAN}{total_notices} Notices{C_RESET})")

    # Issue Category Breakdown
    cat_counts = {}
    issue_type_counts = {}
    for iss in all_issues_summary:
        c = iss.get("category", "Other")
        cat_counts[c] = cat_counts.get(c, 0) + 1
        i_name = iss.get("issue", "Unknown")
        issue_type_counts[i_name] = issue_type_counts.get(i_name, 0) + 1

    logger.log(f"\n{C_BOLD}Issues by Category:{C_RESET}")
    for cat, count in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
        logger.log(f"  • {cat:<18}: {count} occurrences")

    logger.log(f"\n{C_BOLD}Top Issues Across Crawled Pages:{C_RESET}")
    for iname, count in sorted(issue_type_counts.items(), key=lambda x: x[1], reverse=True):
        logger.log(f"  • {iname:<32}: {count} pages affected")

    logger.log(f"\n{C_BOLD}{C_GREEN}✨ Audit complete! Full system log saved to:{C_RESET} {os.path.abspath(args.log)}")
    logger.log(f"{C_BOLD}{C_MAGENTA}{'='*90}{C_RESET}\n")

    logger.close()

if __name__ == "__main__":
    main()
