"""state.py — what the console KNOWS, derived from files on disk.

Everything here is a pure read of a client checkout: which clients exist, what git
says, which artifacts a cycle has, the score, and which of the eight stages the
client is standing on. No HTTP, no subprocess launching, no state of its own —
`server.py` holds the allow-list, the Run class and the request handler, and asks
this module the questions.

Split out of `server.py` when it passed 1300 lines. The seam was already marked
there as `# ── discovery`.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

from pipeline.audit.preflight import todo_paths
from pipeline.lib.common import (client_profile, detect_static_export,
                                framework_family, load_config, resolve_build_dir)
from pipeline.lib.score import progress, score


# ── discovery ────────────────────────────────────────────────────────────────
def discover_clients(clients_dir):
    """Every git repo one level under clients_dir holding docs/client-config.yml.

    No roster file: adding a client is cloning it. A client whose YAML will not
    parse is returned WITH its error rather than dropped — silently vanishing
    from the fleet view is the failure worth spending code to avoid.
    """
    root = Path(clients_dir).expanduser()
    out = []
    if not root.is_dir():
        return out
    for path in sorted(root.iterdir()):
        cfg_path = path / "docs" / "client-config.yml"
        if not path.is_dir() or not (path / ".git").exists() or not cfg_path.exists():
            continue
        try:
            cfg = yaml.safe_load(cfg_path.read_text()) or {}
            slug = cfg.get("client") or path.name
            out.append({"slug": slug, "path": str(path), "cfg": cfg, "error": None})
        except Exception as exc:
            out.append({"slug": path.name, "path": str(path), "cfg": {},
                        "error": f"{type(exc).__name__}: {exc}"})
    return out


def _git(path, *args):
    try:
        r = subprocess.run(["git", "-C", str(path), *args],
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def default_branch(path):
    ref = _git(path, "symbolic-ref", "refs/remotes/origin/HEAD")
    if ref:
        return ref.rsplit("/", 1)[-1]
    for name in ("main", "master"):
        if _git(path, "rev-parse", "--verify", name) is not None:
            return name
    return "main"


def git_state(path):
    """clean · dirty · ahead · behind — four states that are not interchangeable.

    `ahead` is the one that silently loses work: committed locally, invisible to
    anyone else until it is pushed.
    """
    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    if branch is None:
        return {"branch": None, "dirty": False, "ahead": 0, "behind": 0, "state": "error"}
    dirty = bool(_git(path, "status", "--porcelain"))
    ahead = behind = 0
    counts = _git(path, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    # A branch with NO upstream has never been pushed, and that is not the same as
    # "up to date with its upstream" — but both used to come back ahead=0. A fresh
    # `cycle/` branch is exactly the no-upstream case, so anything deciding "has
    # this been pushed?" from `ahead` alone reads an unpushed cycle as pushed.
    upstream = bool(counts)
    if counts:
        parts = counts.split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])
    state = "dirty" if dirty else "ahead" if ahead else "behind" if behind else "clean"
    return {"branch": branch, "dirty": dirty, "ahead": ahead, "behind": behind,
            "upstream": upstream, "pushed": upstream and ahead == 0,
            "state": state, "default_branch": default_branch(path)}


def audit_dir(path):
    return Path(path) / "docs" / "audit"


def cycles(path):
    d = audit_dir(path)
    if not d.is_dir():
        return []
    return sorted((p.name for p in d.iterdir()
                   if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}", p.name)), reverse=True)


def read_artifact(path, ym, name):
    f = audit_dir(path) / ym / name
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text()) if name.endswith(".json") else f.read_text()
    except json.JSONDecodeError as exc:
        return {"error": f"unparseable {name}: {exc}"}


def baseline_state(path):
    """Sharp edge #1: a client with no docs/gate-baseline.json runs the gates BARE,
    so every piece of inherited debt reads as blocking on their first PR. Absent
    is a state worth showing on the fleet card, not a thing to discover in CI."""
    f = Path(path) / "docs" / "gate-baseline.json"
    if not f.is_file():
        return {"present": False, "entries": None}
    try:
        doc = json.loads(f.read_text())
        return {"present": True, "entries": len(doc.get("entries", [])),
                "recorded": doc.get("recorded")}
    except Exception:
        # Present but unreadable is NOT the same as absent, and it is not fine.
        # Broad on purpose, same rule as discover_clients: one malformed file in
        # one client repo must not blank the whole fleet view. `{"entries": 5}`
        # is a TypeError, not a JSONDecodeError.
        return {"present": True, "entries": None, "recorded": None}


def acceptance_state(path):
    """Can `acceptance_check` verify this client's claimed fixes at all?

    It reads the BUILT HTML, and a client with no static export emits no route tree
    — v3 sharp edge #4. lee-series-web is `nextjs-16-app-router` with no
    `output: 'export'`, so `./out` never exists and the gate cannot run there.

    Returns `{"can_verify": bool|None, "reason": str}`. `can_verify: False` must
    render as "cannot verify" and never as "not verified by us yet", because the
    two mean opposite things about whether anyone should trust the claims.
    """
    # OSError/KeyError/yaml errors only. An ImportError or AttributeError here would
    # be a renamed symbol in common.py, and swallowing it renders in the operator's
    # browser as "verification unknown — cannot tell: cannot import name …" — a gate
    # that cannot tell you it is broken, which is the failure this function exists to
    # prevent. Let that one crash.
    try:
        cfg = load_config(str(path))
        profile = client_profile(cfg, str(path))
        raw = ((cfg.get("repo") or {}).get("framework")) or ""
        verdict = detect_static_export(path, framework_family(raw), raw)
        build = Path(path) / resolve_build_dir(profile, path).lstrip("./")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return {"can_verify": None, "reason": f"cannot tell: {exc}"}
    if build.is_dir() and any(build.rglob("*.html")):
        return {"can_verify": True, "reason": f"route tree at {build.name}/"}
    if verdict is False:
        return {"can_verify": False,
                "reason": "no static export — acceptance_check reads the built HTML "
                          "and this repo emits no route tree (v3 sharp edge #4)"}
    return {"can_verify": None,
            "reason": "not built here — run the gate in CI, or build once locally"}


def lane_counts(findings_doc):
    """None until wf-site-plan stamps the lanes back onto the findings, so a
    measured-but-unplanned cycle reads as unplanned rather than as four zeros."""
    if not isinstance(findings_doc, dict):
        return None
    lanes = [f.get("lane") for f in findings_doc.get("findings", [])]
    if not any(lanes):
        return None
    out = {}
    for lane in lanes:
        if lane:
            out[lane] = out.get(lane, 0) + 1
    return out


def has_todos(cfg):
    """True when the config still carries an unresolved TODO — the interview step.

    Asks PREFLIGHT, rather than walking the config the same way preflight does. The
    rail's whole promise is that the stage it shows matches what the command will do,
    so a second definition of "unresolved TODO" is a rail that sends the operator to
    a button that then refuses. This is the one gate in the flow that cannot be
    automated: nobody can invent a licence number, opening hours, or a review count.
    """
    return bool(todo_paths(cfg or {}))


def remediate_warnings(path) -> str | None:
    """What is already known to be wrong with the PR this run is heading toward, or
    None. Rendered in red beside the REMEDIATE button.

    Both facts are on disk before a single dollar is spent, and both cost a whole
    cycle to discover afterwards: a client with no gate baseline runs the gates BARE
    so inherited debt reads as blocking (sharp edge #1), and a client with no render
    source cannot run `acceptance_check` at all — so the gate that makes the loop
    trustworthy by RE-MEASURING will not run, and the fixes ship unverified. This is
    exactly what happened to lee-series-web's 2026-08 cycle.
    """
    reasons = []
    if not baseline_state(path)["present"]:
        reasons.append("no docs/gate-baseline.json — the gates will run bare, so this "
                       "client's inherited debt reads as blocking on the PR")
    verify = acceptance_state(path)
    if verify["can_verify"] is False:
        reasons.append(f"acceptance_check cannot run ({verify['reason']}), so the fixes "
                       f"this spends money on ship unverified")
    return " · ".join(reasons) or None


def cycle_bundle(path, cycle=None):
    """(ym, findings, worklist, changelog, git_state) — every artifact the rail and
    the fleet card both need, read ONCE.

    Split out because `fleet_entry` was reading all of it and then calling
    `next_action`, which read all of it again: `cycles`, three `read_artifact`s and
    `git_state` twice over, plus a third `git_state` inside `commits_to_judge`. That
    is ~20 sequential git subprocesses per client on `GET /api/clients`, for data the
    caller already had in hand.
    """
    cyc = cycles(path)
    ym = cycle if cycle in cyc else (cyc[0] if cyc else None)
    read = (lambda name: read_artifact(path, ym, name)) if ym else (lambda name: None)
    return (ym, read("findings.json"), read("worklist.json"), read("changelog.json"),
            git_state(path))


def commits_to_judge(path):
    """How many commits HEAD carries that origin/<default> does not.

    This is the exact quantity the two three-dot gates diff over, asked of git the
    same way they ask it. 0 means those gates would judge an empty diff and exit 0
    — a pass over nothing. None means we could not tell (no remote-tracking ref,
    a fresh repo), which must not be read as "nothing to judge": the gate is
    allowed to run and speak for itself.
    """
    default = default_branch(path)
    if _git(path, "rev-parse", "--verify", f"origin/{default}") is None:
        return None
    out = _git(path, "rev-list", "--count", f"origin/{default}..HEAD")
    try:
        return int(out)
    except (TypeError, ValueError):
        return None

def next_action(client, cycle=None, bundle=None):
    """{stage, human, label, detail, command, blocked_by} for one client.

    Answers "what do I do now", which is the question the nine-item nav could not
    answer: every screen showed an artifact and no screen showed the sequence.

    `bundle` is the caller's already-read `cycle_bundle`; omitted, it reads its own.
    """
    path, cfg = client["path"], client["cfg"]
    if client["error"]:
        return {"stage": "ERROR", "human": True, "label": "Config will not parse",
                "detail": client["error"], "command": None, "blocked_by": None}
    if has_todos(cfg):
        return {"stage": "INTERVIEW", "human": True,
                "label": "Resolve the config TODOs",
                "detail": f"{path}/docs/client-config.yml still has TODO values. "
                          f"Nobody can invent a licence number or a review count — "
                          f"this is the interview. Then run preflight.",
                "command": "preflight", "blocked_by": None}

    ym, findings, worklist, changelog, st = bundle or cycle_bundle(path, cycle)
    if ym is None:
        return {"stage": "MEASURE", "human": False, "label": "Measure the live site",
                "detail": "No docs/audit/<YYYY-MM>/ yet. site-health crawls the "
                          "sitemap and chains straight into site-plan.",
                "command": "site-health", "blocked_by": None}

    if findings is None:
        return {"stage": "MEASURE", "human": False, "label": "Measure the live site",
                "detail": f"Cycle {ym} has no findings.json. This is not a clean "
                          f"site — it is a cycle that was never measured.",
                "command": "site-health", "blocked_by": None}
    if worklist is None:
        return {"stage": "PLAN", "human": False, "label": "Plan the worklist",
                "detail": f"Cycle {ym} is measured but not planned, so no finding "
                          f"has a lane and nothing is actionable yet.",
                "command": "site-plan", "blocked_by": None}

    prog = progress(worklist, changelog)
    if prog["remaining"] > 0:
        return {"stage": "REMEDIATE", "human": False,
                "label": f"Remediate {prog['remaining']} item(s)",
                "detail": f"{prog['remaining']} of {prog['actionable']} actionable "
                          f"item(s) left" +
                          (f", {prog['attempted_not_fixed']} already attempted once"
                           if prog["attempted_not_fixed"] else "") +
                          ". The agent writes inside the tier; you review the diff next.",
                "command": "site-remediate",
                "blocked_by": remediate_warnings(path)}

    if changelog is None:
        return {"stage": "REVIEW", "human": True, "label": "Nothing to review yet",
                "detail": "Every actionable item is done or none was ever queued.",
                "command": None, "blocked_by": None}

    changed = bool(_git(path, "status", "--porcelain"))
    staged = bool(_git(path, "diff", "--cached", "--name-only"))
    if changed and not staged:
        return {"stage": "REVIEW", "human": True, "label": "Review the diff",
                "detail": f"{prog['fixed']} claimed fix(es) are sitting in the "
                          f"working tree. Approve them item by item, or all at once.",
                "command": None, "blocked_by": None}
    if changed and staged:
        return {"stage": "COMMIT", "human": False, "label": "Commit the approved work",
                "detail": "Approved changes are staged. Commit, then the gates can "
                          "judge a real diff.",
                "command": None, "blocked_by": None}
    # `pushed`, not `ahead`: a fresh cycle branch has no upstream, so `ahead` is 0
    # from the moment it is created and an unpushed cycle read as already pushed —
    # which skipped this stage and the gates with it.
    on_default = st.get("branch") == st.get("default_branch")
    if not on_default and not st.get("pushed") and commits_to_judge(path):
        return {"stage": "PR", "human": False, "label": "Gate, push and open a PR",
                "detail": (f"{st['ahead']} commit(s) exist only in this checkout."
                           if st.get("upstream")
                           else "This branch has never been pushed, so nobody else "
                                "can see it.") +
                          " The gates run first, over a real commit.",
                "command": None, "blocked_by": None}
    return {"stage": "MERGE", "human": True, "label": "Review and merge on GitHub",
            "detail": "A human merging is the only path to production, and reading "
                      "the diff is the point.",
            "command": None, "blocked_by": None}


def fleet_entry(client):
    path, cfg = client["path"], client["cfg"]
    bundle = cycle_bundle(path)
    latest, doc, worklist, changelog, st = bundle
    total = len(doc.get("findings", [])) if isinstance(doc, dict) and "findings" in doc else None
    return {
        "slug": client["slug"],
        "domain": cfg.get("domain"),
        "path": path,
        "tier": cfg.get("tier"),
        "latest_cycle": latest,
        "findings_total": total,
        "findings_by_lane": lane_counts(doc),
        "generated": doc.get("generated") if isinstance(doc, dict) else None,
        "baseline": baseline_state(path),
        "git": st,
        # The two numbers the operator asked for and could not get anywhere: what is
        # our score, and how many findings are left.
        "score": score(doc, cfg),
        "progress": progress(worklist, changelog),
        "next": next_action(client, bundle=bundle),
        "error": client["error"],
    }
