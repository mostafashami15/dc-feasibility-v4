"""
DC Feasibility Tool v4 — Engineering Assumptions
=================================================
Every default value in the model, with source citations.

RULES:
1. No magic numbers anywhere in the engine — all defaults come from here.
2. Every value has a comment with its source.
3. If we can't source it, it's marked "Engineering judgment" with a valid range.
4. Users can override any value via the API — these are just defaults.

Reference: Architecture Agreement v2.0, Sections 3.1–3.17
"""

# ─────────────────────────────────────────────────────────────
# LOAD PROFILES — Rack densities per workload type
# ─────────────────────────────────────────────────────────────
# Source: Architecture Agreement Section 3.16 (Verified March 2026)
# All values in kW per rack.

LOAD_PROFILES: dict[str, dict] = {
    "Colocation (Standard)": {
        "density_low_kw": 4,
        "density_typical_kw": 7,
        "density_high_kw": 12,
        # Source: Uptime Institute Annual Survey 2023: median colo = 7 kW.
        # CBRE Data Center Solutions: 4–12 kW range for retail colocation.
        "compatible_cooling": [
            "Air-Cooled CRAC (DX)",
            "Air-Cooled AHU (No Economizer)",
            "Air-Cooled Chiller + Economizer",
            "Water-Cooled Chiller + Economizer",
            "Rear Door Heat Exchanger (RDHx)",
            "Free Cooling — Dry Cooler (Chiller-less)",
        ],
        "description": "Standard retail colocation. Mixed enterprise workloads.",
    },
    "Colocation (High Density)": {
        "density_low_kw": 12,
        "density_typical_kw": 20,
        "density_high_kw": 35,
        # Source: DCD Intelligence 2024: 20–30 kW high-density offerings.
        # Equinix xScale: up to 35 kW/rack.
        "compatible_cooling": [
            "Air-Cooled Chiller + Economizer",
            "Water-Cooled Chiller + Economizer",
            "Rear Door Heat Exchanger (RDHx)",
            "Direct Liquid Cooling (DLC / Cold Plate)",
        ],
        "description": "High-density colocation for enterprise AI/HPC tenants.",
    },
    "HPC": {
        "density_low_kw": 20,
        "density_typical_kw": 40,
        "density_high_kw": 60,
        # Source: TOP500 analysis: typical HPC cluster 30–50 kW/rack.
        # ORNL Frontier: ~60 kW/rack with liquid cooling.
        "compatible_cooling": [
            "Air-Cooled Chiller + Economizer",
            "Water-Cooled Chiller + Economizer",
            "Rear Door Heat Exchanger (RDHx)",
            "Direct Liquid Cooling (DLC / Cold Plate)",
            "Immersion Cooling (Single-Phase)",
        ],
        "description": "High-performance computing clusters. CPU-heavy, some GPU.",
    },
    "AI / GPU Clusters": {
        "density_low_kw": 40,
        "density_typical_kw": 100,
        "density_high_kw": 140,
        # Source: NVIDIA DGX H100 4-per-rack = 40 kW (low).
        # GB200 NVL72 = 120 kW (NVIDIA docs), HPE reports 132 kW (typical ~100 kW).
        # GB300 NVL72 = 142 kW (Schneider Electric, 2025).
        # TrendForce: GB200 NVL72 TDP 125–130 kW.
        # Future: Vera Rubin NVL144 (2H 2026) ~120–130 kW; Rubin Ultra NVL576 (2027) up to 600 kW.
        "compatible_cooling": [
            "Direct Liquid Cooling (DLC / Cold Plate)",
            "Immersion Cooling (Single-Phase)",
            "Water-Cooled Chiller + Economizer",  # At low density only
        ],
        "description": "GPU-dense AI training/inference racks. DLC or immersion required at typical+ density.",
    },
    "Hyperscale / Cloud": {
        "density_low_kw": 8,
        "density_typical_kw": 15,
        "density_high_kw": 25,
        # Source: Google/Microsoft/Meta published designs: 12–20 kW typical.
        # AWS: up to 25 kW for compute-heavy instances.
        "compatible_cooling": [
            "Air-Cooled Chiller + Economizer",
            "Water-Cooled Chiller + Economizer",
            "Rear Door Heat Exchanger (RDHx)",
            "Free Cooling — Dry Cooler (Chiller-less)",
        ],
        "description": "Large-scale cloud compute. Moderate density, high volume.",
    },
    "Edge / Telco": {
        "density_low_kw": 2,
        "density_typical_kw": 5,
        "density_high_kw": 8,
        # Source: ETSI MEC standards: 2–5 kW typical for edge micro-DC.
        # Telco central offices: up to 8 kW.
        "compatible_cooling": [
            "Air-Cooled CRAC (DX)",
            "Air-Cooled AHU (No Economizer)",
            "Air-Cooled Chiller + Economizer",
        ],
        "description": "Edge computing and telecom equipment. Low density.",
    },
}


