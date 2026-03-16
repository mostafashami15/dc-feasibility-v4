"""
DC Feasibility Tool v4 — PUE Engine (Hourly Simulation)
=========================================================
Full 8,760-hour (or any length) simulation that computes:
    - Hourly facility power and IT capacity
    - Energy-weighted annual PUE (the ONLY correct PUE definition)
    - IT capacity spectrum (worst / P99 / P90 / mean / best)
    - Cooling mode breakdown (hours and energy fractions)
    - Overtemperature hours (for chiller-less topology)

This is the core calculation module. Everything else — space, power,
cooling — feeds into this. The output goes directly to the Results
Dashboard and the report generator.

Two operating modes:
    Area-Constrained:  P_IT is fixed → compute P_facility(t) per hour
    Power-Constrained: P_facility is fixed → compute P_IT(t) per hour

Formula (Architecture Agreement Section 3.3):
    P_facility(t) = P_IT(t) × (1 + a(t)) + b

    a(t) = elec_loss + k_fan + cool_kW_per_kW_IT(t) + [k_econ if econ active]
    b    = P_reference × f_misc   (constant — lighting, BMS, security)

    elec_loss = (1 / η_chain) − 1

Annual PUE (Section 3.4):
    PUE_annual = Σ P_facility(t) / Σ P_IT(t)

    Source: Uptime Institute, "PUE: A Comprehensive Examination" (2014).
    The Green Grid, White Paper #49.
    WARNING: Arithmetic average of hourly PUE ≠ energy-weighted PUE.

IT Capacity Spectrum (Section 3.7):
    Committed (P99) = IT capacity available 99% of the year
    Source: Uptime Institute Tier Standard (2018).

Dependencies:
    engine.cooling — compute_hourly_cooling, CoolingMode
    engine.assumptions — COOLING_PROFILES, MISC_OVERHEAD

Reference: Architecture Agreement v2.0, Sections 3.3, 3.4, 3.7
"""

import math
from dataclasses import dataclass, field

from engine.assumption_overrides import get_effective_misc_overhead_fraction
from engine.cooling import compute_hourly_cooling, CoolingMode


# ─────────────────────────────────────────────────────────────
# Result Data Class
# ─────────────────────────────────────────────────────────────
# Using dataclass (not Pydantic) because this is an internal
# engine result that's never serialized to JSON directly.
# It feeds into ScenarioResult (Pydantic) via the API layer.

@dataclass
class HourlySimResult:
    """Complete result of the hourly PUE simulation.

    Attributes:
        annual_pue: Energy-weighted annual PUE.
            = sum(P_facility) / sum(P_IT)
        total_facility_kwh: Total facility energy over the period (kWh).
        total_it_kwh: Total IT energy over the period (kWh).

        it_capacity_worst_kw: Minimum IT load in any hour (hottest hour).
        it_capacity_p99_kw: IT load available 99% of hours.
        it_capacity_p90_kw: IT load available 90% of hours.
        it_capacity_mean_kw: Average IT load across all hours.
        it_capacity_best_kw: Maximum IT load in any hour (coolest hour).

        mech_hours: Hours in MECH mode.
        econ_part_hours: Hours in ECON_PART mode.
        econ_full_hours: Hours in ECON_FULL mode.

        mech_energy_frac: Fraction of total cooling energy from MECH mode.
        econ_part_energy_frac: Fraction from ECON_PART mode.
        econ_full_energy_frac: Fraction from ECON_FULL mode (always 0).

        overtemperature_hours: Hours where chiller-less system
            cannot maintain setpoint.

        hourly_pue: Per-hour PUE values.
        hourly_it_kw: Per-hour IT load in kW.
        hourly_facility_kw: Per-hour facility power in kW.
        hourly_mode: Per-hour cooling mode string.
        hourly_cop: Per-hour COP (0 for ECON_FULL).
        hourly_cool_kw_per_kw_it: Per-hour cooling load per kW IT.
    """

    # ── Annual metrics ──
    annual_pue: float
    total_facility_kwh: float
    total_it_kwh: float

    # ── IT capacity spectrum ──
    it_capacity_worst_kw: float
    it_capacity_p99_kw: float
    it_capacity_p90_kw: float
    it_capacity_mean_kw: float
    it_capacity_best_kw: float

    # ── Cooling mode breakdown (hours) ──
    mech_hours: int
    econ_part_hours: int
    econ_full_hours: int

    # ── Cooling mode breakdown (energy-weighted) ──
    mech_energy_frac: float
    econ_part_energy_frac: float
    econ_full_energy_frac: float

    # ── Overtemperature ──
    overtemperature_hours: int

    # ── Hourly arrays ──
    hourly_pue: list = field(default_factory=list)
    hourly_it_kw: list = field(default_factory=list)
    hourly_facility_kw: list = field(default_factory=list)
    hourly_mode: list = field(default_factory=list)
    hourly_cop: list = field(default_factory=list)
    hourly_cool_kw_per_kw_it: list = field(default_factory=list)

    # ── Annual overhead decomposition ──
    total_electrical_losses_kwh: float = 0.0
    total_fan_pump_kwh: float = 0.0
    total_cooling_kwh: float = 0.0
    total_economizer_kwh: float = 0.0
    total_misc_kwh: float = 0.0
    total_overhead_kwh: float = 0.0


