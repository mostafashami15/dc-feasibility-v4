"""
DC Feasibility Tool v4 — Cooling Model
========================================
Computes COP, cooling mode, and hourly cooling load per kW of IT.

This module provides the thermal side of the hourly engine. For each
hour of the year, pue_engine.py calls compute_hourly_cooling() with
that hour's weather data. The result feeds directly into the facility
power formula:

    P_facility(t) = P_IT(t) × (1 + a(t)) + b(t)

    where a(t) = elec_loss + k_fan + cool_kW_per_kW_IT(t) + [k_econ if econ]

This module computes cool_kW_per_kW_IT(t) and determines which cooling
mode is active (MECH, ECON_PART, ECON_FULL), which tells pue_engine.py
whether to include k_econ.

Four topologies (from COOLING_PROFILES['topology']):
    mechanical_only           → Always MECH. CRAC, AHU.
    chiller_integral_economizer → 3-mode. Air Chiller, RDHx, DLC, Immersion.
    water_side_economizer     → 2-mode, COP uses wet-bulb. Water Chiller.
    air_side_economizer       → 2-mode, no compressor. Dry Cooler.

Dependencies:
    engine.assumptions — COOLING_PROFILES (COP parameters, thresholds)
    engine.models — CoolingMode enum

Reference: Architecture Agreement v2.0, Sections 3.2, 3.3
"""

import math
from typing import NamedTuple

from engine.assumption_overrides import (
    get_effective_cooling_profile,
    get_effective_misc_overhead_fraction,
)


# ─────────────────────────────────────────────────────────────
# CoolingMode Enum
# ─────────────────────────────────────────────────────────────
# Defined here (not in models.py) because it's internal to the
# cooling/PUE engine and not part of the API data models.
# If pue_engine.py needs it, it imports from cooling.py.

from enum import Enum


class CoolingMode(str, Enum):
    """Cooling operating mode for a given hour.

    MECH:      Full mechanical cooling (compressor running).
    ECON_PART: Partial economizer — compressor + economizer share the load.
    ECON_FULL: Full economizer — compressor off, free cooling only.

    Source: Architecture Agreement Section 3.3
    """
    MECH = "MECH"
    ECON_PART = "ECON_PART"
    ECON_FULL = "ECON_FULL"


# ─────────────────────────────────────────────────────────────
# HourlyCoolingState — returned by compute_hourly_cooling()
# ─────────────────────────────────────────────────────────────
# Using NamedTuple for performance (8,760 calls/year).
# Pydantic models are too heavy for per-hour data.

class HourlyCoolingState(NamedTuple):
    """Cooling state for a single hour.

    Attributes:
        mode: Active cooling mode (MECH, ECON_PART, ECON_FULL).
        cop: Coefficient of Performance at this hour's conditions.
             Meaningless when mode=ECON_FULL (compressor off), set to 0.
        cool_kw_per_kw_it: Cooling electrical demand per kW of IT load.
                           This is the value that goes into the a(t) formula.
                           0.0 when mode=ECON_FULL.
        k_fan: Fan/pump overhead as fraction of IT (from profile).
        k_econ: Economizer overhead as fraction of IT (non-zero only
                when mode is ECON_PART or ECON_FULL).
        is_overtemperature: True if dry-cooler topology cannot maintain
                           setpoint at this ambient temperature.
                           Only relevant for air_side_economizer topology.
    """
    mode: CoolingMode
    cop: float
    cool_kw_per_kw_it: float
    k_fan: float
    k_econ: float
    is_overtemperature: bool


def _combine_hybrid_modes(primary: CoolingMode, residual: CoolingMode) -> CoolingMode:
    """Combine two cooling modes into one system-level mode."""
    if primary == CoolingMode.ECON_FULL and residual == CoolingMode.ECON_FULL:
        return CoolingMode.ECON_FULL
    if primary == CoolingMode.MECH and residual == CoolingMode.MECH:
        return CoolingMode.MECH
    return CoolingMode.ECON_PART


# ═════════════════════════════════════════════════════════════
# WET-BULB TEMPERATURE
# ═════════════════════════════════════════════════════════════

