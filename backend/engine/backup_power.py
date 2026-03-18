"""
DC Feasibility Tool v4 — Backup Power Analysis
=================================================
Computes fuel consumption, CO₂ emissions, and technology comparison
for backup/prime power systems.

This module handles the ENERGY and ENVIRONMENTAL aspects of backup power.
The SPATIAL aspects (unit count, footprint area) are in footprint.py.

Four deliverables per Architecture Agreement Section 3.8:
    (a) Number of units needed       → footprint.py (already done)
    (b) Total footprint              → footprint.py (already done)
    (c) Annual fuel consumption      → THIS MODULE
    (d) CO₂ emissions vs diesel      → THIS MODULE

Key formulas:
    electrical_energy = procurement_power × runtime_hours
    fuel_energy       = electrical_energy / η_electrical
    co2               = fuel_energy × co2_factor
    fuel_volume       = fuel_energy / fuel_energy_density

The backup power choice does NOT affect PUE or IT capacity.
It is a parallel infrastructure decision.

Reference: Architecture Agreement v3.0, Section 3.8
"""

import math
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, Field

from engine.models import BackupPowerType
from engine.assumptions import BACKUP_POWER, FOOTPRINT


# ─────────────────────────────────────────────────────────────
# Fuel Energy Density Constants
# ─────────────────────────────────────────────────────────────
# These convert fuel energy (kWh) into physical volume/mass
# for tank sizing, fuel contracts, and logistics planning.

FUEL_ENERGY_DENSITY: dict[str, dict] = {
    "Diesel": {
        "density_kwh_per_unit": 10.0,
        "unit": "liter",
        "unit_plural": "liters",
        # Source: EN 590 European diesel standard.
        # LHV ≈ 42.5 MJ/kg, density ≈ 0.835 kg/L
        # → 42.5 × 0.835 / 3.6 ≈ 9.86 kWh/L ≈ 10.0 kWh/L (rounded)
        "source": "EN 590 diesel standard (LHV ≈ 42.5 MJ/kg, density 0.835 kg/L)",
    },
    "Natural Gas": {
        "density_kwh_per_unit": 10.3,
        "unit": "m³",
        "unit_plural": "m³",
        # Source: Typical pipeline natural gas at standard conditions (15°C, 1 atm).
        # LHV ≈ 36–38 MJ/m³ → ~10.0–10.6 kWh/m³. Using 10.3 as midpoint.
        # Reference: ISO 6976 (Natural gas — Calculation of calorific values).
        "source": "ISO 6976 pipeline NG at standard conditions (LHV ≈ 37 MJ/m³)",
    },
    "Green H₂": {
        "density_kwh_per_unit": 33.3,
        "unit": "kg",
        "unit_plural": "kg",
        # Source: NIST standard hydrogen properties.
        # LHV = 120 MJ/kg / 3.6 = 33.3 kWh/kg.
        # Reference: NIST Chemistry WebBook; also ISO 14687.
        "source": "NIST standard hydrogen properties (LHV = 120 MJ/kg)",
    },
    "Natural Gas / Biogas / H₂": {
        # SOFC can run on multiple fuels. Default calculation uses NG basis.
        # User can override for biogas/H₂ scenarios.
        "density_kwh_per_unit": 10.3,
        "unit": "m³",
        "unit_plural": "m³ (NG equivalent)",
        "source": "ISO 6976 (NG basis; biogas/H₂ would differ)",
    },
    "None (kinetic)": {
        # Rotary UPS / Flywheel — no fuel consumed.
        "density_kwh_per_unit": 1.0,  # Placeholder — never used (fuel = 0)
        "unit": "N/A",
        "unit_plural": "N/A",
        "source": "N/A — kinetic energy storage, no fuel",
    },
}

# ─────────────────────────────────────────────────────────────
# Default Runtime Assumptions
# ─────────────────────────────────────────────────────────────

DEFAULT_BACKUP_RUNTIME_HOURS = 200
# Typical annual runtime for backup generators.
# Composed of: monthly load-bank testing (12 × 4h = 48h)
#              + annual maintenance runs (~24h)
#              + grid outage events (~50–100h for Southern Europe)
#              + safety margin
# Source: Uptime Institute recommends monthly testing under load.
# Engineering judgment for total: 150–250 hours. Default 200.

DEFAULT_PRIME_RUNTIME_HOURS = 8760
# Continuous operation for prime power applications.
# 365 days × 24 hours = 8,760 hours/year.


# ─────────────────────────────────────────────────────────────
# Result Models
# ─────────────────────────────────────────────────────────────

