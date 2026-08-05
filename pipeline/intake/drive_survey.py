#!/usr/bin/env python3
"""
Drive Survey — comprehensive inventory across THREE sources:
  1. the operator's "SEO - Clients" Drive subtree (Meridian-owned)
  2. "Shared with me" — files owned by external parties (GrowMinion, etc.)
  3. Local external drive ($PIPELINE_LOCAL_VAULT_ROOT/[slug]/)

Output: stdout, one line per file, tab-separated columns:
  source \t client_slug_guess \t depth \t mimeType \t modifiedTime \t size_bytes \t owner \t name \t file_id_or_path \t parent_path

Where:
  source = "meridian-drive" | "shared-with-me" | "local-vault"
  client_slug_guess = best-match client slug based on path/filename + clients.yml aliases
                       (or "UNROUTED" if no match)
  file_id_or_path = Drive file ID for Drive sources, local absolute path for local-vault

Usage:
  python3 drive-survey.py > /tmp/drive-survey.tsv
"""

from __future__ import annotations

import os
import sys
import re
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────

from pipeline.intake.roster import load_clients, parent_folder_id

PARENT_FOLDER_ID = parent_folder_id()
SCRIPT_DIR = Path(__file__).resolve().parent
TOKEN_FILE = SCRIPT_DIR / ".drive-token-readonly.json"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

LOCAL_VAULT_ROOT = Path(
    os.environ.get("PIPELINE_LOCAL_VAULT_ROOT", "")
)

# Client routing — supplied at run time, never committed (see roster.py).
CLIENTS = load_clients()


def route_client(text: str) -> str:
    text_l = text.lower()
    for client in CLIENTS:
        for alias in client["aliases"]:
            if alias.lower() in text_l:
                return client["slug"]
    return "UNROUTED"


# ─── Drive helpers ────────────────────────────────────────────────────────


def get_drive():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def emit(source: str, client_slug: str, depth: int, mime: str, modified: str, size: str, owner: str, name: str, fid_or_path: str, parent: str):
    cols = [source, client_slug, str(depth), mime, modified, size, owner, name, fid_or_path, parent]
    print("\t".join(c.replace("\t", " ").replace("\n", " ") for c in cols))


# ─── Source 1: Meridian-owned SEO - Clients tree ─────────────────────────


def walk_client_drive(drive):
    def walk(folder_id: str, path_prefix: str, depth: int):
        page_token = None
        while True:
            resp = drive.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, size, owners(emailAddress))",
                pageSize=200,
                pageToken=page_token,
            ).execute()
            for f in resp.get("files", []):
                is_folder = f["mimeType"] == "application/vnd.google-apps.folder"
                owner_email = f.get("owners", [{}])[0].get("emailAddress", "?") if f.get("owners") else "?"
                client = route_client(path_prefix + " " + f["name"])
                emit(
                    "meridian-drive",
                    client,
                    depth,
                    f["mimeType"],
                    f.get("modifiedTime", ""),
                    str(f.get("size", "")),
                    owner_email,
                    f["name"],
                    f["id"],
                    path_prefix,
                )
                if is_folder:
                    walk(f["id"], f"{path_prefix}/{f['name']}", depth + 1)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    # Top-level: iterate client subfolders under SEO - Clients
    resp = drive.files().list(
        q=f"'{PARENT_FOLDER_ID}' in parents and trashed = false",
        fields="files(id, name, mimeType, modifiedTime, size, owners(emailAddress))",
        pageSize=50,
    ).execute()
    for item in resp.get("files", []):
        is_folder = item["mimeType"] == "application/vnd.google-apps.folder"
        owner_email = item.get("owners", [{}])[0].get("emailAddress", "?") if item.get("owners") else "?"
        client = route_client(item["name"])
        emit(
            "meridian-drive",
            client,
            1,
            item["mimeType"],
            item.get("modifiedTime", ""),
            str(item.get("size", "")),
            owner_email,
            item["name"],
            item["id"],
            "SEO - Clients",
        )
        if is_folder:
            walk(item["id"], item["name"], 2)


# ─── Source 2: "Shared with me" — external (GrowMinion etc.) ──────────────


