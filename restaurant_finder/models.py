"""Typed data models shared by the API, service, and UI layers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Any


RATING_COLORS = {
    "4.7": "#2563EB",  # blue
    "4.8": "#7C3AED",  # purple
    "4.9+": "#F59E0B",  # gold
}

EARTH_RADIUS_METERS = 6_371_008.8


def distance_meters(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return great-circle distance using the haversine formula."""

    lat_a, lat_b = radians(latitude_a), radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lng = radians(longitude_b - longitude_a)
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(lat_a) * cos(lat_b) * sin(delta_lng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * asin(sqrt(haversine))


def rating_color(rating: float) -> str:
    """Return the exact visual band color for an already-curated rating."""

    if rating >= 4.9:
        return RATING_COLORS["4.9+"]
    if rating >= 4.8:
        return RATING_COLORS["4.8"]
    return RATING_COLORS["4.7"]


def rating_band(rating: float) -> str:
    if rating >= 4.9:
        return "4.9–5.0"
    if rating >= 4.8:
        return "4.8"
    return "4.7"


@dataclass(frozen=True, slots=True)
class Place:
    id: str
    name: str
    address: str
    latitude: float
    longitude: float
    rating: float
    review_count: int
    primary_type: str
    price_level: str | None
    google_maps_uri: str | None
    matched_types: tuple[str, ...]
    is_closed: bool = False
    recommended_dishes: tuple[str, ...] = ()
    known_for: str | None = None
    reviews_uri: str | None = None
    summary_disclosure: str | None = None
    summary_flag_uri: str | None = None
    menu_uri: str | None = None
    menu_checked: bool = False
    dish_candidates_found: bool = False
    insights_loaded: bool = False
    insights_error: str | None = None

    @property
    def color(self) -> str:
        return rating_color(self.rating)

    @property
    def rating_band(self) -> str:
        return rating_band(self.rating)

    @property
    def category_label(self) -> str:
        labels = {"restaurant": "Restaurant", "bar": "Bar"}
        return " & ".join(labels.get(item, item.replace("_", " ").title()) for item in self.matched_types)

    @property
    def primary_type_label(self) -> str:
        return self.primary_type.replace("_", " ").title() if self.primary_type else self.category_label

    @property
    def price_label(self) -> str:
        return {
            "PRICE_LEVEL_FREE": "Free",
            "PRICE_LEVEL_INEXPENSIVE": "$",
            "PRICE_LEVEL_MODERATE": "$$",
            "PRICE_LEVEL_EXPENSIVE": "$$$",
            "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
        }.get(self.price_level or "", "Price unavailable")

    def with_matched_type(self, place_type: str) -> "Place":
        types = tuple(sorted(set((*self.matched_types, place_type))))
        return replace(self, matched_types=types)

    def with_insights(
        self,
        *,
        recommended_dishes: tuple[str, ...] = (),
        known_for: str | None = None,
        reviews_uri: str | None = None,
        summary_disclosure: str | None = None,
        summary_flag_uri: str | None = None,
        menu_uri: str | None = None,
        menu_checked: bool = False,
        dish_candidates_found: bool = False,
        insights_loaded: bool = True,
        insights_error: str | None = None,
    ) -> "Place":
        return replace(
            self,
            recommended_dishes=recommended_dishes,
            known_for=known_for,
            reviews_uri=reviews_uri,
            summary_disclosure=summary_disclosure,
            summary_flag_uri=summary_flag_uri,
            menu_uri=menu_uri,
            menu_checked=menu_checked,
            dish_candidates_found=dish_candidates_found,
            insights_loaded=insights_loaded,
            insights_error=insights_error,
        )

    @classmethod
    def from_api(cls, payload: dict[str, Any], matched_type: str) -> "Place | None":
        """Convert one Places API object, skipping records that cannot be mapped."""

        location = payload.get("location") or {}
        place_id = str(payload.get("id") or "").strip()
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if not place_id or latitude is None or longitude is None:
            return None

        display_name = payload.get("displayName") or {}
        name = str(display_name.get("text") or "Unnamed place").strip()

        try:
            parsed_latitude = float(latitude)
            parsed_longitude = float(longitude)
            parsed_rating = float(payload.get("rating") or 0)
            parsed_reviews = int(payload.get("userRatingCount") or 0)
            if (
                not all(isfinite(value) for value in (parsed_latitude, parsed_longitude, parsed_rating))
                or not -90 <= parsed_latitude <= 90
                or not -180 <= parsed_longitude <= 180
                or not 0 <= parsed_rating <= 5
                or parsed_reviews < 0
            ):
                return None
            return cls(
                id=place_id,
                name=name,
                address=str(payload.get("formattedAddress") or "Address unavailable"),
                latitude=parsed_latitude,
                longitude=parsed_longitude,
                rating=parsed_rating,
                review_count=parsed_reviews,
                primary_type=str(payload.get("primaryType") or matched_type),
                price_level=payload.get("priceLevel"),
                google_maps_uri=payload.get("googleMapsUri"),
                matched_types=(matched_type,),
                is_closed=payload.get("businessStatus") in {
                    "CLOSED_PERMANENTLY",
                    "CLOSED_TEMPORARILY",
                },
            )
        except (TypeError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class SearchArea:
    """A Google-resolved location and its logical radial search area."""

    name: str
    formatted_address: str
    center_latitude: float
    center_longitude: float
    radius_meters: float
    low_latitude: float
    low_longitude: float
    high_latitude: float
    high_longitude: float
    scope_type: str = "locality"
    is_walkable: bool = False

    @property
    def rectangle(self) -> dict[str, dict[str, float]]:
        return {
            "low": {
                "latitude": self.low_latitude,
                "longitude": self.low_longitude,
            },
            "high": {
                "latitude": self.high_latitude,
                "longitude": self.high_longitude,
            },
        }

    def contains(self, place: Place) -> bool:
        within_rectangle = (
            self.low_latitude <= place.latitude <= self.high_latitude
            and self.low_longitude <= place.longitude <= self.high_longitude
        )
        if not within_rectangle:
            return False
        return (
            distance_meters(
                self.center_latitude,
                self.center_longitude,
                place.latitude,
                place.longitude,
            )
            <= self.radius_meters
        )

    def search_rectangles(self, thorough: bool) -> tuple[dict[str, dict[str, float]], ...]:
        """Return the full viewport or four cells for a higher-coverage sweep."""

        if not thorough:
            return (self.rectangle,)
        middle_latitude = (self.low_latitude + self.high_latitude) / 2
        middle_longitude = (self.low_longitude + self.high_longitude) / 2
        rectangles = []
        for low_lat, high_lat in (
            (self.low_latitude, middle_latitude),
            (middle_latitude, self.high_latitude),
        ):
            for low_lng, high_lng in (
                (self.low_longitude, middle_longitude),
                (middle_longitude, self.high_longitude),
            ):
                rectangles.append(
                    {
                        "low": {"latitude": low_lat, "longitude": low_lng},
                        "high": {"latitude": high_lat, "longitude": high_lng},
                    }
                )
        return tuple(rectangles)


@dataclass(frozen=True, slots=True)
class FetchResult:
    places: tuple[Place, ...]
    scanned_count: int
    page_count: int
    search_area: SearchArea
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchResult:
    location: str
    places: tuple[Place, ...]
    scanned_count: int
    page_count: int
    search_area: SearchArea
    fetched_at: datetime
    warnings: tuple[str, ...] = ()
    thorough: bool = False

    @classmethod
    def create(
        cls,
        *,
        location: str,
        places: tuple[Place, ...],
        scanned_count: int,
        page_count: int,
        search_area: SearchArea,
        warnings: tuple[str, ...] = (),
        thorough: bool = False,
    ) -> "SearchResult":
        return cls(
            location=location,
            places=places,
            scanned_count=scanned_count,
            page_count=page_count,
            search_area=search_area,
            fetched_at=datetime.now(timezone.utc),
            warnings=warnings,
            thorough=thorough,
        )
