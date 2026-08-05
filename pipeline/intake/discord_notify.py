#!/usr/bin/env python3
"""Discord notify — post pipeline feedback BACK to the channel the team works in.

The other half of `discord_intake.py`. Intake pulls a content drop out of a
Discord channel; this posts the verdict back into the SAME channel, so the
content team gets `preflight_docx.py`'s fix-list where they already are —
no cross-repo push, no PAT, no client-repo write access required.

Auth, DNS and error semantics are DELIBERATELY NOT REIMPLEMENTED here. Token
resolution (`DISCORD_BOT_TOKEN` env, else `~/.meridian/discord-bot.token`) and
the DNS-over-HTTPS override for ISPs that hand back a bogus A record for
discord.com are imported straight from `discord_intake`, so the poller and the
notifier can never drift apart on either.

PERMISSIONS. Intake needs View Channels + Read Message History. Posting needs
one more: **Send Messages** (and Attach Files, for `--file`). A bot that can
read but not write returns 403 on POST. That is a *permission grant a human
still has to make*, not a bug, so a 403 here degrades gracefully: it prints the
exact fix and returns 3 (a distinct, catchable code) instead of exploding a CI
run that has already done its real work.

THE 2000-CHARACTER WALL. Discord hard-rejects a message body over 2000 chars
with a 400. A fix-list for a 25-page DOCX blows through that easily, so this
module never sends a body it has not measured: `truncate()` cuts to the last
clean line boundary that fits and appends a pointer to the full artifact. The
full fix-list always survives as a workflow artifact — the message is a
signpost, never the system of record.

Usage
-----
  discord_notify.py --channel ID --message "text"
  discord_notify.py --channel ID --message-file summary.md --file fix-list.md
  discord_notify.py --channel ID --summary-json run-summary.json --artifact-url URL
  discord_notify.py --channel ID --summary-json run-summary.json --dry-run

`--dry-run` prints the exact bytes that WOULD be posted and touches neither the
network nor the token. It is the supported way to validate formatting offline.

Exit codes
----------
  0  posted (or dry-run rendered, or nothing to say)
  1  network / unexpected API failure
  2  usage or auth problem (no token, no channel)
  3  403 Forbidden — the bot lacks Send Messages on that channel
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

if __name__ == '__main__' and __package__ is None:  # see distill.py invocation caveat
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Reuse, do not duplicate: one definition of the API base, the user agent, the
# token search order and the DoH workaround.
from pipeline.intake.discord_intake import (  # noqa: E402
    API,
    UA,
    install_dns_override,
    resolve_token,
)

# Discord's documented hard limit on message content. Not a style choice.
MAX_MESSAGE = 2000
# Room reserved for the "full report" pointer appended to a truncated body.
TRUNCATE_MARGIN = 220


# ── formatting ────────────────────────────────────────────────────────────────
def truncate(body: str, artifact_url: str | None = None, limit: int = MAX_MESSAGE) -> str:
    """Fit `body` inside Discord's message limit, cutting on a line boundary.

    A mid-word cut in the middle of a fix-list reads like corruption, so the cut
    lands on the last newline that fits. The pointer that replaces the dropped
    tail names where the complete version lives — a truncated message that does
    not say it was truncated is worse than no message.
    """
    if len(body) <= limit:
        return body

    where = f'\n\n… truncated. Full fix-list: {artifact_url}' if artifact_url else \
            '\n\n… truncated — see the `intake-fix-lists` artifact on this workflow run for the full list.'
    budget = limit - len(where)
    if budget <= 0:                      # pathological pointer; fall back to a hard cut
        return body[:limit]
    cut = body[:budget]
    nl = cut.rfind('\n')
    if nl > budget * 0.5:                # only snap to a line break if it keeps most of the text
        cut = cut[:nl]
    return cut.rstrip() + where


def _plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + 's')


def format_summary(summary: dict) -> str:
    """Render an intake run-summary into the message the team reads.

    Input is the JSON the workflow assembles: each entry pairs a retrieved file
    with the `preflight_docx.py --json` payload for it (or a reason there is
    none). Returns '' when there is nothing new — the caller MUST treat empty as
    "post nothing". A poller that says "nothing new" every 15 minutes trains the
    channel to mute it, which costs us the one thing this loop is for.
    """
    files = summary.get('files') or []
    if not files:
        return ''

    artifact_url = summary.get('artifact_url')
    run_url = summary.get('run_url')

    n = len(files)
    lines = [f'**Intake pre-flight** — {n} new {_plural(n, "file")} picked up from this channel', '']

    for f in files:
        name = f.get('name', '?')
        client = f.get('client') or 'unrouted'
        status = f.get('status', 'unknown')
        pf = f.get('preflight') or {}

        if status == 'skipped':
            lines.append(f'`{name}` → **{client}** · pre-flight skipped')
            if f.get('note'):
                lines.append(f'  ↳ {f["note"]}')
            lines.append('')
            continue

        if status == 'error':
            lines.append(f'`{name}` → **{client}** · ⚠️ pre-flight could not run')
            if f.get('note'):
                lines.append(f'  ↳ {f["note"]}')
            lines.append('')
            continue

        pages = pf.get('pages', 0)
        blocking = pf.get('blocking_findings', 0)
        curate = pf.get('curate_findings', 0)
        ready = len(pf.get('pages_ready') or [])
        blocked = pf.get('pages_blocked') or []

        icon = '🔴' if blocking else ('🟡' if curate else '🟢')
        lines.append(f'{icon} `{name}` → **{client}**')
        lines.append(
            f'  {pages} {_plural(pages, "page")} · '
            f'**{blocking} blocking** · {curate} curate · {ready} ready to ship'
        )
        if blocked:
            shown = ', '.join(blocked[:6])
            more = f' (+{len(blocked) - 6} more)' if len(blocked) > 6 else ''
            lines.append(f'  ↳ would be REFUSED at emit: {shown}{more}')
        lines.append('')

    checked = [f for f in files if f.get('preflight')]
    total_block = sum((f.get('preflight') or {}).get('blocking_findings', 0) for f in checked)

    if total_block:
        lines.append(f'**{total_block} blocking {_plural(total_block, "finding")} must be fixed in the '
                     'source doc before these pages can be built.**')
    elif not checked:
        # NEVER report a clean bill of health for files nothing actually
        # inspected. "No blocking findings" when every file was skipped is a
        # false all-clear, and a false all-clear is worse than silence.
        lines.append('⚠️ **Pre-flight did not run on any of these files** — they were retrieved and '
                     'archived, but NOT checked. Nothing above says the content is clean.')
    elif len(checked) < len(files):
        n = len(files) - len(checked)
        lines.append(f'No blocking findings in the {len(checked)} file(s) checked — '
                     f'{n} not pre-flighted (see above).')
    else:
        lines.append('No blocking findings — this handoff can go to build.')

    if artifact_url:
        lines.append(f'Full fix-list: {artifact_url}')
    elif run_url:
        lines.append(f'Full fix-list: `intake-fix-lists` artifact on {run_url}')

    return truncate('\n'.join(lines).rstrip() + '\n', artifact_url)


# ── transport ─────────────────────────────────────────────────────────────────
def _handle_http_error(e: urllib.error.HTTPError, channel: str) -> int:
    body = e.read().decode(errors='replace')[:400]
    if e.code == 401:
        print('[FAIL] 401 Unauthorized — the bot token is wrong or was reset.', file=sys.stderr)
        return 2
    if e.code == 403:
        print(
            f'[SKIP] 403 Forbidden posting to channel {channel} — the bot can read this channel '
            'but is not allowed to write to it.\n'
            '  Grant the bot **Send Messages** (and **Attach Files** if you post attachments) on '
            'this channel:\n'
            '    Server Settings -> Roles -> <bot role> -> Send Messages,  or\n'
            '    right-click the channel -> Edit Channel -> Permissions -> add the bot role.\n'
            '  The run itself succeeded; only the notification was dropped.',
            file=sys.stderr,
        )
        return 3
    if e.code == 404:
        print(f'[FAIL] 404 on channel {channel} — wrong channel id, or the bot cannot see it.',
              file=sys.stderr)
        return 2
    if e.code == 400:
        print(f'[FAIL] 400 Bad Request posting to {channel}: {body}\n'
              '  Most often a body over 2000 chars — that should have been truncated before send.',
              file=sys.stderr)
        return 1
    print(f'[FAIL] HTTP {e.code} posting to {channel}: {body}', file=sys.stderr)
    return 1


def post_message(channel: str, token: str, content: str, file_path: Path | None = None) -> int:
    """POST /channels/{id}/messages, optionally as multipart with one attachment."""
    url = f'{API}/channels/{channel}/messages'
    headers = {'Authorization': f'Bot {token}', 'User-Agent': UA}

    if file_path is None:
        data = json.dumps({'content': content, 'allowed_mentions': {'parse': []}}).encode()
        headers['Content-Type'] = 'application/json'
    else:
        boundary = f'----meridian{uuid.uuid4().hex}'
        ctype = mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream'
        payload = json.dumps({
            'content': content,
            'allowed_mentions': {'parse': []},
            'attachments': [{'id': 0, 'filename': file_path.name}],
        })
        parts: list[bytes] = []
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n'
            f'Content-Type: application/json\r\n\r\n{payload}\r\n'.encode()
        )
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; '
            f'filename="{file_path.name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
        )
        parts.append(file_path.read_bytes())
        parts.append(f'\r\n--{boundary}--\r\n'.encode())
        data = b''.join(parts)
        headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'

    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            msg = json.loads(r.read().decode())
        print(f'[OK] posted to channel {channel} (message id {msg.get("id")})')
        return 0
    except urllib.error.HTTPError as e:
        return _handle_http_error(e, channel)
    except urllib.error.URLError as e:
        print(f'[FAIL] network error posting to {channel}: {e}', file=sys.stderr)
        return 1


# ── CLI ───────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        prog='wf-discord-notify',
        description='Post pipeline feedback back to a Discord channel (the reply half of discord_intake).')
    ap.add_argument('--channel', help='destination channel id')
    src = ap.add_argument_group('message source (exactly one)')
    src.add_argument('--message', help='literal message text')
    src.add_argument('--message-file', help='read the message body from this file')
    src.add_argument('--summary-json', help='an intake run-summary JSON; formats the standard digest')
    ap.add_argument('--file', dest='attach', help='attach this file to the message')
    ap.add_argument('--artifact-url', help='URL shown as the pointer to the full fix-list')
    ap.add_argument('--dry-run', action='store_true',
                    help='print the exact message that would be posted; no network, no token needed')
    ap.add_argument('--token-file', help='path to a file holding the bot token')
    ap.add_argument('--no-doh', action='store_true',
                    help='do not resolve Discord over DNS-over-HTTPS (use the system resolver)')
    ap.add_argument('--allow-empty', action='store_true',
                    help='post even when the summary is empty (default: post nothing)')
    args = ap.parse_args()

    sources = [bool(args.message), bool(args.message_file), bool(args.summary_json)]
    if sum(sources) != 1:
        print('[FAIL] give exactly one of --message, --message-file, --summary-json.', file=sys.stderr)
        return 2

    if args.message:
        content = truncate(args.message, args.artifact_url)
    elif args.message_file:
        p = Path(args.message_file)
        if not p.is_file():
            print(f'[FAIL] no such message file: {p}', file=sys.stderr)
            return 2
        content = truncate(p.read_text(), args.artifact_url)
    else:
        p = Path(args.summary_json)
        if not p.is_file():
            print(f'[FAIL] no such summary JSON: {p}', file=sys.stderr)
            return 2
        try:
            summary = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            print(f'[FAIL] {p} is not valid JSON: {e}', file=sys.stderr)
            return 2
        if args.artifact_url:
            summary.setdefault('artifact_url', args.artifact_url)
        content = format_summary(summary)

    # Nothing new is the common case on a 15-minute cron. Say nothing.
    if not content.strip() and not args.allow_empty:
        print('[ok] nothing to report — posting nothing (this is the quiet path, not a failure).')
        return 0

    attach = None
    if args.attach:
        attach = Path(args.attach)
        if not attach.is_file():
            print(f'[FAIL] no such attachment: {attach}', file=sys.stderr)
            return 2

    if args.dry_run:
        print('─── DRY RUN: the message that would be posted ' + '─' * 24)
        print(content)
        print('─' * 68)
        print(f'[dry-run] {len(content)} chars (limit {MAX_MESSAGE})'
              + (f", attachment: {attach.name}" if attach else '')
              + f", channel: {args.channel or '<unset>'}")
        return 0

    if not args.channel:
        print('[FAIL] --channel is required to post (or use --dry-run).', file=sys.stderr)
        return 2

    if not args.no_doh:
        install_dns_override()

    token = resolve_token(args.token_file)   # exits 2 with an actionable message if absent
    return post_message(args.channel, token, content, attach)


if __name__ == '__main__':
    raise SystemExit(main())
