"""Adapter contract + the shape a rendered card is extracted into."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TypedDict

from .parsing import parse_area, parse_bathrooms, parse_bedrooms, parse_price


@dataclass
class SearchParams:
    """What the searcher is looking for. Region defaults to the whole Algarve
    (Faro district). Concelho-level narrowing happens post-collection via filters."""

    region: str = "algarve"  # canonical; each adapter maps it to its own slug
    max_price: int | None = 1500
    min_beds: int | None = 2
    max_beds: int | None = 4
    property_types: list[str] = field(default_factory=lambda: ["moradia", "apartamento"])


class ExtractedRow(TypedDict, total=False):
    """One listing card as pulled from a rendered results page by the browser tools.
    Everything is a raw string exactly as shown on the page (we parse it in `to_raw`)."""

    url: str
    title: str
    price_text: str  # e.g. "1.200 €/mês"
    area_text: str  # e.g. "85 m²"
    typology: str  # e.g. "T2"
    rooms_text: str  # e.g. "2 quartos, 1 wc"
    location: str  # e.g. "Almancil, Loulé"
    description: str
    is_private: bool
    image_url: str  # card <img> src captured during collection — thumbnail w/o a detail fetch


class Adapter(Protocol):
    name: str

    def search_urls(self, params: SearchParams, pages: int = 1) -> list[str]:
        """The search-results URLs the searcher opens in their logged-in Chrome."""

    def to_raw(self, row: ExtractedRow) -> dict:
        """Map an extracted card into a canonical raw listing dict for `normalize()`.
        Site-specific field parsing lives here; keyword derivation stays in normalize."""


def concelho_from_location(location: str | None, default: str = "unknown") -> str:
    """'Almancil, Loulé' → 'Loulé' (last comma-separated token is the concelho)."""
    if not location:
        return default
    parts = [p.strip() for p in location.split(",") if p.strip()]
    return parts[-1] if parts else default


def freguesia_from_location(location: str | None) -> str | None:
    if not location:
        return None
    parts = [p.strip() for p in location.split(",") if p.strip()]
    return parts[0] if len(parts) >= 2 else None


def row_to_raw(source: str, row: ExtractedRow) -> dict:
    """Map an extracted card into a canonical raw listing dict for `normalize()`.

    Shared by every site adapter — the only per-site difference is `source`. Keyword
    derivation (yard/pets/bathtub) and property-type inference stay in `normalize`.
    """
    location = row.get("location")
    description = " ".join(filter(None, [row.get("title"), row.get("description")]))
    # Try each source in turn — the first that yields a number wins (a truthy-but-
    # typology-less title must not shadow a "T3" in rooms_text).
    bedrooms = None
    for src in (row.get("rooms_text"), row.get("typology"), row.get("title")):
        bedrooms = parse_bedrooms(src)
        if bedrooms is not None:
            break
    return {
        "source": source,
        "source_url": row.get("url"),
        "is_private_landlord": bool(row.get("is_private")),
        "title": row.get("title"),
        "description_raw": description,
        "price_eur_month": parse_price(row.get("price_text")),
        "size_m2": parse_area(row.get("area_text")),
        "bedrooms": bedrooms,
        "bathrooms": parse_bathrooms(row.get("rooms_text")),
        "concelho": concelho_from_location(location),
        "freguesia": freguesia_from_location(location),
        # A card-captured thumbnail url (if any) → photos[0]; photos.py downloads it directly
        # instead of fetching the detail page for og:image (and it's the Idealista thumbnail path).
        "photos": [row["image_url"]] if row.get("image_url") else [],
    }
