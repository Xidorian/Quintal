"""Enrichment chain (geocode → beach walk-time → ruralness).

Each step is bounded, cached by lat/lng, and observable — a miss falls through to the
next step rather than crashing (resilience principle). Keyless by default: Nominatim for
geocoding, Overpass for beaches/towns, and a straight-line walking estimate. An
OpenRouteService key (optional) upgrades the walk time to real routed minutes.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

from .geo import estimate_walk_minutes, haversine
from .logconf import get_logger
from .schema import Listing

log = get_logger()

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
PHOTON_URL = "https://photon.komoot.io/api/"  # OSM-based fallback; no bulk rate-limit
ORS_WALK_URL = "https://api.openrouteservice.org/v2/directions/foot-walking"
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
USER_AGENT = os.environ.get("NOMINATIM_USER_AGENT", "quintal-rental-finder (xidorian@gmail.com)")

# Fetch all points of a kind for the region once (1 call/kind), then nearest is local.
# `beach` (natural=beach) covers BOTH ocean and river beaches — OSM tags praias fluviais
# the same way — so the same axis serves the Algarve coast and the Douro river. `green` is
# small, centroid-accurate green space you can walk a dog to (parks/gardens/reserves); large
# forests are deliberately excluded (their centroid misleads — the `rural` axis covers wild
# nature instead).
_REGION_QUERIES = {
    "beach": "node[natural=beach]({bbox});way[natural=beach]({bbox})",
    "green": (
        "way[leisure=park]({bbox});way[leisure=garden]({bbox});"
        "way[leisure=nature_reserve]({bbox});way[leisure=dog_park]({bbox})"
    ),
    "town": "node[place~'^(town|city|village)$']({bbox})",
}


@dataclass(frozen=True)
class Region:
    """A search region: its OSM bounding box and the geocode-query suffix that
    disambiguates place names to it. `bbox` is (south, west, north, east)."""

    name: str
    bbox: tuple[float, float, float, float]
    geocode_suffix: str


# Faro district (Algarve coast) and the Norte expansion (Porto + Douro + Minho, spanning the
# Porto/Braga/Viana do Castelo/Vila Real/Viseu districts). Norte places carry a plain
# ", Portugal" suffix — freguesia+concelho is specific enough, and appending a wrong sub-region
# (as ", Algarve" once was, hardcoded) would mislocate every northern listing.
ALGARVE = Region("algarve", (36.95, -9.0, 37.55, -7.35), "Algarve, Portugal")
NORTE = Region("norte", (40.4, -8.95, 42.2, -6.85), "Portugal")
REGIONS: dict[str, Region] = {r.name: r for r in (ALGARVE, NORTE)}
ALGARVE_BBOX = ALGARVE.bbox  # back-compat alias


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

    def __init__(
        self, cache_path: str | Path, *, ors_key: str | None = None, region: Region = ALGARVE
    ) -> None:
        self.cache = JsonCache(cache_path)
        self.session = requests.Session()
        self.ors_key = ors_key
        self.region = region
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
        """All (lat, lng) of `kind` in the region, fetched once and cached. Keyed by region
        name so distinct regions don't clobber each other even in a shared cache file."""
        key = f"region:{self.region.name}:{kind}"
        if self.cache.has(key):
            return [tuple(p) for p in self.cache.get(key)]
        bbox = ",".join(str(x) for x in self.region.bbox)
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

    def nearest_green(self, lat: float, lng: float) -> tuple[float, tuple[float, float]] | None:
        return self._nearest(lat, lng, "green")

    def nearest_town_m(self, lat: float, lng: float) -> float | None:
        found = self._nearest(lat, lng, "town")
        return found[0] if found else None

    # Portuguese concelho (município) at a point. Nominatim spreads it across fields —
    # `municipality` when present (else `city`/`town`), while `county` is unreliable
    # (sometimes the distrito). Verified against Porto/Maia/Gaia/Régua/Alijó/Baião. Cached
    # by rounded coords: same freguesia → same geocoded centroid → one reverse call.
    def reverse_concelho(self, lat: float, lng: float) -> str | None:
        key = f"rev:{round(lat, 4)},{round(lng, 4)}"
        if self.cache.has(key):
            return self.cache.get(key) or None
        self._throttle()
        try:
            resp = self.session.get(
                NOMINATIM_REVERSE_URL,
                params={"lat": lat, "lon": lng, "format": "json", "zoom": 10, "addressdetails": 1},
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            addr = resp.json().get("address", {})
        except (requests.RequestException, ValueError, AttributeError):
            return None  # don't cache a transient failure — retry next run
        concelho = addr.get("municipality") or addr.get("city") or addr.get("town")
        if not concelho:
            return None
        self.cache.set(key, concelho)
        self.cache.save()  # persist per-lookup so a kill mid-run keeps progress
        return concelho

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


# Some Idealista Norte cards put a street/title fragment where a locality should be
# ("Apartamento T2 na Rua da Areosa", "…localizado em Santo Ildefonso Porto"). Such a
# string never geocodes AND — being unique per listing — is never cached, so it re-hits
# the geocoder for every listing. Drop these before they cost a call.
_JUNK_LOCALITY = re.compile(
    r"apartamento|moradia|arrenda|localizado|quartos|\bT\d|\bRua\b|\bAvenida\b|\bTravessa\b",
    re.IGNORECASE,
)


def _place_ok(name: str | None) -> bool:
    return bool(name) and not _JUNK_LOCALITY.search(name)


# Idealista Norte titles embed the locality after a preposition ("Apartamento T2 em
# Pedrouços", "Moradia independente em Mateus"). When the parsed concelho/freguesia is junk
# (no comma in the title → the whole title became the concelho), recover the place from the
# text after the LAST em/na/no/nas/nos, then its most specific comma-chunk.
_TITLE_LOCALITY = re.compile(r".*\b(?:em|na|no|nas|nos)\s+(.+)$", re.IGNORECASE)


def _title_locality(title: str | None) -> str | None:
    m = _TITLE_LOCALITY.search(title or "")
    if not m:
        return None
    loc = m.group(1).split(",")[-1].strip()
    return loc or None


def _geocode_queries(listing: Listing, suffix: str = "Algarve, Portugal") -> list[str]:
    """Freguesia-first candidate queries; fall through until one resolves.

    Freguesia-first gives the most accurate coords: large concelhos (Loulé, Silves)
    stretch from the coast deep inland, so a concelho centroid badly inflates beach
    walk-time for coastal spots — Vilamoura geocoded to inland Loulé town read as
    ~119 min from the sea. The freguesia (Quarteira, Luz, …) lands far closer. This
    was concelho-first only while public Nominatim rate-limited us on freguesia
    misses; the Photon fallback removed that constraint, so a miss now just falls
    through cheaply. Concelho is the reliable backstop; full street/title queries
    rarely resolve, so the title is a last resort. `suffix` scopes the place name to
    the region (e.g. "Algarve, Portugal" vs a plain "Portugal" for the Norte).
    """
    queries = []
    freg_ok = _place_ok(listing.freguesia)
    conc_ok = _place_ok(listing.concelho)
    if freg_ok and listing.freguesia != listing.concelho:
        # A junk concelho would poison "freguesia, concelho" — pair only with a clean concelho.
        queries.append(
            f"{listing.freguesia}, {listing.concelho}, {suffix}"
            if conc_ok
            else f"{listing.freguesia}, {suffix}"
        )
    if conc_ok:
        queries.append(f"{listing.concelho}, {suffix}")
    # No clean parsed locality → recover it from the title's "…em <place>" tail. This rescues
    # the ~270 Idealista Norte cards (real T2/T3s) whose comma-less title became the concelho.
    if not (freg_ok or conc_ok):
        loc = _title_locality(listing.title)
        if loc and _place_ok(loc):
            queries.append(f"{loc}, {suffix}")
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
        for query in _geocode_queries(listing, self.client.region.geocode_suffix):
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


class GreenEnricher:
    name = "green"

    def __init__(self, client: GeoClient) -> None:
        self.client = client

    def apply(self, listing: Listing) -> None:
        if listing.lat is None or listing.lng is None:
            return
        found = self.client.nearest_green(listing.lat, listing.lng)
        if found is not None:
            dist, dest = found
            listing.dist_green_m = round(dist)
            listing.walk_min_green = self.client.walk_minutes(
                listing.lat, listing.lng, dist, dest
            )


class ConcelhoEnricher:
    """Overwrite an Idealista concelho with the reverse-geocoded município.

    Idealista embeds location in the card title, and outside the Algarve that title ends
    in the *freguesia* (Paranhos, Cedofeita) or a generic string — so the parsed concelho is
    wrong, which pollutes valuation peer-buckets and the app's per-area sentiment. Imovirtual
    usually carries a clean concelho, but a minority of cards whose address line didn't
    extract fall back to the title too. So once a listing is located, reverse-geocode the
    authoritative concelho for **Idealista (always)** and **any card whose parsed concelho is
    junk**, while leaving a clean non-Idealista concelho untouched. Skips the Algarve region:
    its title-parse is reliable and that pool is live — don't disturb it.
    """

    name = "concelho"

    def __init__(self, client: GeoClient) -> None:
        self.client = client

    def apply(self, listing: Listing) -> None:
        if listing.lat is None or listing.lng is None:
            return
        if self.client.region.name == "algarve":
            return
        if listing.source != "idealista" and _place_ok(listing.concelho):
            return  # a clean, non-Idealista (Imovirtual) concelho — trust it
        concelho = self.client.reverse_concelho(listing.lat, listing.lng)
        if concelho:
            listing.concelho = concelho


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
    cache_path: str | Path, *, ors_key: str | None = None, region: Region = ALGARVE
) -> tuple[GeoClient, list[Enricher]]:
    client = GeoClient(cache_path, ors_key=ors_key, region=region)
    return client, [
        GeocodeEnricher(client),
        ConcelhoEnricher(client),  # after geocode (needs coords), before valuation buckets
        BeachEnricher(client),
        GreenEnricher(client),
        RuralnessEnricher(client),
    ]


