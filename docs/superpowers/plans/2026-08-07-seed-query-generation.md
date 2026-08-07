# Seed Query Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a hand-typed 5-entry `seed_queries` list into a ~40-entry list grounded in the client's own page titles, generated once by Claude Code and approved by a human before it lands in the config.

**Architecture:** One new module, `pipeline/audit/seed_queries.py`, exposed as `wf-seed-queries`. It crawls the live sitemap for page titles and h1s, hands those facts plus the client's config to Claude Code with an expansion recipe, and parses the reply back into a validated query list. It **prints** a YAML block; it never writes `docs/client-config.yml`. Two pure functions carry all the logic, so the suite runs offline.

**Tech Stack:** Python 3, stdlib only. Reuses `pipeline.lib.common.curl` / `load_config` and `pipeline.audit.measure.discover_urls`. Drives the `claude` CLI the same way `remediate.py:218` does.

## Global Constraints

- **stdlib-only runtime.** PyYAML is the sole runtime dependency. No new dependency.
- **`Finding.context` is fingerprinted.** The query IS part of a SERP finding's identity, so a list that changes between cycles makes every finding NEW and destroys the ratchet. Generation happens **once**, offline, into a human-reviewed commit — never inside `measure.py`.
- **No writes to `docs/client-config.yml`.** It is on `DEFAULT_DENY` at every tier including T3. This command prints; a human pastes.
- **Named skips, never silent zeroes.** Every refusal states the reason on stderr and returns a non-zero exit, matching the provider doctrine in `providers.py`.
- **Proof or it did not happen** (`CLAUDE.md` §4). Every verification step below runs on its own line and its real output goes in the CHANGELOG.
- **No em dashes in public-facing copy.** Internal markdown, code comments and commit messages are exempt.

---

## File Structure

| Path | Responsibility | Action |
|---|---|---|
| `pipeline/audit/seed_queries.py` | The whole command: two pure functions, one network crawl, one agent call, one printer | Create |
| `tests/test_seed_queries.py` | Offline tests for both pure functions and the CLI's refusals | Create |
| `pyproject.toml` | Register `wf-seed-queries` | Modify (`[project.scripts]`, audit section) |
| `docs/MODULES.md` | Header counts + one line for the new module | Modify (`:3`, audit package line) |
| `docs/ADMIN-CHECKLIST.md` | How an operator fills `seed_queries` | Modify (§4) |
| `config/client-config.starter.yml` | Point `seed_queries` at the generator | Modify (`:299`) |
| `CHANGELOG.md` | `[Unreleased]` entry with real output | Modify |

---

### Task 1: The two pure functions

**Files:**
- Create: `pipeline/audit/seed_queries.py`
- Test: `tests/test_seed_queries.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `page_facts(html: str) -> tuple[str, list[str]]` returning `(title, h1s)`
  - `parse_query_list(text: str, brand: str, limit: int) -> list[str]`

- [ ] **Step 1: Write the failing tests**

```python
"""Offline tests for wf-seed-queries. Both pure functions, no network, no agent."""
import pipeline.audit.seed_queries as sq


def test_the_title_and_every_h1_come_back():
    html = "<html><head><title>Rice Cake Cleanser | LEE SERIE</title></head>" \
           "<body><h1>Rice Cake Cleanser</h1><h1>How To Use</h1></body></html>"
    title, h1s = sq.page_facts(html)
    assert title == "Rice Cake Cleanser | LEE SERIE"
    assert h1s == ["Rice Cake Cleanser", "How To Use"]


def test_tags_inside_an_h1_do_not_leak_into_the_text():
    """A styled h1 is the common case, not the exception. Without stripping,
    the grounding facts carry markup into the prompt."""
    title, h1s = sq.page_facts("<h1>Stretch <span>Marks</span> Set</h1>")
    assert h1s == ["Stretch Marks Set"]


def test_a_page_with_no_title_is_empty_not_an_exception():
    title, h1s = sq.page_facts("<html><body><p>hi</p></body></html>")
    assert (title, h1s) == ("", [])


