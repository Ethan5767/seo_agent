#!/usr/bin/env python3
"""
Meridian SEO Ops — Drive Intake

Reads clients.yml and downloads ONE CYCLE MONTH of team content per client, from
`From Team/Client Work/[Month YYYY]/`, into a local intake directory.

Routing — exactly what it does, in order:
    1. Start at the Drive folder id in PIPELINE_DRIVE_PARENT_FOLDER_ID ("SEO - Clients")
    2. Keep clients whose clients.yml `pipeline_status` is pilot|active
    3. Find that client's LIVE folder by alias match. Archive-marked folders
       (OLD, ARCHIVE, ...) are excluded, and the longest matching alias wins;
       ambiguity is printed, never silently resolved.  [BUG-008]
    4. Descend `From Team` → `Client Work` (exact names)
    5. Resolve ONE month folder: `--month YYYY-MM` if given, else the latest
       month folder that is not in the future. Names are parsed tolerantly —
       "July 2026", "7. July", "07 - July", "Jul 2026", "2026-07" all work.
    6. Recurse that ONE folder and take every file — no date filter
    7. Download: Google Docs → .docx, Sheets → .xlsx, native files as-is
    8. Save to <intake_dir>/<client-slug>/<YYYY-MM-DD>-<original_name>.<ext>

Why the month folder is the selector and not a date window (BUG-001 / BUG-002,
fixed 2026-07-28): a cycle is a month. This previously recursed EVERY month
folder and filtered only on `modifiedTime >= now - since_hours`, which had two
failure modes. It returned all seven of a client's month folders at once; and
because Drive bumps `modifiedTime` when a file is merely MOVED, one bulk Drive
reorganisation re-dated months of old content into the current window, so a
routine run would silently ingest half a year as "new". Scoping to a single
month folder removes both. `--since-hours` now applies only under `--all-months`
or when a client has no parseable month folders, and that fallback is announced.

Auth:
  Local dev: reads ~/.claude/scripts/seo-pipeline/.drive-token-readonly.json
  Superset cloud workspace: reads env vars DRIVE_REFRESH_TOKEN + DRIVE_CLIENT_ID +
                            DRIVE_CLIENT_SECRET (refresh-token flow)

Output (stdout — parseable by the calling Superset agent):
  CLIENT: <slug>  STATUS: <ok|skipped|error>  REASON: <text>
  ROUTED: <client-slug> <relative-path-to-downloaded-file>
  TOTAL_NEW: <N>
  ELAPSED_SECONDS: <float>

Exit codes:
  0 — ran cleanly (zero or more files downloaded)
  1 — auth failure
  2 — clients.yml malformed or missing
  3 — Drive API error
  4 — filesystem error (intake_dir not writable)

Usage (local):
  python3 drive-intake.py --since-hours 168 \\
    --clients-yml /path/to/meridian-seo-ops/clients.yml \\
    --intake-dir /tmp/intake \\
    --client northstar-landscaping          # optional: restrict to one client
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.intake.roster import parent_folder_id

PARENT_FOLDER_ID = parent_folder_id()
DEFAULT_TOKEN_FILE = Path.home() / ".claude/scripts/seo-pipeline/.drive-token-readonly.json"
SCOPES_READONLY = ["https://www.googleapis.com/auth/drive.readonly"]

MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]

# Folder-name tokens that mark a client folder as archived. A client folder whose
# name contains any of these is never selected unless it is the ONLY match.
# Why this exists: aliases are substring matches, and "OLD | Casey - The Northstar
# Company" contains the alias "Northstar Landscaping" exactly as the live folder does.
# Before this, selection was whichever folder the Drive API happened to return
# first — unordered, so the pipeline could silently read the archive. (BUG-008)
# Matched on WORD BOUNDARIES, not as substrings: a plain "old" substring test
# flags "Gold Standard" (G-old), which would hide a live client folder.
ARCHIVE_MARKER_RE = re.compile(
    r"\b(old|archives?|archived|deprecated|backup|superseded|do\s+not\s+use)\b",
    re.IGNORECASE,
)

# Ingest ledger. Lives at the ROOT of the intake dir so one file covers every
# client. Drive intake previously had no memory at all between runs: it
# re-downloaded unchanged files every time, and a doc edited on two different
# days produced two accumulated copies. (BUG-009)
STATE_FILENAME = ".drive-intake-state.json"

_MONTH_LOOKUP: dict[str, int] = {}
for _i, _m in enumerate(MONTH_NAMES, 1):
    _MONTH_LOOKUP[_m.lower()] = _i
    _MONTH_LOOKUP[_m[:3].lower()] = _i


# ─── Month folder resolution (BUG-001 / BUG-002) ───────────────────────────


def parse_month_folder(name: str, default_year: int | None = None) -> tuple[int, int] | None:
    """Parse a Drive month-folder name into (year, month), or None if it is not one.

    Deliberately tolerant, because real client folders are not consistent. All of
    these resolve: "January 2026", "1. January", "01 - January", "Jan 2026",
    "2026-01", "July". A folder with no year uses `default_year`.
    """
    s = (name or "").strip()

    # Numeric form first: 2026-01, 2026_01, 2026.01, 202601 is NOT accepted (ambiguous)
    m = re.match(r"^(20\d{2})\s*[-_./]\s*(0?[1-9]|1[0-2])$", s)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    # Strip a leading ordinal used purely for sort order: "1. January", "01 - January"
    s2 = re.sub(r"^\s*\d{1,2}\s*[.)\-–_]\s*", "", s)

    month = None
    for tok in re.findall(r"[A-Za-z]+", s2):
        hit = _MONTH_LOOKUP.get(tok.lower())
        if hit:
            month = hit
            break
    if month is None:
        return None

    ym = re.search(r"(20\d{2})", s2)
    year = int(ym.group(1)) if ym else default_year
    if year is None:
        return None
    return (year, month)


def list_child_folders(drive, parent_id: str) -> list[dict]:
    """Every non-trashed subfolder of parent_id."""
    out, page_token = [], None
    while True:
        r = drive.files().list(
            q=f"'{parent_id}' in parents and trashed = false "
              f"and mimeType = 'application/vnd.google-apps.folder'",
            fields="nextPageToken, files(id, name, modifiedTime)",
            pageSize=200, pageToken=page_token,
        ).execute()
        out.extend(r.get("files", []))
        page_token = r.get("nextPageToken")
        if not page_token:
            break
    return out


def resolve_month_folder(drive, client_work_id: str, want: tuple[int, int] | None = None):
    """Pick the month folder to ingest under `Client Work`.

    Returns (folder_dict | None, label, parsed) where `parsed` is every month
    folder found as [(year, month, folder), ...] sorted oldest first.

    Selection: the explicitly requested month if `want` is given, otherwise the
    LATEST month folder that is not in the future. Future-dated folders are
    skipped so a team member pre-creating "September 2026" in July does not
    silently redirect the whole cycle into an empty folder.
    """
    now = datetime.now(timezone.utc)
    parsed = []
    for f in list_child_folders(drive, client_work_id):
        ym = parse_month_folder(f["name"], default_year=now.year)
        if ym:
            parsed.append((ym[0], ym[1], f))
    parsed.sort(key=lambda t: (t[0], t[1]))

    if not parsed:
        return (None, "no month folders", parsed)

    if want:
        for y, mo, f in parsed:
            if (y, mo) == want:
                return (f, f"{MONTH_NAMES[mo - 1]} {y}", parsed)
        return (None, f"requested {want[0]}-{want[1]:02d} not found", parsed)

    eligible = [(y, mo, f) for y, mo, f in parsed if (y, mo) <= (now.year, now.month)]
    if not eligible:
        return (None, "every month folder is in the future", parsed)
    y, mo, f = eligible[-1]
    return (f, f"{MONTH_NAMES[mo - 1]} {y}", parsed)


# ─── Auth ──────────────────────────────────────────────────────────────────


def get_credentials():
    """Local: load cached token. Cloud: build from env vars (refresh token flow)."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    # Cloud / Superset workspace path — env vars
    refresh = os.environ.get("DRIVE_REFRESH_TOKEN")
    client_id = os.environ.get("DRIVE_CLIENT_ID")
    client_secret = os.environ.get("DRIVE_CLIENT_SECRET")
    if refresh and client_id and client_secret:
        creds = Credentials(
            token=None,
            refresh_token=refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES_READONLY,
        )
        creds.refresh(Request())
        return creds

    # Local dev path — cached token
    if not DEFAULT_TOKEN_FILE.exists():
        print(f"ERROR: no auth available. Either set env vars (DRIVE_REFRESH_TOKEN/DRIVE_CLIENT_ID/DRIVE_CLIENT_SECRET) or run bootstrap-drive-oauth.py --scope readonly first.", file=sys.stderr)
        sys.exit(1)
    creds = Credentials.from_authorized_user_file(str(DEFAULT_TOKEN_FILE), SCOPES_READONLY)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("ERROR: cached token invalid. Re-run bootstrap-drive-oauth.py --scope readonly.", file=sys.stderr)
            sys.exit(1)
    return creds


