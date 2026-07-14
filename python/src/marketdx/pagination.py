"""Lazy auto-paginating result set.

``for s in mdx.news(...)`` transparently walks every page. ``.to_df()``
materializes the whole set into a pandas DataFrame (API-native columns);
``.to_list()`` / ``.first()`` / ``len(...)`` and ``.total`` are conveniences.
Nothing is fetched until you iterate (or read ``.total``).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

_PAGE_SIZE = 100  # per-request page while auto-paging


class Page:
    def __init__(
        self,
        get_page: Callable[[int, int], Any],  # (offset, limit) -> _http.Response
        key: str,                             # the data array key: results/stocks/…
        parse: Callable[[Dict[str, Any]], Any],
        *,
        columns: Optional[Sequence[str]] = None,
        max_items: Optional[int] = None,
        row_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._get_page = get_page
        self._key = key
        self._parse = parse
        self._columns = columns
        self._max = max_items
        self._row_kwargs = row_kwargs or {}
        self._total: Optional[int] = None

    def __iter__(self) -> Iterator[Any]:
        offset, seen = 0, 0
        # Honor the cap in the per-request page size — never fetch (or pay for) more than we'll
        # yield. `max_items` (the effective `limit`) None → walk the whole set in _PAGE_SIZE pages;
        # a small cap → a single right-sized request (this is what makes `limit=10` actually mean 10).
        page_size = min(self._max, _PAGE_SIZE) if self._max else _PAGE_SIZE
        while True:
            resp = self._get_page(offset, page_size)
            data = resp.data if isinstance(resp.data, dict) else {}
            if self._total is None:
                self._total = data.get("total")
            items = data.get(self._key) or []
            for it in items:
                if self._max is not None and seen >= self._max:
                    return
                seen += 1
                yield self._parse(it)
            # Stop BEFORE fetching another (metered) page once the cap is met — otherwise an exact
            # multiple of the page size (e.g. cap=100) would pay for one wasted extra request.
            if self._max is not None and seen >= self._max:
                return
            if not data.get("has_more") or not items:
                return
            offset += page_size

    def to_list(self) -> List[Any]:
        # Comprehension iterates via __iter__ only — deliberately NO __len__ on this
        # class: it's a lazy, network-backed cursor, so len() would either recurse or
        # silently double-fetch a metered API. Use `.total` (one cheap call) for a count.
        return [item for item in self]

    def first(self) -> Optional[Any]:
        return next(iter(self), None)

    @property
    def total(self) -> Optional[int]:
        """Full match count (ignoring paging). Triggers one fetch if not seen yet."""
        if self._total is None:
            resp = self._get_page(0, 1)
            self._total = (resp.data or {}).get("total") if isinstance(resp.data, dict) else None
        return self._total

    def to_df(self, **row_kwargs: Any):
        """Flatten every item (``.to_rows()``) into a pandas DataFrame."""
        try:
            import pandas as pd
        except ImportError as e:  # pragma: no cover
            raise ImportError("to_df() needs pandas — `pip install marketdx[pandas]`") from e
        kw = {**self._row_kwargs, **row_kwargs}
        rows: List[Dict[str, Any]] = []
        for item in self:
            to_rows = getattr(item, "to_rows", None)
            rows.extend(to_rows(**kw) if to_rows else [item])
        df = pd.DataFrame(rows)
        if self._columns and not df.empty:
            ordered = [c for c in self._columns if c in df.columns]
            extra = [c for c in df.columns if c not in ordered]
            df = df[ordered + extra]
        return df
