"""
DC Feasibility Tool v4 — Green Energy Dispatch Simulation
===========================================================
Simulates hourly dispatch of renewable energy sources against the
data center's overhead demand (facility power minus IT load).

6-step dispatch priority (Architecture Agreement Section 3.9):
    For each hour t:
        overhead_kW(t) = P_facility(t) − P_IT(t)

        1. PV generation → apply to overhead (direct offset)
        2. Surplus PV → charge BESS (bounded by capacity and η)
        3. Remaining surplus → export to grid (or curtail)
        4. Remaining deficit → discharge BESS
        5. Remaining deficit → fuel cell dispatch
        6. Remaining deficit → grid import

BESS model (Section 3.9):
    η_roundtrip ≈ 0.85–0.90 (Source: NREL ATB 2024, lithium-ion)
    η_oneway = √(η_roundtrip)
    SoC(t+1) = SoC(t) + charge(t) × η_oneway − discharge(t) / η_oneway
    SoC bounded [0, capacity_kWh]

Known simplifications (documented, acceptable for feasibility):
    - No C-rate limit on BESS
    - No battery degradation over project life
    - No behind-the-meter grid export constraints
    - Fuel cell treated as clean dispatchable (fuel source not detailed)

This module does NOT affect PUE or IT capacity. Green energy compensates
overhead AFTER the hourly PUE simulation runs.

This module does NOT fetch PV data. It takes hourly PV generation
as an input array supplied by the caller.

Reference: Architecture Agreement v3.0, Section 3.9
"""

import math
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

DEFAULT_BESS_ROUNDTRIP_EFF = 0.875
# Midpoint of 0.85–0.90 range for lithium-ion batteries.
# Source: NREL Annual Technology Baseline (ATB) 2024,
# utility-scale battery storage section.

DEFAULT_FUEL_CELL_CAPACITY_KW = 0.0
# Default: no fuel cell installed. User must explicitly set capacity.

# CO₂ grid emission factor for Italy
DEFAULT_GRID_CO2_KG_PER_KWH = 0.256
# Source: ISPRA (Italian National Institute for Environmental Protection),
# "Fattori di emissione atmosferica di gas a effetto serra nel settore
# elettrico nazionale e nei principali Paesi Europei" (2023).
# Italy 2022 grid average: ~256 g CO₂/kWh.


# ─────────────────────────────────────────────────────────────
# Result Data Classes
# ─────────────────────────────────────────────────────────────

@dataclass
class HourlyDispatchState:
    """Dispatch result for a single hour.

    Tracks exactly how each kWh of overhead was served.
    """
    hour: int
    overhead_kw: float       # P_facility − P_IT (demand to cover)
    pv_generation_kw: float  # PV output this hour
    pv_to_overhead_kw: float  # Step 1: PV directly offsetting overhead
    pv_to_bess_kw: float     # Step 2: surplus PV charging BESS
    pv_curtailed_kw: float   # Step 3: surplus PV exported/curtailed
    bess_discharge_kw: float  # Step 4: BESS discharging to cover deficit
    fuel_cell_kw: float      # Step 5: fuel cell dispatch
    grid_import_kw: float    # Step 6: remaining deficit from grid
    bess_soc_kwh: float      # BESS state of charge after this hour


@dataclass
class GreenEnergyResult:
    """Complete annual green energy simulation result.

    Contains both hourly dispatch detail and annual summary metrics.
    Used for the Green Energy page and the detailed technical report.
    """

    # ── Hourly arrays (for dispatch visualization) ──
    hourly_dispatch: list[HourlyDispatchState] = field(default_factory=list)

    # ── Annual energy totals (kWh) ──
    total_overhead_kwh: float = 0.0
    total_pv_generation_kwh: float = 0.0
    total_pv_to_overhead_kwh: float = 0.0
    total_pv_to_bess_kwh: float = 0.0
    total_pv_curtailed_kwh: float = 0.0
    total_bess_discharge_kwh: float = 0.0
    total_fuel_cell_kwh: float = 0.0
    total_grid_import_kwh: float = 0.0

    # ── Coverage and renewable metrics ──
    overhead_coverage_fraction: float = 0.0
    # Fraction of overhead covered by green sources (PV + BESS + FC).
    # = (total_pv_to_overhead + total_bess_discharge + total_fuel_cell)
    #   / total_overhead
    # 1.0 = 100% of overhead covered by renewables.

    renewable_fraction: float = 0.0
    # Fraction of total facility energy from renewable sources.
    # = green_energy_total / total_facility_energy

    pv_self_consumption_fraction: float = 0.0
    # Fraction of PV generation used on-site (not curtailed).
    # = (pv_to_overhead + pv_to_bess) / pv_generation

    bess_cycles_equivalent: float = 0.0
    # Equivalent full charge-discharge cycles per year.
    # = total_bess_discharge / bess_capacity (if capacity > 0)

    # ── CO₂ metrics ──
    co2_avoided_tonnes: float = 0.0
    # CO₂ avoided by not importing from grid.
    # = (green_kWh_used) × grid_co2_factor / 1000

    # ── Configuration echo ──
    pv_capacity_kwp: float = 0.0
    bess_capacity_kwh: float = 0.0
    bess_roundtrip_efficiency: float = 0.0
    fuel_cell_capacity_kw: float = 0.0
    total_facility_kwh: float = 0.0
    total_it_kwh: float = 0.0


@dataclass
class FirmCapacityDispatchHour:
    """One hour of peak-support dispatch for a constant IT target."""
    hour: int
    facility_required_kw: float
    pv_generation_kw: float
    pv_direct_kw: float
    grid_to_load_kw: float
    pv_to_bess_kw: float
    grid_to_bess_kw: float
    pv_curtailed_kw: float
    bess_discharge_kw: float
    fuel_cell_kw: float
    backup_dispatch_kw: float
    unmet_kw: float
    bess_soc_kwh: float


@dataclass
class FirmCapacitySupportResult:
    """Annual result for sustaining a constant IT target under a grid cap."""

    feasible: bool
    target_it_kw: float
    grid_capacity_kw: float
    max_required_facility_kw: float
    peak_support_kw: float
    peak_unmet_kw: float
    hours_above_grid_cap: int
    hours_with_capacity_support: int
    unmet_hours: int
    total_required_facility_kwh: float
    total_grid_to_load_kwh: float
    total_grid_to_bess_kwh: float
    total_pv_generation_kwh: float
    total_pv_direct_kwh: float
    total_pv_to_bess_kwh: float
    total_pv_curtailed_kwh: float
    total_bess_discharge_kwh: float
    total_fuel_cell_kwh: float
    total_backup_dispatch_kwh: float
    total_unmet_kwh: float
    initial_bess_soc_kwh: float
    final_bess_soc_kwh: float
    cyclic_bess: bool = False
    cyclic_converged: bool = True
    hourly_dispatch: list[FirmCapacityDispatchHour] = field(default_factory=list)


