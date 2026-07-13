"""The MarketDX client — the financial impact graph in a few lines."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from . import enums
from ._http import Transport
from .models import (
    Company,
    MegatrendNode,
    MemberStock,
    Signal,
    StockNews,
    SIGNAL_COLUMNS,
    STOCK_NEWS_COLUMNS,
)
from .pagination import Page
from .taxonomy import Taxonomy

DEFAULT_BASE_URL = "https://api.marketdx.lab.ai"

NodeRef = Union[int, str, None]  # id | slug | name


class MarketDX:
    """Client for the MarketDX Data API.

    ```python
    from marketdx import MarketDX
    mdx = MarketDX(api_key="avn_live_…")
    for s in mdx.news(megatrend="ai-power", impact="indirect"):
        print(s.title, [(e.name, e.impact.net_direction) for e in s.entities])
    ```
    """

    def __init__(self, api_key: str, *, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("api_key is required — get one at https://marketdx.lab.ai")
        self._http = Transport(base_url, api_key, timeout=timeout)
        self._taxonomy = Taxonomy(lambda: self._get("/v1/megatrends").data.get("nodes", []))

    # ── low level ─────────────────────────────────────────────────────────────
    def _get(self, path: str, params: Optional[Dict[str, Any]] = None):
        return self._http.get(path, params)

    def _resolve(self, value: NodeRef) -> Optional[int]:
        return self._taxonomy.resolve(value)

    # ── Group A — news feed ───────────────────────────────────────────────────
    def news(
        self,
        *,
        megatrend: NodeRef = None,
        gics: Optional[str] = None,
        include: str = "entities,impact",
        impact: Optional[enums.ImpactType] = None,
        direction: Optional[enums.Direction] = None,
        aspect: Optional[Union[enums.Aspect, str]] = None,
        news_type: Optional[Union[str, List[str]]] = None,
        country: Optional[str] = None,
        lang: Optional[str] = None,
        order_by: Optional[str] = None,
        since: Optional[str] = None,
        from_: Optional[str] = None,
        to: Optional[str] = None,
        limit: int = 50,
        max_items: Optional[int] = None,
    ) -> "Page":
        """News signals, one :class:`~marketdx.models.Signal` per event. Auto-paginated."""
        params = {
            "megatrend": self._resolve(megatrend), "gics": gics, "include": include,
            "impact": impact, "direction": direction, "aspect": aspect, "news_type": news_type,
            "country": country, "lang": lang, "order_by": order_by, "since": since,
            "from": from_, "to": to,
        }
        return self._page("/v1/news", "results", Signal.from_dict, params,
                          columns=SIGNAL_COLUMNS, max_items=max_items)

    def news_search(self, q: str, *, entity_type: Optional[enums.EntityType] = None,
                    limit: int = 20, lang: Optional[str] = None,
                    include: str = "entities,impact", max_items: Optional[int] = None) -> "Page":
        """Semantic (vector) search — news matched by MEANING. Relevance-ranked top-K.

        Unlike the ``news()`` feed, search supports an ``entity_type`` filter (keeps only
        articles with a related entity of that type — stock/forex/crypto/commodity/private/
        public_off_coverage), applied server-side.
        """
        return self._page("/v1/news/search", "results", Signal.from_dict,
                          {"q": q, "lang": lang, "include": include, "entity_type": entity_type},
                          columns=SIGNAL_COLUMNS, max_items=max_items)

    def news_by_tickers(self, ticker: Union[str, List[str]], *, direction: Optional[enums.Direction] = None,
                        aspect: Optional[Union[enums.Aspect, str]] = None,
                        impact: Optional[enums.ImpactType] = None, include: str = "entities,impact",
                        lang: Optional[str] = None, limit: int = 50, max_items: Optional[int] = None) -> "Page":
        """News for one or more tickers — the article + that ticker's **direct AND indirect**
        impact. Use this to query by a specific ticker (incl. commodities like ``GOLD.COMM``),
        which the ``news()`` feed does not filter by. ``ticker`` accepts ``NVDA.US`` or a list."""
        return self._page("/v1/news/by-tickers", "results", Signal.from_dict,
                          {"ticker": ticker, "direction": direction, "aspect": aspect,
                           "impact": impact, "include": include, "lang": lang},
                          columns=SIGNAL_COLUMNS, max_items=max_items)

    def news_types(self) -> List[Dict[str, Any]]:
        """The controlled news-type vocabulary (18 types)."""
        return self._get("/v1/news/types").data.get("types", [])

    # ── Group B — by trend / sector ───────────────────────────────────────────
    def megatrends(self, id: NodeRef = None) -> Union["MegatrendRef", "Page"]:
        """No arg → the trend tree (``Page`` of nodes). With an id/slug/name → a
        :class:`MegatrendRef` you can call ``.stocks()`` / ``.off_coverage()`` on."""
        if id is None:
            return self._page("/v1/megatrends", "nodes", MegatrendNode.from_dict, {})
        return MegatrendRef(self, self._resolve(id))

    def gics(self, code: Optional[str] = None) -> Union["GicsRef", "Page"]:
        """No arg → the GICS list. With a code → a :class:`GicsRef` (``.stocks()``)."""
        if code is None:
            return self._page("/v1/gics", "gics", MegatrendNode.from_dict, {})
        return GicsRef(self, code)

    # ── Group C — by stock ────────────────────────────────────────────────────
    def stocks(self, *, q: Optional[str] = None, megatrend: NodeRef = None,
               aspect: Optional[Union[enums.Aspect, str]] = None, direction: Optional[enums.Direction] = None,
               country: Optional[str] = None, gate: Optional[str] = None, order_by: Optional[str] = None,
               since: Optional[str] = None, limit: int = 50, max_items: Optional[int] = None) -> "Page":
        """``q=`` → identity search; otherwise → the news-driven impact screener."""
        params = {"q": q, "megatrend": self._resolve(megatrend), "aspect": aspect,
                  "direction": direction, "country": country, "gate": gate,
                  "order_by": order_by, "since": since}
        return self._page("/v1/stocks", "stocks", MemberStock.from_dict, params, max_items=max_items)

    def stock(self, ticker: str) -> "StockRef":
        """A per-stock handle: ``.news()`` / ``.competitors()`` / ``.peers()``."""
        return StockRef(self, ticker)

    # ── reference ─────────────────────────────────────────────────────────────
    def enums(self) -> Dict[str, Any]:
        """The live controlled vocabularies — the runtime source of truth (free, unmetered)."""
        return self._get("/v1/enums").data

    def account(self) -> Dict[str, Any]:
        """Your account status: balance, quota + reset, plan, rate limit (free, unmetered)."""
        return self._get("/v1/account").data

    # ── helpers / lifecycle ───────────────────────────────────────────────────
    def _page(self, path, key, parse, params, *, columns=None, max_items=None) -> "Page":
        return Page(lambda offset, lim: self._get(path, {**params, "limit": lim, "offset": offset}),
                    key, parse, columns=columns, max_items=max_items)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "MarketDX":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class MegatrendRef:
    """A bound megatrend node — its members (listed + off-coverage)."""

    def __init__(self, client: MarketDX, node_id: Optional[int]) -> None:
        self._c = client
        self.node_id = node_id

    def get(self) -> MegatrendNode:
        return MegatrendNode.from_dict(self._c._get(f"/v1/megatrends/{self.node_id}").data)

    def stocks(self, *, country: str, exposure: Optional[enums.Exposure] = None,
               exchange: Optional[str] = None, domicile: Optional[str] = None,
               rollup: bool = True, max_items: Optional[int] = None) -> "Page":
        """Listed member companies (FX-normalized cap, geo-filtered). ``country`` is required."""
        params = {"country": country, "exposure": exposure, "exchange": exchange,
                  "domicile": domicile, "rollup": rollup}
        return self._c._page(f"/v1/megatrends/{self.node_id}/stocks", "stocks",
                            MemberStock.from_dict, params, max_items=max_items)

    def off_coverage(self, *, kind: Optional[str] = None, country: Optional[str] = None,
                     exposure: Optional[enums.Exposure] = None, include_flagged: bool = False,
                     rollup: bool = True, max_items: Optional[int] = None) -> "Page":
        """Private / public-out-of-coverage members — the "beyond tickers" roster.

        Strict by default (only critic-clean mappings); ``include_flagged=True`` for the rest.
        """
        params = {"kind": kind, "country": country, "exposure": exposure,
                  "include_flagged": include_flagged, "rollup": rollup}
        return self._c._page(f"/v1/megatrends/{self.node_id}/off-coverage", "companies",
                            Company.from_dict, params, max_items=max_items)


class GicsRef:
    def __init__(self, client: MarketDX, code: str) -> None:
        self._c = client
        self.code = code

    def stocks(self, *, country: str, exposure: Optional[enums.Exposure] = None,
               rollup: bool = True, max_items: Optional[int] = None) -> "Page":
        params = {"country": country, "exposure": exposure, "rollup": rollup}
        return self._c._page(f"/v1/gics/{self.code}/stocks", "stocks",
                            MemberStock.from_dict, params, max_items=max_items)


class StockRef:
    def __init__(self, client: MarketDX, ticker: str) -> None:
        self._c = client
        self.ticker = ticker

    def news(self, *, direction: Optional[enums.Direction] = None,
             aspect: Optional[Union[enums.Aspect, str]] = None, order_by: Optional[str] = None,
             since: Optional[str] = None, limit: int = 50, max_items: Optional[int] = None) -> "Page":
        """This stock's OWN impact timeline (:class:`~marketdx.models.StockNews`): each article
        + the stock's per-article ``impact`` (net_direction + aspects), ``trend``, and
        ``relevance``. No ``entities[]`` — the stock is the subject; use ``mdx.news()`` for the
        full entity graph of an article."""
        params = {"direction": direction, "aspect": aspect, "order_by": order_by, "since": since}
        return self._c._page(f"/v1/stocks/{self.ticker}/news", "results", StockNews.from_dict,
                            params, columns=STOCK_NEWS_COLUMNS, max_items=max_items)

    def competitors(self, *, max_items: Optional[int] = None) -> "Page":
        """Rivals derived from competition co-occurrence."""
        return self._c._page(f"/v1/stocks/{self.ticker}/competitors", "competitors",
                            MemberStock.from_dict, {}, max_items=max_items)

    def peers(self, *, max_items: Optional[int] = None) -> "Page":
        """"Same arena" cohort (co-membership in trend nodes)."""
        return self._c._page(f"/v1/stocks/{self.ticker}/peers", "peers",
                            MemberStock.from_dict, {}, max_items=max_items)
