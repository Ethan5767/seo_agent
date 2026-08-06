"""The pin has to agree with itself.

A client repo holds a thin caller pinned `@vX.Y.Z`. That tag decides which
gates guard their production site. Three separate places have to say the same
thing, and nothing but a test was ever going to keep them saying it:

  * `PIPELINE_REPO` / `PIPELINE_REF` stamped in each reusable workflow — the
    fallback used for CHECKOUT 2 when `github.job_workflow_sha` is empty
  * the `uses:` line in each example caller, which is what an operator copies
  * the git tag actually cut

They drifted for a full release: every file still stamped
`richardnhek/seo-content-pipeline@v2.1.0` after the repo moved to
`Ethan5767/seo_agent` and the engine moved to v3, so a client who copied an
example verbatim would have been gated by the v2 DOCX-era suite — 16 gates, no
tiering, no authorship floor — while every doc in the repo said 19.

The stamp is deliberately self-referential: v3.0.0's copy of the file stamps
v3.0.0, so a tagged checkout is always internally consistent. These tests are
what make that true rather than aspirational.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted(Path(".github/workflows").glob("*.reusable.yml"))
EXAMPLES = sorted(Path(".github/examples").glob("*.yml"))

SEMVER = re.compile(r"^v\d+\.\d+\.\d+$")
STAMP = re.compile(r'^\s*PIPELINE_(REPO|REF):\s*"([^"]+)"\s*$', re.M)
USES = re.compile(r"^\s*uses:\s*([\w.-]+/[\w.-]+)/\.github/workflows/([\w.-]+)@(\S+)\s*$", re.M)


def stamps(path: Path) -> dict:
    return {k: v for k, v in STAMP.findall(path.read_text())}


def test_there_are_workflows_and_examples_to_check():
    # Guard against the whole suite passing vacuously if a glob ever goes stale.
    assert WORKFLOWS and EXAMPLES


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_every_reusable_workflow_carries_both_stamps(wf):
    s = stamps(wf)
    assert set(s) == {"REPO", "REF"}, f"{wf.name} is missing a PIPELINE_* stamp"
    assert SEMVER.match(s["REF"]), (
        f"{wf.name} stamps {s['REF']!r} — the fallback ref must be an exact "
        f"version, never a branch: it is what runs when job_workflow_sha is empty")


def test_the_workflows_all_agree():
    seen = {wf.name: stamps(wf) for wf in WORKFLOWS}
    refs = {v["REF"] for v in seen.values()}
    repos = {v["REPO"] for v in seen.values()}
    assert len(refs) == 1, f"reusable workflows stamp different refs: {seen}"
    assert len(repos) == 1, f"reusable workflows stamp different repos: {seen}"


@pytest.mark.parametrize("ex", EXAMPLES, ids=lambda p: p.name)
def test_every_example_pins_an_exact_tag_at_the_stamped_repo(ex):
    hits = USES.findall(ex.read_text())
    assert hits, f"{ex.name} has no `uses:` line — it is not a thin caller"
    expected = stamps(WORKFLOWS[0])
    for repo, workflow, ref in hits:
        assert repo == expected["REPO"], (
            f"{ex.name} calls {repo}, but the workflows stamp {expected['REPO']} — "
            f"an operator copying this gets a different engine than the one here")
        assert SEMVER.match(ref), (
            f"{ex.name} pins {ref!r}. Never `@main`, never a moving `@v3`: this "
            f"workflow gates production and a mutable ref can change without a PR")
        assert ref == expected["REF"], (
            f"{ex.name} pins {ref}, the workflows stamp {expected['REF']}")
        assert (Path(".github/workflows") / workflow).is_file(), (
            f"{ex.name} calls {workflow}, which does not exist in this repo")


def test_no_reference_to_the_repo_this_was_imported_from_survives():
    """v3 was imported from richardnhek/seo-content-pipeline @ v2.1.0. A leftover
    reference there is not a cosmetic problem — it points a client's production
    gate at a different organisation's code."""
    for f in WORKFLOWS + EXAMPLES:
        assert "richardnhek" not in f.read_text(), f"{f} still references the import source"
