"""linkbank.py — the candidate store, in the CLIENT repo.

docs/outreach/linkbank.json holds one entry per candidate domain: its safety
verdict, tier, and (once drafted) its outreach copy. Model A: the bank lives in
the client's own repo, never this shared engine. Upsert is idempotent and keyed
by domain, so re-qualifying a domain updates it in place rather than duplicating.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pipeline.lib.atomic import write_json_atomic

SCHEMA = "outreach-linkbank/1"


def bank_path(project) -> Path:
    return Path(project) / "docs" / "outreach" / "linkbank.json"


def load(project) -> dict:
    """The bank, or a fresh empty one. An unreadable file reads as absent."""
    p = bank_path(project)
    if p.is_file():
        try:
            doc = json.loads(p.read_text())
            if isinstance(doc, dict) and isinstance(doc.get("domains"), dict):
                return doc
        except (json.JSONDecodeError, OSError):
            pass
    return {"schema": SCHEMA, "domains": {}}


def save(project, bank: dict) -> Path:
    p = bank_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(p, bank)
    return p


def upsert(project, entry: dict) -> dict:
    """Merge one entry (keyed by entry['domain']) into the bank and persist it."""
    domain = entry.get("domain")
    if not domain:
        raise ValueError("a link-bank entry needs a 'domain'")
    bank = load(project)
    existing = bank["domains"].get(domain, {})
    bank["domains"][domain] = {**existing, **entry, "updated": date.today().isoformat()}
    save(project, bank)
    return bank