# ─────────────────────────────────────────────────────────────
# Percentile Helper
# ─────────────────────────────────────────────────────────────

def _percentile_low(sorted_values: list[float], percentile: float) -> float:
    """Compute the value at a given percentile (low-side).

    For IT capacity, we want the value that is EXCEEDED for
    (100 - percentile)% of the year. This is the low-side percentile.

    P99 = value at 1st percentile → IT capacity available 99% of year
    P90 = value at 10th percentile → IT capacity available 90% of year

    Uses nearest-rank method (floor):
        index = floor(N × p / 100)
        clamped to [0, N-1]

    Source: Architecture Agreement Section 3.7

    Args:
        sorted_values: Values sorted in ascending order.
        percentile: Percentile value (e.g., 1 for P99, 10 for P90).

    Returns:
        Value at the given percentile.
    """
    n = len(sorted_values)
    if n == 0:
        raise ValueError("Cannot compute percentile of empty list")
    idx = int(math.floor(n * percentile / 100.0))
    idx = max(0, min(idx, n - 1))
    return sorted_values[idx]


def _validate_hourly_inputs(
    temperatures: list[float],
    humidities: list[float] | None,
) -> int:
    """Validate hourly weather arrays and return the hour count."""
    n_hours = len(temperatures)
    if n_hours == 0:
        raise ValueError("temperatures must not be empty")

    if humidities is not None and len(humidities) != n_hours:
        raise ValueError(
            f"temperatures ({n_hours}) and humidities ({len(humidities)}) "
            "must have the same length"
        )

    return n_hours


def _hourly_state_terms(
    T_db: float,
    RH: float | None,
    cooling_type: str,
    eta_chain: float,
    f_misc: float,
    override_preset_key: str | None = None,
):
    """Return the cooling state and overhead terms for one hour."""
    elec_loss = (1.0 / eta_chain) - 1.0
    state = compute_hourly_cooling(
        T_db=T_db,
        RH=RH,
        cooling_type=cooling_type,
        eta_chain=eta_chain,
        f_misc=f_misc,
        override_preset_key=override_preset_key,
    )
    a_t = elec_loss + state.k_fan + state.cool_kw_per_kw_it + state.k_econ
    facility_factor = 1.0 + a_t + f_misc
    return state, elec_loss, a_t, facility_factor


def build_hourly_facility_factors(
    temperatures: list[float],
    humidities: list[float] | None,
    cooling_type: str,
    eta_chain: float,
    f_misc: float | None = None,
    override_preset_key: str | None = None,
) -> list[float]:
    """Compute facility-kW-per-kW-IT factors for each hour.

    This matches the area-constrained hourly engine approximation:

        P_facility(t) = P_IT × factor(t)

    where:
        factor(t) = 1 + elec_loss + k_fan + cool_kW_per_kW_IT(t)
                    + k_econ + f_misc

    The factor is used by the peak-support solver to evaluate how much
    facility power is required to sustain a constant IT target through
    the full year.
    """
    n_hours = _validate_hourly_inputs(temperatures, humidities)
    if f_misc is None:
        f_misc = get_effective_misc_overhead_fraction(override_preset_key)
    factors: list[float] = []

    for t in range(n_hours):
        T_db = temperatures[t]
        RH = humidities[t] if humidities is not None else None
        _, _, _, factor = _hourly_state_terms(
            T_db=T_db,
            RH=RH,
            cooling_type=cooling_type,
            eta_chain=eta_chain,
            f_misc=f_misc,
            override_preset_key=override_preset_key,
        )
        factors.append(factor)

    return factors


# ═════════════════════════════════════════════════════════════
# MAIN SIMULATION FUNCTION
# ═════════════════════════════════════════════════════════════

