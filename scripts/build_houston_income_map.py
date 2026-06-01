"""
scripts/build_houston_income_map.py

Fetches ACS 5-year median household income data for Texas census tracts,
selects every tract that intersects the Houston study region (the City of
Houston plus the incorporated places that touch it — Pasadena, Bellaire, South
Houston, the enclaves, etc.), and renders an interactive choropleth map.

Output: public/index.html  (served as-is by Vercel's static `public/` directory)

Geometry strategy (the important part)
--------------------------------------
The earlier version restricted tracts to Harris County and *clipped* them to the
City of Houston boundary. That dropped valid areas two ways:

  * Harris-only + a City-of-Houston clip excludes neighbouring cities like
    Pasadena (a separate municipality) and shaves edge tracts to the city line.
  * Clipping can also produce empty/degenerate slivers that fall out entirely.

This version replaces the clip with intersection-based *selection*:

  * SELECT, don't clip. Any tract that intersects the study region is kept as a
    WHOLE tract — edge tracts (the Pasadena side, the ship channel, the western
    suburbs) are retained intact, not trimmed.
  * The income join stays a LEFT join, so tracts the Census reports no income
    for keep their geometry and render in a neutral gray "No data" colour.

Every stage logs its row count, the GEOIDs it drops, and its bounding box to
data/processed/build_log.txt so the geometry funnel is auditable.

Run:
    python scripts/build_houston_income_map.py
"""

import io
import json
import os
import tempfile
import zipfile
from datetime import datetime

import branca.colormap as cm
import folium
import geopandas as gpd
import pandas as pd
import requests
from shapely import make_valid
from shapely.ops import unary_union

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACS_API_URL = "https://api.census.gov/data/2024/acs/acs5"
INCOME_FIELD = "B19013_001E"       # ACS field: median household income
CENSUS_NULL_SENTINEL = -666666666  # Census API integer for suppressed/unavailable values

STATE_FIPS = "48"    # Texas

# Houston's TIGER/Line place FIPS code (City of Houston, TX). We grow the study
# region outward from this place by unioning in every place that touches it.
HOUSTON_PLACE_FP = "35000"

# Texas places shapefile from Census TIGER/Line (~5 MB download)
TX_PLACES_URL = "https://www2.census.gov/geo/tiger/TIGER2024/PLACE/tl_2024_48_place.zip"
TX_PLACES_SHP_NAME = "tl_2024_48_place.shp"

# Paths relative to project root (this script lives one level below root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TRACT_SHAPEFILE = os.path.join(
    _PROJECT_ROOT, "data", "TIGER_shape_files",
    "tl_2025_48_tract", "tl_2025_48_tract.shp",
)
PROCESSED_DIR = os.path.join(_PROJECT_ROOT, "data", "processed")
LOG_PATH = os.path.join(PROCESSED_DIR, "build_log.txt")
# public/index.html is the Vercel-deployable output. Vercel serves the public/
# directory as a static site automatically — no build command needed.
OUTPUT_PATH = os.path.join(_PROJECT_ROOT, "public", "index.html")

# Coordinate reference systems.
#   - TIGER/Line ships in EPSG:4269 (NAD83 geographic).
#   - EPSG:5070 (USA Contiguous Albers Equal Area) is used for spatial
#     predicates so intersection tests are numerically robust.
#   - EPSG:4326 (WGS84 lat/lon) is the final CRS because Folium requires it.
CRS_WGS84 = "EPSG:4326"
CRS_EQUAL_AREA = "EPSG:5070"

# Map visual settings
MAP_TILES = "CartoDB Positron"  # Labeled basemap; city/neighborhood names stay visible
FILL_OPACITY = 0.65             # Semi-transparent so basemap labels show through
BORDER_COLOR = "#999999"
BORDER_WEIGHT = 0.5
NO_DATA_COLOR = "#cccccc"       # Neutral gray for tracts with no income estimate

