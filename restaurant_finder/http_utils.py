"""Shared HTTP response and error handling."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .errors import (
    AuthenticationError,
    GoogleServiceError,
    InvalidLocationError,
    RateLimitError,
)


ALLOWED_OUTBOUND_HOSTS = frozenset(
    {
        "places.googleapis.com",
        "tile.googleapis.com",
    }
)


class GoogleOnlySession(requests.Session):
    """Reject server-side HTTP calls outside the approved Google APIs."""

    @staticmethod
    def _is_allowed_url(url: str) -> bool:
        try:
            parsed = urlsplit(url)
            return (
                parsed.scheme == "https"
                and parsed.hostname is not None
                and parsed.hostname.casefold() in ALLOWED_OUTBOUND_HOSTS
                and not parsed.username
            )
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _blocked() -> requests.RequestException:
        return requests.RequestException(
            "Blocked an outbound request outside Google Places and Map Tiles."
        )

    def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> requests.Response:
        if not self._is_allowed_url(url):
            raise self._blocked()
        return super().request(method, url, *args, **kwargs)

    def send(
        self,
        request: requests.PreparedRequest,
        **kwargs: Any,
    ) -> requests.Response:
        # Session.send is called again when Requests follows a redirect, so this
        # second check prevents an approved Google URL redirecting off-allowlist.
        if not request.url or not self._is_allowed_url(request.url):
            raise requests.RequestException(
                "Blocked an outbound request outside Google Places and Map Tiles."
            )
        return super().send(request, **kwargs)


def build_retrying_session() -> requests.Session:
    """Create an allowlisted session with one transient-failure retry."""

    retry = Retry(
        total=1,
        connect=1,
        read=1,
        status=1,
        backoff_factor=0.6,
        # A 429 is a quota response, not a reason to spend another attempt.
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = GoogleOnlySession()
    session.mount("https://", adapter)
    return session


def error_message(response: requests.Response) -> str:
    try:
        payload: dict[str, Any] = response.json()
        message = (payload.get("error") or {}).get("message") or payload.get("message")
        if message:
            return str(message)[:300]
    except (ValueError, TypeError, AttributeError):
        pass
    return (response.text or "No error details were returned.")[:300]


def raise_for_google_error(response: requests.Response, *, request_kind: str) -> None:
    """Convert a non-success Google response into a useful domain exception."""

    if 200 <= response.status_code < 300:
        return

    detail = error_message(response)
    if response.status_code == 400:
        raise InvalidLocationError(f"Google rejected the {request_kind} request: {detail}")
    if response.status_code in (401, 403):
        raise AuthenticationError(
            f"Google denied the {request_kind} request. Check the API key, API enablement, "
            f"key restrictions, and billing. Details: {detail}"
        )
    if response.status_code == 429:
        raise RateLimitError(
            f"Google Maps quota was exceeded while loading {request_kind}. Try again later."
        )
    if response.status_code >= 500:
        raise GoogleServiceError(
            f"Google Maps is temporarily unavailable while loading {request_kind}."
        )
    raise GoogleServiceError(f"The {request_kind} request failed: {detail}")
