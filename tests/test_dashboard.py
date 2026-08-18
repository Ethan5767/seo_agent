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

from pipeline.dashboard.review import build_git_argv
from pipeline.dashboard.server import (
    COMMANDS,
    ONBOARD_EXITS,
    RUNS,
    build_argv,
    build_onboard,
    busy_run,
    interpret_exit,
)
from pipeline.dashboard.state import (
    cycles,
    default_branch,
    discover_clients,
    fleet_entry,
    git_state,
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


def test_text_list_argument_accepts_real_terms():
    argv = build_argv("search-add", "/p", {"write": ["Top AI agency in Cambodia", "best seo phnom penh"]})
    assert argv == ["wf-seed-queries", "--project", "/p",
                     "--write", "Top AI agency in Cambodia",
                     "--write", "best seo phnom penh"]


def test_text_list_argument_must_be_a_list():
    with pytest.raises(ValueError):
        build_argv("search-add", "/p", {"write": "Top AI agency in Cambodia"})


@pytest.mark.parametrize("bad", ["", "   ", "x" * 201])
def test_text_list_argument_rejects_blank_or_oversized_terms(bad):
    with pytest.raises(ValueError):
        build_argv("search-add", "/p", {"write": [bad]})


def test_site_health_provider_flags_are_declared_including_serp():
    argv = build_argv("site-health", "/p",
                       {"with-crux": True, "with-gsc": True, "with-dataforseo": True,
                        "with-serp": True, "max-crawl-pages": 20})
    assert "--with-crux" in argv
    assert "--with-gsc" in argv
    assert "--with-dataforseo" in argv
    assert "--with-serp" in argv
    assert "--max-crawl-pages" in argv and "20" in argv


def test_search_suggest_caps_the_agent_at_five_and_asks_for_json():
    argv = build_argv("search-suggest", "/p", {})
    assert argv == ["wf-seed-queries", "--project", "/p", "--limit", "5", "--format", "json"]


def test_there_is_no_separate_search_check_command():
    """A second command with a narrower provider set than site-health's would
    let one button silently erase the other's findings from findings.json.
    There must be exactly one measuring command."""
    assert "search-check" not in COMMANDS


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


def test_staging_covers_the_remediators_code_edits_not_just_the_audit_json(tmp_path):
    """B-011. `git add docs/audit` + `git commit -m` committed the reports and
    none of the fixes they described. Staging must reach the site files too."""
    p = _repo(tmp_path, "acme")
    assert build_git_argv("stage-all", p, {}) == ["git", "add", "-A"]
    with pytest.raises(ValueError, match="unknown git action"):
        build_git_argv("stage-audit", p, {})


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
    came to render as "Findings written". An empty dict is a deliberate yes.

    `onboard` is not in COMMANDS — it is the one command with no project to run
    against — so it is asserted alongside rather than being the single command
    this invariant cannot see."""
    for name, spec in COMMANDS.items():
        assert "exits" in spec, f"{name}: declare `exits` ({{}} = speaks the rail's vocabulary)"
    assert set(ONBOARD_EXITS) == {0, 1, 2, 3}, "wf-onboard documents exactly these four"


def test_a_failed_git_action_is_never_a_success():
    """`git pull --ff-only` exits 1 when it cannot fast-forward."""
    assert interpret_exit(1, "git:pull")["kind"] == "error"


# ── onboarding a new client ──────────────────────────────────────────────────

@pytest.mark.parametrize("repo", [
    "acme/roofing-site",
    "https://github.com/acme/roofing-site",
    "https://github.com/acme/roofing-site.git",
    "git@github.com:acme/roofing-site.git",
])
def test_onboard_normalises_every_way_an_operator_states_the_repo(repo):
    """An operator pastes the browser URL. wf-onboard documents owner/name."""
    slug, argv, env = build_onboard({"repo": repo, "domain": "acmeroofing.com"}, "/c")
    assert slug == "acme/roofing-site"
    # `--tier 1` is stated rather than left implicit: the console previews this exact
    # argv, and the tier is the most consequential field on the form. An operator
    # reading the preview should see which authority they are granting.
    assert argv == ["wf-onboard", "acme/roofing-site", "acmeroofing.com",
                    "--clients-dir", "/c", "--tier", "1"]
    assert env is None


@pytest.mark.parametrize("raw", [
    "acmeroofing.com",
    "https://AcmeRoofing.com/",
    "http://acmeroofing.com:8080/index.html?utm=x",   # what is actually in the clipboard
])
def test_onboard_reduces_a_pasted_url_to_its_hostname(raw):
    _, argv, _ = build_onboard({"repo": "acme/site", "domain": raw}, "/c")
    assert argv[2] == "acmeroofing.com"


@pytest.mark.parametrize("repo", [
    "--clients-dir/tmp",       # a LEADING DASH: argparse reads it as a flag
    "-/-",
    "owner/..",                # escapes --clients-dir. see below
    "../../etc/passwd",
    "acme/site; rm -rf /",
    "acme site/x",
    "",
])
def test_onboard_refuses_a_repo_that_is_not_owner_slash_name(repo):
    with pytest.raises(ValueError, match="repo"):
        build_onboard({"repo": repo, "domain": "acme.com"}, "/c")


def test_onboard_refuses_a_repo_whose_checkout_would_land_outside_clients_dir(tmp_path):
    """onboard.py names the checkout `slug.split("/")[-1]`, so `owner/..` is
    Path(clients_dir)/".." — the PARENT. It exists, so onboard skips the clone
    entirely and scaffolds client docs into it. This is the reason `..` is
    refused here and not merely discouraged."""
    clients = tmp_path / "clients"
    clients.mkdir()
    assert (clients / "owner/..".split("/")[-1]).resolve() == tmp_path.resolve()
    with pytest.raises(ValueError):
        build_onboard({"repo": "owner/..", "domain": "acme.com"}, str(clients))


@pytest.mark.parametrize("domain", [
    "-x", "not a domain", "", "a..b.com", "localhost", "münchen.de",
])
def test_onboard_refuses_anything_that_is_not_an_ascii_hostname(domain):
    with pytest.raises(ValueError, match="domain"):
        build_onboard({"repo": "acme/site", "domain": domain}, "/c")


def test_onboard_token_reaches_the_environment_and_never_the_argv():
    """argv is written to the run log, listed in the run history and streamed to
    the browser. A credential in it is a credential on disk."""
    slug, argv, env = build_onboard(
        {"repo": "acme/site", "domain": "acme.com", "token": "ghp_" + "a" * 36}, "/c")
    assert not any("ghp_" in tok for tok in argv)
    assert env["GH_TOKEN"] == env["GITHUB_TOKEN"] == "ghp_" + "a" * 36
    assert "PATH" in env, "the child needs the operator's PATH to find wf-onboard"


@pytest.mark.parametrize("token", ["short", "has spaces in it", "tok\nen", "tok;en"])
def test_onboard_refuses_a_token_that_is_not_one(token):
    with pytest.raises(ValueError, match="token"):
        build_onboard({"repo": "acme/site", "domain": "acme.com", "token": token}, "/c")


def test_onboard_exit_1_is_the_interview_step_not_a_failure():
    """wf-onboard exits 1 when it stopped on the TODOs a human must fill, and the
    same command resumes from there. Rendering that as an error sends the
    operator looking for a break; rendering it as the rail's "findings written"
    claims a measurement that did not happen."""
    ex = interpret_exit(1, "onboard")
    assert ex["kind"] == "warn"
    assert "again" in ex["text"]
    assert interpret_exit(0, "onboard")["kind"] == "clean"
    assert interpret_exit(3, "onboard")["kind"] == "error"
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


# ── one writer per checkout ──────────────────────────────────────────────────
class _FakeRun:
    """Only what busy_run reads. A real Run spawns a subprocess."""

    def __init__(self, slug, command, exit_code):
        self.slug, self.command, self.exit_code = slug, command, exit_code


@pytest.fixture
def runs():
    RUNS.clear()
    yield RUNS
    RUNS.clear()


def test_no_run_for_this_client_is_not_busy(runs):
    assert busy_run("acme") is None


def test_a_live_run_makes_that_client_busy(runs):
    """Two remediate runs on one checkout is two agents editing the same files,
    and the loser's edits vanish without a word. Happened on lee-series-web."""
    runs["r1"] = _FakeRun("acme", "site-remediate", None)
    assert busy_run("acme").command == "site-remediate"


def test_a_finished_run_does_not_block_the_next_one(runs):
    runs["r1"] = _FakeRun("acme", "site-remediate", 0)
    assert busy_run("acme") is None


def test_another_clients_run_does_not_block(runs):
    """Serialising the whole fleet behind one slow measure would be a bug, not
    a guard. The lock is per checkout because the conflict is per checkout."""
    runs["r1"] = _FakeRun("acme", "site-remediate", None)
    assert busy_run("beta") is None


# ── the tier the operator picked reaches wf-onboard ──────────────────────────

def test_the_tier_is_carried_into_the_onboard_argv():
    _, argv, _ = build_onboard(
        {"repo": "acme/site", "domain": "acme.com", "tier": 3}, "/c")
    assert argv[-2:] == ["--tier", "3"]


def test_a_complete_t2_carries_its_content_paths():
    _, argv, _ = build_onboard({
        "repo": "acme/site", "domain": "acme.com", "tier": 2,
        "content_location": "src/content/blog/",
        "content_registry": ["src/data/posts.ts", "src/data/nav.ts"]}, "/c")
    assert argv[-8:] == ["--tier", "2",
                         "--content-location", "src/content/blog/",
                         "--content-registry", "src/data/posts.ts",
                         "--content-registry", "src/data/nav.ts"]


def test_t2_without_its_fields_is_refused_at_the_form_not_after_a_clone():
    # bootstrap_config refuses this too, but by then wf-onboard has cloned the repo
    # and run a network access check. The operator should learn it from the form.
    with pytest.raises(ValueError, match="authority over nowhere"):
        build_onboard({"repo": "acme/site", "domain": "acme.com", "tier": 2}, "/c")
    with pytest.raises(ValueError, match="registry"):
        build_onboard({"repo": "acme/site", "domain": "acme.com", "tier": 2,
                       "content_location": "src/content/"}, "/c")


@pytest.mark.parametrize("tier", [0, 4, "two", None, 1.5])
def test_a_tier_that_is_not_one_two_or_three_is_refused(tier):
    with pytest.raises(ValueError, match="tier must be"):
        build_onboard({"repo": "acme/site", "domain": "acme.com", "tier": tier}, "/c")


@pytest.mark.parametrize("bad", ["../../etc", "-flag", "/abs", "src/x\ny"])
def test_a_content_path_that_escapes_the_repo_is_refused(bad):
    # These land in a config the gates read. Same two rules as a branch name: must
    # start alphanumeric, no `..`.
    with pytest.raises(ValueError, match="bad content"):
        build_onboard({"repo": "acme/site", "domain": "acme.com", "tier": 3,
                       "content_location": bad}, "/c")


def test_t3_needs_no_content_paths():
    _, argv, _ = build_onboard(
        {"repo": "acme/site", "domain": "acme.com", "tier": 3}, "/c")
    assert "--content-location" not in argv


# ── B-015: a gate with nothing committed refuses instead of passing ──────────
# tier-check and claim-provenance diff origin/<default>...HEAD — the THREE-dot
# form, blind to the working tree. On a dirty checkout with no cycle commit the
# diff is empty, both exit 0, and the console printed "Clean — every check passed"
# over work they never looked at.

def _committed_repo(tmp_path, name="acme"):
    """A checkout with an origin/<default> ref, so commits_to_judge can count."""
    p = tmp_path / name
    (p / "docs").mkdir(parents=True)
    (p / "docs" / "client-config.yml").write_text(yaml.safe_dump({"client": name}))
    for cmd in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t.t"],
                ["config", "user.name", "t"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", "-C", str(p), *cmd], check=True, capture_output=True)
    # A local stand-in for the remote-tracking ref the gates diff against.
    subprocess.run(["git", "-C", str(p), "update-ref", "refs/remotes/origin/main", "HEAD"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(p), "symbolic-ref", "refs/remotes/origin/HEAD",
                    "refs/remotes/origin/main"], check=True, capture_output=True)
    return p


def test_an_uncommitted_tree_has_nothing_for_those_gates_to_judge(tmp_path):
    from pipeline.dashboard.state import commits_to_judge
    p = _committed_repo(tmp_path)
    (p / "src.ts").write_text("export const x = 1\n")     # dirty, uncommitted
    assert commits_to_judge(p) == 0


def test_a_cycle_commit_gives_those_gates_something_to_judge(tmp_path):
    from pipeline.dashboard.state import commits_to_judge
    p = _committed_repo(tmp_path)
    (p / "src.ts").write_text("export const x = 1\n")
    for cmd in (["add", "-A"], ["commit", "-qm", "cycle"]):
        subprocess.run(["git", "-C", str(p), *cmd], check=True, capture_output=True)
    assert commits_to_judge(p) == 1


def test_no_remote_ref_is_cannot_tell_not_nothing_to_judge(tmp_path):
    # A repo with no origin/<default> must let the gate run and speak for itself.
    # Reading "cannot tell" as "empty diff" would refuse every local-only checkout.
    from pipeline.dashboard.state import commits_to_judge
    p = tmp_path / "bare"
    (p / "docs").mkdir(parents=True)
    for cmd in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t.t"],
                ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(p), *cmd], check=True, capture_output=True)
    (p / "a.txt").write_text("x")
    for cmd in (["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", "-C", str(p), *cmd], check=True, capture_output=True)
    assert commits_to_judge(p) is None