# Census API key — required as of 2025. Set via environment variable or a .env file
# in the project root. Get a free key at: https://api.census.gov/data/key_signup.html
def _load_census_api_key():
    """Read CENSUS_API_KEY from the environment, or fall back to a .env file."""
    key = os.environ.get("CENSUS_API_KEY", "")
    if key:
        return key.strip().strip('"').strip("'")

    env_path = os.path.join(_PROJECT_ROOT, ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("CENSUS_API_KEY"):
                    _, _, value = line.partition("=")
                    return value.strip().strip('"').strip("'")
    return ""

CENSUS_API_KEY = _load_census_api_key()


# ---------------------------------------------------------------------------
# Logging — buffered to build_log.txt so the geometry funnel is auditable even
# when the terminal truncates output.
# ---------------------------------------------------------------------------

_log_lines = []


def log(message):
    """Record an audit line to both stdout and the build_log.txt buffer."""
    stamped = f"[{datetime.now():%H:%M:%S}] {message}"
    print(stamped)
    _log_lines.append(stamped)


def flush_log():
    """Write the accumulated audit trail to data/processed/build_log.txt."""
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(_log_lines) + "\n")


def log_bbox(gdf, label):
    """Log a layer's bounding box so extents can be compared across stages."""
    minx, miny, maxx, maxy = gdf.total_bounds
    log(f"bbox [{label}]: x[{minx:.4f}, {maxx:.4f}] y[{miny:.4f}, {maxy:.4f}]")


def repair_geometries(gdf, label):
    """Drop null geometries and repair invalid ones via make_valid.

    Invalid geometries (self-intersections, bow-ties) make spatial predicates
    return wrong or empty results — a subtle way tracts vanish. We fix them in
    place rather than dropping them.
    """
    null_count = int(gdf.geometry.isna().sum())
    if null_count:
        log(f"  {label}: dropping {null_count} null geometries")
        gdf = gdf[gdf.geometry.notna()].copy()

    invalid_mask = ~gdf.geometry.is_valid
    invalid_count = int(invalid_mask.sum())
    if invalid_count:
        log(f"  {label}: repairing {invalid_count} invalid geometries (make_valid)")
        gdf.loc[invalid_mask, "geometry"] = gdf.loc[invalid_mask, "geometry"].apply(
            make_valid
        )
    return gdf


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_acs_income_data():
    """
    Query the Census ACS 5-year API for tract-level median household income
    across all of Texas.

    We pull the whole state in one request (rather than a single county) because
    the Houston study region spans several counties; a statewide pull guarantees
    an income row for every tract we might select.

    The API returns a JSON array where the first element is the column header
    row and each subsequent element is a data row. We zip them into dicts.

    Returns:
        list[dict]: Each dict has keys NAME, B19013_001E, state, county, tract.
    """
    if not CENSUS_API_KEY:
        raise EnvironmentError(
            "Census API key not found. Set the CENSUS_API_KEY environment variable.\n"
            "  Get a free key at: https://api.census.gov/data/key_signup.html\n"
            "  Then run: set CENSUS_API_KEY=your_key_here  (Windows)\n"
            "          or export CENSUS_API_KEY=your_key_here  (Mac/Linux)"
        )

    params = [
        ("get", f"NAME,{INCOME_FIELD}"),
        ("for", "tract:*"),
        ("in", f"state:{STATE_FIPS}"),
        ("key", CENSUS_API_KEY),
    ]

    log("  Querying Census ACS 5-year API for Texas tract income ...")
    response = requests.get(ACS_API_URL, params=params, timeout=60)
    response.raise_for_status()

    # If the API returns HTML instead of JSON, the key may be invalid
    content_type = response.headers.get("Content-Type", "")
    if "html" in content_type:
        raise ValueError(
            f"Census API returned HTML instead of JSON. "
            f"Check that CENSUS_API_KEY is valid.\nResponse: {response.text[:300]}"
        )

    rows = response.json()  # [[header...], [row...], ...]
    header, data_rows = rows[0], rows[1:]
    return [dict(zip(header, row)) for row in data_rows]


