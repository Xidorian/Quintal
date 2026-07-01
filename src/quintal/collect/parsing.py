"""Parse the messy PT-formatted strings that come off listing cards.

The real gotcha here is European number formatting: '1.200' means 1200 (dot is the
thousands separator), while '1.200,50' means 1200.5 (comma is the decimal). Get this
wrong and every price is off by 1000×.
"""

from __future__ import annotations

import re


def parse_eu_number(text: str | None) -> float | None:
    """'1.200 €/mês' → 1200.0, '1.200,50' → 1200.5, '950' → 950.0, '85 m²' → 85.0."""
    if not text:
        return None
    # Keep digits and the two separators only.
    cleaned = re.sub(r"[^0-9.,]", "", str(text))
    if not cleaned:
        return None
    if "." in cleaned and "," in cleaned:
        # Both present: '.' is thousands, ',' is decimal.
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        # Only comma → decimal separator.
        cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        # Only dot: thousands sep if it groups 3 digits ('1.200'), else a decimal.
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", cleaned):
            cleaned = cleaned.replace(".", "")
        # else leave as a plain decimal ('85.5')
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_price(text: str | None) -> float | None:
    """Monthly rent in euros. Ignores '/mês', '/month', currency symbols."""
    return parse_eu_number(text)


def parse_area(text: str | None) -> float | None:
    """Living area in m². Takes the number immediately before an m²/m2 token if present."""
    if not text:
        return None
    m = re.search(r"([\d.,]+)\s*m(?:²|2)\b", str(text), re.IGNORECASE)
    return parse_eu_number(m.group(1)) if m else parse_eu_number(text)


def parse_bedrooms(text: str | None) -> int | None:
    """PT typology 'T2' → 2 (T2+1 → 3); also '2 quartos'/'2 assoalhadas'."""
    if not text:
        return None
    t = re.search(r"\bT(\d)(?:\s*\+\s*(\d))?\b", str(text), re.IGNORECASE)
    if t:
        return int(t.group(1)) + (int(t.group(2)) if t.group(2) else 0)
    q = re.search(r"(\d+)\s*(?:quartos?|assoalhadas?|bedrooms?)", str(text), re.IGNORECASE)
    return int(q.group(1)) if q else None


def parse_bathrooms(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(
        r"(\d+)\s*(?:casas?\s+de\s+banho|wc|bathrooms?|banhos?)", str(text), re.IGNORECASE
    )
    return int(m.group(1)) if m else None
