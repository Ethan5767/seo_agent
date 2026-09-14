"""qualify.py — the 4-point backlink safety check (SOP §12).

Before a domain enters the link bank it must clear four gates:

    not_penalized   the domain is not de-ranked / dead in Google
    real_traffic    it has verifiable organic search traffic
    outbound_links  the host page does not spray authority across dozens of links
    in_content      the placement is in real body copy, not a footer/sidebar farm

The first two are derivable from DataForSEO's organic footprint; the last two are
page-level facts a domain endpoint cannot see, so they are marked `manual` — a
human confirms them on the actual placement page.

DataForSEO spends live when credentials are in the process environment and
DATAFORSEO_PAUSE_SPEND is off (one paid call per domain, no budget: B-124); without
them, so
with no live data every automatable check returns `unknown` and the domain's
verdict is `unknown` — a NAMED SKIP carrying the provider's own status string,
never a fabricated pass (CLAUDE.md sharp-edge #6). When live data does flow, the
same code computes real pass/fail verdicts.
"""
from __future__ import annotations

from pipeline.scanner import dataforseo as dfs

_AUTOMATABLE = ("not_penalized", "real_traffic")
_MANUAL = ("outbound_links", "in_content")


def qualify_domain(domain: str, call=None) -> dict:
    """{domain, verdict, checks, reasons, status}. verdict in pass|fail|unknown."""
    call = call or dfs.call
    rows, status, _cost = dfs.domain_overview(domain, call=call)

    if not rows:
        checks = {k: "unknown" for k in (_AUTOMATABLE + _MANUAL)}
        return {"domain": domain, "verdict": "unknown", "checks": checks,
                "reasons": [f"organic data unavailable: {status}"], "status": status}

    # A live overview row is severity "ok" only when the domain ranks for >0
    # keywords — a penalized or dead domain collapses to zero footprint, which is
    # the same signal for both automatable checks.
    has_footprint = rows[0].get("severity") == "ok"
    checks = {
        "not_penalized": "pass" if has_footprint else "fail",
        "real_traffic": "pass" if has_footprint else "fail",
        "outbound_links": "manual",
        "in_content": "manual",
    }
    reasons: list[str] = []
    if has_footprint:
        if rows[0].get("fix"):
            reasons.append(rows[0]["fix"])
        reasons.append("outbound-link count and in-content placement need a manual "
                       "check on the host page")
        verdict = "pass"
    else:
        reasons.append("domain shows ~zero organic footprint (dead or penalized)")
        verdict = "fail"

    return {"domain": domain, "verdict": verdict, "checks": checks,
            "reasons": reasons, "status": status}