def test_only_the_three_dot_gates_carry_needs_commit():
    from pipeline.dashboard.server import COMMANDS
    marked = {k for k, v in COMMANDS.items() if v.get("needs_commit")}
    # site-health measures the live site and site-remediate reads the worklist —
    # neither looks at a diff, and refusing them on a clean tree would break the
    # normal flow.
    assert marked == {"tier-check", "claim-provenance"}


# ── the stage rail: what do I do now ─────────────────────────────────────────
# Derived entirely from files on disk, so the console still holds no state. The
# complaint it answers: nine nav items showed nine artifacts and none showed the
# sequence.

def _client(path, cfg=None):
    from pipeline.dashboard.state import discover_clients
    for c in discover_clients(Path(path).parent):
        if c["path"] == str(path):
            return c
    raise AssertionError(f"{path} not discovered")


def _cycle_artifacts(path, ym="2026-08", **files):
    d = Path(path) / "docs" / "audit" / ym
    d.mkdir(parents=True, exist_ok=True)
    for name, doc in files.items():
        f = d / name.replace("_", ".", 1)
        f.write_text(json.dumps(doc) if name.endswith("json") else doc)


def test_a_config_with_todos_is_the_interview_gate(tmp_path):
    from pipeline.dashboard.state import next_action
    p = _repo(tmp_path, "acme", {"business": {"trade": "TODO"}})
    n = next_action(_client(p))
    assert n["stage"] == "INTERVIEW"
    # The one gate that cannot be automated, and it must say why rather than look
    # like a failure.
    assert n["human"] is True
    assert "invent" in n["detail"]


