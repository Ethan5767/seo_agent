"""wf-dashboard — local operator console.

A localhost web UI over the artifacts the pipeline already writes into client
repos. Holds no state of its own: every client is a checkout on disk, every
artifact is a JSON file in that checkout, and every action shells out to a
`wf-*` entry point, `git`, or `gh`.

See docs/superpowers/specs/2026-08-05-dashboard-design.md.
"""
import argparse
import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML required. Run: pip3 install pyyaml", file=sys.stderr)
    sys.exit(2)

from pipeline.lib.score import progress, score, series

STATIC = Path(__file__).parent / "static"
RUN_LOGS = Path.home() / ".cache" / "seo_agent" / "runs"

# ── the command allow-list ───────────────────────────────────────────────────
# POST /api/runs takes a NAME from this dict, never a shell string, and argv is
# never joined into one. Without this the dashboard is a remote shell bound to
# a port. `{project}` resolves only to a path discover_clients() found.
# Every entry declares `exits`. An empty dict is the deliberate statement "this
# command speaks the rail's exit vocabulary" — the alternative is the key being
# absent because nobody asked, which is how a failed `git pull` and a broken
# ratchet both came to render as a green success chip.
COMMANDS = {
    # `then` chains the follow-on run. A measured cycle with no lanes is the one
    # genuinely useless state in the rail — the fleet card has to render it as the
    # words "not planned" — and nobody has ever wanted to stop there. The chain is
    # declarative rather than a second orchestrator: exit 0 or 1 launches it, 2+
    # does not, because a refusal must not be followed by work built on it.
    "site-health": {
        "argv": ["wf-site-health", "--project", "{project}"],
        "args": {"limit": "int", "url": "path-list"},
        "label": "Measure live site",
        "exits": {},
        "then": "site-plan",
    },
    "site-plan": {
        "argv": ["wf-site-plan", "--project", "{project}"],
        "args": {"cycle": "cycle"},
        "label": "Plan lanes + worklist",
        "exits": {},
    },
    # `dry-run` prints the prompts and writes nothing, which is the right first
    # click against any client — the console has no undo.
    "site-remediate": {
        "argv": ["wf-site-remediate", "--project", "{project}"],
        "args": {"cycle": "cycle", "max-items": "int", "max-files": "int",
                 "dry-run": "flag"},
        "label": "Remediate worklist (agent writes)",
        # remediate returns 0 when it fixed NOTHING (and after a --dry-run).
        # "Clean — every check passed" over a run where every item errored is
        # the same lie the git and ratchet overrides exist to stop.
        "exits": {0: ("warn", "Ran, fixed nothing — a dry run, or every item "
                              "errored. Read the changelog")},
    },
    # Gates, runnable locally so the operator sees the verdict before the PR
    # does. None of them mutate anything.
    #
    # `needs_commit` marks the two that diff `origin/<default>...HEAD` — the
    # THREE-dot form, which compares commits and is blind to the working tree.
    # Run either on a dirty checkout with no cycle commit and the diff is empty,
    # both exit 0, and the console printed "Clean — every check passed" over work
    # they never looked at (B-015). That is exactly the failure the exit vocabulary
    # exists to prevent, so `_start_run` refuses to launch them with nothing
    # committed instead of rendering a vacuous pass.
    "tier-check": {
        "argv": ["wf-tier-check", "--project", "{project}"],
        "args": {},
        "label": "Check the diff against the tier",
        "exits": {},
        "needs_commit": True,
    },
    "claim-provenance": {
        "argv": ["wf-claim-provenance-check", "--project", "{project}"],
        "args": {"cycle": "cycle"},
        "label": "Check claims are sourced",
        "exits": {},
        "needs_commit": True,
    },
    "acceptance-check": {
        "argv": ["wf-acceptance-check", "--project", "{project}"],
        "args": {"cycle": "cycle"},
        "label": "Re-measure the claimed fixes",
        "exits": {},
    },
    # v3 sharp edge #4: a client with no static export emits no HTML tree, so the
    # nine OUT gates (acceptance_check among them) have nothing to read. This crawls
    # a rendered deployment into the tree they expect. `base-url` is a URL, not a
    # path, so it gets its own declared type rather than riding on `path-list`.
    "render-snapshot": {
        "argv": ["wf-render-snapshot", "--project", "{project}"],
        "args": {"base-url": "url", "url": "path-list", "limit": "int",
                 "clean": "flag"},
        "label": "Crawl a deployment into the tree the gates read",
        "exits": {
            19: ("refused", "REFUSED — nothing was fetched, so nothing was written. "
                            "An empty build dir would make every gate pass over zero files"),
        },
    },
    "preflight": {
        "argv": ["wf-preflight", "--project", "{project}"],
        "args": {},
        "label": "Pre-flight checks",
        "exits": {},
    },
    "client-profile": {
        "argv": ["wf-client-profile", "--project", "{project}"],
        "args": {},
        "label": "Resolve build dir / framework",
        "exits": {},
    },
    # Sharp edge #1: a client with no docs/gate-baseline.json runs the gates
    # BARE, so every piece of inherited debt reads as blocking on their first
    # PR. wf-gate-baseline is two commands wearing one name — check mode reads,
    # record mode WRITES the accepted-debt file into the client repo — and they
    # do not share an exit vocabulary. Splitting them is what lets each carry an
    # exit table that is true, and stops the destructive mode being the one you
    # get by forgetting to tick a box.
    "gate-baseline-check": {
        "argv": ["wf-gate-baseline", "--project", "{project}", "--check"],
        "args": {},
        "label": "Check the gate baseline ratchet (read-only)",
        "exits": {
            1: ("refused", "REFUSED — findings absent from the baseline. Regressions, not legacy debt"),
            2: ("error", "No baseline to check against, or it will not load. Record one first"),
            3: ("error", "Baseline error — see the output"),
        },
    },
    "gate-baseline-record": {
        "argv": ["wf-gate-baseline", "--project", "{project}"],
        "args": {"refresh": "flag", "accept-new": "flag"},
        "label": "RECORD the gate baseline (writes to the client repo)",
        "exits": {
            1: ("refused", "REFUSED to grow the baseline. It may only shrink — "
                           "fix them, or accept them with --refresh --accept-new"),
            2: ("refused", "REFUSED — a baseline already exists. --refresh to drop fixed entries"),
            3: ("error", "Baseline error — see the output"),
        },
    },
}

