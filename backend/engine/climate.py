"""
DC Feasibility Tool v4 — Climate Analysis Module
==================================================
Analyses hourly weather data to produce climate suitability metrics
for data center feasibility.

Key outputs:
    1. Free cooling hours — per cooling type, how many hours/year the
       compressor can be off (ECON_FULL mode).
    2. Climate suitability rating — EXCELLENT/GOOD/MARGINAL/NOT_RECOMMENDED
       based on free cooling hours.
    3. Temperature statistics — min, max, mean, percentiles, monthly.
    4. Delta projection — impact of +X°C climate change on all metrics.

The free cooling threshold depends on the cooling topology:
    - chiller_integral_economizer: T_db ≤ CHWS − ECO_full_approach
    - water_side_economizer: T_wb ≤ WSE_WB_C (needs RH)
    - air_side_economizer: T_db ≤ ASE_DB_C
    - mechanical_only: 0 hours (no economizer)

Dependencies:
    engine.assumptions — COOLING_PROFILES, CLIMATE_SUITABILITY
    engine.cooling — compute_wet_bulb

Reference: Architecture Agreement v2.0, Sections 3.10, 3.17
"""

import math
from dataclasses import dataclass, field
from typing import Optional

from engine.assumptions import COOLING_PROFILES, CLIMATE_SUITABILITY
from engine.cooling import compute_wet_bulb, determine_cooling_mode, CoolingMode


# ─────────────────────────────────────────────────────────────
# Result Data Classes
# ─────────────────────────────────────────────────────────────

@dataclass
class TemperatureStats:
    """Statistical summary of the temperature dataset.

    All values in °C.
    """
    count: int
    mean: float
    min: float
    max: float
    median: float
    p1: float    # 1st percentile (design cold)
    p99: float   # 99th percentile (design hot)
    std_dev: float


@dataclass
class MonthlyStats:
    """Monthly temperature summary.

    Each list has 12 entries (index 0 = January, 11 = December).
    For datasets shorter than 8,760 hours, monthly breakdown is
    not meaningful — use only with full-year data.
    """
    monthly_mean: list[float] = field(default_factory=list)
    monthly_min: list[float] = field(default_factory=list)
    monthly_max: list[float] = field(default_factory=list)


@dataclass
class FreeCoolingAnalysis:
    """Free cooling hours analysis for a specific cooling type.

    Attributes:
        cooling_type: The cooling type analysed.
        threshold_description: Human-readable threshold description.
        free_cooling_hours: Number of hours in ECON_FULL mode.
        partial_hours: Number of hours in ECON_PART mode.
        mechanical_hours: Number of hours in MECH mode.
        free_cooling_fraction: free_cooling_hours / total_hours.
        suitability: Climate suitability rating.
    """
    cooling_type: str
    threshold_description: str
    free_cooling_hours: int
    partial_hours: int
    mechanical_hours: int
    free_cooling_fraction: float
    suitability: str  # EXCELLENT / GOOD / MARGINAL / NOT_RECOMMENDED


@dataclass
class ClimateAnalysisResult:
    """Complete climate analysis for a site.

    Contains temperature statistics, free cooling analysis for
    one or more cooling types, and optional delta projections.
    """
    temperature_stats: TemperatureStats
    monthly_stats: Optional[MonthlyStats]
    free_cooling: list[FreeCoolingAnalysis] = field(default_factory=list)
    delta_results: dict = field(default_factory=dict)
    # delta_results maps delta_C (float) → FreeCoolingAnalysis list


# ═════════════════════════════════════════════════════════════
# TEMPERATURE STATISTICS
# ═════════════════════════════════════════════════════════════

