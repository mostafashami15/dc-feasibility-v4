"""
DC Feasibility Tool v4 — Sensitivity Analysis
================================================
Two functions:

1. compute_tornado()    — One-at-a-time (OAT) parameter variation.
                          Shows which input parameter has the biggest
                          impact on the output metric. For the tornado
                          chart in the Results Dashboard.

2. compute_break_even() — Given a target output (e.g., 15 MW IT load),
                          solve for the parameter value that achieves it.
                          Uses direct algebra on the power chain formulas.

Power-constrained formula (Architecture Agreement Section 3.1):
    IT_load = facility_power × η_chain / PUE

Area-constrained formula:
    IT_load = effective_racks × rack_density_kW / 1000
    effective_racks = (buildable × floors × ws_ratio / rack_fp) × ws_adj
    buildable = land_area × coverage_ratio   (in ratio mode)

Sensitivity parameters:
    - PUE: cooling efficiency; divides into IT load
    - η_chain: power chain efficiency; multiplies into IT load
    - rack_density_kw: power per rack; converts racks ↔ MW
    - whitespace_ratio: fraction of building for IT halls
    - site_coverage_ratio: fraction of land for building
    - available_power_mw: grid power input (power-constrained only)

Reference: Architecture Agreement v3.0, Sections 3.1, 3.3, 3.14
"""

from typing import Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

DEFAULT_VARIATION_PCT = 10.0
# Default ±% variation for tornado chart.
# 10% is standard for feasibility-grade sensitivity.
# Source: Engineering judgment; AACE International Recommended Practice
# 18R-97 uses ±10% for Class 4 estimates (feasibility stage).

SENSITIVITY_PARAMETERS = [
    "pue",
    "eta_chain",
    "rack_density_kw",
    "whitespace_ratio",
    "site_coverage_ratio",
    "available_power_mw",
]


# ─────────────────────────────────────────────────────────────
# Result Models
# ─────────────────────────────────────────────────────────────

class TornadoBar(BaseModel):
    """One bar in the tornado chart — one parameter's sensitivity range.

    The bar spans from output_at_low to output_at_high, centered
    on the baseline output. Wider bars = more influential parameters.
    """
    parameter: str = Field(description="Parameter name")
    parameter_label: str = Field(description="Human-readable label for the chart")
    baseline_value: float = Field(description="Baseline parameter value")
    low_value: float = Field(description="Parameter value at −Δ%")
    high_value: float = Field(description="Parameter value at +Δ%")
    output_at_low: float = Field(
        description="Output metric when parameter is at low_value"
    )
    output_at_baseline: float = Field(
        description="Output metric at baseline"
    )
    output_at_high: float = Field(
        description="Output metric when parameter is at high_value"
    )
    spread: float = Field(
        description="Absolute spread = |output_at_high − output_at_low|"
    )
    unit: str = Field(description="Unit of the parameter (e.g., 'MW', '—', 'm²/m²')")


class TornadoResult(BaseModel):
    """Complete tornado chart data for one scenario.

    Bars are sorted by spread (descending) — widest bar first.
    The output metric is specified by output_metric_name.
    """
    output_metric_name: str = Field(
        description="Name of the output being measured (e.g., 'IT Load (MW)')"
    )
    output_metric_unit: str = Field(description="Unit of the output metric")
    variation_pct: float = Field(description="±% variation applied")
    bars: list[TornadoBar] = Field(
        description="Tornado bars sorted by spread (descending)"
    )
    most_influential: str = Field(
        description="Parameter with the widest spread"
    )
    least_influential: str = Field(
        description="Parameter with the narrowest spread"
    )


class BreakEvenResult(BaseModel):
    """Result of a break-even calculation.

    "What value of parameter X achieves target Y?"
    """
    parameter: str = Field(description="Parameter being solved for")
    parameter_label: str = Field(description="Human-readable label")
    target_metric: str = Field(description="Output metric name")
    target_value: float = Field(description="Desired output value")
    break_even_value: float = Field(
        description="Parameter value that achieves the target"
    )
    baseline_value: float = Field(description="Current baseline parameter value")
    change_from_baseline: float = Field(
        description="break_even_value − baseline_value"
    )
    change_pct: float = Field(
        description="Percentage change from baseline"
    )
    feasible: bool = Field(
        description=(
            "True if break-even value is physically achievable "
            "(e.g., PUE ≥ 1.0, ratios in [0, 1])"
        )
    )
    feasibility_note: str = Field(
        default="",
        description="Explanation if not feasible"
    )


