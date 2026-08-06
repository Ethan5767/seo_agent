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
            dry_run: bool) -> int:
    project = checkout(repo, clients_dir, skip_clone)
    print(f"[ok] checkout: {project}")

    check_access(project)

    if dry_run:
        print(f"[DRY RUN] would bootstrap, preflight, scaffold, measure and plan {project}")
        return 0

    if run(["wf-bootstrap-config", str(project), domain]).returncode != 0:
        raise OnboardError("wf-bootstrap-config failed — it refuses rather than write a "
                           "config nothing can load")

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
    args = ap.parse_args()
    try:
        return onboard(args.repo, args.domain, args.clients_dir, args.skip_clone,
                       args.dry_run)
    except OnboardError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
