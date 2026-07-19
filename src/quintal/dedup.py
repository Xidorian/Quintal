"""Collapse the same flat appearing across sites/agencies into one canonical listing.

Two passes:
1. **Attribute** — same concelho AND bedrooms AND size within ±5% AND price within ±5%.
2. **Photo** (QT-032) — thumbnails match (dHash) AND bedrooms + price corroborate. Catches
   dupes the attribute rule misses because the concelho was parsed differently across sites
   (freguesia vs concelho, e.g. Almancil vs Loulé). Guarded so a shared generic photo can't
   merge two genuinely different flats.

Private-landlord listing wins as canonical over an agency repost.
"""

from __future__ import annotations

from . import config
from .photo_hash import dhash, hamming
from .photos import photo_path
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


def _photo_dup(x: Listing, y: Listing, hashes: dict[str, int]) -> bool:
    """Same flat by matching thumbnail — but only with corroborating bedrooms + price, since
    unrelated listings sometimes share a generic photo (dHash distance 0)."""
    hx, hy = hashes.get(x.listing_id), hashes.get(y.listing_id)
    if hx is None or hy is None:
        return False
    return (
        hamming(hx, hy) <= config.DEDUP_PHASH_MAX_DIST
        and x.bedrooms == y.bedrooms
        and _within(x.price_eur_month, y.price_eur_month, config.DEDUP_PHASH_PRICE_TOL)
    )


def _pick_canonical(group: list[Listing]) -> Listing:
    # Private landlord wins; otherwise the cheaper listing.
    return sorted(
        group, key=lambda listing: (not listing.is_private_landlord, listing.price_eur_month)
    )[0]


def _collapse(cluster: list[Listing]) -> Listing:
    """Pick the canonical of a duplicate cluster; fold the rest into its `also_listed_at`."""
    canonical = _pick_canonical(cluster)
    also = set(canonical.also_listed_at)
    for other in cluster:
        if other is canonical:
            continue
        also.update(other.also_listed_at)  # union dupes found in an earlier pass
        if other.source_url:
            also.add(other.source_url)
        other.duplicate_of = canonical.listing_id
    canonical.also_listed_at = sorted(also)
    return canonical


def _cluster(items: list[Listing], is_dup) -> list[Listing]:
    """Greedy single-link clustering within a bucket → one canonical per cluster."""
    clusters: list[list[Listing]] = []
    for item in items:
        for cluster in clusters:
            if is_dup(cluster[0], item):
                cluster.append(item)
                break
        else:
            clusters.append([item])
    return [_collapse(c) for c in clusters]


def _photo_hashes(listings: list[Listing]) -> dict[str, int]:
    out: dict[str, int] = {}
    for listing in listings:
        path = photo_path(listing.listing_id)
        if path.exists():
            h = dhash(path)
            if h is not None:
                out[listing.listing_id] = h
    return out


def dedup(listings: list[Listing], photo_hashes: dict[str, int] | None = None) -> list[Listing]:
    """Return canonical listings only; each carries `also_listed_at` of its dupes."""
    for listing in listings:
        listing.ensure_id()

    # Pass 1 — attribute match, bucketed by the cheap (concelho, bedrooms) key.
    buckets: dict[tuple[str, int | None], list[Listing]] = {}
    for listing in listings:
        buckets.setdefault((listing.concelho, listing.bedrooms), []).append(listing)
    canonicals: list[Listing] = []
    for bucket in buckets.values():
        canonicals.extend(_cluster(bucket, _same_flat))

    # Pass 2 — photo match across concelhos, bucketed by bedrooms (dupes share a bed count).
    if photo_hashes is None:
        photo_hashes = _photo_hashes(canonicals)
    if not photo_hashes:
        return canonicals
    by_beds: dict[int | None, list[Listing]] = {}
    for listing in canonicals:
        by_beds.setdefault(listing.bedrooms, []).append(listing)
    merged: list[Listing] = []
    for bucket in by_beds.values():
        merged.extend(_cluster(bucket, lambda a, b: _photo_dup(a, b, photo_hashes)))
    return merged