@dataclass
class SupportRecommendation:
    """One deterministic support pathway for a chosen IT target."""

    key: str
    label: str
    description: str
    target_it_kw: float
    feasible: bool
    bess_capacity_kwh: float
    fuel_cell_capacity_kw: float
    backup_dispatch_capacity_kw: float
    peak_support_kw: float
    hours_with_capacity_support: int
    total_grid_to_bess_kwh: float
    total_bess_discharge_kwh: float
    total_fuel_cell_kwh: float
    total_backup_dispatch_kwh: float
    total_unmet_kwh: float
    notes: list[str] = field(default_factory=list)


@dataclass
class SupportRecommendationBundle:
    """Support recommendations for closing the grid-only capacity gap."""

    target_it_kw: float
    target_already_feasible: bool
    annual_support_energy_kwh: float
    peak_support_kw: float
    hours_above_grid_cap: int
    gap_vs_p99_kw: float
    gap_vs_worst_kw: float
    candidates: list[SupportRecommendation] = field(default_factory=list)


def _validate_bess_and_dispatch_inputs(
    bess_capacity_kwh: float,
    bess_roundtrip_efficiency: float,
    bess_initial_soc_kwh: float,
    fuel_cell_capacity_kw: float,
    backup_dispatch_capacity_kw: float,
) -> None:
    """Validate shared storage/dispatch parameters."""
    if bess_capacity_kwh < 0:
        raise ValueError(f"bess_capacity_kwh cannot be negative: {bess_capacity_kwh}")
    if not (0 < bess_roundtrip_efficiency <= 1.0):
        raise ValueError(
            f"bess_roundtrip_efficiency must be in (0, 1.0]: {bess_roundtrip_efficiency}"
        )
    if bess_initial_soc_kwh < 0:
        raise ValueError(f"bess_initial_soc_kwh cannot be negative: {bess_initial_soc_kwh}")
    if bess_initial_soc_kwh > bess_capacity_kwh:
        raise ValueError(
            f"bess_initial_soc_kwh ({bess_initial_soc_kwh}) > "
            f"bess_capacity_kwh ({bess_capacity_kwh})"
        )
    if fuel_cell_capacity_kw < 0:
        raise ValueError(
            f"fuel_cell_capacity_kw cannot be negative: {fuel_cell_capacity_kw}"
        )
    if backup_dispatch_capacity_kw < 0:
        raise ValueError(
            "backup_dispatch_capacity_kw cannot be negative: "
            f"{backup_dispatch_capacity_kw}"
        )


def _prepare_pv_array(
    n_hours: int,
    hourly_pv_kw: Optional[list[float]],
) -> list[float]:
    """Return a non-negative PV array matching the dispatch horizon."""
    if hourly_pv_kw is None:
        return [0.0] * n_hours
    if len(hourly_pv_kw) != n_hours:
        raise ValueError(
            f"hourly_pv_kw length ({len(hourly_pv_kw)}) != "
            f"required length ({n_hours})"
        )
    return [max(0.0, value) for value in hourly_pv_kw]


def _simulate_firm_capacity_once(
    hourly_facility_factors: list[float],
    target_it_kw: float,
    grid_capacity_kw: float,
    hourly_pv_kw: Optional[list[float]] = None,
    bess_capacity_kwh: float = 0.0,
    bess_roundtrip_efficiency: float = DEFAULT_BESS_ROUNDTRIP_EFF,
    bess_initial_soc_kwh: float = 0.0,
    fuel_cell_capacity_kw: float = DEFAULT_FUEL_CELL_CAPACITY_KW,
    backup_dispatch_capacity_kw: float = 0.0,
) -> FirmCapacitySupportResult:
    """Dispatch support assets for one full year at a fixed IT target."""
    n_hours = len(hourly_facility_factors)
    if n_hours == 0:
        raise ValueError("hourly_facility_factors must not be empty")
    if target_it_kw < 0:
        raise ValueError(f"target_it_kw cannot be negative: {target_it_kw}")
    if grid_capacity_kw < 0:
        raise ValueError(f"grid_capacity_kw cannot be negative: {grid_capacity_kw}")

    _validate_bess_and_dispatch_inputs(
        bess_capacity_kwh=bess_capacity_kwh,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        bess_initial_soc_kwh=bess_initial_soc_kwh,
        fuel_cell_capacity_kw=fuel_cell_capacity_kw,
        backup_dispatch_capacity_kw=backup_dispatch_capacity_kw,
    )

    pv_profile = _prepare_pv_array(n_hours, hourly_pv_kw)
    eta_oneway = math.sqrt(bess_roundtrip_efficiency)
    soc = bess_initial_soc_kwh
    hourly_dispatch: list[FirmCapacityDispatchHour] = []

    max_required_facility = 0.0
    peak_support = 0.0
    peak_unmet = 0.0
    hours_above_grid_cap = 0
    hours_with_capacity_support = 0
    unmet_hours = 0

    total_required_facility = 0.0
    total_grid_to_load = 0.0
    total_grid_to_bess = 0.0
    total_pv_generation = 0.0
    total_pv_direct = 0.0
    total_pv_to_bess = 0.0
    total_pv_curtailed = 0.0
    total_bess_discharge = 0.0
    total_fuel_cell = 0.0
    total_backup_dispatch = 0.0
    total_unmet = 0.0

    for hour, factor in enumerate(hourly_facility_factors):
        pv = pv_profile[hour]
        facility_required = target_it_kw * factor
        max_required_facility = max(max_required_facility, facility_required)

        if facility_required > grid_capacity_kw:
            hours_above_grid_cap += 1

        pv_direct = min(facility_required, pv)
        residual_after_pv = facility_required - pv_direct

        grid_to_load = min(residual_after_pv, grid_capacity_kw)
        deficit = residual_after_pv - grid_to_load

        bess_discharge = 0.0
        if deficit > 0 and soc > 0 and bess_capacity_kwh > 0:
            max_deliver = soc * eta_oneway
            bess_discharge = min(deficit, max_deliver)
            soc -= bess_discharge / eta_oneway
            deficit -= bess_discharge

        fuel_cell = 0.0
        if deficit > 0 and fuel_cell_capacity_kw > 0:
            fuel_cell = min(deficit, fuel_cell_capacity_kw)
            deficit -= fuel_cell

        backup_dispatch = 0.0
        if deficit > 0 and backup_dispatch_capacity_kw > 0:
            backup_dispatch = min(deficit, backup_dispatch_capacity_kw)
            deficit -= backup_dispatch

        unmet = deficit
        if unmet > 0:
            unmet_hours += 1

        pv_surplus = pv - pv_direct
        pv_to_bess = 0.0
        grid_to_bess = 0.0
        pv_curtailed = pv_surplus
        grid_headroom = max(0.0, grid_capacity_kw - grid_to_load)

        if bess_capacity_kwh > 0 and soc < bess_capacity_kwh and eta_oneway > 0:
            headroom = bess_capacity_kwh - soc
            max_charge_input = headroom / eta_oneway

            pv_to_bess = min(pv_surplus, max_charge_input)
            soc += pv_to_bess * eta_oneway
            pv_curtailed = pv_surplus - pv_to_bess

            remaining_charge_input = max_charge_input - pv_to_bess
            grid_to_bess = min(grid_headroom, remaining_charge_input)
            soc += grid_to_bess * eta_oneway

        soc = max(0.0, min(soc, bess_capacity_kwh))

        support_this_hour = pv_direct + bess_discharge + fuel_cell + backup_dispatch
        if support_this_hour > 0 and facility_required > grid_capacity_kw:
            hours_with_capacity_support += 1

        peak_support = max(peak_support, support_this_hour)
        peak_unmet = max(peak_unmet, unmet)

        hourly_dispatch.append(FirmCapacityDispatchHour(
            hour=hour,
            facility_required_kw=round(facility_required, 4),
            pv_generation_kw=round(pv, 4),
            pv_direct_kw=round(pv_direct, 4),
            grid_to_load_kw=round(grid_to_load, 4),
            pv_to_bess_kw=round(pv_to_bess, 4),
            grid_to_bess_kw=round(grid_to_bess, 4),
            pv_curtailed_kw=round(pv_curtailed, 4),
            bess_discharge_kw=round(bess_discharge, 4),
            fuel_cell_kw=round(fuel_cell, 4),
            backup_dispatch_kw=round(backup_dispatch, 4),
            unmet_kw=round(unmet, 4),
            bess_soc_kwh=round(soc, 4),
        ))

        total_required_facility += facility_required
        total_grid_to_load += grid_to_load
        total_grid_to_bess += grid_to_bess
        total_pv_generation += pv
        total_pv_direct += pv_direct
        total_pv_to_bess += pv_to_bess
        total_pv_curtailed += pv_curtailed
        total_bess_discharge += bess_discharge
        total_fuel_cell += fuel_cell
        total_backup_dispatch += backup_dispatch
        total_unmet += unmet

    return FirmCapacitySupportResult(
        feasible=total_unmet <= 1e-6,
        target_it_kw=round(target_it_kw, 4),
        grid_capacity_kw=round(grid_capacity_kw, 4),
        max_required_facility_kw=round(max_required_facility, 4),
        peak_support_kw=round(peak_support, 4),
        peak_unmet_kw=round(peak_unmet, 4),
        hours_above_grid_cap=hours_above_grid_cap,
        hours_with_capacity_support=hours_with_capacity_support,
        unmet_hours=unmet_hours,
        total_required_facility_kwh=round(total_required_facility, 4),
        total_grid_to_load_kwh=round(total_grid_to_load, 4),
        total_grid_to_bess_kwh=round(total_grid_to_bess, 4),
        total_pv_generation_kwh=round(total_pv_generation, 4),
        total_pv_direct_kwh=round(total_pv_direct, 4),
        total_pv_to_bess_kwh=round(total_pv_to_bess, 4),
        total_pv_curtailed_kwh=round(total_pv_curtailed, 4),
        total_bess_discharge_kwh=round(total_bess_discharge, 4),
        total_fuel_cell_kwh=round(total_fuel_cell, 4),
        total_backup_dispatch_kwh=round(total_backup_dispatch, 4),
        total_unmet_kwh=round(total_unmet, 4),
        initial_bess_soc_kwh=round(bess_initial_soc_kwh, 4),
        final_bess_soc_kwh=round(soc, 4),
        hourly_dispatch=hourly_dispatch,
    )


