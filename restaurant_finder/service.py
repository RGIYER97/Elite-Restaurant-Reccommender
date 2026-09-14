"""Business rules for producing the curated result set."""

from __future__ import annotations

from .models import Place, SearchArea, SearchResult
from .places_client import GooglePlacesClient


MIN_RATING = 4.7
MIN_REVIEW_COUNT = 200


def curate_places(
    places: tuple[Place, ...],
    *,
    search_area: SearchArea | None = None,
    minimum_review_count: int = MIN_REVIEW_COUNT,
) -> tuple[Place, ...]:
    """Apply strict thresholds, deduplicate, then rank strongest results first."""

    if (
        isinstance(minimum_review_count, bool)
        or not isinstance(minimum_review_count, int)
        or minimum_review_count < 0
    ):
        raise ValueError("Minimum review count must be zero or greater.")

    unique: dict[str, Place] = {}
    for place in places:
        if place.is_closed:
            continue
        if place.rating < MIN_RATING or place.review_count < minimum_review_count:
            continue
        if search_area is not None and not search_area.contains(place):
            continue

        existing = unique.get(place.id)
        if existing is None:
            unique[place.id] = place
            continue

        merged = existing
        for matched_type in place.matched_types:
            merged = merged.with_matched_type(matched_type)
        unique[place.id] = merged

    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (-item.rating, -item.review_count, item.name.casefold()),
        )
    )


def find_curated_places(
    location: str,
    *,
    api_key: str,
    max_pages: int | None = None,
    thorough: bool = False,
    enrich: bool = True,
    place_types: tuple[str, ...] = ("restaurant", "bar"),
    minimum_review_count: int = MIN_REVIEW_COUNT,
    radius_miles: float | None = None,
) -> SearchResult:
    if (
        isinstance(minimum_review_count, bool)
        or not isinstance(minimum_review_count, int)
        or minimum_review_count < 0
    ):
        raise ValueError("Minimum review count must be zero or greater.")

    client = GooglePlacesClient(
        api_key=api_key,
        max_pages=max_pages,
    )
    fetched = client.search_location(
        location,
        place_types=place_types,
        thorough=thorough,
        radius_miles=radius_miles,
    )
    curated = curate_places(
        fetched.places,
        search_area=fetched.search_area,
        minimum_review_count=minimum_review_count,
    )
    return SearchResult.create(
        location=" ".join(location.split()),
        places=client.enrich_places(curated) if enrich else curated,
        scanned_count=fetched.scanned_count,
        page_count=fetched.page_count,
        search_area=fetched.search_area,
        warnings=fetched.warnings,
        thorough=thorough,
        place_types=place_types,
        minimum_review_count=minimum_review_count,
    )
