"""
DC Feasibility Tool v4 — Power Chain Calculation
==================================================
Computes IT load, facility power, procurement power, and RAG status.

Two modes:
    Power-Constrained (STMG available):
        Power → IT Load → compare with space → binding constraint
    Area-Constrained (no STMG):
        Space → IT Load → compute required facility and procurement power

The power input mode (operational vs. grid reservation) determines
how the STMG value is interpreted. See Architecture Agreement Section 3.5.

Redundancy effects (Section 3.6):
    1. eta_chain_derate — small UPS efficiency penalty → tiny PUE increase
    2. procurement_factor — grid capacity sizing → does NOT affect PUE

RAG Status (Section 3.17): 4-level system (RED/AMBER/GREEN/BLUE).

Reference: Architecture Agreement v2.0, Sections 3.1, 3.5, 3.6, 3.17
"""

from engine.models import (
    Site,
    Scenario,
    SpaceResult,
    PowerResult,
    RAGStatus,
    PowerInputMode,
    CoolingType,
)
from engine.assumptions import (
    evaluate_compatibility,
    get_rack_density_kw,
)
from engine.assumption_overrides import (
    get_effective_cooling_profile,
    get_effective_redundancy_profile,
)
from engine.space import compute_space, compute_it_load_from_space


def _dedupe_reasons(reasons: list[str]) -> list[str]:
    """Preserve reason order while removing duplicates."""
    seen: set[str] = set()
    unique: list[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            unique.append(reason)
    return unique


def _get_eta_chain(redundancy_level: str, preset_key: str | None = None) -> float:
    """Get the power chain efficiency for a redundancy level.

    The eta_chain_derate represents UPS partial-load efficiency.
    In 2N, each UPS carries 50% load → slightly less efficient
    than at full load. This is a SMALL effect (0.5–1% on PUE).

    Source: Uptime Institute Tier Standard; IEEE 3006.7

    Args:
        redundancy_level: Key matching RedundancyLevel enum value
                          (e.g., "2N", "N+1")

    Returns:
        Power chain efficiency (0 < η ≤ 1).
    """
    profile = get_effective_redundancy_profile(redundancy_level, preset_key)
    return profile["eta_chain_derate"]


def _get_procurement_factor(
    redundancy_level: str,
    preset_key: str | None = None,
) -> float:
    """Get the procurement (grid sizing) factor for a redundancy level.

    This is a SIZING multiplier only. It affects:
    - Equipment capacity (transformers, UPS, switchgear)
    - Grid connection request (STMG)
    - Infrastructure footprint

    It does NOT affect PUE, operational power, or IT capacity.

    Source: Uptime Institute Tier Standard: Topology (2018)

    Args:
        redundancy_level: Key matching RedundancyLevel enum value

    Returns:
        Procurement factor (≥ 1.0).
    """
    profile = get_effective_redundancy_profile(redundancy_level, preset_key)
    return profile["procurement_factor"]


def _get_pue(scenario: Scenario) -> float:
    """Get the PUE value to use for static calculation.

    Priority:
    1. User override (scenario.pue_override) — if set, always use it
    2. Cooling profile typical PUE — default for feasibility

    When weather data is available, the hourly engine replaces this
    with an energy-weighted annual PUE. This function is only for
    the static (no-weather) calculation path.

    Args:
        scenario: The scenario being evaluated.

    Returns:
        PUE value (> 1.0).
    """
    if scenario.pue_override is not None:
        return scenario.pue_override

    cooling_profile = get_effective_cooling_profile(
        scenario.cooling_type.value,
        scenario.assumption_override_preset_key,
    )
    return cooling_profile["pue_typical"]


def compute_power_constrained(
    site: Site,
    scenario: Scenario,
    space: SpaceResult,
) -> PowerResult:
    """Power-constrained mode: Power is known → compute IT load.

    Two sub-modes based on power_input_mode (Architecture Agreement 3.1):

    Option A — OPERATIONAL:
        facility_power = entered value
        IT load = facility_power × η_chain / PUE
        procurement = facility_power × procurement_factor

    Option B — GRID_RESERVATION:
        procurement = entered value
        facility_power = entered value / procurement_factor
        IT load = facility_power × η_chain / PUE

    Then compare IT load from power with IT load from space.
    Binding constraint = whichever gives fewer racks.

    Args:
        site: Validated Site with available_power_mw > 0.
        scenario: Scenario with load type, cooling, redundancy.
        space: Pre-computed SpaceResult.

    Returns:
        PowerResult with all power values and RAG status.
    """
    eta_chain = _get_eta_chain(
        scenario.redundancy.value,
        scenario.assumption_override_preset_key,
    )
    procurement_factor = _get_procurement_factor(
        scenario.redundancy.value,
        scenario.assumption_override_preset_key,
    )
    pue = _get_pue(scenario)
    rack_density_kw = get_rack_density_kw(
        scenario.load_type.value, scenario.density_scenario.value
    )

    # ── Determine facility power based on input mode ──
    if site.power_input_mode == PowerInputMode.OPERATIONAL:
        # Option A: entered value IS the operational facility power
        facility_power_mw = site.available_power_mw
        procurement_power_mw = facility_power_mw * procurement_factor
    else:
        # Option B: entered value IS the total grid reservation
        procurement_power_mw = site.available_power_mw
        facility_power_mw = site.available_power_mw / procurement_factor

    # ── Compute IT load from power ──
    # IT load = facility_power × η_chain / PUE
    # η_chain accounts for electrical conversion losses (transformer, UPS, PDU)
    # PUE accounts for all overhead (cooling, fans, lighting, misc)
    it_load_from_power_mw = facility_power_mw * eta_chain / pue

    # ── Compute IT load from space ──
    it_load_from_space_mw = compute_it_load_from_space(
        space.effective_racks, rack_density_kw
    )

    # ── Determine binding constraint ──
    racks_by_power = int(it_load_from_power_mw * 1000 / rack_density_kw)

    if racks_by_power <= space.effective_racks:
        # Power is the bottleneck — space has room to spare
        binding = "POWER"
        racks_deployed = racks_by_power
        it_load_mw = it_load_from_power_mw
    else:
        # Space is the bottleneck — power has headroom
        binding = "AREA"
        racks_deployed = space.effective_racks
        it_load_mw = it_load_from_space_mw

    # ── Power headroom (only meaningful when power-constrained) ──
    # How much of the facility power budget is unused?
    actual_facility_needed_mw = it_load_mw * pue / eta_chain
    power_headroom_mw = round(facility_power_mw - actual_facility_needed_mw, 3)

    # ── RAG status evaluation ──
    rag_status, rag_reasons = _evaluate_rag(
        site=site,
        scenario=scenario,
        space=space,
        it_load_mw=it_load_mw,
        facility_power_mw=facility_power_mw,
        pue=pue,
        racks_deployed=racks_deployed,
        rack_density_kw=rack_density_kw,
        binding=binding,
        power_headroom_mw=power_headroom_mw,
    )

    return PowerResult(
        it_load_mw=round(it_load_mw, 3),
        facility_power_mw=round(facility_power_mw, 3),
        procurement_power_mw=round(procurement_power_mw, 3),
        racks_by_power=racks_by_power,
        racks_deployed=racks_deployed,
        rack_density_kw=rack_density_kw,
        binding_constraint=binding,
        power_headroom_mw=round(power_headroom_mw, 3),
        eta_chain=eta_chain,
        pue_used=pue,
        procurement_factor=procurement_factor,
        power_input_mode=site.power_input_mode,
        rag_status=rag_status,
        rag_reasons=rag_reasons,
    )


def compute_area_constrained(
    site: Site,
    scenario: Scenario,
    space: SpaceResult,
) -> PowerResult:
    """Area-constrained mode: Space is known → compute required power.

    IT load is determined entirely by how many racks fit.
    Then we calculate how much power to request from the grid.

    Calculation:
        IT load (MW) = effective_racks × rack_density_kw / 1000
        Facility power = IT load × PUE / η_chain
        Procurement power = facility_power × procurement_factor

    Args:
        site: Validated Site with available_power_mw == 0 or not confirmed.
        scenario: Scenario with load type, cooling, redundancy.
        space: Pre-computed SpaceResult.

    Returns:
        PowerResult with required power values and RAG status.
    """
    eta_chain = _get_eta_chain(
        scenario.redundancy.value,
        scenario.assumption_override_preset_key,
    )
    procurement_factor = _get_procurement_factor(
        scenario.redundancy.value,
        scenario.assumption_override_preset_key,
    )
    pue = _get_pue(scenario)
    rack_density_kw = get_rack_density_kw(
        scenario.load_type.value, scenario.density_scenario.value
    )

    # ── IT load from space (only path in area-constrained mode) ──
    it_load_mw = compute_it_load_from_space(space.effective_racks, rack_density_kw)

    # ── Required facility and procurement power ──
    facility_power_mw = it_load_mw * pue / eta_chain
    procurement_power_mw = facility_power_mw * procurement_factor

    # ── RAG status evaluation ──
    rag_status, rag_reasons = _evaluate_rag(
        site=site,
        scenario=scenario,
        space=space,
        it_load_mw=it_load_mw,
        facility_power_mw=facility_power_mw,
        pue=pue,
        racks_deployed=space.effective_racks,
        rack_density_kw=rack_density_kw,
        binding="AREA",
        power_headroom_mw=None,
    )

    return PowerResult(
        it_load_mw=round(it_load_mw, 3),
        facility_power_mw=round(facility_power_mw, 3),
        procurement_power_mw=round(procurement_power_mw, 3),
        racks_by_power=None,  # Not applicable in area mode
        racks_deployed=space.effective_racks,
        rack_density_kw=rack_density_kw,
        binding_constraint="AREA",
        power_headroom_mw=None,
        eta_chain=eta_chain,
        pue_used=pue,
        procurement_factor=procurement_factor,
        power_input_mode=site.power_input_mode,
        rag_status=rag_status,
        rag_reasons=rag_reasons,
    )


def solve(
    site: Site,
    scenario: Scenario,
    cooling_type_for_space: CoolingType | None = None,
) -> tuple[SpaceResult, PowerResult]:
    """Main entry point: run space + power calculation for a site/scenario.

    Automatically selects power-constrained or area-constrained mode
    based on whether the site has confirmed power availability.

    Args:
        site: The candidate site.
        scenario: The scenario to evaluate.
        cooling_type_for_space: Cooling type for whitespace adjustment.
                                If None, uses scenario.cooling_type.

    Returns:
        Tuple of (SpaceResult, PowerResult).

    Example:
        >>> from engine.models import Site, Scenario, LoadType, CoolingType
        >>> site = Site(name="Test", land_area_m2=25000, available_power_mw=20.0, power_confirmed=True)
        >>> scenario = Scenario(load_type=LoadType.AI_GPU, cooling_type=CoolingType.DLC)
        >>> space, power = solve(site, scenario)
        >>> print(f"IT Load: {power.it_load_mw} MW, Binding: {power.binding_constraint}")
    """
    # Use scenario cooling type for space adjustment if not explicitly provided
    ct = cooling_type_for_space if cooling_type_for_space is not None else scenario.cooling_type

    # Step 1: Compute space (always runs first)
    space = compute_space(site, cooling_type=ct)

    # Step 2: Select mode and compute power
    if site.power_confirmed and site.available_power_mw > 0:
        power = compute_power_constrained(site, scenario, space)
    else:
        power = compute_area_constrained(site, scenario, space)

    return space, power


def apply_hourly_rag_adjustments(
    power: PowerResult,
    scenario: Scenario,
    overtemperature_hours: int | None,
) -> PowerResult:
    """Downgrade fragile topologies using representative-year hourly results."""
    if overtemperature_hours is None:
        return power

    if scenario.cooling_type != CoolingType.DRY_COOLER:
        return power

    status = power.rag_status
    reasons = list(power.rag_reasons)

    if overtemperature_hours > 200:
        status = RAGStatus.RED
        reasons.insert(
            0,
            "Representative-year hourly simulation exceeds the dry-cooler "
            f"temperature limit for {overtemperature_hours} hours, so a "
            "chiller-less design is not robust enough as a firm basis.",
        )
    elif overtemperature_hours > 0 and status != RAGStatus.RED:
        if status in (RAGStatus.BLUE, RAGStatus.GREEN):
            status = RAGStatus.AMBER
        reasons.insert(
            0,
            "Representative-year hourly simulation exceeds the dry-cooler "
            f"temperature limit for {overtemperature_hours} hours, so the "
            "topology needs trim/mechanical backup and cannot be treated as a "
            "default BLUE design.",
        )

    if status == power.rag_status and reasons == power.rag_reasons:
        return power

    return power.model_copy(
        update={
            "rag_status": status,
            "rag_reasons": _dedupe_reasons(reasons),
        }
    )


# ─────────────────────────────────────────────────────────────
# RAG Status Evaluation
# ─────────────────────────────────────────────────────────────
# Source: Architecture Agreement Section 3.17
# Evaluation order: RED first → AMBER → BLUE → GREEN

def _evaluate_rag(
    site: Site,
    scenario: Scenario,
    space: SpaceResult,
    it_load_mw: float,
    facility_power_mw: float,
    pue: float,
    racks_deployed: int,
    rack_density_kw: float,
    binding: str,
    power_headroom_mw: float | None,
) -> tuple[RAGStatus, list[str]]:
    """Evaluate the 4-level RAG status for a scenario.

    Checks conditions in order: RED → AMBER → BLUE → GREEN.
    If any RED condition triggers, status is RED immediately.
    If any AMBER triggers (no RED), status is AMBER.
    If BLUE criteria are met (no RED/AMBER), status is BLUE.
    Otherwise GREEN.

    Returns:
        Tuple of (RAGStatus, list of reason strings).
    """
    reasons: list[str] = []

    # ── Check compatibility first ──
    compatibility_status, compatibility_reasons = evaluate_compatibility(
        scenario.load_type.value,
        scenario.cooling_type.value,
        density_scenario=scenario.density_scenario.value,
        rack_density_kw=rack_density_kw,
    )
    compatible = compatibility_status != "incompatible"

    # ══════════════════════════════════════════════════════════
    # RED conditions — Fatal (scenario not viable)
    # ══════════════════════════════════════════════════════════

    red_reasons: list[str] = []

    # Incompatible cooling + load type combination
    if not compatible:
        red_reasons.extend(compatibility_reasons)

    # IT load is negative or zero (physically impossible)
    if it_load_mw <= 0:
        red_reasons.append(f"IT load is {it_load_mw} MW — not viable")

    # Building height insufficient for even 1 floor
    if (
        site.max_building_height_m is not None
        and site.max_building_height_m > 0
        and site.max_building_height_m < site.floor_to_floor_height_m
    ):
        red_reasons.append(
            f"Building height {site.max_building_height_m}m is less than "
            f"one floor ({site.floor_to_floor_height_m}m)"
        )

    if red_reasons:
        return RAGStatus.RED, red_reasons

    # ══════════════════════════════════════════════════════════
    # AMBER conditions — Warning (viable but constrained)
    # ══════════════════════════════════════════════════════════

    amber_reasons: list[str] = []

    if compatibility_status == "conditional":
        amber_reasons.extend(compatibility_reasons)

    # Area is the binding constraint (power headroom exists but no space)
    if binding == "AREA" and site.power_confirmed and site.available_power_mw > 0:
        amber_reasons.append("Area is the binding constraint — power headroom exists but no space")

    # Power headroom very small
    if power_headroom_mw is not None and 0 < power_headroom_mw < 1.0:
        amber_reasons.append(
            f"Power headroom only {power_headroom_mw:.2f} MW — nearly maxed out"
        )

    # IT load very small
    if 0 < it_load_mw < 1.0:
        amber_reasons.append(
            f"IT load only {it_load_mw:.2f} MW — may not be economically viable"
        )

    # Very few racks
    if racks_deployed < 50:
        amber_reasons.append(
            f"Only {racks_deployed} racks — minimum viable data center questionable"
        )

    # Tight site
    if space.site_coverage_used > 0.70:
        amber_reasons.append(
            f"Site coverage ratio {space.site_coverage_used:.0%} — "
            f"tight site, limited outdoor equipment space"
        )

    # Gray space sufficiency check (Phase 1.2)
    # For Tier III facilities, gray space ratio should be ≥ 0.55.
    # If whitespace_ratio > 0.45 the gray space may be too small for
    # support infrastructure (power rooms, cooling plant, corridors).
    if space.gray_space_ratio < 0.55:
        amber_reasons.append(
            f"Gray space ratio {space.gray_space_ratio:.0%} "
            f"(< 55% threshold) — may be insufficient for support infrastructure"
        )

    if amber_reasons:
        return RAGStatus.AMBER, amber_reasons

    # ══════════════════════════════════════════════════════════
    # BLUE conditions — Excellent (best scenarios)
    # Must meet at least 2 of the criteria below.
    # ══════════════════════════════════════════════════════════

    blue_criteria_met = 0
    blue_details: list[str] = []

    # PUE < 1.20
    if pue < 1.20:
        blue_criteria_met += 1
        blue_details.append(f"Excellent PUE: {pue:.2f}")

    # Good utilization ratio (IT / facility > 0.70)
    if facility_power_mw > 0:
        utilization = it_load_mw / facility_power_mw
        if utilization > 0.70:
            blue_criteria_met += 1
            blue_details.append(f"High utilization: {utilization:.0%}")

    # Power headroom > 5 MW (room for growth)
    if power_headroom_mw is not None and power_headroom_mw > 5.0:
        blue_criteria_met += 1
        blue_details.append(f"Power headroom: {power_headroom_mw:.1f} MW")

    # Free cooling eligibility (proxy — actual hours computed in Phase 2)
    if blue_criteria_met >= 2:
        return RAGStatus.BLUE, blue_details

    # ══════════════════════════════════════════════════════════
    # GREEN — Good (all checks pass, not exceptional)
    # ══════════════════════════════════════════════════════════

    return RAGStatus.GREEN, ["All checks pass — scenario viable"]