def simulate_firm_capacity_support(
    hourly_facility_factors: list[float],
    target_it_kw: float,
    grid_capacity_kw: float,
    hourly_pv_kw: Optional[list[float]] = None,
    bess_capacity_kwh: float = 0.0,
    bess_roundtrip_efficiency: float = DEFAULT_BESS_ROUNDTRIP_EFF,
    bess_initial_soc_kwh: float = 0.0,
    fuel_cell_capacity_kw: float = DEFAULT_FUEL_CELL_CAPACITY_KW,
    backup_dispatch_capacity_kw: float = 0.0,
    cyclic_bess: bool = False,
    max_cycles: int = 12,
    convergence_tol_kwh: float = 1e-3,
) -> FirmCapacitySupportResult:
    """Sustain a constant IT target using grid headroom and support assets.

    The grid connection is treated as a fixed cap. In hours where the
    required facility power is below that cap, spare grid headroom can
    charge the BESS. In hours where facility power exceeds the cap, the
    deficit is covered in this order:

        PV direct -> BESS discharge -> fuel cell -> backup dispatch

    If `cyclic_bess=True`, the solver iterates the year until the end-of-
    year SoC matches the start-of-year SoC within tolerance. This avoids
    assuming an arbitrary one-time starting charge state for a recurring
    representative year.
    """
    base_result = _simulate_firm_capacity_once(
        hourly_facility_factors=hourly_facility_factors,
        target_it_kw=target_it_kw,
        grid_capacity_kw=grid_capacity_kw,
        hourly_pv_kw=hourly_pv_kw,
        bess_capacity_kwh=bess_capacity_kwh,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        bess_initial_soc_kwh=bess_initial_soc_kwh,
        fuel_cell_capacity_kw=fuel_cell_capacity_kw,
        backup_dispatch_capacity_kw=backup_dispatch_capacity_kw,
    )
    base_result.cyclic_bess = cyclic_bess

    if not cyclic_bess or bess_capacity_kwh <= 0:
        return base_result

    start_soc = bess_initial_soc_kwh
    result = base_result
    converged = False

    for _ in range(max_cycles):
        result = _simulate_firm_capacity_once(
            hourly_facility_factors=hourly_facility_factors,
            target_it_kw=target_it_kw,
            grid_capacity_kw=grid_capacity_kw,
            hourly_pv_kw=hourly_pv_kw,
            bess_capacity_kwh=bess_capacity_kwh,
            bess_roundtrip_efficiency=bess_roundtrip_efficiency,
            bess_initial_soc_kwh=start_soc,
            fuel_cell_capacity_kw=fuel_cell_capacity_kw,
            backup_dispatch_capacity_kw=backup_dispatch_capacity_kw,
        )
        if abs(result.final_bess_soc_kwh - start_soc) <= convergence_tol_kwh:
            converged = True
            break
        start_soc = result.final_bess_soc_kwh

    result.cyclic_bess = True
    result.cyclic_converged = converged
    return result


