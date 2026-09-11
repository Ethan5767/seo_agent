"""Dry-run handler — the guard branches (named errors, never a silent empty) and
the stdout→prompts parser. No subprocess/Claude here; the real dry-run is
exercised separately and edits nothing."""
from pipeline.scanner.server import (
    handle_remediate_dryrun, parse_dryrun_output,
    handle_remediate_apply, summarize_changelog,
)


def wi(code):
    return {"code": code, "what": "w", "fix": "f", "severity": "warn", "priority": 1, "status": "NEW"}


def test_no_repo_named_error():
    out = handle_remediate_dryrun({"worklist": [wi("health.title_missing")]})
    assert out["ok"] is False and "repo" in out["error"].lower()


def test_remote_repo_rejected(tmp_path):
    out = handle_remediate_dryrun({"repo": "owner/repo", "worklist": []})
    assert out["ok"] is False and "local checkout" in out["error"]


def test_not_onboarded_named(tmp_path):
    # a real dir but no docs/client-config.yml → prereq named, no subprocess run
    out = handle_remediate_dryrun({"repo": str(tmp_path), "worklist": [wi("health.title_missing")]})
    assert out["ok"] is False and "client-config.yml" in out["error"]


def test_onboarded_but_nothing_bridged_writes_worklist(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "client-config.yml").write_text("tier: 1\n")
    # only unbridgeable codes → no subprocess, but the bridged (empty) worklist is written
    out = handle_remediate_dryrun({"repo": str(tmp_path), "url": "https://ex.com/",
                                   "worklist": [wi("aeo.statistics")], "cycle": "2026-09"})
    assert out["ok"] is True and out["items"] == []
    assert out["unbridged"] and out["unbridged"][0]["code"] == "aeo.statistics"
    assert (tmp_path / "docs" / "audit" / "2026-09" / "worklist.json").is_file()


def test_bad_cycle_rejected_no_traversal(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "client-config.yml").write_text("tier: 1\n")
    out = handle_remediate_dryrun({"repo": str(tmp_path), "url": "https://ex.com/",
                                   "worklist": [wi("health.title_missing")], "cycle": "../../etc"})
    assert out["ok"] is False and "cycle" in out["error"].lower()
    # nothing written outside docs/audit
    assert not (tmp_path.parent / "etc").exists()


def test_parse_dryrun_output():
    stdout = (
        "[resume] 0 done\n"
        "\n===== wi-2026-09-0001 — health.title_missing on https://ex.com/ =====\n"
        "You are fixing the title.\nMake it 30-60 chars.\n"
        "\n===== wi-2026-09-0002 — health.h1_count on https://ex.com/a =====\n"
        "Fix the H1 count.\n"
    )
    items = parse_dryrun_output(stdout)
    assert len(items) == 2
    assert items[0]["header"] == "wi-2026-09-0001 — health.title_missing on https://ex.com/"
    assert "fixing the title" in items[0]["prompt"]
    assert items[1]["header"].endswith("on https://ex.com/a")


def test_parse_dryrun_output_empty():
    assert parse_dryrun_output("no items printed") == []


# ── apply (the real edit-run) — guards only; never spawns Claude here ─────────

def test_apply_requires_confirm():
    out = handle_remediate_apply({"repo": "/whatever", "worklist": [wi("health.title_missing")]})
    assert out["ok"] is False and "confirm" in out["error"].lower()


def test_apply_refuses_without_claude(monkeypatch):
    # confirm given, but no `claude` on PATH → named refusal, no run
    monkeypatch.setattr("pipeline.scanner.server.shutil.which", lambda _: None)
    out = handle_remediate_apply({"confirm": True, "repo": "/whatever",
                                  "worklist": [wi("health.title_missing")]})
    assert out["ok"] is False and "claude" in out["error"].lower()


def test_apply_confirmed_but_repo_invalid(monkeypatch):
    # claude present, confirmed → falls through to the shared prep guards
    monkeypatch.setattr("pipeline.scanner.server.shutil.which", lambda _: "/usr/bin/claude")
    out = handle_remediate_apply({"confirm": True, "repo": "owner/repo",
                                  "worklist": [wi("health.title_missing")]})
    assert out["ok"] is False and "local checkout" in out["error"]


def test_summarize_changelog():
    cl = {"attempted": 2, "queued": 0, "stopped": None, "cost_usd": 0.12,
          "files": {"src/a.tsx": ["wi-1"]},
          "items": [
              {"id": "wi-1", "code": "health.title_missing", "url": "https://ex.com/",
               "status": "fixed", "note": "set title", "files": ["src/a.tsx"]},
              {"id": "wi-2", "code": "health.h1_count", "url": "https://ex.com/a",
               "status": "no_change", "note": "refused"},
          ]}
    out = summarize_changelog(cl)
    assert out["attempted"] == 2 and out["cost_usd"] == 0.12
    assert len(out["items"]) == 2
    assert out["items"][0]["status"] == "fixed" and out["items"][0]["files"] == ["src/a.tsx"]
    assert out["items"][1]["files"] == []   # missing files → [] not crash


def test_summarize_changelog_empty():
    out = summarize_changelog({})
    assert out["items"] == [] and out["files"] == {}
