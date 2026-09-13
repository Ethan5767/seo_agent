from tests import e2e_fixture as fx
from pipeline.scanner import run as scan_run


def _prep(tmp_path, monkeypatch):
    from pipeline.audit import measure
    project = fx.build_fixture(tmp_path / "client")
    curl, cs = fx.serve(project)
    monkeypatch.setattr(measure, "curl", curl)
    monkeypatch.setattr(measure, "curl_status", cs)
    return project


def test_model_b_fixes_and_decides_auto(tmp_path, monkeypatch):
    project = _prep(tmp_path, monkeypatch)
    from pipeline.audit import remediate as rem
    monkeypatch.setattr(rem, "run_agent", fx.agent_that_fixes(project))
    out = scan_run.run_cycle(project, fx.URL, model="B")
    assert out["model"] == "B"
    assert any(i["status"] == "fixed" for i in out["changelog"]["items"])
    assert out["decision"]["action"] in ("AUTO", "HUMAN")
    assert fx.GOOD_TITLE in out["diff"]


def test_model_a_writes_brief_and_leaves_tree_clean(tmp_path, monkeypatch):
    project = _prep(tmp_path, monkeypatch)
    out = scan_run.run_cycle(project, fx.URL, model="A")
    assert out["model"] == "A"
    assert out["worklist"], "model A must surface the planned work"
    assert "Fix:" in out["brief"]
    # the code was never touched
    import subprocess
    status = subprocess.run(["git", "-C", str(project), "status", "--porcelain", "out/"],
                            capture_output=True, text=True).stdout
    assert status.strip() == "", "Model A must not edit the site code"