def test_no_cycle_at_all_is_measure(tmp_path):
    from pipeline.dashboard.state import next_action
    p = _repo(tmp_path, "acme", {"domain": "acme.com"})
    n = next_action(_client(p))
    assert (n["stage"], n["command"]) == ("MEASURE", "site-health")


def test_a_measured_but_unplanned_cycle_is_plan(tmp_path):
    from pipeline.dashboard.state import next_action
    p = _repo(tmp_path, "acme")
    _cycle_artifacts(p, findings_json={"urls_checked": 1, "findings": []})
    n = next_action(_client(p))
    assert (n["stage"], n["command"]) == ("PLAN", "site-plan")


def test_a_worklist_with_items_left_is_remediate_and_says_how_many(tmp_path):
    from pipeline.dashboard.state import next_action
    p = _repo(tmp_path, "acme")
    _cycle_artifacts(p, findings_json={"urls_checked": 1, "findings": []},
                     worklist_json={"items": [{"id": "wi-1"}, {"id": "wi-2"}]})
    n = next_action(_client(p))
    assert (n["stage"], n["command"]) == ("REMEDIATE", "site-remediate")
    assert "2 item(s)" in n["label"]


def test_a_dirty_tree_after_remediation_is_the_review_gate(tmp_path):
    from pipeline.dashboard.state import next_action
    p = _repo(tmp_path, "acme")
    _cycle_artifacts(p, findings_json={"urls_checked": 1, "findings": []},
                     worklist_json={"items": [{"id": "wi-1"}]},
                     changelog_json={"items": [{"id": "wi-1", "status": "fixed"}],
                                     "files": {"src.ts": ["wi-1"]}})
    (p / "src.ts").write_text("export const x = 2\n")
    n = next_action(_client(p))
    assert (n["stage"], n["human"]) == ("REVIEW", True)


