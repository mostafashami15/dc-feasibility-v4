# DC Feasibility v4 — Enhancement Roadmap

**Created:** 2026-03-24
**Status:** Approved
**Financial Calculations:** Explicitly excluded (handled by separate colleague)

---


## Overview

This roadmap organizes 7 categories of enhancements into 7 phased milestones, ordered by dependency and priority. Each phase builds on the previous, with some parallelism possible between independent phases.

### Dependency Graph

```
Phase 0 (Foundation & Model Fixes)
  │
  ├──→ Phase 1 (Gray Space) ─────────────────────────┐
  │                                                    │
  ├──→ Phase 2 (Green Energy Integration) ────────────┤
  │         ↕ can overlap                              ├──→ Phase 5 (Deployment)
  ├──→ Phase 3 (Red Flag Model) ──────────────────────┤        │
  │                                                    │        ↓
  └──→ Phase 4 (Advanced Sensitivity) ────────────────┘   Phase 6 (CFD Research)
```

---

## Phase 0: Foundation & Model Fixes ✅ COMPLETE

**Timeline:** Weeks 1–3
**Status:** Completed 2026-03-25
**Rationale:** Fix known issues and refactor technical debt before building new features on top.

### 0.1 — W8: KML Input Sanitization `[S]` ✅

- ✅ Added file size limit (10 MB max) in `routes_site.py`
- ✅ Replaced `xml.etree.ElementTree.fromstring()` with `defusedxml.ElementTree.fromstring()` to prevent XXE attacks
- ✅ Added coordinate range validation (lon ∈ [-180,180], lat ∈ [-90,90]) — invalid coordinates silently skipped
- ✅ Added `defusedxml==0.7.1` to `requirements.txt`
- **Files:** `backend/engine/weather.py`, `backend/api/routes_site.py`, `backend/requirements.txt`

### 0.2 — W9: Overpass API Hardening `[S]` ✅

- ✅ Added retry with exponential backoff (3 retries, 1s × 2^attempt)
- ✅ Graceful degradation: returns empty asset list instead of crashing on API failure
- ✅ Added `compute_data_quality_confidence()` — 0.0–1.0 score based on region coverage (asset count, voltage tags, substation presence)
- ✅ Added `data_quality_confidence` field to `GridContextResult` model
- **Files:** `backend/engine/grid_context.py`, `backend/engine/models.py`

### 0.3 — W7: Sensitivity Formula Deduplication `[M]` ✅

- ✅ Extracted shared `compute_effective_racks()` and `compute_it_load_from_racks()` into `space.py`
- ✅ Refactored `_it_load_area_constrained()` and `_effective_racks_from_geometry()` in `sensitivity.py` to delegate to the shared functions
- ✅ Ensures tornado/break-even results stay in sync with actual engine — single source of truth for geometry→racks arithmetic
- **Files:** `backend/engine/sensitivity.py`, `backend/engine/space.py`

### 0.4 — Linear COP to Quadratic Model `[M]` ✅

- ✅ Added optional `COP_quadratic` coefficient to all 8 cooling profiles in `COOLING_PROFILES`
- ✅ Formula: `COP = COP_ref + COP_slope × ΔT + COP_quadratic × ΔT²`
- ✅ Default `COP_quadratic = 0` preserves backward compatibility — all existing tests pass unchanged
- ✅ Added `TestCOPQuadratic` test class verifying quadratic key presence and linear equivalence
- **Files:** `backend/engine/cooling.py`, `backend/engine/assumptions.py`, `backend/tests/test_cooling.py`

### 0.5 — W6: Dynamic PUE in Load Mix Optimizer `[S–M]` ✅

- ✅ Added `get_pue_for_load_type()` helper in `assumptions.py`
- ✅ Replaced static `cooling_pue_typical` with per-load-type PUE lookup via `pue_per_load_type` dict
- ✅ Each load type's PUE contribution is now individually resolved — supports future per-zone cooling
- **Files:** `backend/engine/ranking.py`, `backend/engine/assumptions.py`

**Dependencies:** All tasks are independent and can be parallelized.
**Test results:** 538/538 tests passing after all changes.

---

## Phase 1: Gray Space Calculation ✅ COMPLETE

**Timeline:** Weeks 3–5
**Status:** Completed 2026-03-25
**Rationale:** Fills a gap in the space/footprint model. Gray space is the complement of whitespace and constrains infrastructure equipment placement.

