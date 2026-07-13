"""Slug / name → megatrend node-id resolution.

So ``megatrend="ai-power"`` or ``"AI Power & Cooling"`` works, not just
``10040000``. The trend tree is fetched once (``/v1/megatrends``) and cached.
Numeric ids pass straight through — no lookup, no network.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Union

from .errors import MarketDXError


def slugify(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


class Taxonomy:
    def __init__(self, fetch_nodes: Callable[[], List[dict]]) -> None:
        self._fetch = fetch_nodes
        self._by_name: Dict[str, int] = {}
        self._by_slug: Dict[str, int] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        for n in self._fetch():
            nid = n.get("node_id") or n.get("id")
            name = n.get("name")
            if nid is None or not name:
                continue
            self._by_name[name.lower()] = nid
            self._by_slug[slugify(name)] = nid
        self._loaded = True

    def resolve(self, value: Union[int, str, None]) -> Optional[int]:
        """Return the node id for an id / name / slug. None stays None."""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        v = value.strip()
        if v.isdigit():
            return int(v)
        self._load()
        key = v.lower()
        if key in self._by_name:
            return self._by_name[key]
        s = slugify(v)
        if s in self._by_slug:
            return self._by_slug[s]
        # unique-substring fallback: "ai-power" → "ai-power-cooling"
        hits = [(slug, nid) for slug, nid in self._by_slug.items() if s and s in slug]
        if len(hits) == 1:
            return hits[0][1]
        if len(hits) > 1:
            opts = ", ".join(sorted(slug for slug, _ in hits)[:8])
            raise MarketDXError(f"megatrend {value!r} is ambiguous — matches: {opts}. Use a fuller name or the numeric id.")
        raise MarketDXError(f"megatrend {value!r} not found. Pass a valid trend name, slug, or node id (see mdx.megatrends()).")
