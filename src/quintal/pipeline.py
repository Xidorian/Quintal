"""Orchestrate the brain: load → normalize → dedup → enrich → value → score → render.

Per-item error isolation: one malformed listing is logged and skipped, never aborts the
batch (operational vs programmer errors, per house standards).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from . import descriptions, liveness
from . import enrich as enrich_mod
from .dedup import dedup
from .enrich import default_chain, enrich_listings
from .errors import AppError
from .logconf import get_logger
from .normalize import normalize
from .render_html import render
from .schema import Listing
from .score import score_listing
from .screening import Blocklist, screen
from .valuation import value_pool

log = get_logger()


def load_jsonl(path: str | Path) -> list[dict]:
    rows: list[dict] = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            log.warning(
                "skipping malformed jsonl line",
                extra={"event": "bad_jsonl", "ctx_line": i, "ctx_err": str(exc)},
            )
    return rows


def run(
    input_path: str | Path,
    html_out: str | Path | None = None,
    *,
    synthetic: bool = False,
    enrich: bool = False,
    blocklist_path: str | Path = "data/blocklist.json",
    cache_path: str | Path = "data/enrichment_cache.json",
    descriptions_path: str | Path = descriptions.DEFAULT_PATH,
    delisted_path: str | Path = liveness.DEFAULT_PATH,
    geo_path: str | Path = enrich_mod.DEFAULT_GEO_PATH,
) -> list[Listing]:
    raw_rows = load_jsonl(input_path)

    # Layer in detail-page descriptions (Imovirtual cards have none) before deriving
    # yard/bathtub/pets from text. No-op when the sidecar is absent.
    enriched = descriptions.apply(raw_rows, descriptions_path)
    if enriched:
        log.info(
            "applied detail descriptions",
            extra={"event": "descriptions_applied", "ctx_enriched": enriched},
        )

    listings: list[Listing] = []
    for raw in raw_rows:
        try:
            listings.append(normalize(raw))
        except AppError as exc:
            log.warning(
                "skipping invalid listing", extra={"event": "normalize_skip", "ctx_err": str(exc)}
            )
    log.info(
        "normalized listings",
        extra={"event": "normalized", "ctx_kept": len(listings), "ctx_seen": len(raw_rows)},
    )

    # Drop delisted listings (HTTP 410/404) before valuing — a gone listing wastes a click
    # and its price shouldn't anchor the relative valuation.
    listings, delisted_n = liveness.drop_delisted(listings, delisted_path)
    if delisted_n:
        log.info(
            "dropped delisted listings",
            extra={"event": "delisted_dropped", "ctx_dropped": delisted_n},
        )

    # Purge short-term / holiday rentals and remember them (they poison the valuation pool).
    blocklist = Blocklist(blocklist_path)
    listings, purged = screen(listings, blocklist)
    blocklist.save()
    log.info(
        "screened short-term rentals",
        extra={"event": "screened", "ctx_purged": purged, "ctx_kept": len(listings)},
    )

    listings = dedup(listings)

    # Persisted geo first (zero network): fills already-known listings so a plain run keeps
    # geo and an enrich run only hits the network for genuinely new localities.
    applied = enrich_mod.apply_geo(listings, geo_path)
    if applied:
        log.info("applied persisted geo", extra={"event": "geo_applied", "ctx_applied": applied})

    if enrich:
        ors_key = os.environ.get("OPENROUTESERVICE_API_KEY")
        client, chain = default_chain(cache_path, ors_key=ors_key)
        enrich_listings(listings, chain)
        client.save()
        saved = enrich_mod.save_geo(listings, geo_path)  # persist for future/plain runs
        located = sum(1 for listing in listings if listing.lat is not None)
        log.info(
            "enriched listings",
            extra={
                "event": "enriched",
                "ctx_located": located,
                "ctx_total": len(listings),
                "ctx_geo_saved": saved,
            },
        )

    value_pool(listings)
    for listing in listings:
        listing.match_score, listing.match_breakdown = score_listing(listing)

    listings.sort(key=lambda listing: listing.match_score or 0, reverse=True)

    if html_out:
        out = render(listings, html_out, synthetic=synthetic)
        log.info(
            "wrote html",
            extra={"event": "html_written", "ctx_path": str(out), "ctx_count": len(listings)},
        )

    return listings


def main() -> None:
    parser = argparse.ArgumentParser(description="Quintal — rank and value Algarve rentals")
    parser.add_argument("--input", required=True, help="path to listings .jsonl")
    parser.add_argument("--html", help="output HTML path (e.g. out/listings.html)")
    parser.add_argument(
        "--synthetic", action="store_true", help="flag the data as synthetic in the page"
    )
    parser.add_argument(
        "--enrich", action="store_true", help="geocode + beach walk-time + ruralness (OSM APIs)"
    )
    args = parser.parse_args()

    if args.enrich:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

    listings = run(args.input, args.html, synthetic=args.synthetic, enrich=args.enrich)

    print(f"\n{len(listings)} listings (top by match):")
    for listing in listings[:10]:
        band = listing.valuation_band or "unvalued"
        pct = f"{listing.valuation_pct * 100:+.0f}%" if listing.valuation_pct is not None else "—"
        price = f"€{listing.price_eur_month:>6.0f}"
        print(f"  {listing.match_score:>3}/100  {band:<12} {pct:>5}  {price}  {listing.title}")


if __name__ == "__main__":
    main()
