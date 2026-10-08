"""Raw site dict → validated `Listing`, plus PT/EN keyword feature derivation."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from pydantic import ValidationError

from . import rules
from .errors import AppError
from .schema import DerivedBool, DerivedPets, Listing, PropertyType

# --- Keyword sets (folded: lowercase, accents stripped) ---
YARD_KEYWORDS = ["quintal", "jardim", "terreno", "logradouro", "yard", "garden", "backyard", "plot"]
TERRACE_KEYWORDS = ["terraco", "varanda", "patio", "terrace", "balcony", "rooftop"]
BATHTUB_KEYWORDS = ["banheira", "bathtub", "bath tub"]
PETS_NEGATIVE = [
    "nao aceita animais",
    "nao sao permitidos animais",
    "nao permitimos animais",
    "nao permite animais",
    "nao permitido animais",
    "sem animais",
    "no pets",
    "pets not allowed",
    "no animals",
]
PETS_POSITIVE = [
    "aceita animais",
    "animais de estimacao",
    "animais permitidos",
    "caes permitidos",
    "pet friendly",
    "pet-friendly",
    "pets allowed",
    "pets welcome",
]
# A pets noun followed (within a short window) by a negated allow-verb — catches
# "animais de estimacao nao permitido" that the fixed-phrase lists miss and would
# otherwise mis-read as the positive "animais de estimacao". Runs on folded,
# punctuation-collapsed text; the window is bounded so it stays sentence-local.
_PETS_DENY_REVERSED = re.compile(r"anima(?:l|is)\b[\w ]{0,20}?\bnao (?:\w+ )?(?:permit|aceit|admit)")
# The forward twin: "<negated verb> ... animais". Every denial the pool leaked past us was
# this word order — measured 2026-10-08, a forward pattern changes 27 Algarve listings, 22
# of them from a confident `yes`. The fixed-phrase list could never cover it without
# enumerating every conjugation (aceita/aceito/aceites/aceitam/aceitamos/serão aceites)
# times every verb times both orders.
#
# `anima` must follow the verb directly (one optional article between), NOT within a loose
# window: "não é permitido fumar, animais são permitidos" is an allow, and a window wide
# enough to reach past "fumar" reads it as a denial. See
# test_pets_allow_survives_unrelated_negation.
_PETS_DENY_FORWARD = re.compile(
    r"\bnao (?:se |me )?(?:sao |serao |foi |e |esta )?"
    # Whole stems, not just the participle: the pool has "não se admite animais" as well as
    # "não são admitidos". `tenha/possua` cover the tenant-side phrasing, "a quem não tenha
    # animais de estimação", which is a refusal written as a preference.
    r"(?:aceit\w+|permit\w+|admit\w+|autoriz\w+|tenha\w*|possua\w*) "
    # One coordinated noun may sit in front: "não são permitidas festas e animais".
    r"(?:[ao]s? )?(?:\w+ e )?anima"
)
# "estritamente proibido a animais" (and the "estritamento" typo in the live pool), plus
# the reverse "animais ... proibido".
_PETS_DENY_PROHIBITED = re.compile(
    r"\bproibid\w* (?:[ao]s? )?anima|\banima\w*(?: \w+){0,2} proibid"
)
# English: the list had "pets not allowed", which "pets ARE not allowed" does not contain.
_PETS_DENY_EN = re.compile(r"\bpets?\b[\w ]{0,15}?\bnot (?:be )?(?:allow|accept|permit)")
# Conditional, not permissive: "animais de estimação sem a prévia autorização",
# "necessidade a ser confirmado", "mediante autorização prévia", "a confirmar". These read
# as `yes` today purely because the bare noun "animais de estimacao" sits in PETS_POSITIVE
# and nothing negates it — about 30 Algarve listings. They are genuinely unknown, which is
# the bucket this project already keeps and flags (pets are protected in PT long-lets).
_PETS_CONDITIONAL = re.compile(
    r"\banima\w*[\w ]{0,45}?(?:sem (?:a )?previa autoriza|mediante (?:a )?autoriza"
    r"|so com autoriza|a ser confirmad|a confirmar|sujeit\w+ a autoriza)"
    r"|(?:sem (?:a )?previa autoriza|mediante (?:a )?autoriza)[\w ]{0,45}?\banima"
)
_PETS_DENY_PATTERNS = (
    _PETS_DENY_REVERSED,
    _PETS_DENY_FORWARD,
    _PETS_DENY_PROHIBITED,
    _PETS_DENY_EN,
)

# --- Property type ---
# Matched as whole words, and against the TITLE first. Both halves of that matter, because
# naive substring matching over title+description mistyped 201 of 2307 Algarve listings
# (QT-054):
#   · "villa" matched "Balaia Golf Village" → 18 apartments became houses
#   · "house" matched "penthouse" → 15 more
#   · "banda" matched "Rua da Banda Musical de Tavira" → townhouses
#   · "t0" matched loosely; "casa " (the trailing-space hack) matched the description's
#     generic "a casa é mobilada" → 145 apartments became houses, the biggest slice by far.
# A Portuguese listing calls any home "a casa" in its prose, so the description can never
# outrank the title's own dwelling noun. Each entry is a regex fragment, joined with \b.
_HOUSE_WORDS = ["moradia", "vivenda", "casa", "villa", "house", "detached", "chale"]
_TOWNHOUSE_WORDS = ["geminada", "em banda", "townhouse", "terraced"]
_APARTMENT_WORDS = ["apartamento", "apartment", "flat", "andar", "duplex", "penthouse"]
_STUDIO_WORDS = ["estudio", "studio", "t0", "kitchenette"]
# "casa" is the word any PT listing uses for "home" — safe in a title ("Casa com 3 quartos"),
# meaningless in prose. Same for the bare "house". Dropped from the description fallback.
_DESCRIPTION_BLIND = frozenset({"casa", "house"})


def fold(text: str) -> str:
    """Lowercase + strip accents so 'pátio'/'patio', 'não'/'nao' match uniformly."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _matches(folded_text: str, keywords: list[str]) -> list[str]:
    return [kw for kw in keywords if kw in folded_text]


