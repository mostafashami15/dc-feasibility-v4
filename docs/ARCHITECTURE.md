# DC Feasibility Tool v4 â€” Architecture & Roadmap Agreement

> **Status:** AGREED â€” Signed off by both parties. Development may begin.
> **Date:** March 2026
> **Participants:** Mostafa (Project Developer, Metlen) + Claude (AI Engineering Assistant)

---

## 0. Purpose of This Document

This document defines **every technical decision, formula source, architecture choice, and development phase** for the DC Feasibility Tool v4. Nothing gets coded until we both agree on the contents. When in doubt during development, we come back to this document.

---

## 1. What the Tool Does â€” Plain Language

You receive a candidate site for a data center (usually as a KML/KMZ file from your boss, sometimes just coordinates or an address). You also get constraints: land area, sometimes buildable area, sometimes building height, and sometimes power availability (STMG). Your job is to answer:

**"How much IT load can this site deliver, under what conditions, and how attractive is it?"**

The tool calculates this by combining:
- **Site geometry** â†’ how many racks physically fit
- **Power constraint** â†’ how much IT load the grid connection supports
- **Climate data** â†’ hourly cooling demand for 8,760 hours/year
- **Cooling technology** â†’ which system is used and its efficiency profile
- **Redundancy level** â†’ affects equipment sizing and procurement, not PUE
- **Green energy** â†’ PV, BESS, fuel cells to offset overhead demand

The output is a **feasibility report** showing the site's potential to a client: IT capacity, power requirements, PUE, infrastructure footprint, climate suitability, and recommendations.

---

## 2. Architecture Overview

### Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Backend** | Python 3.12 + FastAPI | You know Python; FastAPI is modern, fast, and has automatic API docs |
| **Frontend** | React 18 + TypeScript + Vite | Professional UI, interactive charts, clean component architecture |
| **Charts** | Recharts (React) + backend-generated inline SVG (reports) | Recharts for in-app; deterministic inline SVG for exported HTML/PDF visuals |
| **Styling** | Tailwind CSS | Utility-first, no custom CSS files to manage, consistent look |
| **Maps** | Leaflet.js (via react-leaflet) | Free, no API key needed, good for site location display |
| **Reports** | Jinja2 HTML templates -> PDF (via weasyprint) + Excel (openpyxl) | HTML as the master format; PDF derived from the same template |
| **State** | React Context + Zustand (lightweight) | Simple state management, no Redux complexity |
| **HTTP** | Axios | Clean API calls from frontend to backend |

### Project Structure

```
dc-feasibility-v4/
â”‚
â”œâ”€â”€ backend/                          â† Python (FastAPI + engine)
â”‚   â”œâ”€â”€ main.py                       â† FastAPI app entry point
â”‚   â”œâ”€â”€ api/
â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”œâ”€â”€ routes_site.py            â† Site CRUD endpoints
â”‚   â”‚   â”œâ”€â”€ routes_scenario.py        â† Run scenarios, get results
â”‚   â”‚   â”œâ”€â”€ routes_climate.py         â† Weather fetch, climate analysis
â”‚   â”‚   â”œâ”€â”€ routes_green.py           â† Green energy simulation
â”‚   â”‚   â””â”€â”€ routes_export.py          â† Report generation endpoints
â”‚   â”‚
â”‚   â”œâ”€â”€ engine/                       â† Pure calculation â€” ZERO UI dependency
â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”œâ”€â”€ models.py                 â† Pydantic data models (Site, Scenario, Result)
â”‚   â”‚   â”œâ”€â”€ assumptions.py            â† All defaults with source citations
â”‚   â”‚   â”œâ”€â”€ space.py                  â† Site geometry calculations
â”‚   â”‚   â”œâ”€â”€ power.py                  â† Power chain, redundancy, procurement
â”‚   â”‚   â”œâ”€â”€ cooling.py                â† COP model, cooling modes, hourly cooling load
â”‚   â”‚   â”œâ”€â”€ pue_engine.py             â† Hourly 8760 PUE simulation (the core)
â”‚   â”‚   â”œâ”€â”€ green_energy.py           â† PV, BESS, fuel cell dispatch
â”‚   â”‚   â”œâ”€â”€ climate.py                â† Climate analysis and suitability
â”‚   â”‚   â”œâ”€â”€ weather.py                â† Open-Meteo fetch, KML parse, geocoding
â”‚   â”‚   â”œâ”€â”€ footprint.py              â† Infrastructure area calculations
â”‚   â”‚   â”œâ”€â”€ ranking.py                â† RAG status, scoring, load mix optimizer
â”‚   â”‚   â”œâ”€â”€ sensitivity.py            â† Tornado chart, break-even analysis
â”‚   â”‚   â””â”€â”€ backup_power.py           â† Genset, fuel cell, hydrogen alternatives
â”‚   â”‚
â”‚   â”œâ”€â”€ export/
â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”œâ”€â”€ html_report.py            â† Jinja2 HTML report renderer
â”‚   â”‚   â”œâ”€â”€ pdf_export.py             â† HTML â†’ PDF via weasyprint
â”‚   â”‚   â”œâ”€â”€ excel_export.py           â† openpyxl structured workbook
â”‚   â”‚   â””â”€â”€ templates/                â† Jinja2 HTML report templates
â”‚   â”‚       â”œâ”€â”€ base.html
â”‚   â”‚       â”œâ”€â”€ executive_summary.html
â”‚   â”‚       â””â”€â”€ detailed_report.html
â”‚   â”‚
â”‚   â”œâ”€â”€ data/                         â† Runtime data storage
â”‚   â”‚   â”œâ”€â”€ sites/                    â† Saved site JSON files
â”‚   â”‚   â”œâ”€â”€ weather/                  â† Cached weather parquet files
â”‚   â”‚   â””â”€â”€ solar/                    â† Cached PVGIS data
â”‚   â”‚
â”‚   â”œâ”€â”€ tests/                        â† Unit tests for every engine module
â”‚   â”‚   â”œâ”€â”€ test_space.py
â”‚   â”‚   â”œâ”€â”€ test_power.py
â”‚   â”‚   â”œâ”€â”€ test_cooling.py
â”‚   â”‚   â”œâ”€â”€ test_pue_engine.py
â”‚   â”‚   â””â”€â”€ ...
â”‚   â”‚
â”‚   â””â”€â”€ requirements.txt
â”‚
â”œâ”€â”€ frontend/                         â† React + TypeScript
â”‚   â”œâ”€â”€ package.json
â”‚   â”œâ”€â”€ tsconfig.json
â”‚   â”œâ”€â”€ vite.config.ts
â”‚   â”œâ”€â”€ index.html
â”‚   â”œâ”€â”€ public/
â”‚   â”‚   â””â”€â”€ favicon.ico
â”‚   â””â”€â”€ src/
â”‚       â”œâ”€â”€ main.tsx                  â† App entry
â”‚       â”œâ”€â”€ App.tsx                   â† Router + layout
â”‚       â”œâ”€â”€ api/                      â† Axios API client functions
â”‚       â”‚   â””â”€â”€ client.ts
â”‚       â”œâ”€â”€ store/                    â† Zustand state stores
â”‚       â”‚   â””â”€â”€ useAppStore.ts
â”‚       â”œâ”€â”€ components/               â† Reusable UI components
â”‚       â”‚   â”œâ”€â”€ Layout.tsx
â”‚       â”‚   â”œâ”€â”€ Sidebar.tsx
â”‚       â”‚   â”œâ”€â”€ MapView.tsx
â”‚       â”‚   â””â”€â”€ charts/
â”‚       â”‚       â”œâ”€â”€ PUEChart.tsx
â”‚       â”‚       â”œâ”€â”€ CoolingModeChart.tsx
â”‚       â”‚       â””â”€â”€ ...
â”‚       â”œâ”€â”€ pages/                    â† Full page views
â”‚       â”‚   â”œâ”€â”€ SiteManager.tsx
â”‚       â”‚   â”œâ”€â”€ ScenarioRunner.tsx
â”‚       â”‚   â”œâ”€â”€ ResultsDashboard.tsx
â”‚       â”‚   â”œâ”€â”€ ClimateAnalysis.tsx
â”‚       â”‚   â”œâ”€â”€ GreenEnergy.tsx
â”‚       â”‚   â”œâ”€â”€ Settings.tsx
â”‚       â”‚   â””â”€â”€ Export.tsx
â”‚       â””â”€â”€ types/                    â† TypeScript type definitions
â”‚           â””â”€â”€ index.ts
â”‚
â”œâ”€â”€ docs/                             â† Project documentation
â”‚   â”œâ”€â”€ HANDBOOK.md                   â† Living handbook (built incrementally)
â”‚   â”œâ”€â”€ FORMULAS.md                   â† Every formula with source citation
â”‚   â”œâ”€â”€ ASSUMPTIONS.md                â† Every default value with justification
â”‚   â””â”€â”€ CHANGELOG.md                  â† Version history
â”‚
â””â”€â”€ README.md
```