# ─────────────────────────────────────────────────────────────
# Tornado Chart Computation
# ─────────────────────────────────────────────────────────────

# ── IT Load computation helpers ──
# These replicate the core power chain formulas from power.py
# in a lightweight form suitable for rapid sensitivity sweeps.
# They do NOT replace power.py — they're simplified for OAT analysis.

def _it_load_power_constrained(
    facility_power_mw: float,
    eta_chain: float,
    pue: float,
) -> float:
    """IT load in power-constrained mode (MW).

    Formula: IT_load = facility_power × η_chain / PUE
    Source: Architecture Agreement Section 3.1, Option A.
    """
    if pue <= 0:
        return 0.0
    return facility_power_mw * eta_chain / pue


def _it_load_area_constrained(
    land_area_m2: float,
    coverage_ratio: float,
    num_floors: int,
    whitespace_ratio: float,
    rack_footprint_m2: float,
    whitespace_adjustment: float,
    rack_density_kw: float,
) -> float:
    """IT load in area-constrained mode (MW).

    Formula chain (Architecture Agreement Section 3.14):
        buildable = land_area × coverage_ratio
        gross = buildable × floors
        whitespace = gross × ws_ratio
        max_racks = whitespace / rack_footprint
        effective_racks = max_racks × ws_adjustment
        IT_load = effective_racks × rack_density / 1000

    Returns IT load in MW.
    """
    buildable = land_area_m2 * coverage_ratio
    gross = buildable * num_floors
    whitespace = gross * whitespace_ratio
    max_racks = int(whitespace / rack_footprint_m2) if rack_footprint_m2 > 0 else 0
    effective = int(max_racks * whitespace_adjustment)
    return effective * rack_density_kw / 1000.0


def _facility_power_from_it(
    it_load_mw: float,
    eta_chain: float,
    pue: float,
) -> float:
    """Facility power from IT load (MW).

    Formula: facility_power = IT_load × PUE / η_chain
    Source: Architecture Agreement Section 3.1, area-constrained path.
    """
    if eta_chain <= 0:
        return 0.0
    return it_load_mw * pue / eta_chain


def _procurement_power(
    facility_power_mw: float,
    procurement_factor: float,
) -> float:
    """Procurement power (MW).

    Formula: procurement = facility_power × procurement_factor
    Source: Architecture Agreement Section 3.5.
    """
    return facility_power_mw * procurement_factor


# ── Parameter labels and units ──
PARAM_LABELS: dict[str, tuple[str, str]] = {
    "pue": ("PUE", "—"),
    "eta_chain": ("Power Chain Efficiency (η)", "—"),
    "rack_density_kw": ("Rack Density", "kW/rack"),
    "whitespace_ratio": ("Whitespace Ratio", "—"),
    "site_coverage_ratio": ("Site Coverage Ratio", "—"),
    "available_power_mw": ("Available Power", "MW"),
}


