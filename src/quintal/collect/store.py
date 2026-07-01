"""Idempotent persistence to data/listings.jsonl.

Re-collecting the same search must not create duplicates — a listing is keyed by its
source URL (falling back to source+title+price when a URL is missing), so a second run
updates the existing record in place instead of appending a copy.
"""

from __future__ import annotations

import json
from pathlib import Path

Key = tuple


def _key(row: dict) -> Key:
    url = row.get("source_url")
    if url:
        return ("url", url)
    return ("attr", row.get("source"), row.get("title"), row.get("price_eur_month"))


def load(path: str | Path) -> dict[Key, dict]:
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[Key, dict] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        out[_key(row)] = row
    return out


def upsert(path: str | Path, rows: list[dict]) -> tuple[int, int]:
    """Merge `rows` into the store. Returns (added, updated)."""
    existing = load(path)
    added = updated = 0
    for row in rows:
        key = _key(row)
        if key in existing:
            existing[key] = {**existing[key], **row}
            updated += 1
        else:
            existing[key] = row
            added += 1

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for row in existing.values():
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return added, updated
