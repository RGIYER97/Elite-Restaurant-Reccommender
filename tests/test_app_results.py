from streamlit.testing.v1 import AppTest

from restaurant_finder.sharing import SharedCollection, decode_collection, encode_collection


RESULTS_APP = r'''
import app
from restaurant_finder.config import Settings
from restaurant_finder.map_tiles import MapTileSession
from restaurant_finder.models import OpeningPeriod, Place, SearchArea, SearchResult

app.cached_tile_session = lambda **kwargs: MapTileSession("token", "key")
hours = (OpeningPeriod(open_day=0, open_minute=0),)
restaurant = Place(
    id="restaurant", name="Dinner", address="1 Main St", latitude=40.75,
    longitude=-74.0, rating=4.9, review_count=900,
    primary_type="italian_restaurant", price_level="PRICE_LEVEL_EXPENSIVE",
    google_maps_uri="https://maps.google.com/dinner", matched_types=("restaurant",),
    website_uri="https://example.com", directions_uri="https://maps.google.com/directions",
    open_now=True, opening_periods=hours,
)
bar = Place(
    id="bar", name="Drinks", address="2 Main St", latitude=40.751,
    longitude=-74.001, rating=4.8, review_count=500,
    primary_type="cocktail_bar", price_level="PRICE_LEVEL_MODERATE",
    google_maps_uri="https://maps.google.com/bar", matched_types=("bar",),
    open_now=True, opening_periods=hours,
)
area = SearchArea(
    name="Test Area", formatted_address="Test Area", center_latitude=40.75,
    center_longitude=-74.0, radius_meters=1200, low_latitude=40.74,
    low_longitude=-74.01, high_latitude=40.76, high_longitude=-73.99,
    scope_type="neighborhood", is_walkable=True,
)
result = SearchResult.create(
    location="Test Area", places=(restaurant, bar), scanned_count=2,
    page_count=2, search_area=area, place_types=("restaurant", "bar"),
)
settings = Settings(places_api_key="key", map_tiles_api_key="key")
app.render_results(result, settings)
'''


MAIN_APP = r'''
import streamlit as st
import app
from restaurant_finder.config import Settings
from restaurant_finder.map_tiles import MapTileSession
from restaurant_finder.models import Place, SearchArea, SearchResult

place = Place(
    id="bar", name="Test Bar", address="1 Main St", latitude=42.36,
    longitude=-71.06, rating=4.8, review_count=500,
    primary_type="cocktail_bar", price_level="PRICE_LEVEL_MODERATE",
    google_maps_uri="https://maps.google.com/bar", matched_types=("bar",),
)
area = SearchArea(
    name="Boston", formatted_address="Boston, MA", center_latitude=42.36,
    center_longitude=-71.06, radius_meters=5000, low_latitude=42.30,
    low_longitude=-71.12, high_latitude=42.42, high_longitude=-71.00,
)

def fake_search(location, **kwargs):
    st.session_state["search_call"] = {
        "location": location,
        "place_types": kwargs["place_types"],
        "thorough": kwargs["thorough"],
    }
    return SearchResult.create(
        location=location, places=(place,), scanned_count=1, page_count=1,
        search_area=area, thorough=kwargs["thorough"],
        place_types=kwargs["place_types"],
    )

def fake_insights(result, **kwargs):
    st.session_state["insights_requested"] = True
    return result

app.load_settings = lambda: Settings(places_api_key="key", map_tiles_api_key="key")
app.cached_search = fake_search
app.add_cached_insights = fake_insights
app.cached_tile_session = lambda **kwargs: MapTileSession("token", "key")
app.main()
'''


def click_button(rendered: AppTest, label: str) -> AppTest:
    button = next(item for item in rendered.button if item.label == label)
    button.click()
    return rendered.run(timeout=20)


def test_results_ui_renders_filters_collections_and_itinerary() -> None:
    rendered = AppTest.from_string(RESULTS_APP).run(timeout=20)

    assert not rendered.exception
    assert "Your collections & sharing" in [item.label for item in rendered.expander]
    assert "Refine the shortlist" in [item.label for item in rendered.expander]
    assert "Plan dinner + drinks" in [item.label for item in rendered.expander]
    assert "Active collection" in [item.label for item in rendered.selectbox]
    assert "Availability" in [item.label for item in rendered.selectbox]


def test_collection_buttons_save_remove_share_clear_and_save_itinerary() -> None:
    rendered = AppTest.from_string(RESULTS_APP).run(timeout=20)

    rendered = click_button(rendered, "Save to Favorites")
    assert rendered.session_state["collections"]["Favorites"] == ["restaurant"]
    assert "Remove from Favorites" in [item.label for item in rendered.button]

    rendered = click_button(rendered, "Create share link")
    token = rendered.query_params["share"][0]
    assert decode_collection(token).place_ids == ("restaurant",)

    rendered = click_button(rendered, "Clear active collection")
    assert rendered.session_state["collections"]["Favorites"] == []

    rendered = click_button(rendered, "Save both to active collection")
    assert rendered.session_state["collections"]["Favorites"] == ["restaurant", "bar"]

    rendered = click_button(rendered, "Remove from Favorites")
    assert rendered.session_state["collections"]["Favorites"] == ["bar"]