# ─────────────────────────────────────────────────────────────
# COOLING PROFILES — Per-topology parameters
# ─────────────────────────────────────────────────────────────
# Source: Architecture Agreement Sections 3.2 and 3.15
# COP sources: ASHRAE Handbook Chapter 38 + manufacturer datasheets.
# Whitespace adjustment: Architecture Agreement Section 3.15.

COOLING_PROFILES: dict[str, dict] = {
    "Air-Cooled CRAC (DX)": {
        # Topology: Mechanical only (no economizer)
        "topology": "mechanical_only",
        "pue_min": 1.50,
        "pue_typical": 1.65,
        "pue_max": 1.90,
        "max_rack_density_kw": 10,
        "free_cooling_eligible": False,
        "capex_index": 1.0,  # Baseline reference
        # COP model parameters
        # Source: Emerson/Copeland Selection Software — typical scroll compressor DX.
        "COP_ref": 3.5,
        "COP_min": 2.0,
        "COP_max": 5.5,
        "T_ref_C": 35.0,
        "COP_slope": 0.12,  # dCOP/dT — Engineering judgment, typical for DX scroll
        "COP_quadratic": 0.0,  # Quadratic coefficient (dCOP/dT²), 0 = linear model
        "k_fan": 0.08,  # 8% of IT load — floor-standing CRAC units with internal fans
        "k_econ": 0.0,  # No economizer
        # Whitespace adjustment
        # Source: Schneider Electric WP 130 — CRAC units consume ~8% of white space
        "whitespace_adjustment_factor": 0.92,
        "description": "Standalone DX units with integrated compressor. Lowest efficiency.",
    },
    "Air-Cooled AHU (No Economizer)": {
        # Topology: Mechanical only
        "topology": "mechanical_only",
        "pue_min": 1.40,
        "pue_typical": 1.55,
        "pue_max": 1.75,
        "max_rack_density_kw": 20,
        "free_cooling_eligible": False,
        "capex_index": 1.1,
        # Source: Carrier 30XA datasheet — central air-cooled chiller, better than DX.
        "COP_ref": 4.5,
        "COP_min": 2.5,
        "COP_max": 7.0,
        "T_ref_C": 35.0,
        "COP_slope": 0.12,
        "COP_quadratic": 0.0,
        "k_fan": 0.06,  # 6% — AHU fans less overhead than CRAC
        "k_econ": 0.0,
        "whitespace_adjustment_factor": 1.00,  # AHU in separate plant room
        "description": "Central chiller with AHU distribution. No economizer.",
    },
    "Air-Cooled Chiller + Economizer": {
        # Topology: Chiller integral economizer (3-mode: MECH/ECON_PART/ECON_FULL)
        # v1 BUG FIX: Was incorrectly mapped to "air-side economizer" in v1.
        # An air-cooled chiller with integral economizer uses a refrigerant-side
        # or chilled-water-side bypass coil, NOT outdoor air dampers.
        "topology": "chiller_integral_economizer",
        "pue_min": 1.25,
        "pue_typical": 1.38,
        "pue_max": 1.55,
        "max_rack_density_kw": 50,
        "free_cooling_eligible": True,
        "capex_index": 1.3,
        # Source: Carrier 30XA/30XV at Eurovent conditions — high-efficiency screw chiller.
        "COP_ref": 5.5,
        "COP_min": 2.5,
        "COP_max": 9.0,
        "T_ref_C": 35.0,
        "COP_slope": 0.15,
        "COP_quadratic": 0.0,
        "k_fan": 0.05,  # 5%
        "k_econ": 0.015,  # 1.5% — economizer pump/fan when compressor off
        # Chiller integral economizer thresholds
        # Standard chilled water: CHWS=16°C, CHWR=24°C
        "CHWS_set_C": 16.0,
        "CHWR_target_C": 24.0,
        "ECO_enable_dT_C": 2.0,  # ECON_PART starts when T_amb ≤ CHWR - this
        "ECO_full_approach_C": 2.0,  # ECON_FULL when T_amb ≤ CHWS - this
        # Thresholds: ECON_FULL below 14°C, ECON_PART 14–22°C, MECH above 22°C
        "whitespace_adjustment_factor": 1.00,
        "description": "Air-cooled chiller with integral economizer bypass. 3-mode operation.",
    },
    "Water-Cooled Chiller + Economizer": {
        # Topology: Water-side economizer (2-mode: MECH/ECON_FULL)
        # COP driven by WET-BULB temperature (not dry-bulb).
        # Source: ASHRAE Fundamentals Ch.1 — cooling towers reject to wet-bulb.
        "topology": "water_side_economizer",
        "pue_min": 1.18,
        "pue_typical": 1.28,
        "pue_max": 1.42,
        "max_rack_density_kw": 50,
        "free_cooling_eligible": True,
        "capex_index": 1.45,
        # Source: Trane CenTraVac — water-cooled centrifugal chiller, AHRI 550/590.
        "COP_ref": 7.0,
        "COP_min": 3.5,
        "COP_max": 12.0,
        "T_ref_C": 35.0,  # This is wet-bulb reference
        "COP_slope": 0.20,
        "COP_quadratic": 0.0,
        "k_fan": 0.06,  # 6% — includes cooling tower fans and pumps
        "k_econ": 0.015,
        # Water-side economizer threshold
        "WSE_WB_C": 12.8,  # Free cooling when wet-bulb ≤ this
        "whitespace_adjustment_factor": 1.00,
        "description": "Water-cooled centrifugal chiller with cooling tower. COP uses wet-bulb.",
    },
    "Rear Door Heat Exchanger (RDHx)": {
        # Topology: Chiller integral economizer
        # RDHx is a heat distribution method, not a chiller type.
        # Uses the same central chiller as Air Chiller + Econ.
        "topology": "chiller_integral_economizer",
        "pue_min": 1.20,
        "pue_typical": 1.30,
        "pue_max": 1.45,
        "max_rack_density_kw": 60,
        "free_cooling_eligible": True,
        "capex_index": 1.4,
        # Same chiller as Air Chiller + Econ
        "COP_ref": 5.5,
        "COP_min": 2.5,
        "COP_max": 9.0,
        "T_ref_C": 35.0,
        "COP_slope": 0.15,
        "COP_quadratic": 0.0,
        "k_fan": 0.04,  # 4% — less fan overhead (rear door handles airflow)
        "k_econ": 0.015,
        "CHWS_set_C": 16.0,
        "CHWR_target_C": 24.0,
        "ECO_enable_dT_C": 2.0,
        "ECO_full_approach_C": 2.0,
        "whitespace_adjustment_factor": 1.00,  # Rear door adds depth, no floor area loss
        "description": "Rear-door water cooling panels. Same chiller as Air Chiller + Econ.",
    },
    "Direct Liquid Cooling (DLC / Cold Plate)": {
        # Topology: Chiller integral economizer (warm water variant)
        # Cold plates on CPUs/GPUs, warm water supply ~35°C.
        # v3 CORRECTIONS: ECO_dT=5°C (was 2°C), COP_min=4.0 (was 2.5).
        # Dry coolers have 5–7°C approach (no evaporation), not 2°C.
        "topology": "chiller_integral_economizer",
        "pue_min": 1.05,
        "pue_typical": 1.12,
        "pue_max": 1.20,
        "max_rack_density_kw": 150,  # Supports up to GB300 NVL72 at 142 kW
        "free_cooling_eligible": True,
        "capex_index": 1.8,
        # Source: Asetek/CoolIT warm water DLC datasheets.
        # Warm water supply (35°C) enables higher evaporator temp → higher COP floor.
        "COP_ref": 7.0,
        "COP_min": 4.0,   # v3 correction: was 2.5. At 35°C supply, COP can't drop to 2.5.
        "COP_max": 12.0,
        "T_ref_C": 35.0,
        "COP_slope": 0.18,
        "COP_quadratic": 0.0,
        "k_fan": 0.03,  # 3% — minimal air movement needed
        "k_econ": 0.012,  # Slightly lower — just CDU pumps
        # Partial liquid coverage
        # Existing note states ~20–30% of server heat remains air-cooled.
        # We model the midpoint explicitly: 25% residual air path, 75% liquid path.
        # Residual air path is represented with the existing Air Chiller + Economizer
        # topology already used elsewhere in the tool, rather than inventing a new model.
        "liquid_coverage_fraction": 0.75,
        "residual_cooling_type": "Air-Cooled Chiller + Economizer",
        # Warm water thresholds — dry cooler approach = 5°C (v3 correction)
        "CHWS_set_C": 30.0,  # Warm water supply
        "CHWR_target_C": 40.0,  # Warm water return
        "ECO_enable_dT_C": 5.0,  # v3 correction: was 2.0. Dry cooler approach.
        "ECO_full_approach_C": 5.0,  # v3 correction: was 2.0.
        # Thresholds: ECON_FULL below 25°C, MECH above 35°C
        "whitespace_adjustment_factor": 0.92,  # In-row CDUs ~1 per 12 racks (~8% loss)
        "description": "Cold plates on CPUs/GPUs. Warm water loop. Wide economizer window.",
        "known_simplification": (
            "DLC now uses a fixed 75% liquid / 25% residual-air split, derived from "
            "the documented 20–30% air-cooled remainder. Site-specific server mixes "
            "can differ, so this remains an explicit default assumption."
        ),
    },
    "Immersion Cooling (Single-Phase)": {
        # Topology: Chiller integral economizer (high fluid temp variant)
        # Servers submerged in dielectric fluid at ~40°C.
        # v3 CORRECTIONS: ECO_dT=6°C (was 2°C), COP_min=4.5 (was 2.5).
        "topology": "chiller_integral_economizer",
        "pue_min": 1.03,
        "pue_typical": 1.06,
        "pue_max": 1.12,
        "max_rack_density_kw": 200,
        "free_cooling_eligible": True,
        "capex_index": 2.5,
        # Source: GRC/LiquidCool published performance data.
        # 40°C fluid → even higher evaporator temp → highest COP floor.
        "COP_ref": 8.0,
        "COP_min": 4.5,   # v3 correction: was 2.5.
        "COP_max": 15.0,
        "T_ref_C": 35.0,
        "COP_slope": 0.20,
        "COP_quadratic": 0.0,
        "k_fan": 0.02,  # 2% — almost no air movement
        "k_econ": 0.010,
        # High fluid temp thresholds — dry cooler approach = 6°C (v3 correction)
        "CHWS_set_C": 34.0,  # Immersion fluid supply
        "CHWR_target_C": 45.0,  # Immersion fluid return
        "ECO_enable_dT_C": 6.0,  # v3 correction: was 2.0.
        "ECO_full_approach_C": 6.0,  # v3 correction: was 2.0.
        # Thresholds: ECON_FULL below 28°C, MECH above 39°C
        "whitespace_adjustment_factor": 0.85,  # Tank layout differs from rack layout
        "description": "Servers submerged in dielectric fluid. Highest efficiency.",
    },
    "Free Cooling — Dry Cooler (Chiller-less)": {
        # Topology: Air-side economizer (2-mode: MECH/ECON_FULL)
        # No compressor at all. Fan-only heat rejection via dry cooler.
        # When ambient exceeds threshold, system CANNOT maintain setpoint.
        "topology": "air_side_economizer",
        "pue_min": 1.08,
        "pue_typical": 1.15,
        "pue_max": 1.25,
        "max_rack_density_kw": 15,
        "free_cooling_eligible": True,
        "capex_index": 1.15,
        # Source: Airedale/Güntner dry cooler fan power curves.
        # COP here represents fan-only power (no compressor).
        "COP_ref": 12.0,
        "COP_min": 5.0,
        "COP_max": 20.0,
        "T_ref_C": 20.0,  # Lower reference — fan COP drops at higher ambient
        "COP_slope": 0.30,
        "COP_quadratic": 0.0,
        "k_fan": 0.04,  # 4%
        "k_econ": 0.015,
        # Air-side economizer thresholds
        "ASE_DB_C": 30.0,  # Overtemperature when dry-bulb exceeds this
        "whitespace_adjustment_factor": 1.00,
        "description": "No chiller. Dry cooler fans only. Risk of overtemperature in hot climates.",
    },
}


