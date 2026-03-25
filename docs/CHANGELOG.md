# DC Feasibility Tool v4 - Changelog

## v4.4.2 - Feasibility Gate: RAG & Score Reflect Infrastructure Fit (March 25, 2026)

### RAG Status Now Reflects Infrastructure Fit
- **Critical fix:** RAG status was computed during power calculation (before footprint), so it never knew whether equipment physically fits. A scenario where equipment overflows gray space by 200% could still show BLUE RAG.
- After footprint computation, RAG is now overridden to **RED** when equipment does not fit (`gray_space_utilization > 100%`). The reason is added to `rag_reasons`.
- Applied in both guided and batch scoring paths.
- **Files:** `backend/api/routes_scenario.py`, `backend/engine/ranking.py`

### Composite Score Hard-Capped for Non-Feasible Scenarios
- When equipment doesn't fit, the composite score is **capped at 25** regardless of how good other metrics are (PUE, IT capacity, etc.).
- The `rag_score` component is forced to 0 (RED equivalent) when equipment doesn't fit, eliminating the disconnect between a BLUE RAG and a non-fitting scenario.
- New `ScoreBreakdown` fields: `equipment_fits`, `score_capped`, `score_cap_reason`, `component_reasons`
- **Files:** `backend/engine/ranking.py`

### Score Breakdown Tooltip (Frontend)
- Added a help icon (?) next to every score cell in the results table and detail panel header.
- Clicking it opens a popover showing:
  - Per-component score bars with weights (PUE, IT Capacity, Space Utilization, RAG, Infrastructure Fit)
  - Human-readable explanation for each component
  - Composite score with cap warning when applicable
  - All RAG reasons that contributed to the feasibility assessment
- Score text turns red when capped due to non-feasibility.
- **Files:** `frontend/src/pages/ResultsDashboard.tsx`, `frontend/src/types/index.ts`

## v4.4.1 - Footprint Sizing Basis Fix & Auto-Compute (March 25, 2026)

### Footprint Sizing Basis Correction
- **Bug fix:** Footprint equipment sizing was using grid power availability (`facility_power_mw`, `procurement_power_mw`) instead of actual committed power. In area-constrained scenarios, this oversized all equipment because the grid offers more power than the DC can physically use.
- Now derives actual power from committed IT capacity: `actual_facility = committed_it × PUE / eta_chain`, `actual_procurement = actual_facility × procurement_factor`
- Uses hourly-simulated values when available: `it_capacity_p99_mw` and `annual_pue`
- Fixed in all 4 call sites: guided scoring, batch scoring, frontend Infrastructure tab, and export report
- **Files:** `backend/api/routes_scenario.py`, `backend/export/report/chapters/scenario.py`, `frontend/src/pages/ResultsDashboard.tsx`

### Infrastructure Fit Now Affects Ranking
- Footprint computation was already wired into the scoring pipeline (both guided and batch), but used wrong power values — now uses correct committed power values
- Different scenarios now get meaningfully different infrastructure_fit scores based on their actual power demand, not the shared grid availability
- Infrastructure fit weight: 10% of composite score (configurable)

### Auto-Compute Infrastructure Tab
- Infrastructure Footprint and Backup Power Comparison now auto-load when the Infrastructure tab is opened (previously required manual "Compute" / "Compare" button click)
- Button labels changed to "Recompute" / kept for manual refresh after parameter changes
- **Files:** `frontend/src/pages/ResultsDashboard.tsx`

### Roof Usable Single Source of Truth
- Removed duplicate `roof_usable` toggle from Infrastructure tab — now uses site-level setting from Site Manager only
- Shows read-only badge ("Roof usable" / "Roof not usable") with "(set in Site Manager)" hint
- Backend scoring paths now look up `site.roof_usable` from stored site config instead of hardcoding `True`
- **Files:** `frontend/src/pages/ResultsDashboard.tsx`, `backend/api/routes_scenario.py`

## v4.4.0 - Phase 1: Gray Space Calculation & Footprint Rework (March 25, 2026)

### Gray Space Model
- Added `gray_space_m2` and `gray_space_ratio` fields to `SpaceResult` model
- Gray space is the complement of IT whitespace — represents power rooms, cooling plant, corridors, and other support infrastructure
- Computed automatically: `gray_space_m2 = gross_building_area - it_whitespace_m2`, `gray_space_ratio = 1 - whitespace_ratio`
- **Files:** `backend/engine/models.py`, `backend/engine/space.py`

