import pytest

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


def test_pets_negative_permitimos_variant():
    # Surfaced by real Idealista data: "não permitimos animais".
    listing = normalize(
        {
            "description_raw": "Estúdio, não permitimos animais de estimação.",
            "price_eur_month": 800,
            "concelho": "Lagos",
        }
    )
    assert listing.pets.value == "no"


def test_pets_reversed_deny_beats_noun_positive():
    # Real imovirtual attribute label "Animais de estimação não permitido": the noun
    # "animais de estimacao" is a positive keyword, so the negated verb after it must win.
    for desc in (
        "Animais de estimação não permitido",
        "Animais de estimação: não permitidos",
        "Animais de estimação não são permitidos",
    ):
        listing = normalize(
            {"description_raw": desc, "price_eur_month": 800, "concelho": "Loulé"}
        )
        assert listing.pets.value == "no", desc


def test_pets_allow_survives_unrelated_negation():
    # "não é permitido fumar" is a different prohibition — pets stay allowed.
    listing = normalize(
        {
            "description_raw": "Animais de estimação são permitidos, não é permitido fumar.",
            "price_eur_month": 800,
            "concelho": "Loulé",
        }
    )
    assert listing.pets.value == "yes"


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


def test_implausible_size_dropped_to_none():
    base = {"description_raw": "", "price_eur_month": 1000, "concelho": "Faro"}
    # Garbage parses (10M m² card, "10 m²" on a real home) become unknown, not skew.
    assert normalize({**base, "size_m2": 10_000_000}).size_m2 is None
    assert normalize({**base, "size_m2": 10}).size_m2 is None
    # Real sizes pass through untouched.
    assert normalize({**base, "size_m2": 85}).size_m2 == 85
    assert normalize({**base, "size_m2": 21}).size_m2 == 21  # a genuine T0 studio


# --- QT-054: property type comes from the title, matched as whole words ------------------
# Malia: "there are instances where the app says house but even in the title it says
# apartamento." Substring matching over title+description mistyped 201 of the 2307 collected
# Algarve listings. Every string below is a real title or description fragment from the pool
# on 2026-09-30, with the count it stood for.
@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        # "villa" inside "Village" — 18 listings.
        ("Apartamento T2 em Balaia Golf Village, Albufeira", "", "apartment"),
        # "house" inside "penthouse" — 15 listings.
        ("Apartamento T2, Vale do Lobo", "penthouse com 133 m2 de area bruta", "apartment"),
        # "banda" inside a street name — 4 listings.
        ("Apartamento T2 na Rua da Banda Musical de Tavira, 18", "", "apartment"),
        # The big one: the description's generic "a casa" — 145 listings. A PT listing calls
        # any home "a casa" in its prose, so the description never outranks the title.
        ("Apartamento T3 na Urbanização Mar e Serra, Alvor", "Casa mobilada e equipada.", "apartment"),
        ("Apartamento T2 na Rua das Moradias, Quarteira", "", "apartment"),
        # The title still wins when it genuinely names a house...
        ("Moradia T3 com quintal", "O apartamento tem 2 frentes.", "house"),
        ("Casa com 3 quartos em Albufeira", "", "house"),
        ("Vivenda T4 com piscina", "", "house"),
        # ...and a townhouse/studio marker refines its own base noun, never the other one.
        ("Moradia em banda na Rua dos Portugueses", "", "townhouse"),
        ("Moradia geminada T3", "", "townhouse"),
        ("Apartamento T0 na Estrada N125-9, Odiáxere", "", "studio"),
        ("Apartamento duplex num 1º andar de moradia geminada", "", "apartment"),
        # Plurals count as the noun.
        ("Apartamentos T1 em Albufeira", "", "apartment"),
        # No dwelling noun in the title → the description gets a say, but stays blind to
        # "casa"/"house", which mean nothing in prose.
        ("T2 renovado em Faro", "A casa fica no centro.", "other"),
        ("T3 em Braga", "Moradia isolada com terreno.", "house"),
    ],
)
def test_property_type_reads_the_title_first(title, description, expected):
    listing = normalize(
        {
            "title": title,
            "description_raw": f"{title} {description}".strip(),
            "price_eur_month": 1000,
            "concelho": "Faro",
        }
    )
    assert listing.property_type == expected


def test_explicit_site_property_type_still_wins():
    listing = normalize(
        {
            "title": "Apartamento T2",
            "description_raw": "",
            "property_type": "house",
            "price_eur_month": 1000,
            "concelho": "Faro",
        }
    )
    assert listing.property_type == "house"
