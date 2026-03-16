# DC Feasibility Tool v4 — Completed Feature Archive

> Historical record of implemented features, their design rationale, and verification.
> Each section was originally a standalone implementation document.

---

## Table of Contents

1. [Results Dashboard Enhancements](#1-results-dashboard-enhancements)
2. [Firm Capacity with Peak Support](#2-firm-capacity-with-peak-support)
3. [Support Recommendations, Green Energy & Load Mix](#3-support-recommendations-green-energy--load-mix)
4. [PVGIS Solar Integration](#4-pvgis-solar-integration)
5. [Settings Runtime Diagnostics](#5-settings-runtime-diagnostics)
6. [Manual Weather CSV Upload](#6-manual-weather-csv-upload)
7. [Grid Context Feature](#7-grid-context-feature)
8. [Report Generation System](#8-report-generation-system)

---

## 1. Results Dashboard Enhancements

**Date**: March 10, 2026

### Changes
- Removed page width cap, switched to full-width 12-column grid layout
- Added detailed infrastructure footprint panel showing per-element breakdown with source citations
- Added backup technology selection within footprint analysis (Diesel, NG, SOFC, PEM, Flywheel)
- Added cooling footprint factor override (`m²/kW`)
- Added PUE overhead decomposition panel showing annual energy by component (electrical losses, fan/pump, cooling, economizer, misc)
- Added `site_id` to ScenarioResult for PUE breakdown API calls

### New API endpoint
- `POST /api/scenarios/pue-breakdown`

### Files changed
`backend/engine/models.py`, `backend/engine/pue_engine.py`, `backend/api/routes_scenario.py`, `frontend/src/types/index.ts`, `frontend/src/api/client.ts`, `frontend/src/pages/ResultsDashboard.tsx`

### Verification
Backend: 79 passed. Frontend build: passed.

---

## 2. Firm Capacity with Peak Support

**Date**: March 10, 2026

### Problem
The PUE paradox: annual mean PUE suggests high average IT load, but hottest hours require much more cooling power. The annual mean IT load is not a safe committed capacity.

### Model
Solves the maximum constant IT load maintainable over a full representative year under:
- Fixed facility-power cap
- Hourly climate-driven cooling demand
- Optional support from PV, BESS, fuel cell, generic backup

### Support dispatch order
1. PV serves facility demand directly
2. Grid serves remaining load up to cap
3. BESS discharges if demand exceeds cap
4. Fuel cell dispatches
5. Generic backup contributes
6. Spare grid headroom / surplus PV charges BESS

### BESS treatment
- `η_oneway = sqrt(η_roundtrip)`
- Cyclic-year convergence (start/end SoC matching) enabled by default

### New API endpoint
- `POST /api/green/firm-capacity`

### Inconsistencies resolved
- Results table now shows committed IT (P99) instead of static IT when hourly data exists
- Headline metrics show Committed IT (P99), Worst-Hour IT, Annual Mean IT, Nominal IT
- Scenario scoring now uses P99 when available

### Files changed
`backend/engine/pue_engine.py`, `backend/engine/green_energy.py`, `backend/api/routes_green.py`, `backend/api/routes_scenario.py`, `backend/tests/test_green_energy.py`, `frontend/src/types/index.ts`, `frontend/src/api/client.ts`, `frontend/src/pages/ResultsDashboard.tsx`

### Verification
Targeted: 87 passed. Full suite: 412 passed. Frontend build: passed.

---

## 3. Support Recommendations, Green Energy & Load Mix

**Date**: March 10, 2026

### Changes
1. **Firm-capacity recommendations**: Deterministic solver-based pathways (fuel_cell_only, backup_only, bess_only, hybrid_fc_bess) with sized capacities
2. **Green Energy real data**: New `POST /api/green/scenario-dispatch` uses real scenario hourly arrays instead of placeholders. Removed random PV generation.
3. **Load Mix Planner**: New `/load-mix` route with `LoadMixPlanner.tsx` exposing the existing backend optimizer

### Consistency fixes
- Fixed recursive self-call in `_validate_hourly_inputs()`
- Removed incorrect PV comments implying PVGIS already existed

### Files changed
Backend: `pue_engine.py`, `green_energy.py`, `routes_green.py`, tests. Frontend: `types/index.ts`, `client.ts`, `ResultsDashboard.tsx`, `GreenEnergy.tsx`, `LoadMixPlanner.tsx`, `Sidebar.tsx`, `App.tsx`

### Verification
Full backend: 417 passed. Frontend build: passed.

---

## 4. PVGIS Solar Integration

**Date**: March 10–11, 2026

### Design
- Fetch PVGIS `seriescalc` hourly PV output for `1 kWp` normalized system
- Multi-year averaging into one representative year
- File-backed cache at `backend/data/solar/{site_id}/{profile_key}.json`
- Backend-side scaling: `hourly_pv_kw[t] = hourly_pv_kw_per_kwp[t] × pv_capacity_kwp`

### New API endpoint
- `POST /api/green/fetch-pvgis-profile`

### PVGIS parameters exposed
- Year range (default 2019–2023)
- PV technology (crystSi, CIS, CdTe)
- Mounting (free-standing, building-integrated)
- System loss (default 14%)
- Horizon, optimal angles, manual tilt/azimuth

### Follow-up fixes (March 11)
- Fixed cache-hit bug (computed `hours` field not accepted by constructor)
- Added backend error detail surfacing to frontend
- Added session-state persistence for Green Energy and Scenario Runner pages

### Files changed
`backend/engine/solar.py` (new), `backend/api/store.py`, `backend/api/routes_green.py`, `frontend/src/pages/GreenEnergy.tsx`, `frontend/src/api/client.ts`, `frontend/src/types/index.ts`

### Verification
Targeted + full backend: passed. Frontend build: passed.

---

## 5. Settings Runtime Diagnostics

**Date**: March 12, 2026

### Changes
- Added `GET /api/settings/runtime-status` — site/weather/solar/template counts
- Added `POST /api/settings/test-external-services` — probes Open-Meteo Archive, Geocoding, PVGIS
- Added `POST /api/settings/clear-cache` — weather and solar cache clearing
- Updated health metadata in `main.py`

### Files changed
`backend/api/routes_settings.py` (new), `backend/api/store.py`, `backend/main.py`, `frontend/src/pages/Settings.tsx`, `frontend/src/api/client.ts`, `frontend/src/types/index.ts`

### Verification
Settings route tests: passed. Frontend build: passed.

---

## 6. Manual Weather CSV Upload

**Date**: March 12, 2026

### Supported CSV schema
- `dry_bulb_c` (required): Hourly dry-bulb temperature °C
- `relative_humidity_pct` (optional): Must be complete if present
- `timestamp_utc` (optional): ISO hourly UTC timestamps
- 8,760 rows (standard year) or 8,784 rows (leap year, Feb 29 removed)

### Source metadata
- `source_type`: `open_meteo_archive` or `manual_upload`
- Tracked: original filename, upload timestamp

### New API endpoint
- `POST /api/climate/upload-weather`

### Current limits
- CSV only (no EPW/TMY)
- No UI column mapping
- Single upload per site (replaces previous)

### Files changed
`backend/api/routes_climate.py`, `backend/engine/weather.py`, `frontend/src/pages/ClimateAnalysis.tsx`, `frontend/src/api/client.ts`, `frontend/src/types/index.ts`

### Verification
Targeted backend: passed. Frontend build: passed.

---

## 7. Grid Context Feature

**Date**: March 12, 2026

### Purpose
Site-level screening of nearby external power infrastructure (lines, substations) for early-stage feasibility assessment.

### What it does NOT do
- Claim exact spare capacity from public data alone
- Claim connection feasibility from proximity alone
- Feed raw line presence into the PUE engine

### Implemented milestones
1. **Data Model + Backend**: `GridAsset`, `GridContextResult`, `GridContextScore` models; `grid_context.py` engine; `routes_grid.py` API; cache in `data/grid_context/`
2. **Frontend Integration**: Site Manager grid context card with radius selector (500m–10km), asset table, map overlay
3. **Real Data Provider**: OSM/Overpass query for power lines and substations with caching
4. **Heuristic Scoring**: 35% distance, 30% voltage, 20% asset count, 15% evidence boost. Labeled as "screening attractiveness"
5. **Official Evidence**: Manual entry of confirmed voltage, MW, substation, timeline. `user_confirmed` confidence layer separate from `mapped_public`

### Confidence model
- `mapped_public`: OSM-derived, screening-grade
- `official_aggregate`: Area-level indicators
- `user_confirmed`: User-supplied official evidence only

### Voltage color coding
- ≤36 kV: gray | 63–132 kV: amber | 150–220 kV: orange | ≥380 kV: red

### Files
`backend/engine/grid_context.py`, `backend/api/routes_grid.py`, `backend/api/store.py`, `backend/engine/models.py`, `frontend/src/pages/SiteManager.tsx`, `frontend/src/components/MapView.tsx`, `frontend/src/types/index.ts`, `frontend/src/api/client.ts`

---

## 8. Report Generation System

**Date**: March 12–13, 2026

### Design principles
- Reports assembled from structured backend data, not freehand
- Model-generated narratives bounded to interpretation/summary only
- Unknown/low-confidence infrastructure excluded from headlines
- One primary deep-dive per site; alternatives in compact comparison

### Chapter order
1. Cover
2. Site Specifics and Properties (with map)
3. Grid Context / Power Access Context (optional)
4. Climate Study (optional)
5. Selected Scenario
6. Scenario Results Deep Dive
7. Ranked Alternatives (compact, max 3)
8. Load Mix (optional, if run)
9. Green Energy (optional, if run)
10. Appendix / Analyst Export

### Layout modes
- `presentation_16_9`: Slide-style widescreen
- `report_a4_portrait`: Formal A4 portrait

### Export request contract
- `studied_site_ids`, `primary_result_keys`, `layout_mode`
- Optional per-site `load_mix_results`, `green_energy_results`

### Visual assets
- Backend-generated inline SVG for site maps, grid context maps, climate charts
- No dependency on frontend chart libraries in export

### Narrative guardrails
- `structured_guardrail_v1` policy
- Short bounded blocks tied to structured data
- `Structured basis` labels for traceability

### Completed milestones
1. Scope & config refactor (studied-site selection, layout mode)
2. Unified report data aggregation layer
3. Map and visual asset capture (static SVG)
4. Core chapter templates
5. Advanced result sections (PUE, capacity, footprint, backup, sensitivity, break-even)
6. Load mix and green energy chapters
7. Narrative guardrails
8. Presentation and A4 layout CSS
9. Excel workbook expansion (full matrix, depth sheets)
10. Test and documentation hardening

### Files
`backend/export/html_report.py`, `backend/export/pdf_export.py`, `backend/export/excel_export.py`, `backend/export/report_data.py`, `backend/export/visual_assets.py`, `backend/export/templates/`, `backend/api/routes_export.py`, `frontend/src/pages/Export.tsx`
