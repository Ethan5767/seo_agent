# Repo-In SEO Pipeline — design doc v3

**Status:** agreed · **Repo:** `Ethan5767/seo_agent` · **Imported from:** `richardnhek/seo-content-pipeline` @ `v2.1.0` · **Date:** 2026-08-05

**Supersedes v2.** v2 designed a repo-in pipeline that kept the DOCX flow beside it,
tiered each *change* by machine-checkability, auto-merged the safe ones, and ran on a
Vercel dashboard with a pull-based worker. Four decisions collapsed most of that:

| Decision | Consequence |
|---|---|
| Internal studio tooling, repos we have access to | No dashboard, no multi-tenant anything |
| **A human merges everything** | No auto-merge, no A/B/C risk tiers |
| **Tier is per-project authority**, set at onboarding | Tier answers "what may the agent touch", not "who approves" |
| **Claude Code is the only writer** | The emitter, DOCX intake, and the typed contract are deleted |

The result is one rail, one writer, and about half the code.

---

## 1. Target flow

```
GitHub repo + domain
   ↓  MEASURE       live site → findings.json
   ↓  RATCHET       lib/baseline.py → RESOLVED / PERSISTING / NEW / REGRESSION
   ↓  PLAN          findings → worklist.json + report.md
   ↓  REMEDIATE     Claude Code edits files, within tier → changelog.json
   ↓  PR            artifacts committed alongside the diff
   ──────────────── everything above runs in a container, on your machine
   ↓  GATES         16 inherited + 3 new, in Actions on the client repo
   ↓  HUMAN MERGE   always
   ↓  DEPLOY        verify-live → crawler-check → auto-rollback → proof
```

Nothing below the PR line is new. That half already works and is untouched.

Every arrow is a JSON file with a schema — no stage talks to the next through memory
or a prompt. That is the inherited convention and it is what makes each stage
re-runnable and testable offline.

**Artifacts live in the client repo** at `docs/audit/<YYYY-MM>/` and ship *inside the
PR*. The worker holds no state, which is what makes the host swappable: there is
nothing to back up and nothing to migrate.

---

## 2. Tiering — the core of v3

Tier is a **path + operation allow-list**, declared per project and enforced by a gate
on the PR diff. The tier is also injected into the agent's prompt, but that is
efficiency, not safety. **The gate is what makes it true.**

| | May modify | May create | May delete |
|---|---|---|---|
| **T1** — copy | files matching `text_paths` | ✗ | ✗ |
| **T2** — content | `text_paths` + `content.registry` | under `content.location` | ✗ |
| **T3** — full | anything not denied | anything not denied | anything not denied |

- **T1** — wording, meta descriptions, titles, alt text, heading case, schema field
  values. Existing files only.
- **T2** — T1 plus new pages and blog posts, wired into the site via a narrow write
  allowance on `content.registry` (the data file or nav a new page must be added to,
  or `orphan_check` will fail it anyway).
- **T3** — structural work: components, templates, layout, routing.

**The deny-list applies at every tier, T3 included.** It is the shortest and most
load-bearing part of the design:

```yaml
deny:
  - .github/**             # the agent must never edit the gates that judge it
  - docs/client-config.yml # must never raise its own tier
  - package*.json          # no dependency changes
  - wrangler.toml          # deploy config is the rollback path
  - .env*
```

### Config

Tiering extends the **existing `docs/client-config.yml`** — one config per client, not
a second file. Every gate already loads it.

```yaml
tier: 1
text_paths:
  - src/data/**/*.ts
  - src/content/**/*.mdx
content:                          # T2+ only
  location: src/content/blog/
  registry: [src/data/posts.ts]
  format: mdx
```

**No `content.location` declared → T2 is unavailable.** No declared content home means
no content writing; the agent does structural SEO only.

### The honest limit

Path globs are structural, not semantic. At T1 the agent may modify `services.ts` —
nothing at the path level stops it changing a price instead of a sentence. Three
things cover that gap:

1. `claim_provenance_check` — every factual claim must trace to config (§4.1)
2. `acceptance_check` — the change must clear the finding it claims to fix (§4.3)
3. You, merging