def test_numbering_and_bullets_are_stripped_off_the_agents_lines():
    """The CLI is told one query per line, but models number things anyway."""
    out = sq.parse_query_list("1. stretch mark cream\n- rice cake cleanser\n* sunscreen kh\n",
                              brand="LEE SERIE", limit=40)
    assert out == ["stretch mark cream", "rice cake cleanser", "sunscreen kh"]


def test_the_bare_brand_name_is_dropped_as_navigational():
    """You always rank #1 for your own name, so tracking it buys a permanently
    green finding at full price. The agent is told to drop these; this is the
    backstop for when it does not."""
    out = sq.parse_query_list("lee serie\nLEE SERIE\nstretch mark cream\n",
                              brand="LEE SERIE", limit=40)
    assert out == ["stretch mark cream"]


def test_the_brand_inside_a_longer_query_survives():
    """`lee serie` is navigational. `lee serie stretch mark cream review` is
    commercial and worth tracking - substring matching would kill both."""
    out = sq.parse_query_list("lee serie stretch mark cream review\n",
                              brand="LEE SERIE", limit=40)
    assert out == ["lee serie stretch mark cream review"]


def test_duplicates_collapse_case_insensitively_keeping_first_order():
    out = sq.parse_query_list("Rice Cake Cleanser\nrice cake cleanser\nsunscreen\n",
                              brand="X", limit=40)
    assert out == ["rice cake cleanser", "sunscreen"]


def test_prose_lines_are_not_queries():
    """Models preface lists. A sentence is not a search query."""
    out = sq.parse_query_list(
        "Here are the queries I generated based on the page titles:\n"
        "stretch mark cream\n", brand="X", limit=40)
    assert out == ["stretch mark cream"]


