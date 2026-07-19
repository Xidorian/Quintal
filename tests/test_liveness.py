"""QT-026 — delisted-listing detection."""

import json

from quintal import liveness
from quintal.schema import Listing


def test_roundtrip(tmp_path):
    path = tmp_path / "delisted.json"
    liveness.save({"https://imv/1": "410"}, path)
    assert liveness.load(path) == {"https://imv/1": "410"}


def test_drop_delisted_removes_gone_keeps_live(tmp_path):
    path = tmp_path / "delisted.json"
    liveness.save({"https://imv/gone": "410"}, path)
    listings = [
        Listing(source_url="https://imv/gone", price_eur_month=1000),
        Listing(source_url="https://imv/live", price_eur_month=1200),
        Listing(source_url=None, price_eur_month=900),  # unknown url is never dropped
    ]
    kept, dropped = liveness.drop_delisted(listings, path)
    assert dropped == 1
    assert [x.source_url for x in kept] == ["https://imv/live", None]


def test_drop_delisted_noop_without_set(tmp_path):
    listings = [Listing(source_url="x", price_eur_month=1000)]
    kept, dropped = liveness.drop_delisted(listings, tmp_path / "absent.json")
    assert dropped == 0 and kept == listings


def test_probe_records_only_gone_and_skips_idealista(monkeypatch, tmp_path):
    listings_path = tmp_path / "listings.jsonl"
    rows = [
        {"source": "imovirtual", "source_url": "https://imv/gone", "price_eur_month": 1000},
        {"source": "imovirtual", "source_url": "https://imv/live", "price_eur_month": 1000},
        {"source": "imovirtual", "source_url": "https://imv/flaky", "price_eur_month": 1000},
        {"source": "idealista", "source_url": "https://ide/x", "price_eur_month": 1000},
    ]
    listings_path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    codes = {"https://imv/gone": 410, "https://imv/live": 200}

    class _Resp:
        def __init__(self, code):
            self.status_code = code

    class _Session:
        headers: dict = {}

        def get(self, url, **kwargs):
            if url == "https://imv/flaky":
                raise liveness.requests.RequestException("boom")
            return _Resp(codes[url])

    monkeypatch.setattr(liveness.requests, "Session", lambda: _Session())
    stats = liveness.probe(listings_path, tmp_path / "d.json", delay=0)

    assert stats.get("gone") == 1  # only the 410
    assert stats.get("live") == 1
    assert stats.get("error") == 1  # the flaky one, NOT recorded as delisted
    assert stats.get("skip") == 1  # idealista never probed
    assert liveness.load(tmp_path / "d.json") == {"https://imv/gone": "410"}


def test_probe_skips_known_gone(monkeypatch, tmp_path):
    listings_path = tmp_path / "listings.jsonl"
    row = {"source": "imovirtual", "source_url": "https://imv/gone", "price_eur_month": 1}
    listings_path.write_text(json.dumps(row), encoding="utf-8")
    liveness.save({"https://imv/gone": "410"}, tmp_path / "d.json")

    class _Session:
        headers: dict = {}

        def get(self, url, **kwargs):
            raise AssertionError("should not fetch a known-gone url")

    monkeypatch.setattr(liveness.requests, "Session", lambda: _Session())
    stats = liveness.probe(listings_path, tmp_path / "d.json", delay=0)
    assert stats.get("known-gone") == 1
