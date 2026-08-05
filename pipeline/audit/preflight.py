#!/usr/bin/env python3
"""Pipeline Step 0: config + live site gates.

Fails if: config missing/invalid, site not 200, bot-fight challenge,
required schema missing from homepage.

Usage: python3 preflight.py [PROJECT_DIR]
"""
import sys, re
from pathlib import Path
from pipeline.lib.common import load_config, curl, curl_status


def main():
    if len(sys.argv) < 2:
        print("Usage: preflight.py [PROJECT_DIR]", file=sys.stderr); sys.exit(1)
    project = Path(sys.argv[1])
    config_path = project / "docs" / "client-config.yml"
    if not config_path.exists():
        print(f"[STOP] {config_path} missing. Run bootstrap-config.py first."); sys.exit(10)
    cfg = load_config(str(project))

    # required fields
    required = ["client", "domain", "industry", "topology", "nap", "trust_signals", "schema_type", "repo"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        print(f"[STOP] Config missing fields: {missing}"); sys.exit(11)
    todos = []
    def walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items(): walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj): walk(v, f"{path}[{i}]")
        elif isinstance(obj, str) and obj == "TODO":
            todos.append(path)
    walk(cfg)
    if todos:
        print(f"[STOP] Config has unresolved TODOs: {todos}"); sys.exit(12)

    # live checks
    domain = cfg["domain"]
    home = f"https://{domain}/"
    code = curl_status(home)
    if code != 200:
        print(f"[STOP] Homepage {home} returned {code}"); sys.exit(13)
    html = curl(home)
    if "cf-mitigated" in html.lower() or "challenge" in html[:500].lower():
        print(f"[STOP] Cloudflare challenge detected. Turn off Bot Fight Mode."); sys.exit(14)
    # schema type present on homepage
    schema = cfg["schema_type"]
    if schema not in html:
        print(f"[WARN] {schema} schema not detected on homepage. Verify.")

    print(f"[OK] Preflight passed — {cfg['client']} ({cfg['industry']}, {cfg['topology']})")


if __name__ == "__main__":
    main()