class BackupPowerSizing(BaseModel):
    """Sizing and operational details for one backup power technology.

    Combines physical sizing (from footprint logic) with energy
    and emissions calculations unique to backup_power.py.
    """

    # ── Technology identity ──
    technology: str = Field(description="Technology name (e.g., 'Diesel Genset')")
    technology_type: str = Field(
        description="Role: 'backup', 'backup_or_prime', 'prime_power', 'bridge_power'"
    )
    fuel_type: str = Field(description="Fuel used (e.g., 'Diesel', 'Green H₂')")

    # ── Physical sizing ──
    num_units: int = Field(description="Number of modules/units required")
    unit_size_kw: float = Field(description="Rated power per module (kW)")
    total_rated_kw: float = Field(
        description="Total installed capacity = num_units × unit_size_kw (kW)"
    )
    footprint_m2: float = Field(description="Total ground footprint (m²)")
    ramp_time_seconds: float = Field(description="Time to full power (seconds)")

    # ── Efficiency ──
    efficiency_min: float = Field(description="Lower bound of electrical efficiency")
    efficiency_max: float = Field(description="Upper bound of electrical efficiency")
    efficiency_typical: float = Field(
        description="Midpoint efficiency used for calculations"
    )

    # ── Energy (for given runtime) ──
    annual_runtime_hours: float = Field(
        description="Assumed annual runtime hours for this calculation"
    )
    electrical_energy_mwh: float = Field(
        description="Annual electrical energy output (MWh)"
    )
    fuel_energy_mwh: float = Field(
        description="Annual fuel energy input (MWh thermal)"
    )

    # ── Fuel volume ──
    fuel_volume: float = Field(
        description="Annual fuel consumption in physical units"
    )
    fuel_volume_unit: str = Field(
        description="Unit for fuel_volume (liters, m³, kg, or N/A)"
    )

    # ── Emissions ──
    co2_tonnes_per_year: float = Field(
        description="Annual CO₂ emissions (metric tonnes)"
    )
    co2_kg_per_kwh_fuel: float = Field(
        description="CO₂ emission factor used (kg CO₂ per kWh fuel energy)"
    )
    emissions_category: str = Field(
        description="Qualitative category: 'high', 'medium', 'low', 'zero'"
    )

    # ── Source ──
    source: str = Field(description="Primary source citation for this technology")


class BackupPowerComparison(BaseModel):
    """Side-by-side comparison of all backup power technologies.

    The comparison uses the same procurement power and runtime hours
    for every technology, making the results directly comparable.
    The diesel baseline is always included for CO₂ savings calculation.
    """

    # ── Inputs ──
    procurement_power_mw: float = Field(
        description="Common sizing basis for all technologies (MW)"
    )
    annual_runtime_hours: float = Field(
        description="Common runtime assumption for all technologies (hours/year)"
    )

    # ── Per-technology results ──
    technologies: list[BackupPowerSizing] = Field(
        description="Results for each technology, same order as BackupPowerType enum"
    )

    # ── Diesel baseline reference ──
    diesel_co2_tonnes: float = Field(
        description="Diesel baseline CO₂ for savings comparison (tonnes/year)"
    )

    # ── Rankings ──
    lowest_co2_technology: str = Field(
        description="Technology with lowest CO₂ emissions"
    )
    lowest_footprint_technology: str = Field(
        description="Technology with smallest physical footprint"
    )
    fastest_ramp_technology: str = Field(
        description="Technology with fastest ramp to full power"
    )


# ─────────────────────────────────────────────────────────────
# Core Calculation
# ─────────────────────────────────────────────────────────────

