"""Shared helpers for SEO pipeline v3 scripts."""
import sys, os, re, json, subprocess
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML required. Run: pip3 install pyyaml", file=sys.stderr)
    sys.exit(2)


def load_config(project_dir: str) -> dict:
    path = Path(project_dir) / "docs" / "client-config.yml"
    if not path.exists():
        print(f"[BLOCKER] {path} missing. Run bootstrap-config.py first.", file=sys.stderr)
        sys.exit(10)
    with open(path) as f:
        return yaml.safe_load(f)


def audit_log_dir(project_dir: str, date: str) -> Path:
    d = Path(project_dir) / "docs" / "audit-logs" / date
    d.mkdir(parents=True, exist_ok=True)
    return d


# Default curl UA gets blocked by Cloudflare WAF and returns challenge HTML.
# All pipeline fetches must use a real browser UA + Accept header to get past WAF.
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


# A host that hangs is UNREACHABLE, not a crash. subprocess.run raises
# TimeoutExpired, which every caller here would otherwise propagate as an
# uncaught traceback mid-run. Both helpers already have an established failure
# signal — "" for curl, 0 for curl_status — so a timeout returns that instead.
def curl(url: str, cache_bust: bool = True) -> str:
    u = url + (f"?cb={os.urandom(4).hex()}" if cache_bust else "")
    # -L follows redirects so sites with no-trailing-slash policy (BLH, etc.) still return real HTML
    try:
        r = subprocess.run(
            ["curl", "-sL", "-A", BROWSER_UA, "-H", f"Accept: {BROWSER_ACCEPT}", u],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return ""
    return r.stdout


def curl_status(url: str, follow: bool = True) -> int:
    args = ["curl", "-sI", "-A", BROWSER_UA, "-H", f"Accept: {BROWSER_ACCEPT}"]
    if follow:
        args = ["curl", "-sIL", "-A", BROWSER_UA, "-H", f"Accept: {BROWSER_ACCEPT}",
                "-o", "/dev/null", "-w", "%{http_code}"]
    try:
        r = subprocess.run(args + [url], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return 0
    if follow:
        try:
            return int(r.stdout.strip())
        except ValueError:
            return 0
    m = re.match(r"HTTP/[0-9.]+ (\d+)", r.stdout)
    return int(m.group(1)) if m else 0


TOPOLOGY_PATTERNS = {
    "single-location-single-city": {
        "hub": r"^/[a-z0-9-]+/$",
        "spoke": None,
    },
    "single-location-multi-metro": {
        "hub": r"^/[a-z0-9-]+/$",
        "spoke": r"^/[a-z0-9-]+/[a-z0-9-]+-[a-z]{2}/$",
    },
    "multi-state-chain": {
        "hub": r"^/[a-z]{2}/[a-z0-9-]+/$",
        "spoke": r"^/[a-z]{2}/[a-z0-9-]+/[a-z0-9-]+/$",
    },
    "franchise": {
        "hub": r"^/[a-z0-9-]+-[a-z]{2}/$",
        "spoke": r"^/[a-z0-9-]+-[a-z]{2}/[a-z0-9-]+/$",
        # /[metro]/[city]/[subservice]/ — Acme ships 36 of these; absent
        # from the table they threw 24 topology_gap warns per 2026-08 run and
        # classified only via repo precedent (right, but by luck not pattern).
        "subspoke": r"^/[a-z0-9-]+-[a-z]{2}/[a-z0-9-]+/[a-z0-9-]+/$",
    },
    "satellite-offices": {
        "hub": r"^/[a-z0-9-]+-[a-z]{2}/$",
        "spoke": r"^/[a-z0-9-]+-[a-z]{2}/[a-z0-9-]+/$",
    },
    # BLH-style: category hub (/commercial/, /residential/) → service hub
    # (/services/[service]/) → city × service spoke (/[city]/[service]/).
    # Hub matches both 1-segment categories AND 2-segment services/* paths.
    # Spoke is the [city]/[service] shape that Joy's DOCX produces.
    "hub-spoke": {
        "hub": r"^/(?:[a-z0-9-]+|services/[a-z0-9-]+)/$",
        "spoke": r"^/[a-z0-9-]+/[a-z0-9-]+/$",
    },
    # ── url_topology vocabulary (validate_multistate_config's terms) ──────────
    # The multistate gate has always demanded `url_topology:` with these values;
    # until 2026-08 nothing else read the key, so the URL-shape vocabulary and
    # this table never met (ENGINE-FIXES-2026-08 fix 3). city-state-direct is
    # Crestline's real shape: /baltimore-md/ hub, /baltimore-md/[service]/ spoke —
    # identical regexes to franchise/satellite-offices, which is the point:
    # business shape and URL shape are different facts.
    "city-state-direct": {
        "hub": r"^/[a-z0-9-]+-[a-z]{2}/$",
        "spoke": r"^/[a-z0-9-]+-[a-z]{2}/[a-z0-9-]+/$",
    },
    # /locations/md/baltimore/ hub → /locations/md/baltimore/[service]/ spoke.
    "locations-state-city": {
        "hub": r"^/locations/[a-z]{2}/[a-z0-9-]+/$",
        "spoke": r"^/locations/[a-z]{2}/[a-z0-9-]+/[a-z0-9-]+/$",
    },
}


# ── Build / framework sub-profile (Model A, 2026-07-19, T01) ───────────────────
# The fleet is heterogeneous: 4 Next.js static-export sites (build → out/) and 1
# Vite/react-ssg site (Northstar, build → dist/). The pipeline branches ONCE at the
# build step by framework_family; every gate downstream stays framework-blind and
# scans whatever `resolve_build_dir()` hands it. Framework strings in the configs
# are inconsistent free-text (nextjs-app-router / next.js-15-app-router /
# vite-react-ssg-custom), and build-dir lives under three different keys
# (build_output_dir / build_dir / none), so these helpers normalize both.

# Family default build output dir. Next static export → out/, Vite → dist/.
# wordpress is server-rendered with no static build dir (None → callers fall back
# to a scan of the project root or skip built-mode).
FRAMEWORK_FAMILY_DEFAULT_DIR = {
    "next": "out",
    "vite": "dist",
    "wordpress": None,
}


def framework_family(framework_raw: str):
    """Map a free-text framework string to a canonical family, or None if unknown.
    *next* → next · *vite* → vite · *wordpress*/*wp* → wordpress."""
    low = (framework_raw or "").lower()
    if "next" in low:
        return "next"
    if "vite" in low:
        return "vite"
    if "wordpress" in low or re.search(r"\bwp\b", low):
        return "wordpress"
    return None


def _default_ssr_model(family: str):
    return {
        "next": "static-export",
        "vite": "ssg-prerender",
        "wordpress": "server-rendered",
    }.get(family)


def _build_dir_stale(configured: str, root: Path) -> bool:
    """True when the configured build path has a LEADING (wrapper) segment that is
    absent on disk — the Northstar footgun where the config still carries the GitHub
    zip's `<repo>-main/` prefix that never existed in the checked-out repo."""
    if not configured:
        return False
    parts = Path(configured).parts
    if len(parts) <= 1:
        return False  # a single segment like "out"/"dist" is never wrapper-stale
    return not (root / parts[0]).exists()


def resolve_build_dir(profile: dict, project) -> str:
    """Resolve the on-disk build output dir for a client, tolerating a stale
    config path.

    Any leading segment of the configured `build_output_dir` that is ABSENT on
    disk (e.g. Northstar's stale `northstar-landscaping-site-main/` wrapper) is
    ignored; if no configured candidate exists on disk, fall back to the
    framework-family default (`out` for next, `dist` for vite). Returns a
    project-relative POSIX path prefixed with `./` — join with `project` for an
    absolute path. Never raises on a missing key (defaults gracefully)."""
    root = Path(project)
    family = profile.get("framework_family")
    default = FRAMEWORK_FAMILY_DEFAULT_DIR.get(family) or "out"
    configured = (profile.get("build_output_dir") or "").strip().rstrip("/")

    candidates = []
    if configured:
        parts = Path(configured).parts
        # full configured path first, then progressively drop leading segments so
        # a stale wrapper prefix falls away to the real relative dir.
        for i in range(len(parts)):
            candidates.append(Path(*parts[i:]).as_posix())
    candidates.append(default)

    seen, ordered = set(), []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)

    # first candidate that exists on disk wins (post-build reality)
    for c in ordered:
        if (root / c).is_dir():
            return "./" + c

    # pre-build / nothing on disk yet: prefer the configured path's own tail when
    # it already equals the family default, else the family default itself.
    if configured and Path(configured).name == default:
        return "./" + default
    return "./" + default


# ── Tiering (v3 §2) ───────────────────────────────────────────────────────────
# Tier is a path + operation allow-list declared per project, enforced by a gate on
# the PR diff (phase 4). The deny-list applies at EVERY tier, T3 included, and is
# unioned in here rather than read from the config alone: a client repo that forgets
# it still gets the floor, and the floor is what stops the agent editing the gates
# that judge it or raising its own tier.
DEFAULT_DENY = [
    ".github/**",             # the agent must never edit the gates that judge it
    "docs/client-config.yml", # must never raise its own tier
    "package*.json",          # no dependency changes
    "wrangler.toml",          # deploy config is the rollback path
    ".env*",
]

NEXT_CONFIG_NAMES = ("next.config.mjs", "next.config.js", "next.config.ts")


def detect_static_export(project, family, framework_raw: str = ""):
    """True / False / None (cannot tell) — does this repo build a full static HTML
    route tree?

    v3 §6: `orphan_check` and `parity_check` derive routes from
    `<build_dir>/index.html`. An SSR/ISR site produces no such tree, so both gates
    scan nothing and report green. That makes static export an ONBOARDING
    PRECONDITION, not a footnote — verify it before promising the full gate suite."""
    if family == "wordpress":
        return False
    if family == "vite":
        # A plain Vite SPA emits ONE index.html at the dist root; only the SSG
        # variant emits a route tree. Unknowable unless the framework string says so.
        return True if "ssg" in (framework_raw or "").lower() else None
    if family == "next":
        for name in NEXT_CONFIG_NAMES:
            p = Path(project) / name
            if p.is_file():
                try:
                    text = p.read_text()
                except OSError:
                    return None
                return bool(re.search(r"""output\s*:\s*['"]export['"]""", text))
    return None


def _as_str_list(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v.strip()]
    return []


def resolve_repo_path(configured, project):
    """Resolve a configured repo-relative path (file OR dir) on disk, tolerating
    the same stale wrapper-prefix class `_build_dir_stale` documents (Northstar's
    `<repo>-main/` zip prefix). Progressively drops leading segments; the first
    candidate that exists wins. Returns a project-relative POSIX string, or None
    when nothing configured resolves."""
    if not configured or not isinstance(configured, str):
        return None
    root = Path(project)
    parts = Path(configured.strip()).parts
    if not parts:
        return None
    for i in range(len(parts)):
        cand = Path(*parts[i:]).as_posix()
        if (root / cand).exists():
            return cand
    return None


def url_fits_topology(url: str, topology: str) -> tuple[bool, str]:
    """Returns (fits, kind) where kind is 'hub' | 'spoke' | 'invalid'."""
    patterns = TOPOLOGY_PATTERNS.get(topology)
    if not patterns:
        return False, "invalid"
    path = url if url.startswith("/") else "/" + url.split("/", 3)[-1]
    if not path.endswith("/"):
        path += "/"
    if re.match(patterns["hub"], path):
        return True, "hub"
    if patterns["spoke"] and re.match(patterns["spoke"], path):
        return True, "spoke"
    subspoke = patterns.get("subspoke")
    if subspoke and re.match(subspoke, path):
        return True, "subspoke"
    return False, "invalid"


# ── Self-describing client profile (Model A, 2026-07-15) ───────────────────────
# Every client-config.yml is now a single canonical file carrying a self-describing
# topology header. These helpers let the pipeline branch by CLIENT SHAPE instead of
# guessing, and answer the three onboarding questions on every run:
#   1. who is the client    -> profile["client_slug"] / ["client_name"]
#   2. how many SEO states  -> profile["state_count"] / ["states_served"]
#   3. where the AEO refs   -> profile["aeo_geo_path"] (repo) + proof_paths (~/.aeo-tracker/<slug>/)
#
# Client shapes handled:
#   single-site-single-state  (D) Casey / Northstar        1 repo, 1 state
#   single-site-multi-state   (B) Lee: MD+FL on 1 site · (C) Dana: NC/SC/VA/WV on 1 site
#   multi-site-division       (A) Pat: BLH-North + BLH-Florida = 2 repos, linked via sister_sites

VALID_TOPOLOGY_CLASSES = {
    "single-site-single-state",
    "single-site-multi-state",
    "multi-site-division",
}


def client_profile(cfg: dict, project_dir=None) -> dict:
    """Normalize a client-config.yml into a self-describing profile. Prefers the
    explicit header fields (topology_class, site_count, states_served,
    sister_sites, aeo_geo_dir) and DERIVES any a pre-migration config lacks, so it
    works on old and new configs alike (new keys are additive)."""
    slug = cfg.get("client_slug") or cfg.get("client") or "unknown-client"
    name = cfg.get("client_name") or cfg.get("business", {}).get("legal_name") or slug
    states = cfg.get("states_served") or []
    if isinstance(states, str):
        states = [s.strip() for s in re.split(r"[,\s]+", states) if s.strip()]
    sisters = cfg.get("sister_sites") or []
    site_count = cfg.get("site_count")

    tclass = cfg.get("topology_class")
    derived = tclass not in VALID_TOPOLOGY_CLASSES
    if derived:
        if sisters or (isinstance(site_count, int) and site_count > 1):
            tclass = "multi-site-division"
        elif len(states) > 1:
            tclass = "single-site-multi-state"
        else:
            tclass = "single-site-single-state"
    if not isinstance(site_count, int):
        site_count = (1 + len(sisters)) if sisters else 1

    aeo_dir = (cfg.get("aeo_geo_dir") or "aeo-geo/").rstrip("/")

    # ── build / framework sub-profile ──────────────────────────────────────────
    repo = cfg.get("repo") or {}
    fw_raw = repo.get("framework") or ""
    family = framework_family(fw_raw)
    build_output = repo.get("build_output_dir") or repo.get("build_dir") or ""
    if isinstance(build_output, str):
        build_output = build_output.strip().rstrip("/")
    else:
        build_output = ""
    build_cwd = repo.get("build_cwd")
    if isinstance(build_cwd, str):
        build_cwd = build_cwd.strip().rstrip("/") or None
    build_command = repo.get("build_command") or None
    ssr_model = repo.get("ssr_model") or _default_ssr_model(family)

    # ── tiering sub-profile (v3 §2) ────────────────────────────────────────────
    tier_raw = cfg.get("tier")
    tier = tier_raw if isinstance(tier_raw, int) and not isinstance(tier_raw, bool) else None
    content = cfg.get("content") if isinstance(cfg.get("content"), dict) else {}

    profile = {
        "client_slug": slug,
        "client_name": name,
        "owner_name": cfg.get("owner_name"),
        "domain": cfg.get("domain") or cfg.get("website"),
        "topology_class": tclass,
        "topology_class_derived": derived,          # True = config predates the header
        # URL shape. The dedicated `url_topology:` key wins when it names a
        # known pattern (city-state-direct etc. — the multistate gate's required
        # vocabulary, ignored here until 2026-08: this line read `topology`
        # unconditionally, so Crestline could satisfy the gate or classify, never
        # both). `topology:` stays the business-shape fallback; an unknown
        # url_topology value (e.g. the gate's 'single-state') also falls back.
        "url_topology": (
            cfg.get("url_topology")
            if cfg.get("url_topology") in TOPOLOGY_PATTERNS
            else cfg.get("topology")
        ),
        "url_topology_declared": cfg.get("url_topology"),   # raw, for validation
        "site_count": site_count,
        "states_served": states,
        "state_count": len(states),
        "is_multi_site": (tclass == "multi-site-division") or bool(sisters),
        "is_multi_state": len(states) > 1,
        "sister_sites": sisters,
        "aeo_geo_dir": aeo_dir,
        "seed_query_count": len(cfg.get("seed_queries") or []),
        "engines": cfg.get("engines") or [],
        # build / framework sub-profile
        "framework_raw": fw_raw or None,
        "framework_family": family,                 # next | vite | wordpress | None
        "build_output_dir": build_output or None,   # trailing-slash-stripped
        "build_command": build_command,
        "build_cwd": build_cwd,
        "ssr_model": ssr_model,
        # tiering: what the agent may touch in this repo. `tier` is None when the
        # declaration is missing OR not an int — `tier_declared` keeps the raw
        # value so validation can tell "absent" from "garbage".
        "tier": tier,
        "tier_declared": tier_raw,
        "text_paths": _as_str_list(cfg.get("text_paths")),
        "content_location": content.get("location"),
        "content_registry": _as_str_list(content.get("registry")),
        "content_format": content.get("format"),
        # deny is a UNION, never a replacement — see DEFAULT_DENY.
        "deny": DEFAULT_DENY + [d for d in _as_str_list(cfg.get("deny")) if d not in DEFAULT_DENY],
        "static_export": None,      # needs the repo on disk; filled in below
        # forbidden-phrase ledger sources (T02): the sweep unions both, so a repo
        # carrying BOTH is worth a WARN in case one is a stale duplicate.
        "has_inconfig_forbidden": bool(cfg.get("forbidden_phrases")),
        # repo layout declarations (raw, possibly wrapper-stale — resolve with
        # resolve_repo_path at point of use). The indexer and emitter read these
        # so a non-default layout (Vite, no src/, N-segment routes) is seen
        # instead of assumed away.
        "repo_paths": {
            k: repo[k] for k in
            ("route_file", "sitemap", "spoke_data_dir", "pages_dir", "service_pages_dir")
            if isinstance(repo.get(k), str) and repo[k].strip()
        },
    }
    if project_dir is not None:
        p = Path(project_dir)
        profile["aeo_geo_path"] = str(p / aeo_dir)
        profile["aeo_geo_exists"] = (p / aeo_dir).is_dir()
        profile["banned_phrases_file_exists"] = (p / "docs" / "banned-phrases.txt").is_file()
        # resolve the real build dir on disk, tolerating a stale config path
        resolved = resolve_build_dir(profile, p)
        profile["resolved_build_dir"] = resolved
        profile["build_dir_stale"] = _build_dir_stale(build_output, p)
        profile["build_dir_exists"] = (p / resolved).is_dir()
        profile["static_export"] = detect_static_export(p, family, fw_raw)
    return profile


def validate_profile(profile: dict) -> list:
    """Return [(level, message)] config-consistency findings. level = 'ERROR'
    (block the run) or 'WARN' (surface, don't block). Catches the shape mistakes
    that would silently mis-scope a client (e.g. multi-state site marked single)."""
    issues = []
    tclass = profile["topology_class"]
    n_states = profile["state_count"]
    sisters = profile["sister_sites"]

    if tclass == "single-site-single-state" and n_states > 1:
        issues.append(("ERROR", f"topology_class=single-site-single-state but states_served has {n_states}: {profile['states_served']}."))
    if tclass == "single-site-multi-state" and n_states < 2:
        issues.append(("WARN", f"topology_class=single-site-multi-state but only {n_states} state(s) listed."))
    if tclass == "multi-site-division" and not sisters:
        issues.append(("WARN", "topology_class=multi-site-division but sister_sites is empty — the other division site isn't linked."))
    if tclass != "multi-site-division" and sisters:
        issues.append(("WARN", f"sister_sites populated but topology_class={tclass} (expected multi-site-division)."))
    if profile["site_count"] < 1:
        issues.append(("ERROR", f"site_count={profile['site_count']} is invalid."))
    if n_states == 0:
        issues.append(("ERROR", "states_served is empty — cannot scope SEO."))
    if profile.get("aeo_geo_exists") is False:
        issues.append(("WARN", f"aeo_geo_dir '{profile['aeo_geo_dir']}' not found on disk — AEO refs may need seeding (expected for BLH pending clients)."))
    if profile["topology_class_derived"]:
        issues.append(("WARN", "topology_class was DERIVED (config predates the self-describing header) — add it explicitly."))

    # ── forbidden-phrase ledger sources (T02) ──────────────────────────────────
    # forbidden-sweep unions the in-config forbidden_phrases block with
    # docs/banned-phrases.txt. Both present is legal (every rule fires) but worth
    # surfacing so a stale duplicate ledger isn't mistaken for the live one.
    if profile.get("has_inconfig_forbidden") and profile.get("banned_phrases_file_exists"):
        issues.append(("WARN",
            "both docs/banned-phrases.txt and an in-config forbidden_phrases block exist — "
            "forbidden-sweep unions them (deduped by pattern); confirm both are current and "
            "one isn't a stale duplicate ledger."))

    # ── url topology vocabulary ────────────────────────────────────────────────
    declared = profile.get("url_topology_declared")
    if declared and declared != "single-state" and declared not in TOPOLOGY_PATTERNS:
        issues.append(("WARN",
            f"url_topology '{declared}' is not in TOPOLOGY_PATTERNS — falling back to "
            f"topology '{profile.get('url_topology')}' for URL-shape checks. Either the "
            "value is a typo or the pattern table needs the shape."))

    # ── build / framework consistency ──────────────────────────────────────────
    fw_raw = profile.get("framework_raw")
    family = profile.get("framework_family")
    if fw_raw and family is None:
        issues.append(("ERROR", f"framework '{fw_raw}' maps to no known family (expected next / vite / wordpress)."))
    elif not fw_raw:
        issues.append(("WARN", "repo.framework is unset — cannot branch the build step by framework_family."))
    if profile.get("build_dir_stale"):
        issues.append(("WARN",
            f"build path config is stale: '{profile.get('build_output_dir')}' has a leading segment "
            f"absent on disk; resolve_build_dir falls back to '{profile.get('resolved_build_dir')}'. "
            "Follow-up PR: fix the build_dir/build_output_dir key in docs/client-config.yml."))
    elif profile.get("build_dir_exists") is False and profile.get("resolved_build_dir"):
        issues.append(("WARN",
            f"resolved build dir '{profile.get('resolved_build_dir')}' is not present on disk — "
            f"expected only before a build; built-mode gates will scan nothing until "
            f"`{profile.get('build_command') or 'the build'}` has run."))

    # ── tiering + the static-export precondition (v3 §2, §6) ───────────────────
    # Missing tier is a WARN, not an ERROR: `wf-client-profile` exits 5 on ERROR and
    # runs inside build-site/action.yml for every client, so making the pre-phase-2
    # fleet's absent tier fatal would break five builds. Absent = no authority, which
    # is the safe default. An INCOHERENT tier is fatal — it claims authority it
    # cannot have.
    tier, declared_tier = profile.get("tier"), profile.get("tier_declared")
    if declared_tier is None:
        issues.append(("WARN",
            "no `tier:` declared — the agent has no authority over this repo. "
            "Add the block with `wf-bootstrap-config <dir> <domain> --add-tier`."))
    elif tier not in (1, 2, 3):
        issues.append(("ERROR", f"tier {declared_tier!r} is not 1, 2 or 3."))
    else:
        if not profile.get("text_paths"):
            issues.append(("ERROR",
                f"tier {tier} declared but text_paths is empty — the allow-list permits "
                "nothing, so every copy fix would be refused."))
        if tier >= 2 and not profile.get("content_location"):
            issues.append(("ERROR",
                "tier 2+ requires content.location — no declared content home means T2 is "
                "unavailable and the agent does structural SEO only (v3 §2)."))
        if tier >= 2 and not profile.get("content_registry"):
            issues.append(("WARN",
                "content.registry is empty — a new page wired into no nav or data file is an "
                "orphan, and orphan_check will refuse the PR."))
        static = profile.get("static_export")
        if static is False:
            issues.append(("WARN",
                f"NOT a static export (ssr_model={profile.get('ssr_model') or '?'}) — orphan_check "
                "and parity_check derive routes from <build_dir>/index.html, so on this repo they "
                "scan nothing and report GREEN. Onboarding precondition (v3 §6): verify the client "
                "statically exports before promising the full gate suite."))
        elif static is None and profile.get("framework_family"):
            issues.append(("WARN",
                "static export could not be confirmed from the repo (no `output: 'export'` in a "
                "next.config, or a Vite build that may be an SPA). Confirm by hand — an SSR site "
                "makes orphan_check and parity_check silently green (v3 §6)."))
    return issues
