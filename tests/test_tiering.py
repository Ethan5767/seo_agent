"""Phase 2 — the tier declaration (v3 §2) and the static-export precondition (§6).

The load-bearing properties: the deny-list is a floor a config cannot remove, an
incoherent tier is fatal while an absent one is not (wf-client-profile exits 5 on
ERROR and runs in every client's build), and a site that does not statically export
is flagged rather than silently gating nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pipeline.audit.bootstrap_config import add_tier, detect_text_paths, tier_block
from pipeline.lib.common import (
    DEFAULT_DENY,
    client_profile,
    detect_static_export,
    validate_profile,
)


def errors(prof):
    return [m for lvl, m in validate_profile(prof) if lvl == "ERROR"]


def warns(prof):
    return [m for lvl, m in validate_profile(prof) if lvl == "WARN"]


BASE = {                      # a config that is otherwise clean, so only tier issues show
    "client": "acme",
    "domain": "acme.com",
    "topology_class": "single-site-single-state",
    "states_served": ["NC"],
    "repo": {"framework": "nextjs-app-router"},
}


def cfg(**over):
    out = dict(BASE)
    out.update(over)
    return out


# ── the profile ──────────────────────────────────────────────────────────────

def test_tier_block_parsed_into_the_profile():
    prof = client_profile(cfg(
        tier=2,
        text_paths=["src/data/**/*.ts"],
        content={"location": "src/content/blog/", "registry": ["src/data/posts.ts"], "format": "mdx"},
    ))
    assert prof["tier"] == 2
    assert prof["text_paths"] == ["src/data/**/*.ts"]
    assert prof["content_location"] == "src/content/blog/"
    assert prof["content_registry"] == ["src/data/posts.ts"]
    assert prof["content_format"] == "mdx"


def test_absent_tier_is_none_but_garbage_tier_is_kept_raw():
    """None vs 'one' must stay distinguishable: absent is safe, garbage is fatal."""
    assert client_profile(cfg())["tier"] is None
    prof = client_profile(cfg(tier="one"))
    assert prof["tier"] is None and prof["tier_declared"] == "one"


def test_deny_is_a_union_a_config_cannot_shrink():
    prof = client_profile(cfg(tier=1, deny=["src/generated/**"]))
    assert set(DEFAULT_DENY).issubset(prof["deny"])
    assert "src/generated/**" in prof["deny"]


def test_deny_floor_survives_an_empty_deny_key():
    assert client_profile(cfg(tier=1, deny=[]))["deny"] == DEFAULT_DENY


# ── validation ───────────────────────────────────────────────────────────────

def test_missing_tier_warns_but_never_blocks_a_build():
    prof = client_profile(cfg())
    assert errors(prof) == []
    assert any("no `tier:` declared" in m for m in warns(prof))


@pytest.mark.parametrize("bad", [0, 4, "1", True])
def test_incoherent_tier_is_fatal(bad):
    assert any("is not 1, 2 or 3" in m for m in errors(client_profile(cfg(tier=bad))))


def test_tier_with_no_text_paths_is_fatal():
    """An empty allow-list permits nothing — a T1 that can fix zero findings."""
    assert any("text_paths is empty" in m for m in errors(client_profile(cfg(tier=1))))


def test_t2_without_content_location_is_fatal():
    prof = client_profile(cfg(tier=2, text_paths=["src/data/**/*.ts"]))
    assert any("tier 2+ requires content.location" in m for m in errors(prof))


def test_t2_without_registry_warns_about_the_orphan():
    prof = client_profile(cfg(tier=2, text_paths=["a/**"], content={"location": "src/content/blog/"}))
    assert errors(prof) == []
    assert any("orphan_check" in m for m in warns(prof))


def test_clean_t1_has_no_tier_findings(tmp_path):
    (tmp_path / "next.config.mjs").write_text("export default { output: 'export' };\n")
    prof = client_profile(cfg(tier=1, text_paths=["src/data/**/*.ts"]), tmp_path)
    assert errors(prof) == []
    assert not any("tier" in m or "static export" in m for m in warns(prof))


# ── the static-export precondition ───────────────────────────────────────────

@pytest.mark.parametrize("body,expected", [
    ("export default { output: 'export' };", True),
    ('module.exports = { output: "export" };', True),
    ("export default { images: { unoptimized: true } };", False),
])
def test_next_static_export_read_from_the_config(tmp_path, body, expected):
    (tmp_path / "next.config.mjs").write_text(body)
    assert detect_static_export(tmp_path, "next", "nextjs-app-router") is expected


def test_static_export_unknown_without_a_next_config(tmp_path):
    assert detect_static_export(tmp_path, "next", "nextjs-app-router") is None


def test_vite_is_static_only_when_the_framework_says_ssg(tmp_path):
    """A plain Vite SPA emits ONE index.html; only the SSG variant emits a tree."""
    assert detect_static_export(tmp_path, "vite", "vite-react-ssg-custom") is True
    assert detect_static_export(tmp_path, "vite", "vite") is None


def test_wordpress_is_never_a_static_export(tmp_path):
    assert detect_static_export(tmp_path, "wordpress", "wordpress") is False


def test_non_static_site_warns_that_two_gates_go_green_on_nothing(tmp_path):
    prof = client_profile(
        cfg(tier=1, text_paths=["a/**"], repo={"framework": "wordpress"}), tmp_path)
    msgs = warns(prof)
    assert any("NOT a static export" in m and "report GREEN" in m for m in msgs)


def test_unconfirmed_static_export_warns_rather_than_assuming(tmp_path):
    prof = client_profile(cfg(tier=1, text_paths=["a/**"]), tmp_path)   # no next.config
    assert any("could not be confirmed" in m for m in warns(prof))


# ── bootstrap: writing the block ─────────────────────────────────────────────

def test_detect_text_paths_only_returns_dirs_that_exist(tmp_path):
    (tmp_path / "src" / "data").mkdir(parents=True)
    assert detect_text_paths(tmp_path) == ["src/data/**/*.ts"]


def test_emitted_block_parses_and_carries_the_deny_floor(tmp_path):
    import yaml
    (tmp_path / "src" / "data").mkdir(parents=True)
    parsed = yaml.safe_load(tier_block(tmp_path))
    assert parsed["tier"] == 1
    assert parsed["text_paths"] == ["src/data/**/*.ts"]
    assert parsed["deny"] == DEFAULT_DENY
    assert "content" not in parsed       # T2 stays commented out until it is earned


def test_add_tier_appends_to_an_existing_config_without_eating_comments(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "client-config.yml"
    target.write_text("# hand-written comment\nclient: acme\ndomain: acme.com\n")
    assert add_tier(target) == 0
    text = target.read_text()
    assert "# hand-written comment" in text
    import yaml
    assert yaml.safe_load(text)["tier"] == 1


def test_bootstrapped_config_is_loadable_yaml_carrying_the_tier(tmp_path, monkeypatch):
    """B-002: the repo template block was missing its f-string prefix, so every
    generated config carried a literal `{framework}` and `per_service: {{}}` and
    PyYAML refused the whole file — the tier declaration included."""
    import yaml
    from pipeline.audit import bootstrap_config as bc

    (tmp_path / "src" / "data").mkdir(parents=True)
    (tmp_path / "next.config.mjs").write_text("export default { output: 'export' };")
    monkeypatch.setattr(bc, "curl", lambda *a, **k: "")
    monkeypatch.setattr(bc, "extract_from_docs", lambda p: {
        "forbidden_rules": [], "services_hints": [], "keyword_hints": []})
    monkeypatch.setattr(sys, "argv", ["bootstrap-config.py", str(tmp_path), "acme.com"])
    bc.main()

    parsed = yaml.safe_load((tmp_path / "docs" / "client-config.yml").read_text())
    assert parsed["tier"] == 1
    assert parsed["text_paths"] == ["src/data/**/*.ts"]
    assert parsed["repo"]["framework"] == "nextjs-app-router"
    assert parsed["h1_format"]["per_service"] == {}


def test_add_tier_is_a_no_op_when_a_tier_already_exists(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "client-config.yml"
    target.write_text("client: acme\ntier: 3\n")
    assert add_tier(target) == 0
    assert target.read_text() == "client: acme\ntier: 3\n"


# ── the tier is declared at onboarding (T1 default, T2 needs its fields) ─────
# The picker is not a relaxation of the tier model: docs/client-config.yml stays on
# the deny floor at every tier, so the AGENT still cannot raise its own authority,
# and wf-onboard writes this into a commit on the default branch. What changed is
# WHEN the human declares it.

from pipeline.audit.bootstrap_config import build_parser, registry_paths, tier_block
from pipeline.lib.common import TierRefused, UnsafePath


def test_the_default_tier_is_one(tmp_path):
    assert "tier: 1" in tier_block(tmp_path)


def test_t3_needs_no_content_block(tmp_path):
    block = tier_block(tmp_path, 3)
    assert "tier: 3" in block
    # T3 may create anything not denied, so a content location does not constrain
    # it. Writing one would imply it does.
    assert "# content:" in block


def test_t2_is_refused_without_a_content_location(tmp_path):
    with pytest.raises(TierRefused, match="content location"):
        tier_block(tmp_path, 2, content_registry=["src/data/posts.ts"])


def test_t2_is_refused_without_a_registry(tmp_path):
    # A location with no registry is the worse half: the agent creates a page,
    # nothing links to it, and orphan_check refuses the PR after the spend.
    with pytest.raises(TierRefused, match="registry path"):
        tier_block(tmp_path, 2, content_location="src/content/blog/")


def test_a_refused_t2_is_never_silently_downgraded(tmp_path):
    # The failure mode this replaces: a config that says T2 and behaves as T1.
    try:
        tier_block(tmp_path, 2)
    except TierRefused as exc:
        assert "authority over nowhere" in str(exc)
    else:
        raise AssertionError("T2 with neither field was written")


def test_a_complete_t2_writes_a_real_content_block(tmp_path):
    block = tier_block(tmp_path, 2, "src/content/blog/", ["src/data/posts.ts"])
    assert "tier: 2" in block
    assert "location: src/content/blog/" in block
    assert "registry: [src/data/posts.ts]" in block
    assert "# content:" not in block


def test_the_deny_floor_is_written_at_every_tier(tmp_path):
    for tier in (1, 2, 3):
        block = tier_block(tmp_path, tier, "src/content/", ["src/data/p.ts"])
        # The one line that makes the picker safe: whatever tier the operator
        # chose, the agent can never edit the file that declares it.
        assert "docs/client-config.yml" in block
        assert ".github/**" in block


@pytest.mark.parametrize("bad", ["../escape", "-flag", "/abs/path"])
def test_a_content_path_that_is_not_repo_relative_is_refused(tmp_path, bad):
    with pytest.raises(UnsafePath):
        tier_block(tmp_path, 3, content_location=bad)


def test_an_out_of_range_tier_is_refused(tmp_path):
    with pytest.raises(TierRefused, match="1, 2 or 3"):
        tier_block(tmp_path, 4)


def test_the_tier_flag_takes_a_value_and_does_not_eat_the_domain():
    # The old hand-rolled argv filter dropped `--add-tier` by equality, which would
    # have left `2` from `--tier 2` sitting where DOMAIN goes. argparse cannot make
    # that mistake, which is the reason to use it.
    args = build_parser().parse_args(
        ["/tmp/acme", "acme.com", "--tier", "2", "--content-location", "src/c/",
         "--content-registry", "a.ts,b.ts"])
    assert args.domain == "acme.com"
    assert (args.tier, args.content_location) == (2, "src/c/")
    assert registry_paths(args.content_registry) == ["a.ts", "b.ts"]
    assert args.add_tier is False


def test_a_registry_is_repeatable_as_well_as_comma_separated():
    args = build_parser().parse_args(
        ["/tmp/a", "a.com", "--content-registry", "a.ts", "--content-registry", "b.ts,c.ts"])
    assert registry_paths(args.content_registry) == ["a.ts", "b.ts", "c.ts"]


def test_argparse_refuses_an_out_of_range_tier_without_our_own_check(capsys):
    # `choices=(1,2,3)` does what a hand-rolled `re.fullmatch(r"[123]")` did.
    with pytest.raises(SystemExit):
        build_parser().parse_args(["/tmp/a", "a.com", "--tier", "4"])
    assert "invalid choice" in capsys.readouterr().err
