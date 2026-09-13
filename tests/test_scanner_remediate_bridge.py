"""Bridge the web Plan worklist into the pipeline's worklist shape so the real
`wf-site-remediate` fixer can dry-run over it. Pure, offline. Reuses
plan.work_item as the item builder, so only codes in plan.ACTIONS bridge — the
rest are reported as unbridged (not machine-fixable on this rail)."""
from pipeline.scanner.remediate_bridge import bridge_worklist


def wi(code, sev="warn", pri=1, what="thing", fix="do it", pages=None):
    r = {"code": code, "severity": sev, "priority": pri, "what": what,
         "fix": fix, "detail": "seen on the page"}
    if pages is not None:
        r["pages"] = pages
    return r


def test_health_codes_bridge_others_unbridged():
    items = [
        wi("health.title_missing", "error"),     # in ACTIONS (T1)
        wi("health.h1_count", "warn"),           # in ACTIONS (T3)
        wi("src.next_config", "error"),          # not in ACTIONS
        wi("aeo.statistics", "warn"),            # not in ACTIONS
    ]
    out = bridge_worklist(items, scan_url="https://ex.com/", tier=3, cycle="2026-09")
    codes = [i["code"] for i in out["worklist"]["items"]]
    assert codes == ["health.title_missing", "health.h1_count"]
    assert {u["code"] for u in out["unbridged"]} == {"src.next_config", "aeo.statistics"}


def test_bridged_item_has_pipeline_shape():
    out = bridge_worklist([wi("health.title_missing", "error")],
                          scan_url="https://ex.com/", tier=1, cycle="2026-09")
    it = out["worklist"]["items"][0]
    # the fields wf-site-remediate / build_prompt read
    for key in ("id", "finding_fp", "url", "kind", "code", "min_tier", "tier_blocked", "evidence", "acceptance"):
        assert key in it, f"missing {key}"
    assert it["code"] == "health.title_missing"
    assert it["kind"] == "title_missing"          # from plan.ACTIONS
    assert it["url"] == "https://ex.com/"          # falls back to scan_url
    assert it["evidence"]["detail"] == "seen on the page"


def test_url_prefers_affected_page():
    out = bridge_worklist([wi("health.img_alt_missing", pages=["https://ex.com/a", "https://ex.com/b"])],
                          scan_url="https://ex.com/", tier=1, cycle="2026-09")
    assert out["worklist"]["items"][0]["url"] == "https://ex.com/a"


def test_fingerprint_stable_and_code_url_scoped():
    a = bridge_worklist([wi("health.title_missing")], "https://ex.com/", 1, "2026-09")
    b = bridge_worklist([wi("health.title_missing")], "https://ex.com/", 1, "2026-09")
    assert a["worklist"]["items"][0]["finding_fp"] == b["worklist"]["items"][0]["finding_fp"]
    # different page → different fingerprint (independent resume)
    c = bridge_worklist([wi("health.title_missing", pages=["https://ex.com/x"])],
                        "https://ex.com/", 1, "2026-09")
    assert c["worklist"]["items"][0]["finding_fp"] != a["worklist"]["items"][0]["finding_fp"]


def test_tier_gating_passes_through():
    # a T3 code under a T1 client is visible but tier_blocked (no authority)
    out = bridge_worklist([wi("health.canonical_mismatch")], "https://ex.com/", 1, "2026-09")
    it = out["worklist"]["items"][0]
    assert it["min_tier"] == 3 and it["tier_blocked"] is True


def test_worklist_envelope_and_ids():
    out = bridge_worklist([wi("health.title_missing"), wi("health.desc_missing")],
                          "https://ex.com/", 3, "2026-09")
    wl = out["worklist"]
    assert wl["cycle"] == "2026-09" and "schema" in wl and "items" in wl
    # ids are positional + unique
    ids = [i["id"] for i in wl["items"]]
    assert len(ids) == len(set(ids)) == 2


def test_empty():
    out = bridge_worklist([], "https://ex.com/", 1, "2026-09")
    assert out["worklist"]["items"] == [] and out["unbridged"] == []
