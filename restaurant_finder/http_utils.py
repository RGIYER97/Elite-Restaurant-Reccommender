"""Shared HTTP response and error handling."""

from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .errors import (
    AuthenticationError,
    GoogleServiceError,
    InvalidLocationError,
    RateLimitError,
)


def build_retrying_session() -> requests.Session:
    """Create a session that retries transient POST and GET failures."""

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
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
