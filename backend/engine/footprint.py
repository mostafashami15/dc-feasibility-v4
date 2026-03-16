"""
DC Feasibility Tool v4 — Infrastructure Footprint Calculation
==============================================================
Computes the physical area consumed by infrastructure equipment
that sits OUTSIDE the data center building (or on its roof).

Five infrastructure elements:
    1. Cooling equipment (roof) — condensers/dry coolers, sized by heat rejection
    2. Backup power (ground)   — gensets/fuel cells, sized by procurement power
    3. Transformers (ground)    — HV/MV step-down, sized by procurement power
    4. Substation (ground)      — MV switchgear, sized by procurement power
    5. Fit check               — does everything fit on the site?

Key sizing principle:
    - Cooling equipment is sized by FACILITY power (≈ total heat rejection).
      All electricity entering the building becomes heat that must be rejected.
      Source: first law of thermodynamics; standard HVAC sizing practice.
    - Backup power, transformers, and substation are sized by PROCUREMENT power,
      because these components must handle the full redundant capacity.
      Source: Uptime Institute Tier Standard: Topology (2018).

Reference: Architecture Agreement v3.0, Sections 3.8, 3.11
"""

import math
from typing import Optional
from pydantic import BaseModel, Field

from engine.models import BackupPowerType, RAGStatus
from engine.assumptions import FOOTPRINT, BACKUP_POWER


# ─────────────────────────────────────────────────────────────
# Result Models
# ─────────────────────────────────────────────────────────────

class FootprintElement(BaseModel):
    """Detail for one infrastructure element's footprint.

    Tracks the element name, area consumed, sizing basis, and
    whether it sits on the ground or the roof. This breakdown
    appears in the detailed technical report.
    """
    name: str = Field(description="Element name (e.g., 'Cooling Equipment')")
    area_m2: float = Field(description="Total footprint in m²")
    location: str = Field(description="'ground' or 'roof'")
    sizing_basis_kw: float = Field(
        description="Power basis used for sizing (facility kW or procurement kW)"
    )
    m2_per_kw_used: float = Field(
        description="Footprint factor applied (m²/kW)"
    )
    num_units: Optional[int] = Field(
        default=None,
        description="Number of discrete units (for backup power)"
    )
    unit_size_kw: Optional[float] = Field(
        default=None,
        description="Size per unit in kW (for backup power)"
    )
    source: str = Field(description="Source citation for the footprint factor")


class FootprintResult(BaseModel):
    """Complete infrastructure footprint analysis for one scenario.

    Separates ground-level and roof-level equipment, checks whether
    everything fits on the site, and provides a utilization ratio
    for the available outdoor area.
    """

    # ── Per-element breakdown ──
    elements: list[FootprintElement] = Field(
        description="Detailed breakdown per infrastructure element"
    )

    # ── Aggregated areas ──
    total_ground_m2: float = Field(
        description="Total ground-level infrastructure footprint (m²)"
    )
    total_roof_m2: float = Field(
        description="Total roof-level infrastructure footprint (m²)"
    )
    total_infrastructure_m2: float = Field(
        description="Total infrastructure footprint (ground + roof) (m²)"
    )

    # ── Site fit analysis ──
    available_outdoor_m2: float = Field(
        description="Available ground area outside the building (m²)"
    )
    building_roof_m2: float = Field(
        description="Building roof area available for equipment (m²)"
    )
    ground_utilization_ratio: float = Field(
        description=(
            "Ground equipment / available outdoor area. "
            ">1.0 means equipment does NOT fit."
        )
    )
    roof_utilization_ratio: float = Field(
        description=(
            "Roof equipment / building roof area. "
            ">1.0 means equipment does NOT fit."
        )
    )
    ground_fits: bool = Field(
        description="True if all ground-level equipment fits in available outdoor area"
    )
    roof_fits: bool = Field(
        description="True if all roof equipment fits on the building roof"
    )
    all_fits: bool = Field(
        description="True if both ground and roof equipment fit"
    )

    # ── Backup power details ──
    backup_power_type: str = Field(description="Backup power technology used")
    backup_num_units: int = Field(description="Number of backup power units")
    backup_unit_size_kw: float = Field(description="Size per backup unit (kW)")


# ─────────────────────────────────────────────────────────────
# Main Calculation
# ─────────────────────────────────────────────────────────────

