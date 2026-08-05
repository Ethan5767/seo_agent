"""The handoff stage (retrieved DOCX -> client-repo intake PR), proven offline.

the operator's 2026-08 override allows PR-MEDIATED cross-repo writes and nothing else.
These tests hold the code to that ruling without ever touching a real client
repo: the API layer is a scripted fake transport, and the invariants asserted
are the ones that make the override safe —

    * the only branch ever written is `cycle/<slug>-<YYYY-MM>`, and that name
      matches cycle-emit.reusable.yml's naming byte for byte (the intake PR
      must ripen into the content PR on the SAME branch);
    * re-runs are no-ops: an unchanged DOCX (same git blob sha) is never
      re-committed, an existing PR is updated in place, never duplicated;
    * a repo without cycle-emit installed warns and continues (404 tolerated);
    * the drive-poll gate stays GREEN and inert when CLIENT_REPOS_TOKEN is
      absent — executed, not mirrored, same style as the verdict tests.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from pipeline.intake import client_handoff as ch

REPO = Path(__file__).resolve().parents[1]
DRIVE_POLL = REPO / ".github" / "workflows" / "drive-poll.yml"
CYCLE_EMIT = REPO / ".github" / "workflows" / "cycle-emit.reusable.yml"
ROSTER = REPO / "config" / "drive-intake.example.yml"

EXPECTED_REPOS = {
    "example-client": "your-org/example-client-site",
    "second-example": "your-org/second-example-site",
}


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def test_cycle_branch_shape():
    assert ch.cycle_branch("acme-roofing", "2026-08") == "cycle/acme-roofing-2026-08"


@pytest.mark.parametrize("slug,cycle", [
    ("acme-roofing", "2026-13"),      # no month 13
    ("acme-roofing", "26-08"),        # not YYYY
    ("acme-roofing", ""),
    ("acme_roofing", "2026-08"),      # not kebab-case
    ("", "2026-08"),
    ("../evil", "2026-08"),           # a slug is never a path
])
def test_cycle_branch_rejects_bad_input(slug, cycle):
    with pytest.raises(ch.HandoffError):
        ch.cycle_branch(slug, cycle)


def test_branch_naming_matches_cycle_emit_reusable():
    """The intake branch and the emit branch MUST be the same branch — that is
    what turns the intake PR into the content PR. Assert against the shipped
    workflow text, not against a copy of it."""
    text = CYCLE_EMIT.read_text(encoding="utf-8")
    assert 'BRANCH="cycle/${SLUG}-${CYCLE_ID}"' in text, (
        "cycle-emit.reusable.yml no longer derives cycle/<slug>-<YYYY-MM>; "
        "client_handoff.cycle_branch must be realigned with it")


def test_roster_maps_every_client_to_its_repo():
    cfg = yaml.safe_load(ROSTER.read_text(encoding="utf-8"))
    clients = cfg["clients"]
    for slug, repo in EXPECTED_REPOS.items():
        assert ch.repo_for(clients, slug) == repo


def test_repo_for_missing_repo_field_is_actionable():
    with pytest.raises(ch.HandoffError, match="drive-intake.yml"):
        ch.repo_for([{"slug": "new-client"}], "new-client")


def test_repo_for_unknown_slug():
    with pytest.raises(ch.HandoffError, match="not in the roster"):
        ch.repo_for([], "ghost")


def test_repo_for_rejects_non_owner_repo_shape():
    with pytest.raises(ch.HandoffError, match="owner/repo"):
        ch.repo_for([{"slug": "x", "repo": "https://github.com/a/b"}], "x")


def test_git_blob_sha_matches_git_hash_object(tmp_path):
    """The idempotency key must be EXACTLY what GitHub reports for the file,
    which is `git hash-object`. Cross-checked against real git, not mirrored."""
    if shutil.which("git") is None:
        pytest.skip("git not available")
    payload = b"July handoff \xf0\x9f\x97\x93 content\n"
    f = tmp_path / "doc.docx"
    f.write_bytes(payload)
    expect = subprocess.run(["git", "hash-object", str(f)],
                            capture_output=True, text=True, check=True).stdout.strip()
    assert ch.git_blob_sha(payload) == expect


def test_plan_actions_idempotency():
    local = {"a.docx": "sha-a", "b.docx": "sha-b2", "c.docx": "sha-c"}
    remote = {"a.docx": "sha-a", "b.docx": "sha-b1"}
    assert ch.plan_actions(local, remote) == {
        "a.docx": "skip", "b.docx": "update", "c.docx": "create"}


def test_intake_dest_sanitizes():
    assert ch.intake_dest("2026-08", "July Handoff.docx") == \
        "docs/intake/2026-08/July Handoff.docx"
    assert ch.intake_dest("2026-08", "nested/dir/f.docx") == "docs/intake/2026-08/f.docx"
    with pytest.raises(ch.HandoffError):
        ch.intake_dest("2026-08", "..")


def test_pr_title():
    assert ch.pr_title("2026-08", 1) == "content intake: 2026-08 — 1 doc"
    assert ch.pr_title("2026-08", 3) == "content intake: 2026-08 — 3 docs"


def test_entry_point_declared_and_callable():
    tomllib = pytest.importorskip("tomllib")
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["wf-client-handoff"] == \
        "pipeline.intake.client_handoff:main"
    assert callable(ch.main)


# ---------------------------------------------------------------------------
# The API layer, against a scripted fake transport (offline by construction)
# ---------------------------------------------------------------------------

class FakeTransport:
    """Route table keyed on (METHOD, path). Records every write it sees so the
    tests can assert what was — and was NOT — touched."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method, url, headers, body):
        import json
        path = url.replace(ch.API_BASE, "").split("?")[0]
        payload = json.loads(body) if body else None
        self.calls.append((method, path, payload))
        key = (method, path)
        if key not in self.routes:
            raise AssertionError(f"unexpected API call: {method} {path}")
        hit = self.routes[key]
        if isinstance(hit, list):          # consecutive scripted responses
            hit = hit.pop(0)
        return hit

    def writes(self):
        return [(m, p, b) for m, p, b in self.calls if m in ("POST", "PUT", "PATCH")]