# Exit codes are meaningful and a bare number communicates nothing. A refusal
# must read as a refusal — a run that measured nothing is not a clean site.
# This is the RAIL's vocabulary; a command that differs says so in its `exits`.
EXIT_MEANING = {
    0: ("clean", "Clean — every check passed"),
    1: ("findings", "Findings written"),
    2: ("error", "Usage error — bad arguments, or a sitemap with no <loc> entries"),
    4: ("refused", "REFUSED — the gate's ruleset is empty. It cannot run, so it will not pass"),
    9: ("refused", "REFUSED — a BLOCK finding, or an edit outside the declared tier. No PR"),
    10: ("error", "Missing docs/client-config.yml"),
    15: ("warn", "Emitted, some pages held for curation"),
    16: ("refused", "REFUSED — nothing to process"),
    17: ("refused", "REFUSED — the diff changes files the declared tier does not permit"),
    18: ("refused", "REFUSED — changed text states a fact that traces to no source"),
    19: ("refused", "REFUSED — every source unreachable. Nothing was written"),
    20: ("refused", "REFUSED — a claimed fix does not clear the finding it claims to fix"),
}


GIT_EXITS = {0: ("clean", "Done"), 1: ("error", "git/gh refused — read the output")}

# wf-onboard is the one command that runs WITHOUT a client, because it is what
# creates one. It is kept out of COMMANDS deliberately: every entry there is
# per-project and gets offered on the run console, and this one has no project
# to be offered against yet.
ONBOARD_EXITS = {
    0: ("clean", "READY — cloned, configured, measured and planned"),
    1: ("warn", "STOPPED on the step a human must clear. Read the output, edit "
                "docs/client-config.yml in the checkout, then run this again — "
                "it resumes from here"),
    2: ("error", "Usage error — read the output"),
    3: ("error", "The checkout failed. Check the collaborator invite was accepted, "
                 "and that gh is authenticated or a token was supplied"),
}