### 1.1 — Define Gray Space in the Model `[S]` ✅

- ✅ Added `gray_space_m2` and `gray_space_ratio` fields to `SpaceResult` model
- ✅ Gray space computed as `gross_building_area - it_whitespace_m2` (explicit naming of existing `support_area_m2`)
- ✅ `gray_space_ratio = 1.0 - whitespace_ratio` (complement)
- **Files:** `backend/engine/models.py`, `backend/engine/space.py`

### 1.2 — Gray Space Sufficiency Check `[S]` ✅

- ✅ Minimum gray space ratio threshold set to 0.55 for Tier III
- ✅ If `gray_space_ratio < 0.55`, AMBER RAG warning: "Gray space ratio X% (< 55% threshold) — may be insufficient for support infrastructure"
- ✅ In scoring: if equipment doesn't fit (`worst_util > 1.0`) AND gray space is tight, infrastructure score drops to 0 (RED escalation)
- **Files:** `backend/engine/power.py`, `backend/engine/ranking.py`

### 1.3 — Integrate into RAG Scoring `[S]` ✅

- ✅ Added `gray_space_ratio` parameter to `score_scenario()` under `infrastructure_fit` component
- ✅ Below-threshold gray space ratio applies proportional penalty (up to 20 points)
- ✅ Both call sites in `routes_scenario.py` (guided mode + standard scoring) pass `gray_space_ratio`
- **Files:** `backend/engine/ranking.py`, `backend/api/routes_scenario.py`

### 1.4 — Frontend Display `[S]` ✅

- ✅ Added `gray_space_m2` and `gray_space_ratio` to TypeScript `SpaceResult` interface
- ✅ New "Building Area Split" section in ResultsDashboard Overview tab with:
  - Gross Building Area, IT Whitespace, Gray Space, Gray Space Ratio metrics
  - Stacked bar showing whitespace (blue) vs gray space (gray) split
  - Legend with color coding
  - Warning badge and amber alert when gray space < 55%
- **Files:** `frontend/src/pages/ResultsDashboard.tsx`, `frontend/src/types/index.ts`

### 1.5 — Export Integration `[S]` ✅

- ✅ Added "Gray space" (m²) and "Gray space ratio" (%) facts to the scenario chapter space section
- ✅ RAG warnings from power.py automatically appear in report export via `rag_reasons`
- **Files:** `backend/export/report/chapters/scenario.py`

### 1.6 — Footprint Model Rework (Equipment Inside Building) `[L]` ✅

- ✅ **Conceptual change:** All equipment lives INSIDE the buildable footprint, not on external land
- ✅ Building is split into white space (IT) and gray space (support equipment)
- ✅ Added `roof_usable` boolean to `Site` model — user controls whether cooling goes on roof or in gray space
- ✅ Complete rewrite of `footprint.py`: `compute_footprint()` now takes `gray_space_m2` + `roof_usable` instead of `land_area_m2`
- ✅ New `FootprintResult` fields: `total_gray_space_equipment_m2`, `total_roof_equipment_m2`, `gray_space_utilization_ratio`, `gray_space_fits`, `gray_space_remaining_m2`, `warnings`, `roof_usable`
- ✅ Backward-compatible aliases: `ground_utilization_ratio`, `ground_fits`
- ✅ Auto-generated warnings for: equipment exceeding gray space, cooling exceeding roof, roof not usable, tight gray space (>85%)
- ✅ Updated API endpoint (`FootprintRequest`), all call sites in guided/standard scoring
- ✅ Rewritten Infrastructure Footprint tab in frontend with gray space metrics, utilization bar, fit badges, roof usable toggle
- ✅ Added `roof_usable` checkbox in SiteManager
- ✅ Updated export report chapters to use new field names
- ✅ Complete rewrite of `test_footprint.py` — 27 tests
- **Files:** `backend/engine/footprint.py`, `backend/engine/models.py`, `backend/api/routes_scenario.py`, `backend/export/report/chapters/scenario.py`, `backend/tests/test_footprint.py`, `frontend/src/pages/ResultsDashboard.tsx`, `frontend/src/pages/SiteManager.tsx`, `frontend/src/types/index.ts`, `frontend/src/api/client.ts`

