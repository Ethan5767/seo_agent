#!/usr/bin/env python3
"""
robots-aicrawler-check.py — STATIC, build-time AI-crawler robots.txt gate (T05).

The static companion to cf-crawler-check.sh. That script catches an EDGE block
(Cloudflare) on the live URL post-deploy; this one runs pre-deploy on the built
`out/robots.txt` and catches the other half: a robots.txt that Disallows a
citation crawler, or a missing robots.txt altogether.

Doctrine (AEO pillar): the citation crawlers that feed AI answers WITH a link
back — OAI-SearchBot, ChatGPT-User, PerplexityBot, Bingbot, Googlebot,
Claude-SearchBot — MUST be allowed. A `Disallow: /` reaching any of them zeroes
AEO while every build metric stays green. Training/corpus crawlers
(GPTBot, ClaudeBot, Google-Extended, CCBot) are INFO-only — blocking them is a
legitimate privacy choice and never turns the gate RED.

A MISSING robots.txt is RED with a "generate robots.txt" finding: the pipeline
wants an EXPLICIT robots.txt that Allows the citation set and (optionally)
Disallows the training set, not an implicit default-allow.

UA lists resolve env override > client-config.yml > hardcoded defaults, so a
vendor bot-rename is a one-line env/config change, never a code edit:
    CITATION_UAS / TRAINING_UAS   (space/comma-separated tokens)
    config keys: top-level `citation_uas` / `training_uas`, OR nested under
                 `ai_crawlers:` — absent keys default gracefully (no KeyError).

Exit codes:
    0  GREEN — robots.txt present and every citation UA is allowed at root
    1  RED   — missing robots.txt, OR any citation UA Disallowed from root

Usage:
    robots-aicrawler-check.py --out ./out
    robots-aicrawler-check.py --robots ./out/robots.txt
    robots-aicrawler-check.py --out ./out --project /path/to/client   # reads config UA lists
"""
from __future__ import annotations

import argparse
import os
import re
import sys

# ── Hardcoded sane defaults ────────────────────────────────────────────────
DEFAULT_CITATION_UAS = [
    "OAI-SearchBot", "ChatGPT-User", "PerplexityBot",
    "Bingbot", "Googlebot", "Claude-SearchBot",
]
DEFAULT_TRAINING_UAS = ["GPTBot", "ClaudeBot", "Google-Extended", "CCBot"]


