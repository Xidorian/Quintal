"""Detect delisted listings so a stale pool doesn't show Malia homes that are gone (QT-026).

Listings expire fast — a 2026-07-08 pull had ~13% of its Imovirtual listings already
returning HTTP 410 Gone eleven days later. A delisted listing is worse than useless: it
wastes a viewing click *and* its price still anchors the relative valuation. This probes
detail pages and records the gone ones in a persistent ``data/delisted.json`` set, which the
pipeline drops before valuing/ranking (mirroring how ``screening.py`` purges short-term lets).

Server-side detail fetches only work for Imovirtual (Idealista is DataDome-403, same as
``photos.py``/``descriptions.py``) — Idealista liveness needs the logged-in browser session.

Probe:  python -m quintal.liveness
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from .collect import store
from .logconf import get_logger
from .schema import Listing

log = get_logger()

DEFAULT_PATH = "data/delisted.json"
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
_ENRICHABLE = {"imovirtual"}  # the only source we can probe server-side
_GONE = {404, 410}  # deliberate "removed" statuses; NOT 5xx/timeouts (transient)


def load(path: str | Path = DEFAULT_PATH) -> dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save(data: dict[str, str], path: str | Path = DEFAULT_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def drop_delisted(
    listings: list[Listing], path: str | Path = DEFAULT_PATH
) -> tuple[list[Listing], int]:
    """Remove listings whose source_url is known-delisted. Returns (kept, dropped_count).

    A no-op when the set is empty, so the pipeline can always call it.
    """
    gone = load(path)
    if not gone:
        return listings, 0
    kept = [x for x in listings if (x.source_url or "") not in gone]
    return kept, len(listings) - len(kept)


_ABSENT = "absent"  # cull reason — reversible, unlike the sticky 404/410 probe results


def cull_absent(
    site: str,
    pulled_urls: set[str],
    input_path: str,
    path: str | Path = DEFAULT_PATH,
) -> tuple[int, int]:
    """Mark `site` listings absent from a **complete** pull as delisted, and resurrect any
    previously-absent ones that reappeared. Returns (culled, resurrected).

    This is the idealista counterpart to :func:`probe`: idealista IP-rate-limits detail-page
    liveness checks, so instead of probing we treat a *complete* search pull as authoritative —
    any listing of that site still in the store but not re-seen in the pull is no longer listed,
    so it is culled. The cull is recorded with reason ``"absent"`` rather than a 404/410 status,
    which keeps it **reversible**: a URL that comes back in a later pull (idealista indexing
    blips, or a listing re-posted) is un-culled, whereas a real ``probe`` 404/410 stays sticky.

    CALLER CONTRACT: only pass a pull that paged to exhaustion. A partial pull would cull live
    listings sitting on the pages you didn't collect. ``pulled_urls`` is the set of source_urls
    from that pull; ``input_path`` is the store (read to enumerate the site's current listings).
    """
    gone = load(path)
    resurrected = 0
    for url in pulled_urls:
        if gone.get(url) == _ABSENT:  # back in the search → no longer gone (404/410 stays sticky)
            del gone[url]
            resurrected += 1
    site_urls = {
        r["source_url"]
        for r in store.load(input_path).values()
        if r.get("source") == site and r.get("source_url")
    }
    culled = 0
    for url in site_urls - pulled_urls:
        if url not in gone:  # don't clobber a real 404/410, don't re-count an existing cull
            gone[url] = _ABSENT
            culled += 1
    save(gone, path)
    log.info(
        "culled absent listings",
        extra={
            "event": "culled_absent",
            "ctx_site": site,
            "ctx_culled": culled,
            "ctx_resurrected": resurrected,
        },
    )
    return culled, resurrected


def probe(input_path: str, path: str | Path = DEFAULT_PATH, delay: float = 0.4) -> dict:
    """Probe enrichable listings and record HTTP 404/410 (gone) ones. Resumable + polite.

    Known-delisted urls are skipped (a removed listing stays removed); everything else is
    re-checked each run so a listing that dies later gets caught. Transient errors (5xx,
    timeouts) are never recorded as delisted.
    """
    session = requests.Session()
    session.headers["User-Agent"] = _UA
    gone = load(path)
    stats: dict[str, int] = {}
    rows = list(store.load(input_path).values())
    try:
        for i, row in enumerate(rows, 1):
            url = row.get("source_url")
            if row.get("source") not in _ENRICHABLE or not url:
                stats["skip"] = stats.get("skip", 0) + 1
                continue
            if url in gone:
                stats["known-gone"] = stats.get("known-gone", 0) + 1
                continue
            try:
                code = session.get(url, timeout=15, allow_redirects=True).status_code
            except requests.RequestException:
                stats["error"] = stats.get("error", 0) + 1
                continue
            if code in _GONE:
                gone[url] = str(code)
                stats["gone"] = stats.get("gone", 0) + 1
            elif code == 200:
                stats["live"] = stats.get("live", 0) + 1
            else:
                stats[f"http-{code}"] = stats.get(f"http-{code}", 0) + 1
            time.sleep(delay)
            if i % 100 == 0:
                save(gone, path)  # checkpoint
    finally:
        save(gone, path)
    log.info(
        "liveness probe complete",
        extra={"event": "liveness_done", **{f"ctx_{k}": v for k, v in stats.items()}},
    )
    return stats


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Probe listings and record delisted (410/404) ones")
    p.add_argument("--input", default="data/listings.jsonl")
    p.add_argument("--path", default=DEFAULT_PATH)
    p.add_argument("--delay", type=float, default=0.4)
    args = p.parse_args()
    stats = probe(args.input, args.path, args.delay)
    print("liveness:", ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))


if __name__ == "__main__":
    main()
