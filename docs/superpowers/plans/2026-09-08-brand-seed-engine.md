# Brand Seed Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `pipeline/seed/` module that turns brand-citation *gaps* (from the existing measure agent) into brand-mentioning topic posts — auto-posted to safe platforms, queued for approval on strict ones, never on Wikipedia.

**Architecture:** Five small modules mirroring `pipeline/audit/providers.py` and `pipeline/scanner/mentions.py` conventions — pure parse/build functions with an injectable side-effecting caller so the whole suite runs offline. Input is a `gaps.json` file; output is `seed-log.json` plus yellow-tier `drafts/*.md`. MVP uses a stub poster (no external accounts) and generates drafts via the `claude` CLI on the user's subscription (no API key).

**Tech Stack:** Python 3 (stdlib only — `argparse`, `subprocess`, `json`, `dataclasses`, `re`, `time`, `pathlib`), `claude` CLI for generation, pytest.

## Global Constraints

- **One flat module, one function per platform.** No ABC, no registry, no sub-package. (verbatim rule from `providers.py`)
- **Credentials from environment only.** No `.env` read in code; nothing stored in the repo.
- **Every skip is loud.** Missing creds / unknown platform / bad gap → a `skipped`/`dropped` record with a reason string in `seed-log.json`. Never a silent success.
- **Pure parse/build functions** take already-fetched/assembled payloads; the only side effects are the injectable caller, file writes, and the CLI.
- **Generation via `claude` CLI subscription** (`claude -p <prompt> --output-format json`) — no `ANTHROPIC_API_KEY`.
- **Tiers:** green `[medium, devto, hashnode, tumblr, blogger]` auto; yellow `[reddit, quora]` → draft file; red `[wikipedia]` skip; unknown → skip (loud).
- File header on every module: `from __future__ import annotations`.
- Python floor: 3.10+ (repo already uses `str | None` unions).

---

### Task 1: Tier map (`tiers.py`)

**Files:**
- Create: `pipeline/seed/__init__.py` (empty)
- Create: `pipeline/seed/tiers.py`
- Test: `tests/test_seed_tiers.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `GREEN: list[str]`, `YELLOW: list[str]`, `RED: list[str]`, `tier_of(platform: str) -> str` returning one of `"green" | "yellow" | "red" | "unknown"` (case-insensitive on input).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seed_tiers.py
"""Tier membership is the safety rule in code: green auto-posts, yellow queues,
red never, unknown is skipped loudly. A platform silently defaulting to green
would auto-post somewhere we never vetted — so unknown must NOT be green."""
from __future__ import annotations

from pipeline.seed.tiers import tier_of, GREEN, YELLOW, RED


def test_green_platforms():
    for p in ("medium", "devto", "hashnode", "tumblr", "blogger"):
        assert tier_of(p) == "green"


def test_yellow_platforms():
    for p in ("reddit", "quora"):
        assert tier_of(p) == "yellow"


def test_red_platform():
    assert tier_of("wikipedia") == "red"


def test_case_insensitive():
    assert tier_of("DevTo") == "green"
    assert tier_of("Reddit") == "yellow"


def test_unknown_is_not_green():
    assert tier_of("mastodon") == "unknown"
    assert tier_of("") == "unknown"


def test_tier_lists_are_disjoint():
    assert set(GREEN) & set(YELLOW) == set()
    assert set(GREEN) & set(RED) == set()
    assert set(YELLOW) & set(RED) == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/seo_agent && .venv/bin/pytest tests/test_seed_tiers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.seed'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/seed/__init__.py
```
(empty file)

