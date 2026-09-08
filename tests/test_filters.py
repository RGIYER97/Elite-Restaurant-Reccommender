from datetime import datetime

from restaurant_finder.filters import filter_places
from restaurant_finder.models import OpeningPeriod, Place


def place(
    place_id: str,
    *,
    kind: str = "restaurant",
    cuisine: str = "italian_restaurant",
    rating: float = 4.8,
    reviews: int = 500,
    price: str | None = "PRICE_LEVEL_MODERATE",
    open_now: bool | None = True,
    periods: tuple[OpeningPeriod, ...] = (),
    types: tuple[str, ...] = (),
) -> Place:
    return Place(
        id=place_id,
        name=place_id,
        address="1 Main St",
        latitude=40.7,
        longitude=-74.0,
        rating=rating,
        review_count=reviews,
        primary_type=cuisine,
        price_level=price,
        google_maps_uri=None,
        matched_types=(kind,),
        types=types,
        open_now=open_now,
        opening_periods=periods,
    )


def test_filters_kind_quality_price_cuisine_and_saved_collection() -> None:
    places = (
        place("italian"),
        place("bar", kind="bar", cuisine="cocktail_bar", price="PRICE_LEVEL_EXPENSIVE"),
    )

    assert [
        item.id
        for item in filter_places(
            places,
            kind="restaurant",
            minimum_rating=4.8,
            minimum_reviews=400,
            price_levels=frozenset({"PRICE_LEVEL_MODERATE"}),
            cuisines=frozenset({"italian_restaurant"}),
            saved_place_ids=frozenset({"italian"}),
        )
    ] == ["italian"]


def test_cuisine_filter_uses_all_google_place_types() -> None:
    venue = place(
        "bistro",
        cuisine="restaurant",
        types=("french_restaurant", "restaurant"),
    )

    assert filter_places(
        (venue,),
        cuisines=frozenset({"french_restaurant"}),
    ) == (venue,)


def test_open_now_excludes_unknown_and_closed_places() -> None:
    places = (
        place("open", open_now=True),
        place("closed", open_now=False),
        place("unknown", open_now=None),
    )

    assert [item.id for item in filter_places(places, availability="open_now")] == ["open"]


def test_open_at_handles_overnight_weekly_hours() -> None:
    # Friday 18:00 through Saturday 02:00, using Google's Sunday=0 convention.
    overnight = OpeningPeriod(open_day=5, open_minute=18 * 60, close_day=6, close_minute=120)
    venue = place("late", periods=(overnight,))

    assert venue.is_open_at(datetime(2026, 9, 11, 23, 0)) is True
    assert venue.is_open_at(datetime(2026, 9, 12, 1, 30)) is True
    assert venue.is_open_at(datetime(2026, 9, 12, 3, 0)) is False
    assert venue.is_open_now(datetime(2026, 9, 11, 23, 0)) is True
