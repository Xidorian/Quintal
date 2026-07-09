from quintal.collect import idealista, imovirtual, receiver, store
from quintal.collect.base import SearchParams, concelho_from_location
from quintal.collect.parsing import parse_area, parse_bathrooms, parse_bedrooms, parse_price
from quintal.normalize import normalize


# --- PT number/format parsing (the thousands-dot vs decimal-comma trap) ---
def test_price_eu_thousands_dot():
    assert parse_price("1.200 €/mês") == 1200.0


def test_price_decimal_comma():
    assert parse_price("1.200,50") == 1200.5


def test_price_english_format():
    # Idealista renders EN when the account language is English: comma = thousands.
    assert parse_price("1,100€/month") == 1100.0
    assert parse_price("3,000€") == 3000.0
    assert parse_price("1,234.50") == 1234.5


def test_price_plain_and_spaced():
    assert parse_price("950") == 950.0
    assert parse_price("1 200 €") == 1200.0


def test_area_extracts_before_m2():
    assert parse_area("T2 · 85 m²") == 85.0
    assert parse_area("120 m2") == 120.0


def test_bedrooms_typology():
    assert parse_bedrooms("T2") == 2
    assert parse_bedrooms("T2+1") == 3
    assert parse_bedrooms("T0") == 0
    assert parse_bedrooms("2 quartos") == 2


def test_bathrooms():
    assert parse_bathrooms("2 wc") == 2
    assert parse_bathrooms("1 casa de banho") == 1


def test_concelho_is_last_location_token():
    assert concelho_from_location("Almancil, Loulé") == "Loulé"


# --- Search URL builders ---
def test_idealista_url_has_price_and_bedroom_filters():
    urls = idealista.search_urls(SearchParams(max_price=1500, min_beds=2, max_beds=4))
    assert "faro-distrito" in urls[0]  # canonical "algarve" → Idealista's slug
    assert "com-preco-max_1500" in urls[0]
    assert ",t2,t3,t4" in urls[0]


def test_imovirtual_url_has_params_and_own_region_slug():
    urls = imovirtual.search_urls(SearchParams(max_price=1500, min_beds=2, max_beds=3))
    assert "/faro?" in urls[0] and "faro-distrito" not in urls[0]  # its own slug, not Idealista's
    assert "priceMax=1500" in urls[0]
    assert "TWO" in urls[0] and "THREE" in urls[0]


def test_pagination_produces_distinct_pages():
    urls = idealista.search_urls(SearchParams(), pages=2)
    assert len(urls) == 2 and urls[0] != urls[1]


def test_imovirtual_location_drops_district_for_concelho():
    # Imovirtual reads '[street, ]freguesia, concelho, Faro' — the last token is the
    # district, so the concelho must NOT collapse to 'Faro' (that bug bucketed all 443
    # listings together and mislocated geocoding to Faro city).
    raw = imovirtual.to_raw({"location": "Rua João Simões Tavares, Portimão, Portimão, Faro"})
    assert raw["concelho"] == "Portimão"
    raw = imovirtual.to_raw({"location": "Quarteira, Loulé, Faro"})
    assert raw["concelho"] == "Loulé" and raw["freguesia"] == "Quarteira"
    raw = imovirtual.to_raw({"location": "Albufeira e Olhos de Água, Albufeira, Faro"})
    assert raw["concelho"] == "Albufeira"
    # A listing genuinely in Faro concelho stays Faro (only the district suffix is dropped).
    raw = imovirtual.to_raw({"location": "Faro (Sé e São Pedro), Faro, Faro"})
    assert raw["concelho"] == "Faro" and raw["freguesia"] == "Faro (Sé e São Pedro)"


# --- Extraction row → raw → normalized Listing (end to end) ---
def test_bedrooms_from_rooms_text_when_title_lacks_typology():
    # Regression: a truthy title without "T3" must not shadow the typology in rooms_text.
    row = {
        "url": "https://x/1",
        "title": "Moradia independente na Vale Garifo, Luz",
        "rooms_text": "T3",
        "price_text": "1.425 €/mês",
        "location": "Luz",
    }
    assert idealista.to_raw(row)["bedrooms"] == 3


def test_extracted_row_maps_and_normalizes():
    row = {
        "url": "https://www.idealista.pt/imovel/1",
        "title": "Moradia T2 em Tavira",
        "price_text": "1.250 €/mês",
        "area_text": "110 m²",
        "typology": "T2",
        "rooms_text": "2 quartos, 2 wc",
        "location": "Santa Maria, Tavira",
        "description": "Com quintal e jardim. Aceita animais.",
        "is_private": True,
    }
    listing = normalize(idealista.to_raw(row))
    assert listing.source == "idealista"
    assert listing.price_eur_month == 1250.0
    assert listing.size_m2 == 110.0
    assert listing.bedrooms == 2
    assert listing.bathrooms == 2
    assert listing.concelho == "Tavira"
    assert listing.property_type == "house"
    assert listing.has_yard.value is True
    assert listing.pets.value == "yes"


# --- Idempotent persistence ---
def test_upsert_is_idempotent(tmp_path):
    path = tmp_path / "listings.jsonl"
    row = {"source": "idealista", "source_url": "https://x/1", "price_eur_month": 1000}

    added, updated = store.upsert(path, [row])
    assert (added, updated) == (1, 0)

    added, updated = store.upsert(path, [{**row, "price_eur_month": 1100}])
    assert (added, updated) == (0, 1)  # same URL → update, not duplicate

    assert len(path.read_text().splitlines()) == 1
    assert store.load(path)[("url", "https://x/1")]["price_eur_month"] == 1100


def test_receiver_ingest_rows_maps_and_persists(tmp_path):
    path = tmp_path / "listings.jsonl"
    rows = [
        {
            "url": "https://www.idealista.pt/imovel/9",
            "title": "T2 em Faro",
            "price_text": "1.200 €/mês",
        }
    ]
    added, updated = receiver.ingest_rows("idealista", rows, str(path))
    assert (added, updated) == (1, 0)
    stored = store.load(path)[("url", "https://www.idealista.pt/imovel/9")]
    assert stored["price_eur_month"] == 1200.0 and stored["source"] == "idealista"
