#!/usr/bin/env python3
"""Forbidden-phrase sweep — two modes.

  source  scan src/data/*.ts (+ extra globs) for forbidden phrases as raw word
          matches. Catches violations BEFORE build (e.g. a banned phrase in a
          services.ts template string that would render to body HTML on every
          spoke page).

  built   scan the built HTML (out/**/*.html) for forbidden phrases using the
          angle-bracket-aware patterns from client-config.yml forbidden_phrases[].
          <script> and <style> blocks are BLANKED first (line-preserving), so
          Next.js RSC flight payloads (self.__next_f.push([1,"...$1..."])) and
          inline JS/CSS never produce false positives. This is the same
          <script>/<style> masking em-dash-check.py uses.

Phrase source (Model A): the UNION of client-config.yml `forbidden_phrases:` in
the repo AND docs/banned-phrases.txt (one regex per line; `#` comments allowed),
deduped by pattern. A repo may carry BOTH a canonical ledger file and an in-config
block (Crestline's 60+ FL/MD/VA ledger, BLH-North's canonical ledger); unioning
means every rule fires instead of one source silently shadowing the other.
If NEITHER yields any pattern, the gate FAILS LOUD (exit 4) rather than passing
an empty legal check silently.

Both modes exit non-zero (3) on any hit so the pipeline blocks before deploy.

Usage:
  forbidden-sweep.py source PROJECT_DIR [extra_glob ...] [--config PATH]
  forbidden-sweep.py built  PROJECT_DIR [--build-dir DIR] [--config PATH]
"""
import sys, re, argparse
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML required. Run: pip3 install pyyaml", file=sys.stderr)
    sys.exit(2)

from pipeline.lib.common import load_config

# Blank <script>/<style> bodies so RSC flight payloads and inline JS/CSS are not
# scanned. Kept line-preserving so reported line numbers match the real file.
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def blank_keep_lines(m: "re.Match") -> str:
    return "\n" * m.group(0).count("\n")


# ── Placement lint — make the wrong-file footgun LOUD ────────────────────────
# the operator's rules-placement doctrine (2026-07-31): plain phrases belong in
# docs/banned-phrases.txt; regex rules belong in the client-config.yml
# forbidden_phrases: block. "Adding to the wrong file fails silently." The
# Crestline free system incident is the canonical failure: a plain `free system` txt
# line matched every form the YAML rule's negative lookahead deliberately
# excepts, silently defeating the coded exception (133 false blocks, July 2026).
# These checks WARN on stderr only — never fatal, never a detection change; the
# union of both sources stays the union.

#: Characters that change meaning when a "plain" txt line is compiled as regex.
#: Deliberately excludes `.` `%` `'` `-` `,` so ordinary prose stays quiet.
_REGEX_METACHARS_RE = re.compile(r"[\\()\[\]|*+?{}^$]")


class PlacementWarning(str):
    """A lint warning that is still a plain str (existing callers/tests keep
    working) but carries a machine-readable `.code` so rules_selftest can
    escalate the fatal classes (`txt-metachar`, `union-defeat`) to failures
    while this gate stays WARN-only by contract."""

    code: str

    def __new__(cls, code: str, msg: str):
        s = super().__new__(cls, msg)
        s.code = code
        return s