def interpret_exit(code, command=None):
    """The command's own table first, the rail's second. Exit 1 is not universal:
    for the rail it means "it wrote what it found", for git and for the ratchet
    it means the run failed, and for onboard it means "stopped, re-runnable"."""
    if command == "onboard":
        table = ONBOARD_EXITS
    elif (command or "").startswith("git:"):
        table = GIT_EXITS
    else:
        table = COMMANDS.get(command, {}).get("exits", {})
    kind, text = table.get(code) or EXIT_MEANING.get(code, ("error", f"Exited {code}"))
    return {"code": code, "kind": kind, "text": text}


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
    try:
        from pipeline.lib.common import (client_profile, detect_static_export,
                                        framework_family, load_config,
                                        resolve_build_dir)
        cfg = load_config(str(path))
        profile = client_profile(cfg, str(path))
        raw = ((cfg.get("repo") or {}).get("framework")) or ""
        verdict = detect_static_export(path, framework_family(raw), raw)
        build = Path(path) / resolve_build_dir(profile, path).lstrip("./")
    except Exception as exc:
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

    Walks the same way preflight does. This is the one gate in the whole flow that
    cannot be automated: nobody can invent a licence number, opening hours, or a
    review count.
    """
    def walk(obj):
        if isinstance(obj, dict):
            return any(walk(v) for v in obj.values())
        if isinstance(obj, list):
            return any(walk(v) for v in obj)
        return obj == "TODO"
    return walk(cfg or {})


# The seven stages a client moves through, in order, and who clears each. Derived
# entirely from files already on disk — the console still holds no state.
#
# `human` marks the three gates. Everything else is one button, and the point of
# the rail is that the operator never has to work out which button.
STAGES = ["INTERVIEW", "MEASURE", "PLAN", "REMEDIATE", "REVIEW", "COMMIT", "PR", "MERGE"]


def next_action(client, cycle=None):
    """{stage, human, label, detail, command, blocked_by} for one client.

    Answers "what do I do now", which is the question the nine-item nav could not
    answer: every screen showed an artifact and no screen showed the sequence.
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

    cyc = cycles(path)
    ym = cycle if cycle in cyc else (cyc[0] if cyc else None)
    if ym is None:
        return {"stage": "MEASURE", "human": False, "label": "Measure the live site",
                "detail": "No docs/audit/<YYYY-MM>/ yet. site-health crawls the "
                          "sitemap and chains straight into site-plan.",
                "command": "site-health", "blocked_by": None}

    findings = read_artifact(path, ym, "findings.json")
    worklist = read_artifact(path, ym, "worklist.json")
    changelog = read_artifact(path, ym, "changelog.json")
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
    st = git_state(path)
    if prog["remaining"] > 0:
        return {"stage": "REMEDIATE", "human": False,
                "label": f"Remediate {prog['remaining']} item(s)",
                "detail": f"{prog['remaining']} of {prog['actionable']} actionable "
                          f"item(s) left" +
                          (f", {prog['attempted_not_fixed']} already attempted once"
                           if prog["attempted_not_fixed"] else "") +
                          ". The agent writes inside the tier; you review the diff next.",
                "command": "site-remediate",
                # Read access is a fact to check, not assume: a run that cannot end
                # in a PR should say so before it spends money.
                "blocked_by": None}

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
    cyc = cycles(path)
    latest = cyc[0] if cyc else None
    doc = read_artifact(path, latest, "findings.json") if latest else None
    total = len(doc.get("findings", [])) if isinstance(doc, dict) and "findings" in doc else None
    worklist = read_artifact(path, latest, "worklist.json") if latest else None
    changelog = read_artifact(path, latest, "changelog.json") if latest else None
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
        "git": git_state(path),
        # The two numbers the operator asked for and could not get anywhere: what is
        # our score, and how many findings are left.
        "score": score(doc, cfg),
        "progress": progress(worklist, changelog),
        "next": next_action(client),
        "error": client["error"],
    }


# ── runs ─────────────────────────────────────────────────────────────────────
class Run:
    """One subprocess. Lines land in a list (for SSE) and a log file (so a
    browser refresh does not lose the output of a run that already finished)."""

    def __init__(self, run_id, slug, command, argv, cwd, env=None, on_exit=None):
        self.id, self.slug, self.command, self.argv = run_id, slug, command, argv
        self.lines, self.exit_code, self.started = [], None, time.time()
        self.cwd, self.on_exit, self.chained = cwd, on_exit, None
        RUN_LOGS.mkdir(parents=True, exist_ok=True)
        self.log = RUN_LOGS / f"{run_id}.log"
        # `env` carries a credential and is never echoed. argv is — into the log
        # file, the run history and the SSE stream — so nothing secret goes there.
        self.proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        with open(self.log, "w") as fh:
            fh.write("$ " + " ".join(self.argv) + "\n")
            for line in self.proc.stdout:
                line = line.rstrip("\n")
                self.lines.append(line)
                fh.write(line + "\n")
                fh.flush()
        code = self.proc.wait()
        # The follow-on is launched BEFORE exit_code is published, so busy_run still
        # sees this client as busy and the chain cannot race the one-writer rule.
        if self.on_exit is not None:
            try:
                self.chained = self.on_exit(self, code)
            except Exception as exc:                # a broken chain must not
                self.lines.append(f"[WARN] follow-on not started: {exc}")   # hide the
        self.exit_code = code                                              # real exit

    def status(self):
        return {"run_id": self.id, "slug": self.slug, "command": self.command,
                "argv": self.argv, "started": self.started, "lines": len(self.lines),
                "running": self.exit_code is None, "chained": self.chained,
                "exit": None if self.exit_code is None
                else interpret_exit(self.exit_code, self.command)}


RUNS = {}
# Checked and written under one lock: ThreadingHTTPServer answers two POSTs at
# once, so a bare check-then-insert lets both pass and start.
RUNS_LOCK = threading.Lock()