### Key Architecture Principles

1. **Engine is pure Python with zero UI imports.** You can run any calculation from a Python script or test without starting the server. This is non-negotiable â€” it's what makes the model trustworthy and testable.

2. **Every number has a source.** No default value exists without a comment saying where it comes from. If we can't source it, we mark it as "engineering judgment" with a range and let the user override it.

3. **One calculation path, no duplicates.** The v3 model had `rho_IT_kW_per_m2` as a parallel path â€” we will never have two ways to compute the same thing. One formula, one function, one result.

4. **Pydantic models for all data.** Every site, scenario, and result is a Pydantic model with validation. This catches bad inputs before they reach the engine.

5. **Incremental testing.** Every engine module gets tests before we move to the next module. You'll run tests with Claude Code to verify.

---

## 3. Technical Decisions â€” Every Question Answered

### 3.1 The Two Modes

**Power-Constrained (STMG available):**

The user enters "Available Power (MW)" and selects what this value represents:

**Option A â€” "Operational facility power" (grid delivers this for operations):**
```
facility_power = entered value (e.g. 100 MW)
IT Load = facility_power Ã— Î·_chain / PUE
procurement_power = facility_power Ã— procurement_factor (for equipment sizing)
Compare with: Site geometry â†’ max racks by space â†’ IT Load from space
Binding constraint = whichever is smaller
```
Use when: The STMG value represents usable operational power. Redundancy is internal â€”
two power paths exist but the site draws up to the full entered amount in normal operation.

**Option B â€” "Total grid reservation including redundancy":**
```
procurement_power = entered value (e.g. 100 MW)
facility_power = entered value / procurement_factor (e.g. 50 MW for 2N)
IT Load = facility_power Ã— Î·_chain / PUE
Compare with: Site geometry â†’ max racks by space â†’ IT Load from space
Binding constraint = whichever is smaller
```
Use when: The STMG document states the total reserved grid capacity, which already
accounts for redundant power paths.

**Area-Constrained (no STMG):**
```
Site geometry â†’ max racks by space â†’ IT Load (MW) â†’ multiply by PUE â†’ Facility Power
Apply procurement factor â†’ Procurement Power (what to request from grid)
```

Both modes use the same underlying engine. The only difference is which variable is the input and which is the output. The results dashboard always shows all three numbers clearly labelled: IT Load, Facility Power, and Procurement Power.

### 3.2 COP Model

**Default: Linear model (feasibility-grade)**
```
COP(T) = COP_ref + COP_slope Ã— (T_ref âˆ’ T_cond_driver)
clamped to [COP_min, COP_max]
```

**Source:** ASHRAE Handbook â€” HVAC Systems and Equipment, Chapter 38 (Compressor performance approximation). The linear model is a first-order Taylor expansion of the Carnot COP around a reference operating point.

**T_cond_driver selection:**
- Air-cooled systems â†’ dry-bulb temperature (T_db)
- Water-cooled systems (cooling tower) â†’ wet-bulb temperature (T_wb)

**Source for T_wb selection:** ASHRAE Fundamentals, Chapter 1: Cooling towers reject heat to the wet-bulb temperature, not the dry-bulb. The leaving condenser water temperature from a cooling tower tracks T_wb + approach (typically 3â€“5Â°C).

**Wet-bulb formula:** Stull (2011) approximation:
```
T_wb = T Ã— atan(0.151977 Ã— âˆš(RH + 8.313659)) + atan(T + RH)
       âˆ’ atan(RH âˆ’ 1.676331) + 0.00391838 Ã— RH^1.5 Ã— atan(0.023101 Ã— RH) âˆ’ 4.686035
```
**Source:** Stull, R. (2011). "Wet-Bulb Temperature from Relative Humidity and Air Temperature." Journal of Applied Meteorology and Climatology, 50(11), 2267â€“2269.

**Enhanced option (Phase 2+):** Allow upload of manufacturer COP data table (COP vs ambient temperature at rated conditions). Interpolate using scipy. This replaces the linear model when available.

**Per-topology COP defaults (all sourced):**

