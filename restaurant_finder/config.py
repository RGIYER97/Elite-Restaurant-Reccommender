"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigurationError(ValueError):
    """Raised when the local application configuration is invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings.

    A separate map-tiles key is optional but useful in production because tile
    requests are made by the browser while Places requests are server-side.
    """

    places_api_key: str
    map_tiles_api_key: str
    geocoding_api_key: str | None = None
    map_region: str = "US"
    map_language: str = "en-US"
    max_pages: int | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        places_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
        tiles_key = os.getenv("GOOGLE_MAP_TILES_API_KEY", "").strip() or places_key
        geocoding_key = os.getenv("GOOGLE_GEOCODING_API_KEY", "").strip() or None
        region = os.getenv("MAP_REGION", "US").strip().upper()
        language = os.getenv("MAP_LANGUAGE", "en-US").strip()

        raw_max_pages = os.getenv("PLACES_API_MAX_PAGES", "0").strip()
        try:
            parsed_max_pages = int(raw_max_pages)
        except ValueError as exc:
            raise ConfigurationError("PLACES_API_MAX_PAGES must be an integer.") from exc

        if parsed_max_pages < 0:
            raise ConfigurationError("PLACES_API_MAX_PAGES cannot be negative.")
        if len(region) != 2 or not region.isalpha():
            raise ConfigurationError("MAP_REGION must be a two-letter region code.")
        if not language:
            raise ConfigurationError("MAP_LANGUAGE cannot be empty.")

        return cls(
            places_api_key=places_key,
            map_tiles_api_key=tiles_key,
            geocoding_api_key=geocoding_key,
            map_region=region,
            map_language=language,
            max_pages=parsed_max_pages or None,
        )
