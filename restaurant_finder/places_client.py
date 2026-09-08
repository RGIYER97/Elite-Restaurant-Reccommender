"""Google Places API (New) Text Search client."""

from __future__ import annotations

from collections.abc import Iterable
from math import cos, radians
import re
from urllib.parse import quote

import requests

from .errors import (
    AuthenticationError,
    GoogleMapsError,
    GoogleServiceError,
    InvalidLocationError,
    RateLimitError,
)
from .http_utils import build_retrying_session, raise_for_google_error
from .menu_verifier import MenuVerifier
from .models import FetchResult, Place, SearchArea, distance_meters
from .recommendations import extract_recommended_dishes


PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.primaryType",
        "places.priceLevel",
        "places.googleMapsUri",
        "places.businessStatus",
        "nextPageToken",
    )
)
LOCATION_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.viewport",
        "places.types",
    )
)

GEOGRAPHIC_TYPES = {
    "country",
    "administrative_area_level_1",
    "administrative_area_level_2",
    "administrative_area_level_3",
    "administrative_area_level_4",
    "administrative_area_level_5",
    "administrative_area_level_6",
    "administrative_area_level_7",
    "locality",
    "postal_code",
    "neighborhood",
    "sublocality",
    "sublocality_level_1",
    "sublocality_level_2",
    "sublocality_level_3",
    "sublocality_level_4",
    "sublocality_level_5",
}

WALKABLE_RADIUS_METERS = 1_200.0
MIN_WALKABLE_RADIUS_METERS = 400.0
SMALL_SUBLOCALITY_MAX_RADIUS_METERS = 3_000.0
SUBLOCALITY_TYPES = {
    "sublocality",
    "sublocality_level_1",
    "sublocality_level_2",
    "sublocality_level_3",
    "sublocality_level_4",
    "sublocality_level_5",
}


