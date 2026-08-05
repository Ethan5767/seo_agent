#!/usr/bin/env python3
"""
Drive Reorganization — restructure each client's subfolder under "SEO - Clients"
to match GrowMinion's clean convention:

  [Client] /
  ├── Business Context              (top-level, intake reference)
  ├── Client Worksheet              (top-level, intake reference)
  ├── Monthly Report /
  │   └── [Month YYYY] /            (e.g., "April 2026") — GrowMinion's monthly client reports
  ├── Work File /
  │   └── [Month YYYY] /            — GrowMinion's monthly SEO content + service-page drafts
  ├── Meridian Materials /          — Alex-created docs shared WITH the team: original audit / proposal,
  │                                   trifold brochure, the operator's original game plan. Stay accessible to team.
  ├── _Internal /                   (Meridian-only — NOT shared with team eventually:
  │                                   GSC reports, performance dashboards, etc.)
  └── Archive /                     (existing — preserved as-is, never modified)

Safety rules:
  • Default mode is DRY-RUN. Pass --execute to actually move files.
  • Never deletes anything. Only moves + creates folders.
  • Anything that can't be classified is flagged "MANUAL" — left in place.
  • Output: a move plan to stdout. Same output in both dry-run and execute modes.

Usage:
  # See what would happen (no changes)
  python3 drive-reorg.py --client northstar-landscaping > /tmp/reorg-plan-northstar.txt

  # See plan for all clients
  python3 drive-reorg.py --all > /tmp/reorg-plan-all.txt

  # Execute after reviewing the plan
  python3 drive-reorg.py --client northstar-landscaping --execute
"""

from __future__ import annotations

import os
import argparse
import re
import sys
from pathlib import Path

from pipeline.intake.roster import load_clients, parent_folder_id

PARENT_FOLDER_ID = parent_folder_id()
SCRIPT_DIR = Path(__file__).resolve().parent
TOKEN_FILE = SCRIPT_DIR / ".drive-token-full.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Same client routing as drive_survey.py — supplied at run time (roster.py).
CLIENTS = load_clients()

MONTH_PATTERN = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|februrary)\b",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")

MONTH_NORM = {
    "jan": "January", "january": "January",
    "feb": "February", "february": "February", "februrary": "February",
    "mar": "March", "march": "March",
    "apr": "April", "april": "April",
    "may": "May",
    "jun": "June", "june": "June",
    "jul": "July", "july": "July",
    "aug": "August", "august": "August",
    "sep": "September", "sept": "September", "september": "September",
    "oct": "October", "october": "October",
    "nov": "November", "november": "November",
    "dec": "December", "december": "December",
}

# GSC / performance reports — source data for the future monthly report
# automation. Route into Monthly Report/[Month YYYY]/GSC Data/.
GSC_REPORT_PATTERNS = re.compile(
    r"(performance[- ]on[- ]search|search[- ]performance|gsc[- ]data|google-search)",
    re.IGNORECASE,
)

# True internal (do NOT share with team eventually) — currently nothing,
# leaving the pattern set up for future additions.
INTERNAL_PATTERNS = re.compile(
    r"(gmb-manage|_proposal_internal)",
    re.IGNORECASE,
)

# Date pattern in GSC report filenames: 2026-05-21 → year + month index
GSC_DATE_PATTERN = re.compile(r"(\d{4})-(\d{2})-\d{2}")

# Alex-created materials he shares WITH the team (not from team).
# These go to a "Meridian Materials" subfolder, kept accessible to the team.
PIPELINE_MATERIAL_PATTERNS = re.compile(
    r"(\bproposal\b|\baudit\b|tri.?fold|trifold|brochure|\.pptx?$|\.key$|design[- ]?file)",
    re.IGNORECASE,
)

# File extensions typically owned by Alex (uploaded from desktop, not native Google Docs)
NICK_FILE_EXTENSIONS = re.compile(r"\.(docx|doc|pptx|ppt|pdf|key|pages)$", re.IGNORECASE)

