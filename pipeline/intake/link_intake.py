#!/usr/bin/env python3
"""Ingest Google Doc LINKS shared in Discord, routing each by folder then contents.

    wf-link-intake --clients-yml <path> --intake-dir <dir> [URL ...]
    wf-link-intake --clients-yml <path> --intake-dir <dir> --links-file links.txt
    wf-discord-intake --poll ... | wf-link-intake --clients-yml … --intake-dir … --stdin

**Why this exists.** The team drops Google Doc *links* in Discord rather than
uploading into `From Team/Client Work/[Month YYYY]/`. The 2026-07-28 poll found
**78 links and zero DOCX**. The standing policy says they should upload; they do
not, and a pipeline that only works when people follow a policy is not a pipeline.

So links are a first-class intake path. Each one is resolved by
`pipeline.intake.link_router`: folder parentage first, document contents second,
and a hard refusal when the two disagree. Nothing is guessed — an unresolved link
lands in `unrouted/` with the reason, for a human.

Shares this ledger with `drive_intake` (`.drive-intake-state.json` at the intake
root), so a doc reached by link and later by folder is not ingested twice.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.intake.drive_intake import (
    file_fingerprint,
    get_credentials,
    get_drive,
    is_settling,
    load_clients,
    load_state,
    safe_name,
    save_state,
)
from pipeline.intake.link_router import extract_file_id, resolve, signatures

MAX_ANCESTOR_HOPS = 8
EXPORT_TEXT = "text/plain"
EXPORT_DOCX = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx")


def ancestors_of(drive, meta: dict) -> list[str]:
    """Walk up the folder chain. Team-owned shares usually have none."""
    out, cur = [], meta
    for _ in range(MAX_ANCESTOR_HOPS):
        parents = cur.get("parents") or []
        if not parents:
            break
        out.append(parents[0])
        try:
            cur = drive.files().get(fileId=parents[0], fields="id,name,parents").execute()
        except Exception:
            break
    return out


def export_text(drive, fid: str) -> str:
    try:
        return drive.files().export(fileId=fid, mimeType=EXPORT_TEXT).execute().decode("utf-8", "ignore")
    except Exception:
        return ""


def save_doc(drive, meta: dict, out_dir: Path) -> Path:
    """Export a native Google Doc to .docx, or download a binary as-is."""
    out_dir.mkdir(parents=True, exist_ok=True)
    modified = (meta.get("modifiedTime") or "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    name = safe_name(meta.get("name", "untitled"))
    mime = meta.get("mimeType", "")
    if mime == "application/vnd.google-apps.document":
        blob = drive.files().export(fileId=meta["id"], mimeType=EXPORT_DOCX[0]).execute()
        target = out_dir / f"{modified}-{name}{EXPORT_DOCX[1]}"
    else:
        blob = drive.files().get_media(fileId=meta["id"]).execute()
        ext = "." + meta.get("name", "").rsplit(".", 1)[-1] if "." in meta.get("name", "") else ""
        target = out_dir / f"{modified}-{name}{ext}"
    target.write_bytes(blob)
    return target


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest shared Google Doc links, routed by folder then contents.")
    ap.add_argument("urls", nargs="*", help="Drive/Docs URLs")
    ap.add_argument("--links-file", type=Path, help="File with one URL per line")
    ap.add_argument("--stdin", action="store_true", help="Read URLs from stdin (any text; links are extracted)")
    ap.add_argument("--clients-yml", type=Path, required=True)
    ap.add_argument("--intake-dir", type=Path, required=True)
    ap.add_argument("--settle-hours", type=int, default=6,
                    help="Skip docs edited within the last N hours — a live Doc has no 'done' signal. 0 disables.")
    ap.add_argument("--force", action="store_true", help="Ignore the ingest ledger")
    ap.add_argument("--dry-run", action="store_true", help="Resolve and report, download nothing")
    args = ap.parse_args()

    raw = list(args.urls)
    if args.links_file:
        raw += args.links_file.read_text().split()
    if args.stdin:
        raw += sys.stdin.read().split()

    ids, seen = [], set()
    for tok in raw:
        fid = extract_file_id(tok)
        if fid and fid not in seen:
            seen.add(fid)
            ids.append(fid)
    if not ids:
        print("no Drive links found in input")
        print("TOTAL_NEW: 0")
        return

    cfg = load_clients(args.clients_yml)
    clients = cfg.get("clients", [])
    sigs = signatures(clients)
    folder_map = {c["drive_folder_id"]: c["slug"] for c in clients if c.get("drive_folder_id")}
    active = {c["slug"] for c in clients if c.get("pipeline_status") in ("pilot", "active")}

    drive = get_drive(get_credentials())
    state = {} if args.force else load_state(args.intake_dir)
    settle_cutoff = (datetime.now(timezone.utc) - timedelta(hours=args.settle_hours)
                     if args.settle_hours > 0 else None)

    print(f"{len(ids)} unique link(s); {len(sigs)} client signatures, {len(folder_map)} pinned folders")
    routed = unrouted = skipped = archived = 0

    for fid in ids:
        try:
            meta = drive.files().get(
                fileId=fid, fields="id,name,mimeType,modifiedTime,parents,version,md5Checksum").execute()
        except Exception as e:
            print(f"ERROR: {fid} unreadable — {e}")
            continue

        v = resolve(meta, ancestors_of(drive, meta), export_text(drive, fid), folder_map, sigs)
        name = meta.get("name", "?")

        if not v.routed:
            unrouted += 1
            print(f"UNROUTED: {name!r} — {v.detail}")
            if not args.dry_run:
                save_doc(drive, meta, args.intake_dir / "unrouted")
            continue

        # A client not yet pilot|active still gets its content RETRIEVED, into a
        # holding area. Dropping a real team drop because of a status flag loses
        # work nobody knows is missing — the team shared it, so it exists. It just
        # does not enter the cycle until the client is switched on.
        if v.slug not in active:
            archived += 1
            print(f"HELD: {v.slug} {name!r} — routed correctly, but pipeline_status "
                  f"is not pilot|active. Retrieved to inactive/{v.slug}/ , not ingested.")
            if not args.dry_run:
                save_doc(drive, meta, args.intake_dir / "inactive" / v.slug)
            continue

        if is_settling(meta, settle_cutoff):
            skipped += 1
            print(f"SETTLING: {v.slug} {name!r} — edited {meta['modifiedTime']}, still inside "
                  f"the {args.settle_hours}h quiet period")
            continue

        if not args.force and state.get(fid, {}).get("fingerprint") == file_fingerprint(meta):
            skipped += 1
            print(f"UNCHANGED: {v.slug} {name!r} — already ingested at this version")
            continue

        if args.dry_run:
            print(f"WOULD ROUTE: {v.slug}  {name!r}  via {v.how}")
            routed += 1
            continue

        try:
            target = save_doc(drive, meta, args.intake_dir / v.slug)
        except Exception as e:
            print(f"ERROR-DOWNLOAD: {v.slug} {name!r} — {e}")
            continue

        state[fid] = {
            "fingerprint": file_fingerprint(meta), "name": name,
            "modifiedTime": meta.get("modifiedTime"), "version": meta.get("version"),
            "slug": v.slug, "scope": f"link:{v.how}",
            "path": str(target.relative_to(args.intake_dir)),
        }
        routed += 1
        print(f"ROUTED: {v.slug}  {target.relative_to(args.intake_dir)}  (via {v.how})")

    if not args.dry_run:
        save_state(args.intake_dir, state)

    print(f"TOTAL_NEW: {routed}")
    print(f"TOTAL_UNROUTED: {unrouted}")
    print(f"TOTAL_SKIPPED: {skipped}")
    print(f"TOTAL_HELD_INACTIVE: {archived}")
    if unrouted:
        print(f"NOTE: {unrouted} link(s) in {args.intake_dir}/unrouted/ need a human. "
              f"Usual causes: two clients in one doc, or a doc filed under the wrong client.")


if __name__ == "__main__":
    main()
