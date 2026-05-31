"""
scripts/build_houston_income_map.py

Fetches ACS 5-year median household income data for Harris County census tracts,
clips to Houston city limits, and renders an interactive choropleth map.

Output: output/houston_income_map.html

Run:
    python scripts/build_houston_income_map.py
"""

import io
import json
import os
import tempfile
import zipfile

import branca.colormap as cm
import folium
import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACS_API_URL = "https://api.census.gov/data/2024/acs/acs5"
INCOME_FIELD = "B19013_001E"       # ACS field: median household income
CENSUS_NULL_SENTINEL = -666666666  # Census API integer for suppressed/unavailable values

STATE_FIPS = "48"    # Texas
COUNTY_FIPS = "201"  # Harris County

# Houston's TIGER/Line place FIPS code (City of Houston, TX)
HOUSTON_PLACE_FP = "35000"

# Texas places shapefile from Census TIGER/Line (~5 MB download)
TX_PLACES_URL = "https://www2.census.gov/geo/tiger/TIGER2024/PLACE/tl_2024_48_place.zip"

# Paths relative to project root (this script lives one level below root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TRACT_SHAPEFILE = os.path.join(
    _PROJECT_ROOT, "data", "TIGER_shape_files",
    "tl_2025_48_tract", "tl_2025_48_tract.shp",
)
PROCESSED_DIR = os.path.join(_PROJECT_ROOT, "data", "processed")
# public/index.html is the Vercel-deployable output. Vercel serves the public/
# directory as a static site automatically — no build command needed.
OUTPUT_PATH = os.path.join(_PROJECT_ROOT, "public", "index.html")

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

# Map visual settings
MAP_TILES = "CartoDB Positron"  # Labeled basemap; city/neighborhood names stay visible
FILL_OPACITY = 0.65             # Semi-transparent so basemap labels show through
BORDER_COLOR = "#999999"
BORDER_WEIGHT = 0.5


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_acs_income_data():
    """
    Query the Census ACS 5-year API for tract-level median household income
    in Harris County, Texas.

    The API returns a JSON array where the first element is the column header
    row and each subsequent element is a data row. We zip them into dicts.

    The Census API uses multiple `in=` parameters to specify the geography
    hierarchy (state, then county). Passing them as a list of tuples ensures
    requests serializes them as separate URL parameters.

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

    # List of tuples preserves duplicate parameter names (two separate `in=` values)
    params = [
        ("get", f"NAME,{INCOME_FIELD}"),
        ("for", "tract:*"),
        ("in", f"state:{STATE_FIPS}"),
        ("in", f"county:{COUNTY_FIPS}"),
        ("key", CENSUS_API_KEY),
    ]

    print("  Querying Census ACS 5-year API for Harris County tract income ...")
    response = requests.get(ACS_API_URL, params=params, timeout=30)
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
    Load Census TIGER/Line tract geometry from the local shapefile, filtered
    to Harris County.

    The shapefile covers all of Texas (~5,000 tracts). Filtering immediately
    to Harris County (COUNTYFP == '201') keeps the spatial pipeline fast.

    The GEOID column in TIGER/Line is the 11-character string formed by
    concatenating STATEFP + COUNTYFP + TRACTCE (e.g. "48201001234").

    Returns:
        GeoDataFrame: Harris County census tracts in their native CRS (EPSG:4269).
    """
    print("  Reading Harris County tracts from local TIGER/Line shapefile ...")
    gdf = gpd.read_file(TRACT_SHAPEFILE)
    harris = gdf[gdf["COUNTYFP"] == COUNTY_FIPS].copy()
    print(f"  Loaded {len(harris)} Harris County tracts.")
    return harris


def load_houston_boundary():
    """
    Download the Texas places TIGER/Line shapefile and extract the Houston
    city limits polygon.

    We download to memory, unzip to a temp directory, read with GeoPandas,
    then filter to Houston (PLACEFP == '35000'). The temp directory is
    cleaned up automatically after the read.

    The shapefile uses EPSG:4269 (NAD83); callers handle reprojection.

    Returns:
        GeoDataFrame: Single-row GeoDataFrame for the City of Houston.

    Raises:
        ValueError: If Houston is not found in the downloaded places file.
    """
    print("  Downloading Texas places shapefile from Census TIGER/Line (~5 MB) ...")
    response = requests.get(TX_PLACES_URL, timeout=120)
    response.raise_for_status()

    zip_bytes = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_bytes) as zf:
        with tempfile.TemporaryDirectory() as tmpdir:
            zf.extractall(tmpdir)
            shp_path = os.path.join(tmpdir, "tl_2024_48_place.shp")
            all_places = gpd.read_file(shp_path)

    houston = all_places[all_places["PLACEFP"] == HOUSTON_PLACE_FP].copy()
    if houston.empty:
        raise ValueError(
            f"Houston (PLACEFP='{HOUSTON_PLACE_FP}') not found in the Texas places file. "
            f"Source URL: {TX_PLACES_URL}"
        )

    print(f"  Loaded city boundary for: {houston.iloc[0]['NAME']}")
    return houston


