import yaml
from pipeline.scanner.config import ensure_config


def test_scaffolds_when_absent(tmp_path):
    repo = tmp_path / "site"
    repo.mkdir()
    p = ensure_config(repo, "https://acme.com/services/", tier=1)
    assert p == repo / "docs" / "client-config.yml"
    cfg = yaml.safe_load(p.read_text())
    assert cfg["domain"] == "acme.com"
    assert cfg["tier"] == 1
    assert cfg["repo"]["build_output_dir"] == "out"


def test_keeps_existing_config(tmp_path):
    repo = tmp_path / "site"
    (repo / "docs").mkdir(parents=True)
    existing = {"client": "keep-me", "domain": "keep.com", "tier": 3}
    (repo / "docs" / "client-config.yml").write_text(yaml.safe_dump(existing))
    ensure_config(repo, "https://other.com/", tier=1)
    cfg = yaml.safe_load((repo / "docs" / "client-config.yml").read_text())
    assert cfg["client"] == "keep-me" and cfg["tier"] == 3


def test_onboard_profile_is_written_into_config(tmp_path):
    repo = tmp_path / "site"; repo.mkdir()
    profile = {"business": "Orienda Hospital", "keywords": ["hospital phnom penh"],
               "competitors": ["rival.com"], "goal": "more calls"}
    p = ensure_config(repo, "https://x.com/", tier=1, profile=profile)
    cfg = yaml.safe_load(p.read_text())
    assert cfg["client"] == "Orienda Hospital"
    assert cfg["seed_queries"] == ["hospital phnom penh"]
    assert cfg["competitors"] == ["rival.com"]
    assert cfg["goal"] == "more calls"
