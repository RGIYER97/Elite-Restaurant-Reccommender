"""Pure-ish Streamlit and Folium presentation helpers."""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit, urlunsplit

import folium
import streamlit as st

from .map_tiles import MapTileSession
from .models import Place, RATING_COLORS, SearchArea, SearchResult


APP_CSS = """
<style>
    .stApp { background: #f7f5ef; color:#21342b; }
    .block-container { max-width: 1480px; padding: 2rem 2.6rem 3rem; }
    [data-testid="stHeader"] { background:transparent; }
    .brand-row {
        align-items:center; border-bottom:1px solid #d9ddd3; display:flex;
        justify-content:space-between; margin-bottom:2rem; padding-bottom:1.1rem;
    }
    .wordmark { align-items:center; display:flex; font-size:1.05rem; font-weight:800; gap:.65rem; }
    .brand-mark {
        align-items:center; background:#244b3d; border-radius:9px; color:white;
        display:flex; font-size:1.1rem; height:30px; justify-content:center; width:30px;
    }
    .brand-note { color:#728077; font-size:.63rem; font-weight:800; letter-spacing:.16em; }
    .hero {
        align-items:center; display:grid; gap:2rem; grid-template-columns:minmax(0,1fr) auto;
        margin-bottom:1.6rem;
    }
    .hero h1 {
        color:#1f342a; font-family:Georgia,'Times New Roman',serif;
        font-size:clamp(2.7rem,5vw,4.5rem); font-weight:400; letter-spacing:-.045em;
        line-height:1.03; margin:.35rem 0 .75rem; padding:0;
    }
    .hero h1 em { color:#537260; font-weight:400; }
    .hero-copy { color:#68766e; line-height:1.65; margin:0; max-width:650px; }
    .quality-seal {
        align-items:center; border:1px solid #b9c5bb; border-radius:50%; color:#456653;
        display:flex; flex-direction:column; height:116px; justify-content:center;
        transform:rotate(7deg); width:116px;
    }
    .quality-seal b { font:400 2rem Georgia,serif; }
    .quality-seal small { font-size:.5rem; letter-spacing:.13em; text-transform:uppercase; }
    .eyebrow {
        color:#6d7d72; font-size:.65rem; font-weight:850;
        letter-spacing:.17em; text-transform:uppercase;
    }
    [data-testid="stForm"] {
        background:white; border:1px solid #d8ded5; border-radius:15px;
        box-shadow:0 8px 30px rgba(38,62,49,.04); padding:1.1rem 1.35rem;
    }
    .result-summary {
        align-items:flex-end; border-bottom:1px solid #d9ddd3; display:flex;
        gap:1rem; justify-content:space-between; margin:.6rem 0 1rem; padding:1rem 0;
    }
    .result-summary h2 { font:400 2rem/1.2 Georgia,serif; margin:.25rem 0; padding:0; }
    .result-summary p { color:#6e7b73; font-size:.75rem; margin:0; }
    .result-count { color:#315542; font:400 2.8rem Georgia,serif; }
    .coverage-note {
        background:#fffaf0; border:1px solid #eadcbf; border-radius:10px;
        color:#715b30; font-size:.78rem; margin:.5rem 0; padding:.65rem .8rem;
    }
    .place-card {
        background:white; border:1px solid #dfe3da; border-left:5px solid var(--band);
        border-radius:11px; margin:0 0 .75rem; padding:1rem 1.05rem;
    }
    .place-top { display:flex; align-items:flex-start; gap:.75rem; justify-content:space-between; }
    .place-name { color:#21372c; font:400 1.34rem/1.25 Georgia,serif; }
    .rating-pill {
        background:var(--band); border-radius:6px; color:white; flex:none;
        font-size:.8rem; font-weight:850; padding:.3rem .55rem;
    }
    .place-meta { color:#64748b; font-size:.83rem; margin-top:.42rem; }
    .place-address { color:#334155; font-size:.88rem; line-height:1.35; margin-top:.62rem; }
    .place-link { color:#315d47 !important; font-size:.8rem; font-weight:750; text-decoration:none; }
    .place-actions { display:flex; flex-wrap:wrap; gap:.45rem 1rem; margin-top:.75rem; }
    .open-now { color:#28724c; font-weight:800; }
    .closed-now { color:#9b3d32; font-weight:800; }
    .known-for { color:#475569; font-size:.84rem; line-height:1.4; margin-top:.72rem; }
    .dish-label {
        color:#64748b; font-size:.7rem; font-weight:850; letter-spacing:.08em;
        margin-top:.8rem; text-transform:uppercase;
    }
    .dish-list { display:flex; flex-wrap:wrap; gap:.38rem; margin-top:.38rem; }
    .dish-chip {
        background:#eef3ed; border:1px solid #d9e2d9; border-radius:999px;
        color:#0f172a; font-size:.78rem; font-weight:720; padding:.28rem .55rem;
    }
    .evidence { color:#64748b; font-size:.69rem; line-height:1.35; margin-top:.65rem; }
    .evidence a { color:#64748b !important; text-decoration:underline; }
    .legend { display:flex; flex-wrap:wrap; gap:.65rem 1.1rem; margin:.25rem 0 1rem; }
    .legend-item { color:#475569; font-size:.82rem; }
    .legend-dot { border-radius:50%; display:inline-block; height:10px; margin-right:6px; width:10px; }
    .google-attribution { color:#64748b; font-size:.73rem; margin:.6rem 0 0; }
    .empty-state {
        border:1px dashed #bdc9be; border-radius:14px; margin:1rem 0;
        padding:3.4rem 1.5rem; text-align:center;
    }
    .empty-state h2 { font:400 1.9rem Georgia,serif; margin:.7rem 0; padding:0; }
    .empty-state p { color:#718078; line-height:1.65; margin:auto; max-width:560px; }
    .intro-grid { display:grid; gap:1.5rem; grid-template-columns:repeat(3,1fr); margin-top:1.8rem; }
    .intro-step { border-top:1px solid #d7ded5; padding-top:1rem; }
    .intro-step small { color:#668070; font-size:.6rem; font-weight:800; letter-spacing:.14em; }
    .intro-step h3 { font:400 1.25rem Georgia,serif; margin:.45rem 0; padding:0; }
    .intro-step p { color:#738078; font-size:.78rem; line-height:1.6; }
    .footer {
        border-top:1px solid #d9ddd3; color:#7b867f; display:flex; font-size:.65rem;
        justify-content:space-between; margin-top:2rem; padding-top:1rem;
    }
    iframe { border-radius:12px; }
    @media (max-width: 760px) {
        .block-container { padding:1.2rem 1rem 2rem; }
        .brand-note,.quality-seal { display:none; }
        .hero { grid-template-columns:1fr; }
        .hero h1 { font-size:2.8rem; }
        .intro-grid { grid-template-columns:1fr; }
        .result-summary { align-items:flex-start; }
    }
</style>
"""


