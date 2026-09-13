"""One row shape for the free check modules. Each module makes a `_row` bound to
its code-prefix, so the row builder isn't triplicated across tech/onpage/eeat."""
from __future__ import annotations


def make_row(prefix: str):
    """Return a row(what, severity, why, fix, detail='') builder that stamps
    `code = <prefix>.<slug-of-what>`."""
    def _row(what: str, severity: str, why: str, fix: str, detail: str = "") -> dict:
        slug = what.lower().replace(" ", "_").replace(":", "")
        return {"code": f"{prefix}.{slug}", "what": what, "why": why,
                "fix": fix, "detail": detail, "severity": severity}
    return _row
