# Houston Income Heatmap

## Project overview

This project builds an interactive Houston income heatmap as a standalone HTML map.

The map must:

- Show Houston-area census tracts colored by median household income.
- Use a Spectral color palette.
- Show city/town/place labels on the basemap.
- Export to a single shareable HTML file in `output/`.
- Be built in Python using GeoPandas and Folium.

Primary output:

- `output/houston_income_map.html`

## Goal

Produce a clean, readable, well-structured geospatial pipeline that:

1. Fetches ACS 5-year median household income data by census tract.
2. Loads tract geometry.
3. Loads Houston city boundary geometry.
4. Clips tracts to Houston city limits.
5. Joins income data to tract geometry by GEOID.
6. Renders an interactive choropleth map with hover tooltips.
7. Saves the final result to HTML.

## Tech stack

- Python
- pandas
- geopandas
- requests
- folium
- branca
- shapely
- pyogrio or fiona

## Directory structure

- `scripts/` → Python scripts
- `data/raw/` → downloaded source files
- `data/processed/` → cleaned intermediate outputs
- `output/` → final HTML map
- `README.md` → setup and usage notes

Preferred main script:

- `scripts/build_houston_income_map.py`

## Data sources

Use these data sources unless explicitly told otherwise:

1. U.S. Census ACS 5-year API for tract-level median household income.
   - Use field `B19013_001E`.
2. Census TIGER/Line tract geometry.
3. Houston city boundary geometry.
4. A labeled basemap tile layer in Folium so city/town/place names are visible.

## Map requirements

The map must:

- Be centered on Houston.
- Use a labeled tile layer such as `CartoDB Positron` or equivalent readable labeled tiles.
- Use a Spectral palette for the choropleth.
- Include a legend.
- Include hover tooltips with at minimum:
  - tract GEOID
  - median household income
- Use readable formatting for currency values.
- Fit bounds to the resulting Houston geometry.
- Save as a standalone HTML file.

## Geography rules

- Default geography is census tract, not ZIP code.
- Clip to Houston city limits, not just Harris County.
- Use consistent CRS before spatial operations.
- Prefer the cleanest accurate implementation over clever shortcuts.

## Code quality rules

Code must be written for clarity first.

Required:

- Use small, well-named functions.
- Add necessary comments explaining non-obvious logic, spatial operations, API assumptions, and mapping choices.
- Add light abstraction for clarity, not overengineering.
- Keep the main execution flow easy to read from top to bottom.
- Use descriptive variable names; avoid one-letter names except simple loop indices.
- Separate data fetching, cleaning, spatial processing, styling, and export steps into distinct functions.
- Include docstrings for public/helper functions.
- Handle expected failure cases with clear error messages.

Do not:

- Write everything in one giant script block.
- Add unnecessary complexity, classes, or premature architecture.
- Hide important logic inside vague helper names.
- Use magic constants without naming them.

## Suggested function breakdown

Use a structure close to this unless there is a strong reason not to:

- `fetch_acs_income_data()`
- `load_tract_geometries()`
- `load_houston_boundary()`
- `clip_tracts_to_houston()`
- `prepare_income_geodataframe()`
- `build_income_map()`
- `save_map()`
- `main()`

## Tooltip and styling rules

- Tooltips should be implemented cleanly and reliably.
- Show formatted income values.
- Use a sensible line weight and polygon opacity so the basemap labels remain visible.
- Make high-income vs low-income areas visually distinct without making the map muddy.
- Spectral palette should be applied intentionally and consistently.

## Comments and abstraction

This project explicitly requires:

- necessary comments for code clarity
- clear function boundaries / abstraction
- explanation of any tricky geospatial join, clip, CRS conversion, or Folium styling logic

Comments should explain:

- why a step exists
- what assumptions are being made
- anything a future maintainer could trip over

Do not add noisy comments that repeat obvious code.

## Output rules

Always produce:

- `output/houston_income_map.html`

Prefer also producing:

- a processed GeoJSON or GeoPackage in `data/processed/` if it makes debugging easier

## Validation checklist

Before finishing, verify:

- The script runs end-to-end.
- The final HTML file is created.
- The map opens correctly.
- Houston is the focus, not the entire county/state.
- City/town labels are visible on the basemap.
- Tooltips work on hover.
- The legend is present.
- The Spectral palette is applied.
- No obvious CRS mismatch or broken geometry issues remain.

## Workflow expectations

When implementing:

1. Inspect the repository structure first.
2. Reuse existing folders if already present.
3. Explain the plan briefly before major edits.
4. Make incremental changes.
5. After coding, summarize:
   - what was built
   - files created/changed
   - any assumptions
   - any data source decisions
   - how to run the script

## README expectations

If `README.md` is missing or minimal, add/update it with:

- project purpose
- setup
- run command
- output path
- data sources
- known limitations

## Decision preference

When there are multiple valid choices, prefer:

1. readability
2. reliability
3. simple geospatial pipeline
4. maintainability
5. visual polish