```python
# pipeline/seed/tiers.py
"""Platform tiers — the safety rule as data. Green auto-posts, yellow is queued
for human approval, red is never automated (Wikipedia: COI/paid-editing policy,
permanent public history). Unknown platforms are NOT green on purpose: a typo or
new platform must fall through to a loud skip, never to auto-posting."""
from __future__ import annotations

GREEN = ["medium", "devto", "hashnode", "tumblr", "blogger"]
YELLOW = ["reddit", "quora"]
RED = ["wikipedia"]


def tier_of(platform: str) -> str:
    p = (platform or "").strip().lower()
    if p in GREEN:
        return "green"
    if p in YELLOW:
        return "yellow"
    if p in RED:
        return "red"
    return "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/seo_agent && .venv/bin/pytest tests/test_seed_tiers.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/seo_agent
git add pipeline/seed/__init__.py pipeline/seed/tiers.py tests/test_seed_tiers.py
git commit -m "feat(seed): platform tier map (green/yellow/red/unknown)"
```

---

### Task 2: Gap parsing (`gaps.py`)

**Files:**
- Create: `pipeline/seed/gaps.py`
- Test: `tests/test_seed_gaps.py`
- Create: `tests/fixtures/seed_gaps.json`

**Interfaces:**
- Consumes: nothing (takes an already-loaded `list[dict]`).
- Produces:
  - `@dataclass Gap` with fields `brand, platform, topic, target_keyword, angle, url_target` (all `str`).
  - `REQUIRED: tuple[str, ...]` — the six field names.
  - `parse_gaps(rows: list[dict]) -> tuple[list[Gap], list[dict]]` returning `(gaps, dropped)`. A row missing any required field (or with a blank value) goes to `dropped` with an added `"_reason"` key; it is never silently discarded.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seed_gaps.py
"""parse_gaps turns the measure agent's gaps.json rows into Gap objects. A
malformed row (missing/blank field) is dropped WITH a reason, never silently —
same discipline as the providers' loud skips: a silent drop would make a run
look complete when it seeded fewer gaps than it was handed."""
from __future__ import annotations

from pipeline.seed.gaps import parse_gaps, Gap, REQUIRED

GOOD = {
    "brand": "Acme",
    "platform": "devto",
    "topic": "best widget for teams",
    "target_keyword": "team widget",
    "angle": "compare on setup speed",
    "url_target": "https://acme.com/widget",
}


def test_parses_a_good_row():
    gaps, dropped = parse_gaps([GOOD])
    assert dropped == []
    assert gaps == [Gap(brand="Acme", platform="devto",
                        topic="best widget for teams",
                        target_keyword="team widget",
                        angle="compare on setup speed",
                        url_target="https://acme.com/widget")]


def test_drops_row_missing_field_with_reason():
    bad = {k: v for k, v in GOOD.items() if k != "url_target"}
    gaps, dropped = parse_gaps([bad])
    assert gaps == []
    assert len(dropped) == 1
    assert "url_target" in dropped[0]["_reason"]


def test_drops_row_with_blank_field():
    bad = {**GOOD, "brand": "   "}
    gaps, dropped = parse_gaps([bad])
    assert gaps == []
    assert "brand" in dropped[0]["_reason"]


def test_mixed_batch_keeps_good_drops_bad():
    bad = {**GOOD, "platform": ""}
    gaps, dropped = parse_gaps([GOOD, bad, GOOD])
    assert len(gaps) == 2
    assert len(dropped) == 1


def test_required_fields_frozen():
    assert REQUIRED == ("brand", "platform", "topic",
                        "target_keyword", "angle", "url_target")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/seo_agent && .venv/bin/pytest tests/test_seed_gaps.py -v`
Expected: FAIL with `ModuleNotFoundError` / `cannot import name 'parse_gaps'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/seed/gaps.py
"""Parse the measure agent's gaps.json into Gap objects. Pure: takes an
already-loaded list of dicts (run.py owns the file read). A row missing any
required field, or carrying a blank one, is dropped WITH a reason so the run log
can show exactly what the agent handed us that we could not use."""
from __future__ import annotations

from dataclasses import dataclass

REQUIRED = ("brand", "platform", "topic", "target_keyword", "angle", "url_target")


