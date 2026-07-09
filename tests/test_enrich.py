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


def test_geocode_queries_concelho_first_and_deduped():
    q = _geocode_queries(
        Listing(price_eur_month=1000, concelho="Loulé", freguesia="Almancil")
    )
    # Concelho leads (only ~16 exist and all resolve → bounded, bulk-safe lookups);
    # freguesia is a later fall-through, only tried if the concelho somehow misses.
    assert q[0] == "Loulé, Algarve, Portugal"
    assert "Almancil, Loulé, Algarve, Portugal" in q
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
