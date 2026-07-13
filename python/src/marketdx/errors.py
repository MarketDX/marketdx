"""Typed exceptions.

Every non-2xx response maps to one of these so callers branch on the *kind* of
failure without inspecting status codes. All inherit from :class:`MarketDXError`
— ``except MarketDXError`` catches everything.
"""

from __future__ import annotations

from typing import Optional


class MarketDXError(Exception):
    """Base class for every SDK error."""

    def __init__(self, message: str, *, status: Optional[int] = None, response: object = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.response = response


class AuthError(MarketDXError):
    """401 — the API key is missing or invalid."""


class QuotaError(MarketDXError):
    """402 — the daily credit quota is exhausted.

    Call :meth:`MarketDX.account` (free + unmetered) any time — even while 402 —
    to read your balance, quota, and reset.
    """


class RateLimitError(MarketDXError):
    """429 — per-minute rate limit hit. ``retry_after`` = seconds to wait."""

    def __init__(self, message: str, *, retry_after: Optional[float] = None, **kw: object) -> None:
        super().__init__(message, **kw)  # type: ignore[arg-type]
        self.retry_after = retry_after


class BadRequestError(MarketDXError):
    """400 — invalid parameters (unknown enum value, bad id, contradictory args)."""


class NotFoundError(MarketDXError):
    """404 — the requested resource does not exist."""


class ServerError(MarketDXError):
    """5xx — a server-side error (detail is logged server-side, never leaked)."""
