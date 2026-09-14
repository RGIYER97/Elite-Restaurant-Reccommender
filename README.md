# The Shortlist

A Streamlit app that resolves an entered town/neighborhood/postal code, searches
Google Places inside a user-selected radius from that location, follows every
returned page, deduplicates overlaps, and shows only establishments with:

- a Google rating of **4.7 or higher**, and
- at least the user-selected number of Google reviews (default: **200**).

Results are ranked by rating and review count, displayed as matching cards and
Folium map markers, and colored blue (4.7), purple (4.8), or gold (4.9–5.0).
Users can optionally enrich up to ten qualified places with Google review/place
summaries describing what each venue is known for.

## Features

- Search restaurants, bars, or both before any paid business lookup is made.
- Set the qualifying review count and a 0.25–25 mile radius from the resolved
  location center before searching.
- Filter the fetched shortlist locally by type, rating, review count, cuisine,
  price, open-now status, or a selected local date and time.
- Save places into named session collections and put an encoded collection into
  the browser URL for sharing. Opening a shared URL prefills the search but never
  triggers a paid request until the recipient submits it.
- Build a dinner-to-drinks pairing from qualifying venues and open walking
  directions through a free Google Maps URL.
- Open the authoritative venue website for reservation/ordering options, or use
  direct Google Maps place and directions links.
- Opt into Google review summaries only when wanted.
- Rate-limit repeated, thorough, and enriched searches per connection before a
  cached or paid lookup is attempted.
- Restrict all server-originated HTTP to Google Places and Google Map Tiles.

## Project layout

```text
app.py                         Streamlit orchestration and one-result cache
restaurant_finder/
  config.py                    Environment configuration
  places_client.py             Places API calls and pagination
  map_tiles.py                 Google Map Tiles session handling
  rate_limiter.py              Process-wide sliding-window abuse limits
  service.py                   Filtering, deduplication, and ranking
  filters.py                   Local, zero-request result refinements
  itinerary.py                 Dinner/drinks pairing and Maps URL creation
  sharing.py                   Validated shareable collection tokens
  models.py                    Typed models and rating colors
  ui.py                        Folium map and Streamlit card rendering
tests/                         Unit tests for filtering and pagination
```

## Google Cloud setup

1. Create or select a Google Cloud project and attach a billing account.
2. Enable **Places API (New)** and **Map Tiles API** only.
3. Create API credentials. For local development, one key can serve both APIs.
   For production, use separate, appropriately restricted server and browser
   keys because Folium tile URLs are loaded by the browser.
4. Copy the environment template and add the key(s):

```bash
cp .env.example .env
```

```dotenv
GOOGLE_PLACES_API_KEY=your_server_key
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
overlapping neighborhood searches reuse review insights instead of buying them
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

- Google review insights are opt-in. A normal search skips Place Details
  Enterprise + Atmosphere requests; enabling insights adds at most ten such
  requests per search, with results cached independently by Place ID.
- Each connection is limited to 3 searches per minute and 20 per rolling day.
  Thorough and insight-enabled searches are each limited to 1 per 10 minutes and
  3 per rolling day. These lightweight counters are process-local, so production
  deployments with multiple replicas should also enforce limits at the edge.
- **Thorough coverage** remains off by default because it can issue four times as
  many paginated restaurant/bar searches. Use it only when ordinary coverage is
  insufficient in a dense or large area.
- The default per-category page ceiling is 3 (Google's full 60-result query
  window). Set `PLACES_API_MAX_PAGES=0` only
  when exhaustive pagination is intentionally preferred over predictable spend.
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
- Each input is first resolved to Google's geographic center. The selected mile
  radius becomes a rectangular API restriction around that center, followed by
  an exact Haversine distance check locally. The UI labels and draws the same
  effective circular boundary shown on the map.
- Google only accepts `minRating` in 0.5 increments. The API query uses 4.5 to
  reduce noise, and the exact `rating >= 4.7` rule is enforced locally.
- When review insights are enabled, Place Details requests are made only for the
  first ten establishments that already pass the rating, review-count, viewport,
  and radius filters. The server never fetches their websites or menu documents.
- Review and place summaries use the Place Details Enterprise + Atmosphere SKU.
  The UI preserves Google's reviews link, Gemini disclosure, and reporting link.
- With `PLACES_API_MAX_PAGES=3` (the default), each area/category sweep covers
  Google's full 60-result query window. The UI warns when a lower configured
  ceiling stops while another page token remains. Setting it to `0` follows
  every `nextPageToken` returned by Google.
- The optional **Thorough coverage** control divides the selected search area into
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
- A hostname allowlist in the shared HTTP client blocks accidental server-side
  calls outside `places.googleapis.com` and `tile.googleapis.com`. Google Maps,
  directions, and official-site links are opened by the user's browser.
- Google Places content may not be shown with a non-Google basemap. This project
  therefore uses official Google roadmap tiles inside Folium instead of Folium's
  default OpenStreetMap layer and includes Google Maps attribution.
