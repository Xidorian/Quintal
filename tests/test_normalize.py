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


# --- Pets: the forward-order gap (QT-058, 2026-10-08) -------------------------
# Every phrasing below is quoted from the live pool. Before this, `_PETS_DENY_REVERSED`
# only handled "<noun> ... não permitido", so verb-first denials leaked — and because the
# bare noun "animais de estimacao" sits in PETS_POSITIVE, most leaked as a confident
# **yes**, which even a strict filter passes. Measured across both pools: 91 listings
# changed verdict — 58 now read `no` (43 of them from `yes`) and 33 conditionals moved
# from `yes` to `unknown`. All 91 were read by hand; none was a false positive.

PETS_DENIALS_FROM_THE_POOL = [
    "nao serao aceites animais de estimacao",
    "nao sao aceites animais de estimacao",
    "nao sao aceiteis animais de estimacao so peixes",  # sic
    "nao serao aceite animais de estimacao",
    "nao aceitamos animais de estimacao",
    "nao aceito animais",
    "nao se aceitam animais domesticos",
    "nao se aceita animais de estimacao",
    "nao e permitido animais e ou eventos",
    "nao sao permitidos animais de estimacao",
    "nao sao admitidos animais",
    "nao se admite animais de estimacao",          # "admite", not "admitidos"
    "estritamente proibido a animais de estimacao",
    "estritamento proibido a animais de estimacao",  # typo, live in the pool
    "animais proibido caes",
    "nao sao permitidas festas e animais de estimacao",  # coordinated noun
    "da se preferencia a quem nao tenha animais de estimacao",  # refusal as preference
    "pets are not allowed",
    "pets will not be accepted",
    "no pets or children",
]


@pytest.mark.parametrize("description", PETS_DENIALS_FROM_THE_POOL)
def test_pets_denials_from_the_pool_read_as_no(description):
    listing = normalize(
        {"description_raw": description, "price_eur_month": 800, "concelho": "Loulé"}
    )
    assert listing.pets.value == "no", description


PETS_CONDITIONALS_FROM_THE_POOL = [
    "nao incluem a possibilidade de trazer animais de estimacao sem a previa autorizacao",
    "animais de estimacao necessidade a ser confirmado antes",
    "animais so com autorizacao",
    "animais de estimacao podem ser permitidos mediante autorizacao previa",
    "animais de estimacao a confirmar",
]


@pytest.mark.parametrize("description", PETS_CONDITIONALS_FROM_THE_POOL)
def test_pets_conditionals_read_as_unknown_not_yes(description):
    """"Pets, with prior authorisation" is not "pets allowed" — and it is not a refusal
    either. `unknown` is the bucket this project keeps and flags, which is the honest answer
    and the legally safer one in a PT long-let."""
    listing = normalize(
        {"description_raw": description, "price_eur_month": 800, "concelho": "Loulé"}
    )
    assert listing.pets.value == "unknown", description
    # Lower confidence than an unmentioned unknown: this one was mentioned, just unclear.
    assert listing.pets.confidence < 0.9
    assert listing.pets.evidence, "a conditional should say what it matched"


PETS_ALLOWS_FROM_THE_POOL = [
    "animais de estimacao permitido fumadores nao permitido",
    "animais de estimacao sao bem vindos pets welcome",
    "aceita animais domesticos sujeito a porte e numero",
    "aceita animais pequeno porte",
    "sao aceites animais de estimacao valor mensal 750",
]


@pytest.mark.parametrize("description", PETS_ALLOWS_FROM_THE_POOL)
def test_pets_allows_are_not_caught_by_the_new_denial_patterns(description):
    """The expensive mistake would be the other direction — hiding a listing she could
    have taken. Each of these stays `yes` with the denial patterns live."""
    listing = normalize(
        {"description_raw": description, "price_eur_month": 800, "concelho": "Loulé"}
    )
    assert listing.pets.value == "yes", description


def test_a_different_prohibition_next_to_a_pets_allow_stays_yes():
    """The trap the forward pattern has to avoid: "não é permitido fumar" is about smoking,
    and a match window wide enough to reach past "fumar" to a later "animais" would read
    the whole thing as a pets refusal. `anima` must follow the verb directly."""
    listing = normalize(
        {
            "description_raw": (
                "Nao e permitido fumar no interior. Animais de estimacao sao permitidos."
            ),
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