@dataclass
class Gap:
    brand: str
    platform: str
    topic: str
    target_keyword: str
    angle: str
    url_target: str


def parse_gaps(rows: list[dict]) -> tuple[list[Gap], list[dict]]:
    gaps: list[Gap] = []
    dropped: list[dict] = []
    for row in rows:
        missing = [f for f in REQUIRED
                   if not str(row.get(f, "")).strip()]
        if missing:
            dropped.append({**row, "_reason": f"missing/blank: {', '.join(missing)}"})
            continue
        gaps.append(Gap(**{f: str(row[f]).strip() for f in REQUIRED}))
    return gaps, dropped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/seo_agent && .venv/bin/pytest tests/test_seed_gaps.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Create the fixture (used by Task 5 e2e)**

```json
// tests/fixtures/seed_gaps.json
[
  {
    "brand": "Acme",
    "platform": "devto",
    "topic": "best widget for remote teams",
    "target_keyword": "remote team widget",
    "angle": "compare on setup speed",
    "url_target": "https://acme.com/widget"
  },
  {
    "brand": "Acme",
    "platform": "reddit",
    "topic": "how do you pick a team widget",
    "target_keyword": "team widget",
    "angle": "honest tradeoffs, mention Acme as one option",
    "url_target": "https://acme.com/widget"
  },
  {
    "brand": "Acme",
    "platform": "wikipedia",
    "topic": "Acme (company)",
    "target_keyword": "acme company",
    "angle": "notability-based entry",
    "url_target": "https://acme.com"
  }
]
```

- [ ] **Step 6: Commit**

```bash
cd ~/seo_agent
git add pipeline/seed/gaps.py tests/test_seed_gaps.py tests/fixtures/seed_gaps.json
git commit -m "feat(seed): parse gaps.json into Gap objects, drop bad rows loudly"
```

---

### Task 3: Draft generation via `claude` CLI (`generate.py`)

**Files:**
- Create: `pipeline/seed/generate.py`
- Test: `tests/test_seed_generate.py`

**Interfaces:**
- Consumes: `Gap` from `pipeline.seed.gaps`.
- Produces:
  - `@dataclass Draft` with fields `gap: Gap`, `title: str`, `body: str`, `brand_mention: str`.
  - `build_prompt(gap: Gap) -> str` (pure).
  - `parse_result(raw: str) -> dict` (pure) — takes the raw stdout of `claude -p ... --output-format json`, returns the inner dict `{"title","body","brand_mention"}`. Strips ```` ```json ```` fences if present. Raises `ValueError` on unparseable input.
  - `draft(gap: Gap, run=None) -> Draft` — `run` is an injectable `Callable[[str], str]` (defaults to the real `claude` subprocess). This is the offline test seam.
  - `_run_claude(prompt: str) -> str` — real subprocess caller (not unit-tested; exercised only live).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seed_generate.py
"""Generation is a claude CLI subprocess behind an injectable `run` seam, so the
suite is fully offline. build_prompt and parse_result are pure; parse_result must
survive both bare JSON and the ```json fenced form the model sometimes emits."""
from __future__ import annotations

import json

import pytest

from pipeline.seed.gaps import Gap
from pipeline.seed.generate import build_prompt, parse_result, draft, Draft

GAP = Gap(brand="Acme", platform="devto", topic="best widget for remote teams",
          target_keyword="remote team widget", angle="compare on setup speed",
          url_target="https://acme.com/widget")

INNER = {"title": "5 Widgets for Remote Teams",
         "body": "# Widgets\nAcme is a solid pick...",
         "brand_mention": "Acme (https://acme.com/widget) sets up in minutes."}


def _claude_stdout(inner: dict, fenced: bool = False) -> str:
    text = json.dumps(inner)
    if fenced:
        text = f"```json\n{text}\n```"
    return json.dumps({"type": "result", "subtype": "success",
                       "is_error": False, "result": text})


def test_build_prompt_includes_gap_facts():
    p = build_prompt(GAP)
    for needle in ("Acme", "devto", "remote team widget",
                   "https://acme.com/widget", "compare on setup speed"):
        assert needle in p
    # must instruct JSON-only output with the three keys
    assert "title" in p and "body" in p and "brand_mention" in p


def test_parse_result_bare_json():
    d = parse_result(_claude_stdout(INNER))
    assert d == INNER


def test_parse_result_fenced_json():
    d = parse_result(_claude_stdout(INNER, fenced=True))
    assert d == INNER


def test_parse_result_bad_input_raises():
    with pytest.raises(ValueError):
        parse_result("not json at all")


def test_draft_uses_injected_runner():
    calls = []

    def fake_run(prompt: str) -> str:
        calls.append(prompt)
        return _claude_stdout(INNER)

    d = draft(GAP, run=fake_run)
    assert isinstance(d, Draft)
    assert d.title == INNER["title"]
    assert d.body == INNER["body"]
    assert d.brand_mention == INNER["brand_mention"]
    assert d.gap is GAP
    assert "Acme" in calls[0]  # the runner got the built prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/seo_agent && .venv/bin/pytest tests/test_seed_generate.py -v`
Expected: FAIL with `cannot import name 'build_prompt'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/seed/generate.py
"""Gap -> Draft via the `claude` CLI on the user's subscription (no API key, no
per-token cost). build_prompt and parse_result are pure; the subprocess is the
only side effect and is injectable as `run` so the suite runs offline.

