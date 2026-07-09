"""The `Listing` contract — the one model every pipeline stage speaks."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Plausible built-area bounds for an Algarve rental. Outside this, a parsed size is
# garbage (a 10,000,000 m² card, or "10 m²" on a 3-bed house) — treat it as unknown so
# it can't skew the hedonic valuation (size is a regression feature) or the size filter.
MIN_PLAUSIBLE_M2 = 15
MAX_PLAUSIBLE_M2 = 2000

PropertyType = Literal["house", "townhouse", "apartment", "studio", "other"]
PetsValue = Literal["yes", "no", "unknown"]
Band = Literal["undervalued", "fair", "overpriced"]
Confidence = Literal["low", "medium", "high"]


class DerivedBool(BaseModel):
    """A boolean feature derived from listing text, with a confidence and evidence."""

    value: bool | None = None
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class DerivedPets(BaseModel):
    value: PetsValue = "unknown"
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class Listing(BaseModel):
    # --- Identity / provenance ---
    listing_id: str = ""
    source: str = "unknown"
    source_url: str | None = None
    also_listed_at: list[str] = Field(default_factory=list)
    is_private_landlord: bool = False

    # --- Core attributes ---
    title: str | None = None
    description_raw: str = ""
    price_eur_month: float
    size_m2: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    property_type: PropertyType = "other"
    furnished: bool | None = None
    concelho: str = "unknown"
    freguesia: str | None = None

    @field_validator("size_m2")
    @classmethod
    def _drop_implausible_size(cls, v: float | None) -> float | None:
        if v is not None and not (MIN_PLAUSIBLE_M2 <= v <= MAX_PLAUSIBLE_M2):
            return None
        return v

    # --- Geo / enrichment ---
    lat: float | None = None
    lng: float | None = None
    dist_beach_m: float | None = None
    walk_min_beach: float | None = None
    dist_town_m: float | None = None
    photos: list[str] = Field(default_factory=list)

    # --- Derived features ---
    has_yard: DerivedBool = Field(default_factory=DerivedBool)
    has_terrace: DerivedBool = Field(default_factory=DerivedBool)
    has_bathtub: DerivedBool = Field(default_factory=DerivedBool)
    pets: DerivedPets = Field(default_factory=DerivedPets)

    # --- Valuation (filled by valuation stage) ---
    valuation_pct: float | None = None
    valuation_band: Band | None = None
    valuation_expected_eur: float | None = None
    valuation_confidence: Confidence | None = None
    valuation_method: str | None = None
    valuation_why: list[str] = Field(default_factory=list)

    # --- Ranking / dedup (filled later) ---
    match_score: int | None = None
    match_breakdown: dict[str, float] = Field(default_factory=dict)
    duplicate_of: str | None = None

    def ensure_id(self) -> str:
        """Stable id: prefer the source URL, else a hash of canonical attributes.

        Stable across re-collection so a listing keeps its identity (and its 👍/👎).
        """
        if self.listing_id:
            return self.listing_id
        basis = self.source_url or "|".join(
            str(x)
            for x in (
                self.concelho,
                self.bedrooms,
                round(self.size_m2) if self.size_m2 else "",
                round(self.price_eur_month),
                (self.title or "")[:40],
            )
        )
        self.listing_id = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
        return self.listing_id