def simulate_hourly(
    temperatures: list[float],
    humidities: list[float] | None,
    cooling_type: str,
    eta_chain: float,
    facility_power_kw: float | None = None,
    it_load_kw: float | None = None,
    f_misc: float | None = None,
    override_preset_key: str | None = None,
) -> HourlySimResult:
    """Run the hourly PUE simulation.

    This is the main entry point for the entire engine. For each hour,
    it calls compute_hourly_cooling() to get the cooling state, then
    computes facility power or IT load depending on the mode.

    Two modes (exactly one of facility_power_kw / it_load_kw must be set):

    Area-Constrained (it_load_kw given):
        P_IT = fixed (from rack count × density)
        P_facility(t) = P_IT × (1 + a(t)) + b
        where b = P_IT × f_misc (first-order approximation)
        Use: When no STMG power is confirmed.

    Power-Constrained (facility_power_kw given):
        P_facility = fixed (from STMG)
        P_IT(t) = (P_facility − b) / (1 + a(t))
        where b = P_facility × f_misc
        Use: When utility power is known.

    The b term represents miscellaneous fixed loads (lighting, BMS,
    security). In the cooling load formula, f_misc is already included
    in the heat rejection numerator (misc heat must be cooled). Here,
    b represents the electrical consumption of those loads — a separate
    physical effect. This is NOT double-counting.

    Source: Architecture Agreement Sections 3.3, 3.4, 3.7

    Args:
        temperatures: Dry-bulb temperatures in °C, one per hour.
        humidities: Relative humidity in % (0–100), one per hour.
            Required for water-cooled topologies. Pass None for
            air-cooled if RH data is unavailable.
        cooling_type: Key from COOLING_PROFILES.
        eta_chain: Power chain efficiency (from REDUNDANCY_PROFILES).
        facility_power_kw: Fixed facility power in kW (power-constrained).
        it_load_kw: Fixed IT load in kW (area-constrained).
        f_misc: Miscellaneous overhead fraction. Default 0.025 (2.5%).

    Returns:
        HourlySimResult with all metrics and hourly arrays.

    Raises:
        ValueError: If neither or both of facility_power_kw and
            it_load_kw are provided, or if input lengths mismatch.

    Example:
        >>> result = simulate_hourly(
        ...     temperatures=[10.0, 18.0, 30.0, 35.0],
        ...     humidities=None,
        ...     cooling_type="Air-Cooled Chiller + Economizer",
        ...     eta_chain=0.95,
        ...     it_load_kw=10000.0,
        ... )
        >>> print(f"PUE: {result.annual_pue:.4f}")
    """

    # ── Validate inputs ──
    n_hours = len(temperatures)
    if n_hours == 0:
        raise ValueError("temperatures must not be empty")

    if humidities is not None and len(humidities) != n_hours:
        raise ValueError(
            f"temperatures ({n_hours}) and humidities ({len(humidities)}) "
            f"must have the same length"
        )

    if (facility_power_kw is None) == (it_load_kw is None):
        raise ValueError(
            "Exactly one of facility_power_kw or it_load_kw must be provided. "
            "facility_power_kw → power-constrained mode. "
            "it_load_kw → area-constrained mode."
        )

    if f_misc is None:
        f_misc = get_effective_misc_overhead_fraction(override_preset_key)

    is_power_constrained = facility_power_kw is not None
    if is_power_constrained:
        assert facility_power_kw is not None
        # b = P_facility × f_misc (fixed overhead from facility power)
        b_kw = facility_power_kw * f_misc
    else:
        assert it_load_kw is not None
        # b = P_IT × f_misc (approximation for area-constrained)
        # The exact form is b = P_facility × f_misc, but P_facility
        # is what we're computing. Using P_IT introduces a small error:
        # ~f_misc × (PUE−1) × f_misc ≈ 0.025 × 0.3 × 0.025 ≈ 0.02%
        # Negligible for feasibility.
        b_kw = it_load_kw * f_misc

    # ── Hourly simulation loop ──
    hourly_pue = []
    hourly_it_kw = []
    hourly_facility_kw = []
    hourly_mode = []
    hourly_cop = []
    hourly_cool = []
    total_electrical_losses_kwh = 0.0
    total_fan_pump_kwh = 0.0
    total_cooling_kwh = 0.0
    total_economizer_kwh = 0.0
    total_misc_kwh = 0.0

    sum_facility = 0.0
    sum_it = 0.0

    # Mode counters
    mech_hours = 0
    econ_part_hours = 0
    econ_full_hours = 0
    overtemp_hours = 0

    # Cooling energy accumulators (for energy-weighted mode breakdown)
    mech_cool_energy = 0.0
    econ_part_cool_energy = 0.0
    # econ_full always contributes 0 cooling energy

    for t in range(n_hours):
        T_db = temperatures[t]
        RH = humidities[t] if humidities is not None else None

        # Step 1: Get cooling state and overhead terms for this hour.
        state, elec_loss, a_t, _ = _hourly_state_terms(
            T_db=T_db,
            RH=RH,
            cooling_type=cooling_type,
            eta_chain=eta_chain,
            f_misc=f_misc,
            override_preset_key=override_preset_key,
        )

        # Step 3: Compute facility and IT power
        if is_power_constrained:
            assert facility_power_kw is not None
            # P_facility = fixed, P_IT varies
            p_facility = facility_power_kw
            p_it = (facility_power_kw - b_kw) / (1.0 + a_t)
        else:
            assert it_load_kw is not None
            # P_IT = fixed, P_facility varies
            p_it = it_load_kw
            p_facility = it_load_kw * (1.0 + a_t) + b_kw

        # Step 4: PUE for this hour
        pue_t = p_facility / p_it if p_it > 0 else float("inf")

        # Step 5: Accumulate
        sum_facility += p_facility
        sum_it += p_it
        total_electrical_losses_kwh += p_it * elec_loss
        total_fan_pump_kwh += p_it * state.k_fan
        total_cooling_kwh += p_it * state.cool_kw_per_kw_it
        total_economizer_kwh += p_it * state.k_econ
        total_misc_kwh += b_kw

        hourly_pue.append(pue_t)
        hourly_it_kw.append(p_it)
        hourly_facility_kw.append(p_facility)
        hourly_mode.append(state.mode.value)
        hourly_cop.append(state.cop)
        hourly_cool.append(state.cool_kw_per_kw_it)

        # Mode counting
        if state.mode == CoolingMode.MECH:
            mech_hours += 1
            mech_cool_energy += state.cool_kw_per_kw_it
        elif state.mode == CoolingMode.ECON_PART:
            econ_part_hours += 1
            econ_part_cool_energy += state.cool_kw_per_kw_it
        else:  # ECON_FULL
            econ_full_hours += 1
            # No cooling energy contribution

        if state.is_overtemperature:
            overtemp_hours += 1

    # ── Annual PUE (energy-weighted) ──
    # Source: Architecture Agreement Section 3.4
    # PUE_annual = Σ P_facility(t) / Σ P_IT(t)
    # This is the ONLY correct definition. NOT the arithmetic average.
    annual_pue = sum_facility / sum_it if sum_it > 0 else float("inf")

    # ── IT capacity spectrum ──
    # Source: Architecture Agreement Section 3.7
    sorted_it = sorted(hourly_it_kw)

    it_worst = sorted_it[0]
    it_best = sorted_it[-1]
    it_mean = sum_it / n_hours
    it_p99 = _percentile_low(sorted_it, 1.0)   # Available 99% of time
    it_p90 = _percentile_low(sorted_it, 10.0)   # Available 90% of time

    # ── Cooling energy-weighted mode breakdown ──
    total_cool_energy = mech_cool_energy + econ_part_cool_energy
    if total_cool_energy > 0:
        mech_energy_frac = mech_cool_energy / total_cool_energy
        econ_part_energy_frac = econ_part_cool_energy / total_cool_energy
    else:
        # All hours are ECON_FULL (no cooling energy at all)
        mech_energy_frac = 0.0
        econ_part_energy_frac = 0.0
    econ_full_energy_frac = 0.0  # Always 0 by definition

    return HourlySimResult(
        annual_pue=round(annual_pue, 6),
        total_facility_kwh=round(sum_facility, 4),
        total_it_kwh=round(sum_it, 4),
        it_capacity_worst_kw=round(it_worst, 4),
        it_capacity_p99_kw=round(it_p99, 4),
        it_capacity_p90_kw=round(it_p90, 4),
        it_capacity_mean_kw=round(it_mean, 4),
        it_capacity_best_kw=round(it_best, 4),
        mech_hours=mech_hours,
        econ_part_hours=econ_part_hours,
        econ_full_hours=econ_full_hours,
        mech_energy_frac=round(mech_energy_frac, 6),
        econ_part_energy_frac=round(econ_part_energy_frac, 6),
        econ_full_energy_frac=econ_full_energy_frac,
        overtemperature_hours=overtemp_hours,
        hourly_pue=hourly_pue,
        hourly_it_kw=hourly_it_kw,
        hourly_facility_kw=hourly_facility_kw,
        hourly_mode=hourly_mode,
        hourly_cop=hourly_cop,
        hourly_cool_kw_per_kw_it=hourly_cool,
        total_electrical_losses_kwh=round(total_electrical_losses_kwh, 4),
        total_fan_pump_kwh=round(total_fan_pump_kwh, 4),
        total_cooling_kwh=round(total_cooling_kwh, 4),
        total_economizer_kwh=round(total_economizer_kwh, 4),
        total_misc_kwh=round(total_misc_kwh, 4),
        total_overhead_kwh=round(sum_facility - sum_it, 4),
    )