def load_tract_geometries():
    """
    Load Census TIGER/Line tract geometry for all of Texas from the local
    shapefile, standardized to WGS84 and with geometries repaired.

    We deliberately do NOT pre-filter to a single county: the Houston study
    region spills into Fort Bend, Galveston, Montgomery and others, and a county
    filter is a common source of edge gaps. Spatial selection narrows it later.

    The GEOID column in TIGER/Line is the 11-character string formed by
    concatenating STATEFP + COUNTYFP + TRACTCE (e.g. "48201001234").

    Returns:
        GeoDataFrame: Texas census tracts in EPSG:4326.
    """
    log("  Reading Texas tracts from local TIGER/Line shapefile ...")
    gdf = gpd.read_file(TRACT_SHAPEFILE)
    log(f"  Raw tracts loaded (statewide): {len(gdf)} in CRS {gdf.crs}")

    gdf = gdf.to_crs(CRS_WGS84)
    gdf = repair_geometries(gdf, "tracts")
    return gdf


def load_houston_study_region():
    """
    Download the Texas places TIGER/Line shapefile and build the Houston study
    region: the City of Houston unioned with every incorporated place that
    touches it.

    Why "touching places" rather than just Houston: Pasadena and the inner-ring
    edge areas the map needs are *separate* incorporated cities, so a strict
    Houston-only boundary erases them. Including every place that touches Houston
    also captures the enclaves (Bellaire, West University Place, ...) that sit as
    holes inside Houston, filling what would otherwise be donut-shaped gaps.

    Returns:
        shapely geometry: the unioned study region in EPSG:4326.

    Raises:
        ValueError: If Houston is not found in the downloaded places file.
    """
    log("  Downloading Texas places shapefile from Census TIGER/Line (~5 MB) ...")
    response = requests.get(TX_PLACES_URL, timeout=120)
    response.raise_for_status()

    zip_bytes = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_bytes) as zf:
        with tempfile.TemporaryDirectory() as tmpdir:
            zf.extractall(tmpdir)
            all_places = gpd.read_file(os.path.join(tmpdir, TX_PLACES_SHP_NAME))

    all_places = all_places.to_crs(CRS_WGS84)
    all_places = repair_geometries(all_places, "places")

    houston = all_places[all_places["PLACEFP"] == HOUSTON_PLACE_FP]
    if houston.empty:
        raise ValueError(
            f"Houston (PLACEFP='{HOUSTON_PLACE_FP}') not found in the Texas places file. "
            f"Source URL: {TX_PLACES_URL}"
        )
    houston_geom = unary_union(houston.geometry.values)

    # Adjacent = any place whose geometry intersects Houston (a shared border
    # counts as touching). Intentionally inclusive.
    touching = all_places[all_places.geometry.intersects(houston_geom)]
    study_region = make_valid(unary_union(touching.geometry.values))

    names = sorted(touching["NAME"].unique().tolist())
    log(f"  Study region = Houston + {len(touching) - 1} touching places")
    log("  Contributing places: " + ", ".join(names))
    return study_region


# ---------------------------------------------------------------------------
# Spatial processing
# ---------------------------------------------------------------------------

def select_tracts_intersecting_region(tracts, study_region):
    """
    Keep every WHOLE tract that intersects the study region.

    This deliberately replaces gpd.clip: clipping cuts tracts along the region
    boundary and can drop tracts whose clipped piece becomes empty.
    Intersection-based selection keeps the full tract polygon, so edge tracts
    (e.g. on the Pasadena side) are retained intact.

    The predicate runs in an equal-area CRS for numerical robustness; the
    returned geometries are the untouched WGS84 originals.

    Args:
        tracts (GeoDataFrame): Texas tracts in EPSG:4326.
        study_region (shapely geometry): the Houston study region in EPSG:4326.

    Returns:
        GeoDataFrame: selected whole tracts in EPSG:4326.
    """
    log("  Selecting tracts that intersect the study region (whole tracts) ...")
    region_ea = gpd.GeoSeries([study_region], crs=CRS_WGS84).to_crs(CRS_EQUAL_AREA).iloc[0]
    tracts_ea = tracts.to_crs(CRS_EQUAL_AREA)

    mask = tracts_ea.geometry.intersects(region_ea)
    selected = tracts[mask.values].copy()  # keep the original WGS84 geometry

    dropped = sorted(set(tracts["GEOID"]) - set(selected["GEOID"]))
    log(f"  Tracts intersecting study region: {len(selected)} of {len(tracts)}")
    log(f"  Tracts excluded (outside region): {len(dropped)}")
    return selected


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def _format_income(value):
    """Format a numeric income value as a USD currency string, or return 'No data'."""
    if pd.isna(value):
        return "No data"
    return f"${value:,.0f}"


