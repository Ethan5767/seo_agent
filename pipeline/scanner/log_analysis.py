"""Access-log ingestion and crawl-behaviour analysis.

The parser accepts common/combined Apache and Nginx lines plus one JSON object
per line (Cloudflare, Fastly, and CloudFront exports). DNS verification is
injectable so tests stay offline and production can cache reverse/forward
lookups without coupling the analysis to a particular DNS provider.
"""

from __future__ import annotations

import json
import re
import socket
from collections import Counter
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

_COMMON = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^]]+)\] "(?P<method>\S+) (?P<url>\S+) [^"]+" (?P<status>\d{3}) (?P<bytes>\S+)'
)
_BOT = re.compile(r"bot|spider|crawler|slurp|bingpreview|facebookexternalhit|petalbot", re.I)


@dataclass(frozen=True)
class AccessLogEntry:
    ip: str
    timestamp: str
    method: str
    url: str
    status: int
    user_agent: str
    bot_name: str | None = None
    verified_bot: bool = False


def _bot_name(user_agent: str) -> str | None:
    if not _BOT.search(user_agent or ""):
        return None
    ua = (user_agent or "").lower()
    for name in ("googlebot", "bingbot", "yandexbot", "duckduckbot", "baiduspider", "gptbot", "claudebot", "perplexitybot"):
        if name in ua:
            return name
    return "other-bot"


def _json_entry(obj: dict) -> AccessLogEntry | None:
    ip = str(obj.get("ClientIP") or obj.get("client_ip") or obj.get("clientIP") or obj.get("ip") or "")
    url = str(obj.get("ClientRequestURI") or obj.get("cs-uri-stem") or obj.get("url") or obj.get("request_uri") or "")
    ua = str(obj.get("UserAgent") or obj.get("user_agent") or obj.get("cs(User-Agent)") or "")
    status = obj.get("EdgeResponseStatus") or obj.get("sc-status") or obj.get("status")
    if not url or not ip or status is None:
        return None
    try:
        status = int(status)
    except (TypeError, ValueError):
        return None
    return AccessLogEntry(ip, str(obj.get("Datetime") or obj.get("timestamp") or obj.get("date") or ""),
                          str(obj.get("method") or obj.get("cs-method") or "GET"), url, status, ua, _bot_name(ua))


def parse_access_logs(text: str) -> list[AccessLogEntry]:
    """Parse newline-delimited JSON or common/combined web-server logs."""
    entries: list[AccessLogEntry] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("{"):
            try:
                entry = _json_entry(json.loads(line))
            except (json.JSONDecodeError, TypeError):
                entry = None
        else:
            m = _COMMON.match(line)
            if not m:
                continue
            rest = line[m.end():]
            quoted = re.findall(r'"([^"]*)"', rest)
            ua = quoted[-1] if quoted else ""
            entry = AccessLogEntry(m.group("ip"), m.group("ts"), m.group("method"), m.group("url"), int(m.group("status")), ua, _bot_name(ua))
        if entry:
            entries.append(entry)
    return entries


def verify_bot_ip(ip: str, reverse_lookup, forward_lookup) -> bool:
    """Return true only when reverse DNS and forward DNS confirm the IP."""
    try:
        names = reverse_lookup(ip) or []
        return any(ip in (forward_lookup(name) or []) for name in names)
    except (OSError, ValueError):
        return False


def _system_verify(ip: str, _bot_name: str) -> bool:
    """Use forward-confirmed reverse DNS for production log analysis."""
    try:
        names = socket.gethostbyaddr(ip)[1]
        return any(ip in {item[4][0] for item in socket.getaddrinfo(name, None)} for name in names)
    except (OSError, ValueError):
        return False


def analyze_logs(entries: list[AccessLogEntry], verify=None, crawl_urls: set[str] | None = None) -> list[dict]:
    """Summarize verified-bot crawling, waste, and directory budgets."""
    if not entries:
        return [{"code": "logs.no_entries", "what": "No access-log entries parsed", "severity": "info",
                 "why": "No bot-crawl conclusion can be drawn without readable access-log entries.",
                 "fix": "Upload a supported access-log export."}]
    verified: list[AccessLogEntry] = []
    for entry in entries:
        ok = bool(entry.bot_name) and bool((verify or _system_verify)(entry.ip, entry.bot_name))
        verified.append(AccessLogEntry(**{**entry.__dict__, "verified_bot": ok}))
    bots = [e for e in verified if e.verified_bot]
    rows: list[dict] = []
    by_bot = Counter(e.bot_name for e in bots)
    for bot, count in by_bot.most_common():
        rows.append({"code": "logs.crawl_frequency", "what": f"{bot} crawl frequency", "severity": "info",
                     "why": "Real bot frequency shows which crawlers consume crawl budget.", "fix": "Monitor changes and investigate unexpected spikes.",
                     "detail": f"{count} verified request(s)", "bot": bot})
    status_counts = Counter(e.status for e in bots)
    waste = [e for e in bots if e.status in {301, 302, 307, 308, 404, 410, 500, 502, 503} or bool(parse_qsl(urlsplit(e.url).query))]
    rows.append({"code": "logs.bot_response_codes", "what": "Bot response codes", "severity": "warn" if any(s >= 400 for s in status_counts) else "ok",
                 "why": "Bots receiving errors, redirects, or parameter variants spend crawl budget without indexable content.",
                 "fix": "Fix error responses and reduce redirect/parameter waste.", "detail": dict(status_counts)})
    rows.append({"code": "logs.crawl_waste", "what": "Bot crawl waste", "severity": "warn" if waste else "ok",
                 "why": "Redirects, errors, and parameter URLs consume crawl budget without adding indexable pages.",
                 "fix": "Remove wasted internal URLs, canonicalize useful variants, and constrain traps.", "detail": f"{len(waste)} of {len(bots)} verified requests"})
    directories = Counter((urlsplit(e.url).path.strip("/").split("/")[0] or "/") for e in bots)
    if directories:
        rows.append({"code": "logs.directory_budget", "what": "Bot crawl budget by directory", "severity": "info",
                     "why": "Directory-level volume identifies sections consuming disproportionate crawl budget.",
                     "fix": "Compare high-volume directories with their indexable page value.", "detail": dict(directories)})
    if crawl_urls is not None:
        hit = {e.url for e in bots}
        orphan_hits = sorted(hit - crawl_urls)
        if orphan_hits:
            rows.append({"code": "logs.orphan_urls", "what": "Bot-hit URLs outside the crawl graph", "severity": "warn",
                         "why": "Bots are requesting URLs our internal crawl could not reach.",
                         "fix": "Link valuable pages internally or remove/redirect unintended URLs.", "pages": orphan_hits[:100], "detail": f"{len(orphan_hits)} URL(s)"})
    return rows
