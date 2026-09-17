"""Bridge the web MVP Plan worklist into the pipeline's worklist shape, so the
real `wf-site-remediate` fixer (Claude Code on the Claude subscription) can run —
starting with `--dry-run`, which streams the fix prompts and edits nothing.

The pipeline only acts on codes that have a machine-checkable acceptance, i.e. an
entry in `plan.ACTIONS`; those keys are the same `health.*` codes the web scanner
emits for on-page findings. So the on-page subset bridges faithfully and every
other web code (`src.* / lh.* / crux.* / aeo.* / dfs.*`) is reported as
`unbridged` — honestly "not machine-fixable on this rail", never forced through.

We reuse `plan.work_item` as the item builder rather than re-declaring the item
schema here, so there is zero drift from what `wf-site-remediate` expects.
"""
from __future__ import annotations

from pipeline.audit import plan as P


def _finding_for(item: dict, scan_url: str) -> dict:
    """Shape a web worklist item into the `finding` dict plan.work_item reads.
    URL prefers the first affected page (the specific offender), else the scanned
    URL. The fingerprint is stable and scoped to code+url so resume lines up and
    two pages with the same issue stay independent."""
    code = item.get("code", "")
    pages = item.get("pages") or []
    url = pages[0] if pages else (scan_url or "")
    return {
        "code": code,
        "fingerprint": f"{code}|{url}",
        "location": url,
        "context": item.get("what", ""),
        "detail": item.get("detail", "") or item.get("fix", ""),
    }


def bridge_worklist(web_items: list[dict], scan_url: str, tier, cycle: str) -> dict:
    """Return `{"worklist": <pipeline worklist envelope>, "unbridged": [...]}`.

    `web_items` is the web Plan worklist (already prioritised). Items whose code
    has a `plan.ACTIONS` entry become pipeline worklist items (via plan.work_item);
    the rest are collected in `unbridged` with a short reason."""
    items: list[dict] = []
    unbridged: list[dict] = []
    n = 0
    for w in web_items or []:
        finding = _finding_for(w, scan_url)
        n += 1
        built = P.work_item(n, cycle or "", finding, w.get("status", "NEW"), tier)
        if built:
            items.append(built)
        else:
            n -= 1  # keep pipeline ids dense over the bridged items only
            unbridged.append({
                "code": w.get("code", ""),
                "what": w.get("what", ""),
                "reason": "no machine-checkable acceptance on the code-fix rail — "
                          "fix by hand or via a content/strategy step",
            })

    worklist = {
        "schema": P.SCHEMA,
        "cycle": cycle,
        "domain": scan_url,
        "tier": tier,
        "counts": {"items": len(items), "unbridged": len(unbridged)},
        "items": items,
    }
    return {"worklist": worklist, "unbridged": unbridged}
