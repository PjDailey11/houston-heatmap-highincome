# Houston Market Opportunity Map — TASKS

## Current objective

Build a working MVP first, then evolve it into an explainable Houston market opportunity tool.

---

## Phase 1 — MVP map

### Setup

- [ ] Confirm project structure exists:
  - [ ] `CLAUDE.md`
  - [ ] `PLAN.md`
  - [ ] `TASKS.md`
  - [ ] `scripts/`
  - [ ] `data/raw/`
  - [ ] `data/processed/`
  - [ ] `output/`
- [ ] Confirm required Python libraries are installed.
- [ ] Place tract shapefile data in `data/raw/`.

### Data

- [ ] Confirm tract geometry source.
- [ ] Confirm demographic source for income and any related variables.
- [ ] Decide whether build-time data comes from downloadable files or a keyed API process.
- [ ] Document the chosen source in `README.md`.

### MVP implementation

- [ ] Load tract geometry.
- [ ] Load demographic data.
- [ ] Build/verify tract GEOID join.
- [ ] Merge data to geometry.
- [ ] Render map with labeled basemap.
- [ ] Apply Spectral palette.
- [ ] Add tooltip with tract details.
- [ ] Export standalone HTML map.

### MVP QA

- [ ] Confirm the map opens locally.
- [ ] Confirm labels are visible.
- [ ] Confirm polygons render correctly.
- [ ] Confirm no obvious CRS mismatch.
- [ ] Confirm output is shareable.

---

## Phase 2 — Explainable scoring v2

### Score design

- [ ] Finalize the first visible score criteria.
- [ ] Finalize initial weights.
- [ ] Define score bands:
  - [ ] Excellent
  - [ ] Strong
  - [ ] Moderate
  - [ ] Weak
  - [ ] Poor
- [ ] Define normalization method for each criterion.

### Criteria implementation

- [ ] Implement income fit score.
- [ ] Implement audience fit score.
- [ ] Implement market size score.
- [ ] Create placeholder structure for competition gap.
- [ ] Create placeholder structure for serviceability / reach.
- [ ] Compute weighted final score.

### Score explanation

- [ ] Generate top positive drivers.
- [ ] Generate top negative drivers.
- [ ] Generate plain-English explanation summary.
- [ ] Add confidence / limitation note when data is incomplete.

### Action plan generation

- [ ] Generate “who to target” output.
- [ ] Generate message angle.
- [ ] Generate recommended channels.
- [ ] Generate offer suggestion.
- [ ] Generate distribution approach.
- [ ] Generate 30-day action plan.

### UI / output

- [ ] Decide where score, explanation, and plan are displayed:
  - [ ] popup
  - [ ] custom side panel
  - [ ] HTML panel beside map
- [ ] Make score criteria visible.
- [ ] Make explanation readable.
- [ ] Make action plan practical and concise.

---

## Phase 3 — Houston-specific expansion

### Houston relevance

- [ ] Add flood-risk dataset research.
- [ ] Identify a usable Houston/Harris flood layer.
- [ ] Add flood-aware scoring logic.
- [ ] Add service radius / drive-time design.
- [ ] Add neighborhood profile summaries.

### Business-specific presets

- [ ] Tutoring preset
- [ ] Dentistry / med spa preset
- [ ] Real estate preset
- [ ] Home services preset
- [ ] General local business preset

---

## Phase 4 — Productization

### Deliverables

- [ ] Add exportable area brief.
- [ ] Add CSV/JSON export for scored areas.
- [ ] Add client-facing summary view.
- [ ] Add area comparison mode.

### Commercial usefulness

- [ ] Add competitor overlay strategy.
- [ ] Add business address input.
- [ ] Add low / medium / aggressive marketing budget modes.
- [ ] Add “best areas to target now” ranked list.

---

## Documentation

- [ ] Keep `PLAN.md` current when scope changes.
- [ ] Keep `TASKS.md` updated as work is completed.
- [ ] Update `README.md` with setup, data source, and run instructions.
- [ ] Document assumptions and limitations clearly.

---

## Immediate next actions

- [ ] Finalize open data source for demographics.
- [ ] Confirm tract shapefile location.
- [ ] Build and verify the shareable map MVP.
- [ ] Implement transparent Opportunity Score v2.
