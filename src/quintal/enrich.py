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
PHOTON_URL = "https://photon.komoot.io/api/"  # OSM-based fallback; no bulk rate-limit
ORS_WALK_URL = "https://api.openrouteservice.org/v2/directions/foot-walking"
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
        self._last_ors = 0.0

    def _throttle(self) -> None:
        dt = time.monotonic() - self._last_call
        if dt < 1.0:
            time.sleep(1.0 - dt)
        self._last_call = time.monotonic()

    def _throttle_ors(self) -> None:
        # ORS free tier: 40 directions/min → keep a ≥1.6s gap.
        dt = time.monotonic() - self._last_ors
        if dt < 1.6:
            time.sleep(1.6 - dt)
        self._last_ors = time.monotonic()

    def geocode(self, query: str) -> tuple[float, float] | None:
        key = f"geo:{query}"
        if self.cache.has(key):
            cached = self.cache.get(key)
            return tuple(cached) if cached else None
        # Ordered fallback (resilience principle): Nominatim is precise but bulk-rate-
        # limits us; Photon is OSM-based with no bulk limit. Try each, then give up.
        result = self._geocode_nominatim(query) or self._geocode_photon(query)
        if result is None:
            return None  # don't cache a miss — could be a transient throttle; retry next run
        self.cache.set(key, list(result))
        self.cache.save()  # persist per-lookup so a kill/timeout mid-run keeps progress
        return result

    def _geocode_nominatim(self, query: str) -> tuple[float, float] | None:
        self._throttle()
        try:
            resp = self.session.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1},
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            rows = resp.json()
        except (requests.RequestException, ValueError):
            return None
        if not rows:
            return None
        return (float(rows[0]["lat"]), float(rows[0]["lon"]))

    def _geocode_photon(self, query: str) -> tuple[float, float] | None:
        self._throttle()
        try:
            resp = self.session.get(
                PHOTON_URL,
                params={"q": query, "limit": 1},
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            feats = resp.json().get("features") or []
        except (requests.RequestException, ValueError, AttributeError):
            return None
        if not feats:
            return None
        try:
            lon, lat = feats[0]["geometry"]["coordinates"][:2]  # GeoJSON order: [lon, lat]
        except (KeyError, IndexError, TypeError, ValueError):
            return None
        return (float(lat), float(lon))

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

    def _nearest(
        self, lat: float, lng: float, kind: str
    ) -> tuple[float, tuple[float, float]] | None:
        """(distance_m, (lat, lng)) of the nearest `kind` point, or None."""
        points = self.region_points(kind)
        if not points:
            return None
        plat, plng = min(points, key=lambda p: haversine(lat, lng, p[0], p[1]))
        return haversine(lat, lng, plat, plng), (plat, plng)

    def nearest_beach(self, lat: float, lng: float) -> tuple[float, tuple[float, float]] | None:
        return self._nearest(lat, lng, "beach")

    def nearest_town_m(self, lat: float, lng: float) -> float | None:
        found = self._nearest(lat, lng, "town")
        return found[0] if found else None

    @staticmethod
    def _walk_key(lat: float, lng: float, dlat: float, dlng: float) -> str:
        return f"walk:{round(lat, 4)},{round(lng, 4)}>{round(dlat, 4)},{round(dlng, 4)}"

    def walk_minutes(
        self, lat: float, lng: float, dist_m: float, dest: tuple[float, float] | None = None
    ) -> float:
        """Foot-walking minutes to `dest`: a cached routed value (used even without a key, so
        routes computed once and shipped in the cache serve the hosted app), else a fresh ORS
        route when a key is set, else a straight-line estimate. ORS failures fall back too."""
        if dest is not None:
            key = self._walk_key(lat, lng, dest[0], dest[1])
            cached = self.cache.get(key)
            if cached is not None:
                return cached
            if self.ors_key:
                routed = self._ors_walk_minutes(key, lat, lng, dest[0], dest[1])
                if routed is not None:
                    return routed
        return round(estimate_walk_minutes(dist_m), 1)

    def _ors_walk_minutes(
        self, key: str, lat: float, lng: float, dlat: float, dlng: float
    ) -> float | None:
        """Fetch routed foot-walking minutes from ORS and cache under `key`."""
        self._throttle_ors()
        try:
            resp = self.session.post(
                ORS_WALK_URL,
                json={"coordinates": [[lng, lat], [dlng, dlat]]},  # ORS wants [lon, lat]
                headers={"Authorization": self.ors_key},
                timeout=20,
            )
            duration = resp.json()["routes"][0]["summary"]["duration"]  # seconds
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            return None  # unreachable / rate-limited / no route → caller uses the estimate
        minutes = round(duration / 60, 1)
        self.cache.set(key, minutes)
        self.cache.save()  # persist per-lookup so a kill mid-run keeps progress
        return minutes

    def save(self) -> None:
        self.cache.save()


# --- Enrichers -------------------------------------------------------------------------


def _geocode_queries(listing: Listing) -> list[str]:
    """Freguesia-first candidate queries; fall through until one resolves.

    Freguesia-first gives the most accurate coords: large concelhos (Loulé, Silves)
    stretch from the coast deep inland, so a concelho centroid badly inflates beach
    walk-time for coastal spots — Vilamoura geocoded to inland Loulé town read as
    ~119 min from the sea. The freguesia (Quarteira, Luz, …) lands far closer. This
    was concelho-first only while public Nominatim rate-limited us on freguesia
    misses; the Photon fallback removed that constraint, so a miss now just falls
    through cheaply. Concelho is the reliable backstop; full street/title queries
    rarely resolve, so the title is a last resort.
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
        found = self.client.nearest_beach(listing.lat, listing.lng)
        if found is not None:
            dist, dest = found
            listing.dist_beach_m = round(dist)
            listing.walk_min_beach = self.client.walk_minutes(
                listing.lat, listing.lng, dist, dest
            )


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


# --- Per-listing geo persistence (QT-027) ----------------------------------------------
# The enrichment_cache is keyed by locality; this sidecar persists each listing's *resolved*
# geo by id, so any run (even without --enrich) carries geo, and the hosted app needs no
# network for already-known listings. Layers on top of listings.jsonl (raw-collected truth).

DEFAULT_GEO_PATH = "data/geo.json"
GEO_FIELDS = ("lat", "lng", "dist_beach_m", "walk_min_beach", "dist_town_m")


def _load_geo(path: str | Path) -> dict[str, dict]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def apply_geo(listings: list[Listing], path: str | Path = DEFAULT_GEO_PATH) -> int:
    """Fill missing geo fields on listings from the persisted sidecar (keyed by id).

    Only fills gaps — never overwrites geo already set by a fresh enrich this run. No-op
    when the sidecar is absent. Returns how many listings were touched.
    """
    store = _load_geo(path)
    if not store:
        return 0
    touched = 0
    for listing in listings:
        geo = store.get(listing.ensure_id())
        if not geo:
            continue
        for field in GEO_FIELDS:
            if geo.get(field) is not None and getattr(listing, field) is None:
                setattr(listing, field, geo[field])
        touched += 1
    return touched


def save_geo(listings: list[Listing], path: str | Path = DEFAULT_GEO_PATH) -> int:
    """Persist each located listing's geo fields by id, merging into any existing sidecar.

    Returns how many located listings were written.
    """
    store = _load_geo(path)
    saved = 0
    for listing in listings:
        if listing.lat is None or listing.lng is None:
            continue
        store[listing.ensure_id()] = {field: getattr(listing, field) for field in GEO_FIELDS}
        saved += 1
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    return saved


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