REPO_NAME = "your-org/acme-roofing-site"
BR = "cycle/acme-roofing-2026-08"


def _routes(branch_exists=False, remote_listing=None, pr_exists=False,
            dispatch_status=204):
    listing = ([{"type": "file", "name": n, "sha": s}
                for n, s in (remote_listing or {}).items()])
    return {
        ("GET", f"/repos/{REPO_NAME}"): (200, {"default_branch": "main"}),
        ("GET", f"/repos/{REPO_NAME}/git/ref/heads/main"): (200, {"object": {"sha": "mainsha"}}),
        ("GET", f"/repos/{REPO_NAME}/git/ref/heads/{BR}"):
            (200, {"object": {"sha": "brsha"}}) if branch_exists else (404, {"message": "Not Found"}),
        ("POST", f"/repos/{REPO_NAME}/git/refs"): (201, {"ref": f"refs/heads/{BR}"}),
        ("GET", f"/repos/{REPO_NAME}/contents/docs/intake/2026-08"):
            (200, listing) if listing else (404, {"message": "Not Found"}),
        ("PUT", f"/repos/{REPO_NAME}/contents/docs/intake/2026-08/july.docx"):
            (201, {"content": {"sha": "newsha"}}),
        ("GET", f"/repos/{REPO_NAME}/pulls"):
            (200, [{"number": 7, "html_url": "https://github.com/x/pull/7"}] if pr_exists else []),
        ("POST", f"/repos/{REPO_NAME}/pulls"):
            (201, {"number": 8, "html_url": "https://github.com/x/pull/8"}),
        ("PATCH", f"/repos/{REPO_NAME}/pulls/7"): (200, {}),
        ("POST", f"/repos/{REPO_NAME}/actions/workflows/cycle-emit.yml/dispatches"):
            (dispatch_status, None if dispatch_status == 204 else {"message": "Not Found"}),
    }


def _docx(tmp_path: Path) -> Path:
    p = tmp_path / "july.docx"
    p.write_bytes(b"docx bytes")
    return p


def _run(tmp_path, **route_kw):
    fake = FakeTransport(_routes(**route_kw))
    api = ch.GitHubApi("t0ken", transport=fake)
    result = ch.handoff_client(
        api, "acme-roofing", REPO_NAME, "2026-08", [_docx(tmp_path)],
        project_dir=None, dry_run=False, dispatch=False)
    return fake, result