def busy_run(slug):
    """The run still going against this client, or None.

    Two wf-site-remediate runs on one checkout means two Claude Code agents
    editing the same files, and whichever writes last wins — silently. It
    happened on 2026-08-07 against lee-series-web. Keyed on slug rather than
    cwd because onboard's cwd is the clients dir, shared by every client.

    ponytail: RUNS is per-process, so this covers the console and not a
    `./run.sh wf-site-remediate` in a terminal. A lockfile in remediate.py is
    the upgrade if that path ever bites.
    """
    return next((r for r in RUNS.values()
                 if r.slug == slug and r.exit_code is None), None)


def commits_to_judge(path):
    """How many commits HEAD carries that origin/<default> does not.

    This is the exact quantity the two three-dot gates diff over, asked of git the
    same way they ask it. 0 means those gates would judge an empty diff and exit 0
    — a pass over nothing. None means we could not tell (no remote-tracking ref,
    a fresh repo), which must not be read as "nothing to judge": the gate is
    allowed to run and speak for itself.
    """
    st = git_state(path)
    default = st.get("default_branch") or "main"
    if _git(path, "rev-parse", "--verify", f"origin/{default}") is None:
        return None
    out = _git(path, "rev-list", "--count", f"origin/{default}..HEAD")
    try:
        return int(out)
    except (TypeError, ValueError):
        return None


def chain_after(slug, cwd, command):
    """The `on_exit` hook that starts a command's declared follow-on, or None.

    Only `COMMANDS[command]["then"]` can be launched — the same allow-list
    discipline as everything else, so a chain can never become a way to reach a
    command that is not offered. It fires on exit 0 and 1 only: for the rail those
    mean "measured / wrote what it found", and anything else is a refusal that the
    next stage must not be built on top of.
    """
    then = COMMANDS.get(command, {}).get("then")
    if then is None:
        return None

    def start(run, code):
        if code not in (0, 1):
            run.lines.append(f"[chain] {then} not started — {command} exited {code}")
            return None
        run_id = f"{int(time.time() * 1000):x}-{secrets.token_hex(3)}"
        argv = build_argv(then, cwd, {})
        run.lines.append(f"[chain] {command} exited {code} -> starting {then}")
        with RUNS_LOCK:
            RUNS[run_id] = Run(run_id, slug, then, argv, cwd,
                               on_exit=chain_after(slug, cwd, then))
        return {"run_id": run_id, "command": then}
    return start


def build_argv(command, project, args):
    """Name → argv. Every supplied argument is validated against a declared type
    before it joins the list; nothing is interpolated into a shell."""
    spec = COMMANDS.get(command)
    if spec is None:
        raise ValueError(f"unknown command: {command}")
    argv = [project if tok == "{project}" else tok for tok in spec["argv"]]
    for key, value in (args or {}).items():
        kind = spec["args"].get(key)
        if kind is None:
            raise ValueError(f"unknown argument for {command}: {key}")
        if kind == "int":
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{key} must be a positive integer")
            argv += [f"--{key}", str(value)]
        elif kind == "path-list":
            if not isinstance(value, list):
                raise ValueError(f"{key} must be a list")
            for item in value:
                if not isinstance(item, str) or not re.fullmatch(r"[\w\-./~:]{1,300}", item):
                    raise ValueError(f"bad {key} value: {item!r}")
                argv += [f"--{key}", item]
        elif kind == "cycle":
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
                raise ValueError(f"{key} must be YYYY-MM")
            argv += [f"--{key}", value]
        elif kind == "url":
            # An absolute http(s) URL and nothing else. A path-list value would let
            # `--base-url` carry `-flag` or a shell-ish string; this is the one
            # argument in the allow-list that must be a real origin.
            if not isinstance(value, str) or \
                    not re.fullmatch(r"https?://[\w.\-]+(?::\d{1,5})?(?:/[\w\-./~%]*)?", value):
                raise ValueError(f"{key} must be an absolute http(s) URL")
            argv += [f"--{key}", value]
        elif kind == "flag":
            # A flag carries no value, so anything other than an explicit true is
            # a caller that thinks it is setting something. Refuse rather than
            # guess: `{"dry-run": false}` must not silently run for real.
            if value is not True:
                raise ValueError(f"{key} is a flag — pass true or omit it")
            argv += [f"--{key}"]
        else:
            # A type with no branch here would be silently dropped, and a
            # silently ignored argument is a run that did not do what the
            # operator asked. Refuse instead.
            raise ValueError(f"unhandled argument type for {key}: {kind}")
    return argv


