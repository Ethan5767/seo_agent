# Repo-In SEO Pipeline — design doc v2

**Status:** proposal · **Base:** `richardnhek/seo-content-pipeline` @ `v2.1.0` · **Date:** 2026-08-05

**Supersedes v1.** v1 assumed the client site stayed as-is and only content flowed
in. v2 is your revised spec: *point it at a GitHub repo, measure the live site,
let Claude Code improve the repo (code + content), PR, merge, deploy.*

---

## 1. Feasibility, up front

I checked the coupling before designing. The verdict splits cleanly, and the
split is the whole architecture:

| Layer | Generalizes to an arbitrary repo? | Why |
|---|---|---|
| **Gates** (19 modules) | **Yes, today** | They are framework-blind by design — every one scans whatever `BUILD_DIR` points at. `quality-gate.reusable.yml` states it explicitly: *"There is no per-gate framework logic anywhere."* |
| **Deploy rail** | **Yes, today** | build → deploy → verify → crawler-check → auto-rollback → proof is framework-agnostic |
| **Emitter** (`emit_ts`) | **No** | See below |

`pipeline/generate/repo_layout.py` exists *because* the emitter was hardcoded to
one client's shape. Its own docstring:

> *"models.py and emit_ts.py have always encoded ONE repo's shape — Acme's:
> `src/app/[slug]/...` route files, `location-pages.ts`/`services.ts` data files…
> The 2026-08 four-terminal cycle proved every other client repo blocked on those
> assumptions."*

Even after generalization it still requires Next-style route files, TypeScript
data files, and registry arrays. It generalizes across *similar* repos, not
arbitrary ones. `framework_family()` knows exactly three families: `next`,
`vite`, `wordpress`.

**So do not generalize the emitter. Bypass it.**

That is exactly what your instinct — "Claude CLI go through the repo" — already
does. Claude Code *is* the general-purpose writer. The emitter stays for clients
whose repos fit the typed contract, where determinism and byte-idempotency are
worth more than flexibility.

**The load-bearing asset you are inheriting is the gate layer, not the emitter.**
Nineteen deterministic checks that run against built HTML from any framework,
plus a ratchet, plus a deploy rail with auto-rollback and proof. That is the part
that makes an agent safe to let loose on a repo, and it already works.

---

## 2. Tooling — research findings

You planned DataForSEO. **That is the right call, and it is more right than you
realized** — you were thinking of it as a rank/keyword API. Its **On-Page API is
a crawler-as-a-service**, which makes Sitebulb redundant for anything automated.

### The finding that matters

DataForSEO On-Page API crawls a whole site and returns ~120 metrics per page —
status codes, redirect chains, duplicate content, broken links, meta tags,
internal links, structured-data validation, and **Google Lighthouse / Core Web
Vitals** — across 21 endpoints, with JS rendering available.

Pricing is pay-as-you-go, no subscription, **$0.000125/page** base ·
**$0.00125/page** with JS rendering · $0.00425 with full browser rendering.

At your scale that is a rounding error:

| Site size | Base crawl | With JS rendering |
|---|---|---|
| 500 pages | **$0.06** | **$0.63** |
| 2,000 pages | $0.25 | $2.50 |
| 5 clients × 2,000 pages, monthly | $1.25/mo | $12.50/mo |

Unused pages are refunded if you over-specify. $50 minimum deposit.

### The comparison