**Dependencies:** 1.1 → 1.2 → 1.3 sequential. 1.4, 1.5, 1.6 parallel after 1.3.
**Test results:** 540/540 tests passing after all changes.

### 1.7 — Footprint Sizing Basis Fix `[M]` ✅

- ✅ **Bug fix:** Footprint was sized using grid power availability (`facility_power_mw`) instead of actual committed power. In area-constrained scenarios, this oversized all equipment.
- ✅ Now uses: `actual_facility = committed_it × PUE / eta_chain`, with hourly values (`it_capacity_p99_mw`, `annual_pue`) when available
- ✅ Fixed in all 4 call sites: guided scoring, batch scoring, frontend, and export report
- ✅ Infrastructure tab auto-loads footprint and backup comparison on tab open (no manual "Compute" click needed)
- ✅ `roof_usable` in scoring now reads from site config (not hardcoded `True`)
- **Files:** `backend/api/routes_scenario.py`, `backend/export/report/chapters/scenario.py`, `frontend/src/pages/ResultsDashboard.tsx`

### 1.8 — Feasibility Gate: RAG & Score Reflect Infrastructure Fit `[M]` ✅

- ✅ **Critical fix:** RAG was evaluated during power calculation (before footprint), so it never knew if equipment fits. A scenario with 200% gray space overflow could still show BLUE RAG and rank #1.
- ✅ Post-footprint RAG override: if equipment doesn't fit → **RED** with reason added to `rag_reasons`
- ✅ Composite score hard-capped at **25** when equipment doesn't fit (was only a 10% weight penalty before)
- ✅ `rag_score` forced to 0 (RED equivalent) when equipment doesn't fit
- ✅ New `ScoreBreakdown` fields: `equipment_fits`, `score_capped`, `score_cap_reason`, `component_reasons`
- ✅ Frontend: Score info tooltip (?) button on every row and detail header showing per-component bars, weights, reasons, and cap warnings
- **Files:** `backend/engine/ranking.py`, `backend/api/routes_scenario.py`, `frontend/src/pages/ResultsDashboard.tsx`, `frontend/src/types/index.ts`

**Test results:** 540/540 tests passing after all changes.

---

## Phase 2: Green Energy Integration ✅ COMPLETE

**Timeline:** Weeks 5–10
**Status:** Completed 2026-03-25
**Rationale:** The largest single feature. Moves green energy from a disconnected standalone page into the core scenario pipeline.

### Design Decision

The green energy redesign is **architecturally sound** for these reasons:

1. **Solar data belongs at the site level** — irradiance is a geographic property, not a scenario property. Fetching PVGIS on site creation is correct data modeling.
2. **Green dispatch inside the scenario pipeline** eliminates the fragmented workflow where users must manually re-select scenarios on a separate page.
3. **Advisory mode** transforms the tool from "what if I install X?" to "what do I need for Y% coverage?" — the question stakeholders actually ask.
4. **Firm capacity already depends on green energy** — integrating upstream removes a manual handoff.

**Caveats:**
- PVGIS auto-fetch must be async/non-blocking (FastAPI `BackgroundTasks`)
- Keep standalone page temporarily as advanced exploration mode until integrated flow is validated

### 2.1 — Auto-Fetch PVGIS on Site Creation `[M]` ✅

- ✅ Background PVGIS fetch triggered on site create/update with valid lat/lon
- ✅ Uses `solar.py → build_representative_pvgis_profile()` and `store.save_solar_profile()`
- ✅ Fetch status tracked in-memory: none → loading → cached → error
- ✅ New `has_any_solar_profile()` helper in store.py
- ✅ New `GET /api/sites/{site_id}/solar-status` endpoint for polling
- ✅ `SiteResponse` includes `has_solar` and `solar_fetch_status` fields
- **Files:** `backend/api/routes_site.py`, `backend/api/store.py`

### 2.2 — Add Green Energy Inputs to Site Model `[S]` ✅

- ✅ New optional fields on `Site`: `pv_capacity_kwp`, `bess_capacity_kwh`, `bess_efficiency`, `fuel_cell_kw`
- ✅ New `green_energy` dict field on `ScenarioResult` for integrated dispatch results
- ✅ Frontend types updated with matching fields on `Site`, `ScenarioResult`, `SiteResponse`
- ✅ New `GreenAdvisoryCoverageLevel` and `GreenAdvisoryResult` TypeScript interfaces
- **Files:** `backend/engine/models.py`, `frontend/src/types/index.ts`

