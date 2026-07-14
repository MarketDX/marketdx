"""Typed models for the impact graph.

Plain dataclasses (zero runtime deps) with attribute access + IDE autocomplete.
Each keeps ``.raw`` (the untouched JSON) so a field the API adds tomorrow is
never lost — forward-compatible by construction. ``.to_rows()`` flattens a model
to the **API-native columns** that mirror the sample dataset's
``impact-signals.csv`` (so code prototyped on the CSV works unchanged on
``.to_df()``); the dataset-only ``theme`` column is deliberately excluded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# The impact-signals contract columns (event × entity × aspect), API-native.
SIGNAL_COLUMNS: tuple[str, ...] = (
    "published_at", "title", "brief_text",
    "entity_name", "entity_ticker", "entity_type",
    "direction", "aspect", "reason", "relevance",
    "impact", "impact_score", "node_name", "entity_country",
    "publisher", "url",
)

# A stock's own impact timeline (one row per article × aspect) — the subject is the stock.
STOCK_NEWS_COLUMNS: tuple[str, ...] = (
    "published_at", "title", "trend", "direction", "aspect", "reason",
    "relevance", "impact_score", "brief_text", "publisher", "url",
)


def _g(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


@dataclass
class Aspect:
    """One causal channel of an entity's impact (the *why*)."""

    aspect: Optional[str]      # demand | supply | … (see enums.Aspect); may be None
    direction: Optional[str]   # pos | neg | ambiguous
    reason: Optional[str]
    relevance: Optional[float]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Aspect":
        return cls(d.get("aspect"), d.get("direction"), d.get("reason"), d.get("relevance"), raw=d)


@dataclass
class Impact:
    """An entity's aggregate impact for one article: net direction + per-aspect breakdown."""

    net_direction: Optional[str]
    relevance: Optional[float]
    aspects: List[Aspect]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> Optional["Impact"]:
        if not d:
            return None
        return cls(
            d.get("net_direction"),
            d.get("relevance"),
            [Aspect.from_dict(a) for a in (d.get("aspects") or [])],
            raw=d,
        )


@dataclass
class Entity:
    """A company or asset affected by an article. ``ticker`` is None for private cos."""

    name: Optional[str]
    ticker: Optional[str]
    type: Optional[str]        # stock | forex | crypto | commodity | private | public_off_coverage
    country: Optional[str]
    direct: bool               # True = epicenter, False = ripple
    impact: Optional[Impact]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Entity":
        return cls(
            d.get("name"), d.get("ticker"), d.get("type"), d.get("country"),
            bool(d.get("direct")), Impact.from_dict(d.get("impact")), raw=d,
        )


@dataclass
class Signal:
    """One news event + every entity it moves. The core of the graph."""

    title: Optional[str]
    brief_text: Optional[str]
    url: Optional[str]
    publisher: Optional[str]
    publisher_type: Optional[str]
    published_at: Optional[str]
    impact_type: Optional[str]     # article-level: direct/indirect (see per-entity too)
    impact_score: Optional[int]    # 1–5 market-wide magnitude
    confidence: Optional[float]
    news_types: List[str]
    node_id: Optional[int]
    node_name: Optional[str]
    rationale: Optional[str]
    entities: List[Entity]
    similarity: Optional[float] = None  # search only: 0–1 cosine, how strongly it matched the query
    scored: Optional[bool] = None       # search only: does the article carry a judged impact on an entity
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Signal":
        # node fields are top-level (node_id/node_name); older shapes nested them under "node".
        node = d.get("node") if isinstance(d.get("node"), dict) else {}
        node_id = _g(d, "node_id") or node.get("node_id")
        node_name = _g(d, "node_name") or node.get("node_name") or node.get("name")
        return cls(
            title=d.get("title"),
            brief_text=d.get("brief_text"),
            url=d.get("url"),
            publisher=d.get("publisher"),
            publisher_type=d.get("publisher_type"),
            published_at=_g(d, "article_published_at", "published_at"),
            impact_type=d.get("impact_type"),
            impact_score=d.get("impact_score"),
            confidence=d.get("confidence"),
            news_types=list(d.get("news_types") or []),
            node_id=node_id,
            node_name=node_name,
            rationale=d.get("rationale"),
            entities=[Entity.from_dict(e) for e in (d.get("entities") or [])],
            similarity=d.get("similarity"),
            scored=d.get("scored"),
            raw=d,
        )

    def to_rows(self, *, all_entities: bool = False) -> List[Dict[str, Any]]:
        """Flatten to event × entity × aspect rows (the impact-signals schema).

        By default only entities that carry an impact are emitted (matching the
        curated CSV). ``all_entities=True`` also emits mentioned-only entities
        (blank impact fields).
        """
        base = {
            "published_at": self.published_at, "title": self.title,
            "brief_text": self.brief_text, "impact_score": self.impact_score,
            "node_name": self.node_name, "publisher": self.publisher, "url": self.url,
        }
        rows: List[Dict[str, Any]] = []
        for e in self.entities:
            ent = {
                "entity_name": e.name, "entity_ticker": e.ticker,
                "entity_type": e.type, "entity_country": e.country,
                "impact": "direct" if e.direct else "indirect",
            }
            if e.impact and e.impact.aspects:
                for a in e.impact.aspects:
                    rows.append({**base, **ent, "direction": a.direction, "aspect": a.aspect,
                                 "reason": a.reason, "relevance": a.relevance})
            elif e.impact:  # scored, but channel unclear (aspect empty)
                rows.append({**base, **ent, "direction": e.impact.net_direction, "aspect": None,
                             "reason": None, "relevance": e.impact.relevance})
            elif all_entities:  # mentioned only
                rows.append({**base, **ent, "direction": None, "aspect": None,
                             "reason": None, "relevance": None})
        return rows


