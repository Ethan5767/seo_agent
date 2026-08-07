# Admin Checklist — human-only setup

Things the pipeline cannot do for itself. Update this file in the same commit
as any change that alters what a human must configure by hand (`CLAUDE.md` §2).

Everything below is verified against the code. Every secret named here appears
in `.github/workflows/*.reusable.yml` or `pipeline/`; nothing is aspirational.

---

## 1. Per client repo — secrets

Set under Settings → Secrets and variables → Actions on the **client's** repo.
The thin callers pass them through with `secrets: inherit`.

| Secret | Required by | Without it |
|---|---|---|
| `PIPELINE_REPO_TOKEN` | quality-gate, preview, deploy, seo-health | **Every gate fails to start.** See §1a. |
| `CLOUDFLARE_API_TOKEN` | preview, deploy | Deploy and preview cannot run |
| `CLOUDFLARE_ACCOUNT_ID` | preview, deploy | Same |
| `CLOUDFLARE_PAGES_PROJECT` | preview, deploy | Same |
| `INDEXNOW_KEY` | deploy (optional) | IndexNow submit no-ops; rail stays green |
| `CHAT_WEBHOOK_URL` | deploy, preview, seo-health (optional) | Notifications skipped; run logs the link |

### 1a. `PIPELINE_REPO_TOKEN` — the one that blocks everything

A GitHub PAT with read access to `Ethan5767/seo_agent`, stored as a secret on
each client repo.

Every thin caller does two checkouts: the client's own code, then this engine
repo at a pinned tag so the `wf-*` gates are on `PATH`. A client repo's
`GITHUB_TOKEN` is scoped to that repo only and cannot read a *different private*
repo. All four reusable workflows declare it `required: false` and fall back:

```yaml
# quality-gate.reusable.yml:176
token: ${{ secrets.PIPELINE_REPO_TOKEN || github.token }}
```

That fallback only works once `seo_agent` is **public**. While it is private,
the PAT is mandatory or the gates cannot check out the code that runs them.

