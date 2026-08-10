#!/usr/bin/env python3
"""Rules self-test — the ruleset's own quality gate (NEVER baselineable).

The forbidden-phrase ruleset is legal-exposure code, but until this gate it was
the only code in the pipeline nothing tested. Three shipped bugs define the
classes it must catch by construction:

  BUG-018        a bare `$` in banned-phrases.txt is a regex anchor — the line
                 compiled fine, matched nothing, and enforced nothing for weeks
  BUG-019        a case-sensitive rule let "free system" ship past a lowercase ban
  union-defeat   Crestline's plain `free system` txt line silently defeated the YAML
                 rule's negative-lookahead exception through the union
                 (133 false blocks, July 2026)

Every check runs against the SAME union + compile path the built sweep uses
(imported from forbidden_sweep — nothing is reimplemented, so a passing fixture
proves the production matcher, not a copy of it).

  FAIL  a union pattern does not compile
  FAIL  regex metacharacters in banned-phrases.txt (dead literal rule)
  FAIL  a plain txt line defeats a YAML negative-lookahead exception
  FAIL  a docs/rule-fixtures.yml must_match sample no rule matches
  FAIL  a docs/rule-fixtures.yml must_not_match sample a rule matches
  FAIL  a negative-lookahead rule with no must_not_match fixture proving its
        exception still works through the union
  WARN  a letter-bearing YAML rule compiled case-sensitively (no `(?i)`) —
        annotate the rule `case_sensitive: true` if that is intentional
  WARN  no docs/rule-fixtures.yml yet (bootstrap — seed one to arm checks 4-6)
  WARN  rules no must_match fixture exercises

docs/rule-fixtures.yml:
  must_match:       # body-text samples ≥1 rule MUST flag
    - "We pay your deductible on every job."
  must_not_match:   # samples NO rule may flag (incl. every coded exception)
    - "Call today for a free system inspection."

Samples are scanned as `<p>{sample}</p>` so angle-bracket-anchored rules see
the same `>…<` context as built HTML; a sample that already starts with `<`
is scanned as-is (write `<h2>…</h2>` to exercise heading-anchored rules).

Usage: rules-selftest.py PROJECT_DIR [--config PATH]
Exit: 0 pass (warnings allowed) · 3 failures · 4 empty ruleset · 2 env error
"""
import sys, re, argparse
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML required. Run: pip3 install pyyaml", file=sys.stderr)
    sys.exit(2)

from pipeline.gates.forbidden_sweep import (
    load_phrases, lint_phrase_placement, read_txt_entries, _strip_lookarounds,
)
from pipeline.lib.common import ruleset_declared_empty

_LETTERS_RE = re.compile(r"[A-Za-z]")


def _as_scanned(sample: str) -> str:
    """Fixture samples are body text; give them the `>…<` context built HTML
    has, unless the author supplied their own markup."""
    return sample if sample.lstrip().startswith("<") else f"<p>{sample}</p>"


