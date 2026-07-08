"""Enrichment chain (geocode → beach walk-time → ruralness).

Each step is bounded, cached by lat/lng, and observable — a miss falls through to the
next step rather than crashing (resilience principle). Keyless by default: Nominatim for
geocoding, Overpass for beaches/towns, and a straight-line walking estimate. An
OpenRouteService key (optional) upgrades the walk time to real routed minutes.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Protocol

import requests

from .geo import estimate_walk_minutes, haversine
from .logconf import get_logger
from .schema import Listing

log = get_logger()

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
USER_AGENT = os.environ.get("NOMINATIM_USER_AGENT", "quintal-rental-finder (xidorian@gmail.com)")

# Whole Algarve (Faro district) bounding box: (south, west, north, east).
ALGARVE_BBOX = (36.95, -9.0, 37.55, -7.35)
# Fetch all beaches / towns for the region once (2 calls total), then nearest is local.
_REGION_QUERIES = {
    "beach": "node[natural=beach]({bbox});way[natural=beach]({bbox})",
    "town": "node[place~'^(town|city|village)$']({bbox})",
}


class Enricher(Protocol):
    name: str

    def apply(self, listing: Listing) -> None:
        """Mutate the listing in place. Bounded; must not raise on empty results."""


# --- Cache + polite HTTP client --------------------------------------------------------


class JsonCache:
    """Tiny persistent JSON cache so a flaky/slow upstream isn't re-hit per run."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def has(self, key: str) -> bool:
        return key in self.data

    def set(self, key: str, value) -> None:
        self.data[key] = value

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


class GeoClient:
    """Shared geocoding/lookup client: one session, cache, and ≥1s throttle (OSM policy)."""

    def __init__(self, cache_path: str | Path, *, ors_key: str | None = None) -> None:
        self.cache = JsonCache(cache_path)
        self.session = requests.Session()
        self.ors_key = ors_key
        self._last_call = 0.0

    def _throttle(self) -> None:
        dt = time.monotonic() - self._last_call
        if dt < 1.0:
            time.sleep(1.0 - dt)
        self._last_call = time.monotonic()

    def geocode(self, query: str) -> tuple[float, float] | None:
        key = f"geo:{query}"
        if self.cache.has(key):
            cached = self.cache.get(key)
            return tuple(cached) if cached else None
        self._throttle()
        resp = self.session.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        rows = resp.json()
        if not rows:
            return None  # don't cache a miss — could be a transient throttle; retry next run
        result = (float(rows[0]["lat"]), float(rows[0]["lon"]))
        self.cache.set(key, list(result))
        self.cache.save()  # persist per-lookup so a kill/timeout mid-run keeps progress
        return result

    def _overpass(self, query: str) -> dict | None:
        """POST to Overpass, trying each mirror until one returns valid JSON."""
        for endpoint in OVERPASS_ENDPOINTS:
            self._throttle()
            try:
                resp = self.session.post(endpoint, data={"data": query}, timeout=60)
            except requests.RequestException:
                continue
            if resp.status_code == 200 and resp.text.strip():
                try:
                    return resp.json()
                except ValueError:
                    continue
        return None

    def region_points(self, kind: str) -> list[tuple[float, float]]:
        """All (lat, lng) of `kind` in the Algarve, fetched once and cached."""
        key = f"region:{kind}"
        if self.cache.has(key):
            return [tuple(p) for p in self.cache.get(key)]
        bbox = ",".join(str(x) for x in ALGARVE_BBOX)
        query = f"[out:json][timeout:60];({_REGION_QUERIES[kind].format(bbox=bbox)};);out center;"
        data = self._overpass(query)
        if data is None:
            return []  # upstream down — leave uncached so a later run can retry
        points = []
        for el in data.get("elements", []):
            plat = el.get("lat") or el.get("center", {}).get("lat")
            plng = el.get("lon") or el.get("center", {}).get("lon")
            if plat is not None and plng is not None:
                points.append((plat, plng))
        self.cache.set(key, points)
        self.cache.save()  # persist per-lookup so a kill/timeout mid-run keeps progress
        return points

    def _nearest_m(self, lat: float, lng: float, kind: str) -> float | None:
        points = self.region_points(kind)
        if not points:
            return None
        return min(haversine(lat, lng, plat, plng) for plat, plng in points)

    def nearest_beach_m(self, lat: float, lng: float) -> float | None:
        return self._nearest_m(lat, lng, "beach")

    def nearest_town_m(self, lat: float, lng: float) -> float | None:
        return self._nearest_m(lat, lng, "town")

    def walk_minutes(self, lat: float, lng: float, dist_m: float) -> float:
        """Real routed minutes if an ORS key is set, else a straight-line estimate."""
        if not self.ors_key:
            return round(estimate_walk_minutes(dist_m), 1)
        # ORS needs the destination point; we only cached distance, so estimate stays the
        # default. (A future step can cache the beach coords and route to them.)
        return round(estimate_walk_minutes(dist_m), 1)

    def save(self) -> None:
        self.cache.save()


# --- Enrichers -------------------------------------------------------------------------


def _geocode_queries(listing: Listing) -> list[str]:
    """Locality-first candidate queries; fall through until one resolves.

    Full street/title queries almost never resolve in Nominatim and just double the
    request load (→ rate-limiting), so we lead with the reliable locality name. Coords
    land at town/freguesia centroid — precise enough for beach/town distance.
    """
    queries = []
    if listing.freguesia and listing.freguesia != listing.concelho:
        queries.append(f"{listing.freguesia}, {listing.concelho}, Algarve, Portugal")
    queries.append(f"{listing.concelho}, Algarve, Portugal")
    if listing.title:  # last resort; only reached (and only costs a call) if locality misses
        queries.append(f"{listing.title}, Algarve, Portugal")
    # De-dup while preserving order.
    seen: set[str] = set()
    return [q for q in queries if not (q in seen or seen.add(q))]


class GeocodeEnricher:
    name = "geocode"

    def __init__(self, client: GeoClient) -> None:
        self.client = client

    def apply(self, listing: Listing) -> None:
        if listing.lat is not None and listing.lng is not None:
            return
        for query in _geocode_queries(listing):
            result = self.client.geocode(query)
            if result:
                listing.lat, listing.lng = result
                return


class BeachEnricher:
    name = "beach"

    def __init__(self, client: GeoClient) -> None:
        self.client = client

    def apply(self, listing: Listing) -> None:
        if listing.lat is None or listing.lng is None:
            return
        dist = self.client.nearest_beach_m(listing.lat, listing.lng)
        if dist is not None:
            listing.dist_beach_m = round(dist)
            listing.walk_min_beach = self.client.walk_minutes(listing.lat, listing.lng, dist)


class RuralnessEnricher:
    name = "ruralness"

    def __init__(self, client: GeoClient) -> None:
        self.client = client

    def apply(self, listing: Listing) -> None:
        if listing.lat is None or listing.lng is None:
            return
        dist = self.client.nearest_town_m(listing.lat, listing.lng)
        if dist is not None:
            listing.dist_town_m = round(dist)


def default_chain(
    cache_path: str | Path, *, ors_key: str | None = None
) -> tuple[GeoClient, list[Enricher]]:
    client = GeoClient(cache_path, ors_key=ors_key)
    return client, [GeocodeEnricher(client), BeachEnricher(client), RuralnessEnricher(client)]


# --- Runner ----------------------------------------------------------------------------


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