NICK_OWNER_EMAILS = {
    e.strip()
    for e in os.environ.get("PIPELINE_OWNER_EMAILS", "").split(",")
    if e.strip()
}


def route_client(name: str) -> str:
    nl = name.lower()
    for client in CLIENTS:
        for alias in client["aliases"]:
            if alias.lower() in nl:
                return client["slug"]
    return "UNROUTED"


def extract_month_year(name: str, fallback_modified_time: str = "") -> tuple[str, str] | None:
    """Return (Month, YYYY) tuple or None if not findable."""
    m_match = MONTH_PATTERN.search(name)
    y_match = YEAR_PATTERN.search(name)
    if m_match:
        month = MONTH_NORM.get(m_match.group(1).lower(), m_match.group(1).title())
        year = y_match.group(1) if y_match else (fallback_modified_time[:4] if fallback_modified_time else None)
        if year:
            return (month, year)
    if fallback_modified_time:
        # Use the file's modifiedTime as last-resort
        try:
            yr = fallback_modified_time[:4]
            mo_num = int(fallback_modified_time[5:7])
            mo_names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
            return (mo_names[mo_num - 1], yr)
        except Exception:
            pass
    return None


def classify(name: str, modified: str, owner_email: str = "", mime_type: str = "") -> tuple[str, str]:
    """
    Classify a file. Returns (action, destination_path).
    Actions:
      - MOVE → destination_path is the target subfolder under the client's folder
      - INTERNAL → flagged for _Internal/ (future exit to external drive vault)
      - PIPELINE_MATERIALS → the operator's deliverables shared WITH the team (audit, proposal, brochure)
      - MANUAL → can't classify, leave in place
    """
    n = name.lower()
    nick_owned = owner_email.lower() in NICK_OWNER_EMAILS

    # GSC / performance reports — source data for monthly report automation.
    # Route into Monthly Report/[Month YYYY]/GSC Data/.
    if GSC_REPORT_PATTERNS.search(n):
        # Extract month/year from the date in the filename
        date_match = GSC_DATE_PATTERN.search(name)
        if date_match:
            yr = date_match.group(1)
            mo_idx = int(date_match.group(2))
            mo_names = ["January", "February", "March", "April", "May", "June",
                        "July", "August", "September", "October", "November", "December"]
            return ("MOVE", f"Monthly Report/{mo_names[mo_idx - 1]} {yr}/GSC Data")
        # Fallback to modifiedTime
        my = extract_month_year("", modified)
        if my:
            return ("MOVE", f"Monthly Report/{my[0]} {my[1]}/GSC Data")
        return ("MOVE", "Monthly Report/GSC Data")

    # True internal (currently empty pattern set, future use)
    if INTERNAL_PATTERNS.search(n):
        return ("INTERNAL", "_Internal")

    # Meridian Materials — the operator's original docs shared WITH the team.
    # Match: contains "proposal" / "audit" / "brochure" / "tri-fold" / Office-format files (pptx/docx) Alex uploaded.
    if PIPELINE_MATERIAL_PATTERNS.search(name):
        return ("MOVE", "Meridian Materials")

    # Alex-owned Office docs (Word/PowerPoint/PDF uploaded from desktop) with month pattern → likely the operator's original plan
    if nick_owned and NICK_FILE_EXTENSIONS.search(name):
        if "plan" in n:
            return ("MOVE", "Meridian Materials")
        # Generic Alex-uploaded Office doc — Meridian Materials by default
        return ("MOVE", "Meridian Materials")

    # Business Context (intake reference)
    if "business context" in n:
        return ("MOVE", "Business Context")

    # Client Worksheet (intake reference)
    if "worksheet" in n or "client work sheet" in n:
        return ("MOVE", "Client Worksheet")

    # Monthly Report — has the literal phrase "monthly report"
    if "monthly report" in n:
        my = extract_month_year(name, modified)
        if my:
            return ("MOVE", f"Monthly Report/{my[0]} {my[1]}")
        return ("MOVE", "Monthly Report")

    # Work File — explicit "work file" OR "work plan" OR "game plan" (GrowMinion's monthly output)
    if "work file" in n or "work plan" in n or "game plan" in n or "gameplan" in n:
        my = extract_month_year(name, modified)
        if my:
            return ("MOVE", f"Work File/{my[0]} {my[1]}")
        return ("MOVE", "Work File")

    # Link Building / Citations — Work File support assets
    if "link building" in n or "map citations" in n or "citations" in n:
        return ("MOVE", "Work File/_Link Building")

    # Service-page / content docs with a month name in them — Work File for that month
    if MONTH_PATTERN.search(name):
        my = extract_month_year(name, modified)
        if my:
            return ("MOVE", f"Work File/{my[0]} {my[1]}")

    # Service-page / content docs WITHOUT month — use modifiedTime as fallback
    if any(k in n for k in ["service page", "service pages", "sub service", "page content", "blog", "faq", "content", "industries", "soffit", "siding", "gutter", "fascia", "hub and sub", "hub and subrab", "restoration", "water damage", "residential", "commercial", "stucco", "masonry", "waterproofing"]):
        my = extract_month_year("", modified)
        if my:
            return ("MOVE", f"Work File/{my[0]} {my[1]}")

    # Product description → Business Context
    if "product description" in n:
        return ("MOVE", "Business Context")

    # Couldn't figure it out
    return ("MANUAL", "")


