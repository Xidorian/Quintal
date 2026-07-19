from quintal.enrich import (
    BeachEnricher,
    GeoClient,
    GeocodeEnricher,
    JsonCache,
    _geocode_queries,
)
from quintal.geo import estimate_walk_minutes, haversine
from quintal.schema import Listing


# --- Pure geo helpers ---
def test_haversine_one_degree_latitude():
    # ~111 km per degree of latitude.
    assert 110_000 < haversine(37.0, -8.0, 38.0, -8.0) < 112_000


def test_haversine_zero():
    assert haversine(37.1, -8.5, 37.1, -8.5) == 0.0


def test_walk_estimate_monotonic_and_signed():
    assert estimate_walk_minutes(0) == 0
    # 1200 m with 1.3 detour at 80 m/min → 19.5 min.
    assert round(estimate_walk_minutes(1200), 1) == 19.5


def test_cache_roundtrip(tmp_path):
    c = JsonCache(tmp_path / "c.json")
    c.set("k", [1, 2])
    c.save()
    assert JsonCache(tmp_path / "c.json").get("k") == [1, 2]


def test_geocode_queries_freguesia_first_and_deduped():
    q = _geocode_queries(
        Listing(price_eur_month=1000, concelho="Loulé", freguesia="Almancil")
    )
    # Freguesia leads for coastal accuracy (concelho centroids inflate beach walk-time
    # in big inland-spanning concelhos); concelho is the reliable backstop.
    assert q[0] == "Almancil, Loulé, Algarve, Portugal"
    assert "Loulé, Algarve, Portugal" in q
    assert len(q) == len(set(q))


def test_geocode_queries_dedupes_when_no_freguesia():
    q = _geocode_queries(Listing(price_eur_month=1000, concelho="Faro"))
    assert q == ["Faro, Algarve, Portugal"]


# --- Enrichers with a fake HTTP session (no network) ---
class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = "ok"

    def json(self):
        return self._payload


class _Session:
    def __init__(self, get_payload=None, post_payload=None):
        self._get, self._post = get_payload, post_payload
        self.get_calls = 0

    def get(self, *a, **k):
        self.get_calls += 1
        return _Resp(self._get)

    def post(self, *a, **k):
        return _Resp(self._post)


def _client(tmp_path, **kw):
    c = GeoClient(tmp_path / "cache.json")
    c._throttle = lambda: None  # no sleeping in tests
    c.session = _Session(**kw)
    return c


def test_geocode_sets_latlng_and_caches(tmp_path):
    client = _client(tmp_path, get_payload=[{"lat": "37.1", "lon": "-8.5"}])
    listing = Listing(price_eur_month=1000, concelho="Portimão", title="T2 em Portimão")
    GeocodeEnricher(client).apply(listing)
    assert (listing.lat, listing.lng) == (37.1, -8.5)
    # Second call hits the cache, not the session.
    calls = client.session.get_calls
    GeocodeEnricher(client).apply(
        Listing(price_eur_month=1, concelho="Portimão", title="T2 em Portimão")
    )
    assert client.session.get_calls == calls


class _RoutedSession:
    """Returns a Nominatim-shaped or Photon-shaped payload based on the called URL."""

    def __init__(self, nominatim, photon):
        self.nominatim, self.photon = nominatim, photon
        self.get_calls = 0

    def get(self, url, *a, **k):
        self.get_calls += 1
        return _Resp(self.nominatim if "nominatim" in url else self.photon)


def test_geocode_falls_back_to_photon_when_nominatim_empty(tmp_path):
    client = GeoClient(tmp_path / "cache.json")
    client._throttle = lambda: None
    # Nominatim returns nothing (rate-limited); Photon resolves (GeoJSON [lon, lat]).
    client.session = _RoutedSession(
        nominatim=[],
        photon={"features": [{"geometry": {"coordinates": [-8.5, 37.1]}}]},
    )
    assert client.geocode("Portimão, Algarve, Portugal") == (37.1, -8.5)
    # It tried Nominatim first, then Photon.
    assert client.session.get_calls == 2