| Tool | API / CI | Crawls site | CWV | Verdict |
|---|---|---|---|---|
| **DataForSEO On-Page** | ✅ REST | ✅ | ✅ Lighthouse | **Take it.** Cheapest by an order of magnitude, no subscription |
| **Google Search Console API** | ✅ REST | — | — | **Take it, free.** Only source of truth for impressions/clicks/CTR/position + index state. Config already declares `gsc_property`, read by nothing |
| **PageSpeed Insights / CrUX API** | ✅ REST | — | ✅ **field** data | **Take it, free.** Lighthouse is lab data; CrUX is what Google actually ranks on |
| **Lighthouse CI** | ✅ OSS | — | ✅ lab | Free, runs in Actions. Good as a **PR gate** for CWV regressions — complements, doesn't replace |
| **Screaming Frog CLI** | ✅ CLI | ✅ | ✅ | The only desktop crawler with real CLI/CI support (~£259/yr). Take it **only** if you need custom extraction or want crawling inside CI with no external API. A licensed desktop binary in Actions is awkward |
| **Sitebulb** | ❌ **none** | ✅ | ✅ | **Disqualified for automation.** No CLI, no API; cloud has scheduling but no programmatic access. Its strength is human-read reporting and crawl-over-crawl diffs — which is why the current docs describe it as a manual 5-click monthly process |
| **SE Ranking** | ✅ | ✅ | ✅ | Reporting + AI-visibility built in (~$103/mo + $149/100k credits). Higher cost, less building. Reasonable if you'd rather buy dashboards than write them |
| **Semrush API** | ✅ | ✅ | ✅ | Gated behind the **$499.95/mo** Business tier. Skip |
| **Serper / SerpApi / Bright Data** | ✅ | ❌ | ❌ | SERP data only. Serper is cheapest if you need only SERPs |

### AEO / AI-visibility — a separate category

Your config already declares `engines: [aio, chatgpt, perplexity, ai_mode,
bing_copilot]`, `seed_queries`, and `competitors` — and **`competitors` is read
by exactly zero modules.** The scaffolding is there; nothing fills it.

This category is the least mature and the most volatile. **Otterly.AI** (~$29/mo)
is the cheap entry; **Profound** is the enterprise option; **SE Ranking** bundles
it. My advice: don't buy yet. Phase 4 below defines the loop; pick a vendor when
you have a real question the numbers would answer.

### Recommended stack

```
Free tier, build first:   GSC API + PSI/CrUX API + the existing audit_live checks
Paid core:                DataForSEO On-Page (crawl + Lighthouse) + SERP/Keywords
In CI as a PR gate:       Lighthouse CI
Skip:                     Sitebulb (no API), Semrush (paywalled API)
Defer:                    AI-visibility vendor until phase 4 has a question for it
```

Write **one** provider module — `pipeline/audit/dataforseo.py` — returning
normalized findings. Do not build a `providers/` package with an ABC and a
registry for one vendor. Add the abstraction when a second vendor actually lands.

---

## 3. The merge — a concern, then the design

You wrote: *"open the pr, merge and deploy."*

**The concern, briefly.** Every layer of this codebase is arranged around one
rule — a human merge is the only path to production. It is in the README, in
`HOW-IT-WORKS.md` §5 ("the sacred gate"), in the header of every workflow, and
enforced by branch protection. Removing the human is not a config toggle; it
removes the thing the other decisions were built to serve.

**But it is your call, and there is a version of it that is genuinely sound.**

GitHub's native auto-merge (`gh pr merge --auto`) merges *only when every required
check passes*. So "merge" need not mean "merge blindly" — it can mean **the gates
decide instead of a person**. That is consistent with "agent proposes, gates
dispose"; it just makes gate coverage the whole safety argument.

Which leads to the real question:

> **Auto-merge is safe exactly to the degree your gates cover the change class.**

For structural fixes — meta length, title band, alt text, schema fields, internal
links, image dimensions, canonicals, heading case — coverage is genuine, the
acceptance test is exact, and the change is trivially revertible. For net-new
model-written prose, coverage does not exist yet (§5).

### Risk-tiered auto-merge

Tier each work item by whether its acceptance criterion is fully machine-checkable:

| Tier | Change class | Merge |
|---|---|---|
| **A** | Deterministic + exact acceptance test: meta/title bands, alt text, schema fields, internal links, `width`/`height`, canonical, heading case, redirect fixes | **auto-merge** once all checks green |
| **B** | Model-written prose: rewritten body copy, new pages, anything touching claims, trust signals, or pricing | **human review** — always |
| **C** | Anything the provenance gate flagged, any REGRESSION-lane item, any repo in its first 3 cycles | **human review** — always |

