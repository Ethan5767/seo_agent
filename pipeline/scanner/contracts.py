"""Shared scanner contracts.

The registry historically exposed ``group``/``cost`` fields and row builders
returned a loose ``what/why/fix`` shape.  Keep those fields for compatibility,
but add one explicit metadata contract and normalize every emitted finding at
the scanner boundary.
"""

from __future__ import annotations

from typing import Any, Iterable


DEFAULT_RUNTIME_SECONDS = {
    "free": 2.0,
    "dataforseo": 8.0,
    "source": 5.0,
}


def tool_metadata(tool: Any) -> dict[str, Any]:
    """Return the stable metadata required by the tool catalogue contract."""
    return {
        "name": tool.label,
        "data_source": "own_crawler" if tool.group == "free" else tool.group,
        "cost_per_run": float(tool.cost_num or 0.0),
        "requires_auth": tool.needs in ("repo", "oauth"),
        "avg_runtime": DEFAULT_RUNTIME_SECONDS.get(tool.group, 5.0),
    }


def normalize_finding(row: dict[str, Any], tool: Any) -> dict[str, Any]:
    """Add the canonical finding fields without breaking legacy consumers."""
    out = dict(row)
    severity = str(out.get("severity") or "info").lower()
    pages = out.get("affected_urls", out.get("pages", []))
    if isinstance(pages, str):
        pages = [pages]
    if not isinstance(pages, list):
        pages = []
    out.update({
        "id": str(out.get("id") or out.get("code") or f"{tool.key}:{out.get('what', 'finding')}"),
        "category": str(out.get("category") or tool.category),
        "severity": severity,
        "affected_urls": [str(url) for url in pages if url],
        "evidence": out.get("evidence") or {
            "code": out.get("code"),
            "detail": out.get("detail", ""),
        },
        "why_it_matters": str(out.get("why_it_matters") or out.get("why") or ""),
        "how_to_fix": str(out.get("how_to_fix") or out.get("fix") or ""),
        "effort": str(out.get("effort") or "unknown"),
        "estimated_impact": out.get("estimated_impact") or {
            "critical": 10, "error": 8, "warn": 5, "info": 1, "ok": 0,
        }.get(severity, 1),
        "source_tool": tool.key,
        "confidence": out.get("confidence") or ("high" if severity != "info" else "medium"),
    })
    return out


def normalize_findings(rows: Iterable[dict[str, Any]] | None, tool: Any) -> list[dict[str, Any]]:
    return [normalize_finding(row, tool) for row in (rows or []) if isinstance(row, dict)]
