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
