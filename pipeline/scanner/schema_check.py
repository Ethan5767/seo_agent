"""Structured-data validation — parse every JSON-LD block and flag broken ones.

The Technical card lists which schema *types* exist; this checks they're actually
*valid* (invalid JSON-LD earns nothing and can suppress rich results) and that
each object declares @type. Pure: HTML in, rows out.
"""
from __future__ import annotations

import json
import re

from pipeline.scanner.rows import make_row

_row = make_row("schema")
_BLOCK = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL)


def schema_rows(html: str) -> list[dict]:
    blocks = _BLOCK.findall(html or "")
    if not blocks:
        return [_row("Structured data", "warn",
                     "No JSON-LD structured data — search and AI engines get no machine-readable facts.",
                     "add schema.org JSON-LD (LocalBusiness, Breadcrumb, FAQ, etc.)")]
    rows: list[dict] = []
    invalid = 0
    no_type = 0
    types: set[str] = set()
    for raw in blocks:
        try:
            data = json.loads(raw.strip())
        except (ValueError, TypeError):
            invalid += 1
            continue
        for obj in (data if isinstance(data, list) else [data]):
            if isinstance(obj, dict):
                t = obj.get("@type")
                if t:
                    types.update(t if isinstance(t, list) else [t])
                else:
                    no_type += 1
    if invalid:
        rows.append(_row("Valid JSON-LD", "error",
                         f"{invalid} of {len(blocks)} JSON-LD block(s) are invalid JSON — they earn nothing and can break rich results.",
                         "fix the JSON syntax (validate at schema.org/validator)",
                         detail=f"{invalid} broken"))
    else:
        rows.append(_row("Valid JSON-LD", "ok",
                         f"All {len(blocks)} JSON-LD block(s) parse cleanly.",
                         "passing", detail=f"{len(blocks)} block(s)"))
    if no_type:
        rows.append(_row("Schema @type", "warn",
                         f"{no_type} JSON-LD object(s) have no @type — search engines can't classify them.",
                         "add an @type to every JSON-LD object"))
    if types:
        rows.append(_row("Schema types", "ok", f"Types declared: {', '.join(sorted(types))}.",
                         "passing", detail=", ".join(sorted(types))))
    return rows
