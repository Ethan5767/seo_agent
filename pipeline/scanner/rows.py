"""One row shape for the free check modules. Each module makes a `_row` bound to
its code-prefix, so the row builder isn't triplicated across tech/onpage/eeat."""
from __future__ import annotations


def unavailable_row(tool_key: str, reason: str, label: str = "") -> dict:
    """The row a tool emits when it could not run: one, ungraded, named.

    A tool that silently produced no group read as "nothing found" on every
    screen that filters for it. `info` keeps it out of the score (health_score
    grades ok/warn/error only); the reason is the whole content.
    """
    name = label or tool_key
    return {"code": f"unavailable.{tool_key}", "what": f"{name} did not run",
            "why": reason, "fix": "Resolve the reason above, then scan again.",
            "detail": "", "severity": "info"}


def make_row(prefix: str):
    """Return a row(what, severity, why, fix, detail='') builder that stamps
    `code = <prefix>.<slug-of-what>`."""
    def _row(what: str, severity: str, why: str, fix: str, detail: str = "") -> dict:
        slug = what.lower().replace(" ", "_").replace(":", "")
        return {"code": f"{prefix}.{slug}", "what": what, "why": why,
                "fix": fix, "detail": detail, "severity": severity}
    return _row
