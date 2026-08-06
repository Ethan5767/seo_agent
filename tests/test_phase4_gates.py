"""Phase 4 — the safety floor: tier_check, claim_provenance_check, acceptance_check.

The properties worth a test are the ones the whole design rests on:

  * the deny floor holds at T3, and a config cannot shrink it
  * a rename is a delete plus a create, not a modify (the T1 escape hatch)
  * an invented credential is refused; a claim already on the page is not
  * an empty corpus REFUSES rather than passing every claim for want of a check
  * a claimed fix whose finding still fires blocks the PR
  * a claimed fix with no page in the build output blocks it too — silence is
    not proof
"""
from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from pipeline.gates import acceptance_check as acc
from pipeline.gates import claim_provenance_check as prov
from pipeline.gates import tier_check as tc
from pipeline.lib.baseline import NEVER_BASELINEABLE, BaselineError, assert_baselineable
from pipeline.lib.common import client_profile, glob_re, path_matches, tier_verdict


def profile(**over):
    cfg = {
        "client": "acme", "domain": "acme.com",
        "topology_class": "single-site-single-state", "states_served": ["NC"],
        "tier": 1, "text_paths": ["src/data/**/*.ts"],
    }
    cfg.update(over)
    return client_profile(cfg)


# ── the matcher ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pattern,path,hit", [
    ("src/data/**/*.ts", "src/data/services.ts", True),
    ("src/data/**/*.ts", "src/data/nc/charlotte.ts", True),
    ("src/data/**/*.ts", "src/data/services.tsx", False),
    ("src/data/**/*.ts", "src/app/data/services.ts", False),
    (".github/**", ".github/workflows/quality-gate.yml", True),
    ("package*.json", "package-lock.json", True),
    (".env*", "apps/web/.env.local", True),          # unanchored: any depth
    ("docs/client-config.yml", "docs/client-config.yml", True),
])
def test_glob_matching(pattern, path, hit):
    assert path_matches(path, [pattern]) is hit


def test_star_does_not_cross_a_segment_boundary():
    """fnmatch's `*` eats `/`, which would make `src/*.ts` an allow-list over the
    whole tree. That is the bug this matcher exists to not have."""
    assert glob_re("src/*.ts").match("src/a/b.ts") is None
    assert glob_re("src/*.ts").match("src/b.ts") is not None


# ── the tier verdict ─────────────────────────────────────────────────────────

def test_t1_may_modify_text_paths_only():
    p = profile()
    assert tier_verdict(p, "src/data/services.ts", "M")[0] is True
    assert tier_verdict(p, "src/components/Hero.tsx", "M")[0] is False
    assert tier_verdict(p, "src/data/new.ts", "A")[0] is False
    assert tier_verdict(p, "src/data/services.ts", "D")[0] is False


def test_t2_creates_under_content_location_and_wires_the_registry():
    p = profile(tier=2, content={"location": "src/content/blog/",
                                 "registry": ["src/data/posts.ts"], "format": "mdx"})
    assert tier_verdict(p, "src/content/blog/new-roof.mdx", "A")[0] is True
    assert tier_verdict(p, "src/data/posts.ts", "M")[0] is True
    assert tier_verdict(p, "src/pages/about.mdx", "A")[0] is False
    assert tier_verdict(p, "src/content/blog/old.mdx", "D")[0] is False, "only T3 deletes"


def test_t3_may_do_anything_except_what_is_denied():
    p = profile(tier=3)
    assert tier_verdict(p, "src/components/Hero.tsx", "M")[0] is True
    assert tier_verdict(p, "src/components/Old.tsx", "D")[0] is True
    for denied in (".github/workflows/ci.yml", "docs/client-config.yml",
                   "package.json", "wrangler.toml", ".env.production"):
        allowed, reason = tier_verdict(p, denied, "M")
        assert allowed is False, f"{denied} must be refused at T3"
        assert "deny list" in reason


def test_a_config_cannot_shrink_the_deny_floor():
    """A client repo that declares its own short deny list still gets the floor —
    the union is what stops the agent editing the gates that judge it."""
    p = profile(tier=3, deny=["only-this.txt"])
    assert tier_verdict(p, ".github/workflows/ci.yml", "M")[0] is False
    assert tier_verdict(p, "only-this.txt", "M")[0] is False


def test_no_declared_tier_means_no_authority():
    p = profile(tier=None)
    allowed, reason = tier_verdict(p, "src/data/services.ts", "M")
    assert allowed is False
    assert "no `tier:` declared" in reason


def test_audit_artifacts_ride_along_at_every_tier_but_are_never_deleted():
    """The cycle's own artifacts ship inside the PR (v3 §1). If the tier refused
    them, every remediation PR would be blocked by its own gate."""
    p = profile()
    assert tier_verdict(p, "docs/audit/2026-08/changelog.json", "A")[0] is True
    assert tier_verdict(p, "docs/audit/2026-08/report.md", "M")[0] is True
    assert tier_verdict(p, "docs/audit/2026-07/findings.json", "D")[0] is False


