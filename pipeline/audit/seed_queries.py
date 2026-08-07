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

The agent is asked for a JSON array and its reply is `json.loads`-ed. An earlier
draft asked for one query per line and recovered structure with heuristics —
strip bullets, over ten words is prose, a trailing colon is a heading. Every one
of those rules was both too loose and too tight: it admitted a `claude` CLI
warning line as a query, and it deleted the eleven-word People Also Ask
questions the recipe exists to produce. Malformed JSON is now a loud exit 20
carrying the raw reply, which is what this repo does everywhere else — a skip is
never a measurement.

The expansion recipe is adapted from AgriciDaniel/claude-seo (MIT), skill
`seo-cluster` steps 1 and 3.

The split at page_facts/brand_names/parse_reply is the testable seam: none of
them touches the network or the filesystem, so the whole suite runs offline.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

from pipeline.audit.measure import urls_or_refuse
from pipeline.lib.common import curl, load_config

# Crawling every URL costs a request each and the titles repeat quickly on a
# catalogue site. 40 pages is plenty of vocabulary to ground the expansion.
CRAWL_MAX = 40
# Every query emitted is one paid Bright Data request per cycle, forever.
DEFAULT_LIMIT = 40

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
# Models wrap JSON in a ```json fence however firmly you ask them not to.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def _text(raw: str) -> str:
    """Tag-stripped, whitespace-collapsed inner text."""
    return " ".join(_TAG_RE.sub(" ", raw).split())


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


# ── the grounding ────────────────────────────────────────────────────────────

def page_facts(html: str) -> tuple[str, list[str]]:
    """(title, h1s) for one already-fetched page. Pure.

    This is the grounding. A query expanded from the site's own vocabulary is
    derived; one invented from a bare seed keyword is not.

    Deliberately not the `<title>` regex from measure.py:51, which is `[^<]+`
    and stops at the first tag. That is right for measuring title *length* and
    wrong here, where an `<h1>` wrapping a `<span>` is the common case and its
    words are the vocabulary we came for.
    """
    m = _TITLE_RE.search(html or "")
    title = _text(m.group(1)) if m else ""
    h1s = [t for t in (_text(h) for h in _H1_RE.findall(html or "")) if t]
    return title, h1s


def brand_names(cfg: dict) -> set[str]:
    """Every spelling of the client's own name, normalized.

    A bare brand query is navigational: you already rank first for your own
    name, so tracking it buys a permanently green finding at full price. One
    field is not enough to catch it — `business.legal_name` is the *legal* name
    and carries entity suffixes ("Lee Serie Co., Ltd."), while the query people
    actually type is the trade name in `nap.name` ("LEE SERIE"). Matching only
    the legal name silently fails on exactly the case this exists for.
    """
    biz = cfg.get("business") or {}
    nap = cfg.get("nap") or {}
    candidates = [cfg.get("client_name"), biz.get("legal_name"), biz.get("trade"),
                  nap.get("name"), (cfg.get("client_slug") or "").replace("-", " ")]
    return {_norm(c) for c in candidates if _norm(c)}


def gather_facts(urls: list) -> list[str]:
    """One `path - title - h1s` line per page that answered. Unreachable pages
    contribute nothing: a blank fact reads to the model as a topicless page."""
    facts = []
    for url in urls:
        title, h1s = page_facts(curl(url))
        if not (title or h1s):
            continue
        path = urlsplit(url).path or "/"
        facts.append(" - ".join(p for p in [path, title, *h1s] if p))
    return facts


# ── the reply ────────────────────────────────────────────────────────────────

def parse_reply(text: str, brands: set, limit: int) -> tuple:
    """(queries, dropped). Pure.

    `text` is the agent's reply, expected to be a JSON array of strings. Returns
    an empty list — never a partial guess — when it is not, so main can exit 20
    with the raw reply rather than paste something invented into a config that
    will fingerprint it forever.

    `dropped` names what was removed and why, because silent omission is the one
    thing this codebase refuses (measure.py `_warn_unmeasurable`, every provider
    skip string).
    """
    try:
        doc = json.loads(_FENCE_RE.sub("", (text or "").strip()))
    except json.JSONDecodeError:
        return [], []
    if not isinstance(doc, list):
        return [], []

    out: list[str] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for item in doc:
        if not isinstance(item, str):
            dropped.append(f"{item!r} (not a string)")
            continue
        q = _norm(item)
        if not q:
            continue
        if q in seen:
            dropped.append(f"{q} (duplicate)")
            continue
        if q in brands:
            dropped.append(f"{q} (navigational — we already rank first for it)")
            continue
        seen.add(q)
        out.append(q)
    if len(out) > limit:
        dropped.append(f"{len(out) - limit} more past --limit {limit}")
        out = out[:limit]
    return out, dropped