def inject_styles() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)


def safe_url(value: str | None) -> str:
    """Allow provider links only when they are ordinary HTTPS URLs."""

    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username:
            return urlunsplit(
                ("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment)
            )
    except (TypeError, ValueError):
        pass
    return ""


def render_hero() -> None:
    st.markdown(
        """
        <div class="brand-row">
          <div class="wordmark"><span class="brand-mark">✳</span>The Shortlist</div>
          <span class="brand-note">GOOD PLACES · HIGH STANDARDS</span>
        </div>
        <section class="hero">
          <div>
            <span class="eyebrow">RESTAURANTS &amp; BARS WORTH YOUR TIME</span>
            <h1>Go somewhere<br><em>really good.</em></h1>
            <p class="hero-copy">A considered collection of standout tables and exceptional bars—bounded to your chosen area and backed by hundreds of reviews.</p>
          </div>
          <div class="quality-seal"><small>The standard</small><b>4.7+</b><small>200+ reviews</small></div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_intro() -> None:
    st.markdown(
        """
        <div class="intro-grid">
          <div class="intro-step"><small>01 / PICK A PLACE</small><h3>Your corner of the world.</h3><p>Start with a city, neighborhood, or postal code. We resolve and visibly bound the search area.</p></div>
          <div class="intro-step"><small>02 / SET A HIGH BAR</small><h3>Only the standouts.</h3><p>Every result clears both immutable standards: a 4.7 rating and at least 200 reviews.</p></div>
          <div class="intro-step"><small>03 / ORDER WELL</small><h3>Know what to try.</h3><p>When requested, review favorites appear only after they are verified against an accessible online menu.</p></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(has_candidates: bool) -> None:
    detail = (
        "Places were found, but none cleared both quality thresholds inside the resolved radius."
        if has_candidates
        else "Google returned no restaurants or bars inside the resolved area."
    )
    st.markdown(
        f'<div class="empty-state"><span class="eyebrow">A HIGH BAR, BY DESIGN</span>'
        f'<h2>No places made the cut.</h2><p>{detail} Try a nearby neighborhood or a broader city.</p></div>',
        unsafe_allow_html=True,
    )


def render_legend() -> None:
    st.markdown(
        f"""
        <div class="legend" aria-label="Rating color legend">
          <span class="legend-item"><i class="legend-dot" style="background:{RATING_COLORS['4.7']}"></i>4.7</span>
          <span class="legend-item"><i class="legend-dot" style="background:{RATING_COLORS['4.8']}"></i>4.8</span>
          <span class="legend-item"><i class="legend-dot" style="background:{RATING_COLORS['4.9+']}"></i>4.9–5.0</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_summary(result: SearchResult) -> None:
    noun = "pick" if len(result.places) == 1 else "picks"
    radius_km = result.search_area.radius_meters / 1_000
    radius_miles = result.search_area.radius_meters / 1_609.344
    walking_minutes = max(5, round(result.search_area.radius_meters / 80))
    scope_description = (
        f"Walkable area · ≈{walking_minutes} min · {radius_miles:.1f} mi / {radius_km:.1f} km"
        if result.search_area.is_walkable
        else f"{radius_miles:.1f} mi / {radius_km:.1f} km radius"
    )
    details_count = sum(place.insights_loaded for place in result.places)
    cold_cache_calls = 1 + result.page_count + details_count
    st.markdown(
        f"""
        <div class="result-summary">
          <div><span class="eyebrow">YOUR NEXT GOOD EVENING</span>
            <h2>The shortlist in {escape(result.search_area.name)}</h2>
            <p>{scope_description} · {result.scanned_count:,} candidates · {result.page_count} pages · {cold_cache_calls} provider calls on a cold cache · Updated {result.fetched_at.strftime('%b %d, %H:%M UTC')}</p>
          </div>
          <span class="result-count" title="{len(result.places)} exceptional {noun}">{len(result.places):02d}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for warning in result.warnings:
        st.markdown(f'<div class="coverage-note">{escape(warning)}</div>', unsafe_allow_html=True)


def build_map(
    places: tuple[Place, ...],
    tiles: MapTileSession,
    *,
    search_area: SearchArea | None = None,
) -> folium.Map:
    """Build a Google-backed Folium map with strictly banded markers."""

    latitudes = [place.latitude for place in places]
    longitudes = [place.longitude for place in places]
    center = [sum(latitudes) / len(latitudes), sum(longitudes) / len(longitudes)]
    result_map = folium.Map(
        location=center,
        zoom_start=13,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )
    folium.TileLayer(
        tiles=tiles.tile_url,
        attr=f'<a href="https://maps.google.com/">Google Maps</a> · {escape(tiles.copyright)}',
        name="Google Maps",
        max_zoom=22,
        overlay=False,
        control=False,
    ).add_to(result_map)

    if search_area is not None:
        walking_minutes = max(5, round(search_area.radius_meters / 80))
        radius_tooltip = (
            f"≈{walking_minutes}-minute walk area · {search_area.radius_meters / 1_609.344:.1f} mi"
            if search_area.is_walkable
            else f"Search radius · {search_area.radius_meters / 1_609.344:.1f} mi"
        )
        folium.Circle(
            location=(search_area.center_latitude, search_area.center_longitude),
            radius=search_area.radius_meters,
            color="#475569",
            weight=2,
            opacity=0.65,
            fill=True,
            fill_color="#94A3B8",
            fill_opacity=0.08,
            tooltip=radius_tooltip,
        ).add_to(result_map)

    for index, place in enumerate(places, start=1):
        maps_link = ""
        maps_url = safe_url(place.google_maps_uri)
        if maps_url:
            maps_link = (
                f'<br><a href="{escape(maps_url, quote=True)}" '
                'target="_blank" rel="noopener noreferrer">Open in Google Maps</a>'
            )
        dishes = ""
        if place.recommended_dishes:
            dishes = f"<br><strong>Try:</strong> {escape(', '.join(place.recommended_dishes))}"
        open_now = place.is_open_now()
        hours = (
            "<br><strong>Open now</strong>"
            if open_now is True
            else "<br><strong>Closed now</strong>"
            if open_now is False
            else ""
        )
        popup = folium.Popup(
            (
                f"<strong>{escape(place.name)}</strong><br>"
                f"{place.rating:.1f} ★ · {place.review_count:,} reviews<br>"
                f"{escape(place.address)}{hours}{dishes}{maps_link}"
            ),
            max_width=300,
        )
        marker_html = (
            f'<div style="width:32px;height:32px;background:{place.color};color:white;'
            'border:2px solid white;border-radius:50%;box-shadow:0 2px 8px #0004;'
            'display:flex;align-items:center;justify-content:center;'
            f'font:750 11px system-ui">{index:02d}</div>'
        )
        folium.Marker(
            location=(place.latitude, place.longitude),
            icon=folium.DivIcon(
                html=marker_html,
                icon_size=(36, 36),
                icon_anchor=(18, 18),
            ),
            tooltip=f"{index}. {escape(place.name)} · {place.rating:.1f}",
            popup=popup,
        ).add_to(result_map)

    if len(places) > 1:
        bounds = [
            [min(latitudes), min(longitudes)],
            [max(latitudes), max(longitudes)],
        ]
        result_map.fit_bounds(bounds, padding=(28, 28), max_zoom=15)
    return result_map


def render_place_card(place: Place, rank: int) -> None:
    action_links: list[str] = []
    maps_url = safe_url(place.google_maps_uri)
    if maps_url:
        action_links.append(
            f'<a class="place-link" '
            f'href="{escape(maps_url, quote=True)}" target="_blank" '
            'rel="noopener noreferrer">Google Maps ↗</a>'
        )
    directions_url = safe_url(place.directions_uri)
    if directions_url:
        action_links.append(
            f'<a class="place-link" href="{escape(directions_url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">Directions ↗</a>'
        )
    website_url = safe_url(place.website_uri)
    if website_url:
        action_links.append(
            f'<a class="place-link" href="{escape(website_url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">Official site · reserve/order ↗</a>'
        )
    actions = (
        f'<div class="place-actions">{"".join(action_links)}</div>'
        if action_links
        else ""
    )

    open_now = place.is_open_now()
    if open_now is True:
        opening_status = '<span class="open-now">Open now</span>'
    elif open_now is False:
        opening_status = '<span class="closed-now">Closed now</span>'
    else:
        opening_status = "Hours unavailable"

    known_for = ""
    if place.known_for:
        known_for = f'<div class="known-for"><strong>Known for:</strong> {escape(place.known_for)}</div>'

    dish_section = ""
    if place.recommended_dishes:
        chips = "".join(
            f'<span class="dish-chip">{escape(dish)}</span>'
            for dish in place.recommended_dishes
        )
        dish_section = (
            '<div class="dish-label">Menu-verified picks</div>'
            f'<div class="dish-list">{chips}</div>'
        )
    elif not place.insights_loaded:
        dish_section = (
            '<div class="evidence">Menu picks were not loaded in cost-saving mode.</div>'
        )
    elif place.insights_error:
        dish_section = '<div class="evidence">Dish recommendations are temporarily unavailable.</div>'
    elif place.dish_candidates_found and not place.menu_checked:
        dish_section = (
            '<div class="evidence">Review favorites were found, but no accessible online menu '
            'was available to verify them.</div>'
        )
    elif place.dish_candidates_found:
        dish_section = (
            '<div class="evidence">Review favorites were found, but none could be verified on '
            'the accessible menu.</div>'
        )
    else:
        dish_section = '<div class="evidence">No clear dish consensus was found in available reviews.</div>'

    evidence_links: list[str] = []
    menu_url = safe_url(place.menu_uri)
    if menu_url:
        evidence_links.append(
            f'<a href="{escape(menu_url, quote=True)}" target="_blank" '
            'rel="noopener noreferrer">Menu source ↗</a>'
        )
    reviews_url = safe_url(place.reviews_uri)
    if reviews_url:
        evidence_links.append(
            f'<a href="{escape(reviews_url, quote=True)}" target="_blank" '
            'rel="noopener noreferrer">Google review evidence ↗</a>'
        )
    if place.summary_disclosure:
        evidence_links.append(escape(place.summary_disclosure))
    flag_url = safe_url(place.summary_flag_uri)
    if flag_url:
        evidence_links.append(
            f'<a href="{escape(flag_url, quote=True)}" target="_blank" '
            'rel="noopener noreferrer">Report summary ↗</a>'
        )
    evidence = (
        f'<div class="evidence">{" · ".join(evidence_links)}</div>'
        if evidence_links
        else ""
    )

    st.markdown(
        f"""
        <article class="place-card" style="--band:{place.color}">
          <div class="place-top">
            <div class="place-name">{rank}. {escape(place.name)}</div>
            <div class="rating-pill">{place.rating:.1f} ★</div>
          </div>
          <div class="place-meta">
            {escape(place.category_label)} · {escape(place.primary_type_label)} ·
            {escape(place.price_label)} · {place.review_count:,} reviews · {opening_status}
          </div>
          <div class="place-address">{escape(place.address)}</div>
          {known_for}
          {dish_section}
          {evidence}
          {actions}
        </article>
        """,
        unsafe_allow_html=True,
    )
