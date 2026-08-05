#!/usr/bin/env python3
"""pipeline.intake.client_handoff — the HANDOFF stage: retrieved DOCX -> a PR
on the client repo.

WHY THIS EXISTS (the operator's decision, 2026-08)
------------------------------------------
Until now the pipeline STOPPED at an artifact: drive-poll retrieved the team's
DOCX, uploaded it as a run artifact, and waited for a human to move it into a
cycle. Nobody owned that last hop, and 82 delivered pages sat in limbo because
of it. the operator's ruling closes the hop:

    "pipeline opens a PR on the client repo — PR not direct push, so a human
     still approves before deploy... that's the one decision that fixes this
     whole month's class of failure."

THE SPIRIT OF `drive-poll.yml`'s OLD "NO CROSS-REPO WRITE" HEADER IS PRESERVED:

    * NEVER pushes to a client's default branch. All writes land on
      `cycle/<slug>-<YYYY-MM>`.
    * NEVER merges. the operator's merge stays the gate to production.
    * The whole path activates ONLY when the `CLIENT_REPOS_TOKEN` secret
      exists — a fine-grained PAT scoped to the five client repos and nothing
      else (see docs/ADMIN-CHECKLIST.md for the exact mint spec). Absent
      the secret, drive-poll behaves exactly as before: artifact only.

WHAT ONE RUN DOES, per client with retrieved docs
-------------------------------------------------
    1. resolve the client repo from `repo:` in config/drive-intake.yml
    2. create `cycle/<slug>-<YYYY-MM>` from the repo's default branch
       (or reuse it — the branch is the cycle's visible home for the month)
    3. commit each DOCX to `docs/intake/<YYYY-MM>/<file>` on that branch via
       the GitHub contents API — no full clone for the write path. Idempotent:
       an unchanged file (same git blob sha) is never re-committed.
    4. shallow-clone the client repo (depth 1, read) so `wf-preflight-docx`
       can run against that client's own config and banned-phrases list
    5. open ONE PR per client per month (`content intake: <YYYY-MM> — <n>
       docs`) whose body is the pre-flight summary. Re-runs UPDATE that PR.
    6. `workflow_dispatch` the client repo's cycle-emit.yml ON THE CYCLE
       BRANCH (so the DOCX is present in its checkout and its emitted pages
       land on the SAME branch, ripening the intake PR into the content PR).
       A repo without cycle-emit.yml gets a warning, never a failure.

Every GitHub API failure (401/403/404/422) degrades with an actionable
message; one client failing never blocks the others.

TESTABILITY. The API layer is a thin injectable transport; branch naming,
roster mapping, blob-sha idempotency and action planning are pure functions
covered offline by tests/test_client_handoff.py. No test ever talks to a real
client repo.

Exit codes
----------
    0  every client handled (including "nothing to do")
    1  at least one client failed hard (bad token, API refusal on the writes)
    2  usage / configuration error (no token, unreadable roster, bad cycle)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import yaml

TOKEN_ENV = "CLIENT_REPOS_TOKEN"
API_BASE = "https://api.github.com"
CYCLE_EMIT_WORKFLOW = "cycle-emit.yml"
INTAKE_PREFIX = "docs/intake"

_CYCLE_RE = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

#: intake-dir children that are never client slugs. `unrouted/` and
#: `inactive/<slug>/` are link-intake's triage bins — a human decides those.
_NON_CLIENT_DIRS = frozenset({"unrouted", "inactive"})


class HandoffError(RuntimeError):
    """A defect the operator can act on. The message IS the fix."""


# ---------------------------------------------------------------------------
# Pure functions (unit-tested offline)
# ---------------------------------------------------------------------------

def current_cycle() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def cycle_branch(slug: str, cycle: str) -> str:
    """`cycle/<slug>-<YYYY-MM>` — MUST match cycle-emit.reusable.yml's
    `BRANCH="cycle/${SLUG}-${CYCLE_ID}"`, so a dispatched emit run pushes onto
    the same branch this module opened the intake PR from."""
    if not _SLUG_RE.match(slug or ""):
        raise HandoffError(f"invalid client slug {slug!r} (want lowercase kebab-case)")
    if not _CYCLE_RE.match(cycle or ""):
        raise HandoffError(f"invalid cycle {cycle!r} (want YYYY-MM, e.g. 2026-08)")
    return f"cycle/{slug}-{cycle}"


def repo_for(clients: list[dict], slug: str) -> str:
    """slug -> `owner/repo` from the roster's `repo:` field."""
    for entry in clients:
        if entry.get("slug") == slug:
            repo = str(entry.get("repo") or "").strip()
            if not repo:
                raise HandoffError(
                    f"client {slug!r} has no `repo:` in config/drive-intake.yml — add "
                    "`repo: your-org/<client-repo>` to its roster entry (and to "
                    "meridian-seo-ops/clients.yml so regeneration keeps it).")
            if not _REPO_RE.match(repo):
                raise HandoffError(f"client {slug!r} repo {repo!r} is not `owner/repo`")
            return repo
    raise HandoffError(f"client {slug!r} is not in the roster")