def compute_wet_bulb(T_db: float, RH: float) -> float:
    """Compute wet-bulb temperature using the Stull (2011) approximation.

    This is needed for water-cooled systems where the condenser rejects
    heat to a cooling tower. Cooling towers approach the wet-bulb
    temperature, not the dry-bulb.

    Formula:
        T_wb = T × atan(0.151977 × √(RH + 8.313659))
               + atan(T + RH)
               − atan(RH − 1.676331)
               + 0.00391838 × RH^1.5 × atan(0.023101 × RH)
               − 4.686035

    Source: Stull, R. (2011). "Wet-Bulb Temperature from Relative
    Humidity and Air Temperature." Journal of Applied Meteorology
    and Climatology, 50(11), 2267–2269.

    Valid range: T = −20°C to 50°C, RH = 5% to 99%.
    Accuracy: ±1°C for most conditions, ±0.3°C in the 5–35°C range.

    Args:
        T_db: Dry-bulb temperature in °C.
        RH: Relative humidity in % (0–100 scale, NOT 0–1).

    Returns:
        Wet-bulb temperature in °C.

    Raises:
        ValueError: If RH is outside [0, 100] or appears to be fractional.
    """
    if RH < 0 or RH > 100:
        raise ValueError(f"RH must be 0–100%, got {RH}")
    if 0 < RH < 1:
        raise ValueError(
            f"RH={RH} looks fractional. Use 0–100 scale, not 0–1."
        )

    T_wb = (
        T_db * math.atan(0.151977 * math.sqrt(RH + 8.313659))
        + math.atan(T_db + RH)
        - math.atan(RH - 1.676331)
        + 0.00391838 * (RH ** 1.5) * math.atan(0.023101 * RH)
        - 4.686035
    )
    return T_wb


# ═════════════════════════════════════════════════════════════
# COP MODEL
# ═════════════════════════════════════════════════════════════

def compute_cop(
    T_db: float,
    RH: float | None,
    cooling_type: str,
    override_preset_key: str | None = None,
) -> float:
    """Compute the Coefficient of Performance at given conditions.

    Linear model (first-order Taylor expansion of Carnot COP):
        COP(T) = COP_ref + COP_slope × (T_ref − T_driver)
        clamped to [COP_min, COP_max]

    The condenser driver temperature depends on the topology:
        - Air-cooled systems → T_driver = T_db (dry-bulb)
        - Water-cooled systems → T_driver = T_wb (wet-bulb)

    Source: ASHRAE Handbook — HVAC Systems and Equipment, Chapter 38.
    COP defaults per topology: Architecture Agreement Section 3.2.

    Args:
        T_db: Dry-bulb temperature in °C.
        RH: Relative humidity in % (required for water-cooled topology,
            None acceptable for air-cooled topologies).
        cooling_type: Key from COOLING_PROFILES (e.g., "Air-Cooled CRAC (DX)").

    Returns:
        COP value (always ≥ COP_min, ≤ COP_max).

    Raises:
        KeyError: If cooling_type is not in COOLING_PROFILES.
        ValueError: If RH is None for water-cooled topology.
    """
    profile = get_effective_cooling_profile(cooling_type, override_preset_key)

    # Resolve condenser driver temperature
    if profile["topology"] == "water_side_economizer":
        # Water-cooled: COP driven by wet-bulb temperature
        # Source: ASHRAE Fundamentals Ch.1 — cooling towers reject to wet-bulb
        if RH is None:
            raise ValueError(
                f"RH is required for water-cooled topology '{cooling_type}'. "
                f"Cooling towers reject heat to the wet-bulb temperature."
            )
        T_driver = compute_wet_bulb(T_db, RH)
    else:
        # All other topologies: COP driven by dry-bulb temperature
        T_driver = T_db

    # Linear COP model with clamping
    COP_ref = profile["COP_ref"]
    COP_slope = profile["COP_slope"]
    T_ref = profile["T_ref_C"]
    COP_min = profile["COP_min"]
    COP_max = profile["COP_max"]

    cop_raw = COP_ref + COP_slope * (T_ref - T_driver)
    cop_clamped = max(COP_min, min(COP_max, cop_raw))

    return cop_clamped


# ═════════════════════════════════════════════════════════════
# COOLING MODE DETERMINATION
# ═════════════════════════════════════════════════════════════