# ── onboarding a new client ──────────────────────────────────────────────────
# Both fields are normalised to the shape wf-onboard documents rather than
# passed through: an operator pastes the browser URL, not an owner/name slug.
#
# Each path segment must START alphanumeric and may not contain `..`, the same
# two rules build_git_argv applies to a branch name and for the same reasons. A
# leading `-` is read by argparse as a flag; `..` escapes --clients-dir, and it
# escapes it WITHOUT cloning anything — onboard.py names the checkout
# `slug.split("/")[-1]`, so `owner/..` resolves to the PARENT of the clients
# directory, finds it already exists, and scaffolds client docs into it.
REPO_RE = re.compile(
    r"(?:https?://[\w.-]+/|git@[\w.-]+:)?([A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*?)(?:\.git)?/?")
# ghp_/gho_/github_pat_ are alphanumeric + underscore. Refusing the rest turns a
# pasted password or a stray newline into a message instead of a failed clone.
TOKEN_RE = re.compile(r"[A-Za-z0-9_]{20,255}")
# One label, then at least one more. No empty label (`a..b.com` is not a
# hostname), no leading or trailing hyphen. ponytail: ASCII only — an IDN needs
# `.encode("idna")` here and in every provider that fetches the site, so it is
# a refusal with a message rather than a half-supported path.
HOST_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+")
# A content path is written into the config the gates read. Same two rules as a
# branch name and a repo slug: must start alphanumeric (a leading `-` is read as a
# flag by argparse), and no `..`.
CONTENT_PATH_RE = re.compile(r"[A-Za-z0-9][\w\-./]{0,199}")


def _content_paths(value, label):
    """A list of validated repo-relative paths from a string or a list."""
    items = value if isinstance(value, list) else [value] if value else []
    out = []
    for raw in items:
        if not isinstance(raw, str):
            raise ValueError(f"{label} must be text")
        raw = raw.strip()
        if not raw:
            continue
        if not CONTENT_PATH_RE.fullmatch(raw) or ".." in raw:
            raise ValueError(f"bad {label}: {raw!r} — a repo-relative path starting "
                             f"with a letter or digit, no '..'")
        out.append(raw)
    return out


def build_onboard(body, clients_dir):
    """(slug, argv, env) for a new client, or ValueError with what to fix."""
    raw_repo = (body.get("repo") or "").strip()
    repo = REPO_RE.fullmatch(raw_repo)
    if not repo or ".." in raw_repo:
        raise ValueError("repo must be owner/name or a GitHub URL, e.g. acme/roofing-site")
    # urlparse does scheme, port, path, query and userinfo correctly and lowercases
    # the host; hand-rolling that refused `acme.com/index.html` and `acme.com:8080`,
    # which is most of what an operator actually has in the clipboard.
    raw_domain = (body.get("domain") or "").strip()
    host = urlparse(raw_domain if "//" in raw_domain else f"//{raw_domain}").hostname or ""
    if not HOST_RE.fullmatch(host):
        raise ValueError("domain must be an ASCII hostname, e.g. acmeroofing.com")
    slug = repo.group(1)
    argv = ["wf-onboard", slug, host, "--clients-dir", str(clients_dir)]

    # The tier the operator is declaring for this client. Defaults to 1 — the tier
    # that can only reword what already exists — because raising a tier is a
    # deliberate act, never something you get by leaving a field alone.
    #
    # This is not a relaxation of the tier model. `docs/client-config.yml` stays on
    # the deny floor at every tier including T3, so the AGENT still can never raise
    # its own authority; and wf-onboard writes this into a commit on the DEFAULT
    # branch, which is the human PR the model always required. What changed is when
    # the human declares it, not whether one has to.
    tier = body.get("tier", 1)
    if isinstance(tier, str) and tier.strip().isdigit():
        tier = int(tier.strip())
    if tier not in (1, 2, 3):
        raise ValueError("tier must be 1, 2 or 3")
    location = _content_paths(body.get("content_location"), "content location")
    registry = _content_paths(body.get("content_registry"), "content registry path")
    if len(location) > 1:
        raise ValueError("one content location, not several")
    # Refused here as well as in bootstrap_config, so the operator learns it from
    # the form rather than from a run that clones a repo and then stops.
    if tier == 2 and not (location and registry):
        raise ValueError("T2 needs a content location AND at least one registry path "
                         "— T2 means \"may create pages there and wire them in\", so "
                         "without both it grants authority over nowhere. Use T1, or "
                         "fill both in.")
    argv += ["--tier", str(tier)]
    if location:
        argv += ["--content-location", location[0]]
    for reg in registry:
        argv += ["--content-registry", reg]

    token = (body.get("token") or "").strip()
    if not token:
        return slug, argv, None
    if not TOKEN_RE.fullmatch(token):
        raise ValueError("that does not look like a GitHub token")
    # The token goes in the ENVIRONMENT and nowhere else. Nothing writes it to
    # disk, it never reaches argv (which is logged and streamed), and CLAUDE.md
    # §6 keeps it out of every repo. Re-enter it on the next run; that is the
    # point. It is inherited by the whole SUBTREE, not just wf-onboard —
    # bootstrap, preflight, scaffold, measure and plan all run under it, though
    # only checkout() and check_access() have any use for it.
    return slug, argv, {**os.environ, "GH_TOKEN": token, "GITHUB_TOKEN": token}


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
        hit = [g for g in groups if file in g["files"] or (g["items"] & ids)]
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
            "untracked": [f for f in files if status.get(f) == "??"],
            "diff": _diff(path, files, cached=False),
            "staged_diff": _diff(path, files, cached=True),
        })
    return out


