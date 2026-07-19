"""Persistent searcher preferences: per-listing 👍/👎/hide and per-area sentiment.

The source of truth for what we like. It survives re-collection and re-runs (a listing
keeps its identity via its stable id), and can live in one of two stores behind the same
`Preferences` API:

- `LocalFileBackend` — a JSON file on disk (`data/preferences.json`). The default for
  local dev.
- `GistBackend` — a private GitHub Gist, so a hosted deploy (Streamlit Cloud, whose disk
  is ephemeral) keeps preferences *and* both of us share one live source of truth.

`Preferences(path)` keeps working exactly as before; pass `backend=` to swap the store.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, Protocol

Sentiment = Literal["like", "dislike"]

_GIST_FILENAME = "preferences.json"


class PrefsBackend(Protocol):
    """A store that can load and save the preferences payload (a plain dict)."""

    def load(self) -> dict: ...
    def save(self, payload: dict) -> None: ...


class LocalFileBackend:
    """Preferences as a JSON file on the local disk."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def save(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class GistBackend:
    """Preferences as a single file in a private GitHub Gist.

    Shared + durable: a hosted deploy reads/writes the same Gist both searchers point at.
    Transport failures are raised (never swallowed) so a transient network blip can't make
    us save an *empty* payload over real preferences — the caller shows an error instead.
    """

    _API = "https://api.github.com/gists"

    def __init__(
        self,
        gist_id: str,
        token: str,
        *,
        filename: str = _GIST_FILENAME,
        timeout: float = 10.0,
    ) -> None:
        self.gist_id = gist_id
        self.token = token
        self.filename = filename
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def load(self) -> dict:
        import requests

        try:
            resp = requests.get(
                f"{self._API}/{self.gist_id}", headers=self._headers(), timeout=self.timeout
            )
            resp.raise_for_status()
            files = resp.json().get("files", {})
        except requests.RequestException as exc:  # network / HTTP → operational, but loud
            raise RuntimeError(f"could not read preferences gist: {exc}") from exc

        entry = files.get(self.filename)
        if not entry:  # gist exists but not seeded yet → start empty
            return {}
        content = entry.get("content", "")
        if entry.get("truncated") and entry.get("raw_url"):
            content = requests.get(entry["raw_url"], timeout=self.timeout).text
        try:
            return json.loads(content) if content.strip() else {}
        except json.JSONDecodeError:
            return {}

    def save(self, payload: dict) -> None:
        import requests

        body = {
            "files": {
                self.filename: {"content": json.dumps(payload, ensure_ascii=False, indent=2)}
            }
        }
        try:
            resp = requests.patch(
                f"{self._API}/{self.gist_id}",
                headers=self._headers(),
                json=body,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"could not write preferences gist: {exc}") from exc


def default_backend(local_path: str | Path) -> PrefsBackend:
    """Gist backend when `QUINTAL_GIST_ID` + `QUINTAL_GITHUB_TOKEN` are set, else local file.

    Hosts (Streamlit Cloud) usually inject secrets as env vars; the app layer bridges
    `st.secrets` → env before calling this, so this stays framework-agnostic.
    """
    gist_id = os.getenv("QUINTAL_GIST_ID")
    token = os.getenv("QUINTAL_GITHUB_TOKEN")
    if gist_id and token:
        return GistBackend(gist_id, token)
    return LocalFileBackend(local_path)


class Preferences:
    def __init__(
        self, path: str | Path | None = None, *, backend: PrefsBackend | None = None
    ) -> None:
        if backend is None:
            if path is None:
                raise ValueError("Preferences needs either a path or a backend")
            backend = LocalFileBackend(path)
        self.backend = backend
        self.liked: set[str] = set()
        self.disliked: set[str] = set()
        self.hidden: set[str] = set()
        self.areas: dict[str, Sentiment] = {}
        self._load()

    def _load(self) -> None:
        data = self.backend.load()
        self.liked = set(data.get("liked", []))
        self.disliked = set(data.get("disliked", []))
        self.hidden = set(data.get("hidden", []))
        self.areas = dict(data.get("areas", {}))

    def _payload(self) -> dict:
        return {
            "liked": sorted(self.liked),
            "disliked": sorted(self.disliked),
            "hidden": sorted(self.hidden),
            "areas": self.areas,
        }

    def save(self) -> None:
        self.backend.save(self._payload())

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
