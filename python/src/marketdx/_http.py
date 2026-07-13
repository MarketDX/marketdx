"""HTTP transport — auth, request, and status→exception mapping.

Kept tiny and private. The public surface is :class:`marketdx.MarketDX`.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import httpx

from . import __version__
from .errors import (
    AuthError,
    BadRequestError,
    MarketDXError,
    NotFoundError,
    QuotaError,
    RateLimitError,
    ServerError,
)


class Response:
    """A parsed API response + the metering headers that rode with it."""

    __slots__ = ("data", "credits_charged", "rate_limit", "rate_remaining")

    def __init__(self, data: Any, headers: Mapping[str, str]) -> None:
        self.data = data
        self.credits_charged = _int(headers.get("x-credits-charged"))
        self.rate_limit = _int(headers.get("x-ratelimit-limit"))
        self.rate_remaining = _int(headers.get("x-ratelimit-remaining"))


class Transport:
    def __init__(self, base_url: str, api_key: str, *, timeout: float) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": f"marketdx-python/{__version__}",
            },
        )

    def get(self, path: str, params: Optional[Mapping[str, Any]] = None) -> Response:
        # Drop None params; join list/tuple values as CSV (the API's convention).
        clean = {k: _fmt(v) for k, v in (params or {}).items() if v is not None}
        try:
            r = self._client.get(path, params=clean)
        except httpx.RequestError as e:  # network/DNS/timeout — not an HTTP status
            raise MarketDXError(f"request failed: {e}") from e
        if r.is_success:
            return Response(r.json(), r.headers)
        raise _to_error(r)

    def close(self) -> None:
        self._client.close()


def _fmt(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return ",".join(str(x) for x in v)
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _int(v: Optional[str]) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _to_error(r: httpx.Response) -> MarketDXError:
    try:
        msg = r.json().get("error") or r.text
    except Exception:  # noqa: BLE001 — non-JSON body
        msg = r.text or f"HTTP {r.status_code}"
    s = r.status_code
    if s == 400:
        return BadRequestError(msg, status=s, response=r)
    if s == 401:
        return AuthError(msg, status=s, response=r)
    if s == 402:
        return QuotaError(msg, status=s, response=r)
    if s == 404:
        return NotFoundError(msg, status=s, response=r)
    if s == 429:
        return RateLimitError(msg, status=s, response=r, retry_after=_float(r.headers.get("retry-after")))
    if s >= 500:
        return ServerError(msg, status=s, response=r)
    return MarketDXError(msg, status=s, response=r)


def _float(v: Optional[str]) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
