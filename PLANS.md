# Houston Market Opportunity Map — PLANS

## Purpose

Build a Houston-focused, shareable market opportunity map that helps local businesses decide **where to market, why an area is attractive, and what to do next**.

The product should move beyond a normal income heatmap and become a practical decision-support tool for:

- local business owners,
- consultants,
- marketers,
- and portfolio/demo use.

## Product vision

The application should let a user:

1. View a Houston-area map by tract or neighborhood.
2. See an **Opportunity Score** for each area.
3. Understand the **visible criteria** behind that score.
4. Read a plain-English explanation of **why** the score was earned.
5. Get a direct **marketing and distribution plan** for that area.
6. Later incorporate Houston-specific layers such as flood risk and serviceability.

## Core product principles

- The score must be **transparent**, not a black box.
- Every score must show named criteria, weights, and sub-scores.
- Every score must generate a human-readable explanation.
- Every explanation must lead to a concrete action plan.
- The MVP should be useful before the full data stack is complete.
- Public sharing should be easy; the output should be hostable as a static app.

## Primary users

### 1. Houston business owners

Need help deciding:

- where to advertise,
- where to expand,
- which neighborhoods match their customer profile,
- and what channels to use.

### 2. Consultant / strategist use

Used as a consulting deliverable for local market analysis, lead generation, and growth recommendations.

### 3. Portfolio / student showcase use

Demonstrates geospatial work, data processing, scoring logic, business thinking, and product design.

## v1 scope

Goal: produce a working interactive map MVP.

### v1 features

- Tract-level Houston/Harris County map.
- Income-based choropleth using a Spectral palette.
- Labeled basemap so city/town names are visible.
- Tooltips with tract name / GEOID / core metrics.
- Clean static output that can be shared publicly.

### v1 data

- Census tract geometry from TIGER/Line shapefiles.
- Income and related demographic data from an open downloadable source or build-time API process.

### v1 deliverable

- Standalone HTML map.

## v2 scope

Goal: evolve the map into an explainable scoring tool.

### v2 features

- Opportunity Score for each tract.
- Visible score criteria and weights.
- Sub-score breakdown by criterion.
- Plain-English explanation for why the tract scored as it did.
- Score band labels such as Excellent / Strong / Moderate / Weak / Poor.
- Action panel with direct marketing and distribution guidance.

### v2 scoring criteria

Initial criteria should be transparent and modular:

- Income fit
- Audience fit
- Market size
- Competition gap (placeholder if real data is not yet available)
- Serviceability / reach (placeholder if real data is not yet available)

Each criterion should produce a normalized 0–100 score.
The final score should be a weighted aggregate.

### v2 recommendation output

For each selected tract, generate:

- Who to target
- Why this area matters
- Recommended channels
- Message angle
- Offer idea
- Distribution approach
- 30-day action plan

## v3 scope

Goal: make the tool locally differentiated and commercially stronger.

### v3 Houston-specific additions

- Flood risk overlay
- Service radius / drive-time logic
- Neighborhood profile cards
- Area comparison mode
- Exportable opportunity brief

### v3 business-specific presets

Preset scoring for categories such as:

- tutoring,
- dentistry / med spa,
- real estate,
- home services,
- boutique local businesses.

## Data strategy

## Current strategy

Prefer open or build-time-acquired data so the public-facing product is easy to share.

### Data sources by need

- Geometry: TIGER/Line tract shapefiles
- Demographics: open downloadable ACS-derived sources or Census build-time pipeline
- Houston-specific risk layer: flood-related open data when added
- Competitor data: future business directory or curated dataset

### Sharing strategy

The app should not depend on end users making live API calls.
Preferred model:

1. Fetch or download data at build time.
2. Precompute scores and explanations.
3. Publish a static HTML/JS app or self-contained output.

## Product flow

The application should follow this sequence:

1. User chooses a business type or default mode.
2. User clicks a tract / area.
3. App shows the Opportunity Score.
4. App shows visible score breakdown.
5. App explains the score in plain language.
6. App generates a direct marketing and distribution plan.

## UX requirements

- Map must stay readable and labeled.
- Score must be visually prominent.
- Criteria must be easy to inspect.
- Explanation must be concise and understandable.
- Action plan must be direct and practical.
- UI should favor clarity over excessive visual complexity.

## Technical direction

### Suggested stack

- Python for data prep and scoring
- pandas / geopandas for joins and transformations
- Folium or a lightweight web map output for MVP
- Static HTML export for easy sharing

### Code architecture

The codebase should be modular and readable.
Suggested modules/functions:

- data loading
- geometry loading
- score normalization
- score calculation
- explanation generation
- recommendation generation
- map rendering
- export

## Documentation approach

Use:

- `CLAUDE.md` for persistent project instructions
- `PLAN.md` for product and implementation roadmap
- `TASKS.md` for current execution checklist

Do not create novelty context files like `soul.md` or `body.md` unless there is a very specific, justified workflow need.

## Success criteria

The project is successful when:

- a Houston user can open the map and quickly understand it,
- each area has a clear score,
- the score is visibly explained,
- the output includes actionable marketing guidance,
- and the tool feels like a real business decision aid rather than a generic map demo.

## Near-term priorities

1. Finish a working shareable map MVP.
2. Add transparent scoring logic.
3. Add explanation generation.
4. Add direct marketing/distribution recommendations.
5. Add Houston-specific risk and reach layers.