def walk_shared_with_me(drive):
    """List everything in 'Shared with me' that routes to a known client."""
    # Drive doesn't have a single "shared with me" folder ID; query syntax: sharedWithMe = true
    # We list top-level shared items first (anything where the immediate parent isn't our drive)
    # then walk into folders we have access to.

    def walk(folder_id: str, path_prefix: str, depth: int):
        page_token = None
        while True:
            try:
                resp = drive.files().list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime, size, owners(emailAddress))",
                    pageSize=200,
                    pageToken=page_token,
                ).execute()
            except Exception as e:
                emit("shared-with-me", "ERROR", depth, "", "", "", "?", f"WALK_ERROR: {e}", folder_id, path_prefix)
                return
            for f in resp.get("files", []):
                is_folder = f["mimeType"] == "application/vnd.google-apps.folder"
                owner_email = f.get("owners", [{}])[0].get("emailAddress", "?") if f.get("owners") else "?"
                client = route_client(path_prefix + " " + f["name"])
                emit(
                    "shared-with-me",
                    client,
                    depth,
                    f["mimeType"],
                    f.get("modifiedTime", ""),
                    str(f.get("size", "")),
                    owner_email,
                    f["name"],
                    f["id"],
                    path_prefix,
                )
                if is_folder:
                    walk(f["id"], f"{path_prefix}/{f['name']}", depth + 1)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    # Top-level shared items
    page_token = None
    while True:
        resp = drive.files().list(
            q="sharedWithMe = true and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, size, owners(emailAddress))",
            pageSize=200,
            pageToken=page_token,
        ).execute()
        for item in resp.get("files", []):
            is_folder = item["mimeType"] == "application/vnd.google-apps.folder"
            owner_email = item.get("owners", [{}])[0].get("emailAddress", "?") if item.get("owners") else "?"
            client = route_client(item["name"])
            # Skip non-client noise (only emit items that route to a client OR are folders we should walk)
            if client == "UNROUTED" and not is_folder:
                continue
            emit(
                "shared-with-me",
                client,
                1,
                item["mimeType"],
                item.get("modifiedTime", ""),
                str(item.get("size", "")),
                owner_email,
                item["name"],
                item["id"],
                "Shared with me",
            )
            if is_folder and client != "UNROUTED":
                # Only walk INTO folders that route to a known client
                walk(item["id"], item["name"], 2)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break


# ─── Source 3: Local external drive vault ─────────────────────────────────


def walk_local_vault():
    if not LOCAL_VAULT_ROOT.exists():
        emit("local-vault", "ERROR", 0, "", "", "", "?", f"ROOT_NOT_FOUND: {LOCAL_VAULT_ROOT}", "", "")
        return
    for client_dir in sorted(LOCAL_VAULT_ROOT.iterdir()):
        if not client_dir.is_dir() or client_dir.name.startswith("."):
            continue
        slug = client_dir.name
        for path in sorted(client_dir.rglob("*")):
            if path.name.startswith(".") or "/.git/" in str(path) or "/node_modules/" in str(path):
                continue
            depth = len(path.relative_to(client_dir).parts)
            stat = path.stat()
            modified = ""
            try:
                from datetime import datetime, timezone
                modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            except Exception:
                pass
            mime = "directory" if path.is_dir() else "file"
            size = str(stat.st_size) if path.is_file() else ""
            emit(
                "local-vault",
                slug,
                depth,
                mime,
                modified,
                size,
                "alex (local)",
                path.name,
                str(path),
                str(path.parent.relative_to(client_dir)),
            )


def main():
    if not PARENT_FOLDER_ID:
        raise SystemExit("[ERROR] PIPELINE_DRIVE_PARENT_FOLDER_ID is not set. "
                         "Export the Drive parent folder id before running this tool.")
    drive = get_drive()
    print(f"# Drive survey — generated by drive-survey.py", file=sys.stderr)
    print(f"# columns: source\\tclient_slug\\tdepth\\tmimeType\\tmodifiedTime\\tsize\\towner\\tname\\tid_or_path\\tparent", file=sys.stderr)

    print("# === SOURCE 1: meridian-drive (SEO - Clients) ===", file=sys.stderr)
    walk_client_drive(drive)

    print("# === SOURCE 2: shared-with-me ===", file=sys.stderr)
    walk_shared_with_me(drive)

    print("# === SOURCE 3: local-vault ===", file=sys.stderr)
    walk_local_vault()


if __name__ == "__main__":
    main()