def test_staged_work_is_commit(tmp_path):
    from pipeline.dashboard.state import next_action
    p = _repo(tmp_path, "acme")
    _cycle_artifacts(p, findings_json={"urls_checked": 1, "findings": []},
                     worklist_json={"items": [{"id": "wi-1"}]},
                     changelog_json={"items": [{"id": "wi-1", "status": "fixed"}],
                                     "files": {"src.ts": ["wi-1"]}})
    (p / "src.ts").write_text("export const x = 2\n")
    subprocess.run(["git", "-C", str(p), "add", "-A"], check=True, capture_output=True)
    assert next_action(_client(p))["stage"] == "COMMIT"


def test_a_broken_config_is_its_own_stage_not_a_silent_measure(tmp_path):
    from pipeline.dashboard.state import next_action
    p = _repo(tmp_path, "broken", raw_cfg="client: [unclosed\n  bad: :\n")
    n = next_action(_client(p))
    assert n["stage"] == "ERROR"


def test_the_fleet_card_carries_the_score_and_what_is_left(tmp_path):
    p = _repo(tmp_path, "acme", {"domain": "acme.com"})
    _cycle_artifacts(p, findings_json={"urls_checked": 2, "findings": [
        {"code": "health.title_missing", "location": "/", "fingerprint": "fp1"}]},
        worklist_json={"items": [{"id": "wi-1"}, {"id": "wi-2"}]})
    entry = fleet_entry(_client(p))
    assert entry["score"]["seo"]["score"] is not None
    assert entry["progress"]["remaining"] == 2
    assert entry["next"]["stage"] == "REMEDIATE"


