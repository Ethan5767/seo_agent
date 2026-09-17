"""Live progress from inside a running tool, without threading a callback
through every provider signature.

`build_report` opens `reporting(sink)` around each tool; anything that tool
calls (a DataForSEO request, a crawl poll) reports with `emit(text, **detail)`.
A context variable, so concurrent scans on the threaded server never see each
other's sink.

Only facts go through here: a request started, answered in N ms at $X, a crawl
has crawled K of M pages. No estimated percentages.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable

Sink = Callable[[str, dict], None]

_sink: ContextVar[Sink | None] = ContextVar("scan_progress_sink", default=None)


def emit(text: str, **detail) -> None:
    fn = _sink.get()
    if fn is None:
        return
    try:
        fn(text, detail)
    except Exception:  # noqa: BLE001 - a broken UI stream must never fail a paid scan
        pass


@contextmanager
def reporting(sink: Sink | None):
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)
