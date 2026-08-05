#!/usr/bin/env python3
"""
validate_multistate_config.py — gate before any pipeline run on a multi-state SEO client.

Enforces the rules in:
  ~/.claude/references/multi-state-client-addendum.md
  ~/.claude/references/seo-pipeline-disciplines.md (Rule 16)
  ~/.claude/references/seo-client-config-schema.yml

Usage:
  python3 validate_multistate_config.py /path/to/client/docs/client-config.yml

Exit codes:
  0 = config is valid (or single-state, addendum doesn't apply)
  1 = HARD failure — pipeline must stop
  2 = WARN — pipeline can proceed but Alex should review

Designed to fail loud. Every check shows mechanical proof in stdout (Disciplines Rule 13).
"""
import sys
import re
from pathlib import Path

# Optional PyYAML — falls back to regex parsing if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def load_config(path):
    text = Path(path).read_text()
    if HAS_YAML:
        # Strip comments that confuse PyYAML in YAML 1.1 mode (we want the data, not the comments)
        return yaml.safe_load(text), text
    return None, text


def find_states_blocks(raw_text):
    """Crude state-block extraction when PyYAML isn't installed."""
    blocks = {}
    pattern = re.compile(
        r'^  - abbrev:\s*(\w+)\s*\n(.*?)(?=^  - abbrev:|^# ──+|\Z)',
        re.MULTILINE | re.DOTALL
    )
    for m in pattern.finditer(raw_text):
        blocks[m.group(1)] = m.group(2)
    return blocks


def parse_yaml_list(text_block, key):
    """Extract list items from a YAML key, handling both inline `key: [a, b]` and block `key:\n  - a\n  - b` forms."""
    # Try inline form first: `key: [a, b, c]`
    inline = re.search(rf'{re.escape(key)}:\s*\[([^\]]*)\]', text_block)
    if inline:
        items = [s.strip().strip('"\'') for s in inline.group(1).split(',') if s.strip()]
        return items
    # Block form: `key:\n  - a\n  - b`
    block = re.search(rf'{re.escape(key)}:\s*\n((?:[ \t]+-[^\n]*\n)*)', text_block)
    if block:
        items = []
        for line in block.group(1).splitlines():
            m = re.match(r'\s*-\s*(.+?)\s*$', line)
            if m:
                # strip inline comments and quotes
                val = re.sub(r'\s+#.*$', '', m.group(1)).strip().strip('"\'')
                if val:
                    items.append(val)
        return items
    return []


def check(name, passed, detail=""):
    icon = "✓" if passed else "✗"
    print(f"  {icon} {name}{':  ' + detail if detail else ''}")
    return passed


