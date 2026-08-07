#!/usr/bin/env python3
"""Seed query generation. Crawls the client's own pages for grounding facts,
hands them to Claude Code with an expansion recipe, prints a YAML block for a
human to paste into docs/client-config.yml.

Why a separate command and not a flag on wf-site-health: `Finding.context` is
fingerprinted, so the query IS part of a SERP finding's identity. A list
regenerated every cycle makes every finding NEW forever and the RESOLVED /
PERSISTING ratchet stops meaning anything. The list is generated once, reviewed
by a human, and committed — the same shape as the tier.

Nothing here writes docs/client-config.yml. It is on DEFAULT_DENY at every tier
including T3, and the human paste IS the review step: these queries are derived
from the site's own vocabulary but they are not volume-ranked, so a query nobody
searches would produce a real serp.absent finding that reads like a site defect.

The expansion recipe is adapted from AgriciDaniel/claude-seo (MIT), skill
`seo-cluster` steps 1 and 3.

The split at page_facts/parse_query_list is the testable seam: neither touches
the network or the filesystem, so the whole suite runs offline.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

from pipeline.audit.measure import discover_urls
from pipeline.lib.common import curl, load_config

GATE = "seed_queries"

# Crawling every URL costs a request each and the titles repeat quickly on a
# catalogue site. 40 pages is plenty of vocabulary to ground the expansion.
CRAWL_MAX = 40
DEFAULT_LIMIT = 40

# A real search query is short and unpunctuated. A model's preamble ("Here are
# the queries:") is neither, and it is the only prose that survives bullet
# stripping.
QUERY_MAX_WORDS = 10

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
# A leading "1.", "1)", "-", "*" or "•" is list decoration, not part of the query.
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def _text(raw: str) -> str:
    """Tag-stripped, whitespace-collapsed inner text."""
    return " ".join(_TAG_RE.sub(" ", raw).split())


def page_facts(html: str) -> tuple[str, list[str]]:
    """(title, h1s) for one already-fetched page. Pure.

    This is the grounding. A query expanded from the site's own vocabulary is
    derived; one invented from a bare seed keyword is not.
    """
    m = _TITLE_RE.search(html or "")
    title = _text(m.group(1)) if m else ""
    h1s = [t for t in (_text(h) for h in _H1_RE.findall(html or "")) if t]
    return title, h1s


def parse_query_list(text: str, brand: str, limit: int) -> list[str]:
    """The agent's reply, validated into a query list. Pure.

    Drops list decoration, prose, duplicates and the bare brand name. The brand
    check is exact-match on the whole normalized line, never a substring: `lee
    serie` is navigational and you always rank #1 for it, but `lee serie stretch
    mark cream review` is commercial and worth every cent of tracking.
    """
    brand_norm = " ".join((brand or "").lower().split())
    out: list[str] = []
    seen: set[str] = set()
    for line in (text or "").splitlines():
        q = " ".join(_BULLET_RE.sub("", line).lower().split())
        if not q or q in seen:
            continue
        if len(q.split()) > QUERY_MAX_WORDS or q.endswith((":", ".")):
            continue
        if brand_norm and q == brand_norm:
            continue
        seen.add(q)
        out.append(q)
        if len(out) >= limit:
            break
    return out


# ── the network seam ─────────────────────────────────────────────────────────

def gather_facts(cfg: dict, urls: list) -> list[str]:
    """One `path - title - h1` line per page that answered. Unreachable pages
    contribute nothing: a blank fact reads to the model as a topicless page."""
    facts = []
    for url in urls:
        title, h1s = page_facts(curl(url))
        if not (title or h1s):
            continue
        path = urlsplit(url).path or "/"
        facts.append(" - ".join([path, title] + h1s[:1]).strip(" -"))
    return facts


# ── the prompt ───────────────────────────────────────────────────────────────

# Adapted from AgriciDaniel/claude-seo (MIT), skill `seo-cluster` steps 1 and 3.
RECIPE = """\
Expand these into search queries real customers would type, using every angle:

1. Related searches and "people also search for" — use WebSearch on the core
   product terms and read what Google suggests.
2. People Also Ask questions from those same SERPs.
3. Long-tail modifiers: best, how to, vs, for, review, price, where to buy.
4. Question mining: who / what / when / where / why / how variants.
5. Intent modifiers: pricing, alternative, comparison, near me.

Then classify each by intent and KEEP only informational, commercial and
transactional queries. DROP every navigational query — a bare brand name or a
login term. We already rank first for our own name, so tracking it costs money
and can never produce an actionable finding.

Do not invent products, ingredients, claims or locations. Every query must be
derivable from the page facts above or from what WebSearch actually returned.
"""


def build_prompt(cfg: dict, facts: list, limit: int) -> str:
    biz = cfg.get("business") or {}
    brand = biz.get("legal_name") or cfg.get("domain", "")
    where = cfg.get("primary_metro") or ", ".join(cfg.get("service_areas") or []) or ""
    return "\n".join([
        f"You are choosing the search queries to track for {brand}"
        + (f", a {cfg['industry']} business" if cfg.get("industry") else "")
        + (f" serving {where}" if where else "") + ".",
        "",
        "These are the pages the site actually publishes, title and h1:",
        "",
        *(f"  {f}" for f in facts),
        "",
        RECIPE,
        "",
        f"Output at most {limit} queries, ONE PER LINE, lowercase, nothing else.",
        "No numbering, no bullets, no preamble, no commentary. Just the queries.",
    ])


# ── the agent ────────────────────────────────────────────────────────────────

def run_agent(prompt: str, model: str, timeout: int) -> tuple:
    """(ok, text). WebSearch only — this command reads the web and writes
    nothing, so it needs no file tools and gets none.

    The prompt goes on STDIN, matching remediate.py:230: the CLI's option parser
    reads a leading `---` as a malformed flag.
    """
    argv = ["claude", "-p", "--model", model, "--allowedTools", "WebSearch"]
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)
    except OSError as exc:
        return False, str(exc)
    try:
        out, _ = proc.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return False, f"timed out after {timeout}s"
    return proc.returncode == 0, out or ""


# ── the CLI ──────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-seed-queries",
        description="Generate a grounded seed_queries list for a client. Prints "
                    "a YAML block; never writes docs/client-config.yml, which is "
                    "on the deny floor at every tier.")
    ap.add_argument("--project", default=".", help="client checkout")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help=f"max queries to emit (default {DEFAULT_LIMIT}). Every "
                         f"query is one paid Bright Data request per cycle.")
    ap.add_argument("--crawl-max", type=int, default=CRAWL_MAX,
                    help=f"max pages to read for grounding (default {CRAWL_MAX})")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    # Refuse before crawling: 40 requests and then "no writer" wastes the
    # operator's time and the client's bandwidth.
    if shutil.which("claude") is None:
        print("[ERROR] `claude` is not on PATH — there is nothing to generate with.",
              file=sys.stderr)
        return 2

    cfg = load_config(args.project)
    urls = discover_urls(cfg, [], limit=args.crawl_max)
    facts = gather_facts(cfg, urls)
    if not facts:
        print(f"[ERROR] no page answered out of {len(urls)} in the sitemap — "
              f"nothing to ground the queries in.", file=sys.stderr)
        return 19
    print(f"[INFO] grounded in {len(facts)}/{len(urls)} pages", file=sys.stderr)

    ok, text = run_agent(build_prompt(cfg, facts, args.limit), args.model, args.timeout)
    if not ok:
        print(f"[ERROR] the agent failed: {text[-400:]}", file=sys.stderr)
        return 20
    brand = (cfg.get("business") or {}).get("legal_name") or ""
    queries = parse_query_list(text, brand, args.limit)
    if not queries:
        print("[ERROR] no usable query came back. Raw reply:\n" + text[-400:],
              file=sys.stderr)
        return 20

    print("seed_queries:")
    for q in queries:
        print(f"  - {q}")
    print(f"\n[INFO] {len(queries)} queries. Each is one paid Bright Data request "
          f"per cycle. Review, then paste into docs/client-config.yml and commit.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
