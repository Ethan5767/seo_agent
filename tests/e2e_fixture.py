"""The E2E fixture site + its network seam.

Automation-spine Task 4. A tiny, self-contained client repo built fresh under
tmp_path, carrying EXACTLY two seeded SEO defects and nothing incidental:

    - health.title_length : the <title> is 72 chars (band is 30-60)  -> T1 fix
    - health.desc_missing : there is no <meta name="description">     -> T1 fix

Both are T1 copy edits (plan.ACTIONS), so a clean run ends at a low-risk,
all-gates-green change — the exact shape automerge.decide() calls AUTO. Every
other check in measure.check_page is deliberately satisfied so the measure step
finds those two findings and no others.

The site is served to the (network-free) measure step by `serve()`, which maps a
request URL back onto the on-disk out/<route>/index.html — the same files the
gates glob and the remediator edits. Source == built here on purpose: the
fixture proves the LOOP wiring, not a real client's source/build split.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

# The one route the fixture serves. Kept to a single page so the seeded-vs-found
# finding set is exact and the demo reads cleanly.
ROUTE = "services/"
DOMAIN = "example.com"
BASE = f"https://{DOMAIN}/"
URL = f"{BASE}{ROUTE}"

# A too-long title: 72 chars, above the 60 ceiling -> health.title_length.
BAD_TITLE = "Professional Roof Repair and Full Roof Replacement Services in Charlotte NC"
# The T1 fix: 43 chars, inside the 30-60 band.
GOOD_TITLE = "Roof Repair and Replacement in Charlotte NC"

# The meta description the desc_missing fix adds: 134 chars, inside the 120-160
# acceptance band, no $-figures and no em dash so the forbidden rules stay quiet.
DESC_TEXT = ("Trusted roof repair and full roof replacement across Charlotte NC, "
             "with clear written estimates and a workmanship warranty on every job.")
DESC_TAG = f'<meta name="description" content="{DESC_TEXT}">'


def apply_title_fix(html: str) -> str:
    """The in-band title, in place. Exactly what a correct T1 title fix does."""
    return html.replace(BAD_TITLE, GOOD_TITLE)


def apply_desc_fix(html: str) -> str:
    """Insert the meta description after </title>. No-op if one already exists."""
    if 'name="description"' in html:
        return html
    return html.replace("</title>\n", f"</title>\n{DESC_TAG}\n", 1)

# ~520 words of clean body copy so health.thin_content (<500 words) does NOT
# fire — we want only the two seeded findings. No $-figures and no em dashes, so
# the forbidden-phrase rules stay quiet. Plain prose, Title-Case headings.
_BODY_PARAS = [
    "Our roofing crews have served homeowners across the greater Charlotte "
    "region for more than two decades, and in that time we have built a "
    "reputation for careful work, honest estimates, and a finished result that "
    "holds up through every season. When a storm rolls through and lifts a row "
    "of shingles, or when years of sun and rain finally wear a roof down, the "
    "right response is a calm inspection and a clear plan rather than a rushed "
    "sales pitch, and that is exactly what our estimators bring to every home.",
    "A repair begins with a full walk of the roof. We check the field shingles, "
    "the ridge line, every valley, the flashing around each penetration, and "
    "the condition of the underlayment where it can be seen from the attic. "
    "Only after that walk do we hand you a written scope, because a number "
    "offered before the inspection is a guess, and a guess is how a small job "
    "quietly turns into a large invoice. You see the same photographs we take, "
    "and you decide what work goes forward.",
    "When a roof has reached the end of its service life, a replacement is the "
    "honest recommendation, and we say so plainly. A new roof is a considered "
    "investment in the home, and the value comes from doing it once and doing "
    "it correctly: a clean tear-off, a dry deck, fresh underlayment, and "
    "manufacturer-approved installation that keeps the warranty intact. We walk "
    "you through each material tier, explain how the choices change the look "
    "and the lifespan, and let the decision rest with you rather than with a "
    "commission.",
    "Every project ends the way it should, with the site swept clean, the "
    "gutters cleared of debris, and a magnetic sweep of the yard and driveway "
    "so that no stray nail finds a tire or a bare foot. We stand behind the "
    "workmanship in writing, we answer the phone after the job is done, and we "
    "treat the callback as seriously as the sale. That is the whole of our "
    "promise, and it is why so much of our work now comes from neighbors of "
    "the families we have already served across the county.",
    "Timing matters as much as workmanship. We schedule around the weather "
    "rather than against it, we stage materials so a tear-off is never left "
    "open to an evening storm, and we keep the crew size matched to the roof so "
    "the deck is dried in the same day it is opened. Homeowners are told what "
    "will happen on which day, and if the forecast turns we call before we "
    "load the truck, because the fastest roof is worth nothing if the attic "
    "takes on water while it waits for the next dry morning to arrive.",
    "Financing a roof should be as clear as inspecting one. We explain the "
    "written estimate line by line, we note which items are required and which "
    "are optional upgrades, and we never bundle a surprise into the final "
    "invoice. If a hidden problem appears once the old shingles come off, work "
    "stops and we show you the deck before we continue, so the change is your "
    "decision and not our assumption. Clear numbers and clear photographs are "
    "how trust is earned on a roof that a family cannot easily climb up to see.",
]


def page_html(*, title: str, with_desc: bool) -> str:
    """Build the fixture page. `title` and `with_desc` are the only knobs the
    seed and the fix touch — everything else is held clean and constant."""
    desc = (
        '<meta name="description" content="Trusted roof repair and full roof '
        'replacement across Charlotte NC, with written estimates, clean '
        'workmanship, and a workmanship warranty on every project we finish.">'
        if with_desc else ""
    )
    paras = "\n".join(f"<p>{p}</p>" for p in _BODY_PARAS)
    # An answer-first capsule (interrogative H2 + a 40-80 word, <=3 sentence
    # answer) so capsule_check gives a real PASS rather than failing a generic
    # page. Title Case heading, no $-figures, no em dash.
    capsule = (
        "<h2>How Much Does a New Roof Cost in Charlotte, NC?</h2>\n"
        "<p>A new roof in Charlotte typically runs a few thousand dollars, and "
        "the exact figure depends on the square footage, the roof pitch, and the "
        "material tier that you choose for the project. Our estimator walks the "
        "entire roof and hands you a written number before any work starts, so "
        "the price you see is the price you actually pay in full.</p>"
    )
    # A single JSON-LD block satisfies the LocalBusiness + BreadcrumbList schema
    # checks; og:image and canonical are present; exactly one <h1>.
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<title>{title}</title>
{desc}
<link rel="canonical" href="{URL}">
<meta property="og:image" content="{BASE}og.png">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"LocalBusiness","name":"Summit Roofing"}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[]}}
</script>
</head>
<body><main>
<h1>Roof Repair and Replacement in Charlotte</h1>
{capsule}
{paras}
</main></body>
</html>
"""


