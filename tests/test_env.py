"""The one shared .env loader (pipeline/lib/env.py)."""
import os

from pipeline.lib.env import load_env


def test_loads_keys_without_overwriting(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# creds\n"
        "CRUX_API_KEY=crux123\n"
        'DATAFORSEO_LOGIN="dfs_user"\n'
        "ALREADY=fromfile\n"
        "\n"
        "bad line no equals\n"
    )
    monkeypatch.setenv("ALREADY", "preexisting")
    monkeypatch.delenv("CRUX_API_KEY", raising=False)
    monkeypatch.delenv("DATAFORSEO_LOGIN", raising=False)

    loaded = load_env(env)

    assert set(loaded) == {"CRUX_API_KEY", "DATAFORSEO_LOGIN"}
    assert os.environ["CRUX_API_KEY"] == "crux123"
    assert os.environ["DATAFORSEO_LOGIN"] == "dfs_user"      # quotes stripped
    assert os.environ["ALREADY"] == "preexisting"            # never overwrites


def test_missing_file_is_fine(tmp_path):
    assert load_env(tmp_path / "nope.env") == []
