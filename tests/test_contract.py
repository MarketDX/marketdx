"""Cross-cutting CONTRACT test — the enforcement that makes the SDK and the sample
dataset "speak one language" without duplicating a hand-maintained copy.

Asserts three things agree:
  • SDK  — the `Literal`/tuple vocabularies in `python/src/marketdx/enums.py`
  • dataset — the `constraints.enum`s in `datasets/datapackage.json` (offline snapshot)
  • API  — the live `/v1/enums` values (the runtime source of truth)   [needs MDX_KEY]

...plus the column contract: `to_df()` (SIGNAL_COLUMNS) == the dataset's `impact-signals`
schema, minus the dataset-only `theme` column.

Run: `MDX_KEY=… pytest tests/test_contract.py`  (the API checks skip without a key).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "src"))

from marketdx import enums                       # noqa: E402
from marketdx.client import DEFAULT_BASE_URL     # noqa: E402
from marketdx.models import SIGNAL_COLUMNS       # noqa: E402

DATAPACKAGE = json.loads((ROOT / "datasets" / "datapackage.json").read_text())


def _resource(name: str) -> dict:
    return next(r for r in DATAPACKAGE["resources"] if r["name"] == name)


def _field_enum(resource: str, field: str) -> set[str]:
    fields = _resource(resource)["schema"]["fields"]
    f = next(x for x in fields if x["name"] == field)
    return {v for v in f["constraints"]["enum"] if v != ""}  # drop the allowed empty


# ── SDK ≡ dataset (offline — always runs) ─────────────────────────────────────

def test_entity_type_sdk_matches_dataset():
    assert set(enums.ENTITY_TYPES) == _field_enum("impact-signals", "entity_type")


def test_direction_sdk_matches_dataset():
    assert set(enums.DIRECTIONS) == _field_enum("impact-signals", "direction")


def test_aspect_sdk_matches_dataset():
    assert set(enums.ASPECTS) == _field_enum("impact-signals", "aspect")


def test_exposure_data_values_match_dataset():
    # data-values only (core/secondary) — the query-only "all" lives in EXPOSURE_FILTERS
    assert set(enums.EXPOSURE_VALUES) == _field_enum("private-roster", "exposure")


def test_impact_type_matches_dataset():
    assert set(enums.IMPACT_TYPES) == _field_enum("impact-signals", "impact")


def test_signal_columns_match_impact_signals_schema():
    fields = [f["name"] for f in _resource("impact-signals")["schema"]["fields"]]
    api_native = [f for f in fields if f != "theme"]  # theme is dataset-only
    assert list(SIGNAL_COLUMNS) == api_native


def test_base_url_is_the_api_domain():
    assert DEFAULT_BASE_URL == "https://api.marketdx.lab.ai"
    llms = (ROOT / "datasets" / "llms.txt").read_text()
    assert "api.marketdx.lab.ai" in llms, "dataset 'Go live' URL should match the SDK base"


# ── SDK ≡ live API (needs a key — skips otherwise) ────────────────────────────

@pytest.mark.skipif(not os.environ.get("MDX_KEY"), reason="set MDX_KEY for live /v1/enums checks")
def test_sdk_matches_live_enums():
    from marketdx import MarketDX

    api = MarketDX(api_key=os.environ["MDX_KEY"]).enums()

    def values(key: str) -> set[str]:
        vs = api[key]["values"]
        return {v if isinstance(v, str) else v.get("value") for v in vs}

    assert set(enums.ENTITY_TYPES) == values("entity_type")
    assert set(enums.DIRECTIONS) == values("direction")
    assert set(enums.ASPECTS) == values("aspect")
    # exposure: applies_to = query endpoints, so the API adds "all" on top of the data-values
    assert set(enums.EXPOSURE_VALUES) <= values("exposure")
    assert values("exposure") - set(enums.EXPOSURE_VALUES) == {"all"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
