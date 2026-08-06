"""Tests for wf-dashboard.

Hermetic: no network, no real client repo, no bound socket. Every client is a
directory built under tmp_path; the handler logic is exercised through the
functions it delegates to.

The security properties come first because they are what stops a web server that
runs subprocesses from being a remote shell bound to a port.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from pipeline.dashboard.server import (
    COMMANDS,
    build_argv,
    build_git_argv,
    cycles,
    default_branch,
    discover_clients,
    fleet_entry,
    git_state,
    interpret_exit,
    lane_counts,
    read_artifact,
)


def _repo(root, slug, cfg=None, raw_cfg=None):
    """A client checkout: a git repo with docs/client-config.yml."""
    p = root / f"{slug}-site"
    (p / "docs").mkdir(parents=True)
    (p / "docs" / "client-config.yml").write_text(
        raw_cfg if raw_cfg is not None else yaml.safe_dump({"client": slug, **(cfg or {})}))
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=p, check=True)
    subprocess.run(["git", "add", "-A"], cwd=p, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=p, check=True)
    return p


# ── the command allow-list: the security boundary ────────────────────────────

def test_unknown_command_is_rejected():
    with pytest.raises(ValueError, match="unknown command"):
        build_argv("rm -rf /", "/tmp/proj", {})


def test_argv_is_a_list_and_never_a_shell_string():
    """Nothing is joined. A caller cannot smuggle a second command through."""
    argv = build_argv("site-health", "/tmp/proj", {"limit": 5})
    assert argv == ["wf-site-health", "--project", "/tmp/proj", "--limit", "5"]
    assert all(isinstance(tok, str) for tok in argv)
    assert not any(";" in tok or "&&" in tok or "|" in tok for tok in argv)


def test_project_placeholder_resolves_to_the_given_path():
    argv = build_argv("preflight", "/some/client", {})
    assert "{project}" not in argv
    assert argv == ["wf-preflight", "--project", "/some/client"]


def test_undeclared_argument_is_rejected():
    with pytest.raises(ValueError, match="unknown argument"):
        build_argv("site-health", "/tmp/proj", {"exec": "whoami"})


@pytest.mark.parametrize("bad", [0, -1, "5", 1.5, True, None])
def test_limit_must_be_a_positive_integer(bad):
    with pytest.raises(ValueError, match="positive integer"):
        build_argv("site-health", "/tmp/proj", {"limit": bad})


@pytest.mark.parametrize("bad", [
    "; touch /tmp/pwned",
    "$(whoami)",
    "`id`",
    "/path with space",
    "a" * 400,
])
def test_url_argument_rejects_shell_metacharacters(bad):
    with pytest.raises(ValueError, match="bad url value"):
        build_argv("site-health", "/tmp/proj", {"url": [bad]})


def test_url_argument_accepts_real_paths():
    argv = build_argv("site-health", "/p", {"url": ["/roofing/", "https://x.com/a"]})
    assert argv.count("--url") == 2
    assert "/roofing/" in argv


def test_url_argument_must_be_a_list():
    with pytest.raises(ValueError, match="must be a list"):
        build_argv("site-health", "/tmp/proj", {"url": "/roofing/"})


def test_cycle_argument_is_a_month_or_nothing():
    assert build_argv("site-plan", "/p", {"cycle": "2026-08"})[-2:] == ["--cycle", "2026-08"]
    for bad in ("2026-8", "../../etc", "2026-08; rm -rf /", 202608):
        with pytest.raises(ValueError, match="YYYY-MM"):
            build_argv("site-plan", "/p", {"cycle": bad})


# ── git actions: no merge, no default-branch push ────────────────────────────

def test_merge_is_not_an_available_action(tmp_path):
    """Human merge is the only path to production. There is no merge action to
    call, so no frontend change can reintroduce one on its own."""
    p = _repo(tmp_path, "acme")
    with pytest.raises(ValueError, match="unknown git action"):
        build_git_argv("merge", p, {})


@pytest.mark.parametrize("action", ["push", "pr"])
def test_push_and_pr_refuse_from_the_default_branch(tmp_path, action):
    p = _repo(tmp_path, "acme")
    assert git_state(p)["branch"] == "main"
    with pytest.raises(ValueError, match="default branch"):
        build_git_argv(action, p, {})


@pytest.mark.parametrize("action", ["push", "pr"])
def test_push_and_pr_allowed_from_a_cycle_branch(tmp_path, action):
    p = _repo(tmp_path, "acme")
    subprocess.run(["git", "checkout", "-qb", "cycle/acme-2026-08"], cwd=p, check=True)
    argv = build_git_argv(action, p, {})
    assert argv[0] in ("git", "gh")


@pytest.mark.parametrize("bad", [
    "a; rm -rf /",
    "../../escape",        # traversal
    "--force",             # would be read as a git flag, not a name
    "with space",
    "",
])
def test_branch_name_is_validated(tmp_path, bad):
    p = _repo(tmp_path, "acme")
    with pytest.raises(ValueError, match="bad branch name"):
        build_git_argv("branch", p, {"branch": bad})


def test_valid_cycle_branch_name_is_accepted(tmp_path):
    p = _repo(tmp_path, "acme")
    assert build_git_argv("branch", p, {"branch": "cycle/acme-2026-08"}) == \
        ["git", "checkout", "-b", "cycle/acme-2026-08"]


def test_commit_requires_a_message(tmp_path):
    p = _repo(tmp_path, "acme")
    with pytest.raises(ValueError, match="commit message required"):
        build_git_argv("commit", p, {"message": "   "})


def test_commit_message_is_a_single_argv_token(tmp_path):
    """A message with shell characters in it stays one argument."""
    p = _repo(tmp_path, "acme")
    argv = build_git_argv("commit", p, {"message": "audit: $(whoami) && rm -rf /"})
    assert argv == ["git", "commit", "-m", "audit: $(whoami) && rm -rf /"]


# ── discovery ────────────────────────────────────────────────────────────────

def test_discovers_repos_with_a_client_config(tmp_path):
    _repo(tmp_path, "acme", {"domain": "acme.com"})
    _repo(tmp_path, "globex", {"domain": "globex.io"})
    found = discover_clients(tmp_path)
    assert sorted(c["slug"] for c in found) == ["acme", "globex"]


def test_ignores_directories_without_a_client_config(tmp_path):
    _repo(tmp_path, "acme")
    (tmp_path / "not-a-client").mkdir()
    (tmp_path / "notes.txt").write_text("hello")
    assert [c["slug"] for c in discover_clients(tmp_path)] == ["acme"]


def test_ignores_a_config_that_is_not_in_a_git_repo(tmp_path):
    p = tmp_path / "loose"
    (p / "docs").mkdir(parents=True)
    (p / "docs" / "client-config.yml").write_text("client: loose\n")
    assert discover_clients(tmp_path) == []


def test_unparseable_config_is_reported_not_dropped(tmp_path):
    """A client that vanishes from the fleet view because its YAML broke reads
    as 'no problems here', which is the opposite of the truth."""
    _repo(tmp_path, "acme")
    _repo(tmp_path, "broken", raw_cfg="client: [unclosed\n  bad: :\n")
    found = discover_clients(tmp_path)
    assert len(found) == 2
    broken = next(c for c in found if c["error"])
    assert broken["slug"] == "broken-site"        # falls back to the directory name
    assert "ParserError" in broken["error"]


def test_slug_comes_from_the_config_not_the_directory(tmp_path):
    _repo(tmp_path, "dirname", {"client": "real-slug"})
    # _repo writes client=<slug> first, then the override wins on dump order.
    assert discover_clients(tmp_path)[0]["slug"] in ("dirname", "real-slug")


def test_missing_clients_dir_yields_nothing(tmp_path):
    assert discover_clients(tmp_path / "nope") == []


# ── artifacts ────────────────────────────────────────────────────────────────

def test_cycles_lists_only_yyyy_mm_dirs_newest_first(tmp_path):
    p = _repo(tmp_path, "acme")
    for name in ("2026-06", "2026-08", "2026-07", "scratch", "2026-8"):
        (p / "docs" / "audit" / name).mkdir(parents=True)
    assert cycles(p) == ["2026-08", "2026-07", "2026-06"]


def test_read_artifact_returns_none_when_absent(tmp_path):
    p = _repo(tmp_path, "acme")
    assert read_artifact(p, "2026-08", "findings.json") is None


def test_read_artifact_reports_bad_json_rather_than_raising(tmp_path):
    p = _repo(tmp_path, "acme")
    d = p / "docs" / "audit" / "2026-08"
    d.mkdir(parents=True)
    (d / "findings.json").write_text("{not json")
    assert "unparseable" in read_artifact(p, "2026-08", "findings.json")["error"]


def test_lane_counts_is_none_before_the_ratchet_exists():
    """Phase 1 findings carry no lane. Rendering four zeros would look measured."""
    doc = {"findings": [{"code": "health.title_length"}, {"code": "health.h1_count"}]}
    assert lane_counts(doc) is None


def test_lane_counts_tallies_lanes_once_they_appear():
    doc = {"findings": [{"lane": "NEW"}, {"lane": "NEW"}, {"lane": "PERSISTING"}]}
    assert lane_counts(doc) == {"NEW": 2, "PERSISTING": 1}


def test_fleet_entry_distinguishes_never_run_from_clean(tmp_path):
    """`None` (no findings.json) and `0` (measured, nothing found) mean opposite
    things and must not collapse to the same rendering."""
    never = _repo(tmp_path, "never")
    clean = _repo(tmp_path, "clean")
    d = clean / "docs" / "audit" / "2026-08"
    d.mkdir(parents=True)
    (d / "findings.json").write_text(json.dumps(
        {"generated": "2026-08-05", "urls_checked": 3, "findings": []}))
    entries = {c["slug"]: fleet_entry(c) for c in discover_clients(tmp_path)}
    assert entries["never"]["findings_total"] is None
    assert entries["clean"]["findings_total"] == 0


# ── git state ────────────────────────────────────────────────────────────────

def test_git_state_clean(tmp_path):
    st = git_state(_repo(tmp_path, "acme"))
    assert st["state"] == "clean" and st["branch"] == "main"


def test_git_state_dirty(tmp_path):
    p = _repo(tmp_path, "acme")
    (p / "docs" / "new.txt").write_text("x")
    assert git_state(p)["state"] == "dirty"


def test_git_state_of_a_non_repo_is_error(tmp_path):
    (tmp_path / "plain").mkdir()
    assert git_state(tmp_path / "plain")["state"] == "error"


def test_default_branch_falls_back_when_there_is_no_remote(tmp_path):
    assert default_branch(_repo(tmp_path, "acme")) == "main"


# ── exit codes ───────────────────────────────────────────────────────────────

def test_exit_19_reads_as_a_refusal_not_a_success():
    """A run that measured nothing is not a clean site."""
    got = interpret_exit(19)
    assert got["kind"] == "refused"
    assert "unreachable" in got["text"]


@pytest.mark.parametrize("code,kind", [(0, "clean"), (1, "findings"), (2, "error"),
                                       (9, "refused"), (15, "warn"), (16, "refused"),
                                       (19, "refused")])
def test_known_exit_codes_map_to_their_kind(code, kind):
    assert interpret_exit(code)["kind"] == kind


def test_unknown_exit_code_is_an_error_never_a_success():
    assert interpret_exit(42)["kind"] == "error"


# ── phases 4-8: the new commands in the allow-list ───────────────────────────

def test_the_agent_commands_are_in_the_allow_list():
    for name in ("site-remediate", "tier-check", "claim-provenance", "acceptance-check"):
        assert name in COMMANDS


def test_a_flag_argument_must_be_an_explicit_true():
    """`{"dry-run": false}` must not silently run the agent for real."""
    argv = build_argv("site-remediate", "/p", {"dry-run": True})
    assert argv[-1] == "--dry-run"
    with pytest.raises(ValueError, match="flag"):
        build_argv("site-remediate", "/p", {"dry-run": False})


def test_remediate_caps_must_be_positive_integers():
    with pytest.raises(ValueError):
        build_argv("site-remediate", "/p", {"max-items": "10"})
    assert build_argv("site-remediate", "/p", {"max-items": 5})[-2:] == \
        ["--max-items", "5"]


# ── the ratchet is reachable from the console (sharp edge #1) ────────────────

def test_gate_baseline_is_in_the_allow_list():
    """A client with no baseline runs the gates BARE. Recording one has to be
    something the operator can do from the console, not lore in a doc."""
    assert build_argv("gate-baseline-record", "/p", {}) == \
        ["wf-gate-baseline", "--project", "/p"]
    assert build_argv("gate-baseline-check", "/p", {})[-1] == "--check"


def test_the_read_only_baseline_check_cannot_be_made_to_write():
    """Check and record are separate entries precisely so the destructive one is
    never a forgotten checkbox away. --check takes no arguments at all."""
    assert COMMANDS["gate-baseline-check"]["args"] == {}
    for flag in ("refresh", "accept-new", "check"):
        with pytest.raises(ValueError, match="unknown argument"):
            build_argv("gate-baseline-check", "/p", {flag: True})


def test_gate_baseline_exit_1_reads_as_a_refusal_not_findings():
    """Exit 1 means "wrote what it found" for the rail and "the ratchet broke"
    for the baseline. Rendering the second as the first launders a regression."""
    assert interpret_exit(1)["kind"] == "findings"
    assert interpret_exit(1, "gate-baseline-check")["kind"] == "refused"


def test_check_mode_exit_2_does_not_claim_a_baseline_already_exists():
    """Exit 2 from --check means the baseline is ABSENT or will not load, which
    is the state the fleet's NO BASELINE chip exists to surface. Telling that
    operator a baseline already exists sends them in the wrong direction."""
    assert "already exists" not in interpret_exit(2, "gate-baseline-check")["text"]
    assert "already exists" in interpret_exit(2, "gate-baseline-record")["text"]


def test_remediate_exit_0_is_never_reported_as_clean():
    """remediate returns 0 when it fixed NOTHING — a dry run, or every item
    errored. "Clean, every check passed" over that is the same lie as a green
    chip on a failed pull."""
    assert interpret_exit(0)["kind"] == "clean"
    assert interpret_exit(0, "site-remediate")["kind"] == "warn"


def test_every_command_states_which_exit_vocabulary_it_speaks():
    """An absent `exits` key means nobody asked whether this command's exit
    codes mean what the rail's mean. That silence is how a failed `git pull`
    came to render as "Findings written". An empty dict is a deliberate yes."""
    for name, spec in COMMANDS.items():
        assert "exits" in spec, f"{name}: declare `exits` ({{}} = speaks the rail's vocabulary)"


def test_a_failed_git_action_is_never_a_success():
    """`git pull --ff-only` exits 1 when it cannot fast-forward."""
    assert interpret_exit(1, "git:pull")["kind"] == "error"
    assert interpret_exit(0, "git:pull")["kind"] == "clean"


def test_every_declared_argument_type_has_a_builder():
    """A type with no branch in build_argv used to be silently dropped. Every
    type any command declares must round-trip through the builder."""
    samples = {"int": 1, "path-list": ["/a/"], "cycle": "2026-08", "flag": True}
    for name, spec in COMMANDS.items():
        for arg, kind in spec["args"].items():
            assert kind in samples, f"{name}.{arg}: no sample for type {kind}"
            build_argv(name, "/p", {arg: samples[kind]})


def test_every_declared_argument_type_has_a_widget():
    """The half that actually broke was the CLIENT: page-runs.js rendered a
    path-list input for every type it did not know, so `cycle` and `flag` were
    sent as lists and refused on arrival. The server being able to build a type
    proves nothing about the screen being able to ask for it.

    A grep, deliberately. The type vocabulary lives in Python and in no-build-step
    JS; sharing it means generating a constant, which is more machinery than this
    four-value enum is worth."""
    js = (Path(__file__).parents[1] / "pipeline" / "dashboard" / "static"
          / "page-runs.js").read_text()
    for name, spec in COMMANDS.items():
        for arg, kind in spec["args"].items():
            assert f"'{kind}'" in js, \
                f"page-runs.js has no widget for {name}.{arg} (type {kind})"


# ── the baseline chip on the fleet card ──────────────────────────────────────

def test_missing_baseline_is_reported_as_absent(tmp_path):
    p = _repo(tmp_path, "acme")
    assert fleet_entry(discover_clients(tmp_path)[0])["baseline"] == \
        {"present": False, "entries": None}


def test_baseline_entries_are_counted(tmp_path):
    p = _repo(tmp_path, "acme")
    (p / "docs" / "gate-baseline.json").write_text(json.dumps(
        {"recorded": "2026-08-01", "entries": [{"gate": "audit_built"}, {"gate": "capsule_check"}]}))
    bl = fleet_entry(discover_clients(tmp_path)[0])["baseline"]
    assert bl == {"present": True, "entries": 2, "recorded": "2026-08-01"}


def test_an_unreadable_baseline_is_not_reported_as_absent(tmp_path):
    """Present-and-broken and absent are different problems with different fixes."""
    p = _repo(tmp_path, "acme")
    (p / "docs" / "gate-baseline.json").write_text("{not json")
    bl = fleet_entry(discover_clients(tmp_path)[0])["baseline"]
    assert bl["present"] is True and bl["entries"] is None
