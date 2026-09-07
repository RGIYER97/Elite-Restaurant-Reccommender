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
) -> tuple[Place, ...]:
    """Apply strict thresholds, deduplicate, then rank strongest results first."""

    unique: dict[str, Place] = {}
    for place in places:
        if place.is_closed:
            continue
        if place.rating < MIN_RATING or place.review_count < MIN_REVIEW_COUNT:
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
) -> SearchResult:
    client = GooglePlacesClient(api_key=api_key, max_pages=max_pages)
    fetched = client.search_location(location, thorough=thorough)
    curated = curate_places(fetched.places, search_area=fetched.search_area)
    return SearchResult.create(
        location=" ".join(location.split()),
        places=client.enrich_places(curated),
        scanned_count=fetched.scanned_count,
        page_count=fetched.page_count,
        search_area=fetched.search_area,
        warnings=fetched.warnings,
        thorough=thorough,
    )
