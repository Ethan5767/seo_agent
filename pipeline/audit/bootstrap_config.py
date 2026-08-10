#!/usr/bin/env python3
"""Auto-generate docs/client-config.yml for a client repo.

Reads CLAUDE.md, sitemap.xml, live homepage schema, and repo files.
Prefills whatever can be auto-detected. Marks everything else TODO.

The agent that invokes this is expected to INTERVIEW Alex (via AskUserQuestion)
to resolve the TODOs — services offered, forbidden phrases, FAQ seeds,
target keywords. Never guesses those — every client is unique.

Never overwrites an existing config.

Usage: python3 bootstrap-config.py [PROJECT_DIR] [DOMAIN]
"""
import argparse
import sys, re, json
from pathlib import Path
from pipeline.lib.common import TierRefused, curl, resolve_tier, yaml


def detect_deploy_platform(project_dir: Path) -> str:
    if (project_dir / "wrangler.toml").exists(): return "cloudflare-pages"
    if (project_dir / "vercel.json").exists(): return "vercel"
    if (project_dir / "netlify.toml").exists(): return "netlify"
    if (project_dir / "wp-config.php").exists(): return "wordpress"
    if (project_dir / "next.config.mjs").exists() or (project_dir / "next.config.js").exists():
        return "cloudflare-pages"
    return "TODO"


def detect_framework(project_dir: Path) -> str:
    if (project_dir / "next.config.mjs").exists() or (project_dir / "next.config.js").exists():
        return "nextjs-app-router"
    if (project_dir / "vite.config.ts").exists() or (project_dir / "vite.config.js").exists():
        return "vite-ssg"
    if (project_dir / "wp-config.php").exists():
        return "wordpress"
    return "TODO"


def detect_topology(sitemap_xml: str) -> str:
    urls = re.findall(r"<loc>https?://[^/]+(/[^<]*)</loc>", sitemap_xml)
    paths = [u for u in urls if u != "/"]
    if not paths: return "TODO"
    state_first = sum(1 for p in paths if re.match(r"^/[a-z]{2}/[a-z]", p))
    metro_first = sum(1 for p in paths if re.match(r"^/[a-z0-9-]+-[a-z]{2}/", p))
    hubspoke = sum(1 for p in paths if re.match(r"^/[a-z0-9-]+/[a-z0-9-]+-[a-z]{2}/", p))
    total = len(paths)
    if state_first / total > 0.3: return "multi-state-chain"
    if metro_first / total > 0.3: return "franchise"
    if hubspoke / total > 0.1: return "single-location-multi-metro"
    return "single-location-single-city"


def extract_from_claudemd(path: Path) -> dict:
    if not path.exists(): return {}
    text = path.read_text()
    out = {}
    m = re.search(r"\*\*(?:Phone|Tel|Contact)[^:]*:\*\*\s*([\(\d][\d\s\-\)\.]+)", text)
    if m: out["phone"] = m.group(1).strip()
    m = re.search(r"\*\*Address[^:]*:\*\*\s*([^\n]+)", text)
    if m: out["address"] = m.group(1).strip()
    m = re.search(r"\*\*Email[^:]*:\*\*\s*([\w@.\-]+)", text)
    if m: out["email"] = m.group(1).strip()
    m = re.search(r"Rating:\s*(\d\.\d)\s*stars?\s*/?\s*(\d+)\s*reviews", text, re.I)
    if m: out["rating"], out["reviews"] = m.group(1), int(m.group(2))
    m = re.search(r"(\d+)\+?\s*years?\s+(?:in business|serving)", text, re.I)
    if m: out["years"] = int(m.group(1))
    m = re.search(r"GA4?[^:]*:\s*`?(G-[A-Z0-9]+)", text)
    if m: out["ga4"] = m.group(1)
    m = re.search(r"Clarity[^:]*project\s+(\w+)", text, re.I)
    if m: out["clarity"] = m.group(1)
    m = re.search(r"GBP:\s*(https?://[^\s\)]+)", text, re.I)
    if m: out["gbp_url"] = m.group(1)
    return out


