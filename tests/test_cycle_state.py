"""Tests for shared cycle state — the two-operator problem.

Alex and Robin both drive this pipeline and never see each other's screens.
The failure these guard against is the expensive one: sitting down, not knowing
a step is already finished, and redoing it — or worse, half-redoing it and
producing a second version of the same cycle's work.
"""

from pathlib import Path

from pipeline.lib.cycle_state import (
    DONE,
    FAILED,
    RUNNING,
    SKIPPED,
    STEP_NAMES,
    CycleState,
    state_path,
)


def fresh(tmp_path: Path) -> CycleState:
    return CycleState.load(tmp_path, "northstar-landscaping", "2026-07")


# ── layout ──

def test_state_lives_beside_the_cycle_post_mortem(tmp_path: Path):
    p = state_path(tmp_path, "2026-07")
    assert p == tmp_path / "docs/cycle-logs/2026-07/cycle-state.json"


def test_a_new_cycle_starts_with_every_step_pending(tmp_path: Path):
    st = fresh(tmp_path)
    assert st.next_step() == STEP_NAMES[0]
    assert all(not st.is_done(s) for s in STEP_NAMES)


# ── the point: do not redo the other person's work ──

def test_claim_allows_a_step_nobody_has_run(tmp_path: Path):
    go, _ = fresh(tmp_path).claim("intake")
    assert go is True


def test_claim_refuses_a_step_someone_else_finished(tmp_path: Path):
    st = fresh(tmp_path)
    st.mark("intake", DONE, "7 files", at="2026-07-29T01:00:00+00:00")
    st.data["steps"]["intake"]["by"] = "robin"
    go, why = st.claim("intake")
    assert go is False
    assert "robin" in why and "already done" in why


def test_claim_refuses_a_step_another_run_is_mid_way_through(tmp_path: Path):
    """Two people starting the same step at once is the worst case."""
    st = fresh(tmp_path)
    st.mark("distill", RUNNING, at="2026-07-29T01:00:00+00:00")
    go, why = st.claim("distill")
    assert go is False and "another run claimed" in why


def test_force_overrides_a_stale_running_claim(tmp_path: Path):
    st = fresh(tmp_path)
    st.mark("distill", RUNNING, at="2026-07-29T01:00:00+00:00")
    go, _ = st.claim("distill", force=True)
    assert go is True


def test_a_skipped_step_counts_as_done_and_is_not_repeated(tmp_path: Path):
    st = fresh(tmp_path)
    st.mark("classify", SKIPPED, "nothing to classify")
    assert st.is_done("classify")
    assert st.claim("classify")[0] is False


def test_a_failed_step_is_retried_not_treated_as_done(tmp_path: Path):
    st = fresh(tmp_path)
    st.mark("gates", FAILED, "orphan_check red")
    assert not st.is_done("gates")
    assert st.claim("gates")[0] is True


# ── ordering ──

def test_next_step_walks_the_cycle_in_order(tmp_path: Path):
    st = fresh(tmp_path)
    for expected in STEP_NAMES:
        assert st.next_step() == expected
        st.mark(expected, DONE)
    assert st.next_step() is None


def test_out_of_order_completion_still_reports_the_earliest_gap(tmp_path: Path):
    st = fresh(tmp_path)
    st.mark("emit", DONE)
    assert st.next_step() == "intake"


# ── persistence: this is what the other person actually reads ──

def test_state_round_trips_through_disk(tmp_path: Path):
    st = fresh(tmp_path)
    st.mark("intake", DONE, "7 files from July 2026")
    st.save()

    reloaded = CycleState.load(tmp_path, "northstar-landscaping", "2026-07")
    assert reloaded.is_done("intake")
    assert reloaded.step("intake")["detail"] == "7 files from July 2026"
    assert reloaded.next_step() == "distill"


def test_every_step_records_who_ran_it(tmp_path: Path):
    st = fresh(tmp_path)
    st.mark("intake", DONE)
    assert st.step("intake").get("by")


def test_separate_cycles_do_not_share_state(tmp_path: Path):
    july = CycleState.load(tmp_path, "northstar-landscaping", "2026-07")
    july.mark("intake", DONE).save()
    august = CycleState.load(tmp_path, "northstar-landscaping", "2026-08")
    assert not august.is_done("intake")


def test_a_corrupt_state_file_does_not_crash_the_run(tmp_path: Path):
    p = state_path(tmp_path, "2026-07")
    p.parent.mkdir(parents=True)
    p.write_text("{ not json")
    st = CycleState.load(tmp_path, "northstar-landscaping", "2026-07")
    assert st.next_step() == STEP_NAMES[0]


def test_render_names_who_did_what(tmp_path: Path):
    st = fresh(tmp_path)
    st.mark("intake", DONE, "7 files", at="2026-07-29T01:00:00+00:00")
    out = st.render()
    assert "northstar-landscaping" in out and "2026-07" in out
    assert "7 files" in out
    assert "NEXT: distill" in out