def find_minimum_bess_capacity(
    hourly_facility_factors: list[float],
    target_it_kw: float,
    grid_capacity_kw: float,
    hourly_pv_kw: Optional[list[float]] = None,
    bess_roundtrip_efficiency: float = DEFAULT_BESS_ROUNDTRIP_EFF,
    fuel_cell_capacity_kw: float = 0.0,
    backup_dispatch_capacity_kw: float = 0.0,
    cyclic_bess: bool = False,
    resolution_kwh: float = 1.0,
    max_iterations: int = 60,
) -> tuple[float, FirmCapacitySupportResult] | None:
    """Solve the minimum BESS energy capacity needed for a target IT load.

    This keeps all other support assets fixed and finds the smallest BESS
    energy capacity that makes the target feasible under the current
    energy-only storage model (no separate C-rate limit).
    """
    if resolution_kwh <= 0:
        raise ValueError(f"resolution_kwh must be > 0: {resolution_kwh}")

    no_bess = simulate_firm_capacity_support(
        hourly_facility_factors=hourly_facility_factors,
        target_it_kw=target_it_kw,
        grid_capacity_kw=grid_capacity_kw,
        hourly_pv_kw=hourly_pv_kw,
        bess_capacity_kwh=0.0,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        bess_initial_soc_kwh=0.0,
        fuel_cell_capacity_kw=fuel_cell_capacity_kw,
        backup_dispatch_capacity_kw=backup_dispatch_capacity_kw,
        cyclic_bess=cyclic_bess,
    )
    if no_bess.feasible:
        return (0.0, no_bess)

    raw_support_need = simulate_firm_capacity_support(
        hourly_facility_factors=hourly_facility_factors,
        target_it_kw=target_it_kw,
        grid_capacity_kw=grid_capacity_kw,
        hourly_pv_kw=hourly_pv_kw,
        bess_capacity_kwh=0.0,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        bess_initial_soc_kwh=0.0,
        fuel_cell_capacity_kw=0.0,
        backup_dispatch_capacity_kw=0.0,
        cyclic_bess=cyclic_bess,
    )

    eta_oneway = math.sqrt(bess_roundtrip_efficiency)
    upper = max(
        raw_support_need.total_unmet_kwh / eta_oneway if eta_oneway > 0 else 0.0,
        raw_support_need.peak_unmet_kw / eta_oneway if eta_oneway > 0 else 0.0,
        resolution_kwh,
    )

    best_capacity = upper
    best = simulate_firm_capacity_support(
        hourly_facility_factors=hourly_facility_factors,
        target_it_kw=target_it_kw,
        grid_capacity_kw=grid_capacity_kw,
        hourly_pv_kw=hourly_pv_kw,
        bess_capacity_kwh=upper,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        bess_initial_soc_kwh=0.0,
        fuel_cell_capacity_kw=fuel_cell_capacity_kw,
        backup_dispatch_capacity_kw=backup_dispatch_capacity_kw,
        cyclic_bess=cyclic_bess,
    )
    if not best.feasible:
        return None

    low = 0.0
    high = upper
    for _ in range(max_iterations):
        if high - low <= resolution_kwh:
            break
        mid = (low + high) / 2.0
        candidate = simulate_firm_capacity_support(
            hourly_facility_factors=hourly_facility_factors,
            target_it_kw=target_it_kw,
            grid_capacity_kw=grid_capacity_kw,
            hourly_pv_kw=hourly_pv_kw,
            bess_capacity_kwh=mid,
            bess_roundtrip_efficiency=bess_roundtrip_efficiency,
            bess_initial_soc_kwh=0.0,
            fuel_cell_capacity_kw=fuel_cell_capacity_kw,
            backup_dispatch_capacity_kw=backup_dispatch_capacity_kw,
            cyclic_bess=cyclic_bess,
        )
        if candidate.feasible:
            high = mid
            best_capacity = mid
            best = candidate
        else:
            low = mid

    return (best_capacity, best)


def _make_support_recommendation(
    key: str,
    label: str,
    description: str,
    result: FirmCapacitySupportResult,
    bess_capacity_kwh: float = 0.0,
    fuel_cell_capacity_kw: float = 0.0,
    backup_dispatch_capacity_kw: float = 0.0,
    notes: Optional[list[str]] = None,
) -> SupportRecommendation:
    """Convert a firm-capacity result into a user-facing recommendation."""
    return SupportRecommendation(
        key=key,
        label=label,
        description=description,
        target_it_kw=round(result.target_it_kw, 4),
        feasible=result.feasible,
        bess_capacity_kwh=round(bess_capacity_kwh, 4),
        fuel_cell_capacity_kw=round(fuel_cell_capacity_kw, 4),
        backup_dispatch_capacity_kw=round(backup_dispatch_capacity_kw, 4),
        peak_support_kw=round(result.peak_support_kw, 4),
        hours_with_capacity_support=result.hours_with_capacity_support,
        total_grid_to_bess_kwh=round(result.total_grid_to_bess_kwh, 4),
        total_bess_discharge_kwh=round(result.total_bess_discharge_kwh, 4),
        total_fuel_cell_kwh=round(result.total_fuel_cell_kwh, 4),
        total_backup_dispatch_kwh=round(result.total_backup_dispatch_kwh, 4),
        total_unmet_kwh=round(result.total_unmet_kwh, 4),
        notes=notes or [],
    )


