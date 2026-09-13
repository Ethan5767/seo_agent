"""Shared pytest fixtures for the gate test suite.

Everything here is HERMETIC: no network, no dependence on the real client repos.
The one real artifact borrowed from the pilot is a single sanitized Next.js RSC
flight-payload snippet, embedded in tests/fixtures/rsc_payload.html (client phone
numbers / GA ids scrubbed to placeholders). Every project a test needs is built
fresh under pytest's tmp_path via the `make_project` factory.
"""
from __future__ import annotations

import socket
import textwrap
from pathlib import Path

import pytest
import yaml

FIXTURES = Path(__file__).parent / "fixtures"


# ── hermetic for real (B-077) ────────────────────────────────────────────────
#
# The docstring above promised "no network" and the suite did not deliver it.
# `test_measure.py` calls `measure.main()`, which calls `load_env()`, which
# pushes the DEVELOPER'S real .env into os.environ for the remainder of the
# process. Everything downstream then inherits live credentials, and
# `lighthouse.py` picks up PAGESPEED_API_KEY and makes a real PageSpeed call —
# against a URL this project does not own.
#
# Measured: three live requests to www.googleapis.com per run, and 54 of the
# suite's 65 seconds spent waiting on them. The tests pass identically with the
# network blocked, so the calls bought nothing at all.
#
# The leak also made four DataForSEO tests fail in-suite while passing alone:
# the leaked DATAFORSEO_PAUSE_SPEND=1 reached code that was asserting retry
# behaviour. Those four were then hidden by an `addopts` exclusion, which is how
# a red test becomes invisible.
#
# Two guards, both autouse, both failing loudly rather than silently allowing.

@pytest.fixture(autouse=True)
def _no_real_dotenv(monkeypatch, tmp_path):
    """Point the .env loader at an empty temp dir.

    A test that wants a credential sets it explicitly with monkeypatch.setenv,
    which is visible in the test. Inheriting one from whoever happens to be
    running the suite is not a fixture, it is a coincidence.
    """
    import pipeline.lib.env as env
    monkeypatch.setattr(env, "REPO_ROOT", tmp_path, raising=False)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Any real socket is a test bug. Say which host, so it is findable."""
    def refuse(address, *a, **k):
        host = address[0] if isinstance(address, (tuple, list)) and address else address
        raise AssertionError(
            f"this test tried to reach {host} — the suite is hermetic. "
            f"Stub the boundary (curl, urlopen, the provider function) instead."
        )
    monkeypatch.setattr(socket, "create_connection", refuse)


# ── the reference forbidden-phrase rules (mirror config/client-config.starter.yml) ──
# Three rules exercise the three real legal-exposure classes: dollar figures, em
# dashes, and an insurance-claim phrase.
DOLLAR_RULE = {"pattern": r"\$[0-9]", "reason": "no dollar amounts on site"}
EM_DASH_RULE = {"pattern": "—", "reason": "no em dashes in deliverables"}
INSURANCE_RULE = {"pattern": r"(?i)waive\s+your\s+deductible",
                  "reason": "insurance-claim language restriction"}


def _minimal_config(**overrides):
    """A client-config.yml just rich enough for load_config / client_profile /
    the gates. Placeholder values only — never real client data."""
    cfg = {
        "client": "test-client",
        "domain": "example.com",
        "website": "https://example.com",
        "topology_class": "single-site-single-state",
        "site_count": 1,
        "states_served": ["NC"],
        "topology": "single-location-multi-metro",
        "repo": {
            "framework": "nextjs-app-router",
            "build_output_dir": "out",
        },
        "forbidden_phrases": [DOLLAR_RULE, EM_DASH_RULE],
        "required_phrases": ["Matthews", "Mint Hill"],
        "nap": {"city": "Charlotte", "street": "Main St"},
        "owner_name": "Jordan Wayne",
        "content": {"long_page_threshold": 1200},
    }
    cfg.update(overrides)
    return cfg


@pytest.fixture
def make_project(tmp_path):
    """Factory: build a self-contained client project under tmp_path.

    make_project(config=<dict|None>, pages=<{route: html}>, banned=<str|None>,
                 name=<slug>) -> Path to the project dir (holds docs/client-config.yml
    and, for any pages given, an `out/<route>/index.html` tree).
    """
    counter = {"n": 0}

    def _make(config=None, pages=None, banned=None, name=None):
        counter["n"] += 1
        proj = tmp_path / (name or f"proj{counter['n']}")
        docs = proj / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        if config is None:
            config = _minimal_config()
        (docs / "client-config.yml").write_text(yaml.safe_dump(config, sort_keys=False))
        if banned is not None:
            (docs / "banned-phrases.txt").write_text(banned)
        if pages:
            out = proj / "out"
            for route, html in pages.items():
                rel = route.strip("/")
                page_dir = out / rel if rel else out
                page_dir.mkdir(parents=True, exist_ok=True)
                (page_dir / "index.html").write_text(html)
        return proj

    return _make


@pytest.fixture
def rsc_payload_html():
    """The built-HTML fixture with $1/$L3 RSC tokens inside <script>/<style>
    (must be masked) and a visible $5,000, an em dash, and an insurance phrase in
    the body (must all match)."""
    return (FIXTURES / "rsc_payload.html").read_text()


@pytest.fixture
def forbidden_rules():
    return [DOLLAR_RULE, EM_DASH_RULE, INSURANCE_RULE]


def page_html(*, h2="How much does a new roof cost in Charlotte, NC?",
              answer=None, body_extra="", title="Roofing in Charlotte, NC",
              tokens="Our Matthews and Mint Hill crews"):
    """Build a minimal but capsule-valid service page. `answer` defaults to a
    40-80 word, <=3 sentence answer-first block so the capsule gate passes."""
    if answer is None:
        answer = (
            "A new roof in Charlotte typically runs a few thousand dollars, and "
            "the exact figure depends on the square footage, the roof pitch, and "
            "the material tier that you choose for the project. Our estimator "
            "walks the entire roof and hands you a written number before any work "
            "starts, so the price you see is the price you actually pay in full.")
    return textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="en"><head><title>{title}</title></head>
        <body><main>
        <h1>{title}</h1>
        <p>{tokens} have handled hundreds of local roofs.</p>
        <h2>{h2}</h2>
        <p>{answer}</p>
        {body_extra}
        </main>
        <script>self.__next_f.push([1,"0:{{\\"ref\\":\\"$L3\\",\\"n\\":\\"$1\\"}}"])</script>
        </body></html>
    """)