def compute_backup_sizing(
    procurement_power_mw: float,
    backup_type: BackupPowerType,
    annual_runtime_hours: Optional[float] = None,
) -> BackupPowerSizing:
    """Compute sizing, fuel consumption, and emissions for one technology.

    This is the single-technology calculation. For side-by-side comparison
    of all technologies, use compare_technologies().

    Formulas:
        electrical_energy = procurement_power_kW × runtime_hours   [kWh]
        η_typical         = (η_min + η_max) / 2                   [—]
        fuel_energy       = electrical_energy / η_typical          [kWh]
        fuel_volume       = fuel_energy / fuel_energy_density      [liters/m³/kg]
        co2_kg            = fuel_energy × co2_kg_per_kWh_fuel      [kg]
        co2_tonnes        = co2_kg / 1000                          [tonnes]

    Sources:
        - Efficiency ranges: Architecture Agreement Section 3.8
        - CO₂ factors: IPCC emission factors (in assumptions.py)
        - Fuel densities: EN 590 (diesel), ISO 6976 (NG), NIST (H₂)
        - Module sizes: Manufacturer datasheets (in assumptions.py)

    Args:
        procurement_power_mw:
            Grid capacity in MW. Backup systems are sized to this value
            because they must handle the full redundant capacity.
            Source: Uptime Institute Tier Standard.

        backup_type:
            Which technology to evaluate.

        annual_runtime_hours:
            Hours per year the system operates. If None, uses defaults:
            - bridge_power → 0 (seconds only, negligible fuel)
            - prime_power → 8,760 (continuous)
            - backup / backup_or_prime → 200 (testing + outages)

    Returns:
        BackupPowerSizing with all sizing, energy, and emissions data.

    Raises:
        ValueError: If procurement_power_mw is negative.

    Example:
        >>> result = compute_backup_sizing(
        ...     procurement_power_mw=40.0,
        ...     backup_type=BackupPowerType.DIESEL_GENSET,
        ...     annual_runtime_hours=200,
        ... )
        >>> print(f"CO₂: {result.co2_tonnes_per_year:.1f} t/year")
        >>> print(f"Diesel: {result.fuel_volume:.0f} liters/year")
    """
    if procurement_power_mw < 0:
        raise ValueError(
            f"procurement_power_mw cannot be negative: {procurement_power_mw}"
        )

    profile = BACKUP_POWER[backup_type.value]
    procurement_power_kw = procurement_power_mw * 1000

    # ── Physical sizing ──
    unit_size_kw = float(profile["module_size_kw"])
    if procurement_power_kw > 0:
        num_units = math.ceil(procurement_power_kw / unit_size_kw)
    else:
        num_units = 0
    total_rated_kw = num_units * unit_size_kw

    # Footprint area (same calculation as footprint.py, included here
    # for self-contained results — not a duplicate path, just the
    # same simple multiplication for convenience)
    footprint_key = profile["footprint_key"]
    footprint_m2_per_kw = FOOTPRINT[footprint_key]["default"]
    footprint_m2 = procurement_power_kw * footprint_m2_per_kw

    # ── Efficiency ──
    # Midpoint of the range for feasibility-grade calculation.
    # Real efficiency varies with load factor and ambient conditions.
    eff_min = profile["efficiency_min"]
    eff_max = profile["efficiency_max"]
    eff_typical = (eff_min + eff_max) / 2

    # ── Runtime ──
    tech_type = profile["type"]
    if annual_runtime_hours is not None:
        runtime = annual_runtime_hours
    elif tech_type == "bridge_power":
        # Rotary UPS/flywheel: runs for seconds only.
        # Fuel consumption is effectively zero — no fuel involved.
        runtime = 0.0
    elif tech_type == "prime_power":
        runtime = DEFAULT_PRIME_RUNTIME_HOURS
    else:
        # "backup" or "backup_or_prime" — default to backup scenario
        runtime = DEFAULT_BACKUP_RUNTIME_HOURS

    # ── Energy calculation ──
    # Electrical energy = what the system delivers to the data center
    electrical_energy_kwh = procurement_power_kw * runtime
    electrical_energy_mwh = electrical_energy_kwh / 1000

    # Fuel energy = what goes IN (thermal), accounting for conversion losses
    # fuel_energy = electrical_energy / η
    if eff_typical > 0 and runtime > 0:
        fuel_energy_kwh = electrical_energy_kwh / eff_typical
    else:
        fuel_energy_kwh = 0.0
    fuel_energy_mwh = fuel_energy_kwh / 1000

    # ── Fuel volume (physical units) ──
    fuel_type = profile["fuel"]
    fuel_density_info = FUEL_ENERGY_DENSITY.get(fuel_type, FUEL_ENERGY_DENSITY["None (kinetic)"])
    fuel_density_kwh_per_unit = fuel_density_info["density_kwh_per_unit"]

    if fuel_density_kwh_per_unit > 0 and fuel_energy_kwh > 0:
        fuel_volume = fuel_energy_kwh / fuel_density_kwh_per_unit
    else:
        fuel_volume = 0.0

    fuel_volume_unit = fuel_density_info["unit_plural"]

    # ── CO₂ emissions ──
    # co2 = fuel_energy (kWh) × co2_factor (kg CO₂ / kWh fuel)
    # Source: IPCC emission factors, stored in assumptions.py
    co2_factor = profile["co2_kg_per_kwh_fuel"]
    co2_kg = fuel_energy_kwh * co2_factor
    co2_tonnes = co2_kg / 1000

    return BackupPowerSizing(
        technology=backup_type.value,
        technology_type=tech_type,
        fuel_type=fuel_type,
        num_units=num_units,
        unit_size_kw=unit_size_kw,
        total_rated_kw=total_rated_kw,
        footprint_m2=round(footprint_m2, 1),
        ramp_time_seconds=float(profile["ramp_time_seconds"]),
        efficiency_min=eff_min,
        efficiency_max=eff_max,
        efficiency_typical=eff_typical,
        annual_runtime_hours=runtime,
        electrical_energy_mwh=round(electrical_energy_mwh, 2),
        fuel_energy_mwh=round(fuel_energy_mwh, 2),
        fuel_volume=round(fuel_volume, 1),
        fuel_volume_unit=fuel_volume_unit,
        co2_tonnes_per_year=round(co2_tonnes, 2),
        co2_kg_per_kwh_fuel=co2_factor,
        emissions_category=profile["emissions"],
        source=profile["source"],
    )


# ─────────────────────────────────────────────────────────────
# Technology Comparison
# ─────────────────────────────────────────────────────────────