def compute_temperature_stats(temperatures: list[float]) -> TemperatureStats:
    """Compute statistical summary of temperature data.

    Args:
        temperatures: Hourly dry-bulb temperatures in °C.

    Returns:
        TemperatureStats with all summary metrics.

    Raises:
        ValueError: If temperatures is empty.
    """
    n = len(temperatures)
    if n == 0:
        raise ValueError("temperatures must not be empty")

    sorted_t = sorted(temperatures)
    mean = sum(temperatures) / n
    t_min = sorted_t[0]
    t_max = sorted_t[-1]
    median = sorted_t[n // 2]

    # Percentiles (nearest-rank)
    p1_idx = max(0, min(n - 1, int(math.floor(n * 0.01))))
    p99_idx = max(0, min(n - 1, int(math.floor(n * 0.99))))
    p1 = sorted_t[p1_idx]
    p99 = sorted_t[p99_idx]

    # Standard deviation
    variance = sum((t - mean) ** 2 for t in temperatures) / n
    std_dev = math.sqrt(variance)

    return TemperatureStats(
        count=n,
        mean=round(mean, 2),
        min=round(t_min, 2),
        max=round(t_max, 2),
        median=round(median, 2),
        p1=round(p1, 2),
        p99=round(p99, 2),
        std_dev=round(std_dev, 2),
    )


# ═════════════════════════════════════════════════════════════
# MONTHLY BREAKDOWN
# ═════════════════════════════════════════════════════════════

# Hours per month in a standard (non-leap) year
HOURS_PER_MONTH = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
# Jan=744, Feb=672 (28d), Mar=744, Apr=720, May=744, Jun=720,
# Jul=744, Aug=744, Sep=720, Oct=744, Nov=720, Dec=744
# Sum = 8760


def compute_monthly_stats(temperatures: list[float]) -> Optional[MonthlyStats]:
    """Compute monthly temperature breakdown for a full-year dataset.

    Only meaningful for 8,760-hour datasets. Returns None for
    shorter datasets.

    Args:
        temperatures: Hourly temperatures (must be exactly 8,760 for
            monthly breakdown).

    Returns:
        MonthlyStats with 12-element lists, or None if not 8,760 hours.
    """
    if len(temperatures) != 8760:
        return None

    monthly_mean = []
    monthly_min = []
    monthly_max = []

    offset = 0
    for hours in HOURS_PER_MONTH:
        month_temps = temperatures[offset:offset + hours]
        monthly_mean.append(round(sum(month_temps) / hours, 2))
        monthly_min.append(round(min(month_temps), 2))
        monthly_max.append(round(max(month_temps), 2))
        offset += hours

    return MonthlyStats(
        monthly_mean=monthly_mean,
        monthly_min=monthly_min,
        monthly_max=monthly_max,
    )


# ═════════════════════════════════════════════════════════════
# FREE COOLING HOURS
# ═════════════════════════════════════════════════════════════

def _get_free_cooling_threshold(cooling_type: str) -> tuple[str, float | None, str]:
    """Get the free cooling threshold for a cooling type.

    Returns:
        Tuple of (driver, threshold, description):
        - driver: "drybulb", "wetbulb", or "none"
        - threshold: Temperature threshold in °C, or None for no economizer
        - description: Human-readable threshold description
    """
    profile = COOLING_PROFILES[cooling_type]
    topology = profile["topology"]

    if "liquid_coverage_fraction" in profile and "residual_cooling_type" in profile:
        residual_type = profile["residual_cooling_type"]
        residual_profile = COOLING_PROFILES[residual_type]
        residual_chws = residual_profile["CHWS_set_C"]
        residual_approach = residual_profile["ECO_full_approach_C"]
        residual_threshold = residual_chws - residual_approach
        primary_threshold = profile["CHWS_set_C"] - profile["ECO_full_approach_C"]
        return (
            "hybrid",
            None,
            "Full free cooling requires both DLC and residual air path to be in ECON_FULL "
            f"(DLC T_db ≤ {primary_threshold:.1f}°C; residual air T_db ≤ {residual_threshold:.1f}°C).",
        )

    if topology == "mechanical_only":
        return ("none", None, "No economizer — 0 free cooling hours")

    if topology == "chiller_integral_economizer":
        CHWS = profile["CHWS_set_C"]
        ECO_full_approach = profile["ECO_full_approach_C"]
        threshold = CHWS - ECO_full_approach
        return ("drybulb", threshold,
                f"T_db ≤ {threshold:.1f}°C (CHWS={CHWS}°C − approach={ECO_full_approach}°C)")

    if topology == "water_side_economizer":
        WSE_WB = profile["WSE_WB_C"]
        return ("wetbulb", WSE_WB,
                f"T_wb ≤ {WSE_WB:.1f}°C (wet-bulb threshold)")

    if topology == "air_side_economizer":
        ASE_DB = profile["ASE_DB_C"]
        return ("drybulb", ASE_DB,
                f"T_db ≤ {ASE_DB:.1f}°C (dry cooler threshold)")

    return ("none", None, f"Unknown topology '{topology}'")


def count_cooling_mode_hours(
    temperatures: list[float],
    cooling_type: str,
    humidities: list[float] | None = None,
    delta_C: float = 0.0,
) -> tuple[int, int, int]:
    """Count hours in each cooling mode: ECON_FULL, ECON_PART, and MECH.

    Uses the actual per-topology thresholds from COOLING_PROFILES via
    determine_cooling_mode(), so each cooling type gets its correct
    economizer thresholds rather than a single shared threshold.

    Args:
        temperatures: Dry-bulb temperatures in °C.
        cooling_type: Key from COOLING_PROFILES.
        humidities: Relative humidity in % (required for water-cooled).
        delta_C: Temperature delta for climate projection.
            Applied uniformly to all hours.
            Source: Architecture Agreement Section 3.10 — CIBSE TM49.

    Returns:
        Tuple of (econ_full_hours, econ_part_hours, mech_hours).
    """
    econ_full = 0
    econ_part = 0
    mech = 0

    profile = COOLING_PROFILES[cooling_type]

    # For topologies without an economizer, all hours are mechanical
    if profile["topology"] == "mechanical_only":
        return (0, 0, len(temperatures))

    for i, T in enumerate(temperatures):
        T_shifted = T + delta_C
        RH = humidities[i] if humidities is not None else None
        mode = determine_cooling_mode(T_shifted, RH, cooling_type)
        if mode == CoolingMode.ECON_FULL:
            econ_full += 1
        elif mode == CoolingMode.ECON_PART:
            econ_part += 1
        else:
            mech += 1

    return (econ_full, econ_part, mech)


def count_free_cooling_hours(
    temperatures: list[float],
    cooling_type: str,
    humidities: list[float] | None = None,
    delta_C: float = 0.0,
) -> int:
    """Count hours where full free cooling (ECON_FULL) is available.

    This counts hours where the compressor can be completely off --
    the economizer handles the full cooling load alone.

    Args:
        temperatures: Dry-bulb temperatures in °C.
        cooling_type: Key from COOLING_PROFILES.
        humidities: Relative humidity in % (required for water-cooled).
        delta_C: Temperature delta for climate projection.
            Applied uniformly to all hours.
            Source: Architecture Agreement Section 3.10 -- CIBSE TM49.

    Returns:
        Number of free cooling hours.
    """
    econ_full, _, _ = count_cooling_mode_hours(
        temperatures, cooling_type, humidities, delta_C
    )
    return econ_full


# ═════════════════════════════════════════════════════════════
# CLIMATE SUITABILITY RATING
# ═════════════════════════════════════════════════════════════

def classify_suitability(free_cooling_hours: int) -> str:
    """Classify climate suitability based on free cooling hours.

    Thresholds (from CLIMATE_SUITABILITY in assumptions.py):
        EXCELLENT:       ≥ 7000 hours/year
        GOOD:            ≥ 5000 hours/year
        MARGINAL:        ≥ 3000 hours/year
        NOT_RECOMMENDED: < 3000 hours/year

    Source: Architecture Agreement Section 3.10 + v3 handbook Section 10.

    Args:
        free_cooling_hours: Number of ECON_FULL hours per year.

    Returns:
        Rating string: "EXCELLENT", "GOOD", "MARGINAL", or "NOT_RECOMMENDED".
    """
    # Check in descending order of threshold
    for rating in ["EXCELLENT", "GOOD", "MARGINAL"]:
        if free_cooling_hours >= CLIMATE_SUITABILITY[rating]["min_hours"]:
            return rating
    return "NOT_RECOMMENDED"


# ═════════════════════════════════════════════════════════════
# FREE COOLING ANALYSIS (per cooling type)
# ═════════════════════════════════════════════════════════════

def analyse_free_cooling(
    temperatures: list[float],
    cooling_type: str,
    humidities: list[float] | None = None,
    delta_C: float = 0.0,
) -> FreeCoolingAnalysis:
    """Analyse free cooling potential for a specific cooling type.

    Computes hours in each cooling mode (ECON_FULL, ECON_PART, MECH)
    using the actual per-topology thresholds from COOLING_PROFILES.

    Args:
        temperatures: Dry-bulb temperatures in °C.
        cooling_type: Key from COOLING_PROFILES.
        humidities: RH in % (required for water-cooled).
        delta_C: Climate change temperature delta.

    Returns:
        FreeCoolingAnalysis with hours per mode, fraction, and suitability.
    """
    _, _, description = _get_free_cooling_threshold(cooling_type)
    total_hours = len(temperatures)

    econ_full, econ_part, mech = count_cooling_mode_hours(
        temperatures, cooling_type, humidities, delta_C
    )

    fraction = econ_full / total_hours if total_hours > 0 else 0.0
    suitability = classify_suitability(econ_full)

    return FreeCoolingAnalysis(
        cooling_type=cooling_type,
        threshold_description=description,
        free_cooling_hours=econ_full,
        partial_hours=econ_part,
        mechanical_hours=mech,
        free_cooling_fraction=round(fraction, 4),
        suitability=suitability,
    )


# ═════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═════════════════════════════════════════════════════════════

def analyse_climate(
    temperatures: list[float],
    cooling_types: list[str] | None = None,
    humidities: list[float] | None = None,
    deltas: list[float] | None = None,
) -> ClimateAnalysisResult:
    """Complete climate analysis for a site.

    This is the main function called by the API layer. It produces
    all climate metrics for the Climate & Weather page.

    Args:
        temperatures: Hourly dry-bulb temperatures in °C.
            Typically 8,760 values (one representative year).
        cooling_types: List of cooling type keys to analyse.
            If None, analyses all free-cooling-eligible types.
        humidities: RH in % (required if water-cooled types included).
        deltas: Temperature deltas for climate projection (°C).
            Default: [0.5, 1.0, 1.5, 2.0] per Architecture Agreement
            Section 3.10 (CIBSE TM49 approach, IPCC AR6 SSP2-4.5).

    Returns:
        ClimateAnalysisResult with all metrics.

    Example:
        >>> temps = [10.0] * 5000 + [25.0] * 3760
        >>> result = analyse_climate(temps, ["Air-Cooled Chiller + Economizer"])
        >>> print(result.free_cooling[0].suitability)
        'GOOD'
    """
    if len(temperatures) == 0:
        raise ValueError("temperatures must not be empty")

    # ── Default cooling types: all free-cooling-eligible ──
    # Skip water-cooled types when no humidity data is available,
    # since they need wet-bulb temperature (requires RH).
    if cooling_types is None:
        cooling_types = [
            name for name, profile in COOLING_PROFILES.items()
            if profile.get("free_cooling_eligible", False)
            and (profile["topology"] != "water_side_economizer" or humidities is not None)
        ]

    # ── Default deltas ──
    if deltas is None:
        deltas = [0.5, 1.0, 1.5, 2.0]

    # ── Temperature statistics ──
    temp_stats = compute_temperature_stats(temperatures)

    # ── Monthly breakdown (only for 8760-hour datasets) ──
    monthly = compute_monthly_stats(temperatures)

    # ── Free cooling analysis (baseline, delta=0) ──
    free_cooling = []
    for ct in cooling_types:
        fc = analyse_free_cooling(temperatures, ct, humidities, delta_C=0.0)
        free_cooling.append(fc)

    # ── Delta projection ──
    delta_results = {}
    for delta in deltas:
        delta_fc_list = []
        for ct in cooling_types:
            fc = analyse_free_cooling(
                temperatures, ct, humidities, delta_C=delta
            )
            delta_fc_list.append(fc)
        delta_results[delta] = delta_fc_list

    return ClimateAnalysisResult(
        temperature_stats=temp_stats,
        monthly_stats=monthly,
        free_cooling=free_cooling,
        delta_results=delta_results,
    )
