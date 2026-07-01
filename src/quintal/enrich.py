"""Pluggable enrichment chain (geocode → beach walk-time → ruralness).

Phase 3 work. Kept as a bounded, observable chain of steps so the AI review pass can
slot in later as just another enricher. For the step-1 brain, no enrichers run — the
sample data already carries geo fields — and this is a no-op passthrough.
"""

from __future__ import annotations

from typing import Protocol

from .logconf import get_logger
from .schema import Listing

log = get_logger()


class Enricher(Protocol):
    name: str

    def apply(self, listing: Listing) -> None:
        """Mutate the listing in place. Must be bounded and must not raise on empty
        results — a miss falls through to the next step (fallback chain)."""


def enrich_listings(listings: list[Listing], chain: list[Enricher] | None = None) -> list[Listing]:
    """Run each enricher over each listing; a failing step is logged and skipped
    (operational), never fatal. Returns the same list, mutated."""
    chain = chain or []
    for listing in listings:
        for step in chain:
            try:
                step.apply(listing)
            except Exception as exc:  # bounded + observable: log which source failed
                log.warning(
                    "enricher failed",
                    extra={
                        "event": "enrich_step_failed",
                        "ctx_step": step.name,
                        "ctx_id": listing.listing_id,
                        "ctx_err": str(exc),
                    },
                )
    return listings


# Phase-3 enrichers (Nominatim geocode, Overpass beaches, OpenRouteService walk-time,
# ruralness) will implement the Enricher protocol here, each cached by lat/lng.
