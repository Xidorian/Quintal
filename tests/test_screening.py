from quintal.schema import Listing
from quintal.screening import Blocklist, is_short_term, screen, short_term_reason


def _l(desc: str, **kw) -> Listing:
    return Listing(price_eur_month=1000, concelho="Faro", description_raw=desc, **kw)


def test_detects_al_registration():
    assert is_short_term(_l("151506/AL - Apartamento para Férias.")) is not None


def test_detects_holiday_phrasing():
    assert is_short_term(_l("Apartamento T1 para férias em Altura.")) is not None
    assert is_short_term(_l("Arrendamento por semana, ótimo para temporada.")) is not None


def test_detects_seasonal_academic_year():
    assert is_short_term(_l("Arrendamento de Outubro a Maio.")) is not None
    assert is_short_term(_l("Disponível de 5 de Setembro a final de Junho.")) is not None


def test_detects_year_interrupted_seasonal_span():
    # The gap that slipped through: a year between the two months.
    assert is_short_term(_l("T2 Olhos Agua/Açoteias, Setembro 2025 a Junho 2026")) is not None
    assert is_short_term(_l("Arrendamento de setembro 2025 até maio 2026.")) is not None


def test_seasonal_span_does_not_overmatch_across_sentences():
    # Months in separate sentences must not trip it (a year-round listing).
    assert is_short_term(_l("Disponível em setembro. Piscina aberta até maio no verão.")) is None


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


# --- QT-048: seasonal spans the old rule missed, and the traps it must keep missing ------
# Malia was still hitting short-term lets. The span rule only knew setembro|outubro →
# maio|junho|julho joined by "a"/"ate", so every november/december start, march/april end,
# "e" connector, dash form and abbreviated month slipped past. All strings below are taken
# from listings that were live in the pool on 2026-08-31.
import pytest


@pytest.mark.parametrize(
    "text",
    [
        "disponivel de 30 de setembro a 30 de abril",  # abril end
        "arrendamento de 1 de novembro de 2025 ate 30 junho de 2026",  # novembro start
        "arrendamento de média duração | dezembro de 2026 a junho de 2027",  # dezembro start
        "disponível para arrendamento entre outubro de 2026 e maio de 2027",  # "e" connector
        "disponibilidade: novembro de 2026 – 15 de março de 2027",  # en-dash, março end
        "apartamento T1 mobilado Albufeira/Oura de out/26 a mai/27",  # abbreviated months
        "aluger de invierno nov 26- abril 27",  # abbreviated + hyphen
        "arrendamento curta duração em época baixa (15 out 2026 a 30 abr 2027)",
    ],
)
def test_seasonal_spans_are_caught(text):
    assert short_term_reason(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "*curto prazo nov-abril",
        "disponível para arrendamentos de inverno, entre outubro e maio, mínimo de 2 meses",
        "arrendamento de curta duração, 1 a 4 meses",
        "seja para um winter let, trabalho remoto ou uma estadia prolongada",
        "arrendamento para o ano lectivo",
        "quarto para estudante Erasmus",
        "não é um arrendamento anual",
    ],
)
def test_duration_language_is_caught(text):
    assert short_term_reason(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        # Each of these READS short-term but is a perfectly good year-round let. Adding the
        # tempting phrase behind it ("meses", "mês de", "hóspedes", "estudantes",
        # "a partir de setembro") would purge real listings — that is why they are absent
        # from SHORT_TERM_PATTERNS, and this test is what keeps them absent.
        "contrato de arrendamento mínimo de 12 meses, 2 meses de caução",
        "nota: o valor é para um contrato de 8 meses, se o contrato for de 12 meses a renda é 950",
        "pagar de início: 1 mês de renda e 2 de caução",
        "divisão extra ideal para escritório ou quarto de hóspedes. arrendamento anual.",
        # NOTE (QT-053): this case used to name Uniplaces. The point it was making is about
        # "estudantes" — a platform blurb listing students *and* professionals *and* families
        # says nothing about the term — so it keeps making that point with the platform name
        # removed. The platform itself is now blocked; see the QT-053 block below for why.
        "arrendo a indivíduos, sejam estudantes, profissionais ou famílias, arrendamento anual",
        "condições do arrendamento: 3.100 €/mês (disponível a partir de setembro), arrendamento anual",
        "moradia T3 | arrendamento de longa duração | disponível a partir de setembro",
    ],
)
def test_long_term_listings_are_not_purged(text):
    assert short_term_reason(text) is None


# --- QT-053: booking-platform syndication ------------------------------------------------
# Malia: "lots and lots of short term rentals are showing up when they should be
# automatically filtered out." They were one platform. Imovirtual carries Uniplaces stock
# verbatim, and on 2026-09-30 that was 118 of the 646 ranked Algarve listings — 18% of the
# pool — every one of them quoting a minimum stay in DAYS.
@pytest.mark.parametrize(
    "text",
    [
        # The real boilerplate, as it appears in the pool (trimmed).
        "RESERVAS E PEDIDOS DE INFORMAÇÃO TERMOS E CONDIÇÕES DE ALOJAMENTO: - Data de"
        " Disponibilidade: 04/10/2026 - Duração Mínima de Aluguer: 30 dias",
        "Descrição da Propriedade na Uniplaces: Flat with two rooms, located in Albufeira",
        # The syndication title template, which is all we get for the Norte pool (those
        # cards carry no description at all). The plural after "1" is the giveaway.
        "Apartamento com 1 quartos - localizado em Bonfim Porto",
        "Casa com 3 quartos - localizado em Albufeira",
        # A minimum stay counted in days is a booking, never a lease.
        "equipada para estadias curtas (mínimo de 5 dias até um máximo de 1 mês)",
        # Booking/Airbnb "entire place" phrasing, and company-only worker housing.
        "Alojamento inteiro: moradia geminada em Olhos de Água, Portugal",
        "Disponível para arrendamento exclusivamente a empresas que necessitem de"
        " alojamento para os seus colaboradores",
    ],
)
def test_syndicated_short_stays_are_caught(text):
    assert short_term_reason(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        # A minimum stated in MONTHS is what a real lease does — the days rule must not
        # reach it, and neither must anything else added for QT-053.
        "contrato de arrendamento, mínimo de 12 meses, disponível já",
        "Apartamento T2 com 2 quartos em Albufeira, arrendamento anual",
        "Moradia T3 com 3 quartos, localizada em Braga, para arrendamento de longa duração",
        # "localizado em" on its own is ordinary Portuguese; only the full template counts.
        "Moradia T4 localizado em Tavira, arrendamento anual, aceita animais",
        # 30 days' notice is a lease term, not a minimum stay.
        "rescisão com aviso prévio de 30 dias",
    ],
)
def test_long_term_survives_the_syndication_rules(text):
    assert short_term_reason(text) is None
