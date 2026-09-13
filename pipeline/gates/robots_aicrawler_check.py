#!/usr/bin/env python3
"""
robots-aicrawler-check.py — STATIC, build-time AI-crawler robots.txt gate (T05).

The static companion to crawler-check.sh. That script catches an EDGE block
(Cloudflare) on the live URL post-deploy; this one runs pre-deploy on the built
`out/robots.txt` and catches the other half: a robots.txt that Disallows a
citation crawler, or a missing robots.txt altogether.

Doctrine (AEO pillar): the citation crawlers that feed AI answers WITH a link
back — OAI-SearchBot, PerplexityBot, Bingbot, Googlebot, Claude-SearchBot,
Applebot, Amzn-SearchBot, meta-webindexer — MUST be allowed. A `Disallow: /`
reaching any of them zeroes AEO while every build metric stays green.

Two other classes are reported and never gated, because grading them would
claim a control the client does not have:

  * TRAINING/corpus crawlers (GPTBot, ClaudeBot, Google-Extended, CCBot,
    meta-externalagent, Amazonbot, Applebot-Extended) — blocking them is a
    legitimate business choice and does not affect citation.
  * USER-TRIGGERED fetchers (ChatGPT-User, Perplexity-User, Amzn-User,
    meta-externalfetcher) — five of the six vendors state in their own docs that
    these may ignore robots.txt entirely. `Claude-User` is the sole exception
    and is labelled as such, because it is the one place in this class where the
    site owner's directive is documented to be respected.

A MISSING robots.txt is RED with a "generate robots.txt" finding: the pipeline
wants an EXPLICIT robots.txt that Allows the citation set and (optionally)
Disallows the training set, not an implicit default-allow.

UA lists resolve env override > client-config.yml > hardcoded defaults, so a
vendor bot-rename is a one-line env/config change, never a code edit:
    CITATION_UAS / TRAINING_UAS / USER_TRIGGERED_UAS  (space/comma-separated)
    config keys: top-level `citation_uas` / `training_uas` / `user_triggered_uas`,
                 OR nested under `ai_crawlers:` — absent keys default gracefully
                 (no KeyError).

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
#
# Three classes, because the vendors document three, and conflating them
# produces findings that are wrong in both directions.
#
# CITATION crawlers build the index an engine answers from. Every vendor
# documents that these honour robots.txt, so a Disallow here really does mean
# the site cannot be cited. This is the only class where "blocked" is a defect.
#
# TRAINING crawlers collect content to train models. Blocking them is a
# legitimate business choice and does not affect citation, so it is reported as
# information rather than a fault.
#
# USER-TRIGGERED fetchers run when a person asks the assistant about a page.
# **Five of the six major vendors state in their own documentation that these
# ignore robots.txt** - OpenAI ("robots.txt rules may not apply"), Perplexity
# ("generally ignores robots.txt rules"), Google ("generally ignore robots.txt
# rules"), Meta ("may bypass robots.txt rules"), Amazon ("may not follow all
# robots.txt directives"). Anthropic is the sole exception: its stated policy
# covers all three of its bots with no user-initiated carve-out.
#
# `ChatGPT-User` sat in the citation list until this was checked against
# OpenAI's docs. It is neither a citation crawler nor reliably blockable, so a
# "blocked" verdict on it told a client they were shut out of ChatGPT when they
# very likely were not, and a "passing" verdict promised a control they do not
# have. Both directions were wrong.
DEFAULT_CITATION_UAS = [
    "OAI-SearchBot", "PerplexityBot", "Bingbot", "Googlebot",
    "Claude-SearchBot", "Applebot", "Amzn-SearchBot", "meta-webindexer",
]
DEFAULT_TRAINING_UAS = [
    "GPTBot", "ClaudeBot", "Google-Extended", "CCBot",
    "meta-externalagent", "Amazonbot", "Applebot-Extended",
]

#: Fetchers that run on a person's request. Reported so an operator knows they
#: exist, never graded: a Disallow here is advisory at best, and treating one as
#: a pass would claim a control the vendor has disclaimed in writing.
DEFAULT_USER_TRIGGERED_UAS = [
    "ChatGPT-User", "Perplexity-User", "Amzn-User", "meta-externalfetcher",
]

#: The one user-triggered fetcher whose vendor states it honours robots.txt.
#: Worth naming rather than burying: it is the only place in this class where a
#: site owner's directive is documented to be respected.
ROBOTS_HONOURING_USER_UAS = ["Claude-User"]


def _split(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        toks = [str(v).strip() for v in value]
    else:
        toks = re.split(r"[,\s]+", str(value))
    return [t for t in (s.strip() for s in toks) if t]


def _config_uas(project: str | None, config_path: str | None) -> tuple[list[str], list[str], list[str]]:
    """Read the three UA lists from client-config.yml if present. Returns
    (citation, training, user_triggered); any may be empty. Never raises — a
    missing file, missing key, or absent PyYAML all degrade to empty (defaults
    take over)."""
    path = None
    if config_path:
        path = config_path
    elif project:
        path = os.path.join(project, "docs", "client-config.yml")
    if not path or not os.path.isfile(path):
        return [], [], []
    try:
        import yaml  # optional dependency; absence is non-fatal here
    except Exception:
        return [], [], []
    try:
        with open(path) as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception:
        return [], [], []
    if not isinstance(cfg, dict):
        return [], [], []
    block = cfg.get("ai_crawlers") if isinstance(cfg.get("ai_crawlers"), dict) else {}
    cit = _split(block.get("citation_uas") or cfg.get("citation_uas"))
    trn = _split(block.get("training_uas") or cfg.get("training_uas"))
    usr = _split(block.get("user_triggered_uas") or cfg.get("user_triggered_uas"))
    return cit, trn, usr


def resolve_ua_lists(project, config_path):
    """env override > config file > hardcoded defaults.

    Returns (citation, training, user_triggered). The third list is REPORTED and
    never graded — see the module docstring. `Claude-User` is appended to it from
    ROBOTS_HONOURING_USER_UAS unless the operator supplied their own list, so the
    one fetcher that does honour robots.txt is still named in the output.
    """
    cfg_cit, cfg_trn, cfg_usr = _config_uas(project, config_path)
    citation = _split(os.environ.get("CITATION_UAS")) or cfg_cit or list(DEFAULT_CITATION_UAS)
    training = _split(os.environ.get("TRAINING_UAS")) or cfg_trn or list(DEFAULT_TRAINING_UAS)
    user = (_split(os.environ.get("USER_TRIGGERED_UAS")) or cfg_usr
            or list(DEFAULT_USER_TRIGGERED_UAS) + list(ROBOTS_HONOURING_USER_UAS))
    return citation, training, user


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
    """Does a robots.txt `User-agent:` token address this crawler?

    ONE DIRECTION ONLY: the token matches when it is a case-insensitive PREFIX of
    the crawler's product token (RFC 9309 / Google's matcher). `Applebot` in
    robots.txt therefore addresses `Applebot-Extended`, and `Applebot-Extended`
    does NOT address `Applebot`.

    B-080. This used to match both directions plus a bare substring test, so a
    client doing the completely ordinary thing — allowing everything, then
    opting out of model training with `User-agent: Applebot-Extended` /
    `Disallow: /` — had that Disallow attributed to the CITATION crawler
    `Applebot`, and the gate went RED for blocking a crawler the client had
    explicitly allowed. The gate that exists to protect AEO was failing the PR
    for a correct robots.txt, and blocking training crawlers is documented right
    here as a legitimate choice that never gates.
    """
    if agent == "*":
        return False  # wildcard handled separately
    return ua_l.startswith(agent)


def rules_for_ua(groups, ua: str):
    """Return (rules, matched_specifically). The LONGEST matching token wins, then
    the wildcard group; if neither matches, returns (None, False) meaning
    default-allow.

    Longest-match rather than last-match, also B-080: with two groups addressing
    the same crawler at different specificities, "whichever appears last in the
    file" makes the verdict depend on the order a generator happened to emit."""
    ua_l = ua.lower()
    best_len = -1
    specific = None
    wildcard = None
    for agents, rules in groups:
        for a in agents:
            if a == "*":
                if wildcard is None:
                    wildcard = rules
            elif _agent_matches(a, ua_l) and len(a) > best_len:
                best_len, specific = len(a), rules
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

    citation, training, user_triggered = resolve_ua_lists(args.project, args.config)
    robots_path = resolve_robots_path(args)

    print("== robots-aicrawler-check (STATIC robots.txt) ==")
    print(f"robots.txt: {robots_path}")
    print(f"citation UAs (gating): {', '.join(citation)}")
    print(f"training UAs (INFO):   {', '.join(training)}")
    print(f"user-triggered (INFO): {', '.join(user_triggered)}")
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

    # User-triggered fetchers. Reported so an operator knows they exist, never
    # graded: five of the six vendors document that these may ignore robots.txt,
    # so both verdicts would be lies — "blocked" would tell a client they are shut
    # out when they very likely are not, and "allowed" would promise a control the
    # vendor has disclaimed in writing.
    print()
    print("-- user-triggered fetchers (INFO only, never gate) --")
    for ua in user_triggered:
        rules, specific = rules_for_ua(groups, ua)
        scope = "explicit group" if specific else ("wildcard *" if rules is not None else "no rule")
        state = "Disallowed" if root_blocked(rules) else "Allowed"
        honours = ua in ROBOTS_HONOURING_USER_UAS
        note = ("vendor states it honours robots.txt, so this directive is real"
                if honours else "vendor states robots.txt may not apply to this bot")
        print(f"  INFO [{ua}] {state} at root ({scope}) — {note}")

    print()
    print(f"robots-aicrawler-check: {len(citation)} citation UA(s), {red} RED")
    if red:
        print(f"FAIL: {red} citation crawler(s) Disallowed in robots.txt.")
        print("  Fix: change their `Disallow: /` to `Allow: /` in the source that")
        print("  generates robots.txt. (This is the robots side; crawler-check.sh")
        print("  covers the Cloudflare EDGE side post-deploy.)")
        return 1
    print("PASS: robots.txt allows every citation crawler at root.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