Tier A is most of the volume, so you get most of the automation. Tier B is where
a mistake is expensive and hard to detect — keep the human there.

**Two safety notes:**

1. The post-deploy net already exists and is good: `verify-live.sh` +
   `cf-crawler-check.sh` are blocking, and `cf-rollback.sh` auto-reverts to the
   captured deployment id on failure. That materially strengthens the case for
   Tier A auto-merge.
2. **It does not cover bad content.** Rollback restores a *build*; a wrong-but-
   valid meta description builds and verifies fine and will sit live. Tier A
   therefore needs a post-deploy acceptance re-check plus a documented
   `git revert` + redeploy runbook. Build that with the auto-merge, not after.

---

## 4. Target flow

```
GitHub repo URL + domain
        │  ONBOARD — detect framework, build cmd, output dir, content location
        │            → docs/client-config.yml (scaffolded, human-confirmed once)
        ▼
    MEASURE — DataForSEO On-Page + GSC + PSI/CrUX + existing audit_live checks
        │            ↓ typed Findings, fingerprinted
        ▼
    RATCHET — lib/baseline.py → RESOLVED / PERSISTING / NEW / REGRESSION
        │
        ▼
     PLAN — findings → work-list, each item tiered A/B/C with an acceptance test
        │            ↓ docs/audit/<YYYY-MM>/worklist.json
        ▼
   ┌────┴─────────────────────────────────┐
   │ TYPED PATH          │  AGENT PATH     │   ← two writers, one gate layer
   │ emit_ts             │  Claude Code    │
   │ (contract repos)    │  (any repo)     │
   └────┬─────────────────────────────────┘
        ▼
     GATES — 19 existing (framework-blind) + 3 new agent-authorship gates
        │
        ▼
      PR ──► Tier A: auto-merge on green · Tier B/C: human merge
        │
        ▼
   DEPLOY → verify-live + crawler check → auto-rollback → proof
        │
        ▼
   ACCEPTANCE RE-CHECK — did the finding actually clear on the live site?
        └──► feeds the next month's baseline
```

Every arrow is a file with a schema — no stage talks to the next through memory
or a prompt. That is the existing repo's convention (`drafts.json` →
`decisions.json` → typed data) and it is what makes each stage re-runnable and
testable offline. Keep it.

---

## 5. New work

### 5.1 Onboarding an arbitrary repo — `pipeline/audit/detect_repo.py`

Today onboarding is `bootstrap_config.py` + a human. For repo-in you need
detection: framework, build command, output dir, and **where content lives**.

```
wf-detect-repo --repo <owner/name> --domain <d> [--write]
  → docs/client-config.yml (scaffold)
  exit 0 detected · 12 framework unknown, needs a human · 2 usage
```

Detection is a lookup table, not intelligence — `next.config.*` → next,
`astro.config.*` → astro, `hugo.toml` → hugo, `wp-content/` → wordpress. Adding
a family is one entry in `FRAMEWORK_FAMILY_DEFAULT_DIR` plus a build command.
Refuse on unknown rather than guess; the repo's own rule is *fail loud, never
guess*.

**Content location** is the new field your spec needs — the "dedicated place to
write":

```yaml
content:
  location: src/content/blog/     # or content/posts/, _posts/, app/blog/
  format: mdx                     # mdx | md | tsx | wordpress-api
  frontmatter_schema: docs/frontmatter.schema.json
  routing: file-based             # file path → URL mapping
```

If absent, the agent does structural SEO only and never authors pages. That is
the correct default: **no declared content home means no content writing.**

### 5.2 Measurement — `site_health.py`

Three sources, one normalized `Finding` output. Refactor `audit_live.py` to
*return* findings rather than print a summary — that is mechanical and gives you
its 13 existing checks for free.

```
wf-site-health --project . [--no-api] [--no-gsc]
  → docs/audit/<YYYY-MM>/findings.json
  exit 0 clean · 1 findings · 2 usage · 19 every source unreachable (REFUSE)
```

Exit 19 matters: a run where all sources failed must be **red**, not a green
report with zero findings. Same rule as `forbidden_sweep`'s empty-ruleset exit 4
— *a gate that cannot run must refuse, not pass.*