def fixture_config() -> dict:
    """A T1 client-config for the fixture. text_paths reaches the page files so a
    T1 copy edit to the title/meta is inside tier; forbidden_phrases keep the
    dollar and em-dash rules live; nap has no phone so those checks SKIP (not
    fire); no ga4 so that check SKIPs too."""
    return {
        "client": "e2e-fixture",
        "domain": DOMAIN,
        "website": BASE.rstrip("/"),
        "topology_class": "single-site-single-state",
        "site_count": 1,
        "states_served": ["NC"],
        "topology": "single-location-multi-metro",
        "tier": 1,  # int, per common.client_profile (a string like "T1" reads as no tier)
        "repo": {"framework": "nextjs-app-router", "build_output_dir": "out"},
        # T1 allow-list: the page files the agent may edit in place.
        "text_paths": ["out/**/*.html"],
        "forbidden_phrases": [
            {"pattern": r"\$[0-9]", "reason": "no dollar amounts on site"},
            {"pattern": "—", "reason": "no em dashes in deliverables"},
        ],
        "required_phrases": ["Charlotte"],
        "nap": {"city": "Charlotte", "street": "Main St"},
        "owner_name": "Jordan Wayne",
        "content": {"long_page_threshold": 1200},
    }


def build_fixture(root: Path, *, title: str = BAD_TITLE, with_desc: bool = False) -> Path:
    """Write the fixture client repo under `root` and git-init it (remediate
    measures changes via `git status`, so the tree must be a repo). Returns root.

    Defaults seed the two defects: the bad long title and the missing meta desc.
    """
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "client-config.yml").write_text(yaml.safe_dump(fixture_config(), sort_keys=False))

    page_dir = root / "out" / ROUTE.strip("/")
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "index.html").write_text(page_html(title=title, with_desc=with_desc))

    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=e2e@test", "-c", "user.name=e2e",
         "commit", "-q", "-m", "fixture: seed site")
    return root


