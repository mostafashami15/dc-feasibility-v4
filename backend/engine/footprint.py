"""
DC Feasibility Tool v4 — Infrastructure Footprint Calculation
==============================================================
Computes the physical area consumed by infrastructure equipment
within the building's gray space (and optionally the roof).

All equipment lives INSIDE the buildable footprint:
    - Gray space: backup power, transformers, substation, and cooling
      (if roof is not usable)
    - Roof: cooling equipment ONLY, and ONLY when the user confirms
      the roof is usable for equipment placement.

The buildable footprint is the building envelope — nothing is placed
outside it. The land area outside the building is NOT used for
equipment in this model.

Key sizing principle:
    - Cooling equipment is sized by FACILITY power (≈ total heat rejection).
      All electricity entering the building becomes heat that must be rejected.
      Source: first law of thermodynamics; standard HVAC sizing practice.
    - Backup power, transformers, and substation are sized by PROCUREMENT power,
      because these components must handle the full redundant capacity.
      Source: Uptime Institute Tier Standard: Topology (2018).

Space budget:
    gross_building_area = buildable_footprint × active_floors
    it_whitespace       = gross_building_area × whitespace_ratio
    gray_space          = gross_building_area - it_whitespace

    All support equipment must fit in gray_space (+ roof for cooling if usable).

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
    whether it sits in gray space or on the roof.
    """
    name: str = Field(description="Element name (e.g., 'Cooling Equipment')")
    area_m2: float = Field(description="Total footprint in m²")
    location: str = Field(description="'gray_space' or 'roof'")
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

    Checks whether all equipment fits in the building's gray space
    (and optionally on the roof for cooling equipment).
    """

    # ── Per-element breakdown ──
    elements: list[FootprintElement] = Field(
        description="Detailed breakdown per infrastructure element"
    )

    # ── Aggregated areas ──
    total_gray_space_equipment_m2: float = Field(
        description="Total equipment area placed in gray space (m²)"
    )
    total_roof_equipment_m2: float = Field(
        description="Total equipment area placed on roof (m²)"
    )
    total_infrastructure_m2: float = Field(
        description="Total infrastructure footprint (gray space + roof) (m²)"
    )

    # ── Available space ──
    gray_space_m2: float = Field(
        description="Available gray space inside the building (m²)"
    )
    building_roof_m2: float = Field(
        description="Building roof area (= buildable footprint) (m²)"
    )
    roof_usable: bool = Field(
        description="Whether the roof is usable for cooling equipment"
    )

    # ── Utilization ratios ──
    gray_space_utilization_ratio: float = Field(
        description=(
            "Equipment in gray space / available gray space. "
            ">1.0 means equipment does NOT fit."
        )
    )
    roof_utilization_ratio: float = Field(
        description=(
            "Cooling on roof / building roof area. "
            ">1.0 means cooling does NOT fit. 0.0 if roof not usable."
        )
    )

    # ── Fit verdicts ──
    gray_space_fits: bool = Field(
        description="True if all gray-space equipment fits"
    )
    roof_fits: bool = Field(
        description="True if roof equipment fits (always True when roof not usable)"
    )
    all_fits: bool = Field(
        description="True if everything fits"
    )

    # ── Remaining capacity ──
    gray_space_remaining_m2: float = Field(
        description="Unused gray space after equipment placement (m²)"
    )

    # ── Backward-compatible aliases for scoring ──
    ground_utilization_ratio: float = Field(
        description="Alias for gray_space_utilization_ratio (backward compatibility)"
    )
    ground_fits: bool = Field(
        description="Alias for gray_space_fits (backward compatibility)"
    )

    # ── Backup power details ──
    backup_power_type: str = Field(description="Backup power technology used")
    backup_num_units: int = Field(description="Number of backup power units")
    backup_unit_size_kw: float = Field(description="Size per backup unit (kW)")

    # ── Warnings ──
    warnings: list[str] = Field(
        default_factory=list,
        description="Human-readable warnings about equipment fit"
    )


# ─────────────────────────────────────────────────────────────
# Main Calculation
# ─────────────────────────────────────────────────────────────

def compute_footprint(
    facility_power_mw: float,
    procurement_power_mw: float,
    buildable_footprint_m2: float,
    gray_space_m2: float,
    roof_usable: bool = True,
    backup_power_type: BackupPowerType = BackupPowerType.DIESEL_GENSET,
    cooling_m2_per_kw_override: Optional[float] = None,
    # Deprecated — kept for backward compatibility, unused in new model
    land_area_m2: Optional[float] = None,
) -> FootprintResult:
    """Compute infrastructure footprint and gray space fit analysis.

    All equipment is placed INSIDE the building:
        - Gray space: generators, transformers, substation, and cooling
          (when roof is not usable)
        - Roof: cooling equipment only (when roof is usable)

    Args:
        facility_power_mw:
            Total facility power in MW (from power.py).
            Used as the heat rejection basis for cooling equipment sizing.

        procurement_power_mw:
            Grid capacity in MW (from power.py).
            Used for backup power, transformers, and substation sizing.

        buildable_footprint_m2:
            Building ground-floor footprint in m² (from space.py).
            Used as roof area when roof_usable=True.

        gray_space_m2:
            Available gray space inside the building (from space.py).
            This is where all support equipment must fit.

        roof_usable:
            Whether the building roof can host cooling equipment.
            If False, cooling is placed in gray space instead.

        backup_power_type:
            Which backup power technology to size.

        cooling_m2_per_kw_override:
            Optional override for cooling footprint factor (m²/kW).

        land_area_m2:
            Deprecated. Kept for API backward compatibility.

    Returns:
        FootprintResult with per-element breakdown and fit analysis.
    """
    if facility_power_mw < 0:
        raise ValueError(f"facility_power_mw cannot be negative: {facility_power_mw}")
    if procurement_power_mw < 0:
        raise ValueError(f"procurement_power_mw cannot be negative: {procurement_power_mw}")

    facility_power_kw = facility_power_mw * 1000
    procurement_power_kw = procurement_power_mw * 1000

    elements: list[FootprintElement] = []
    warnings: list[str] = []

    # ══════════════════════════════════════════════════════════
    # 1. COOLING EQUIPMENT
    # ══════════════════════════════════════════════════════════
    # Location depends on roof_usable:
    #   roof_usable=True  → roof (condensers/dry coolers on rooftop)
    #   roof_usable=False → gray_space (cooling plant room inside building)
    #
    # Source: Carrier/Trane condenser selection guides.

    cooling_fp = FOOTPRINT["cooling_skid_m2_per_kw_rejected"]
    cooling_m2_per_kw = (
        cooling_m2_per_kw_override
        if cooling_m2_per_kw_override is not None
        else cooling_fp["default"]
    )
    cooling_area_m2 = facility_power_kw * cooling_m2_per_kw
    cooling_location = "roof" if roof_usable else "gray_space"

    elements.append(FootprintElement(
        name="Cooling Equipment (Condensers / Dry Coolers)",
        area_m2=round(cooling_area_m2, 1),
        location=cooling_location,
        sizing_basis_kw=facility_power_kw,
        m2_per_kw_used=cooling_m2_per_kw,
        source=cooling_fp["source"],
    ))

    # ══════════════════════════════════════════════════════════
    # 2. BACKUP POWER (gray space)
    # ══════════════════════════════════════════════════════════
    # Generators/fuel cells live inside the building in dedicated
    # plant rooms within the gray space.
    #
    # Source: Per-technology datasheets.

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
        location="gray_space",
        sizing_basis_kw=procurement_power_kw,
        m2_per_kw_used=backup_m2_per_kw,
        num_units=backup_num_units,
        unit_size_kw=backup_unit_size_kw,
        source=backup_profile["source"],
    ))

    # ══════════════════════════════════════════════════════════
    # 3. TRANSFORMERS (gray space)
    # ══════════════════════════════════════════════════════════
    # HV/MV to LV step-down transformers in dedicated rooms.
    #
    # Source: ABB/Siemens MV/LV transformer datasheets.

    transformer_fp = FOOTPRINT["transformer_m2_per_kw"]
    transformer_m2_per_kw = transformer_fp["default"]
    transformer_area_m2 = procurement_power_kw * transformer_m2_per_kw

    elements.append(FootprintElement(
        name="Transformers (HV/MV → LV)",
        area_m2=round(transformer_area_m2, 1),
        location="gray_space",
        sizing_basis_kw=procurement_power_kw,
        m2_per_kw_used=transformer_m2_per_kw,
        source=transformer_fp["source"],
    ))

    # ══════════════════════════════════════════════════════════
    # 4. SUBSTATION (gray space)
    # ══════════════════════════════════════════════════════════
    # MV switchgear room inside the building.
    #
    # Source: IEC 62271-200 MV switchgear room sizing.

    substation_fp = FOOTPRINT["substation_m2_per_kw"]
    substation_m2_per_kw = substation_fp["default"]
    substation_area_m2 = procurement_power_kw * substation_m2_per_kw

    elements.append(FootprintElement(
        name="Substation (MV Switchgear)",
        area_m2=round(substation_area_m2, 1),
        location="gray_space",
        sizing_basis_kw=procurement_power_kw,
        m2_per_kw_used=substation_m2_per_kw,
        source=substation_fp["source"],
    ))

    # ══════════════════════════════════════════════════════════
    # 5. AGGREGATE AND FIT CHECK
    # ══════════════════════════════════════════════════════════

    total_gray_m2 = sum(e.area_m2 for e in elements if e.location == "gray_space")
    total_roof_m2 = sum(e.area_m2 for e in elements if e.location == "roof")
    total_infrastructure_m2 = total_gray_m2 + total_roof_m2

    # Gray space fit check
    gray_utilization = (
        total_gray_m2 / gray_space_m2
        if gray_space_m2 > 0
        else float("inf") if total_gray_m2 > 0 else 0.0
    )
    gray_fits = gray_utilization <= 1.0
    gray_remaining = max(0.0, gray_space_m2 - total_gray_m2)

    # Roof fit check (only relevant when roof is usable)
    building_roof_m2 = buildable_footprint_m2
    if roof_usable and total_roof_m2 > 0:
        roof_utilization = (
            total_roof_m2 / building_roof_m2
            if building_roof_m2 > 0
            else float("inf")
        )
        roof_fits = roof_utilization <= 1.0
    else:
        roof_utilization = 0.0
        roof_fits = True  # No roof equipment or roof not usable

    all_fits = gray_fits and roof_fits

    # ── Generate warnings ──
    if not gray_fits:
        overshoot_m2 = total_gray_m2 - gray_space_m2
        warnings.append(
            f"Equipment exceeds gray space by {overshoot_m2:,.0f} m² "
            f"({gray_utilization:.0%} utilization). "
            f"Consider increasing building size, adding floors, or reducing whitespace ratio."
        )

    if not roof_fits:
        warnings.append(
            f"Cooling equipment ({total_roof_m2:,.0f} m²) exceeds roof capacity "
            f"({building_roof_m2:,.0f} m²). Consider splitting cooling between "
            f"roof and gray space or increasing building footprint."
        )

    if not roof_usable:
        warnings.append(
            "Roof not usable — cooling equipment placed in gray space. "
            "This significantly increases gray space demand."
        )

    if gray_fits and gray_utilization > 0.85:
        warnings.append(
            f"Gray space is {gray_utilization:.0%} utilized — tight margin. "
            f"Only {gray_remaining:,.0f} m² remaining for corridors and ancillary."
        )

    return FootprintResult(
        elements=elements,
        total_gray_space_equipment_m2=round(total_gray_m2, 1),
        total_roof_equipment_m2=round(total_roof_m2, 1),
        total_infrastructure_m2=round(total_infrastructure_m2, 1),
        gray_space_m2=round(gray_space_m2, 1),
        building_roof_m2=round(building_roof_m2, 1),
        roof_usable=roof_usable,
        gray_space_utilization_ratio=round(gray_utilization, 4),
        roof_utilization_ratio=round(roof_utilization, 4),
        gray_space_fits=gray_fits,
        roof_fits=roof_fits,
        all_fits=all_fits,
        gray_space_remaining_m2=round(gray_remaining, 1),
        ground_utilization_ratio=round(gray_utilization, 4),
        ground_fits=gray_fits,
        backup_power_type=backup_power_type.value,
        backup_num_units=backup_num_units,
        backup_unit_size_kw=backup_unit_size_kw,
        warnings=warnings,
    )
