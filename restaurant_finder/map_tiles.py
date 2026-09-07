"""Google Map Tiles API support for Folium/Leaflet rendering."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import requests

from .errors import GoogleServiceError
from .http_utils import build_retrying_session, raise_for_google_error


CREATE_SESSION_URL = "https://tile.googleapis.com/v1/createSession"


@dataclass(frozen=True, slots=True)
class MapTileSession:
    token: str
    api_key: str
    copyright: str = "Map data © Google"

    @property
    def tile_url(self) -> str:
        token = quote(self.token, safe="")
        key = quote(self.api_key, safe="")
        return (
            "https://tile.googleapis.com/v1/2dtiles/{z}/{x}/{y}"
            f"?session={token}&key={key}"
        )


class GoogleMapTilesClient:
    def __init__(
        self,
        api_key: str,
        *,
        region: str = "US",
        language: str = "en-US",
        timeout_seconds: float = 15,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.region = region
        self.language = language
        self.timeout_seconds = timeout_seconds
        self.session = session or build_retrying_session()

    def create_session(self) -> MapTileSession:
        try:
            response = self.session.post(
                CREATE_SESSION_URL,
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "mapType": "roadmap",
                    "language": self.language,
                    "region": self.region,
                },
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise GoogleServiceError("Google Map Tiles timed out.") from exc
        except requests.RequestException as exc:
            raise GoogleServiceError("Could not reach Google Map Tiles.") from exc

        raise_for_google_error(response, request_kind="Map Tiles session")
        try:
            token = str(response.json().get("session") or "")
        except (ValueError, AttributeError) as exc:
            raise GoogleServiceError("Google Map Tiles returned an invalid response.") from exc
        if not token:
            raise GoogleServiceError("Google Map Tiles did not return a session token.")
        return MapTileSession(token=token, api_key=self.api_key)
