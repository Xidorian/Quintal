"""Idealista adapter.

Idealista uses path-segment filters AND path-segment pagination, e.g.
  https://www.idealista.pt/arrendar-casas/faro-distrito/pagina-2
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
    lo = max(params.min_beds or 1, 1)
    hi = max(params.max_beds or lo, lo)
    # Idealista typology tokens are t1, t2, t3, and t4-t5 for the "T4+" bucket — there is NO
    # standalone t4 (a bare t4 soft-404s the whole URL). Verified from the live filter UI
    # 2026-07-19: …/com-preco-max_1500,t2,t3,t4-t5/. Emit t{lo..3}, then t4-t5 when hi ≥ 4.
    filters.extend(f"t{b}" for b in range(lo, min(hi, 3) + 1))
    if hi >= 4:
        filters.append("t4-t5")

    region = _REGION_SLUGS.get(params.region, params.region)
    url = f"{_BASE}/{region}/"
    if filters:
        url += ",".join(filters) + "/"
    # Idealista paginates by path segment (…/pagina-2), appended to the trailing slash.
    # NOT ?pagina=N (overlaps page 1) and NOT /pagina-N.htm (redirects to landing).
    # Verified against the live site's own pagination links, 2026-07-08.
    return [url + (f"pagina-{p}" if p > 1 else "") for p in range(1, pages + 1)]


def to_raw(row: ExtractedRow) -> dict:
    return row_to_raw(name, row)
