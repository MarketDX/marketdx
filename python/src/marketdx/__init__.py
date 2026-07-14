"""MarketDX — the financial impact graph, in Python.

    from marketdx import MarketDX
    mdx = MarketDX(api_key="…")
    for s in mdx.news(megatrend="ai-power", impact="indirect"):
        ...
"""

from __future__ import annotations

__version__ = "0.7.0"

from . import enums
from .client import GicsRef, MarketDX, MegatrendRef, StockRef
from .errors import (
    AuthError,
    BadRequestError,
    MarketDXError,
    NotFoundError,
    QuotaError,
    RateLimitError,
    ServerError,
)
from .models import Aspect, Company, Entity, Impact, MegatrendNode, MemberStock, Signal, StockNews

__all__ = [
    "MarketDX",
    "MegatrendRef",
    "GicsRef",
    "StockRef",
    "enums",
    # models
    "Signal",
    "StockNews",
    "Entity",
    "Impact",
    "Aspect",
    "MemberStock",
    "Company",
    "MegatrendNode",
    # errors
    "MarketDXError",
    "AuthError",
    "QuotaError",
    "RateLimitError",
    "BadRequestError",
    "NotFoundError",
    "ServerError",
    "__version__",
]
