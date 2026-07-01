"""Parse the messy PT-formatted strings that come off listing cards.

The real gotcha here is European number formatting: '1.200' means 1200 (dot is the
thousands separator), while '1.200,50' means 1200.5 (comma is the decimal). Get this
wrong and every price is off by 1000×.
"""

from __future__ import annotations

import re


def parse_eu_number(text: str | None) -> float | None:
    """Parse a number in either PT/EU or EN formatting.

    PT/EU: '1.200 €/mês' → 1200.0, '1.200,50' → 1200.5
    EN:    '1,100€/month' → 1100.0, '1,234.50' → 1234.5
    Plain: '950' → 950.0, '85 m²' → 85.0

    Rule: when both separators appear, whichever comes last is the decimal point.
    With a single separator, a 3-digit trailing group means thousands ('1.200'/'1,100'),
    anything else is a decimal ('85,5'/'85.5').
    """
    if not text:
        return None
    cleaned = re.sub(r"[^0-9.,]", "", str(text))
    if not cleaned:
        return None

    has_dot, has_comma = "." in cleaned, "," in cleaned
    if has_dot and has_comma:
        if cleaned.rfind(",") > cleaned.rfind("."):  # comma last → EU decimal
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:  # dot last → EN decimal
            cleaned = cleaned.replace(",", "")
    elif has_comma:
        if cleaned.count(",") > 1 or len(cleaned.rsplit(",", 1)[1]) == 3:
            cleaned = cleaned.replace(",", "")  # grouping separator
        else:
            cleaned = cleaned.replace(",", ".")  # decimal
    elif has_dot:
        if cleaned.count(".") > 1 or len(cleaned.rsplit(".", 1)[1]) == 3:
            cleaned = cleaned.replace(".", "")  # grouping separator
        # else a plain decimal ('85.5')
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
