"""
DC Feasibility Tool v4 - Advisory Expansion Modeling
====================================================
Models future site upside without changing the baseline feasibility score.

This module answers a planning question:
    "If we build out the remaining space and any extra floors allowed by
    height, how much additional IT load could the site support, and what
    extra grid request would that require?"

The output is advisory only. It does NOT change the current scenario score
or ranking because it represents hypothetical future build-out.
"""

from typing import Optional

from pydantic import BaseModel, Field

from engine.models import PowerInputMode, Scenario, Site, SpaceResult, PowerResult
from engine.space import compute_space


class ExpansionCapacitySnapshot(BaseModel):
    """Capacity summary for one stage of site development."""

    racks: int = Field(description="Rack count for this stage")
    it_load_mw: float = Field(description="IT load supported in MW")
    facility_power_mw: float = Field(description="Facility power required in MW")
    procurement_power_mw: float = Field(description="Grid procurement power in MW")


class ExpansionAdvisoryResult(BaseModel):
    """Advisory-only expansion potential for one site and scenario."""

    advisory_only: bool = Field(
        default=True,
        description="Always true - advisory outputs are excluded from ranking",
    )
    binding_constraint: str = Field(description="Current baseline binding constraint")
    rack_density_kw: float = Field(description="Rack density used for the scenario")
    pue_used: float = Field(description="PUE used for advisory calculations")
    pue_source: str = Field(description="static or hourly")
    eta_chain: float = Field(description="Power chain efficiency used")
    procurement_factor: float = Field(description="Redundancy procurement factor used")

    active_floors: int = Field(description="Currently active floors")
    declared_expansion_floors: int = Field(
        description="User-declared future expansion floors"
    )
    latent_height_floors: int = Field(
        description="Extra floors allowed by height beyond the current plan"
    )
    max_total_floors: Optional[int] = Field(
        default=None,
        description="Maximum total floors allowed by height, if a height limit exists",
    )

    current_floor_capacity_racks: int = Field(
        description="Physical rack capacity on active floors"
    )
    unused_active_racks: int = Field(
        description="Active-floor racks left unused because power is the current limit"
    )
    declared_expansion_racks: int = Field(
        description="Additional racks from user-declared expansion floors"
    )
    latent_height_racks: int = Field(
        description="Additional racks from extra floors implied by height allowance"
    )
    total_additional_racks: int = Field(
        description="Total advisory racks beyond the current deployed baseline"
    )

    current_facility_envelope_mw: float = Field(
        description="Current confirmed or inferred facility-power envelope in MW"
    )
    current_procurement_envelope_mw: float = Field(
        description="Current confirmed or inferred procurement-power envelope in MW"
    )
    additional_grid_request_mw: float = Field(
        description="Extra procurement power to request to unlock full site potential"
    )

    current_feasible: ExpansionCapacitySnapshot = Field(
        description="Current feasible deployed capacity"
    )
    future_expandable: ExpansionCapacitySnapshot = Field(
        description="Additional advisory-only capacity beyond the current baseline"
    )
    total_site_potential: ExpansionCapacitySnapshot = Field(
        description="Total site potential if all advisory expansion is built"
    )

    notes: list[str] = Field(
        default_factory=list,
        description="Human-readable notes explaining the advisory outputs",
    )


def _derive_max_total_floors(site: Site) -> Optional[int]:
    """Return the total floors allowed by height, if the site has a limit."""
    if site.max_building_height_m is None or site.max_building_height_m <= 0:
        return None

    derived = int(site.max_building_height_m / site.floor_to_floor_height_m)
    return max(1, derived)


def _snapshot_from_racks(
    racks: int,
    rack_density_kw: float,
    pue_used: float,
    eta_chain: float,
    procurement_factor: float,
) -> ExpansionCapacitySnapshot:
    """Convert rack count into IT/facility/procurement power."""
    it_load_mw = racks * rack_density_kw / 1000.0
    facility_power_mw = it_load_mw * pue_used / eta_chain if eta_chain > 0 else 0.0
    procurement_power_mw = facility_power_mw * procurement_factor

    return ExpansionCapacitySnapshot(
        racks=racks,
        it_load_mw=round(it_load_mw, 3),
        facility_power_mw=round(facility_power_mw, 3),
        procurement_power_mw=round(procurement_power_mw, 3),
    )


