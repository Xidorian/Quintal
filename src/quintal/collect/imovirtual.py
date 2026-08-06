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
# Every Imovirtual location string ends in the *district* (not the concelho). We strip that
# trailing token to recover the concelho — but the district varies by region now (Norte
# expansion), so match against the full set of mainland districts rather than a single
# hardcoded "faro". A concelho sharing its district's name (Porto, Braga, …) is unaffected:
# only the *trailing* token is dropped, leaving the concelho token intact.
_DISTRICTS = frozenset(
    d.casefold()
    for d in (
        "Aveiro", "Beja", "Braga", "Bragança", "Castelo Branco", "Coimbra", "Évora",
        "Faro", "Guarda", "Leiria", "Lisboa", "Portalegre", "Porto", "Santarém",
        "Setúbal", "Viana do Castelo", "Vila Real", "Viseu",
    )
)
_BASE = "https://www.imovirtual.com/pt/resultados/arrendar"
_ROOMS = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE"}
# Canonical region → Imovirtual location slug. See idealista._REGION_SLUGS for the Norte set.
_REGION_SLUGS = {
    "algarve": "faro",
    "porto": "porto",
    "braga": "braga",
    "viana-do-castelo": "viana-do-castelo",
    "vila-real": "vila-real",
    "viseu": "viseu",
}


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
    """Imovirtual addresses read '[street, ]freguesia, concelho, <District>' — the trailing
    token is the *district*, not the concelho (unlike Idealista's 'freguesia, concelho').
    Drop the district, then concelho = last remaining, freguesia = the one before it.
    Returns (concelho, freguesia).
    """
    if not location:
        return None, None
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if len(parts) > 1 and parts[-1].casefold() in _DISTRICTS:
        parts = parts[:-1]  # drop the district suffix (only when it isn't the sole token)
    if not parts:
        return None, None
    concelho = parts[-1]
    freguesia = parts[-2] if len(parts) >= 2 else None
    return concelho, freguesia


def _rent_only(price_text: str | None) -> str | None:
    """Imovirtual's price cell concatenates rent + price-per-m² ('1350 €16,88 €/m²') and
    sometimes a tax note ('1300 €+ taxa: 0 €/mês'). The monthly rent is everything before
    the first euro sign — take that so parse_price doesn't read '135016.88'."""
    if not price_text:
        return price_text
    return price_text.split("€", 1)[0]


def to_raw(row: ExtractedRow) -> dict:
    row = {**row, "price_text": _rent_only(row.get("price_text"))}
    raw = row_to_raw(name, row)
    # Override the shared (Idealista-shaped) concelho/freguesia derivation with the
    # Imovirtual-specific parse, so every listing doesn't collapse to concelho 'Faro'.
    concelho, freguesia = _parse_location(row.get("location"))
    if concelho:
        raw["concelho"] = concelho
    raw["freguesia"] = freguesia
    return raw