# ─────────────────────────────────────────────────────────────
# REDUNDANCY PROFILES
# ─────────────────────────────────────────────────────────────
# Source: Uptime Institute Tier Standard: Topology (2018)
# IEEE 3006.7 (Recommended Practice for UPS Systems)
#
# eta_chain_derate: UPS partial-load efficiency.
#   In 2N, each UPS carries 50% load → slightly less efficient.
#   This is a SMALL effect on PUE (0.5–1%).
#
# procurement_factor: Grid capacity sizing multiplier.
#   Does NOT affect PUE or operational power.
#   Affects: equipment sizing, footprint, grid connection fee.

REDUNDANCY_PROFILES: dict[str, dict] = {
    "N": {
        "eta_chain_derate": 0.970,  # Full-load UPS efficiency
        "procurement_factor": 1.00,  # Single path
        "tier": "Tier I",
        "description": "No redundancy. Single power path.",
    },
    "N+1": {
        "eta_chain_derate": 0.965,  # UPS at ~85% load
        "procurement_factor": 1.15,  # One spare component per group (~15% oversizing)
        "tier": "Tier II",
        "description": "Component redundancy. One spare per group.",
    },
    "2N": {
        "eta_chain_derate": 0.950,  # UPS at 50% load
        "procurement_factor": 2.00,  # Two complete paths
        "tier": "Tier III",
        "description": "Full redundancy. Two independent power paths.",
    },
    "2N+1": {
        "eta_chain_derate": 0.940,  # Max derate (50% load + extra module losses)
        "procurement_factor": 2.00,  # Two paths + spare (grid still sees 2×)
        "tier": "Tier IV",
        "description": "Fault tolerant. Two paths plus one spare.",
    },
}


