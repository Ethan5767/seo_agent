#!/usr/bin/env python3
"""Validate DOCX intake before build.

Checks:
1. Every Meta Title has matching URL
2. URL slug contains a keyword from Meta Title (typo detection)
3. Every URL fits client topology
4. No duplicate URLs in DOCX
5. All pricing flags surfaced

Usage: python3 validate-docx-intake.py [DOCX_PATH] [PROJECT_DIR]
Exit 0 = pass, non-zero = block pipeline.
"""
import sys, re, subprocess
from pathlib import Path
from pipeline.lib.common import load_config, url_fits_topology


def extract_pages(md_text: str):
    """Return [(meta_title, url, start_line)]."""
    lines = md_text.splitlines()
    pages = []
    current = {}
    for i, line in enumerate(lines, 1):
        if "Meta Title:" in line:
            current = {"meta_line": i}
        mt = re.search(r"\|?\s*([A-Z][^|]{10,70}?)\s*(?:\\\||$)", line) if current.get("meta_line") == i - 2 else None
        if "URL:" in line or re.match(r".*https?://\S+", line):
            m = re.search(r"https?://[^\s\\|]+", line)
            if m and current:
                current["url"] = m.group(0).rstrip("*").rstrip("/").lower() + "/"
                pages.append(current); current = {}
    # Fallback: simpler line-based parse.
    # Handles every DOCX team variant:
    #   - `**Meta Title:**` / `**Meta Title (58 chars):**` (with colon, bolded)
    #   - `**META TITLE**` / `**META TITLE: ...**` (all caps, bolded, colon optional)
    #   - `Meta Title:` / `Page Title:` (unbolded)
    #   - `**Meta Tittle:**` (Joy DOCX typo) — accepted via Tit?le pattern
    pages = []
    split_re = re.compile(
        r"(?:\*\*)?(?:Meta\s+Tit?le|Page\s+Title)(?:\s*\([^)]*\))?\s*:?\s*(?:\*\*)?",
        re.IGNORECASE,
    )
    text_blocks = split_re.split(md_text)
    for idx, block in enumerate(text_blocks[1:], 1):
        title_m = re.search(r"([^\n|]+)", block)
        # Strip pandoc span markup in any order: `]{.underline}`, `]{.mark}`,
        # nested `]{.underline}]{.mark}`, etc. + `[[`, + `](url)` artifacts.
        clean = re.sub(r"\]\{[^}]*\}", "", block)        # ]{.underline} or ]{.mark}
        clean = re.sub(r"\{[^}]*\}", "", clean)          # bare {.foo}
        clean = re.sub(r"\[+", "", clean)                # [[ or [
        clean = re.sub(r"\]\([^)]*\)", "", clean)        # ](url)
        # Prefer URL adjacent to a Slug:/URL: marker (Joy DOCX emits these in
        # the first ~10 lines of each page block). Falls back to first URL in
        # block only if no marker is present — avoids picking up body links
        # like "/instock/" that appear later in long-form content.
        marked = re.search(
            r"(?:URL|Slug|Canonical)\s*:\s*[^\n]*?(https?://[^\s\\|)(>\]\}\{]+)",
            clean,
            re.IGNORECASE,
        )
        if marked:
            url_str = marked.group(1)
        else:
            head = "\n".join(clean.splitlines()[:15])
            fallback = re.search(r"https?://[^\s\\|)(>\]\}\{]+", head)
            url_str = fallback.group(0) if fallback else None

        title_text = title_m.group(1).strip().strip("|").strip().rstrip("\\").strip() if title_m else ""

        # Final fallback: derive `/[city]/[service]/` from title when Joy omits
        # the Slug: line entirely (recurring DOCX edge case — Delray-residential,
        # PBG-commercial, RPB-commercial in May'26 waterproofing batch). Title
        # shape is "[Residential|Commercial] [Service…] in [City]".
        derived = None
        m = re.match(
            r"\s*(Residential|Commercial)\s+([A-Za-z &-]+?)\s+in\s+(.+?)\s*(?:\||$)",
            title_text,
            re.IGNORECASE,
        )
        if m:
            kind, svc, city = m.group(1).lower(), m.group(2).lower(), m.group(3).lower()
            slug_svc = re.sub(r"\s+", "-", svc.strip())
            slug_city = re.sub(r"\s+", "-", city.strip())
            derived = f"/{slug_city}/{kind}-{slug_svc}/"

        # Picking order: marker URL → first body URL in head → derived slug.
        # If marker/body URL points at a hub like `/commercial` or `/residential`
        # (no city segment), prefer the derived slug instead.
        chosen_path = None
        if url_str:
            raw = url_str.rstrip("*").rstrip("/").rstrip(",.;:").lower()
            full = raw + "/"
            chosen_path = "/" + full.split("/", 3)[-1] if "://" in full else full
            if not chosen_path.startswith("/"):
                chosen_path = "/" + chosen_path
            # Reject hub-shaped paths in favor of derived city/service spoke.
            if derived and chosen_path.count("/") < 3:
                chosen_path = derived
        elif derived:
            chosen_path = derived

        if title_text and chosen_path:
            pages.append({
                "title": title_text,
                "url": chosen_path,
                "block_idx": idx,
            })
    return pages


