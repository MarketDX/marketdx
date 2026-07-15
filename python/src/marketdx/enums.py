"""Controlled vocabularies — **type-sugar only**, never a runtime gate.

These `Literal` types give your editor/`mypy` autocomplete + typo-flagging at
author-time (before any network call). At *runtime* the SDK does NOT validate
against them — it passes your value straight to the API, which is the single
source of truth (`GET /v1/enums`) and returns a clear ``400`` (→
:class:`marketdx.errors.BadRequestError`) if the value is wrong.

Why not hard-validate here? Forward-compatibility. When the API gains a new
value (e.g. the ``monetary`` / ``tariff`` aspects added mid-2026), an old SDK
that validated against a frozen copy would *reject a value the API accepts* —
reintroducing drift. A stale `Literal` only shows an ignorable editor hint; it
never blocks execution. So: hints catch typos, the API stays authoritative.

The same vocabularies are mirrored (offline) in the sample dataset's
``datapackage.json``; a root CI test asserts SDK ≡ datapackage ≡ ``/v1/enums``.
"""

from __future__ import annotations

from typing import Literal

# ── Literal types (author-time autocomplete / typo hints) ─────────────────────
EntityType = Literal["stock", "etf", "forex", "crypto", "commodity", "private", "public_off_coverage"]
Direction = Literal["pos", "neg", "ambiguous"]
Aspect = Literal[
    "demand", "supply", "pricing", "capital", "competition",
    "technology", "regulation", "tariff", "geopolitics", "monetary",
]
# As a *query filter* exposure also accepts "all" (= don't filter). Stored row
# values are only core/secondary — see EXPOSURE_VALUES vs EXPOSURE_FILTERS below.
Exposure = Literal["core", "secondary", "all"]
ImpactType = Literal["direct", "indirect"]
Relation = Literal["competitor", "peer"]

# ── Tuples (the data-value sets — what the CI contract test compares) ─────────
ENTITY_TYPES: tuple[str, ...] = (
    "stock", "forex", "crypto", "commodity", "private", "public_off_coverage",
)
DIRECTIONS: tuple[str, ...] = ("pos", "neg", "ambiguous")
ASPECTS: tuple[str, ...] = (
    "demand", "supply", "pricing", "capital", "competition",
    "technology", "regulation", "tariff", "geopolitics", "monetary",
)
EXPOSURE_VALUES: tuple[str, ...] = ("core", "secondary")          # values in rows
EXPOSURE_FILTERS: tuple[str, ...] = ("core", "secondary", "all")  # valid ?exposure=
IMPACT_TYPES: tuple[str, ...] = ("direct", "indirect")
RELATIONS: tuple[str, ...] = ("competitor", "peer")