def compare_technologies(
    procurement_power_mw: float,
    annual_runtime_hours: Optional[float] = None,
) -> BackupPowerComparison:
    """Compare all backup power technologies side by side.

    Runs compute_backup_sizing for every technology in BackupPowerType,
    using the SAME procurement power and runtime hours for fair comparison.
    Always includes diesel as the baseline for CO₂ savings.

    The comparison table appears in the detailed technical report
    (Architecture Agreement Section 7, Report Design).

    Args:
        procurement_power_mw:
            Common sizing basis for all technologies (MW).

        annual_runtime_hours:
            Common runtime for comparison. If None, each technology
            uses its default (backup=200h, prime=8760h, bridge=0h).
            For a fair apples-to-apples comparison, specify a value.

    Returns:
        BackupPowerComparison with all technologies and rankings.

    Example:
        >>> comparison = compare_technologies(
        ...     procurement_power_mw=40.0,
        ...     annual_runtime_hours=200,
        ... )
        >>> for tech in comparison.technologies:
        ...     print(f"{tech.technology}: {tech.co2_tonnes_per_year:.1f} t CO₂")
    """
    if procurement_power_mw < 0:
        raise ValueError(
            f"procurement_power_mw cannot be negative: {procurement_power_mw}"
        )

    technologies: list[BackupPowerSizing] = []
    for backup_type in BackupPowerType:
        sizing = compute_backup_sizing(
            procurement_power_mw=procurement_power_mw,
            backup_type=backup_type,
            annual_runtime_hours=annual_runtime_hours,
        )
        technologies.append(sizing)

    # ── Diesel baseline (always computed for comparison) ──
    diesel_result = next(
        t for t in technologies if t.technology == BackupPowerType.DIESEL_GENSET.value
    )
    diesel_co2 = diesel_result.co2_tonnes_per_year

    # ── Actual runtime used for the comparison header ──
    # If annual_runtime_hours was None, technologies may have different defaults.
    # Report the first non-bridge technology's runtime as the reference.
    if annual_runtime_hours is not None:
        comparison_runtime = annual_runtime_hours
    else:
        # Find the first non-bridge technology for the reference runtime
        non_bridge = [t for t in technologies if t.technology_type != "bridge_power"]
        comparison_runtime = non_bridge[0].annual_runtime_hours if non_bridge else 0.0

    # ── Rankings ──
    # Lowest CO₂ (exclude technologies with 0 runtime / bridge power
    # from meaningful comparison, but still include them in the list)
    lowest_co2 = min(technologies, key=lambda t: t.co2_tonnes_per_year)

    lowest_footprint = min(technologies, key=lambda t: t.footprint_m2)

    fastest_ramp = min(technologies, key=lambda t: t.ramp_time_seconds)

    return BackupPowerComparison(
        procurement_power_mw=procurement_power_mw,
        annual_runtime_hours=comparison_runtime,
        technologies=technologies,
        diesel_co2_tonnes=diesel_co2,
        lowest_co2_technology=lowest_co2.technology,
        lowest_footprint_technology=lowest_footprint.technology,
        fastest_ramp_technology=fastest_ramp.technology,
    )


# ─────────────────────────────────────────────────────────────
# CO₂ Savings Helper
# ─────────────────────────────────────────────────────────────

def co2_savings_vs_diesel(
    technology_co2_tonnes: float,
    diesel_co2_tonnes: float,
) -> dict[str, float]:
    """Calculate CO₂ savings of a technology compared to diesel baseline.

    Returns absolute savings (tonnes) and percentage reduction.
    Used in the report's emissions comparison section.

    Args:
        technology_co2_tonnes: Annual CO₂ for the alternative technology.
        diesel_co2_tonnes: Annual CO₂ for the diesel baseline.

    Returns:
        Dict with 'absolute_tonnes' and 'percentage' keys.

    Example:
        >>> savings = co2_savings_vs_diesel(100.0, 500.0)
        >>> print(f"Saves {savings['absolute_tonnes']:.0f} t ({savings['percentage']:.0f}%)")
        Saves 400 t (80%)
    """
    absolute = diesel_co2_tonnes - technology_co2_tonnes

    if diesel_co2_tonnes > 0:
        percentage = (absolute / diesel_co2_tonnes) * 100
    else:
        percentage = 0.0

    return {
        "absolute_tonnes": round(absolute, 2),
        "percentage": round(percentage, 1),
    }


# ─────────────────────────────────────────────────────────────
# Firm Capacity Advisory (Preset Engineering Methodology)
# ─────────────────────────────────────────────────────────────
# When the hourly simulation shows IT capacity varies by hour
# (power-constrained mode), "firm capacity" is the guaranteed IT
# load available year-round. The gap between firm capacity and
# mean/peak capacity can be bridged with mitigation strategies.
#
# This advisory uses preset engineering assumptions -- no manual
# user input required. It auto-suggests backup technologies and
# quantities based on the hourly simulation results.
#
# Reference: Architecture Agreement v3.0, Section 3.7
# ─────────────────────────────────────────────────────────────

# Engineering cost assumptions for mitigation strategies (2025 USD)
# These are budget-grade estimates for feasibility screening.
MITIGATION_COST_ASSUMPTIONS: dict[str, dict] = {
    "tes_chilled_water": {
        "capex_usd_per_kwh_thermal": 35.0,
        # Source: ASHRAE HVAC Applications Ch.51 — stratified chilled water TES.
        # Typical range: $25–50/kWh_th. Using $35 as midpoint for steel tanks.
        "description": "Chilled water thermal energy storage (stratified tank)",
        "source": "ASHRAE HVAC Applications Ch.51; Trane/BAC TES guidance",
    },
    "trim_chiller": {
        "capex_usd_per_kw": 400.0,
        # Source: RSMeans/Carrier — air-cooled scroll chiller (100–500 kW class).
        # Typical range: $300–600/kW installed. Using $400 for modular trim units.
        "description": "Supplemental trim chiller for hot-hour cooling peaks",
        "source": "RSMeans Mechanical; Carrier/Trane chiller selection guides",
    },
    "bess": {
        "capex_usd_per_kwh": 350.0,
        # Source: BloombergNEF LCOE 2024 — utility-scale Li-ion BESS.
        # Range: $250–500/kWh installed. Using $350 for containerized DC BESS.
        "description": "Battery energy storage system (Li-ion, containerized)",
        "source": "BloombergNEF LCOE 2024; Tesla/BYD BESS datasheets",
    },
    "it_load_management": {
        "capex_usd_per_kw": 0.0,
        # IT load management (throttling/scheduling) has no direct capex.
        # Operational cost is in reduced compute throughput.
        "description": "IT workload throttling / deferral during peak cooling hours",
        "source": "Engineering judgment — software-defined power management",
    },
}

