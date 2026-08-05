"""Client-roster + Drive-parent loader for the Drive intake tooling.

The roster (client slugs, domains, folder aliases) and the Google Drive parent
folder id are *client data*, not engine code. Per repo rule #2 they never live
in this repo. They are supplied at run time:

    PIPELINE_DRIVE_PARENT_FOLDER_ID   the Drive folder id holding client folders
    PIPELINE_CLIENT_ROSTER            path to a JSON roster file (see
                                      client-roster.example.json)

If PIPELINE_CLIENT_ROSTER is unset, `pipeline/intake/secrets/client-roster.json`
is used when present — that directory is covered by the repo's `**/secrets/**`
gitignore rule, so a real roster there can never be committed. Absent both, the
roster is empty and every file routes to UNROUTED: the tools still run, they
just cannot route.

Roster JSON shape (list of objects):

    [
      {
        "slug": "example-client",
        "domain": "example.com",
        "folder_name_contains": "example",
        "aliases": ["example.com", "example roofing", "example"]
      }
    ]
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT_ROSTER = Path(__file__).resolve().parent / "secrets" / "client-roster.json"

ROSTER_ENV = "PIPELINE_CLIENT_ROSTER"
PARENT_ENV = "PIPELINE_DRIVE_PARENT_FOLDER_ID"


def roster_path() -> Path | None:
    """Resolve the roster file location, or None if there isn't one."""
    env = os.environ.get(ROSTER_ENV, "").strip()
    if env:
        return Path(env).expanduser()
    if _DEFAULT_ROSTER.is_file():
        return _DEFAULT_ROSTER
    return None


def load_clients() -> list[dict]:
    """Return the client roster, or [] when none is configured.

    Every entry is normalized to have slug / domain / folder_name_contains /
    aliases keys so callers can index them unconditionally.
    """
    path = roster_path()
    if path is None or not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # pragma: no cover - operator error
        raise SystemExit(f"[ERROR] cannot read client roster {path}: {exc}")
    if not isinstance(data, list):
        raise SystemExit(f"[ERROR] client roster {path} must be a JSON list")

    out: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict) or not entry.get("slug"):
            continue
        slug = str(entry["slug"])
        aliases = entry.get("aliases") or [slug]
        out.append(
            {
                "slug": slug,
                "domain": entry.get("domain", ""),
                "folder_name_contains": entry.get("folder_name_contains", slug),
                "aliases": [str(a) for a in aliases],
            }
        )
    return out


def parent_folder_id() -> str:
    """Drive folder id that holds the per-client folders. '' when unset."""
    return os.environ.get(PARENT_ENV, "").strip()


def require_parent_folder_id() -> str:
    pid = parent_folder_id()
    if not pid:
        raise SystemExit(
            f"[ERROR] {PARENT_ENV} is not set. Export the Drive parent folder id "
            "before running the Drive intake tools."
        )
    return pid
