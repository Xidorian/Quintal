from quintal.schema import Listing
from quintal.screening import Blocklist, is_short_term, screen


def _l(desc: str, **kw) -> Listing:
    return Listing(price_eur_month=1000, concelho="Faro", description_raw=desc, **kw)


def test_detects_al_registration():
    assert is_short_term(_l("151506/AL - Apartamento para Férias.")) is not None


def test_detects_holiday_phrasing():
    assert is_short_term(_l("Apartamento T1 para férias em Altura.")) is not None
    assert is_short_term(_l("Arrendamento por semana, ótimo para temporada.")) is not None


def test_passes_long_term_listing():
    assert is_short_term(_l("Moradia T2 com quintal para arrendamento anual.")) is None


def test_screen_purges_and_remembers(tmp_path):
    bl = Blocklist(tmp_path / "blocklist.json")
    good = _l("Moradia com quintal, arrendamento anual.", source_url="g")
    holiday = _l("173028/AL - apartamento para férias.", source_url="h")

    kept, purged = screen([good, holiday], bl)
    assert [listing.source_url for listing in kept] == ["g"]
    assert purged == 1
    assert bl.contains(holiday.ensure_id())

    # Persist and reload → the holiday id is purged on sight, even a clean-looking one.
    bl.save()
    reloaded = Blocklist(tmp_path / "blocklist.json")
    kept2, purged2 = screen([good, holiday], reloaded)
    assert purged2 == 1 and [listing.source_url for listing in kept2] == ["g"]
