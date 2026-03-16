"""
DC Feasibility Tool v4 — Space Calculation Module
===================================================
Pure geometry: how many racks physically fit in the building.

This module has ZERO dependency on power, PUE, or cooling efficiency.
It answers one question: given land area, building constraints, and
cooling type, how many racks can be deployed?

Calculation chain:
    Land Area
    → Buildable Footprint (via ratio or absolute)
    → × Active Floors
    → = Gross Building Area
    → × Whitespace Ratio
    → = IT Hall Area (m²)
    → ÷ Rack Footprint (m²/rack)
    → = Max Racks by Space
    → × Cooling Whitespace Adjustment Factor
    → = Effective Racks (what you can actually deploy)

Sources:
    - Site coverage ratio: Italian 'indice di copertura' Zone D (0.30–0.60)
    - Whitespace ratio: Uptime Institute Tier III/IV (40–45%), DCD Intelligence (35–45%)
    - Rack footprint: ASHRAE TC 9.9, Thermal Guidelines for Data Processing Environments
    - Floor height: ASHRAE TC 9.9 minimum 4.0m
    - Cooling adjustment factors: Architecture Agreement Section 3.15

Reference: Architecture Agreement v2.0, Sections 3.14–3.15
"""

import math
from engine.models import Site, SpaceResult, CoolingType
from engine.assumptions import COOLING_PROFILES


def compute_space(site: Site, cooling_type: CoolingType | None = None) -> SpaceResult:
    """Compute site geometry and rack capacity.

    This is the first calculation in every scenario. It determines
    the physical constraint: how many racks fit in the building.

    Args:
        site: A validated Site model with all geometry fields.
        cooling_type: Optional cooling type for whitespace adjustment.
                      If None, no adjustment is applied (factor = 1.0).

    Returns:
        SpaceResult with all derived geometry values and rack counts.

    Example:
        >>> from engine.models import Site, CoolingType
        >>> site = Site(name="Test", land_area_m2=25000)
        >>> result = compute_space(site, CoolingType.AIR_CHILLER_ECON)
        >>> print(f"Effective racks: {result.effective_racks}")
    """

    # ── Step 1: Buildable footprint ──
    # Two modes per Architecture Agreement Section 3.14:
    #   RATIO: buildable = land_area × site_coverage_ratio
    #   ABSOLUTE: buildable = explicit value from planning permission
    if site.buildable_area_mode.value == "absolute" and site.buildable_area_m2 is not None:
        buildable_footprint_m2 = site.buildable_area_m2
    else:
        buildable_footprint_m2 = site.land_area_m2 * site.site_coverage_ratio

    # ── Step 2: Determine number of active floors ──
    # If max building height is specified, derive floors from height.
    # Otherwise, use the user-specified num_floors.
    max_total_floors = None
    if site.max_building_height_m is not None and site.max_building_height_m > 0:
        # How many floors fit within the height limit?
        derived_floors = int(site.max_building_height_m / site.floor_to_floor_height_m)
        max_total_floors = max(1, derived_floors)
        # Use the smaller of derived floors and user-specified floors
        # (user might want fewer floors than the height allows)
        active_floors = max(1, min(max_total_floors, site.num_floors))
    else:
        active_floors = site.num_floors

    # ── Step 3: Gross building area ──
    # Total building area across all active floors.
    # Each floor has the same footprint (simplification for feasibility).
    gross_building_area_m2 = buildable_footprint_m2 * active_floors

    # ── Step 4: IT whitespace area ──
    # The portion of the building dedicated to IT equipment.
    # The rest is power rooms, cooling plant, corridors, offices.
    # Source: Uptime Institute Tier III/IV: 40–45% typical.
    it_whitespace_m2 = gross_building_area_m2 * site.whitespace_ratio

    # Support/M&E area is the remainder
    support_area_m2 = gross_building_area_m2 - it_whitespace_m2

    # ── Step 5: Maximum racks by space ──
    # Each rack needs rack_footprint_m2 of floor area (includes aisles).
    # Source: ASHRAE TC 9.9 — standard 42U rack + hot/cold aisle = 2.5–3.5 m²
    max_racks_by_space = int(it_whitespace_m2 / site.rack_footprint_m2)

    # ── Step 6: Apply cooling whitespace adjustment ──
    # Different cooling types consume different amounts of IT hall space.
    # Source: Architecture Agreement Section 3.15
    #   CRAC: 0.92 (floor-standing units take ~8%)
    #   DLC:  0.92 (in-row CDUs take ~1 per 12 racks)
    #   Immersion: 0.85 (tank layout wider, needs service access)
    #   Others: 1.00 (equipment in separate plant rooms)
    if cooling_type is not None:
        cooling_profile = COOLING_PROFILES[cooling_type.value]
        whitespace_adjustment = cooling_profile["whitespace_adjustment_factor"]
    else:
        whitespace_adjustment = 1.0

    effective_racks = int(max_racks_by_space * whitespace_adjustment)

    # ── Step 7: Expansion floors ──
    # If the user specified expansion floors, compute their capacity too.
    # These are NOT included in the active deployment — they represent
    # future phases that can be built out later.
    expansion_floors = site.num_expansion_floors
    if max_total_floors is not None:
        remaining_height_floors = max(0, max_total_floors - active_floors)
        expansion_floors = min(expansion_floors, remaining_height_floors)
    expansion_whitespace_m2 = 0.0
    expansion_racks = 0

    if expansion_floors > 0:
        expansion_gross = buildable_footprint_m2 * expansion_floors
        expansion_whitespace_m2 = expansion_gross * site.whitespace_ratio
        expansion_racks_raw = int(expansion_whitespace_m2 / site.rack_footprint_m2)
        expansion_racks = int(expansion_racks_raw * whitespace_adjustment)

    # ── Build and return result ──
    return SpaceResult(
        buildable_footprint_m2=round(buildable_footprint_m2, 1),
        gross_building_area_m2=round(gross_building_area_m2, 1),
        it_whitespace_m2=round(it_whitespace_m2, 1),
        support_area_m2=round(support_area_m2, 1),
        max_racks_by_space=max_racks_by_space,
        effective_racks=effective_racks,
        whitespace_adjustment_factor=whitespace_adjustment,
        site_coverage_used=site.site_coverage_ratio,
        whitespace_ratio_used=site.whitespace_ratio,
        rack_footprint_used=site.rack_footprint_m2,
        active_floors=active_floors,
        floor_to_floor_height_used=site.floor_to_floor_height_m,
        expansion_floors=expansion_floors,
        expansion_whitespace_m2=round(expansion_whitespace_m2, 1),
        expansion_racks=expansion_racks,
    )


def compute_it_load_from_space(
    effective_racks: int,
    rack_density_kw: float,
) -> float:
    """Convert rack count to IT load in MW.

    This is the area-constrained path: we know how many racks fit,
    and each rack has a known power density → total IT load.

    Args:
        effective_racks: Number of deployable racks (after cooling adjustment).
        rack_density_kw: Power per rack in kW (from LOAD_PROFILES).

    Returns:
        IT load in MW.

    Example:
        >>> compute_it_load_from_space(1666, 7.0)  # Standard colo
        11.662
    """
    return round(effective_racks * rack_density_kw / 1000.0, 3)
