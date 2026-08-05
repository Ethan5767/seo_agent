#!/usr/bin/env python3
"""Discord intake — pull the SEO team's content drops out of Discord.

Polls channels over the REST API on a schedule (cron-friendly). No gateway,
no websocket daemon, no privileged Message Content intent required: a bot with
View Channel + Read Message History gets full message objects (content +
attachments) from GET /channels/{id}/messages.

Auth (never hardcoded, never in the repo):
  1. DISCORD_BOT_TOKEN environment variable, else
  2. ~/.meridian/discord-bot.token  (single line, chmod 600)

Routing — a drop is filed under a client slug resolved in this order:
  1. explicit channel -> slug mapping (--channel ID:slug, or --config yaml)
  2. a known slug (or its alias) found in the filename or message text
  3. 'unrouted/' for manual triage — it NEVER guesses a client silently,
     because filing a client's content against the wrong repo is worse than
     filing it nowhere.

State: <dest>/.discord-intake-state.json records the last seen message id per
channel, so re-running never re-downloads the same drop.

Usage:
  discord_intake.py --check-auth
  discord_intake.py --list-channels --guild GUILD_ID
  discord_intake.py --poll --channel 123456:acme-roofing --dest ./intake
  discord_intake.py --poll --config ~/.meridian/discord-intake.yml

Exit: 0 ok (including "nothing new") · 2 auth/config problem · 1 fetch failure
"""
import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

API = "https://discord.com/api/v10"
UA = "SEOContentPipeline/1.0 (intake poller)"
# Content the team actually hands off. Anything else is logged, not downloaded.
CONTENT_EXT = {".docx", ".doc", ".pdf", ".md", ".txt", ".csv", ".xlsx", ".zip"}
DRIVE_RE = re.compile(r"https://(?:docs|drive)\.google\.com/[^\s>)\]]+")

# Hosts the poller talks to. Some ISPs return a bogus A record for discord.com
# (observed 2026-07: an ISP resolver answering 203.190.164.182, which blackholes),
# which makes every request time out for reasons that look nothing like DNS.
DISCORD_HOSTS = ("discord.com", "cdn.discordapp.com", "media.discordapp.net")
DOH_URL = "https://1.1.1.1/dns-query?name={}&type=A"  # IP-direct: needs no DNS itself