def test_first_run_creates_branch_commits_and_opens_pr(tmp_path):
    fake, result = _run(tmp_path)
    methods = [(m, p) for m, p, _ in fake.writes()]
    assert ("POST", f"/repos/{REPO_NAME}/git/refs") in methods
    assert ("PUT", f"/repos/{REPO_NAME}/contents/docs/intake/2026-08/july.docx") in methods
    assert ("POST", f"/repos/{REPO_NAME}/pulls") in methods
    assert result["branch"] == BR
    assert result["pr_action"] == "opened"
    assert result["committed"] == ["docs/intake/2026-08/july.docx"]


def test_every_write_targets_the_cycle_branch_never_main(tmp_path):
    """The load-bearing invariant of the operator's override: PR-mediated only."""
    fake, _ = _run(tmp_path)
    for method, path, payload in fake.writes():
        if path.endswith("/git/refs"):
            assert payload["ref"] == f"refs/heads/{BR}"
        if "/contents/" in path:
            assert payload["branch"] == BR, "a content write aimed at a non-cycle branch"
        assert "merge" not in path, "the handoff must never merge anything"


def test_rerun_with_unchanged_doc_is_a_noop_commit_wise(tmp_path):
    sha = ch.git_blob_sha(b"docx bytes")
    fake, result = _run(tmp_path, branch_exists=True,
                        remote_listing={"july.docx": sha}, pr_exists=True)
    paths = [p for m, p, _ in fake.writes()]
    assert not any("/contents/" in p for p in paths), "unchanged doc was re-committed"
    assert not any(p.endswith("/git/refs") for p in paths), "existing branch re-created"
    assert result["pr_action"] == "updated"      # body refresh only, PR #7 reused
    assert result["committed"] == []


def test_changed_doc_updates_with_the_remote_sha(tmp_path):
    fake, result = _run(tmp_path, branch_exists=True,
                        remote_listing={"july.docx": "stale-sha"}, pr_exists=True)
    put = next(b for m, p, b in fake.writes() if "/contents/" in p)
    assert put["sha"] == "stale-sha", "an update PUT must carry the old blob sha"
    assert result["committed"] == ["docs/intake/2026-08/july.docx"]


def test_dispatch_fires_on_the_cycle_branch_for_the_current_month(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "current_cycle", lambda: "2026-08")
    fake = FakeTransport(_routes())
    api = ch.GitHubApi("t0ken", transport=fake)
    result = ch.handoff_client(api, "acme-roofing", REPO_NAME, "2026-08",
                               [_docx(tmp_path)], project_dir=None, dispatch=True)
    dispatch = next(b for m, p, b in fake.calls if p.endswith("/dispatches"))
    assert dispatch["ref"] == BR, "cycle-emit must run ON the cycle branch"
    assert dispatch["inputs"] == {"source_doc": "docs/intake/2026-08/july.docx",
                                  "dry_run": "false"}
    assert result["dispatched"] is True


def test_dispatch_tolerates_repo_without_cycle_emit(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ch, "current_cycle", lambda: "2026-08")
    fake = FakeTransport(_routes(dispatch_status=404))
    api = ch.GitHubApi("t0ken", transport=fake)
    result = ch.handoff_client(api, "acme-roofing", REPO_NAME, "2026-08",
                               [_docx(tmp_path)], project_dir=None, dispatch=True)
    assert result["dispatched"] is False        # warned, did not raise
    assert "cycle-emit not" in capsys.readouterr().out


def test_dispatch_skipped_for_a_non_current_month(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ch, "current_cycle", lambda: "2026-09")
    fake = FakeTransport(_routes())
    api = ch.GitHubApi("t0ken", transport=fake)
    result = ch.handoff_client(api, "acme-roofing", REPO_NAME, "2026-08",
                               [_docx(tmp_path)], project_dir=None, dispatch=True)
    assert result["dispatched"] is False
    assert not any(p.endswith("/dispatches") for _, p, _ in fake.calls), (
        "cycle-emit derives CYCLE_ID from 'now'; dispatching a past month would "
        "push a mismatched branch")
    assert "not the current month" in capsys.readouterr().out


def test_unreadable_repo_is_actionable(tmp_path):
    fake = FakeTransport({("GET", f"/repos/{REPO_NAME}"): (404, {"message": "Not Found"})})
    api = ch.GitHubApi("t0ken", transport=fake)
    with pytest.raises(ch.HandoffError, match="CLIENT_REPOS_TOKEN"):
        ch.handoff_client(api, "acme-roofing", REPO_NAME, "2026-08",
                          [_docx(tmp_path)], project_dir=None)