def prepare_income_geodataframe(acs_rows, houston_tracts):
    """
    Join ACS income data to the selected tract geometry by GEOID.

    The ACS API returns geography as three separate fields (state, county,
    tract). We concatenate them into an 11-character GEOID string — matching
    the GEOID column in the TIGER/Line shapefile — to perform the join.

    The Census API uses -666666666 as a sentinel for suppressed or
    unavailable estimates. We replace this with NaN so these tracts
    display as "No data" rather than incorrectly appearing at the bottom
    of the income color scale.

    Args:
        acs_rows (list[dict]): Raw rows from the ACS API response.
        houston_tracts (GeoDataFrame): Selected tracts in EPSG:4326.

    Returns:
        GeoDataFrame: tracts with 'income' (float), 'income_label' (str), and
                      'display_name' (str) columns. CRS: EPSG:4326.
    """
    income_df = pd.DataFrame(acs_rows)

    # Assemble 11-char GEOID: state(2) + county(3) + tract(6) characters
    income_df["GEOID"] = income_df["state"] + income_df["county"] + income_df["tract"]

    # Convert income to float; replace Census null sentinel with NaN
    income_df["income"] = pd.to_numeric(income_df[INCOME_FIELD], errors="coerce")
    income_df.loc[income_df["income"] == CENSUS_NULL_SENTINEL, "income"] = float("nan")

    income_df = income_df.rename(columns={"NAME": "acs_name"})

    # LEFT join: keeps every selected tract even when the ACS has no income value
    # for it. The join key must match exactly: both sides are 11-char strings.
    before = len(houston_tracts)
    merged = houston_tracts.merge(
        income_df[["GEOID", "acs_name", "income"]],
        on="GEOID",
        how="left",
    )
    assert len(merged) == before, "row count changed during join (duplicate GEOIDs?)"

    # NAMELSAD ("Census Tract 3508.03") comes from the TIGER/Line shapefile and
    # is always present for every tract. Use it as the primary display name in
    # tooltips so the name is never missing, even when the ACS join doesn't match.
    merged["display_name"] = merged["NAMELSAD"].fillna(merged["acs_name"]).fillna("Unknown tract")

    # Pre-format income as a currency string for use in map tooltips
    merged["income_label"] = merged["income"].apply(_format_income)

    n_missing = int(merged["income"].isna().sum())
    log(f"  Tracts after income join: {len(merged)} (kept all selected tracts)")
    log(f"  Tracts with no income (rendered gray 'No data'): {n_missing}")

    return merged


# ---------------------------------------------------------------------------
# Map building
# ---------------------------------------------------------------------------