def _derive_bool(folded_text: str, keywords: list[str]) -> DerivedBool:
    hits = _matches(folded_text, keywords)
    if hits:
        return DerivedBool(value=True, confidence=0.85, evidence=hits)
    # Absence in text weakly implies absence in reality — low confidence.
    return DerivedBool(value=False, confidence=0.4, evidence=[])


def _derive_pets(folded_text: str) -> DerivedPets:
    # Collapse punctuation to spaces so imovirtual's attribute label
    # "Animais de estimação: não permitido" reads as one continuous run.
    text = re.sub(r"[^a-z0-9]+", " ", folded_text)
    # Negatives first: "aceita animais" is a substring of "nao aceita animais", and
    # the bare noun "animais de estimacao" appears in BOTH allow and deny sentences —
    # so the deny verb, not the noun, is what decides.
    neg = _matches(text, PETS_NEGATIVE)
    # Both word orders plus "proibido" and the English forms — the fixed-phrase list can
    # cover none of them without enumerating every conjugation and gap.
    for pattern in _PETS_DENY_PATTERNS:
        m = pattern.search(text)
        if m:
            neg.append(m.group(0))
    if neg:
        return DerivedPets(value="no", confidence=0.9, evidence=neg)
    # Conditional is checked BEFORE positive, and the order is the whole point: every
    # conditional sentence contains the bare noun "animais de estimacao", so PETS_POSITIVE
    # would claim it as a yes. Lower confidence than an unmentioned unknown, because this
    # one was mentioned — we just can't call it.
    cond = _PETS_CONDITIONAL.search(text)
    if cond:
        return DerivedPets(value="unknown", confidence=0.5, evidence=[cond.group(0)])
    pos = _matches(text, PETS_POSITIVE)
    if pos:
        return DerivedPets(value="yes", confidence=0.85, evidence=pos)
    return DerivedPets(value="unknown", confidence=0.9, evidence=[])


def _word_at(
    folded_text: str, words: list[str], *, blind: frozenset[str] = frozenset()
) -> int | None:
    """Position of the first of `words` appearing as a whole word, or None.

    Trailing "s" is tolerated so "apartamentos"/"moradias" match. `blind` drops entries
    that are only trustworthy in a title (see `_DESCRIPTION_BLIND`).
    """
    usable = [w for w in words if w not in blind]
    if not usable:
        return None
    m = re.search(r"\b(?:" + "|".join(usable) + r")s?\b", folded_text)
    return m.start() if m else None


