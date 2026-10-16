import json

import pytest

from quintal.preferences import (
    GistBackend,
    LocalFileBackend,
    Preferences,
    default_backend,
)


def test_like_dislike_mutually_exclusive(tmp_path):
    p = Preferences(tmp_path / "prefs.json")
    p.like("a")
    assert p.listing_state("a") == "liked"
    p.dislike("a")  # flips
    assert p.listing_state("a") == "disliked"
    assert "a" not in p.liked


def test_like_toggles_off(tmp_path):
    p = Preferences(tmp_path / "prefs.json")
    p.like("a")
    p.like("a")
    assert p.listing_state("a") == "neutral"


def test_area_sentiment_set_and_clear(tmp_path):
    p = Preferences(tmp_path / "prefs.json")
    p.set_area("Loulé", "dislike")
    assert p.area_of("Loulé") == "dislike"
    p.set_area("Loulé", None)
    assert p.area_of("Loulé") is None


def test_preference_rank_orders_liked_above_disliked_area(tmp_path):
    p = Preferences(tmp_path / "prefs.json")
    p.like("good")
    p.set_area("Bad", "dislike")
    assert p.preference_rank("good", "Anywhere") > p.preference_rank("x", "Bad")


def test_undo_dislike_restores_the_like_it_replaced(tmp_path):
    """A mis-tapped pass on a 👍 listing goes back to 👍, not to neutral."""
    p = Preferences(tmp_path / "prefs.json")
    p.like("a")
    p.dislike("a", by="Malia", context={"title": "T2 in Tavira"})
    assert p.latest_feedback("a")["was_liked"] is True
    assert p.undo_dislike("a") is True
    assert p.listing_state("a") == "liked"
    assert p.latest_feedback("a") is None  # the receipt is retracted, not deleted
    assert p.feedback[0]["retracted"] is True


def test_undo_dislike_on_a_neutral_pass_returns_to_neutral(tmp_path):
    p = Preferences(tmp_path / "prefs.json")
    p.dislike("b")
    assert "was_liked" not in p.latest_feedback("b")
    assert p.undo_dislike("b") is True
    assert p.listing_state("b") == "neutral"
    assert p.undo_dislike("b") is False  # nothing to undo


def test_recent_feedback_is_newest_first_and_skips_retracted(tmp_path):
    p = Preferences(tmp_path / "prefs.json")
    for lid in ("a", "b", "c"):
        p.dislike(lid)
    p.undo_dislike("b")
    assert [e["listing_id"] for e in p.recent_feedback()] == ["c", "a"]
    assert [e["listing_id"] for e in p.recent_feedback(limit=1)] == ["c"]


def test_roundtrip(tmp_path):
    path = tmp_path / "prefs.json"
    p = Preferences(path)
    p.like("a")
    p.dislike("b")
    p.hide("c")
    p.set_area("Tavira", "like")
    p.save()

    reloaded = Preferences(path)
    assert reloaded.listing_state("a") == "liked"
    assert reloaded.listing_state("b") == "disliked"
    assert "c" in reloaded.hidden
    assert reloaded.area_of("Tavira") == "like"


# --- Backend abstraction ------------------------------------------------------


class _DictBackend:
    """An in-memory backend to prove Preferences works over any store (e.g. the Gist)."""

    def __init__(self) -> None:
        self.data: dict = {}

    def load(self) -> dict:
        return dict(self.data)

    def save(self, payload: dict) -> None:
        self.data = dict(payload)


def test_preferences_works_over_a_swapped_backend():
    backend = _DictBackend()
    p = Preferences(backend=backend)
    p.like("a")
    p.set_area("Lagos", "like")
    p.save()

    # A fresh instance over the same store sees the shared state (the hosted-Gist case).
    other = Preferences(backend=backend)
    assert other.listing_state("a") == "liked"
    assert other.area_of("Lagos") == "like"


def test_preferences_requires_path_or_backend():
    with pytest.raises(ValueError):
        Preferences()


# --- Gist backend (requests mocked) -------------------------------------------


class _FakeResp:
    def __init__(self, payload=None, *, text=""):
        self._payload = payload
        self.text = text

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeRequests:
    """Minimal stand-in for the `requests` module used inside GistBackend."""

    RequestException = Exception

    def __init__(self):
        self.patched = None

    def get(self, url, **kwargs):
        content = json.dumps({"liked": ["x"], "disliked": [], "hidden": [], "areas": {}})
        return _FakeResp({"files": {"preferences.json": {"content": content}}})

    def patch(self, url, **kwargs):
        self.patched = kwargs.get("json")
        return _FakeResp({})


def _install_fake_requests(monkeypatch, fake):
    import requests

    fake.RequestException = requests.RequestException
    monkeypatch.setitem(__import__("sys").modules, "requests", fake)


def test_gist_backend_load_parses_file_content(monkeypatch):
    _install_fake_requests(monkeypatch, _FakeRequests())
    data = GistBackend("gid", "tok").load()
    assert data["liked"] == ["x"]


@pytest.mark.exercises_gist_backend
def test_gist_backend_save_sends_file_payload(monkeypatch):
    fake = _FakeRequests()
    _install_fake_requests(monkeypatch, fake)
    GistBackend("gid", "tok").save({"liked": ["y"], "disliked": [], "hidden": [], "areas": {}})
    sent = fake.patched["files"]["preferences.json"]["content"]
    assert json.loads(sent)["liked"] == ["y"]


def test_gist_backend_load_raises_on_network_error(monkeypatch):
    import requests

    class _Boom(_FakeRequests):
        def get(self, url, **kwargs):
            raise requests.RequestException("down")

    _install_fake_requests(monkeypatch, _Boom())
    with pytest.raises(RuntimeError):
        GistBackend("gid", "tok").load()


def test_default_backend_switches_on_env(monkeypatch, tmp_path):
    monkeypatch.delenv("QUINTAL_GIST_ID", raising=False)
    monkeypatch.delenv("QUINTAL_GITHUB_TOKEN", raising=False)
    assert isinstance(default_backend(tmp_path / "p.json"), LocalFileBackend)

    monkeypatch.setenv("QUINTAL_GIST_ID", "gid")
    monkeypatch.setenv("QUINTAL_GITHUB_TOKEN", "tok")
    assert isinstance(default_backend(tmp_path / "p.json"), GistBackend)
