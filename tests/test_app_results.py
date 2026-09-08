from streamlit.testing.v1 import AppTest


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


def test_results_ui_renders_filters_collections_and_itinerary() -> None:
    rendered = AppTest.from_string(RESULTS_APP).run(timeout=20)

    assert not rendered.exception
    assert "Your collections & sharing" in [item.label for item in rendered.expander]
    assert "Refine the shortlist" in [item.label for item in rendered.expander]
    assert "Plan dinner + drinks" in [item.label for item in rendered.expander]
    assert "Active collection" in [item.label for item in rendered.selectbox]
    assert "Availability" in [item.label for item in rendered.selectbox]