If diffs come back sloppy in practice, the upgrade is **per-item scope**: each work
item declares its target files and the gate checks hunks against them. Deferred
deliberately — it is real machinery and the three checks above plus human review may
well be enough. Revisit after the first few real cycles.

---

## 3. What was removed

Done, in commit `79b0b5b`. **133 files → 73. 354 tests → 87** (the missing tests
covered the deleted code). Both commits are in the repo, so any of this is one
`git revert` away.

### Whole directories

| Path | Files | Why |
|---|---|---|
| `pipeline/intake/` | 16 | DOCX, Google Drive, and Discord intake |
| `pipeline/generate/` | 11 | `emit_ts`, `models`, `repo_layout`, `brief`, `classify`, `distill`, `repair`, `validators`, 2 SPECs |
| `distiller/` | 4 | DOCX distillation skill — **`anti-slop-prose.md` and `serp-title-meta-craft.md` were ported first**, to `skills/site-remediation/references/`. They are the best prose doctrine in the tree and the new skill needs them |

### Gates: 19 → 16

| Gate | Verdict | Why |
|---|---|---|
| `pages_are_data_check.py` | ❌ deleted | Hardcoded to Next `src/app` and its dynamic-segment model, and it enforces *emitter doctrine* — "content lives in DATA, `page.tsx` is a thin template". Meaningless on an arbitrary repo |
| `brief_fanout_check.py` | ❌ deleted | Runs on `docs/briefs/*.json`, which only the emitter produced. Its five requirements survive as **doctrine in the remediation skill** for T2 authoring |
| `validate_multistate_config.py` | ❌ deleted | Reads `~/.claude/references/*` — files outside the repo, on one machine. Unportable by construction, and it validates the config schema being replaced |
| `client_docs_check.py` + `lib/client_docs.py` | 🔧 rework | Right idea (a cycle must leave a durable in-repo record), wrong target — retarget from `docs/intake-archive/` to `docs/audit/` |
| `noncommodity_check.py` | 🔧 re-tune | Works as-is; thresholds were calibrated on human writing (§4.4) |
| the other 14 | ✅ kept | |

**Surviving 16:** `audit_built`, `audit_ssr`, `capsule_check`, `check_headings`,
`client_docs_check`, `em_dash_check`, `fingerprint_check`, `forbidden_sweep`,
`image_budget_check`, `lcp_hygiene_check`, `llms_sales_purge`, `noncommodity_check`,
`orphan_check`, `parity_check`, `robots_aicrawler_check`, `rules_selftest`.

### Everything else

| Removed | Why |
|---|---|
| `cycle_status.py`, `lib/cycle_state.py` | Two-operator coordination for a manual multi-stage cycle. One local CLI run does not need it |
| `gbp_baseline.py` | Writes a map-pack stub for an agent to fill via MCP. Out of scope |
| `setup_gtm_foundation.py` | GTM conversion tagging — unrelated, and it also reads `~/.claude/references/*` |
| `intake-poll.yml`, `drive-poll.yml`, `cycle-emit.reusable.yml` + example | **~2,180 cron minutes/month**, which was the entire case for making the engine repo public |
| `discord-intake.example.yml`, `drive-intake.example.yml`, `requirements-intake.txt` | |
| 15 test files | Tests of the above |

### Kept against first instinct

`pipeline/audit/client_profile.py` looked like DOCX-era client-shape logic and was
deleted, then restored: **`.github/actions/build-site/action.yml` shells out to
`wf-client-profile`** to resolve build dir and framework before every build. Removing
it breaks the build for every client. It stays, and gets reworked with the config
schema.

### Repairs the deletion forced

- **`quality-gate.reusable.yml`** — dropped the two dead gate steps and their eight
  outcome references (summary table, failure messages, exit-code registry, the
  `for g in …` loop).
- **`tests/conftest.py`** — imported `pipeline.generate.repo_layout` at module level,
  which broke the entire suite, not just emitter tests.
- **`pyproject.toml`** — pruned ~25 dead entry points; dropped the `[intake]` extra
  (docling + the Google client stack); added `[test]`. This fixes the v2 §11 bug
  where `pip install -e .` could not run the tests — the three modules that imported
  `docx` are all gone now.