def test_the_limit_truncates_because_every_query_costs_money():
    out = sq.parse_query_list("\n".join(f"query {i}" for i in range(50)),
                              brand="X", limit=5)
    assert len(out) == 5
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_seed_queries.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'pipeline.audit.seed_queries'`

- [ ] **Step 3: Write the module's pure half**

```python
#!/usr/bin/env python3
"""Seed query generation. Crawls the client's own pages for grounding facts,
hands them to Claude Code with an expansion recipe, prints a YAML block for a
human to paste into docs/client-config.yml.

Why a separate command and not a flag on wf-site-health: `Finding.context` is
fingerprinted, so the query IS part of a SERP finding's identity. A list
regenerated every cycle makes every finding NEW forever and the RESOLVED /
PERSISTING ratchet stops meaning anything. The list is generated once, reviewed
by a human, and committed - the same shape as the tier.

The expansion recipe is adapted from AgriciDaniel/claude-seo (MIT), skill
`seo-cluster` steps 1 and 3.

The split at page_facts/parse_query_list is the testable seam: neither touches
the network or the filesystem, so the whole suite runs offline.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import threading

from pipeline.lib.common import curl, load_config

GATE = "seed_queries"

# Crawling every URL costs a request each and the titles repeat quickly on a
# catalogue site. 40 pages is plenty of vocabulary to ground the expansion.
CRAWL_MAX = 40
DEFAULT_LIMIT = 40

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
    derived; one invented from a bare seed keyword is not, and an invented query
    produces a real serp.absent finding that reads like a site defect.
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
        # Prose, not a query. Real search queries are short and unpunctuated;
        # a model's preamble ("Here are the queries...") is neither.
        if len(q.split()) > 10 or q.endswith((":", ".")):
            continue
        if brand_norm and q == brand_norm:
            continue
        seen.add(q)
        out.append(q)
        if len(out) >= limit:
            break
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_seed_queries.py -q`
Expected: PASS, 9 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/audit/seed_queries.py tests/test_seed_queries.py
git commit -m "seed-queries: the two pure functions, grounding and validation"
```

---

### Task 2: The crawl, the prompt and the agent

**Files:**
- Modify: `pipeline/audit/seed_queries.py`
- Test: `tests/test_seed_queries.py`

**Interfaces:**
- Consumes: `page_facts`, `parse_query_list` from Task 1.
- Produces:
  - `gather_facts(cfg: dict, urls: list) -> list[str]` returning one `"path — title — h1"` line per reachable page
  - `build_prompt(cfg: dict, facts: list, limit: int) -> str`
  - `run_agent(prompt: str, model: str, timeout: int) -> tuple[bool, str]`

- [ ] **Step 1: Write the failing tests**

```python
def test_only_pages_that_answered_become_facts(monkeypatch):
    """An unreachable page contributes nothing rather than an empty line -
    blank facts in the prompt read to the model as 'this page has no topic'."""
    pages = {"https://x.com/a/": "<title>Rice Cake Cleanser</title><h1>Cleanser</h1>",
             "https://x.com/b/": ""}
    monkeypatch.setattr(sq, "curl", lambda url, **kw: pages.get(url, ""))
    facts = sq.gather_facts({"domain": "x.com"}, list(pages))
    assert len(facts) == 1
    assert "Rice Cake Cleanser" in facts[0] and "/a/" in facts[0]


def test_the_prompt_carries_the_facts_the_brand_and_the_limit():
    prompt = sq.build_prompt(
        {"business": {"legal_name": "LEE SERIE"}, "domain": "x.com",
         "primary_metro": "Phnom Penh", "industry": "skincare"},
        ["/a/ - Rice Cake Cleanser"], limit=40)
    assert "Rice Cake Cleanser" in prompt
    assert "LEE SERIE" in prompt
    assert "Phnom Penh" in prompt
    assert "40" in prompt


def test_the_prompt_forbids_inventing_products():
    """Derivation only, never invention (CLAUDE.md). The grounding is worthless
    if the agent is free to expand past it."""
    prompt = sq.build_prompt({"business": {"legal_name": "X"}, "domain": "x.com"},
                             ["/a/ - Cleanser"], limit=10)
    assert "navigational" in prompt.lower()
    assert "do not invent" in prompt.lower()


def test_no_pages_answered_is_a_named_refusal(monkeypatch, capsys):
    """Exit 19, matching measure.py's Unreachable. A run that measured nothing
    must be red, never an empty list that reads as 'this site has no topics'."""
    monkeypatch.setattr(sq, "curl", lambda url, **kw: "")
    monkeypatch.setattr(sq, "discover_urls", lambda cfg, args, limit=None: ["https://x.com/a/"])
    monkeypatch.setattr(sq, "load_config", lambda d: {"domain": "x.com", "business": {}})
    monkeypatch.setattr(sys, "argv", ["wf-seed-queries", "--project", "."])
    assert sq.main() == 19
    assert "no page answered" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_seed_queries.py -q`
Expected: FAIL, `AttributeError: module 'pipeline.audit.seed_queries' has no attribute 'gather_facts'`

- [ ] **Step 3: Write the crawl, the prompt and the agent driver**

Append to `pipeline/audit/seed_queries.py`:

```python
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

1. Related searches and "people also search for" - use WebSearch on the core
   product terms and read what Google suggests.
2. People Also Ask questions from those same SERPs.
3. Long-tail modifiers: best, how to, vs, for, review, price, where to buy.
4. Question mining: who / what / when / where / why / how variants.
5. Intent modifiers: pricing, alternative, comparison, near me.

Then classify each by intent and KEEP only informational, commercial and
transactional queries. DROP every navigational query - a brand name or a login
term. We already rank first for our own name, so tracking it costs money and can
never produce an actionable finding.

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
    """(ok, text). WebSearch only - this command reads the web and writes
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
```

Add `from urllib.parse import urlsplit` and `from pipeline.audit.measure import discover_urls` to the imports.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_seed_queries.py -q`
Expected: the first three PASS; the fourth still fails on `main` not existing. That is Task 3.

- [ ] **Step 5: Commit**

```bash
git add pipeline/audit/seed_queries.py tests/test_seed_queries.py
git commit -m "seed-queries: crawl the client's own pages, prompt from those facts"
```