def _porcelain(path):
    r = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "-uall"],
                       capture_output=True, text=True, timeout=20)
    return [ln for ln in r.stdout.splitlines() if ln.strip()] if r.returncode == 0 else []


def _diff(path, files, cached):
    """`git diff` over exactly these paths. Untracked files have no diff at all —
    `--no-index` against /dev/null is how git shows a create, and doing it any other
    way shows nothing and reads as "no changes"."""
    base = ["git", "-C", str(path), "diff", "--no-color"]
    if cached:
        base.append("--cached")
    r = subprocess.run(base + ["--", *files], capture_output=True, text=True, timeout=30)
    text = r.stdout if r.returncode == 0 else ""
    if cached:
        return text
    for f in files:
        full = Path(path) / f
        if not full.is_file():
            continue
        tracked = subprocess.run(["git", "-C", str(path), "ls-files", "--error-unmatch", "--", f],
                                 capture_output=True, text=True)
        if tracked.returncode == 0:
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
    untracked = []
    for f in files:
        r = subprocess.run(["git", "-C", str(path), "ls-files", "--error-unmatch", "--", f],
                           capture_output=True, text=True)
        if r.returncode != 0:
            untracked.append(f)
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


# ── HTTP ─────────────────────────────────────────────────────────────────────
PAGES = {"/": "fleet.html", "/fleet": "fleet.html", "/client": "client.html",
         "/findings": "findings.html", "/runs": "runs.html", "/git": "git.html",
         "/worklist": "worklist.html", "/report": "report.html", "/config": "config.html",
         "/changelog": "changelog.html", "/review": "review.html"}


