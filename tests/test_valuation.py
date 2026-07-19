from quintal.schema import Listing
from quintal.valuation import _band, value_pool


def test_band_thresholds():
    assert _band(-0.2) == "undervalued"
    assert _band(0.0) == "fair"
    assert _band(0.2) == "overpriced"


def test_peer_median_flags_overpriced_in_small_pool():
    # Small pool → peer-median fallback. Four 2-bed 100 m² flats in Faro at ~€10/m²,
    # plus one asking way more for the same thing.
    pool = [
        Listing(price_eur_month=1000, size_m2=100, bedrooms=2, concelho="Faro", source_url=f"u{i}")
        for i in range(4)
    ]
    pool.append(
        Listing(price_eur_month=1500, size_m2=100, bedrooms=2, concelho="Faro", source_url="pricey")
    )
    value_pool(pool)
    pricey = pool[-1]
    assert pricey.valuation_method == "peer_median"
    assert pricey.valuation_band == "overpriced"
    assert pricey.valuation_pct > 0.1


def test_hedonic_used_for_large_pool():
    # >= MIN_POOL_FOR_MODEL sized listings with price ~ €12/m² → hedonic path.
    pool = [
        Listing(
            price_eur_month=12 * size,
            size_m2=size,
            bedrooms=2,
            bathrooms=1,
            concelho="Loulé",
            property_type="apartment",
            source_url=f"h{i}",
        )
        for i, size in enumerate(range(60, 120))
    ]
    # One clearly overpriced outlier.
    pool.append(
        Listing(
            price_eur_month=12 * 90 * 1.6,
            size_m2=90,
            bedrooms=2,
            bathrooms=1,
            concelho="Loulé",
            property_type="apartment",
            source_url="out",
        )
    )
    value_pool(pool)
    assert any(listing.valuation_method == "hedonic" for listing in pool)
    outlier = next(listing for listing in pool if listing.source_url == "out")
    assert outlier.valuation_band == "overpriced"


def _clean_line_pool(n_leaks=5):
    # 60 flats on a perfect €12/m² line — the hedonic fit should reproduce them exactly…
    pool = [
        Listing(price_eur_month=12 * s, size_m2=s, bedrooms=2, bathrooms=1,
                concelho="Loulé", property_type="apartment", source_url=f"n{i}")
        for i, s in enumerate(range(60, 120))
    ]
    # …plus €300k sale/parse-leaks at a normal size — the kind that distort a naive fit.
    for i in range(n_leaks):
        pool.append(
            Listing(price_eur_month=300000, size_m2=90, bedrooms=2, bathrooms=1,
                    concelho="Loulé", property_type="apartment", source_url=f"junk{i}")
        )
    return pool


def test_extreme_outliers_trimmed_from_valuation_fit():
    pool = _clean_line_pool()
    value_pool(pool)
    normals = [x for x in pool if x.source_url.startswith("n")]
    # The leaks are excluded from the fit, so the clean line is preserved → normals read fair.
    assert all(x.valuation_band == "fair" for x in normals)
    mid = next(x for x in normals if x.size_m2 == 90)
    assert 950 <= mid.valuation_expected_eur <= 1210  # ≈ €12×90 = 1080, not inflated
    # The leaks are still scored (and come out wildly overpriced).
    assert all(x.valuation_band == "overpriced" for x in pool if x.source_url.startswith("junk"))


def test_disabling_trim_lets_outliers_distort_the_fit(monkeypatch):
    from quintal import config
    monkeypatch.setattr(config, "VALUATION_FIT_MAD_K", 0)  # no trimming
    pool = _clean_line_pool()
    value_pool(pool)
    mid = next(x for x in pool if x.source_url == "n30")  # size 90, actual rent €1080
    # Without trimming the leaks inflate the fit → same-sized normals read falsely undervalued.
    assert mid.valuation_expected_eur > 1300
    assert mid.valuation_band == "undervalued"
