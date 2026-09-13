"""One .env, read once, used everywhere.

A single gitignored `.env` at the repo root holds every credential (CRUX,
DataForSEO, Bright Data, GSC, ...). `load_env()` reads it into the process
environment without overwriting anything already set, so an operator fills in
ONE file and every `wf-*` command + the web backend picks the keys up — never
per-run, never per-credential. The file is .gitignored; `.env.example` is the
committed template.
"""
from __future__ import annotations

import os
from pathlib import Path

# repo root = three levels up from pipeline/lib/env.py
REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env(path: Path | None = None) -> list[str]:
    """Load KEY=VALUE lines from the repo-root .env into os.environ (without
    overwriting anything already set). Returns the names loaded. A missing file
    is fine — it just loads nothing, so unset credentials stay unset and every
    provider degrades honestly."""
    path = path or (REPO_ROOT / ".env")
    loaded: list[str] = []
    if not path.is_file():
        return loaded
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        # Skip blank values: an empty placeholder line is "not set", so it must
        # not shadow the environment or read as a loaded credential.
        if key and val and key not in os.environ:
            os.environ[key] = val
            loaded.append(key)
    return loaded