def get_drive(creds):
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ─── Drive helpers ─────────────────────────────────────────────────────────


def find_child_folder(drive, parent_id: str, name: str) -> dict | None:
    name_esc = name.replace("'", "\\'")
    r = drive.files().list(
        q=f"'{parent_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder' and name = '{name_esc}'",
        fields="files(id, name, modifiedTime)", pageSize=5,
    ).execute()
    items = r.get("files", [])
    return items[0] if items else None


def is_archive_folder(name: str) -> bool:
    """True if a folder name marks it as superseded (OLD, ARCHIVE, ...).

    Word-boundary matched on purpose. A substring test flags "Gold Standard" as
    archived because of the "old" inside "Gold", which would make a live client
    folder invisible to intake.
    """
    return bool(ARCHIVE_MARKER_RE.search(name or ""))


def find_client_folder(drive, aliases: list[str], slug: str = "?") -> dict | None:
    """Find the client's live Drive folder under SEO - Clients by alias match.

    BUG-008 (fixed 2026-07-28). This used to return the FIRST folder whose name
    contained ANY alias, with no ordering on the Drive query. Aliases are
    substring matches, so "OLD | Casey - Northstar Landscaping" matches the alias
    "Northstar Landscaping" exactly as well as the live folder does — and Drive does
    not guarantee list order. The pipeline could silently ingest the archive, with
    no error, on any run. It picked correctly on 2026-07-28 by luck.

    Now: collect EVERY match, drop archive-marked folders, and rank by alias
    specificity (longest matching alias wins, since clients.yml orders aliases
    most-specific-first for exactly this reason). Ambiguity is reported, never
    silently resolved.
    """
    r = drive.files().list(
        q=f"'{PARENT_FOLDER_ID}' in parents and trashed = false "
          f"and mimeType = 'application/vnd.google-apps.folder'",
        fields="files(id, name)", pageSize=200,
    ).execute()

    matches = []
    for f in r.get("files", []):
        nl = f["name"].lower()
        best = max((len(a) for a in aliases if a.lower() in nl), default=0)
        if best:
            matches.append((best, f))
    if not matches:
        return None

    live = [(score, f) for score, f in matches if not is_archive_folder(f["name"])]
    archived = [f["name"] for _s, f in matches if is_archive_folder(f["name"])]

    if not live:
        # Only archive folders matched. Use it rather than failing the run, but be loud.
        print(f"WARN: {slug} — only archive-marked folders matched {aliases}: {archived}. "
              f"Using {matches[0][1]['name']!r}. Rename or update aliases.")
        return matches[0][1]

    live.sort(key=lambda t: -t[0])
    chosen = live[0][1]

    if archived:
        print(f"NOTE: {slug} — ignored archive folder(s): {archived}")
    if len(live) > 1 and live[0][0] == live[1][0]:
        others = [f["name"] for _s, f in live[1:]]
        print(f"WARN: {slug} — AMBIGUOUS client folder. Chose {chosen['name']!r}; "
              f"equally-good matches: {others}. Tighten aliases in clients.yml.")

    return chosen