### 5.3 Ratchet + plan — `site_plan.py`

**Reuse `lib/baseline.py` verbatim.** It already fingerprints findings by content
(never line numbers) and partitions new-vs-known. Feeding audit findings through
it gives you the four lanes `HOW-IT-WORKS.md` specifies but which have **no
implementation anywhere in the repo**: RESOLVED / PERSISTING / NEW / REGRESSION.

Without a ratchet, run #2 reports the same 400 legacy issues as run #1 and people
stop reading it. Do not write a second ratchet.

A work item is typed data, not prose:

```jsonc
{
  "id": "wi-2026-08-0031",
  "finding_fp": "a3f9…",
  "url": "/roof-replacement-charlotte-nc/",
  "kind": "meta_description_out_of_band",
  "tier": "A",
  "lane": "REGRESSION",
  "evidence": { "current": "…", "length": 71 },
  "acceptance": { "check": "meta_desc_length", "expect": { "min": 120, "max": 160 } },
  "allowed_scope": ["src/data/services.ts#roof-replacement-charlotte-nc"],
  "authoring": "agent"
}
```

`tier`, `acceptance`, and `allowed_scope` are load-bearing — §6 gates and the
auto-merge decision all read them. **An item with no machine-checkable
`acceptance` cannot be Tier A.** That rule alone prevents most of the ways this
goes wrong.

### 5.4 The agent path — `skills/site-remediation/SKILL.md`

Claude Code, given the work-list and the repo, editing files directly.

Follow the `distiller/` precedent exactly — it is already this shape: a skill,
run against a config, whose output must pass a deterministic scanner clean before
it counts as done. Inherit its hard rule verbatim:

> **Derivation only, never invent.** Every number, credential, rating, warranty
> name, and year-count comes from config (`trust_signals`, `licenses`, `usp`,
> `bio_paragraphs`) or the work item's own evidence. A claim you cannot source
> gets removed, not reworded.

Constraints on the agent, enforced by §6 gates rather than trust:

- Touch only paths in the union of the work-list's `allowed_scope`
- Emit `docs/audit/<YYYY-MM>/changelog.json` mapping every changed file → work item
- Never write content unless `content.location` is declared
- Hard per-run caps: max files, max items, max tokens — same instinct as `--limit`

---

## 6. New gates — required before agent writes ship

The existing 19 assume a human wrote the words. These three assume a model did.
All belong in `NEVER_BASELINEABLE` (`lib/baseline.py:132`) — you cannot
grandfather a fabricated credential.

### 6.1 ⛔ `claim_provenance_check.py` — build this first

**Every factual claim in changed text must resolve to a config field or a cited
source.** Numbers, years in business, star ratings, review counts, license
numbers, certifications, warranty terms, guarantees, superlatives ("largest",
"only", "#1").

This is the largest new risk by a wide margin. A model writing *"licensed and
insured for 28 years, 4.9★ across 1,200 reviews"* about a business with none of
that is legal exposure — and it is the error class models produce most fluently.

The rule already exists in `distiller/SKILL.md`. **As prose.** Which is precisely
what this codebase's own doctrine says must not happen:

> *"A lesson that only lives in someone's head gets re-learned."* — `HOW-IT-WORKS.md:110`

Promote it to code. Fail loud on an empty allow-list.

### 6.2 ⛔ `change_scope_check.py`

Every changed file and entry in the diff must map to a work item's
`allowed_scope`. Unattributed change = red.

Without it, "fix this meta description" can return a diff that also rewrote three
sibling pages and nobody notices until it is live. The emitter already has this
instinct — its commit step is an allow-list, not `git add -A`
(`cycle-emit.reusable.yml:476-488`). Same idea, finer grain, and **it is what
makes auto-merge defensible.**

### 6.3 ⛔ `acceptance_check.py`

Re-run each work item's `acceptance` check against the built output. **If the
finding it claims to fix is still present, refuse.**

