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
        while True:
            resp = self._get_page(offset, _PAGE_SIZE)
            data = resp.data if isinstance(resp.data, dict) else {}
            if self._total is None:
                self._total = data.get("total")
            items = data.get(self._key) or []
            for it in items:
                if self._max is not None and seen >= self._max:
                    return
                seen += 1
                yield self._parse(it)
            if not data.get("has_more") or not items:
                return
            offset += _PAGE_SIZE

    def to_list(self) -> List[Any]:
        return list(self)

    def first(self) -> Optional[Any]:
        return next(iter(self), None)

    def __len__(self) -> int:
        return len(self.to_list())

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