def get_drive():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def ensure_folder(drive, parent_id: str, name: str, dry_run: bool) -> str:
    """Find or create a folder. Returns folder ID (or '[would-create]' in dry-run)."""
    resp = drive.files().list(
        q=f"'{parent_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder' and name = '{name.replace(chr(39), chr(92)+chr(39))}'",
        fields="files(id, name)",
        pageSize=10,
    ).execute()
    items = resp.get("files", [])
    if items:
        return items[0]["id"]
    if dry_run:
        return "[would-create]"
    new_folder = drive.files().create(
        body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
        fields="id",
    ).execute()
    return new_folder["id"]


def reorg_client(drive, client_slug: str, dry_run: bool):
    # Find the client's top-level subfolder under SEO - Clients
    resp = drive.files().list(
        q=f"'{PARENT_FOLDER_ID}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'",
        fields="files(id, name)",
        pageSize=50,
    ).execute()

    client_folder = None
    for f in resp.get("files", []):
        if route_client(f["name"]) == client_slug:
            client_folder = f
            break
    if not client_folder:
        print(f"# ERROR: no Drive folder found for client {client_slug}")
        return

    print(f"\n# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"# CLIENT: {client_slug}")
    print(f"# Drive folder: {client_folder['name']} (id={client_folder['id']})")
    print(f"# Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print(f"# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # List children at depth 1
    page_token = None
    items = []
    while True:
        r = drive.files().list(
            q=f"'{client_folder['id']}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, owners(emailAddress))",
            pageSize=200,
            pageToken=page_token,
        ).execute()
        items.extend(r.get("files", []))
        page_token = r.get("nextPageToken")
        if not page_token:
            break

    print(f"# {len(items)} items at root.\n")

    # Detect duplicates by name (case-insensitive, trimmed)
    name_counts: dict[str, int] = {}
    for item in items:
        key = item["name"].strip().lower()
        name_counts[key] = name_counts.get(key, 0) + 1
    duplicate_names = {n for n, c in name_counts.items() if c > 1}

    # Plan moves
    plan = []
    for item in items:
        # Skip the Archive folder + already-organized subfolders + already-classified subfolders
        if item["mimeType"] == "application/vnd.google-apps.folder":
            if item["name"] in ("Archive", "Business Context", "Client Worksheet", "Monthly Report", "Monthly Reports", "Work File", "Meridian Materials", "_Internal"):
                print(f"  SKIP (already-existing structure folder): 📁 {item['name']}  ← merge contents into new structure manually if you want")
                continue
        # If duplicate, flag MANUAL regardless of what we'd otherwise do
        if item["name"].strip().lower() in duplicate_names:
            plan.append((item, "MANUAL", "DUPLICATE — leave in place, you decide which to keep"))
            continue
        owner_email = item.get("owners", [{}])[0].get("emailAddress", "") if item.get("owners") else ""
        action, dest = classify(item["name"], item.get("modifiedTime", ""), owner_email, item.get("mimeType", ""))
        plan.append((item, action, dest))

    # Group by action
    moves_by_dest = {}
    manuals = []
    internals = []
    for item, action, dest in plan:
        if action == "MOVE":
            moves_by_dest.setdefault(dest, []).append(item)
        elif action == "INTERNAL":
            internals.append(item)
        else:
            manuals.append(item)

    # Print plan
    if moves_by_dest:
        print("## MOVE plan:")
        for dest in sorted(moves_by_dest.keys()):
            print(f"  → {dest}/")
            for item in moves_by_dest[dest]:
                kind = "📁" if item["mimeType"].endswith("folder") else ("🔗" if "shortcut" in item["mimeType"] else "📄")
                print(f"      {kind} {item['name']}")

    if internals:
        print("\n## INTERNAL (move to _Internal/ for now, future exit to external drive):")
        for item in internals:
            kind = "📁" if item["mimeType"].endswith("folder") else ("🔗" if "shortcut" in item["mimeType"] else "📄")
            print(f"  {kind} {item['name']}")

    if manuals:
        print("\n## MANUAL (couldn't classify — leave in place, you decide):")
        for item in manuals:
            kind = "📁" if item["mimeType"].endswith("folder") else ("🔗" if "shortcut" in item["mimeType"] else "📄")
            print(f"  {kind} {item['name']}  (modified: {item.get('modifiedTime', '?')})")

    # Execute (if not dry-run)
    if not dry_run:
        print("\n## EXECUTING MOVES…")
        # Resolve all destination folder IDs (creating along the way)
        dest_id_cache = {}
        for dest in moves_by_dest.keys():
            parts = dest.split("/")
            current_id = client_folder["id"]
            current_path = ""
            for part in parts:
                current_path = f"{current_path}/{part}" if current_path else part
                if current_path not in dest_id_cache:
                    fid = ensure_folder(drive, current_id, part, dry_run=False)
                    dest_id_cache[current_path] = fid
                current_id = dest_id_cache[current_path]
        # Resolve _Internal
        if internals:
            dest_id_cache["_Internal"] = ensure_folder(drive, client_folder["id"], "_Internal", dry_run=False)

        # Move files
        for dest, dest_items in moves_by_dest.items():
            dest_id = dest_id_cache[dest]
            for item in dest_items:
                drive.files().update(
                    fileId=item["id"],
                    addParents=dest_id,
                    removeParents=client_folder["id"],
                    fields="id, parents",
                ).execute()
                print(f"  ✓ moved → {dest}/{item['name']}")
        for item in internals:
            drive.files().update(
                fileId=item["id"],
                addParents=dest_id_cache["_Internal"],
                removeParents=client_folder["id"],
                fields="id, parents",
            ).execute()
            print(f"  ✓ moved → _Internal/{item['name']}")
        print(f"\n## DONE — {sum(len(v) for v in moves_by_dest.values()) + len(internals)} files moved, {len(manuals)} left in place for manual review")


def main():
    if not PARENT_FOLDER_ID:
        raise SystemExit("[ERROR] PIPELINE_DRIVE_PARENT_FOLDER_ID is not set. "
                         "Export the Drive parent folder id before running this tool.")
    parser = argparse.ArgumentParser(description="Reorganize Drive client folders to GrowMinion convention.")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--client", help="Client slug (e.g., northstar-landscaping)")
    g.add_argument("--all", action="store_true", help="Run for all clients")
    parser.add_argument("--execute", action="store_true", help="Execute moves (default = dry-run)")
    args = parser.parse_args()

    drive = get_drive()
    dry_run = not args.execute

    if args.all:
        for client in CLIENTS:
            reorg_client(drive, client["slug"], dry_run)
    else:
        reorg_client(drive, args.client, dry_run)


if __name__ == "__main__":
    main()
