"""Owned security/infrastructure heuristics for the technical audit."""

from __future__ import annotations

import re
from urllib.parse import urlsplit


def security_rows(url: str, html: str, headers: dict | None = None,
                  normal_html: str | None = None, crawler_html: str | None = None) -> list[dict]:
    headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    rows: list[dict] = []
    mixed = re.findall(r"(?:src|href|action)=[\"'](http://[^\"']+)", html or "", re.I)
    rows.append({"code": "security.mixed_content", "what": "Mixed content", "severity": "error" if mixed else "ok",
                 "why": "HTTP subresources on an HTTPS page can be blocked or tampered with by the network.",
                 "fix": "Serve every page resource over HTTPS.", "detail": f"{len(mixed)} insecure resource(s)", "pages": mixed[:100]})
    powered = headers.get("server", "") + " " + headers.get("x-powered-by", "")
    rows.append({"code": "security.server_disclosure", "what": "Server signature disclosure", "severity": "info" if powered else "ok",
                 "why": "Verbose server headers reveal implementation details useful to attackers.",
                 "fix": "Minimize unnecessary Server and X-Powered-By response detail.", "detail": powered or "not disclosed"})
    suspicious = re.findall(r"(?:pharmacy|casino|viagra|porn|malware|payday)\b", html or "", re.I)
    rows.append({"code": "security.injection_heuristic", "what": "Spam-injection heuristic", "severity": "warn" if suspicious else "ok",
                 "why": "Unexpected pharmaceutical, gambling, or malware terms can indicate defacement or injected content.",
                 "fix": "Review unexpected terms and outbound scripts against the known site baseline.", "detail": f"{len(suspicious)} suspicious term(s)"})
    if normal_html is not None and crawler_html is not None:
        same = re.sub(r"\s+", " ", normal_html).strip() == re.sub(r"\s+", " ", crawler_html).strip()
        rows.append({"code": "security.cloaking", "what": "Crawler-vs-normal response", "severity": "ok" if same else "error",
                     "why": "Materially different content for crawlers and users can be cloaking or an accidental bot-serving bug.",
                     "fix": "Serve the same indexable content to normal and Googlebot-like requests.", "detail": "responses agree" if same else "responses differ", "confidence": "high"})
    return rows
