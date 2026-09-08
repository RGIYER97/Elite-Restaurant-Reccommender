"""Compact, validated URL payloads for shareable personal collections."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import json


MAX_SHARED_PLACES = 50
MAX_TOKEN_LENGTH = 8_000


@dataclass(frozen=True, slots=True)
class SharedCollection:
    name: str
    location: str
    place_types: tuple[str, ...]
    place_ids: tuple[str, ...]


def encode_collection(collection: SharedCollection) -> str:
    payload = {
        "v": 1,
        "n": collection.name[:40],
        "l": collection.location[:180],
        "t": [value for value in collection.place_types if value in {"restaurant", "bar"}],
        "p": list(dict.fromkeys(collection.place_ids))[:MAX_SHARED_PLACES],
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
    return SharedCollection(
        name=name or "Shared shortlist",
        location=location,
        place_types=place_types,
        place_ids=place_ids,
    )
