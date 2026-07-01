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
    "outubro a maio",
    "outubro a junho",
    "setembro a maio",
    "setembro a junho",
    "a final de maio",
    "a final de junho",
    "epoca baixa",
    "temporada baixa",
]
# Alojamento Local registration, e.g. "151506/AL".
_AL_REGISTRATION = re.compile(r"\b\d{3,6}\s*/\s*al\b")


def is_short_term(listing: Listing) -> str | None:
    """Return a reason string if this looks like a short-term/AL rental, else None."""
    text = fold(f"{listing.title or ''} {listing.description_raw}")
    if _AL_REGISTRATION.search(text):
        return "AL registration number"
    for pattern in SHORT_TERM_PATTERNS:
        if pattern in text:
            return f"matched '{pattern}'"
    return None


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
