#!/usr/bin/env python3
"""deliver.py — a rendered report leaves the pipeline, over email or Telegram.

The SOP promises reports "sent via Email or Telegram", behind a human review:
"a real person always checks it first so no bad or confusing messages ever go
out to a client" (SOP §10). This module encodes exactly that gate.

    wf-deliver --project <repo> --cycle 2026-09 --report progress
        -> renders the message and WRITES it to
           docs/audit/<cycle>/outbox/<channel>-<report>.txt, prints a preview,
           and stops. Nothing is sent. This is the review step.

    wf-deliver ... --send
        -> actually transmits over the channels in the client's delivery config,
           then appends a receipt (channel, target, status — never the body) to
           docs/audit/<cycle>/outbox/delivery-log.jsonl.

Secrets are read from the environment BY NAME (CLAUDE.md §6); recipients live in
the CLIENT repo docs/client-config.yml under `delivery:`. Anything unconfigured
degrades to a NAMED SKIP — never a crash, never a silent success:

    delivery:
      channels: []                 # ["email", "telegram"]; empty = deliver nothing
      email: "<client@example.com>"
      telegram_chat_id: "<chat-id>"

Env: SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASS; TELEGRAM_BOT_TOKEN.
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
import urllib.error
import urllib.request
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from pipeline.audit.plan import audit_dir, cycles
from pipeline.lib.common import load_config

REPORTS = {
    "progress": "report-progress.md",
    "action": "report-action.md",
    "combined": "report.md",
}
TELEGRAM_MAX = 4096


def resolve_report(project, cycle: str, report: str) -> tuple:
    """(subject, body) for the chosen report, or raise FileNotFoundError."""
    fname = REPORTS[report]
    path = audit_dir(project) / cycle / fname
    body = path.read_text()  # FileNotFoundError propagates to the caller
    titles = {"progress": "Progress Report", "action": "Action-Needed Report",
              "combined": "Site Health Report"}
    return f"{titles[report]} — {cycle}", body


def send_email(subject: str, body: str, to: str) -> str:
    """Transmit over SMTP with STARTTLS, or a named skip. Returns a status."""
    host = os.environ.get("SMTP_HOST")
    port = os.environ.get("SMTP_PORT", "587")
    user = os.environ.get("SMTP_USER")
    pw = os.environ.get("SMTP_PASS")
    for name, val in (("SMTP_HOST", host), ("SMTP_USER", user), ("SMTP_PASS", pw)):
        if not val:
            return f"SKIP email: {name} unset"
    if not to:
        return "SKIP email: delivery.email unset in client config"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, int(port), timeout=30) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        return f"ERROR email: {type(exc).__name__}: {exc}"
    return f"sent email -> {to}"


def send_telegram(body: str, chat_id: str) -> str:
    """POST to the Telegram Bot API, or a named skip. Returns a status."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return "SKIP telegram: TELEGRAM_BOT_TOKEN unset"
    if not chat_id:
        return "SKIP telegram: delivery.telegram_chat_id unset in client config"
    text = body if len(body) <= TELEGRAM_MAX else body[:TELEGRAM_MAX - 3] + "..."
    payload = json.dumps({"chat_id": str(chat_id), "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except (urllib.error.URLError, OSError) as exc:
        return f"ERROR telegram: {type(exc).__name__}: {exc}"
    return f"sent telegram -> chat {chat_id}"


def _outbox(project, cycle: str) -> Path:
    d = audit_dir(project) / cycle / "outbox"
    d.mkdir(parents=True, exist_ok=True)
    return d


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-deliver",
        description="Deliver a rendered report to the client (outbox by default; "
                    "--send actually transmits).")
    ap.add_argument("--project", required=True, help="client repo root")
    ap.add_argument("--cycle", help="YYYY-MM (default: the newest measured cycle)")
    ap.add_argument("--report", choices=list(REPORTS), default="progress",
                    help="which report to deliver (default: progress)")
    ap.add_argument("--send", action="store_true",
                    help="actually transmit; without it, only the outbox preview is written")
    args = ap.parse_args()

    cycle = args.cycle
    if not cycle:
        available = cycles(args.project)
        if not available:
            print(f"[ERROR] no measured cycle under {audit_dir(args.project)}",
                  file=sys.stderr)
            return 2
        cycle = available[-1]

    try:
        subject, body = resolve_report(args.project, cycle, args.report)
    except FileNotFoundError:
        print(f"[ERROR] {REPORTS[args.report]} not found for cycle {cycle} — "
              f"run wf-site-plan first", file=sys.stderr)
        return 2

    cfg = load_config(args.project)
    delivery = cfg.get("delivery") if isinstance(cfg.get("delivery"), dict) else {}
    channels = delivery.get("channels") or []
    message = f"{subject}\n\n{body}"

    if not args.send:
        out = _outbox(args.project, cycle)
        for ch in channels or ["(none configured)"]:
            preview = out / f"{ch}-{args.report}.txt"
            preview.write_text(message)
        print(f"[OUTBOX] wrote preview for {channels or 'no channels'} to {out}. "
              f"Review it, then re-run with --send.")
        print("\n--- preview ---\n" + message[:800]
              + ("\n... (truncated)" if len(message) > 800 else ""))
        return 0

    if not channels:
        print("[WARN] delivery.channels is empty — nothing sent. Declare "
              "channels in docs/client-config.yml.", file=sys.stderr)
        return 0

    statuses = []
    for ch in channels:
        if ch == "email":
            statuses.append(("email", delivery.get("email", ""),
                             send_email(subject, message, delivery.get("email", ""))))
        elif ch == "telegram":
            statuses.append(("telegram", delivery.get("telegram_chat_id", ""),
                             send_telegram(message, delivery.get("telegram_chat_id", ""))))
        else:
            statuses.append((ch, "", f"SKIP: unknown channel {ch!r}"))

    log = _outbox(args.project, cycle) / "delivery-log.jsonl"
    with log.open("a") as fh:
        for channel, target, status in statuses:
            fh.write(json.dumps({"date": date.today().isoformat(), "cycle": cycle,
                                 "report": args.report, "channel": channel,
                                 "target": target, "status": status}) + "\n")
            print(f"[{channel}] {status}", file=sys.stderr)

    # A run where every channel skipped/errored is not a success.
    return 0 if any(s.startswith("sent") for _, _, s in statuses) else 1


if __name__ == "__main__":
    sys.exit(main())