This closes the loop that makes the whole system trustworthy: a change is done
because the original measurement now passes, not because a model said so. It also
kills the most common agent failure — a confident summary describing a fix that
never landed.

Run it **twice**: pre-merge against the build, and post-deploy against the live
site (§3, safety note 2).

### 6.4 Tuning, not new code

`noncommodity_check.py` (sibling 5-gram overlap) already guards templated
sameness — but it was calibrated on human writing. Forty city pages rewritten by
one model in one run will converge much harder than forty written by four
freelancers. **Re-tune thresholds against real agent output before trusting
them.** No new module.

---

## 7. SEO/AEO practice register

Organized by *what enforces it*, because a practice list in a document rots.
**✅ gated · 🟡 measured not gated · 🔴 gap** · ⛔ never-baselineable

### Technical / indexation

| Practice | Enforcement | Status |
|---|---|---|
| Every sitemap URL has ≥1 inbound internal link | `orphan_check.py` ⛔ | ✅ |
| sitemap == built routes == llms.txt | `parity_check.py` ⛔ | ✅ |
| robots.txt allows every AI **citation** crawler | `robots_aicrawler_check.py` | ✅ |
| Citation bots reach the live edge (not WAF-blocked) | `cf-crawler-check.sh` | ✅ |
| Key routes 200 + expected content post-deploy | `verify-live.sh` | ✅ |
| No unguarded `window`/`document` in SSR paths | `audit_ssr.py` ⛔ | ✅ |
| Self-referencing canonical | `audit_live.py` check 5 | 🟡 gate it |
| No unintended `noindex` | `audit_live.py` check 6 | 🟡 gate it |
| IndexNow on change (Bing/Copilot) | `indexnow_submit.py` | ✅ |
| Redirect chains, loops, soft-404s | — | 🔴 **DataForSEO gives you this** |
| Broken internal/external links | — | 🔴 **DataForSEO** |
| Click depth ≤3 for money pages | — | 🔴 **DataForSEO** |
| Keyword cannibalization | — | 🔴 **GSC** |

### On-page

| Practice | Enforcement | Status |
|---|---|---|
| Title in band, entity skeleton + differentiator | `audit_built.py`, `validators.py` | ✅ |
| Meta description 120–160, qualifier + proof | `audit_built.py`, `audit_live.py` | ✅ |
| Exactly one H1 | `audit_live.py`, `audit_built.py` | ✅ |
| Title Case headings, no possessive contractions | `check_headings.py` | ✅ |
| No em dashes in public text | `em_dash_check.py` | ✅ |
| No invisible / zero-width / bidi characters | `fingerprint_check.py` ⛔ | ✅ |
| Alt text on every image | `audit_built.py`, `audit_live.py` | ✅ |
| Substantive body (800–1500w core band) | `distill.py` | ✅ |
| No page ships orphaned (inbound link wired) | `emit_ts.py` | ✅ |
| Descriptive anchor text | — | 🔴 new |
| Heading hierarchy (no H2→H4 skips) | — | 🔴 new |

### AEO / answer-engine

| Practice | Enforcement | Status |
|---|---|---|
| Answer-first capsule: interrogative H2 → answer → TL;DR | `capsule_check.py` §20 | ✅ |
| ≥6 fan-out queries per page | `brief_fanout_check.py` §19 | ✅ |
| Proprietary variable per page, from allow-list | `noncommodity_check.py` §21 | ✅ |
| Siblings not near-duplicates (5-gram overlap) | `noncommodity_check.py` | ✅ re-tune §6.4 |
| llms.txt factual, zero sales/CTA copy | `llms_sales_purge.py` §30 | ✅ |
| FAQPage + LocalBusiness-subtype + Breadcrumb schema | `audit_built.py` | ✅ |
| Structured-data **validation** (not just `@type` present) | — | 🔴 **DataForSEO** |
| Citation share across `engines:` | declared, **read by nothing** | 🔴 new |
| Competitor citation overlap | `competitors:` **read by zero modules** | 🔴 new |

### Entity / local · Performance · Compliance

