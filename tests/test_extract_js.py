"""Gate on `src/quintal/collect/extract.js` — the in-browser card extractor.

WHY THIS FILE EXISTS
extract.js is pasted into a live logged-in browser, so for most of this project's life it had
no test at all. Every other stage speaks the `Listing` contract and is covered by pytest; the
one stage that *creates* the data was checked by eye. Both bugs it has produced were therefore
found as corrupted rows in the collected pool rather than as a failing test:

  QT-049 (2026-09-04)  imovirtual's SSR emitted a styled-components rule *inside* the price
                       cell, so a raw .textContent read the rent out of a colour and a
                       font-size — thirteen Faro listings priced at EUR 0.63/month, which
                       would have ranked as the most undervalued property in the Algarve.
  QT-050 (2026-09-26)  imovirtual nulled address.city/address.province, so every organic card
                       lost its freguesia and geocoded to a concelho centroid. Silent: the
                       concelho stayed correct, only the beach walk-time degraded.

Both are *data truth* failures on the product's critical path (Quintal's whole value is an
honest relative valuation), so they get a real gate, not a source-diff. The harness runs the
actual extract.js in jsdom over saved fixtures and this module asserts on the rows — then
pushes those same rows through the real Python adapters, so the JS extraction and the Python
parsing are verified to agree on one shared input rather than merely looking aligned.

alarm-proved 2026-09-26 — both regressions were planted back into a throwaway copy of
extract.js (plain .textContent for QT-049; addr.city-only for QT-050) and each turned the
corresponding test below red. See the STATUS.md entry for the observed failure output.

WHAT THIS GATE DOES AND DOES NOT DO
It pins the parsing contract and the two known regression classes. It does **not** detect
future production drift on its own: the fixtures are a snapshot, so a portal changing its
markup next month breaks the real pull while these tests stay green. Re-capture the fixtures
when a pull looks wrong — see tests/fixtures/extract/README.md for how.

Requires node + `npm install` (jsdom). Skipped, loudly, when they are absent.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from quintal.collect import idealista, imovirtual

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "extract_harness.mjs"
FIXTURES = ROOT / "tests" / "fixtures" / "extract"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not (ROOT / "node_modules" / "jsdom").is_dir(),
    reason="extract.js harness needs node + `npm install` (jsdom); see tests/test_extract_js.py",
)


def _extract(fixture: str, site: str) -> list[dict]:
    """Run the real extract.js over a fixture and return the rows it produced."""
    proc = subprocess.run(
        ["node", str(HARNESS), str(FIXTURES / fixture), site],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=ROOT,
    )
    assert proc.returncode == 0, f"harness failed:\n{proc.stderr}"
    return json.loads(proc.stdout)["rows"]


def _by_id(rows: list[dict], needle: str) -> dict:
    matches = [r for r in rows if needle in r["url"]]
    assert len(matches) == 1, f"expected exactly one row matching {needle!r}, got {len(matches)}"
    return matches[0]


# --- Selector contract: the extractor still finds the cards at all ---------------------
def test_imovirtual_cards_are_found():
    # A selector change that finds zero cards is the worst failure mode: `--cull` would read
    # an empty pull as "everything is delisted" and wipe the live pool.
    rows = _extract("imovirtual-search.html", "imovirtual")
    assert len(rows) == 3
    assert all(r["url"].startswith("https://www.imovirtual.com/") for r in rows)
    assert all(r["price_text"] for r in rows), "every card must yield a price"


def test_idealista_cards_are_found():
    rows = _extract("idealista-search.html", "idealista")
    assert len(rows) == 2
    assert all("/imovel/" in r["url"] for r in rows)


# --- QT-050: the freguesia must survive imovirtual nulling address.city ----------------
def test_imovirtual_location_keeps_the_freguesia():
    """The fixture was captured *after* imovirtual nulled address.city/address.province, so
    reverseGeocoding is the only remaining source of the parish and district. Reading the
    freguesia from addr.city (as the code did before QT-050) collapses this to a bare
    concelho, and _geocode_queries is freguesia-first precisely because a concelho centroid
    inflates beach walk-time badly (Vilamoura-as-inland-Loulé read ~119 min from the sea).
    """
    rows = _extract("imovirtual-search.html", "imovirtual")

    # The canary: a card whose freguesia genuinely differs from its concelho. A regression to
    # addr.city would leave this as "Lagos" alone.
    lagos = _by_id(rows, "ID1iUGn")
    assert lagos["location"] == "São Gonçalo de Lagos, Lagos, Faro"

    # Every card carries the full "freguesia, concelho, District" triple, from either the
    # __NEXT_DATA__ path or the address-<p> fallback (ID1iUwb is not in the blob).
    for row in rows:
        parts = [p.strip() for p in row["location"].split(",") if p.strip()]
        assert len(parts) >= 3, f"lost the freguesia/district: {row['location']!r}"
        assert parts[-1] == "Faro", f"district suffix missing: {row['location']!r}"


def test_imovirtual_location_parses_to_the_right_concelho_and_freguesia():
    """Cross-surface check: the JS extraction and the Python parser must agree on one shared
    input. Diffing the two files would only prove they look aligned."""
    rows = _extract("imovirtual-search.html", "imovirtual")

    raw = imovirtual.to_raw(_by_id(rows, "ID1iUGn"))
    assert raw["concelho"] == "Lagos"
    assert raw["freguesia"] == "São Gonçalo de Lagos"

    raw = imovirtual.to_raw(_by_id(rows, "ID1iV78"))
    assert raw["concelho"] == "Portimão"
    assert raw["freguesia"] == "Portimão"


# --- QT-049: inline CSS in the price cell must never be read as the rent ---------------
def test_imovirtual_price_cell_ignores_inline_css():
    """The incident fixture restores the styled-components <style> that imovirtual's SSR put
    inside the price cell. Without txt()'s <style> stripping, the cell's textContent begins
    '.css-6t3bie{color:#071121FF;font-size:19px;...}1000 €' and parse_price reads the digits
    out of the colour and font size instead of the rent.
    """
    rows = _extract("imovirtual-price-css-incident.html", "imovirtual")
    assert len(rows) == 1
    price_text = rows[0]["price_text"]

    # NOTE: these two assertions are the actual gate, and they must stay at the JS boundary.
    # QT-049 fixed this at *both* ends, so `_rent_only`'s _CSS_RULE strip would quietly repair
    # a JS regression and keep price_eur_month at 1000.0 — proved by planting the regression
    # (2026-09-26): the price assertion below stayed green while these two went red. Asserting
    # only on the parsed price would therefore test nothing about extract.js.
    assert "css-" not in price_text, f"inline CSS leaked into the price: {price_text!r}"
    assert "{" not in price_text and "font-size" not in price_text

    # The Python second line of defence still has to land on the real rent.
    raw = imovirtual.to_raw(rows[0])
    assert raw["price_eur_month"] == 1000.0


def test_imovirtual_price_strips_the_per_m2_suffix():
    # Card ID1iUwb carries the real '680 €12,36 €/m²' concatenation — the rent is everything
    # before the first euro sign, or parse_price would read '68012.36'.
    rows = _extract("imovirtual-search.html", "imovirtual")
    row = _by_id(rows, "ID1iUwb")
    assert "/m²" in row["price_text"], "fixture no longer exercises the €/m² concatenation"
    assert imovirtual.to_raw(row)["price_eur_month"] == 680.0


# --- Idealista: private-vs-agency branding, and the title-derived concelho -------------
def test_idealista_private_landlord_detection():
    """`is_private` decides which duplicate wins as canonical in dedup.py, so a branding
    selector change silently flips every listing to 'private'."""
    rows = _extract("idealista-search.html", "idealista")
    assert _by_id(rows, "34419275")["is_private"] is True  # no agency branding on the card
    assert _by_id(rows, "35358106")["is_private"] is False  # agency-branded card


def test_idealista_row_parses_through_the_python_adapter():
    rows = _extract("idealista-search.html", "idealista")

    raw = idealista.to_raw(_by_id(rows, "34419275"))
    assert raw["price_eur_month"] == 850.0
    assert raw["bedrooms"] == 2
    assert raw["size_m2"] == 80.0
    # Idealista embeds the location in the title, so the concelho is its last comma token.
    # (The derived `freguesia` is title junk here — "Moradia em banda na Rua do Jardim" — which
    # is expected: enrich._place_ok rejects it and QT-042's reverse-geocode pass supersedes it.)
    assert raw["concelho"] == "Lagos"

    raw = idealista.to_raw(_by_id(rows, "35358106"))
    assert raw["price_eur_month"] == 1150.0
    assert raw["concelho"] == "Luz"