# ─────────────────────────────────────────────────────────────
# POWER CHAIN
# ─────────────────────────────────────────────────────────────
# Source: Architecture Agreement Section 3.6
# Individual component efficiencies multiplied together.

POWER_CHAIN: dict[str, float] = {
    # Component efficiencies at full load
    "hv_mv_transformer_efficiency": 0.985,
    # Source: ABB/Siemens MV/LV transformer datasheets (2000 kVA class)

    "ups_efficiency_full_load": 0.940,
    # Source: Schneider Galaxy VX, Eaton 93PM — online double-conversion UPS at full load.

    "pdu_busway_efficiency": 0.980,
    # Source: Typical PDU/busway distribution losses (Schneider, Legrand datasheets).

    # Combined chain efficiency (product of all three)
    # 0.985 × 0.940 × 0.980 = 0.907
    "combined_efficiency": 0.907,
    # This is overridden by eta_chain_derate from REDUNDANCY_PROFILES when redundancy is set.
}

# Formula: elec_loss = (1 / eta_chain) - 1
# At η = 0.95 (2N): elec_loss ≈ 0.053 → 5.3% of IT load as conversion heat.
# At η = 0.907 (N, full load): elec_loss ≈ 0.103 → 10.3%.


# ─────────────────────────────────────────────────────────────
# MISCELLANEOUS OVERHEAD
# ─────────────────────────────────────────────────────────────