### 2.3 — SiteManager UI for Green Inputs `[M]` ✅

- ✅ "Green Energy Facilities" fieldset in site entry form with PV, BESS, efficiency, fuel cell fields
- ✅ PVGIS status indicator (loading/cached/error) shown when editing existing site
- ✅ Solar status badge in site list card (alongside weather badge)
- ✅ Green facility summary block in site detail view
- ✅ Solar MetricCard in site detail header
- **Files:** `frontend/src/pages/SiteManager.tsx`

### 2.4 — Integrate Green Dispatch into Scenario Pipeline `[L]` ✅

- ✅ After `simulate_hourly()` in `_run_single_scenario`, auto-runs green dispatch if site has green inputs
- ✅ New `_try_green_dispatch()` helper loads PVGIS profile, scales by PV capacity, runs dispatch
- ✅ `GreenEnergyResult` summary attached to `ScenarioResult.green_energy` (hourly arrays excluded for bandwidth)
- ✅ Works in both batch and single run endpoints
- **Files:** `backend/api/routes_scenario.py`, `backend/engine/models.py`

### 2.5 — Green Energy Tab in ResultsDashboard `[M]` ✅

- ✅ New "Green Energy" tab positioned after Expansion, before Firm Capacity
- ✅ Tab order: Overview → Capacity & PUE → Infrastructure → Sensitivity → Expansion → **Green Energy** → Firm Capacity
- ✅ Contents: headline metrics, configuration summary, dispatch breakdown with visual bars, additional metrics
- ✅ Graceful empty state when no green energy is configured
- **Files:** `frontend/src/pages/ResultsDashboard.tsx`, `frontend/src/types/index.ts`

### 2.6 — Advisory Mode: Auto-Sizing for Coverage Targets `[L]` ✅

- ✅ New `compute_green_advisory()` in `green_energy.py`: binary search on PV capacity for target coverage levels
- ✅ Coverage targets: 10%, 25%, 50%, 75%, 100% of overhead
- ✅ BESS sized as 4 hours of average PV output (standard rule of thumb)
- ✅ New `POST /api/scenarios/green-advisory` endpoint
- ✅ Output: table of {coverage_target, pv_kwp_needed, bess_kwh_needed, annual_generation_mwh, co2_avoided_tonnes}
- **Files:** `backend/engine/green_energy.py`, `backend/api/routes_scenario.py`

### 2.7 — Advisory Mode UI `[M]` ✅

- ✅ Advisory section embedded in the Green Energy tab with "Compute Advisory Sizing" button
- ✅ Results displayed as a table showing PV/BESS sizing across coverage levels
- ✅ Loading/error states handled
- **Files:** `frontend/src/pages/ResultsDashboard.tsx`, `frontend/src/api/client.ts`

### 2.8 — Export Integration `[S–M]` ✅

- ✅ Report assembly auto-populates green energy chapter from `ScenarioResult.green_energy` when no explicit input
- ✅ Advisory table builder added to green energy chapter (`_build_advisory_table()`)
- **Files:** `backend/export/report/chapters/green_energy.py`, `backend/export/report/_assembly.py`

### 2.9 — Deprecate Standalone Green Energy Page `[S]` ✅

- ✅ Removed from sidebar navigation (comment explains integration)
- ✅ Route kept at `/green` as advanced exploration archive
- ✅ Component file preserved for advanced users
- **Files:** `frontend/src/components/Sidebar.tsx`

**Dependencies:** 2.1 before 2.4. 2.2 before 2.3. 2.4 before 2.5/2.6. 2.6 before 2.7. 2.8 depends on 2.4.
**Test results:** 540/540 tests passing after all changes.

---

## Phase 3: Red Flag Model & Infrastructure Layers

**Timeline:** Weeks 8–14
**Rationale:** Adds infrastructure context layers to produce a report comparable to L22DC's Red Flag Report. The L22 report (Lonate Pozzolo, 47 slides, 16:9 landscape) covers 6 chapters: Location & Positioning, Risk Assessment, Environmental Analysis, Site Conditions, Power Assessment, and Urban Planning. Our model should automate as much of this as possible using APIs and public data sources.

**Reference:** L22DC Red Flag Report — "0000 ES R DD 01 - Red Flag Metlen - Lonate Pozzolo.pdf" (2026-02-25)