def _split(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        toks = [str(v).strip() for v in value]
    else:
        toks = re.split(r"[,\s]+", str(value))
    return [t for t in (s.strip() for s in toks) if t]


def _config_uas(project: str | None, config_path: str | None) -> tuple[list[str], list[str]]:
    """Read citation/training UA lists from client-config.yml if present. Returns
    (citation, training); either may be empty. Never raises — a missing file,
    missing key, or absent PyYAML all degrade to empty (defaults take over)."""
    path = None
    if config_path:
        path = config_path
    elif project:
        path = os.path.join(project, "docs", "client-config.yml")
    if not path or not os.path.isfile(path):
        return [], []
    try:
        import yaml  # optional dependency; absence is non-fatal here
    except Exception:
        return [], []
    try:
        with open(path) as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception:
        return [], []
    if not isinstance(cfg, dict):
        return [], []
    block = cfg.get("ai_crawlers") if isinstance(cfg.get("ai_crawlers"), dict) else {}
    cit = _split(block.get("citation_uas") or cfg.get("citation_uas"))
    trn = _split(block.get("training_uas") or cfg.get("training_uas"))
    return cit, trn


def resolve_ua_lists(project, config_path):
    """env override > config file > hardcoded defaults."""
    cfg_cit, cfg_trn = _config_uas(project, config_path)
    citation = _split(os.environ.get("CITATION_UAS")) or cfg_cit or list(DEFAULT_CITATION_UAS)
    training = _split(os.environ.get("TRAINING_UAS")) or cfg_trn or list(DEFAULT_TRAINING_UAS)
    return citation, training


# ── robots.txt parsing ─────────────────────────────────────────────────────
def parse_groups(text: str):
    """Parse robots.txt into [(agents_lower[], rules[(type, path)])]. A new group
    begins at the first User-agent line after any rule line (consecutive
    User-agent lines share one group, per the robots spec)."""
    groups = []
    agents: list[str] = []
    rules: list[tuple[str, str]] = []
    started_rules = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            if started_rules and agents:
                groups.append((agents, rules))
                agents, rules, started_rules = [], [], False
            agents.append(value.lower())
        elif field in ("allow", "disallow"):
            started_rules = True
            rules.append((field, value))
        # sitemap/host/crawl-delay etc. are ignored
    if agents:
        groups.append((agents, rules))
    return groups


def _agent_matches(agent: str, ua_l: str) -> bool:
    if agent == "*":
        return False  # wildcard handled separately
    # robots UA matching is substring/prefix based and case-insensitive
    return agent == ua_l or ua_l.startswith(agent) or agent.startswith(ua_l) or agent in ua_l


def rules_for_ua(groups, ua: str):
    """Return (rules, matched_specifically). A specific group beats the wildcard
    group; if neither matches, returns (None, False) meaning default-allow."""
    ua_l = ua.lower()
    specific = None
    wildcard = None
    for agents, rules in groups:
        for a in agents:
            if a == "*":
                if wildcard is None:
                    wildcard = rules
            elif _agent_matches(a, ua_l):
                specific = rules  # last specific match wins
    if specific is not None:
        return specific, True
    return wildcard, False


def root_blocked(rules) -> bool:
    """True when a group Disallows the whole site (Disallow: /) at root with no
    equal-or-more-specific Allow overriding it. An empty `Disallow:` means
    allow-all and never blocks; a partial `Disallow: /somepath` does not block
    root, so it is not the AEO-zeroing case this gate guards."""
    if not rules:
        return False
    best_dis = -1
    best_allow = -1
    for typ, path in rules:
        if path == "/":  # whole-site rule
            if typ == "disallow":
                best_dis = max(best_dis, len(path))
            else:
                best_allow = max(best_allow, len(path))
    if best_dis < 0:
        return False
    if best_allow >= best_dis:  # Allow wins on a tie (Google semantics)
        return False
    return True


def resolve_robots_path(args) -> str:
    if args.robots:
        return os.path.abspath(args.robots)
    return os.path.abspath(os.path.join(args.out, "robots.txt"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail if built robots.txt blocks AI citation crawlers or is missing.")
    ap.add_argument("--out", default="./out", help="build output dir containing robots.txt")
    ap.add_argument("--robots", default=None, help="explicit path to robots.txt (overrides --out)")
    ap.add_argument("--project", default=None, help="client dir (reads docs/client-config.yml UA lists)")
    ap.add_argument("--config", default=None, help="explicit client-config.yml path for UA lists")
    args = ap.parse_args()

    citation, training = resolve_ua_lists(args.project, args.config)
    robots_path = resolve_robots_path(args)

    print("== robots-aicrawler-check (STATIC robots.txt) ==")
    print(f"robots.txt: {robots_path}")
    print(f"citation UAs (gating): {', '.join(citation)}")
    print(f"training UAs (INFO):   {', '.join(training)}")
    print()

    if not os.path.isfile(robots_path):
        print(f"  RED  robots.txt MISSING at {robots_path}")
        print()
        print("FAIL: no robots.txt in the build output.")
        print("  FINDING (generate robots.txt): ship an explicit robots.txt that")
        print("  Allows the citation crawlers and Disallows training crawlers, e.g.:")
        for ua in citation:
            print(f"    User-agent: {ua}\n    Allow: /\n")
        for ua in training:
            print(f"    User-agent: {ua}\n    Disallow: /\n")
        print("    Sitemap: https://<domain>/sitemap.xml")
        return 1

    with open(robots_path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    groups = parse_groups(text)

    red = 0
    for ua in citation:
        rules, specific = rules_for_ua(groups, ua)
        scope = "explicit group" if specific else ("wildcard *" if rules is not None else "no rule (default allow)")
        if root_blocked(rules):
            print(f"  RED  [{ua}] Disallow: / via {scope} — citation crawler BLOCKED in robots.txt")
            red += 1
        else:
            print(f"  PASS [{ua}] allowed at root ({scope})")

    print()
    print("-- training bots (INFO only, never gate) --")
    for ua in training:
        rules, specific = rules_for_ua(groups, ua)
        scope = "explicit group" if specific else ("wildcard *" if rules is not None else "no rule")
        state = "Disallowed" if root_blocked(rules) else "Allowed"
        print(f"  INFO [{ua}] {state} at root ({scope})")

    print()
    print(f"robots-aicrawler-check: {len(citation)} citation UA(s), {red} RED")
    if red:
        print(f"FAIL: {red} citation crawler(s) Disallowed in robots.txt.")
        print("  Fix: change their `Disallow: /` to `Allow: /` in the source that")
        print("  generates robots.txt. (This is the robots side; cf-crawler-check.sh")
        print("  covers the Cloudflare EDGE side post-deploy.)")
        return 1
    print("PASS: robots.txt allows every citation crawler at root.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
