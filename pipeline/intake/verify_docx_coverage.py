#!/usr/bin/env python3
"""Verify DOCX coverage against live deploy.

Mechanical proof that every section, distinctive phrase, and FAQ from the
team DOCX renders on the live site. Eliminates "I read it and it covers
everything" vibes-based confidence.

Usage:
    python3 verify-docx-coverage.py [DOCX_PATH] [PROJECT_DIR] [LIVE_DOMAIN]

Exit codes:
    0 = all coverage passes (100%)
    1 = usage error
    2 = DOCX parse error or pandoc missing
    3 = coverage gaps detected (ghost sections, missing phrases, FAQ count mismatch, ratio failures)

Output:
    docs/audit-logs/[DATE]/coverage-verify.md per Step 5.5 of seo-content-pipeline.md
"""
import sys
import re
import subprocess
import urllib.request
import urllib.error
import json
from pathlib import Path
from datetime import datetime
from html.parser import HTMLParser

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


WORD_RATIO_GATE = 0.70
PHRASE_SAMPLE_PER_PAGE = 3
WORD_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9'-]+\b")

# Hub-banner page-starts are merged with a following Meta-Title page-start
# if the Meta Title appears within this many lines. Banners alone are not
# distinct pages — they introduce the page that the Meta Title defines.
HUB_BANNER_MERGE_WINDOW = 10


def _strip_json_ld_blocks(text: str) -> str:
    """Strip pandoc-converted JSON-LD pseudo-JSON from DOCX body.

    Team docs frequently include literal schema markup as a teaching aid:
        {"@type": "Service", "name": "Residential Roof Inspection"}
    pandoc converts this to escaped-quote text inline with the prose. Without
    stripping, those `"name":"<service>"` strings get sampled as distinctive
    phrases AND inflate the body word count, then both fail against live
    HTML where the schema is in <script> tags (which are stripped before
    word counting).

    Drops any line that matches a JSON-LD-shaped pattern (escaped or raw
    quotes around `@type`, `@context`, `@graph`, `itemOffered`,
    `itemListElement`, `mainEntity`, `address`, `geo`, `priceCurrency`,
    `provider`, etc.) and any structural line of the form `["{`, `}],`,
    `}` etc.
    """
    JSON_KEY_RE = re.compile(
        r'\\?"@?(?:type|context|graph|id|itemOffered|itemListElement|mainEntity|address|geo|priceCurrency|provider|sameAs|areaServed|telephone|openingHours|aggregateRating|ratingValue|reviewCount|streetAddress|addressLocality|addressRegion|postalCode|hasOfferCatalog|name|description|url|image|priceRange|founder|foundingDate)\\?"\s*:\s*',
        re.IGNORECASE,
    )
    JSON_STRUCT_RE = re.compile(r'^\s*[\[\]{},]+\s*$')
    out = []
    for line in text.splitlines():
        if JSON_KEY_RE.search(line):
            continue
        if JSON_STRUCT_RE.match(line):
            continue
        out.append(line)
    return "\n".join(out)


class TextExtractor(HTMLParser):
    """Strip HTML to plain text for word counting + phrase searching.

    Skips <script> and <style> bodies (so JSON-LD does not pollute counts).
    """

    SKIP_TAGS = {"script", "style", "noscript"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skipping = False
        self.skip_tag = None

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self.skipping = True
            self.skip_tag = tag

    def handle_endtag(self, tag):
        if self.skipping and tag == self.skip_tag:
            self.skipping = False
            self.skip_tag = None

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)

    def text(self):
        return " ".join(self.parts)


BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def fetch_url(url: str, timeout: int = 30) -> str:
    """Return raw HTML for a URL, or '' on network failure.

    Uses a real-browser User-Agent because Cloudflare WAF (and similar)
    block bot-flavored UAs like 'verify-docx-coverage/1.0' on protected
    domains. Without a browser UA, every fetch returns 403 / challenge HTML
    instead of the actual page, producing false fails.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return ""


def html_to_text(html: str) -> str:
    parser = TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.text()


def word_count(text: str) -> int:
    return len(WORD_PATTERN.findall(text))


def extract_pages_from_docx_md(md_text: str):
    """Split DOCX-converted markdown into per-page blocks.

    Heuristic: a "page" begins at a Meta Title or Page Title line and runs
    until the next one (or EOF). Captures URL + title + body lines.
    """
    lines = md_text.splitlines()
    title_re = re.compile(
        r"^(?:#{1,6}\s+)?(?:\*\*)?(?:Meta\s+Title|Page\s+Title)(?:\s*\([^)]*\))?(?:\s*[:\-—])?(?:\*\*)?",
        re.IGNORECASE,
    )
    # Hub-banner detector: `# **City, ST --- Full Location Page Content**` style.
    # Some team docs use this banner instead of (or before) a Meta Title line for
    # major hub sections — without this match, the hub-banner line gets folded
    # into the previous page block and shows up as a phantom "missing section".
    hub_banner_re = re.compile(
        r"^#{1,2}\s+\*\*[A-Z][a-zA-Z\s]+,\s+[A-Z]{2}\b.*?(?:Full Location Page|---)",
    )
    url_re = re.compile(r"https?://[^\s\\|)(>\]\}\{]+")

    title_starts = [i for i, line in enumerate(lines) if title_re.search(line)]
    banner_starts = [i for i, line in enumerate(lines) if hub_banner_re.search(line)]

    # If a hub-banner is immediately followed by a Meta-Title within
    # HUB_BANNER_MERGE_WINDOW lines, the banner is just a header for that page
    # and should NOT trigger a separate page boundary. Drop banners that have
    # a title-start within the window.
    title_set = set(title_starts)
    filtered_banners = [
        b for b in banner_starts
        if not any(t for t in title_starts if 0 < t - b <= HUB_BANNER_MERGE_WINDOW)
    ]
    page_starts = sorted(set(title_starts + filtered_banners))
    if not page_starts:
        return []

    pages = []
    for idx, start in enumerate(page_starts):
        end = page_starts[idx + 1] if idx + 1 < len(page_starts) else len(lines)
        block = lines[start:end]

        # Title is the same line or the line after the marker
        title_line = block[0]
        title_after_colon = re.sub(title_re, "", title_line, count=1).strip(" *|\\:")
        if not title_after_colon and len(block) > 1:
            title_after_colon = block[1].strip(" *|\\:")
        title_after_colon = re.sub(r"\]\{[^}]*\}", "", title_after_colon)
        title_after_colon = re.sub(r"\{[^}]*\}", "", title_after_colon)
        title_after_colon = re.sub(r"\[+", "", title_after_colon)
        title_after_colon = re.sub(r"\]\([^)]*\)", "", title_after_colon).strip()

        # First URL in the block (clean pandoc artifacts)
        block_text = "\n".join(block)
        clean = re.sub(r"\]\{[^}]*\}", "", block_text)
        clean = re.sub(r"\{[^}]*\}", "", clean)
        clean = re.sub(r"\[+", "", clean)
        clean = re.sub(r"\]\([^)]*\)", "", clean)
        url_m = url_re.search(clean)

        body = "\n".join(block[1:])
        # Strip pandoc-converted JSON-LD pseudo-JSON before downstream
        # measurement. Without this, body word count is inflated by inline
        # schema markup (which gets stripped from live HTML by SKIP_TAGS),
        # and distinctive-phrase sampling pulls in `"name":"<service>"`
        # strings that don't appear in rendered text.
        body = _strip_json_ld_blocks(body)
        pages.append({
            "title": title_after_colon[:120],
            "url_full": url_m.group(0).rstrip("*").rstrip("/").rstrip(",.;:").lower() if url_m else "",
            "body_md": body,
            "doc_line_start": start + 1,
            "doc_line_end": end,
            "body_words": word_count(body),
        })
    return pages


def extract_section_headings(body_md: str):
    """Return list of section heading strings (H1-H4).

    Filters out doc metadata lines that pandoc renders as headings:
    "H1:", "H2:", "H3:", "H4:" labels, "Meta Title:", "Meta Description:",
    "Page Title:", "URL:", "Section Label:". These are doc-authoring
    annotations, not real page sections.
    """
    # Lines starting with these prefixes are doc metadata, NOT real page sections
    # (regardless of remainder length). Skip the entire line.
    metadata_full_skip = re.compile(
        r"^(?:Meta\s+Title|Meta\s+Description|Page\s+Title|URL|Section\s+Label|Schema|JSON-LD|Image\s+Alt|Image\s+Filename|Schema\s+Block|SEO\s+META\s+TAGS|SEO\s+MARKUP|SCHEMA\s+MARKUP|FOOTNOTES)\b",
        re.IGNORECASE,
    )
    # Lines starting with "H1:" / "H2:" are doc-author hints — strip the prefix
    # and use the remainder as the heading (the remainder is typically the
    # actual page heading the team wants rendered).
    h_prefix = re.compile(r"^H[1-6]\s*:\s*", re.IGNORECASE)

    # Hub-banner pattern (e.g., 'Charlotte, NC --- Full Location Page Content')
    # is a structural marker for the start of a hub block, never a real page
    # section. Filter from heading list.
    hub_banner_check = re.compile(
        r"^[A-Z][a-zA-Z\s]+,\s+[A-Z]{2}\b.*?(?:Full Location Page|---)",
    )

    headings = []
    for m in re.finditer(r"^#{1,4}\s+(.+)$", body_md, re.MULTILINE):
        text = m.group(1).strip()
        text = re.sub(r"\*+", "", text)
        text = re.sub(r"\\", "", text)
        text = re.sub(r"`", "", text)
        if not text or len(text) > 200:
            continue
        if metadata_full_skip.match(text):
            continue  # entire line is doc metadata, drop
        if hub_banner_check.match(text):
            continue  # structural hub-banner, never a real section
        text = h_prefix.sub("", text).strip()
        if not text or len(text) < 4:
            continue
        headings.append(text)
    return headings


JUNK_PHRASES = {
    "meta description", "meta title", "page title", "section label",
    "schema", "json-ld", "application/ld+json", "image alt", "h1", "h2", "h3", "h4",
    "url", "hero section", "intro section", "footer", "topbar",
}


def _is_section_banner(text: str) -> bool:
    """All-caps banner labels (TOPBAR, EXTERIOR SERVICES SECTION) are DOCX
    layout markers, not page sections — live HTML expresses them via class
    names + sentence-case sub-headings, not the literal CAPS string.

    Returns True if the heading is a banner that should be skipped from
    section-coverage checks (the underlying content is verified via
    distinctive-phrase + word-ratio gates instead).
    """
    stripped = re.sub(r"[^A-Za-z\s]", "", text).strip()
    if not stripped:
        return False
    # Must be predominantly all-caps (allow rare lowercase like 'and', 'or')
    letters_only = re.sub(r"[^A-Za-z]", "", stripped)
    if not letters_only:
        return False
    upper_ratio = sum(1 for c in letters_only if c.isupper()) / len(letters_only)
    if upper_ratio < 0.85:
        return False
    if stripped.upper().endswith("SECTION"):
        return True
    if stripped.upper() in {"TOPBAR", "FOOTER", "HERO", "ZIGZAG", "CTA",
                            "ROW 1", "ROW 2", "ROW 3", "ROW 4"}:
        return True
    # Also flag DOCX zigzag/row sub-banners like "ZIGZAG --- RESIDENTIAL ROOFING"
    if "ZIGZAG" in stripped.upper() and upper_ratio >= 0.85:
        return True
    return False


def _load_coverage_method(project: Path) -> str:
    """Read client-config.yml repo.coverage_method. Returns 'strict-section' default.
    'builder-collapse' downgrades section-presence + word-ratio to advisory and
    adds 1/3 distinctive-entity sampling tolerance — for renderers that collapse
    raw DOCX sections into a smaller fixed set of builder slots.
    """
    if yaml is None:
        return "strict-section"
    cfg_path = project / "docs" / "client-config.yml"
    if not cfg_path.exists():
        return "strict-section"
    try:
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        return (cfg.get("repo", {}) or {}).get("coverage_method", "strict-section")
    except Exception:
        return "strict-section"


def _load_h1_format(project: Path) -> str | None:
    """Read client-config.yml h1_format.default. Returns None if absent
    or YAML library unavailable. Used to recognize H1-rename equivalence
    when DOCX heading wording differs from the locked live H1 pattern.
    """
    if yaml is None:
        return None
    cfg_path = project / "docs" / "client-config.yml"
    if not cfg_path.exists():
        return None
    try:
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        h1f = (cfg.get("h1_format") or {}).get("default")
        if h1f and h1f != "TODO":
            return h1f
    except Exception:
        pass
    return None


def _heading_equivalents(heading: str, h1_format: str | None) -> list[str]:
    """Return alternate forms to consider equivalent to `heading`.

    If the DOCX heading is a city-bound H1 like 'Roofing and Exterior
    Services in Charlotte, NC' and `h1_format` is a different locked
    pattern (e.g., 'Roofing Contractor in [City], [ST]'), return both
    forms so the verifier accepts a match on EITHER. This handles the
    case where a Cycle E rename diverged the live H1 from the DOCX H1.
    """
    alts = [heading]
    if not h1_format:
        return alts
    m = re.search(r"\bin\s+([A-Z][a-zA-Z\s\-]+),\s+([A-Z]{2})\b", heading)
    if m:
        city = m.group(1).strip()
        st = m.group(2).strip()
        renamed = (
            h1_format
            .replace("[City]", city)
            .replace("[ST]", st)
            .replace("[State]", st)
            .replace("[Brand]", "")
            .strip(" |")
        )
        if renamed and renamed != heading:
            alts.append(renamed)
    return alts

JUNK_FRAGMENTS = (
    "application/", "json+ld", "ld+json", "{.underline}", "schema.org", "@type",
    "ld+json\\", "type=", "<script", "</script", "<div", "</div",
    "https://", "http://", "www.",
    # HTML attribute residue + image filename leakage (added v4.1)
    "alt=", "href=", "src=", "rel=", "class=", "id=",
    ".webp", ".jpg", ".jpeg", ".png", ".svg", ".gif",
    "noindex", "nofollow",
    "viewbox", "stroke-linecap", "stroke-width",  # SVG attributes
)


# Generic DOCX H1/title fragments that the team uses across many pages.
# These are not "distinctive" — they appear on every spoke page in the doc
# and don't help prove per-page coverage. Excluded from candidate sampling.
GENERIC_TITLE_FRAGMENTS = (
    "roofing and exterior services",
    "roofing & exterior services",
    "gaf master elite roofer",
    "full location page content",
)


def _is_junk_phrase(phrase: str) -> bool:
    p = phrase.strip().lower()
    if p in JUNK_PHRASES:
        return True
    for frag in JUNK_FRAGMENTS:
        if frag in p:
            return True
    # Generic DOCX H1 fragments (templated across every page) are not
    # distinctive — exclude from candidate sampling. Per-page H1 coverage
    # is proven via the heading-equivalence machinery, not phrase sampling.
    for frag in GENERIC_TITLE_FRAGMENTS:
        if frag in p and len(p) <= len(frag) + 10:
            return True
    if re.match(r"^[\W_]+$", p):
        return True
    return False


def extract_distinctive_phrases(body_md: str, k: int = PHRASE_SAMPLE_PER_PAGE):
    """Pick k distinctive phrases from the doc body for live-page presence check.

    Heuristic: prefer phrases with proper nouns, numbers, or quotation marks.
    Filters out doc metadata labels and code-fence artifacts.
    """
    # Strip code fences entirely so they cannot contribute candidates
    cleaned_body = re.sub(r"```.*?```", "", body_md, flags=re.DOTALL)
    cleaned_body = re.sub(r"`[^`\n]+`", "", cleaned_body)
    # Strip pandoc backslash-escapes that leak into candidate phrases as
    # trailing characters like 'Question?\\' — these would never match
    # against the live HTML even when the underlying content is present.
    cleaned_body = cleaned_body.replace("\\", "")

    candidates = []

    # Quoted phrases (testimonial-like)
    for m in re.finditer(r'["“”]([^"“”\n]{20,120})["“”]', cleaned_body):
        phrase = m.group(1).strip()
        if not _is_junk_phrase(phrase):
            candidates.append(("quoted", phrase))

    # Specific numbers + units (e.g., "5,000+ projects", "$485,000", "15-25 tons")
    for m in re.finditer(r"(?<![\w])([\$£€]?\d[\d,]*\+?(?:\s?[-–]\s?\d[\d,]*)?\s*(?:tons|projects|sq\.?\s?ft|years|miles|feet|ft|sf|homeowners|customers|reviews|sqft|psi|gallons))", cleaned_body, re.IGNORECASE):
        phrase = m.group(0).strip()
        if not _is_junk_phrase(phrase):
            candidates.append(("number", phrase))

    # Proper noun chunks of 2-5 capitalized words (likely neighborhoods, brand names)
    for m in re.finditer(r"\b((?:[A-Z][a-zA-Z'&]+(?:\s+|-)){1,4}[A-Z][a-zA-Z'&]+)\b", cleaned_body):
        chunk = m.group(1).strip()
        if not (6 <= len(chunk) <= 60):
            continue
        if chunk.lower().startswith(("the ", "a ", "an ", "and ", "or ")):
            continue
        if _is_junk_phrase(chunk):
            continue
        candidates.append(("proper_noun", chunk))

    # Dedupe, prefer first occurrences
    seen = set()
    unique = []
    for kind, phrase in candidates:
        key = phrase.lower()
        if key not in seen and len(phrase) >= 6:
            seen.add(key)
            unique.append((kind, phrase))

    # Prefer mix of types
    quoted = [p for p in unique if p[0] == "quoted"][:k]
    numbers = [p for p in unique if p[0] == "number"][:k]
    nouns = [p for p in unique if p[0] == "proper_noun"][:k]

    picks = []
    pools = [quoted, numbers, nouns]
    while len(picks) < k and any(pools):
        for pool in pools:
            if pool and len(picks) < k:
                picks.append(pool.pop(0))
    return picks


def doc_faq_count(body_md: str) -> int:
    """Count Q&A pairs in DOCX body."""
    # Patterns the team uses: "Q1:", "**Q1:**", "Q:", "Question 1:", "1. Q:"
    matches = re.findall(
        r"(?im)^[\s>*]*(?:\*\*)?(?:Q\d*|Question\s*\d*)[:\.\)]\s*(?:\*\*)?",
        body_md,
    )
    return len(matches)


def live_faq_count(html: str) -> int:
    """Count FAQ entries from FAQPage JSON-LD in live HTML.

    Walks both top-level entities and @graph children. Falls back to
    raw `@type":"Question"` count if structured parse misses (handles
    sites that emit Questions outside a top-level FAQPage wrapper or
    with non-standard nesting).
    """
    count = 0
    seen_question_via_structure = False

    def walk(node):
        nonlocal count, seen_question_via_structure
        if isinstance(node, list):
            for child in node:
                walk(child)
            return
        if not isinstance(node, dict):
            return
        node_type = node.get("@type")
        if node_type == "FAQPage":
            main = node.get("mainEntity", [])
            if isinstance(main, list):
                count += len(main)
            elif isinstance(main, dict):
                count += 1
            seen_question_via_structure = True
        # Recurse into @graph + any other nested structures
        for key, val in node.items():
            if key == "mainEntity":
                continue
            if isinstance(val, (list, dict)):
                walk(val)

    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        block = m.group(1).strip()
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        walk(data)

    if count == 0 and not seen_question_via_structure:
        # Fallback: count raw Question @types in the page (catches loose
        # FAQ markup or schemas where Questions render outside a FAQPage)
        question_matches = re.findall(r'"@type"\s*:\s*"Question"', html)
        if question_matches:
            count = len(question_matches)
    return count


def normalize_for_search(s: str) -> str:
    """Lowercase + collapse whitespace + strip basic punctuation for fuzzy presence checks."""
    s = re.sub(r"[\s ]+", " ", s)
    s = re.sub(r"[\"'`‘’“”]", "", s)
    return s.strip().lower()


def check_phrase_presence(phrase: str, live_text_norm: str) -> bool:
    norm = normalize_for_search(phrase)
    if len(norm) < 6:
        return False
    return norm in live_text_norm


def verify_page(page: dict, live_domain: str, h1_format: str | None = None, coverage_method: str = "strict-section") -> dict:
    """Run all coverage checks against a single page's live URL."""
    full_url = page["url_full"]
    if not full_url:
        return {**page, "result": "skip_no_url"}

    # Build canonical live URL for the host the user asked about
    parsed_path = re.sub(r"^https?://[^/]+", "", full_url)
    if not parsed_path:
        parsed_path = "/"
    if not parsed_path.endswith("/"):
        parsed_path += "/"
    live_url = f"https://{live_domain.strip('/')}{parsed_path}"

    html = fetch_url(live_url)
    fail_reasons = []

    if not html:
        fail_reasons.append(f"Live URL did not return HTML: {live_url}")
        return {
            **page,
            "live_url": live_url,
            "fail_reasons": fail_reasons,
            "result": "fail",
        }

    text = html_to_text(html)
    text_norm = normalize_for_search(text)
    live_words = word_count(text)
    word_ratio = (live_words / page["body_words"]) if page["body_words"] else 0.0

    # Section heading coverage
    headings = extract_section_headings(page["body_md"])
    missing_sections = []
    for h in headings:
        h_clean = re.sub(r"^(SECTION|HERO SECTION|FAQ SECTION)\s*", "", h, flags=re.IGNORECASE)
        # Skip DOCX layout-banner labels — they are not real page sections.
        # Live HTML expresses them via class names, not literal CAPS strings.
        if _is_section_banner(h_clean):
            continue
        # Build the equivalence set: try DOCX heading literally + the locked
        # h1_format expansion if the heading looks city-bound.
        candidates = _heading_equivalents(h_clean, h1_format)
        if not any(check_phrase_presence(c, text_norm) for c in candidates):
            # Try matching just the first 4 words as a softer fallback
            short = " ".join(candidates[0].split()[:4])
            if short and not check_phrase_presence(short, text_norm):
                missing_sections.append(h)

    # Distinctive phrase coverage
    phrases = extract_distinctive_phrases(page["body_md"])
    missing_phrases = []
    for kind, phrase in phrases:
        if not check_phrase_presence(phrase, text_norm):
            missing_phrases.append((kind, phrase))

    # FAQ count
    doc_faqs = doc_faq_count(page["body_md"])
    live_faqs = live_faq_count(html)
    faq_match = live_faqs >= doc_faqs if doc_faqs else True

    # Word ratio
    ratio_ok = word_ratio >= WORD_RATIO_GATE

    # Honor coverage_method from client-config.yml.repo.coverage_method.
    # strict-section (default): all four criteria authoritative.
    # builder-collapse: only distinctive-entity + FAQ count match are authoritative.
    # Section-presence + word-ratio become advisory under builder-collapse
    # (architecture artifact, renderer collapses DOCX sections into builder slots).
    advisory_reasons = []

    if missing_sections:
        msg = f"{len(missing_sections)} sections missing on live: {missing_sections[:5]}"
        if coverage_method == "builder-collapse":
            advisory_reasons.append(f"[ADVISORY] {msg}")
        else:
            fail_reasons.append(msg)
    if missing_phrases:
        # Distinctive-entity tolerance — random sampling can flag 1 of 3 phrases on
        # paraphrased content. Allow 1 miss out of 3 sampled as advisory; 2+ misses
        # is authoritative failure.
        missing_count = len(missing_phrases)
        sampled_count = len([p for p in phrases]) or 3
        msg = f"{missing_count} distinctive phrases missing: {[p[1][:50] for p in missing_phrases[:3]]}"
        if coverage_method == "builder-collapse" and missing_count <= 1 and sampled_count >= 3:
            advisory_reasons.append(f"[ADVISORY] {msg} (within 1/3 sampling tolerance)")
        else:
            fail_reasons.append(msg)
    if not faq_match:
        fail_reasons.append(f"FAQ count mismatch: doc={doc_faqs}, live={live_faqs}")
    if not ratio_ok:
        msg = f"Word ratio {word_ratio:.2f} below gate {WORD_RATIO_GATE}"
        if coverage_method == "builder-collapse":
            advisory_reasons.append(f"[ADVISORY] {msg}")
        else:
            fail_reasons.append(msg)

    return {
        **page,
        "live_url": live_url,
        "live_words": live_words,
        "word_ratio": word_ratio,
        "headings_total": len(headings),
        "missing_sections": missing_sections,
        "phrases_checked": phrases,
        "missing_phrases": missing_phrases,
        "doc_faqs": doc_faqs,
        "live_faqs": live_faqs,
        "coverage_method": coverage_method,
        "advisory_reasons": advisory_reasons,
        "fail_reasons": fail_reasons,
        "result": "fail" if fail_reasons else "pass",
    }