# ── the diff parser ──────────────────────────────────────────────────────────

def test_a_rename_is_a_delete_plus_a_create():
    """Collapsing R to 'modify' is exactly how a T1 agent moves a file out of its
    allow-list and keeps editing it."""
    changes = tc.parse_name_status("R100\tsrc/data/services.ts\tsrc/other/services.ts\n")
    assert ("D", "src/data/services.ts") in changes
    assert ("A", "src/other/services.ts") in changes
    allowed, refused = tc.judge(profile(), changes)
    assert len(refused) == 2 and not allowed


def test_tier_check_judges_a_name_status_diff(tmp_path, make_project):
    proj = make_project(config={
        "client": "acme", "domain": "acme.com",
        "topology_class": "single-site-single-state", "states_served": ["NC"],
        "tier": 1, "text_paths": ["src/data/**/*.ts"],
    })
    diff = tmp_path / "diff.txt"
    diff.write_text("M\tsrc/data/services.ts\nM\tsrc/components/Hero.tsx\n")
    changes = tc.changed_paths(proj, None, str(diff))
    allowed, refused = tc.judge(client_profile(_cfg(proj), proj), changes)
    assert [p for _, p, _ in allowed] == ["src/data/services.ts"]
    assert [p for _, p, _ in refused] == ["src/components/Hero.tsx"]


def _cfg(proj):
    import yaml
    return yaml.safe_load((Path(proj) / "docs" / "client-config.yml").read_text())


# ── claim provenance ─────────────────────────────────────────────────────────

CORPUS = prov.normalize("Founded in 1998. 4.9 stars. 1,200 reviews. License #NC-4471. "
                        "The only active stone quarry in Florida.")


@pytest.mark.parametrize("text,sourced", [
    ("Rated 4.9 stars by our customers", True),
    ("Rated 4.8 stars by our customers", False),
    ("Over 1,200 reviews", True),
    ("Over 3,000 reviews", False),
    ("License #NC-4471", True),
    ("License #NC-9999", False),
    ("The only active stone quarry", True),
    ("The largest roofing company in the state", False),
    ("Serving homeowners since 1998", True),
    ("Serving homeowners since 1975", False),
])
def test_claims_are_checked_against_the_corpus(text, sourced):
    claims = prov.claims_in(text)
    assert claims, f"no claim detected in {text!r}"
    assert all(prov.is_sourced(k, t, CORPUS) for k, t, _ in claims) is sourced


def test_ordinary_prose_carries_no_claims():
    """A gate that flags '5 Signs You Need a New Roof' gets switched off."""
    assert prov.claims_in("5 Signs You Need a New Roof This Spring") == []
    assert prov.claims_in("Call us today to book an inspection") == []


def test_only_string_literals_are_scanned_in_code():
    line = '  { id: 4471, blurb: "Rated 4.8 stars across 3,000 reviews" },'
    assert prov.prose_from("src/data/services.ts", line) == \
        ["Rated 4.8 stars across 3,000 reviews"]
    # the bare `id: 4471` is not a claim about the business
    assert not any(t == "4471" for _, t, _ in
                   prov.claims_in(prov.prose_from("src/data/services.ts", line)[0]))


def test_a_claim_already_on_the_page_is_not_invented_here():
    added = {"src/content/about.mdx": ["We have served Charlotte for 28 years."]}
    assert prov.scan(added, CORPUS, {}), "unsourced against config alone"
    prior = {"src/content/about.mdx": "Serving Charlotte for 28 years and counting."}
    assert prov.scan(added, CORPUS, prior) == [], "the claim predates this run"


def test_a_cited_line_passes():
    added = {"docs/x.md": ["Ranked #1 in the county (source: https://example.gov/report)"]}
    assert prov.scan(added, CORPUS, {}) == []


def test_added_lines_are_parsed_out_of_a_unified_diff(tmp_path):
    diff = tmp_path / "d.diff"
    diff.write_text(textwrap.dedent("""\
        diff --git a/src/content/about.mdx b/src/content/about.mdx
        --- a/src/content/about.mdx
        +++ b/src/content/about.mdx
        @@ -1 +1,2 @@
        -old line
        +Rated 4.9 stars across 1,200 reviews.
        """))
    added = prov.added_lines(tmp_path, None, str(diff))
    assert added == {"src/content/about.mdx": ["Rated 4.9 stars across 1,200 reviews."]}
    assert prov.scan(added, CORPUS, {}) == []


def test_empty_corpus_refuses(make_project, monkeypatch, capsys):
    """Same rule as forbidden_sweep's empty ruleset: a gate that cannot run must
    refuse, not pass."""
    proj = make_project(config={"client": "x"})
    monkeypatch.setattr(prov, "build_corpus", lambda *a, **k: ("", []))
    monkeypatch.setattr("sys.argv", ["wf-claim-provenance-check", "--project", str(proj)])
    assert prov.main() == prov.EMPTY_CORPUS_EXIT