def build_income_map(income_gdf):
    """
    Construct an interactive Folium choropleth map of median household income.

    Design choices:
    - CartoDB Positron: labeled basemap that keeps neighborhood and street
      names visible through the semi-transparent tract polygons.
    - Spectral_11 colormap: diverging red->yellow->green->blue palette scaled
      to the 5th-95th income percentile so a few extreme-income tracts don't
      compress the color range for the majority of Houston.
    - folium.GeoJson (not folium.Choropleth): gives full control over
      per-feature styling and GeoJsonTooltip, which Choropleth does not
      support as cleanly.
    - fillOpacity=0.65: keeps CartoDB city/neighborhood labels legible.
    - Gray fill: tracts with no income data are shown neutrally rather than at
      the bottom of the income color scale.

    Args:
        income_gdf (GeoDataFrame): Merged tracts + income in EPSG:4326.

    Returns:
        folium.Map: Completed map ready to save.
    """
    bounds = income_gdf.total_bounds  # [minx, miny, maxx, maxy] in longitude/latitude
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    m = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles=MAP_TILES)

    # Scale the Spectral colormap to the 5th-95th percentile of valid income values
    valid_incomes = income_gdf["income"].dropna()
    vmin = valid_incomes.quantile(0.05)
    vmax = valid_incomes.quantile(0.95)
    colormap = cm.linear.Spectral_11.scale(vmin, vmax)
    colormap.caption = "Median Household Income (USD)"

    # to_json() correctly converts pandas NaN to JSON null, avoiding serialization issues
    geojson_dict = json.loads(income_gdf.to_json())

    def style_function(feature):
        """Return Folium polygon fill and border styles for a single tract."""
        income = feature["properties"].get("income")
        # JSON null deserializes to Python None; show gray for missing income data
        fill_color = colormap(income) if income is not None else NO_DATA_COLOR
        return {
            "fillColor": fill_color,
            "color": BORDER_COLOR,
            "weight": BORDER_WEIGHT,
            "fillOpacity": FILL_OPACITY,
        }

    # display_name uses NAMELSAD from the shapefile — always present, never "Unknown".
    # GEOID and income_label are the two primary data fields shown on hover.
    tooltip = folium.GeoJsonTooltip(
        fields=["display_name", "GEOID", "income_label"],
        aliases=["Tract:", "GEOID:", "Median Income:"],
        localize=True,
        sticky=False,
        labels=True,
    )

    folium.GeoJson(
        geojson_dict,
        name="Median Household Income",
        style_function=style_function,
        highlight_function=lambda _f: {"weight": 2.0, "color": "#000000"},
        tooltip=tooltip,
    ).add_to(m)

    # Attach the Spectral color legend bar to the map
    colormap.add_to(m)

    # Zoom the initial view to fit all rendered tracts
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

    return m


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_map(folium_map):
    """
    Save the Folium map as a standalone HTML file at public/index.html.

    Vercel serves the public/ directory as a static site with no build
    command required. Committing this file is all that's needed to deploy.

    Args:
        folium_map (folium.Map): The completed map.
    """
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    folium_map.save(OUTPUT_PATH)
    log(f"  Saved: {OUTPUT_PATH}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """
    Orchestrate the full data pipeline from API call to HTML output.

    Steps:
        1. Fetch ACS median household income for all Texas tracts
        2. Load Texas tract geometry from the local TIGER/Line shapefile
        3. Build the Houston study region (Houston + touching places)
        4. Select tracts that intersect the study region (whole tracts)
        5. Join income data to tract geometry by GEOID (LEFT join)
        6. Build the interactive Folium choropleth map
        7. Save the HTML map and a debug GeoJSON
    """
    log("=== Houston Income Heatmap Builder ===")

    log("[1/7] Fetching ACS income data ...")
    acs_rows = fetch_acs_income_data()
    log(f"      Received {len(acs_rows)} tract rows from the Census API.")

    log("[2/7] Loading Texas tract geometry ...")
    tracts = load_tract_geometries()
    log_bbox(tracts, "all TX tracts")

    log("[3/7] Building Houston study region ...")
    study_region = load_houston_study_region()

    log("[4/7] Selecting tracts that intersect the study region ...")
    selected_tracts = select_tracts_intersecting_region(tracts, study_region)
    log_bbox(selected_tracts, "selected tracts")

    log("[5/7] Joining income data to tract geometry ...")
    income_gdf = prepare_income_geodataframe(acs_rows, selected_tracts)
    log(f"      Final dataset: {len(income_gdf)} tracts.")

    log("[6/7] Building Folium map ...")
    folium_map = build_income_map(income_gdf)

    log("[7/7] Saving output ...")
    save_map(folium_map)

    # Save a processed GeoJSON for debugging / inspection in QGIS or similar
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    processed_path = os.path.join(PROCESSED_DIR, "houston_tracts_income.geojson")
    income_gdf.to_file(processed_path, driver="GeoJSON")
    log(f"  Debug GeoJSON: {processed_path}")

    log("=== Done! ===")
    log(f"Open in a browser: {OUTPUT_PATH}")
    flush_log()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # make sure failures land in the log file too
        log(f"BUILD FAILED: {type(exc).__name__}: {exc}")
        flush_log()
        raise