# --- Per-listing geo persistence (QT-027) ----------------------------------------------
# The enrichment_cache is keyed by locality; this sidecar persists each listing's *resolved*
# geo by id, so any run (even without --enrich) carries geo, and the hosted app needs no
# network for already-known listings. Layers on top of listings.jsonl (raw-collected truth).

DEFAULT_GEO_PATH = "data/geo.json"
GEO_FIELDS = (
    "lat",
    "lng",
    "dist_beach_m",
    "walk_min_beach",
    "dist_green_m",
    "walk_min_green",
    "dist_town_m",
    "concelho",
)
# Geo coords/distances are filled only when missing (a fresh enrich this run wins). But the
# persisted concelho is the *authoritative* reverse-geocoded value (ConcelhoEnricher) — it
# must replace the parsed freguesia-level/junk value even on a plain, no-enrich load.
GEO_OVERWRITE_FIELDS = frozenset({"concelho"})


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

    Fills gaps — never overwrites geo already set by a fresh enrich this run — except the
    authoritative reverse-geocoded concelho, which replaces the parsed value. No-op when the
    sidecar is absent. Returns how many listings were touched.
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
            if geo.get(field) is None:
                continue
            if field in GEO_OVERWRITE_FIELDS or getattr(listing, field) is None:
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