def test_beach_sets_distance_and_walk_estimate(tmp_path):
    # One beach node ~1 km east of the listing.
    client = _client(tmp_path, post_payload={"elements": [{"lat": 37.1, "lon": -8.4886}]})
    listing = Listing(price_eur_month=1000, concelho="Portimão", lat=37.1, lng=-8.5)
    BeachEnricher(client).apply(listing)
    assert listing.dist_beach_m is not None and 900 < listing.dist_beach_m < 1100
    assert listing.walk_min_beach is not None and listing.walk_min_beach > 0


# --- Per-listing geo persistence (QT-027) ---
from quintal.enrich import apply_geo, save_geo  # noqa: E402


def test_save_and_apply_geo_roundtrip(tmp_path):
    path = tmp_path / "geo.json"
    src = Listing(
        source_url="https://x/1", price_eur_month=1000,
        lat=37.1, lng=-8.2, dist_beach_m=500, walk_min_beach=7.0, dist_town_m=1200,
    )
    src.ensure_id()
    assert save_geo([src], path) == 1

    # A fresh, un-enriched copy (same id via same source_url) gets geo from the sidecar.
    fresh = Listing(source_url="https://x/1", price_eur_month=1000)
    assert apply_geo([fresh], path) == 1
    assert fresh.walk_min_beach == 7.0 and fresh.dist_beach_m == 500 and fresh.lat == 37.1


def test_save_geo_skips_unlocated(tmp_path):
    path = tmp_path / "geo.json"
    located = Listing(source_url="a", price_eur_month=1, lat=37.0, lng=-8.0)
    unlocated = Listing(source_url="b", price_eur_month=1)
    assert save_geo([located, unlocated], path) == 1
    import json
    assert list(json.load(open(path)).keys()) == [located.ensure_id()]


def test_apply_geo_does_not_overwrite_fresh(tmp_path):
    path = tmp_path / "geo.json"
    stale = Listing(source_url="a", price_eur_month=1, lat=1.0, lng=2.0, walk_min_beach=99.0)
    save_geo([stale], path)
    fresh = Listing(source_url="a", price_eur_month=1, lat=1.0, lng=2.0, walk_min_beach=5.0)
    apply_geo([fresh], path)
    assert fresh.walk_min_beach == 5.0  # freshly-enriched value wins over the sidecar


def test_apply_geo_noop_without_file(tmp_path):
    assert apply_geo([Listing(source_url="a", price_eur_month=1)], tmp_path / "absent.json") == 0


# --- ORS routed walk-time (QT-035) ---
def test_walk_minutes_uses_ors_when_key_and_dest(tmp_path):
    c = GeoClient(tmp_path / "c.json", ors_key="k")

    class _R:
        def json(self):
            return {"routes": [{"summary": {"duration": 600}}]}  # 600s → 10.0 min

    c.session.post = lambda *a, **k: _R()
    assert c.walk_minutes(37.1, -8.2, 800, dest=(37.11, -8.21)) == 10.0

    # Second call is served from cache — must not hit the network again.
    def _boom(*a, **k):
        raise AssertionError("routed result should be cached")

    c.session.post = _boom
    assert c.walk_minutes(37.1, -8.2, 800, dest=(37.11, -8.21)) == 10.0


def test_walk_minutes_falls_back_on_ors_failure(tmp_path):
    import requests
    c = GeoClient(tmp_path / "c.json", ors_key="k")

    def _fail(*a, **k):
        raise requests.RequestException("down")

    c.session.post = _fail
    assert c.walk_minutes(37.1, -8.2, 1200, dest=(37.11, -8.21)) == round(
        estimate_walk_minutes(1200), 1
    )


def test_walk_minutes_estimate_without_key(tmp_path):
    c = GeoClient(tmp_path / "c.json")  # no ORS key → straight-line estimate
    assert c.walk_minutes(37.1, -8.2, 1200, dest=(37.11, -8.21)) == round(
        estimate_walk_minutes(1200), 1
    )


def test_walk_minutes_uses_cached_route_without_key(tmp_path):
    # The hosted app has no ORS key but ships the route cache — it must still get routed times.
    c = GeoClient(tmp_path / "c.json")  # no key
    c.cache.set(c._walk_key(37.1, -8.2, 37.11, -8.21), 12.3)
    assert c.walk_minutes(37.1, -8.2, 800, dest=(37.11, -8.21)) == 12.3