---

### Task 3: The CLI

**Files:**
- Modify: `pipeline/audit/seed_queries.py`, `pyproject.toml`
- Test: `tests/test_seed_queries.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `main() -> int`. Exit 0 on success, 2 on usage, 19 when no page answered, 20 when the agent failed or returned no usable query.

- [ ] **Step 1: Write the failing test**

```python
def test_the_command_prints_a_pasteable_yaml_block(monkeypatch, capsys):
    """End to end with the network and the agent stubbed. B-007: a green unit
    test on parse_query_list proves the parser works, not that main calls it."""
    monkeypatch.setattr(sq, "load_config",
                        lambda d: {"domain": "x.com", "business": {"legal_name": "LEE SERIE"}})
    monkeypatch.setattr(sq, "discover_urls", lambda cfg, args, limit=None: ["https://x.com/a/"])
    monkeypatch.setattr(sq, "curl", lambda url, **kw: "<title>Rice Cake Cleanser</title>")
    monkeypatch.setattr(sq, "run_agent",
                        lambda p, m, t: (True, "lee serie\nrice cake cleanser\nbest cleanser kh\n"))
    monkeypatch.setattr(sys, "argv", ["wf-seed-queries", "--project", "."])
    assert sq.main() == 0
    out = capsys.readouterr().out
    assert "seed_queries:" in out
    assert "  - rice cake cleanser" in out
    assert "lee serie\n" not in out          # the brand was dropped as navigational


def test_an_agent_that_returns_nothing_usable_is_exit_20(monkeypatch, capsys):
    monkeypatch.setattr(sq, "load_config", lambda d: {"domain": "x.com", "business": {}})
    monkeypatch.setattr(sq, "discover_urls", lambda cfg, args, limit=None: ["https://x.com/a/"])
    monkeypatch.setattr(sq, "curl", lambda url, **kw: "<title>T</title>")
    monkeypatch.setattr(sq, "run_agent", lambda p, m, t: (True, "Here are your queries:\n"))
    monkeypatch.setattr(sys, "argv", ["wf-seed-queries", "--project", "."])
    assert sq.main() == 20
    assert "no usable quer" in capsys.readouterr().err.lower()


