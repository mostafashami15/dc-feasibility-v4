"""
Tests for expansion.py - advisory-only future build-out modeling.
"""

import pytest

from engine.expansion import compute_expansion_advisory
from engine.models import (
    CoolingType,
    DensityScenario,
    LoadType,
    PowerInputMode,
    RedundancyLevel,
    Scenario,
    Site,
)
from engine.power import solve


def _make_scenario(
    load=LoadType.COLOCATION_STANDARD,
    cooling=CoolingType.AIR_CHILLER_ECON,
    redundancy=RedundancyLevel.TWO_N,
    density=DensityScenario.TYPICAL,
):
    return Scenario(
        load_type=load,
        cooling_type=cooling,
        redundancy=redundancy,
        density_scenario=density,
    )


def test_expansion_advisory_power_constrained_with_height_uplift():
    """Power-limited site should report unused active racks and future floors."""
    site = Site(
        name="Power Limited",
        land_area_m2=15000,
        num_floors=1,
        num_expansion_floors=1,
        max_building_height_m=13.5,
        floor_to_floor_height_m=4.5,
        available_power_mw=5.0,
        power_confirmed=True,
        power_input_mode=PowerInputMode.OPERATIONAL,
    )
    scenario = _make_scenario()

    space, power = solve(site, scenario)
    result = compute_expansion_advisory(site, scenario, space, power)

    assert result.binding_constraint == "POWER"
    assert result.active_floors == 1
    assert result.declared_expansion_floors == 1
    assert result.latent_height_floors == 1
    assert result.current_floor_capacity_racks == 1000
    assert result.unused_active_racks == 509
    assert result.declared_expansion_racks == 1000
    assert result.latent_height_racks == 1000
    assert result.total_additional_racks == 2509

    assert result.current_feasible.racks == 491
    assert result.total_site_potential.racks == 3000
    assert result.total_site_potential.it_load_mw == 21.0
    assert result.current_procurement_envelope_mw == 10.0
    assert result.additional_grid_request_mw == pytest.approx(51.011, abs=0.001)


def test_expansion_advisory_area_mode_uses_baseline_power_requirement():
    """Without confirmed power, the extra grid ask is relative to baseline demand."""
    site = Site(
        name="Area Mode",
        land_area_m2=10000,
        num_floors=1,
        num_expansion_floors=0,
        max_building_height_m=13.5,
        floor_to_floor_height_m=4.5,
    )
    scenario = _make_scenario()

    space, power = solve(site, scenario)
    result = compute_expansion_advisory(site, scenario, space, power)

    assert result.binding_constraint == "AREA"
    assert result.current_feasible.racks == 666
    assert result.unused_active_racks == 0
    assert result.latent_height_floors == 2
    assert result.latent_height_racks == 1334
    assert result.total_additional_racks == 1334
    assert result.current_procurement_envelope_mw == result.current_feasible.procurement_power_mw
    assert result.additional_grid_request_mw == pytest.approx(
        result.future_expandable.procurement_power_mw,
        abs=0.001,
    )


def test_expansion_advisory_without_height_limit_stays_horizontal_only():
    """If no height limit exists, the engine should not invent extra floors."""
    site = Site(
        name="No Height Limit",
        land_area_m2=15000,
        num_floors=1,
        num_expansion_floors=1,
    )
    scenario = _make_scenario()

    space, power = solve(site, scenario)
    result = compute_expansion_advisory(site, scenario, space, power)

    assert result.max_total_floors is None
    assert result.latent_height_floors == 0
    assert result.latent_height_racks == 0
    assert any("No height limit" in note for note in result.notes)