| Practice | Enforcement | Status |
|---|---|---|
| NAP consistent, `tel:` + visible phone | `audit_built.py`, `audit_live.py` | ✅ |
| Correct per-state DID on multi-state pages | `distill.py`, distiller rule 4 | ✅ |
| LocalBusiness **subtype**, not bare LocalBusiness | `schema_type`, `audit_built.py` | ✅ |
| Multi-state config consistency | `validate_multistate_config.py` | ✅ |
| Hero not lazy-loaded; `<img>` width/height | `lcp_hygiene_check.py` | ✅ |
| Per-tier image byte budgets | `image_budget_check.py` | ✅ |
| **Field** CWV (LCP/INP/CLS from real users) | — | 🔴 **CrUX API, free** |
| Lab CWV regression on PRs | — | 🔴 **Lighthouse CI, free** |
| Forbidden-phrase ledger (the legal gate) | `forbidden_sweep.py` ⛔ | ✅ |
| The ruleset itself is tested | `rules_selftest.py` ⛔ | ✅ |
| Pages are data + templates, not bespoke TSX | `pages_are_data_check.py` | ✅ |
| **Every factual claim traceable** | — | 🔴 **§6.1 — first** |
| **Diff confined to requested work items** | — | 🔴 **§6.2** |
| **The claimed fix actually passes** | — | 🔴 **§6.3** |

**Read:** on-page and AEO coverage is genuinely strong — better than most
agencies run. Gaps cluster in two places: **crawl-level technical health**, which
is exactly what DataForSEO buys for pennies, and **agent-authorship safety**,
which nothing covers because nothing has needed it yet.

---

## 8. Build sequence

Each phase ships alone. Do not start one before the phase above is merged.

| # | Phase | Ships | Auto-merge? |
|---|---|---|---|
| 1 | `audit_live.py` returns typed `Finding`s | every existing check, ratchet-ready | — |
| 2 | `detect_repo` + `site_health --no-api` | onboard any repo; HTML-only health, zero spend | — |
| 3 | `site_plan` on `lib/baseline.py` | four lanes + **REGRESSION detection** | — |
| 4 | DataForSEO + GSC + CrUX providers | redirects, broken links, depth, field CWV, cannibalization | — |
| 5 | **§6 gates** (provenance, scope, acceptance) | the safety floor | — |
| 6 | `site-remediation` skill, **Tier A only** | agent does structural fixes | ✅ **Tier A** |
| 7 | Content authoring (needs `content.location`) | agent writes pages | ❌ Tier B, human |
| 8 | `site-audit.reusable.yml` monthly cron | the loop runs itself | per tier |

**Phase 3 is the highest-value stopping point if you stall.** Health + ratchet +
REGRESSION detection, with humans remediating, delivers most of the value at none
of the model risk.

**Gates before authorship — phase 5 precedes 6 deliberately.** Shipping agent
writes against the current 19 gates means shipping unvalidated model claims to
client sites, and auto-merging them means doing it without anyone looking.

---

## 9. Open decisions — yours

1. **Does repo-in replace the DOCX flow or run beside it?** I designed *beside* —
   a second front-end on the same rail, selected per client. Reversible, doesn't
   disturb the five live clients. Replacing makes the intake pollers and
   `client_handoff.py` dead code.
2. **Which model authors, and what is the per-cycle token ceiling?** Needed before
   phase 6. There should be a hard cap, the way `--limit` caps pages.
3. **Does the agent get commit rights, or does it propose a patch a job applies?**
   Proposing a patch keeps CI deterministic and reruns cheap. Recommended.
4. **Tier A auto-merge — all clients, or earn it per client after N clean cycles?**
   I would earn it. Three clean cycles, then enable.
5. **What is the content-revert runbook?** Deploy rollback restores a build, not a
   merged content change. Needs `git revert` + redeploy, documented, before Tier A
   auto-merge goes live.

---

## 10. Hosting and cost

Short version: **the pipeline is nearly free to host. The only real spend is
Claude tokens and the SEO API — and both are small at five clients.**

### The biggest lever: make the engine repo public