MISC_OVERHEAD: dict[str, float] = {
    "f_misc": 0.025,
    # Miscellaneous fixed loads as fraction of available power.
    # Covers: lighting, BMS, security systems, fire suppression, office HVAC.
    # Source: EU Code of Conduct on Data Centre Energy Efficiency (JRC, 2022).
    # Typical range: 2–4% of available power. Default 2.5%.

    "f_headroom": 0.05,
    # Power headroom reserved — not used for IT or overhead.
    # Prevents operating at 100% capacity (margin for transients).
    # Source: Engineering judgment. Typical 3–7%. Default 5%.

    "IT_utilization_factor": 1.0,
    # Fraction of rated IT capacity in active use.
    # 1.0 = worst case (all racks at full rated power).
    # Real utilization is typically 0.6–0.8, but for feasibility
    # we use 1.0 to size for worst case.
    # Source: Uptime Institute guidance on capacity planning.
}


# ─────────────────────────────────────────────────────────────
# INFRASTRUCTURE FOOTPRINT
# ─────────────────────────────────────────────────────────────
# Source: Architecture Agreement Section 3.11
# All values in m² per kW of the relevant sizing basis.

FOOTPRINT: dict[str, dict] = {
    "cooling_skid_m2_per_kw_rejected": {
        "default": 0.15,
        "min": 0.10,
        "max": 0.30,
        "location": "roof",
        # Source: Carrier/Trane condenser selection guides.
        # Typical air-cooled condenser: 0.15 m²/kW rejected.
        "source": "Carrier/Trane condenser selection guides",
    },
    "diesel_genset_m2_per_kw": {
        "default": 0.008,
        "min": 0.006,
        "max": 0.012,
        "location": "ground",
        # Source: Caterpillar C32/QSK60, Cummins genset dimension tables.
        # Includes enclosure, base tank, access clearance.
        "source": "Caterpillar/Cummins genset dimension tables",
    },
    "genset_unit_size_kw": {
        "default": 2000,
        # Typical containerized genset unit: 2 MW.
        "source": "Industry standard containerized genset sizing",
    },
    "natural_gas_genset_m2_per_kw": {
        "default": 0.010,
        "min": 0.008,
        "max": 0.015,
        "location": "ground",
        "source": "Caterpillar/Wärtsilä gas genset datasheets",
    },
    "sofc_fuel_cell_m2_per_kw": {
        "default": 0.015,
        "min": 0.012,
        "max": 0.020,
        "location": "ground",
        # Source: Bloom Energy Server ES5 datasheet (2023).
        # 300 kW/module, 1.05m × 3.65m per module = 3.83 m² / 300 kW ≈ 0.013 m²/kW
        # With access clearance: ~0.015 m²/kW.
        "source": "Bloom Energy Server ES5 datasheet (2023)",
    },
    "pem_fuel_cell_m2_per_kw": {
        "default": 0.020,
        "min": 0.015,
        "max": 0.030,
        "location": "ground",
        # Source: Ballard/Plug Power module dimension guides.
        "source": "Ballard/Plug Power module dimension guides",
    },
    "transformer_m2_per_kw": {
        "default": 0.004,
        "min": 0.003,
        "max": 0.007,
        "location": "ground",
        # Source: ABB/Siemens MV/LV transformer datasheets (2000 kVA class).
        # Includes oil bund and access clearance.
        "source": "ABB/Siemens MV/LV transformer datasheets",
    },
    "substation_m2_per_kw": {
        "default": 0.005,
        "min": 0.003,
        "max": 0.010,
        "location": "ground",
        # Source: Typical MV switchgear room sizing per IEC 62271-200.
        "source": "IEC 62271-200 MV switchgear room sizing",
    },
    "rotary_ups_m2_per_kw": {
        "default": 0.005,
        "min": 0.003,
        "max": 0.008,
        "location": "ground",
        "source": "Hitec/Piller DRUPS datasheets",
    },
}