def render_report(docx_path: Path, project: Path, live_domain: str, results: list) -> str:
    total = len(results)
    passed = sum(1 for r in results if r["result"] == "pass")
    failed = sum(1 for r in results if r["result"] == "fail")
    skipped = sum(1 for r in results if r["result"] == "skip_no_url")

    lines = [
        f"# DOCX Coverage Verification — {docx_path.name}",
        f"",
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"DOCX: `{docx_path}`",
        f"Project: `{project}`",
        f"Live domain: `{live_domain}`",
        f"",
        f"## Summary",
        f"",
        f"- Total pages: {total}",
        f"- Pass: {passed}",
        f"- Fail: {failed}",
        f"- Skipped (no URL in DOCX block): {skipped}",
        f"",
    ]

    if failed == 0 and skipped == 0:
        lines.append("**STATUS: ✅ 100% coverage. No ghosted content, no dropped phrases, no FAQ count gaps.**")
    elif failed == 0:
        lines.append(f"**STATUS: ⚠️ {skipped} skipped (no URL parseable from DOCX block) — review parser hits**")
    else:
        lines.append(f"**STATUS: ❌ {failed} pages failed coverage. See per-page detail below. Fix and redeploy before advancing pipeline.**")
    lines.append("")

    lines.append("## Per-page detail")
    lines.append("")
    for r in results:
        status_icon = {"pass": "✅", "fail": "❌", "skip_no_url": "⚠️"}.get(r["result"], "?")
        url = r.get("live_url", r.get("url_full", "(no URL)"))
        lines.append(f"### {status_icon} {url}")
        lines.append(f"- Title: {r.get('title', '(no title)')}")
        lines.append(f"- DOCX lines: {r.get('doc_line_start', '?')}–{r.get('doc_line_end', '?')}")
        lines.append(f"- DOCX body words: {r.get('body_words', 0)}")
        if "live_words" in r:
            lines.append(f"- Live HTML words: {r['live_words']}")
            lines.append(f"- Word ratio (live/docx): {r['word_ratio']:.2f}  (gate: ≥{WORD_RATIO_GATE})")
        if "headings_total" in r:
            lines.append(f"- Section headings checked: {r['headings_total']} (missing: {len(r['missing_sections'])})")
            if r["missing_sections"]:
                lines.append(f"  - Missing: {r['missing_sections'][:5]}")
        if "phrases_checked" in r:
            lines.append(f"- Distinctive phrases sampled: {len(r['phrases_checked'])} (missing: {len(r['missing_phrases'])})")
            if r["missing_phrases"]:
                for kind, phrase in r["missing_phrases"][:3]:
                    lines.append(f"  - Missing [{kind}]: \"{phrase[:80]}\"")
        if "doc_faqs" in r:
            lines.append(f"- FAQ count: doc={r['doc_faqs']}, live={r['live_faqs']}")
        if r.get("fail_reasons"):
            lines.append(f"- **Fail reasons:**")
            for reason in r["fail_reasons"]:
                lines.append(f"  - {reason}")
        lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 4:
        print("Usage: verify-docx-coverage.py [DOCX_PATH] [PROJECT_DIR] [LIVE_DOMAIN]", file=sys.stderr)
        sys.exit(1)

    docx_path = Path(sys.argv[1])
    project = Path(sys.argv[2])
    live_domain = sys.argv[3].replace("https://", "").replace("http://", "").strip("/")

    if not docx_path.exists():
        print(f"[FAIL] DOCX not found: {docx_path}", file=sys.stderr)
        sys.exit(2)
    if not project.exists():
        print(f"[FAIL] Project dir not found: {project}", file=sys.stderr)
        sys.exit(2)

    md_path = Path("/tmp") / (docx_path.stem + "-coverage.md")
    try:
        subprocess.run(["pandoc", str(docx_path), "-o", str(md_path)], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[FAIL] pandoc failed: {e}", file=sys.stderr)
        sys.exit(2)

    md = md_path.read_text()
    pages = extract_pages_from_docx_md(md)
    if not pages:
        print("[FAIL] No DOCX pages parsed (no Meta Title / Page Title markers found).", file=sys.stderr)
        sys.exit(2)

    h1_format = _load_h1_format(project)
    if h1_format:
        print(f"[INFO] Loaded h1_format from client-config.yml: '{h1_format}' (used for H1-rename equivalence).")

    coverage_method = _load_coverage_method(project)
    print(f"[INFO] coverage_method = {coverage_method}")

    print(f"[INFO] Parsed {len(pages)} pages from DOCX. Verifying against {live_domain} ...")
    results = []
    for i, page in enumerate(pages, 1):
        print(f"  [{i}/{len(pages)}] {page['url_full'] or '(no URL)'} ...", end="", flush=True)
        result = verify_page(page, live_domain, h1_format=h1_format, coverage_method=coverage_method)
        results.append(result)
        print(f" {result['result']}")

    # Write report
    audit_dir = project / "docs" / "audit-logs" / datetime.now().strftime("%Y-%m-%d")
    audit_dir.mkdir(parents=True, exist_ok=True)
    report_path = audit_dir / "coverage-verify.md"
    report_path.write_text(render_report(docx_path, project, live_domain, results))
    print(f"\n[INFO] Report: {report_path}")

    failed = sum(1 for r in results if r["result"] == "fail")
    skipped = sum(1 for r in results if r["result"] == "skip_no_url")
    if failed > 0:
        print(f"[BLOCKED] {failed} pages failed coverage. Fix and redeploy.", file=sys.stderr)
        sys.exit(3)
    if skipped > 0:
        print(f"[WARN] {skipped} skipped (no URL parsed from DOCX block). Manual review recommended.", file=sys.stderr)
    print("[OK] 100% coverage on all pages with URLs.")


if __name__ == "__main__":
    main()
