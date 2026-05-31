# Houston Income Heatmap

Interactive choropleth map of median household income by census tract,
clipped to Houston city limits.

## Setup

Install dependencies (Python 3.9+):

```bash
pip install requests pandas geopandas folium branca shapely pyogrio
```

## Run

```bash
python scripts/build_houston_income_map.py
```

## Output

- **`output/houston_income_map.html`** — standalone interactive map; open in any browser

Optional debug output:

- `data/processed/houston_tracts_income.geojson` — joined tract + income GeoJSON

## Data sources

| Source | Description |
| -------- | ------------- |
| U.S. Census ACS 5-year API (`B19013_001E`) | Tract-level median household income |
| TIGER/Line `tl_2025_48_tract` (local) | Texas census tract geometry |
| TIGER/Line `tl_2024_48_place` (downloaded at runtime) | Houston city boundary polygon |

## Known limitations

- Requires internet access to fetch the ACS API response and Houston boundary.
- ACS 5-year estimates have a margin of error; tract-level values are estimates, not exact counts.
- Tracts where income data is suppressed by the Census Bureau display as gray ("No data").
- The Houston boundary reflects the city limits at the time of the 2024 TIGER/Line release.