**A human collaborator grant is not Actions access.** Being a collaborator lets
*you* clone the repo. It grants nothing to a client repo's runner — different
identity entirely. (`CLAUDE.md` sharp edge #3.)

This secret becomes unnecessary the moment `seo_agent` goes public, which v3
made viable: both cron pollers and their ~2,180 Actions minutes/month are gone.

---

## 2. Per client repo — one-time setup

| # | Item | Why it bites | Status |
|---|---|---|---|
| 1 | Thin callers copied from `.github/examples/`, pinned to an exact tag (`@v3.0.0`, never `@main`, never `@v3`) | A mutable ref means the thing guarding production can change without a PR. `tests/test_pipeline_pin.py` enforces this here | ☐ |
| 2 | `docs/gate-baseline.json` recorded and committed to the **client's** repo before their first PR: `wf-gate-baseline --project <repo> --out docs/gate-baseline.json` | Missing = the gates run BARE and every piece of inherited debt reads as blocking. The workflow warns rather than failing, which is deliberate but is not "handled" (B-007) | ☐ |
| 3 | Static export verified — `wf-onboard` reports the verdict | `orphan_check` and `parity_check` derive routes from the built HTML tree. No tree = both gates scan nothing and report **green**, which is worse than not running. `None` means "cannot tell", not "fine" | ☐ |
| 4 | `docs/client-config.yml` written by `wf-bootstrap-config` (writes `tier: 1`) | T2/T3 exist in code but are unreachable until a human raises the tier in a human PR. That is the enforcement | ☐ |
| 5 | `quality-gate` set as a **required status check** on the default branch | Red gate = un-clickable Merge = production blocked by construction. Without it a red gate is only advisory | ☐ |
| 6 | Branch protection on the default branch | **Cannot be enabled on GitHub Free for a private repo.** The gate reports but cannot block. Needs a paid plan, or a public client repo | ☐ |
| 7 | Cloudflare Pages project created in the **client's own** Cloudflare account | Model A: the client repo is the single source of truth, host swappable | ☐ |
| 8 | `seo-health.yml` thin caller written by hand | `seo-health.reusable.yml` exists here; **no example caller does.** Copy the shape from `preview.yml` | ☐ |

---

## 3. Operator workstation / container

| Item | Notes |
|---|---|
| `ANTHROPIC_API_KEY` in the environment | The only thing the container needs baked in from you. `wf-site-remediate` drives Claude Code with it |
| `git` and `gh` config mounted into the container | The image bakes in no credentials at all (`Dockerfile`) |
| `gh auth status` working against the client repo | Onboard clones and remediate pushes with it |

---

## 4. Optional measurement credentials

`wf-site-health` runs without any of these. Each provider returns a **named
skip** when its credential is absent, so a silent zero can never look like a
clean site. Read the status string on the first real run, not the finding count.

| Env var | Enables | Flag |
|---|---|---|
| `CRUX_API_KEY` | Field Core Web Vitals from CrUX | `--with-crux` |
| `GSC_ACCESS_TOKEN` (+ optional `GSC_SITE_URL`) | Impressions, CTR, cannibalization | `--with-gsc` |
| `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` | Crawl-wide on-page: broken pages, click depth, duplicate meta | `--with-dataforseo` |
| `BRIGHTDATA_API_KEY` / `BRIGHTDATA_SERP_ZONE` | Rank and absence over the config's `seed_queries` | `--with-serp` |

**Filling `seed_queries`.** `--with-serp` measures exactly the queries in the
client's `docs/client-config.yml` and nothing else, so that list *is* the
measurement. `wf-seed-queries --project <checkout>` crawls the site's own page
titles and h1s, expands them, drops navigational terms, and prints a YAML block
to paste. Review before committing: every entry is one paid request per cycle,
and because `Finding.context` is fingerprinted, changing the list later re-files
every SERP finding as NEW and makes RESOLVED unreachable. The queries are
grounded in the site's vocabulary but **not volume-ranked** — a query nobody
searches produces a real `serp.absent` finding that reads like a site defect,
which is why the human paste step exists.

**Live status, 2026-08-07.** Two of the four have now run against their real
APIs; the flag names above were wrong (`--crux` for `--with-crux`) until this
was checked against `measure.py`, and DataForSEO was described as SERP data,
which is the one thing it does not do.

| Provider | Status |
|---|---|
| CrUX | **Ran live.** On `www.leeserie.com`: `no field data: CrUX has no record (too little traffic)` — a fact about Google's dataset, not the site. |
| Bright Data SERP | **Ran live.** `partial: 4/5 queries measured`. Two defects only the real payload exposed: `global_rank` counts SERP features so a #1 result read as rank 4, and **B-019**, page-two findings can never fire because Google returns one page of organic results. |
| DataForSEO | **Blocked, not broken.** Credentials authenticate (`20000 Ok`, $51 balance) but every billable endpoint returns `40104 Please verify your account before using the API`. One-time verification at app.dataforseo.com. |
| Search Console | **Never run.** No client has granted access — see below. |

### Getting Search Console access (human, per client)

GSC returns data only for a property someone has verified and shared. You
cannot add a client's domain to your own account and read it.

1. The client opens Search Console → **Settings → Users and permissions** on
   their existing verified property.
2. They add your Google account (or a **service account** email) as a user.
   **Restricted** is sufficient; the API scope needed is `webmasters.readonly`.
3. `GSC_SITE_URL` defaults to `sc-domain:<domain>`. If their property is a URL
   prefix rather than a domain property, set it explicitly.

⚠️ **`GSC_ACCESS_TOKEN` is an OAuth *access* token, so it expires in about an
hour.** It is fine for an attended run and useless for an unattended one —
there is no refresh flow in `providers.py`, which reads the variable and
nothing else. A service account with a locally-minted token is the real answer
if GSC is ever wanted on a schedule. Recorded here rather than in the code
because it is a setup decision, not a bug.

---

## Removed in v3

These were on this checklist and are now dead. Nothing outside `docs/`
references any of them:

```
$ grep -rln "DISCORD_BOT_TOKEN\|DRIVE_\|CLIENT_REPOS_TOKEN" \
    --include="*.yml" --include="*.py" --include="*.sh" .
(no output)
```

`DISCORD_BOT_TOKEN`, `DRIVE_*`, `PIPELINE_DRIVE_PARENT_FOLDER_ID` and
`CLIENT_REPOS_TOKEN` all belonged to the intake rail (`pipeline/intake`,
`pipeline/generate`, the two cron pollers), deleted in v3. Do not mint them.
See `SITE-AUDIT-PIPELINE.md` §3.
