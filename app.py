"""Streamlit entry point for the curated restaurant finder."""

from __future__ import annotations

from datetime import timedelta
import hashlib
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st
from streamlit_folium import st_folium

from restaurant_finder.config import ConfigurationError, Settings
from restaurant_finder.errors import GoogleMapsError
from restaurant_finder.map_tiles import GoogleMapTilesClient, MapTileSession
from restaurant_finder.models import SearchResult
from restaurant_finder.service import find_curated_places
from restaurant_finder.ui import (
    build_map,
    inject_styles,
    render_empty_state,
    render_hero,
    render_intro,
    render_legend,
    render_place_card,
    render_summary,
)


# Always load the .env next to this file. Streamlit is often launched from a
# different directory or from a shell that still contains an older key; in both
# cases the project-local credential must win.
load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"), override=True)
st.set_page_config(
    page_title="The Shortlist · Restaurants & Bars",
    page_icon="◆",
    layout="wide",
)

# Keep only the latest distinct response. It remains cached across Streamlit
# reruns until a different query evicts it, with a 30-day policy safety cap.
@st.cache_data(show_spinner=False, max_entries=1, ttl=timedelta(days=30))
def cached_search(
    location: str,
    *,
    thorough: bool,
    credential_version: str,
    _api_key: str,
    max_pages: int | None,
) -> SearchResult:
    # credential_version intentionally participates in Streamlit's cache key;
    # _api_key does not, which keeps the full secret out of cache metadata.
    del credential_version
    return find_curated_places(
        location,
        api_key=_api_key,
        max_pages=max_pages,
        thorough=thorough,
    )


# Map Tiles tokens currently last about two weeks. Cache for slightly less.
@st.cache_data(show_spinner=False, max_entries=4, ttl=timedelta(days=13))
def cached_tile_session(
    *,
    credential_version: str,
    _api_key: str,
    region: str,
    language: str,
) -> MapTileSession:
    del credential_version
    return GoogleMapTilesClient(
        _api_key,
        region=region,
        language=language,
    ).create_session()


def credential_fingerprint(api_key: str) -> str:
    """Invalidate a cache if credentials change without exposing the key."""

    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


def load_settings() -> Settings | None:
    try:
        return Settings.from_env()
    except ConfigurationError as exc:
        st.error(str(exc))
        return None


def render_results(result: SearchResult, settings: Settings) -> None:
    render_summary(result)
    render_legend()

    if result.scanned_count == 0:
        render_empty_state(has_candidates=False)
        return
    if not result.places:
        render_empty_state(has_candidates=True)
        return

    filter_column, sort_column = st.columns((3, 2), gap="large")
    with filter_column:
        kind = st.radio(
            "Show places",
            ("All places", "Restaurants", "Bars"),
            horizontal=True,
            key="place_kind",
        )
    with sort_column:
        order = st.selectbox(
            "Sort by",
            ("Highest rated", "Most reviewed", "Name"),
            key="place_order",
        )

    visible = tuple(
        place
        for place in result.places
        if kind == "All places"
        or ("restaurant" if kind == "Restaurants" else "bar") in place.matched_types
    )
    if order == "Most reviewed":
        visible = tuple(
            sorted(visible, key=lambda place: (-place.review_count, -place.rating, place.name.casefold()))
        )
    elif order == "Name":
        visible = tuple(sorted(visible, key=lambda place: (place.name.casefold(), place.id)))

    if not visible:
        st.info("No places in this category made the shortlist. Select All places to see every match.")
        return

    list_column, map_column = st.columns((5, 7), gap="large")
    with list_column:
        st.caption(f"{len(visible)} PLACES · NUMBERED TO MATCH THE MAP")
        with st.container(height=680, border=False):
            for rank, place in enumerate(visible, start=1):
                render_place_card(place, rank)
            st.markdown(
                '<div class="google-attribution">Place data © Google Maps</div>',
                unsafe_allow_html=True,
            )

    with map_column:
        st.caption("EXPLORE THE AREA · SELECT A NUMBERED MARKER FOR DETAILS")
        try:
            tiles = cached_tile_session(
                credential_version=credential_fingerprint(settings.map_tiles_api_key),
                _api_key=settings.map_tiles_api_key,
                region=settings.map_region,
                language=settings.map_language,
            )
            st_folium(
                build_map(visible, tiles, search_area=result.search_area),
                height=680,
                use_container_width=True,
                returned_objects=[],
            )
        except GoogleMapsError as exc:
            st.error(str(exc))
            st.caption(
                "Enable the Google Map Tiles API for the map key. The curated "
                "Places results remain available in the list."
            )


def main() -> None:
    inject_styles()
    render_hero()

    settings = load_settings()
    if settings is None:
        return
    if not settings.places_api_key:
        st.warning(
            "Add GOOGLE_PLACES_API_KEY to your .env file, then restart Streamlit."
        )
        st.code("cp .env.example .env\nstreamlit run app.py", language="bash")
        return

    with st.form("location_search", clear_on_submit=False):
        input_column, button_column = st.columns((5, 1), vertical_alignment="bottom")
        with input_column:
            location = st.text_input(
                "City, neighborhood, or ZIP/postal code",
                value="Manhattan, NYC",
                max_chars=180,
                placeholder="e.g. Williamsburg, Brooklyn",
            )
        with button_column:
            submitted = st.form_submit_button(
                "Find my shortlist",
                type="primary",
                use_container_width=True,
            )
        thorough = st.checkbox(
            "Thorough coverage for larger areas",
            value=False,
            help=(
                "Splits the resolved viewport into four cells and paginates restaurants and bars "
                "inside each. This can find results hidden by Google's per-query cap, but may use "
                "up to four times as many billable search requests."
            ),
        )

    if submitted:
        st.session_state.pop("latest_result", None)
        normalized_location = " ".join(location.split())
        if not normalized_location:
            st.error("Enter a city, neighborhood, or ZIP/postal code.")
        else:
            try:
                with st.spinner(f"Sweeping restaurants and bars in {normalized_location}…"):
                    # Session state keeps the result visible on widget reruns. The
                    # one-entry data cache makes repeated identical calls free.
                    st.session_state["latest_result"] = cached_search(
                        normalized_location,
                        thorough=thorough,
                        credential_version=credential_fingerprint(settings.places_api_key),
                        _api_key=settings.places_api_key,
                        max_pages=settings.max_pages,
                    )
                    st.session_state["place_kind"] = "All places"
                    st.session_state["place_order"] = "Highest rated"
            except (GoogleMapsError, ValueError) as exc:
                st.error(str(exc))

    latest_result = st.session_state.get("latest_result")
    if isinstance(latest_result, SearchResult):
        render_results(latest_result, settings)
    else:
        render_legend()
        render_intro()

    st.markdown(
        '<div class="footer"><span>THE SHORTLIST · A LITTLE MORE SELECTIVE.</span>'
        '<span>Ratings and review insights from Google Maps. Menu verification reflects accessible online menus at search time.</span></div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