def compute_tornado(
    # ── Baseline values ──
    pue: float,
    eta_chain: float,
    rack_density_kw: float,
    whitespace_ratio: float,
    site_coverage_ratio: float,
    available_power_mw: float,
    # ── Site geometry (fixed during sensitivity) ──
    land_area_m2: float,
    num_floors: int = 1,
    rack_footprint_m2: float = 3.0,
    whitespace_adjustment: float = 1.0,
    procurement_factor: float = 2.0,
    # ── Options ──
    variation_pct: float = DEFAULT_VARIATION_PCT,
    output_metric: str = "it_load",
    power_constrained: bool = True,
) -> TornadoResult:
    """Compute tornado chart data via one-at-a-time parameter variation.

    For each parameter in SENSITIVITY_PARAMETERS, varies it by ±variation_pct
    while holding all others at baseline. Computes the output metric at each
    extreme. Returns bars sorted by spread (widest first).

    The output metric can be:
        - "it_load" — IT load in MW (default)
        - "facility_power" — total facility power in MW
        - "procurement_power" — grid capacity request in MW

    For power-constrained mode:
        IT_load = facility_power × η / PUE
        (available_power_mw determines facility_power)

    For area-constrained mode:
        IT_load = f(land, coverage, floors, ws_ratio, rack_fp, ws_adj, density)
        facility_power = IT_load × PUE / η

    Args:
        pue: Baseline PUE (from hourly engine or cooling profile).
        eta_chain: Baseline power chain efficiency.
        rack_density_kw: Baseline rack density (kW/rack).
        whitespace_ratio: Baseline whitespace ratio (0–1).
        site_coverage_ratio: Baseline site coverage ratio (0–1).
        available_power_mw: Baseline available power (MW).
        land_area_m2: Total site land area (fixed).
        num_floors: Number of active floors (fixed).
        rack_footprint_m2: Floor area per rack in m² (fixed).
        whitespace_adjustment: Cooling-type whitespace factor (fixed).
        procurement_factor: Grid sizing factor for redundancy (fixed).
        variation_pct: ±% variation to apply. Default 10%.
        output_metric: Which output to measure. Default "it_load".
        power_constrained: True = power mode, False = area mode.

    Returns:
        TornadoResult with bars sorted by spread (descending).

    Example:
        >>> result = compute_tornado(
        ...     pue=1.25, eta_chain=0.95, rack_density_kw=100,
        ...     whitespace_ratio=0.40, site_coverage_ratio=0.50,
        ...     available_power_mw=20.0, land_area_m2=25000,
        ... )
        >>> print(f"Most influential: {result.most_influential}")
        >>> for bar in result.bars:
        ...     print(f"  {bar.parameter_label}: spread={bar.spread:.3f} MW")
    """
    # ── Package baseline values ──
    baselines = {
        "pue": pue,
        "eta_chain": eta_chain,
        "rack_density_kw": rack_density_kw,
        "whitespace_ratio": whitespace_ratio,
        "site_coverage_ratio": site_coverage_ratio,
        "available_power_mw": available_power_mw,
    }

    # ── Compute output at baseline ──
    baseline_output = _compute_output(
        baselines, land_area_m2, num_floors, rack_footprint_m2,
        whitespace_adjustment, procurement_factor,
        output_metric, power_constrained,
    )

    # ── Output metric label ──
    metric_names = {
        "it_load": ("IT Load (MW)", "MW"),
        "facility_power": ("Facility Power (MW)", "MW"),
        "procurement_power": ("Procurement Power (MW)", "MW"),
    }
    metric_name, metric_unit = metric_names.get(
        output_metric, ("IT Load (MW)", "MW")
    )

    # ── Vary each parameter ──
    bars: list[TornadoBar] = []
    delta = variation_pct / 100.0

    for param in SENSITIVITY_PARAMETERS:
        # Skip available_power_mw in area-constrained mode
        # (it's not an input, it's an output)
        if param == "available_power_mw" and not power_constrained:
            continue

        # Skip area parameters in power-constrained mode if power is binding
        # (they still affect the space constraint, so we include them)

        base_val = baselines[param]
        if base_val == 0:
            continue  # Can't vary zero

        low_val = base_val * (1 - delta)
        high_val = base_val * (1 + delta)

        # Clamp ratios to valid range
        if param in ("whitespace_ratio", "site_coverage_ratio"):
            low_val = max(0.01, low_val)
            high_val = min(0.99, high_val)
        if param == "pue":
            low_val = max(1.0, low_val)  # PUE can't be below 1.0
        if param == "eta_chain":
            high_val = min(1.0, high_val)  # Efficiency can't exceed 100%

        # Compute output at low and high values
        params_low = baselines.copy()
        params_low[param] = low_val

        params_high = baselines.copy()
        params_high[param] = high_val

        output_low = _compute_output(
            params_low, land_area_m2, num_floors, rack_footprint_m2,
            whitespace_adjustment, procurement_factor,
            output_metric, power_constrained,
        )
        output_high = _compute_output(
            params_high, land_area_m2, num_floors, rack_footprint_m2,
            whitespace_adjustment, procurement_factor,
            output_metric, power_constrained,
        )

        spread = abs(output_high - output_low)

        label, unit = PARAM_LABELS.get(param, (param, ""))

        bars.append(TornadoBar(
            parameter=param,
            parameter_label=label,
            baseline_value=round(base_val, 6),
            low_value=round(low_val, 6),
            high_value=round(high_val, 6),
            output_at_low=round(output_low, 4),
            output_at_baseline=round(baseline_output, 4),
            output_at_high=round(output_high, 4),
            spread=round(spread, 4),
            unit=unit,
        ))

    # ── Sort by spread (descending) ──
    bars.sort(key=lambda b: b.spread, reverse=True)

    most = bars[0].parameter if bars else ""
    least = bars[-1].parameter if bars else ""

    return TornadoResult(
        output_metric_name=metric_name,
        output_metric_unit=metric_unit,
        variation_pct=variation_pct,
        bars=bars,
        most_influential=most,
        least_influential=least,
    )