# Default cooling COP at peak conditions for TES sizing
# When the hourly COP drops at peak ambient temperature, TES can
# supply pre-chilled water to absorb the cooling deficit.
DEFAULT_TES_COP_PEAK = 3.5  # Conservative COP at design hot conditions
DEFAULT_TES_CHARGE_COP = 6.0  # COP during overnight off-peak charging


@dataclass
class MitigationStrategy:
    """One recommended mitigation to close the firm capacity gap.

    Attributes:
        key: Machine-readable identifier.
        label: Human-readable strategy name.
        description: What this strategy does.
        capacity_kw: How much additional IT capacity this unlocks (kW).
        capacity_mw: Same in MW.
        estimated_capex_usd: Budget-grade capital cost estimate.
        sizing_summary: Human-readable sizing details.
        notes: Engineering notes and assumptions.
    """
    key: str
    label: str
    description: str
    capacity_kw: float
    capacity_mw: float
    estimated_capex_usd: float
    sizing_summary: str
    notes: list[str]


@dataclass
class FirmCapacityAdvisory:
    """Auto-computed firm capacity analysis with preset methodology.

    No user input required. All sizing and cost estimates use
    built-in engineering assumptions from the BACKUP_POWER profiles.

    Attributes:
        firm_capacity_kw: P99 IT capacity (guaranteed 99% of hours).
        firm_capacity_mw: Same in MW.
        mean_capacity_kw: Mean hourly IT capacity.
        mean_capacity_mw: Same in MW.
        worst_capacity_kw: Worst-hour IT capacity.
        worst_capacity_mw: Same in MW.
        best_capacity_kw: Best-hour IT capacity.
        best_capacity_mw: Same in MW.
        capacity_gap_kw: mean_capacity - firm_capacity (opportunity).
        capacity_gap_mw: Same in MW.
        peak_deficit_kw: mean_capacity - worst_capacity (max instantaneous shortfall below mean).
        peak_deficit_mw: Same in MW.
        deficit_hours: Number of hours where IT capacity < mean capacity.
        deficit_energy_kwh: Total energy shortfall below mean capacity.
        strategies: Recommended mitigation strategies with sizing/cost.
    """
    firm_capacity_kw: float
    firm_capacity_mw: float
    mean_capacity_kw: float
    mean_capacity_mw: float
    worst_capacity_kw: float
    worst_capacity_mw: float
    best_capacity_kw: float
    best_capacity_mw: float
    capacity_gap_kw: float
    capacity_gap_mw: float
    peak_deficit_kw: float
    peak_deficit_mw: float
    deficit_hours: int
    deficit_energy_kwh: float
    strategies: list[MitigationStrategy]


