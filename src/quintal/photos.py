"""Listing thumbnails via the Open Graph image on each detail page.

Per-listing fallback chain (resilience principle): og:image → twitter:image → skip
(the UI shows a placeholder). The image is downloaded once to
``data/photos/<listing_id>.jpg`` and skipped on re-runs, so a flaky upstream isn't
re-hit and an interrupted backfill resumes where it stopped.

Coverage note: Idealista detail pages are DataDome-protected and return 403 to
server-side fetches, so this covers Imovirtual today. Idealista thumbnails need the
logged-in browser session (see NEXT.md) — those listings fall through to a placeholder.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import requests

from .errors import AppError
from .logconf import get_logger
from .normalize import normalize
from .collect import store

log = get_logger()

DEFAULT_DIR = "data/photos"
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
# Ordered so the primary social image wins; twitter:image is the graceful second source.
_META_PATTERNS = (
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
)


def og_image_url(html: str) -> str | None:
    """Best social-preview image URL from page HTML, or None."""
    for pat in _META_PATTERNS:
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1)
    return None


def photo_path(listing_id: str, photos_dir: str | Path = DEFAULT_DIR) -> Path:
    return Path(photos_dir) / f"{listing_id}.jpg"


def fetch_one(
    listing_id: str, source_url: str, session: requests.Session, photos_dir: str | Path
) -> str:
    """Fetch+store one listing's thumbnail. Returns a status: cached|ok|blocked|no-image|error."""
    out = photo_path(listing_id, photos_dir)
    if out.exists():
        return "cached"
    try:
        resp = session.get(source_url, timeout=20)
    except requests.RequestException:
        return "error"
    if resp.status_code == 403:
        return "blocked"  # DataDome etc. — needs the browser session
    if resp.status_code != 200:
        return "error"
    img_url = og_image_url(resp.text)
    if not img_url:
        return "no-image"
    try:
        img = session.get(img_url, timeout=20)
    except requests.RequestException:
        return "error"
    if img.status_code != 200 or not img.headers.get("Content-Type", "").startswith("image/"):
        return "error"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(img.content)
    return "ok"


def backfill(input_path: str, photos_dir: str | Path = DEFAULT_DIR, delay: float = 0.8) -> dict:
    """Fetch a thumbnail for every stored listing that lacks one. Resumable + polite."""
    session = requests.Session()
    session.headers["User-Agent"] = _UA
    listings = []
    for raw in store.load(input_path).values():
        try:
            listings.append(normalize(raw))  # per-item isolation: one bad record can't abort
        except AppError:
            continue
    stats: dict[str, int] = {}
    for i, listing in enumerate(listings, 1):
        if not listing.source_url:
            stats["no-url"] = stats.get("no-url", 0) + 1
            continue
        status = fetch_one(listing.listing_id, listing.source_url, session, photos_dir)
        stats[status] = stats.get(status, 0) + 1
        if status in ("ok", "no-image"):
            time.sleep(delay)  # pace only real page fetches; a fast 403/cached needs no wait
        if i % 50 == 0:
            log.info("photo backfill progress", extra={"event": "photos", "ctx_done": i, **{f"ctx_{k}": v for k, v in stats.items()}})
    log.info("photo backfill complete", extra={"event": "photos_done", **{f"ctx_{k}": v for k, v in stats.items()}})
    return stats


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Backfill listing thumbnails via og:image")
    p.add_argument("--input", default="data/listings.jsonl")
    p.add_argument("--dir", default=DEFAULT_DIR)
    p.add_argument("--delay", type=float, default=0.8)
    args = p.parse_args()
    stats = backfill(args.input, args.dir, args.delay)
    print("photos:", ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))


if __name__ == "__main__":
    main()