### Gray Space Sufficiency Check
- Added AMBER RAG warning when gray space ratio falls below 55% (Tier III minimum threshold)
- Warning: "Gray space ratio X% (< 55% threshold) — may be insufficient for support infrastructure"
- **Files:** `backend/engine/power.py`

### RAG Scoring Integration
- Added `gray_space_ratio` parameter to `score_scenario()` function
- Below-threshold gray space applies proportional penalty to `infrastructure_fit` score (up to 20 points)
- If equipment doesn't fit AND gray space is tight, infrastructure score drops to 0
- **Files:** `backend/engine/ranking.py`, `backend/api/routes_scenario.py`

### Footprint Model Rework (Equipment Inside Building)
- **Conceptual change:** All equipment lives INSIDE the buildable footprint, not outside on land
- Building split: white space (IT halls) + gray space (all support infrastructure)
- Gray space holds: backup generators, transformers, substation, and cooling (if roof not usable)
- Roof holds: cooling equipment ONLY, and ONLY when user confirms roof is usable
- Added `roof_usable` boolean to `Site` model (user toggle, default: True)
- Complete rewrite of `FootprintResult`: new fields `total_gray_space_equipment_m2`, `total_roof_equipment_m2`, `gray_space_utilization_ratio`, `gray_space_fits`, `gray_space_remaining_m2`, `warnings`
- Backward-compatible aliases: `ground_utilization_ratio` → `gray_space_utilization_ratio`, `ground_fits` → `gray_space_fits`
- Auto-generated warnings: equipment exceeding gray space, cooling exceeding roof, roof not usable, tight gray space (>85%)
- **Files:** `backend/engine/footprint.py`, `backend/engine/models.py`

### Frontend — Building Area Split & Infrastructure Tab
- New "Building Area Split" section in ResultsDashboard Overview tab
- Displays: Gross Building Area, IT Whitespace, Gray Space, Gray Space Ratio
- Stacked bar visualization: whitespace (blue) vs gray space (gray) within gross building area
- Warning badge and amber alert when gray space is insufficient (< 55%)
- Rewritten Infrastructure Footprint tab: gray space metrics, utilization bar, warnings display, fit badges, roof usable toggle
- Added `roof_usable` checkbox in SiteManager building section
- **Files:** `frontend/src/pages/ResultsDashboard.tsx`, `frontend/src/pages/SiteManager.tsx`, `frontend/src/types/index.ts`, `frontend/src/api/client.ts`

### Export Integration
- Added gray space (m²) and gray space ratio (%) to scenario chapter in report export
- Updated footprint export blocks to use gray space field names
- RAG warnings automatically included via `rag_reasons` pipeline
- **Files:** `backend/export/report/chapters/scenario.py`

### API Changes
- `FootprintRequest`: `land_area_m2` replaced by `gray_space_m2` + `roof_usable`
- All `compute_footprint` call sites updated (endpoint, guided scoring, batch scoring)
- **Files:** `backend/api/routes_scenario.py`

### Tests
- Complete rewrite of `test_footprint.py` — 27 tests covering gray space model, roof usable toggle, fit checks, warnings, backup types
- Updated `test_export.py` fixtures with `gray_space_m2` and `gray_space_ratio`
- All 540 tests passing

## v4.3.0 - Guided Mode, UI Renovation & Terrain Maps (March 16, 2026)

### Guided Mode (Preset Scenario Layer)
- Added Guided Mode to Scenario Runner: user selects sites only, all 6 load types run automatically with fixed best-practice cooling/density/redundancy presets
- Each load type maps to exactly one cooling topology, typical density, and N+1 redundancy
- Full 8,760-hour hourly simulation for climate-specific PUE (not static defaults)
- Backend: `backend/engine/smart_preset.py` with `GUIDED_PRESETS` mapping
- Backend: `GET /api/scenarios/guided-presets` and `POST /api/scenarios/guided-run` endpoints
- Frontend: Guided/Advanced mode toggle in ScenarioRunner with read-only preset summary table
- Results scored and ranked server-side, displayed in existing Results Dashboard