The CLI returns an outer JSON envelope whose `.result` is the model's text. We
ask the model for a compact JSON object {title, body, brand_mention}; parse_result
unwraps the envelope, strips any ```json fence, and json.loads the inner text."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from pipeline.seed.gaps import Gap


@dataclass
class Draft:
    gap: Gap
    title: str
    body: str
    brand_mention: str


def build_prompt(gap: Gap) -> str:
    return (
        "You are an SEO content writer. Write one platform-appropriate post that "
        "naturally mentions a brand, to seed brand presence where it is currently "
        "absent.\n\n"
        f"Brand: {gap.brand}\n"
        f"Platform: {gap.platform}\n"
        f"Topic: {gap.topic}\n"
        f"Target keyword: {gap.target_keyword}\n"
        f"Angle: {gap.angle}\n"
        f"Brand URL to link: {gap.url_target}\n\n"
        "The post must read as genuinely useful, not an ad. Mention the brand once, "
        "in context, with the URL. Weave in the target keyword naturally.\n\n"
        "Output ONLY a JSON object, no prose, with exactly these keys:\n"
        '{"title": "...", "body": "markdown body", '
        '"brand_mention": "the single sentence that cites the brand + URL"}'
    )


def parse_result(raw: str) -> dict:
    try:
        envelope = json.loads(raw)
        text = envelope["result"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ValueError(f"unparseable claude envelope: {e}")
    text = text.strip()
    if text.startswith("```"):
        # strip ```json ... ``` fence
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    try:
        inner = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"claude result is not JSON: {e}")
    if not all(k in inner for k in ("title", "body", "brand_mention")):
        raise ValueError(f"claude result missing keys: {inner.keys()}")
    return inner


def _run_claude(prompt: str) -> str:
    proc = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr[:200]}")
    return proc.stdout