# Shared-with-me as a source is INTENTIONALLY REMOVED (2026-05-21).
# Rationale: GrowMinion has been instructed to upload directly into the
# Meridian-owned `From Team/Client Work/[Month YYYY]/` folders. Reading from
# "Shared with me" risks misrouting when filenames lack a client signal
# (e.g., "Stucco Sub Service Location Page" — Pat vs Lee ambiguous).
# Historical Shared-with-me docs are handled manually by Alex. The pipeline
# is single-source: Meridian-owned tree only.
def _DEPRECATED_scan_shared_with_me(drive, all_clients: list[dict], since: datetime) -> dict[str, list[dict]]:
    """
    Scan 'Shared with me' for files modified after `since`. Route each to a client
    by matching aliases against (1) the file's parent folder name walked up, and
    (2) the filename itself.

    Returns {slug: [file_objs, ...]}.
    """
    routed: dict[str, list[dict]] = {}
    # Build alias map for routing
    slug_aliases = {c["slug"]: c.get("aliases", []) for c in all_clients}

    # Step A: get all top-level "Shared with me" items
    top_items = []
    page_token = None
    while True:
        r = drive.files().list(
            q="sharedWithMe = true and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, parents, owners(emailAddress), size)",
            pageSize=200, pageToken=page_token,
        ).execute()
        top_items.extend(r.get("files", []))
        page_token = r.get("nextPageToken")
        if not page_token: break

    since_iso = since.isoformat()

    def route_by_text(text: str) -> str | None:
        for slug, aliases in slug_aliases.items():
            if matches_aliases(text, aliases):
                return slug
        return None

    def file_in_window(f: dict) -> bool:
        mt = f.get("modifiedTime", "")
        if not mt:
            return False
        try:
            return datetime.fromisoformat(mt.replace("Z", "+00:00")) >= since
        except Exception:
            return False

    def walk(folder_id: str, ancestor_text: str, slug_hint: str | None):
        page = None
        while True:
            try:
                r = drive.files().list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime, parents, owners(emailAddress), size)",
                    pageSize=200, pageToken=page,
                ).execute()
            except Exception:
                return
            for f in r.get("files", []):
                # Track ancestor text for path-based routing
                if f["mimeType"] == "application/vnd.google-apps.folder":
                    walk(f["id"], f"{ancestor_text} {f['name']}", slug_hint or route_by_text(f["name"]))
                else:
                    if not file_in_window(f):
                        continue
                    target_slug = slug_hint or route_by_text(f["name"]) or route_by_text(ancestor_text)
                    if target_slug:
                        routed.setdefault(target_slug, []).append(f)
                    else:
                        # Unrouted — record for visibility (we'll log it but not download)
                        routed.setdefault("__unrouted__", []).append(f)
            page = r.get("nextPageToken")
            if not page: break

    # Step B: for each top-level shared item, route or walk
    for item in top_items:
        is_folder = item["mimeType"] == "application/vnd.google-apps.folder"
        slug_hint = route_by_text(item["name"])
        if is_folder:
            # Walk regardless of slug_hint — sometimes top-level is a generic folder
            walk(item["id"], item["name"], slug_hint)
        else:
            # Top-level file
            if not file_in_window(item):
                continue
            target_slug = slug_hint
            if not target_slug:
                # Try peeking content for client signal (only for Google Docs/Sheets — cheap)
                if item["mimeType"] in ("application/vnd.google-apps.document", "application/vnd.google-apps.spreadsheet"):
                    try:
                        if item["mimeType"] == "application/vnd.google-apps.document":
                            data = drive.files().export(fileId=item["id"], mimeType="text/plain").execute()
                        else:
                            data = drive.files().export(fileId=item["id"], mimeType="text/csv").execute()
                        sample = data.decode("utf-8", errors="ignore")[:500] if isinstance(data, bytes) else str(data)[:500]
                        target_slug = route_by_text(sample)
                    except Exception:
                        pass
            if target_slug:
                routed.setdefault(target_slug, []).append(item)
            else:
                routed.setdefault("__unrouted__", []).append(item)

    return routed


