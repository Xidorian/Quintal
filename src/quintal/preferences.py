"""Persistent searcher preferences: per-listing 👍/👎/hide and per-area sentiment.

The source of truth for what we like, kept in `data/preferences.json` so it survives
re-collection and re-runs (a listing keeps its identity via its stable id).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

Sentiment = Literal["like", "dislike"]


class Preferences:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.liked: set[str] = set()
        self.disliked: set[str] = set()
        self.hidden: set[str] = set()
        self.areas: dict[str, Sentiment] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        self.liked = set(data.get("liked", []))
        self.disliked = set(data.get("disliked", []))
        self.hidden = set(data.get("hidden", []))
        self.areas = dict(data.get("areas", {}))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "liked": sorted(self.liked),
            "disliked": sorted(self.disliked),
            "hidden": sorted(self.hidden),
            "areas": self.areas,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- per-listing toggles (mutually exclusive like/dislike) ---
    def like(self, listing_id: str) -> None:
        self.disliked.discard(listing_id)
        self.liked.symmetric_difference_update({listing_id})  # toggle

    def dislike(self, listing_id: str) -> None:
        self.liked.discard(listing_id)
        self.disliked.symmetric_difference_update({listing_id})

    def hide(self, listing_id: str) -> None:
        self.hidden.symmetric_difference_update({listing_id})

    # --- per-area sentiment ---
    def set_area(self, concelho: str, sentiment: Sentiment | None) -> None:
        if sentiment is None:
            self.areas.pop(concelho, None)
        else:
            self.areas[concelho] = sentiment

    def area_of(self, concelho: str) -> Sentiment | None:
        return self.areas.get(concelho)

    def listing_state(self, listing_id: str) -> str:
        if listing_id in self.liked:
            return "liked"
        if listing_id in self.disliked:
            return "disliked"
        return "neutral"

    def preference_rank(self, listing_id: str, concelho: str) -> int:
        """Higher = show earlier. 👍 pins up, 👎 / disliked-area pushes down."""
        score = 0
        if listing_id in self.liked:
            score += 100
        if listing_id in self.disliked:
            score -= 100
        area = self.areas.get(concelho)
        if area == "like":
            score += 10
        elif area == "dislike":
            score -= 50
        return score