def draft(gap: Gap, run=None) -> Draft:
    run = run or _run_claude
    inner = parse_result(run(build_prompt(gap)))
    return Draft(gap=gap, title=inner["title"], body=inner["body"],
                 brand_mention=inner["brand_mention"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/seo_agent && .venv/bin/pytest tests/test_seed_generate.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/seo_agent
git add pipeline/seed/generate.py tests/test_seed_generate.py
git commit -m "feat(seed): generate drafts via claude CLI behind injectable seam"
```

---

### Task 4: Posters — stub + yellow draft file (`posters.py`)

**Files:**
- Create: `pipeline/seed/posters.py`
- Test: `tests/test_seed_posters.py`

**Interfaces:**
- Consumes: `Draft` from `pipeline.seed.generate`.
- Produces:
  - `@dataclass PostResult` with fields `platform: str`, `status: str` (`"posted" | "queued" | "skipped"`), `url: str | None = None`, `detail: str | None = None`.
  - `slugify(text: str) -> str` — lowercase, non-alphanumerics → `-`, collapsed, trimmed, max 60 chars.
  - `write_draft_file(draft: Draft, drafts_dir: str) -> PostResult` — writes `<drafts_dir>/<platform>-<slug>.md` (creating the dir), returns `PostResult(status="queued", detail=<path>)`.
  - `stub_post(draft: Draft) -> PostResult` — MVP green stand-in; no HTTP; returns `PostResult(status="posted", url=None, detail="stub: would POST to <platform>: <title>")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seed_posters.py
"""Posters for the MVP: a stub green poster (no HTTP, no accounts) and the real
yellow draft-file writer. The stub records exactly what it WOULD post so the log
is honest that nothing went live yet."""
from __future__ import annotations

from pipeline.seed.gaps import Gap
from pipeline.seed.generate import Draft
from pipeline.seed.posters import slugify, write_draft_file, stub_post, PostResult

GAP = Gap(brand="Acme", platform="reddit", topic="how do you pick a team widget",
          target_keyword="team widget", angle="honest tradeoffs",
          url_target="https://acme.com/widget")
DRAFT = Draft(gap=GAP, title="How Do You Pick a Team Widget?",
              body="# Thoughts\nAcme is one option...",
              brand_mention="Acme (https://acme.com/widget) is one option.")


def test_slugify_basic():
    assert slugify("How Do You Pick a Team Widget?") == "how-do-you-pick-a-team-widget"


def test_slugify_trims_and_caps_length():
    assert slugify("  Hello,  World!!  ") == "hello-world"
    assert len(slugify("word " * 40)) <= 60


def test_write_draft_file_writes_and_reports(tmp_path):
    res = write_draft_file(DRAFT, str(tmp_path / "drafts"))
    assert res.platform == "reddit"
    assert res.status == "queued"
    written = (tmp_path / "drafts" / "reddit-how-do-you-pick-a-team-widget.md")
    assert written.exists()
    text = written.read_text()
    assert "How Do You Pick a Team Widget?" in text
    assert "Acme (https://acme.com/widget)" in text
    assert res.detail == str(written)


def test_stub_post_reports_would_post_without_url():
    res = stub_post(DRAFT)
    assert isinstance(res, PostResult)
    assert res.status == "posted"
    assert res.url is None
    assert "would POST to reddit" in res.detail
    assert "How Do You Pick a Team Widget?" in res.detail
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/seo_agent && .venv/bin/pytest tests/test_seed_posters.py -v`
Expected: FAIL with `cannot import name 'slugify'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/seed/posters.py
"""MVP posters. `stub_post` is the green-tier stand-in: it performs NO HTTP and
requires NO account — it records what it would post so the log never claims a
live post that did not happen. `write_draft_file` is the real yellow-tier action:
it writes a markdown draft for a human to review and post by hand.

Real green posters (post_devto, post_medium, ...) are added post-MVP as
identical-shape functions that replace stub_post — one per platform, env creds,
loud skip on missing creds, following pipeline/audit/providers.py."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from pipeline.seed.generate import Draft


@dataclass
class PostResult:
    platform: str
    status: str            # "posted" | "queued" | "skipped"
    url: str | None = None
    detail: str | None = None


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60].rstrip("-")


def write_draft_file(draft: Draft, drafts_dir: str) -> PostResult:
    os.makedirs(drafts_dir, exist_ok=True)
    slug = slugify(draft.title) or "untitled"
    path = os.path.join(drafts_dir, f"{draft.gap.platform}-{slug}.md")
    content = (
        f"# {draft.title}\n\n"
        f"> platform: {draft.gap.platform} | keyword: {draft.gap.target_keyword}\n"
        f"> brand mention: {draft.brand_mention}\n\n"
        f"{draft.body}\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return PostResult(platform=draft.gap.platform, status="queued", detail=path)


def stub_post(draft: Draft) -> PostResult:
    return PostResult(
        platform=draft.gap.platform,
        status="posted",
        url=None,
        detail=f"stub: would POST to {draft.gap.platform}: {draft.title}",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/seo_agent && .venv/bin/pytest tests/test_seed_posters.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/seo_agent
git add pipeline/seed/posters.py tests/test_seed_posters.py
git commit -m "feat(seed): stub green poster + yellow draft-file writer"
```

---

### Task 5: Dispatch + CLI (`run.py`) and console script

**Files:**
- Create: `pipeline/seed/run.py`
- Modify: `pyproject.toml` (add `wf-seed` under `[project.scripts]`, in the audit/setup block)
- Test: `tests/test_seed_run.py`

**Interfaces:**
- Consumes: `parse_gaps`, `Gap` (gaps.py); `draft`, `Draft` (generate.py); `tier_of` (tiers.py); `stub_post`, `write_draft_file`, `PostResult` (posters.py).
- Produces:
  - `dispatch(drafts: list[Draft], drafts_dir: str, poster=None) -> list[PostResult]` — `poster` injectable, defaults to `stub_post`. green → `poster(draft)`; yellow → `write_draft_file`; red → `PostResult(status="skipped", detail="never-auto")`; unknown → `PostResult(status="skipped", detail="unknown platform")`.
  - `run_seed(gaps_path: str, out_dir: str, drafts_dir: str, runner=None, poster=None, live: bool=False) -> dict` — reads+json-loads `gaps_path`, `parse_gaps`, drafts each gap (a gap whose generation raises is recorded under `dropped` with `_reason` and skipped), dispatches, writes `<out_dir>/seed-log.json`, returns the log dict. `runner` is the injectable claude seam passed to `draft`.
  - `main() -> int` — argparse: `--gaps` (required), `--out-dir` (default `.`), `--drafts-dir` (default `<out_dir>/drafts`), `--live` (store_true, reserved; recorded in log `mode`). Prints a one-line summary.
- Log shape: `{"mode": "dry-run"|"live", "counts": {"posted","queued","skipped","dropped"}, "results": [PostResult-as-dict...], "dropped": [rows-with-_reason...]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seed_run.py
"""Dispatch routes each draft by tier; run_seed is the offline end-to-end with an
injected claude runner and the stub poster, so it makes no network calls and
needs no accounts. A gap whose generation fails is recorded in `dropped`, never
crashing the run."""
from __future__ import annotations

import json

from pipeline.seed.gaps import Gap
from pipeline.seed.generate import Draft
from pipeline.seed.posters import PostResult
from pipeline.seed.run import dispatch, run_seed


def _draft(platform: str) -> Draft:
    g = Gap(brand="Acme", platform=platform, topic="t", target_keyword="k",
            angle="a", url_target="https://acme.com")
    return Draft(gap=g, title=f"Title {platform}", body="body",
                 brand_mention="Acme (https://acme.com).")


def test_dispatch_routes_by_tier(tmp_path):
    drafts = [_draft("devto"), _draft("reddit"), _draft("wikipedia"),
              _draft("mastodon")]
    results = dispatch(drafts, str(tmp_path / "drafts"))
    by_platform = {r.platform: r for r in results}
    assert by_platform["devto"].status == "posted"
    assert by_platform["reddit"].status == "queued"
    assert by_platform["wikipedia"].status == "skipped"
    assert by_platform["wikipedia"].detail == "never-auto"
    assert by_platform["mastodon"].status == "skipped"
    assert "unknown" in by_platform["mastodon"].detail


def _fake_runner(prompt: str) -> str:
    inner = {"title": "Generated", "body": "# b\nAcme rocks",
             "brand_mention": "Acme (https://acme.com/widget)."}
    return json.dumps({"result": json.dumps(inner)})


def test_run_seed_end_to_end_offline(tmp_path):
    log = run_seed(
        gaps_path="tests/fixtures/seed_gaps.json",
        out_dir=str(tmp_path),
        drafts_dir=str(tmp_path / "drafts"),
        runner=_fake_runner,
    )
    # fixture has devto(green), reddit(yellow), wikipedia(red)
    assert log["counts"]["posted"] == 1
    assert log["counts"]["queued"] == 1
    assert log["counts"]["skipped"] == 1
    assert log["mode"] == "dry-run"
    # log file written
    written = json.loads((tmp_path / "seed-log.json").read_text())
    assert written["counts"] == log["counts"]
    # yellow draft file exists
    assert (tmp_path / "drafts").exists()


def test_run_seed_records_generation_failure_as_dropped(tmp_path):
    def boom(prompt: str) -> str:
        raise RuntimeError("claude down")

    log = run_seed(
        gaps_path="tests/fixtures/seed_gaps.json",
        out_dir=str(tmp_path),
        drafts_dir=str(tmp_path / "drafts"),
        runner=boom,
    )
    assert log["counts"]["posted"] == 0
    assert log["counts"]["dropped"] == 3  # all three gaps fail generation
    assert any("claude down" in d["_reason"] for d in log["dropped"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/seo_agent && .venv/bin/pytest tests/test_seed_run.py -v`
Expected: FAIL with `cannot import name 'dispatch'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/seed/run.py
"""Orchestrate the seed engine: gaps.json -> drafts (claude) -> dispatch by tier
-> seed-log.json. Offline-testable via injectable `runner` (claude seam) and
`poster` (green action). MVP uses the stub poster, so a run makes no network
calls and needs no platform accounts — only the claude subscription for drafts.

CLI: wf-seed --gaps gaps.json [--out-dir .] [--drafts-dir ./drafts] [--live]
`--live` is reserved for when real green posters replace the stub; today the stub
is always used and the flag only labels the log's `mode`."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from pipeline.seed.gaps import parse_gaps
from pipeline.seed.generate import draft
from pipeline.seed.posters import PostResult, stub_post, write_draft_file
from pipeline.seed.tiers import tier_of


def dispatch(drafts, drafts_dir: str, poster=None) -> list[PostResult]:
    poster = poster or stub_post
    results: list[PostResult] = []
    for d in drafts:
        tier = tier_of(d.gap.platform)
        if tier == "green":
            results.append(poster(d))
        elif tier == "yellow":
            results.append(write_draft_file(d, drafts_dir))
        elif tier == "red":
            results.append(PostResult(platform=d.gap.platform,
                                      status="skipped", detail="never-auto"))
        else:
            results.append(PostResult(platform=d.gap.platform, status="skipped",
                                      detail="unknown platform"))
    return results


def run_seed(gaps_path: str, out_dir: str, drafts_dir: str,
             runner=None, poster=None, live: bool = False) -> dict:
    with open(gaps_path, encoding="utf-8") as fh:
        rows = json.load(fh)
    gaps, dropped = parse_gaps(rows)

    drafts = []
    for g in gaps:
        try:
            drafts.append(draft(g, run=runner))
        except Exception as e:  # generation failure ≠ dead run
            dropped.append({"platform": g.platform, "topic": g.topic,
                            "_reason": f"generation failed: {e}"})

    results = dispatch(drafts, drafts_dir, poster=poster)

    counts = {
        "posted": sum(r.status == "posted" for r in results),
        "queued": sum(r.status == "queued" for r in results),
        "skipped": sum(r.status == "skipped" for r in results),
        "dropped": len(dropped),
    }
    log = {
        "mode": "live" if live else "dry-run",
        "counts": counts,
        "results": [asdict(r) for r in results],
        "dropped": dropped,
    }
    import os
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "seed-log.json"), "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=2)
    return log


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Seed brand-mention topics from a gaps.json.")
    ap.add_argument("--gaps", required=True, help="path to gaps.json")
    ap.add_argument("--out-dir", default=".", help="where seed-log.json goes")
    ap.add_argument("--drafts-dir", default="",
                    help="where yellow-tier drafts go (default <out-dir>/drafts)")
    ap.add_argument("--live", action="store_true",
                    help="reserved: use real green posters (MVP: stub only)")
    args = ap.parse_args()
    import os
    drafts_dir = args.drafts_dir or os.path.join(args.out_dir, "drafts")
    log = run_seed(args.gaps, args.out_dir, drafts_dir, live=args.live)
    c = log["counts"]
    print(f"seed [{log['mode']}]: posted={c['posted']} queued={c['queued']} "
          f"skipped={c['skipped']} dropped={c['dropped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/seo_agent && .venv/bin/pytest tests/test_seed_run.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Register the console script**

In `pyproject.toml`, under `[project.scripts]` in the `# ── audit / setup ──` block, add:

```toml
# Brand seed engine — turns the measure agent's gaps.json into brand-mention
# topics: green auto-post (stub in MVP), yellow drafts for approval, red skip.
wf-seed = "pipeline.seed.run:main"
```

- [ ] **Step 6: Reinstall + smoke-test the CLI end-to-end**

```bash
cd ~/seo_agent && .venv/bin/pip install -e . -q && \
  .venv/bin/wf-seed --gaps tests/fixtures/seed_gaps.json --out-dir /tmp/seedtest && \
  cat /tmp/seedtest/seed-log.json
```
Expected: prints `seed [dry-run]: posted=1 queued=1 skipped=1 dropped=0` and a `seed-log.json` with matching counts. (This step DOES call the real `claude` CLI for the 1 green + 1 yellow gap — ~2 subscription calls, no dollar cost.)

- [ ] **Step 7: Run the full seed suite + commit**

```bash
cd ~/seo_agent && .venv/bin/pytest tests/test_seed_*.py -v && \
  git add pipeline/seed/run.py tests/test_seed_run.py pyproject.toml && \
  git commit -m "feat(seed): dispatch + wf-seed CLI, offline e2e"
```
Expected: all seed tests PASS, commit created.

---

## Self-Review

**Spec coverage:**
- Tiering (green/yellow/red) → Task 1 + Task 5 dispatch ✅
- gaps.json contract + loud drop → Task 2 ✅
- generate via claude CLI, no API key → Task 3 ✅
- one fn per platform, env creds, loud skip (posters shape) → Task 4 (stub + yellow; real posters post-MVP as noted in spec Future) ✅
- pure/injectable seam, offline suite → Tasks 3/5 use injected `run`/`poster` ✅
- seed-log.json + loud skips + dropped → Task 5 ✅
- `--dry-run` default / `--live` opt-in → Task 5 (`--live` reserved; stub is inherently non-live) ✅
- MVP = core engine + stub poster, only claude subscription → Tasks 1–5 ✅

**Placeholder scan:** no TBD/TODO; every code step shows full code. ✅

**Type consistency:** `Gap`, `Draft`, `PostResult` fields identical across tasks; `tier_of` returns match dispatch branches; `run`/`runner`/`poster` seam names consistent (generate uses `run`, run_seed exposes `runner` and passes it as `run=`). ✅

Note: real green platform posters (`post_devto`, etc.) are intentionally out of MVP scope per spec "Future"; they slot in as `poster=` replacements for `stub_post` with zero interface change.