| Topology | COP_ref | COP_min | COP_max | T_ref | Source |
|----------|---------|---------|---------|-------|--------|
| CRAC (DX) | 3.5 | 2.0 | 5.5 | 35Â°C | Typical scroll compressor DX unit. Ref: Emerson/Copeland Selection Software typical operating range. |
| AHU (no econ) | 4.5 | 2.5 | 7.0 | 35Â°C | Central air-cooled chiller, better than DX. Ref: Carrier 30XA datasheet typical range. |
| Air Chiller + Econ | 5.5 | 2.5 | 9.0 | 35Â°C | High-efficiency air-cooled screw chiller. Ref: Carrier 30XA/30XV at Eurovent conditions. |
| Water Chiller + Econ | 7.0 | 3.5 | 12.0 | 35Â°C (wb) | Water-cooled centrifugal chiller. Ref: Trane CenTraVac, AHRI 550/590 rating. |
| RDHx | 5.5 | 2.5 | 9.0 | 35Â°C | Same chiller as Air Chiller + Econ (RDHx is a distribution method, not a chiller type). |
| DLC (warm water) | 7.0 | 4.0 | 12.0 | 35Â°C | Warm water supply (35Â°C) enables higher evaporator temp â†’ higher COP floor. Ref: Asetek/CoolIT warm water DLC datasheets. |
| Immersion | 8.0 | 4.5 | 15.0 | 35Â°C | Even warmer fluid (40Â°C) â†’ even higher COP floor. Ref: GRC/LiquidCool published performance data. |
| Dry Cooler (chiller-less) | 12.0 | 5.0 | 20.0 | 20Â°C | No compressor; COP represents fan power only. Ref: Airedale/GÃ¼ntner dry cooler fan power curves. |

### 3.3 Hourly Facility Power Formula

```
P_facility(t) = P_IT(t) Ã— (1 + a(t)) + b(t)

Where:
  a(t) = elec_loss + k_fan + cool_kW_per_kW_IT(t) + [k_econ if economizer active]
  b(t) = P_available_kW Ã— f_misc

  elec_loss = (1 / Î·_chain) âˆ’ 1
  k_fan = fan/pump power as fraction of IT load (topology-specific)
  f_misc = miscellaneous fixed loads as fraction of available power (lighting, BMS, security)
```

**Implementation note on b(t):** In the hourly engine (pue_engine.py), the b term is computed as:
- Power-constrained mode: `b = P_facility Ã— f_misc` (P_facility â‰ˆ P_available in practice)
- Area-constrained mode: `b = P_IT Ã— f_misc` (approximation; introduces ~0.02% error, negligible for feasibility)

This avoids a circular dependency in area-constrained mode where P_facility is what we're solving for. The approximation error is `f_misc Ã— (PUEâˆ’1) Ã— f_misc â‰ˆ 0.025 Ã— 0.3 Ã— 0.025 â‰ˆ 0.02%`.

**Source:** This is the standard overhead decomposition used in the Uptime Institute's PUE measurement methodology and the EU Code of Conduct on Data Centre Energy Efficiency (JRC Technical Report, 2022).

**Cooling load per unit IT load:**
```
MECH mode:
  cool_kW/kW_IT = (1 + elec_loss + k_fan + f_misc) / COP(T)
  [Numerator = total heat to reject: IT + electrical losses + fan heat + misc]

ECON_PART mode:
  blend = (T_amb âˆ’ T_econ_full) / (T_mech âˆ’ T_econ_full), clamped [0, 1]
  cool_kW/kW_IT = blend Ã— (1 + elec_loss + k_fan + f_misc) / COP(T)

ECON_FULL mode:
  cool_kW/kW_IT = 0
  [Compressor off. Residual overhead captured by k_econ in a(t)]
```

**Source for heat rejection numerator including k_fan:** ASHRAE 90.4 (Energy Standard for Data Centers), Section 6.4.3. Fan motors inside the data hall add their electrical input as heat that must be removed by the cooling plant. This is the v3 correction and it is physically correct.

**Source for ECON_FULL = 0:** When the compressor is off, there is no refrigerant cycle. Dividing by COP is meaningless. The only parasitic loads are economizer pump and fans, captured by k_econ (typically 1â€“2% of IT load). Ref: ASHRAE TC 9.9, "Thermal Guidelines for Data Processing Environments."

### 3.4 Annual PUE (Energy-Weighted)

```
PUE_annual = Î£_{t=1}^{8760} P_facility(t) / Î£_{t=1}^{8760} P_IT(t)
```