def git_blob_sha(data: bytes) -> str:
    """The sha git/GitHub assigns this exact content (`git hash-object`).

    This is the idempotency key: the contents API reports each existing file's
    blob sha, so an unchanged DOCX is recognised WITHOUT downloading anything
    and never re-committed on a re-run."""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def intake_dest(cycle: str, filename: str) -> str:
    """Where a retrieved DOCX lands in the client repo."""
    name = PurePosixPath(filename.replace("\\", "/")).name
    if not name or name.startswith("."):
        raise HandoffError(f"unusable intake filename {filename!r}")
    return f"{INTAKE_PREFIX}/{cycle}/{name}"


def plan_actions(local: dict[str, str], remote: dict[str, str]) -> dict[str, str]:
    """{filename: blob-sha} x2 -> {filename: create|update|skip}. Pure."""
    out: dict[str, str] = {}
    for name, sha in local.items():
        if name not in remote:
            out[name] = "create"
        elif remote[name] == sha:
            out[name] = "skip"
        else:
            out[name] = "update"
    return out


def pr_title(cycle: str, n_docs: int) -> str:
    return f"content intake: {cycle} — {n_docs} doc{'' if n_docs == 1 else 's'}"


# ---------------------------------------------------------------------------
# GitHub API client (transport injectable — tests never touch the network)
# ---------------------------------------------------------------------------

Transport = Callable[[str, str, dict, bytes | None], tuple[int, Any]]


def _urllib_transport(method: str, url: str, headers: dict,
                      body: bytes | None) -> tuple[int, Any]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = {"message": raw.decode("utf-8", "replace")[:400]}
        return exc.code, payload
    except urllib.error.URLError as exc:
        raise HandoffError(f"cannot reach api.github.com: {exc.reason}") from exc