def extract_from_docs(project_dir: Path) -> dict:
    """Scan docs/ + memory/ for client-specific rules, services, keywords."""
    out = {"forbidden_rules": [], "services_hints": [], "keyword_hints": []}
    search_paths = []
    docs = project_dir / "docs"
    if docs.exists():
        search_paths.extend(docs.rglob("*.md"))
    # Memory lives at ~/.claude/projects/[project-slug]/memory/
    mem_root = Path.home() / ".claude" / "projects"
    if mem_root.exists():
        project_marker = project_dir.name.lower()
        for p in mem_root.iterdir():
            if project_marker in p.name.lower():
                mem = p / "memory"
                if mem.exists(): search_paths.extend(mem.rglob("*.md"))

    for f in search_paths:
        try: text = f.read_text()
        except Exception: continue
        # Forbidden rules: "NEVER [do X]" or "do NOT [do X]"
        for m in re.finditer(r"(?:NEVER|Never|do NOT|DO NOT)\s+([^.\n]+)", text):
            rule = m.group(1).strip()[:120]
            if rule and rule not in [r["reason"] for r in out["forbidden_rules"]]:
                out["forbidden_rules"].append({"reason": rule, "source": f.name})
        # Services — look for Services headings
        for m in re.finditer(r"(?:^|\n)(?:###?\s+)?[Ss]ervices?(?:\s+[Oo]ffered)?[:\n]([^\n#]{20,500})", text):
            chunk = m.group(1)
            for bullet in re.findall(r"(?:^|\n)[-*]\s+\*?\*?([A-Z][^:\n*]{3,80})", chunk):
                out["services_hints"].append(bullet.strip())
        # Target keyword hints — look for "target keyword" or keyword tables
        for m in re.finditer(r'"([a-z][a-z0-9 \-]{5,60})"\s*(?:\||:)', text):
            kw = m.group(1).strip()
            if any(c.isalpha() for c in kw) and " " in kw:
                out["keyword_hints"].append(kw)
    out["services_hints"] = list(dict.fromkeys(out["services_hints"]))[:20]
    out["keyword_hints"] = list(dict.fromkeys(out["keyword_hints"]))[:30]
    return out


def extract_from_live(domain: str) -> dict:
    out = {}
    html = curl(f"https://{domain}/", cache_bust=True)
    if not html: return out
    m = re.search(r'"name":"([^"]+)"', html)
    if m: out["business_name"] = m.group(1)
    m = re.search(r'"ratingValue":"?(\d\.\d)"?', html)
    if m: out["rating"] = m.group(1)
    m = re.search(r'"reviewCount":\s*"?(\d+)"?', html)
    if m: out["reviews"] = int(m.group(1))
    m = re.search(r'"sameAs":\s*\[([^\]]+)\]', html)
    if m:
        for url in re.findall(r'"(https?://[^"]+)"', m.group(1)):
            if "google.com" in url or "g.co" in url or "share.google" in url:
                out["gbp_url"] = url
                break
    m = re.search(r"G-[A-Z0-9]{8,}", html)
    if m: out["ga4"] = m.group(0)
    return out


def detect_text_paths(project_dir: Path) -> list:
    """Globs for existing files the agent may reword at T1. Only directories that
    are actually on disk: a glob matching nothing is an allow-list permitting
    nothing, which reads as a working T1 and fixes zero findings."""
    candidates = [
        ("src/data", "src/data/**/*.ts"),
        ("src/content", "src/content/**/*.mdx"),
        ("content", "content/**/*.md"),
        ("app", "app/**/*.mdx"),
    ]
    return [glob for d, glob in candidates if (project_dir / d).is_dir()]