# ---------------------------------------------------------------------------
# Spatial processing
# ---------------------------------------------------------------------------

def clip_tracts_to_houston(harris_tracts, houston_boundary):
    """
    Clip Harris County census tracts to the Houston city limits polygon.

    Spatial clip operations require a projected CRS (in meters) to correctly
    handle boundary edges and thin slivers. We reproject both layers to
    EPSG:3857 (Web Mercator) for the clip, then return the result in WGS84
    (EPSG:4326) because Folium requires longitude/latitude coordinates.

    Tracts that partially overlap the Houston boundary have their geometry
    trimmed to the city edge; fully interior tracts are kept whole.

    Args:
        harris_tracts (GeoDataFrame): Harris County tracts in any CRS.
        houston_boundary (GeoDataFrame): Houston city limits polygon in any CRS.

    Returns:
        GeoDataFrame: Tracts clipped to Houston in EPSG:4326.
    """
    print("  Reprojecting to EPSG:3857 and clipping tracts to Houston city limits ...")

    tracts_proj = harris_tracts.to_crs("EPSG:3857")
    houston_proj = houston_boundary.to_crs("EPSG:3857")

    # Houston's city boundary polygon has interior holes where independent
    # incorporated enclaves (Bellaire, West University Place) are located.
    # A strict clip would drop any tract entirely within those holes.
    # We fill the holes first so enclave tracts are kept in the output.
    houston_filled = _fill_polygon_holes(houston_proj.geometry.iloc[0])
    houston_mask = gpd.GeoDataFrame(geometry=[houston_filled], crs=houston_proj.crs)

    clipped = gpd.clip(tracts_proj, houston_mask)
    clipped_wgs84 = clipped.to_crs("EPSG:4326")

    # Clipping at the city boundary produces GeometryCollections (when a tract
    # edge touches the boundary at only a point or line) and occasionally
    # degenerate LineString/Point results. Keep only valid polygon features.
    clipped_wgs84 = _normalize_geometry(clipped_wgs84)

    print(f"  {len(clipped_wgs84)} tracts remain within Houston area.")
    return clipped_wgs84


def _fill_polygon_holes(geom):
    """
    Remove all interior holes (rings) from a Polygon or MultiPolygon.

    Houston's TIGER/Line boundary has interior holes where independent
    incorporated enclaves (Bellaire, West University Place) are located.
    Filling those holes before clipping ensures we keep tracts that fall
    entirely within the enclave areas.
    """
    if geom.geom_type == "Polygon":
        return Polygon(geom.exterior)
    if geom.geom_type == "MultiPolygon":
        return MultiPolygon([Polygon(p.exterior) for p in geom.geoms])
    return geom


