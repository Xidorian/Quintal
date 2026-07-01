from quintal.normalize import fold, normalize


def test_fold_strips_accents():
    assert fold("Pátio com Não") == "patio com nao"


def test_derives_yard_and_bathtub():
    listing = normalize(
        {
            "title": "Moradia T2 com quintal",
            "description_raw": "Jardim privativo e banheira na suite.",
            "price_eur_month": 1200,
            "size_m2": 100,
            "concelho": "Tavira",
        }
    )
    assert listing.has_yard.value is True
    assert "quintal" in listing.has_yard.evidence
    assert listing.has_bathtub.value is True


def test_terrace_is_not_a_yard():
    listing = normalize(
        {
            "title": "Apartamento",
            "description_raw": "Com terraco e varanda.",
            "price_eur_month": 900,
            "concelho": "Faro",
        }
    )
    assert listing.has_yard.value is False
    assert listing.has_terrace.value is True


def test_pets_negative_beats_substring_positive():
    # "aceita animais" is a substring of "nao aceita animais" — negative must win.
    listing = normalize(
        {"description_raw": "Nao aceita animais.", "price_eur_month": 800, "concelho": "Lagos"}
    )
    assert listing.pets.value == "no"


def test_pets_unknown_when_unmentioned():
    listing = normalize(
        {"description_raw": "Apartamento mobilado.", "price_eur_month": 800, "concelho": "Lagos"}
    )
    assert listing.pets.value == "unknown"


def test_bathtub_not_triggered_by_bathroom_word():
    listing = normalize(
        {"description_raw": "Casa de banho renovada.", "price_eur_month": 800, "concelho": "Olhão"}
    )
    assert listing.has_bathtub.value is False


def test_property_type_and_bedrooms_inferred():
    listing = normalize(
        {"title": "Moradia T3", "description_raw": "", "price_eur_month": 1300, "concelho": "Loulé"}
    )
    assert listing.property_type == "house"
    assert listing.bedrooms == 3


def test_id_is_stable():
    raw = {"source_url": "https://x/1", "price_eur_month": 1000, "concelho": "Faro"}
    assert normalize(raw).listing_id == normalize(raw).listing_id
