"""Collapse the same flat appearing across sites/agencies into one canonical listing.

Attribute rule: same concelho AND bedrooms AND size within ±5% AND price within ±5%.
Private-landlord listing wins as canonical over an agency repost. (Perceptual photo-hash
is a later optional enhancement — attribute matching handles most dupes without photos.)
"""

from __future__ import annotations

from . import config
from .schema import Listing


def _within(a: float | None, b: float | None, tol: float) -> bool:
    if a is None or b is None:
        return False
    if a == 0 or b == 0:
        return a == b
    return abs(a - b) / max(a, b) <= tol


def _same_flat(x: Listing, y: Listing) -> bool:
    return (
        x.concelho == y.concelho
        and x.bedrooms == y.bedrooms
        and _within(x.size_m2, y.size_m2, config.DEDUP_SIZE_TOL)
        and _within(x.price_eur_month, y.price_eur_month, config.DEDUP_PRICE_TOL)
    )


def _pick_canonical(group: list[Listing]) -> Listing:
    # Private landlord wins; otherwise the cheaper listing.
    return sorted(
        group, key=lambda listing: (not listing.is_private_landlord, listing.price_eur_month)
    )[0]


def dedup(listings: list[Listing]) -> list[Listing]:
    """Return canonical listings only; each carries `also_listed_at` of its dupes."""
    for listing in listings:
        listing.ensure_id()

    # Bucket by cheap key first, then pairwise within the bucket (avoids O(n²) globally).
    buckets: dict[tuple[str, int | None], list[Listing]] = {}
    for listing in listings:
        buckets.setdefault((listing.concelho, listing.bedrooms), []).append(listing)

    canonicals: list[Listing] = []
    for bucket in buckets.values():
        clusters: list[list[Listing]] = []
        for listing in bucket:
            for cluster in clusters:
                if _same_flat(cluster[0], listing):
                    cluster.append(listing)
                    break
            else:
                clusters.append([listing])

        for cluster in clusters:
            canonical = _pick_canonical(cluster)
            others = [c for c in cluster if c is not canonical]
            urls = [c.source_url for c in others if c.source_url]
            canonical.also_listed_at = sorted(set(canonical.also_listed_at + urls))
            for dup in others:
                dup.duplicate_of = canonical.listing_id
            canonicals.append(canonical)
    return canonicals
