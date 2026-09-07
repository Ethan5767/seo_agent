"""DataForSEO Business Data — Local SEO / Google Business Profile.

A separate module (dataforseo.py is at its size line) for the local layer:
GBP rating/reviews/category/NAP/claimed. Endpoints are DataForSEO Business Data
(not in the tested INPUTS-17 doc) — parsers built to the documented shape;
verify against a live response. Pure parser + injectable caller.
"""
from __future__ import annotations

from pipeline.scanner.dataforseo import _tool, LOCATION_CODE, LANGUAGE_CODE, result_items


def _row(what, severity, why, fix, detail=""):
    return {"code": f"gbp.{what.lower().replace(' ', '_')}", "what": what,
            "why": why, "fix": fix, "detail": detail, "severity": severity}


def parse_gbp(doc: dict) -> list[dict]:
    items = result_items(doc)
    if not items:
        return [_row("Google Business Profile", "warn",
                     "No Google Business Profile found for this name/location — local search (the map pack) drives most calls for local businesses.",
                     "create/claim a Google Business Profile")]
    it = items[0] or {}
    rows: list[dict] = []

    rating = (it.get("rating") or {})
    val, votes = rating.get("value"), rating.get("votes_count") or rating.get("reviews_count")
    if val:
        sev = "ok" if float(val) >= 4.0 else "warn"
        rows.append(_row("Reviews", sev, f"{val}★ from {votes or 0} reviews — a top local ranking + trust signal.",
                         "keep a compliant review-request flow going", detail=f"{val}★ / {votes or 0}"))
    else:
        rows.append(_row("Reviews", "warn", "No reviews on the profile — few reviews hurt map-pack rank and trust.",
                         "set up a compliant review-request flow"))

    cat = it.get("category")
    rows.append(_row("Primary category", "ok" if cat else "warn",
                     f"Primary category: {cat}." if cat else "No primary category — the #1 local ranking factor.",
                     "passing" if cat else "set the most accurate primary category", detail=cat or ""))

    addr = it.get("address") or it.get("address_info")
    phone = it.get("phone")
    rows.append(_row("NAP", "ok" if (addr and phone) else "warn",
                     "Name/address/phone present on the profile." if (addr and phone)
                     else "Missing address and/or phone — NAP must be complete and consistent.",
                     "passing" if (addr and phone) else "complete the address + phone, consistent with the site"))

    if it.get("is_claimed") is False:
        rows.append(_row("Claimed", "warn", "The profile is unclaimed — anyone can suggest edits and you can't fully control it.",
                         "claim the profile"))
    return rows


def gbp_local(business: str, call=None) -> tuple:
    """(rows, status, cost) — Google Business Profile audit for `business`."""
    from pipeline.scanner.dataforseo import call as _call
    call = call or _call
    return _tool("/v3/business_data/google/my_business_info/live",
                 [{"keyword": business, "location_code": LOCATION_CODE, "language_code": LANGUAGE_CODE}],
                 parse_gbp, call=call, status="ok (verify live)")
