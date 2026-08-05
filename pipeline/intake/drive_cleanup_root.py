#!/usr/bin/env python3
"""
Drive root cleanup: scan files floating at My Drive root, route them into
the right client folder using the locked convention.

Routing logic:
  1. Match filename against client aliases (domain, owner name, business name)
  2. If ambiguous AND the file is a Google Doc/Sheet, READ the first ~500 chars
     of body content + look for client signals
  3. Target paths:
       - GSC / performance reports → SEO - Clients / [Client] / From Team / Monthly Reports / [Month YYYY] / GSC Data /
       - Monthly content / Work File → SEO - Clients / [Client] / From Team / Client Work / [Month YYYY] /
       - Client Worksheets / intake → SEO - Clients / [Client] / Client Worksheet (or to Client Worksheet/ subfolder)
       - Meridian Materials (audits / proposals / brochures) → SEO - Clients / [Client] / Meridian Materials /
  4. Untitled docs / unroutable → flagged MANUAL, left in place

Default mode is DRY-RUN. Use --execute to actually move.

Usage:
  python3 drive-cleanup-root.py > /tmp/root-cleanup-plan.txt
  python3 drive-cleanup-root.py --execute
"""

from __future__ import annotations

import os
import argparse
import re
import sys
from pathlib import Path

from pipeline.intake.roster import load_clients, parent_folder_id

PARENT = parent_folder_id()  # Drive folder holding the client folders
TOKEN = Path.home() / ".claude/scripts/seo-pipeline/.drive-token-full.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

CLIENTS = load_clients()

GSC_DATE_PATTERN = re.compile(r"(\d{4})-(\d{2})-\d{2}")
MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]

GSC_REPORT_PATTERNS = re.compile(
    r"(performance[- ]on[- ]search|search[- ]performance|google[- ]search[- ]console|gsc[- ]data|last \d+ month|last \d+ days)",
    re.IGNORECASE,
)


def route_filename(name: str) -> str:
    nl = name.lower()
    for c in CLIENTS:
        for alias in c["aliases"]:
            if alias.lower() in nl:
                return c["slug"]
    return ""


def find_client_folder(drive, slug: str) -> dict | None:
    keyword = next((c["folder_name_contains"] for c in CLIENTS if c["slug"] == slug), None)
    if not keyword:
        return None
    r = drive.files().list(
        q=f"'{PARENT}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'",
        fields="files(id, name)", pageSize=50,
    ).execute()
    for f in r.get("files", []):
        if keyword in f["name"].lower():
            return f
    return None


def ensure_folder(drive, parent_id: str, name: str) -> str:
    name_esc = name.replace("'", "\\'")
    r = drive.files().list(
        q=f"'{parent_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder' and name = '{name_esc}'",
        fields="files(id, name)", pageSize=5,
    ).execute()
    items = r.get("files", [])
    if items:
        return items[0]["id"]
    new = drive.files().create(
        body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
        fields="id",
    ).execute()
    return new["id"]


def peek_doc_content(drive, file_id: str, mime: str) -> str:
    """Read first ~500 chars of a Google Doc or Sheet."""
    try:
        if mime == "application/vnd.google-apps.document":
            data = drive.files().export(fileId=file_id, mimeType="text/plain").execute()
            return data.decode("utf-8", errors="ignore")[:500] if isinstance(data, bytes) else str(data)[:500]
        elif mime == "application/vnd.google-apps.spreadsheet":
            data = drive.files().export(fileId=file_id, mimeType="text/csv").execute()
            return data.decode("utf-8", errors="ignore")[:500] if isinstance(data, bytes) else str(data)[:500]
    except Exception:
        return ""
    return ""


def classify_target(name: str, modified: str) -> tuple[str, str]:
    """Return (target_subpath_under_client, classification_label)."""
    n = name.lower()

    # GSC report — figure out year/month from filename, route to From Team/Monthly Reports/[Month YYYY]/GSC Data
    if GSC_REPORT_PATTERNS.search(n):
        date_match = GSC_DATE_PATTERN.search(name)
        if date_match:
            yr = date_match.group(1)
            mo = int(date_match.group(2))
            return (f"From Team/Monthly Reports/{MONTH_NAMES[mo - 1]} {yr}/GSC Data", "GSC")
        # Fallback to modifiedTime
        try:
            yr = modified[:4]
            mo = int(modified[5:7])
            return (f"From Team/Monthly Reports/{MONTH_NAMES[mo - 1]} {yr}/GSC Data", "GSC")
        except Exception:
            pass
        return ("From Team/Monthly Reports/GSC Data", "GSC")

    # Audit / Proposal / Brochure / PowerPoint — Meridian Materials
    if re.search(r"(\bproposal\b|\baudit\b|tri.?fold|trifold|brochure|\.pptx?$|\.key$)", name, re.IGNORECASE):
        return ("Meridian Materials", "PIPELINE_MATERIAL")

    # Client Worksheet
    if "worksheet" in n:
        return ("Client Worksheet", "WORKSHEET")

    # Business Context
    if "business context" in n:
        return ("Business Context", "BUSINESS_CONTEXT")

    # Default: Work File for current month (use modifiedTime)
    try:
        yr = modified[:4]
        mo = int(modified[5:7])
        return (f"From Team/Client Work/{MONTH_NAMES[mo - 1]} {yr}", "DEFAULT_CONTENT")
    except Exception:
        return ("", "MANUAL")


