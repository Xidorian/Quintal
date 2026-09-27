"""QT-026 — delisted-listing detection."""

import json

import pytest

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


def _store(tmp_path, rows):
    p = tmp_path / "listings.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def test_cull_absent_marks_absent_only_for_site(tmp_path):
    store = _store(
        tmp_path,
        [
            {"source": "idealista", "source_url": "https://ide/a"},
            {"source": "idealista", "source_url": "https://ide/b"},
            {"source": "idealista", "source_url": "https://ide/gone"},  # not in pull
            {"source": "imovirtual", "source_url": "https://imv/x"},  # other site, untouched
        ],
    )
    path = tmp_path / "d.json"
    culled, resurrected = liveness.cull_absent(
        "idealista", {"https://ide/a", "https://ide/b"}, store, path
    )
    assert (culled, resurrected) == (1, 0)
    assert liveness.load(path) == {"https://ide/gone": "absent"}  # imv/x never touched


def test_cull_absent_resurrects_returning_url(tmp_path):
    store = _store(tmp_path, [{"source": "idealista", "source_url": "https://ide/a"}])
    path = tmp_path / "d.json"
    liveness.save({"https://ide/a": "absent"}, path)  # was culled last week
    culled, resurrected = liveness.cull_absent("idealista", {"https://ide/a"}, store, path)
    assert (culled, resurrected) == (0, 1)
    assert liveness.load(path) == {}  # back in the search → un-culled


def test_cull_absent_keeps_real_gone_sticky(tmp_path):
    # A 404/410 from the real probe must never be overwritten or resurrected by the cull.
    store = _store(tmp_path, [{"source": "idealista", "source_url": "https://ide/dead"}])
    path = tmp_path / "d.json"
    liveness.save({"https://ide/dead": "410"}, path)
    culled, resurrected = liveness.cull_absent("idealista", {"https://ide/dead"}, store, path)
    assert (culled, resurrected) == (0, 0)  # present in pull, but 410 stays sticky
    assert liveness.load(path) == {"https://ide/dead": "410"}


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


# --- Cull plausibility guard (the destructive-step half of the selector check) ----------
# `--cull` trusts a pull to be the complete current search, so a collapsed pull — moved card
# selector, CAPTCHA page, half-finished paging, wrong file — would delist most of the live pool
# in one command. The caller contract used to be human-remembered only; it is now checked.
# alarm-proved 2026-09-26: with the guard removed, test_cull_refused_when_the_pull_collapsed
# goes green-with-9-culled (i.e. the pool is wiped), which is the failure it exists to stop.
def _many(site, n, prefix="https://ide/"):
    return [{"source": site, "source_url": f"{prefix}{i}"} for i in range(n)]


def test_cull_refused_when_the_pull_collapsed(tmp_path):
    store = _store(tmp_path, _many("idealista", 10))
    path = tmp_path / "d.json"
    with pytest.raises(liveness.CullRefused) as exc:
        liveness.cull_absent("idealista", {"https://ide/0"}, store, path)
    assert "refusing to cull" in str(exc.value)
    # Raised before any write: the sidecar must not even exist yet.
    assert not path.exists(), "a refused cull must not touch the delisted sidecar"


def test_force_cull_overrides_the_floor(tmp_path):
    store = _store(tmp_path, _many("idealista", 10))
    path = tmp_path / "d.json"
    culled, resurrected = liveness.cull_absent(
        "idealista", {"https://ide/0"}, store, path, force=True
    )
    assert (culled, resurrected) == (9, 0)


def test_cull_allowed_at_real_world_churn(tmp_path):
    # The worst churn actually observed was the 22-day 2026-09-26 gap: 62% of live Norte
    # idealista listings re-surfaced. The floor must clear that comfortably.
    store = _store(tmp_path, _many("idealista", 100))
    path = tmp_path / "d.json"
    pulled = {f"https://ide/{i}" for i in range(62)}
    culled, _ = liveness.cull_absent("idealista", pulled, store, path)
    assert culled == 38


def test_cull_coverage_ignores_already_delisted_listings(tmp_path):
    """The store keeps every listing it ever saw, so most of a mature store is long dead and
    can never be re-surfaced. Measuring coverage against all of them would make a perfectly
    healthy pull look collapsed and block every future cull."""
    store = _store(tmp_path, _many("idealista", 100))
    path = tmp_path / "d.json"
    # 90 were culled in earlier weeks; only 10 are live, and the pull re-surfaces 9 of them.
    liveness.save({f"https://ide/{i}": "absent" for i in range(90)}, path)
    pulled = {f"https://ide/{i}" for i in range(90, 99)}
    culled, _ = liveness.cull_absent("idealista", pulled, store, path)
    assert culled == 1  # only https://ide/99, the one live listing that really did go


def test_cull_guard_is_per_site(tmp_path):
    # A big imovirtual store must not drag the idealista coverage calculation down.
    store = _store(tmp_path, _many("idealista", 4) + _many("imovirtual", 500, "https://imv/"))
    path = tmp_path / "d.json"
    culled, _ = liveness.cull_absent(
        "idealista", {f"https://ide/{i}" for i in range(3)}, store, path
    )
    assert culled == 1