### UI Renovation
- Created reusable UI components: `CollapsibleSection`, `Tooltip`, `TabGroup`, `SlidePanel`
- **ResultsDashboard**: Completely renovated from 2-column layout to full-width results table + tab-based detail panel (Overview, Capacity & PUE, Infrastructure, Sensitivity, Expansion, Firm Capacity)
- **Settings**: All 6 sections converted to collapsible sections with smart defaults (overrides open, others collapsed)

### Terrain Maps in Reports
- Added `backend/export/terrain_map.py` using `staticmap` library with OpenTopoMap tiles (no API key needed)
- Terrain imagery rendered as first visual in site sections of HTML/PDF reports
- Added `GET /api/export/terrain-preview?site_id=` endpoint for frontend preview
- Added `staticmap==0.5.7` to requirements.txt
- Graceful fallback when coordinates unavailable or staticmap not installed

## v4.2.0 - Documentation Consolidation (March 16, 2026)
- Consolidated 17 documentation files into 4 canonical files:
  - `ARCHITECTURE.md` — Master architecture agreement
  - `HANDBOOK.md` — Technical reference (assumptions, formulas, DLC hybrid, overrides, engine credibility)
  - `CHANGELOG.md` — Version history
  - `COMPLETED_FEATURES.md` — Archive of implemented feature plans
- Deleted 15 individual feature/stub files that were merged
- Updated `README.md` documentation references

## v4.1.7 - Expanded Override Catalog Coverage (March 12, 2026)
- Chose broader override catalog coverage as the next smallest solid override step for the current repo
- Expanded the controlled override catalog so Settings now covers every cooling family currently exposed in Scenario Runner for:
  - `pue_typical`
  - `COP_ref`
  - `k_fan`
- Added curated override coverage for:
  - `Air-Cooled CRAC (DX)`
  - `Air-Cooled AHU (No Economizer)`
  - `Rear Door Heat Exchanger (RDHx)`
  - `Free Cooling — Dry Cooler (Chiller-less)`
- Kept the existing persistence, validation, runtime-resolution, and scenario-trace flow unchanged so current scenario engine compatibility is preserved
- Updated Settings and Scenario Runner copy to reflect the broader current override surface and the remaining preset/history follow-up scope
- Added focused backend regression coverage for:
  - full cooling-family catalog coverage
  - new RDHx static/hourly override resolution
  - new dry-cooler hourly trace coverage
- Documentation updated:
  - `docs/repo-status-next-actions.md`
  - `docs/assumption-overrides.md`

## v4.1.6 - Settings Runtime Fix and Climate Upload UX (March 12, 2026)
- Fixed a frontend reference-data shape mismatch that could blank the Settings page at runtime when rendering load density defaults
- Normalized `/api/reference-data` load-density fields in the frontend API client so pages consistently receive `density_kw.{low,typical,high}`
- Hardened the Settings page load-density table against either the normalized or legacy backend shape
- Improved the Climate page manual weather workflow with:
  - explicit `Choose CSV` action
  - `Clear Selected File` action before upload
  - `Delete Cached Weather` action for the selected site
- Added backend regression coverage for deleting one site's cached weather payload

## v4.1.5 - Manual Weather CSV Upload (March 12, 2026)
- Added a manual site-weather upload workflow that stores uploaded CSV data in the existing per-site weather cache instead of creating a separate path
- Added backend climate endpoint:
  - `POST /api/climate/upload-weather`
- Added manual weather CSV parsing and validation in `backend/engine/weather.py` with support for:
  - required hourly `dry_bulb_c`
  - optional `relative_humidity_pct`
  - optional `timestamp_utc`
  - `8760` standard-year rows
  - `8784` leap-year rows normalized by removing February 29
- Added source-traceable weather cache metadata so the app can distinguish:
  - `manual_upload`
  - `open_meteo_archive`
- Extended weather status responses to include source metadata, humidity availability, upload filename, and upload timestamp
- Updated the Climate page with:
  - Open-Meteo fetch and manual CSV upload cards
  - cached-weather source badges and metadata chips
  - replacement confirmation when changing the active cache source
  - automatic re-analysis after fetch or upload
- Added focused backend regression coverage for:
  - manual CSV parsing rules
  - climate upload route behavior
- Documentation added:
  - `docs/manual-weather-upload.md`

