from restaurant_finder.itinerary import suggest_evening_plan
from restaurant_finder.models import Place


def place(place_id: str, kind: str, longitude: float, rating: float = 4.8) -> Place:
    return Place(
        id=place_id,
        name=place_id.title(),
        address=f"{place_id} address",
        latitude=40.75,
        longitude=longitude,
        rating=rating,
        review_count=500,
        primary_type=kind,
        price_level=None,
        google_maps_uri=None,
        matched_types=(kind,),
    )


def test_evening_plan_pairs_selected_dinner_with_nearby_bar() -> None:
    places = (
        place("dinner", "restaurant", -74.0),
        place("near-bar", "bar", -74.001, 4.7),
        place("far-bar", "bar", -74.02, 5.0),
    )

    plan = suggest_evening_plan(places, dinner_id="dinner")

    assert plan is not None
    assert plan.dinner.id == "dinner"
    assert plan.drinks.id == "near-bar"
    assert plan.straight_line_meters < 200
    assert "travelmode=walking" in plan.walking_url
    assert "origin_place_id=dinner" in plan.walking_url


def test_evening_plan_requires_distinct_restaurant_and_bar() -> None:
    both = place("both", "restaurant", -74.0)
    both = both.with_matched_type("bar")

    assert suggest_evening_plan((both,)) is None