def load_state(intake_dir: Path) -> dict:
    """Load the ingest ledger. Missing or corrupt ledger means 'ingest everything'."""
    p = intake_dir / STATE_FILENAME
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text()).get("files", {})
    except Exception:
        print(f"WARN: could not read {p} — treating every file as new.")
        return {}


def save_state(intake_dir: Path, state: dict) -> None:
    intake_dir.mkdir(parents=True, exist_ok=True)
    (intake_dir / STATE_FILENAME).write_text(
        json.dumps({"version": 1, "files": state}, indent=2, sort_keys=True)
    )


def file_fingerprint(f: dict) -> str:
    """Change signature for a Drive file.

    `md5Checksum` exists for binary uploads (.docx, .pdf) but NOT for native
    Google Docs, which is exactly the case that matters here — the team keeps one
    living Doc per month. Drive's `version` increments on every edit including
    native Docs, so it is the dependable signal; modifiedTime is the fallback.
    """
    return f.get("md5Checksum") or f.get("version") or f.get("modifiedTime") or ""


def is_settling(f: dict, settle_cutoff: datetime | None) -> bool:
    """True if the file was touched too recently to be considered finished.

    A Google Doc is always live — there is no 'the writer is done' event. Ingesting
    mid-edit pushes a half-written document into the cycle. Requiring a quiet
    period is the closest available proxy for done.
    """
    if settle_cutoff is None:
        return False
    try:
        mt = datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00"))
    except Exception:
        return False
    return mt > settle_cutoff