def _normalize_geometry(gdf):
    """
    Ensure every feature has a clean Polygon or MultiPolygon geometry.

    geopandas.clip() can produce GeometryCollections (a mix of polygon,
    line, and point components) when a tract edge only touches the clip
    boundary at a line or point. It can also produce pure LineString or
    Point results in rare edge cases. Both break Folium tooltips and
    choropleth rendering, so we extract only the polygon parts and drop
    any feature with no polygon area.
    """
    def extract_polygons(geom):
        if geom is None or geom.is_empty:
            return None
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            return geom
        if geom.geom_type == "GeometryCollection":
            poly_parts = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
            if not poly_parts:
                return None
            return unary_union(poly_parts)
        # LineString, Point, and other non-area geometry types have no fill;
        # they are degenerate clip artifacts and should be dropped.
        return None

    result = gdf.copy()
    result["geometry"] = result["geometry"].apply(extract_polygons)
    return result[result["geometry"].notna()].reset_index(drop=True)


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
    Join ACS income data to Houston tract geometry by GEOID.

    The ACS API returns geography as three separate fields (state, county,
    tract). We concatenate them into an 11-character GEOID string — matching
    the GEOID column in the TIGER/Line shapefile — to perform the join.

    The Census API uses -666666666 as a sentinel for suppressed or
    unavailable estimates. We replace this with NaN so these tracts
    display as "No data" rather than incorrectly appearing at the bottom
    of the income color scale.

    Args:
        acs_rows (list[dict]): Raw rows from the ACS API response.
        houston_tracts (GeoDataFrame): Tracts clipped to Houston in EPSG:4326.

    Returns:
        GeoDataFrame: Houston tracts with 'income' (float), 'income_label'
                      (str), and 'tract_name' (str) columns. CRS: EPSG:4326.
    """
    income_df = pd.DataFrame(acs_rows)

    # Assemble 11-char GEOID: state(2) + county(3) + tract(6) characters
    income_df["GEOID"] = income_df["state"] + income_df["county"] + income_df["tract"]

    # Convert income to float; replace Census null sentinel with NaN
    income_df["income"] = pd.to_numeric(income_df[INCOME_FIELD], errors="coerce")
    income_df.loc[income_df["income"] == CENSUS_NULL_SENTINEL, "income"] = float("nan")

    income_df = income_df.rename(columns={"NAME": "tract_name"})

    # Left join: keeps all Houston tracts even if the ACS has no income value.
    # The join key must match exactly: both sides are 11-char zero-padded strings.
    merged = houston_tracts.merge(
        income_df[["GEOID", "tract_name", "income"]],
        on="GEOID",
        how="left",
    )

    # NAMELSAD ("Census Tract 3508.03") comes from the TIGER/Line shapefile and
    # is always present for every tract. Use it as the primary display name in
    # tooltips so the name is never missing, even when the ACS join doesn't match.
    merged["display_name"] = merged["NAMELSAD"].fillna(merged["NAME"]).fillna("Unknown tract")

    # Pre-format income as a currency string for use in map tooltips
    merged["income_label"] = merged["income"].apply(_format_income)

    n_missing = merged["income"].isna().sum()
    if n_missing > 0:
        print(f"  Note: {n_missing} tract(s) have no income data (shown in gray).")

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
    - Gray fill (#cccccc): tracts with no income data are shown neutrally
      rather than at the bottom of the income color scale.

    Args:
        income_gdf (GeoDataFrame): Merged Houston tracts + income in EPSG:4326.

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
        fill_color = colormap(income) if income is not None else "#cccccc"
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
        tooltip=tooltip,
    ).add_to(m)

    # Attach the Spectral color legend bar to the map
    colormap.add_to(m)

    # Zoom the initial view to fit all Houston tracts
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
    print(f"  Saved: {OUTPUT_PATH}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """
    Orchestrate the full data pipeline from API call to HTML output.

    Steps:
        1. Fetch ACS median household income for Harris County tracts
        2. Load Harris County tract geometry from the local TIGER/Line shapefile
        3. Download Houston city boundary from the Census TIGER/Line places file
        4. Clip Harris County tracts to Houston city limits
        5. Join income data to tract geometry by GEOID
        6. Build the interactive Folium choropleth map
        7. Save the HTML map and a debug GeoJSON
    """
    print("=== Houston Income Heatmap Builder ===\n")

    print("[1/7] Fetching ACS income data ...")
    acs_rows = fetch_acs_income_data()
    print(f"      Received {len(acs_rows)} tract rows from the Census API.\n")

    print("[2/7] Loading Harris County tract geometry ...")
    harris_tracts = load_tract_geometries()
    print()

    print("[3/7] Loading Houston city boundary ...")
    houston_boundary = load_houston_boundary()
    print()

    print("[4/7] Clipping tracts to Houston city limits ...")
    houston_tracts = clip_tracts_to_houston(harris_tracts, houston_boundary)
    print()

    print("[5/7] Joining income data to tract geometry ...")
    income_gdf = prepare_income_geodataframe(acs_rows, houston_tracts)
    print(f"      Final dataset: {len(income_gdf)} Houston tracts.\n")

    print("[6/7] Building Folium map ...")
    folium_map = build_income_map(income_gdf)
    print()

    print("[7/7] Saving output ...")
    save_map(folium_map)

    # Save a processed GeoJSON for debugging / inspection in QGIS or similar
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    processed_path = os.path.join(PROCESSED_DIR, "houston_tracts_income.geojson")
    income_gdf.to_file(processed_path, driver="GeoJSON")
    print(f"  Debug GeoJSON: {processed_path}")

    print("\n=== Done! ===")
    print(f"Open in a browser: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