def main():
    if not PARENT:
        raise SystemExit("[ERROR] PIPELINE_DRIVE_PARENT_FOLDER_ID is not set. "
                         "Export the Drive parent folder id before running this tool.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    # List all items at My Drive root (parents = 'root')
    items = []
    page_token = None
    while True:
        r = drive.files().list(
            q="'root' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, owners(emailAddress), size)",
            pageSize=200,
            pageToken=page_token,
        ).execute()
        items.extend(r.get("files", []))
        page_token = r.get("nextPageToken")
        if not page_token:
            break

    print(f"# {'EXECUTE' if args.execute else 'DRY-RUN'}  — found {len(items)} items at My Drive root\n")

    # Plan routing
    plan_per_client: dict[str, list[tuple[dict, str, str]]] = {}
    manual: list[tuple[dict, str]] = []
    untitled: list[dict] = []
    folders_at_root: list[dict] = []

    for item in items:
        # Skip folders at root (they're not "floating files" — they're structural)
        if item["mimeType"] == "application/vnd.google-apps.folder":
            folders_at_root.append(item)
            continue
        name = item["name"]
        # Skip clearly-named "Untitled" stuff — flag as manual
        if name.lower().startswith("untitled") or name.strip() in ("", "the"):
            untitled.append(item)
            continue

        slug = route_filename(name)
        # For ambiguous filenames (Google Search Console | Last 28 Days vs Previous...),
        # peek content
        if not slug and "google search console" in name.lower():
            content = peek_doc_content(drive, item["id"], item["mimeType"])
            slug = route_filename(content)

        if not slug:
            manual.append((item, "no client signal in filename or content"))
            continue

        target_subpath, label = classify_target(name, item.get("modifiedTime", ""))
        if not target_subpath:
            manual.append((item, "couldn't classify target subfolder"))
            continue
        plan_per_client.setdefault(slug, []).append((item, target_subpath, label))

    # Print plan
    print("## Folders at root (UNTOUCHED):")
    for f in folders_at_root:
        print(f"  📁 {f['name']}")

    print("\n## Per-client move plan:")
    for slug, entries in plan_per_client.items():
        print(f"\n  ━━━ {slug} ━━━")
        for item, dest, label in entries:
            kind = "📄"
            if "spreadsheet" in item["mimeType"]:
                kind = "📊"
            elif "document" in item["mimeType"]:
                kind = "📝"
            print(f"    {kind} [{label}] {item['name']}")
            print(f"        → {dest}/")

    if untitled:
        print("\n## UNTITLED / placeholder docs (MANUAL — leave in place):")
        for item in untitled:
            print(f"  📄 '{item['name']}' (modified {item.get('modifiedTime', '?')[:10]}, size {item.get('size', '?')} bytes)")

    if manual:
        print("\n## MANUAL — couldn't route, leave in place:")
        for item, reason in manual:
            print(f"  📄 {item['name']}  — {reason}")

    if not args.execute:
        print("\n# (Dry-run only. Re-run with --execute to perform the moves.)")
        return

    # Execute
    print("\n## EXECUTING MOVES…")
    moves_done = 0
    for slug, entries in plan_per_client.items():
        client_folder = find_client_folder(drive, slug)
        if not client_folder:
            print(f"  ⚠ {slug}: client folder not found")
            continue
        for item, dest_subpath, _ in entries:
            # Resolve / create each segment in dest_subpath
            current_parent = client_folder["id"]
            for segment in dest_subpath.split("/"):
                current_parent = ensure_folder(drive, current_parent, segment)
            # Move from root → current_parent
            drive.files().update(
                fileId=item["id"],
                addParents=current_parent,
                removeParents="root",
                fields="id, parents",
            ).execute()
            print(f"  ✓ moved → {slug}/{dest_subpath}/{item['name']}")
            moves_done += 1

    print(f"\n## DONE — {moves_done} moves executed, {len(untitled)} untitled left in place, {len(manual)} manual left in place")


if __name__ == "__main__":
    main()
