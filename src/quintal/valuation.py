"""Relative valuation: is this listing a good deal vs the *current pool*?

Hedonic ridge regression on log(price) when the pool is large enough, otherwise a
peer-median €/m² fallback for thin areas. This is a relative indicator within the
collected pool, NOT an official market appraisal — the UI must say so.
"""

from __future__ import annotations

import math
import statistics

from . import config
from .logconf import get_logger
from .schema import Band, Confidence, Listing

log = get_logger()


def _band(pct: float) -> Band:
    if pct <= -config.VALUATION_THRESHOLD:
        return "undervalued"
    if pct >= config.VALUATION_THRESHOLD:
        return "overpriced"
    return "fair"


def _peer_count(listing: Listing, pool: list[Listing]) -> int:
    return sum(
        1
        for other in pool
        if other is not listing
        and other.bedrooms == listing.bedrooms
        and other.concelho == listing.concelho
    )


def _confidence(peer_count: int, method: str) -> Confidence:
    if peer_count >= config.PEER_MIN_FOR_HIGH:
        base: Confidence = "high"
    elif peer_count >= config.PEER_MIN_FOR_MEDIUM:
        base = "medium"
    else:
        base = "low"
    # A peer-median fallback in a thin area never claims "high".
    if method == "peer_median" and base == "high":
        return "medium"
    return base


def _peer_median_expected(listing: Listing, pool: list[Listing]) -> float | None:
    """Fair rent from the median €/m² of same-bedroom comparables."""
    if not listing.size_m2:
        return None

    def ppm2(other: Listing) -> float:
        return other.price_eur_month / other.size_m2  # type: ignore[operator]

    peers = [
        o
        for o in pool
        if o is not listing
        and o.size_m2
        and o.bedrooms == listing.bedrooms
        and o.concelho == listing.concelho
    ]
    if len(peers) < 3:  # widen out of a thin concelho bucket
        peers = [
            o for o in pool if o is not listing and o.size_m2 and o.bedrooms == listing.bedrooms
        ]
    if not peers:
        return None
    return statistics.median(ppm2(o) for o in peers) * listing.size_m2


def _hedonic_expected(pool: list[Listing]) -> dict[str, float]:
    """Fit ridge on log(price); return {listing_id: expected_rent}. In-sample by design
    (relative indicator); confidence comes from pool/peer counts, not train error."""
    import numpy as np
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    rows = []
    for listing in pool:
        rows.append(
            {
                "id": listing.ensure_id(),
                "price": listing.price_eur_month,
                "log_size": math.log(listing.size_m2) if listing.size_m2 else None,
                "bedrooms": listing.bedrooms,
                "bathrooms": listing.bathrooms,
                "dist_beach_m": listing.dist_beach_m,
                "dist_town_m": listing.dist_town_m,
                "yard": int(bool(listing.has_yard.value)),
                "furnished": int(bool(listing.furnished)),
                "property_type": listing.property_type,
                "concelho": listing.concelho,
            }
        )
    df = pd.DataFrame(rows)
    num = ["log_size", "bedrooms", "bathrooms", "dist_beach_m", "dist_town_m", "yard", "furnished"]
    cat = ["property_type", "concelho"]
    y = np.log(df["price"].to_numpy())

    pre = ColumnTransformer(
        [
            (
                "num",
                Pipeline(
                    [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
                ),
                num,
            ),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat),
        ]
    )
    model = Pipeline([("pre", pre), ("ridge", RidgeCV(alphas=np.logspace(-3, 3, 13)))])
    model.fit(df[num + cat], y)
    expected = np.exp(model.predict(df[num + cat]))
    return {row_id: float(exp) for row_id, exp in zip(df["id"], expected, strict=True)}


def _why(listing: Listing, expected: float, method: str) -> list[str]:
    pct = (listing.price_eur_month - expected) / expected
    bits = [f"asked €{listing.price_eur_month:.0f}, model expects €{expected:.0f} ({pct:+.0%})"]
    if listing.size_m2:
        bits.append(f"{listing.size_m2:.0f} m²")
    if listing.bedrooms is not None:
        bits.append(f"{listing.bedrooms}-bed")
    if listing.has_yard.value:
        bits.append("has yard")
    if listing.dist_beach_m:
        bits.append(f"{listing.dist_beach_m / 1000:.1f} km from beach")
    bits.append(f"[{method}]")
    return bits


def _apply(listing: Listing, expected: float, method: str, peer_count: int) -> None:
    pct = (listing.price_eur_month - expected) / expected
    listing.valuation_expected_eur = round(expected)
    listing.valuation_pct = round(pct, 3)
    listing.valuation_band = _band(pct)
    listing.valuation_method = method
    listing.valuation_confidence = _confidence(peer_count, method)
    listing.valuation_why = _why(listing, expected, method)


def value_pool(listings: list[Listing]) -> list[Listing]:
    """Value every listing against the pool. Mutates and returns the list."""
    pool = [
        listing for listing in listings if listing.price_eur_month and listing.price_eur_month > 0
    ]
    sized = [listing for listing in pool if listing.size_m2]

    expected: dict[str, float] = {}
    method: dict[str, str] = {}
    if len(sized) >= config.MIN_POOL_FOR_MODEL:
        try:
            for lid, exp in _hedonic_expected(sized).items():
                expected[lid], method[lid] = exp, "hedonic"
        except Exception as exc:  # any model failure → graceful fallback
            log.warning(
                "hedonic model failed, using peer-median",
                extra={"event": "valuation_fallback", "ctx_err": str(exc)},
            )

    for listing in pool:
        lid = listing.ensure_id()
        if lid not in expected:
            exp = _peer_median_expected(listing, pool)
            if exp is not None:
                expected[lid], method[lid] = exp, "peer_median"

    for listing in pool:
        lid = listing.ensure_id()
        exp = expected.get(lid)
        if exp is None:
            listing.valuation_method = "none"
            listing.valuation_confidence = "low"
            listing.valuation_why = ["insufficient comparables to value"]
            continue
        _apply(listing, exp, method[lid], _peer_count(listing, pool))
    return listings
