from __future__ import annotations

from typing import Any

import pytest

from restaurant_finder.errors import RateLimitError
from restaurant_finder.places_client import GooglePlacesClient


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def post(self, *_args: Any, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeGeocodingSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get(self, *_args: Any, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        return self.response


def raw_place(place_id: str) -> dict[str, Any]:
    return {
        "id": place_id,
        "displayName": {"text": place_id.title()},
        "formattedAddress": "New York, NY",
        "location": {"latitude": 40.75, "longitude": -73.98},
        "rating": 4.8,
        "userRatingCount": 400,
        "primaryType": "restaurant",
    }


def raw_location() -> dict[str, Any]:
    return {
        "id": "town",
        "displayName": {"text": "South Orange Village"},
        "formattedAddress": "South Orange Village, NJ 07079, USA",
        "types": ["locality", "political"],
        "location": {"latitude": 40.745737, "longitude": -74.258023},
        "viewport": {
            "low": {"latitude": 40.735637, "longitude": -74.283114},
            "high": {"latitude": 40.762303, "longitude": -74.234671},
        },
    }


def raw_neighborhood() -> dict[str, Any]:
    return {
        "id": "flatiron",
        "displayName": {"text": "Flatiron District"},
        "formattedAddress": "Flatiron District, New York, NY, USA",
        "types": ["neighborhood", "political"],
        "location": {"latitude": 40.7411, "longitude": -73.9897},
        "viewport": {
            "low": {"latitude": 40.72, "longitude": -74.01},
            "high": {"latitude": 40.76, "longitude": -73.97},
        },
    }


def test_client_follows_pagination_for_each_type() -> None:
    fake_session = FakeSession(
        [
            FakeResponse({"places": [raw_location()]}),
            FakeResponse({"places": [raw_place("r1")], "nextPageToken": "next"}),
            FakeResponse({"places": [raw_place("r2")]}),
            FakeResponse({"places": [raw_place("b1")]}),
        ]
    )
    client = GooglePlacesClient("key", session=fake_session)  # type: ignore[arg-type]

    result = client.search_location("Manhattan", ("restaurant", "bar"))

    assert [place.id for place in result.places] == ["r1", "r2", "b1"]
    assert result.page_count == 3
    assert result.scanned_count == 3
    assert fake_session.calls[2]["json"]["pageToken"] == "next"
    assert fake_session.calls[1]["json"]["strictTypeFiltering"] is True
    assert "locationRestriction" in fake_session.calls[1]["json"]


def test_client_turns_429_into_rate_limit_error() -> None:
    fake_session = FakeSession(
        [
            FakeResponse({"places": [raw_location()]}),
            FakeResponse({"error": {"message": "Quota exceeded"}}, status_code=429),
        ]
    )
    client = GooglePlacesClient("key", session=fake_session)  # type: ignore[arg-type]

    with pytest.raises(RateLimitError):
        client.search_location("Manhattan", ("restaurant",))


def test_thorough_search_queries_both_types_in_four_cells() -> None:
    fake_session = FakeSession(
        [FakeResponse({"places": [raw_location()]})]
        + [FakeResponse({"places": []}) for _ in range(8)]
    )
    client = GooglePlacesClient("key", session=fake_session)  # type: ignore[arg-type]

    result = client.search_location("South Orange", thorough=True)

    search_calls = fake_session.calls[1:]
    assert result.page_count == 8
    assert len(search_calls) == 8
    assert len(
        {
            str(call["json"]["locationRestriction"]["rectangle"])
            for call in search_calls
        }
    ) == 4


def test_neighborhood_resolves_to_clipped_walkable_radius() -> None:
    fake_session = FakeSession([FakeResponse({"places": [raw_neighborhood()]})])
    client = GooglePlacesClient("key", session=fake_session)  # type: ignore[arg-type]

    area = client.resolve_location("Flatiron, NYC")

    assert area.name == "Flatiron District"
    assert area.scope_type == "neighborhood"
    assert area.is_walkable is True
    assert area.radius_meters == 1_200
    assert area.low_latitude > 40.72
    assert area.high_longitude < -73.97


def test_optional_geocoding_resolver_avoids_a_places_text_search() -> None:
    response = FakeResponse(
        {
            "status": "OK",
            "results": [
                {
                    "place_id": "flatiron",
                    "formatted_address": "Flatiron District, New York, NY, USA",
                    "types": ["neighborhood", "political"],
                    "address_components": [
                        {
                            "long_name": "Flatiron District",
                            "types": ["neighborhood", "political"],
                        }
                    ],
                    "geometry": {
                        "location": {"lat": 40.7411, "lng": -73.9897},
                        "viewport": {
                            "southwest": {"lat": 40.72, "lng": -74.01},
                            "northeast": {"lat": 40.76, "lng": -73.97},
                        },
                    },
                }
            ],
        }
    )
    session = FakeGeocodingSession(response)
    client = GooglePlacesClient(
        "places-key",
        geocoding_api_key="geocoding-key",
        session=session,  # type: ignore[arg-type]
    )

    area = client.resolve_location("Flatiron, NYC")

    assert area.name == "Flatiron District"
    assert area.is_walkable is True
    assert area.radius_meters == 1_200
    assert session.calls[0]["params"]["address"] == "Flatiron, NYC"