def agent_that_fixes(root: Path):
    """A stand-in for remediate.run_agent: applies the ONE fix named by the item
    in the prompt, editing the page on disk. The real snapshot + tier_verdict
    machinery then measures the change — the test fakes the writer, not the
    verdict. Signature and return shape match run_agent: (ok, note, cost_usd)."""
    page = root / "out" / ROUTE.strip("/") / "index.html"

    def _agent(project, prompt, model, timeout, tools=None):
        html = page.read_text()
        if "health.title_length" in prompt:
            new = apply_title_fix(html)
        elif "health.desc_missing" in prompt:
            new = apply_desc_fix(html)
        else:
            return False, "NO CHANGE (unrecognized item)", 0.0
        if new == html:
            return True, "NO CHANGE (already applied)", 0.0
        page.write_text(new)
        return True, f"FIXED out/{ROUTE}index.html", 0.0

    return _agent


def serve(root: Path):
    """Return (curl, curl_status) stand-ins closed over the fixture tree.

    They map a request URL onto out/<route>/index.html, so the real measure.main
    runs unchanged with no network. An unknown route reports status 0 (curl's
    connection-failure signal), matching common.curl_status semantics.
    """
    def _file_for(url: str) -> Path:
        rel = url[len(BASE):].strip("/") if url.startswith(BASE) else url.strip("/")
        return root / "out" / rel / "index.html"

    def curl(url: str, cache_bust: bool = True) -> str:
        f = _file_for(url)
        return f.read_text() if f.is_file() else ""

    def curl_status(url: str, follow: bool = True) -> int:
        return 200 if _file_for(url).is_file() else 0

    return curl, curl_status


def head_sha(root: Path) -> str:
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def commit_fix(root: Path, branch: str = "seo-fix") -> str:
    """Commit remediate's working-tree edits onto a PR branch and return the base
    SHA (the seeded commit) to diff against — the shape tier_check judges in CI."""
    base = head_sha(root)
    _git(root, "checkout", "-q", "-b", branch)
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=e2e@test", "-c", "user.name=e2e",
         "commit", "-q", "-m", "seo: apply T1 fixes")
    return base


# The gates a T1 copy edit is responsible for and that judge built HTML / the
# diff standalone. NOT the full 19-gate CI suite (TSC/SSR/LCP/etc. need the
# client's real framework build and run in the client repo's Actions, by design
# — CLAUDE.md "Where Workflows Live"). These are the ones the fix itself must
# satisfy, each run with its real CLI.
def run_gates(root: Path, base: str) -> dict:
    """Return {gate_name: exit_code} for the content-gate set, run from the
    project dir so each gate's default ./out resolves to the fixed tree."""
    P = str(root)
    specs = {
        "tier_check":         ["tier_check", "--project", P, "--base", base],
        "acceptance_check":   ["acceptance_check", "--project", P],
        "check_headings":     ["check_headings", "--project", P],
        "forbidden_sweep":    ["forbidden_sweep", "built", P],
        "noncommodity_check": ["noncommodity_check", P],
        "capsule_check":      ["capsule_check", P],
        "em_dash_check":      ["em_dash_check", "--out", str(root / "out")],
    }
    out = {}
    for name, args in specs.items():
        r = subprocess.run([sys.executable, "-m", f"pipeline.gates.{args[0]}", *args[1:]],
                           cwd=P, capture_output=True, text=True)
        out[name] = r.returncode
    return out


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True)