def list_files_recursive(drive, folder_id: str, since: datetime | None) -> list[dict]:
    """List every non-folder file under folder_id modified after `since`.

    `since=None` disables the date filter entirely. That is the correct mode when
    the caller has already scoped to a single month folder: the folder IS the
    selector, and filtering on modifiedTime there would drop legitimate files
    whose content predates the window (BUG-002).
    """
    results = []
    page_token = None
    while True:
        r = drive.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields=("nextPageToken, files(id, name, mimeType, modifiedTime, parents, "
                    "size, version, md5Checksum)"),
            pageSize=200, pageToken=page_token,
        ).execute()
        for f in r.get("files", []):
            if f["mimeType"] == "application/vnd.google-apps.folder":
                results.extend(list_files_recursive(drive, f["id"], since))
            elif since is None:
                results.append(f)  # month folder already scoped the selection
            else:
                # Filter by modifiedTime
                try:
                    mt = datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00"))
                    if mt >= since:
                        results.append(f)
                except Exception:
                    results.append(f)  # keep if we can't parse date
        page_token = r.get("nextPageToken")
        if not page_token: break
    return results


EXPORT_MIME = {
    "application/vnd.google-apps.document": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
}

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(s: str) -> str:
    s = SAFE_NAME.sub("-", s)
    return s.strip("-")[:120]