Public repos get **unlimited free Actions minutes** on standard runners. Private
repos get 2,000/month free, then **$0.006/min** for Linux 2-core (rates dropped
up to 39% on 2026-01-01).

Your crons alone already exceed the free tier:

| Workflow | Cadence | Runs/mo | ~min each | Total |
|---|---|---|---|---|
| `intake-poll.yml` | hourly | 730 | ~2 | **1,460** |
| `drive-poll.yml` | every 3h | 240 | ~3 | **720** |
| | | | | **~2,180 min** |

That is over the 2,000 free minutes before a single gate run — and it is mostly
waste: each run pays ~60–90s of setup (harden-runner, two checkouts,
setup-python, pip install) for ~10–20s of actual API polling.

**The engine repo is already a sanitized template with no secrets** — README says
so, and the sweep confirms it (Acme / Crestline / Northstar / Meridian /
GrowMinion are consistent pseudonyms; no live IDs or tokens in the tree). Making
it public takes ~2,180 min/month to **$0**, and the workflow headers already note
that `PIPELINE_REPO_TOKEN` becomes unnecessary once it is.

Client repos stay private — their usage (~500–600 min/month across gates, deploy,
and CI for five clients) sits comfortably inside the free tier.

### Full monthly cost, five clients

| Component | Where | Cost |
|---|---|---|
| Crons, intake, CI | GitHub Actions — engine repo **public** | **$0** |
| Gates, preview, deploy | GitHub Actions — client repos (private, free tier) | **$0** |
| Static hosting | Cloudflare Pages (already) | **$0** |
| GSC + CrUX + PageSpeed Insights | Google APIs | **$0** |
| DataForSEO On-Page crawl | pay-as-you-go, $0.000125/page | **$1–13** |
| Claude agent runs | API pay-as-you-go (see below) | **~$5–20** |
| | | **≈ $6–33/mo** |

### The Claude line, specifically

Per-MTok list: **Opus 5** $5 in / $25 out · **Sonnet 5** $3/$15 (intro **$2/$10**
through 2026-08-31) · **Haiku 4.5** $1/$5.

A remediation run over one client's work-list — reading repo files, proposing
edits, writing `proposals.json` — is on the order of 200K input / 30K output.
Rough per-client-per-cycle:

| Model | Estimate |
|---|---|
| Sonnet 5 (intro) | ~$0.70 |
| Sonnet 5 (list) | ~$1.05 |
| Opus 5 | ~$1.75 |

Five clients monthly lands under $10 even on Opus, before caching. **Use prompt
caching** — the client config, house rules, and work-list schema are a stable
prefix, and cache reads run ~0.1× input price. Note the 512-token minimum
cacheable prefix on Opus 5 (1024 on Sonnet 5).

**Default to Sonnet 5 for bulk remediation, Opus 5 for the hard judgment** (§5.4
authoring, ambiguous scope calls). Haiku 4.5 for anything mechanical.

**Pay-as-you-go beats a subscription at this volume.** A Max subscription only
wins if the agent runs near-continuously; at five clients on a monthly cycle,
metered API is cheaper and easier to attribute per client.

### Deployment topology — dashboard on Vercel, worker elsewhere

Once there's a UI for creating projects and configuring pipelines, three tiers
fall out — and the split is forced by one constraint:

> **Vercel functions cap at 300s.** A site crawl, an agent run over a repo, and a
> `npm ci && next build` all blow past that. The long work cannot live in a
> request path.

| Tier | Runs | Why there |
|---|---|---|
| **Dashboard + API** — Vercel | Project CRUD, config, auth, trigger runs, render status/history, receive webhooks | Short requests, great DX, free-to-cheap at this scale |
| **Worker** — Mac mini or droplet | Crawl, `site_health`, `site_plan`, **Claude Code agent runs**, opens the PR | Long-running, needs a real filesystem and a git checkout |
| **Gates + deploy** — GitHub Actions, client repos | 19 gates, preview, deploy, verify, rollback, proof | **Already built, already free, runner isolation is load-bearing.** Do not reimplement this in the dashboard |