class GitHubApi:
    def __init__(self, token: str, transport: Transport | None = None):
        self._token = token
        self._transport = transport or _urllib_transport

    def request(self, method: str, path: str,
                payload: dict | None = None) -> tuple[int, Any]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "seo-content-pipeline-handoff",
        }
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        return self._transport(method, f"{API_BASE}{path}", headers, body)

    # -- reads ---------------------------------------------------------------

    def default_branch(self, repo: str) -> str:
        status, data = self.request("GET", f"/repos/{repo}")
        if status == 200 and isinstance(data, dict) and data.get("default_branch"):
            return str(data["default_branch"])
        raise HandoffError(
            f"cannot read {repo} (HTTP {status}: {_msg(data)}). The "
            f"{TOKEN_ENV} PAT must include this repo with Contents read/write — "
            "see docs/ADMIN-CHECKLIST.md for the mint spec.")

    def branch_sha(self, repo: str, branch: str) -> str | None:
        status, data = self.request("GET", f"/repos/{repo}/git/ref/heads/{branch}")
        if status == 200 and isinstance(data, dict):
            return data.get("object", {}).get("sha")
        if status == 404:
            return None
        raise HandoffError(f"cannot read ref {branch} on {repo} (HTTP {status}: {_msg(data)})")

    def dir_listing(self, repo: str, path: str, ref: str) -> dict[str, str]:
        """{filename: blob-sha} for one directory. 404 = empty (no dir yet)."""
        status, data = self.request("GET", f"/repos/{repo}/contents/{path}?ref={ref}")
        if status == 404:
            return {}
        if status == 200 and isinstance(data, list):
            return {str(e["name"]): str(e["sha"]) for e in data
                    if isinstance(e, dict) and e.get("type") == "file"}
        raise HandoffError(f"cannot list {repo}/{path}@{ref} (HTTP {status}: {_msg(data)})")

    # -- writes (branch only — NEVER the default branch) ----------------------

    def ensure_branch(self, repo: str, branch: str, from_sha: str) -> str:
        if self.branch_sha(repo, branch):
            return "exists"
        status, data = self.request(
            "POST", f"/repos/{repo}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": from_sha})
        if status == 201:
            return "created"
        if status == 422 and "already exists" in _msg(data).lower():
            return "exists"          # raced with a parallel run — fine
        raise HandoffError(
            f"cannot create branch {branch} on {repo} (HTTP {status}: {_msg(data)}). "
            f"The {TOKEN_ENV} PAT needs Contents: read and write on this repo.")

    def put_file(self, repo: str, path: str, branch: str, content: bytes,
                 message: str, sha: str | None = None) -> None:
        payload: dict[str, Any] = {
            "message": message, "branch": branch,
            "content": base64.b64encode(content).decode("ascii"),
        }
        if sha:
            payload["sha"] = sha
        status, data = self.request("PUT", f"/repos/{repo}/contents/{path}", payload)
        if status not in (200, 201):
            raise HandoffError(
                f"cannot commit {path} to {repo}@{branch} (HTTP {status}: {_msg(data)})")

    def find_open_pr(self, repo: str, branch: str) -> dict | None:
        owner = repo.split("/", 1)[0]
        status, data = self.request(
            "GET", f"/repos/{repo}/pulls?state=open&head={owner}:{branch}")
        if status == 200 and isinstance(data, list) and data:
            return data[0]
        if status in (200, 404):
            return None
        raise HandoffError(f"cannot list PRs on {repo} (HTTP {status}: {_msg(data)})")

    def open_or_update_pr(self, repo: str, branch: str, base: str,
                          title: str, body: str) -> tuple[str, str]:
        """-> (action, url). Idempotent: one PR per client per month."""
        existing = self.find_open_pr(repo, branch)
        if existing:
            number = existing["number"]
            status, data = self.request(
                "PATCH", f"/repos/{repo}/pulls/{number}",
                {"title": title, "body": body})
            if status != 200:
                raise HandoffError(
                    f"cannot update PR #{number} on {repo} (HTTP {status}: {_msg(data)})")
            return "updated", str(existing.get("html_url", f"{repo}#{number}"))
        status, data = self.request(
            "POST", f"/repos/{repo}/pulls",
            {"title": title, "head": branch, "base": base, "body": body})
        if status == 201 and isinstance(data, dict):
            return "opened", str(data.get("html_url", ""))
        raise HandoffError(
            f"cannot open the PR on {repo} (HTTP {status}: {_msg(data)}). "
            f"The {TOKEN_ENV} PAT needs Pull requests: read and write.")

    def dispatch_cycle_emit(self, repo: str, ref: str, source_doc: str) -> bool:
        """Fire the client's cycle-emit.yml ON THE CYCLE BRANCH with dry_run
        false. Tolerates a repo that has not installed the caller yet (404) and
        an out-of-date caller (422) — both warn, neither fails the handoff."""
        status, data = self.request(
            "POST",
            f"/repos/{repo}/actions/workflows/{CYCLE_EMIT_WORKFLOW}/dispatches",
            {"ref": ref, "inputs": {"source_doc": source_doc, "dry_run": "false"}})
        if status == 204:
            return True
        if status == 404:
            print(f"WARN: {repo} has no {CYCLE_EMIT_WORKFLOW} — cycle-emit not "
                  "installed yet. Copy .github/examples/cycle-emit.yml into the "
                  "client repo to close this gap; the intake PR stands either way.")
            return False
        if status in (403, 422):
            print(f"WARN: could not dispatch {CYCLE_EMIT_WORKFLOW} on {repo} "
                  f"(HTTP {status}: {_msg(data)}). If 403, add Actions: read and "
                  f"write to the {TOKEN_ENV} PAT; if 422, the client's caller "
                  "predates the source_doc/dry_run inputs — update it from "
                  ".github/examples/cycle-emit.yml. The intake PR stands either way.")
            return False
        raise HandoffError(
            f"dispatching {CYCLE_EMIT_WORKFLOW} on {repo} failed (HTTP {status}: {_msg(data)})")


