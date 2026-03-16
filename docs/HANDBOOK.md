# DC Feasibility Tool v4 — Project Handbook

> Complete technical reference and continuation guide.
> Last updated: March 16, 2026

## Documentation Map

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Master architecture agreement — all technical decisions |
| **HANDBOOK.md** (this file) | Technical reference: assumptions, formulas, engine models, overrides |
| [CHANGELOG.md](./CHANGELOG.md) | Chronological version history |
| [COMPLETED_FEATURES.md](./COMPLETED_FEATURES.md) | Archive of implemented feature plans and verification records |

---

## 1. Engineering Assumptions

Every default value in the model is sourced and cited. The canonical source is `backend/engine/assumptions.py`. No magic numbers exist anywhere in the engine.

### 1.1 Load Profiles

All values in kW per rack.

| Load Type | Low | Typical | High | Source |
|-----------|-----|---------|------|--------|
| Colocation (Standard) | 4 | 7 | 12 | Uptime Institute 2023, CBRE Data Center Solutions |
| Colocation (High Density) | 12 | 20 | 35 | DCD Intelligence 2024, Equinix xScale |
| HPC | 20 | 40 | 60 | TOP500 analysis, ORNL Frontier |
| AI / GPU Clusters | 40 | 100 | 140 | NVIDIA DGX H100/GB200/GB300 specs |
| Hyperscale / Cloud | 8 | 15 | 25 | Google/Microsoft/Meta published designs |
| Edge / Telco | 2 | 5 | 8 | ETSI MEC standards, ATC tower colocation |

### 1.2 Cooling Profiles

Each cooling type belongs to one of four topologies with distinct physics:

| Topology | Systems | Driver | Economizer |
|----------|---------|--------|------------|
| mechanical_only | CRAC (DX), AHU | Dry-bulb | None |
| chiller_integral_economizer | Air Chiller+Econ, RDHx, DLC, Immersion | Dry-bulb | 3-mode |
| water_side_economizer | Water Chiller+Econ | Wet-bulb | 2-mode |
| air_side_economizer | Dry Cooler (chiller-less) | Dry-bulb | 2-mode |

**Default PUE values** (static, typical density):

| Cooling Type | PUE typical |
|-------------|-------------|
| Air-Cooled CRAC (DX) | 1.65 |
| Air-Cooled AHU (No Economizer) | 1.55 |
| Air-Cooled Chiller + Economizer | 1.38 |
| Water-Cooled Chiller + Economizer | 1.28 |
| Rear Door Heat Exchanger (RDHx) | 1.30 |
| Direct Liquid Cooling (DLC) | 1.12 |
| Immersion Cooling (Single-Phase) | 1.06 |
| Free Cooling — Dry Cooler | 1.15 |

### 1.3 COP Linear Model

Per topology, COP varies linearly with ambient temperature:

```
COP(T) = COP_ref + COP_slope × (T_ref - T_driver)
Clamped to [COP_min, COP_max]
```

Example (Air-Cooled Chiller + Economizer):
- COP_ref: 5.5 @ 35°C, slope: 0.15/°C, range: [2.5, 9.0]

### 1.4 Power Chain Efficiency

```
η_chain = transformer (0.985) × UPS (0.940) × PDU (0.980) = 0.907
Derated by redundancy: N: 0.970, N+1: 0.965, 2N: 0.950, 2N+1: 0.940
```

### 1.5 Miscellaneous Overhead

`f_misc = 0.025` (2.5% of available power for lighting, BMS, security, fire suppression, office HVAC).
Source: EU Code of Conduct on DC Energy Efficiency.

### 1.6 Whitespace Adjustment Factors

| Cooling Type | Factor | Reason |
|-------------|--------|--------|
| Immersion | 0.85 | Tank layout wider |
| CRAC / DLC | 0.92 | Floor equipment takes space |
| All others | 1.00 | Separate plant rooms |

---

## 2. Core Formulas

### 2.1 Hourly Facility Power

```
P_facility(t) = P_IT(t) × (1 + a(t)) + b
where:
  a(t) = elec_loss + k_fan + cool_kW_per_kW_IT(t) + k_econ(t)
  b = P_reference × f_misc
```

### 2.2 Annual PUE (Energy-Weighted)

```
PUE_annual = Σ P_facility(t) / Σ P_IT(t)     (NOT arithmetic mean)
```

### 2.3 Wet-Bulb Temperature

