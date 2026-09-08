"""Zero-request filtering over an already-fetched shortlist."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from .models import Place


Availability = Literal["any", "open_now", "open_at"]
Kind = Literal["all", "restaurant", "bar"]


def filter_places(
    places: tuple[Place, ...],
    *,
    kind: Kind = "all",
    minimum_rating: float = 4.7,
    minimum_reviews: int = 200,
    price_levels: frozenset[str] = frozenset(),
    cuisines: frozenset[str] = frozenset(),
    availability: Availability = "any",
    open_at: datetime | None = None,
    saved_place_ids: frozenset[str] | None = None,
) -> tuple[Place, ...]:
    """Apply user refinements locally without issuing another provider request."""

    filtered: list[Place] = []
    for place in places:
        if kind != "all" and kind not in place.matched_types:
            continue
        if place.rating < minimum_rating or place.review_count < minimum_reviews:
            continue
        if price_levels and (place.price_level or "UNKNOWN") not in price_levels:
            continue
        venue_types = frozenset((*place.types, place.primary_type))
        if cuisines and not venue_types.intersection(cuisines):
            continue
        if saved_place_ids is not None and place.id not in saved_place_ids:
            continue
        if availability == "open_now" and place.is_open_now() is not True:
            continue
        if availability == "open_at":
            if open_at is None or place.is_open_at(open_at) is not True:
                continue
        filtered.append(place)
    return tuple(filtered)
