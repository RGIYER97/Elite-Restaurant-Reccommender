# The Shortlist

A Streamlit app that resolves an entered town/neighborhood/postal code, searches
Google Places inside its geographic viewport and calculated radius, follows every
returned page, deduplicates overlaps, and shows only establishments with:

- a Google rating of **4.7 or higher**, and
- **200 or more** Google user ratings.

Results are ranked by rating and review count, displayed as matching cards and
Folium map markers, and colored blue (4.7), purple (4.8), or gold (4.9–5.0).
Users can optionally enrich qualified places with Google review/place summaries
and recent reviews to identify candidate dishes and what each venue is known for.
Candidate dishes are displayed only when the same item is also found on an
accessible HTML or PDF menu reached from the venue website supplied by Google.

## Features

- Search restaurants, bars, or both before any paid business lookup is made.
- Filter the fetched shortlist locally by type, rating, review count, cuisine,
  price, open-now status, or a selected local date and time.
- Save places into named session collections and put an encoded collection into
  the browser URL for sharing. Opening a shared URL prefills the search but never
  triggers a paid request until the recipient submits it.
- Build a dinner-to-drinks pairing from qualifying venues and open walking
  directions through a free Google Maps URL.
- Open the authoritative venue website for reservation/ordering options, or use
  direct Google Maps place and directions links.
- Opt into menu-verified review recommendations only when wanted.

## Project layout

```text
app.py                         Streamlit orchestration and one-result cache
restaurant_finder/
  config.py                    Environment configuration
  places_client.py             Places API calls and pagination
  menu_verifier.py             Official-site menu discovery and dish verification
  map_tiles.py                 Google Map Tiles session handling
  service.py                   Filtering, deduplication, and ranking
  filters.py                   Local, zero-request result refinements
  itinerary.py                 Dinner/drinks pairing and Maps URL creation
  sharing.py                   Validated shareable collection tokens
  recommendations.py           Evidence-based dish phrase extraction
  models.py                    Typed models and rating colors
  ui.py                        Folium map and Streamlit card rendering
tests/                         Unit tests for filtering and pagination
```

## Google Cloud setup

1. Create or select a Google Cloud project and attach a billing account.
2. Enable **Places API (New)** and **Map Tiles API**. Optionally enable
   **Geocoding API** to reduce the cost of location-resolution requests.
3. Create API credentials. For local development, one key can serve both APIs.
   For production, use separate, appropriately restricted server and browser
   keys because Folium tile URLs are loaded by the browser.
4. Copy the environment template and add the key(s):

```bash
cp .env.example .env
```

```dotenv
GOOGLE_PLACES_API_KEY=your_server_key
GOOGLE_GEOCODING_API_KEY=your_optional_geocoding_key
GOOGLE_MAP_TILES_API_KEY=your_optional_tile_key
```

Never commit `.env`; it is already ignored.

## Run locally

Python 3.10 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

You can also use the portable launcher from any working directory:

```bash
python run.py
```

Open the local URL printed by Streamlit. The input defaults to `Manhattan, NYC`.
Searches begin only when **Find my shortlist** is pressed, which avoids an unintended
billable request on startup.

## Caching behavior

Area searches use a shared, normalized Streamlit data cache with up to 64 recent
queries and a 30-day ceiling. Case and whitespace variants share the same entry.
Place Details enrichment has a separate 1,024-entry cache keyed by Place ID, so
overlapping neighborhood searches reuse dish insights instead of buying them
again. The latest result is also kept in session state, so harmless UI reruns do
not call Google.

The Map Tiles session is cached for 13 days, just under Google's current
approximately two-week token lifetime. No results are written to disk.

To force a fresh API call during development, use Streamlit's app menu and select
**Clear cache**, or stop Streamlit and run:

```bash
streamlit cache clear
```

## Cost controls

- Menu-verified dish and drink picks are opt-in. A normal search skips Place
  Details Enterprise + Atmosphere requests; enabling picks adds at most one such
  request per strictly qualified venue, with results cached independently.
