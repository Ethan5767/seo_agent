"""Keyword clustering — a site plan from keywords the scan already bought.

The big suites call this a Keyword Strategy Builder: take a flat keyword list and
group it into the pages a site should have, so a plan comes out rather than a
spreadsheet. This is the same idea over rows the scan has already paid for.

Deliberately NOT semantic clustering. No embeddings, no model call, no network:
grouping is by shared head term, which is crude, explainable and free. A cluster
you can read the rule for is one an operator can argue with; an embedding
cluster is one they have to trust. If this proves useful, the upgrade path is to
swap the grouping function and keep the shape.

`plan_clusters` is pure: keyword rows in, clusters out, no clock and no I/O.
"""
from __future__ import annotations

import re
from collections import defaultdict

#: Words that carry no topical signal, so they must not become a cluster head.
#: Deliberately short: an aggressive list starts eating real terms like "near me"
#: or "best", which are exactly the intent markers a plan wants to keep.
STOP = {
    "a", "an", "and", "the", "for", "to", "of", "in", "on", "at", "by", "with",
    "is", "are", "was", "how", "what", "why", "when", "where", "which", "who",
    "do", "does", "can", "you", "your", "my", "me", "i", "it", "its",
}

#: A cluster needs at least this many keywords to earn a page of its own.
#: Below it, the term belongs in a section of a broader page, not a new URL.
MIN_CLUSTER = 2

#: Guardrail on the head-term vocabulary, so one enormous cluster does not
#: swallow a whole keyword set.
MAX_CLUSTERS = 40


def _terms(keyword: str) -> list[str]:
    """Content words in a keyword, lowercased, order preserved."""
    words = re.findall(r"[a-z0-9']+", (keyword or "").lower())
    return [w for w in words if w not in STOP and len(w) > 2]


def _volume(row: dict) -> int:
    """Search volume off a keyword row, from the figure the parsers put in
    `detail` (e.g. "1,300/mo"). Zero when absent: a keyword with no volume is
    still a keyword, and dropping it would silently shrink the plan."""
    m = re.search(r"([\d,]+)", str(row.get("detail") or ""))
    if not m:
        return 0
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return 0


def _keyword_of(row: dict) -> str:
    """The keyword a row is about. The parsers put it in `what`, sometimes with
    a trailing qualifier the UI renders, so the leading phrase is what counts."""
    what = str(row.get("what") or "").strip()
    return what.split(" — ")[0].split(":")[0].strip()


def plan_clusters(rows: list[dict], min_cluster: int = MIN_CLUSTER,
                  max_clusters: int = MAX_CLUSTERS) -> list[dict]:
    """Group keyword rows into candidate pages, biggest opportunity first.

    Returns one dict per cluster: `head` (the shared term), `keywords` (the
    members, by volume), `volume` (their total), `size`, and `intent` when every
    member agrees on one. Keywords that share no head term with anything land in
    a final `"unclustered"` group rather than being dropped - a plan that
    silently loses half its input is worse than one that shows the remainder.
    """
    by_kw: dict[str, dict] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        kw = _keyword_of(r)
        if kw and kw not in by_kw:
            by_kw[kw] = r
    if not by_kw:
        return []

    # Candidate heads are PHRASES first, single words second.
    #
    # Frequency alone picks the broadest term, and the broadest term claims
    # everything: on a roofing keyword set, "roof" swallowed "roof repair" and
    # "metal roof" into one cluster of five, which is not a plan - it is the
    # original list with a label. Two-word heads run first so the specific
    # cluster forms before the general one can absorb it, and single words then
    # pick up whatever is left.
    freq: dict[str, set[str]] = defaultdict(set)
    for kw in by_kw:
        terms = _terms(kw)
        for a, b in zip(terms, terms[1:]):
            freq[f"{a} {b}"].add(kw)
        for t in terms:
            freq[t].add(kw)

    def _rank(t: str) -> tuple:
        # More words first (specific before general), then frequency, then the
        # term itself so the output is stable rather than dict-ordered.
        return (-t.count(" "), -len(freq[t]), t)

    heads = sorted(freq, key=_rank)[:max_clusters]

    clusters: list[dict] = []
    claimed: set[str] = set()
    for head in heads:
        members = sorted(freq[head] - claimed,
                         key=lambda k: (-_volume(by_kw[k]), k))
        if len(members) < min_cluster:
            continue
        claimed.update(members)
        intents = {str(by_kw[m].get("fix") or "").strip().lower() for m in members}
        clusters.append({
            "head": head,
            "size": len(members),
            "volume": sum(_volume(by_kw[m]) for m in members),
            "keywords": members,
            "intent": intents.pop() if len(intents) == 1 else "",
        })

    clusters.sort(key=lambda c: (-c["volume"], -c["size"], c["head"]))

    leftover = sorted(set(by_kw) - claimed, key=lambda k: (-_volume(by_kw[k]), k))
    if leftover:
        clusters.append({
            "head": "unclustered",
            "size": len(leftover),
            "volume": sum(_volume(by_kw[k]) for k in leftover),
            "keywords": leftover,
            "intent": "",
        })
    return clusters


def cluster_rows(rows: list[dict]) -> list[dict]:
    """Clusters as report rows, so a plan reaches a screen like any finding.

    Severity is `info` throughout: a cluster is an opportunity, not a defect, and
    grading it would put "you have not written this page yet" in the same bucket
    as a broken canonical.
    """
    out: list[dict] = []
    for c in plan_clusters(rows):
        if c["head"] == "unclustered":
            out.append({
                "code": "cluster.unclustered",
                "what": f"{c['size']} keyword(s) share no theme",
                "why": "These did not group with anything else, so each is either a"
                       " one-off or a theme with only one term measured so far.",
                "fix": "review them individually; do not build a page per keyword",
                "severity": "info",
                "detail": f"{c['volume']:,}/mo" if c["volume"] else "",
                "pages": c["keywords"][:25],
            })
            continue
        out.append({
            "code": f"cluster.{c['head']}",
            "what": f"\"{c['head']}\" — {c['size']} keyword(s)",
            "why": f"{c['size']} measured keywords share this term"
                   + (f", worth about {c['volume']:,} searches a month" if c["volume"] else "")
                   + ". A cluster this size usually wants one page covering all of it"
                     " rather than a page per keyword, which competes with itself.",
            "fix": "write or extend one page to cover the whole cluster",
            "severity": "info",
            "detail": f"{c['volume']:,}/mo" if c["volume"] else f"{c['size']} keywords",
            "pages": c["keywords"][:25],
        })
    return out
