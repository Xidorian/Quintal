from quintal.preferences import Preferences


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
