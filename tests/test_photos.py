from quintal.photos import og_image_url, photo_path


def test_og_image_extracted():
    html = '<meta property="og:image" content="https://cdn/x.jpg"/>'
    assert og_image_url(html) == "https://cdn/x.jpg"


def test_og_image_reversed_attr_order():
    html = '<meta content="https://cdn/y.jpg" property="og:image">'
    assert og_image_url(html) == "https://cdn/y.jpg"


def test_falls_back_to_twitter_image():
    html = '<meta name="twitter:image" content="https://cdn/tw.jpg">'
    assert og_image_url(html) == "https://cdn/tw.jpg"


def test_no_image_returns_none():
    assert og_image_url("<html><head></head></html>") is None


def test_photo_path_uses_listing_id():
    assert photo_path("abc123", "data/photos").name == "abc123.jpg"


# --- Captured image_url path (QT-028) ---
from quintal.photos import fetch_one  # noqa: E402


class _Resp:
    def __init__(self, status=200, content=b"\xff\xd8jpg", ctype="image/jpeg", text=""):
        self.status_code = status
        self.content = content
        self.headers = {"Content-Type": ctype}
        self.text = text


class _Session:
    """Records GET urls so we can assert the detail page is (not) fetched."""

    def __init__(self, responses):
        self.responses = responses
        self.gets = []

    def get(self, url, **kwargs):
        self.gets.append(url)
        return self.responses.get(url, _Resp(status=404))


def test_captured_image_url_skips_detail_fetch(tmp_path):
    s = _Session({"https://cdn/card.jpg": _Resp()})
    status = fetch_one(
        "id1", "https://site/detail", s, tmp_path, image_url="https://cdn/card.jpg"
    )
    assert status == "ok"
    assert s.gets == ["https://cdn/card.jpg"]  # detail page never fetched
    assert (tmp_path / "id1.jpg").exists()


def test_falls_back_to_detail_og_image_without_capture(tmp_path):
    s = _Session({
        "https://site/detail": _Resp(text='<meta property="og:image" content="https://cdn/og.jpg">'),
        "https://cdn/og.jpg": _Resp(),
    })
    status = fetch_one("id2", "https://site/detail", s, tmp_path)
    assert status == "ok"
    assert s.gets == ["https://site/detail", "https://cdn/og.jpg"]  # detail fetched for og:image