Stull (2011) approximation using dry-bulb + relative humidity. Valid: -20°C to 50°C, 5–99% RH. Accuracy: ±1°C typical.

### 2.4 Procurement Power

```
P_procurement = P_facility × procurement_factor
```

Where procurement_factor accounts for grid reservation vs operational power.

---

## 3. DLC Hybrid Model

Date implemented: March 10, 2026.

The DLC (Direct Liquid Cooling) system uses an explicit hybrid split rather than treating the entire load as liquid-cooled:

- **75% liquid-cooled path**: Warm water (35°C supply) with high COP
- **25% residual air-cooled path**: Uses Air-Cooled Chiller + Economizer model

This split is derived from the documented 20–30% residual air-cooled remainder (cold plates cover CPUs/GPUs only).

### Hourly calculation

For each hour:
1. Compute primary DLC branch using DLC profile
2. Compute residual air branch using Air-Cooled Chiller + Economizer
3. Combine with 75/25 weighting:
   - `cool_kw_per_kw_it = 0.75 × cool_dlc + 0.25 × cool_air`
   - `k_fan = 0.75 × k_fan_dlc + 0.25 × k_fan_air`
   - `k_econ = 0.75 × k_econ_dlc + 0.25 × k_econ_air`

### Mode determination (conservative)
- ECON_FULL only if both branches are ECON_FULL
- MECH only if both branches are MECH
- Otherwise ECON_PART

### Climate free-cooling hours
DLC full free cooling now requires both the liquid branch AND the residual air branch to be ECON_FULL.

### Limitation
The 75/25 split is a fixed default assumption. Future enhancement: make liquid coverage configurable per workload/site.

Files: `backend/engine/assumptions.py`, `backend/engine/cooling.py`, `backend/engine/climate.py`

---

## 4. Controlled Assumption Overrides

### Architecture

Three layers of assumptions:
1. **Baseline** — hardcoded in `assumptions.py` (sourced defaults)
2. **Settings Overrides** — persisted globally to `data/settings/assumption_overrides.json`
3. **Scenario-Local Presets** — applied per-scenario via `assumption_override_preset_key`

### Override Catalog

Current curated coverage:

**Cooling profiles** (all 8 families):
- `pue_typical`, `COP_ref`, `k_fan`

**Redundancy profiles** (N, N+1, 2N, 2N+1):
- `eta_chain_derate`

**Miscellaneous**:
- `f_misc`

### Override Requirements
- Every override requires a **source citation** and **justification**
- Values are **range-validated** before persistence
- Override history is tracked at `data/settings/assumption_override_history.json`

### Impact Scope
- `static_and_hourly`: Changes both static PUE and hourly simulation
- `hourly_only`: Only affects 8,760-hour engine

### Runtime Resolution
```python
profile = get_effective_cooling_profile(cooling_type, override_preset_key)
# Returns baseline merged with:
#   1) Settings-persisted overrides
#   2) Scenario-local preset values
#   Last write wins
```

Files: `backend/engine/assumption_overrides.py`, `backend/api/routes_settings.py`

---

## 5. Engine Credibility & Compatibility

### Compatibility Levels

The engine uses a three-tier compatibility system:
- **compatible**: Technically supported and recommended
- **conditional**: Technically possible but niche/climate-limited/specialized
- **incompatible**: Should be rejected

### Current Conditional Rules
- AI/GPU + Water-Cooled Chiller: conditional at low density only
- Hyperscale + Dry Cooler: conditional
- Colocation Std + Dry Cooler: conditional
- Colocation HD + DLC: conditional
- HPC + Immersion: conditional at low/typical density
- AI/GPU + Immersion: conditional at low density

### RAG Status Refinements
- BLUE no longer awarded just for "free cooling eligible" label
- Hourly overtemperature hours now feed back into RAG for dry-cooler topology
- Rules: >0 overtemp hours prevents BLUE; >200 overtemp hours escalates to RED

Files: `backend/engine/assumptions.py`, `backend/engine/power.py`, `backend/api/routes_scenario.py`

---

## 6. API Reference

### Sites — 7 endpoints
| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/sites | Create site |
| GET | /api/sites/{id} | Get site |
| PUT | /api/sites/{id} | Update site |
| DELETE | /api/sites/{id} | Delete site |
| GET | /api/sites | List all sites |
| POST | /api/sites/upload-kml | KML upload |
| GET | /api/reference-data | Reference values |