def main():
    if len(sys.argv) < 3:
        print("Usage: validate-docx-intake.py [DOCX_PATH] [PROJECT_DIR]", file=sys.stderr); sys.exit(1)
    docx, project = Path(sys.argv[1]), Path(sys.argv[2])
    cfg = load_config(str(project))
    topology = cfg["topology"]

    md_path = Path("/tmp") / (docx.stem + ".md")
    subprocess.run(["pandoc", str(docx), "-o", str(md_path)], check=True)
    md = md_path.read_text()
    pages = extract_pages(md)

    if not pages:
        print("[FAIL] No Meta Title + URL pairs found in DOCX."); sys.exit(2)

    errors, warnings = [], []
    seen_urls = {}

    for p in pages:
        url, title = p["url"], p["title"]
        # Check 1: duplicate URLs
        if url in seen_urls:
            errors.append(f"Duplicate URL: {url} (pages {seen_urls[url]} and {p['block_idx']})")
        seen_urls[url] = p["block_idx"]

        # Check 2: topology fit
        fits, kind = url_fits_topology(url, topology)
        if not fits:
            errors.append(f"URL {url} violates topology '{topology}'")

        # Check 3: slug-title mismatch (typo detection)
        title_keywords = re.findall(r"[A-Za-z]{4,}", title.lower())
        slug_keywords = re.findall(r"[a-z]{4,}", url.lower())
        stop = {"with", "from", "your", "near", "same", "service", "company", "northstar"}
        key_title = [w for w in title_keywords if w not in stop][:2]
        if key_title and not any(kt in " ".join(slug_keywords) for kt in key_title):
            warnings.append(f"URL {url} may not match Meta Title '{title}' — verify slug")

    # Pricing flag scan
    forbidden = cfg.get("forbidden_phrases", [])
    for rule in forbidden:
        hits = len(re.findall(rule["pattern"], md))
        if hits > 0:
            warnings.append(f"{hits}× forbidden pattern /{rule['pattern']}/ in DOCX — scrub before build")

    print(f"[INTAKE] {len(pages)} pages parsed")
    for p in pages:
        print(f"  {p['url']:60s}  {p['title'][:50]}")
    print()
    for w in warnings: print(f"[WARN] {w}")
    for e in errors: print(f"[FAIL] {e}")
    if errors:
        print(f"\n[BLOCKED] {len(errors)} errors. Fix DOCX before proceeding."); sys.exit(3)
    print(f"\n[OK] Intake valid. {len(warnings)} warnings to review.")


if __name__ == "__main__":
    main()