def tier_block(project_dir: Path, tier: int = 1, content_location: str = "",
               content_registry=None) -> str:
    """The v3 §2 tiering block.

    Defaults to T1 — the tier that can only reword what already exists — because
    raising a tier is a deliberate act, never something you get by omission.

    The rules live in `common.resolve_tier`, which the dashboard's onboard endpoint
    calls too: T2 is refused without both content fields, and paths are validated by
    `common.safe_path`. Stating either here as well would be the same rule in two
    places, agreeing until someone edits one.
    """
    tier, location, registry = resolve_tier(tier, content_location, content_registry)

    found = detect_text_paths(project_dir)
    paths = "\n".join(f"  - {p}" for p in found) if found else \
        "  # - src/data/**/*.ts        TODO: the files the agent may reword"

    if location:
        reg = ", ".join(registry)
        content = f"""content:                          # T2+ — where the agent may CREATE
  location: {location}
  registry: [{reg}]
"""
    else:
        content = """# content:                        # T2+ ONLY. No content.location -> T2 is unavailable.
#   location: src/content/blog/
#   registry: [src/data/posts.ts] # the nav/data file a new page must be wired into,
#                                 # or orphan_check refuses the PR anyway
#   format: mdx
"""

    return f"""
# ── Tiering (v3 §2) — the agent's authority over THIS repo ────────────────────
# T1 copy   : modify text_paths only. No creates, no deletes.
# T2 content: T1 + create under content.location, wire into content.registry.
# T3 full   : anything not denied.
# Enforced by tier_check against the PR diff — not by the prompt, not by trust.
#
# Declared by the operator at onboarding, in a commit on the DEFAULT branch. The
# agent can never change this file at any tier — see the deny floor below — so it
# can never raise its own authority.
tier: {tier}
text_paths:                       # EXISTING files the agent may rewrite
{paths}
{content}deny:                             # applies at EVERY tier, T3 included
  - .github/**                    # the agent must never edit the gates that judge it
  - docs/client-config.yml        # must never raise its own tier
  - package*.json                 # no dependency changes
  - wrangler.toml                 # deploy config is the rollback path
  - .env*
  - docs/banned-phrases.txt       # the other half of the legal ruleset — deleting it
                                  # must never be a way to disarm forbidden_sweep
  - docs/human-worklist.md        # the fix queue's skip list; writing it would let the
                                  # agent permanently dequeue its own work
"""


def add_tier(target: Path, tier: int = 1, content_location: str = "",
             content_registry=None) -> int:
    """Append the tier block to an EXISTING config. Appending rather than
    round-tripping through PyYAML is the whole point: a 16KB starter file is mostly
    comments, and yaml.safe_load/dump would eat every one of them.

    Takes the same tier arguments as the fresh-config path so raising a tier later
    runs one code path, not a second one that drifts from it."""
    text = target.read_text()
    if re.search(r"^tier:", text, re.M):
        print(f"[OK] {target} already declares a tier."); return 0
    block = tier_block(target.parent.parent, tier, content_location, content_registry)
    target.write_text(text.rstrip("\n") + "\n" + block)
    print(f"[OK] Appended the tier block to {target} (tier: {tier})")
    print("[NEXT] Confirm text_paths matches this repo, then `wf-client-profile <dir>`.")
    return 0


def warn_unresolved_registry(project_dir: Path, content_registry) -> None:
    """A registry file that is not on disk is the wiring target for a page that
    does not exist yet, so it is a WARN here and an ERROR from validate_profile —
    the seam where config coherence already stops the run (wf-client-profile
    exit 5). Saying it at onboarding costs nothing and saves a cycle."""
    for rel in content_registry or []:
        if not (project_dir / rel).exists():
            print(f"[WARN] content.registry '{rel}' is not on disk. A new page has "
                  f"nothing to be wired into, and orphan_check refuses an unlinked "
                  f"page. Confirm the path before remediating at T2.")


# argparse, like every other entry point in this package — including onboard.py,
# which declares these same three flags in three lines. The old hand-rolled
# `[a for a in argv if a != "--add-tier"]` filter worked only because no flag took a
# value; `--tier 2` is two tokens, which is what broke it. That the style ran out is
# a reason to stop matching it, not to extend it by forty lines.
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="wf-bootstrap-config",
        description="Generate docs/client-config.yml, or append the tiering block.")
    ap.add_argument("project_dir", type=Path)
    ap.add_argument("domain")
    ap.add_argument("--add-tier", action="store_true",
                    help="append the tier block to an existing config and stop")
    ap.add_argument("--tier", type=int, choices=(1, 2, 3), default=1,
                    help="the agent's authority over this repo (default: 1, copy only)")
    ap.add_argument("--content-location", default="",
                    help="T2+: the directory the agent may CREATE pages under")
    # Repeatable AND comma-separated: a registry is usually one file and
    # occasionally two, and both spellings are what a caller reaches for.
    ap.add_argument("--content-registry", action="append", default=[], metavar="PATH",
                    help="T2+: the nav/data file a new page must be wired into")
    return ap


def registry_paths(values) -> list:
    return [p for v in values for p in str(v).split(",") if p.strip()]


