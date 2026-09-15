"""B-124: `wf-outreach --qualify` made one paid DataForSEO call per candidate with
no cap, no confirmation and no printed cost, once the spend latches were gone."""
from __future__ import annotations

import sys

import pytest

from pipeline.outreach import qualify, run


def test_qualify_reports_its_cost():
    def call(path, payload=None, **k):
        return {"cost": 0.0101, "status_code": 20000, "tasks": [{"status_code": 20000, "result": [{"items": [
            {"metrics": {"organic": {"count": 50, "etv": 900.0, "pos_1": 2}}}]}]}]}, None

    v = qualify.qualify_domain("rival.com", call=call)
    assert v["cost"] == 0.0101


@pytest.fixture
def cli(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "load_config", lambda p: {"outreach": {"enabled": True, "tier": 1}})
    banked = []
    monkeypatch.setattr(run.linkbank, "upsert", lambda proj, entry: banked.append(entry["domain"]))
    monkeypatch.setattr(run.linkbank, "bank_path", lambda proj: tmp_path / "linkbank.json")
    cands = tmp_path / "c.txt"
    cands.write_text("\n".join(f"d{i}.com" for i in range(30)))

    def go(*extra):
        monkeypatch.setattr(sys, "argv", ["wf-outreach", "--project", str(tmp_path), "--qualify", str(cands), *extra])
        return run.main(), banked

    return go


def test_the_default_domain_cap_stops_a_long_list(cli, monkeypatch, capsys):
    monkeypatch.setattr(run.qualify, "qualify_domain",
                        lambda d: {"domain": d, "verdict": "pass", "checks": {}, "reasons": [], "status": "ok", "cost": 0.01})
    code, banked = cli()
    assert len(banked) == 20
    out = capsys.readouterr().out
    assert "stopped at --max-domains 20" in out
    assert "$0.2000" in out


def test_the_spend_cap_stops_before_it_is_passed(cli, monkeypatch, capsys):
    monkeypatch.setattr(run.qualify, "qualify_domain",
                        lambda d: {"domain": d, "verdict": "pass", "checks": {}, "reasons": [], "status": "ok", "cost": 0.3})
    code, banked = cli("--max-usd", "1.00")
    assert len(banked) == 3          # 0.9 spent; a 4th would reach 1.2
    assert "stopped at --max-usd $1.00" in capsys.readouterr().out


def test_every_qualified_domain_prints_its_cost(cli, monkeypatch, capsys):
    monkeypatch.setattr(run.qualify, "qualify_domain",
                        lambda d: {"domain": d, "verdict": "unknown", "checks": {}, "reasons": ["x"], "status": "skipped", "cost": 0.0})
    cli("--max-domains", "2")
    out = capsys.readouterr().out
    assert out.count("· $0.0000") == 2
