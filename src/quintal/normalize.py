"""Raw site dict → validated `Listing`, plus PT/EN keyword feature derivation."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from pydantic import ValidationError

from .errors import AppError
from .schema import DerivedBool, DerivedPets, Listing, PropertyType

# --- Keyword sets (folded: lowercase, accents stripped) ---
YARD_KEYWORDS = ["quintal", "jardim", "terreno", "logradouro", "yard", "garden", "backyard", "plot"]
TERRACE_KEYWORDS = ["terraco", "varanda", "patio", "terrace", "balcony", "rooftop"]
BATHTUB_KEYWORDS = ["banheira", "bathtub", "bath tub"]
PETS_NEGATIVE = [
    "nao aceita animais",
    "nao sao permitidos animais",
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

_HOUSE_WORDS = ["moradia", "vivenda", "casa ", "villa", "house", "detached"]
_TOWNHOUSE_WORDS = ["geminada", "banda", "townhouse", "terraced"]
_APARTMENT_WORDS = ["apartamento", "apartment", "flat", "andar"]
_STUDIO_WORDS = ["estudio", "studio", "t0", "kitchenette"]


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
    # Negatives first: "aceita animais" is a substring of "nao aceita animais".
    neg = _matches(folded_text, PETS_NEGATIVE)
    if neg:
        return DerivedPets(value="no", confidence=0.9, evidence=neg)
    pos = _matches(folded_text, PETS_POSITIVE)
    if pos:
        return DerivedPets(value="yes", confidence=0.85, evidence=pos)
    return DerivedPets(value="unknown", confidence=0.9, evidence=[])


def _infer_property_type(folded_text: str, given: str | None) -> PropertyType:
    if given in ("house", "townhouse", "apartment", "studio"):
        return given  # type: ignore[return-value]
    if any(w in folded_text for w in _STUDIO_WORDS):
        return "studio"
    if any(w in folded_text for w in _TOWNHOUSE_WORDS):
        return "townhouse"
    if any(w in folded_text for w in _HOUSE_WORDS):
        return "house"
    if any(w in folded_text for w in _APARTMENT_WORDS):
        return "apartment"
    return "other"


def _infer_bedrooms(folded_text: str, given: Any) -> int | None:
    if isinstance(given, int):
        return given
    # PT typology "T2" → 2 bedrooms (T0 = studio → 0).
    m = re.search(r"\bt(\d)\b", folded_text)
    return int(m.group(1)) if m else None


def normalize(raw: dict[str, Any]) -> Listing:
    """Build a validated `Listing` from a raw site dict; derive text features.

    Raises AppError (operational) if the record can't satisfy the schema — the
    pipeline skips it rather than crashing the batch.
    """
    text = f"{raw.get('title', '')} {raw.get('description_raw', '')}"
    folded = fold(text)

    data = dict(raw)
    data["property_type"] = _infer_property_type(folded, raw.get("property_type"))
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
    listing.ensure_id()
    return listing