# ── acceptance ───────────────────────────────────────────────────────────────

GOOD_DESC = "a" * 140
PAGE = """<html><head><title>{title}</title>
<meta name="description" content="{desc}"><link rel="canonical" href="{url}">
</head><body><h1>H</h1></body></html>"""


def _item(code="health.desc_length", url="/roofing/", status="fixed"):
    return {"id": "wi-2026-08-0001", "url": url, "status": status,
            "acceptance": {"check": "code_absent", "code": code},
            "evidence": {"context": "", "detail": "len=71"}}


def _built(tmp_path, route, html):
    d = tmp_path / "out" / route.strip("/")
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(html)
    return tmp_path / "out"


def test_a_fix_that_landed_passes(tmp_path):
    out = _built(tmp_path, "/roofing/", PAGE.format(
        title="Roofing Services in Charlotte NC Today", desc=GOOD_DESC,
        url="https://acme.com/roofing/"))
    ok, msg = acc.verify_item(_item(), out, {}, "acme.com")
    assert ok, msg


def test_a_fix_that_did_not_land_blocks(tmp_path):
    out = _built(tmp_path, "/roofing/", PAGE.format(
        title="Roofing Services in Charlotte NC Today", desc="too short",
        url="https://acme.com/roofing/"))
    ok, msg = acc.verify_item(_item(), out, {}, "acme.com")
    assert not ok and "STILL FIRES" in msg


def test_a_claimed_url_with_no_built_page_blocks(tmp_path):
    out = _built(tmp_path, "/roofing/", "<html></html>")
    ok, msg = acc.verify_item(_item(url="/siding/"), out, {}, "acme.com")
    assert not ok and "no page in the build output" in msg


def test_an_unimplemented_acceptance_check_blocks(tmp_path):
    out = _built(tmp_path, "/roofing/", "<html></html>")
    item = _item()
    item["acceptance"] = {"check": "vibes", "code": "health.desc_length"}
    ok, msg = acc.verify_item(item, out, {}, "acme.com")
    assert not ok and "not implemented" in msg


def test_no_changelog_is_a_skip_not_a_pass(make_project, monkeypatch, capsys):
    proj = make_project()
    monkeypatch.setattr("sys.argv", ["wf-acceptance-check", "--project", str(proj)])
    assert acc.main() == 0
    assert "[SKIP]" in capsys.readouterr().out


def test_acceptance_end_to_end_blocks_a_lie(make_project, monkeypatch, capsys):
    proj = make_project(pages={"/roofing/": PAGE.format(
        title="Roofing Services in Charlotte NC Today", desc="still too short",
        url="https://example.com/roofing/")})
    cycle = proj / "docs" / "audit" / "2026-08"
    cycle.mkdir(parents=True)
    (cycle / "changelog.json").write_text(json.dumps({"items": [_item()]}))
    monkeypatch.setattr("sys.argv", ["wf-acceptance-check", "--project", str(proj),
                                     "--out", str(proj / "out")])
    assert acc.main() == acc.FAILED_EXIT
    assert "STILL FIRES" in capsys.readouterr().out


# ── the three gates can never carry accepted debt ────────────────────────────

@pytest.mark.parametrize("gate", ["claim_provenance_check", "tier_check", "acceptance_check"])
def test_the_new_gates_are_never_baselineable(gate):
    assert gate in NEVER_BASELINEABLE
    with pytest.raises(BaselineError):
        assert_baselineable(gate)


# ── one end-to-end run over a real git repo ──────────────────────────────────

@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_tier_check_reads_a_real_git_diff(make_project):
    proj = make_project(config={
        "client": "acme", "domain": "acme.com",
        "topology_class": "single-site-single-state", "states_served": ["NC"],
        "tier": 1, "text_paths": ["src/data/**/*.ts"],
    })
    run = lambda *a: subprocess.run(["git", "-C", str(proj), *a], check=True,
                                    capture_output=True, text=True)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (proj / "src" / "data").mkdir(parents=True)
    (proj / "src" / "data" / "services.ts").write_text("export const a = 1\n")
    (proj / "src" / "app.tsx").write_text("export const B = 2\n")
    run("add", "-A")
    run("commit", "-qm", "base")
    (proj / "src" / "data" / "services.ts").write_text("export const a = 2\n")
    run("add", "-A")
    run("commit", "-qm", "in tier")

    changes = tc.changed_paths(proj, "HEAD~1", None)
    assert changes == [("M", "src/data/services.ts")]
    assert not tc.judge(client_profile(_cfg(proj), proj), changes)[1]

    (proj / "src" / "app.tsx").write_text("export const B = 3\n")
    run("add", "-A")
    run("commit", "-qm", "out of tier")
    changes = tc.changed_paths(proj, "HEAD~1", None)
    assert tc.judge(client_profile(_cfg(proj), proj), changes)[1], "must refuse src/app.tsx"
