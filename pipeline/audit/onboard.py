#!/usr/bin/env python3
"""onboard.py — a repo and a URL in, a worklist out.

    wf-onboard <repo> <domain> [--clients-dir DIR] [--skip-clone] [--dry-run]

    wf-onboard acme/roofing-site acmeroofing.com
    wf-onboard ~/clients/acme-roofing-site acmeroofing.com

`repo` is an existing checkout path, an `owner/name` slug, or any git URL.

WHAT THIS IS
------------
The six commands of onboarding, in order, with their exit codes read and
translated. Nothing here does work the individual commands do not already do —
the value is that a partial onboarding reports WHICH step it stopped on and what
a human has to do to unblock it, instead of leaving the operator to remember the
order and interpret an exit 12.

RESUMABLE, BECAUSE STEP 4 NEEDS A HUMAN
---------------------------------------
`wf-bootstrap-config` cannot invent a client's hours, their licence number or
what they refuse to do. It writes TODOs and `wf-preflight` exits 12 until a human
replaces them. That is not a failure mode to design around, it is the interview,
and it is the one step that cannot be automated.

So this command runs as far as it can, prints the blocking step in the
imperative, and exits 1. Fill the TODOs, run the same command again, and it
picks up where it stopped. Every underlying step is idempotent already
(`bootstrap_config` refuses to overwrite, `scaffold_client_docs` skips what
exists, measure/plan rewrite their own cycle folder), so a re-run is safe.

WE ARE A GUEST IN THE CLIENT'S REPO
-----------------------------------
The flow this serves is "the client adds us as a collaborator", so write access
is a fact to CHECK, not to assume. Step 2 asks `gh` what permission we actually
hold and says so out loud. READ is not fatal — every measuring step still works
and the report is still worth delivering — but it means no PR can ever be opened
from this checkout, and finding that out at onboarding beats finding it out
after a remediation run has spent money.

Exit: 0 ready to remediate · 1 stopped on a step a human must clear (re-runnable)
      · 2 usage · 3 the checkout itself failed
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pipeline.lib.common import detect_static_export, framework_family, load_config

# `gh` reports one of these for a repo you can push to. Anything else (READ,
# TRIAGE, or no answer at all) means the PR at the end of the pipeline is not
# available, whatever the rest of the run reports.
WRITE_PERMISSIONS = {"WRITE", "MAINTAIN", "ADMIN"}

# preflight's documented stops, split by who can clear them. The config ones are
# the interview; the site ones are somebody with access to the client's DNS or
# their Cloudflare dashboard.
PREFLIGHT_STOPS = {
    10: "docs/client-config.yml is missing — bootstrap did not run",
    11: "the config is missing required fields",
    12: "the config still has TODOs — this is the interview step",
    13: "the homepage did not return 200",
    14: "Cloudflare Bot Fight Mode is challenging us — turn it off for our UA",
}


class OnboardError(Exception):
    """A step failed in a way a re-run will not fix."""


def run(argv: list, cwd=None, capture=False) -> subprocess.CompletedProcess:
    """Run a step. Output goes to the operator's terminal unless we need to read
    it — an onboarding that hides what its steps printed is an onboarding you
    debug twice.

    Every step is a `wf-*` console script installed beside this interpreter. Put
    that directory on PATH: `.venv/bin/wf-onboard` is the normal way to invoke
    this without activating the venv, and without this the very first step dies
    with FileNotFoundError: 'wf-bootstrap-config'."""
    env = dict(os.environ)
    bindir = str(Path(sys.executable).parent)
    if bindir not in env.get("PATH", "").split(os.pathsep):
        env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    return subprocess.run(argv, cwd=cwd, text=True, env=env,
                          capture_output=capture, check=False)


# ── step 1: the checkout ─────────────────────────────────────────────────────

def repo_slug(repo: str) -> str | None:
    """`owner/name` out of a slug or any git URL, or None if it is a local path."""
    if Path(repo).expanduser().exists():
        return None
    m = re.search(r"[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$", repo)
    if m:
        return m.group(1)
    return repo if re.fullmatch(r"[\w.-]+/[\w.-]+", repo) else None


def checkout(repo: str, clients_dir: Path, skip_clone: bool) -> Path:
    local = Path(repo).expanduser()
    if local.exists():
        if not (local / ".git").is_dir():
            raise OnboardError(f"{local} is not a git checkout")
        return local.resolve()
    slug = repo_slug(repo)
    if not slug:
        raise OnboardError(f"cannot read {repo!r} as a path, an owner/name slug, or a git URL")
    dest = (clients_dir / slug.split("/")[-1]).expanduser()
    if dest.exists():
        return dest.resolve()
    if skip_clone:
        raise OnboardError(f"{dest} does not exist and --skip-clone was given")
    clients_dir.expanduser().mkdir(parents=True, exist_ok=True)
    print(f"[clone] {slug} -> {dest}")
    tool = ["gh", "repo", "clone", slug, str(dest)] if shutil.which("gh") else \
           ["git", "clone", repo if "/" in repo and ":" in repo else
            f"git@github.com:{slug}.git", str(dest)]
    if run(tool).returncode != 0:
        raise OnboardError(f"could not clone {slug} — check the collaborator invite was accepted")
    return dest.resolve()


# ── step 2: what access do we actually hold ──────────────────────────────────

def check_access(project: Path) -> bool:
    """True when we can open a PR from this checkout. A warning, never fatal:
    measuring a repo you can only read is still worth doing."""
    if not shutil.which("gh"):
        print("[warn] access: `gh` not on PATH — cannot verify we can open a PR")
        return False
    r = run(["gh", "repo", "view", "--json", "viewerPermission", "-q", ".viewerPermission"],
            cwd=str(project), capture=True)
    perm = (r.stdout or "").strip()
    if r.returncode != 0 or not perm:
        print("[warn] access: `gh` could not read our permission on this repo "
              "(not authenticated, or the repo is not on GitHub)")
        return False
    if perm in WRITE_PERMISSIONS:
        print(f"[ok] access: {perm} — we can open a PR")
        return True
    print(f"[warn] access: {perm} — we can measure and plan, but NEVER open a PR "
          "from this checkout. Ask for Write before promising a delivery.")
    return False


# ── the scaffold has to be committed, and only this step can do it (B-014) ───

# The six paths onboarding creates. On a T1 client every one is a CREATE that
# `tier_check` refuses: the five docs match no `text_paths` glob, and
# `client-config.yml` is on the deny floor, refused at every tier including T3.
# That floor is correct and must not be relaxed — it is what stops an agent
# raising its own tier. The gap it left is that nothing ever COMMITTED them, so
# the operator met the deny floor as exit 17 on their first PR instead of as an
# instruction here.
SCAFFOLD_PATHS = [
    "docs/client-config.yml",
    "docs/INDEX.md",
    "docs/seo-progress.md",
    "docs/seo-work-log.md",
    "docs/cycle-logs",
    "docs/intake-archive",
]


def _git_out(project: Path, *args) -> str:
    r = subprocess.run(["git", "-C", str(project), *args],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def _git_status(project: Path, paths: list) -> list:
    """`git status --porcelain` lines over `paths`, WITHOUT stripping.

    Separate from _git_out on purpose: porcelain encodes the index in column 1 and
    the worktree in column 2, so ` M file` (modified, unstaged) and `M  file`
    (staged) are different states — and `.strip()` turns the first into the second
    on the first line of the output. That silently made a human's uncommitted edit
    to a scaffold path read as ours to commit.
    """
    r = subprocess.run(["git", "-C", str(project), "status", "--porcelain",
                        "-uall", "--", *paths], capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def commit_scaffold(project: Path) -> None:
    """Commit the onboarding scaffold to the DEFAULT branch, by named pathspec.

    Four constraints, and they are what make a tool committing on your behalf
    something other than a surprise:

      * named pathspec only — never `git add -A`. Whatever else is dirty in this
        checkout is not ours to commit.
      * refuses unless HEAD is the default branch, so this can never land on a
        cycle branch and become part of an agent's PR.
      * refuses if any scaffold path is already TRACKED and modified — that is a
        human's edit to a file we merely happen to name, not a scaffold.
      * commits locally and never pushes. Push stays a human action.

    A no-op when there is nothing to commit, because onboarding is re-runnable and
    the second run must not fail on the first run's success.
    """
    default = _git_out(project, "symbolic-ref", "refs/remotes/origin/HEAD").rsplit("/", 1)[-1]
    if not default:
        default = "main" if _git_out(project, "rev-parse", "--verify", "main") else "master"
    branch = _git_out(project, "rev-parse", "--abbrev-ref", "HEAD")
    if branch != default:
        print(f"[warn] scaffold: on branch '{branch}', not the default branch "
              f"('{default}') — NOT committing. The scaffold belongs on the default "
              f"branch in its own commit; `tier_check` refuses these six paths on a "
              f"cycle branch (B-014). Check out {default} and re-run.")
        return

    present = [p for p in SCAFFOLD_PATHS if (project / p).exists()]
    if not present:
        return

    # Over just our paths. An UNTRACKED path (`??`) is one we just wrote and is
    # ours to commit. A TRACKED path with any worktree change is somebody's edit to
    # a file we merely happen to name — most often the operator resolving the
    # interview TODOs in client-config.yml — and committing that for them would put
    # their unreviewed work in a commit with our message on it.
    status = _git_status(project, present)
    theirs = [ln[3:] for ln in status if not ln.startswith("??")]
    if theirs:
        print(f"[warn] scaffold: NOT committing — these carry changes that are not "
              f"this run's to commit: {', '.join(theirs)}. Commit or revert them "
              f"yourself, then re-run.")
        return
    if not status:
        print("[ok] scaffold: already committed")
        return

    if run(["git", "add", "--", *present], cwd=str(project)).returncode != 0:
        raise OnboardError("could not stage the onboarding scaffold")
    slug = _git_out(project, "rev-parse", "--show-toplevel").rsplit("/", 1)[-1]
    msg = f"docs: onboard {slug} — client config and pipeline docs"
    if run(["git", "commit", "-m", msg, "--", *present], cwd=str(project)).returncode != 0:
        raise OnboardError("could not commit the onboarding scaffold")
    print(f"[ok] scaffold: committed {len(present)} path(s) to {default} — NOT pushed. "
          f"`git push origin {default}` when you are ready.")


# ── step 6: the precondition the gate suite quietly depends on ───────────────

def check_static_export(project: Path) -> None:
    """v3 §6. orphan_check and parity_check derive routes from the built HTML
    tree. A site that does not emit one makes both gates scan nothing and report
    green, which is worse than not running them."""
    try:
        cfg = load_config(str(project))
    except Exception as e:                       # a config we cannot read is step 5's problem
        print(f"[warn] static export: cannot read the config ({e})")
        return
    raw = ((cfg.get("repo") or {}).get("framework")) or ""
    verdict = detect_static_export(project, framework_family(raw), raw)
    if verdict is True:
        print("[ok] static export: this repo builds a route tree — the full gate suite applies")
    elif verdict is False:
        print("[warn] static export: NO route tree. orphan_check and parity_check will scan "
              "nothing and report green. Onboard at T1 with a reduced gate set, or decline "
              "until the client statically exports (v3 §6).")
    else:
        print("[warn] static export: cannot tell from the config. Build the repo once and "
              "check for an index.html route tree before promising the full gate suite.")


# ── the run ──────────────────────────────────────────────────────────────────

def onboard(repo: str, domain: str, clients_dir: Path, skip_clone: bool,
            dry_run: bool, tier: int = 1, content_location: str = "",
            content_registry=None) -> int:
    # `tier` arrives as None when the operator did not type --tier at all. Keeping
    # that distinct from an explicit `--tier 1` is what lets the mismatch check
    # below stay quiet on an ordinary re-run and speak up on an ignored request.
    requested_tier, tier = tier, (tier or 1)
    project = checkout(repo, clients_dir, skip_clone)
    print(f"[ok] checkout: {project}")

    check_access(project)

    if dry_run:
        print(f"[DRY RUN] would bootstrap (tier {tier}), preflight, scaffold, commit, "
              f"measure and plan {project}")
        return 0

    # The tier is declared HERE, before the scaffold commit below, so one commit
    # carries the finished config. Writing tier 1 and amending it later would put
    # a raise in a second commit that nobody reviews as a raise.
    #
    # `--add-tier` is what makes the tier land on a config that ALREADY exists —
    # without it `wf-bootstrap-config` prints "Config already exists" and exits 0,
    # so `wf-onboard --tier 3` on an onboarded client silently kept the old tier
    # and reported success (B-032). It is inert on a fresh config, where the tier
    # comes from `tier_block` on the write path instead.
    bootstrap = ["wf-bootstrap-config", str(project), domain,
                 "--tier", str(tier), "--add-tier"]
    if content_location:
        bootstrap += ["--content-location", content_location]
    for reg in content_registry or []:
        bootstrap += ["--content-registry", reg]
    code = run(bootstrap).returncode
    if code == 4:
        print("\n[STOPPED] the tier could not be written as asked — read the refusal "
              "above. Nothing was written; re-run with the fields it names.")
        return 1
    if code != 0:
        raise OnboardError("wf-bootstrap-config failed — it refuses rather than write a "
                           "config nothing can load")

    # A tier that was ASKED FOR and not applied must never reach the [READY] banner
    # (B-032). `add_tier` is append-only: it declines an existing `tier:` and returns
    # 0, so raising a declared tier is deliberately a human edit. That is a fine
    # model; reporting a clean run while the request was dropped is not. Same rule
    # the gates follow — a step that did not do the thing must not read as success.
    if requested_tier is not None:
        on_disk = load_config(str(project)).get("tier")
        if on_disk != requested_tier:
            print(f"\n[STOPPED] you asked for tier {requested_tier}, but "
                  f"docs/client-config.yml still declares tier {on_disk}. The tier was "
                  f"NOT changed.\n"
                  f"  Why     `wf-bootstrap-config --add-tier` appends a MISSING tier "
                  f"block; it never rewrites one that is already declared.\n"
                  f"  Fix     edit `tier:` in {project}/docs/client-config.yml by hand, "
                  f"commit it to the default branch, then re-run this command.\n"
                  f"  Note    that commit is the human declaration the tier model rests "
                  f"on (v3 §2) — the agent can never raise its own tier.",
                  file=sys.stderr)
            return 1

    code = run(["wf-preflight", str(project)]).returncode
    if code:
        reason = PREFLIGHT_STOPS.get(code, f"wf-preflight exited {code}")
        print(f"\n[STOPPED] {reason}")
        print(f"  Edit    {project}/docs/client-config.yml")
        print("  Then    re-run this exact command — it resumes from here.")
        if code == 12:
            print("  Note    trust_signals is the block that matters most: "
                  "claim_provenance_check treats it as the corpus, so a rating you "
                  "never entered is a rating the agent can never write.")
        return 1

    if run(["wf-client-profile", str(project)]).returncode == 5:
        print("\n[STOPPED] the config parses but does not cohere — wf-client-profile "
              "reported an ERROR above. Fix it and re-run.")
        return 1

    check_static_export(project)

    slug = load_config(str(project)).get("client") or project.name
    if run(["wf-scaffold-client-docs", str(project), "--slug", str(slug)]).returncode != 0:
        raise OnboardError("wf-scaffold-client-docs failed")

    # Before measure, so the cycle artifacts measure/plan write are the ONLY dirty
    # paths left when the operator reaches the Git screen. B-014.
    commit_scaffold(project)

    if run(["wf-site-health", "--project", str(project)]).returncode >= 2:
        print("\n[STOPPED] the site could not be measured — wf-site-health refused above. "
              "Nothing downstream can run without findings.json.")
        return 1

    # 0 = no findings at all, 1 = a worklist was written. Both are a finished
    # onboarding; only a 2 (nothing measured, or unparseable findings) is not.
    if run(["wf-site-plan", "--project", str(project)]).returncode >= 2:
        print("\n[STOPPED] wf-site-plan could not read the findings it was given.")
        return 1

    print(f"\n[READY] {project}")
    print(f"  Report    {project}/docs/audit/<cycle>/report.md")
    print(f"  Worklist  {project}/docs/audit/<cycle>/worklist.json")
    print(f"  Next      wf-site-remediate --project {project} --max-items 1 --dry-run")
    # The one step onboarding cannot do for itself, said at the end of every run
    # rather than once in ADMIN-CHECKLIST. Without it the client's first PR fails
    # at the pipeline checkout and reads as a broken pipeline, not a missing key.
    print("\n  [HUMAN] Add the `SEO_AGENT` secret to the CLIENT repo before its first PR.")
    print("          Settings -> Secrets and variables -> Actions -> New repository secret")
    print("          Name  seo_agent   (GitHub stores it as SEO_AGENT)")
    print("          Value a FINE-GRAINED PAT: only Ethan5767/seo_agent, Contents Read-only.")
    print("          Why   the gates live in a private repo, and a client repo's GITHUB_TOKEN")
    print("                cannot read a different private repo — every gate fails to start.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-onboard",
        description="Take a client repo and a domain to a measured worklist.")
    ap.add_argument("repo", help="checkout path, owner/name slug, or git URL")
    ap.add_argument("domain", help="the live site, e.g. acmeroofing.com")
    ap.add_argument("--clients-dir", type=Path, default=Path("~/clients"),
                    help="where to clone (default: ~/clients, what wf-dashboard scans)")
    ap.add_argument("--skip-clone", action="store_true",
                    help="refuse to clone; the checkout must already exist")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve the checkout and report access, write nothing")
    # default=None, not 1: an omitted --tier and an explicit `--tier 1` must stay
    # distinguishable, or the B-032 mismatch check fires on every ordinary re-run
    # of a T2/T3 client. `onboard()` resolves None to 1.
    ap.add_argument("--tier", type=int, choices=(1, 2, 3), default=None,
                    help="the agent's authority over this repo (default: 1, copy only). "
                         "T2 requires --content-location and --content-registry. "
                         "Raising a tier that is already declared is a human edit to "
                         "docs/client-config.yml — this flag will not do it for you.")
    ap.add_argument("--content-location", default="",
                    help="T2+: the directory the agent may CREATE pages under")
    ap.add_argument("--content-registry", action="append", default=[], metavar="PATH",
                    help="T2+: the nav/data file a new page must be wired into "
                         "(repeatable), or orphan_check refuses the PR")
    args = ap.parse_args()
    try:
        return onboard(args.repo, args.domain, args.clients_dir, args.skip_clone,
                       args.dry_run, args.tier, args.content_location,
                       args.content_registry)
    except OnboardError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