def _determine_cooling_mode_base(
    T_db: float,
    RH: float | None,
    cooling_type: str,
    override_preset_key: str | None = None,
) -> CoolingMode:
    """Determine the active cooling mode for given ambient conditions.

    Each topology has a different mode selection logic:

    1. mechanical_only (CRAC, AHU):
       → Always MECH. No economizer option.

    2. chiller_integral_economizer (Air Chiller, RDHx, DLC, Immersion):
       → 3-mode based on dry-bulb:
         ECON_FULL when T_db ≤ CHWS_set − ECO_full_approach  (compressor off)
         ECON_PART when T_db ≤ CHWR_target − ECO_enable_dT   (blended)
         MECH      when T_db > CHWR_target − ECO_enable_dT   (full compressor)

    3. water_side_economizer (Water Chiller):
       → 2-mode based on wet-bulb:
         ECON_FULL when T_wb ≤ WSE_WB_C
         MECH      otherwise

    4. air_side_economizer (Dry Cooler):
       → 2-mode based on dry-bulb:
         ECON_FULL when T_db ≤ ASE_DB_C
         MECH      otherwise (overtemperature risk!)

    Source: Architecture Agreement Section 3.3 (mode definitions),
    COOLING_PROFILES thresholds in assumptions.py.

    Args:
        T_db: Dry-bulb temperature in °C.
        RH: Relative humidity in % (required for water-cooled topology).
        cooling_type: Key from COOLING_PROFILES.

    Returns:
        CoolingMode enum value.
    """
    profile = get_effective_cooling_profile(cooling_type, override_preset_key)
    topology = profile["topology"]

    # ── mechanical_only: always MECH ──
    if topology == "mechanical_only":
        return CoolingMode.MECH

    # ── chiller_integral_economizer: 3-mode ──
    if topology == "chiller_integral_economizer":
        # Thresholds from profile
        CHWS = profile["CHWS_set_C"]
        CHWR = profile["CHWR_target_C"]
        ECO_full_approach = profile["ECO_full_approach_C"]
        ECO_enable_dT = profile["ECO_enable_dT_C"]

        # Temperature boundaries
        T_econ_full = CHWS - ECO_full_approach  # Below this: compressor off
        T_mech = CHWR - ECO_enable_dT           # Above this: full compressor

        if T_db <= T_econ_full:
            return CoolingMode.ECON_FULL
        elif T_db <= T_mech:
            return CoolingMode.ECON_PART
        else:
            return CoolingMode.MECH

    # ── water_side_economizer: 2-mode (wet-bulb) ──
    if topology == "water_side_economizer":
        if RH is None:
            raise ValueError(
                f"RH required for water-side economizer '{cooling_type}'."
            )
        T_wb = compute_wet_bulb(T_db, RH)
        WSE_WB = profile["WSE_WB_C"]

        if T_wb <= WSE_WB:
            return CoolingMode.ECON_FULL
        else:
            return CoolingMode.MECH

    # ── air_side_economizer: 2-mode ──
    if topology == "air_side_economizer":
        ASE_DB = profile["ASE_DB_C"]

        if T_db <= ASE_DB:
            return CoolingMode.ECON_FULL
        else:
            # Above threshold: no compressor, can't maintain setpoint.
            # Mode is MECH in the sense that cooling is needed but
            # the system has no mechanical backup. The is_overtemperature
            # flag in HourlyCoolingState captures this condition.
            return CoolingMode.MECH

    raise ValueError(f"Unknown topology '{topology}' for '{cooling_type}'")


def determine_cooling_mode(
    T_db: float,
    RH: float | None,
    cooling_type: str,
    override_preset_key: str | None = None,
) -> CoolingMode:
    """Determine the active cooling mode for given ambient conditions."""
    profile = get_effective_cooling_profile(cooling_type, override_preset_key)

    if "liquid_coverage_fraction" in profile and "residual_cooling_type" in profile:
        primary_mode = _determine_cooling_mode_base(
            T_db, RH, cooling_type, override_preset_key
        )
        residual_mode = _determine_cooling_mode_base(
            T_db, RH, profile["residual_cooling_type"], override_preset_key
        )
        return _combine_hybrid_modes(primary_mode, residual_mode)

    return _determine_cooling_mode_base(T_db, RH, cooling_type, override_preset_key)


# ═════════════════════════════════════════════════════════════
# COOLING LOAD PER kW IT
# ═════════════════════════════════════════════════════════════