def download_file(drive, file_obj: dict, out_dir: Path) -> Path:
    from googleapiclient.http import MediaIoBaseDownload

    fid = file_obj["id"]
    mime = file_obj["mimeType"]
    orig_name = file_obj["name"]
    modified = file_obj.get("modifiedTime", "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    out_dir.mkdir(parents=True, exist_ok=True)

    if mime in EXPORT_MIME:
        export_mime, ext = EXPORT_MIME[mime]
        req = drive.files().export_media(fileId=fid, mimeType=export_mime)
        target = out_dir / f"{modified}-{safe_name(orig_name)}{ext}"
    else:
        # Native binary file (Word, PDF, etc.)
        req = drive.files().get_media(fileId=fid)
        # Preserve original extension if present
        ext = ""
        if "." in orig_name:
            ext = "." + orig_name.rsplit(".", 1)[-1]
        target = out_dir / f"{modified}-{safe_name(orig_name)}"
        if ext and not target.name.endswith(ext):
            target = out_dir / f"{modified}-{safe_name(orig_name)}{ext}"

    fh = io.FileIO(str(target), "wb")
    downloader = MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    fh.close()
    return target


# ─── Clients config ────────────────────────────────────────────────────────


def load_clients(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text())


# ─── Main ──────────────────────────────────────────────────────────────────


def process_client(drive, client_cfg: dict, since: datetime, intake_dir: Path,
                   want_month: tuple[int, int] | None = None,
                   all_months: bool = False,
                   state: dict | None = None,
                   settle_cutoff: datetime | None = None,
                   settle_hours: int = 0,
                   force: bool = False) -> tuple[int, int]:
    """Process one client. Returns (downloaded_count, error_count).

    Single source of intake (locked 2026-05-21):
      Meridian-owned folder: SEO - Clients / [Client] / From Team / Client Work / [Month YYYY]
    GrowMinion has been instructed to upload directly here. Shared-with-me as a
    source was intentionally removed — see deprecated function above for rationale.

    Scope (2026-07-28): one MONTH FOLDER per run, because one cycle is one month.
    `want_month` pins an explicit (year, month); default is the latest month
    folder that is not in the future. `all_months` restores the old behaviour of
    recursing everything under `Client Work` with a `--since-hours` date filter.
    """
    slug = client_cfg["slug"]
    aliases = client_cfg.get("aliases", [])
    state = state if state is not None else {}

    client_intake = intake_dir / slug
    downloaded = 0

    # An explicit folder id beats alias guessing and should be preferred for every
    # client. Aliases are substring matches against human-typed folder names, which
    # is fragile in both directions: on 2026-07-28 `blueline-hvac-north` matched NOTHING
    # (its folder is "Casey Blueline & Son's (North Divison)" — note the typo —
    # and no alias is a contiguous substring of it), while `blueline-hvac` matched BOTH
    # Blueline folders with only a 7-character alias-length margin deciding which.
    # (BUG-011)
    folder_id = client_cfg.get("drive_folder_id")
    if folder_id:
        try:
            client_folder = drive.files().get(
                fileId=folder_id, fields="id, name, mimeType").execute()
            if client_folder.get("mimeType") != "application/vnd.google-apps.folder":
                print(f"CLIENT: {slug}  STATUS: error  "
                      f"REASON: drive_folder_id {folder_id} is not a folder")
                return (0, 1)
        except Exception as e:
            print(f"CLIENT: {slug}  STATUS: error  "
                  f"REASON: drive_folder_id {folder_id} unreadable — {e}")
            return (0, 1)
    else:
        client_folder = find_client_folder(drive, aliases, slug)
        if not client_folder:
            print(f"CLIENT: {slug}  STATUS: error  REASON: drive folder not found "
                  f"(aliases tried: {aliases}). Set `drive_folder_id` in clients.yml "
                  f"to remove the guessing entirely.")
            return (0, 1)
        print(f"NOTE: {slug} — matched by alias, not by id. Pin `drive_folder_id: "
              f"{client_folder['id']}` in clients.yml to make this deterministic.")

    from_team = find_child_folder(drive, client_folder["id"], "From Team")
    if not from_team:
        print(f"CLIENT: {slug}  STATUS: skipped  REASON: no 'From Team' folder in {client_folder['name']!r}")
        return (0, 0)

    client_work = find_child_folder(drive, from_team["id"], "Client Work")
    if not client_work:
        print(f"CLIENT: {slug}  STATUS: skipped  REASON: no 'From Team/Client Work' folder")
        return (0, 0)

    # ── Month selection (BUG-001 / BUG-002) ────────────────────────────────
    # A cycle is a month, so the MONTH FOLDER is the selector — not a rolling
    # date window. This also neutralises BUG-002: Drive bumps modifiedTime when a
    # file is merely MOVED, so a bulk reorg used to make months of old content
    # look brand new. Scoping to one month folder makes that irrelevant.
    scan_root, scope, date_filter = client_work, "ALL MONTHS", since

    if not all_months:
        month_folder, label, parsed = resolve_month_folder(drive, client_work["id"], want_month)
        if month_folder:
            scan_root, scope, date_filter = month_folder, label, None
        elif parsed:
            # Month folders exist but none was selectable (e.g. an explicit --month miss).
            print(f"CLIENT: {slug}  STATUS: skipped  REASON: {label} "
                  f"(available: {', '.join(f'{MONTH_NAMES[m-1]} {y}' for y, m, _ in parsed)})")
            return (0, 0)
        else:
            # No parseable month folders. Fall back to the old time-window behaviour,
            # but say so — a silent fallback here is how BUG-002 goes unnoticed.
            print(f"WARN: {slug} — no month folders under 'Client Work'; falling back to "
                  f"--since-hours window. Moved/reorganised files WILL look new. "
                  f"Name them like 'July 2026'.")

    print(f"CLIENT: {slug}  SCOPE: {scope}  FOLDER: {scan_root['name']!r}")
    new_files = list_files_recursive(drive, scan_root["id"], date_filter)

    if not new_files:
        window = "no date filter" if date_filter is None else f"since {date_filter.isoformat()}"
        print(f"CLIENT: {slug}  STATUS: ok  REASON: no files in {scope} ({window})")
        return (0, 0)

    # ── Settle window + ingest ledger (BUG-009) ────────────────────────────
    # The team keeps ONE living Google Doc per month and edits it all cycle. Two
    # consequences this guards against: ingesting it mid-edit (a Doc has no "done"
    # event), and re-ingesting an unchanged 1.8 MB file on every single run.
    settling, unchanged, to_get = [], [], []
    for f in new_files:
        if is_settling(f, settle_cutoff):
            settling.append(f)
        elif not force and state.get(f["id"], {}).get("fingerprint") == file_fingerprint(f):
            unchanged.append(f)
        else:
            to_get.append(f)

    for f in settling:
        print(f"SETTLING: {slug}  {f['name']!r} — modified {f['modifiedTime']}, "
              f"still inside the {settle_hours}h quiet period. Not ingested.")
    for f in unchanged:
        print(f"UNCHANGED: {slug}  {f['name']!r} — already ingested at this version.")

    if not to_get:
        print(f"CLIENT: {slug}  STATUS: ok  REASON: nothing new in {scope} "
              f"({len(settling)} settling, {len(unchanged)} unchanged)")
        return (0, 0)

    print(f"CLIENT: {slug}  STATUS: ok  NEW_FILES: {len(to_get)}")
    for f in to_get:
        try:
            target = download_file(drive, f, client_intake)
            print(f"ROUTED: {slug}  {target.relative_to(intake_dir)}")
            state[f["id"]] = {
                "fingerprint": file_fingerprint(f),
                "name": f["name"],
                "modifiedTime": f.get("modifiedTime"),
                "version": f.get("version"),
                "slug": slug,
                "scope": scope,
                "path": str(target.relative_to(intake_dir)),
            }
            downloaded += 1
        except Exception as e:
            print(f"ERROR-DOWNLOAD: {slug} {f.get('name','?')} — {e}")

    return (downloaded, 0)


def main():
    if not PARENT_FOLDER_ID:
        raise SystemExit("[ERROR] PIPELINE_DRIVE_PARENT_FOLDER_ID is not set. "
                         "Export the Drive parent folder id before running this tool.")
    parser = argparse.ArgumentParser(description="Meridian SEO Ops — Drive intake")
    parser.add_argument("--clients-yml", type=Path, required=True, help="Path to clients.yml")
    parser.add_argument("--intake-dir", type=Path, required=True, help="Directory where downloaded files land")
    parser.add_argument("--since-hours", type=int, default=168, help="Date-window fallback, in hours (default 168 = 7 days). Only applies with --all-months, or when a client has no parseable month folders.")
    parser.add_argument("--client", help="Restrict to one client slug (optional — default = all pilot|active)")
    parser.add_argument("--month", help="Pin an explicit cycle month as YYYY-MM (e.g. 2026-07). Default: the latest month folder that is not in the future.")
    parser.add_argument("--all-months", action="store_true", help="Legacy mode: recurse every month folder and filter by --since-hours. Beware: Drive bumps modifiedTime on MOVE, so a reorg makes old files look new (BUG-002).")
    parser.add_argument("--settle-hours", type=int, default=6, help="Skip files edited within the last N hours — the team keeps one living Doc per month and there is no 'done' signal, so a quiet period is the proxy. 0 disables.")
    parser.add_argument("--force", action="store_true", help="Ignore the ingest ledger and re-download even unchanged files.")
    args = parser.parse_args()

    want_month = None
    if args.month:
        m = re.match(r"^(20\d{2})-(0[1-9]|1[0-2])$", args.month.strip())
        if not m:
            print(f"ERROR: --month must be YYYY-MM (got {args.month!r})", file=sys.stderr)
            sys.exit(2)
        want_month = (int(m.group(1)), int(m.group(2)))
    if args.month and args.all_months:
        print("ERROR: --month and --all-months are mutually exclusive", file=sys.stderr)
        sys.exit(2)

    if not args.clients_yml.exists():
        print(f"ERROR: clients.yml not found at {args.clients_yml}", file=sys.stderr)
        sys.exit(2)

    cfg = load_clients(args.clients_yml)
    clients = cfg.get("clients", [])

    # Filter by pipeline_status + optional --client
    active_clients = [c for c in clients if c.get("pipeline_status") in ("pilot", "active")]
    if args.client:
        active_clients = [c for c in active_clients if c["slug"] == args.client]
    if not active_clients:
        print("ERROR: no clients matched (none with pipeline_status pilot|active, or --client filter eliminated all)", file=sys.stderr)
        sys.exit(0)  # not technically an error — just nothing to do

    creds = get_credentials()
    drive = get_drive(creds)

    since = datetime.now(timezone.utc) - timedelta(hours=args.since_hours)
    settle_cutoff = (datetime.now(timezone.utc) - timedelta(hours=args.settle_hours)
                     if args.settle_hours > 0 else None)
    state = {} if args.force else load_state(args.intake_dir)
    if args.force:
        print("NOTE: --force — ingest ledger ignored, every file will be re-downloaded.")
    started = time.time()

    total_downloaded = 0
    total_errors = 0
    for client in active_clients:
        d, e = process_client(drive, client, since, args.intake_dir,
                              want_month=want_month, all_months=args.all_months,
                              state=state, settle_cutoff=settle_cutoff,
                              settle_hours=args.settle_hours, force=args.force)
        total_downloaded += d
        total_errors += e

    save_state(args.intake_dir, state)

    elapsed = time.time() - started
    print(f"TOTAL_NEW: {total_downloaded}")
    print(f"TOTAL_ERRORS: {total_errors}")
    print(f"ELAPSED_SECONDS: {elapsed:.2f}")

    if total_errors > 0:
        sys.exit(3)


if __name__ == "__main__":
    main()
