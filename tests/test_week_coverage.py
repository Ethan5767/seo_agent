"""week_coverage — the operator's 'detect what weeks are done' (2026-08-02).
Synthetic docx fixtures; grounded in the real conventions (Title-style
'🗓️/🟥 Week N' dividers; 2 of 7 real docs have no week structure at all)."""
import docx
import pytest

from pipeline.intake.week_coverage import analyze


def _doc(tmp_path, blocks):
    d = docx.Document()
    for style, text in blocks:
        p = d.add_paragraph(text)
        p.style = d.styles[style]
    f = tmp_path / "t.docx"
    d.save(str(f))
    return str(f)


def _page(n):
    body = [("Normal", f"Canonical URL: https://x.com/p{n}/")]
    body += [("Normal", ("real page copy " * 30))]
    return body


def test_full_month_all_done(tmp_path):
    blocks = []
    for wk in (1, 2, 3, 4):
        blocks.append(("Title", f"🟥 Week {wk}"))
        blocks += _page(wk)
    r = analyze(_doc(tmp_path, blocks), min_words=50)
    assert r["has_week_structure"]
    assert all(w["status"] == "DONE" for w in r["weeks"].values())


def test_missing_and_empty_weeks(tmp_path):
    blocks = [("Title", "🗓️ Week 1"), *_page(1),
              ("Title", "Week  2")]           # double-space variant, no content
    r = analyze(_doc(tmp_path, blocks), min_words=50)
    assert r["weeks"][1]["status"] == "DONE"
    assert r["weeks"][2]["status"] == "EMPTY"
    assert r["weeks"][3]["status"] == "MISSING"
    assert r["weeks"][4]["status"] == "MISSING"


def test_partial_week(tmp_path):
    blocks = [("Title", "Week 1"),
              ("Normal", "a thin stub of words that clears the empty floor " * 8)]  # 72w: >40 (not EMPTY), <300 (not DONE)
    r = analyze(_doc(tmp_path, blocks), min_words=300)
    assert r["weeks"][1]["status"] == "PARTIAL"


def test_no_week_structure_reports_honestly(tmp_path):
    r = analyze(_doc(tmp_path, _page(1) + _page(2)), min_words=50)
    assert not r["has_week_structure"]
    assert r["weeks"] == {}
    assert r["total_pages"] == 2


def test_prose_mentioning_week_is_not_a_divider(tmp_path):
    blocks = [("Normal", "we finished week 2 of the project last month"), *_page(1)]
    r = analyze(_doc(tmp_path, blocks), min_words=50)
    assert not r["has_week_structure"]
