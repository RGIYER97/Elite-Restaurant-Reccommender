from __future__ import annotations

from typing import Any

from restaurant_finder.menu_verifier import MenuVerifier, _dish_appears


class FakeResponse:
    def __init__(
        self,
        content: bytes,
        *,
        status_code: int = 200,
        content_type: str = "text/html",
        location: str | None = None,
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        if location:
            self.headers["Location"] = location


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url: str, **_kwargs: Any) -> FakeResponse:
        self.calls.append(url)
        return self.responses[url]


def test_verifies_review_candidates_against_linked_menu() -> None:
    homepage = b'<html><a href="/menu">Food menu</a></html>'
    menu = (
        b"<html><title>Dinner Menu</title><h1>Our dinner menu</h1>"
        b"<h2>Jerk Chicken</h2><p>Spiced chicken with rice, salad, and house sauce.</p>"
        b"<h2>Lamb Gyro</h2><p>Sliced lamb, lettuce, tomato, and onion in warm pita.</p>"
        b"<h2>Falafel</h2><p>Chickpea fritters with tahini and pickled vegetables.</p></html>"
    )
    session = FakeSession(
        {
            "https://example.com": FakeResponse(homepage),
            "https://example.com/menu": FakeResponse(menu),
        }
    )

    result = MenuVerifier(session=session).verify(  # type: ignore[arg-type]
        "https://example.com",
        ("jerk chicken", "lamb gyros", "truffle fries"),
    )

    assert result.dishes == ("Jerk Chicken", "Lamb Gyro")
    assert result.menu_url == "https://example.com/menu"
    assert result.checked is True
    assert session.calls == ["https://example.com", "https://example.com/menu"]


def test_withholds_candidates_when_no_accessible_menu_exists() -> None:
    session = FakeSession(
        {"https://example.com": FakeResponse(b"unavailable", status_code=503)}
    )

    result = MenuVerifier(session=session).verify(  # type: ignore[arg-type]
        "https://example.com",
        ("jerk chicken",),
    )

    assert result.dishes == ()
    assert result.menu_url is None
    assert result.checked is False


def test_upgrades_legacy_http_without_making_a_plaintext_request() -> None:
    session = FakeSession(
        {
            "https://example.com/menu": FakeResponse(
                b"<html><title>Food menu</title><h1>Full menu</h1><h2>Margherita Pizza</h2>"
                b"<p>Pizza with tomato, "
                b"mozzarella, basil, and olive oil.</p><p>Pasta with seasonal vegetables, "
                b"garlic, parmesan, and herbs.</p><p>Chocolate cake with cream.</p></html>"
            )
        }
    )
    verifier = MenuVerifier(session=session)  # type: ignore[arg-type]

    assert verifier.verify("http://example.com/menu", ("margherita pizza",)).dishes == (
        "Margherita Pizza",
    )
    assert session.calls == ["https://example.com/menu"]


def test_rejects_private_or_non_web_targets_without_fetching() -> None:
    session = FakeSession({})
    verifier = MenuVerifier(session=session)  # type: ignore[arg-type]

    assert verifier.verify("ftp://example.com/menu", ("pizza",)).checked is False
    assert verifier.verify("https://127.0.0.1/menu", ("pizza",)).checked is False
    assert session.calls == []


def test_menu_match_requires_complete_dish_phrase_or_same_line_tokens() -> None:
    menu = "Lamb Gyro ........ 18\nJerk salmon ........ 24\nChicken ........ 21"

    assert _dish_appears("lamb gyros", menu) is True
    assert _dish_appears("jerk chicken", menu) is False
    assert _dish_appears("pastries", "Pastries\nCroissant\nPain au chocolat") is False


def test_does_not_count_an_empty_javascript_menu_shell_as_checked() -> None:
    session = FakeSession(
        {
            "https://example.com/menu": FakeResponse(
                b"<html><title>Menu</title><div id='app'>Loading...</div></html>"
            )
        }
    )

    result = MenuVerifier(session=session).verify(  # type: ignore[arg-type]
        "https://example.com/menu",
        ("pizza",),
    )

    assert result.checked is False
    assert result.dishes == ()