# ─────────────────────────────────────────────────────────────
# BACKUP POWER TECHNOLOGIES
# ─────────────────────────────────────────────────────────────
# Source: Architecture Agreement Section 3.8

BACKUP_POWER: dict[str, dict] = {
    "Diesel Genset": {
        "type": "backup",
        "efficiency_min": 0.35,
        "efficiency_max": 0.40,
        "module_size_kw": 2000,
        "ramp_time_seconds": 12,
        "fuel": "Diesel",
        "emissions": "high",
        "footprint_key": "diesel_genset_m2_per_kw",
        "co2_kg_per_kwh_fuel": 0.267,  # Source: IPCC emission factors for diesel
        "source": "Caterpillar/Cummins genset datasheets",
    },
    "Natural Gas Genset": {
        "type": "backup_or_prime",
        "efficiency_min": 0.38,
        "efficiency_max": 0.42,
        "module_size_kw": 2500,
        "ramp_time_seconds": 45,
        "fuel": "Natural Gas",
        "emissions": "medium",
        "footprint_key": "natural_gas_genset_m2_per_kw",
        "co2_kg_per_kwh_fuel": 0.202,  # Source: IPCC emission factors for natural gas
        "source": "Caterpillar/Wärtsilä gas genset datasheets",
    },
    "SOFC Fuel Cell": {
        "type": "prime_power",
        "efficiency_min": 0.55,
        "efficiency_max": 0.65,
        "module_size_kw": 300,
        "ramp_time_seconds": 300,  # ~5 min warm start
        "fuel": "Natural Gas / Biogas / H₂",
        "emissions": "low",
        "footprint_key": "sofc_fuel_cell_m2_per_kw",
        "co2_kg_per_kwh_fuel": 0.202,  # NG basis; 0 for biogas/H₂
        "source": "Bloom Energy Server ES5 datasheet (2023)",
    },
    "PEM Fuel Cell (H₂)": {
        "type": "backup_or_prime",
        "efficiency_min": 0.45,
        "efficiency_max": 0.55,
        "module_size_kw": 250,
        "ramp_time_seconds": 5,
        "fuel": "Green H₂",
        "emissions": "zero",
        "footprint_key": "pem_fuel_cell_m2_per_kw",
        "co2_kg_per_kwh_fuel": 0.0,  # Zero if green hydrogen
        "source": "Ballard/Plug Power module datasheets",
    },
    "Rotary UPS + Flywheel": {
        "type": "bridge_power",
        "efficiency_min": 0.95,
        "efficiency_max": 0.97,
        "module_size_kw": 2000,
        "ramp_time_seconds": 0,  # Instant — kinetic energy
        "fuel": "None (kinetic)",
        "emissions": "zero",
        "footprint_key": "rotary_ups_m2_per_kw",
        "co2_kg_per_kwh_fuel": 0.0,
        "source": "Hitec/Piller DRUPS datasheets",
        "note": "Bridge power only (15–60 seconds). Not a genset replacement.",
    },
}


