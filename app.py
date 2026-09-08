"""Streamlit entry point for the curated restaurant finder."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
import hashlib
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st
from streamlit_folium import st_folium

from restaurant_finder.config import ConfigurationError, Settings
from restaurant_finder.errors import GoogleMapsError
from restaurant_finder.filters import filter_places
from restaurant_finder.itinerary import suggest_evening_plan
from restaurant_finder.map_tiles import GoogleMapTilesClient, MapTileSession
from restaurant_finder.models import Place, SearchResult
from restaurant_finder.places_client import GooglePlacesClient
from restaurant_finder.service import find_curated_places
from restaurant_finder.sharing import SharedCollection, decode_collection, encode_collection
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


SEARCH_SCOPES = {
    "Restaurants & bars": ("restaurant", "bar"),
    "Restaurants only": ("restaurant",),
    "Bars only": ("bar",),
}
PRICE_LABELS = {
    "PRICE_LEVEL_INEXPENSIVE": "$",
    "PRICE_LEVEL_MODERATE": "$$",
    "PRICE_LEVEL_EXPENSIVE": "$$$",
    "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
    "UNKNOWN": "Price unavailable",
}
GENERIC_PLACE_TYPES = {
    "bar",
    "establishment",
    "food",
    "point_of_interest",
    "restaurant",
}


# Always load the .env next to this file. Streamlit is often launched from a
# different directory or from a shell that still contains an older key; in both
# cases the project-local credential must win.
load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"), override=True)
st.set_page_config(
    page_title="The Shortlist · Restaurants & Bars",
    page_icon="◆",
    layout="wide",
)

# Reuse recent area sweeps across users and nearby navigation. The bounded cache
# avoids another paid search for spelling/case variants and repeated locations.
@st.cache_data(show_spinner=False, max_entries=64, ttl=timedelta(days=30))
def cached_search(
    location: str,
    *,
    place_types: tuple[str, ...],
    thorough: bool,
    credential_version: str,
    geocoding_credential_version: str,
    _api_key: str,
    _geocoding_api_key: str | None,
    max_pages: int | None,
) -> SearchResult:
    # Fingerprints participate in the cache key while secrets prefixed with an
    # underscore stay out of Streamlit's cache metadata.
    del credential_version, geocoding_credential_version
    return find_curated_places(
        location,
        api_key=_api_key,
        geocoding_api_key=_geocoding_api_key,
        max_pages=max_pages,
        thorough=thorough,
        enrich=False,
        place_types=place_types,
    )


# Details are cached by Place ID independently of area searches. Overlapping
# neighborhoods therefore reuse the expensive review/menu enrichment request.
@st.cache_data(show_spinner=False, max_entries=1_024, ttl=timedelta(days=30))
def cached_place_insight(
    place_id: str,
    *,
    credential_version: str,
    _api_key: str,
    _place: Place,
) -> Place:
    del credential_version
    if _place.id != place_id:
        raise ValueError("Place cache key does not match the requested place.")
    return GooglePlacesClient(api_key=_api_key).enrich_place(_place)


def add_cached_insights(result: SearchResult, *, api_key: str) -> SearchResult:
    """Attach cached per-place details while leaving transient failures uncached."""

    enriched = []
    fingerprint = credential_fingerprint(api_key)
    for place in result.places:
        try:
            cached = cached_place_insight(
                place.id,
                credential_version=fingerprint,
                _api_key=api_key,
                _place=place,
            )
        except GoogleMapsError as exc:
            enriched.append(place.with_insights(insights_error=str(exc)))
            continue
        enriched.append(
            place.with_insights(
                recommended_dishes=cached.recommended_dishes,
                known_for=cached.known_for,
                reviews_uri=cached.reviews_uri,
                summary_disclosure=cached.summary_disclosure,
                summary_flag_uri=cached.summary_flag_uri,
                menu_uri=cached.menu_uri,
                menu_checked=cached.menu_checked,
                dish_candidates_found=cached.dish_candidates_found,
            )
        )
    return replace(result, places=tuple(enriched))


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


def canonical_location(location: str) -> str:
    """Collapse cosmetic input differences so equivalent searches share a cache key."""

    return " ".join(location.split()).casefold()


def scope_label(place_types: tuple[str, ...]) -> str:
    return next(
        (label for label, values in SEARCH_SCOPES.items() if values == place_types),
        "Restaurants & bars",
    )


def collection_state() -> dict[str, list[str]]:
    collections = st.session_state.setdefault("collections", {"Favorites": []})
    if not isinstance(collections, dict):
        collections = {"Favorites": []}
        st.session_state["collections"] = collections
    collections.setdefault("Favorites", [])
    return collections


def import_shared_collection() -> None:
    token = st.query_params.get("share")
    if not token or token == st.session_state.get("imported_share_token"):
        return
    st.session_state["imported_share_token"] = token
    try:
        shared = decode_collection(token)
    except ValueError as exc:
        st.warning(str(exc))
        return

    collections = collection_state()
    imported_name = shared.name
    suffix = 2
    while (
        imported_name in collections
        and collections[imported_name] != list(shared.place_ids)
    ):
        imported_name = f"{shared.name[:27]} (shared {suffix})"
        suffix += 1
    collections[imported_name] = list(shared.place_ids)
    st.session_state["active_collection"] = imported_name
    st.session_state["only_active_collection"] = True
    st.session_state["location_input"] = shared.location
    st.session_state["search_scope"] = scope_label(shared.place_types)
    st.session_state["shared_collection_notice"] = (
        f'Imported “{imported_name}”. Submit the prefilled search to load its places.'
    )


def render_collection_manager(result: SearchResult) -> tuple[str, frozenset[str] | None]:
    collections = collection_state()
    with st.expander("Your collections & sharing", expanded=False):
        create_column, active_column = st.columns((2, 2))
        with create_column:
            new_name = st.text_input(
                "New collection",
                max_chars=40,
                placeholder="e.g. Client dinners",
                key="new_collection_name",
            )
            if st.button("Create collection", use_container_width=True):
                cleaned = " ".join(new_name.split())
                if not cleaned:
                    st.warning("Enter a collection name first.")
                else:
                    collections.setdefault(cleaned, [])
                    st.session_state["active_collection"] = cleaned
                    st.rerun()

        names = tuple(collections)
        selected_name = st.session_state.get("active_collection", "Favorites")
        if selected_name not in collections:
            selected_name = "Favorites"
            st.session_state["active_collection"] = selected_name
        with active_column:
            active = st.selectbox(
                "Active collection",
                names,
                index=names.index(selected_name),
                key="active_collection",
            )
            only_saved = st.checkbox(
                "Only show places in this collection",
                value=False,
                key="only_active_collection",
            )

        saved_ids = tuple(collections.get(active, []))
        st.caption(f"{len(saved_ids)} saved places · Collections live in this browser session.")
        share_column, clear_column = st.columns(2)
        with share_column:
            if st.button("Create share link", use_container_width=True):
                token = encode_collection(
                    SharedCollection(
                        name=active,
                        location=result.location,
                        place_types=result.place_types,
                        place_ids=saved_ids,
                    )
                )
                st.query_params["share"] = token
                st.session_state["last_share_token"] = (active, token)
        with clear_column:
            if st.button("Clear active collection", use_container_width=True):
                collections[active] = []
                st.rerun()

        last_share = st.session_state.get("last_share_token")
        if isinstance(last_share, tuple) and last_share[0] == active:
            token = last_share[1]
            st.success("The browser URL now contains the collection. Copy the address bar to share it.")
            st.code(f"?share={token}", language=None)

    return active, frozenset(saved_ids) if only_saved else None


def render_filters(
    result: SearchResult,
    *,
    saved_place_ids: frozenset[str] | None,
) -> tuple[Place, ...]:
    price_options = tuple(
        value
        for value in PRICE_LABELS
        if value in {(place.price_level or "UNKNOWN") for place in result.places}
    )
    cuisine_options = tuple(
        sorted(
            {
                venue_type
                for place in result.places
                for venue_type in (*place.types, place.primary_type)
                if venue_type and venue_type not in GENERIC_PLACE_TYPES
            }
        )
    )

    with st.expander("Refine the shortlist", expanded=True):
        kind_column, rating_column, reviews_column, sort_column = st.columns(4)
        available_kinds = ["All places"]
        if "restaurant" in result.place_types:
            available_kinds.append("Restaurants")
        if "bar" in result.place_types:
            available_kinds.append("Bars")
        with kind_column:
            kind_label = st.selectbox("Type", available_kinds, key="place_kind")
        with rating_column:
            minimum_rating = st.select_slider(
                "Minimum rating",
                options=(4.7, 4.8, 4.9),
                value=4.7,
                key="minimum_rating",
            )
        with reviews_column:
            maximum_reviews = max(place.review_count for place in result.places)
            minimum_reviews = st.number_input(
                "Minimum reviews",
                min_value=200,
                max_value=maximum_reviews,
                value=200,
                step=50,
                key="minimum_reviews",
            )
        with sort_column:
            order = st.selectbox(
                "Sort by",
                ("Highest rated", "Most reviewed", "Name"),
                key="place_order",
            )

        cuisine_column, price_column, availability_column = st.columns(3)
        with cuisine_column:
            cuisines = st.multiselect(
                "Cuisine / venue style",
                cuisine_options,
                format_func=lambda value: value.replace("_", " ").title(),
                key="cuisine_filters",
            )
        with price_column:
            prices = st.multiselect(
                "Price",
                price_options,
                format_func=lambda value: PRICE_LABELS[value],
                key="price_filters",
            )
        with availability_column:
            availability_label = st.selectbox(
                "Availability",
                ("Any time", "Open now", "Open at selected time"),
                key="availability_filter",
            )

        if availability_label == "Open at selected time":
            date_column, time_column = st.columns(2)
            with date_column:
                selected_date = st.date_input("Date", value=date.today(), key="open_date")
            with time_column:
                selected_time = st.time_input("Local time", value=time(19, 0), key="open_time")
            st.caption(
                "Selected-time filtering uses the venue’s typical weekly hours; holidays and "
                "one-off closures may differ."
            )
        else:
            selected_date = date.today()
            selected_time = time(19, 0)
            if availability_label == "Open now":
                st.caption(
                    "Open-now filtering is calculated in each venue’s time zone from its "
                    "typical weekly hours; holidays and one-off closures may differ."
                )

    kind = {
        "All places": "all",
        "Restaurants": "restaurant",
        "Bars": "bar",
    }[kind_label]
    availability = {
        "Any time": "any",
        "Open now": "open_now",
        "Open at selected time": "open_at",
    }[availability_label]
    open_at = datetime.combine(selected_date, selected_time)
    visible = filter_places(
        result.places,
        kind=kind,
        minimum_rating=float(minimum_rating),
        minimum_reviews=int(minimum_reviews),
        price_levels=frozenset(prices),
        cuisines=frozenset(cuisines),
        availability=availability,
        open_at=open_at,
        saved_place_ids=saved_place_ids,
    )
    if order == "Most reviewed":
        return tuple(
            sorted(visible, key=lambda place: (-place.review_count, -place.rating, place.name.casefold()))
        )
    if order == "Name":
        return tuple(sorted(visible, key=lambda place: (place.name.casefold(), place.id)))
    return tuple(sorted(visible, key=lambda place: (-place.rating, -place.review_count, place.name.casefold())))


def render_evening_planner(places: tuple[Place, ...], active_collection: str) -> None:
    restaurants = tuple(place for place in places if "restaurant" in place.matched_types)
    bars = tuple(place for place in places if "bar" in place.matched_types)
    if not restaurants or not bars:
        return

    with st.expander("Plan dinner + drinks", expanded=False):
        dinner_by_id = {place.id: place for place in restaurants}
        dinner_id = st.selectbox(
            "Start with dinner at",
            tuple(dinner_by_id),
            format_func=lambda place_id: dinner_by_id[place_id].name,
            key="itinerary_dinner",
        )
        plan = suggest_evening_plan(places, dinner_id=dinner_id)
        if plan is None:
            st.info("A distinct qualifying bar is needed to build this itinerary.")
            return
        walk_minutes = max(1, round(plan.straight_line_meters / 80))
        st.markdown(
            f"**Dinner:** {plan.dinner.name}  →  **Drinks:** {plan.drinks.name}  "
            f"· about {walk_minutes} minutes apart as a straight-line estimate"
        )
        action_column, save_column = st.columns(2)
        with action_column:
            st.link_button(
                "Open walking directions",
                plan.walking_url,
                use_container_width=True,
            )
        with save_column:
            if st.button("Save both to active collection", use_container_width=True):
                collections = collection_state()
                existing = collections.setdefault(active_collection, [])
                collections[active_collection] = list(
                    dict.fromkeys((*existing, plan.dinner.id, plan.drinks.id))
                )
                st.rerun()


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

    if not any(place.insights_loaded for place in result.places):
        st.info(
            "Cost-saving mode is active: ratings and the map are complete, while paid dish "
            "insights were skipped. Enable menu-verified picks and submit again to load them "
            "without repeating this cached area search."
        )

    active_collection, saved_filter = render_collection_manager(result)
    visible = render_filters(result, saved_place_ids=saved_filter)
    render_evening_planner(result.places, active_collection)

    if not visible:
        st.info("No places match the active filters or collection. Broaden the refinements above.")
        return

    list_column, map_column = st.columns((5, 7), gap="large")
    with list_column:
        st.caption(f"{len(visible)} PLACES · NUMBERED TO MATCH THE MAP")
        with st.container(height=680, border=False):
            for rank, place in enumerate(visible, start=1):
                render_place_card(place, rank)
                collections = collection_state()
                saved = place.id in collections.get(active_collection, [])
                button_label = (
                    f"Remove from {active_collection}" if saved else f"Save to {active_collection}"
                )
                if st.button(
                    button_label,
                    key=f"collection::{active_collection}::{place.id}",
                    use_container_width=True,
                ):
                    existing = collections.setdefault(active_collection, [])
                    collections[active_collection] = (
                        [place_id for place_id in existing if place_id != place.id]
                        if saved
                        else list(dict.fromkeys((*existing, place.id)))
                    )
                    st.rerun()
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

    import_shared_collection()
    shared_notice = st.session_state.pop("shared_collection_notice", None)
    if shared_notice:
        st.info(shared_notice)

    with st.form("location_search", clear_on_submit=False):
        input_column, scope_column, button_column = st.columns(
            (4, 2, 1),
            vertical_alignment="bottom",
        )
        with input_column:
            location = st.text_input(
                "City, neighborhood, or ZIP/postal code",
                value="Manhattan, NYC",
                max_chars=180,
                placeholder="e.g. Williamsburg, Brooklyn",
                key="location_input",
            )
        with scope_column:
            scope = st.selectbox(
                "Looking for",
                tuple(SEARCH_SCOPES),
                key="search_scope",
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
        include_insights = st.checkbox(
            "Include menu-verified dish and drink picks",
            value=False,
            help=(
                "Adds one Place Details Enterprise + Atmosphere request for each venue that "
                "passes the strict filters. Results are cached per venue for reuse across areas."
            ),
        )

    if submitted:
        st.session_state.pop("latest_result", None)
        normalized_location = " ".join(location.split())
        if not normalized_location:
            st.error("Enter a city, neighborhood, or ZIP/postal code.")
        else:
            try:
                spinner_text = (
                    f"Sweeping and verifying menus in {normalized_location}…"
                    if include_insights
                    else f"Sweeping restaurants and bars in {normalized_location}…"
                )
                with st.spinner(spinner_text):
                    # Area searches and per-place details have separate caches,
                    # so enabling insights later does not repeat the area sweep.
                    result = cached_search(
                        canonical_location(normalized_location),
                        place_types=SEARCH_SCOPES[scope],
                        thorough=thorough,
                        credential_version=credential_fingerprint(settings.places_api_key),
                        geocoding_credential_version=credential_fingerprint(
                            settings.geocoding_api_key or ""
                        ),
                        _api_key=settings.places_api_key,
                        _geocoding_api_key=settings.geocoding_api_key,
                        max_pages=settings.max_pages,
                    )
                    if include_insights:
                        result = add_cached_insights(result, api_key=settings.places_api_key)
                    st.session_state["latest_result"] = replace(
                        result,
                        location=normalized_location,
                    )
                    for widget_key in (
                        "place_kind",
                        "place_order",
                        "minimum_rating",
                        "minimum_reviews",
                        "cuisine_filters",
                        "price_filters",
                        "availability_filter",
                    ):
                        st.session_state.pop(widget_key, None)
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