def recommend_support_portfolios(
    hourly_facility_factors: list[float],
    target_it_kw: float,
    grid_capacity_kw: float,
    baseline_p99_kw: float,
    baseline_worst_kw: float,
    hourly_pv_kw: Optional[list[float]] = None,
    bess_roundtrip_efficiency: float = DEFAULT_BESS_ROUNDTRIP_EFF,
    cyclic_bess: bool = False,
) -> SupportRecommendationBundle:
    """Generate deterministic support pathways for one IT target.

    The recommendations use the same hourly solver as the main firm-capacity
    engine. No heuristic capacities are inserted into the response.

    Returned pathways:
        - Fuel cell only: exact dispatch capacity = worst hourly deficit
        - Backup dispatch only: exact dispatch capacity = worst hourly deficit
        - BESS only: minimum energy capacity solved by binary search
        - Hybrid FC + BESS: FC sized to mean deficit over deficit hours,
          BESS sized to absorb the residual spikes if feasible
    """
    baseline_need = simulate_firm_capacity_support(
        hourly_facility_factors=hourly_facility_factors,
        target_it_kw=target_it_kw,
        grid_capacity_kw=grid_capacity_kw,
        hourly_pv_kw=hourly_pv_kw,
        bess_capacity_kwh=0.0,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        bess_initial_soc_kwh=0.0,
        fuel_cell_capacity_kw=0.0,
        backup_dispatch_capacity_kw=0.0,
        cyclic_bess=cyclic_bess,
    )

    bundle = SupportRecommendationBundle(
        target_it_kw=round(target_it_kw, 4),
        target_already_feasible=baseline_need.feasible,
        annual_support_energy_kwh=round(baseline_need.total_unmet_kwh, 4),
        peak_support_kw=round(baseline_need.peak_unmet_kw, 4),
        hours_above_grid_cap=baseline_need.hours_above_grid_cap,
        gap_vs_p99_kw=round(max(0.0, target_it_kw - baseline_p99_kw), 4),
        gap_vs_worst_kw=round(max(0.0, target_it_kw - baseline_worst_kw), 4),
    )

    if baseline_need.feasible or baseline_need.peak_unmet_kw <= 0:
        return bundle

    peak_dispatch_kw = baseline_need.peak_unmet_kw

    fuel_cell_only = simulate_firm_capacity_support(
        hourly_facility_factors=hourly_facility_factors,
        target_it_kw=target_it_kw,
        grid_capacity_kw=grid_capacity_kw,
        hourly_pv_kw=hourly_pv_kw,
        bess_capacity_kwh=0.0,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        bess_initial_soc_kwh=0.0,
        fuel_cell_capacity_kw=peak_dispatch_kw,
        backup_dispatch_capacity_kw=0.0,
        cyclic_bess=cyclic_bess,
    )
    bundle.candidates.append(_make_support_recommendation(
        key="fuel_cell_only",
        label="Fuel Cell Only",
        description=(
            "Continuous dispatch sized exactly to the worst hourly deficit "
            "at the selected IT target."
        ),
        result=fuel_cell_only,
        fuel_cell_capacity_kw=peak_dispatch_kw,
        notes=[
            "Capacity equals the exact maximum hourly support deficit from the solver.",
        ],
    ))

    backup_only = simulate_firm_capacity_support(
        hourly_facility_factors=hourly_facility_factors,
        target_it_kw=target_it_kw,
        grid_capacity_kw=grid_capacity_kw,
        hourly_pv_kw=hourly_pv_kw,
        bess_capacity_kwh=0.0,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        bess_initial_soc_kwh=0.0,
        fuel_cell_capacity_kw=0.0,
        backup_dispatch_capacity_kw=peak_dispatch_kw,
        cyclic_bess=cyclic_bess,
    )
    bundle.candidates.append(_make_support_recommendation(
        key="backup_only",
        label="Backup Dispatch Only",
        description=(
            "Dispatchable backup power sized exactly to the worst hourly deficit "
            "at the selected IT target."
        ),
        result=backup_only,
        backup_dispatch_capacity_kw=peak_dispatch_kw,
        notes=[
            "Use this as the direct genset / external dispatch sizing path.",
        ],
    ))

    bess_only = find_minimum_bess_capacity(
        hourly_facility_factors=hourly_facility_factors,
        target_it_kw=target_it_kw,
        grid_capacity_kw=grid_capacity_kw,
        hourly_pv_kw=hourly_pv_kw,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        cyclic_bess=cyclic_bess,
    )
    if bess_only is not None:
        bess_capacity_kwh, bess_result = bess_only
        bundle.candidates.append(_make_support_recommendation(
            key="bess_only",
            label="BESS Only",
            description=(
                "Minimum storage energy capacity that makes the target feasible "
                "under the current energy-only BESS model."
            ),
            result=bess_result,
            bess_capacity_kwh=bess_capacity_kwh,
            notes=[
                "This uses the current model assumption that BESS has no separate C-rate limit.",
            ],
        ))

    if baseline_need.hours_above_grid_cap > 0:
        mean_dispatch_kw = baseline_need.total_unmet_kwh / baseline_need.hours_above_grid_cap
        if 0 < mean_dispatch_kw < peak_dispatch_kw:
            hybrid = find_minimum_bess_capacity(
                hourly_facility_factors=hourly_facility_factors,
                target_it_kw=target_it_kw,
                grid_capacity_kw=grid_capacity_kw,
                hourly_pv_kw=hourly_pv_kw,
                bess_roundtrip_efficiency=bess_roundtrip_efficiency,
                fuel_cell_capacity_kw=mean_dispatch_kw,
                cyclic_bess=cyclic_bess,
            )
            if hybrid is not None:
                hybrid_bess_kwh, hybrid_result = hybrid
                bundle.candidates.append(_make_support_recommendation(
                    key="hybrid_fc_bess",
                    label="Hybrid Fuel Cell + BESS",
                    description=(
                        "Fuel cell sized to the mean support level across deficit hours; "
                        "BESS covers the residual spikes."
                    ),
                    result=hybrid_result,
                    bess_capacity_kwh=hybrid_bess_kwh,
                    fuel_cell_capacity_kw=mean_dispatch_kw,
                    notes=[
                        "Fuel-cell sizing comes from the exact mean deficit during hours above the grid cap.",
                        "BESS absorbs only the remaining short-duration peaks.",
                    ],
                ))

    return bundle


def find_max_firm_it_capacity(
    hourly_facility_factors: list[float],
    grid_capacity_kw: float,
    max_it_kw: float,
    hourly_pv_kw: Optional[list[float]] = None,
    bess_capacity_kwh: float = 0.0,
    bess_roundtrip_efficiency: float = DEFAULT_BESS_ROUNDTRIP_EFF,
    bess_initial_soc_kwh: float = 0.0,
    fuel_cell_capacity_kw: float = DEFAULT_FUEL_CELL_CAPACITY_KW,
    backup_dispatch_capacity_kw: float = 0.0,
    cyclic_bess: bool = False,
    resolution_kw: float = 1.0,
    max_iterations: int = 40,
) -> FirmCapacitySupportResult:
    """Find the maximum constant IT load that remains feasible all year."""
    if max_it_kw < 0:
        raise ValueError(f"max_it_kw cannot be negative: {max_it_kw}")
    if resolution_kw <= 0:
        raise ValueError(f"resolution_kw must be > 0: {resolution_kw}")

    low = 0.0
    high = max_it_kw
    best = simulate_firm_capacity_support(
        hourly_facility_factors=hourly_facility_factors,
        target_it_kw=0.0,
        grid_capacity_kw=grid_capacity_kw,
        hourly_pv_kw=hourly_pv_kw,
        bess_capacity_kwh=bess_capacity_kwh,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        bess_initial_soc_kwh=bess_initial_soc_kwh,
        fuel_cell_capacity_kw=fuel_cell_capacity_kw,
        backup_dispatch_capacity_kw=backup_dispatch_capacity_kw,
        cyclic_bess=cyclic_bess,
    )

    high_result = simulate_firm_capacity_support(
        hourly_facility_factors=hourly_facility_factors,
        target_it_kw=high,
        grid_capacity_kw=grid_capacity_kw,
        hourly_pv_kw=hourly_pv_kw,
        bess_capacity_kwh=bess_capacity_kwh,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        bess_initial_soc_kwh=bess_initial_soc_kwh,
        fuel_cell_capacity_kw=fuel_cell_capacity_kw,
        backup_dispatch_capacity_kw=backup_dispatch_capacity_kw,
        cyclic_bess=cyclic_bess,
    )
    if high_result.feasible:
        return high_result

    for _ in range(max_iterations):
        if high - low <= resolution_kw:
            break
        mid = (low + high) / 2.0
        candidate = simulate_firm_capacity_support(
            hourly_facility_factors=hourly_facility_factors,
            target_it_kw=mid,
            grid_capacity_kw=grid_capacity_kw,
            hourly_pv_kw=hourly_pv_kw,
            bess_capacity_kwh=bess_capacity_kwh,
            bess_roundtrip_efficiency=bess_roundtrip_efficiency,
            bess_initial_soc_kwh=bess_initial_soc_kwh,
            fuel_cell_capacity_kw=fuel_cell_capacity_kw,
            backup_dispatch_capacity_kw=backup_dispatch_capacity_kw,
            cyclic_bess=cyclic_bess,
        )
        if candidate.feasible:
            low = mid
            best = candidate
        else:
            high = mid

    return best


# ─────────────────────────────────────────────────────────────
# Main Dispatch Simulation
# ─────────────────────────────────────────────────────────────