def main(config_path):
    print(f"\n=== MULTI-STATE CONFIG VALIDATOR ===")
    print(f"Config: {config_path}\n")

    config, raw = load_config(config_path)
    if config is None:
        print("⚠️  PyYAML not installed — running in regex-only mode (some checks limited)")
        print("    Install with: pip3 install pyyaml\n")

    failures = []
    warnings = []

    # ─── PHASE 1: Top-level structure ────────────────────────────────────
    print("PHASE 1 — Top-level fields\n")

    topology_match = re.search(r'^topology:\s*(\S+)', raw, re.MULTILINE)
    topology = topology_match.group(1) if topology_match else None

    states_count = len(re.findall(r'^  - abbrev:\s*\w+', raw, re.MULTILINE))

    if not check("topology field present", topology is not None, f"value: {topology}"):
        failures.append("Missing top-level `topology` field")

    # If single-state, exit early
    if topology != "multi-state-chain" and states_count < 2:
        print(f"\n  Single-state client (topology={topology}, states[]={states_count}). Multi-state addendum does NOT apply. ✓")
        print("\n=== RESULT: PASS (single-state, addendum bypassed) ===\n")
        return 0

    # Multi-state from here on
    if topology != "multi-state-chain":
        failures.append(f"topology must be 'multi-state-chain' when states[] has 2+ entries (got: {topology})")

    url_topology_match = re.search(r'^url_topology:\s*(\S+)', raw, re.MULTILINE)
    url_topology = url_topology_match.group(1) if url_topology_match else None

    primary_state_match = re.search(r'^primary_state:\s*(\S+)', raw, re.MULTILINE)
    primary_state = primary_state_match.group(1) if primary_state_match else None

    check("url_topology field present (required for multi-state)", url_topology is not None,
          f"value: {url_topology}")
    if url_topology is None:
        failures.append("Multi-state client missing required `url_topology` field")
    elif url_topology not in ("city-state-direct", "locations-state-city", "single-state"):
        failures.append(f"url_topology must be one of: city-state-direct, locations-state-city, single-state (got: {url_topology})")

    check("primary_state field present", primary_state is not None, f"value: {primary_state}")
    if primary_state is None:
        failures.append("Multi-state client missing required `primary_state` field")

    check(f"states[] has 2+ entries", states_count >= 2, f"count: {states_count}")

    # ─── PHASE 2: Per-state structure ────────────────────────────────────
    print("\nPHASE 2 — Per-state structure\n")
    state_blocks = find_states_blocks(raw)
    state_abbrevs = list(state_blocks.keys())
    print(f"  States found: {', '.join(state_abbrevs)}\n")

    # Exactly one is_primary: true
    primary_count = sum(1 for b in state_blocks.values()
                        if re.search(r'is_primary:\s*true', b))
    check("exactly 1 state has is_primary: true", primary_count == 1, f"count: {primary_count}")
    if primary_count != 1:
        failures.append(f"Must have exactly 1 state with is_primary: true (got: {primary_count})")

    # primary_state value must match a states[].abbrev with is_primary: true
    if primary_state and primary_state in state_blocks:
        block = state_blocks[primary_state]
        block_is_primary = bool(re.search(r'is_primary:\s*true', block))
        check(f"primary_state '{primary_state}' matches states[] entry with is_primary: true",
              block_is_primary)
        if not block_is_primary:
            failures.append(f"primary_state='{primary_state}' does not have is_primary: true in states[]")
    elif primary_state:
        failures.append(f"primary_state='{primary_state}' not found in states[]")

    # ─── PHASE 3: Active state license blockers ──────────────────────────
    print("\nPHASE 3 — License hard blockers (active states only)\n")
    for abbrev, block in state_blocks.items():
        seo_round_match = re.search(r'seo_round_1:\s*(true|false)', block)
        is_active = seo_round_match and seo_round_match.group(1) == "true"
        license_match = re.search(r'license:\s*\n\s*number:\s*["\']([^"\']*)["\']', block)
        license_num = license_match.group(1).strip() if license_match else ""

        if is_active:
            if license_num:
                check(f"{abbrev} (active): license number present", True, f"# {license_num}")
            else:
                check(f"{abbrev} (active): license number present", False, "MISSING — HARD BLOCKER")
                failures.append(f"State {abbrev} is active (seo_round_1=true) but has no license number — Fla. Stat. § 489.119 / MHIC / DPOR violation if pages publish")
        else:
            print(f"  ⊘ {abbrev} (deferred): license check skipped")

    # ─── PHASE 4: Trade association cross-claim check ────────────────────
    print("\nPHASE 4 — Trade association cross-claim (Addendum Hard Rule 6)\n")
    state_trade_assocs = {}
    for abbrev, block in state_blocks.items():
        # Use shared parser that handles BOTH inline `[A, B]` and block forms
        associations = parse_yaml_list(block, "trade_associations")
        state_trade_assocs[abbrev] = set(associations)

    all_associations = {}
    for abbrev, assocs in state_trade_assocs.items():
        for assoc in assocs:
            if assoc in all_associations:
                # Cross-claimed!
                other = all_associations[assoc]
                check(f"trade association '{assoc}' not cross-claimed", False,
                      f"appears in BOTH {other} and {abbrev}")
                failures.append(f"Trade association '{assoc}' cross-claimed between {other} and {abbrev} (Addendum Hard Rule 6 violation)")
            else:
                all_associations[assoc] = abbrev

    if not failures or all(("cross-claim" not in f) for f in failures):
        check("no trade association cross-claims", True,
              f"checked {len(all_associations)} unique associations across {len(state_blocks)} states")

    # ─── PHASE 5: URL topology decision tree ─────────────────────────────
    print("\nPHASE 5 — URL topology decision tree\n")
    total_cities = 0
    for abbrev, block in state_blocks.items():
        cities = parse_yaml_list(block, "target_cities")
        total_cities += len(cities)

    active_state_count = sum(1 for b in state_blocks.values()
                             if re.search(r'seo_round_1:\s*true', b))

    print(f"  Active states: {active_state_count}")
    print(f"  Total target_cities across active states: {total_cities}")
    print(f"  Configured url_topology: {url_topology}")

    if active_state_count <= 2 and total_cities <= 30:
        recommended = "city-state-direct"
    elif active_state_count <= 5 and total_cities <= 50:
        recommended = "city-state-direct OR locations-state-city (judgment call)"
    elif active_state_count <= 5:
        recommended = "locations-state-city"
    else:
        recommended = "ESCALATE — 6+ active states triggers programmatic-seo skill"

    print(f"  Decision Tree recommendation: {recommended}")
    # Guard against None (when url_topology is missing — already caught as a Phase 1 failure)
    if url_topology is None:
        check("url_topology matches Decision Tree", False, "skipped — url_topology not set (see Phase 1)")
    elif url_topology not in recommended and "OR" not in recommended:
        warnings.append(f"url_topology={url_topology} differs from Decision Tree recommendation ({recommended}) — verify intentional")
        check("url_topology matches Decision Tree", False, "see warning above")
    else:
        check("url_topology matches Decision Tree", True)

    if active_state_count > 5:
        failures.append(f"Active state count ({active_state_count}) exceeds addendum scale ceiling (5). Escalate to programmatic-seo skill.")

    # ─── PHASE 6: Forbidden phrases ledger present ───────────────────────
    print("\nPHASE 6 — Forbidden phrases ledger\n")
    fp_match = re.search(r'^forbidden_phrases:\s*\n((?:\s+- pattern: .*\n.*\n)*)', raw, re.MULTILINE)
    if fp_match and fp_match.group(1).strip():
        fp_count = len(re.findall(r'- pattern:', fp_match.group(1)))
        check("forbidden_phrases ledger populated", fp_count > 0, f"{fp_count} patterns")
    else:
        check("forbidden_phrases ledger populated", False, "empty or missing")
        warnings.append("forbidden_phrases ledger empty — every contractor client needs at least basic legal patterns")

    # ─── RESULT ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if failures:
        print(f"\n❌ FAIL — {len(failures)} hard failure(s):\n")
        for i, f in enumerate(failures, 1):
            print(f"  {i}. {f}")
        if warnings:
            print(f"\n⚠️  Plus {len(warnings)} warning(s):\n")
            for i, w in enumerate(warnings, 1):
                print(f"  {i}. {w}")
        print("\nPipeline MUST NOT proceed until failures are resolved.\n")
        return 1
    elif warnings:
        print(f"\n⚠️  WARN — config valid but {len(warnings)} warning(s):\n")
        for i, w in enumerate(warnings, 1):
            print(f"  {i}. {w}")
        print("\nPipeline can proceed — review warnings with Alex.\n")
        return 2
    else:
        print("\n✅ PASS — config is valid for multi-state pipeline execution\n")
        return 0


def cli() -> int:
    """Console-script wrapper — main() takes the config path as an argument."""
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: wf-validate-multistate-config /path/to/client-config.yml")
        return 0 if len(sys.argv) == 2 else 1
    cfg_path = Path(sys.argv[1])
    if not cfg_path.is_file():
        print(f"[ERROR] no such config file: {cfg_path}", file=sys.stderr)
        return 2
    return main(str(cfg_path))


if __name__ == "__main__":
    sys.exit(cli())
