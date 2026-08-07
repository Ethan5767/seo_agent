"""review.py — GATE 2: the diff the operator approves, and the git actions.

APPROVING IS `git add`. The git index IS the approval record: staged means
approved, unstaged means pending. There is no approvals file, so nothing can drift
out of sync with the tree — `git status` shows the same thing the screen does.

Items that touched the same file are ONE unit, because their diffs are not
separable. And every path in an approve/reject request is validated against that
cycle's `changelog.json`: without that, the endpoint is `git add` and `git restore`
over any path a browser names, bound to a port.

Split out of `server.py` when it passed 1300 lines. The seam was already marked
there as `# ── the diff review`.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pipeline.dashboard.state import git_state


# ── the diff review: approving is `git add` ──────────────────────────────────
# The console holds no state, and approval needs none. STAGED means approved,
# UNSTAGED means still pending. The git index IS the record: `git status` shows it,
# it survives a browser refresh and a server restart, and there is no approvals
# file for anyone to get out of sync with the tree.


def review_units(path, changelog):
    """[{items, files, state, diff, staged_diff}] — the approval units for a cycle.

    Items that touched the SAME FILE are one unit. Their diffs are not separable:
    you cannot approve one and reject the other when both edited
    `lib/page-meta.ts`, and pretending otherwise is how an operator loses a fix
    they approved. So the unit is the transitive closure over shared files, and it
    says so on screen.
    """
    if not isinstance(changelog, dict):
        return []
    files_map = changelog.get("files")
    if not isinstance(files_map, dict):
        return []

    # Union-find over "shares a file with". Small enough that the naive merge is
    # the right one: a cycle has tens of files, not millions.
    groups = []                    # [{"files": set, "items": set}]
    for file, ids in sorted(files_map.items()):
        ids = {i for i in (ids or []) if isinstance(i, str)}
        # Grouped by shared item id only: `files_map` is a dict, so each `file` is
        # visited once and can never already be in a group.
        hit = [g for g in groups if g["items"] & ids]
        merged = {"files": {file}, "items": set(ids)}
        for g in hit:
            merged["files"] |= g["files"]
            merged["items"] |= g["items"]
            groups.remove(g)
        groups.append(merged)

    status = {ln[3:]: ln[:2] for ln in _porcelain(path)}
    out = []
    for g in sorted(groups, key=lambda g: sorted(g["files"])):
        files = sorted(g["files"])
        # `??` from the one porcelain call above already IS "untracked". Asking git
        # again with one `ls-files --error-unmatch` per file was a subprocess per file
        # per request to re-derive a fact in hand.
        untracked = [f for f in files if status.get(f) == "??"]
        codes = [status.get(f) for f in files]
        # A unit is approved when every file it owns is staged and none of them has
        # an unstaged change left. Anything in between is `partial` and says so
        # rather than rounding up to approved.
        present = [c for c in codes if c]
        if not present:
            state = "gone"                       # already committed, or reverted
        elif all(c and c[1] == " " for c in present) and len(present) == len(files):
            state = "approved"
        elif any(c and c[0] != " " and c[0] != "?" for c in present):
            state = "partial"
        else:
            state = "pending"
        out.append({
            "items": sorted(g["items"]),
            "files": files,
            "state": state,
            "untracked": untracked,
            "diff": _diff(path, files, untracked),
            "staged_diff": _diff(path, files, cached=True),
        })
    return out


def _porcelain(path):
    r = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "-uall"],
                       capture_output=True, text=True, timeout=20)
    return [ln for ln in r.stdout.splitlines() if ln.strip()] if r.returncode == 0 else []


def _diff(path, files, untracked=(), cached=False):
    """`git diff` over exactly these paths.

    An untracked file has no diff at all — `--no-index` against /dev/null is how git
    shows a create, and doing it any other way shows nothing and reads as "no
    changes", which for a created file is the opposite of the truth. `untracked` is
    passed in from the caller's single `git status` rather than re-derived per file.
    """
    base = ["git", "-C", str(path), "diff", "--no-color"]
    if cached:
        base.append("--cached")
    r = subprocess.run(base + ["--", *files], capture_output=True, text=True, timeout=30)
    text = r.stdout if r.returncode == 0 else ""
    if cached:
        return text
    for f in untracked:
        if not (Path(path) / f).is_file():
            continue
        n = subprocess.run(["git", "-C", str(path), "diff", "--no-color", "--no-index",
                            "/dev/null", f], capture_output=True, text=True, timeout=30)
        text += n.stdout
    return text


REVIEW_ACTIONS = ("approve", "reject")


def build_review_argv(action, path, changelog, files):
    """argv for approving or rejecting a set of paths, or ValueError.

    **Every path must appear in this cycle's `changelog.json` file map.** That is
    the security boundary and it is not optional: without it this endpoint is
    `git add` and `git restore` over any path the browser names, bound to a port.
    The changelog is the record of what the agent actually touched, so it is the
    only legitimate source of a path here.
    """
    if action not in REVIEW_ACTIONS:
        raise ValueError(f"unknown review action: {action}")
    known = set((changelog or {}).get("files") or {})
    if not known:
        raise ValueError("this cycle's changelog.json records no changed files, so "
                         "there is nothing to approve")
    if not isinstance(files, list) or not files:
        raise ValueError("name the files to " + action)
    for f in files:
        if not isinstance(f, str) or f not in known:
            raise ValueError(f"{f!r} is not a file this cycle's changelog records. "
                             f"Only the paths the agent actually touched can be "
                             f"approved or rejected here.")
    if action == "approve":
        return ["git", "add", "--", *files]

    # Reject. `git restore` cannot revert a create, and the honest alternative
    # (`git clean -f`) silently deletes a file — so an untracked path is refused
    # with the reason rather than quietly destroyed.
    #
    # One `git status` for the whole set, not one `ls-files` per file: `??` already
    # means untracked, and it is the same call `review_units` makes.
    status = {ln[3:]: ln[:2] for ln in _porcelain(path)}
    untracked = [f for f in files if status.get(f) == "??"]
    if untracked:
        raise ValueError(
            f"{', '.join(untracked)} did not exist before this run, so there is no "
            f"previous version to restore. Reverting a create means deleting the "
            f"file, which this console will not do silently — delete it yourself if "
            f"that is what you want.")
    return ["git", "restore", "--staged", "--worktree", "--", *files]


# `merge` is deliberately absent and must stay absent: human merge is the only
# path to production (SITE-AUDIT-PIPELINE.md §1), and a button beside a green
# checkmark is not the same act as reading a diff.
GIT_ACTIONS = {
    "pull": lambda st, extra: ["git", "pull", "--ff-only"],
    "branch": lambda st, extra: ["git", "checkout", "-b", extra["branch"]],
    "commit": lambda st, extra: ["git", "commit", "-m", extra["message"]],
    # `-A`, not `docs/audit`. Staging only the audit JSON produced a PR that
    # reported eight fixes and carried none of them: `wf-site-remediate` writes
    # the reports AND edits the site, and `git commit -m` commits only what is
    # staged. Staging everything is safe because it is not the last word —
    # `tier_check` judges the whole PR diff, so an out-of-tier file that gets
    # staged here fails the gate rather than reaching production.
    "stage-all": lambda st, extra: ["git", "add", "-A"],
    "push": lambda st, extra: ["git", "push", "-u", "origin", st["branch"]],
    "pr": lambda st, extra: ["gh", "pr", "create", "--fill"],
}


def build_git_argv(action, path, extra):
    fn = GIT_ACTIONS.get(action)
    if fn is None:
        raise ValueError(f"unknown git action: {action}")
    st = git_state(path)
    if action in ("push", "pr") and st["branch"] == st.get("default_branch"):
        raise ValueError(f"refusing to {action} from the default branch "
                         f"({st['branch']}) — work on a cycle/ branch")
    if action == "branch":
        # Must start alphanumeric (a leading `-` would be read as a git flag) and
        # carry no `..` (path traversal, and git rejects it anyway — better to say
        # so here than to let git decide).
        name = (extra or {}).get("branch", "")
        if not re.fullmatch(r"[A-Za-z0-9][\w\-./]{0,99}", name) or ".." in name:
            raise ValueError("bad branch name")
    if action == "commit":
        if not (extra or {}).get("message", "").strip():
            raise ValueError("commit message required")
    return fn(st, extra or {})