def _compute_cooling_load_mech(
    cop: float,
    elec_loss: float,
    k_fan: float,
    f_misc: float,
) -> float:
    """Cooling electrical load in MECH mode, per kW of IT.

    Formula:
        cool_kW/kW_IT = (1 + elec_loss + k_fan + f_misc) / COP

    The numerator represents the total heat that must be rejected
    by the cooling plant:
        1       = IT equipment heat
        elec_loss = UPS/transformer/PDU conversion losses (heat)
        k_fan   = Fan/pump motor heat inside the data hall
        f_misc  = Miscellaneous heat (lighting, BMS, etc.)

    Source: Architecture Agreement Section 3.3
    v3 correction: k_fan in numerator (ASHRAE 90.4 Section 6.4.3).

    Args:
        cop: COP at this hour's conditions (from compute_cop).
        elec_loss: (1 / eta_chain) - 1. Electrical conversion losses.
        k_fan: Fan/pump power as fraction of IT load (from profile).
        f_misc: Miscellaneous overhead fraction (from MISC_OVERHEAD).

    Returns:
        Cooling electrical demand per kW of IT load.
    """
    heat_to_reject = 1.0 + elec_loss + k_fan + f_misc
    return heat_to_reject / cop


def _compute_blend_factor(
    T_db: float,
    T_econ_full: float,
    T_mech: float,
) -> float:
    """Compute the ECON_PART blend factor.

    The blend factor linearly interpolates between full economizer
    (blend=0, compressor off) and full mechanical (blend=1, full compressor).

    Formula:
        blend = (T_amb − T_econ_full) / (T_mech − T_econ_full)
        clamped to [0, 1]

    At T_econ_full: blend = 0 (all economizer)
    At T_mech:      blend = 1 (all compressor)
    Between:        proportional mix

    Source: Architecture Agreement Section 3.3

    Args:
        T_db: Ambient dry-bulb temperature.
        T_econ_full: Temperature at which economizer can handle full load.
        T_mech: Temperature at which compressor must handle full load.

    Returns:
        Blend factor between 0.0 and 1.0.
    """
    if T_mech <= T_econ_full:
        # Degenerate case: no partial range. Should not occur with valid profiles.
        return 1.0
    blend = (T_db - T_econ_full) / (T_mech - T_econ_full)
    return max(0.0, min(1.0, blend))


# ═════════════════════════════════════════════════════════════
# MAIN ENTRY POINT — called 8,760 times per scenario
# ═════════════════════════════════════════════════════════════

def _compute_hourly_cooling_base(
    T_db: float,
    RH: float | None,
    cooling_type: str,
    eta_chain: float,
    f_misc: float | None = None,
    override_preset_key: str | None = None,
) -> HourlyCoolingState:
    """Compute complete cooling state for one hour.

    This is the main function called by pue_engine.py for each of
    the 8,760 hours. It combines mode determination, COP calculation,
    and cooling load computation into a single call.

    The k_fan value is looked up from COOLING_PROFILES (not passed in)
    because it is a physical property of the cooling topology, not a
    scenario parameter.

    Args:
        T_db: Dry-bulb temperature in °C for this hour.
        RH: Relative humidity in % (0–100). Required for water-cooled
            topologies (cooling tower). Pass None for air-cooled if
            RH data is unavailable.
        cooling_type: Key from COOLING_PROFILES
                      (e.g., "Air-Cooled Chiller + Economizer").
        eta_chain: Power chain efficiency (from REDUNDANCY_PROFILES).
                   Used to compute elec_loss = (1/eta_chain) - 1.
        f_misc: Miscellaneous overhead fraction.
                Default 0.025 (2.5%) from MISC_OVERHEAD.

    Returns:
        HourlyCoolingState with mode, COP, cooling load, and flags.

    Example:
        >>> state = compute_hourly_cooling(
        ...     T_db=18.0, RH=None,
        ...     cooling_type="Air-Cooled Chiller + Economizer",
        ...     eta_chain=0.95
        ... )
        >>> print(f"Mode: {state.mode}, Cool load: {state.cool_kw_per_kw_it:.4f}")
        Mode: ECON_PART, Cool load: 0.0700
    """
    profile = get_effective_cooling_profile(cooling_type, override_preset_key)
    if f_misc is None:
        f_misc = get_effective_misc_overhead_fraction(override_preset_key)
    topology = profile["topology"]
    k_fan = profile["k_fan"]
    k_econ = profile["k_econ"]
    elec_loss = (1.0 / eta_chain) - 1.0

    # ── Step 1: Determine cooling mode ──
    mode = _determine_cooling_mode_base(T_db, RH, cooling_type, override_preset_key)

    # ── Step 2: Compute COP (even for ECON_FULL, though not used) ──
    # For ECON_FULL, COP is meaningless (compressor off), but we
    # compute it anyway for logging/analysis. Set to 0.0 in output.
    if mode == CoolingMode.ECON_FULL:
        cop = 0.0
    else:
        cop = compute_cop(T_db, RH, cooling_type, override_preset_key)

    # ── Step 3: Compute cooling load per kW IT ──
    if mode == CoolingMode.MECH:
        # Full mechanical: entire heat rejection via compressor
        cool_kw = _compute_cooling_load_mech(cop, elec_loss, k_fan, f_misc)
        econ_active = False
        is_overtemp = False

        # Check overtemperature for dry cooler (air_side_economizer)
        # In this topology, "MECH" means the ambient exceeds the
        # threshold and the system CANNOT maintain setpoint.
        if topology == "air_side_economizer":
            is_overtemp = True
            # Dry cooler has no compressor — COP is fan-only.
            # When overtemperature, the fans still run but can't
            # maintain setpoint. We still compute the fan power.
            # The cool_kw computed above represents the fan energy,
            # but the heat rejection is insufficient.

    elif mode == CoolingMode.ECON_PART:
        # Partial economizer: blend between ECON_FULL and MECH
        # Source: Architecture Agreement Section 3.3
        CHWS = profile["CHWS_set_C"]
        CHWR = profile["CHWR_target_C"]
        ECO_full_approach = profile["ECO_full_approach_C"]
        ECO_enable_dT = profile["ECO_enable_dT_C"]

        T_econ_full = CHWS - ECO_full_approach
        T_mech = CHWR - ECO_enable_dT

        blend = _compute_blend_factor(T_db, T_econ_full, T_mech)
        full_mech_load = _compute_cooling_load_mech(
            cop, elec_loss, k_fan, f_misc
        )
        cool_kw = blend * full_mech_load
        econ_active = True
        is_overtemp = False

    else:  # ECON_FULL
        # Full economizer: compressor off. Cooling load = 0.
        # Only residual overhead is the economizer pump/fans,
        # captured by k_econ in the a(t) formula.
        # Source: Architecture Agreement Section 3.3
        cool_kw = 0.0
        econ_active = True
        is_overtemp = False

    # k_econ is only added to a(t) when economizer is active
    effective_k_econ = k_econ if econ_active else 0.0

    return HourlyCoolingState(
        mode=mode,
        cop=cop,
        cool_kw_per_kw_it=cool_kw,
        k_fan=k_fan,
        k_econ=effective_k_econ,
        is_overtemperature=is_overtemp,
    )


