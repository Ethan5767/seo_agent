"""Smoke tests for two built-HTML gates against small crafted fixtures — one
passing, one failing each. Not exhaustive; they prove the gate wires up (config
load, page selection, exit code) end to end so a refactor that breaks the plumbing
is caught.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

ANSWER = (
    "A new roof in Charlotte typically runs a few thousand dollars, and the exact "
    "figure depends on the square footage, the roof pitch, and the material tier "
    "that you choose for the project. Our estimator walks the entire roof and hands "
    "you a written number before any work starts, so the price you see is the price "
    "you actually pay in full.")

CAPSULE_PASS = (
    "<!DOCTYPE html><html><head><title>Roofing in Charlotte, NC</title></head><body>"
    "<main><h1>Roofing in Charlotte, NC</h1>"
    "<h2>How much does a new roof cost in Charlotte, NC?</h2>"
    f"<p>{ANSWER}</p></main></body></html>")

CAPSULE_FAIL = (
    "<!DOCTYPE html><html><head><title>Roofing in Charlotte, NC</title></head><body>"
    "<main><h1>Roofing in Charlotte, NC</h1>"
    "<h2>Our Roofing Services</h2>"           # not interrogative
    f"<p>{ANSWER}</p></main></body></html>")

NONCOMMODITY_PASS = CAPSULE_PASS              # contains 'Charlotte' (nap.city token)

NONCOMMODITY_FAIL = (
    "<!DOCTYPE html><html><head><title>Roofing</title></head><body>"
    "<main><h1>Roofing</h1><h2>Services</h2>"
    "<p>We install and repair roofs across the region for homes and businesses.</p>"
    "</main></body></html>")                  # zero allow-list tokens


def _run(gate, proj):
    return subprocess.run(
        [sys.executable, "-m", f"pipeline.gates.{gate}", str(proj)],
        capture_output=True, text=True,
    )


def test_capsule_pass(make_project):
    proj = make_project(pages={"/roofing/": CAPSULE_PASS})
    r = _run("capsule_check", proj)
    assert r.returncode == 0, f"expected pass, got {r.returncode}\n{r.stdout}\n{r.stderr}"


def test_capsule_fail_non_interrogative_h2(make_project):
    proj = make_project(pages={"/roofing/": CAPSULE_FAIL})
    r = _run("capsule_check", proj)
    assert r.returncode == 6, f"expected exit 6, got {r.returncode}\n{r.stdout}\n{r.stderr}"


def test_noncommodity_pass(make_project):
    proj = make_project(pages={"/roofing/": NONCOMMODITY_PASS})
    r = _run("noncommodity_check", proj)
    assert r.returncode == 0, f"expected pass, got {r.returncode}\n{r.stdout}\n{r.stderr}"


def test_noncommodity_fail_generic_page(make_project):
    proj = make_project(pages={"/roofing/": NONCOMMODITY_FAIL})
    r = _run("noncommodity_check", proj)
    assert r.returncode == 7, f"expected exit 7, got {r.returncode}\n{r.stdout}\n{r.stderr}"


def test_noncommodity_empty_allowlist_exits_4(make_project):
    """No required_phrases and no NAP/owner tokens => refuse to run an empty
    differentiation gate (exit 4), same shape as the legal gate's exit 4."""
    cfg = {
        "client": "bare",
        "topology_class": "single-site-single-state",
        "states_served": ["NC"],
        "topology": "single-location-multi-metro",
        "repo": {"framework": "nextjs-app-router", "build_output_dir": "out"},
    }
    proj = make_project(config=cfg, pages={"/roofing/": NONCOMMODITY_PASS})
    r = _run("noncommodity_check", proj)
    assert r.returncode == 4, f"expected exit 4, got {r.returncode}\n{r.stdout}\n{r.stderr}"
