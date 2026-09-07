from dataclasses import replace

from restaurant_finder.models import Place, SearchArea, rating_color
from restaurant_finder.service import curate_places


def make_place(
    place_id: str,
    rating: float,
    reviews: int,
    matched_type: str = "restaurant",
) -> Place:
    return Place(
        id=place_id,
        name=f"Place {place_id}",
        address="123 Main St",
        latitude=40.75,
        longitude=-73.98,
        rating=rating,
        review_count=reviews,
        primary_type=matched_type,
        price_level="PRICE_LEVEL_MODERATE",
        google_maps_uri=None,
        matched_types=(matched_type,),
    )


def test_curate_places_enforces_both_thresholds() -> None:
    curated = curate_places(
        (
            make_place("qualified", 4.7, 200),
            make_place("low-rating", 4.6, 900),
            make_place("low-reviews", 5.0, 199),
        )
    )

    assert [place.id for place in curated] == ["qualified"]


def test_curate_places_excludes_closed_venues() -> None:
    closed = replace(make_place("closed", 4.9, 900), is_closed=True)

    assert curate_places((closed,)) == ()


def test_curate_places_deduplicates_and_merges_categories() -> None:
    curated = curate_places(
        (
            make_place("same", 4.8, 500, "restaurant"),
            make_place("same", 4.8, 500, "bar"),
        )
    )

    assert len(curated) == 1
    assert curated[0].matched_types == ("bar", "restaurant")


def test_results_sort_by_rating_then_review_count() -> None:
    curated = curate_places(
        (
            make_place("second", 4.8, 900),
            make_place("third", 4.8, 500),
            make_place("first", 4.9, 200),
        )
    )

    assert [place.id for place in curated] == ["first", "second", "third"]


def test_rating_colors_match_required_bands() -> None:
    assert rating_color(4.7) == "#2563EB"
    assert rating_color(4.8) == "#7C3AED"
    assert rating_color(4.9) == "#F59E0B"
    assert rating_color(5.0) == "#F59E0B"


def test_curate_places_enforces_resolved_boundary_and_radius() -> None:
    area = SearchArea(
        name="Test Town",
        formatted_address="Test Town, NJ",
        center_latitude=40.75,
        center_longitude=-74.25,
        radius_meters=2_000,
        low_latitude=40.72,
        low_longitude=-74.29,
        high_latitude=40.78,
        high_longitude=-74.21,
    )
    nearby = replace(make_place("nearby", 4.8, 500), longitude=-74.25)
    outside = replace(nearby, id="outside", longitude=-74.21)

    curated = curate_places((nearby, outside), search_area=area)

    assert [place.id for place in curated] == ["nearby"]


def test_search_area_can_split_into_four_thorough_cells() -> None:
    area = SearchArea(
        name="Test Town",
        formatted_address="Test Town",
        center_latitude=1,
        center_longitude=1,
        radius_meters=2_000,
        low_latitude=0,
        low_longitude=0,
        high_latitude=2,
        high_longitude=2,
    )

    cells = area.search_rectangles(thorough=True)

    assert len(cells) == 4
    assert cells[0]["high"] == {"latitude": 1, "longitude": 1}
    assert cells[-1]["low"] == {"latitude": 1, "longitude": 1}
    assert len(replace(area, is_walkable=True).search_rectangles(thorough=True)) == 4