def compute_firm_capacity_advisory(
    hourly_it_kw: list[float],
    facility_power_kw: float,
    annual_pue: float,
    cooling_type: str,
) -> FirmCapacityAdvisory:
    """Compute firm capacity advisory with preset engineering methodology.

    Analyses the hourly IT capacity profile from a power-constrained
    simulation and auto-generates mitigation strategies to close the
    gap between firm (P99) and mean capacity. No user input required.

    The advisory answers: "Given this site's climate and cooling system,
    what is the guaranteed IT capacity, and what would it cost to
    increase it?"

    Mitigation strategies considered (real backup power technologies):
        1. SOFC Fuel Cell — NG/Biogas/H₂, 60% efficiency, 300 kW modules.
        2. PEM Fuel Cell — Green H₂, 50% efficiency, 250 kW modules, zero CO₂.
        3. BESS (Li-ion) — Battery storage, 87.5% roundtrip efficiency.
        4. Rotary UPS + Flywheel — 2 MW modules, instant ramp, bridging.
        5. Diesel Genset — 2 MW modules, 12s ramp (reference, not green).
        6. Natural Gas Genset — 2.5 MW modules, 45s ramp (reference).

    Args:
        hourly_it_kw: Per-hour IT capacity from power-constrained sim (kW).
            Typically 8,760 values from simulate_hourly().
        facility_power_kw: Fixed facility power (grid cap) in kW.
        annual_pue: Energy-weighted annual PUE from the simulation.
        cooling_type: Key from COOLING_PROFILES (for TES sizing context).

    Returns:
        FirmCapacityAdvisory with firm capacity, gap analysis,
        and recommended strategies with quantities and costs.

    Raises:
        ValueError: If hourly_it_kw is empty.

    Example:
        >>> from engine.pue_engine import simulate_hourly
        >>> sim = simulate_hourly(temps, None, "Air-Cooled Chiller + Economizer",
        ...                       eta_chain=0.95, facility_power_kw=50000)
        >>> advisory = compute_firm_capacity_advisory(
        ...     sim.hourly_it_kw, 50000, sim.annual_pue,
        ...     "Air-Cooled Chiller + Economizer")
        >>> print(f"Firm: {advisory.firm_capacity_mw:.2f} MW")
        >>> for s in advisory.strategies:
        ...     print(f"  {s.label}: +{s.capacity_mw:.2f} MW, ${s.estimated_capex_usd:,.0f}")
    """
    if not hourly_it_kw:
        raise ValueError("hourly_it_kw must not be empty")

    n = len(hourly_it_kw)
    sorted_it = sorted(hourly_it_kw)

    # ── Capacity spectrum ──
    worst_kw = sorted_it[0]
    best_kw = sorted_it[-1]
    mean_kw = sum(hourly_it_kw) / n

    # P99 = value at 1st percentile (available 99% of hours)
    p99_idx = max(0, min(n - 1, int(math.floor(n * 0.01))))
    firm_kw = sorted_it[p99_idx]

    # ── Gap analysis ──
    # Capacity gap: how much more IT we could serve if we could
    # flatten the curve from firm to mean
    capacity_gap_kw = max(0.0, mean_kw - firm_kw)

    # Peak deficit: how far worst hour is below MEAN capacity
    # This is the maximum instantaneous shortfall that mitigation must cover
    peak_deficit_kw = max(0.0, mean_kw - worst_kw)

    # Count deficit hours and energy below MEAN capacity
    # These are the hours where hourly IT < Mean (weather anomaly pushes cooling up)
    # Compensating this deficit energy effectively raises guaranteed capacity
    # from P99 to Mean.
    deficit_hours = 0
    deficit_energy_kwh = 0.0
    for it_kw in hourly_it_kw:
        if it_kw < mean_kw:
            deficit_hours += 1
            deficit_energy_kwh += (mean_kw - it_kw)

    # ── Mitigation strategies ──
    # Real backup/supplemental power technologies from the backup power
    # comparison module. Each is sized to cover the deficit energy
    # (below mean) so that guaranteed capacity rises from P99 to Mean.
    strategies: list[MitigationStrategy] = []

    if peak_deficit_kw > 0 and deficit_energy_kwh > 0:
        deficit_energy_mwh = deficit_energy_kwh / 1000

        # ── Strategy 1: SOFC Fuel Cell ──
        # NG/Biogas/H2, 60% electrical efficiency, 300 kW modules, 300s ramp
        sofc_profile = BACKUP_POWER["SOFC Fuel Cell"]
        sofc_module_kw = float(sofc_profile["module_size_kw"])
        sofc_eff = (sofc_profile["efficiency_min"] + sofc_profile["efficiency_max"]) / 2
        sofc_num_modules = math.ceil(peak_deficit_kw / sofc_module_kw)
        sofc_total_kw = sofc_num_modules * sofc_module_kw
        sofc_capex_per_kw = 6000.0  # $/kW installed (Bloom Energy range $5k-$8k/kW)
        sofc_capex = sofc_total_kw * sofc_capex_per_kw

        strategies.append(MitigationStrategy(
            key="sofc_fuel_cell",
            label="SOFC Fuel Cell",
            description=(
                "Solid Oxide Fuel Cell running on Natural Gas, Biogas, or H₂. "
                "High electrical efficiency (60%), suitable for continuous or "
                "long-duration deficit compensation."
            ),
            capacity_kw=round(peak_deficit_kw, 1),
            capacity_mw=round(peak_deficit_kw / 1000, 3),
            estimated_capex_usd=round(sofc_capex, 0),
            sizing_summary=(
                f"{sofc_num_modules} × {sofc_module_kw:.0f} kW SOFC modules = "
                f"{sofc_total_kw:,.0f} kW, covering {deficit_energy_mwh:,.1f} MWh deficit"
            ),
            notes=[
                f"Fuel: {sofc_profile['fuel']} | Electrical efficiency: {sofc_eff * 100:.0f}%.",
                f"Ramp time: {sofc_profile['ramp_time_seconds']}s (warm start). Best for baseload deficit.",
                f"CO₂: {sofc_profile['co2_kg_per_kwh_fuel']} kg/kWh (NG basis); zero on biogas/H₂.",
                f"Source: {sofc_profile['source']}",
            ],
        ))

        # ── Strategy 2: PEM Fuel Cell (Green H₂) ──
        # 50% electrical efficiency, 250 kW modules, 5s ramp, zero CO₂
        pem_profile = BACKUP_POWER["PEM Fuel Cell (H₂)"]
        pem_module_kw = float(pem_profile["module_size_kw"])
        pem_eff = (pem_profile["efficiency_min"] + pem_profile["efficiency_max"]) / 2
        pem_num_modules = math.ceil(peak_deficit_kw / pem_module_kw)
        pem_total_kw = pem_num_modules * pem_module_kw
        pem_capex_per_kw = 4000.0  # $/kW installed (Ballard/Plug Power range $3k-$5k/kW)
        pem_capex = pem_total_kw * pem_capex_per_kw

        strategies.append(MitigationStrategy(
            key="pem_fuel_cell",
            label="PEM Fuel Cell (Green H₂)",
            description=(
                "Proton Exchange Membrane Fuel Cell powered by green hydrogen. "
                "Zero CO₂ emissions, fast ramp (5s), suitable for rapid deficit response."
            ),
            capacity_kw=round(peak_deficit_kw, 1),
            capacity_mw=round(peak_deficit_kw / 1000, 3),
            estimated_capex_usd=round(pem_capex, 0),
            sizing_summary=(
                f"{pem_num_modules} × {pem_module_kw:.0f} kW PEM modules = "
                f"{pem_total_kw:,.0f} kW, covering {deficit_energy_mwh:,.1f} MWh deficit"
            ),
            notes=[
                f"Fuel: {pem_profile['fuel']} | Electrical efficiency: {pem_eff * 100:.0f}%.",
                f"Ramp time: {pem_profile['ramp_time_seconds']}s. Fast response for transient deficits.",
                "Zero CO₂ emissions (green hydrogen pathway).",
                f"Source: {pem_profile['source']}",
            ],
        ))

        # ── Strategy 3: BESS (Li-ion) ──
        # Battery energy storage, 87.5% roundtrip efficiency, sized to deficit energy
        bess_roundtrip_eff = 0.875
        bess_cost_per_kwh = 350.0  # $/kWh installed (BloombergNEF 2024)
        bess_energy_kwh_sized = deficit_energy_kwh / bess_roundtrip_eff
        bess_capex = bess_energy_kwh_sized * bess_cost_per_kwh

        strategies.append(MitigationStrategy(
            key="bess_li_ion",
            label="BESS (Li-ion)",
            description=(
                "Containerized lithium-ion battery energy storage. Charged from "
                "the grid during off-peak cooling hours and discharged during "
                "deficit hours to maintain IT capacity at mean level."
            ),
            capacity_kw=round(peak_deficit_kw, 1),
            capacity_mw=round(peak_deficit_kw / 1000, 3),
            estimated_capex_usd=round(bess_capex, 0),
            sizing_summary=(
                f"BESS: {bess_energy_kwh_sized:,.0f} kWh "
                f"({bess_energy_kwh_sized / max(peak_deficit_kw, 1):.1f}h at "
                f"{peak_deficit_kw:,.0f} kW peak deficit), "
                f"covering {deficit_energy_mwh:,.1f} MWh deficit"
            ),
            notes=[
                f"Roundtrip efficiency: {bess_roundtrip_eff * 100:.1f}%.",
                f"Sized to total deficit energy: {deficit_energy_kwh:,.0f} kWh over {deficit_hours} hours.",
                f"Estimated cost: ${bess_cost_per_kwh:.0f}/kWh installed.",
                "Source: BloombergNEF LCOE 2024; Tesla/BYD BESS datasheets.",
            ],
        ))

        # ── Strategy 4: Rotary UPS + Flywheel ──
        # 2 MW modules, 0s ramp (instant), short-duration bridging
        rotary_profile = BACKUP_POWER["Rotary UPS + Flywheel"]
        rotary_module_kw = float(rotary_profile["module_size_kw"])
        rotary_num_modules = math.ceil(peak_deficit_kw / rotary_module_kw)
        rotary_total_kw = rotary_num_modules * rotary_module_kw
        rotary_capex_per_kw = 800.0  # $/kW installed (Hitec/Piller DRUPS)
        rotary_capex = rotary_total_kw * rotary_capex_per_kw

        strategies.append(MitigationStrategy(
            key="rotary_ups_flywheel",
            label="Rotary UPS + Flywheel",
            description=(
                "Dynamic Rotary UPS with integrated flywheel for instant (0s) "
                "power bridging. Provides short-duration ride-through while "
                "longer-duration assets ramp up."
            ),
            capacity_kw=round(peak_deficit_kw, 1),
            capacity_mw=round(peak_deficit_kw / 1000, 3),
            estimated_capex_usd=round(rotary_capex, 0),
            sizing_summary=(
                f"{rotary_num_modules} × {rotary_module_kw / 1000:.0f} MW DRUPS modules = "
                f"{rotary_total_kw / 1000:,.1f} MW, instant bridge for {peak_deficit_kw:,.0f} kW deficit"
            ),
            notes=[
                f"Ramp time: {rotary_profile['ramp_time_seconds']}s (instant — kinetic energy).",
                "Bridge power only (15–60 seconds). Pairs with gensets or fuel cells for sustained deficit.",
                f"No fuel consumed. Zero emissions.",
                f"Source: {rotary_profile['source']}",
            ],
        ))

        # ── Strategy 5: Diesel Genset ──
        # 2 MW modules, 12s ramp (backup comparison reference)
        diesel_profile = BACKUP_POWER["Diesel Genset"]
        diesel_module_kw = float(diesel_profile["module_size_kw"])
        diesel_num_modules = math.ceil(peak_deficit_kw / diesel_module_kw)
        diesel_total_kw = diesel_num_modules * diesel_module_kw
        diesel_capex_per_kw = 500.0  # $/kW installed (Caterpillar/Cummins)
        diesel_capex = diesel_total_kw * diesel_capex_per_kw

        strategies.append(MitigationStrategy(
            key="diesel_genset",
            label="Diesel Genset",
            description=(
                "Diesel generator set — conventional backup power reference. "
                "Fast ramp (12s), proven technology, but high CO₂ emissions."
            ),
            capacity_kw=round(peak_deficit_kw, 1),
            capacity_mw=round(peak_deficit_kw / 1000, 3),
            estimated_capex_usd=round(diesel_capex, 0),
            sizing_summary=(
                f"{diesel_num_modules} × {diesel_module_kw / 1000:.0f} MW diesel gensets = "
                f"{diesel_total_kw / 1000:,.1f} MW, covering {deficit_energy_mwh:,.1f} MWh deficit"
            ),
            notes=[
                f"Fuel: {diesel_profile['fuel']} | Efficiency: "
                f"{(diesel_profile['efficiency_min'] + diesel_profile['efficiency_max']) / 2 * 100:.0f}%.",
                f"Ramp time: {diesel_profile['ramp_time_seconds']}s.",
                f"High emissions: {diesel_profile['co2_kg_per_kwh_fuel']} kg CO₂/kWh fuel. Not a green pathway.",
                f"Source: {diesel_profile['source']}",
            ],
        ))

        # ── Strategy 6: Natural Gas Genset ──
        # 2.5 MW modules, 45s ramp (backup comparison reference)
        ng_profile = BACKUP_POWER["Natural Gas Genset"]
        ng_module_kw = float(ng_profile["module_size_kw"])
        ng_num_modules = math.ceil(peak_deficit_kw / ng_module_kw)
        ng_total_kw = ng_num_modules * ng_module_kw
        ng_capex_per_kw = 600.0  # $/kW installed (Caterpillar/Wärtsilä)
        ng_capex = ng_total_kw * ng_capex_per_kw

        strategies.append(MitigationStrategy(
            key="natural_gas_genset",
            label="Natural Gas Genset",
            description=(
                "Natural gas reciprocating engine generator — lower emissions "
                "than diesel, dual-fuel capable. Backup comparison reference."
            ),
            capacity_kw=round(peak_deficit_kw, 1),
            capacity_mw=round(peak_deficit_kw / 1000, 3),
            estimated_capex_usd=round(ng_capex, 0),
            sizing_summary=(
                f"{ng_num_modules} × {ng_module_kw / 1000:.1f} MW NG gensets = "
                f"{ng_total_kw / 1000:,.1f} MW, covering {deficit_energy_mwh:,.1f} MWh deficit"
            ),
            notes=[
                f"Fuel: {ng_profile['fuel']} | Efficiency: "
                f"{(ng_profile['efficiency_min'] + ng_profile['efficiency_max']) / 2 * 100:.0f}%.",
                f"Ramp time: {ng_profile['ramp_time_seconds']}s.",
                f"Medium emissions: {ng_profile['co2_kg_per_kwh_fuel']} kg CO₂/kWh fuel.",
                f"Source: {ng_profile['source']}",
            ],
        ))

        # ── Strategy 7: Thermal Energy Storage (TES) ──
        # Chilled water buffer tanks to absorb cooling peaks
        tes_cost_per_kwh_thermal = 50.0  # $/kWh-thermal for chilled water TES
        tes_energy_kwh = deficit_energy_kwh  # size to total deficit
        tes_capex = tes_energy_kwh * tes_cost_per_kwh_thermal

        strategies.append(MitigationStrategy(
            key="tes",
            label="Thermal Energy Storage (TES)",
            description=(
                "Chilled water buffer tanks that pre-cool during off-peak hours and "
                "absorb cooling peaks during high-temperature periods, reducing "
                "cooling-driven IT capacity curtailment."
            ),
            capacity_kw=round(peak_deficit_kw, 1),
            capacity_mw=round(peak_deficit_kw / 1000, 3),
            estimated_capex_usd=round(tes_capex, 0),
            sizing_summary=(
                f"TES: {tes_energy_kwh:,.0f} kWh-thermal storage, "
                f"bridging {deficit_hours} deficit hours at up to {peak_deficit_kw:,.0f} kW peak"
            ),
            notes=[
                "Pre-chills water during off-peak hours for use during cooling peaks.",
                "Zero emissions — uses existing chiller plant off-peak capacity.",
                "Requires plant room space for buffer tanks.",
                "Best paired with economizer or chiller-based cooling systems.",
            ],
        ))

        # ── Strategy 8: IT Load Management ──
        # Throttle non-critical workloads during peak cooling hours (zero capex)
        strategies.append(MitigationStrategy(
            key="it_load_mgmt",
            label="IT Load Management",
            description=(
                "Dynamic workload throttling during peak cooling hours. Reduces "
                "non-critical IT load to maintain critical services within the "
                "available cooling envelope. Zero CapEx — operational measure."
            ),
            capacity_kw=round(peak_deficit_kw, 1),
            capacity_mw=round(peak_deficit_kw / 1000, 3),
            estimated_capex_usd=0,
            sizing_summary=(
                f"Shed up to {peak_deficit_kw:,.0f} kW non-critical IT during "
                f"{deficit_hours} deficit hours ({deficit_hours / max(n, 1) * 100:.1f}% of year)"
            ),
            notes=[
                "Zero CapEx — operational measure only.",
                "Requires workload classification and orchestration (e.g., Kubernetes resource limits).",
                "Impacts SLA for non-critical workloads during deficit hours.",
                "Can be combined with other strategies for partial mitigation.",
            ],
        ))

    return FirmCapacityAdvisory(
        firm_capacity_kw=round(firm_kw, 1),
        firm_capacity_mw=round(firm_kw / 1000, 3),
        mean_capacity_kw=round(mean_kw, 1),
        mean_capacity_mw=round(mean_kw / 1000, 3),
        worst_capacity_kw=round(worst_kw, 1),
        worst_capacity_mw=round(worst_kw / 1000, 3),
        best_capacity_kw=round(best_kw, 1),
        best_capacity_mw=round(best_kw / 1000, 3),
        capacity_gap_kw=round(capacity_gap_kw, 1),
        capacity_gap_mw=round(capacity_gap_kw / 1000, 3),
        peak_deficit_kw=round(peak_deficit_kw, 1),
        peak_deficit_mw=round(peak_deficit_kw / 1000, 3),
        deficit_hours=deficit_hours,
        deficit_energy_kwh=round(deficit_energy_kwh, 1),
        strategies=strategies,
    )
