from quintal import config
from quintal.schema import DerivedBool, Listing
from quintal.score import _beach_walk_sub, score_listing


def _listing(**kw) -> Listing:
    base = dict(price_eur_month=1200, concelho="Loulé")
    base.update(kw)
    return Listing(**base)


def test_walk_grading_curve():
    assert _beach_walk_sub(10) == 1.0  # ≤15 min → full
    assert _beach_walk_sub(45) == 0.0  # ≥45 min → zero
    assert 0.35 < _beach_walk_sub(30) < 0.45  # ~40% at 30 min
    assert _beach_walk_sub(None) == 0.4  # unknown → neutral-ish


def test_yard_beats_terrace():
    yard = _listing(has_yard=DerivedBool(value=True, confidence=0.85))
    terrace = _listing(has_terrace=DerivedBool(value=True, confidence=0.85))
    assert score_listing(yard)[1]["yard"] == 25.0
    assert score_listing(terrace)[1]["yard"] == 10.0  # 0.4 partial credit × 25


def test_score_bounds_and_breakdown_sums():
    total, breakdown = score_listing(
        _listing(bedrooms=2, bathrooms=2, walk_min_beach=10, dist_town_m=4000)
    )
    assert 0 <= total <= 100
    assert round(sum(breakdown.values())) == total


def test_green_walk_counts_only_under_norte_weights():
    # A listing next to a park. Under the Algarve set (no green_walk) it earns 0 there;
    # under the Norte set it earns the full green_walk weight.
    listing = _listing(walk_min_green=5)
    algarve = score_listing(listing, config.WEIGHTS)[1]
    norte = score_listing(listing, config.WEIGHTS_NORTE)[1]
    assert algarve["green_walk"] == 0.0
    assert norte["green_walk"] == config.WEIGHTS_NORTE["green_walk"]  # 5 min → full credit


def test_norte_breakdown_sums_to_total():
    total, breakdown = score_listing(
        _listing(bedrooms=2, walk_min_beach=10, walk_min_green=8, dist_town_m=5000),
        config.WEIGHTS_NORTE,
    )
    assert 0 <= total <= 100
    assert round(sum(breakdown.values())) == total


def test_perfect_house_scores_high():
    great = _listing(
        property_type="house",
        bedrooms=2,
        bathrooms=2,
        has_yard=DerivedBool(value=True, confidence=0.85),
        has_bathtub=DerivedBool(value=True, confidence=0.85),
        walk_min_beach=12,
        dist_town_m=5000,
        price_eur_month=1200,
    )
    assert score_listing(great)[0] >= 90