def _type_from(folded_text: str, *, blind: frozenset[str] = frozenset()) -> PropertyType | None:
    """The dwelling type this one piece of text claims, or None if it names none.

    The *base* noun is whichever of house/apartment comes first, because a PT listing title
    leads with the type it is selling ("Apartamento T2 na Rua das Moradias" is an apartment
    on a street called Moradias, not a house). The other two types are refinements, not
    competitors: "em banda"/"geminada" narrows a house to a townhouse, and a T0/kitchenette
    narrows an apartment to a studio — so each only applies to its own base. That keeps
    "Apartamento duplex num 1º andar de moradia geminada" an apartment.
    """
    house_at = _word_at(folded_text, _HOUSE_WORDS, blind=blind)
    apartment_at = _word_at(folded_text, _APARTMENT_WORDS, blind=blind)
    townhouse = _word_at(folded_text, _TOWNHOUSE_WORDS, blind=blind) is not None
    studio = _word_at(folded_text, _STUDIO_WORDS, blind=blind) is not None

    if house_at is not None and (apartment_at is None or house_at < apartment_at):
        return "townhouse" if townhouse else "house"
    if apartment_at is not None:
        return "studio" if studio else "apartment"
    if townhouse:  # "Townhouse T3" — its own noun, no house word needed
        return "townhouse"
    return "studio" if studio else None


def _infer_property_type(
    folded_title: str, folded_text: str, given: str | None
) -> PropertyType:
    """The site's own type if it gave one, else the title's claim, else the description's.

    The title is authoritative: it is the one place the lister names the dwelling. The
    description only gets a say when the title names no type at all, and even then it is
    blind to the words that mean nothing in prose (`_DESCRIPTION_BLIND`).
    """
    if given in ("house", "townhouse", "apartment", "studio"):
        return given  # type: ignore[return-value]
    return (
        _type_from(folded_title)
        or _type_from(folded_text, blind=_DESCRIPTION_BLIND)
        or "other"
    )


def _infer_bedrooms(folded_text: str, given: Any) -> int | None:
    if isinstance(given, int):
        return given
    # PT typology "T2" → 2 bedrooms (T0 = studio → 0).
    m = re.search(r"\bt(\d)\b", folded_text)
    return int(m.group(1)) if m else None


# rule attribute → the Listing field it overrides. `pets` and `short_term` are handled
# separately: one carries a string verdict, the other only ever fires positively.
_RULE_BOOL_FIELDS = {"yard": "has_yard", "bathtub": "has_bathtub"}


def _apply_rules(listing: Listing, folded: str) -> None:
    """Let a searcher-authored rule override the keyword derivation.

    Runs last and wins, because whoever wrote the rule opened the listing and read it —
    the regex did not. Confidence goes to 1.0 and the evidence names the rule, so a
    verdict that came from a person is never mistaken for one the keywords produced.
    """
    hit = rules.verdict_for("pets", folded)
    if hit is not None:
        verdict, rule = hit
        listing.pets = DerivedPets(value=verdict, confidence=1.0, evidence=[f"rule:{rule.id}"])

    for attribute, field in _RULE_BOOL_FIELDS.items():
        hit = rules.verdict_for(attribute, folded)
        if hit is not None:
            verdict, rule = hit
            setattr(
                listing,
                field,
                DerivedBool(value=verdict == "yes", confidence=1.0, evidence=[f"rule:{rule.id}"]),
            )

    hit = rules.verdict_for("short_term", folded)
    if hit is not None:
        _, rule = hit
        listing.suspected_short_term = DerivedBool(
            value=True, confidence=1.0, evidence=[f"rule:{rule.id}"]
        )


def normalize(raw: dict[str, Any]) -> Listing:
    """Build a validated `Listing` from a raw site dict; derive text features.

    Raises AppError (operational) if the record can't satisfy the schema — the
    pipeline skips it rather than crashing the batch.
    """
    title = raw.get("title") or ""
    text = f"{title} {raw.get('description_raw', '')}"
    folded = fold(text)
    folded_title = fold(title)

    data = dict(raw)
    data["property_type"] = _infer_property_type(
        folded_title, folded, raw.get("property_type")
    )
    inferred_beds = _infer_bedrooms(folded, raw.get("bedrooms"))
    if inferred_beds is not None:
        data["bedrooms"] = inferred_beds

    try:
        listing = Listing(**{k: v for k, v in data.items() if k in Listing.model_fields})
    except ValidationError as exc:
        raise AppError(
            f"invalid listing: {exc.errors()[:2]}", operational=True, status=422
        ) from exc

    listing.has_yard = _derive_bool(folded, YARD_KEYWORDS)
    listing.has_terrace = _derive_bool(folded, TERRACE_KEYWORDS)
    listing.has_bathtub = _derive_bool(folded, BATHTUB_KEYWORDS)
    listing.pets = _derive_pets(folded)
    _apply_rules(listing, folded)  # a person's rule outranks our keywords
    listing.ensure_id()
    return listing