def compute_footprint(
    facility_power_mw: float,
    procurement_power_mw: float,
    buildable_footprint_m2: float,
    land_area_m2: float,
    backup_power_type: BackupPowerType = BackupPowerType.DIESEL_GENSET,
    cooling_m2_per_kw_override: Optional[float] = None,
) -> FootprintResult:
    """Compute infrastructure footprint and site fit analysis.

    This function takes pre-computed power values from power.py and
    calculates the physical area needed for all infrastructure equipment.
    It does NOT recompute any power values — it only consumes them.

    Args:
        facility_power_mw:
            Total facility power in MW (from power.py).
            Used as the heat rejection basis for cooling equipment sizing.
            Rationale: all electricity → heat → must be rejected.
            Source: standard HVAC sizing practice (ASHRAE Handbook — Fundamentals).

        procurement_power_mw:
            Grid capacity in MW (from power.py).
            Used for backup power, transformers, and substation sizing.
            Source: Uptime Institute Tier Standard — equipment must handle
            full redundant capacity.

        buildable_footprint_m2:
            Building ground-floor footprint in m² (from space.py).
            Used to compute available outdoor area and roof capacity.

        land_area_m2:
            Total site land area in m².

        backup_power_type:
            Which backup power technology to size.
            Default: Diesel Genset. Source: Architecture Agreement Section 3.8.

        cooling_m2_per_kw_override:
            Optional override for cooling footprint factor (m²/kW).
            If None, uses FOOTPRINT["cooling_skid_m2_per_kw_rejected"]["default"].

    Returns:
        FootprintResult with per-element breakdown and site fit analysis.

    Raises:
        ValueError: If facility_power_mw or procurement_power_mw is negative.

    Example:
        >>> result = compute_footprint(
        ...     facility_power_mw=20.0,
        ...     procurement_power_mw=40.0,
        ...     buildable_footprint_m2=5000.0,
        ...     land_area_m2=12000.0,
        ...     backup_power_type=BackupPowerType.DIESEL_GENSET,
        ... )
        >>> print(f"Ground: {result.total_ground_m2:.0f} m², Fits: {result.ground_fits}")
    """
    # ── Input validation ──
    if facility_power_mw < 0:
        raise ValueError(f"facility_power_mw cannot be negative: {facility_power_mw}")
    if procurement_power_mw < 0:
        raise ValueError(f"procurement_power_mw cannot be negative: {procurement_power_mw}")

    # Convert MW → kW for all footprint calculations
    facility_power_kw = facility_power_mw * 1000
    procurement_power_kw = procurement_power_mw * 1000

    elements: list[FootprintElement] = []

    # ══════════════════════════════════════════════════════════
    # 1. COOLING EQUIPMENT (roof-mounted)
    # ══════════════════════════════════════════════════════════
    # Heat rejection load ≈ facility power.
    # All electricity entering the building is converted to heat:
    #   IT load → servers → heat
    #   Electrical losses (UPS, PDU) → heat
    #   Fan/pump motors → heat
    #   Misc loads (lighting, BMS) → heat
    # The cooling plant must reject ALL of this to the outdoors.
    #
    # At the condenser side, rejection = Q_evap + W_compressor,
    # which is slightly MORE than facility power. However, the
    # footprint factor from Carrier/Trane selection guides already
    # accounts for this in their m²/kW ratings.
    #
    # Source: Carrier/Trane condenser selection guides.
    # Architecture Agreement Section 3.11.

    cooling_fp = FOOTPRINT["cooling_skid_m2_per_kw_rejected"]
    cooling_m2_per_kw = (
        cooling_m2_per_kw_override
        if cooling_m2_per_kw_override is not None
        else cooling_fp["default"]
    )

    cooling_area_m2 = facility_power_kw * cooling_m2_per_kw

    elements.append(FootprintElement(
        name="Cooling Equipment (Condensers / Dry Coolers)",
        area_m2=round(cooling_area_m2, 1),
        location=cooling_fp["location"],  # "roof"
        sizing_basis_kw=facility_power_kw,
        m2_per_kw_used=cooling_m2_per_kw,
        source=cooling_fp["source"],
    ))

    # ══════════════════════════════════════════════════════════
    # 2. BACKUP POWER (ground-level)
    # ══════════════════════════════════════════════════════════
    # Sized to procurement power — must handle full redundant capacity.
    # Number of units = ceil(procurement_kW / module_size_kW).
    # You can't install half a generator.
    #
    # Source: Per-technology datasheets.
    # Architecture Agreement Section 3.8.

    backup_profile = BACKUP_POWER[backup_power_type.value]
    footprint_key = backup_profile["footprint_key"]
    backup_fp = FOOTPRINT[footprint_key]
    backup_m2_per_kw = backup_fp["default"]

    backup_unit_size_kw = float(backup_profile["module_size_kw"])

    if procurement_power_kw > 0:
        backup_num_units = math.ceil(procurement_power_kw / backup_unit_size_kw)
    else:
        backup_num_units = 0

    backup_area_m2 = procurement_power_kw * backup_m2_per_kw

    elements.append(FootprintElement(
        name=f"Backup Power ({backup_power_type.value})",
        area_m2=round(backup_area_m2, 1),
        location=backup_fp["location"],  # "ground"
        sizing_basis_kw=procurement_power_kw,
        m2_per_kw_used=backup_m2_per_kw,
        num_units=backup_num_units,
        unit_size_kw=backup_unit_size_kw,
        source=backup_profile["source"],
    ))

    # ══════════════════════════════════════════════════════════
    # 3. TRANSFORMERS (ground-level)
    # ══════════════════════════════════════════════════════════
    # HV/MV to LV step-down transformers.
    # Sized to procurement power — must handle full redundant paths.
    # Includes oil bund and access clearance in the m²/kW factor.
    #
    # Source: ABB/Siemens MV/LV transformer datasheets (2000 kVA class).
    # Architecture Agreement Section 3.11.

    transformer_fp = FOOTPRINT["transformer_m2_per_kw"]
    transformer_m2_per_kw = transformer_fp["default"]
    transformer_area_m2 = procurement_power_kw * transformer_m2_per_kw

    elements.append(FootprintElement(
        name="Transformers (HV/MV → LV)",
        area_m2=round(transformer_area_m2, 1),
        location=transformer_fp["location"],  # "ground"
        sizing_basis_kw=procurement_power_kw,
        m2_per_kw_used=transformer_m2_per_kw,
        source=transformer_fp["source"],
    ))

    # ══════════════════════════════════════════════════════════
    # 4. SUBSTATION (ground-level)
    # ══════════════════════════════════════════════════════════
    # MV switchgear room. Also sized to procurement power.
    #
    # Source: IEC 62271-200 MV switchgear room sizing.
    # Architecture Agreement Section 3.11.

    substation_fp = FOOTPRINT["substation_m2_per_kw"]
    substation_m2_per_kw = substation_fp["default"]
    substation_area_m2 = procurement_power_kw * substation_m2_per_kw

    elements.append(FootprintElement(
        name="Substation (MV Switchgear)",
        area_m2=round(substation_area_m2, 1),
        location=substation_fp["location"],  # "ground"
        sizing_basis_kw=procurement_power_kw,
        m2_per_kw_used=substation_m2_per_kw,
        source=substation_fp["source"],
    ))

    # ══════════════════════════════════════════════════════════
    # 5. AGGREGATE AND FIT CHECK
    # ══════════════════════════════════════════════════════════

    total_ground_m2 = sum(e.area_m2 for e in elements if e.location == "ground")
    total_roof_m2 = sum(e.area_m2 for e in elements if e.location == "roof")
    total_infrastructure_m2 = total_ground_m2 + total_roof_m2

    # Available outdoor area = land minus building footprint
    # This is where ground-level equipment goes: gensets, transformers, substation.
    available_outdoor_m2 = max(0.0, land_area_m2 - buildable_footprint_m2)

    # Building roof area = building footprint (single floor of roof space).
    # Multi-floor buildings still have one roof.
    building_roof_m2 = buildable_footprint_m2

    # Utilization ratios — >1.0 means doesn't fit
    ground_utilization = (
        total_ground_m2 / available_outdoor_m2
        if available_outdoor_m2 > 0
        else float("inf") if total_ground_m2 > 0 else 0.0
    )
    roof_utilization = (
        total_roof_m2 / building_roof_m2
        if building_roof_m2 > 0
        else float("inf") if total_roof_m2 > 0 else 0.0
    )

    ground_fits = ground_utilization <= 1.0
    roof_fits = roof_utilization <= 1.0

    return FootprintResult(
        elements=elements,
        total_ground_m2=round(total_ground_m2, 1),
        total_roof_m2=round(total_roof_m2, 1),
        total_infrastructure_m2=round(total_infrastructure_m2, 1),
        available_outdoor_m2=round(available_outdoor_m2, 1),
        building_roof_m2=round(building_roof_m2, 1),
        ground_utilization_ratio=round(ground_utilization, 4),
        roof_utilization_ratio=round(roof_utilization, 4),
        ground_fits=ground_fits,
        roof_fits=roof_fits,
        all_fits=ground_fits and roof_fits,
        backup_power_type=backup_power_type.value,
        backup_num_units=backup_num_units,
        backup_unit_size_kw=backup_unit_size_kw,
    )
