"""Dinner-to-drinks pairing without paid routing requests."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from .models import Place, distance_meters


@dataclass(frozen=True, slots=True)
class EveningPlan:
    dinner: Place
    drinks: Place
    straight_line_meters: float
    walking_url: str


def google_walking_url(origin: Place, destination: Place) -> str:
    """Build a free Google Maps URL; opening it does not require an API key."""

    params = urlencode(
        {
            "api": "1",
            "origin": origin.address,
            "origin_place_id": origin.id,
            "destination": destination.address,
            "destination_place_id": destination.id,
            "travelmode": "walking",
        }
    )
    return f"https://www.google.com/maps/dir/?{params}"


def suggest_evening_plan(
    places: tuple[Place, ...],
    *,
    dinner_id: str | None = None,
) -> EveningPlan | None:
    """Pair a selected/top restaurant with the strongest nearby distinct bar."""

    restaurants = [place for place in places if "restaurant" in place.matched_types]
    bars = [place for place in places if "bar" in place.matched_types]
    if not restaurants or not bars:
        return None

    dinner = next((place for place in restaurants if place.id == dinner_id), restaurants[0])
    candidates = [place for place in bars if place.id != dinner.id]
    if not candidates:
        return None

    def bar_key(bar: Place) -> tuple[float, float, int, str]:
        distance = distance_meters(
            dinner.latitude,
            dinner.longitude,
            bar.latitude,
            bar.longitude,
        )
        # Keep the recommendation walk-minded, then break close ties by quality.
        return (distance // 250, -bar.rating, -bar.review_count, bar.name.casefold())

    drinks = min(candidates, key=bar_key)
    distance = distance_meters(
        dinner.latitude,
        dinner.longitude,
        drinks.latitude,
        drinks.longitude,
    )
    return EveningPlan(
        dinner=dinner,
        drinks=drinks,
        straight_line_meters=distance,
        walking_url=google_walking_url(dinner, drinks),
    )