def _compute_output(
    params: dict[str, float],
    land_area_m2: float,
    num_floors: int,
    rack_footprint_m2: float,
    whitespace_adjustment: float,
    procurement_factor: float,
    output_metric: str,
    power_constrained: bool,
) -> float:
    """Compute the output metric for a given set of parameter values.

    Supports both power-constrained and area-constrained modes.
    In power-constrained mode, also checks the space limit and
    takes the binding constraint (min of power-based and area-based IT).
    """
    pue = params["pue"]
    eta = params["eta_chain"]
    density = params["rack_density_kw"]
    ws_ratio = params["whitespace_ratio"]
    coverage = params["site_coverage_ratio"]
    avail_power = params["available_power_mw"]

    # Area-based IT load is always computed (needed for binding constraint)
    it_from_area = _it_load_area_constrained(
        land_area_m2, coverage, num_floors, ws_ratio, rack_footprint_m2,
        whitespace_adjustment, density,
    )

    if power_constrained:
        it_from_power = _it_load_power_constrained(avail_power, eta, pue)
        # Binding constraint: take the smaller
        it_load = min(it_from_power, it_from_area)
    else:
        it_load = it_from_area

    # Compute derived outputs
    facility = _facility_power_from_it(it_load, eta, pue)
    procurement = _procurement_power(facility, procurement_factor)

    if output_metric == "facility_power":
        return facility
    elif output_metric == "procurement_power":
        return procurement
    else:
        return it_load


# ─────────────────────────────────────────────────────────────
# Break-Even Analysis
# ─────────────────────────────────────────────────────────────

