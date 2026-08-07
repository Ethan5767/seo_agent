"""Phase 5 — the remediator. The agent writes; the measurements decide.

`run_agent` is the only thing stubbed. Everything else is real: a real git repo,
a real worklist, real snapshots, and the real tier judge — because the properties
under test are exactly "what happens when the model edits the wrong file" and
"is the file→item map an observation or a claim".
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from pipeline.audit import remediate as rem

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

CONFIG = {
    "client": "acme", "domain": "acme.com",
    "topology_class": "single-site-single-state", "states_served": ["NC"],
    "tier": 1, "text_paths": ["src/data/**/*.ts"],
}


def item(n=1, code="health.title_length", lane="NEW", blocked=False, url="/roofing/"):
    return {"id": f"wi-2026-08-{n:04d}", "finding_fp": f"fp{n}", "url": url,
            "kind": "title_out_of_band", "code": code, "lane": lane, "min_tier": 1,
            "tier_blocked": blocked, "evidence": {"context": "", "detail": "len=71"},
            "acceptance": {"check": "code_absent", "code": code}}


@pytest.fixture
def repo(tmp_path):
    """A client checkout with a config, a data file, and a planned cycle."""
    def _make(config=None, items=None):
        proj = tmp_path / "client"
        (proj / "docs" / "audit" / "2026-08").mkdir(parents=True)
        (proj / "src" / "data").mkdir(parents=True)
        (proj / "docs" / "client-config.yml").write_text(
            yaml.safe_dump(config or CONFIG, sort_keys=False))
        (proj / "src" / "data" / "services.ts").write_text("export const title = 'x'\n")
        (proj / "src" / "components").mkdir(parents=True)
        (proj / "src" / "components" / "Hero.tsx").write_text("export const Hero = 1\n")
        (proj / "docs" / "audit" / "2026-08" / "worklist.json").write_text(json.dumps(
            {"schema": "site-plan-worklist/1", "cycle": "2026-08", "domain": "acme.com",
             "tier": (config or CONFIG).get("tier"), "items": items or [item()]}))
        for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@e.com"],
                     ["config", "user.name", "t"], ["add", "-A"], ["commit", "-qm", "base"]):
            subprocess.run(["git", "-C", str(proj), *args], check=True, capture_output=True)
        return proj
    return _make


def agent_that(edits):
    """A stub writer: {relative path: new text} applied on invocation."""
    def _run(project, prompt, model, timeout):
        for rel, text in edits.items():
            p = Path(project) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        return True, "FIXED", 0.01
    return _run


# ── selection ────────────────────────────────────────────────────────────────

def test_tier_blocked_items_never_reach_the_agent():
    wl = {"items": [item(1), item(2, blocked=True)]}
    assert [i["id"] for i in rem.selectable(wl, {})] == ["wi-2026-08-0001"]


def test_regressions_are_worked_first():
    """With a cap on items, the lane that says a fix did not hold must not be the
    part that gets cut."""
    wl = {"items": [item(1, lane="PERSISTING"), item(2, lane="NEW"),
                    item(3, lane="REGRESSION")]}
    assert [i["lane"] for i in rem.selectable(wl, {})] == \
        ["REGRESSION", "NEW", "PERSISTING"]


# ── the run ──────────────────────────────────────────────────────────────────

def test_an_in_tier_fix_is_recorded_against_the_file_it_actually_changed(repo, monkeypatch):
    proj = repo()
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/services.ts": "export const title = 'a much better title here'\n"}))
    log, code = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    assert code == 1
    assert log["items"][0]["status"] == "fixed"
    assert log["items"][0]["files"] == ["src/data/services.ts"]
    assert log["files"] == {"src/data/services.ts": ["wi-2026-08-0001"]}


def test_the_map_is_measured_not_claimed(repo, monkeypatch):
    """The stub says FIXED and edits a DIFFERENT file than the one it names. The
    changelog must record what git saw, not what the model said."""
    proj = repo()
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/other.ts": "export const x = 2\n"}))
    log, code = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    # a CREATE under text_paths is out of authority at T1, so this is also refused
    assert log["items"][0]["files"] == ["src/data/other.ts"]
    assert code == rem.REFUSED_EXIT


def test_an_out_of_tier_edit_refuses_and_stops_the_run(repo, monkeypatch):
    proj = repo(items=[item(1), item(2)])
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/components/Hero.tsx": "export const Hero = 2\n"}))
    log, code = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    assert code == rem.REFUSED_EXIT
    assert log["items"][0]["status"] == "refused"
    assert "not permitted at T1" in log["items"][0]["note"]
    assert log["attempted"] == 1, "the run stops rather than keep writing"
    assert log["stopped"]


def test_a_run_that_changed_nothing_is_not_a_fix(repo, monkeypatch):
    proj = repo()
    monkeypatch.setattr(rem, "run_agent", lambda *a: (True, "NO CHANGE no data file", 0.0))
    log, code = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    assert code == 0
    assert log["items"][0]["status"] == "no_change"
    assert log["items"][0]["files"] == []


def test_an_agent_error_is_recorded_not_swallowed(repo, monkeypatch):
    proj = repo()
    monkeypatch.setattr(rem, "run_agent", lambda *a: (False, "timed out after 60s", 0.0))
    log, code = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    assert log["items"][0]["status"] == "error"
    assert "timed out" in log["items"][0]["note"]


def test_max_items_stops_cleanly_and_says_what_is_left(repo, monkeypatch):
    proj = repo(items=[item(1), item(2), item(3)])
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/services.ts": "export const title = 'better'\n"}))
    log, code = rem.remediate(proj, None, 1, 20, "sonnet", 60, False)
    assert log["attempted"] == 1
    assert "2 item(s) left" in log["stopped"]


def test_max_files_stops_cleanly(repo, monkeypatch):
    proj = repo(items=[item(1), item(2)])
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/services.ts": "export const title = 'better'\n"}))
    log, code = rem.remediate(proj, None, 10, 1, "sonnet", 60, False)
    assert log["attempted"] == 1
    assert "max-files" in log["stopped"]


def test_t3_may_touch_a_component(repo, monkeypatch):
    proj = repo(config=dict(CONFIG, tier=3))
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/components/Hero.tsx": "export const Hero = 2\n"}))
    log, code = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    assert code == 1 and log["items"][0]["status"] == "fixed"


def test_t2_may_create_a_page_and_wire_the_registry(repo, monkeypatch):
    cfg = dict(CONFIG, tier=2, content={"location": "src/content/blog/",
                                        "registry": ["src/data/posts.ts"], "format": "mdx"})
    proj = repo(config=cfg, items=[dict(item(1, code="health.thin_content"), min_tier=2)])
    (proj / "src" / "data" / "posts.ts").write_text("export const posts = []\n")
    subprocess.run(["git", "-C", str(proj), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(proj), "commit", "-qm", "posts"], check=True,
                   capture_output=True)
    monkeypatch.setattr(rem, "run_agent", agent_that({
        "src/content/blog/new-roof.mdx": "# New Roof\n",
        "src/data/posts.ts": "export const posts = ['new-roof']\n"}))
    log, code = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    assert code == 1, log["items"][0]["note"]
    assert sorted(log["items"][0]["files"]) == \
        ["src/content/blog/new-roof.mdx", "src/data/posts.ts"]


def test_no_tier_declared_means_every_edit_is_refused(repo, monkeypatch):
    cfg = {k: v for k, v in CONFIG.items() if k != "tier"}
    proj = repo(config=cfg)
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/services.ts": "export const title = 'better'\n"}))
    log, code = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    assert code == rem.REFUSED_EXIT
    assert "no `tier:` declared" in log["items"][0]["note"]


# ── the prompt ───────────────────────────────────────────────────────────────

def test_the_prompt_states_the_authority_and_the_deny_floor():
    from pipeline.lib.common import client_profile
    prof = client_profile(CONFIG)
    prompt = rem.build_prompt(item(), prof, "DOCTRINE")
    assert "TIER 1" in prompt
    assert "src/data/**/*.ts" in prompt
    assert ".github/**" in prompt
    assert "docs/client-config.yml" in prompt
    assert "wi-2026-08-0001" in prompt


def test_dry_run_writes_nothing(repo, monkeypatch, capsys):
    proj = repo()
    monkeypatch.setattr(rem, "run_agent", agent_that({"src/data/services.ts": "boom\n"}))
    log, code = rem.remediate(proj, None, 10, 20, "sonnet", 60, True)
    assert code == 0
    assert (proj / "src" / "data" / "services.ts").read_text() == "export const title = 'x'\n"
    assert not (proj / "docs" / "audit" / "2026-08" / "changelog.json").exists()


def test_no_worklist_is_a_usage_error(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "client-config.yml").write_text(yaml.safe_dump(CONFIG))
    with pytest.raises(rem.RemediateError, match="run wf-site-plan first"):
        rem.remediate(tmp_path, None, 10, 20, "sonnet", 60, False)


# ── the doctrine the prompt carries ──────────────────────────────────────────

def test_the_skill_ships_the_rule_the_whole_gate_suite_rests_on():
    text = rem.read_doctrine()
    assert "Derivation only, never invent" in text
    assert "removed, not reworded" in text


def test_the_prompt_goes_on_stdin_not_argv(monkeypatch, capsys):
    """The prompt opens with a markdown document, and a leading `---` is parsed by
    the CLI's option parser as a malformed flag. Found by the first live run; no
    test that stubs `run_agent` can see it, so this one stubs `subprocess.Popen`."""
    seen = {}

    class FakeStdin:
        def write(self, data):
            seen["input"] = data

        def close(self):
            pass

    class FakeStdout:
        def __iter__(self):
            yield '{"type":"assistant","message":{"content":[{"type":"text","text":"working"}]}}'
            yield '{"type":"result","subtype":"success","result":"FIXED","total_cost_usd":0.01}'

    class FakeProc:
        def __init__(self):
            self.stdin = FakeStdin()
            self.stdout = FakeStdout()

        def wait(self):
            return 0

        def kill(self):
            pass

    def fake_popen(argv, **kw):
        seen["argv"] = argv
        assert kw.get("stdin") is subprocess.PIPE
        return FakeProc()

    monkeypatch.setattr(rem.subprocess, "Popen", fake_popen)
    ok, note, cost = rem.run_agent("/p", "---\nfrontmatter\n---\nbody", "sonnet", 60)
    assert ok and note == "FIXED" and cost == 0.01
    assert seen["input"].startswith("---")
    assert not any(a.startswith("---") for a in seen["argv"])
    assert "--output-format" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--output-format") + 1] == "stream-json"
    assert "--verbose" in seen["argv"]
    # Live tee: both stream events must have reached stdout while the agent ran.
    out = capsys.readouterr().out
    assert '"type":"assistant"' in out
    assert '"type":"result"' in out


def test_a_streamed_error_result_is_not_ok(monkeypatch, capsys):
    class FakeStdin:
        def write(self, data): pass
        def close(self): pass

    class FakeStdout:
        def __iter__(self):
            yield '{"type":"result","subtype":"error","is_error":true,"result":"no config"}'

    class FakeProc:
        stdin = FakeStdin()
        stdout = FakeStdout()
        def wait(self): return 1
        def kill(self): pass

    monkeypatch.setattr(rem.subprocess, "Popen", lambda *a, **k: FakeProc())
    ok, note, cost = rem.run_agent("/p", "body", "sonnet", 60)
    assert not ok and "no config" in note and cost == 0.0


def test_the_skill_frontmatter_is_not_sent_to_the_writer():
    text = rem.read_doctrine()
    assert not text.startswith("---")
    assert "description: Use when fixing" not in text
    assert text.lstrip().startswith("# Site Remediation")


# ── B-013: a re-run resumes, and never destroys the first run's record ───────
# The docstring promised "the remaining items keep their place in the worklist for
# the next run" and the code did the opposite: selectable() rebuilt the queue from
# worklist.json alone so run two re-attempted the same first N, while main() wrote
# changelog.json wholesale so run two's record replaced run one's.

def write_changelog(proj, doc):
    (Path(proj) / "docs" / "audit" / "2026-08" / "changelog.json").write_text(
        json.dumps(doc))


def test_a_rerun_skips_what_the_changelog_records_as_fixed(repo, monkeypatch, capsys):
    proj = repo(items=[item(1), item(2), item(3)])
    write_changelog(proj, {"cycle": "2026-08", "items": [
        {"id": "wi-2026-08-0001", "finding_fp": "fp1", "status": "fixed"}]})
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/services.ts": "export const title = 'better'\n"}))
    log, _ = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    worked = [i["id"] for i in log["items"] if i["status"] != "fixed" or True]
    assert "wi-2026-08-0001" in worked            # carried over from the prior run
    assert "resume" in capsys.readouterr().out
    # It was NOT re-attempted: exactly the two unfixed items ran this time.
    assert log["queued"] == 2


def test_a_status_other_than_fixed_is_retried(repo, monkeypatch):
    # error / no_change / refused all mean "not done". Skipping them would strand
    # an item that failed for a transient reason.
    proj = repo(items=[item(1), item(2)])
    write_changelog(proj, {"cycle": "2026-08", "items": [
        {"id": "wi-2026-08-0001", "finding_fp": "fp1", "status": "error"},
        {"id": "wi-2026-08-0002", "finding_fp": "fp2", "status": "no_change"}]})
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/services.ts": "export const title = 'better'\n"}))
    log, _ = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    assert log["queued"] == 2


def test_the_second_run_merges_rather_than_destroying_the_first(repo, monkeypatch):
    proj = repo(items=[item(1), item(2)])
    write_changelog(proj, {"cycle": "2026-08", "cost_usd": 2.5, "runs": 1, "items": [
        {"id": "wi-2026-08-0001", "finding_fp": "fp1", "status": "fixed",
         "note": "run one"}],
        "files": {"src/data/old.ts": ["wi-2026-08-0001"]}})
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/services.ts": "export const title = 'better'\n"}))
    log, _ = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    ids = [i["id"] for i in log["items"]]
    # Run one's reviewed evidence survives, and run two's is added to it.
    assert ids == ["wi-2026-08-0001", "wi-2026-08-0002"]
    assert log["items"][0]["note"] == "run one"
    assert log["runs"] == 2
    assert log["cost_usd"] > 2.5                 # cumulative, reconcilable with the bill
    assert "src/data/old.ts" in log["files"]     # run one's file map is not dropped
    assert "src/data/services.ts" in log["files"]


def test_a_fresh_attempt_replaces_its_own_earlier_entry(repo, monkeypatch):
    proj = repo(items=[item(1)])
    write_changelog(proj, {"cycle": "2026-08", "items": [
        {"id": "wi-2026-08-0001", "status": "error", "note": "old"}]})
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/services.ts": "export const title = 'better'\n"}))
    log, _ = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    entries = [i for i in log["items"] if i["id"] == "wi-2026-08-0001"]
    assert len(entries) == 1                     # one id, one entry
    assert entries[0]["status"] == "fixed"


def test_a_dry_run_never_touches_the_record_of_runs_that_wrote(repo, monkeypatch):
    proj = repo(items=[item(1), item(2)])
    write_changelog(proj, {"cycle": "2026-08", "cost_usd": 2.5, "runs": 1, "items": [
        {"id": "wi-2026-08-0001", "finding_fp": "fp1", "status": "fixed"}]})
    log, code = rem.remediate(proj, None, 10, 20, "sonnet", 60, True)
    assert code == 0
    assert log["runs"] == 0
    assert log["cost_usd"] == 0.0
    assert all(i["status"] == "dry-run" for i in log["items"])


def test_an_unreadable_changelog_is_said_out_loud_not_silently_obeyed(repo, monkeypatch, capsys):
    proj = repo(items=[item(1)])
    (Path(proj) / "docs" / "audit" / "2026-08" / "changelog.json").write_text("{ truncated")
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/services.ts": "export const title = 'better'\n"}))
    rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    assert "will not parse" in capsys.readouterr().err


def test_the_changelog_carries_the_fingerprint_of_the_finding_it_fixed(repo, monkeypatch):
    # Without finding_fp, mapping a fixed item back to its finding means matching
    # on (url, code) — ambiguous the moment one page has two findings of one code,
    # which is the common case (img_alt_missing), not the exotic one.
    proj = repo(items=[item(1)])
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/services.ts": "export const title = 'better'\n"}))
    log, _ = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    assert log["items"][0]["finding_fp"] == "fp1"


# ── B-020: resume survives a renumbering ─────────────────────────────────────

def test_a_remeasure_that_renumbers_ids_still_skips_what_was_fixed(repo, monkeypatch):
    """Work item ids are positional (`wi-<cycle>-<idx>`), so re-measuring a live
    site renumbers them: on lee-series-web three new SERP findings shifted 19 of
    20 fixed ids onto unrelated findings. Keying resume on `id` would have
    skipped nineteen UNFIXED items as done while re-attempting the fixed ones.
    The fingerprint is the identity that survives."""
    # The changelog fixed fp2 under its old id. After the re-measure fp2 sits at
    # a different index, and the old id now belongs to fp1.
    proj = repo(items=[item(1), item(2)])
    write_changelog(proj, {"cycle": "2026-08", "items": [
        {"id": "wi-2026-08-0002", "finding_fp": "fp2", "status": "fixed"}]})
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/services.ts": "export const title = 'better'\n"}))
    log, _ = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    assert log["queued"] == 1, "only the unfixed finding should be queued"
    worked = [i["id"] for i in log["items"] if i.get("finding_fp") == "fp1"]
    assert worked == ["wi-2026-08-0001"]


def test_an_item_with_no_fingerprint_is_attempted_not_skipped(repo, monkeypatch):
    """A changelog from before the fingerprint was carried must not silently
    match everything. Attempting twice costs money; skipping a real finding and
    calling it fixed puts a falsehood in the artifact."""
    proj = repo(items=[item(1)])
    write_changelog(proj, {"cycle": "2026-08", "items": [
        {"id": "wi-2026-08-0001", "status": "fixed"}]})     # no finding_fp
    monkeypatch.setattr(rem, "run_agent", agent_that(
        {"src/data/services.ts": "export const title = 'better'\n"}))
    log, _ = rem.remediate(proj, None, 10, 20, "sonnet", 60, False)
    assert log["queued"] == 1
