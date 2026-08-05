#!/usr/bin/env python3
"""
brief-fanout-check.py — producibility gate for content briefs (§19), pre-DRAFT.

Doctrine (§19): every page starts life as a *brief*, not as prose. The brief is
the machine-checkable contract the draft must satisfy, so the expensive content
gates (capsule §20, non-commodity §21) become producible-by-DEFAULT instead of
audited-after. This gate runs at the content-generation step on the emitter's
`docs/briefs/*.json` output and refuses to let a thin/commodity brief reach the
drafting model.

What a valid brief MUST carry (all five, per brief):
  1. fanout        >= N distinct sub-intents / entities the page must cover
                   (min_fanout, default 6; case-insensitive dedupe).
  2. capsule       the AI-liftable unit: an INTERROGATIVE H2 (ends in "?"),
                   an answer-first block (a real sentence, not a fragment),
                   and a TL;DR. Mirrors capsule-check.py (§20) so a brief that
                   passes here cannot fail the draft-time capsule gate on shape.
  3. semantic_triples  >= 1 well-formed (subject, predicate, object) triple —
                   the structured claim the page asserts as an entity.
  4. proprietary_variable  a per-page proprietary variable (crew name, a local
                   street, a job count) that must be in the client's allow-list.
                   This is the non-commodity moat (§21) declared up front.
  5. intent        one of the search-intent enum values.

Config (read GRACEFULLY from docs/client-config.yml via common.load_config; every
key is optional and defaults so an un-provisioned repo never KeyErrors):
  brief:
    min_fanout: 6
    intent_enum: [informational, commercial, transactional, navigational]
    proprietary_variables: [crew_size, neighborhoods, streets, ...]   # allow-list
    min_answer_words: 8
CLI overrides: --min-fanout, --intent-enum, --allowlist, --min-answer-words.

Allow-list policy: if NO allow-list is configured (config absent AND no
--allowlist), the in-allow-list sub-check is SKIPPED with a WARN rather than
failing — the gate still validates that a proprietary_variable is present and
non-empty. It only enforces membership when an allow-list actually exists, so an
un-provisioned repo is not silently red-gated on a key it never set.

Blocked-on-input: `docs/briefs/` is a NEW artifact the emitter must produce. Until
it does, this gate finds zero briefs and exits 0 with a NOTE (nothing to validate
is not a failure). Its first useful output is a real RED on a real bad brief.

Exit codes:
    0  every brief valid (or no briefs found yet — blocked-on-input)
    2  usage / dependency error
    9  one or more briefs invalid (lists brief:field: reason)

Usage:
    brief-fanout-check.py PROJECT_DIR
    brief-fanout-check.py --briefs-dir path/to/briefs --allowlist crew_size,streets
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path


def _load_common():
    """Return the shared pipeline lib module, or None if it cannot be imported."""
    try:
        from pipeline.lib import common  # type: ignore
        return common
    except Exception:
        return None


DEFAULT_INTENT_ENUM = ["informational", "commercial", "transactional", "navigational"]
DEFAULT_MIN_FANOUT = 6
DEFAULT_MIN_ANSWER_WORDS = 8


def load_cfg(project_dir: str | None, config_path: str | None) -> dict:
    """Load client-config.yml gracefully. Never raises on a missing config —
    returns {} so every downstream .get() falls to its default."""
    if config_path:
        p = Path(config_path)
        if p.is_file():
            try:
                import yaml
                return yaml.safe_load(p.read_text()) or {}
            except Exception:
                return {}
        return {}
    if not project_dir:
        return {}
    common = _load_common()
    cfg_path = Path(project_dir) / "docs" / "client-config.yml"
    if not cfg_path.is_file():
        return {}
    if common is not None:
        try:
            return common.load_config(project_dir) or {}
        except SystemExit:
            # common.load_config exits if the file is missing; we already checked
            # it exists, so a SystemExit here means a parse problem — degrade to {}.
            return {}
        except Exception:
            return {}
    try:
        import yaml
        return yaml.safe_load(cfg_path.read_text()) or {}
    except Exception:
        return {}


def _distinct_ci(items) -> int:
    seen = set()
    for it in items:
        if isinstance(it, str) and it.strip():
            seen.add(it.strip().lower())
    return len(seen)


def _word_count(s: str) -> int:
    return len([w for w in str(s).split() if w.strip()])


def validate_brief(brief: dict, *, min_fanout: int, intent_enum: list,
                   allowlist: set, min_answer_words: int) -> list[str]:
    """Return a list of failure strings for one brief ([] == valid). Never raises
    on a missing/mistyped field — a missing field is itself a reported failure."""
    fails: list[str] = []

    # 1. fanout ---------------------------------------------------------------
    fanout = brief.get("fanout")
    if not isinstance(fanout, list):
        fails.append(f"fanout: missing or not a list (need >= {min_fanout} distinct terms)")
    else:
        n = _distinct_ci(fanout)
        if n < min_fanout:
            fails.append(f"fanout: only {n} distinct term(s), need >= {min_fanout}")

    # 2. capsule --------------------------------------------------------------
    capsule = brief.get("capsule")
    if not isinstance(capsule, dict):
        fails.append("capsule: missing or not an object (need interrogative_h2 + answer_first + tldr)")
    else:
        h2 = str(capsule.get("interrogative_h2") or "").strip()
        if not h2:
            fails.append("capsule.interrogative_h2: missing")
        elif not h2.endswith("?"):
            fails.append(f"capsule.interrogative_h2: not interrogative (must end in '?'): {h2[:60]!r}")
        ans = str(capsule.get("answer_first") or "").strip()
        if not ans:
            fails.append("capsule.answer_first: missing")
        elif _word_count(ans) < min_answer_words:
            fails.append(f"capsule.answer_first: fragment ({_word_count(ans)} words, need >= {min_answer_words})")
        tldr = str(capsule.get("tldr") or "").strip()
        if not tldr:
            fails.append("capsule.tldr: missing")

    # 3. semantic_triples -----------------------------------------------------
    triples = brief.get("semantic_triples")
    if not isinstance(triples, list) or not triples:
        fails.append("semantic_triples: need >= 1 (subject, predicate, object) triple")
    else:
        valid = 0
        for t in triples:
            if isinstance(t, dict):
                if all(str(t.get(k) or "").strip() for k in ("subject", "predicate", "object")):
                    valid += 1
            elif isinstance(t, (list, tuple)) and len(t) == 3 and all(str(x).strip() for x in t):
                valid += 1
        if valid < 1:
            fails.append("semantic_triples: no well-formed triple (each needs non-empty subject/predicate/object)")

    # 4. proprietary_variable -------------------------------------------------
    pv = str(brief.get("proprietary_variable") or "").strip()
    if not pv:
        fails.append("proprietary_variable: missing (the non-commodity moat, §21)")
    elif allowlist and pv.lower() not in allowlist:
        fails.append(f"proprietary_variable: {pv!r} not in allow-list ({sorted(allowlist)})")

    # 5. intent ---------------------------------------------------------------
    intent = str(brief.get("intent") or "").strip().lower()
    if not intent:
        fails.append(f"intent: missing (expected one of {intent_enum})")
    elif intent not in {i.lower() for i in intent_enum}:
        fails.append(f"intent: {intent!r} not in enum {intent_enum}")

    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate pre-draft content briefs (§19).")
    ap.add_argument("project", nargs="?", default=".", help="Project dir (briefs at PROJECT/docs/briefs/)")
    ap.add_argument("--briefs-dir", default=None, help="Explicit briefs dir (default PROJECT/docs/briefs)")
    ap.add_argument("--config", default=None, help="Explicit client-config.yml path")
    ap.add_argument("--min-fanout", type=int, default=None)
    ap.add_argument("--min-answer-words", type=int, default=None)
    ap.add_argument("--intent-enum", default=None, help="Comma-separated intent enum override")
    ap.add_argument("--allowlist", default=None, help="Comma-separated proprietary_variable allow-list override")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    cfg = load_cfg(project if args.briefs_dir is None else args.project, args.config)
    brief_cfg = cfg.get("brief") or {}

    min_fanout = args.min_fanout if args.min_fanout is not None else int(brief_cfg.get("min_fanout", DEFAULT_MIN_FANOUT))
    min_answer_words = (args.min_answer_words if args.min_answer_words is not None
                        else int(brief_cfg.get("min_answer_words", DEFAULT_MIN_ANSWER_WORDS)))
    if args.intent_enum:
        intent_enum = [s.strip() for s in args.intent_enum.split(",") if s.strip()]
    else:
        intent_enum = brief_cfg.get("intent_enum") or DEFAULT_INTENT_ENUM

    if args.allowlist is not None:
        allow_src = [s.strip() for s in args.allowlist.split(",") if s.strip()]
    else:
        allow_src = (brief_cfg.get("proprietary_variables")
                     or brief_cfg.get("proprietary_variable_allowlist")
                     or cfg.get("proprietary_variables") or [])
    allowlist = {str(s).strip().lower() for s in allow_src if str(s).strip()}
    if not allowlist:
        print("[WARN] no proprietary_variable allow-list configured "
              "(brief.proprietary_variables / --allowlist) — membership check SKIPPED; "
              "still requiring a non-empty proprietary_variable per brief.", file=sys.stderr)

    briefs_dir = args.briefs_dir or os.path.join(project, "docs", "briefs")
    briefs_dir = os.path.abspath(briefs_dir)
    if not os.path.isdir(briefs_dir):
        print(f"[NOTE] no briefs dir at {briefs_dir} — docs/briefs/ is emitter-produced "
              f"(blocked-on-input). Nothing to validate; exiting clean.")
        return 0

    files = sorted(glob.glob(os.path.join(briefs_dir, "**", "*.json"), recursive=True))
    if not files:
        print(f"[NOTE] no *.json briefs under {briefs_dir} — nothing to validate; exiting clean.")
        return 0

    total_fail = 0
    bad_briefs = 0
    for f in files:
        rel = os.path.relpath(f, briefs_dir)
        try:
            data = json.loads(Path(f).read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            bad_briefs += 1
            total_fail += 1
            print(f"  {rel}: INVALID JSON — {e}")
            continue
        # a briefs file may hold one brief object or a list of briefs
        briefs = data if isinstance(data, list) else [data]
        for idx, brief in enumerate(briefs):
            label = rel if len(briefs) == 1 else f"{rel}[{idx}]"
            if not isinstance(brief, dict):
                bad_briefs += 1
                total_fail += 1
                print(f"  {label}: not a brief object")
                continue
            fails = validate_brief(brief, min_fanout=min_fanout, intent_enum=intent_enum,
                                   allowlist=allowlist, min_answer_words=min_answer_words)
            if fails:
                bad_briefs += 1
                for msg in fails:
                    total_fail += 1
                    print(f"  {label}: {msg}")

    print(f"brief-fanout-check: scanned {len(files)} brief file(s) under {briefs_dir}")
    if total_fail:
        print(f"FAIL: {total_fail} violation(s) across {bad_briefs} invalid brief(s). "
              f"Fix the brief before drafting (§19).")
        return 9
    print(f"PASS: all briefs valid (fanout>={min_fanout}, capsule, >=1 triple, "
          f"proprietary_variable{' in allow-list' if allowlist else ''}, intent enum).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
