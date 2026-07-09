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
