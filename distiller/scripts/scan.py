#!/usr/bin/env python3
"""
seo-distiller deterministic gate.

Scans a text/markdown document against a client's canonical config
(client-config.yml forbidden/required phrases + optional flat
banned-phrases.txt) plus Meridian global writing rules.

Contract: agent proposes, this gate disposes. The distilled output
must exit 0 (no BLOCK findings) before it ships. WARN findings must
be resolved or justified in the output change log.

Usage:
  python3 scan.py DOC.md --config client-config.yml [--banned banned-phrases.txt] [--json]

Exit codes: 0 = clean (no BLOCK), 1 = BLOCK findings present, 2 = usage error.
Stdlib + PyYAML only.
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

# ── Global rules (apply to every client, every doc) ─────────────────────────

# Hard AI-slop tells. BLOCK tier — these also appear in client configs but are
# enforced globally so no client is ever shipped slop.
SLOP_BLOCK = [
    r"in today.{0,3}s fast.paced world",
    r"\bit.{0,3}s important to note\b",
    r"\bdelve into\b",
    r"\bin conclusion\b",
    r"\b(moreover|furthermore),\s",
    r"\bunlock(?:ing)?\s+(?:the\s+)?(?:full\s+)?potential\b",
    r"\bnavigate the (?:complex|complexities of|landscape of|world of)\b",
    r"\blook no further\b",
]

# Softer slop tells. WARN tier — judgment call, but each one must be
# consciously kept or rewritten.
SLOP_WARN = [
    r"\bwhen it comes to\b",
    r"\bseamless(?:ly)?\b",
    r"\belevate your\b",
    r"\bunparalleled\b",
    r"\bnestled\b",
    r"\bvibrant\b",
    r"\bgame.changer\b",
    r"\bhassle.free\b",
    r"\bstate.of.the.art\b",
    r"\btop.notch\b",
]

# License-scope lexicon. WARN tier, global — language that promises work a
# trade license may not cover (public-adjusting class: managing/negotiating/
# supplementing insurance claims). Most states reserve claim advocacy for
# licensed public adjusters. Every hit gets judged against the client's
# license + state law; after legal review a client's config can escalate
# specific patterns to error tier. The safe frame is always: inspect,
# photograph, document, write the report the OWNER files — never manage,
# negotiate, or represent.
LICENSE_SCOPE = [
    r"\b(manag\w+|handl\w+|oversee\w*|overseeing)\b[^.\n]{0,30}\b(insurance claims?|claims? process|full claim|entire claim)\b",
    r"\b(negotiat\w+|settl\w+|maximiz\w+)\b[^.\n]{0,40}\b(claims?|settlements?|payouts?)\b",
    r"\bsupplement\w*\b[^.\n]{0,40}\b(payouts?|settlements?|claims?)\b",
    r"\b(represent\w*|advocat\w*)\b[^.\n]{0,30}\b(you|your|homeowners?)\b[^.\n]{0,30}\b(insur\w+|carrier|adjuster)\b",
    r"\bensur\w+\b[^.\n]{0,40}\b(captured|covered|included)\b[^.\n]{0,30}\b(settlements?|claims?)\b",
    r"\b(adjuster walk\w*|walk the roof with (the|your) adjuster|attend the adjuster)\b",
]

# Unverified-claim lexicon. WARN tier — every hit must be cross-checked
# against config trust_signals / licenses. Not in config = strip or replace.
FACT_GATE = [
    (r"\b\d{1,3}\+?\s*(?:years?|yrs)\b", "year-count claim"),
    (r"\bsince\s+(?:19|20)\d{2}\b", "founding-year claim"),
    (r"\btop\s+\d{1,3}\s*%", "percentile claim"),
    (r"\b[\d,]{3,}\+?\s*(?:projects?|jobs?|roofs?|installs?|installations?|homes?|customers?|clients?|systems?)\b", "volume claim"),
    (r"\b(?:master\s+elite|golden\s+pledge|platinum\s+preferred|surestart|certified|certification)\b", "credential/warranty claim"),
    (r"\b(?:lifetime|[0-9]{1,3}.year)\s+warrant(?:y|ies)\b", "warranty-term claim"),
    (r"\b5(?:\.0)?\s*(?:★|star)|\b4\.\d\s*(?:★|star|rating|rated)\b", "rating claim"),
]

HEADING_CONTRACTIONS = (
    r"\b(it's|let's|here's|there's|that's|what's|who's|where's|how's|when's|why's|"
    r"she's|he's|we're|you're|they're|won't|don't|can't|isn't|aren't|wasn't|weren't|"
    r"haven't|hasn't|hadn't|wouldn't|couldn't|shouldn't|summer's|winter's|spring's|"
    r"fall's|autumn's)\b"
)

# Words allowed lowercase mid-heading under the Title Case rule.
TITLE_CASE_ALLOW = {
    "a", "an", "the", "and", "but", "or", "nor", "for", "yet", "so",
    "at", "by", "in", "of", "on", "to", "up", "as", "with", "vs",
    "per", "via",
}

PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")

# Lines that carry a page title / meta description in team-doc or output format.
# Matched against NORMALIZED lines (bold markers and stray backslashes stripped);
# the value may sit on the same line or the next non-empty line (pandoc splits them).
TITLE_LINE = re.compile(r"^\s*(?:page|meta)\s+title(?:\s*\([^)]*\))?\s*:\s*(.*)$", re.I)
DESC_LINE = re.compile(r"^\s*meta\s+description(?:\s*\([^)]*\))?\s*:\s*(.*)$", re.I)
# Heading label variants seen across team docs: "H2:", "Q1:" (FAQ question
# headings), "Heading 2:", "H2 heading:". Answer labels ("A1:") are body copy,
# never matched. Group 3 is always the heading text.
HEADING_LINE = re.compile(
    r"^\s*(?:(?:H([1-4])|Q\d{1,2}|Heading\s+[1-6]|H[1-6]\s+heading)\s*:\s*|(#{1,6})\s+)(.+)$",
    re.IGNORECASE,
)


def norm(line):
    """Strip markdown bold/italic markers and pandoc escape backslashes so
    structural markers match regardless of docx→md decoration."""
    return line.replace("\\", "").replace("**", "").replace("__", "").strip()


URL_HOST_RE = re.compile(r"https?://([^/\s\"'()\[\]>]+)", re.IGNORECASE)

# Config keys whose values define the client's own web canon. Competitor lists
# are deliberately NOT included — a competitor link in content should flag.
DOMAIN_KEYS = {"domain", "website", "flagship_domain", "bing_property",
               "gsc_property", "baseline_target_domain",
               "secondary_baseline_domain"}


def _norm_host(host):
    host = host.lower().split(":")[0].strip(".")
    return host[4:] if host.startswith("www.") else host


def load_config_phrases(config_path):
    """Return (forbidden, required, allowed_phones, allowed_domains). Each
    forbidden/required entry is (raw_string, reason). Tolerates both
    list-of-strings and list-of-{pattern, reason} shapes."""
    if yaml is None:
        sys.exit("PyYAML not available — cannot parse client-config.yml")
    data = yaml.safe_load(Path(config_path).read_text()) or {}

    def normalize(entries):
        """Each entry → dict with pattern, reason, severity (error|warning|flag,
        default error), and optional approved_alternative for guided rewrites."""
        out = []
        for e in entries or []:
            if isinstance(e, dict):
                out.append({"pattern": str(e.get("pattern", "")),
                            "reason": str(e.get("reason", "")),
                            "severity": str(e.get("severity", "error")).lower(),
                            "alt": str(e.get("approved_alternative", ""))})
            elif isinstance(e, str):
                out.append({"pattern": e, "reason": "client config",
                            "severity": "error", "alt": ""})
        return [r for r in out if r["pattern"]]

    forbidden = normalize(data.get("forbidden_phrases"))
    required = normalize(data.get("required_phrases"))

    # HTML-scoped patterns ('(?i)>\s*[^<]*CORE[^<]*<' — written for the v2
    # built-HTML gate's text nodes) can never fire on markdown. Derive a
    # markdown variant of the core automatically, guarded against slug/URL
    # matches, so the same config serves both consumers with no per-client
    # overlay files. Generic by construction — works for any client config.
    html_wrap = re.compile(r"^\(\?i\)>\\s\*\[\^<\]\*(.+?)\[\^<\]\*<$")
    for rule in list(forbidden):
        m = html_wrap.match(rule["pattern"])
        if m:
            core = m.group(1)
            forbidden.append({
                "pattern": rf"(?i)(?<![/\w-]){core}(?![\w-]*/)",
                "reason": rule["reason"][:140] + " [markdown-derived from HTML-scoped rule]",
                "severity": rule["severity"], "alt": rule["alt"]})

    # Every phone-shaped string anywhere in the config is an allowed phone
    # (covers nap, per-state office DIDs, and audit-trail allowlists).
    # Allowed domains: the client's own canon — URL values anywhere in the
    # config (website, socials, GBP) plus bare domains under DOMAIN_KEYS.
    allowed_phones = set()
    allowed_domains = set()

    def walk(node, key=None):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, str):
            # nap.allowlist documents phones that may appear in CODE COMMENTS
            # (audit trails, JSDoc examples) — they are NOT allowed in content.
            # A dead onboarding number once rode through 164 times because the
            # allowlist was honored here. Content canon = real NAP/office lines.
            if key != "allowlist":
                for m in PHONE_RE.findall(node):
                    allowed_phones.add(re.sub(r"\D", "", m))
            for h in URL_HOST_RE.findall(node):
                allowed_domains.add(_norm_host(h))
            if key in DOMAIN_KEYS:
                bare = node.replace("sc-domain:", "").strip().strip("/")
                if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", bare):
                    allowed_domains.add(_norm_host(bare))

    walk(data)
    return forbidden, required, allowed_phones, allowed_domains


def compile_pattern(raw):
    """Compile a config pattern as regex; fall back to literal."""
    try:
        return re.compile(raw, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(raw), re.IGNORECASE)


def title_case_violations(text):
    """Return lowercase words violating the Title Case heading rule.
    Tokens containing digits ("1990s", "24/7") are never flagged, but they
    still occupy their position so first/last-word logic stays correct."""
    # A linked heading carries a URL that is not visible copy. Reduce
    # "[Display Text](https://host/some-slug/)" to "Display Text" before
    # judging case, or slug words ("product", "clean") get flagged as
    # lowercase heading words. Also drop pandoc span markers.
    text = re.sub(r"\]\((?:[^)\s]+)\)", "]", text)
    text = re.sub(r"\{\.[a-z-]+\}", "", text)

    # Interrogative headings are exempt. FAQ questions are natural-language
    # sentences that feed FAQPage schema and voice/AI extraction; Title Case
    # ("Do I Need A Permit?") reads wrong and degrades those surfaces. The
    # engine's own preflight agrees — it rates heading case CURATE, not
    # blocking. See distiller/CHANGELOG.md 2026-08-03.
    if text.rstrip("*_ \t").endswith("?"):
        return []
    words = re.findall(r"[\w'’-]+", text)
    bad = []
    for i, w in enumerate(words):
        if any(c.isdigit() for c in w):
            continue
        if w[0].islower() and not any(c.isupper() for c in w):
            if i == 0 or i == len(words) - 1 or w.lower() not in TITLE_CASE_ALLOW:
                bad.append(w)
    return bad


def scan(doc_path, config_path, banned_path):
    lines = Path(doc_path).read_text(errors="replace").splitlines()
    text = "\n".join(lines)
    findings = []

    def add(sev, rule, lineno, detail):
        findings.append({"severity": sev, "rule": rule, "line": lineno, "detail": detail})

    forbidden, required, allowed_phones, allowed_domains = ([], [], set(), set())
    if config_path:
        forbidden, required, allowed_phones, allowed_domains = load_config_phrases(config_path)

    if banned_path:
        # Flat-file lines are LITERAL — re.escape()d on load. Regex syntax
        # written into a txt file is silently inert (a '$' becomes a literal
        # dollar sign here, but as regex it would be an end-anchor that never
        # matches). Regex rules belong in the YAML config's forbidden_phrases.
        for raw in Path(banned_path).read_text().splitlines():
            raw = raw.strip()
            if raw and not raw.startswith(("#", "//")):
                forbidden.append({"pattern": re.escape(raw),
                                  "reason": "banned-phrases.txt",
                                  "severity": "error", "alt": ""})

    # 1. Client forbidden phrases. Severity per rule: error → BLOCK (gate
    # fails), warning → WARN, flag → FLAG (surface for the human, no forced
    # rewrite). approved_alternative rides along so rewrites are guided.
    SEV = {"error": "BLOCK", "warning": "WARN", "flag": "FLAG"}
    for rule in forbidden:
        rx = compile_pattern(rule["pattern"])
        for i, line in enumerate(lines, 1):
            m = rx.search(line)
            if m:
                detail = f"'{m.group(0)[:60]}' — {rule['reason'][:100] or rule['pattern']}"
                if rule["alt"]:
                    detail += f" → USE: {rule['alt'][:80]}"
                add(SEV.get(rule["severity"], "BLOCK"), "forbidden-phrase", i, detail)

    # 2. Required phrases missing from the whole doc (BLOCK)
    for rule in required:
        if rule["pattern"] in text or compile_pattern(rule["pattern"]).search(text):
            continue
        add("BLOCK", "required-phrase-missing", 0,
            f"'{rule['pattern']}' absent from document — {rule['reason'][:100]}")

    # 2b. Config self-consistency: conflicting years-in-business values inside
    # the config itself (e.g. trust_signals says 17, bio prose says 16+).
    # Configs rot silently. Reported as FLAG: a human picks the true number.
    if config_path:
        cfg_text = Path(config_path).read_text()
        # Match both prose form ("16+ years") and the canonical field form
        # ("years_in_business: 17") — v1.2 run found the field form was
        # invisible to the prose regex, silently hiding the 17-vs-16 conflict.
        years_found = set(re.findall(r"\b(\d{1,2})\+?\s*years?\b", cfg_text, re.I))
        years_found |= set(re.findall(r"years_in_business\w*:\s*\"?(\d{1,2})\b", cfg_text))
        if len(years_found) > 1:
            add("FLAG", "config-inconsistency", 0,
                f"config states conflicting year counts: {sorted(years_found)} — confirm with client, fix config")

    # 3. Em dashes (BLOCK — public-viewable copy rule)
    for i, line in enumerate(lines, 1):
        if "—" in line:
            add("BLOCK", "em-dash", i, line.strip()[:80])

    # 4. AI slop
    for pat in SLOP_BLOCK:
        rx = re.compile(pat, re.IGNORECASE)
        for i, line in enumerate(lines, 1):
            if rx.search(line):
                add("BLOCK", "ai-slop", i, f"'{rx.search(line).group(0)}'")
    for pat in SLOP_WARN:
        rx = re.compile(pat, re.IGNORECASE)
        for i, line in enumerate(lines, 1):
            if rx.search(line):
                add("WARN", "ai-slop-soft", i, f"'{rx.search(line).group(0)}'")

    # 5. Titles / meta descriptions length
    def value_at(idx, inline_val):
        """Inline value, or the next non-empty normalized line (pandoc splits
        label and value across lines)."""
        if inline_val.strip():
            return inline_val.strip(), idx + 1
        for j in range(idx + 1, min(idx + 4, len(lines))):
            nv = norm(lines[j])
            if nv:
                return nv, j + 1
        return "", idx + 1

    def eff_len(s):
        """Length as the BUILT html measures it: '&' ships as '&amp;' (5 chars).
        A 152-char raw description with two ampersands renders at 160 and fails
        the built gate — measure what ships, not what is typed (v1.6)."""
        return len(s) + 4 * s.count("&")

    for i, line in enumerate(lines):
        nline = norm(line)
        m = TITLE_LINE.match(nline)
        if m:
            val, lineno = value_at(i, m.group(1))
            if val and not 30 <= eff_len(val) <= 60:
                add("BLOCK", "title-length", lineno,
                    f"{eff_len(val)} effective chars (need 30-60): '{val[:70]}'")
        m = DESC_LINE.match(nline)
        if m:
            val, lineno = value_at(i, m.group(1))
            # 130-150 effective — the ONE band (engine validators/preflight and
            # the Content Team Operating Standard §04 agree; the old 120-155
            # disagreed with the emit gate at both edges, and 151-155 passed
            # here then HELD at emit).
            if val and not 130 <= eff_len(val) <= 150:
                add("BLOCK", "meta-desc-length", lineno,
                    f"{eff_len(val)} effective chars (need 130-150)")

    # 6. Headings: Title Case + contractions
    contraction_rx = re.compile(HEADING_CONTRACTIONS, re.IGNORECASE)
    for i, line in enumerate(lines, 1):
        m = HEADING_LINE.match(norm(line))
        if not m:
            continue
        htext = m.group(3).strip()
        if contraction_rx.search(htext):
            # Interrogative headings (FAQ questions) are natural-language
            # sentences; a contraction there is a style judgment, not a
            # shippable defect — surface it, don't block (mirrors the v1.3
            # Title Case exemption).
            if htext.rstrip("*_ \t").endswith("?"):
                add("WARN", "heading-contraction-question", i, htext[:80])
            else:
                add("BLOCK", "heading-contraction", i, htext[:80])
        bad = title_case_violations(htext)
        if bad:
            add("BLOCK", "heading-title-case", i,
                f"lowercase: {', '.join(bad[:5])} in '{htext[:60]}'")

    # 7. Phone numbers not in client canon
    if allowed_phones:
        for i, line in enumerate(lines, 1):
            for m in PHONE_RE.findall(line):
                digits = re.sub(r"\D", "", m)
                if digits not in allowed_phones:
                    add("BLOCK", "phone-mismatch", i,
                        f"'{m}' not an allowed NAP/office phone")

    # 7b. License-scope language (WARN — public-adjusting class promises)
    for pat in LICENSE_SCOPE:
        rx = re.compile(pat, re.IGNORECASE)
        for i, line in enumerate(lines, 1):
            m = rx.search(line)
            if m:
                add("WARN", "license-scope", i,
                    f"'{m.group(0)[:60]}' — possible work outside trade license (public-adjusting class); verify vs client license + state law")

    # 8. Foreign-domain links (WARN — wrong-client contamination detector).
    # Links to domains outside the client's own canon get flagged for judgment:
    # legit external cites (statutes, manufacturers) pass review; another
    # client's blog does not.
    if allowed_domains:
        for i, line in enumerate(lines, 1):
            for h in URL_HOST_RE.findall(line):
                host = _norm_host(h)
                if host in allowed_domains:
                    continue
                if any(host.endswith("." + d) for d in allowed_domains):
                    continue
                add("WARN", "foreign-domain-link", i,
                    f"'{host}' outside client canon — verify not wrong-client contamination")

    # 9. Fact gate (WARN — verify each against config trust signals)
    for pat, label in FACT_GATE:
        rx = re.compile(pat, re.IGNORECASE)
        for i, line in enumerate(lines, 1):
            m = rx.search(line)
            if m:
                add("WARN", "fact-gate", i, f"{label}: '{m.group(0)}'")

    return findings


def main():
    ap = argparse.ArgumentParser(description="seo-distiller deterministic gate")
    ap.add_argument("doc")
    ap.add_argument("--config", help="client-config.yml path")
    ap.add_argument("--banned", help="flat banned-phrases.txt path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not Path(args.doc).exists():
        sys.exit(2)

    findings = scan(args.doc, args.config, args.banned)
    blocks = [f for f in findings if f["severity"] == "BLOCK"]
    warns = [f for f in findings if f["severity"] == "WARN"]
    flags = [f for f in findings if f["severity"] == "FLAG"]

    if args.json:
        print(json.dumps({"blocks": len(blocks), "warns": len(warns),
                          "flags": len(flags), "findings": findings}, indent=2))
    else:
        for f in findings:
            print(f"{f['severity']:5s} L{f['line']:<5d} {f['rule']:24s} {f['detail']}")
        print(f"\n{len(blocks)} BLOCK, {len(warns)} WARN, {len(flags)} FLAG "
              f"({Path(args.doc).name})")

    sys.exit(1 if blocks else 0)


if __name__ == "__main__":
    main()