def simulate_green_dispatch(
    hourly_facility_kw: list[float],
    hourly_it_kw: list[float],
    hourly_pv_kw: list[float],
    bess_capacity_kwh: float = 0.0,
    bess_roundtrip_efficiency: float = DEFAULT_BESS_ROUNDTRIP_EFF,
    bess_initial_soc_kwh: float = 0.0,
    fuel_cell_capacity_kw: float = DEFAULT_FUEL_CELL_CAPACITY_KW,
    pv_capacity_kwp: float = 0.0,
    grid_co2_kg_per_kwh: float = DEFAULT_GRID_CO2_KG_PER_KWH,
) -> GreenEnergyResult:
    """Simulate hourly green energy dispatch for an entire year.

    Takes hourly facility power and IT load arrays (from pue_engine.py)
    plus hourly PV generation (from PVGIS or manual upload) and simulates
    the 6-step dispatch priority from Architecture Agreement Section 3.9.

    Args:
        hourly_facility_kw:
            Hourly total facility power in kW. Length = N hours
            (typically 8,760 for a full year).
            Source: pue_engine.py → HourlySimResult.hourly_facility_kw

        hourly_it_kw:
            Hourly IT load in kW. Same length as hourly_facility_kw.
            Source: pue_engine.py → HourlySimResult.hourly_it_kw

        hourly_pv_kw:
            Hourly PV AC output in kW. Same length as above.
            Source: PVGIS API or manual upload via weather.py.
            If PV is not installed, pass a list of zeros.

        bess_capacity_kwh:
            Battery energy storage capacity in kWh.
            0 = no BESS installed. Default: 0.

        bess_roundtrip_efficiency:
            Round-trip efficiency of the BESS (0 < η ≤ 1).
            Default: 0.875 (midpoint of 0.85–0.90).
            Source: NREL ATB 2024, lithium-ion utility-scale.
            One-way efficiency = √(roundtrip) ≈ 0.935.

        bess_initial_soc_kwh:
            Initial state of charge in kWh. Default: 0.
            Must be ≤ bess_capacity_kwh.

        fuel_cell_capacity_kw:
            Maximum dispatch power of fuel cell in kW.
            0 = no fuel cell. Default: 0.

        pv_capacity_kwp:
            Installed PV peak capacity in kWp.
            Used for reporting only — actual generation comes from
            hourly_pv_kw array. Default: 0.

        grid_co2_kg_per_kwh:
            Grid CO₂ emission factor in kg CO₂ per kWh.
            Default: 0.256 (Italy 2022).
            Source: ISPRA (2023).

    Returns:
        GreenEnergyResult with hourly dispatch and annual summaries.

    Raises:
        ValueError: If input arrays have different lengths, or
                    if BESS parameters are invalid.

    Example:
        >>> result = simulate_green_dispatch(
        ...     hourly_facility_kw=[25000.0] * 8760,
        ...     hourly_it_kw=[20000.0] * 8760,
        ...     hourly_pv_kw=[3000.0] * 4380 + [0.0] * 4380,  # day/night
        ...     bess_capacity_kwh=10000.0,
        ...     fuel_cell_capacity_kw=1000.0,
        ... )
        >>> print(f"Overhead coverage: {result.overhead_coverage_fraction:.1%}")
    """
    # ── Input validation ──
    n_hours = len(hourly_facility_kw)
    if len(hourly_it_kw) != n_hours:
        raise ValueError(
            f"hourly_it_kw length ({len(hourly_it_kw)}) != "
            f"hourly_facility_kw length ({n_hours})"
        )
    if len(hourly_pv_kw) != n_hours:
        raise ValueError(
            f"hourly_pv_kw length ({len(hourly_pv_kw)}) != "
            f"hourly_facility_kw length ({n_hours})"
        )
    if bess_capacity_kwh < 0:
        raise ValueError(f"bess_capacity_kwh cannot be negative: {bess_capacity_kwh}")
    if not (0 < bess_roundtrip_efficiency <= 1.0):
        raise ValueError(
            f"bess_roundtrip_efficiency must be in (0, 1.0]: {bess_roundtrip_efficiency}"
        )
    if bess_initial_soc_kwh < 0:
        raise ValueError(f"bess_initial_soc_kwh cannot be negative: {bess_initial_soc_kwh}")
    if bess_initial_soc_kwh > bess_capacity_kwh:
        raise ValueError(
            f"bess_initial_soc_kwh ({bess_initial_soc_kwh}) > "
            f"bess_capacity_kwh ({bess_capacity_kwh})"
        )
    if fuel_cell_capacity_kw < 0:
        raise ValueError(
            f"fuel_cell_capacity_kw cannot be negative: {fuel_cell_capacity_kw}"
        )

    # ── BESS one-way efficiency ──
    # η_oneway = √(η_roundtrip)
    # Source: Architecture Agreement Section 3.9
    # The one-way efficiency applies on both charge and discharge.
    # Roundtrip: η_roundtrip = η_oneway × η_oneway = η_oneway²
    eta_oneway = math.sqrt(bess_roundtrip_efficiency)

    # ── Initialize state ──
    soc = bess_initial_soc_kwh
    hourly_dispatch: list[HourlyDispatchState] = []

    # ── Annual accumulators ──
    sum_overhead = 0.0
    sum_pv_gen = 0.0
    sum_pv_to_overhead = 0.0
    sum_pv_to_bess = 0.0
    sum_pv_curtailed = 0.0
    sum_bess_discharge = 0.0
    sum_fuel_cell = 0.0
    sum_grid_import = 0.0

    # ── Hourly dispatch loop ──
    for t in range(n_hours):
        p_facility = hourly_facility_kw[t]
        p_it = hourly_it_kw[t]
        pv = max(0.0, hourly_pv_kw[t])  # PV can't be negative

        # Overhead = non-IT portion of facility power
        overhead = max(0.0, p_facility - p_it)

        # ════════════════════════════════════════════════════════
        # Step 1: PV → overhead (direct offset)
        # ════════════════════════════════════════════════════════
        pv_to_overhead = min(pv, overhead)
        remaining_pv = pv - pv_to_overhead
        deficit = overhead - pv_to_overhead

        # ════════════════════════════════════════════════════════
        # Step 2: Surplus PV → charge BESS
        # ════════════════════════════════════════════════════════
        # Energy stored = charge × η_oneway
        # Available BESS headroom = capacity − current SoC
        pv_to_bess = 0.0
        if remaining_pv > 0 and bess_capacity_kwh > 0:
            headroom = bess_capacity_kwh - soc
            # How much PV can we actually store?
            # If we charge X kW, the SoC increases by X × η_oneway.
            # So max charge = headroom / η_oneway (to fill exactly).
            max_charge = headroom / eta_oneway if eta_oneway > 0 else 0.0
            pv_to_bess = min(remaining_pv, max_charge)
            soc += pv_to_bess * eta_oneway
            remaining_pv -= pv_to_bess

        # ════════════════════════════════════════════════════════
        # Step 3: Remaining surplus → export/curtail
        # ════════════════════════════════════════════════════════
        pv_curtailed = remaining_pv  # Whatever PV is left

        # ════════════════════════════════════════════════════════
        # Step 4: Remaining deficit → discharge BESS
        # ════════════════════════════════════════════════════════
        # To deliver X kW to the load, BESS must release X / η_oneway
        # from its SoC (losses during discharge).
        bess_discharge = 0.0
        if deficit > 0 and soc > 0 and bess_capacity_kwh > 0:
            # Max deliverable from current SoC
            max_deliver = soc * eta_oneway  # SoC × η = deliverable kW
            bess_discharge = min(deficit, max_deliver)
            # Reduce SoC by the amount withdrawn (before efficiency loss)
            soc_withdrawn = bess_discharge / eta_oneway
            soc -= soc_withdrawn
            deficit -= bess_discharge

        # ════════════════════════════════════════════════════════
        # Step 5: Remaining deficit → fuel cell
        # ════════════════════════════════════════════════════════
        fuel_cell = 0.0
        if deficit > 0 and fuel_cell_capacity_kw > 0:
            fuel_cell = min(deficit, fuel_cell_capacity_kw)
            deficit -= fuel_cell

        # ════════════════════════════════════════════════════════
        # Step 6: Remaining deficit → grid import
        # ════════════════════════════════════════════════════════
        grid_import = deficit  # Whatever is left

        # ── Clamp SoC to bounds (safety) ──
        soc = max(0.0, min(soc, bess_capacity_kwh))

        # ── Record hourly state ──
        hourly_dispatch.append(HourlyDispatchState(
            hour=t,
            overhead_kw=round(overhead, 4),
            pv_generation_kw=round(pv, 4),
            pv_to_overhead_kw=round(pv_to_overhead, 4),
            pv_to_bess_kw=round(pv_to_bess, 4),
            pv_curtailed_kw=round(pv_curtailed, 4),
            bess_discharge_kw=round(bess_discharge, 4),
            fuel_cell_kw=round(fuel_cell, 4),
            grid_import_kw=round(grid_import, 4),
            bess_soc_kwh=round(soc, 4),
        ))

        # ── Accumulate totals (use unrounded for accuracy) ──
        sum_overhead += overhead
        sum_pv_gen += pv
        sum_pv_to_overhead += pv_to_overhead
        sum_pv_to_bess += pv_to_bess
        sum_pv_curtailed += pv_curtailed
        sum_bess_discharge += bess_discharge
        sum_fuel_cell += fuel_cell
        sum_grid_import += grid_import

    # ── Annual summary metrics ──
    total_green_used = sum_pv_to_overhead + sum_bess_discharge + sum_fuel_cell

    # Overhead coverage: fraction of overhead met by green sources
    if sum_overhead > 0:
        overhead_coverage = total_green_used / sum_overhead
    else:
        overhead_coverage = 0.0

    # Renewable fraction: green energy / total facility energy
    total_facility_kwh = sum(hourly_facility_kw)
    total_it_kwh = sum(hourly_it_kw)
    if total_facility_kwh > 0:
        renewable_fraction = total_green_used / total_facility_kwh
    else:
        renewable_fraction = 0.0

    # PV self-consumption: fraction of PV used on-site
    if sum_pv_gen > 0:
        pv_self_consumption = (sum_pv_to_overhead + sum_pv_to_bess) / sum_pv_gen
    else:
        pv_self_consumption = 0.0

    # BESS equivalent cycles
    if bess_capacity_kwh > 0:
        bess_cycles = sum_bess_discharge / bess_capacity_kwh
    else:
        bess_cycles = 0.0

    # CO₂ avoided: green energy used × grid emission factor
    co2_avoided_kg = total_green_used * grid_co2_kg_per_kwh
    co2_avoided_tonnes = co2_avoided_kg / 1000

    return GreenEnergyResult(
        hourly_dispatch=hourly_dispatch,
        total_overhead_kwh=round(sum_overhead, 2),
        total_pv_generation_kwh=round(sum_pv_gen, 2),
        total_pv_to_overhead_kwh=round(sum_pv_to_overhead, 2),
        total_pv_to_bess_kwh=round(sum_pv_to_bess, 2),
        total_pv_curtailed_kwh=round(sum_pv_curtailed, 2),
        total_bess_discharge_kwh=round(sum_bess_discharge, 2),
        total_fuel_cell_kwh=round(sum_fuel_cell, 2),
        total_grid_import_kwh=round(sum_grid_import, 2),
        overhead_coverage_fraction=round(overhead_coverage, 6),
        renewable_fraction=round(renewable_fraction, 6),
        pv_self_consumption_fraction=round(pv_self_consumption, 6),
        bess_cycles_equivalent=round(bess_cycles, 2),
        co2_avoided_tonnes=round(co2_avoided_tonnes, 2),
        pv_capacity_kwp=pv_capacity_kwp,
        bess_capacity_kwh=bess_capacity_kwh,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        fuel_cell_capacity_kw=fuel_cell_capacity_kw,
        total_facility_kwh=round(total_facility_kwh, 2),
        total_it_kwh=round(total_it_kwh, 2),
    )


