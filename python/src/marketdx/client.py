"""The MarketDX client — the financial impact graph in a few lines."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from . import enums
from ._http import Transport
from .models import (
    Company,
    GicsCode,
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


def _cap(limit: Optional[int], max_items: Optional[int]) -> Optional[int]:
    """Effective cap on results returned by an auto-paginating method. ``limit`` is the primary
    knob (has a sane default; ``None`` = fetch everything). ``max_items`` is a deprecated alias kept
    for back-compat — if given, it wins."""
    return max_items if max_items is not None else limit


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
        collapse: Optional[bool] = None,
        impact: Optional[enums.ImpactType] = None,
        direction: Optional[enums.Direction] = None,
        aspect: Optional[Union[enums.Aspect, str]] = None,
        news_type: Optional[Union[str, List[str]]] = None,
        entity_type: Optional[enums.EntityType] = None,
        only_scored: Optional[bool] = None,
        min_relevance: Optional[float] = None,
        country: Optional[str] = None,
        lang: Optional[str] = None,
        order_by: Optional[str] = None,
        since: Optional[str] = None,
        from_: Optional[str] = None,
        to: Optional[str] = None,
        limit: Optional[int] = 50,
        max_items: Optional[int] = None,
    ) -> "Page":
        """News signals, one :class:`~marketdx.models.Signal` per event. Auto-paginated.

        ``limit`` caps how many signals you get back (default 50; pass ``limit=None`` to walk the
        **entire** match set — mind the credit cost on a broad feed). ``max_items`` is a deprecated
        alias for ``limit``. Iteration pages under the hood; ``page.total`` is the full match count.

        Near-duplicate stories (one story republished / rewritten across outlets) are merged
        into a single signal by default. Pass ``collapse=False`` for the raw, un-deduped feed.

        Server-side entity filters (also work under ``megatrend=`` — but not ``impact="indirect"``):

        * ``entity_type`` — keep only articles with a related entity of that type
          (``stock``/``forex``/``crypto``/``commodity``/``private``/``public_off_coverage``),
          e.g. ``entity_type="private"`` for stories moving a private company (OpenAI, SpaceX).
        * ``only_scored`` — keep only articles with >=1 entity carrying a scored (judged) impact,
          dropping mention-only articles.
        * ``min_relevance`` — keep only articles with >=1 scored entity whose impact relevance
          meets this 0-1 floor (implies scored).

        These filter in SQL, so ``page.total`` stays the exact filtered count.

        ``country`` (ISO-2) keeps only articles impacting a company **listed in that country**
        (e.g. ``country="CN"`` for China-relevant news) — on the bare feed; it is not composed with
        ``megatrend``/``gics`` (use :meth:`brief` or :meth:`stocks` for country + theme).
        """
        params = {
            "megatrend": self._resolve(megatrend), "gics": gics, "include": include,
            "collapse": collapse,
            "impact": impact, "direction": direction, "aspect": aspect, "news_type": news_type,
            "entity_type": entity_type, "only_scored": only_scored, "min_relevance": min_relevance,
            "country": country, "lang": lang, "order_by": order_by, "since": since,
            "from": from_, "to": to,
        }
        return self._page("/v1/news", "results", Signal.from_dict, params,
                          columns=SIGNAL_COLUMNS, max_items=_cap(limit, max_items))

    def news_search(self, q: str, *, entity_type: Optional[enums.EntityType] = None,
                    limit: Optional[int] = 20, lang: Optional[str] = None,
                    include: str = "entities,impact", collapse: Optional[bool] = None,
                    max_items: Optional[int] = None) -> "Page":
        """Semantic (vector) search — news matched by MEANING. Relevance-ranked top-K.

        Each hit carries two explainability fields (on the ``Signal``): ``similarity`` (0–1 cosine —
        *how strongly* it matched; sort/threshold on it or pass ``min_similarity``) and ``scored``
        (does the article actually carry a judged impact on an entity, vs a merely-similar read — a hit
        can be highly similar yet ``scored=False``, e.g. a macro/policy piece moving no covered company).

        ``limit`` is the top-K size (default 20; ``max_items`` is a deprecated alias). Unlike the
        ``news()`` feed, search supports an ``entity_type`` filter (keeps only articles with a
        related entity of that type — stock/forex/crypto/commodity/private/public_off_coverage),
        applied server-side. Near-duplicate stories are merged by default; pass ``collapse=False``
        for the raw hits.
        """
        return self._page("/v1/news/search", "results", Signal.from_dict,
                          {"q": q, "lang": lang, "include": include, "entity_type": entity_type,
                           "collapse": collapse},
                          columns=SIGNAL_COLUMNS, max_items=_cap(limit, max_items))

    def news_by_tickers(self, ticker: Union[str, List[str]], *, direction: Optional[enums.Direction] = None,
                        aspect: Optional[Union[enums.Aspect, str]] = None,
                        impact: Optional[enums.ImpactType] = None, include: str = "entities,impact",
                        collapse: Optional[bool] = None,
                        lang: Optional[str] = None, limit: Optional[int] = 50, max_items: Optional[int] = None) -> "Page":
        """News for one or more tickers — the article + that ticker's **direct AND indirect**
        impact. Use this to query by a specific ticker, which the ``news()`` feed does not filter
        by. ``ticker`` accepts a stock ``NVDA.US`` (or a list), non-stock assets — a
        commodity/crypto/forex as shown in the feed (``GOLD``, ``BTC``) or its ``SYMBOL.EXCHANGE``
        form (``GOLD.COMM``) — AND **off-coverage** private companies as ``oc:<id>`` (``oc:52`` =
        OpenAI). Mix freely: ``news_by_tickers(["NVDA.US", "oc:52"])``. Use :meth:`stocks` (``q=``)
        to look up the exact ``.ticker`` for any of these.
        ``limit`` caps results (default 50; ``None`` = all; ``max_items`` is a deprecated alias).
        Near-duplicate stories are merged by default; pass ``collapse=False`` for the raw feed."""
        return self._page("/v1/news/by-tickers", "results", Signal.from_dict,
                          {"ticker": ticker, "direction": direction, "aspect": aspect,
                           "impact": impact, "include": include, "lang": lang, "collapse": collapse},
                          columns=SIGNAL_COLUMNS, max_items=_cap(limit, max_items))

    def news_types(self) -> List[Dict[str, Any]]:
        """The controlled news-type vocabulary (18 types)."""
        return self._get("/v1/news/types").data.get("types", [])

    # ── Group B — by trend / sector ───────────────────────────────────────────
    def megatrends(self, id: NodeRef = None) -> Union["MegatrendRef", "Page"]:
        """No arg → the **full megatrend tree** as a ``Page`` of nodes (a bounded reference list —
        the whole taxonomy, no ``limit``/paging; filter client-side). With an id/slug/name → a
        :class:`MegatrendRef` you can call ``.stocks()`` / ``.off_coverage()`` on."""
        if id is None:
            return self._page("/v1/megatrends", "nodes", MegatrendNode.from_dict, {})
        return MegatrendRef(self, self._resolve(id))

    def gics(self, code: Optional[str] = None) -> Union["GicsRef", "Page"]:
        """No arg → the **full GICS taxonomy** as a ``Page`` (a small, bounded reference list —
        all ~270 codes across every level; there is no ``limit``/paging, you always get the whole
        tree, so filter client-side). Each row has ``code`` / ``level``
        (sector|group|industry|sub-industry) / ``name`` / ``parent_code``::

            retail = [g for g in mdx.gics() if "retail" in g.name.lower()]   # find a code by name
            groups = [g for g in mdx.gics() if g.level == "group"]           # or by level

        With a code → a :class:`GicsRef` you can call ``.stocks()`` on."""
        if code is None:
            return self._page("/v1/gics", "gics", GicsCode.from_dict, {})
        return GicsRef(self, code)

    # ── Group C — by stock ────────────────────────────────────────────────────
    def stocks(self, *, q: Optional[str] = None, megatrend: NodeRef = None, gics: Optional[str] = None,
               aspect: Optional[Union[enums.Aspect, str]] = None, direction: Optional[enums.Direction] = None,
               country: Optional[str] = None, gate: Optional[str] = None, order_by: Optional[str] = None,
               since: Optional[str] = None, limit: Optional[int] = 50, max_items: Optional[int] = None) -> "Page":
        """``q=`` → identity search (stocks AND commodities/crypto/forex; each result carries a
        ready-to-use ``.ticker`` — e.g. ``NVDA.US``, ``GOLD``, ``BTC`` — to feed straight into
        :meth:`news_by_tickers` / :meth:`stock`); otherwise → the news-driven impact screener,
        scoped by ``megatrend`` and/or ``gics`` (a GICS code prefix, see :meth:`gics`) and/or
        ``country`` (≥1 required). ``limit`` caps results (default 50; ``None`` = all; ``max_items``
        is a deprecated alias)."""
        params = {"q": q, "megatrend": self._resolve(megatrend), "gics": gics, "aspect": aspect,
                  "direction": direction, "country": country, "gate": gate,
                  "order_by": order_by, "since": since}
        # the search (?q=) response nests results under `matches`; the screener under `stocks`
        key = "matches" if q else "stocks"
        return self._page("/v1/stocks", key, MemberStock.from_dict, params, max_items=_cap(limit, max_items))

    def stock(self, ticker: str) -> "StockRef":
        """A per-stock handle: ``.news()`` / ``.competitors()`` / ``.peers()``."""
        return StockRef(self, ticker)

    def theme(self, id: NodeRef) -> "MegatrendRef":
        """A theme handle (= a megatrend node) — call ``.summary(window=…)`` for the one-call analyst
        brief. Alias of ``megatrends(id)`` that reads at the URL you'd expect (``/v1/themes/:id``)."""
        return MegatrendRef(self, self._resolve(id))

    def brief(self, *, megatrend: Optional[Union[NodeRef, List[NodeRef]]] = None,
              news_type: Optional[Union[str, List[str]]] = None,
              country: Optional[Union[str, List[str]]] = None,
              aspect: Optional[Union[enums.Aspect, str, List[str]]] = None,
              gics: Optional[Union[str, List[str]]] = None,
              window: Optional[str] = None, interval: Optional[str] = None,
              from_: Optional[str] = None, to: Optional[str] = None,
              lang: Optional[str] = None) -> Dict[str, Any]:
        """The generalized **analyst brief** (``GET /v1/brief``) — the same composed picture as
        ``theme(id).summary()``, but scoped by ANY AND-combination of **megatrend / news_type /
        country / aspect / gics** (>=1 required). Ask "how is <scope> doing right now?" for a theme, a
        market, a news category, an impact channel, a GICS sector, or any mix — e.g. commodity news
        affecting Japan, everything moving via tariffs, or a European retail pulse::

            mdx.brief(news_type="commodity_supply", country="JP", window="90d")
            mdx.brief(megatrend="ai-power", aspect="tariff")   # == theme("ai-power") narrowed to tariff
            mdx.brief(gics="2550", country=["GB", "DE", "FR", "IT", "ES", "NL"])  # European retail pulse

        Returns the raw brief ``dict`` (same shape as ``summary()``) plus ``applied_scope``. ``node``
        and ``ripple`` appear ONLY when a single ``megatrend`` anchors the brief (ripple = the
        ``megatrend_relation`` spill, undefined without a theme). ``winners``/``losers`` are the
        theme's members under a megatrend scope, else the top +/- companies in the scope. Every count
        is story-deduped. ``theme(id).summary(...)`` == ``brief(megatrend=id, ...)``. Cost: 15 credits.

        ``megatrend`` takes a node id/slug/name (or a list); ``news_type`` (see :meth:`news_types`),
        ``country`` (ISO-2), ``aspect`` and ``gics`` each take one value or a list. ``gics`` is a GICS
        code **prefix** at any depth — sector ``"25"``, industry-group ``"2550"``, industry
        ``"255010"``, or sub-industry ``"25501010"`` (browse codes with :meth:`gics`). ``country`` is
        the company's *listing/exchange* country, not domicile. ``window``/``interval``/``from_``/
        ``to``/``lang`` are as ``summary()``.
        """
        mt = [self._resolve(m) for m in megatrend] if isinstance(megatrend, list) else self._resolve(megatrend)
        params = {"megatrend": mt, "news_type": news_type, "country": country, "aspect": aspect,
                  "gics": gics, "window": window, "interval": interval, "from": from_, "to": to, "lang": lang}
        return self._get("/v1/brief", params).data

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

    def summary(self, *, window: Optional[str] = None, interval: Optional[str] = None,
                country: Optional[str] = None, from_: Optional[str] = None,
                to: Optional[str] = None, lang: Optional[str] = None) -> Dict[str, Any]:
        """The theme's pre-composed **analyst brief** (``GET /v1/themes/:id/summary``) — one call for
        the whole picture, so you don't stitch 5+ requests together. Returns the raw brief ``dict``
        (a fixed composite, not a paginated list):

        * ``pulse`` — headline totals + a **timeseries** ``series`` (volume + sentiment per bucket).
          There's no single momentum number: the latest bucket is the current, partial period.
        * ``top_stories`` (epicenter, deduped; market-wraps + stories that name no member company are
          deprioritized), ``ripple`` (indirect), ``winners`` / ``losers`` (member stocks),
          ``aspect_heatmap``, ``top_entities`` (companies), ``top_assets`` (commodity/forex/crypto).

        Every count is **story-deduped** — a story republished by 20 outlets counts once.

        ``window`` = ``7d``/``30d``/``90d``/``180d``/``1y`` or calendar ``mtd``/``qtd``/``ytd`` (or pass
        ``from_``+``to``). ``interval`` (``day``/``week``/``month``) buckets the pulse series (auto by
        span if omitted). ``country`` geo-filters winners/losers/entities. Cost: 15 credits.
        """
        params = {"window": window, "interval": interval, "country": country,
                  "from": from_, "to": to, "lang": lang}
        return self._c._get(f"/v1/themes/{self.node_id}/summary", params).data


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
             since: Optional[str] = None, limit: Optional[int] = 50, max_items: Optional[int] = None) -> "Page":
        """This stock's OWN impact timeline (:class:`~marketdx.models.StockNews`): each article
        + the stock's per-article ``impact`` (net_direction + aspects), ``trend``, and
        ``relevance``. No ``entities[]`` — the stock is the subject; use ``mdx.news()`` for the
        full entity graph of an article. ``limit`` caps results (default 50; ``None`` = all;
        ``max_items`` is a deprecated alias)."""
        params = {"direction": direction, "aspect": aspect, "order_by": order_by, "since": since}
        return self._c._page(f"/v1/stocks/{self.ticker}/news", "results", StockNews.from_dict,
                            params, columns=STOCK_NEWS_COLUMNS, max_items=_cap(limit, max_items))

    def competitors(self, *, max_items: Optional[int] = None) -> "Page":
        """Rivals derived from competition co-occurrence."""
        return self._c._page(f"/v1/stocks/{self.ticker}/competitors", "competitors",
                            MemberStock.from_dict, {}, max_items=max_items)

    def peers(self, *, max_items: Optional[int] = None) -> "Page":
        """"Same arena" cohort (co-membership in trend nodes)."""
        return self._c._page(f"/v1/stocks/{self.ticker}/peers", "peers",
                            MemberStock.from_dict, {}, max_items=max_items)
