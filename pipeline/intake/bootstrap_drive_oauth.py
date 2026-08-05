#!/usr/bin/env python3
"""
Bootstrap Google Drive OAuth token for Meridian SEO Ops.

First run: opens browser → user signs in as the Meridian clients Google account →
grants Drive scope → token cached for future use by drive-intake.py + reorg script.

Reuses the same OAuth client as setup-gtm-foundation.py (Google Cloud project:
claude-code-mcp-seo-cmd-center) — no new Google Cloud setup required.

Usage:
  # Full Drive scope — for one-time reorg script
  python3 bootstrap-drive-oauth.py --scope full

  # Read-only scope — for ongoing drive-intake.py automation
  python3 bootstrap-drive-oauth.py --scope readonly

Token files (cached separately so daily automation runs with least-privilege):
  ~/.claude/scripts/seo-pipeline/.drive-token-full.json     (full read+write+delete)
  ~/.claude/scripts/seo-pipeline/.drive-token-readonly.json (read-only)

Verify after bootstrap:
  python3 bootstrap-drive-oauth.py --scope readonly --verify
  Prints the authenticated user's email + lists files in the SEO - Clients parent folder.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# OAuth client secrets location is operator-local and NEVER hardcoded here
# (repo rule #2). Set $GTM_OAUTH_CLIENT_SECRETS_FILE, or drop the file at the
# gitignored default below.
DEFAULT_CLIENT_SECRETS = SCRIPT_DIR / "secrets" / "client_secrets.json"
CLIENT_SECRETS_FILE = Path(
    os.environ.get("GTM_OAUTH_CLIENT_SECRETS_FILE", str(DEFAULT_CLIENT_SECRETS))
).expanduser()

# SEO - Clients parent folder ID (from clients.yml drive.parent_folder_id)
from pipeline.intake.roster import parent_folder_id

PARENT_FOLDER_ID = parent_folder_id()

SCOPES = {
    "full": ["https://www.googleapis.com/auth/drive"],
    "readonly": ["https://www.googleapis.com/auth/drive.readonly"],
}

TOKEN_FILES = {
    "full": SCRIPT_DIR / ".drive-token-full.json",
    "readonly": SCRIPT_DIR / ".drive-token-readonly.json",
}


def get_credentials(scope_name: str):
    """OAuth Desktop flow. Opens browser on first run, caches token after."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        sys.exit(
            "Missing deps. Install them, or activate a venv that already has the\n"
            "Google API client (path is operator-local), then run:\n"
            "  python3 bootstrap-drive-oauth.py --scope " + scope_name
        )

    scopes = SCOPES[scope_name]
    token_file = TOKEN_FILES[scope_name]

    creds = None
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), scopes)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print(f"→ Refreshing existing {scope_name} token...")
            creds.refresh(Request())
        else:
            if not CLIENT_SECRETS_FILE.exists():
                sys.exit(
                    f"✗ OAuth client secrets file not found at {CLIENT_SECRETS_FILE}.\n"
                    "Override path with: export GTM_OAUTH_CLIENT_SECRETS_FILE=/path/to/client_secrets.json"
                )
            print(f"→ Browser will open. Sign in as the Meridian clients Google account")
            print(f"→ Grant scope: {scopes[0]}")
            print()
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), scopes)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json())
        os.chmod(token_file, 0o600)
        print(f"✓ Token cached at {token_file}")

    return creds


def verify(creds, scope_name: str):
    """Verify the token works — print user email + list parent folder children."""
    from googleapiclient.discovery import build

    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    # Whoami
    about = drive.about().get(fields="user(emailAddress,displayName)").execute()
    user = about.get("user", {})
    print(f"  Authenticated as: {user.get('emailAddress')} ({user.get('displayName')})")

    # List children of the SEO - Clients parent folder
    print(f"  Listing children of SEO - Clients (parent_id {PARENT_FOLDER_ID})...")
    results = (
        drive.files()
        .list(
            q=f"'{PARENT_FOLDER_ID}' in parents and trashed = false",
            fields="files(id, name, mimeType, modifiedTime)",
            pageSize=50,
        )
        .execute()
    )
    files = results.get("files", [])
    if not files:
        print("  ⚠ Parent folder is empty or not accessible — check sharing.")
        return False
    print(f"  ✓ Found {len(files)} items in parent folder:")
    for f in files[:10]:
        kind = "📁" if f["mimeType"] == "application/vnd.google-apps.folder" else "📄"
        print(f"    {kind} {f['name']}")
    if len(files) > 10:
        print(f"    ... and {len(files) - 10} more")
    return True


def main():
    if not PARENT_FOLDER_ID:
        raise SystemExit("[ERROR] PIPELINE_DRIVE_PARENT_FOLDER_ID is not set. "
                         "Export the Drive parent folder id before running this tool.")
    parser = argparse.ArgumentParser(description="Bootstrap Drive OAuth for Meridian SEO Ops.")
    parser.add_argument("--scope", choices=["full", "readonly"], required=True)
    parser.add_argument("--verify", action="store_true", help="After bootstrap, list parent folder contents")
    args = parser.parse_args()

    print(f"━━━ Drive OAuth Bootstrap — {args.scope} scope ━━━")
    creds = get_credentials(args.scope)

    if args.verify:
        print()
        print("→ Verifying token...")
        ok = verify(creds, args.scope)
        if not ok:
            sys.exit(1)
        print()
        print("✓ Done.")


if __name__ == "__main__":
    main()
