"""Searcher-authored attribute rules — see src/quintal/rules.py.

These guard three properties: a rule beats the keyword derivation, a malformed rule fails
loudly at construction rather than mid-pull, and `prepare()` is the single text shape every
pattern is written against.
"""

from __future__ import annotations

import pytest

from quintal import normalize as norm
from quintal import rules
from quintal.normalize import normalize


@pytest.fixture
def one_rule(monkeypatch):
    """Install a single rule for the duration of a test."""

    def install(**kwargs):
        defaults = {
            "id": "r-test-1",
            "attribute": "pets",
            "verdict": "no",
            "pattern": "nao aceito anima",
            "source": "test",
            "added": "2026-10-08",
        }
        rule = rules.Rule(**{**defaults, **kwargs})
        monkeypatch.setattr(rules, "RULES", [rule])
        return rule

    return install


def _raw(description: str, title: str = "Apartamento T2 em Olhão") -> dict:
    return {
        "title": title,
        "description_raw": description,
        "price_eur_month": 900,
        "source_url": "https://x/1",
    }


# --- Construction: a bad rule must never reach a pull -------------------------


def test_unknown_attribute_is_refused():
    with pytest.raises(ValueError, match="unknown attribute"):
        rules.Rule(
            id="r1", attribute="jacuzzi", verdict="no",
            pattern="x", source="test", added="2026-10-08",
        )


def test_verdict_must_be_legal_for_the_attribute():
    """`short_term` only fires positively — no single phrase proves a listing *is* long-term."""
    with pytest.raises(ValueError, match="cannot be"):
        rules.Rule(
            id="r1", attribute="short_term", verdict="no",
            pattern="x", source="test", added="2026-10-08",
        )


def test_a_rule_without_provenance_is_refused():
    """The whole point is that a person vouched for it; an unsourced rule is a guess."""
    with pytest.raises(ValueError, match="needs a source"):
        rules.Rule(
            id="r1", attribute="pets", verdict="no",
            pattern="x", source="   ", added="2026-10-08",
        )


def test_a_broken_regex_fails_at_construction_not_mid_pull():
    with pytest.raises(Exception):  # noqa: B017 — re.error, surfaced through __post_init__
        rules.Rule(
            id="r1", attribute="pets", verdict="no",
            pattern="nao aceita (anima", source="test", added="2026-10-08",
        )


# --- Matching -----------------------------------------------------------------


def test_prepare_collapses_punctuation_so_patterns_need_no_separators():
    """The imovirtual label case: "Animais de estimação: não permitido" must read as one run."""
    assert rules.prepare("animais de estimacao: nao permitido") == (
        "animais de estimacao nao permitido"
    )
    assert rules.prepare("a  --  b") == "a b"


def test_rule_overrides_the_keyword_derivation(one_rule):
    """The built-in patterns are "animais"-centric, so a refusal written with the species
    instead — "proibido ter cães ou gatos" — reaches none of them. Exactly the case a rule
    is for: one listing's phrasing, not worth a pattern of its own.

    (This test used `nao aceito animais` until QT-058 fixed that gap in `normalize.py`.
    A rules test has to stand on a gap the derivation genuinely has, or it is really a
    test of the derivation.)
    """
    text = "t2 com varanda, proibido ter caes ou gatos"
    assert norm._derive_pets(norm.fold(text)).value == "unknown"  # the gap

    one_rule(pattern="proibido ter caes")
    listing = normalize(_raw(text))
    assert listing.pets.value == "no"
    assert listing.pets.confidence == 1.0
    assert listing.pets.evidence == ["rule:r-test-1"]


def test_rule_beats_a_confident_wrong_derivation(one_rule):
    """"cães permitidos apenas no exterior" lands on `caes permitidos` and derives a
    confident `yes` — but a dog that may not come indoors is not a yes for Luna, and only
    someone reading the sentence knows that. The person outranks the keyword."""
    text = "moradia t3, caes permitidos apenas no exterior"
    assert norm._derive_pets(norm.fold(text)).value == "yes"  # confident, and not useful

    one_rule(pattern="caes permitidos apenas no exterior")
    assert normalize(_raw(text)).pets.value == "no"


