"""Collection CLI.

Two actions:
  --print-urls   emit the search-result URLs to open in your logged-in Chrome (default)
  --ingest FILE  map a JSON array of extracted card rows into data/listings.jsonl

Runtime flow: print URLs → open them in Chrome → extract the visible cards (via the
browser tools) into a JSON array of ExtractedRow → feed it back with --ingest. The
scoring pipeline then reads data/listings.jsonl as usual.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..logconf import get_logger
from . import idealista, imovirtual, store
from .base import SearchParams

log = get_logger()
ADAPTERS = {a.name: a for a in (idealista, imovirtual)}
DEFAULT_STORE = "data/listings.jsonl"


def _params(args: argparse.Namespace) -> SearchParams:
    return SearchParams(
        region=args.region,
        max_price=args.max_price,
        min_beds=args.min_beds,
        max_beds=args.max_beds,
    )


def print_urls(sites: list[str], params: SearchParams, pages: int) -> None:
    for site in sites:
        print(f"\n# {site}")
        for url in ADAPTERS[site].search_urls(params, pages=pages):
            print(url)


def ingest(site: str, rows_path: str, store_path: str) -> None:
    rows = json.loads(Path(rows_path).read_text(encoding="utf-8"))
    raw = [ADAPTERS[site].to_raw(row) for row in rows]
    added, updated = store.upsert(store_path, raw)
    log.info(
        "ingested extracted rows",
        extra={"event": "ingested", "ctx_site": site, "ctx_added": added, "ctx_updated": updated},
    )
    print(f"{site}: +{added} new, {updated} updated → {store_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quintal collection (browser-session based)")
    parser.add_argument("--site", choices=[*ADAPTERS, "all"], default="all")
    parser.add_argument(
        "--region", default="algarve", help="canonical region; each adapter maps it to its slug"
    )
    parser.add_argument("--max-price", type=int, default=1500)
    parser.add_argument("--min-beds", type=int, default=2)
    parser.add_argument("--max-beds", type=int, default=4)
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument(
        "--print-urls", action="store_true", help="emit search URLs (default action)"
    )
    parser.add_argument(
        "--ingest", metavar="ROWS_JSON", help="ingest extracted card rows from a JSON file"
    )
    parser.add_argument("--store", default=DEFAULT_STORE)
    args = parser.parse_args()

    sites = list(ADAPTERS) if args.site == "all" else [args.site]

    if args.ingest:
        if args.site == "all":
            parser.error("--ingest needs a single --site (rows come from one site)")
        ingest(args.site, args.ingest, args.store)
    else:
        print_urls(sites, _params(args), args.pages)


if __name__ == "__main__":
    main()