# ── DNS ───────────────────────────────────────────────────────────────────────
def _doh_resolve(host: str, timeout: int = 10) -> str | None:
    """Resolve a hostname over DNS-over-HTTPS (Cloudflare), bypassing a local
    resolver that returns wrong answers."""
    req = urllib.request.Request(DOH_URL.format(host), headers={
        "Accept": "application/dns-json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    for ans in data.get("Answer", []) or []:
        if ans.get("type") == 1:  # A record
            return ans.get("data")
    return None


def install_dns_override(verbose: bool = True) -> dict:
    """Pin Discord hostnames to DoH-resolved IPs inside getaddrinfo.

    This changes only WHICH resolver we trust. The connection still uses the real
    hostname for TLS SNI and certificate validation, so nothing about transport
    security is weakened — an impostor IP would fail the cert check.
    Returns {host: ip} for whatever it pinned (empty dict = left system DNS alone).
    """
    mapping = {}
    for h in DISCORD_HOSTS:
        try:
            ip = _doh_resolve(h)
            if ip:
                mapping[h] = ip
        except Exception:
            pass
    if not mapping:
        if verbose:
            print("[dns] DoH unavailable — using system DNS", file=sys.stderr)
        return {}

    _orig = socket.getaddrinfo

    def patched(host, port, *a, **kw):
        return _orig(mapping.get(host, host), port, *a, **kw)

    socket.getaddrinfo = patched
    if verbose:
        pinned = ", ".join(f"{h}={ip}" for h, ip in mapping.items())
        print(f"[dns] resolved over DoH: {pinned}", file=sys.stderr)
    return mapping


# ── auth ──────────────────────────────────────────────────────────────────────
def resolve_token(explicit_path: str | None = None) -> str:
    if os.environ.get("DISCORD_BOT_TOKEN"):
        return os.environ["DISCORD_BOT_TOKEN"].strip()
    candidates = [Path(explicit_path)] if explicit_path else []
    candidates.append(Path.home() / ".meridian" / "discord-bot.token")
    for p in candidates:
        if p.is_file():
            tok = p.read_text().strip()
            if tok:
                return tok
    print(
        "[FAIL] No Discord bot token found.\n"
        "  Set DISCORD_BOT_TOKEN, or write the token to ~/.meridian/discord-bot.token:\n"
        "    mkdir -p ~/.meridian && printf '%s' 'YOUR_TOKEN' > ~/.meridian/discord-bot.token\n"
        "    chmod 600 ~/.meridian/discord-bot.token\n"
        "  (never commit it, never paste it into chat)",
        file=sys.stderr,
    )
    sys.exit(2)


class ChannelAccessError(Exception):
    """A 403/404 on ONE channel — recoverable: skip it, keep polling the rest."""
    def __init__(self, code: int, path: str):
        self.code, self.path = code, path
        super().__init__(f"HTTP {code} on {path}")


def api_get(path: str, token: str, params: dict | None = None, retries: int = 3,
            soft_channel_errors: bool = False):
    """GET the Discord REST API, honouring 429 rate limits.

    With soft_channel_errors=True, a 403/404 raises ChannelAccessError instead of
    exiting, so a caller polling many channels can skip an inaccessible one
    (e.g. a channel whose own permission overrides deny the bot despite a
    category grant) and continue with the others."""
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bot {token}",
        "User-Agent": UA,
        "Accept": "application/json",
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            if e.code == 429 and attempt < retries - 1:
                wait = 5.0
                try:
                    wait = float(json.loads(body).get("retry_after", 5.0))
                except Exception:
                    pass
                time.sleep(min(wait + 0.5, 30))
                continue
            if e.code == 401:
                print("[FAIL] 401 Unauthorized — the bot token is wrong or was reset.", file=sys.stderr)
                sys.exit(2)
            if e.code in (403, 404):
                if soft_channel_errors:
                    raise ChannelAccessError(e.code, path)
                if e.code == 403:
                    print(f"[FAIL] 403 Forbidden on {path} — the bot is not in the server, or lacks "
                          "View Channel / Read Message History on that channel.", file=sys.stderr)
                else:
                    print(f"[FAIL] 404 on {path} — wrong channel/guild id, or the bot cannot see it.", file=sys.stderr)
                sys.exit(2)
            print(f"[FAIL] HTTP {e.code} on {path}: {body}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            print(f"[FAIL] network error on {path}: {e}", file=sys.stderr)
            sys.exit(1)
    return None


# ── routing ───────────────────────────────────────────────────────────────────
def _match_slug(hay: str, candidates: list) -> str | None:
    """Match a slug, or a distinctive word of one, inside filename + message text."""
    for slug in candidates:
        if slug.lower() in hay:
            return slug
        # match any distinctive word of the slug (acme-roofing -> "acme")
        for part in re.split(r"[-_]", slug):
            if len(part) >= 5 and part.lower() in hay:
                return slug
    return None


def route(filename: str, text: str, channel_id: str, mapping: dict, slugs: list) -> str:
    """Resolve a client slug for one dropped file.

    A channel may serve ONE client or SEVERAL. Pat's `#blueline_mechanical` is
    the shared drop point for both the North and South division sites, and there
    is no reason to split it — Drive is what separates the divisions, by folder.
    So a shared channel must never resolve to a single default client: mapping it
    to one slug would file every North drop as South, silently. (BUG-013)

    Multi-client form in config:

        "<channel id>":
          slugs: [blueline-hvac, blueline-hvac-north]
          hints:
            blueline-hvac-north: [north, bluelinemech, "blh north"]
            blueline-hvac:       [south, florida, "Blueline industries"]

    Longest matching hint wins. A tie between two clients returns 'unrouted'
    rather than picking one — mis-attributing a cycle to the wrong division is
    far worse than asking a human to look.
    """
    m = mapping.get(channel_id)
    hay = f"{filename} {text}".lower()

    if isinstance(m, dict):
        cands = m.get("slugs") or []
        hints = m.get("hints") or {}
        scored = []
        for s in cands:
            best = max((len(k) for k in hints.get(s, []) if k.lower() in hay), default=0)
            if best:
                scored.append((best, s))
        if scored:
            scored.sort(key=lambda t: -t[0])
            if len(scored) > 1 and scored[0][0] == scored[1][0]:
                return "unrouted"  # ambiguous between two clients — never guess
            return scored[0][1]
        return _match_slug(hay, cands) or "unrouted"

    if m:  # a mapped-but-empty slug must fall through, not file to ""
        return m
    return _match_slug(hay, slugs) or "unrouted"


# ── state ─────────────────────────────────────────────────────────────────────
def load_state(dest: Path) -> dict:
    f = dest / ".discord-intake-state.json"
    if f.is_file():
        try:
            return json.loads(f.read_text())
        except Exception:
            return {}
    return {}


def save_state(dest: Path, state: dict) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / ".discord-intake-state.json").write_text(json.dumps(state, indent=2))


# ── download ──────────────────────────────────────────────────────────────────
def download(url: str, target: Path) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return len(data)


# ── commands ──────────────────────────────────────────────────────────────────
def cmd_check_auth(token: str) -> int:
    me = api_get("/users/@me", token)
    print(f"[OK] authenticated as bot: {me.get('username')}#{me.get('discriminator','0')} (id {me.get('id')})")
    guilds = api_get("/users/@me/guilds", token) or []
    if not guilds:
        print("[WARN] the bot is not in ANY server yet — invite it with the OAuth2 URL "
              "(scope=bot, permissions=66560: View Channels + Read Message History).")
    for g in guilds:
        print(f"  server: {g.get('name')}  (guild id {g.get('id')})")
    return 0


def cmd_list_channels(token: str, guild: str) -> int:
    chans = api_get(f"/guilds/{guild}/channels", token) or []
    text_like = [c for c in chans if c.get("type") in (0, 5, 15)]  # text, announcement, forum
    if not text_like:
        print("[WARN] no readable text channels returned — check the bot's role/permissions.")
    for c in sorted(text_like, key=lambda c: (c.get("position", 0))):
        print(f"  {c['id']}  #{c.get('name')}   (type {c.get('type')})")
    print("\nMap them with:  --channel <channel_id>:<client_slug>")
    return 0


def cmd_poll(token: str, channels: dict, slugs: list, dest: Path, reset: bool, limit: int) -> int:
    state = {} if reset else load_state(dest)
    total_files, total_msgs, drive_links = 0, 0, []
    denied = []

    for chan_id, chan_cfg in channels.items():
        slug_hint = ("+".join(chan_cfg.get("slugs") or []) if isinstance(chan_cfg, dict)
                     else chan_cfg)
        params = {"limit": min(limit, 100)}
        last = state.get(chan_id)
        if last:
            params["after"] = last  # only messages newer than the last seen
        try:
            msgs = api_get(f"/channels/{chan_id}/messages", token, params,
                           soft_channel_errors=True) or []
        except ChannelAccessError as e:
            denied.append((chan_id, slug_hint))
            print(f"[skip] #{chan_id} ({slug_hint or 'unmapped'}): HTTP {e.code} — the bot can't read "
                  "this channel. A channel's OWN permission overrides beat the category grant, so grant "
                  "the bot View Channel + Read Message History on THIS channel specifically.", file=sys.stderr)
            continue
        msgs = list(reversed(msgs))  # API returns newest-first; process oldest-first
        if not msgs:
            print(f"[ok] #{chan_id}: nothing new")
            continue

        for m in msgs:
            total_msgs += 1
            body = m.get("content", "") or ""
            author = (m.get("author") or {}).get("username", "?")
            for link in DRIVE_RE.findall(body):
                drive_links.append((chan_id, m.get("id"), link))
            for att in m.get("attachments", []) or []:
                name = att.get("filename", "unnamed")
                ext = Path(name).suffix.lower()
                if ext not in CONTENT_EXT:
                    print(f"  [skip] {name} (not a content file)")
                    continue
                client = route(name, body, chan_id, channels, slugs)
                target = dest / client / date.today().isoformat() / name
                if target.exists():
                    print(f"  [dupe] {client}/{name} already on disk")
                    continue
                try:
                    size = download(att["url"], target)
                except Exception as e:
                    print(f"  [FAIL] could not download {name}: {e}", file=sys.stderr)
                    continue
                total_files += 1
                flag = "  <-- UNROUTED, triage manually" if client == "unrouted" else ""
                print(f"  [got] {client}/{target.parent.name}/{name}  ({size/1024:.0f} KB, from {author}){flag}")
            state[chan_id] = m.get("id")

    save_state(dest, state)
    if drive_links:
        print(f"\n[drive] {len(drive_links)} Google Drive link(s) posted — fetch via the Drive intake path:")
        for _, _, link in drive_links[:10]:
            print(f"  {link}")
    print(f"\n[done] {total_msgs} new message(s), {total_files} file(s) saved under {dest}")
    if denied:
        names = ", ".join(f"#{c} ({s or 'unmapped'})" for c, s in denied)
        print(f"::warning::{len(denied)} channel(s) not readable, skipped: {names}. "
              "Grant the bot View Channel + Read Message History on each.", file=sys.stderr)
    if total_files and any((dest / "unrouted").glob("**/*")):
        print("[WARN] some drops landed in unrouted/ — add a --channel mapping or a client slug "
              "in the filename so routing is deterministic.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Pull SEO content drops from Discord.")
    ap.add_argument("--check-auth", action="store_true", help="verify the token + list servers the bot is in")
    ap.add_argument("--list-channels", action="store_true", help="list readable channels (needs --guild)")
    ap.add_argument("--guild", help="guild (server) id, for --list-channels")
    ap.add_argument("--poll", action="store_true", help="download new content drops")
    ap.add_argument("--channel", action="append", default=[],
                    help="channel to poll, as ID or ID:client_slug (repeatable)")
    ap.add_argument("--config", help="yaml with discord.channels {id: slug} and discord.slugs []")
    ap.add_argument("--slugs", default="", help="comma-separated known client slugs for filename routing")
    ap.add_argument("--dest", default="./intake", help="intake tree root (default ./intake)")
    ap.add_argument("--token-file", help="path to a file holding the bot token")
    ap.add_argument("--limit", type=int, default=100, help="max messages per channel per run")
    ap.add_argument("--since-reset", action="store_true", help="ignore saved state and re-scan the window")
    ap.add_argument("--no-doh", action="store_true",
                    help="do not resolve Discord over DNS-over-HTTPS (use the system resolver)")
    args = ap.parse_args()

    # Resolve Discord over DoH by default — a hijacked local resolver otherwise
    # presents as an unexplained connection timeout.
    if not args.no_doh:
        install_dns_override()

    channels: dict = {}
    slugs = [s.strip() for s in args.slugs.split(",") if s.strip()]

    if args.config:
        try:
            import yaml  # optional; only needed for --config
        except ImportError:
            print("[FAIL] --config needs PyYAML (pip install pyyaml)", file=sys.stderr)
            return 2
        cfg = yaml.safe_load(Path(args.config).expanduser().read_text()) or {}
        d = cfg.get("discord", {}) or {}
        for k, v in (d.get("channels") or {}).items():
            if isinstance(v, dict):
                # Multi-client channel: candidate slugs + disambiguation hints.
                channels[str(k)] = {
                    "slugs": [str(s) for s in (v.get("slugs") or [])],
                    "hints": {str(sk): [str(x) for x in (sv or [])]
                              for sk, sv in (v.get("hints") or {}).items()},
                }
            else:
                channels[str(k)] = str(v)
        slugs += [str(s) for s in (d.get("slugs") or [])]

    for spec in args.channel:
        cid, _, slug = spec.partition(":")
        channels[cid.strip()] = slug.strip() or ""
    # a mapped slug is itself a known slug for filename routing
    for v in channels.values():
        if isinstance(v, dict):
            slugs += [s for s in v.get("slugs") or [] if s]
        elif v:
            slugs.append(v)
    slugs = sorted({s for s in slugs if s})
    channels = {k: v for k, v in channels.items() if k}

    token = resolve_token(args.token_file)

    if args.check_auth:
        return cmd_check_auth(token)
    if args.list_channels:
        if not args.guild:
            print("[FAIL] --list-channels needs --guild GUILD_ID (run --check-auth to find it)", file=sys.stderr)
            return 2
        return cmd_list_channels(token, args.guild)
    if args.poll:
        if not channels:
            print("[FAIL] no channels given. Use --channel ID:client_slug (repeatable) or --config.", file=sys.stderr)
            return 2
        return cmd_poll(token, channels, slugs, Path(args.dest).expanduser(), args.since_reset, args.limit)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