### Scenarios — 8+ endpoints
| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/scenarios/run | Run single scenario |
| POST | /api/scenarios/batch | Batch run |
| GET | /api/scenarios/{id} | Get results |
| POST | /api/scenarios/rank | Score scenarios |
| POST | /api/scenarios/tornado | Sensitivity analysis |
| POST | /api/scenarios/break-even | Break-even solver |
| POST | /api/scenarios/load-mix | Load mix optimizer |
| POST | /api/scenarios/backup-power | Backup power comparison |
| POST | /api/scenarios/pue-breakdown | PUE decomposition |

### Climate — 4 endpoints
| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/climate/fetch | Open-Meteo weather |
| GET | /api/climate/{id} | Get cached weather |
| POST | /api/climate/analyze | Climate analysis |
| POST | /api/climate/upload-weather | Manual CSV upload |

### Green Energy — 3 endpoints
| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/green/dispatch | Hourly dispatch |
| POST | /api/green/firm-capacity | Firm capacity solver |
| POST | /api/green/fetch-pvgis-profile | PVGIS solar fetch |

### Grid Context — 3 endpoints
| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/grid/context | Fetch grid context |
| GET | /api/grid/context/{id} | Get cached result |
| DELETE | /api/grid/context/{id} | Delete cache |

### Export — 3 endpoints
| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/export/html | Generate HTML report |
| POST | /api/export/pdf | Generate PDF |
| POST | /api/export/excel | Generate Excel |

### Settings — 5+ endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | /api/settings/runtime-status | Runtime snapshot |
| POST | /api/settings/test-external-services | Service checks |
| POST | /api/settings/clear-cache | Cache operations |
| GET | /api/settings/assumption-overrides | List overrides |
| PUT | /api/settings/assumption-overrides | Update overrides |
| GET | /api/scenarios/guided-presets | Guided mode preset table |
| POST | /api/scenarios/guided-run | Run all 6 load types with presets |
| GET | /api/export/terrain-preview | Terrain map image for a site |

### 6.2 Guided Mode (Smart Preset Engine)

Source: `backend/engine/smart_preset.py`

The Guided Mode provides a one-click analysis where the user only selects sites. The system runs all 6 load types with fixed best-practice presets:

| Load Type | Cooling Topology | Density | Redundancy |
|-----------|-----------------|---------|------------|
| Colocation (Standard) | Air-Cooled Chiller + Economizer | typical (7 kW) | N+1 |
| Colocation (High Density) | Rear Door Heat Exchanger (RDHx) | typical (20 kW) | N+1 |
| HPC | Air-Cooled Chiller + Economizer | typical (40 kW) | N+1 |
| AI / GPU Clusters | Direct Liquid Cooling (DLC) | typical (100 kW) | N+1 |
| Hyperscale / Cloud | Air-Cooled Chiller + Economizer | typical (15 kW) | N+1 |
| Edge / Telco | Air-Cooled Chiller + Economizer | typical (5 kW) | N+1 |

All runs use `include_hourly=True` for climate-specific PUE via full 8,760-hour simulation. Results are scored and ranked server-side.

### 6.3 Terrain Maps

Source: `backend/export/terrain_map.py`

Uses `staticmap` library with OpenTopoMap tiles to generate terrain imagery for report site sections. No API key required. Gracefully degrades to SVG-only maps if `staticmap` is not installed or coordinates are unavailable.

---

## 7. Frontend Pages

| Route | Page | Key Features |
|-------|------|-------------|
| `/` | SiteManager | Site CRUD, KML upload, map, grid context |
| `/climate` | ClimateAnalysis | Weather fetch, CSV upload, climate analysis |
| `/scenarios` | ScenarioRunner | Guided mode (site-only) + Advanced mode (full manual selection) |
| `/results` | ResultsDashboard | Tab-based detail panel (Overview, Capacity, Infrastructure, Sensitivity, Expansion, Firm Capacity) |
| `/load-mix` | LoadMixPlanner | Workload allocation optimizer |
| `/green` | GreenEnergy | PV/BESS/FC dispatch simulation |
| `/export` | Export | Report generation (HTML/PDF/Excel) |
| `/settings` | Settings | Overrides, cache management, diagnostics |

---

## 8. Data Storage

All data is file-backed (no database):

```
backend/data/
├── sites/          ← Site JSON files
├── weather/        ← Cached weather per site
├── solar/          ← Cached PVGIS profiles per site
├── grid_context/   ← Cached grid context per site
└── settings/       ← Assumption overrides + history
```