def read_txt_entries(bp: Path) -> list:
    """[(lineno, line)] non-comment lines of docs/banned-phrases.txt — THE one
    parser for the ledger file, shared with rules_selftest."""
    entries: list = []
    if bp.exists():
        for lineno, line in enumerate(bp.read_text(errors="replace").splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            entries.append((lineno, s))
    return entries


def _strip_lookarounds(pattern: str) -> str:
    """Pattern with every balanced (?!...) / (?=...) group removed."""
    out, i = [], 0
    while i < len(pattern):
        if pattern[i:i + 3] in ("(?!", "(?="):
            depth, j = 1, i + 3
            while j < len(pattern) and depth:
                if pattern[j] == "(" and pattern[j - 1] != "\\":
                    depth += 1
                elif pattern[j] == ")" and pattern[j - 1] != "\\":
                    depth -= 1
                j += 1
            i = j
        else:
            out.append(pattern[i])
            i += 1
    return "".join(out)


def _lookahead_bodies(pattern: str) -> list:
    """The inner text of every balanced (?!...) group in the pattern."""
    bodies, i = [], 0
    while i < len(pattern):
        if pattern[i:i + 3] == "(?!":
            depth, j = 1, i + 3
            while j < len(pattern) and depth:
                if pattern[j] == "(" and pattern[j - 1] != "\\":
                    depth += 1
                elif pattern[j] == ")" and pattern[j - 1] != "\\":
                    depth -= 1
                j += 1
            bodies.append(pattern[i + 3:j - 1])
            i = j
        else:
            i += 1
    return bodies


def lint_phrase_placement(cfg_rules: list, txt_entries: list, bp_path: Path,
                          emit: bool = True) -> list:
    """Heuristic placement warnings. Returns PlacementWarning strings (printed
    to stderr unless emit=False). WARN-only by contract in THIS gate: the sweep
    must never fail on these; rules_selftest escalates by `.code`.

    cfg_rules:   the in-config forbidden_phrases dicts (as authored)
    txt_entries: [(lineno, line)] non-comment lines of docs/banned-phrases.txt
    """
    warns: list = []
    plain_txt: list = []
    for lineno, line in txt_entries:
        if _REGEX_METACHARS_RE.search(line):
            warns.append(PlacementWarning(
                "txt-metachar",
                f"{bp_path}:{lineno}: {line!r} contains regex metacharacters, but this "
                "file is for PLAIN phrases (lines are compiled as regex, so '$', '(', '\\b' "
                "change meaning here — a '$' line can silently never match). Regex rules "
                "belong in the client-config.yml forbidden_phrases: block."))
        else:
            plain_txt.append((lineno, line))

    if bp_path.exists():
        for rule in cfg_rules:
            pat = str(rule.get("pattern") or "")
            core = pat[4:] if pat.startswith("(?i)") else pat
            if core and not _REGEX_METACHARS_RE.search(core):
                warns.append(PlacementWarning(
                    "yaml-plain-phrase",
                    f"client-config.yml forbidden_phrases: {pat!r} is a bare phrase with no "
                    f"regex construct — {bp_path.name} is the canonical home for plain phrases."))

    # The Crestline failure shape: a plain txt line that is a strict prefix of a
    # YAML rule carrying a negative lookahead, so the plain line also matches
    # the very forms the lookahead excepts.
    for rule in cfg_rules:
        pat = str(rule.get("pattern") or "")
        if "(?!" not in pat:
            continue
        try:
            rx_full = re.compile(pat)
        except re.error:
            continue
        try:
            rx_base = re.compile(_strip_lookarounds(pat), re.IGNORECASE)
        except re.error:
            continue
        words: list = []
        for body in _lookahead_bodies(pat):
            words += re.findall(r"[A-Za-z][A-Za-z-]{2,}", body)
        for lineno, line in plain_txt:
            if not rx_base.search(line):
                continue
            for w in words:
                sample = f"{line} {w}"
                if not rx_full.search(sample):
                    warns.append(PlacementWarning(
                        "union-defeat",
                        f"{bp_path}:{lineno}: plain line {line!r} is a prefix of the YAML rule "
                        f"/{pat[:70]}.../ whose negative lookahead deliberately ALLOWS forms like "
                        f"{sample!r} — the plain line matches those excepted forms too, silently "
                        "defeating the coded exception. Remove the plain line; the YAML rule "
                        "governs."))
                    break

    if emit:
        for w in warns:
            print(f"[LINT] {w}", file=sys.stderr)
    return warns


def load_phrases(project: Path, config_path: str | None):
    """Return (forbidden_rules, cfg). Rules are the UNION of the in-config
    forbidden_phrases block AND docs/banned-phrases.txt, deduped by pattern
    string. Neither source shadows the other, so a repo carrying BOTH a canonical
    ledger file and an in-config block enforces every rule. Order: in-config rules
    first (they carry richer reasons), then any banned-phrases.txt line not already
    present."""
    cfg = {}
    if config_path:
        p = Path(config_path)
        if not p.is_absolute() and not p.exists():
            p = project / config_path
        if p.exists():
            with open(p) as f:
                cfg = yaml.safe_load(f) or {}
        else:
            print(f"[WARN] --config {config_path} not found; trying in-repo config.", file=sys.stderr)
            cfg = load_config(str(project))
    else:
        cfg = load_config(str(project))

    rules: list = []
    seen: set = set()

    def add(rule: dict):
        pat = rule.get("pattern")
        if not pat or pat in seen:
            return
        seen.add(pat)
        rules.append(rule)

    for rule in (cfg.get("forbidden_phrases") or []):
        if isinstance(rule, dict):
            add(rule)

    bp = project / "docs" / "banned-phrases.txt"
    txt_entries = read_txt_entries(bp)
    for _lineno, s in txt_entries:
        # banned-phrases.txt entries are literal phrase bans (Crestline/BLH
        # ledgers are plain lowercase). Built-mode compiles patterns as-is, so
        # without a flag "We Waive Your Deductible" in a heading would escape a
        # lowercase ledger line. Prepend a global (?i) unless the line already
        # carries one, so the legal gate matches regardless of case.
        pat = s if "(?i)" in s else "(?i)" + s
        add({"pattern": pat, "reason": "docs/banned-phrases.txt"})

    n_cfg = len(cfg.get("forbidden_phrases") or [])
    if bp.exists() and n_cfg:
        print(f"[LEDGER] union: {n_cfg} in-config forbidden_phrases + "
              f"docs/banned-phrases.txt -> {len(rules)} unique patterns enforced.",
              file=sys.stderr)

    # Wrong-file placement lint — advisory only, guaranteed non-fatal.
    try:
        cfg_rules = [r for r in (cfg.get("forbidden_phrases") or []) if isinstance(r, dict)]
        lint_phrase_placement(cfg_rules, txt_entries, bp)
    except Exception as exc:  # pragma: no cover — the lint must never break the gate
        print(f"[LINT] placement lint failed (non-fatal): {exc}", file=sys.stderr)

    return rules, cfg


def derive_word_pattern(html_pattern: str):
    """Extract the bare word(s) from a body-text regex like
       '(?i)>\\s*[^<]*\\bbasement(s)?\\b[^<]*<' -> '\\bbasement(s)?\\b'."""
    m = re.search(r"\\b[^<>]*?\\b", html_pattern)
    return m.group(0) if m else None


def scan_source(project: Path, forbidden: list, cfg: dict, extra: list) -> int:
    repo = cfg.get("repo", {})
    repo_root = project  # Model A: the project dir IS the repo root (no nested client path).
    targets = []
    for rel in ("src/data", repo.get("data_overrides", ""), repo.get("data_services", ""), repo.get("data_cities", "")):
        if not rel:
            continue
        p = repo_root / rel
        if p.is_dir():
            targets += list(p.rglob("*.ts")) + list(p.rglob("*.tsx"))
        elif p.is_file():
            targets.append(p)
    for g in extra:
        targets += list(repo_root.glob(g))
    targets = sorted({t for t in targets if t.is_file()})

    # Slug-context exemptions: a forbidden word allowed when the surrounding entry
    # is intentionally scoped to a legacy slug (e.g. `basement-waterproofing`).
    SLUG_EXEMPTIONS = {
        "apartment": ["apartment-restoration"],
        "basement": ["basement-waterproofing"],
    }
    SLUG_WINDOW = 80

    # Disclosure-context: a same-line "we do NOT do this" / "law prohibits" phrasing
    # is a required compliance disclosure, not a marketing violation.
    DISCLOSURE_CONTEXT = re.compile(
        r"\b(prohibits?|prohibition|prohibited|forbids?|forbidden|"
        r"does\s+not|do\s+not|don't|doesn't|won't|will\s+not|cannot|can't|"
        r"never|no\s+(?:longer\s+)?accept|"
        r"not\s+offer(?:ing|ed)?|not\s+allow(?:ing|ed)?|"
        r"not\s+a\s+(?:public\s+adjuster|claim))",
        re.IGNORECASE,
    )
    NEGATION_PREFIX = re.compile(r"\bno\s+", re.IGNORECASE)

    hits = 0
    for rule in forbidden:
        raw_pattern = rule["pattern"]
        # Heading-anchored rules (e.g. contractions banned ONLY in headings) can't be
        # verified in source — headings are generated from data. Built mode enforces
        # them on rendered HTML with the anchor intact; skip here so legitimate body
        # prose isn't flagged (Defect #2, 2026-07-19).
        if re.search(r"<h\[1-6\]|#\{1,6\}", raw_pattern):
            continue
        if "<" in raw_pattern or ">" in raw_pattern:
            word = derive_word_pattern(raw_pattern)
        else:
            word = raw_pattern
        if not word:
            continue
        rx = re.compile(word, re.IGNORECASE)
        plain = re.search(r"\\b\s*([A-Za-z]+)", word)
        plain_word = plain.group(1).lower() if plain else None
        for f in targets:
            try:
                txt = f.read_text(errors="replace")
            except Exception:
                continue
            lines = txt.splitlines()
            for m in rx.finditer(txt):
                lineno = txt.count("\n", 0, m.start()) + 1
                line_start = txt.rfind("\n", 0, m.start()) + 1
                line_end = txt.find("\n", m.end())
                line = txt[line_start: line_end if line_end > 0 else len(txt)]
                if re.search(r"^\s*(import|from|//|\*|/\*)", line):
                    continue
                exempt_slugs = SLUG_EXEMPTIONS.get(plain_word or "", [])
                if exempt_slugs:
                    lo = max(0, lineno - 1 - SLUG_WINDOW)
                    hi = min(len(lines), lineno - 1 + SLUG_WINDOW)
                    window = "\n".join(lines[lo:hi]).lower()
                    if any(slug in window for slug in exempt_slugs):
                        continue
                if DISCLOSURE_CONTEXT.search(line):
                    continue
                pre_match = line[max(0, m.start() - line_start - 20): m.start() - line_start]
                if NEGATION_PREFIX.search(pre_match):
                    continue
                hits += 1
                print(f"[HIT] {f.relative_to(repo_root)}:{lineno}  {line.strip()[:140]}")
    return hits


def scan_built(project: Path, forbidden: list, cfg: dict, build_dir_override: str | None) -> int:
    repo = cfg.get("repo", {})
    if build_dir_override:
        build_dir = Path(build_dir_override).resolve()
    else:
        name = repo.get("build_output_dir") or repo.get("build_dir") or "out"
        build_dir = project / name
    # Tolerate being handed the build output directly (e.g. `built ./out`).
    if not build_dir.exists() and list(project.glob("*.html")):
        build_dir = project
    if not build_dir.exists():
        print(f"[FAIL] build dir {build_dir} missing — run `next build` first.")
        return 1

    htmls = list(build_dir.rglob("*.html"))
    print(f"[BUILT] scanning {len(htmls)} html files under {build_dir}")
    compiled = [(rule, re.compile(rule["pattern"])) for rule in forbidden]
    hits = 0
    for f in htmls:
        try:
            raw = f.read_text(errors="replace")
        except Exception:
            continue
        stripped = SCRIPT_STYLE_RE.sub(blank_keep_lines, raw)  # RSC/JS/CSS blanked
        for rule, rx in compiled:
            for m in rx.finditer(stripped):
                lineno = stripped.count("\n", 0, m.start()) + 1
                ctx = stripped[max(0, m.start() - 30): m.end() + 30].replace("\n", " ")
                hits += 1
                print(f"[HIT] {f.relative_to(build_dir)}:{lineno}  /{rule['pattern'][:50]}/  …{ctx}…")
    return hits


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("mode", choices=["source", "built"])
    ap.add_argument("project")
    ap.add_argument("extra", nargs="*", help="source mode: extra globs to scan")
    ap.add_argument("--config", default=None, help="path to client-config.yml (default: PROJECT/docs/client-config.yml)")
    ap.add_argument("--build-dir", default=None, help="built mode: explicit build output dir")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    forbidden, cfg = load_phrases(project, args.config)
    if not forbidden:
        print("[FAIL] no forbidden_phrases loaded (checked config forbidden_phrases + "
              "docs/banned-phrases.txt). Refusing to run an empty legal gate.", file=sys.stderr)
        sys.exit(4)

    if args.mode == "source":
        hits = scan_source(project, forbidden, cfg, args.extra)
    else:
        hits = scan_built(project, forbidden, cfg, args.build_dir)

    if hits:
        print(f"\n[BLOCKED] {hits} forbidden-phrase hits in {args.mode} mode."); sys.exit(3)
    print(f"\n[OK] {args.mode} mode clean — 0 forbidden-phrase hits ({len(forbidden)} patterns enforced).")


if __name__ == "__main__":
    main()