def _msg(data: Any) -> str:
    if isinstance(data, dict) and data.get("message"):
        return str(data["message"])
    return "no message"


# ---------------------------------------------------------------------------
# Pre-flight summary (the PR body)
# ---------------------------------------------------------------------------

def preflight_doc(docx: Path, project_dir: Path | None) -> dict:
    """Run the emitter's own pre-flight against the client's own config.

    Degrades to an honest 'not pre-flighted' record instead of failing the
    handoff: the DOCX must reach the PR even when pre-flight cannot run."""
    if project_dir is None or not (project_dir / "docs").is_dir():
        return {"name": docx.name, "error":
                "client repo checkout unavailable — not pre-flighted (the DOCX "
                "is still committed; run wf-preflight-docx locally)"}
    try:
        from pipeline.intake.preflight_docx import _dedupe, preflight
        reports, _rules = preflight(str(docx), str(project_dir))
    except Exception as exc:                       # noqa: BLE001 — degrade, never drop the doc
        return {"name": docx.name, "error": f"pre-flight failed: {exc}"}
    blocking = [f for r in reports for f in _dedupe(r.blocking)]
    curate = [f for r in reports for f in _dedupe(r.curate)]
    top = Counter((f.code, f.offending) for f in blocking).most_common(5)
    return {
        "name": docx.name,
        "pages": len(reports),
        "blocking": len(blocking),
        "curate": len(curate),
        "ready": [r.name for r in reports if r.ready],
        "pages_blocked": [r.name for r in reports if r.blocking],
        "top_blockers": [
            {"code": code, "offending": offending, "count": count,
             "fix": next((f.fix for f in blocking
                          if (f.code, f.offending) == (code, offending)), "")}
            for (code, offending), count in top],
    }


def render_pr_body(slug: str, cycle: str, branch: str, docs: list[dict],
                   run_url: str = "") -> str:
    L: list[str] = []
    L.append(f"## Content intake {cycle} — {slug}")
    L.append("")
    L.append("Opened automatically by the drive-poll handoff stage. This PR is the "
             "cycle's home for the month: the team's handoff DOCX lands here first, "
             "and when the content is clean, cycle-emit pushes the emitted pages to "
             f"this same `{branch}` branch so the diff ripens in place.")
    L.append("")
    L.append("| Document | Pages | Blocking | Curate |")
    L.append("|---|---:|---:|---:|")
    for d in docs:
        if "error" in d:
            L.append(f"| `{d['name']}` | — | — | — |")
        else:
            L.append(f"| `{d['name']}` | {d['pages']} | **{d['blocking']}** | {d['curate']} |")
    L.append("")
    for d in docs:
        if "error" in d:
            L.append(f"> `{d['name']}`: {d['error']}")
            L.append("")
    blockers = [d for d in docs if d.get("blocking")]
    if blockers:
        L.append("### Top blockers (the emitter WILL refuse these pages)")
        L.append("")
        for d in blockers:
            L.append(f"**`{d['name']}`** — {d['blocking']} blocking finding(s) across "
                     f"{len(d.get('pages_blocked', []))} page(s):")
            L.append("")
            for b in d.get("top_blockers", []):
                L.append(f"- `{b['code']}` ×{b['count']} — \"{b['offending']}\". {b['fix']}")
            L.append("")
    ready = [d for d in docs if "error" not in d and not d.get("blocking")]
    if ready and not blockers:
        L.append("Pre-flight found no blocking findings. cycle-emit has been "
                 "dispatched against this branch; its result lands here.")
        L.append("")
    L.append("### What happens next")
    L.append("")
    L.append("- **Blocking findings** stop pages at emit; fix the source doc in Drive "
             "and the next poll updates this PR.")
    L.append("- **Nothing here is live until a human merges.** This automation never "
             "pushes to the default branch, never merges, never deploys.")
    if run_url:
        L.append("")
        L.append(f"Run: {run_url}")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Shallow read-only clone (for pre-flight's client config only)
# ---------------------------------------------------------------------------

def clone_repo(repo: str, token: str, dest: Path) -> Path | None:
    """Depth-1 read clone. The auth header rides the invocation via `-c`, so it
    is never written into the clone's .git/config. Failure degrades to None."""
    if (dest / ".git").is_dir():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    b64 = base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
    cmd = ["git", "-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {b64}",
           "clone", "--depth", "1", "--quiet",
           f"https://github.com/{repo}", str(dest)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"WARN: shallow clone of {repo} failed ({exc}) — pre-flight will be skipped.")
        return None
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-1:] or ["no stderr"]
        print(f"WARN: shallow clone of {repo} failed ({tail[0]}) — pre-flight will be skipped.")
        return None
    return dest