def test_no_claude_on_path_refuses_before_crawling(monkeypatch, capsys):
    """Crawling 40 pages and then discovering there is no writer wastes the
    operator's time and the client's bandwidth."""
    monkeypatch.setattr(sq.shutil, "which", lambda n: None)
    monkeypatch.setattr(sys, "argv", ["wf-seed-queries", "--project", "."])
    assert sq.main() == 2
    assert "claude" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_seed_queries.py -q`
Expected: FAIL on `main`

- [ ] **Step 3: Write `main`**

```python
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

    if shutil.which("claude") is None:
        print("[ERROR] `claude` is not on PATH - there is nothing to generate with.",
              file=sys.stderr)
        return 2

    cfg = load_config(args.project)
    urls = discover_urls(cfg, [], limit=args.crawl_max)
    facts = gather_facts(cfg, urls)
    if not facts:
        print(f"[ERROR] no page answered out of {len(urls)} in the sitemap - "
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
```

Add `import shutil` to the imports.

- [ ] **Step 4: Run the whole file**

Run: `pytest tests/test_seed_queries.py -q`
Expected: PASS, 16 passed

- [ ] **Step 5: Register the command**

In `pyproject.toml`, under the `# ── audit / setup ──` block, after `wf-bootstrap-config`:

```toml
# Generates a grounded seed_queries list. Separate from wf-site-health on purpose:
# Finding.context is fingerprinted, so a list that changes per cycle makes every
# SERP finding NEW forever and the ratchet stops meaning anything.
wf-seed-queries = "pipeline.audit.seed_queries:main"
```

- [ ] **Step 6: Verify the console script resolves**

Run: `pip install -e . -q && wf-seed-queries --help`
Expected: the usage block prints, exit 0

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: 604 passed

- [ ] **Step 8: Commit**

```bash
git add pipeline/audit/seed_queries.py tests/test_seed_queries.py pyproject.toml
git commit -m "seed-queries: the CLI, printing a pasteable block and never writing the config"
```

---

### Task 4: Documentation

**Files:**
- Modify: `docs/MODULES.md:3`, `docs/ADMIN-CHECKLIST.md` §4, `config/client-config.starter.yml:299`, `CHANGELOG.md`

- [ ] **Step 1: Recount, do not remember**

```bash
ls pipeline/**/*.py | grep -v __init__ | wc -l
grep -c '^wf-' pyproject.toml
pytest -q
```

Put the three real numbers into the `docs/MODULES.md` header line, replacing
`5 packages, 39 modules, 5 workflows, 33 wf-* commands, 588 tests`.

- [ ] **Step 2: Add the module line to `docs/MODULES.md`**

In the `pipeline/audit/` package paragraph, after the `providers.py` entry:

```
· `seed_queries.py` (**the query list** — crawls the client's own titles and h1s, hands those
facts to Claude Code with an expansion-and-intent recipe, prints a YAML block a human pastes.
Deliberately NOT a flag on `wf-site-health`: `Finding.context` is fingerprinted, so a list
regenerated each cycle makes every SERP finding NEW forever and RESOLVED unreachable —
`wf-seed-queries`)
```

- [ ] **Step 3: Extend `docs/ADMIN-CHECKLIST.md` §4**

Under the Bright Data row, add:

```markdown
**Filling `seed_queries`.** `--with-serp` measures exactly the queries in the
client's `docs/client-config.yml` and nothing else, so the list is the whole
measurement. `wf-seed-queries --project <checkout>` crawls the site's own page
titles and h1s, expands them, drops navigational terms, and prints a YAML block
to paste. Review it before committing: every entry is one paid request per
cycle, and because `Finding.context` is fingerprinted, changing the list later
re-files every SERP finding as NEW.
```

- [ ] **Step 4: Point the starter config at the generator**

`config/client-config.starter.yml:299`, extend the existing comment:

```yaml
seed_queries: []                       # AEO citation-sweep seeds; also the query
                                       # list for `wf-site-health --with-serp`
                                       # (Bright Data). Empty = that run skips.
                                       # Generate with `wf-seed-queries`, review,
                                       # paste. Changing it later re-files every
                                       # SERP finding as NEW (context is
                                       # fingerprinted).
```

- [ ] **Step 5: CHANGELOG entry with real output**

Under `[Unreleased]`, added at the top of the existing list, never as a new
heading mid-list. Paste the actual `pytest -q` line and the actual first run's
query count.

- [ ] **Step 6: Verify then commit**

```bash
pytest -q
git diff --stat
git add -A
git commit -m "seed-queries: docs, counts recounted"
```

---

## Self-Review

**Spec coverage.** The ask was "use Claude CLI to determine the queries" plus the claude-seo evaluation. Task 2's `RECIPE` carries steps 1 and 3 of `seo-cluster` (expansion angles, intent classification with navigational dropped) and credits the MIT source. Steps 2/4/5 of that skill are content architecture and are deliberately absent.

**Placeholders.** None. Every code step has runnable code; every verification step names a command and its expected output.

**Type consistency.** `page_facts -> (str, list[str])` is consumed by `gather_facts`, which returns `list[str]` into `build_prompt`. `run_agent -> (bool, str)`, whose `str` goes to `parse_query_list -> list[str]`. `main` is the only caller of `run_agent`. Consistent.

**Known limitation, recorded not hidden.** The agent's queries are grounded but not volume-ranked. A query nobody searches produces a `serp.absent` finding that reads like a site defect. The mitigations are the page-title grounding, the navigational drop, and the human paste step. Real volume data needs Google Ads Keyword Planner, which requires an Ads Manager account and a developer token with Basic-access approval, and returns bucketed ranges without active ad spend. Out of scope; note it in the CHANGELOG entry.
