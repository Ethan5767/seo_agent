"""Phased execution — tools run cheapest-first in a fixed phase order, with
phase markers streamed to the UI."""
from pipeline.scanner import server, onpage_audit


def fake_fetch(url):
    return ("<html><head><title>T</title></head><body><h1>H</h1><main>x</main></body></html>", 200, "", None)


def _run(selected, monkeypatch, **kw):
    # keep every phase offline: DataForSEO + source fetch stubbed
    monkeypatch.setattr(onpage_audit, "site_audit_full", lambda d, mp: ([], "ok", 0.0))
    monkeypatch.setattr(server.source_audit, "fetch_repo_files", lambda r, t: {})
    monkeypatch.setattr(server.source_audit, "fetch_repo_tree", lambda r, t: [])
    order, phases = [], []

    def cap(name, state, rows, status, cost):
        if state == "running":
            order.append(name)
        elif state == "phase":
            phases.append(name)

    server.build_report("https://x.com", fetch=fake_fetch, crux=None,
                        selected=selected, on_tool=cap, **kw)
    return order, phases


def test_phase_order_cheap_before_paid_before_source(monkeypatch):
    order, _ = _run({"seo", "site", "source"}, monkeypatch, repo="o/n", github_token="t")
    assert order.index("On-page SEO") < order.index("Site Health (DataForSEO)")
    assert order.index("Site Health (DataForSEO)") < order.index("Source code")


def test_phase_markers_in_ascending_order(monkeypatch):
    _, phases = _run({"seo", "site"}, monkeypatch)          # phase 1 + phase 3
    assert len(phases) == 2
    assert phases[0].startswith("Phase 1")
    assert phases[1].startswith("Phase 3")


def test_empty_phases_emit_no_marker(monkeypatch):
    _, phases = _run({"seo"}, monkeypatch)                  # only phase 1 selected
    assert len(phases) == 1 and phases[0].startswith("Phase 1")


def test_catalog_exposes_phase():
    cat = server.tool_catalog()
    assert all(isinstance(t["phase"], int) and isinstance(t["phase_label"], str) for t in cat)
    byk = {t["key"]: t for t in cat}
    assert byk["seo"]["phase"] == 1
    assert byk["lh_seo"]["phase"] == 2
    assert byk["site"]["phase"] == 3
    assert byk["source"]["phase"] == 4