# ── the measure -> plan chain ────────────────────────────────────────────────

def test_site_health_declares_site_plan_as_its_follow_on():
    # A measured cycle with no lanes is the one useless state in the rail: the
    # fleet card has to render it as the words "not planned".
    assert COMMANDS["site-health"]["then"] == "site-plan"


def test_the_chain_is_acyclic_and_only_reaches_declared_commands():
    # A `then` cycle would hang the server launching runs forever, and a `then`
    # naming something outside COMMANDS would be a way to reach a command the
    # console does not offer.
    for name, spec in COMMANDS.items():
        seen, cur = {name}, spec.get("then")
        while cur is not None:
            assert cur in COMMANDS, f"{name} chains to unknown command {cur}"
            assert cur not in seen, f"chain from {name} cycles at {cur}"
            seen.add(cur)
            cur = COMMANDS[cur].get("then")


def test_a_refusal_does_not_start_the_follow_on():
    from pipeline.dashboard.server import chain_after

    class FakeRun:
        lines = []
    start = chain_after("acme", "/tmp/acme", "site-health")
    run = FakeRun()
    run.lines = []
    # 19 = every source unreachable. Planning on top of a run that measured nothing
    # would produce a worklist from no data.
    assert start(run, 19) is None
    assert any("not started" in ln for ln in run.lines)


def test_a_command_with_no_follow_on_has_no_hook():
    from pipeline.dashboard.server import chain_after
    assert chain_after("acme", "/tmp/acme", "site-plan") is None


# ── GATE 2: the diff review ──────────────────────────────────────────────────
# Approving is `git add`, so the git index IS the approval record — no state, no
# parallel file to drift. What must be tested is the grouping (a shared file is not
# separable) and the pathspec boundary (without it this endpoint is `git add` and
# `git restore` over any path a browser names).

def _remediated(tmp_path, files_map, write=True):
    """A checkout with a changelog claiming `files_map`, and those files dirty."""
    p = _repo(tmp_path, "acme")
    d = p / "docs" / "audit" / "2026-08"
    d.mkdir(parents=True)
    (d / "changelog.json").write_text(json.dumps({"cycle": "2026-08", "files": files_map}))
    if write:
        for f in files_map:
            full = p / f
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text("changed\n")
    return p


def _changelog(p):
    return json.loads((p / "docs" / "audit" / "2026-08" / "changelog.json").read_text())


def test_items_that_share_a_file_are_one_approval_unit(tmp_path):
    """Two items that both edited lib/page-meta.ts cannot be approved separately —
    the diff is not separable, and offering the choice loses a fix."""
    from pipeline.dashboard.review import review_units
    p = _remediated(tmp_path, {"lib/page-meta.ts": ["wi-1", "wi-2"]})
    units = review_units(p, _changelog(p))
    assert len(units) == 1
    assert units[0]["items"] == ["wi-1", "wi-2"]