# ---------------------------------------------------------------------------
# Per-client handoff
# ---------------------------------------------------------------------------

def handoff_client(api: GitHubApi, slug: str, repo: str, cycle: str,
                   docx_paths: list[Path], project_dir: Path | None,
                   dry_run: bool = False, dispatch: bool = True,
                   run_url: str = "") -> dict:
    branch = cycle_branch(slug, cycle)
    base = api.default_branch(repo)
    base_sha = api.branch_sha(repo, base)
    if not base_sha:
        raise HandoffError(f"{repo} default branch {base!r} has no readable head")

    if dry_run:
        print(f"DRY-RUN: {slug} -> {repo} branch {branch}: would commit "
              f"{len(docx_paths)} doc(s) and open/update the intake PR.")
        return {"slug": slug, "dry_run": True}

    created = api.ensure_branch(repo, branch, base_sha)
    print(f"HANDOFF: {slug} branch {branch} ({created}) on {repo}")

    remote = api.dir_listing(repo, f"{INTAKE_PREFIX}/{cycle}", branch)
    local: dict[str, tuple[Path, bytes, str]] = {}
    for p in docx_paths:
        data = p.read_bytes()
        dest_name = PurePosixPath(intake_dest(cycle, p.name)).name
        local[dest_name] = (p, data, git_blob_sha(data))

    actions = plan_actions({n: sha for n, (_, _, sha) in local.items()}, remote)
    changed: list[str] = []
    for name, action in sorted(actions.items()):
        dest = intake_dest(cycle, name)
        if action == "skip":
            print(f"UNCHANGED: {slug} {dest} already on {branch} at this content sha")
            continue
        _, data, _sha = local[name]
        api.put_file(repo, dest, branch, data,
                     f"intake({slug}): {cycle} — {name} [drive-poll handoff]",
                     sha=remote.get(name))
        changed.append(dest)
        print(f"COMMITTED: {slug} {dest} ({action})")

    docs_on_branch = sorted(set(remote) | set(local))
    summaries = [preflight_doc(path, project_dir) for path, _, _ in
                 (local[n] for n in sorted(local))]
    title = pr_title(cycle, len(docs_on_branch))
    body = render_pr_body(slug, cycle, branch, summaries, run_url)
    action, url = api.open_or_update_pr(repo, branch, base, title, body)
    print(f"PR: {slug} {action} {url}")

    dispatched = False
    if dispatch and changed:
        if cycle == current_cycle():
            # Dispatch on the CYCLE BRANCH: the caller checks out the dispatch
            # ref, so the DOCX is present and the emitted pages land on this
            # same branch — the intake PR becomes the content PR.
            newest = max(local, key=lambda n: local[n][0].stat().st_mtime)
            dispatched = api.dispatch_cycle_emit(repo, branch, intake_dest(cycle, newest))
            if dispatched:
                print(f"DISPATCHED: {slug} {CYCLE_EMIT_WORKFLOW} on {branch} "
                      f"(source_doc={intake_dest(cycle, newest)}, dry_run=false)")
        else:
            print(f"NOTE: {slug} cycle {cycle} is not the current month — "
                  f"cycle-emit NOT auto-dispatched (its cycle id would not match "
                  f"this branch). Run the client's Cycle Emit workflow by hand "
                  f"on branch {branch}.")
    elif dispatch and not changed:
        print(f"NOTE: {slug} nothing changed — cycle-emit not re-dispatched.")

    return {"slug": slug, "repo": repo, "branch": branch, "pr": url,
            "pr_action": action, "committed": changed, "dispatched": dispatched}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def discover(intake_dir: Path, roster_slugs: set[str]) -> dict[str, list[Path]]:
    """intake/<slug>/**/*.docx for roster slugs only. unrouted/ and inactive/
    are triage bins — a human routes those, never this module."""
    out: dict[str, list[Path]] = {}
    if not intake_dir.is_dir():
        return out
    for child in sorted(intake_dir.iterdir()):
        if not child.is_dir() or child.name.startswith(".") \
                or child.name in _NON_CLIENT_DIRS:
            continue
        if child.name not in roster_slugs:
            print(f"NOTE: intake/{child.name}/ is not a roster slug — left for triage.")
            continue
        docx = sorted(p for p in child.rglob("*.docx") if p.is_file())
        skipped = [p for p in child.rglob("*") if p.is_file() and p.suffix != ".docx"]
        for p in skipped:
            print(f"NOTE: {child.name}: {p.name} is not a DOCX — stays in the "
                  "artifact, not handed off.")
        if docx:
            out[child.name] = docx
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-client-handoff",
        description="HANDOFF: retrieved team DOCX -> cycle branch + intake PR on the "
                    "client repo (+ cycle-emit dispatch). PR-only, never main.")
    ap.add_argument("--intake-dir", required=True, type=Path)
    ap.add_argument("--clients-yml", required=True, type=Path,
                    help="config/drive-intake.yml (must carry repo: per client)")
    ap.add_argument("--cycle", default=None, help="YYYY-MM (default: current UTC month)")
    ap.add_argument("--clones-dir", type=Path, default=Path(".clients"),
                    help="where read-only client checkouts land (for pre-flight)")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve and report only — no branch, no commit, no PR")
    ap.add_argument("--no-dispatch", action="store_true",
                    help="skip the cycle-emit workflow_dispatch")
    ap.add_argument("--run-url", default=os.environ.get("HANDOFF_RUN_URL", ""),
                    help="Actions run URL, stamped into the PR body")
    args = ap.parse_args()

    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        print(f"[ERROR] {TOKEN_ENV} is not set. The handoff stage only activates "
              "when that secret exists (docs/ADMIN-CHECKLIST.md has the mint "
              "spec).", file=sys.stderr)
        return 2
    cycle = args.cycle or current_cycle()
    if not _CYCLE_RE.match(cycle):
        print(f"[ERROR] --cycle must be YYYY-MM (got {cycle!r})", file=sys.stderr)
        return 2
    if not args.clients_yml.is_file():
        print(f"[ERROR] no such roster: {args.clients_yml}", file=sys.stderr)
        return 2
    cfg = yaml.safe_load(args.clients_yml.read_text(encoding="utf-8")) or {}
    clients = cfg.get("clients") or []

    work = discover(args.intake_dir, {c.get("slug") for c in clients})
    if not work:
        print("HANDOFF: nothing retrieved for any roster client — nothing to do.")
        return 0

    api = GitHubApi(token)
    failures = 0
    for slug, docx_paths in work.items():
        try:
            repo = repo_for(clients, slug)
            project = None if args.dry_run else \
                clone_repo(repo, token, args.clones_dir / slug)
            handoff_client(api, slug, repo, cycle, docx_paths, project,
                           dry_run=args.dry_run,
                           dispatch=not args.no_dispatch,
                           run_url=args.run_url)
        except HandoffError as exc:
            failures += 1
            print(f"ERROR: {slug}: {exc}", file=sys.stderr)

    if failures:
        print(f"[FAIL] {failures} client(s) failed handoff — see ERROR lines above.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