def selftest(project: Path, config_path: str | None = None):
    """Run every check. Returns (fails, warns, n_rules) — lists of strings."""
    fails: list = []
    warns: list = []

    rules, cfg = load_phrases(project, config_path)  # union + one lint print
    if not rules:
        return None, None, 0  # caller exits 4 — same fail-loud as the sweep

    # 1. compile — a rule that will not compile is a rule that enforces nothing.
    compiled: list = []
    for rule in rules:
        pat = str(rule.get("pattern") or "")
        try:
            compiled.append((rule, re.compile(pat)))
        except re.error as exc:
            fails.append(f"pattern does not compile: /{pat[:80]}/ — {exc} "
                         f"(reason: {rule.get('reason', '?')})")

    # 2+3. placement lint, escalated: in the sweep these are WARN-only by
    # contract; here the two fatal classes ARE the gate's reason to exist.
    cfg_rules = [r for r in (cfg.get("forbidden_phrases") or []) if isinstance(r, dict)]
    bp = project / "docs" / "banned-phrases.txt"
    for w in lint_phrase_placement(cfg_rules, read_txt_entries(bp), bp, emit=False):
        if w.code == "txt-metachar":
            fails.append(f"DEAD RULE (BUG-018 class): {w}")
        elif w.code == "union-defeat":
            fails.append(f"UNION DEFEAT (free system class): {w}")
        else:
            warns.append(str(w))

    # case audit (BUG-019 class) — YAML rules only: txt ledger lines already get
    # a global (?i) in load_phrases, so only the in-config block can be
    # case-sensitive in production.
    for rule in cfg_rules:
        pat = str(rule.get("pattern") or "")
        if not _LETTERS_RE.search(pat) or "(?i" in pat:
            continue
        if rule.get("case_sensitive") is True:
            continue
        warns.append(f"case-sensitive rule /{pat[:70]}/ — 'free system' shipped past a "
                     "lowercase ban this way (BUG-019). Add (?i), or annotate the rule "
                     "`case_sensitive: true` if intentional.")

    # 4-6. fixture self-test through the production matcher.
    fx_path = project / "docs" / "rule-fixtures.yml"
    if not fx_path.exists():
        warns.append(f"{fx_path.name} missing — the ruleset has no proof samples yet. "
                     "Seed must_match/must_not_match lists to arm the self-test "
                     "(bootstrap mode: this is a warning, not a failure).")
        return fails, warns, len(rules)

    fx = yaml.safe_load(fx_path.read_text()) or {}
    must = [str(s) for s in (fx.get("must_match") or []) if s]
    must_not = [str(s) for s in (fx.get("must_not_match") or []) if s]

    matched_patterns: set = set()
    for s in must:
        hits = [rule for rule, rx in compiled if rx.search(_as_scanned(s))]
        if not hits:
            fails.append(f"must_match NOT matched by any of {len(compiled)} rules: {s!r} "
                         "— either the sample is stale or a rule went dead.")
        matched_patterns.update(str(r.get("pattern")) for r in hits)
    for s in must_not:
        hits = [rule for rule, rx in compiled if rx.search(_as_scanned(s))]
        if hits:
            r = hits[0]
            fails.append(f"must_not_match MATCHED: {s!r} — rule /{str(r.get('pattern'))[:70]}/ "
                         f"(reason: {r.get('reason', '?')}). A coded exception or "
                         "legitimate phrasing is being blocked.")

    # exception coverage: a lookahead nobody proves is the free system failure
    # waiting to recur. Exercised = some must_not_match sample the rule's
    # lookaround-stripped base matches but the full rule (correctly) does not.
    for rule, rx in compiled:
        pat = str(rule.get("pattern"))
        if "(?!" not in pat:
            continue
        try:
            base = re.compile(_strip_lookarounds(pat), re.IGNORECASE)
        except re.error:
            continue
        if not any(base.search(_as_scanned(s)) and not rx.search(_as_scanned(s))
                   for s in must_not):
            fails.append(f"exception unproven: /{pat[:70]}/ carries a negative lookahead "
                         "but no must_not_match fixture exercises it — add a sample of "
                         "the excepted phrasing so the exception is proven through the "
                         "union every run.")

    uncovered = [str(r.get("pattern")) for r, _ in compiled
                 if str(r.get("pattern")) not in matched_patterns]
    if uncovered:
        head = " · ".join(p[:40] for p in uncovered[:5])
        warns.append(f"{len(uncovered)}/{len(compiled)} rules have no must_match fixture "
                     f"(first: {head}) — an edit that kills one fails nothing.")

    return fails, warns, len(rules)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("project")
    ap.add_argument("--config", default=None,
                    help="path to client-config.yml (default: PROJECT/docs/client-config.yml)")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    fails, warns, n_rules = selftest(project, args.config)
    if fails is None:
        # Same three-state contract as the sweep this gate guards. A ruleset that
        # a human has declared empty has nothing to self-test, and saying so is
        # not the same as passing — see common.ruleset_declared_empty.
        _, cfg = load_phrases(project, args.config)
        if ruleset_declared_empty(cfg, project):
            print("[SKIP] no ruleset to self-test: docs/client-config.yml declares "
                  "`forbidden_phrases: []`. This is a recorded human decision, not "
                  "a ruleset that passed.")
            return
        print("[FAIL] no forbidden_phrases loaded (checked config forbidden_phrases + "
              "docs/banned-phrases.txt). Refusing to self-test an empty legal ruleset. "
              "Declare `forbidden_phrases: []` in docs/client-config.yml to skip it "
              "deliberately.", file=sys.stderr)
        sys.exit(4)

    for w in warns:
        print(f"[WARN] {w}", file=sys.stderr)
    for f in fails:
        print(f"[FAIL] {f}")

    if fails:
        print(f"\n[BLOCKED] rules-selftest: {len(fails)} ruleset defects "
              f"({n_rules} union rules, {len(warns)} warnings).")
        sys.exit(3)
    print(f"\n[OK] rules-selftest clean — {n_rules} union rules proven "
          f"({len(warns)} warnings).")


if __name__ == "__main__":
    main()