## v4.1.4 - Controlled Assumption Overrides (March 12, 2026)
- Added a curated, persisted assumption override workflow for selected engine parameters instead of free-form assumption editing
- Added backend Settings endpoints to list and update controlled assumption overrides with required source and justification metadata
- Added `backend/engine/assumption_overrides.py` to own:
  - the approved override catalog
  - range validation
  - file-backed persistence at `backend/data/settings/assumption_overrides.json`
  - runtime resolution of effective cooling, redundancy, and misc-overhead values
- Updated scenario execution so effective overrides are consumed by the live engine and stamped onto `ScenarioResult` metadata when applied
- Expanded the frontend Settings page with a catalog-driven override editor showing:
  - baseline values
  - effective values
  - allowed ranges
  - source/justification fields
- Updated Scenario Runner to surface active overrides before a batch run starts
- Added focused backend regression coverage for the new Settings and scenario-trace paths
- Documentation added:
  - `docs/assumption-overrides.md`

## v4.1.3 - Settings Runtime Ops and Repo Audit (March 12, 2026)
- Added a repo-grounded implementation audit and next-action checklist to separate completed work from stale roadmap notes
- Added backend Settings endpoints for:
  - runtime status snapshot
  - external service diagnostics (Open-Meteo Archive, Open-Meteo Geocoding, PVGIS)
  - server-side weather/solar cache clearing
- Expanded `backend/api/store.py` with site/cache counting and cache-clear helpers
- Updated the frontend Settings page to show:
  - runtime overview metrics
  - live external service checks
  - weather cache clear action
  - solar cache clear action
  - existing site deletion flow
- Updated backend health metadata so it no longer reports the project as only Phase 4 / API-layer work
- Added backend regression coverage for the new Settings routes
- Documentation added:
  - `docs/repo-status-next-actions.md`
  - `docs/settings-runtime-ops.md`

## v4.0.0 - Phase 0 (March 2026)
- Project setup: FastAPI backend + React frontend skeleton
- Architecture Agreement finalized
- All technical decisions documented

## v4.1.0 - Core Feasibility Buildout (March 10, 2026)
- Site workflow completed with CRUD, geocoding, KML/KMZ upload, geometry preservation, and exact map rendering of imported line/polygon geometries
- Climate workflow completed with representative-year weather fetch, climate analysis, free-cooling suitability outputs, and frontend/backend schema alignment fixes
- Scenario workflow completed with batch run, ranking, results dashboard, detailed infrastructure footprint, PUE overhead decomposition, firm-capacity support analysis, and load-mix planning
- Green Energy workflow upgraded to use real scenario hourly arrays instead of placeholder constant-load assumptions
- DLC hybrid model added so cold-plate systems are no longer treated as 100% liquid-side
- Documentation added:
  - `docs/dlc-hybrid-model.md`
  - `docs/firm-capacity-peak-support.md`
  - `docs/results-dashboard-enhancements.md`
  - `docs/support-recommendations-green-energy-load-mix.md`

## v4.1.1 - PVGIS Solar Integration (March 10, 2026)
- Backend PVGIS fetch flow implemented with normalized `1 kWp` hourly profiles
- Representative-year PV production built from multi-year PVGIS `seriescalc` output
- File-backed solar cache added at `backend/data/solar/{site_id}/{profile_key}.json`
- Green Energy page extended with PVGIS fetch controls, cache refresh, and backend-side scaling by installed PV capacity
- Manual PV CSV upload kept as an explicit override over cached PVGIS data
- Documentation added:
  - `docs/pvgis-fetch-flow.md`

## v4.1.2 - Green Energy and UI Persistence Fixes (March 11, 2026)
- Fixed cached PVGIS profile reload bug that could raise a backend `500` on cache hits because cached JSON included a computed `hours` field not accepted by the profile constructor
- Added regression coverage for cached PVGIS profile loading and scaling
- Improved Green Energy error reporting so backend `detail` messages are shown in the UI instead of generic Axios status text
- Added session-state persistence for Green Energy page inputs and outputs, including:
  - PV/BESS/fuel-cell form values
  - fetched PVGIS profile metadata
  - manual PV upload metadata
  - last successful dispatch result when it still matches the selected scenario
- Added session-state persistence for Scenario Runner selections
- Removed hardcoded default Scenario Runner selections for:
  - `AI / GPU Clusters`
  - `Water-Cooled Chiller + Economizer`
  so users now start with empty load/cooling selections and choose explicitly
