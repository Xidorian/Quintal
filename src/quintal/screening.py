"""Screen out short-term / holiday (Alojamento Local) rentals, and remember offenders.

We only want long-term rentals. Both portals' long-term searches leak them anyway:
Idealista carries holiday/AL stock (weekly/nightly pricing, "para férias", AL registration
numbers), and Imovirtual syndicates booking platforms whose listings quote a *minimum stay
in days* (QT-053). This detects them and records each in a persistent blocklist
("shitlist") so a re-run purges them immediately without re-reviewing.

Three shapes of evidence, in the order `short_term_reason` asks:
an AL registration number · a structural regex (seasonal month span, syndication title,
minimum stay in days) · a folded substring from `SHORT_TERM_PATTERNS`.
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
    # they read short-term but aren't: "estudantes" (a syndicated boilerplate names students,
    # professionals and families alike), "meses"/"minimo de" (match "contrato de 12 meses"),
    # "mes de" (a deposit), "hospedes" (a guest bedroom), "a partir de setembro" (an annual
    # let that starts in September). Note "estudantes" stays out on its own merits — the
    # platform whose boilerplate contains it is blocked by name below (QT-053).
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
    # Booking-platform syndication (QT-053). Imovirtual carries Uniplaces stock verbatim,
    # boilerplate and all: a "TERMOS E CONDIÇÕES DE ALOJAMENTO" header, a per-stay
    # "Duração Mínima de Aluguer: 30 dias", instant-book language. These are *stays*, not
    # home leases — 118 of the 646 ranked Algarve listings on 2026-09-30 were this one
    # platform, which is what "lots and lots of short-term rentals" actually was.
    #
    # The platform name is the pattern. It only ever appears in that syndicated block, so
    # unlike "estudantes" (which its boilerplate also contains, alongside "profissionais"
    # and "famílias") it carries no collateral: all 118 matches were minimum-stay bookings,
    # and nothing else in either pool mentions it. This REVERSES the QT-048 decision to
    # whitelist Uniplaces text — that call was aimed at "estudantes" and took the platform
    # name with it by accident.
    "uniplaces",
    "duracao minima de aluguer",
    "termos e condicoes de alojamento",
    "reservas e pedidos de informacao",
    # Booking/Airbnb "entire place" phrasing — a home lease never describes itself this way.
    "alojamento inteiro",
    # Corporate worker housing / company-only lets: a real listing, but never a home.
    "exclusivamente a empresas",
    "alojamento de trabalhadores",
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

# A minimum stay quoted in *days* is a booking, not a lease — "duração mínima de aluguer: 30
# dias", "mínimo de 5 dias". A year-round let states its minimum in months, or not at all.
_MIN_STAY_DAYS = re.compile(r"\bminim[ao]\b[^.\n]{0,40}?\b\d{1,3}\s*dias\b")
# Machine-generated syndication title: "Apartamento com 2 quartos - localizado em Albufeira".
# The plural after "1" ("com 1 quartos") gives the template away. Verified across both pools
# on 2026-09-30: 187 of 187 template titles that carried a description were Uniplaces stays
# and zero were anything else — and it catches the 830 Norte cards that carry NO description
# for the text patterns above to bite on.
_SYNDICATED_TITLE = re.compile(r"\bcom \d+ quartos? - localizado em\b")


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
    if _SYNDICATED_TITLE.search(text):
        return "booking-platform syndication title"
    if _MIN_STAY_DAYS.search(text):
        return "minimum stay quoted in days"
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