- **Thorough coverage** remains off by default because it can issue four times as
  many paginated restaurant/bar searches. Use it only when ordinary coverage is
  insufficient in a dense or large area.
- Set `PLACES_API_MAX_PAGES` to a positive number for a hard per-category page
  ceiling. Keep `0` only when exhaustive pagination is more important than a
  predictable ceiling.
- Supplying `GOOGLE_GEOCODING_API_KEY` switches location resolution from Places
  Text Search Pro to the less expensive Geocoding Essentials SKU. Use a key
  restricted to Geocoding API; if omitted, the app keeps the existing Places-only
  behavior.
- Configure daily API quotas and a Cloud Billing budget alert in Google Cloud.
  Budget alerts notify you but do not automatically cap spending; API quotas are
  the hard guardrail.
- Choosing **Restaurants only** or **Bars only** skips the other category sweep,
  reducing the ordinary two-category search request count.

## Tests

The tests do not call Google:

```bash
pytest -q
```

## Notes

- Text Search permits one `includedType` per request, so restaurants and bars are
  swept separately with `strictTypeFiltering=true`, then deduplicated by Place ID.
- Each input is first resolved to Google's geographic center and viewport. The
  farthest viewport corner determines a logical radius (clamped to 1.5–25 km).
  Business queries use the viewport as a hard API restriction, followed by an
  exact Haversine radius check locally, so adjacent towns do not leak in.
- Inputs Google classifies as a neighborhood—or as a sufficiently small
  sublocality—switch to walkable mode. The search rectangle is clipped around
  the center and results are capped at a 1.2 km straight-line radius, roughly a
  maximum 15-minute walk at an ordinary pace. Smaller provider viewports produce
  a tighter walk time; the UI labels and draws the effective boundary.
- Google only accepts `minRating` in 0.5 increments. The API query uses 4.5 to
  reduce noise, and the exact `rating >= 4.7` rule is enforced locally.
- When menu picks are enabled, Place Details requests are made only for
  establishments that already pass the rating, review-count, viewport, and radius
  filters. Candidate dishes are extracted only from explicit recommendation/menu
  cues in Google's review-derived content.
  The venue website returned by Place Details is then checked for linked HTML and
  PDF menus; only exact or same-line normalized menu matches become dish chips.
  If a menu is inaccessible, dynamically rendered, or has no match, the UI withholds
  the recommendation and explains why instead of implying certainty.
- Review and place summaries use the Place Details Enterprise + Atmosphere SKU.
  The UI preserves Google's reviews link, Gemini disclosure, and reporting link.
- With `PLACES_API_MAX_PAGES=0` (the default), every `nextPageToken` returned by
  Google is followed. Set a positive value only if you intentionally want a cost
  guard per place type.
- The optional **Thorough coverage** control divides the resolved viewport into
  four cells and searches both types in every cell. It improves discovery in
  larger/dense areas where a single query hits Google's result cap, but can use
  up to four times as many billable search requests. Overlaps are deduplicated.
- Category filters and rating/review/name sorting operate only on the active
  result set and never issue another paid API call.
- Opening hours, authoritative websites, and Google Maps action links are fetched
  in the existing Text Search response. Because rating and review-count fields
  already require the Enterprise tier, these additions do not raise its highest
  Text Search SKU.
- Open-now and selected-time filters are calculated locally from the venue's
  regular weekly hours and IANA time zone. They do not trigger follow-up requests;
  holiday hours and exceptional closures can differ from the displayed status.
- Personal collections live in Streamlit session state. A share token preserves
  the selected Place IDs, search location, and category scope without exposing API
  credentials or automatically issuing a recipient-side search.
- Menu verification is a point-in-time check of public online pages. Menus can
  change, and some JavaScript-only or image-only menus cannot be verified.
- Google Places content may not be shown with a non-Google basemap. This project
  therefore uses official Google roadmap tiles inside Folium instead of Folium's
  default OpenStreetMap layer and includes Google Maps attribution.