# ─────────────────────────────────────────────────────────────
# Advisory Mode: Auto-Sizing for Coverage Targets
# ─────────────────────────────────────────────────────────────

@dataclass
class CoverageLevelResult:
    """Result for one coverage target level — includes both PV-only and PV+BESS."""
    coverage_target: float
    # PV-only sizing
    pv_only_kwp_needed: float
    pv_only_annual_gen_mwh: float
    pv_only_co2_avoided_tonnes: float
    pv_only_coverage_achieved: float
    pv_only_ceiling_reached: bool  # True when PV-only physically can't reach target
    # PV + BESS sizing
    pv_kwp_needed: float
    bess_kwh_needed: float
    annual_generation_mwh: float
    co2_avoided_tonnes: float
    renewable_fraction: float


def _binary_search_pv_coverage(
    target: float,
    hourly_facility_kw: list[float],
    hourly_it_kw: list[float],
    hourly_pv_kw_per_kwp: list[float],
    bess_roundtrip_efficiency: float,
    grid_co2_kg_per_kwh: float,
    with_bess: bool,
) -> tuple[float, float, GreenEnergyResult | None, bool]:
    """Binary search for PV capacity to achieve a target overhead coverage.

    Returns (final_kwp, bess_kwh, best_result, ceiling_reached).
    ceiling_reached is True when the physical maximum coverage is below the target.
    """
    low_kwp = 0.0
    high_kwp = max(hourly_facility_kw) * 10
    best_result = None

    # First check: can we even reach the target at the upper bound?
    upper_pv = [v * high_kwp for v in hourly_pv_kw_per_kwp]
    if with_bess:
        upper_avg = sum(upper_pv) / len(upper_pv) if upper_pv else 0.0
        upper_bess = upper_avg * 4.0
    else:
        upper_bess = 0.0
    upper_result = simulate_green_dispatch(
        hourly_facility_kw=hourly_facility_kw,
        hourly_it_kw=hourly_it_kw,
        hourly_pv_kw=upper_pv,
        bess_capacity_kwh=upper_bess,
        bess_roundtrip_efficiency=bess_roundtrip_efficiency,
        bess_initial_soc_kwh=0.0,
        fuel_cell_capacity_kw=0.0,
        pv_capacity_kwp=high_kwp,
        grid_co2_kg_per_kwh=grid_co2_kg_per_kwh,
    )
    ceiling_reached = upper_result.overhead_coverage_fraction < target - 0.005

    if ceiling_reached:
        # Can't reach target — find the minimum PV that achieves the physical max
        # Run a second binary search to find where adding more PV stops helping
        # (diminishing returns — the coverage plateaus)
        max_coverage = upper_result.overhead_coverage_fraction
        # Search for PV that gets us to 99% of the max achievable coverage
        plateau_target = max_coverage * 0.99

        for _ in range(40):
            mid_kwp = (low_kwp + high_kwp) / 2
            hourly_pv = [v * mid_kwp for v in hourly_pv_kw_per_kwp]
            if with_bess:
                avg_pv = sum(hourly_pv) / len(hourly_pv) if hourly_pv else 0.0
                bess_kwh = avg_pv * 4.0
            else:
                bess_kwh = 0.0

            result = simulate_green_dispatch(
                hourly_facility_kw=hourly_facility_kw,
                hourly_it_kw=hourly_it_kw,
                hourly_pv_kw=hourly_pv,
                bess_capacity_kwh=bess_kwh,
                bess_roundtrip_efficiency=bess_roundtrip_efficiency,
                bess_initial_soc_kwh=0.0,
                fuel_cell_capacity_kw=0.0,
                pv_capacity_kwp=mid_kwp,
                grid_co2_kg_per_kwh=grid_co2_kg_per_kwh,
            )
            best_result = result
            if result.overhead_coverage_fraction < plateau_target:
                low_kwp = mid_kwp
            else:
                high_kwp = mid_kwp
    else:
        for _ in range(40):
            mid_kwp = (low_kwp + high_kwp) / 2
            hourly_pv = [v * mid_kwp for v in hourly_pv_kw_per_kwp]

            if with_bess:
                avg_pv = sum(hourly_pv) / len(hourly_pv) if hourly_pv else 0.0
                bess_kwh = avg_pv * 4.0
            else:
                bess_kwh = 0.0

            result = simulate_green_dispatch(
                hourly_facility_kw=hourly_facility_kw,
                hourly_it_kw=hourly_it_kw,
                hourly_pv_kw=hourly_pv,
                bess_capacity_kwh=bess_kwh,
                bess_roundtrip_efficiency=bess_roundtrip_efficiency,
                bess_initial_soc_kwh=0.0,
                fuel_cell_capacity_kw=0.0,
                pv_capacity_kwp=mid_kwp,
                grid_co2_kg_per_kwh=grid_co2_kg_per_kwh,
            )

            best_result = result
            if result.overhead_coverage_fraction < target:
                low_kwp = mid_kwp
            else:
                high_kwp = mid_kwp

    final_kwp = round((low_kwp + high_kwp) / 2, 1)
    if with_bess:
        avg_pv_final = sum(v * final_kwp for v in hourly_pv_kw_per_kwp) / len(hourly_pv_kw_per_kwp)
        final_bess = round(avg_pv_final * 4.0, 1)
    else:
        final_bess = 0.0

    return final_kwp, final_bess, best_result, ceiling_reached


