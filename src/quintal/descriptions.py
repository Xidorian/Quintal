"""Imovirtual detail-page descriptions → richer amenity text (QT-024).

Imovirtual *search cards* carry no description, so those listings derive yard/bathtub/pets
from their title alone. The *detail pages* do carry the owner's full text — but not where
you'd expect: the visible ``data-cy="adPageAdDescription"`` div is empty in the
server-rendered HTML (React fills it client-side). The real text sits in the page's
``__NEXT_DATA__`` JSON under a ``"description"`` key, next to two auto-generated boilerplate
summaries ("Descubra esta…", "Encontre a sua casa de sonho…"). We take the **longest
non-boilerplate** JSON ``"description"`` value, JSON-unescape it, and strip its HTML tags.

Results are cached to ``data/descriptions.json`` keyed by ``source_url`` — a sidecar that
layers on top of ``listings.jsonl`` (which stays raw-collected truth and survives
re-collection). Idealista detail pages are DataDome-protected (403 server-side), same as
``photos.py``, so this covers Imovirtual — the source that actually needs it.

Backfill:  python -m quintal.descriptions
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

from .collect import store
from .logconf import get_logger

log = get_logger()

DEFAULT_PATH = "data/descriptions.json"
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
# Only this source needs (and allows) server-side detail fetches; Idealista 403s.
_ENRICHABLE = {"imovirtual"}
# JSON string body with escapes (\" etc.) — captured, then json.loads to unescape properly.
_DESC_RE = re.compile(r'"description":"((?:[^"\\]|\\.)*)"')
# Imovirtual's auto-generated summaries — never the owner's real text.
_BOILERPLATE = ("Descubra esta", "Encontre a sua casa de sonho")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def extract_description(html: str) -> str | None:
    """The owner's full description from an Imovirtual detail page, or None.

    Picks the longest non-boilerplate JSON ``description`` value, unescapes it, strips tags.
    """
    best: str | None = None
    for body in _DESC_RE.findall(html):
        try:
            text = json.loads('"' + body + '"')
        except json.JSONDecodeError:
            continue
        if any(text.startswith(p) for p in _BOILERPLATE):
            continue
        if best is None or len(text) > len(best):
            best = text
    if not best:
        return None
    clean = _WS_RE.sub(" ", _TAG_RE.sub(" ", best)).strip()
    return clean or None


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


def apply(rows: list[dict], path: str | Path = DEFAULT_PATH) -> int:
    """Merge cached descriptions into raw rows' ``description_raw`` in place.

    Returns how many rows were enriched. A no-op when the sidecar is absent/empty, so the
    pipeline can always call it. normalize concatenates title + description_raw, so this
    just feeds real content into the existing keyword derivation.
    """
    sidecar = load(path)
    if not sidecar:
        return 0
    enriched = 0
    for row in rows:
        text = sidecar.get(row.get("source_url") or "")
        if text:
            row["description_raw"] = text
            enriched += 1
    return enriched


def fetch_one(source_url: str, session: requests.Session) -> str | None:
    """Fetch a detail page and return its extracted description, or None (blocked/empty/error)."""
    try:
        resp = session.get(source_url, timeout=20)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None  # 403 = DataDome (Idealista); anything non-200 → skip, retried next run
    return extract_description(resp.text)


def backfill(input_path: str, path: str | Path = DEFAULT_PATH, delay: float = 0.8) -> dict:
    """Fetch a description for every enrichable stored listing lacking one. Resumable + polite."""
    session = requests.Session()
    session.headers["User-Agent"] = _UA
    cache = load(path)
    stats: dict[str, int] = {}
    rows = list(store.load(input_path).values())
    try:
        for i, row in enumerate(rows, 1):
            url = row.get("source_url")
            if row.get("source") not in _ENRICHABLE or not url:
                stats["skip"] = stats.get("skip", 0) + 1
                continue
            if url in cache:
                stats["cached"] = stats.get("cached", 0) + 1
                continue
            text = fetch_one(url, session)
            if text:
                cache[url] = text
                stats["ok"] = stats.get("ok", 0) + 1
            else:
                stats["empty"] = stats.get("empty", 0) + 1
            time.sleep(delay)  # pace real fetches only
            if i % 50 == 0:
                save(cache, path)  # checkpoint so an interrupted run keeps its progress
                ctx = {f"ctx_{k}": v for k, v in stats.items()}
                log.info(
                    "description backfill progress",
                    extra={"event": "descriptions", "ctx_done": i, **ctx},
                )
    finally:
        save(cache, path)
    log.info(
        "description backfill complete",
        extra={"event": "descriptions_done", **{f"ctx_{k}": v for k, v in stats.items()}},
    )
    return stats


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Backfill Imovirtual descriptions from detail pages")
    p.add_argument("--input", default="data/listings.jsonl")
    p.add_argument("--path", default=DEFAULT_PATH)
    p.add_argument("--delay", type=float, default=0.8)
    args = p.parse_args()
    stats = backfill(args.input, args.path, args.delay)
    print("descriptions:", ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))


if __name__ == "__main__":
    main()