def main():
    args = build_parser().parse_args()
    project_dir = args.project_dir.resolve()
    registry = registry_paths(args.content_registry)

    target = project_dir / "docs" / "client-config.yml"
    if target.exists():
        if args.add_tier:
            try:
                code = add_tier(target, args.tier, args.content_location, registry)
            except TierRefused as e:
                print(f"[STOP] {e}", file=sys.stderr); sys.exit(4)
            warn_unresolved_registry(project_dir, registry)
            sys.exit(code)
        print(f"[OK] Config already exists: {target}"); sys.exit(0)
    target.parent.mkdir(exist_ok=True)

    domain = args.domain
    tier = args.tier

    # Built BEFORE anything is written or fetched: a refused tier must cost a
    # message, not a half-scaffolded checkout and a network round-trip.
    try:
        tier_yaml = tier_block(project_dir, tier, args.content_location, registry)
    except TierRefused as e:
        print(f"[STOP] {e}", file=sys.stderr); sys.exit(4)

        print(f"[STOP] {e}", file=sys.stderr); sys.exit(4)

    claude = extract_from_claudemd(project_dir / "CLAUDE.md")
    docs_intel = extract_from_docs(project_dir)
    live = extract_from_live(domain)
    sitemap = ""
    sm_file = project_dir / "public" / "sitemap.xml"
    if sm_file.exists(): sitemap = sm_file.read_text()
    topology = detect_topology(sitemap)
    platform = detect_deploy_platform(project_dir)
    framework = detect_framework(project_dir)
    rating = claude.get("rating") or live.get("rating", "TODO")
    reviews = claude.get("reviews") or live.get("reviews", "TODO")
    phone = claude.get("phone", "TODO")
    phone_tel = re.sub(r"\D", "", phone) if phone != "TODO" else "TODO"
    client_slug = project_dir.name.lower().replace(" ", "-").split("-")[0]

    config = f"""# Auto-generated by bootstrap-config.py — INTERVIEW ALEX TO RESOLVE TODOs.
# Every TODO must be replaced with real client-specific data before pipeline runs.
client: {client_slug}
domain: {domain}
deploy_platform: {platform}
topology: {topology}
{tier_yaml}
business:
  legal_name: "{live.get('business_name', 'TODO')}"
  trade: "TODO"                 # free-form, e.g. "demolition & excavation"
  services_offered: []          # ask client: list EXACTLY what they do
  services_not_offered: []      # explicit exclusions — becomes forbidden phrases
  customer_types: []            # ["commercial", "residential", "municipal", etc.]

nap:
  name: "{live.get('business_name', 'TODO')}"
  address: "{claude.get('address', 'TODO')}"
  phone: "{phone}"
  phone_tel: "{phone_tel}"
  email: "{claude.get('email', 'TODO')}"
  hours: "TODO"

trust_signals:
  rating: "{rating}"
  reviews: {reviews}
  years_in_business: {claude.get('years', 'TODO')}
  fleet_or_team: "TODO"         # optional
  certifications: []            # ask client: ["NJDEP", "NATE", "GAF Master Elite", etc.]
  licenses: []                  # state license numbers if public-facing
  insurance_coverage: "TODO"    # e.g. "General liability + workers comp" (NO dollar amounts)

states_served: []               # ["NJ", "PA"]
primary_metro: "TODO"
service_areas: []

offices: []                     # multi-office only; [] for single-location

gbp_url: "{claude.get('gbp_url') or live.get('gbp_url', 'TODO')}"
gsc_property: "sc-domain:{domain}"
bing_property: "TODO"
ga4_id: "{claude.get('ga4') or live.get('ga4', 'TODO')}"
ms_clarity_id: "{claude.get('clarity', 'TODO')}"

# Deal-breakers per client. Start with the universal no-price rule.
# Rules auto-discovered from docs/ + memory/ appear below as hints — agent must
# convert each into a real regex pattern during onboarding interview.
forbidden_phrases:
  - pattern: '\\$[0-9]'
    reason: "Default: no dollar amounts visible on site. Override only if client wants pricing."
"""
    # Append discovered rules as commented hints for the agent to convert
    if docs_intel["forbidden_rules"]:
        config += "  # Hints from client docs/memory — convert each to a real regex:\n"
        for r in docs_intel["forbidden_rules"][:15]:
            config += f"  # - pattern: 'TODO'  # {r['reason']}  [from {r['source']}]\n"
    config += """
required_phrases: []

schema_type: "LocalBusiness"    # override only if schema.org subtype actually matches

# Populated at onboarding from: GBP Q&A, sales calls, competitor FAQs,
# DataForSEO "people also ask" data. Not pre-canned.
faq_seed_questions: []

target_keywords:
  primary: []                   # 5-10 highest-priority keywords from DataForSEO
  secondary: []
"""
    if docs_intel["keyword_hints"]:
        config += "  # Hints from client docs:\n"
        for kw in docs_intel["keyword_hints"][:20]:
            config += f"  # - {kw}\n"
    if docs_intel["services_hints"]:
        config += "\n# Services detected in client docs (review, dedupe, confirm with client):\n"
        for s in docs_intel["services_hints"][:15]:
            config += f"# - {s}\n"
    # f-string: this block interpolates {framework} and escapes its literal braces.
    # Without the prefix it emitted `framework: {framework}` and `per_service: {{}}`
    # verbatim, and PyYAML refused the whole file (B-002).
    config += f"""
repo:
  framework: {framework}
  route_file: "TODO"
  prerender_config: "TODO"
  sitemap: "public/sitemap.xml"
  llms_txt: "public/llms.txt"
  pages_dir: "TODO"
  template_hub: "TODO"
  template_spoke: "TODO"

# GitHub remotes for push targets (added v4.1 — Pat retro)
repo_remote: "TODO"                # e.g. "your-org/client-website" — main site repo
parent_docs_remote: "TODO"          # e.g. "your-org/client-pipeline-docs" — audit log repo (private). Auto-create on first cycle if missing.

# H1 verbatim format for Step 5.5 verifier (added v4.1 — Pat retro)
# Tokens: [City], [ST], [Service], [Brand], [Year]
h1_format:
  default: "TODO"                   # e.g. "[Service] in [City], [ST] | [Brand]"
  per_service: {{}}                  # e.g. {{ commercial-painting: "#1 Commercial Painting Contractor in [City], FL - Trusted Since 1947" }}

# Slug convention (added v4.2 — Casey retro)
# Lock once at onboarding. Worker reads + applies, never asks Alex mid-cycle.
slug_convention: "TODO"             # one of: city-state | city-township-state | service-only | city-service-state

# Redirects source (added v4.2 — Casey retro)
# Explicit path to the canonical redirect-generation mechanism.
# Worker should NEVER have to investigate "where do redirects live in this repo."
redirects_source: "TODO"            # e.g. "public/_redirects" | "wrangler.toml [redirects]" | "next.config.mjs redirects()" | "scripts/build-redirects.js"

# Pipeline auto-decisions per client (added v4.1 — Dana + Pat retros)
auto_decisions:
  bucket_a_word_ratio_min: 0.70     # Step 1.5 gate. Below = Bucket B.
  bucket_a_faq_count_must_match: true
  noindex_under_words: 500          # Step 0.8 thin-page auto-noindex threshold.
  option_full_threshold_pages: 10   # Architectural escalation threshold.
  cloudflare_double_push: true      # Empty commit trigger; set false for non-CF.
  poll_live_max_minutes: 5
  image_budget_mb: 3

form_endpoint: "TODO"
"""
    # A config generator that emits unloadable YAML must refuse, not write: every
    # gate downstream calls load_config, so the failure surfaces five commands later
    # as "missing field" instead of here as "this file is broken" (B-002).
    try:
        yaml.safe_load(config)
    except yaml.YAMLError as e:
        print(f"[STOP] generated config is not valid YAML — refusing to write:\n{e}", file=sys.stderr)
        sys.exit(3)

    target.write_text(config)
    hints_summary = f"{len(docs_intel['forbidden_rules'])} rule hints, {len(docs_intel['services_hints'])} service hints, {len(docs_intel['keyword_hints'])} keyword hints"
    print(f"[DOCS] Parsed client docs/memory — {hints_summary}")
    print(f"[OK] Wrote {target} (tier: {tier})")
    warn_unresolved_registry(project_dir, registry)
    print("[NEXT] Agent must interview Alex to resolve every TODO before pipeline proceeds.")


if __name__ == "__main__":
    main()
