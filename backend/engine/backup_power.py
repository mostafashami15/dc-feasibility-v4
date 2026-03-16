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
