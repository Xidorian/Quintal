"""Static ranked HTML page — the step-1 proof of the scoring/valuation brain.

Renders listings into a self-contained page whose three sort modes (best fit / best
deal / blend) and light filters run client-side, so it's a single openable file with no
server. The real interactive layer is the Streamlit app (Phase 4).
"""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config
from .schema import Listing

_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


def _view(listing: Listing) -> dict:
    band = listing.valuation_band
    band_meta = (
        config.BANDS.get(band, {"emoji": "❔", "label": "Unvalued"})
        if band
        else {"emoji": "❔", "label": "Unvalued"}
    )
    return {
        "id": listing.listing_id,
        "title": listing.title or "(untitled)",
        "concelho": listing.concelho,
        "freguesia": listing.freguesia,
        "price": listing.price_eur_month,
        "size": listing.size_m2,
        "beds": listing.bedrooms,
        "baths": listing.bathrooms,
        "type": listing.property_type,
        "furnished": listing.furnished,
        "yard": bool(listing.has_yard.value),
        "terrace": bool(listing.has_terrace.value),
        "bathtub": bool(listing.has_bathtub.value),
        "pets": listing.pets.value,
        "walk_min": listing.walk_min_beach,
        "dist_beach": listing.dist_beach_m,
        "dist_town": listing.dist_town_m,
        "match_score": listing.match_score,
        "breakdown": listing.match_breakdown,
        "valuation_pct": listing.valuation_pct,
        "band": band or "none",
        "band_emoji": band_meta["emoji"],
        "band_label": band_meta["label"],
        "expected": listing.valuation_expected_eur,
        "confidence": listing.valuation_confidence,
        "why": listing.valuation_why,
        "source": listing.source,
        "url": listing.source_url,
        "also_listed_at": listing.also_listed_at,
    }


def render(listings: list[Listing], out_path: str | Path, *, synthetic: bool = False) -> Path:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("listings.html.j2")
    views = [_view(listing) for listing in listings]
    # Embed in a <script> tag safely: neutralise any "</" that could close it early.
    payload = json.dumps(views, ensure_ascii=False).replace("</", "<\\/")
    html = template.render(
        listings_json=payload,
        count=len(views),
        synthetic=synthetic,
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
