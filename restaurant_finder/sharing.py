"""Compact, validated URL payloads for shareable personal collections."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import json


MAX_SHARED_PLACES = 50
MAX_TOKEN_LENGTH = 8_000
DEFAULT_MINIMUM_REVIEW_COUNT = 200
DEFAULT_RADIUS_MILES = 3.0
MIN_RADIUS_MILES = 0.25
MAX_RADIUS_MILES = 25.0


@dataclass(frozen=True, slots=True)
class SharedCollection:
    name: str
    location: str
    place_types: tuple[str, ...]
    place_ids: tuple[str, ...]
    minimum_review_count: int = DEFAULT_MINIMUM_REVIEW_COUNT
    radius_miles: float = DEFAULT_RADIUS_MILES


def encode_collection(collection: SharedCollection) -> str:
    payload = {
        "v": 1,
        "n": collection.name[:40],
        "l": collection.location[:180],
        "t": [value for value in collection.place_types if value in {"restaurant", "bar"}],
        "p": list(dict.fromkeys(collection.place_ids))[:MAX_SHARED_PLACES],
        "m": collection.minimum_review_count,
        "r": collection.radius_miles,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).decode("ascii")
    return encoded.rstrip("=")


def decode_collection(token: str) -> SharedCollection:
    if not token or len(token) > MAX_TOKEN_LENGTH:
        raise ValueError("The shared collection link is invalid or too large.")
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (binascii.Error, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The shared collection link is invalid.") from exc
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise ValueError("The shared collection link uses an unsupported format.")

    name = str(payload.get("n") or "Shared shortlist").strip()[:40]
    location = str(payload.get("l") or "").strip()[:180]
    raw_types = payload.get("t") or []
    raw_ids = payload.get("p") or []
    if not location or not isinstance(raw_types, list) or not isinstance(raw_ids, list):
        raise ValueError("The shared collection link is incomplete.")
    place_types = tuple(
        value for value in raw_types if value in {"restaurant", "bar"}
    )
    place_ids = tuple(
        dict.fromkeys(
            value[:256]
            for value in raw_ids[:MAX_SHARED_PLACES]
            if isinstance(value, str) and value.strip()
        )
    )
    if not place_types:
        place_types = ("restaurant", "bar")
    raw_minimum_reviews = payload.get("m", DEFAULT_MINIMUM_REVIEW_COUNT)
    raw_radius_miles = payload.get("r", DEFAULT_RADIUS_MILES)
    if (
        isinstance(raw_minimum_reviews, bool)
        or not isinstance(raw_minimum_reviews, int)
        or raw_minimum_reviews < 0
        or raw_minimum_reviews > 100_000
    ):
        raise ValueError("The shared collection has an invalid review threshold.")
    if isinstance(raw_radius_miles, bool) or not isinstance(raw_radius_miles, (int, float)):
        raise ValueError("The shared collection has an invalid search radius.")
    radius_miles = float(raw_radius_miles)
    if not MIN_RADIUS_MILES <= radius_miles <= MAX_RADIUS_MILES:
        raise ValueError("The shared collection has an invalid search radius.")
    return SharedCollection(
        name=name or "Shared shortlist",
        location=location,
        place_types=place_types,
        place_ids=place_ids,
        minimum_review_count=raw_minimum_reviews,
        radius_miles=radius_miles,
    )
