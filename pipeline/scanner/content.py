"""Content / information-gain (ours — DataForSEO has no info-gain tool).

Google's Information Gain favours pages that add something over the SERP
consensus. Full parity means fetching the top-ranking pages and diffing — a
heavier follow-up. This MVP judges the on-page signals that correlate with info
gain: real depth, original data (stats/tables, not just prose), and topical
comprehensiveness. Pure (HTML in, rows out).
"""
from __future__ import annotations

import re

from pipeline.scanner.rows import make_row

_row = make_row("content")


def _text(html: str) -> str:
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r"<[^>]+>", " ", body)


def content_rows(html: str) -> list[dict]:
    low = (html or "").lower()
    words = len(_text(html).split())
    rows: list[dict] = []

    # Depth
    if words < 300:
        rows.append(_row("Content depth", "warn", f"Only ~{words} words — likely below the depth of top-ranking pages.",
                         "expand to genuinely cover the topic", detail=f"{words} words"))
    elif words < 800:
        rows.append(_row("Content depth", "info", f"~{words} words — moderate; top pages are often deeper.",
                         "consider expanding key sections", detail=f"{words} words"))
    else:
        rows.append(_row("Content depth", "ok", f"In-depth (~{words} words).", "passing", detail=f"{words} words"))

    # Original data (info-gain signal): tables / statistics vs plain prose
    has_table = "<table" in low
    text = _text(html)
    stats = len(re.findall(r"\b\d+(?:\.\d+)?\s?%|\$\s?\d|\b\d{2,}\b", text))
    if has_table or stats >= 5:
        rows.append(_row("Original data", "ok",
                         "Carries tables/statistics — a real information-gain signal AI and Google reward.",
                         "passing", detail="tables" if has_table else f"{stats} data points"))
    else:
        rows.append(_row("Original data", "warn",
                         "Mostly prose with little data — low information gain vs competitor pages.",
                         "add original stats, comparison tables or unique findings"))

    # Comprehensiveness
    h2 = len(re.findall(r"<h2\b", low))
    if h2 >= 3:
        rows.append(_row("Comprehensiveness", "ok", f"{h2} sections — covers the topic broadly.", "passing", detail=f"{h2} sections"))
    elif h2 == 0:
        rows.append(_row("Comprehensiveness", "warn", "No subheadings — likely narrow coverage of the topic.",
                         "break the topic into sections that answer related questions"))
    return rows