# ─────────────────────────────────────────────────────────────
# CLIMATE SUITABILITY BANDS
# ─────────────────────────────────────────────────────────────
# Based on hours per year with dry-bulb ≤ 14°C (free cooling threshold
# for standard chilled water with Air-Cooled Chiller + Economizer).
# Source: v3 handbook Section 10 + Architecture Agreement.

CLIMATE_SUITABILITY: dict[str, dict] = {
    "EXCELLENT": {"min_hours": 7000, "color": "green"},
    "GOOD": {"min_hours": 5000, "color": "green"},
    "MARGINAL": {"min_hours": 3000, "color": "amber"},
    "NOT_RECOMMENDED": {"min_hours": 0, "color": "red"},
}


# ─────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────

def get_rack_density_kw(load_type: str, density_scenario: str) -> float:
    """Get rack density in kW for a given load type and scenario.
    
    Args:
        load_type: Key from LOAD_PROFILES (e.g., "AI / GPU Clusters")
        density_scenario: "low", "typical", or "high"
    
    Returns:
        Rack density in kW.
    
    Raises:
        KeyError: If load_type or density_scenario is invalid.
    """
    profile = LOAD_PROFILES[load_type]
    key = f"density_{density_scenario}_kw"
    return profile[key]


def get_pue_for_load_type(load_type: str, cooling_type: str) -> float:
    """Get the effective PUE for a specific load type with a given cooling system.

    If the cooling type is compatible with the load type, returns the cooling
    profile's pue_typical. If incompatible, still returns pue_typical as a
    fallback (compatibility should be checked separately).

    This supports per-load-type PUE in the load mix optimizer, where different
    load types may achieve different effective PUE values depending on cooling
    compatibility and topology.

    Args:
        load_type: Key from LOAD_PROFILES (e.g., "AI / GPU Clusters")
        cooling_type: Key from COOLING_PROFILES (e.g., "Direct Liquid Cooling (DLC / Cold Plate)")

    Returns:
        PUE typical value for the cooling type.
    """
    return COOLING_PROFILES[cooling_type]["pue_typical"]


def is_compatible(load_type: str, cooling_type: str) -> bool:
    """Check if a load type and cooling type are compatible.
    
    Source: Architecture Agreement Section 3.16 compatibility matrix.
    
    Args:
        load_type: Key from LOAD_PROFILES
        cooling_type: Key from COOLING_PROFILES
    
    Returns:
        True if the combination is supported.
    """
    profile = LOAD_PROFILES[load_type]
    return cooling_type in profile["compatible_cooling"]


