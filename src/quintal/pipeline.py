"""Orchestrate the brain: load → normalize → dedup → enrich → value → score → render.

Per-item error isolation: one malformed listing is logged and skipped, never aborts the
batch (operational vs programmer errors, per house standards).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dedup import dedup
from .enrich import enrich_listings
from .errors import AppError
from .logconf import get_logger
from .normalize import normalize
from .render_html import render
from .schema import Listing
from .score import score_listing
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
) -> list[Listing]:
    raw_rows = load_jsonl(input_path)

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

    listings = dedup(listings)
    listings = enrich_listings(listings, chain=[])  # no enrichers in step 1
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
    args = parser.parse_args()

    listings = run(args.input, args.html, synthetic=args.synthetic)

    print(f"\n{len(listings)} listings (top by match):")
    for listing in listings[:10]:
        band = listing.valuation_band or "unvalued"
        pct = f"{listing.valuation_pct * 100:+.0f}%" if listing.valuation_pct is not None else "—"
        price = f"€{listing.price_eur_month:>6.0f}"
        print(f"  {listing.match_score:>3}/100  {band:<12} {pct:>5}  {price}  {listing.title}")


if __name__ == "__main__":
    main()
