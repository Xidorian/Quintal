from quintal.dedup import dedup
from quintal.schema import Listing


def test_collapses_cross_site_duplicate_private_landlord_wins():
    agency = Listing(
        price_eur_month=1390,
        size_m2=138,
        bedrooms=3,
        concelho="Loulé",
        source="idealista",
        source_url="https://x/agency",
        is_private_landlord=False,
    )
    private = Listing(
        price_eur_month=1350,
        size_m2=140,
        bedrooms=3,
        concelho="Loulé",
        source="imovirtual",
        source_url="https://x/private",
        is_private_landlord=True,
    )
    canonicals = dedup([agency, private])
    assert len(canonicals) == 1
    canonical = canonicals[0]
    assert canonical.is_private_landlord is True  # private landlord wins
    assert "https://x/agency" in canonical.also_listed_at  # dupe url retained
    assert agency.duplicate_of == canonical.listing_id


def test_keeps_distinct_flats_apart():
    a = Listing(price_eur_month=1000, size_m2=80, bedrooms=2, concelho="Faro", source_url="a")
    b = Listing(price_eur_month=1400, size_m2=120, bedrooms=3, concelho="Faro", source_url="b")
    assert len(dedup([a, b])) == 2