def compute_hourly_cooling(
    T_db: float,
    RH: float | None,
    cooling_type: str,
    eta_chain: float,
    f_misc: float | None = None,
    override_preset_key: str | None = None,
) -> HourlyCoolingState:
    """Compute complete cooling state for one hour."""
    profile = get_effective_cooling_profile(cooling_type, override_preset_key)
    if f_misc is None:
        f_misc = get_effective_misc_overhead_fraction(override_preset_key)

    if "liquid_coverage_fraction" not in profile or "residual_cooling_type" not in profile:
        return _compute_hourly_cooling_base(
            T_db,
            RH,
            cooling_type,
            eta_chain,
            f_misc,
            override_preset_key,
        )

    liquid_fraction = profile["liquid_coverage_fraction"]
    residual_fraction = 1.0 - liquid_fraction
    residual_type = profile["residual_cooling_type"]

    primary = _compute_hourly_cooling_base(
        T_db,
        RH,
        cooling_type,
        eta_chain,
        f_misc,
        override_preset_key,
    )
    residual = _compute_hourly_cooling_base(
        T_db,
        RH,
        residual_type,
        eta_chain,
        f_misc,
        override_preset_key,
    )

    active_cops = []
    if primary.mode != CoolingMode.ECON_FULL:
        active_cops.append((liquid_fraction, primary.cop))
    if residual.mode != CoolingMode.ECON_FULL:
        active_cops.append((residual_fraction, residual.cop))

    if active_cops:
        total_weight = sum(weight for weight, _ in active_cops)
        effective_cop = sum(weight * cop for weight, cop in active_cops) / total_weight
    else:
        effective_cop = 0.0

    return HourlyCoolingState(
        mode=_combine_hybrid_modes(primary.mode, residual.mode),
        cop=effective_cop,
        cool_kw_per_kw_it=(
            liquid_fraction * primary.cool_kw_per_kw_it
            + residual_fraction * residual.cool_kw_per_kw_it
        ),
        k_fan=(
            liquid_fraction * primary.k_fan
            + residual_fraction * residual.k_fan
        ),
        k_econ=(
            liquid_fraction * primary.k_econ
            + residual_fraction * residual.k_econ
        ),
        is_overtemperature=primary.is_overtemperature or residual.is_overtemperature,
    )
