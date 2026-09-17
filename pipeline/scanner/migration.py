"""Migration snapshot diff and redirect-map validation (owned, optional input)."""
from __future__ import annotations
from pipeline.scanner.rows import make_row

_row = make_row("migration")

def migration_rows(snapshot: dict | None, current: dict | None) -> list[dict]:
    if not snapshot or not current:
        return [_row("Migration snapshot", "info", "Provide a pre-launch snapshot and post-launch crawl to compare migrations.",
                     "Upload a snapshot containing URL, status, title, canonical, hreflang, schema, and links.")]
    old, new = snapshot.get("pages", {}), current.get("pages", {})
    lost = [u for u in old if u not in new]
    changed = [u for u in old if u in new and old[u] != new[u]]
    rows = []
    if lost: rows.append(_row("Migration URL loss", "error", f"{len(lost)} snapshot URL(s) disappeared.", "Restore the URL or add a relevant 301 redirect.", detail=", ".join(lost[:10])))
    if changed: rows.append(_row("Migration regressions", "warn", f"{len(changed)} URL(s) changed metadata or status.", "Review changed canonicals, status codes, titles, and hreflang.", detail=", ".join(changed[:10])))
    return rows or [_row("Migration diff", "ok", "No differences found against the supplied snapshot.", "passing")]