---

## 4. New work

Four modules and three gates. Everything else is reuse. New modules go into the
existing `pipeline/audit/` and `pipeline/gates/` packages — no new top-level package.

### 4.1 ⛔ `gates/claim_provenance_check.py` — build this first

**Every factual claim in changed text must resolve to a config field or a cited
source.** Numbers, years in business, star ratings, review counts, license numbers,
certifications, warranty terms, guarantees, superlatives ("largest", "only", "#1").

This is the largest new risk by a wide margin, and **T1 does not reduce it** — a model
"improving the wording" of a sentence is exactly where an invented credential appears.
A model writing *"licensed and insured for 28 years, 4.9★ across 1,200 reviews"* about
a business with none of that is legal exposure, and it is the error class models
produce most fluently.

The rule already exists in the ported `distiller` doctrine. **As prose.** Promote it
to code:

> **Derivation only, never invent.** Every number, credential, rating, warranty name,
> and year-count comes from config (`trust_signals`, `licenses`, `usp`,
> `bio_paragraphs`) or the work item's own evidence. A claim you cannot source gets
> removed, not reworded.

Fail loud on an empty allow-list — same rule as `forbidden_sweep`'s empty-ruleset
exit 4. **A gate that cannot run must refuse, not pass.**

### 4.2 ⛔ `gates/tier_check.py`

Reads `tier`, `text_paths`, `content.*`, and `deny` from `docs/client-config.yml`;
walks the PR diff; refuses on any changed path or operation the tier does not permit.
Deletes are denied outright at T1 and T2.

The emitter had this instinct — its commit step was an allow-list, not `git add -A`.
Same idea, generalized, and it is what makes the tier promise real rather than a
prompt the model may ignore.

### 4.3 ⛔ `gates/acceptance_check.py`

Re-run each work item's `acceptance` check against the built output. **If the finding
it claims to fix is still present, refuse.**

This closes the loop that makes the system trustworthy: a change is done because the
original measurement now passes, not because a model said so. It also kills the most
common agent failure — a confident summary describing a fix that never landed.