def compute_break_even(
    target_it_load_mw: float,
    parameter: str,
    # ── Baseline values (all others held constant) ──
    pue: float,
    eta_chain: float,
    rack_density_kw: float,
    whitespace_ratio: float,
    site_coverage_ratio: float,
    available_power_mw: float,
    # ── Fixed geometry ──
    land_area_m2: float,
    num_floors: int = 1,
    rack_footprint_m2: float = 3.0,
    whitespace_adjustment: float = 1.0,
    power_constrained: bool = True,
) -> BreakEvenResult:
    """Find the parameter value that achieves a target IT load.

    Uses direct algebra on the power chain formulas — no iteration.

    Power-constrained formulas (solve for parameter):
        IT = facility × η / PUE
        → PUE = facility × η / target_IT
        → η = target_IT × PUE / facility
        → facility (= avail_power) = target_IT × PUE / η

    Area-constrained formulas (solve for parameter):
        IT = eff_racks × density / 1000
        → density = target_IT × 1000 / eff_racks
        → eff_racks = target_IT × 1000 / density
        Then: eff_racks = int(land × coverage × floors × ws_ratio / rack_fp × ws_adj)
        → coverage = required_racks / (land × floors × ws_ratio / rack_fp × ws_adj)
        → ws_ratio = required_racks / (land × coverage × floors / rack_fp × ws_adj)

    Args:
        target_it_load_mw: Desired IT load in MW.
        parameter: Which parameter to solve for.
        (remaining args): Current baseline values.

    Returns:
        BreakEvenResult with the solved parameter value.

    Raises:
        ValueError: If parameter is not in SENSITIVITY_PARAMETERS,
                    or if the target is physically impossible.

    Example:
        >>> result = compute_break_even(
        ...     target_it_load_mw=15.0,
        ...     parameter="pue",
        ...     pue=1.25, eta_chain=0.95, rack_density_kw=100,
        ...     whitespace_ratio=0.40, site_coverage_ratio=0.50,
        ...     available_power_mw=20.0, land_area_m2=25000,
        ... )
        >>> print(f"Need PUE ≤ {result.break_even_value:.3f} for 15 MW IT")
    """
    if parameter not in SENSITIVITY_PARAMETERS:
        raise ValueError(
            f"Unknown parameter '{parameter}'. "
            f"Must be one of: {SENSITIVITY_PARAMETERS}"
        )
    if target_it_load_mw <= 0:
        raise ValueError(f"target_it_load_mw must be positive: {target_it_load_mw}")

    label, unit = PARAM_LABELS.get(parameter, (parameter, ""))
    baseline = {
        "pue": pue,
        "eta_chain": eta_chain,
        "rack_density_kw": rack_density_kw,
        "whitespace_ratio": whitespace_ratio,
        "site_coverage_ratio": site_coverage_ratio,
        "available_power_mw": available_power_mw,
    }[parameter]

    # ── Solve algebraically based on mode and parameter ──
    solved: float
    feasible = True
    note = ""

    if power_constrained and parameter in ("pue", "eta_chain", "available_power_mw"):
        # Power-constrained: IT = avail_power × η / PUE
        if parameter == "pue":
            # PUE = avail_power × η / target_IT
            if target_it_load_mw > 0:
                solved = available_power_mw * eta_chain / target_it_load_mw
            else:
                solved = float("inf")
            if solved < 1.0:
                feasible = False
                note = f"PUE {solved:.3f} is below theoretical minimum (1.0)"

        elif parameter == "eta_chain":
            # η = target_IT × PUE / avail_power
            if available_power_mw > 0:
                solved = target_it_load_mw * pue / available_power_mw
            else:
                solved = float("inf")
                feasible = False
                note = "No available power — cannot solve for η"
            if solved > 1.0:
                feasible = False
                note = f"η {solved:.3f} exceeds theoretical maximum (1.0)"

        elif parameter == "available_power_mw":
            # avail_power = target_IT × PUE / η
            if eta_chain > 0:
                solved = target_it_load_mw * pue / eta_chain
            else:
                solved = float("inf")
                feasible = False
                note = "η is zero — cannot solve for power"

    elif parameter == "rack_density_kw":
        # Both modes: IT = eff_racks × density / 1000
        # → density = target_IT × 1000 / eff_racks
        eff_racks = _effective_racks_from_geometry(
            land_area_m2, site_coverage_ratio, num_floors,
            whitespace_ratio, rack_footprint_m2, whitespace_adjustment,
        )
        if eff_racks > 0:
            solved = target_it_load_mw * 1000 / eff_racks
        else:
            solved = float("inf")
            feasible = False
            note = "No effective racks available"
        if solved < 0:
            feasible = False
            note = f"Negative density ({solved:.1f}) is not physical"

    elif parameter in ("whitespace_ratio", "site_coverage_ratio"):
        # Area path: need to find the ratio that yields enough racks
        # eff_racks_needed = target_IT × 1000 / density
        if rack_density_kw <= 0:
            solved = float("inf")
            feasible = False
            note = "Rack density is zero"
        else:
            racks_needed = target_it_load_mw * 1000 / rack_density_kw
            # eff_racks = int(land × coverage × floors × ws_ratio / rack_fp) × ws_adj
            # We need to invert for the target parameter.
            # Use a continuous approximation (drop the int()) for the break-even value.

            if parameter == "whitespace_ratio":
                # racks_needed = land × coverage × floors × ws_ratio / rack_fp × ws_adj
                # → ws_ratio = racks_needed × rack_fp / (land × coverage × floors × ws_adj)
                denominator = land_area_m2 * site_coverage_ratio * num_floors * whitespace_adjustment
                if denominator > 0:
                    solved = (racks_needed * rack_footprint_m2) / denominator
                else:
                    solved = float("inf")
                    feasible = False
                    note = "Zero buildable area"
                if solved > 1.0:
                    feasible = False
                    note = f"Whitespace ratio {solved:.3f} exceeds maximum (1.0)"
                elif solved < 0:
                    feasible = False
                    note = f"Negative ratio is not physical"

            elif parameter == "site_coverage_ratio":
                # coverage = racks_needed × rack_fp / (land × floors × ws_ratio × ws_adj)
                denominator = land_area_m2 * num_floors * whitespace_ratio * whitespace_adjustment
                if denominator > 0:
                    solved = (racks_needed * rack_footprint_m2) / denominator
                else:
                    solved = float("inf")
                    feasible = False
                    note = "Zero land or whitespace"
                if solved > 1.0:
                    feasible = False
                    note = f"Coverage ratio {solved:.3f} exceeds maximum (1.0)"
                elif solved < 0:
                    feasible = False
                    note = f"Negative ratio is not physical"

    elif parameter == "available_power_mw" and not power_constrained:
        # In area mode, solve for the power needed to support the IT load
        # facility = target_IT × PUE / η
        if eta_chain > 0:
            solved = target_it_load_mw * pue / eta_chain
        else:
            solved = float("inf")
            feasible = False
            note = "η is zero"
    else:
        # Fallback: parameter not directly solvable in this mode
        # Use numerical search (bisection) as a safety net
        solved_candidate = _bisect_solve(
            target_it_load_mw, parameter,
            pue, eta_chain, rack_density_kw,
            whitespace_ratio, site_coverage_ratio, available_power_mw,
            land_area_m2, num_floors, rack_footprint_m2,
            whitespace_adjustment, 2.0, power_constrained,
        )
        if solved_candidate is None:
            solved = float("nan")
            feasible = False
            note = "Could not find break-even value within search bounds"
        else:
            solved = solved_candidate

    # ── Compute change from baseline ──
    change = solved - baseline
    change_pct = (change / baseline * 100) if baseline != 0 else 0.0

    return BreakEvenResult(
        parameter=parameter,
        parameter_label=label,
        target_metric="IT Load (MW)",
        target_value=target_it_load_mw,
        break_even_value=round(solved, 4),
        baseline_value=round(baseline, 4),
        change_from_baseline=round(change, 4),
        change_pct=round(change_pct, 2),
        feasible=feasible,
        feasibility_note=note,
    )


