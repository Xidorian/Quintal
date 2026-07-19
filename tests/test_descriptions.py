"""QT-024 — Imovirtual detail-page description enrichment."""

from quintal import descriptions
from quintal.normalize import normalize

# Mirrors the real page: two auto-generated boilerplate "description" values plus the
# owner's real one in __NEXT_DATA__, HTML-escaped with <br> line breaks. The
# visible adPageAdDescription div is empty server-side (React fills it), as on the live page.
SAMPLE_HTML = (
    '<meta property="og:description" content="Descubra esta Moradia para Arrendamento">'
    '<script id="__NEXT_DATA__" type="application/json">{'
    '"a":{"description":"Encontre a sua casa de sonho com o Imovirtual. Longa treta gerada '
    'automaticamente que nao interessa nada para amenidades."},'
    '"b":{"description":"DISPON\\u00cdVEL PARA SETEMBRO 2026!\\u003cbr/\\u003eMoradia com '
    'jardim, logradouro amplo, piscina privativa e churrasco. 3 casas de banho.\\u003cbr/\\u003e'
    'Aceita animais de estimacao."}}</script>'
    '<div data-cy="adPageAdDescription"></div>'
)


def test_extract_picks_owner_text_not_boilerplate():
    text = descriptions.extract_description(SAMPLE_HTML)
    assert text is not None
    assert text.startswith("DISPONÍVEL PARA SETEMBRO 2026!")
    # Boilerplate openers are excluded.
    assert "casa de sonho" not in text
    # HTML tags stripped, entities unescaped.
    assert "<br" not in text and "\\u003c" not in text
    for kw in ("jardim", "logradouro", "piscina", "animais"):
        assert kw in text


def test_extract_returns_none_without_description():
    assert descriptions.extract_description("<html>no json here</html>") is None


def test_roundtrip_and_apply(tmp_path):
    path = tmp_path / "descriptions.json"
    descriptions.save({"https://imv/1": "Moradia com jardim e piscina."}, path)
    assert descriptions.load(path) == {"https://imv/1": "Moradia com jardim e piscina."}

    rows = [
        {"source_url": "https://imv/1", "title": "T3", "description_raw": "T3"},
        {"source_url": "https://imv/2", "title": "T2", "description_raw": "T2"},
    ]
    enriched = descriptions.apply(rows, path)
    assert enriched == 1
    assert rows[0]["description_raw"] == "Moradia com jardim e piscina."
    assert rows[1]["description_raw"] == "T2"  # untouched — no cached description


def test_apply_is_noop_without_sidecar(tmp_path):
    rows = [{"source_url": "x", "description_raw": "orig"}]
    assert descriptions.apply(rows, tmp_path / "absent.json") == 0
    assert rows[0]["description_raw"] == "orig"


def test_enriched_description_flips_yard_derivation(tmp_path):
    """The point of the whole feature: real text makes normalize see the yard."""
    path = tmp_path / "descriptions.json"
    # Title alone (Imovirtual card) has no yard keyword.
    card = {
        "source": "imovirtual",
        "source_url": "https://imv/9",
        "title": "Moradia T4 em Estoi",
        "description_raw": "Moradia T4 em Estoi",
        "price_eur_month": 1500,
    }
    assert normalize(dict(card)).has_yard.value is False

    descriptions.save({"https://imv/9": "Casa com jardim e logradouro amplo."}, path)
    rows = [dict(card)]
    descriptions.apply(rows, path)
    assert normalize(rows[0]).has_yard.value is True


def test_backfill_only_fetches_imovirtual(monkeypatch, tmp_path):
    """Idealista detail pages 403 — don't waste fetches on them."""
    listings_path = tmp_path / "listings.jsonl"
    import json

    rows = [
        {"source": "imovirtual", "source_url": "https://imv/a", "price_eur_month": 1000},
        {"source": "idealista", "source_url": "https://ide/b", "price_eur_month": 1000},
    ]
    listings_path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    fetched: list[str] = []

    def fake_fetch_one(url, session):
        fetched.append(url)
        return "Casa com jardim."

    monkeypatch.setattr(descriptions, "fetch_one", fake_fetch_one)
    stats = descriptions.backfill(listings_path, tmp_path / "d.json", delay=0)

    assert fetched == ["https://imv/a"]  # idealista skipped
    assert stats.get("ok") == 1
    assert stats.get("skip") == 1
    assert descriptions.load(tmp_path / "d.json") == {"https://imv/a": "Casa com jardim."}