Runs once, pre-merge, in Actions. (v2 ran it twice; the post-deploy run existed to
backstop auto-merge, and the next cycle's measurement covers the same ground.)

All three belong in `NEVER_BASELINEABLE` (`lib/baseline.py:132`) — you cannot
grandfather a fabricated credential.

### 4.4 Tuning, not new code

`noncommodity_check.py` (sibling 5-gram overlap) already guards templated sameness,
but it was calibrated on human writing. Forty city pages rewritten by one model in one
run will converge much harder than forty written by four freelancers. **Re-tune
thresholds against real agent output before trusting them.**

### 4.5 `audit/measure.py` — `wf-site-health`

Refactor `audit_live.py` to *return* typed `Finding`s rather than print a summary —
mechanical, and it gives you its 13 existing checks for free. Later, fold in the
external providers (§5).

```
wf-site-health --project . [--no-api] [--no-gsc]
  → docs/audit/<YYYY-MM>/findings.json
  exit 0 clean · 1 findings · 2 usage · 19 every source unreachable (REFUSE)
```

**Exit 19 matters.** A run where every source failed must be red, not a green report
with zero findings.

### 4.6 `audit/plan.py` — `wf-site-plan`

**Reuse `lib/baseline.py` verbatim.** It already fingerprints findings by content
(never line numbers) and partitions new-vs-known. Feeding audit findings through it
gives you the four lanes `HOW-IT-WORKS.md` specifies but which have no implementation
anywhere in the repo: RESOLVED / PERSISTING / NEW / REGRESSION.

Without a ratchet, run #2 reports the same 400 legacy issues as run #1 and people stop
reading it. **Do not write a second ratchet.**

A work item is typed data, not prose:

```jsonc
{
  "id": "wi-2026-08-0031",
  "finding_fp": "a3f9…",
  "url": "/roof-replacement-charlotte-nc/",
  "kind": "meta_description_out_of_band",
  "lane": "REGRESSION",
  "evidence": { "current": "…", "length": 71 },
  "acceptance": { "check": "meta_desc_length", "expect": { "min": 120, "max": 160 } }
}
```

`acceptance` is load-bearing — §4.3 reads it. An item with no machine-checkable
`acceptance` does not belong in the worklist; it belongs in the report as something a
human should look at.

**The tier filter earns its keep here.** The report lists *every* finding; the worklist
carries only what the tier permits. A "thin content, needs a new page" finding at T1
appears as **not actionable at your tier** — visible, counted, not silently dropped.
Which also means the report tells you when a client should move up a tier.

### 4.7 `audit/remediate.py` + `skills/site-remediation/SKILL.md`

Claude Code, given the worklist and the repo, editing files directly in the local
checkout. The CLI commits and opens the PR.

Constraints, enforced by §4.1–4.3 rather than trust:

- Touch only what the tier permits
- Emit `docs/audit/<YYYY-MM>/changelog.json` mapping every changed file → work item
- Never write content unless `content.location` is declared
- Hard per-run caps: max files, max items, max tokens — same instinct as `--limit`

Failure behaviour: hitting a cap stops cleanly, commits what landed, and records the
stop in `changelog.json`. A half-failed run must be legible.

---

## 5. Tooling

**In the container — 4:**

| Tool | For |
|---|---|
| Python | the pipeline |
| `git` | checkout, branch, commit |
| `gh` CLI | open the PR |
| Claude Code | the writer |

**External APIs — 0 for phase 1.** Measurement starts with the existing `audit_live`
HTTP checks. No accounts, no keys, no spend. You can run a real audit before deciding
whether any paid tool earns its keep.

**Add in phase 6 — 3:**

| API | Buys | Cost |
|---|---|---|
| **DataForSEO On-Page** | redirect chains, broken links, click depth, structured-data validation, Lighthouse | $0.000125/page base · $0.00125 with JS rendering. A 2,000-page crawl is $0.25 |
| **Google Search Console** | impressions, clicks, CTR, position, index state, cannibalization | free |
| **PSI / CrUX** | *field* Core Web Vitals — what Google actually ranks on, vs Lighthouse's lab data | free |

Write **one** provider module, `pipeline/audit/dataforseo.py`, returning normalized
findings. Do not build a `providers/` package with an ABC and a registry for one
vendor. Add the abstraction when a second vendor lands.

**Evaluated and skipped:** Sitebulb (no API or CLI at all — disqualified for
automation), Semrush (API gated behind the $499.95/mo Business tier), Screaming Frog
(a licensed desktop binary in CI is awkward), SE Ranking (buying dashboards we would
not use), the AI-visibility vendors (least mature category — pick one when phase 6 has
a question the numbers would answer).

**Already running:** GitHub Actions (gates, build, deploy) and Cloudflare Pages.

### Docker

One Dockerfile, ~20 lines. No compose, no registry, no orchestration until the worker
actually moves off your machine. The value is not isolation — it is that the
dependencies get declared now instead of discovered missing on a new box in six
months. Moving hosts becomes `scp` + `docker run`.

The thing that actually makes the host swappable is §1: the tool takes a repo URL and
writes a PR, holding no local state.

---

## 6. Known constraints

**The gates are framework-blind only for statically-exported sites.** The inherited
docs claim they "scan whatever `BUILD_DIR` points at", which is true of most of them —
but `orphan_check` and `parity_check` derive routes from `<dir>/index.html` under
`./out`. A client on SSR or ISR produces no such tree and both gates go silent or
wrong. This is an **onboarding precondition**, not a footnote: verify the client
statically exports before promising the full gate suite.

**A `git revert` runbook is still needed.** The deploy rail's auto-rollback restores a
*build*. A wrong-but-valid meta description builds, verifies, and sits live. With a
human merging every change this is much less likely than under v2's auto-merge, but
the runbook should exist before the first T1 client goes live.

**Two extra gates run against every client's build.** Provenance and acceptance both
parse changed text; watch gate-job duration on the larger repos.

---

## 7. Build sequence

Each phase ships alone. Do not start one before the phase above is merged.

| # | Phase | Ships |
|---|---|---|
| 1 | `audit_live` returns typed `Finding`s + `wf-site-health` | every existing check, ratchet-ready, zero spend |
| 2 | Onboarding — extend `bootstrap_config` with the tier block; static-export precondition check | any repo declares its tier and content home |
| 3 | **`plan.py` on `lib/baseline.py`** | four lanes, REGRESSION detection, `report.md` |
| 4 | **`claim_provenance_check` + `tier_check` + `acceptance_check`** | the safety floor |
| 5 | `remediate.py` + `site-remediation` skill + Dockerfile, **T1 only** | agent does copy fixes |
| 6 | DataForSEO + GSC + CrUX providers | redirects, broken links, depth, field CWV, cannibalization |
| 7 | **T2** — content authoring (needs `content.location`) | agent writes pages |
| 8 | **T3** — structural | agent touches components and templates |

**Phase 3 is the highest-value stopping point if you stall.** Health + ratchet +
REGRESSION detection, with humans remediating, delivers most of the value at none of
the model risk.

**Gates before authorship — phase 4 precedes 5 deliberately.** Shipping agent writes
against the current 16 gates means shipping unvalidated model claims to client sites.

---

## 8. Cost, five clients

| Component | Cost |
|---|---|
| Gates, preview, deploy — Actions on private client repos (free tier) | **$0** |
| Static hosting — Cloudflare Pages | **$0** |
| GSC + CrUX + PSI | **$0** |
| DataForSEO On-Page (phase 6+) | **$1–13/mo** |
| Claude agent runs | **~$5–20/mo** |
| | **≈ $6–33/mo** |

Deleting the two cron pollers removed ~2,180 Actions minutes/month, which was the
entire argument for making the engine repo public. **`seo_agent` can stay private.**

Per-MTok: Opus 5 $5/$25 · Sonnet 5 $3/$15 · Haiku 4.5 $1/$5. A remediation run over
one client's worklist is roughly 200K in / 30K out — about $1.05 on Sonnet 5, $1.75 on
Opus 5.

**Default to Sonnet 5 for bulk remediation, Opus 5 for the hard judgment** (T2/T3
authoring, ambiguous scope). **Use prompt caching** — the client config, house rules,
and worklist schema are a stable prefix and cache reads run ~0.1× input price.

Pay-as-you-go beats a subscription at this volume, and per-response `usage` gives
per-client cost attribution for free.

---

## 9. Open decisions

1. **Which model authors, and what is the per-cycle token ceiling?** Needed before
   phase 5. There should be a hard cap, the way `--limit` caps pages.
2. **What does a client repo pin?** Client callers pin the engine by tag. `seo_agent`
   needs its own tagging discipline from day one, and the `PIPELINE_REF` stamp in
   `quality-gate.reusable.yml` still reads `v2.1.0` / `richardnhek/seo-content-pipeline`
   — must be updated before any client points at this repo.
3. **What are the real `noncommodity_check` thresholds for agent output?** Cannot be
   answered without a phase-5 run to measure against.
4. **What happens to a client that does not statically export?** §6. Onboard at T1
   with a reduced gate set, or decline until they do.
5. **Which client goes first?** The smallest static-export repo with the cleanest
   `client-config.yml`.

---

## 10. Inherited debt, worth fixing while here

Found reviewing the imported tree — cheap, and all of it now describes a repo that no
longer exists:

- **README, `HOW-IT-WORKS.md`, and `MODULES.md` all describe the DOCX pipeline.** They
  are now the largest source of wrong information in the repo. `MODULES.md:3` claimed
  55 modules / 47 commands / 327 tests before the deletion; it is wrong in a new way now.
- **Gate count is now wrong in three places** — `README.md:4`, `:24`, and `:40` all say
  19. The true number is 16 today, 19 again after phase 4. Compute it in CI or delete
  the claim.
- **10 dead doc links** — `docs/modules/*.md` (8), `consuming-the-pipeline.md`,
  `DOCTRINE-GATE-MATRIX.md`. The doctrine matrix held each gate's *why*: the most
  valuable missing file, and the one an agent-authorship contributor most needs.
- **`competitors:` is dead config** — declared in the starter, read by zero modules.
  Give it a consumer in phase 6 or delete it.