def evaluate_compatibility(
    load_type: str,
    cooling_type: str,
    density_scenario: str | None = None,
    rack_density_kw: float | None = None,
) -> tuple[str, list[str]]:
    """Assess whether a load/cooling combination is acceptable.

    Returns one of:
        - "compatible": supported and recommended by default
        - "conditional": supported, but only as a constrained edge case
        - "incompatible": should be rejected

    The base compatibility matrix still comes from Section 3.16 of the
    Architecture Agreement. This helper adds density-aware checks where
    the agreement or inline assumption notes explicitly call them out.
    """
    reasons: list[str] = []

    if not is_compatible(load_type, cooling_type):
        return (
            "incompatible",
            [f"{cooling_type} is not supported for {load_type}"],
        )

    if rack_density_kw is None and density_scenario is not None:
        rack_density_kw = get_rack_density_kw(load_type, density_scenario)

    cooling_profile = COOLING_PROFILES[cooling_type]
    max_density = cooling_profile["max_rack_density_kw"]
    if rack_density_kw is not None and rack_density_kw > max_density:
        return (
            "incompatible",
            [
                f"Rack density {rack_density_kw} kW exceeds "
                f"{cooling_type} maximum of {max_density} kW"
            ],
        )

    conditional_reasons: list[str] = []

    if (
        load_type == "AI / GPU Clusters"
        and cooling_type == "Water-Cooled Chiller + Economizer"
    ):
        low_density_kw = LOAD_PROFILES[load_type]["density_low_kw"]
        if rack_density_kw is not None and rack_density_kw > low_density_kw:
            return (
                "incompatible",
                [
                    "Water-Cooled Chiller + Economizer is only supported for "
                    "low-density AI/GPU deployments. Typical and high-density AI "
                    "require DLC or immersion cooling."
                ],
            )

        conditional_reasons.append(
            "Low-density AI/GPU on Water-Cooled Chiller + Economizer is a "
            "conditional edge case; confirm the vendor thermal envelope."
        )

    if (
        cooling_type == "Free Cooling — Dry Cooler (Chiller-less)"
        and load_type in {"Colocation (Standard)", "Hyperscale / Cloud"}
    ):
        conditional_reasons.append(
            "Chiller-less dry-cooler designs are treated as climate-limited niche "
            "solutions for mainstream colocation or hyperscale deployments; "
            "validate the need for trim/mechanical backup before recommending them."
        )

    if (
        cooling_type == "Direct Liquid Cooling (DLC / Cold Plate)"
        and load_type == "Colocation (High Density)"
    ):
        conditional_reasons.append(
            "High-density colocation with DLC is treated as a dedicated "
            "single-tenant AI/HPC suite case, not the default multi-tenant "
            "colocation baseline. Confirm tenant hardware alignment and "
            "liquid-cooling operations support."
        )

    if cooling_type == "Immersion Cooling (Single-Phase)" and load_type == "AI / GPU Clusters":
        low_density_kw = LOAD_PROFILES[load_type]["density_low_kw"]
        if rack_density_kw is not None and rack_density_kw <= low_density_kw:
            conditional_reasons.append(
                "Low-density AI/GPU on immersion is treated as a niche case; "
                "most 40 kW-class AI deployments remain better aligned with DLC "
                "or chilled-water architectures. Confirm the vendor thermal "
                "envelope and service model."
            )

    if cooling_type == "Immersion Cooling (Single-Phase)" and load_type == "HPC":
        typical_density_kw = LOAD_PROFILES[load_type]["density_typical_kw"]
        if rack_density_kw is None or rack_density_kw <= typical_density_kw:
            conditional_reasons.append(
                "Immersion is viable for HPC, but below very-high-density "
                "clusters it remains a specialized design; confirm certified "
                "hardware support and operations readiness."
            )

    if (
        cooling_type == "Immersion Cooling (Single-Phase)"
        and load_type == "AI / GPU Clusters"
        and rack_density_kw is None
    ):
        conditional_reasons.append(
            "Immersion is supported for AI/GPU clusters, but if density is not "
            "specified you should confirm the hardware certification and "
            "operations model before treating it as the baseline design."
        )

    if conditional_reasons:
        return "conditional", conditional_reasons

    return "compatible", reasons


def get_whitespace_adjustment(cooling_type: str) -> float:
    """Get the whitespace adjustment factor for a cooling type.
    
    Source: Architecture Agreement Section 3.15.
    
    Returns:
        Factor between 0.85 and 1.00 to apply to max rack count.
    """
    profile = COOLING_PROFILES[cooling_type]
    return profile["whitespace_adjustment_factor"]
