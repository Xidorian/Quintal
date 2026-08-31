"""Screen out short-term / holiday (Alojamento Local) rentals, and remember offenders.

We only want long-term rentals. Idealista's long-term search still leaks holiday/AL
listings (weekly/nightly pricing, "para férias", AL registration numbers). This detects
them and records each in a persistent blocklist ("shitlist") so a re-run purges them
immediately without re-reviewing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .normalize import fold
from .schema import Listing

# Folded (accent-stripped, lowercased) substrings that mark a short-term/holiday let.
SHORT_TERM_PATTERNS = [
    "para ferias",
    "de ferias",
    "aluguer de ferias",
    "arrendamento de ferias",
    "holiday",
    "short term",
    "short-term",
    "temporada",
    "temporaria",
    "temporario",
    "alojamento local",
    "arrendamento apenas para o periodo",
    "apenas para o periodo",
    "por noite",
    "per night",
    "por semana",
    "per week",
    "/noite",
    "/semana",
    # instant-book / holiday-platform language — long-term listings don't say this
    "reserve em linha",
    "reserva online",
    "reserve online",
    "book online",
    "booking.com",
    # seasonal / academic-year lets (not year-round) — we need a permanent home
    "a final de maio",
    "a final de junho",
    "epoca baixa",
    "temporada baixa",
    # explicit duration language (QT-048). Verified against the live pool: each of these
    # only ever appeared on genuinely short/medium-term lets. Deliberately NOT added, because
    # they read short-term but aren't: "estudantes" (Uniplaces boilerplate names students,
    # professionals and families alike), "meses"/"minimo de" (match "contrato de 12 meses"),
    # "mes de" (a deposit), "hospedes" (a guest bedroom), "a partir de setembro" (an annual
    # let that starts in September).
    "curta duracao",
    "media duracao",
    "curto prazo",
    "medio prazo",
    "medium term",
    "medium-term",
    "short let",
    "winter let",
    "arrendamento de inverno",
    "arrendamentos de inverno",
    "estadias de inverno",
    "nao e um arrendamento anual",
    "ano letivo",
    "ano lectivo",
    "erasmus",
]
# Alojamento Local registration, e.g. "151506/AL".
_AL_REGISTRATION = re.compile(r"\b\d{3,6}\s*/\s*al\b")
# Academic-year / seasonal spans: an autumn/winter start month paired with a spring/summer
# end month — "setembro a junho", "de 30 de setembro a 30 de abril", "novembro 2025 ate maio
# 2026", "outubro 2026 e maio 2027", "setembro 2026-junho 2027", "de 15 nov a 30 jun". Text is
# folded (accent-stripped), so "até" reads "ate". Bounded by 20/15 non-period chars so it
# tolerates a day-and-year on each side but won't span a sentence and over-match a year-round
# listing.
#
# Widened 2026-08-31 (QT-048): the old form only knew setembro|outubro → maio|junho|julho
# joined by "a"/"ate", so it missed every november/december start, every march/april end, the
# "e" connector, the dash form, and abbreviated months — 32 winter lets in the Algarve pool
# alone. Every "e"-connector match was hand-audited before widening: all were real seasonal
# lets, one saying "nao e um arrendamento anual" outright.
_START_MONTH = r"(?:setembro|set|outubro|out|novembro|nov|dezembro|dez)"
_END_MONTH = r"(?:marco|mar|abril|abr|maio|mai|junho|jun|julho|jul)"
_SEASONAL_SPAN = re.compile(
    rf"\b{_START_MONTH}\b[^.\n]{{0,20}}(?:\b(?:a|ate|e)\b|[-\u2013\u2014])[^.\n]{{0,15}}\b{_END_MONTH}\b"
)


def short_term_reason(raw_text: str) -> str | None:
    """Reason string if this *text* reads short-term/AL, else None. Folds the text itself.

    Text-level so anything holding listing prose can ask the same question — the feedback
    report re-runs it over 👎-flagged listings to tell "we now catch this" from "still slips".
    """
    text = fold(raw_text)
    if _AL_REGISTRATION.search(text):
        return "AL registration number"
    if _SEASONAL_SPAN.search(text):
        return "seasonal month-range span"
    for pattern in SHORT_TERM_PATTERNS:
        if pattern in text:
            return f"matched '{pattern}'"
    return None


def is_short_term(listing: Listing) -> str | None:
    """Return a reason string if this looks like a short-term/AL rental, else None."""
    return short_term_reason(f"{listing.title or ''} {listing.description_raw}")


class Blocklist:
    """Persistent set of listing ids known to be short-term, with the reason each was flagged."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.entries: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def contains(self, key: str) -> bool:
        return key in self.entries

    def add(self, key: str, reason: str) -> None:
        self.entries[key] = reason

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.entries, ensure_ascii=False, indent=2)
        self.path.write_text(payload, encoding="utf-8")


def screen(listings: list[Listing], blocklist: Blocklist) -> tuple[list[Listing], int]:
    """Drop already-blocklisted and newly-detected short-term listings; add new ones to the
    blocklist. Returns (kept_listings, purged_count). Caller saves the blocklist."""
    kept: list[Listing] = []
    purged = 0
    for listing in listings:
        lid = listing.ensure_id()
        if blocklist.contains(lid):
            purged += 1
            continue
        reason = is_short_term(listing)
        if reason:
            blocklist.add(lid, reason)
            purged += 1
            continue
        kept.append(listing)
    return kept, purged