def test_transitively_shared_files_collapse_into_one_unit(tmp_path):
    # wi-2 touches both files, so all three items are one unit even though wi-1 and
    # wi-3 share nothing directly.
    from pipeline.dashboard.review import review_units
    p = _remediated(tmp_path, {"a.ts": ["wi-1", "wi-2"], "b.ts": ["wi-2", "wi-3"]})
    units = review_units(p, _changelog(p))
    assert len(units) == 1
    assert units[0]["items"] == ["wi-1", "wi-2", "wi-3"]
    assert units[0]["files"] == ["a.ts", "b.ts"]


def test_independent_items_are_separate_units(tmp_path):
    from pipeline.dashboard.review import review_units
    p = _remediated(tmp_path, {"a.ts": ["wi-1"], "b.ts": ["wi-2"]})
    assert len(review_units(p, _changelog(p))) == 2


def test_an_unstaged_unit_is_pending_and_a_staged_one_is_approved(tmp_path):
    from pipeline.dashboard.review import review_units
    p = _remediated(tmp_path, {"a.ts": ["wi-1"], "b.ts": ["wi-2"]})
    assert {u["state"] for u in review_units(p, _changelog(p))} == {"pending"}
    subprocess.run(["git", "-C", str(p), "add", "--", "a.ts"], check=True, capture_output=True)
    states = {u["files"][0]: u["state"] for u in review_units(p, _changelog(p))}
    assert states == {"a.ts": "approved", "b.ts": "pending"}


def test_a_unit_carries_the_diff_of_a_new_file(tmp_path):
    """An untracked file has no `git diff` at all. Showing nothing would read as
    "no changes" for exactly the case where everything is a change."""
    from pipeline.dashboard.review import review_units
    p = _remediated(tmp_path, {"new.ts": ["wi-1"]})
    unit = review_units(p, _changelog(p))[0]
    assert "changed" in unit["diff"]
    assert unit["untracked"] == ["new.ts"]


def test_a_modified_tracked_file_shows_both_sides(tmp_path):
    from pipeline.dashboard.review import review_units
    p = _repo(tmp_path, "acme")
    (p / "a.ts").write_text("before\n")
    subprocess.run(["git", "-C", str(p), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(p), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "x"], check=True, capture_output=True)
    d = p / "docs" / "audit" / "2026-08"
    d.mkdir(parents=True)
    (d / "changelog.json").write_text(json.dumps({"files": {"a.ts": ["wi-1"]}}))
    (p / "a.ts").write_text("after\n")
    diff = review_units(p, _changelog(p))[0]["diff"]
    assert "-before" in diff and "+after" in diff


# the pathspec boundary

def test_approving_stages_exactly_the_named_paths(tmp_path):
    from pipeline.dashboard.review import build_review_argv
    p = _remediated(tmp_path, {"a.ts": ["wi-1"]})
    assert build_review_argv("approve", p, _changelog(p), ["a.ts"]) == \
        ["git", "add", "--", "a.ts"]


@pytest.mark.parametrize("path", [
    "../../etc/passwd",
    "src/secret.env",
    ".github/workflows/quality-gate.yml",
    "docs/client-config.yml",
])
def test_a_path_outside_the_changelog_is_refused(tmp_path, path):
    """THE security boundary. Without it, POST /review is `git add` and
    `git restore` over any path the browser names, bound to a port. The changelog is
    the record of what the agent actually touched, so it is the only legitimate
    source of a path here."""
    from pipeline.dashboard.review import build_review_argv
    p = _remediated(tmp_path, {"a.ts": ["wi-1"]})
    with pytest.raises(ValueError, match="not a file this cycle's changelog records"):
        build_review_argv("approve", p, _changelog(p), [path])


def test_a_cycle_with_no_recorded_files_can_approve_nothing(tmp_path):
    from pipeline.dashboard.review import build_review_argv
    p = _remediated(tmp_path, {})
    with pytest.raises(ValueError, match="nothing to approve"):
        build_review_argv("approve", p, _changelog(p), ["a.ts"])