def compute_green_advisory(
    hourly_facility_kw: list[float],
    hourly_it_kw: list[float],
    hourly_pv_kw_per_kwp: list[float],
    bess_roundtrip_efficiency: float = DEFAULT_BESS_ROUNDTRIP_EFF,
    grid_co2_kg_per_kwh: float = DEFAULT_GRID_CO2_KG_PER_KWH,
    coverage_targets: list[float] | None = None,
) -> list[CoverageLevelResult]:
    """Compute both PV-only and PV+BESS sizing for target coverage levels.

    For each coverage target, runs binary search twice:
    1. PV-only (no BESS) — finds PV kWp needed
    2. PV+BESS (BESS sized as 4h avg PV) — finds PV kWp + BESS kWh needed

    Returns list of CoverageLevelResult with both pathways.
    """
    if coverage_targets is None:
        coverage_targets = [0.10, 0.25, 0.50, 0.75, 1.00]

    results: list[CoverageLevelResult] = []

    for target in coverage_targets:
        if target <= 0:
            results.append(CoverageLevelResult(
                coverage_target=target,
                pv_only_kwp_needed=0.0,
                pv_only_annual_gen_mwh=0.0,
                pv_only_co2_avoided_tonnes=0.0,
                pv_only_coverage_achieved=0.0,
                pv_only_ceiling_reached=False,
                pv_kwp_needed=0.0,
                bess_kwh_needed=0.0,
                annual_generation_mwh=0.0,
                co2_avoided_tonnes=0.0,
                renewable_fraction=0.0,
            ))
            continue

        # PV-only search
        pv_only_kwp, _, pv_only_result, pv_only_ceiling = _binary_search_pv_coverage(
            target=target,
            hourly_facility_kw=hourly_facility_kw,
            hourly_it_kw=hourly_it_kw,
            hourly_pv_kw_per_kwp=hourly_pv_kw_per_kwp,
            bess_roundtrip_efficiency=bess_roundtrip_efficiency,
            grid_co2_kg_per_kwh=grid_co2_kg_per_kwh,
            with_bess=False,
        )
        pv_only_gen_mwh = round(sum(v * pv_only_kwp for v in hourly_pv_kw_per_kwp) / 1000.0, 1)

        # PV+BESS search
        pv_bess_kwp, bess_kwh, pv_bess_result, _ = _binary_search_pv_coverage(
            target=target,
            hourly_facility_kw=hourly_facility_kw,
            hourly_it_kw=hourly_it_kw,
            hourly_pv_kw_per_kwp=hourly_pv_kw_per_kwp,
            bess_roundtrip_efficiency=bess_roundtrip_efficiency,
            grid_co2_kg_per_kwh=grid_co2_kg_per_kwh,
            with_bess=True,
        )
        pv_bess_gen_mwh = round(sum(v * pv_bess_kwp for v in hourly_pv_kw_per_kwp) / 1000.0, 1)

        results.append(CoverageLevelResult(
            coverage_target=target,
            pv_only_kwp_needed=pv_only_kwp,
            pv_only_annual_gen_mwh=pv_only_gen_mwh,
            pv_only_co2_avoided_tonnes=round(pv_only_result.co2_avoided_tonnes, 1) if pv_only_result else 0.0,
            pv_only_coverage_achieved=round(pv_only_result.overhead_coverage_fraction, 4) if pv_only_result else 0.0,
            pv_only_ceiling_reached=pv_only_ceiling,
            pv_kwp_needed=pv_bess_kwp,
            bess_kwh_needed=bess_kwh,
            annual_generation_mwh=pv_bess_gen_mwh,
            co2_avoided_tonnes=round(pv_bess_result.co2_avoided_tonnes, 1) if pv_bess_result else 0.0,
            renewable_fraction=round(pv_bess_result.renewable_fraction, 4) if pv_bess_result else 0.0,
        ))

    return results