### L22 Report Structure Mapping

| L22 Chapter | Our Current Coverage | Gap |
|---|---|---|
| 00 Executive Summary + RAG | Partial (scoring in `ranking.py`) | Need per-chapter RAG, overall site assessment |
| 01 Location & Positioning | Partial (MapView, terrain_map) | Need macro/micro positioning, infrastructure network, emergency services |
| 02 Risk Assessment | None | Need flood, seismic, geological, industrial/chemical, TIA-942 classification |
| 03 Environmental Analysis | None | Need historical orthophotos, environmental constraints, Natura 2000, air quality |
| 04 Site Conditions | None | Need acoustic classification, utilities, community/stakeholder analysis |
| 05 Power Assessment | Partial (grid_context.py) | Need HV connection process, connection scenarios, Terna substation proximity |
| 06 Urban Planning | None | Need municipal land use, buildability indices, constraints (mostly manual input) |

### 3.1 — Infrastructure Network & Accessibility Layer `[M]`

- Query Overpass API for:
  - **Fiber connectivity:** `telecom=*` features (fiber lines, exchanges, data centers)
  - **Gas pipelines:** `pipeline=gas`, `man_made=pipeline`
  - **Road network:** `highway=trunk|motorway|primary|secondary` + `railway=rail`
  - **Emergency services:** `amenity=hospital|fire_station`, `emergency=*`