class Handler(BaseHTTPRequestHandler):
    server_version = "wf-dashboard"

    # ---- helpers
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg, status=400):
        self._json({"error": msg}, status)

    def _client(self, slug):
        for c in discover_clients(self.server.clients_dir):
            if c["slug"] == slug:
                return c
        return None

    def _authorized(self):
        """127.0.0.1 is not a trust boundary: any page in the operator's browser
        can POST to localhost. The token is injected into served HTML, which
        CORS stops a cross-origin page from reading, so it cannot forge the
        header. The Origin check is the second layer.

        Origin is compared to this request's own Host, which IS the same-origin
        test and needs no list. The list it replaces was hardcoded to
        `127.0.0.1:<port>`, so `--host 0.0.0.0` — the container's own flag —
        made the server 403 every POST from a browser that reached it by any
        other address. A forged Origin still fails: the browser sets Host to
        whatever it connected to, and an attacker page cannot make the two agree.
        """
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return False
        return self.headers.get("X-Dashboard-Token") == self.server.token

    def log_message(self, fmt, *args):
        if self.server.verbose:
            super().log_message(fmt, *args)

    # ---- GET
    def do_GET(self):
        url = urlparse(self.path)
        route, query = url.path, parse_qs(url.query)
        if route.startswith("/api/"):
            return self._api_get(route, query)
        if route in PAGES:
            return self._page(PAGES[route])
        if route.startswith("/static/"):
            return self._static(route[len("/static/"):])
        self._err("not found", 404)

    def _page(self, name):
        f = STATIC / name
        if not f.exists():
            return self._err(f"missing page: {name}", 404)
        # The token rides in the HTML, which a cross-origin page cannot read.
        html = f.read_text().replace(
            "</head>", f'<script>window.DASH_TOKEN="{self.server.token}";</script></head>', 1)
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, rel):
        f = (STATIC / rel).resolve()
        if not str(f).startswith(str(STATIC.resolve())) or not f.is_file():
            return self._err("not found", 404)
        body = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_get(self, route, query):
        parts = route.strip("/").split("/")[1:]          # drop "api"
        if parts == ["clients"]:
            return self._json([fleet_entry(c) for c in discover_clients(self.server.clients_dir)])
        if parts == ["commands"]:
            # argv rides along so the console can preview the REAL command. It
            # guessed `wf-<name>` before, which is wrong for every entry whose
            # binary is not named after its key (claim-provenance).
            return self._json({k: {"label": v["label"], "args": v["args"],
                                   "argv": v["argv"]}
                               for k, v in COMMANDS.items()})
        if parts == ["runs"]:
            return self._json([r.status() for r in
                               sorted(RUNS.values(), key=lambda r: -r.started)])
        if len(parts) >= 2 and parts[0] == "runs":
            run = RUNS.get(parts[1])
            if run is None:
                return self._err("no such run", 404)
            if parts[2:] == ["stream"]:
                return self._stream(run)
            return self._json({**run.status(), "output": run.lines})
        if len(parts) >= 2 and parts[0] == "clients":
            client = self._client(parts[1])
            if client is None:
                return self._err("no such client", 404)
            rest = parts[2:]
            if not rest:
                return self._json({**fleet_entry(client), "config": client["cfg"],
                                   "cycles": cycles(client["path"])})
            if rest == ["config"]:
                return self._json(client["cfg"])
            if rest == ["cycles"]:
                return self._json(cycles(client["path"]))
            # The score over time. Built server-side from the artifacts because
            # `lib/score.series` is the one definition of "the score over time" —
            # a second implementation in JS is a second answer to one question.
            if rest == ["series"]:
                return self._json(self._series(client))
            if rest == ["next"]:
                return self._json(next_action(client, query.get("cycle", [None])[0]))
            if len(rest) == 2 and rest[0] == "cycles":
                return self._json(self._cycle(client["path"], rest[1]))
            if len(rest) == 3 and rest[0] == "cycles" and rest[2] == "review":
                return self._json(self._review(client, rest[1]))
            # Local git is instant; `gh pr view` is a network round-trip. They are
            # separate routes so the screen paints before the network answers.
            if rest == ["git"]:
                return self._json({**git_state(client["path"]),
                                   "changed": self._changed(client["path"])})
            if rest == ["pr"]:
                return self._json({"pr": self._pr(client["path"])})
        self._err("not found", 404)

    def _series(self, client):
        """{series, verified} — the measured/projected points, plus which cycles
        `acceptance_check` has actually verified.

        `verified` is deliberately separate from the score: a projection is a claim
        the changelog makes, and a claim rendered as a measurement is the whole
        thing this pipeline is built to prevent. `None` for a client with no build
        tree means "cannot verify", never "verified".
        """
        path, cfg = client["path"], client["cfg"]
        rows = [(ym, read_artifact(path, ym, "findings.json"),
                 read_artifact(path, ym, "changelog.json"), cfg)
                for ym in cycles(path)]
        return {"series": series(rows), "verified": acceptance_state(path)}

    def _review(self, client, ym):
        """The approval units, plus everything the finish panel needs to decide
        which step to offer. One request: the screen must not paint a COMMIT button
        while it is still waiting to learn whether anything is staged."""
        path = client["path"]
        changelog = read_artifact(path, ym, "changelog.json")
        st = git_state(path)
        return {
            "cycle": ym,
            "units": review_units(path, changelog),
            "git": st,
            "on_default": st.get("branch") == st.get("default_branch"),
            "commits_to_judge": commits_to_judge(path),
            "progress": progress(read_artifact(path, ym, "worklist.json"), changelog),
            "missing_changelog": changelog is None,
        }

    def _cycle(self, path, ym):
        names = ["findings.json", "worklist.json", "changelog.json", "report.md"]
        out, missing = {}, []
        for n in names:
            doc = read_artifact(path, ym, n)
            if doc is None:
                missing.append(n)
            else:
                out[n] = doc
        return {"cycle": ym, "artifacts": out, "missing": missing}

    def _pr(self, path):
        try:
            r = subprocess.run(["gh", "pr", "view", "--json", "number,state,url,title"],
                               cwd=path, capture_output=True, text=True, timeout=20)
            return json.loads(r.stdout) if r.returncode == 0 else None
        except Exception:
            return None

    def _changed(self, path):
        out = _git(path, "status", "--porcelain")
        return [l for l in (out or "").splitlines() if l]

    def _stream(self, run):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        sent = 0
        try:
            while True:
                while sent < len(run.lines):
                    payload = json.dumps({"line": run.lines[sent]})
                    self.wfile.write(f"event: line\ndata: {payload}\n\n".encode())
                    sent += 1
                self.wfile.flush()
                if run.exit_code is not None and sent >= len(run.lines):
                    done = json.dumps(interpret_exit(run.exit_code, run.command))
                    self.wfile.write(f"event: exit\ndata: {done}\n\n".encode())
                    self.wfile.flush()
                    return
                time.sleep(0.15)
        except (BrokenPipeError, ConnectionResetError):
            return

    # ---- POST
    def do_POST(self):
        if not self._authorized():
            return self._err("unauthorized", 403)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._err("bad JSON")
        parts = urlparse(self.path).path.strip("/").split("/")
        # Not under /clients/<slug>/: there is no client until this succeeds.
        if parts == ["api", "onboard"]:
            try:
                slug, argv, env = build_onboard(body, self.server.clients_dir)
            except ValueError as exc:
                return self._err(str(exc))
            # The run is labelled with the checkout name onboard.py will create,
            # not `owner/name`. Every other run's slug is a client slug, and a
            # shape nothing else uses is a run that never joins its own client.
            return self._launch(slug.split("/")[-1], str(self.server.clients_dir),
                                "onboard", argv, env)
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "clients":
            client = self._client(parts[2])
            if client is None:
                return self._err("no such client", 404)
            if parts[3] == "runs":
                return self._start_run(client, body)
            if parts[3] == "git":
                return self._start_git(client, body)
            if parts[3] == "review":
                return self._start_review(client, body)
        self._err("not found", 404)

    def _start_review(self, client, body):
        cycle = body.get("cycle")
        if not isinstance(cycle, str) or not re.fullmatch(r"\d{4}-\d{2}", cycle):
            return self._err("cycle must be YYYY-MM")
        changelog = read_artifact(client["path"], cycle, "changelog.json")
        action = body.get("action")
        try:
            argv = build_review_argv(action, client["path"], changelog, body.get("files"))
        except ValueError as exc:
            return self._err(str(exc))
        return self._launch(client["slug"], client["path"], f"git:{action}", argv)

    def _start_run(self, client, body):
        command = body.get("command")
        try:
            argv = build_argv(command, client["path"], body.get("args"))
        except ValueError as exc:
            return self._err(str(exc))
        # B-015. A gate that would diff nothing must refuse, not pass.
        if COMMANDS[command].get("needs_commit") and \
                commits_to_judge(client["path"]) == 0:
            return self._err(
                f"nothing committed for {command} to judge. It diffs "
                f"origin/<default>...HEAD, so on an uncommitted tree it would "
                f"examine an empty diff and exit 0 — a pass over nothing. Commit "
                f"the cycle first, then check.", 409)
        return self._launch(client["slug"], client["path"], command, argv)

    def _start_git(self, client, body):
        try:
            argv = build_git_argv(body.get("action"), client["path"], body.get("extra"))
        except ValueError as exc:
            return self._err(str(exc))
        return self._launch(client["slug"], client["path"], f"git:{body.get('action')}", argv)

    def _launch(self, slug, cwd, command, argv, env=None):
        run_id = f"{int(time.time() * 1000):x}-{secrets.token_hex(3)}"
        with RUNS_LOCK:
            busy = busy_run(slug)
            if busy is not None:
                return self._err(
                    f"{busy.command} is still running against {slug}. One writer per "
                    f"checkout — wait for it, or open it from the run history.", 409)
            try:
                RUNS[run_id] = Run(run_id, slug, command, argv, cwd, env,
                                   on_exit=chain_after(slug, cwd, command))
            except FileNotFoundError as exc:
                return self._err(f"command not on PATH: {exc.filename}", 500)
        self._json({"run_id": run_id}, 202)