def test_branch_create_race_is_tolerated():
    fake = FakeTransport({
        ("GET", f"/repos/{REPO_NAME}/git/ref/heads/{BR}"): (404, {"message": "Not Found"}),
        ("POST", f"/repos/{REPO_NAME}/git/refs"):
            (422, {"message": "Reference already exists"}),
    })
    api = ch.GitHubApi("t0ken", transport=fake)
    assert api.ensure_branch(REPO_NAME, BR, "mainsha") == "exists"


def test_preflight_degrades_without_a_checkout(tmp_path):
    got = ch.preflight_doc(tmp_path / "july.docx", None)
    assert got["name"] == "july.docx"
    assert "not pre-flighted" in got["error"]


def test_pr_body_names_the_guarantees():
    body = ch.render_pr_body("acme-roofing", "2026-08", BR,
                             [{"name": "july.docx", "pages": 12, "blocking": 2,
                               "curate": 1, "ready": [], "pages_blocked": ["a", "b"],
                               "top_blockers": [{"code": "forbidden_phrase",
                                                 "offending": "$12,000", "count": 2,
                                                 "fix": "use written-word form"}]}])
    assert "| `july.docx` | 12 | **2** | 1 |" in body
    assert "forbidden_phrase" in body and "$12,000" in body
    assert "never" in body and "merges" in body


def test_discover_skips_triage_bins_and_non_roster_dirs(tmp_path, capsys):
    for d, f in [("acme-roofing", "a.docx"), ("unrouted", "x.docx"),
                 ("inactive", "y.docx"), ("mystery-client", "z.docx")]:
        (tmp_path / d).mkdir()
        (tmp_path / d / f).write_bytes(b"x")
    (tmp_path / "acme-roofing" / "notes.txt").write_bytes(b"x")
    got = ch.discover(tmp_path, {"acme-roofing", "northstar-landscaping"})
    assert list(got) == ["acme-roofing"]
    assert [p.name for p in got["acme-roofing"]] == ["a.docx"]
    out = capsys.readouterr().out
    assert "mystery-client" in out and "notes.txt" in out


# ---------------------------------------------------------------------------
# drive-poll gating — executed, not mirrored
# ---------------------------------------------------------------------------

def _drive_poll_steps() -> list[dict]:
    wf = yaml.safe_load(DRIVE_POLL.read_text(encoding="utf-8"))
    return [s for job in wf["jobs"].values() for s in job.get("steps", [])]


def _step(step_id: str) -> dict:
    for s in _drive_poll_steps():
        if s.get("id") == step_id:
            return s
    raise AssertionError(f"drive-poll.yml has no step id {step_id!r}")


@pytest.mark.parametrize("token,expect", [("", "false"), ("ghs_dummy", "true")])
def test_handoff_gate_executes_green_without_the_secret(tmp_path, token, expect):
    """No CLIENT_REPOS_TOKEN -> ready=false and exit 0 (a skipped stage must
    never redden a scheduled poll). Runs the REAL gate script."""
    out = tmp_path / "out"
    out.write_text("")
    proc = subprocess.run(
        ["bash", "-c", _step("handoff-cfg")["run"]],
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
             "CLIENT_REPOS_TOKEN": token, "GITHUB_OUTPUT": str(out)},
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert f"ready={expect}" in out.read_text()
    if not token:
        assert "::notice::" in proc.stdout, "the skip must be announced, quietly"


def test_handoff_step_is_double_gated_and_quiet_by_default():
    cond = _step("handoff")["if"]
    assert "steps.handoff-cfg.outputs.ready == 'true'" in cond
    assert "steps.cfg.outputs.ready == 'true'" in cond
    assert "steps.folder.outputs.new != '0'" in cond, (
        "the handoff must not run when the poll retrieved nothing")


def test_drive_poll_keeps_the_artifact_belt_and_braces():
    names = [s.get("name", "") for s in _drive_poll_steps()]
    assert any("Upload retrieved content" in n for n in names), (
        "the artifact upload must survive the handoff stage — it is the fallback "
        "record when a PR write fails")


def test_no_workflow_carries_a_token_literal():
    text = DRIVE_POLL.read_text(encoding="utf-8")
    import re
    assert not re.search(r"(ghp_|github_pat_|ghs_)[A-Za-z0-9_]{10,}", text)
    assert "CLIENT_REPOS_TOKEN" in text     # by NAME only