def test_rule_marks_short_term_without_touching_the_blocklist(one_rule):
    """Marking, not purging — a misfired rule must stay recoverable."""
    one_rule(attribute="short_term", verdict="yes", pattern="apenas para ferias")
    listing = normalize(_raw("arrendamento apenas para ferias de verao"))
    assert listing.suspected_short_term.value is True
    assert listing.suspected_short_term.evidence == ["rule:r-test-1"]


def test_yard_rule_sets_the_boolean(one_rule):
    one_rule(attribute="yard", verdict="no", pattern="sem qualquer espaco exterior")
    listing = normalize(_raw("t2 sem qualquer espaco exterior, 2o andar"))
    assert listing.has_yard.value is False
    assert listing.has_yard.evidence == ["rule:r-test-1"]


def test_no_rules_means_no_change():
    """The shipped state: RULES is empty, so derivation is untouched."""
    assert rules.RULES == []
    listing = normalize(_raw("casa com quintal grande, aceita animais"))
    assert listing.pets.value == "yes"
    assert listing.pets.evidence != ["rule:"]
    assert listing.suspected_short_term.value is None


def test_non_matching_rule_leaves_the_derivation_alone(one_rule):
    one_rule(pattern="frase que nao aparece")
    listing = normalize(_raw("casa com quintal, aceita animais"))
    assert listing.pets.value == "yes"  # the keyword verdict, not the rule's
    assert listing.pets.confidence < 1.0


def test_verdict_for_returns_the_first_matching_rule(monkeypatch):
    """First, not best — two rules disagreeing is a bug to fix, not a precedence puzzle."""
    first = rules.Rule(
        id="a", attribute="pets", verdict="no", pattern="anima",
        source="test", added="2026-10-08",
    )
    second = rules.Rule(
        id="b", attribute="pets", verdict="yes", pattern="animais",
        source="test", added="2026-10-08",
    )
    monkeypatch.setattr(rules, "RULES", [first, second])
    verdict, rule = rules.verdict_for("pets", "aceita animais")
    assert (verdict, rule.id) == ("no", "a")
    assert rules.verdict_for("yard", "aceita animais") is None


def test_matching_reports_every_rule_that_fires(monkeypatch):
    monkeypatch.setattr(
        rules,
        "RULES",
        [
            rules.Rule(
                id="a", attribute="pets", verdict="no", pattern="anima",
                source="test", added="2026-10-08",
            ),
            rules.Rule(
                id="b", attribute="short_term", verdict="yes", pattern="ferias",
                source="test", added="2026-10-08",
            ),
        ],
    )
    assert [r.id for r in rules.matching("animais ferias")] == ["a", "b"]
    assert rules.matching("nada relevante") == []


# --- The guard ----------------------------------------------------------------


def test_every_attribute_has_a_current_verdict_reader():
    """`rules test` prints what we say today for each attribute. An attribute with no
    reader must raise, not inherit some other attribute's answer — this tool's whole job is
    to be trustworthy in the minutes before someone commits a rule off the back of it."""
    # ATTRIBUTES constrains what a rule may *assert* (short_term: only "yes"); the current
    # state may legitimately be any of the three. Different vocabularies, same words.
    for attribute in rules.ATTRIBUTES:
        verdict, _detail = rules.current_verdict(attribute, "casa com quintal e banheira")
        assert verdict in {"yes", "no", "unknown"}

    rules.ATTRIBUTES["telescope"] = frozenset({"yes"})
    try:
        with pytest.raises(ValueError, match="no current-verdict reader"):
            rules.current_verdict("telescope", "casa com telescopio")
    finally:
        del rules.ATTRIBUTES["telescope"]


def test_verdict_readers_answer_in_their_attributes_own_terms():
    """A yard reader returning a pets verdict would make the guard's table nonsense."""
    text = "casa com quintal e banheira, nao aceita animais, apenas para ferias"
    assert rules.current_verdict("pets", text) == ("no", "")
    assert rules.current_verdict("yard", text) == ("yes", "")
    assert rules.current_verdict("bathtub", text) == ("yes", "")
    # short_term answers in the same vocabulary a rule asserts, with the reason alongside
    # rather than inside the verdict — see the docstring for what comparing them cost.
    verdict, detail = rules.current_verdict("short_term", text)
    assert verdict == "yes" and detail
    assert rules.current_verdict("short_term", "t2 com varanda") == ("no", "")