def main() -> int:
    ap = argparse.ArgumentParser(prog="wf-dashboard", description=__doc__.split("\n")[0])
    ap.add_argument("--clients-dir", default="~/clients",
                    help="directory holding client repo checkouts (default: ~/clients)")
    ap.add_argument("--port", type=int, default=8765)
    # ponytail: containers cannot publish a 127.0.0.1 bind — -p reaches the
    # container's external interface, not its loopback. Publish it as
    # `-p 127.0.0.1:8765:8765` and the exposure stays exactly what it was:
    # host loopback only, still behind the per-run token.
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default: 127.0.0.1; 0.0.0.0 inside a container)")
    ap.add_argument("--verbose", action="store_true", help="log every request")
    args = ap.parse_args()

    clients_dir = Path(args.clients_dir).expanduser()
    if not clients_dir.is_dir():
        print(f"[ERROR] --clients-dir not a directory: {clients_dir}", file=sys.stderr)
        return 2

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.clients_dir = clients_dir
    httpd.token = secrets.token_urlsafe(16)
    httpd.verbose = args.verbose

    found = discover_clients(clients_dir)
    # 0.0.0.0 is a bind address, not somewhere you can browse to. Printing it as
    # a URL sends the operator to a dead link; the container publishes this on
    # the host's loopback, which is where they actually go.
    reachable = "127.0.0.1" if args.host in ("0.0.0.0", "::", "") else args.host
    print(f"wf-dashboard  http://{reachable}:{args.port}"
          f"{'   (bound ' + args.host + ')' if reachable != args.host else ''}")
    print(f"  clients-dir  {clients_dir}  ({len(found)} client(s): "
          f"{', '.join(c['slug'] for c in found) or 'none found'})")
    print(f"  run logs     {RUN_LOGS}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