- Model: `InfraAsset` with type, distance, operator, classification
- Compute distances and response time estimates (based on L22's methodology: hospital 20-30min, fire brigade 5-10min)
- Reuse haversine distance logic from `grid_context.py`
- **Files:** New `backend/engine/infra_context.py`, `backend/engine/models.py`

### 3.2 — Risk Assessment Layer `[L]`

- **Flood risk:** Query PGRA (Flood Risk Management Plan) data or equivalent open data APIs per country
  - For Italy: Geoportale Nazionale flood zone maps
  - Classify distance to nearest flood zone (L22 reports 600m as safe)
- **Seismic risk:** Query seismic zone classification from national databases
  - For Italy: INGV seismic hazard maps (Zones 1-4)
- **Industrial/Chemical risk (Seveso/RIR):** Query Overpass API for `industrial=*` + national Seveso databases
  - Distance to nearest RIR establishment
- **TIA-942-C-2024 Classification:** Automated scoring based on:
  - A1: Distance to flood hazard area
  - A2: Distance to coastal/navigable waterways
  - A3: Distance to highways/rail lines
  - A4: Distance to major airports (`aeroway=aerodrome` in Overpass)
  - Assign Level 1-4 per criterion (L22 methodology on p.29)
- **Files:** New `backend/engine/risk_assessment.py`, `backend/engine/models.py`

### 3.3 — Environmental Analysis Layer `[L — Partial Automation]`

- **Historical orthophotos:** Research APIs (Geoportale della Lombardia, Google Earth Engine, Sentinel Hub)
  - Fetch aerial imagery for site coordinates across multiple years (e.g., 1975, 1998, 2003, 2015, 2021)
  - L22 uses 6 time periods from "Geoportale della Lombardia" (p.31)
  - This is a **research task** — API availability varies by country
- **Environmental constraints:** Partially automatable via national geoportals
  - For Italy: Query PTCP strategic agricultural area designation
  - Natura 2000 network (SIC/ZPS) proximity — available via EU/EEA open data
- **Air quality zones:** Query ARPA data or EU Air Quality Index
- **Landscape sensitivity:** Likely manual input (varies by municipal PGT)
- **Files:** New `backend/engine/environmental.py`

### 3.4 — Site Conditions Layer `[M]`

- **Acoustic classification:** Manual input (acoustic zoning maps are municipal-level, not API-accessible)
  - Model: acoustic class (I-VI), daytime/nighttime emission limits
  - Flag if class needs to change for industrial use (L22 flags Class II → Class V requirement)
- **Community & stakeholder analysis:** Template-based, with proximity to residential areas as automatic input
  - Distance to nearest residential zone (from Overpass: `landuse=residential`)
  - Generate stakeholder power/interest matrix template (L22 p.38)
- **Files:** New `backend/engine/site_conditions.py`, `backend/engine/models.py`

### 3.5 — Power Assessment Enhancement `[M]`

- Extend existing `grid_context.py` to include:
  - Nearest Terna substation by voltage class (132kV, 220kV, 380kV)
  - Connection scenario classification: <100MW → 132kV, >100MW → 380kV mandatory
  - Distance to each voltage class substation
  - HV connection process timeline template (L22 p.40: STMG 90d → design 540d → permit 540d)
- **Files:** `backend/engine/grid_context.py`, `backend/engine/models.py`

### 3.6 — Urban Planning Framework `[S — Manual Input]`

- Add site-level fields for urban planning data (user-entered):
  - Municipal land use designation (residential, industrial, agricultural, etc.)
  - Buildability indices: UF (land utilization), coverage ratio, permeable surface index, setback distances, max height
  - Constraints: airport protection zones, road buffer zones, Natura 2000 proximity
  - Variant required? (boolean + notes)
- Model validates against entered constraints (e.g., if max height < floor_to_floor × num_floors → warning)
- **Files:** `backend/engine/models.py`, `frontend/src/pages/SiteManager.tsx`

### 3.7 — Red Flag Scoring Engine `[L]`

- Per-chapter RAG assessment (matching L22 structure):
  - Location & Positioning → RED/AMBER/GREEN
  - Risk Assessment → RED/AMBER/GREEN
  - Environmental Analysis → RED/AMBER/GREEN
  - Site Conditions → RED/AMBER/GREEN
  - Power Assessment → RED/AMBER/GREEN
  - Urban Planning → RED/AMBER/GREEN
  - **Overall Assessment** → composite
- Rule-based scoring with configurable thresholds (e.g., "no fiber within 5km → RED")
- Integrates into existing RAG system in `ranking.py`
- **Files:** New `backend/engine/red_flag.py`, `backend/engine/ranking.py`

### 3.8 — Map Visualization with Layer Toggles `[L]`

- Display all infrastructure layers on the SiteManager map
- Layer toggle controls: Fiber (blue), Gas (orange), Roads (gray), Grid (yellow), Emergency (red)
- Distance rings at 1km, 5km, 10km (matching L22 visual style)
- Site boundary overlay from KML geometry
- **Files:** `frontend/src/components/MapView.tsx`, `frontend/src/pages/SiteManager.tsx`

### 3.9 — Red Flag Report Export `[L]`

- New report type: "Red Flag Report" (in addition to existing executive/detailed)
- **Layout: 16:9 landscape presentation format** (matching L22 exactly)
  - L22 uses ~1456×816px effective content area per slide
  - Header: dual logo (L22DC + Metlen) top-left, chapter/section title top-right
  - Footer: date bottom-left, document title center, page number bottom-right
  - Navy (#0A2240) headings, standard body text
- Chapter-based structure matching L22's 6-chapter layout
- Auto-generated maps with infrastructure layers as inline images
- RAG summary table on executive summary slide
- TIA-942-C compliance matrix
- **Files:** New `backend/export/report/chapters/red_flag.py`, new template `backend/export/templates/red_flag.html`

**Dependencies:** 3.1-3.4 are independent data layers. 3.5-3.6 extend existing modules. 3.7 depends on all data layers. 3.8 depends on 3.1-3.4. 3.9 depends on 3.7.

### 3.3 — Road Network & Accessibility Layer `[M]`

- Query Overpass API for `highway=trunk|motorway|primary|secondary` and `railway=rail`
- Compute distance to nearest major road and rail line
- Model: `AccessAsset` with type, distance, name, classification
- **Files:** Same as 3.1

### 3.4 — Infrastructure Context API Endpoint `[M]`

- New endpoint: `GET /api/sites/{site_id}/infrastructure-context`
- Returns unified response: fiber, gas, road layers alongside existing grid context
- Caching strategy: same as grid context (file-backed, keyed by radius + version)
- **Files:** `backend/api/routes_grid.py` or new `routes_infra.py`

### 3.5 — Map Visualization with Layer Toggles `[L]`

- Display fiber/gas/road/grid layers on the SiteManager map
- Layer toggle controls (checkboxes) to show/hide each infrastructure type
- Color coding: Fiber (blue), Gas (orange), Roads (gray), Grid (yellow)
- Distance rings at 1km, 5km, 10km
- **Files:** `frontend/src/components/MapView.tsx`, `frontend/src/pages/SiteManager.tsx`

### 3.6 — Red Flag Scoring `[M]`

- Combine infrastructure context into a site-level "Red Flag" assessment
- Flag rules (examples):
  - No fiber within 5 km → RED FLAG
  - No major road within 2 km → AMBER FLAG
  - No gas pipeline within 10 km → INFO (relevant only for gas-based backup)
  - No substation within 5 km → RED FLAG
- Composite infrastructure readiness score (0–100)
- **Files:** New scoring logic in `backend/engine/infra_context.py` or `ranking.py`

### 3.7 — Historical Satellite Imagery `[L — Research]`

- **Research task:** Evaluate available APIs:
  - **Sentinel Hub** (ESA) — free tier, 10m resolution, 5-day revisit
  - **Google Earth Engine** — academic/research access, historical archive back to 1984
  - **Planet** — commercial, daily 3m resolution
- Prototype: fetch 3–5 years of imagery for a site to show land use change
- This is primarily a data sourcing challenge, not an engineering challenge
- **Files:** New module TBD after research

### 3.8 — Report Layout & Red Flag Chapter `[M]`

- Add infrastructure context chapter to the export report
- Include: map with infrastructure layers, red flag summary table, distance matrix
- **Report layout sizing:** Research L22 report format (likely A4 portrait or US Letter) and match page dimensions, margins, and font sizing in `base.html` @page rules
- **Files:** New `backend/export/report/chapters/infrastructure.py`, `backend/export/templates/base.html`

**Dependencies:** 3.1–3.3 independent. 3.4 depends on 3.1–3.3. 3.5/3.6 depend on 3.4. 3.7 independent research. 3.8 depends on 3.4.

---

## Phase 4: Advanced Sensitivity — Monte Carlo

**Timeline:** Weeks 12–16
**Rationale:** Extends the existing OAT sensitivity with probabilistic analysis. Depends on Phase 0.3 (formula deduplication) to ensure Monte Carlo calls the actual engine.

### 4.1 — Monte Carlo Simulation Engine `[L]`

- New function `compute_monte_carlo()` in `sensitivity.py`
- Input: parameter distributions (uniform, triangular, normal) with bounds
- Sample N iterations (1,000–10,000), run `power.solve()` per sample
- Output: percentile results (P10, P50, P90), parameter importance (Spearman rank correlation)
- Support correlated parameters via Cholesky decomposition (optional)
- **Files:** `backend/engine/sensitivity.py`, `backend/tests/test_sensitivity.py`

### 4.2 — Monte Carlo API Endpoint `[M]`

- New `POST /api/scenarios/monte-carlo`
- Accept: parameter distribution definitions, sample count, target metrics
- Return: distribution summary, percentiles, correlation matrix
- **Files:** `backend/api/routes_scenario.py`

### 4.3 — Monte Carlo UI `[L]`

- New sub-section under Sensitivity tab in ResultsDashboard
- Visualizations: histogram of IT load distribution, box plot of key metrics, parameter importance tornado
- Confidence interval display: "90% confident IT load is between X and Y MW"
- **Files:** `frontend/src/pages/ResultsDashboard.tsx`, new chart component

### 4.4 — Export Integration `[S]`

- Add Monte Carlo results to the sensitivity section of the report
- Include: distribution histogram, percentile table, key findings
- **Files:** `backend/export/report/chapters/scenario.py`

**Dependencies:** Requires Phase 0.3. 4.1 → 4.2 → 4.3 sequential. 4.4 after 4.2.

---

## Phase 5: Deployment & Platform Maturity

**Timeline:** Weeks 14–20
**Rationale:** Containerization, auth, and database migration needed for production deployment. Placed after feature work to avoid infrastructure churn, but Docker (5.1) can start anytime.

### 5.1 — Docker Containerization `[M]`

- `Dockerfile.backend`: Python 3.11 + uvicorn
- `Dockerfile.frontend`: Node build stage + nginx serve stage
- `docker-compose.yml`: both services + PostgreSQL (for Phase 5.3)
- Environment variable configuration for all external URLs
- **Files:** New: `Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.yml`, `.dockerignore`

### 5.2 — CI/CD Pipeline `[M]`

- GitHub Actions workflow:
  - Lint: `ruff` (Python), `eslint` (TypeScript)
  - Type check: `mypy` (backend), `tsc --noEmit` (frontend)
  - Test: `pytest` (backend), `vitest` (frontend)
  - Build: Docker images
  - Deploy: push to container registry on merge to main
- **Files:** New: `.github/workflows/ci.yml`

### 5.3 — Database Migration: JSON → PostgreSQL `[XL]`

- Replace `api/store.py` file-backed storage with SQLAlchemy + PostgreSQL
- The store module is cleanly isolated — function signatures stay the same, only implementation changes
- Migration script to import existing JSON/Parquet files
- Use Alembic for schema migrations
- **Files:** `backend/api/store.py` (rewrite), new: `backend/api/database.py`, `backend/api/models_db.py`, `alembic/`

### 5.4 — Authentication `[L]`

- JWT-based auth with FastAPI dependency injection
- Simple user model: email + hashed password
- Protect all API routes with auth middleware
- Login/register UI pages
- **Files:** New: `backend/api/auth.py`, `backend/api/routes_auth.py`, frontend auth pages

### 5.5 — API Versioning `[S]`

- Prefix all routes with `/api/v1/`
- Add version header to responses
- Router reorganization in `main.py`
- **Files:** `backend/api/routes_*.py`, `backend/main.py`

### 5.6 — Frontend Hardening `[M]`

- Error boundaries around all page components
- Loading states and skeleton screens
- Offline detection and graceful degradation
- Input validation matching backend Pydantic constraints
- **Files:** Multiple frontend components

### 5.7 — Test Coverage Expansion `[L]`

- Target: 80% backend coverage with `pytest`
- Add integration tests for the full scenario pipeline (site → scenario → results → export)
- Frontend: component tests with `vitest` + `@testing-library/react`
- **Files:** `backend/tests/`, new `frontend/src/**/*.test.tsx`

**Dependencies:** 5.1 before 5.2. 5.3 independent but large. 5.4 parallel with 5.3. 5.5–5.7 parallel.

---

## Phase 6: CFD Research (Long-Term)

**Timeline:** Weeks 20+
**Rationale:** Computational fluid dynamics is a long-term research initiative. Start with scoping and a simplified intermediate model.

### 6.1 — CFD Feasibility Study `[XL — Research]`

- Evaluate open-source CFD solvers:
  - **OpenFOAM** — mature, extensive documentation, steep learning curve
  - **PyFR** — Python-native, GPU-accelerated, modern
  - **SU2** — lighter weight, good for steady-state
- Define scope: steady-state 2D cross-section of a data hall (not full 3D transient)
- Assess compute requirements: can it run in reasonable time for a feasibility tool?
- **Deliverable:** Technical feasibility report with recommended approach

### 6.2 — Zonal Thermal Model (Intermediate Step) `[L]`

- Before full CFD: implement a simplified zonal model
- Well-mixed zone per hot/cold aisle
- Inputs: rack power density, airflow rate, supply temperature
- Outputs: hot aisle temperature, return air temperature, cooling adequacy
- This feeds into cooling system sizing validation without mesh-based CFD complexity
- **Files:** New: `backend/engine/thermal_zones.py`

---

## Summary Table

| Phase | Name | Timeline | Complexity | Key Deliverable |
|-------|------|----------|-----------|-----------------|
| **0** | Foundation & Model Fixes | Weeks 1–3 | S–M each | Clean, correct engine foundation |
| **1** | Gray Space Calculation | Weeks 3–5 | S each | Gray space warnings + RAG integration |
| **2** | Green Energy Integration | Weeks 5–10 | S–L | Integrated green pipeline + advisory mode |
| **3** | Red Flag Model | Weeks 8–14 | M–L | Infrastructure layers + red flag scoring |
| **4** | Advanced Sensitivity | Weeks 12–16 | M–L | Monte Carlo probabilistic analysis |
| **5** | Deployment & Platform | Weeks 14–20 | S–XL | Production-ready containerized platform |
| **6** | CFD Research | Weeks 20+ | XL | Thermal modeling research & prototype |

## Complexity Legend

| Symbol | Meaning |
|--------|---------|
| `[S]` | Small — less than a day |
| `[M]` | Medium — 1–3 days |
| `[L]` | Large — 3–7 days |
| `[XL]` | Extra Large — 1–3 weeks |

## Explicit Exclusion

**Financial calculations (CAPEX, OPEX, ROI, TCO, NPV) are NOT included in any phase.** This domain is handled by a separate colleague and is intentionally excluded from this roadmap.
