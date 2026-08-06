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
    "site-health": {
        "argv": ["wf-site-health", "--project", "{project}"],
        "args": {"limit": "int", "url": "path-list"},
        "label": "Measure live site",
        "exits": {},
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
    "tier-check": {
        "argv": ["wf-tier-check", "--project", "{project}"],
        "args": {},
        "label": "Check the diff against the tier",
        "exits": {},
    },
    "claim-provenance": {
        "argv": ["wf-claim-provenance-check", "--project", "{project}"],
        "args": {"cycle": "cycle"},
        "label": "Check claims are sourced",
        "exits": {},
    },
    "acceptance-check": {
        "argv": ["wf-acceptance-check", "--project", "{project}"],
        "args": {"cycle": "cycle"},
        "label": "Re-measure the claimed fixes",
        "exits": {},
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


def interpret_exit(code, command=None):
    """The command's own table first, the rail's second. Exit 1 is not universal:
    for the rail it means "it wrote what it found", for git and for the ratchet
    it means the run failed."""
    table = GIT_EXITS if (command or "").startswith("git:") \
        else COMMANDS.get(command, {}).get("exits", {})
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
    if counts:
        parts = counts.split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])
    state = "dirty" if dirty else "ahead" if ahead else "behind" if behind else "clean"
    return {"branch": branch, "dirty": dirty, "ahead": ahead, "behind": behind,
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


def fleet_entry(client):
    path, cfg = client["path"], client["cfg"]
    cyc = cycles(path)
    latest = cyc[0] if cyc else None
    doc = read_artifact(path, latest, "findings.json") if latest else None
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
        "git": git_state(path),
        "error": client["error"],
    }


# ── runs ─────────────────────────────────────────────────────────────────────
class Run:
    """One subprocess. Lines land in a list (for SSE) and a log file (so a
    browser refresh does not lose the output of a run that already finished)."""

    def __init__(self, run_id, slug, command, argv, cwd):
        self.id, self.slug, self.command, self.argv = run_id, slug, command, argv
        self.lines, self.exit_code, self.started = [], None, time.time()
        RUN_LOGS.mkdir(parents=True, exist_ok=True)
        self.log = RUN_LOGS / f"{run_id}.log"
        self.proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
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
        self.exit_code = self.proc.wait()

    def status(self):
        return {"run_id": self.id, "slug": self.slug, "command": self.command,
                "argv": self.argv, "started": self.started, "lines": len(self.lines),
                "running": self.exit_code is None,
                "exit": None if self.exit_code is None
                else interpret_exit(self.exit_code, self.command)}


RUNS = {}


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


# `merge` is deliberately absent and must stay absent: human merge is the only
# path to production (SITE-AUDIT-PIPELINE.md §1), and a button beside a green
# checkmark is not the same act as reading a diff.
GIT_ACTIONS = {
    "pull": lambda st, extra: ["git", "pull", "--ff-only"],
    "branch": lambda st, extra: ["git", "checkout", "-b", extra["branch"]],
    "commit": lambda st, extra: ["git", "commit", "-m", extra["message"]],
    "stage-audit": lambda st, extra: ["git", "add", "docs/audit"],
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
         "/changelog": "changelog.html"}


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
        header. The Origin check is the second layer."""
        origin = self.headers.get("Origin")
        if origin and origin not in self.server.origins:
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
            if len(rest) == 2 and rest[0] == "cycles":
                return self._json(self._cycle(client["path"], rest[1]))
            # Local git is instant; `gh pr view` is a network round-trip. They are
            # separate routes so the screen paints before the network answers.
            if rest == ["git"]:
                return self._json({**git_state(client["path"]),
                                   "changed": self._changed(client["path"])})
            if rest == ["pr"]:
                return self._json({"pr": self._pr(client["path"])})
        self._err("not found", 404)

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
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "clients":
            client = self._client(parts[2])
            if client is None:
                return self._err("no such client", 404)
            if parts[3] == "runs":
                return self._start_run(client, body)
            if parts[3] == "git":
                return self._start_git(client, body)
        self._err("not found", 404)

    def _start_run(self, client, body):
        try:
            argv = build_argv(body.get("command"), client["path"], body.get("args"))
        except ValueError as exc:
            return self._err(str(exc))
        return self._launch(client, body.get("command"), argv)

    def _start_git(self, client, body):
        try:
            argv = build_git_argv(body.get("action"), client["path"], body.get("extra"))
        except ValueError as exc:
            return self._err(str(exc))
        return self._launch(client, f"git:{body.get('action')}", argv)

    def _launch(self, client, command, argv):
        run_id = f"{int(time.time() * 1000):x}-{secrets.token_hex(3)}"
        try:
            RUNS[run_id] = Run(run_id, client["slug"], command, argv, client["path"])
        except FileNotFoundError as exc:
            return self._err(f"command not on PATH: {exc.filename}", 500)
        self._json({"run_id": run_id}, 202)


def main() -> int:
    ap = argparse.ArgumentParser(prog="wf-dashboard", description=__doc__.split("\n")[0])
    ap.add_argument("--clients-dir", default="~/clients",
                    help="directory holding client repo checkouts (default: ~/clients)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--verbose", action="store_true", help="log every request")
    args = ap.parse_args()

    clients_dir = Path(args.clients_dir).expanduser()
    if not clients_dir.is_dir():
        print(f"[ERROR] --clients-dir not a directory: {clients_dir}", file=sys.stderr)
        return 2

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    httpd.clients_dir = clients_dir
    httpd.token = secrets.token_urlsafe(16)
    httpd.verbose = args.verbose
    httpd.origins = {f"http://127.0.0.1:{args.port}", f"http://localhost:{args.port}"}

    found = discover_clients(clients_dir)
    print(f"wf-dashboard  http://127.0.0.1:{args.port}")
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