def test_an_unknown_review_action_is_refused(tmp_path):
    from pipeline.dashboard.review import build_review_argv
    p = _remediated(tmp_path, {"a.ts": ["wi-1"]})
    for bad in ("merge", "commit", "push", "clean"):
        with pytest.raises(ValueError, match="unknown review action"):
            build_review_argv(bad, p, _changelog(p), ["a.ts"])


def test_rejecting_a_tracked_file_restores_it(tmp_path):
    from pipeline.dashboard.review import build_review_argv
    p = _repo(tmp_path, "acme")
    (p / "a.ts").write_text("before\n")
    subprocess.run(["git", "-C", str(p), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(p), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "x"], check=True, capture_output=True)
    d = p / "docs" / "audit" / "2026-08"
    d.mkdir(parents=True)
    (d / "changelog.json").write_text(json.dumps({"files": {"a.ts": ["wi-1"]}}))
    (p / "a.ts").write_text("after\n")
    assert build_review_argv("reject", p, _changelog(p), ["a.ts"]) == \
        ["git", "restore", "--staged", "--worktree", "--", "a.ts"]


def test_rejecting_a_new_file_is_refused_rather_than_deleting_it(tmp_path):
    """`git restore` cannot revert a create, and the honest alternative
    (`git clean -f`) silently deletes a file. A console that quietly destroys the
    agent's work on a misclick is worse than one that says no."""
    from pipeline.dashboard.review import build_review_argv
    p = _remediated(tmp_path, {"new.ts": ["wi-1"]})
    with pytest.raises(ValueError, match="delete it yourself"):
        build_review_argv("reject", p, _changelog(p), ["new.ts"])
    assert (p / "new.ts").exists()


def test_review_needs_at_least_one_file(tmp_path):
    from pipeline.dashboard.review import build_review_argv
    p = _remediated(tmp_path, {"a.ts": ["wi-1"]})
    for bad in ([], None, "a.ts"):
        with pytest.raises(ValueError, match="name the files"):
            build_review_argv("approve", p, _changelog(p), bad)


def test_review_is_empty_without_a_changelog(tmp_path):
    from pipeline.dashboard.review import review_units
    p = _repo(tmp_path, "acme")
    assert review_units(p, None) == []
    assert review_units(p, {"cycle": "2026-08"}) == []


# ── an unpushed branch is not a pushed one ───────────────────────────────────
# A fresh `cycle/` branch has no upstream, so `ahead` is 0 from the moment it is
# created. Anything deciding "has this been pushed?" from `ahead` alone reads an
# unpushed cycle as pushed — which skipped the gate step on exactly the branch that
# needed it and offered a PR straight after the commit. Caught by driving the real
# flow, not by a unit test.

def test_a_branch_with_no_upstream_is_not_reported_as_pushed(tmp_path):
    p = _committed_repo(tmp_path)
    subprocess.run(["git", "-C", str(p), "checkout", "-qb", "cycle/acme-2026-08"],
                   check=True, capture_output=True)
    st = git_state(p)
    assert st["ahead"] == 0            # no upstream to be ahead of
    assert st["upstream"] is False
    assert st["pushed"] is False       # the distinction that matters


def test_a_branch_level_with_its_upstream_is_pushed(tmp_path):
    p = _committed_repo(tmp_path)
    st = git_state(p)                  # main tracks nothing in this fixture…
    assert st["pushed"] is False
    # `@{upstream}` needs a real `remote.origin` entry, not just a
    # refs/remotes/origin/* ref — git refuses to resolve tracking against a ref that
    # belongs to no configured remote.
    for cmd in (["remote", "add", "origin", str(p)],
                ["config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"],
                ["config", "branch.main.remote", "origin"],
                ["config", "branch.main.merge", "refs/heads/main"]):
        subprocess.run(["git", "-C", str(p), *cmd], check=True, capture_output=True)
    st = git_state(p)
    assert (st["upstream"], st["ahead"], st["pushed"]) == (True, 0, True)


