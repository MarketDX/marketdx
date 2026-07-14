"""Pagination cap behavior — the regression guard for the `limit` bug.

Pre-0.5.2 the public methods accepted `limit=` but dropped it: the Page always fetched a fixed
100-row page and the only real cap was `max_items`. These tests pin that (a) the requested per-page
size is right-sized to the cap, and (b) exactly `cap` items are yielded — offline, via a fake page
fetcher, so no key / network is needed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python" / "src"))

from marketdx.client import _cap                # noqa: E402
from marketdx.pagination import Page            # noqa: E402


class _Resp:
    def __init__(self, data): self.data = data


def _fake_source(total_rows: int, requested):
    """A get_page(offset, limit) that logs each requested limit and serves `total_rows` rows."""
    def get_page(offset: int, limit: int):
        requested.append(limit)
        rows = [{"i": i} for i in range(offset, min(offset + limit, total_rows))]
        return _Resp({"results": rows, "total": total_rows, "has_more": offset + limit < total_rows})
    return get_page


def _page(cap, total_rows, requested):
    return Page(_fake_source(total_rows, requested), "results", lambda d: d["i"], max_items=cap)


def test_small_cap_is_one_right_sized_request():
    req = []
    got = list(_page(10, total_rows=9999, requested=req))
    assert got == list(range(10))          # exactly 10 yielded (not 100, not everything)
    assert req == [10]                     # one request, sized to the cap — not a fixed 100


def test_large_cap_pages_at_100_and_stops_at_cap():
    req = []
    got = list(_page(250, total_rows=9999, requested=req))
    assert len(got) == 250
    assert req == [100, 100, 100]          # 3 pages of 100, capped at 250 items


def test_no_cap_walks_the_whole_set():
    req = []
    got = list(_page(None, total_rows=230, requested=req))
    assert len(got) == 230                 # everything (unbounded)
    assert req == [100, 100, 100]          # until has_more is false


def test_cap_precedence():
    assert _cap(50, None) == 50            # default limit, no max_items
    assert _cap(10, None) == 10            # explicit limit honored
    assert _cap(50, 200) == 200            # deprecated max_items wins when given
    assert _cap(None, None) is None        # limit=None → unbounded
