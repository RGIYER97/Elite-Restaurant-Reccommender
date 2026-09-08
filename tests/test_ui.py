from restaurant_finder.ui import safe_url


def test_safe_url_upgrades_legacy_http_and_rejects_executable_urls() -> None:
    assert safe_url("http://example.com/book?party=2") == "https://example.com/book?party=2"
    assert safe_url("javascript:alert(1)") == ""
    assert safe_url("https://user@example.com") == ""