def compute_expansion_advisory(
    site: Site,
    scenario: Scenario,
    space: SpaceResult,
    power: PowerResult,
    annual_pue: Optional[float] = None,
    pue_source: str = "static",
) -> ExpansionAdvisoryResult:
    """Compute advisory-only future expansion potential for a scenario."""
    pue_used = annual_pue if annual_pue is not None else power.pue_used
    max_total_floors = _derive_max_total_floors(site)

    current_feasible = _snapshot_from_racks(
        racks=power.racks_deployed,
        rack_density_kw=power.rack_density_kw,
        pue_used=pue_used,
        eta_chain=power.eta_chain,
        procurement_factor=power.procurement_factor,
    )

    unused_active_racks = max(0, space.effective_racks - power.racks_deployed)
    declared_expansion_racks = space.expansion_racks
    declared_expansion_floors = space.expansion_floors

    latent_height_floors = 0
    latent_height_racks = 0
    notes: list[str] = [
        "Advisory only - future expansion does not change the main scenario ranking."
    ]

    if max_total_floors is None:
        notes.append(
            "No height limit was provided, so vertical expansion beyond the current plan "
            "cannot be estimated."
        )
    else:
        planned_total_floors = space.active_floors + declared_expansion_floors
        latent_height_floors = max(0, max_total_floors - planned_total_floors)

        if latent_height_floors > 0:
            planned_space = compute_space(
                site.model_copy(
                    update={
                        "num_floors": planned_total_floors,
                        "num_expansion_floors": 0,
                    }
                ),
                cooling_type=scenario.cooling_type,
            )
            full_height_space = compute_space(
                site.model_copy(
                    update={
                        "num_floors": max_total_floors,
                        "num_expansion_floors": 0,
                    }
                ),
                cooling_type=scenario.cooling_type,
            )
            latent_height_racks = max(
                0,
                full_height_space.effective_racks - planned_space.effective_racks,
            )
            notes.append(
                f"Height allowance supports {latent_height_floors} more floor(s) beyond "
                "the current plan."
            )

    if unused_active_racks > 0:
        notes.append(
            f"Power is the current constraint: {unused_active_racks} active-floor rack(s) "
            "fit physically but are not energized yet."
        )

    if declared_expansion_floors > 0:
        notes.append(
            f"The current site plan already reserves {declared_expansion_floors} "
            f"future floor(s), adding {declared_expansion_racks} rack(s)."
        )

    total_additional_racks = (
        unused_active_racks + declared_expansion_racks + latent_height_racks
    )
    future_expandable = _snapshot_from_racks(
        racks=total_additional_racks,
        rack_density_kw=power.rack_density_kw,
        pue_used=pue_used,
        eta_chain=power.eta_chain,
        procurement_factor=power.procurement_factor,
    )
    total_site_potential = _snapshot_from_racks(
        racks=power.racks_deployed + total_additional_racks,
        rack_density_kw=power.rack_density_kw,
        pue_used=pue_used,
        eta_chain=power.eta_chain,
        procurement_factor=power.procurement_factor,
    )

    if site.power_confirmed and site.available_power_mw > 0:
        if site.power_input_mode == PowerInputMode.OPERATIONAL:
            current_facility_envelope_mw = site.available_power_mw
            current_procurement_envelope_mw = (
                current_facility_envelope_mw * power.procurement_factor
            )
        else:
            current_procurement_envelope_mw = site.available_power_mw
            current_facility_envelope_mw = (
                current_procurement_envelope_mw / power.procurement_factor
            )
    else:
        current_facility_envelope_mw = current_feasible.facility_power_mw
        current_procurement_envelope_mw = current_feasible.procurement_power_mw

    additional_grid_request_mw = max(
        0.0,
        total_site_potential.procurement_power_mw - current_procurement_envelope_mw,
    )

    if total_additional_racks == 0:
        notes.append("No additional rack capacity was identified beyond the current baseline.")
    elif additional_grid_request_mw <= 0:
        notes.append(
            "The current power envelope is already sufficient for the full advisory build-out."
        )
    else:
        notes.append(
            f"Unlocking the full site potential would require about "
            f"{additional_grid_request_mw:.3f} MW of extra grid procurement."
        )

    return ExpansionAdvisoryResult(
        binding_constraint=power.binding_constraint,
        rack_density_kw=power.rack_density_kw,
        pue_used=round(pue_used, 4),
        pue_source=pue_source,
        eta_chain=power.eta_chain,
        procurement_factor=power.procurement_factor,
        active_floors=space.active_floors,
        declared_expansion_floors=declared_expansion_floors,
        latent_height_floors=latent_height_floors,
        max_total_floors=max_total_floors,
        current_floor_capacity_racks=space.effective_racks,
        unused_active_racks=unused_active_racks,
        declared_expansion_racks=declared_expansion_racks,
        latent_height_racks=latent_height_racks,
        total_additional_racks=total_additional_racks,
        current_facility_envelope_mw=round(current_facility_envelope_mw, 3),
        current_procurement_envelope_mw=round(current_procurement_envelope_mw, 3),
        additional_grid_request_mw=round(additional_grid_request_mw, 3),
        current_feasible=current_feasible,
        future_expandable=future_expandable,
        total_site_potential=total_site_potential,
        notes=notes,
    )
