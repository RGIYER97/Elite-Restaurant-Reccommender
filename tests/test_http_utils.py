import pytest
import requests

from restaurant_finder.http_utils import GoogleOnlySession


def test_google_only_session_blocks_unapproved_hosts() -> None:
    session = GoogleOnlySession()

    with pytest.raises(requests.RequestException, match="Blocked an outbound request"):
        session.get("https://example.com/menu")


def test_google_only_session_blocks_google_hostname_suffix_tricks() -> None:
    session = GoogleOnlySession()

    with pytest.raises(requests.RequestException):
        session.get("https://places.googleapis.com.attacker.example/v1/places")


def test_google_only_session_rechecks_prepared_redirect_requests() -> None:
    session = GoogleOnlySession()
    request = requests.Request("GET", "https://example.com/redirect-target").prepare()

    with pytest.raises(requests.RequestException):
        session.send(request)