def test_named_collection_and_only_saved_filter() -> None:
    rendered = AppTest.from_string(RESULTS_APP).run(timeout=20)
    new_collection = next(item for item in rendered.text_input if item.label == "New collection")
    new_collection.input("Date night")
    rendered = click_button(rendered, "Create collection")

    assert rendered.session_state["active_collection"] == "Date night"
    assert rendered.session_state["collections"]["Date night"] == []

    rendered = click_button(rendered, "Save to Date night")
    only_saved = next(
        item
        for item in rendered.checkbox
        if item.label == "Only show places in this collection"
    )
    only_saved.check()
    rendered = rendered.run(timeout=20)

    collection_buttons = [
        item for item in rendered.button if item.key and item.key.startswith("collection::")
    ]
    assert [(item.label, item.key) for item in collection_buttons] == [
        ("Remove from Date night", "collection::Date night::restaurant")
    ]


def test_filter_controls_and_walking_link_render_correctly() -> None:
    rendered = AppTest.from_string(RESULTS_APP).run(timeout=20)
    assert any("Official site · reserve/order" in item.value for item in rendered.markdown)
    venue_type = next(item for item in rendered.selectbox if item.label == "Type")
    venue_type.select("Bars")
    rendered = rendered.run(timeout=20)

    collection_buttons = [
        item for item in rendered.button if item.key and item.key.startswith("collection::")
    ]
    assert [(item.label, item.key) for item in collection_buttons] == [
        ("Save to Favorites", "collection::Favorites::bar")
    ]

    availability = next(item for item in rendered.selectbox if item.label == "Availability")
    availability.select("Open at selected time")
    rendered = rendered.run(timeout=20)
    assert [item.label for item in rendered.date_input] == ["Date"]
    assert [item.label for item in rendered.time_input] == ["Local time"]

    walking_link = rendered.get("link_button")[0].proto
    assert walking_link.label == "Open walking directions"
    assert "travelmode=walking" in walking_link.url


def test_quality_cuisine_price_sort_and_open_now_controls() -> None:
    rendered = AppTest.from_string(RESULTS_APP).run(timeout=20)
    rendered.select_slider[0].set_value(4.9)
    rendered.number_input[0].set_value(600)
    rendered.multiselect[0].select("Italian Restaurant")
    rendered.multiselect[1].select("$$$")
    next(item for item in rendered.selectbox if item.label == "Sort by").select("Name")
    next(item for item in rendered.selectbox if item.label == "Availability").select(
        "Open now"
    )
    rendered = rendered.run(timeout=20)

    collection_buttons = [
        item for item in rendered.button if item.key and item.key.startswith("collection::")
    ]
    assert [(item.label, item.key) for item in collection_buttons] == [
        ("Save to Favorites", "collection::Favorites::restaurant")
    ]
    assert not rendered.exception


def test_main_search_form_passes_scope_and_cost_toggles() -> None:
    rendered = AppTest.from_string(MAIN_APP).run(timeout=20)
    location = next(
        item
        for item in rendered.text_input
        if item.label == "City, neighborhood, or ZIP/postal code"
    )
    scope = next(item for item in rendered.selectbox if item.label == "Looking for")
    thorough = next(
        item for item in rendered.checkbox if item.label == "Thorough coverage for larger areas"
    )
    insights = next(
        item
        for item in rendered.checkbox
        if item.label == "Include menu-verified dish and drink picks"
    )
    location.input("  Boston,   MA  ")
    scope.select("Bars only")
    thorough.check()
    insights.check()
    rendered = click_button(rendered, "Find my shortlist")

    assert rendered.session_state["search_call"] == {
        "location": "boston, ma",
        "place_types": ("bar",),
        "thorough": True,
    }
    assert rendered.session_state["insights_requested"] is True
    assert rendered.session_state["latest_result"].location == "Boston, MA"
    assert not rendered.exception


def test_shared_collection_prefills_without_triggering_search() -> None:
    token = encode_collection(
        SharedCollection(
            name="Seattle trip",
            location="Seattle, WA",
            place_types=("bar",),
            place_ids=("saved-place",),
        )
    )
    rendered = AppTest.from_string(MAIN_APP)
    rendered.query_params["share"] = token
    rendered = rendered.run(timeout=20)

    location = next(
        item
        for item in rendered.text_input
        if item.label == "City, neighborhood, or ZIP/postal code"
    )
    scope = next(item for item in rendered.selectbox if item.label == "Looking for")
    assert location.value == "Seattle, WA"
    assert scope.value == "Bars only"
    assert rendered.session_state["collections"]["Seattle trip"] == ["saved-place"]
    assert "search_call" not in rendered.session_state.filtered_state
    assert not rendered.exception
