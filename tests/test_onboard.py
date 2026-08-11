"""onboard.py — the six onboarding commands, sequenced and their exits translated.

Hermetic: `onboard.run` is stubbed everywhere, so no step actually executes and
no network is touched. What is worth testing is not that the steps run — it is
that a stop is reported as RESUMABLE rather than failed, and that a step which
stopped the run never lets the steps after it execute. An onboarding that
carries on past a failed preflight measures a site it was told not to trust.
"""
from __future__ import annotations

import subprocess

import pytest

from pipeline.audit import onboard as o


def result(code=0, stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr="")


@pytest.fixture
def repo(make_project):
    """A project that is also a git checkout — step 1 refuses a bare directory."""
    p = make_project(config=dict(client="acme", domain="acmeroofing.com", tier=1,
                                 repo={"framework": "nextjs-app-router"}))
    (p / ".git").mkdir()
    return p


@pytest.fixture
def calls(monkeypatch):
    """Record every step, and let a test dictate what any of them returns."""
    seen, codes = [], {}

    def fake_run(argv, cwd=None, capture=False):
        seen.append(argv[0])
        if argv[0] == "gh":
            return result(0, "WRITE")
        return result(codes.get(argv[0], 0))

    monkeypatch.setattr(o, "run", fake_run)
    monkeypatch.setattr(o.shutil, "which", lambda name: f"/usr/bin/{name}")
    return type("Calls", (), {"seen": seen, "codes": codes})()


# ── step 1: reading what the operator typed ──────────────────────────────────

@pytest.mark.parametrize("given, expected", [
    ("acme/roofing-site", "acme/roofing-site"),
    ("git@github.com:acme/roofing-site.git", "acme/roofing-site"),
    ("https://github.com/acme/roofing-site", "acme/roofing-site"),
    ("https://github.com/acme/roofing-site.git", "acme/roofing-site"),
    ("https://github.com/acme/roofing-site/", "acme/roofing-site"),
])
def test_repo_slug_reads_every_form_a_client_will_send(given, expected):
    assert o.repo_slug(given) == expected


def test_an_existing_path_is_never_treated_as_a_slug(repo):
    assert o.repo_slug(str(repo)) is None


def test_a_directory_that_is_not_a_checkout_is_refused(tmp_path):
    (tmp_path / "not-a-repo").mkdir()
    with pytest.raises(o.OnboardError, match="not a git checkout"):
        o.checkout(str(tmp_path / "not-a-repo"), tmp_path, skip_clone=True)


# ── step 2: we are a guest, so access is checked, not assumed ────────────────

def test_write_access_is_reported(repo, calls, capsys):
    assert o.check_access(repo) is True
    assert "we can open a PR" in capsys.readouterr().out


