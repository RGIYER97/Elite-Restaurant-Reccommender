"""Typed data models shared by the API, service, and UI layers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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
class OpeningPeriod:
    """One recurring weekly opening interval using Google's Sunday=0 convention."""

    open_day: int
    open_minute: int
    close_day: int | None = None
    close_minute: int | None = None

    def contains(self, day: int, minute: int) -> bool:
        if self.close_day is None or self.close_minute is None:
            return True
        week_minutes = 7 * 24 * 60
        start = self.open_day * 24 * 60 + self.open_minute
        end = self.close_day * 24 * 60 + self.close_minute
        if end <= start:
            end += week_minutes
        target = day * 24 * 60 + minute
        return start <= target < end or start <= target + week_minutes < end


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
    types: tuple[str, ...] = ()
    website_uri: str | None = None
    directions_uri: str | None = None
    open_now: bool | None = None
    opening_periods: tuple[OpeningPeriod, ...] = ()
    time_zone: str | None = None
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

    def is_open_at(self, when: datetime) -> bool | None:
        """Evaluate typical local opening hours for a user-selected date/time."""

        if not self.opening_periods:
            return None
        google_day = (when.weekday() + 1) % 7
        minute = when.hour * 60 + when.minute
        return any(period.contains(google_day, minute) for period in self.opening_periods)

    def is_open_now(self, now: datetime | None = None) -> bool | None:
        """Calculate current status dynamically so cached API flags never go stale."""

        if self.opening_periods:
            if now is None:
                try:
                    now = datetime.now(ZoneInfo(self.time_zone)) if self.time_zone else datetime.now()
                except ZoneInfoNotFoundError:
                    now = datetime.now()
            elif self.time_zone and now.tzinfo is not None:
                try:
                    now = now.astimezone(ZoneInfo(self.time_zone))
                except ZoneInfoNotFoundError:
                    pass
            return self.is_open_at(now)
        return self.open_now

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
        maps_links = payload.get("googleMapsLinks") or {}
        if not isinstance(maps_links, dict):
            maps_links = {}
        current_hours = payload.get("currentOpeningHours") or {}
        if not isinstance(current_hours, dict):
            current_hours = {}
        raw_time_zone = payload.get("timeZone")
        if isinstance(raw_time_zone, dict):
            time_zone = str(raw_time_zone.get("id") or "").strip() or None
        elif isinstance(raw_time_zone, str):
            time_zone = raw_time_zone.strip() or None
        else:
            time_zone = None

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
                google_maps_uri=maps_links.get("placeUri") or payload.get("googleMapsUri"),
                matched_types=(matched_type,),
                types=tuple(
                    value
                    for value in payload.get("types", ())
                    if isinstance(value, str) and value.strip()
                ),
                website_uri=payload.get("websiteUri"),
                directions_uri=maps_links.get("directionsUri"),
                reviews_uri=maps_links.get("reviewsUri"),
                open_now=(
                    bool(current_hours["openNow"])
                    if isinstance(current_hours.get("openNow"), bool)
                    else None
                ),
                opening_periods=cls._opening_periods(payload.get("regularOpeningHours")),
                time_zone=time_zone,
                is_closed=payload.get("businessStatus") in {
                    "CLOSED_PERMANENTLY",
                    "CLOSED_TEMPORARILY",
                },
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _opening_periods(value: object) -> tuple[OpeningPeriod, ...]:
        if not isinstance(value, dict) or not isinstance(value.get("periods"), list):
            return ()
        parsed: list[OpeningPeriod] = []
        for period in value["periods"]:
            if not isinstance(period, dict) or not isinstance(period.get("open"), dict):
                continue
            opens = period["open"]
            closes = period.get("close")
            try:
                open_day = int(opens["day"])
                open_minute = int(opens.get("hour", 0)) * 60 + int(opens.get("minute", 0))
                close_day = int(closes["day"]) if isinstance(closes, dict) else None
                close_minute = (
                    int(closes.get("hour", 0)) * 60 + int(closes.get("minute", 0))
                    if isinstance(closes, dict)
                    else None
                )
                if not 0 <= open_day <= 6 or not 0 <= open_minute < 24 * 60:
                    continue
                if close_day is not None and (
                    not 0 <= close_day <= 6
                    or close_minute is None
                    or not 0 <= close_minute < 24 * 60
                ):
                    continue
                parsed.append(
                    OpeningPeriod(
                        open_day=open_day,
                        open_minute=open_minute,
                        close_day=close_day,
                        close_minute=close_minute,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(parsed)


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
    place_types: tuple[str, ...] = ("restaurant", "bar")

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
        place_types: tuple[str, ...] = ("restaurant", "bar"),
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
            place_types=place_types,
        )
