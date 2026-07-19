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


# --- Photo-hash pass (QT-032) ---
from quintal.photo_hash import dhash, hamming  # noqa: E402


def test_dhash_identical_zero_distance_different_far(tmp_path):
    from PIL import Image
    a, b, c = tmp_path / "a.jpg", tmp_path / "b.jpg", tmp_path / "c.jpg"
    Image.new("RGB", (64, 64), (30, 30, 30)).save(a)          # flat dark
    Image.new("RGB", (64, 64), (30, 30, 30)).save(b)          # identical
    img = Image.new("RGB", (64, 64))
    img.putdata([(i * 3 % 256, 0, 0) for i in range(64 * 64)])  # gradient
    img.save(c)
    ha, hb, hc = dhash(a), dhash(b), dhash(c)
    assert hamming(ha, hb) == 0
    assert hamming(ha, hc) > 10
    assert dhash(tmp_path / "missing.jpg") is None


def _flat(price, concelho, url, beds=2):
    return Listing(price_eur_month=price, size_m2=90, bedrooms=beds,
                   concelho=concelho, source_url=url)


def test_photo_pass_merges_across_concelho_when_price_and_beds_agree():
    # Same flat, concelho parsed differently across sites (Almancil ⊂ Loulé), same price+beds.
    a = _flat(1500, "Loulé", "https://x/a")
    b = _flat(1500, "Almancil", "https://x/b")
    a.ensure_id()
    b.ensure_id()
    hashes = {a.listing_id: 0b1010, b.listing_id: 0b1010}   # identical photos
    canonicals = dedup([a, b], photo_hashes=hashes)
    assert len(canonicals) == 1
    assert "https://x/b" in canonicals[0].also_listed_at


def test_photo_pass_rejects_shared_photo_when_price_disagrees():
    # Different flats sharing a generic photo — must NOT merge (the €700/€1200 case).
    a = _flat(700, "Portimão", "https://x/a")
    b = _flat(1200, "Tavira", "https://x/b")
    a.ensure_id()
    b.ensure_id()
    hashes = {a.listing_id: 42, b.listing_id: 42}          # identical photo, distance 0
    assert len(dedup([a, b], photo_hashes=hashes)) == 2    # price guard keeps them apart