def test_read_only_access_warns_but_does_not_stop_the_run(repo, monkeypatch, capsys):
    monkeypatch.setattr(o.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(o, "run", lambda *a, **k: result(0, "READ"))
    assert o.check_access(repo) is False
    out = capsys.readouterr().out
    assert "NEVER open a PR" in out
    # Read-only is a warning about DELIVERY, not about measurement. If this ever
    # becomes fatal, a client who has not yet upgraded our invite gets no report.
    assert "STOPPED" not in out


# ── the sequence, and where it stops ─────────────────────────────────────────

def test_a_clean_onboarding_runs_every_step_in_order(repo, calls):
    assert o.onboard(str(repo), "acmeroofing.com", repo.parent, True, False) == 0
    assert calls.seen == ["gh", "wf-bootstrap-config", "wf-preflight", "wf-client-profile",
                          "wf-scaffold-client-docs", "wf-site-health", "wf-site-plan"]


def test_preflight_todos_stop_the_run_as_resumable_and_nothing_downstream_runs(repo, calls, capsys):
    calls.codes["wf-preflight"] = 12
    # Exit 1, not 3: the operator has to hold an interview, not debug a failure.
    assert o.onboard(str(repo), "acmeroofing.com", repo.parent, True, False) == 1
    out = capsys.readouterr().out
    assert "the interview step" in out
    assert "re-run this exact command" in out
    assert "wf-site-health" not in calls.seen


def test_an_incoherent_config_stops_before_anything_is_measured(repo, calls):
    calls.codes["wf-client-profile"] = 5
    assert o.onboard(str(repo), "acmeroofing.com", repo.parent, True, False) == 1
    assert "wf-scaffold-client-docs" not in calls.seen


def test_a_worklist_written_is_a_finished_onboarding(repo, calls, capsys):
    # wf-site-plan exits 1 when it writes a worklist. That is the SUCCESS case,
    # and reading it as a failure would stop every client that has findings —
    # which is every client.
    calls.codes["wf-site-plan"] = 1
    assert o.onboard(str(repo), "acmeroofing.com", repo.parent, True, False) == 0
    assert "[READY]" in capsys.readouterr().out


def test_an_unmeasurable_site_stops_before_planning(repo, calls):
    calls.codes["wf-site-health"] = 19
    assert o.onboard(str(repo), "acmeroofing.com", repo.parent, True, False) == 1
    assert "wf-site-plan" not in calls.seen


def test_dry_run_touches_nothing_past_the_access_check(repo, calls):
    assert o.onboard(str(repo), "acmeroofing.com", repo.parent, True, True) == 0
    assert calls.seen == ["gh"]


# ── the tier the operator declared reaches bootstrap-config ──────────────────
# The tier is the single most consequential field on the ADD CLIENT form. A tier
# that is collected and then dropped on the floor produces a client whose config
# says T1 while the operator believes it says T3.

def test_the_declared_tier_is_passed_to_bootstrap(repo, monkeypatch):
    seen = {}

    def fake_run(argv, cwd=None, capture=False):
        if argv[0] == "gh":
            return result(0, "WRITE")
        if argv[0] == "wf-bootstrap-config":
            seen["argv"] = argv
        return result(0)

    monkeypatch.setattr(o, "run", fake_run)
    monkeypatch.setattr(o.shutil, "which", lambda name: f"/usr/bin/{name}")
    o.onboard(str(repo), "acmeroofing.com", repo.parent, True, False, tier=2,
              content_location="src/content/blog/",
              content_registry=["src/data/posts.ts"])
    argv = seen["argv"]
    assert argv[argv.index("--tier") + 1] == "2"
    assert argv[argv.index("--content-location") + 1] == "src/content/blog/"
    assert argv[argv.index("--content-registry") + 1] == "src/data/posts.ts"


def test_a_re_onboard_actually_applies_the_new_tier(repo, monkeypatch):
    """B-032: `wf-onboard --tier 3` on an ALREADY-onboarded client silently kept
    the old tier and reported success.

    `wf-bootstrap-config` only writes the tier into an existing config when
    `--add-tier` is passed; without it, it prints "Config already exists" and
    exits 0. onboard read that 0 as done. The operator saw a clean run, the
    worklist kept saying "78 above tier", and the config still said `tier: 1`.
    Caught on lee-series-web, which is the only shape that reproduces it: a
    client whose config is already on disk.
    """
    seen = {}

    def fake_run(argv, cwd=None, capture=False):
        if argv[0] == "gh":
            return result(0, "WRITE")
        if argv[0] == "wf-bootstrap-config":
            seen["argv"] = argv
        return result(0)

    monkeypatch.setattr(o, "run", fake_run)
    monkeypatch.setattr(o.shutil, "which", lambda name: f"/usr/bin/{name}")
    o.onboard(str(repo), "acmeroofing.com", repo.parent, True, False, tier=3)
    assert "--add-tier" in seen["argv"], (
        "without --add-tier the tier is dropped on any config that already exists"
    )


def test_an_ignored_tier_raise_stops_the_run_instead_of_reporting_ready(repo, calls, capsys):
    """B-032: the `repo` fixture already declares tier 1, so asking for 3 is the
    exact lee-series-web case. `add_tier` declines an existing tier and exits 0,
    so without this guard the run sailed on to measure, plan and a [READY] banner
    while the worklist still tier-blocked everything above T1."""
    assert o.onboard(str(repo), "acmeroofing.com", repo.parent, True, False, tier=3) == 1
    err = capsys.readouterr().err
    assert "you asked for tier 3" in err
    assert "still declares tier 1" in err
    # Nothing downstream may run: a worklist planned at the wrong tier is worse
    # than no worklist, because it reads as an answer.
    assert "wf-preflight" not in calls.seen
    assert "wf-site-health" not in calls.seen


def test_a_re_run_without_the_flag_never_trips_the_tier_guard(repo, calls):
    """The guard keys on an EXPLICIT --tier. Re-running a T2/T3 client with no
    flag at all must not stop just because argparse would have defaulted to 1."""
    assert o.onboard(str(repo), "acmeroofing.com", repo.parent, False, False) == 0
    assert "wf-site-health" in calls.seen


def test_tier_defaults_to_one_and_says_so(repo, calls):
    o.onboard(str(repo), "acmeroofing.com", repo.parent, True, False)
    # No content flags at all: T1 has nowhere to create, so passing an empty
    # location would be writing a `content:` block that grants nothing.
    assert "--content-location" not in calls.seen


def test_a_refused_tier_stops_the_run_resumably(repo, calls, capsys):
    # bootstrap_config exits 4 on a tier it will not write (T2 with no content
    # location). Exit 1, not 3: the operator re-runs with the field filled in.
    calls.codes["wf-bootstrap-config"] = 4
    assert o.onboard(str(repo), "acmeroofing.com", repo.parent, True, False) == 1
    assert "tier could not be written" in capsys.readouterr().out
    assert "wf-preflight" not in calls.seen


# ── B-014: the scaffold has to be committed, and only onboard can do it ──────

def git_repo(tmp_path):
    """A real git repo with one commit on `main` and an origin/HEAD ref, because
    commit_scaffold asks git real questions and a fake .git directory answers none
    of them."""
    import subprocess as sp
    p = tmp_path / "client"
    (p / "docs").mkdir(parents=True)
    for cmd in (["init", "-b", "main"], ["config", "user.email", "t@t.t"],
                ["config", "user.name", "t"]):
        sp.run(["git", "-C", str(p), *cmd], check=True, capture_output=True)
    (p / "README.md").write_text("x\n")
    sp.run(["git", "-C", str(p), "add", "-A"], check=True, capture_output=True)
    sp.run(["git", "-C", str(p), "commit", "-m", "init"], check=True, capture_output=True)
    return p


def scaffold(p):
    (p / "docs" / "client-config.yml").write_text("client: acme\ntier: 1\n")
    (p / "docs" / "INDEX.md").write_text("# Index\n")
    (p / "docs" / "seo-progress.md").write_text("# Progress\n")
    (p / "docs" / "seo-work-log.md").write_text("# Log\n")
    for d in ("cycle-logs", "intake-archive"):
        (p / "docs" / d).mkdir()
        (p / "docs" / d / ".gitkeep").write_text("")


def tracked(p):
    import subprocess as sp
    r = sp.run(["git", "-C", str(p), "show", "--name-only", "--format=", "HEAD"],
               capture_output=True, text=True)
    return set(r.stdout.split())


def test_the_scaffold_is_committed_to_the_default_branch(tmp_path, monkeypatch):
    p = git_repo(tmp_path)
    scaffold(p)
    monkeypatch.setattr(o, "run", lambda argv, cwd=None, capture=False:
                        __import__("subprocess").run(argv, cwd=cwd, capture_output=True, text=True))
    o.commit_scaffold(p)
    got = tracked(p)
    assert "docs/client-config.yml" in got
    assert "docs/INDEX.md" in got
    assert "docs/cycle-logs/.gitkeep" in got
    # Nothing left over: the operator reaching the Git screen must see ONLY the
    # cycle artifacts measure/plan then write.
    import subprocess as sp
    assert sp.run(["git", "-C", str(p), "status", "--porcelain"],
                  capture_output=True, text=True).stdout.strip() == ""


def test_the_scaffold_commit_takes_nothing_it_did_not_write(tmp_path, monkeypatch):
    p = git_repo(tmp_path)
    scaffold(p)
    # An unrelated dirty file. `git add -A` would sweep it into a commit the
    # operator never asked for; the named pathspec must not.
    (p / "src.ts").write_text("export const x = 1\n")
    monkeypatch.setattr(o, "run", lambda argv, cwd=None, capture=False:
                        __import__("subprocess").run(argv, cwd=cwd, capture_output=True, text=True))
    o.commit_scaffold(p)
    assert "src.ts" not in tracked(p)
    import subprocess as sp
    assert "src.ts" in sp.run(["git", "-C", str(p), "status", "--porcelain"],
                              capture_output=True, text=True).stdout


def test_the_scaffold_is_never_committed_on_a_cycle_branch(tmp_path, capsys):
    # This is the whole point of B-014: on a cycle branch these six paths are
    # creates that tier_check refuses with exit 17. Committing them there is the
    # bug, not the fix.
    import subprocess as sp
    p = git_repo(tmp_path)
    sp.run(["git", "-C", str(p), "checkout", "-b", "cycle/acme-2026-08"],
           check=True, capture_output=True)
    scaffold(p)
    o.commit_scaffold(p)
    assert tracked(p) == {"README.md"}
    assert "NOT committing" in capsys.readouterr().out


def test_a_second_onboarding_does_not_fail_on_the_first_ones_commit(tmp_path, monkeypatch, capsys):
    p = git_repo(tmp_path)
    scaffold(p)
    monkeypatch.setattr(o, "run", lambda argv, cwd=None, capture=False:
                        __import__("subprocess").run(argv, cwd=cwd, capture_output=True, text=True))
    o.commit_scaffold(p)
    o.commit_scaffold(p)                      # onboarding is re-runnable
    assert "already committed" in capsys.readouterr().out


def test_a_humans_edit_to_a_scaffold_path_is_not_committed_for_them(tmp_path, monkeypatch, capsys):
    p = git_repo(tmp_path)
    scaffold(p)
    monkeypatch.setattr(o, "run", lambda argv, cwd=None, capture=False:
                        __import__("subprocess").run(argv, cwd=cwd, capture_output=True, text=True))
    o.commit_scaffold(p)
    # The operator resolves the interview TODOs. That edit is theirs to commit.
    (p / "docs" / "client-config.yml").write_text("client: acme\ntier: 1\nindustry: real\n")
    o.commit_scaffold(p)
    assert "not this run's to commit" in capsys.readouterr().out
