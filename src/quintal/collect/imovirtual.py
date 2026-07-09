"""Imovirtual adapter.

Imovirtual (OLX-group platform) uses query params, e.g.
  https://www.imovirtual.com/pt/resultados/arrendar/apartamento,moradia/faro?priceMax=1500&roomsNumber=%5BTWO%2CTHREE%2CFOUR%5D&page=2
NOTE: verify param names against the live site on first run — this platform changed
its URL scheme after the OLX migration. The `to_raw` mapping is stable regardless.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from .base import ExtractedRow, SearchParams, row_to_raw

name = "imovirtual"
_DISTRICT = "faro"  # every Imovirtual location ends in the district; it's not the concelho
_BASE = "https://www.imovirtual.com/pt/resultados/arrendar"
_ROOMS = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE"}
_REGION_SLUGS = {"algarve": "faro"}


def search_urls(params: SearchParams, pages: int = 1) -> list[str]:
    types = ",".join(params.property_types) or "apartamento,moradia"
    lo = params.min_beds or 1
    hi = params.max_beds or lo
    rooms = [_ROOMS[b] for b in range(max(lo, 1), hi + 1) if b in _ROOMS]

    region = _REGION_SLUGS.get(params.region, params.region)
    base = f"{_BASE}/{quote(types)}/{region}"
    urls: list[str] = []
    for p in range(1, pages + 1):
        query: dict[str, str] = {}
        if params.max_price:
            query["priceMax"] = str(params.max_price)
        if rooms:
            query["roomsNumber"] = "[" + ",".join(rooms) + "]"
        if p > 1:
            query["page"] = str(p)
        urls.append(base + (f"?{urlencode(query)}" if query else ""))
    return urls


def _parse_location(location: str | None) -> tuple[str | None, str | None]:
    """Imovirtual addresses read '[street, ]freguesia, concelho, Faro' — the trailing
    token is the *district*, not the concelho (unlike Idealista's 'freguesia, concelho').
    Drop the district, then concelho = last remaining, freguesia = the one before it.
    Returns (concelho, freguesia).
    """
    if not location:
        return None, None
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if parts and parts[-1].casefold() == _DISTRICT:
        parts = parts[:-1]  # drop the district suffix
    if not parts:
        return None, None
    concelho = parts[-1]
    freguesia = parts[-2] if len(parts) >= 2 else None
    return concelho, freguesia


def to_raw(row: ExtractedRow) -> dict:
    raw = row_to_raw(name, row)
    # Override the shared (Idealista-shaped) concelho/freguesia derivation with the
    # Imovirtual-specific parse, so every listing doesn't collapse to concelho 'Faro'.
    concelho, freguesia = _parse_location(row.get("location"))
    if concelho:
        raw["concelho"] = concelho
    raw["freguesia"] = freguesia
    return raw