**Make the worker pull, never push.** Vercel writes a row to a `jobs` table; the
worker polls for `queued`, claims with `SELECT … FOR UPDATE SKIP LOCKED`, runs,
writes results back. That one decision buys three things:

- **No inbound connection to the worker.** No Cloudflare Tunnel, no Tailscale
  Funnel, no port-forward, no dynamic-DNS — the whole NAT problem disappears, and
  a Mac mini behind home internet becomes viable without exposing anything.
- **Host choice becomes reversible.** Mac mini today, droplet tomorrow, both at
  once during a migration. Nothing in the dashboard changes.
- **Crash safety for free.** A claimed-but-stale job is re-queued by a timeout;
  the same claim/mark pattern `lib/cycle_state.py` already uses.

> **Ladder note:** the dashboard needs Postgres anyway (projects, configs, run
> history). **A `jobs` table in that same database is the queue.** Do not add
> Redis, SQS, or a queue service for tens of jobs a day — add one when a real
> throughput or fan-out requirement shows up, not before.

### Mac mini vs DigitalOcean

The honest split turns on one question: **is this internal tooling, or a product
with customers?**

| | Mac mini | Droplet |
|---|---|---|
| Cost | **$0** (already owned) | $18/mo DO (2 vCPU/4 GB) · ~€3.79 Hetzner CX22, same specs |
| Speed | M-series is genuinely faster than a $18 droplet | Adequate |
| Uptime | Your power, your ISP, your router | Static IP, snapshots, someone else's on-call |
| Ops | You are the ops team | Mostly handled |
| Claude Code | Runs natively, no container gymnastics | Fine in Docker |

- **Internal / agency tooling → Mac mini.** It's free, it's fast, and with the
  pull-based worker there is nothing to expose. This is the right first move.
- **Product with paying customers → droplet.** Not for performance — for the 3am
  page. A customer-facing SLA on home internet is the thing that wakes you up.
  **Hetzner is ~4× cheaper than DigitalOcean for identical specs** if cost is the
  deciding factor; DO wins on managed Postgres sitting next to it and a nicer
  console.

**Recommended path: build the worker as a container and run it on the Mac mini
now.** If it becomes a product, `docker run` it on a droplet and change one
environment variable. You do not have to decide today, and the pull-based design
is what keeps that true.

One caveat for the product branch: **use metered API keys, not a personal
subscription.** A product needs per-customer cost attribution anyway, and
`usage` on each response gives you that for free.

### Two cheap wins while you're here

1. **Collapse the cron setup cost.** Both pollers pay ~60–90s of setup per run for
   seconds of work. Caching the pip install, or dropping `intake-poll` to every
   2h, roughly halves cron minutes — worth doing even after the repo goes public,
   because it also halves latency-to-nothing on quiet days.
2. **Cap the agent per run.** Add a token ceiling the way `--limit` caps pages.
   The API's `task_budget` (beta) makes the model self-moderate against a budget;
   `max_tokens` remains the hard cap.

---

## 11. Fix while you are in here

Found reviewing `@v2.1.0` — all cheap, all worth doing before building on top:

- **Gate count stated three ways.** README says 19, `HOW-IT-WORKS.md:54` says 21,
  the cycle-emit PR body says 18. Actual: 19 modules, 18 wired steps.
- **10 dead doc links** — `docs/modules/*.md` (8), `consuming-the-pipeline.md`,
  `DOCTRINE-GATE-MATRIX.md`. The doctrine matrix held each gate's *why* — the most
  valuable missing file, and the one an agent-authorship contributor most needs.
- **Stale counts.** `MODULES.md:3` claims 55 modules / 47 commands / 327 tests;
  actual 57 / 48 / 354. `ci.yml` says 274. Compute in CI or delete.
- **`pip install -e .` can't run the tests.** Three modules import `docx`, which
  lives only in the `[intake]` extra (which drags the docling ML stack). Add a
  `[test]` extra; the README's setup instructions are currently wrong.
- **`competitors:` is dead config** — declared in the starter, read by zero
  modules. Phase 4 gives it a consumer, or delete it.