@dataclass
class StockNews:
    """One article in a stock's OWN impact timeline (from ``stock(...).news()``).

    Here the stock IS the subject — its per-article impact lives in ``impact``
    (net_direction + aspects), with the article's ``trend`` and ``relevance``.
    There is no ``entities[]`` (this endpoint is stock-centric); for the full
    entity graph of an article, use :meth:`MarketDX.news`.
    """

    title: Optional[str]
    brief_text: Optional[str]
    url: Optional[str]
    publisher: Optional[str]
    publisher_type: Optional[str]
    published_at: Optional[str]
    impact: Optional[Impact]      # the STOCK's own impact for this article
    relevance: Optional[float]
    trend: Optional[str]
    trend_id: Optional[int]
    impact_score: Optional[int]
    news_types: List[str]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StockNews":
        return cls(
            title=d.get("title"), brief_text=d.get("brief_text"), url=d.get("url"),
            publisher=d.get("publisher"), publisher_type=d.get("publisher_type"),
            published_at=_g(d, "article_published_at", "published_at"),
            impact=Impact.from_dict(d.get("impact")),
            relevance=d.get("relevance"), trend=d.get("trend"), trend_id=d.get("trend_id"),
            impact_score=d.get("impact_score"), news_types=list(d.get("news_types") or []), raw=d,
        )

    def to_rows(self) -> List[Dict[str, Any]]:
        base = {
            "published_at": self.published_at, "title": self.title, "trend": self.trend,
            "relevance": self.relevance, "impact_score": self.impact_score,
            "brief_text": self.brief_text, "publisher": self.publisher, "url": self.url,
        }
        if self.impact and self.impact.aspects:
            return [{**base, "direction": a.direction, "aspect": a.aspect, "reason": a.reason}
                    for a in self.impact.aspects]
        nd = self.impact.net_direction if self.impact else None
        return [{**base, "direction": nd, "aspect": None, "reason": None}]


@dataclass
class MemberStock:
    """A listed company that belongs to a megatrend (from ``megatrends(id).stocks``)."""

    stock_id: Optional[int]
    symbol: Optional[str]
    name: Optional[str]
    exchange: Optional[str]
    country: Optional[str]
    domicile: Optional[str]
    currency: Optional[str]
    gic_code: Optional[str]
    market_cap_usd: Optional[float]
    market_cap_local: Optional[float]
    fx_rate_usd: Optional[float]
    megatrend: Dict[str, Any]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemberStock":
        return cls(
            d.get("stock_id"), d.get("symbol"), d.get("name"), d.get("exchange"),
            d.get("country"), d.get("domicile"), d.get("currency"), d.get("gic_code"),
            d.get("market_cap_usd"), d.get("market_cap_local"), d.get("fx_rate_usd"),
            d.get("megatrend") or {}, raw=d,
        )

    def to_rows(self) -> List[Dict[str, Any]]:
        m = self.megatrend
        return [{
            "stock_id": self.stock_id, "symbol": self.symbol, "name": self.name,
            "exchange": self.exchange, "country": self.country, "domicile": self.domicile,
            "currency": self.currency, "gic_code": self.gic_code,
            "market_cap_usd": self.market_cap_usd, "market_cap_local": self.market_cap_local,
            "node_id": m.get("node_id"), "node_name": m.get("node_name"),
            "exposure": m.get("exposure"), "role": m.get("role"), "confidence": m.get("confidence"),
        }]


@dataclass
class Company:
    """A private / public-out-of-coverage company in a megatrend (``megatrends(id).off_coverage``)."""

    off_company_id: Optional[int]
    name: Optional[str]
    country: Optional[str]
    type: Optional[str]     # private | public_off_coverage
    megatrend: Dict[str, Any]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Company":
        return cls(d.get("off_company_id"), d.get("name"), d.get("country"),
                   d.get("type"), d.get("megatrend") or {}, raw=d)

    def to_rows(self) -> List[Dict[str, Any]]:
        m = self.megatrend
        return [{
            "off_company_id": self.off_company_id, "name": self.name,
            "country": self.country, "type": self.type,
            "node_id": m.get("node_id"), "node_name": m.get("node_name"),
            "exposure": m.get("exposure"), "role": m.get("role"), "confidence": m.get("confidence"),
        }]


@dataclass
class MegatrendNode:
    """A node in the trend taxonomy."""

    id: Optional[int]
    name: Optional[str]
    tier: Optional[int]
    parent_id: Optional[int]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MegatrendNode":
        return cls(_g(d, "node_id", "id"), d.get("name"), _g(d, "tier", "depth"),
                   d.get("parent_id"), raw=d)

    def to_rows(self) -> List[Dict[str, Any]]:
        return [{"node_id": self.id, "name": self.name, "tier": self.tier, "parent_id": self.parent_id}]
