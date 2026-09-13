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

    # Freshness — a visible date/updated marker; fresh content ranks and gets
    # cited more, and its absence makes a page look stale to readers and AI.
    if _FRESH_RE.search(html or ""):
        rows.append(_row("Freshness", "ok", "A visible date / updated marker is present.", "passing"))
    else:
        rows.append(_row("Freshness", "info", "No visible published/updated date — readers and AI can't tell how current this is.",
                         "show a published or last-updated date"))

    # Scannable structure — bullet/numbered lists are easy for readers to skim
    # and for AI engines to lift as steps/points.
    if re.search(r"<(ul|ol)\b", low) and "<li" in low:
        rows.append(_row("Scannable structure", "ok", "Uses lists — scannable and easy for AI to extract as points/steps.", "passing"))
    else:
        rows.append(_row("Scannable structure", "info", "No lists — long prose is harder to skim and to lift as bullet points.",
                         "use bullet/numbered lists for steps, features or comparisons"))
    return rows


_FRESH_RE = re.compile(
    r"<time\b|datetime=|updated|last[\s-]?modified|\b20[12]\d[-/]\d{2}[-/]\d{2}\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+20[12]\d\b",
    re.IGNORECASE)