def test_an_unpushed_cycle_commit_is_the_pr_stage_not_the_merge_stage(tmp_path):
    """The bug this pins: with `ahead` as the test, a committed-but-unpushed cycle
    branch fell through to MERGE — telling the operator to go read a PR on GitHub
    that does not exist, and skipping the gates."""
    from pipeline.dashboard.state import next_action
    p = _repo(tmp_path, "acme")
    subprocess.run(["git", "-C", str(p), "update-ref", "refs/remotes/origin/main", "HEAD"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(p), "symbolic-ref", "refs/remotes/origin/HEAD",
                    "refs/remotes/origin/main"], check=True, capture_output=True)
    _cycle_artifacts(p, findings_json={"urls_checked": 1, "findings": []},
                     worklist_json={"items": [{"id": "wi-1"}]},
                     changelog_json={"items": [{"id": "wi-1", "status": "fixed"}],
                                     "files": {"src.ts": ["wi-1"]}})
    subprocess.run(["git", "-C", str(p), "checkout", "-qb", "cycle/acme-2026-08"],
                   check=True, capture_output=True)
    (p / "src.ts").write_text("export const x = 2\n")
    subprocess.run(["git", "-C", str(p), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(p), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "cycle"], check=True, capture_output=True)
    assert next_action(_client(p))["stage"] == "PR"


# ── the render-snapshot command, and its URL argument type ───────────────────

def test_the_snapshot_command_is_offered_with_a_url_argument():
    assert COMMANDS["render-snapshot"]["args"]["base-url"] == "url"
    # 19 must not read as the rail's "every source unreachable" generic: for this
    # command it means nothing was written, which is the whole safety property.
    assert COMMANDS["render-snapshot"]["exits"][19][0] == "refused"


def test_a_base_url_must_be_an_absolute_http_url():
    argv = build_argv("render-snapshot", "/p", {"base-url": "https://pr-34.pages.dev"})
    assert argv[-2:] == ["--base-url", "https://pr-34.pages.dev"]


@pytest.mark.parametrize("bad", [
    "-flag",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "pr-34.pages.dev",              # no scheme
    "https://x.dev; rm -rf /",
    "https://x.dev/$(whoami)",
    123,
])
def test_a_base_url_that_is_not_an_origin_is_refused(bad):
    with pytest.raises(ValueError, match="absolute http"):
        build_argv("render-snapshot", "/p", {"base-url": bad})


def test_every_declared_argument_type_has_a_builder():
    """A kind with no branch in build_argv used to fall through to the path-list
    input and send the wrong shape; an unhandled kind now raises. This asserts the
    two lists agree, so adding a type to COMMANDS cannot silently break a command."""
    handled = {"int", "path-list", "cycle", "flag", "url", "text-list"}
    for name, spec in COMMANDS.items():
        for arg, kind in spec["args"].items():
            assert kind in handled, f"{name}.{arg} declares unhandled type {kind}"


# ── provider statuses reach the screen (B-007: implemented is not wired) ─────

def test_the_cycle_bundle_carries_provider_statuses(tmp_path):
    """The findings table cannot show a skip: zero rows looks identical whether a
    provider was never asked or asked and found nothing. `page-findings.js` reads
    `doc.providers` to say which — so the bundle has to actually carry it."""
    p = _repo(tmp_path, "acme")
    d = p / "docs" / "audit" / "2026-08"
    d.mkdir(parents=True)
    (d / "findings.json").write_text(json.dumps({
        "schema": 1, "domain": "acme.com", "urls_checked": 3,
        "providers": {"serp": "skipped: BRIGHTDATA_API_KEY / BRIGHTDATA_SERP_ZONE unset",
                      "crux": "ok: 1 record(s)"},
        "findings": [],
    }))
    doc = read_artifact(p, "2026-08", "findings.json")
    assert doc["providers"]["serp"].startswith("skipped:")
    assert doc["providers"]["crux"].startswith("ok:")
    assert doc["findings"] == [], "zero findings AND a skip: the case the strip exists for"


def test_the_findings_screen_actually_renders_the_provider_strip():
    """Asserting the call site, not just the helper. The strip is dead weight if
    the page never calls it or the element it targets is missing — and no JS test
    harness exists here to catch that. renderProviders lives in app.js (shared
    with Analytics), not page-findings.js — findings.html must load app.js for
    the call site in page-findings.js to resolve at all."""
    static = Path(__file__).resolve().parents[1] / "pipeline" / "dashboard" / "static"
    app_js = (static / "app.js").read_text()
    page_js = (static / "page-findings.js").read_text()
    html = (static / "findings.html").read_text()
    assert 'id="providers"' in html, "renderProviders writes into #providers"
    assert "renderProviders(doc.providers)" in page_js, "helper defined but never called"
    assert "function renderProviders" in app_js
    assert '<script src="/static/app.js"></script>' in html
