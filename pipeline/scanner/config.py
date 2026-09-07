"""Scaffold a minimal client-config for a repo that has none, so plan/remediate
can run on an arbitrary site the operator points at. A repo that already
declares a config is left completely untouched."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import yaml


def ensure_config(repo: Path, url: str, tier: int = 1) -> Path:
    """Return docs/client-config.yml, scaffolding a minimal one if absent."""
    repo = Path(repo)
    docs = repo / "docs"
    path = docs / "client-config.yml"
    if path.is_file():
        return path
    docs.mkdir(parents=True, exist_ok=True)
    parts = urlsplit(url)
    host = parts.netloc
    cfg = {
        "client": repo.name or "scanned-client",
        "domain": host,
        "website": f"{parts.scheme}://{host}",
        "topology_class": "single-site-single-state",
        "site_count": 1,
        "states_served": [],
        "tier": int(tier),
        "repo": {"framework": "nextjs-app-router", "build_output_dir": "out"},
        "text_paths": ["out/**/*.html"],
    }
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return path
