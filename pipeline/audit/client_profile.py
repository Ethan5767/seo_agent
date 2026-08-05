#!/usr/bin/env python3
"""Resolve + validate a client's self-describing profile from docs/client-config.yml.

The pipeline's FRONT DOOR: every run starts here so the pipeline branches by client
SHAPE instead of guessing. Answers, from the config alone:
  1. who is the client      2. how many SEO states      3. where the AEO/GEO refs live

Client shapes:
  single-site-single-state  (D) Casey / Northstar        1 site, 1 state
  single-site-multi-state   (B) Lee MD+FL · (C) Dana NC/SC/VA/WV   1 site, N states
  multi-site-division       (A) Pat BLH-North + BLH-Florida         N sites, linked

Usage: client-profile.py PROJECT_DIR [--json]
Exit:  0 ok (warnings allowed) · 5 config ERROR (block the run)
"""
import sys, json, argparse
from pathlib import Path
from pipeline.lib.common import load_config, client_profile, validate_profile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    cfg = load_config(str(project))
    prof = client_profile(cfg, project)
    issues = validate_profile(prof)

    if args.json:
        print(json.dumps({"profile": prof, "issues": issues}, indent=2, default=str))
    else:
        print(f"── Client profile: {prof['client_slug']} " + "─" * 24)
        print(f"  1. Client       : {prof['client_name']}  (slug={prof['client_slug']}, owner={prof['owner_name']})")
        print(f"     Domain       : {prof['domain']}")
        print(f"  2. Shape        : {prof['topology_class']}   (url topology: {prof['url_topology']})")
        print(f"     Sites        : {prof['site_count']}    Sister sites: {prof['sister_sites'] or '—'}")
        print(f"     SEO states   : {prof['state_count']}  {prof['states_served']}")
        print(f"     flags        : multi_site={prof['is_multi_site']}  multi_state={prof['is_multi_state']}")
        print(f"  3. AEO/GEO refs : {prof.get('aeo_geo_path', prof['aeo_geo_dir'])}  (exists: {prof.get('aeo_geo_exists', '?')})")
        print(f"     engines      : {', '.join(prof['engines']) or '—'}   seed queries: {prof['seed_query_count']}")
        print(f"  4. Build        : {prof.get('framework_family') or '?'}   (framework: {prof.get('framework_raw') or '—'}, ssr: {prof.get('ssr_model') or '—'})")
        print(f"     build dir    : {prof.get('resolved_build_dir') or prof.get('build_output_dir') or '—'}   (configured: {prof.get('build_output_dir') or '—'}, exists: {prof.get('build_dir_exists', '?')})")
        print(f"     build cmd    : {prof.get('build_command') or '—'}    cwd: {prof.get('build_cwd') or '.'}")
        print()
        if not issues:
            print("  ✓ config consistent — no warnings.")
        for level, msg in issues:
            print(f"  [{level}] {msg}")

    if any(level == "ERROR" for level, _ in issues):
        sys.exit(5)


if __name__ == "__main__":
    main()
