"""Preference match score (0–100) — separate from valuation.

A weighted sum of normalized per-feature satisfaction. Weights live in config so the
searcher can tune them without touching this logic.
"""

from __future__ import annotations

from . import config
from .schema import Listing


def _yard_sub(listing: Listing) -> float:
    if listing.has_yard.value:
        return 1.0
    if listing.has_terrace.value:
        return 0.4  # partial credit for terrace/balcony
    return 0.0


def _beach_walk_sub(walk_min: float | None) -> float:
    if walk_min is None:
        return config.WALK_UNKNOWN_SCORE
    if walk_min <= config.WALK_FULL_MIN:
        return 1.0
    if walk_min >= config.WALK_ZERO_MIN:
        return 0.0
    if walk_min <= config.WALK_MID_MIN:
        # FULL_MIN..MID_MIN → 1.0..MID_SCORE
        span = config.WALK_MID_MIN - config.WALK_FULL_MIN
        frac = (walk_min - config.WALK_FULL_MIN) / span
        return 1.0 - frac * (1.0 - config.WALK_MID_SCORE)
    # MID_MIN..ZERO_MIN → MID_SCORE..0
    span = config.WALK_ZERO_MIN - config.WALK_MID_MIN
    frac = (walk_min - config.WALK_MID_MIN) / span
    return config.WALK_MID_SCORE * (1.0 - frac)


def _house_sub(listing: Listing) -> float:
    return {"house": 1.0, "townhouse": 0.7}.get(listing.property_type, 0.0)


def _two_bathrooms_sub(bathrooms: int | None) -> float:
    if bathrooms is None:
        return 0.3
    if bathrooms >= 2:
        return 1.0
    return 0.4 if bathrooms == 1 else 0.0


def _two_bedrooms_sub(bedrooms: int | None) -> float:
    if bedrooms is None:
        return 0.3
    if bedrooms == 2:
        return 1.0
    if bedrooms > 2:
        return 0.7
    return 0.2  # a 1-bed is a stretch


def _bathtub_sub(listing: Listing) -> float:
    if listing.has_bathtub.value:
        return 1.0
    return 0.3 if listing.has_bathtub.confidence < 0.5 else 0.0


def _rural_sub(dist_town_m: float | None) -> float:
    if dist_town_m is None:
        return config.RURAL_UNKNOWN_SCORE
    return min(dist_town_m / config.RURAL_FULL_DIST_M, 1.0)


def _budget_sub(price: float) -> float:
    if price >= config.BUDGET_CAP_EUR:
        return 0.0
    return (config.BUDGET_CAP_EUR - price) / config.BUDGET_CAP_EUR


def score_listing(
    listing: Listing, weights: dict[str, float] | None = None
) -> tuple[int, dict[str, float]]:
    """Return (match_score 0–100, per-feature weighted-point breakdown)."""
    w = weights or config.WEIGHTS
    subs = {
        "yard": _yard_sub(listing),
        "beach_walk": _beach_walk_sub(listing.walk_min_beach),
        "house": _house_sub(listing),
        "two_bathrooms": _two_bathrooms_sub(listing.bathrooms),
        "two_bedrooms": _two_bedrooms_sub(listing.bedrooms),
        "bathtub": _bathtub_sub(listing),
        "rural": _rural_sub(listing.dist_town_m),
        "budget_headroom": _budget_sub(listing.price_eur_month),
    }
    breakdown = {k: round(w[k] * v, 1) for k, v in subs.items()}
    total = round(sum(breakdown.values()))
    return total, breakdown