def _effective_racks_from_geometry(
    land_area_m2: float,
    coverage_ratio: float,
    num_floors: int,
    whitespace_ratio: float,
    rack_footprint_m2: float,
    whitespace_adjustment: float,
) -> int:
    """Compute effective racks from site geometry parameters.

    Pure geometry — same chain as space.py but inline for sensitivity.
    """
    buildable = land_area_m2 * coverage_ratio
    gross = buildable * num_floors
    whitespace = gross * whitespace_ratio
    max_racks = int(whitespace / rack_footprint_m2) if rack_footprint_m2 > 0 else 0
    return int(max_racks * whitespace_adjustment)


def _bisect_solve(
    target: float,
    parameter: str,
    pue: float,
    eta_chain: float,
    rack_density_kw: float,
    whitespace_ratio: float,
    site_coverage_ratio: float,
    available_power_mw: float,
    land_area_m2: float,
    num_floors: int,
    rack_footprint_m2: float,
    whitespace_adjustment: float,
    procurement_factor: float,
    power_constrained: bool,
    max_iter: int = 50,
    tol: float = 0.001,
) -> Optional[float]:
    """Bisection fallback for parameters not solvable algebraically.

    Searches for the parameter value where IT load ≈ target.
    Returns None if no solution found within bounds.
    """
    # Define search bounds per parameter
    bounds: dict[str, tuple[float, float]] = {
        "pue": (1.0, 3.0),
        "eta_chain": (0.5, 1.0),
        "rack_density_kw": (1.0, 300.0),
        "whitespace_ratio": (0.1, 0.8),
        "site_coverage_ratio": (0.1, 0.9),
        "available_power_mw": (0.1, 500.0),
    }

    lo, hi = bounds.get(parameter, (0.01, 1000.0))

    def _evaluate(val: float) -> float:
        params = {
            "pue": pue,
            "eta_chain": eta_chain,
            "rack_density_kw": rack_density_kw,
            "whitespace_ratio": whitespace_ratio,
            "site_coverage_ratio": site_coverage_ratio,
            "available_power_mw": available_power_mw,
        }
        params[parameter] = val
        return _compute_output(
            params, land_area_m2, num_floors, rack_footprint_m2,
            whitespace_adjustment, procurement_factor,
            "it_load", power_constrained,
        )

    # Check if target is within range
    f_lo = _evaluate(lo)
    f_hi = _evaluate(hi)

    # Determine if function is increasing or decreasing w.r.t. parameter
    if f_lo > f_hi:
        # Decreasing (e.g., PUE: higher PUE → lower IT)
        if target > f_lo or target < f_hi:
            return None
    else:
        # Increasing (e.g., power: higher power → higher IT)
        if target < f_lo or target > f_hi:
            return None

    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = _evaluate(mid)

        if abs(f_mid - target) < tol:
            return mid

        # Determine which half contains the target
        if (f_mid < target) == (f_lo < f_hi):
            lo = mid
        else:
            hi = mid

    return (lo + hi) / 2  # Best approximation
