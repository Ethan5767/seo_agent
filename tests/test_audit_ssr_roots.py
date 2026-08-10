"""B-027 — which files audit_ssr actually looks at, and what it does when there are none.

The scanner was never the problem. The directory lookup was: it looked for a
folder called `src/`, and exited **0** when it found none. `create-next-app` asks
whether you want a `src/` directory and the default answer is NO, so every client
who took the default had a never-baselineable correctness gate reporting success
over their entire codebase.

Two properties are tested here, and the second is the one that generalises:
  - the scan finds source wherever a repo actually keeps it, for layouts this
    codebase has never seen;
  - scanning zero files is a REFUSAL, not a pass. That holds for any framework,
    including ones `framework_family()` returns None for.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from pipeline.gates.audit_ssr import (CANNOT_JUDGE_EXIT, NON_SOURCE_DIRS,
                                      source_files)

UNSAFE = "export const x = document.body.className;\n"
SAFE = "export const x = typeof window !== 'undefined' ? window.name : '';\n"


def make(tmp_path, files: dict):
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return tmp_path


def run(project):
    return subprocess.run([sys.executable, "-m", "pipeline.gates.audit_ssr", str(project)],
                          capture_output=True, text=True)


# ── layouts ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("layout", [
    "src/app/page.tsx",          # Next with src/ — what the gate used to assume
    "app/page.tsx",              # Next app-router, no src/ — create-next-app's DEFAULT
    "pages/index.jsx",           # Next pages-router at the root
    "components/Thing.tsx",      # not a route dir at all
    "lib/util.ts",
    "islands/Counter.jsx",       # a framework this codebase has never heard of
])
def test_the_scan_finds_source_wherever_the_repo_keeps_it(tmp_path, layout):
    project = make(tmp_path, {layout: UNSAFE})
    r = run(project)
    assert r.returncode == 9, f"{layout}: {r.stdout}{r.stderr}"
    assert "1 files have SSR-dangerous patterns" in r.stdout


def test_an_unknown_framework_is_over_scanned_never_under_scanned():
    """The reason this is a denylist. `framework_family()` knows next, vite and
    wordpress; an allowlist keyed on it would scan NOTHING for anything else,
    which is B-027 again in a new hat."""
    from pipeline.lib.common import framework_family
    assert framework_family("qwik") is None
    assert "islands" not in NON_SOURCE_DIRS


# ── the refusal ──────────────────────────────────────────────────────────────

def test_zero_source_files_is_a_refusal_not_a_pass(tmp_path):
    project = make(tmp_path, {"README.md": "# nothing here\n"})
    r = run(project)
    assert r.returncode == CANNOT_JUDGE_EXIT
    assert "[REFUSED]" in r.stderr
    assert "cannot judge a tree it cannot see" in r.stderr


def test_a_repo_whose_only_js_is_excluded_still_refuses(tmp_path):
    """The dangerous shape: files exist, so a naive 'did we find any files at all'
    check passes, but every one of them is build output."""
    project = make(tmp_path, {"node_modules/pkg/i.js": UNSAFE, ".next/s/p.js": UNSAFE,
                              "dist/bundle.js": UNSAFE})
    r = run(project)
    assert r.returncode == CANNOT_JUDGE_EXIT


def test_wordpress_still_skips_cleanly(tmp_path):
    """A legitimate not-applicable, which is a different thing from cannot-judge
    and must stay exit 0."""
    project = make(tmp_path, {
        "docs/client-config.yml": "client: x\ndomain: x.test\nrepo:\n  framework: wordpress\n"})
    r = run(project)
    assert r.returncode == 0
    assert "[SKIP] WordPress" in r.stdout


# ── what is excluded, and why ────────────────────────────────────────────────

def test_build_output_and_dependencies_are_not_scanned(tmp_path):
    project = make(tmp_path, {"app/page.tsx": SAFE, "node_modules/bad/i.js": UNSAFE,
                              ".next/server/page.js": UNSAFE, "out/index.js": UNSAFE,
                              "public/vendor.js": UNSAFE, "dist/b.min.js": UNSAFE})
    rels = {str(p.relative_to(project)) for p in source_files(project)}
    assert rels == {"app/page.tsx"}
    assert run(project).returncode == 0


def test_the_configured_build_dir_is_excluded_even_when_it_is_unusual(tmp_path):
    """A repo emitting to `.output/` would otherwise have its own generated
    bundles reported as SSR violations in files nobody wrote."""
    project = make(tmp_path, {
        "app/page.tsx": SAFE, ".output/server/index.mjs": UNSAFE,
        "docs/client-config.yml":
            "client: x\ndomain: x.test\nrepo:\n  framework: next\n"
            "  build_output_dir: .output\n"})
    r = run(project)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_minified_bundle_committed_into_source_is_skipped(tmp_path):
    project = make(tmp_path, {"app/page.tsx": SAFE, "lib/analytics.min.js": UNSAFE})
    assert run(project).returncode == 0


def test_a_real_violation_outside_src_is_still_caught(tmp_path):
    """The whole point: this is the file that used to be invisible."""
    project = make(tmp_path, {"components/checkout/Portal.tsx": UNSAFE})
    r = run(project)
    assert r.returncode == 9
    assert "components/checkout/Portal.tsx" in (
        (project / "docs" / "audit-logs").rglob("audit-ssr.md").__next__().read_text())