**Source:** Uptime Institute, "PUE: A Comprehensive Examination of the Metric" (2014). The Green Grid, "PUEâ„¢: A Comprehensive Examination" (White Paper #49). This is the only correct definition. The arithmetic average of hourly PUE values is NOT the same and must NOT be used.

### 3.5 Procurement Power

**What it is:** The electrical capacity you formally request from the grid operator (Terna/e-distribuzione in Italy, via the STMG â€” Soluzione Tecnica Minima Generale â€” process). This is the capacity the grid reserves for your site. It determines:
- Your connection fee and annual capacity charge
- The physical size of the HV/MV substation and transformers
- The kVA rating of your incoming utility transformers

**What it is NOT:** It is not your operational power draw. A 2N site with 20 MW facility power requests 40 MW from the grid, but never draws more than ~20 MW in normal operation. The second power path sits idle, ready for failover.

**The ambiguity problem:** When your boss gives you an STMG value (e.g. "100 MW"), it can mean two different things depending on the project:
- **Case A:** 100 MW is what the site can draw operationally. The 2N equipment inside is doubled, but grid delivers up to 100 MW. Procurement power = 100 MW Ã— 2.0 = 200 MW of equipment capacity.
- **Case B:** 100 MW is the total grid reservation. For a 2N design, operational power = 100 MW / 2.0 = 50 MW.

**How the model handles this:** The user selects "This power value represents: Operational facility power / Total grid reservation" when entering each site. See Section 3.1 for the calculation paths. This choice is stored per site.

**Procurement factors by redundancy:**

| Redundancy | procurement_factor | Explanation |
|------------|-------------------|-------------|
| N | 1.00 | Single path, no overhead |
| N+1 | 1.15 | One spare component per group; ~15% oversizing |
| 2N | 2.00 | Two complete paths; grid sees 2Ã— |
| 2N+1 | 2.00 | Two paths + one spare; grid still sees 2Ã— (spare is within a path) |

**Source:** Uptime Institute Tier Standard: Topology (2018), Sections on Capacity and Redundancy Requirements.

### 3.6 Redundancy Effects â€” What It Does and Doesn't Do

Redundancy has **exactly two effects** and nothing else:

1. **eta_chain_derate (small operational effect):** In a 2N system, each UPS carries only 50% of the IT load. UPS modules are slightly less efficient at partial load (due to fixed losses in the rectifier and inverter). This makes elec_loss slightly larger, which propagates into PUE. The magnitude is small: ~0.5â€“1% on PUE.

2. **procurement_factor (sizing effect only):** How much capacity to request from the grid. Affects the physical infrastructure size (transformers, switchgear, generators) and therefore footprint. Does NOT affect PUE, operational power, or IT capacity.

**What redundancy does NOT do:** It does NOT multiply PUE. The v1 model did this incorrectly â€” it applied an `overhead_factor` that inflated PUE by the redundancy level. This is physically wrong. A 2N UPS system does not consume twice the electricity; only one path is active.

**Source:** Uptime Institute, "Tier Standard: Operational Sustainability" (2020). IEEE 3006.7 (Recommended Practice for UPS Systems).

### 3.7 The PUE Paradox â€” Committed vs. Average IT Capacity

**The problem you described:** Annual PUE of 1.21 with 100 MW facility â†’ average IT â‰ˆ 82.6 MW. But in the hottest hour, available IT drops to ~65 MW. The annual average is misleading because it includes winter hours when cooling is nearly free.

**What data center developers do in practice:**

The industry standard is to **commit IT capacity to the worst-case (or near worst-case) hour.** Specifically:

| Metric | Definition | Use |
|--------|-----------|-----|
| **Design IT Capacity** (worst hour) | Minimum IT load across all 8,760 hours | Conservative commitment â€” guaranteed at all times |
| **P99 IT Capacity** | IT load available 99% of the year (8,672 hours) | Typical SLA commitment â€” allows 88 hours of potential curtailment |
| **P90 IT Capacity** | IT load available 90% of the year | Aggressive commitment, common for hyperscalers with flexibility |
| **Annual Mean IT Capacity** | Average across all hours | For energy billing and annual cost estimates only â€” NOT for SLA |

**Source:** Uptime Institute, "Data Center Site Infrastructure Tier Standard" (2018). The design IT capacity must be available at all times for Tier III/IV certification. The P99/P90 approach is common in hyperscale (Google, Microsoft published discussions of "effective capacity" in this way).

**What we show the client:**
1. **Committed IT Capacity** = P99 value (available 99% of the year) â€” this is the number you sell
2. **Peak IT Capacity** = best hour (winter night) â€” shows the upside potential
3. **Summer Minimum IT Capacity** = worst hour â€” shows the constraint
4. **Annual Mean** = for energy cost estimates

**Compensating the summer deficit:**
The gap between committed (P99) and worst-hour capacity can be addressed by:
- BESS discharge during peak cooling hours (charges at night when cooling is low)
- Fuel cell dispatch during peak hours
- Partial IT load shedding (if tenant SLA allows)
- Oversizing the utility connection to absorb the peak (most common in practice)

We will model the first two options in the Green Energy module. The third is a contractual decision, not a physics one. The fourth is the default behavior of the power-constrained mode.

### 3.8 Backup Power Technologies

**Regulatory context (Italy):** The MASE (Ministero dell'Ambiente e della Sicurezza Energetica) and recent EU guidelines are moving toward limiting diesel genset hours for new data centers. Annual runtime limits and emissions caps are being discussed. New builds should plan for alternatives.

**Technologies we will model:**

| Technology | Type | Efficiency | Module Size | Ramp Time | Fuel | Emissions | Footprint |
|-----------|------|-----------|-------------|-----------|------|-----------|-----------|
| Diesel Genset | Backup only | 35â€“40% electrical | 1â€“3 MW/unit | 10â€“15 sec | Diesel | High (COâ‚‚ + NOx + PM) | 0.008 mÂ²/kW |
| Natural Gas Genset | Backup/prime | 38â€“42% electrical | 1â€“5 MW/unit | 30â€“60 sec | Natural Gas | Medium (COâ‚‚, low NOx) | 0.010 mÂ²/kW |
| SOFC Fuel Cell (e.g. Bloom Energy) | Prime power | 55â€“65% electrical | 250 kW/module | Minutes (warm start) | NG / Biogas / Hâ‚‚ | Low (COâ‚‚ only, no combustion) | ~0.015 mÂ²/kW |
| PEM Fuel Cell (Hâ‚‚) | Backup/prime | 45â€“55% electrical | 100â€“500 kW | Seconds | Green Hâ‚‚ | Zero (water only) | ~0.020 mÂ²/kW |
| Rotary UPS + Flywheel | Bridge power (15â€“60 sec) | 95%+ pass-through | 1â€“3 MW | Instant | None (kinetic) | Zero | 0.005 mÂ²/kW |

**Source for Bloom Energy specs:** Bloom Energy Server ES5 datasheet (2023): 300 kW AC per module, 65% electrical efficiency on natural gas, footprint 1.05m Ã— 3.65m per module.

**What the model does with this:** User selects backup power technology. The model calculates: (a) number of units needed for the procurement power rating, (b) total footprint, (c) annual fuel consumption if used as prime power, (d) COâ‚‚ emissions comparison vs diesel baseline. The backup power choice does NOT affect PUE or IT capacity â€” it's a parallel infrastructure decision.

### 3.9 Green Energy â€” Compensating Overhead

**The dispatch model (same logic as v3, but cleaner implementation):**

```
For each hour t:
  overhead_kW(t) = P_facility(t) âˆ’ P_IT(t)

  1. PV generation â†’ apply to overhead
  2. Surplus PV â†’ charge BESS (bounded by capacity and round-trip efficiency)
  3. Remaining surplus â†’ export to grid (or curtail)
  4. Remaining deficit â†’ discharge BESS
  5. Remaining deficit â†’ fuel cell dispatch
  6. Remaining deficit â†’ grid import
```

**PV model source:** PVGIS (EU JRC Photovoltaic Geographical Information System). Hourly AC output for given location, system size, tilt, azimuth. The PVGIS model accounts for temperature derating, inverter efficiency, cable losses, soiling, and module degradation.

**BESS model:**
```
Î·_roundtrip â‰ˆ 0.85â€“0.90 (lithium-ion, source: NREL ATB 2024)
Î·_oneway = âˆš(Î·_roundtrip)
SoC(t+1) = SoC(t) + charge(t) Ã— Î·_oneway âˆ’ discharge(t) / Î·_oneway
SoC bounded [0, capacity_kWh]
```

**Known simplifications (documented, acceptable for feasibility):**
- No C-rate limit on BESS (conservative for feasibility)
- No battery degradation over project life
- No behind-the-meter grid export constraints
- Fuel cell fuel source not detailed (treated as clean dispatchable)

**Additional green options to consider (Phase 2+):**
- Wind turbines (if site has wind resource â€” relevant for coastal or elevated sites)
- Waste heat recovery to district heating (relevant in Italy â€” can offset cooling cost and generate revenue)
- Grid carbon intensity time-of-use optimization

### 3.10 Climate Data â€” Historical and Future

**Historical (baseline):**
- Source: Open-Meteo Archive API (free, no API key)
- Method: Fetch 5 years (2019â€“2023), average hour-by-hour to produce one representative 8,760-row year
- Variables: T_drybulb (required), RH (recommended), T_dewpoint (optional)
- Fallback: manual upload of Open-Meteo Excel export

**Future projection (design life):**
- Method: Temperature delta approach (simple, transparent, industry-standard for feasibility)
- Deltas: +0.5Â°C, +1.0Â°C, +1.5Â°C, +2.0Â°C applied uniformly to historical baseline
- Shows impact on: PUE, free cooling hours, MECH hours, committed IT capacity

**Source for delta approach:** CIBSE TM49 (2014): "Design Summer Years for London." The delta method is the recommended approach for building services engineering when full climate model outputs are not available. For Southern Europe, IPCC AR6 WG1 Chapter 12 projects +1.5â€“2.5Â°C by 2050 under SSP2-4.5.

**Why not full climate model data:** CMIP6 downscaled projections require bias correction, statistical post-processing, and careful interpretation. This is PhD-level climate science work that adds months of development for marginal accuracy improvement at the feasibility stage. The delta approach captures the key sensitivity (how does +XÂ°C affect our numbers?) without the complexity.

### 3.11 Footprint Factors

All infrastructure footprint defaults will be sourced and documented:

| Element | Default | Source |
|---------|---------|--------|
| Cooling skid (roof) | 0.10â€“0.30 mÂ²/kW rejected (varies by type) | Carrier/Trane condenser selection guides; typical air-cooled condenser: 0.15 mÂ²/kW |
| Diesel genset | 0.008 mÂ²/kW procurement | Caterpillar/Cummins genset dimension tables (C32/QSK60 series including enclosure + fuel tank) |
| Transformer | 0.004 mÂ²/kW | ABB/Siemens MV/LV transformer datasheets (2000 kVA class, including oil bund) |
| Substation | 0.005 mÂ²/kW | Typical MV switchgear room sizing per IEC 62271-200 |
| SOFC fuel cell | 0.015 mÂ²/kW | Bloom Energy Server ES5 datasheet dimensions |
| PEM fuel cell | 0.020 mÂ²/kW | Ballard/Plug Power module dimension guides |

### 3.12 Load Mix Optimization

**New feature:** Given total IT capacity X MW, suggest optimal allocation across workload types.

**Method:**
1. User selects which workload types to consider (e.g., HPC + AI + Hyperscale)
2. Engine generates combinations in 5% or 10% increments of total IT
3. For each combination: compute rack count per type, verify cooling compatibility, compute blended PUE (weighted by IT share), compute total footprint
4. Rank by composite score: PUE efficiency, space utilization, cooling compatibility
5. Present top 5 combinations with trade-off explanation

**Constraints:** Each load type has a minimum viable allocation (you can't run 0.5 MW of AI â€” you need at least a few racks). The minimum is: `min_racks Ã— rack_density_kW / 1000` MW, where min_racks = 10 (configurable).

### 3.13 Hardcoded PUE â€” When to Use

**Rule:** We NEVER show a hardcoded PUE as the final result when weather data is available. Static PUE values from the cooling profiles (pue_min/typical/max) are used ONLY:
- As a quick sanity check during site entry (before weather data is loaded)
- For the area-constrained PUE sensitivity table (showing range of procurement power)
- As a fallback when weather data is genuinely unavailable (no internet, no manual file)

When weather data exists, the hourly engine always runs and its energy-weighted PUE replaces the static value.

### 3.14 White Space Calculation â€” Standards and Sources

**Site Coverage Ratio (building footprint / land area):**
- Comes from local zoning and building codes. In Italy, the "indice di copertura" typically ranges from 0.30â€“0.60 for industrial zones (Zone D in PRG/PGT).
- Default: 0.50 (midpoint for industrial/logistics parks).
- **Always override with actual planning permission value when available.**

**Whitespace Ratio (IT hall area / gross building area):**
- Uptime Institute Tier III/IV design guides: 40â€“45% of gross building area for IT white space is typical for purpose-built data centers.
- DCD Intelligence benchmarking: 35â€“45% IT floor ratio for European colocation facilities.
- Remaining 55â€“65% covers: power rooms (~15%), cooling plant rooms (~10%), loading/staging (~5%), offices/NOC (~5%), corridors/structure (~15â€“20%).
- Default: 0.40 (reasonable midpoint for feasibility).
- **Source:** Uptime Institute, "Data Center Site Infrastructure Tier Standard" (2018); ASHRAE 90.4.

**Rack Footprint (mÂ² per rack including hot/cold aisle):**
- Standard 42U rack body: 0.6m Ã— 1.07m = 0.64 mÂ².
- With hot/cold aisle containment (1.2m cold aisle + 1.2m hot aisle, shared between rows): 2.5â€“3.5 mÂ²/rack.
- Default: 3.0 mÂ²/rack (industry midpoint).
- **Source:** ASHRAE TC 9.9, "Thermal Guidelines for Data Processing Environments" (aisle width recommendations).

**Floor-to-Floor Height:**
- ASHRAE TC 9.9 minimum: 4.0m clear height.
- Typical single-story DC: 4.5â€“5.5m (with raised floor and overhead cable trays).
- Multi-story: 4.0â€“4.5m per floor.
- Default: 4.5m.

### 3.15 Cooling Type Impact on White Space

Different cooling systems consume different amounts of data hall floor space. The model applies a `whitespace_adjustment_factor` per cooling type to the effective rack count:

```
effective_racks = max_racks_by_space Ã— whitespace_adjustment_factor
```

| Cooling Type | Adjustment Factor | Reason | Source |
|-------------|------------------|--------|--------|
| CRAC (DX) | 0.92 | Floor-standing CRAC units consume ~8% of white space (~3â€“4 mÂ² per 100 kW unit) | Schneider Electric White Paper 130: CRAC unit sizing and placement |
| AHU (no econ) | 1.00 | AHU in separate plant room, no IT hall impact | Standard practice â€” AHU rooms are outside white space |
| Air Chiller + Econ | 1.00 | Same as AHU | â€” |
| Water Chiller + Econ | 1.00 | Same as AHU | â€” |
| RDHx | 1.00 | Rear door adds depth but no floor area loss | Rack width unchanged; aisle geometry preserved |
| DLC (Cold Plate) | 0.92 | In-row CDUs take ~1 rack slot per 12 racks (~8% loss) | Asetek/CoolIT CDU installation guides |
| Immersion (Single-Phase) | 0.85 | Tank layout differs from rack layout; tanks wider, need service access | GRC/Submer/LiquidCool tank dimension datasheets |
| Dry Cooler (chiller-less) | 1.00 | Standard air distribution in IT hall | â€” |

All factors are user-overridable. These defaults are engineering judgment based on published equipment dimensions and standard layout practices.

### 3.16 Load Type Rack Densities (Verified March 2026)

| Load Type | Low kW/rack | Typical kW/rack | High kW/rack | Source |
|-----------|------------|----------------|-------------|--------|
| Colocation (Standard) | 4 | 7 | 12 | Uptime Institute Annual Survey 2023: median colo = 7 kW. CBRE Data Center Solutions: 4â€“12 kW range. |
| Colocation (High Density) | 12 | 20 | 35 | DCD Intelligence 2024: 20â€“30 kW offerings. Equinix xScale: up to 35 kW. |
| HPC | 20 | 40 | 60 | TOP500 analysis: 30â€“50 kW typical. ORNL Frontier: ~60 kW with liquid cooling. |
| AI / GPU Clusters | 40 | 100 | 140 | NVIDIA DGX H100 4-per-rack = 40 kW (low). GB200 NVL72 = 120 kW, HPE reports 132 kW (typical ~100). GB300 NVL72 = 142 kW (high). Source: NVIDIA DGX user guides, HPE QuickSpecs, TrendForce. |
| Hyperscale / Cloud | 8 | 15 | 25 | Google/Microsoft/Meta published designs: 12â€“20 kW typical. AWS: up to 25 kW. |
| Edge / Telco | 2 | 5 | 8 | ETSI MEC standards: 2â€“5 kW typical. Telco central offices: up to 8 kW. |

**Future-proofing note:** NVIDIA Vera Rubin NVL144 (2H 2026) is expected at 120â€“130 kW/rack. Rubin Ultra NVL576 (2027) targets up to 600 kW/rack. The model supports user-defined custom densities for next-generation hardware. Defaults reflect what is commercially deployable as of March 2026.

**Compatible cooling per load type:**

| Load Type | Compatible Cooling Types |
|-----------|------------------------|
| Colocation (Standard) | CRAC, AHU, Air Chiller+Econ, Water Chiller+Econ, RDHx, Dry Cooler |
| Colocation (High Density) | Air Chiller+Econ, Water Chiller+Econ, RDHx, DLC |
| HPC | Air Chiller+Econ, Water Chiller+Econ, RDHx, DLC, Immersion |
| AI / GPU Clusters | DLC, Immersion, Water Chiller+Econ (at low density only) |
| Hyperscale / Cloud | Air Chiller+Econ, Water Chiller+Econ, RDHx, Dry Cooler |
| Edge / Telco | CRAC, AHU, Air Chiller+Econ |

### 3.17 RAG Status System (4 Levels)

**ðŸ”´ RED â€” Fatal (scenario not viable):**
- Rack density exceeds cooling type maximum capacity
- IT load < 0 MW (physically impossible)
- Overtemperature hours > 200/year for chiller-less topology
- Building height insufficient for even 1 floor (if height constraint specified)
- Incompatible cooling + load type combination (e.g., CRAC with 100 kW AI racks)

**ðŸŸ¡ AMBER â€” Warning (viable but with significant constraints):**
- Area is the binding constraint (power headroom exists but no space)
- Power headroom < 1 MW (nearly maxed out)
- IT load < 1 MW (very small â€” may not be economically viable)
- Overtemperature hours 50â€“200/year for chiller-less topology
- Committed IT capacity (P99) is more than 20% below annual mean (high climate variability)
- Rack count < 50 (minimum viable data center questionable)
- Building coverage ratio > 0.70 (tight site, limited outdoor equipment space)

**ðŸŸ¢ GREEN â€” Good (scenario viable and attractive):**
- All checks pass
- No RED or AMBER conditions triggered
- Compatible cooling + load combination
- Overtemperature hours < 50 (or 0 for non-chiller-less)

**ðŸ”µ BLUE â€” Excellent (highlights best scenarios):**
- All GREEN conditions met, PLUS at least two of:
  - Annual PUE < 1.20 (very efficient)
  - Committed IT / facility power > 0.70 (good utilization ratio)
  - Free cooling (ECON_FULL) > 60% of annual hours
  - Power headroom > 5 MW (room for growth)

**Evaluation order:** RED conditions checked first. If any RED triggers, stop. Then AMBER. If any AMBER triggers, status = AMBER. Then BLUE conditions. If BLUE criteria met, status = BLUE. Otherwise GREEN.

---

## 4. What the v3 Model Got Right (We Keep These)

1. The facility power formula structure: `P_facility(t) = P_IT(t) Ã— (1 + a(t)) + b(t)`
2. Energy-weighted annual PUE definition
3. The two-effect redundancy model (eta_chain_derate + procurement_factor)
4. v3 corrections: k_fan in heat rejection numerator, ECON_FULL = 0, wet-bulb for water-cooled COP
5. Per-topology k_fan defaults
6. DLC/Immersion dry cooler approach temperature corrections
7. Overtemperature hour tracking for chiller-less topology
8. Green energy dispatch priority (PV â†’ BESS â†’ FC â†’ grid)
9. 5-year weather averaging strategy
10. KML parsing and geocoding

## 5. What the v3 Model Got Wrong (We Fix These)

1. **Parameter sprawl:** Too many overlapping dicts (SPACE, COOLING_PROFILES, LOAD_PROFILES, POWER_LOSSES, CLIMATE, FOOTPRINT) with unclear override precedence. v4 uses Pydantic models with explicit defaults and validation.

2. **Redundant calculation paths:** `rho_IT_kW_per_m2` was a parallel IT load computation inconsistent with the rack-based calculation. v4 has one path only.

3. **Session state chaos:** Streamlit session_state with ~20 keys, fragile across page transitions. v4 has a clean API with stateless endpoints.

4. **No distinction between committed and average IT capacity.** The client sees one number (annual average) that overpromises. v4 shows worst/P99/P90/mean with clear labels.

5. **Reporting was afterthought.** PDF had inconsistent fonts and sizing. v4 builds reports as first-class HTML templates with CSS theming, then converts to PDF.

6. **No backup power alternatives.** Only diesel gensets. v4 includes fuel cells and hydrogen.

7. **No load mix optimization.** Single workload type per scenario. v4 adds multi-load allocation.

8. **Sensitivity analysis was limited.** Only one-at-a-time parameter variation. v4 adds scenario comparison and what-if capability.

9. **RAG system too simple.** Only 3 levels with basic conditions. v4 has 4 levels (RED/AMBER/GREEN/BLUE) with comprehensive evaluation criteria.

10. **No cooling impact on white space.** All cooling types used the same rack count. v4 applies a whitespace_adjustment_factor per cooling type (CRAC consumes floor space, DLC needs CDUs, immersion uses tanks).

11. **Power input ambiguity.** No way to specify whether the STMG value is operational power or grid reservation. v4 has a clear two-option selector per site.

12. **Rack densities outdated.** AI rack densities did not reflect current GB200/GB300 data. v4 uses verified March 2026 data from NVIDIA, HPE, and TrendForce sources.

---

## 6. UI Pages â€” What the User Sees

### Page 1: Site Manager
- Add/edit/delete candidate sites
- Upload KML/KMZ or enter coordinates manually
- Geocoding (type city name â†’ get coordinates)
- Map preview (Leaflet, no API key)
- Site geometry preview (buildable area, floors, whitespace, max racks)
- Per-site weather fetch status

### Page 2: Climate & Weather
- Per-site climate profile (auto-fetched or manual upload)
- Temperature distribution charts (daily, not hourly â€” cleaner visualization)
- Free cooling hours analysis
- Suitability rating (EXCELLENT/GOOD/MARGINAL/NOT RECOMMENDED)
- Climate projection slider (delta approach)

### Page 3: Scenario Configuration
- Select sites, load types, cooling types, redundancy, density
- Show combination count
- Advanced: assumptions overrides (COP, k_fan, chain efficiency)
- Run button â†’ triggers batch calculation

### Page 4: Results Dashboard (the main deliverable)
- **Site Overview Cards:** One card per site showing best scenario, IT capacity, RAG status
- **Scenario Comparison Table:** All scenarios ranked by score, filterable
- **Detailed Scenario View** (selected scenario):
  - Headline metrics: IT capacity (committed P99), facility power, procurement power, PUE, racks
  - PUE decomposition (4 components: electrical, fans, cooling, misc)
  - Cooling mode breakdown (MECH/ECON_PART/ECON_FULL hours and energy %)
  - IT capacity spectrum (worst/P99/P90/mean/best)
  - Monthly climate + performance summary
  - Infrastructure footprint
  - Backup power technology comparison
  - In-building power uplift plan (if power-bound)
  - Expansion plan (if expansion floors defined)
- **Load Mix Optimizer** (if requested)
- **Sensitivity Analysis** (tornado chart)
- **Break-Even Finder**

### Page 5: Green Energy
- PV configuration (auto-fetch from PVGIS or manual upload)
- BESS sizing
- Fuel cell configuration
- Hourly dispatch visualization
- Renewable fraction, overhead coverage, COâ‚‚ avoided
- Impact on committed IT capacity (with/without green compensation)

### Page 6: Reports & Export
- Report template selection (executive vs detailed)
- Theme/branding configuration (logo, colors, fonts)
- Generate HTML (preview in browser)
- Download PDF
- Download Excel workbook

### Page 7: Settings
- Global assumption defaults (with source citations visible)
- Power chain efficiency
- Hourly engine parameters
- Connection test (Open-Meteo reachability)
- Data management (save/load/clear sites)

---

## 7. Report Design

**Master format:** HTML (Jinja2 template + CSS)

**Why HTML first:**
- You can preview it in any browser before converting to PDF
- CSS gives precise control over fonts, colors, spacing, page breaks
- Same template, same numbers, same look every time
- weasyprint converts HTML â†’ PDF with near-perfect fidelity
- No more font/size inconsistencies

**Report types:**

| Report | Audience | Length | Content |
|--------|----------|--------|---------|
| Executive Summary | Boss, client, investor | 2â€“3 pages | Best scenario per site, key metrics, RAG, climate suitability, site map, recommendation |
| Detailed Technical | Engineering team | 8â€“15 pages | Full scenario matrix, PUE decomposition, cooling modes, sensitivity, footprint, green energy, monthly data |

**Excel workbook:** For raw data export. Contains all numbers, all scenarios, all hourly data (if requested). For analysts who want to do their own calculations.

**Theme:** Configurable via a simple config file (primary color hex, secondary color hex, logo image, font choice). Default: clean, professional, minimal.

---

## 8. Development Phases â€” The Roadmap

Each phase is complete and tested before moving to the next. You and I review the output of each phase before proceeding.

### âœ… Phase 0: Project Setup (Day 1) â€” COMPLETE
- Created project directory, Python venv, React app, Claude Code
- **Deliverable:** Empty project skeleton, both servers running

### âœ… Phase 1: Engine Core â€” Space & Power (Week 1) â€” COMPLETE
- `models.py` â€” Pydantic data models (33 tests passing)
- `assumptions.py` â€” All defaults with source citations
- `space.py` â€” Site geometry calculations (15 tests)
- `power.py` â€” Power chain, redundancy, procurement (18 tests)
- **Deliverable:** Can compute max racks, IT load, facility power, procurement power from Python CLI

### âœ… Phase 2: Engine Core â€” Cooling & PUE (Week 2) â€” COMPLETE
- `cooling.py` â€” COP model, cooling modes, per-topology parameters
- `pue_engine.py` â€” Full 8,760-hour simulation
- `climate.py` â€” Climate analysis and suitability
- `weather.py` â€” Open-Meteo fetch, KML parse, geocoding
- Unit tests (all passing)
- **Deliverable:** Given weather data + site + scenario, produces hourly PUE, mode breakdown, IT capacity spectrum

### âœ… Phase 3: Engine Extended â€” Footprint, Ranking, Sensitivity (Week 3) â€” COMPLETE
- `footprint.py` â€” Infrastructure area calculations (cooling, gensets, transformers, substation, fuel cells, site fit check)
- `ranking.py` â€” Composite scoring (5-component weighted) + load mix optimizer (Section 3.12)
- `sensitivity.py` â€” Tornado chart (OAT Â±10%) + break-even solver (algebraic + bisection fallback)
- `backup_power.py` â€” 5-technology comparison (diesel, NG, SOFC, PEM Hâ‚‚, flywheel) + COâ‚‚ vs diesel baseline
- `green_energy.py` â€” 6-step hourly dispatch (PV â†’ BESS â†’ FC â†’ grid) with BESS SoC model
- Unit tests (all passing)
- **Deliverable:** Complete engine, all calculations working from CLI

### âœ… Phase 4: API Layer (Week 4) â€” COMPLETE
- `main.py` â€” FastAPI app with CORS, all 5 routers registered
- `api/store.py` â€” JSON file storage for sites and weather cache
- `api/__init__.py` â€” API package documentation
- `api/routes_site.py` â€” Site CRUD, KML upload, geocoding, space preview, reference data (7 endpoints)
- `api/routes_scenario.py` - Run single/batch, score, load mix, tornado, break-even, backup power, footprint (8 endpoints)
- `api/routes_climate.py` - Weather fetch, get cached, analyse raw, analyse from site (4 endpoints)
- `api/routes_green.py` - Green energy dispatch simulation (1 endpoint)
- `api/routes_export.py` - Scoped HTML, PDF, and Excel report export endpoints (3 endpoints)
- **Deliverable:** All calculations accessible via HTTP at http://localhost:8000/docs

### Phase 5: Frontend - Core Pages (Weeks 5-6) <- NEXT
- React project setup with routing
- Layout + sidebar navigation
- Site Manager page (CRUD + map)
- Scenario Runner page
- Basic Results Dashboard
- **Deliverable:** Working UI that can add sites, run scenarios, see results

### Phase 6: Frontend - Advanced Features (Weeks 7-8)
- Full Results Dashboard with all panels
- Climate & Weather page
- Green Energy page
- Charts (Recharts) for PUE, cooling modes, temperature, IT capacity
- Settings page
- **Deliverable:** Complete interactive UI

### Phase 7: Reports & Export (Week 9)
- Jinja2 HTML templates (executive + detailed)
- CSS theming with brand configuration
- weasyprint PDF generation
- Excel workbook generation
- Export page in frontend
- **Deliverable:** Professional reports downloadable from the UI

### Phase 8: Documentation & Handbook (Week 10)
- Complete HANDBOOK.md (like v3 but for v4)
- FORMULAS.md with every equation and source
- ASSUMPTIONS.md with every default and justification
- CHANGELOG.md
- README.md with setup instructions
- **Deliverable:** Self-contained documentation that any engineer can follow

---

## 9. Claude Code â€” How You'll Use It

**What is Claude Code:** A command-line tool where you type natural language and it runs commands on your machine. Think of it as a smart terminal assistant.

**What you'll use it for:**
1. **Running tests:** "Run the space calculation tests" â†’ it executes `pytest tests/test_space.py`
2. **Debugging:** "This test is failing with error X" â†’ it reads the error and suggests fixes
3. **Installing packages:** "Install the Python requirements" â†’ it runs `pip install -r requirements.txt`
4. **Starting servers:** "Start the backend server" â†’ it runs `uvicorn main:app --reload`

**What you won't use it for (initially):**
- Writing new code from scratch (I'll give you that)
- Making architectural decisions (we've already made those here)

**Setup (we'll do this in Phase 0):**
```bash
# Install Claude Code (requires Node.js)
npm install -g @anthropic-ai/claude-code

# Navigate to project directory
cd /Users/mostafashami/Desktop/dc-feasibility-v4

# Start Claude Code
claude
```

---

## 10. Project Instructions for Claude AI Project

Copy this text into your Claude project's instruction field:

```
PROJECT: DC Feasibility Tool v4
ROLE: I am Mostafa, a project developer at Metlen's innovative team, building a data center feasibility tool.
TECH STACK: Python 3.12 + FastAPI backend, React 18 + TypeScript frontend, Tailwind CSS, Recharts, Leaflet maps.
PROJECT DIR: /Users/mostafashami/Desktop/dc-feasibility-v4

KEY RULES:
1. Never give me code without explaining what it does and why.
2. Every formula must have a source citation (ASHRAE, Uptime Institute, manufacturer datasheet, etc.).
3. Every default value must have a documented justification.
4. Build incrementally â€” one module at a time, test before moving on.
5. The engine (backend/engine/) must have ZERO UI dependencies â€” pure Python calculation.
6. I am new to React/TypeScript â€” explain frontend concepts when they appear.
7. Refer to the Architecture Agreement document for all technical decisions.
8. If I upload files, review them against the Architecture Agreement for consistency.
9. Use Pydantic models for all data validation.
10. When in doubt, ask me â€” don't assume.

ACTIVE FILES: I will upload the latest version of each module as I build it. Always check uploaded files for the current state before suggesting changes.
```

---

## 11. What Happens Next

1. ~~**You review this document.**~~ âœ… DONE
2. ~~**We discuss and finalize.**~~ âœ… DONE
3. ~~**Phase 0: Project Setup.**~~ âœ… COMPLETE
4. ~~**Phase 1: Space & Power.**~~ âœ… COMPLETE
5. ~~**Phase 2: Cooling & PUE.**~~ âœ… COMPLETE
6. ~~**Phase 3: Footprint, Ranking, Sensitivity.**~~ âœ… COMPLETE
7. ~~**Phase 4: API Layer.**~~ âœ… COMPLETE â€” 23 endpoints, all engine functions accessible via HTTP
8. **Phase 5: Frontend â€” Core Pages** â† **WE ARE HERE**
9. Phases 6â€“8: Advanced Frontend, Reports, Documentation

---

*This document is version 5.0 (AGREED). Changes from v4.0:*
*â€” Phase 4 marked complete: 8 API files, 23 endpoints wrapping all engine modules*
*â€” Cross-module harmony confirmed: all API routes correctly delegate to engine*
*â€” No issues found in Phase 4 QA/QC*

**Known Limitations (as of Phase 2 completion):**
1. KML polygon centroid not implemented â€” weather.py extracts Point coordinates only. Polygon-only KML files will return no results. Will be addressed when encountered in practice.
2. Manufacturer COP data table upload not yet implemented (noted as "Phase 2+" enhanced option). Linear COP model is active.
3. DLC partial liquid coverage not modelled â€” cold plates cover CPUs/GPUs only; ~20-30% of server heat is air-cooled. Flagged in assumptions.py.


