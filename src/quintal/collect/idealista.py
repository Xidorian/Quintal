"""Idealista adapter.

Idealista uses path-segment filters, e.g.
  https://www.idealista.pt/arrendar-casas/faro-distrito/com-preco-max_1500,t2,t3,t4/?pagina=2
NOTE: verify the exact segment/param spelling against the live site on first run —
portals adjust these. The `to_raw` mapping is stable regardless of URL scheme.
"""

from __future__ import annotations

from .base import ExtractedRow, SearchParams, row_to_raw

name = "idealista"
_BASE = "https://www.idealista.pt/arrendar-casas"
_REGION_SLUGS = {"algarve": "faro-distrito"}


def search_urls(params: SearchParams, pages: int = 1) -> list[str]:
    filters: list[str] = []
    if params.max_price:
        filters.append(f"com-preco-max_{params.max_price}")
    lo = params.min_beds or 1
    hi = params.max_beds or lo
    filters.extend(f"t{b}" for b in range(max(lo, 1), hi + 1))

    region = _REGION_SLUGS.get(params.region, params.region)
    url = f"{_BASE}/{region}/"
    if filters:
        url += ",".join(filters) + "/"
    return [url + (f"?pagina={p}" if p > 1 else "") for p in range(1, pages + 1)]


def to_raw(row: ExtractedRow) -> dict:
    return row_to_raw(name, row)