# ── the prompt ───────────────────────────────────────────────────────────────

# Adapted from AgriciDaniel/claude-seo (MIT), skill `seo-cluster` steps 1 and 3.
RECIPE = """\
Expand these into search queries real customers would type, using every angle:

1. Related searches and "people also search for" — use WebSearch on the core
   product terms and read what Google suggests.
2. People Also Ask questions from those same SERPs. Keep them long; a
   twelve-word question is the highest-intent, lowest-competition kind.
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
    where = cfg.get("primary_metro") or ", ".join(cfg.get("service_areas") or []) or ""
    brand = next(iter(sorted(brand_names(cfg))), cfg.get("domain", ""))
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
        f"Return at most {limit} queries as a JSON array of lowercase strings.",
        'Example: ["stretch mark cream for pregnancy", "best rice cleanser"]',
        "Output the array and nothing else — no preamble, no commentary, no",
        "markdown fence, no keys. Just the array.",
    ])


# ── the agent ────────────────────────────────────────────────────────────────

# WebSearch and nothing else. This command reads the web and writes no files, so
# it is given no file tools and no bypassed permission mode. Asserted by
# test_the_agent_gets_websearch_and_no_write_tools — the prompt is not what keeps
# an agent inside its authority (CLAUDE.md), the allow-list is.
ALLOWED_TOOLS = "WebSearch"


def run_agent(prompt: str, model: str, timeout: int) -> tuple:
    """(ok, text). `text` is the agent's reply on success, a diagnostic on
    failure.

    stderr is kept SEPARATE, unlike `remediate.run_agent` which merges it. That
    module parses JSON lines and discards whatever fails to parse; here the
    reply IS the payload, so a single CLI warning line merged into stdout breaks
    the JSON parse — or, in the line-oriented draft this replaced, became a
    permanently-fingerprinted paid query.

    The prompt goes on STDIN, matching `remediate.run_agent`: the CLI's option
    parser reads a leading `---` as a malformed flag.
    """
    argv = ["claude", "-p", "--model", model,
            "--allowedTools", ALLOWED_TOOLS,
            "--output-format", "json"]
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
    except OSError as exc:
        return False, str(exc)
    try:
        out, err = proc.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return False, f"timed out after {timeout}s"
    if proc.returncode != 0:
        return False, (err or out or f"claude exited {proc.returncode}")[-400:]
    return unwrap_envelope(out)


def unwrap_envelope(out: str) -> tuple:
    """(ok, text) from `--output-format json`. Pure.

    The envelope carries `is_error` and `subtype` alongside the reply, and a run
    can exit 0 while setting them — remediate.py:291 checks all three for that
    reason. Falls back to treating stdout as the reply when it is not an
    envelope, so a CLI that changes its output shape degrades to the old
    behaviour instead of reporting a clean empty list.
    """
    try:
        doc = json.loads((out or "").strip())
    except json.JSONDecodeError:
        return True, out or ""
    if not isinstance(doc, dict) or "result" not in doc:
        return True, out or ""
    if doc.get("is_error") is True or doc.get("subtype") not in (None, "success"):
        return False, str(doc.get("result") or doc.get("subtype"))[-400:]
    return True, str(doc.get("result") or "")


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
    urls, refused = urls_or_refuse(cfg, [], args.crawl_max)
    if refused:
        return refused
    facts = gather_facts(urls)
    if not facts:
        print(f"[ERROR] no page answered out of {len(urls)} in the sitemap — "
              f"nothing to ground the queries in.", file=sys.stderr)
        return 19
    print(f"[INFO] grounded in {len(facts)}/{len(urls)} pages", file=sys.stderr)

    ok, text = run_agent(build_prompt(cfg, facts, args.limit), args.model, args.timeout)
    if not ok:
        print(f"[ERROR] the agent failed: {text[-400:]}", file=sys.stderr)
        return 20
    queries, dropped = parse_reply(text, brand_names(cfg), args.limit)
    for d in dropped:
        print(f"[WARN] dropped {d}", file=sys.stderr)
    if not queries:
        print("[ERROR] no usable query came back — the reply was not a JSON "
              "array of strings. Raw reply:\n" + text[-400:], file=sys.stderr)
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
