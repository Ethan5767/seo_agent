#!/usr/bin/env python3
"""
Install the Meridian conversion-tracking foundation tag into a client's GTM container.

Foundation = 1 trigger + 1 GA4 Event tag + v1 publish.
Reference spec: ~/.claude/references/conversion-tracking-foundation.md

Trigger:   "Lead — Thank You Page View"  | Page URL contains /thank-you
Tag:       "GA4 — Generate Lead"          | GA4 Event "generate_lead" → client's GA4 property

Idempotent. Safe to re-run — skips existing trigger/tag/version where match found.

Usage:
  python3 setup-gtm-foundation.py --gtm GTM-XXXXXXXX --ga4 G-XXXXXXXXXX --client "Client Name"
  python3 setup-gtm-foundation.py --client-config clients/northstar-landscaping.yaml
  python3 setup-gtm-foundation.py --gtm GTM-XXXXXXXX --ga4 G-XXXXXXXXXX --dry-run

First run will pop a browser window for OAuth consent. Subsequent runs use cached token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# ─── Auth setup ────────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/tagmanager.edit.containers",
    "https://www.googleapis.com/auth/tagmanager.publish",
    "https://www.googleapis.com/auth/tagmanager.readonly",
]

SCRIPT_DIR = Path(__file__).resolve().parent
TOKEN_FILE = SCRIPT_DIR / ".gtm-token.json"

# OAuth client secrets location is operator-local and NEVER hardcoded here
# (repo rule #2). Set $GTM_OAUTH_CLIENT_SECRETS_FILE, or drop the file at the
# gitignored default below. You can reuse the gsc-mcp OAuth client if you have one.
DEFAULT_CLIENT_SECRETS = SCRIPT_DIR / "secrets" / "client_secrets.json"
CLIENT_SECRETS_FILE = Path(
    os.environ.get("GTM_OAUTH_CLIENT_SECRETS_FILE", str(DEFAULT_CLIENT_SECRETS))
).expanduser()


def get_credentials():
    """OAuth Desktop flow — same pattern as gsc-mcp. First run opens browser."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        sys.exit(
            "Missing deps. Install with:\n"
            "  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 pyyaml\n"
            "Or activate an existing venv that already has the Google API client\n"
            "(e.g. the gsc-mcp venv, path is operator-local)."
        )

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRETS_FILE.exists():
                sys.exit(
                    f"OAuth client secrets file not found at {CLIENT_SECRETS_FILE}.\n"
                    "Override path with: export GTM_OAUTH_CLIENT_SECRETS_FILE=/path/to/client_secrets.json\n"
                    "Or create one in Google Cloud Console → Credentials → OAuth Client (Desktop)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
        os.chmod(TOKEN_FILE, 0o600)
    return creds


def get_service(creds):
    from googleapiclient.discovery import build
    return build("tagmanager", "v2", credentials=creds, cache_discovery=False)


# ─── GTM API helpers ───────────────────────────────────────────────────────────


def find_container(tagmanager, gtm_public_id: str) -> dict[str, Any]:
    """Find the container by its public GTM-XXXXXXXX id across all accounts user has access to."""
    accounts = tagmanager.accounts().list().execute().get("account", [])
    for account in accounts:
        containers = tagmanager.accounts().containers().list(parent=account["path"]).execute().get("container", [])
        for c in containers:
            if c.get("publicId") == gtm_public_id:
                return {"account": account, "container": c}
    sys.exit(f"✗ Container {gtm_public_id} not found in any GTM account on this Google identity.")


def get_default_workspace(tagmanager, container_path: str) -> dict[str, Any]:
    workspaces = tagmanager.accounts().containers().workspaces().list(parent=container_path).execute().get("workspace", [])
    for w in workspaces:
        if w.get("name") == "Default Workspace":
            return w
    if workspaces:
        return workspaces[0]
    sys.exit("✗ No workspace found in container.")


def find_existing(items: list[dict], name: str) -> dict | None:
    for item in items:
        if item.get("name") == name:
            return item
    return None


# ─── Foundation install ────────────────────────────────────────────────────────


TRIGGER_NAME = "Lead — Thank You Page View"
TAG_NAME = "GA4 — Generate Lead"
EVENT_NAME = "generate_lead"


def build_trigger_body(thank_you_path: str = "/thank-you") -> dict:
    return {
        "name": TRIGGER_NAME,
        "type": "pageview",
        "filter": [
            {
                "type": "contains",
                "parameter": [
                    {"type": "template", "key": "arg0", "value": "{{Page URL}}"},
                    {"type": "template", "key": "arg1", "value": thank_you_path},
                ],
            }
        ],
    }


def build_tag_body(trigger_id: str, ga4_measurement_id: str) -> dict:
    return {
        "name": TAG_NAME,
        "type": "gaawe",
        "parameter": [
            {"type": "boolean", "key": "sendEcommerceData", "value": "false"},
            {"type": "template", "key": "eventName", "value": EVENT_NAME},
            {"type": "template", "key": "measurementIdOverride", "value": ga4_measurement_id},
        ],
        "firingTriggerId": [trigger_id],
    }


def install_foundation(
    tagmanager,
    gtm_public_id: str,
    ga4_measurement_id: str,
    thank_you_path: str = "/thank-you",
    dry_run: bool = False,
) -> dict:
    """Idempotent install. Returns summary dict."""
    summary: dict[str, Any] = {"gtm": gtm_public_id, "ga4": ga4_measurement_id, "actions": []}

    print(f"→ Locating container {gtm_public_id}...")
    found = find_container(tagmanager, gtm_public_id)
    account, container = found["account"], found["container"]
    print(f"  ✓ Account: {account['name']} | Container: {container['name']}")
    summary["account_name"] = account["name"]
    summary["container_name"] = container["name"]

    workspace = get_default_workspace(tagmanager, container["path"])
    print(f"  ✓ Workspace: {workspace['name']}")
    summary["workspace_name"] = workspace["name"]

    # Triggers
    print(f"→ Checking for trigger '{TRIGGER_NAME}'...")
    existing_triggers = tagmanager.accounts().containers().workspaces().triggers().list(
        parent=workspace["path"]
    ).execute().get("trigger", [])
    trigger = find_existing(existing_triggers, TRIGGER_NAME)

    if trigger:
        print(f"  ⊙ Trigger exists (id: {trigger['triggerId']}) — skipping create")
        summary["actions"].append(f"trigger.skip:{trigger['triggerId']}")
    else:
        if dry_run:
            print(f"  + DRY-RUN: would create trigger '{TRIGGER_NAME}'")
            summary["actions"].append("trigger.dry-create")
            return summary
        trigger = tagmanager.accounts().containers().workspaces().triggers().create(
            parent=workspace["path"], body=build_trigger_body(thank_you_path)
        ).execute()
        print(f"  ✓ Trigger created (id: {trigger['triggerId']})")
        summary["actions"].append(f"trigger.create:{trigger['triggerId']}")

    # Tags
    print(f"→ Checking for tag '{TAG_NAME}'...")
    existing_tags = tagmanager.accounts().containers().workspaces().tags().list(
        parent=workspace["path"]
    ).execute().get("tag", [])
    tag = find_existing(existing_tags, TAG_NAME)

    if tag:
        print(f"  ⊙ Tag exists (id: {tag['tagId']}) — skipping create")
        summary["actions"].append(f"tag.skip:{tag['tagId']}")
    else:
        if dry_run:
            print(f"  + DRY-RUN: would create tag '{TAG_NAME}'")
            summary["actions"].append("tag.dry-create")
            return summary
        tag = tagmanager.accounts().containers().workspaces().tags().create(
            parent=workspace["path"],
            body=build_tag_body(trigger["triggerId"], ga4_measurement_id),
        ).execute()
        print(f"  ✓ Tag created (id: {tag['tagId']})")
        summary["actions"].append(f"tag.create:{tag['tagId']}")

    # Version + publish (only if we changed something this run)
    has_new = any(a.startswith(("trigger.create", "tag.create")) for a in summary["actions"])
    if not has_new:
        print("→ No workspace changes this run — skipping version create + publish")
        summary["actions"].append("publish.skip")
        return summary

    if dry_run:
        print("  + DRY-RUN: would create + publish version")
        summary["actions"].append("publish.dry-run")
        return summary

    print("→ Creating version + publishing...")
    version_result = tagmanager.accounts().containers().workspaces().create_version(
        path=workspace["path"],
        body={
            "name": "Foundation v1 — Lead conversion tracking on /thank-you",
            "notes": (
                "Auto-installed by setup-gtm-foundation.py.\n"
                f"Tag: {TAG_NAME} (event: {EVENT_NAME}, GA4: {ga4_measurement_id})\n"
                f"Trigger: {TRIGGER_NAME} (Page URL contains {thank_you_path})"
            ),
        },
    ).execute()
    version = version_result.get("containerVersion")
    if not version:
        print("  ⚠ Version creation returned no containerVersion (likely empty workspace). Output:")
        print(json.dumps(version_result, indent=2))
        summary["actions"].append("version.empty")
        return summary

    tagmanager.accounts().containers().versions().publish(path=version["path"]).execute()
    print(f"  ✓ Version {version['containerVersionId']} published live")
    summary["version_id"] = version["containerVersionId"]
    summary["actions"].append(f"publish:{version['containerVersionId']}")
    return summary


# ─── CLI ───────────────────────────────────────────────────────────────────────


def load_from_yaml(path: Path) -> tuple[str, str, str]:
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML required for --client-config. pip install pyyaml")
    data = yaml.safe_load(path.read_text())
    tracking = data.get("tracking", {})
    gtm = tracking.get("gtm_id") or data.get("gtm_id")
    ga4 = tracking.get("ga4_id") or data.get("ga4_id")
    thank_you = tracking.get("thank_you_path", "/thank-you")
    if not gtm or not ga4:
        sys.exit(f"✗ {path} missing tracking.gtm_id or tracking.ga4_id")
    return gtm, ga4, thank_you


def main():
    parser = argparse.ArgumentParser(description="Install GTM conversion tracking foundation tag.")
    parser.add_argument("--gtm", help="GTM container public ID (GTM-XXXXXXXX)")
    parser.add_argument("--ga4", help="GA4 Measurement ID (G-XXXXXXXXXX)")
    parser.add_argument("--client", help="Display name (for logs only)")
    parser.add_argument("--thank-you-path", default="/thank-you", help="Path to match (default: /thank-you)")
    parser.add_argument("--client-config", type=Path, help="Read GTM + GA4 IDs from a YAML file")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without writing")
    args = parser.parse_args()

    if args.client_config:
        gtm, ga4, thank_you = load_from_yaml(args.client_config)
        client_label = args.client or args.client_config.stem
    else:
        if not args.gtm or not args.ga4:
            parser.error("Need either --client-config OR both --gtm and --ga4")
        gtm, ga4, thank_you = args.gtm, args.ga4, args.thank_you_path
        client_label = args.client or gtm

    print(f"\n━━━ GTM Foundation Install — {client_label} ━━━")
    print(f"  GTM:        {gtm}")
    print(f"  GA4:        {ga4}")
    print(f"  Thank-you:  {thank_you}")
    print(f"  Mode:       {'DRY-RUN' if args.dry_run else 'LIVE'}\n")

    creds = get_credentials()
    tagmanager = get_service(creds)
    summary = install_foundation(tagmanager, gtm, ga4, thank_you, args.dry_run)

    print(f"\n━━━ Summary ━━━")
    print(json.dumps(summary, indent=2))
    print(f"\n✓ Done — open https://tagmanager.google.com/ to verify")


if __name__ == "__main__":
    main()