class GooglePlacesClient:
    """Small, testable client for exhaustive restaurant/bar text searches."""

    def __init__(
        self,
        api_key: str,
        *,
        geocoding_api_key: str | None = None,
        max_pages: int | None = None,
        timeout_seconds: float = 15,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.geocoding_api_key = geocoding_api_key
        self.max_pages = max_pages
        self.timeout_seconds = timeout_seconds
        self.session = session or build_retrying_session()
        self.menu_verifier = MenuVerifier(
            session=self.session,
            timeout_seconds=min(timeout_seconds, 12),
        )

    def search_location(
        self,
        location: str,
        place_types: Iterable[str] = ("restaurant", "bar"),
        *,
        thorough: bool = False,
    ) -> FetchResult:
        location = " ".join(location.split())
        if not location:
            raise ValueError("Enter a city, neighborhood, or ZIP/postal code.")
        if len(location) > 180:
            raise ValueError("The location is too long. Please use 180 characters or fewer.")

        search_area = self.resolve_location(location)
        all_places: list[Place] = []
        scanned_count = 0
        page_count = 0
        warnings: list[str] = []
        capped_searches = 0
        interrupted = False
        rectangles = search_area.search_rectangles(thorough)
        for rectangle in rectangles:
            for place_type in place_types:
                try:
                    found, scanned, pages, capped = self._search_type(
                        search_area,
                        place_type,
                        rectangle=rectangle,
                    )
                except GoogleMapsError as exc:
                    if not all_places:
                        raise
                    warnings.append(f"Search stopped early; showing partial results. {exc}")
                    interrupted = True
                    break
                all_places.extend(found)
                scanned_count += scanned
                page_count += pages
                capped_searches += int(capped)
            if interrupted:
                break

        if capped_searches:
            suffix = "." if thorough else "; enable Thorough search for better coverage."
            warnings.append(
                f"{capped_searches} area/category searches reached Google's result cap{suffix}"
            )

        return FetchResult(
            places=tuple(all_places),
            scanned_count=scanned_count,
            page_count=page_count,
            search_area=search_area,
            warnings=tuple(warnings),
        )

    def enrich_places(self, places: tuple[Place, ...]) -> tuple[Place, ...]:
        """Add review-backed dish insights to already-qualified places only."""

        enriched: list[Place] = []
        for place in places:
            try:
                enriched.append(self._enrich_place(place))
            except GoogleMapsError as exc:
                # A details/SKU issue should not hide an otherwise valid result.
                enriched.append(place.with_insights(insights_error=str(exc)))
        return tuple(enriched)

    def enrich_place(self, place: Place) -> Place:
        """Load paid review/menu insights for one already-qualified place."""

        return self._enrich_place(place)

    def _enrich_place(self, place: Place) -> Place:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "generativeSummary,reviewSummary,reviews,websiteUri",
        }
        try:
            response = self.session.get(
                PLACE_DETAILS_URL.format(place_id=quote(place.id, safe="")),
                headers=headers,
                params={"languageCode": "en"},
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise GoogleServiceError(f"Dish insights timed out for {place.name}.") from exc
        except requests.RequestException as exc:
            raise GoogleServiceError(f"Could not load dish insights for {place.name}.") from exc

        raise_for_google_error(response, request_kind=f"dish insights for {place.name}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleServiceError(f"Google returned invalid dish insights for {place.name}.") from exc

        generative = payload.get("generativeSummary") or {}
        review_summary_data = payload.get("reviewSummary") or {}
        overview = self._localized_text(generative.get("overview"))
        review_summary = self._localized_text(review_summary_data.get("text"))

        reviews = payload.get("reviews") or []
        review_texts = [
            self._localized_text(review.get("text"))
            for review in reviews
            if isinstance(review, dict)
        ]
        review_texts = [text for text in review_texts if text]
        dish_candidates = extract_recommended_dishes(review_summary, overview, review_texts)
        website_uri = payload.get("websiteUri")
        menu_verification = self.menu_verifier.verify(
            website_uri if isinstance(website_uri, str) else None,
            dish_candidates,
        )

        known_for = overview
        summary_source = generative
        if not known_for and review_summary:
            known_for = re.split(r"(?<=[.!?])\s+", review_summary, maxsplit=1)[0]
            summary_source = review_summary_data

        disclosure = self._localized_text(review_summary_data.get("disclosureText"))
        if not disclosure:
            disclosure = self._localized_text(generative.get("disclosureText"))

        return place.with_insights(
            recommended_dishes=menu_verification.dishes,
            known_for=known_for or None,
            reviews_uri=review_summary_data.get("reviewsUri"),
            summary_disclosure=disclosure or None,
            summary_flag_uri=summary_source.get("flagContentUri"),
            menu_uri=menu_verification.menu_url,
            menu_checked=menu_verification.checked,
            dish_candidates_found=bool(dish_candidates),
        )

    @staticmethod
    def _localized_text(value: object) -> str:
        if not isinstance(value, dict):
            return ""
        return str(value.get("text") or "").strip()

    def resolve_location(self, location: str) -> SearchArea:
        """Resolve a town/neighborhood/postal code before searching businesses."""

        if self.geocoding_api_key:
            return self._resolve_location_with_geocoding(location)

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": LOCATION_FIELD_MASK,
        }
        try:
            response = self.session.post(
                PLACES_TEXT_SEARCH_URL,
                headers=headers,
                json={"textQuery": location, "pageSize": 5, "languageCode": "en"},
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise GoogleServiceError("Google Places timed out while resolving the location.") from exc
        except requests.RequestException as exc:
            raise GoogleServiceError(
                "Could not reach Google Places while resolving the location."
            ) from exc

        raise_for_google_error(response, request_kind="location lookup")
        try:
            candidates = response.json().get("places") or []
        except (ValueError, AttributeError) as exc:
            raise GoogleServiceError("Google returned an invalid location response.") from exc

        geographic_candidates = [
            candidate
            for candidate in candidates
            if isinstance(candidate, dict)
            and GEOGRAPHIC_TYPES.intersection(candidate.get("types") or [])
        ]
        if not geographic_candidates:
            raise InvalidLocationError(
                "That location could not be resolved to a city, neighborhood, or postal code."
            )
        return self._area_from_candidate(geographic_candidates[0])

    def _resolve_location_with_geocoding(self, location: str) -> SearchArea:
        """Use the lower-priced Geocoding SKU when explicitly configured."""

        try:
            response = self.session.get(
                GEOCODING_URL,
                params={
                    "address": location,
                    "key": self.geocoding_api_key,
                    "language": "en",
                },
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise GoogleServiceError("Google Geocoding timed out while resolving the location.") from exc
        except requests.RequestException as exc:
            raise GoogleServiceError(
                "Could not reach Google Geocoding while resolving the location."
            ) from exc

        raise_for_google_error(response, request_kind="location lookup")
        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleServiceError("Google returned an invalid location response.") from exc
        if not isinstance(payload, dict):
            raise GoogleServiceError("Google returned an invalid location response.")

        status = str(payload.get("status") or "")
        detail = str(payload.get("error_message") or "").strip()
        if status == "ZERO_RESULTS":
            raise InvalidLocationError(
                "That location could not be resolved to a city, neighborhood, or postal code."
            )
        if status in {"REQUEST_DENIED", "OVER_DAILY_LIMIT"}:
            suffix = f" Details: {detail[:300]}" if detail else ""
            raise AuthenticationError(
                "Google denied the Geocoding request. Check API enablement, key restrictions, "
                f"and billing.{suffix}"
            )
        if status == "OVER_QUERY_LIMIT":
            raise RateLimitError("Google Geocoding quota was exceeded. Try again later.")
        if status != "OK":
            raise GoogleServiceError(
                f"Google Geocoding could not resolve the location ({status or 'unknown error'})."
            )

        results = payload.get("results") or []
        if not isinstance(results, list):
            raise GoogleServiceError("Google returned an invalid location response.")
        geographic_results = [
            result
            for result in results
            if isinstance(result, dict)
            and GEOGRAPHIC_TYPES.intersection(result.get("types") or [])
        ]
        if not geographic_results:
            raise InvalidLocationError(
                "That location could not be resolved to a city, neighborhood, or postal code."
            )

        result = geographic_results[0]
        geometry = result.get("geometry") or {}
        if not isinstance(geometry, dict):
            raise InvalidLocationError("Google did not return a usable boundary for that location.")
        center = geometry.get("location") or {}
        boundary = geometry.get("bounds") or geometry.get("viewport") or {}
        if not isinstance(center, dict) or not isinstance(boundary, dict):
            raise InvalidLocationError("Google did not return a usable boundary for that location.")
        southwest = boundary.get("southwest") or {}
        northeast = boundary.get("northeast") or {}
        if not isinstance(southwest, dict) or not isinstance(northeast, dict):
            raise InvalidLocationError("Google did not return a usable boundary for that location.")
        raw_types = result.get("types") or []
        display_name = self._geocoding_display_name(result, raw_types)
        return self._area_from_candidate(
            {
                "id": result.get("place_id"),
                "displayName": {"text": display_name},
                "formattedAddress": result.get("formatted_address"),
                "types": raw_types,
                "location": {
                    "latitude": center.get("lat"),
                    "longitude": center.get("lng"),
                },
                "viewport": {
                    "low": {
                        "latitude": southwest.get("lat"),
                        "longitude": southwest.get("lng"),
                    },
                    "high": {
                        "latitude": northeast.get("lat"),
                        "longitude": northeast.get("lng"),
                    },
                },
            }
        )

    @staticmethod
    def _geocoding_display_name(result: dict[str, object], raw_types: object) -> str:
        result_types = (
            {value for value in raw_types if isinstance(value, str)}
            if isinstance(raw_types, list)
            else set()
        )
        priority_types = (
            "neighborhood",
            "postal_code",
            "locality",
            *sorted(SUBLOCALITY_TYPES),
        )
        components = result.get("address_components") or []
        if isinstance(components, list):
            for wanted_type in priority_types:
                if wanted_type not in result_types:
                    continue
                for component in components:
                    if not isinstance(component, dict):
                        continue
                    if wanted_type in (component.get("types") or []):
                        name = str(component.get("long_name") or "").strip()
                        if name:
                            return name
        return str(result.get("formatted_address") or "Search area").split(",", 1)[0]

    @staticmethod
    def _area_from_candidate(candidate: dict[str, object]) -> SearchArea:
        location = candidate.get("location") or {}
        viewport = candidate.get("viewport") or {}
        if not isinstance(location, dict) or not isinstance(viewport, dict):
            raise InvalidLocationError("Google did not return a usable boundary for that location.")

        low = viewport.get("low") or {}
        high = viewport.get("high") or {}
        if not isinstance(low, dict) or not isinstance(high, dict):
            raise InvalidLocationError("Google did not return a usable boundary for that location.")

        try:
            center_latitude = float(location["latitude"])
            center_longitude = float(location["longitude"])
            low_latitude = float(low["latitude"])
            low_longitude = float(low["longitude"])
            high_latitude = float(high["latitude"])
            high_longitude = float(high["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidLocationError("Google did not return a usable boundary for that location.") from exc

        corner_distances = tuple(
            distance_meters(center_latitude, center_longitude, lat, lng)
            for lat in (low_latitude, high_latitude)
            for lng in (low_longitude, high_longitude)
        )
        viewport_radius = max(corner_distances)
        raw_types = candidate.get("types") or []
        candidate_types = {
            value for value in raw_types if isinstance(value, str)
        } if isinstance(raw_types, list) else set()
        small_sublocality = bool(candidate_types.intersection(SUBLOCALITY_TYPES)) and (
            viewport_radius <= SMALL_SUBLOCALITY_MAX_RADIUS_METERS
        )
        is_walkable = "neighborhood" in candidate_types or small_sublocality

        if is_walkable:
            radius_meters = min(
                max(viewport_radius, MIN_WALKABLE_RADIUS_METERS),
                WALKABLE_RADIUS_METERS,
            )
            latitude_delta = radius_meters / 111_320.0
            longitude_scale = max(111_320.0 * cos(radians(center_latitude)), 1.0)
            longitude_delta = radius_meters / longitude_scale
            # Intersect the neighborhood viewport with the walk-radius bounding
            # box before sending the hard restriction to Google.
            low_latitude = max(low_latitude, center_latitude - latitude_delta)
            high_latitude = min(high_latitude, center_latitude + latitude_delta)
            low_longitude = max(low_longitude, center_longitude - longitude_delta)
            high_longitude = min(high_longitude, center_longitude + longitude_delta)
        else:
            # Cover the resolved viewport while guarding against implausibly
            # tiny or huge viewports returned for ambiguous municipalities.
            radius_meters = min(max(viewport_radius, 1_500.0), 25_000.0)

        scope_type = next(
            (
                place_type
                for place_type in (
                    "neighborhood",
                    "postal_code",
                    "locality",
                    *sorted(SUBLOCALITY_TYPES),
                )
                if place_type in candidate_types
            ),
            "area",
        )
        display_name = candidate.get("displayName") or {}
        if not isinstance(display_name, dict):
            display_name = {}

        return SearchArea(
            name=str(display_name.get("text") or candidate.get("formattedAddress") or "Search area"),
            formatted_address=str(candidate.get("formattedAddress") or ""),
            center_latitude=center_latitude,
            center_longitude=center_longitude,
            radius_meters=radius_meters,
            low_latitude=low_latitude,
            low_longitude=low_longitude,
            high_latitude=high_latitude,
            high_longitude=high_longitude,
            scope_type=scope_type,
            is_walkable=is_walkable,
        )

    def _search_type(
        self,
        search_area: SearchArea,
        place_type: str,
        *,
        rectangle: dict[str, dict[str, float]] | None = None,
    ) -> tuple[list[Place], int, int, bool]:
        """Follow every page token returned for one strict place type."""

        base_body: dict[str, object] = {
            "textQuery": f"{place_type}s",
            "includedType": place_type,
            "strictTypeFiltering": True,
            # The API accepts minRating only in 0.5 increments. 4.5 safely
            # reduces noise; the exact >= 4.7 check remains local.
            "minRating": 4.5,
            "pageSize": 20,
            "languageCode": "en",
            # Text Search supports a rectangular hard restriction. The service
            # layer then applies an exact radial Haversine check.
            "locationRestriction": {"rectangle": rectangle or search_area.rectangle},
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        }

        places: list[Place] = []
        scanned_count = 0
        page_count = 0
        page_token: str | None = None
        seen_tokens: set[str] = set()

        while True:
            body = dict(base_body)
            if page_token:
                body["pageToken"] = page_token

            try:
                response = self.session.post(
                    PLACES_TEXT_SEARCH_URL,
                    headers=headers,
                    json=body,
                    timeout=self.timeout_seconds,
                )
            except requests.Timeout as exc:
                raise GoogleServiceError("Google Places timed out. Please try again.") from exc
            except requests.RequestException as exc:
                raise GoogleServiceError(
                    "Could not reach Google Places. Check your network and try again."
                ) from exc

            raise_for_google_error(response, request_kind="Places search")
            try:
                payload = response.json()
            except ValueError as exc:
                raise GoogleServiceError("Google Places returned an invalid response.") from exc

            raw_places = payload.get("places") or []
            if not isinstance(raw_places, list):
                raise GoogleServiceError("Google Places returned an unexpected response shape.")

            page_count += 1
            scanned_count += len(raw_places)
            for raw_place in raw_places:
                if isinstance(raw_place, dict):
                    parsed = Place.from_api(raw_place, place_type)
                    if parsed is not None:
                        places.append(parsed)

            next_token = str(payload.get("nextPageToken") or "").strip()
            if not next_token:
                break
            if next_token in seen_tokens:
                raise GoogleServiceError("Google Places returned a repeated pagination token.")
            seen_tokens.add(next_token)
            page_token = next_token

            if self.max_pages is not None and page_count >= self.max_pages:
                break

        hit_provider_cap = page_count >= 3 and scanned_count >= 60
        return places, scanned_count, page_count, hit_provider_cap
