"""Focused regression coverage for controlled assumption overrides."""

from pathlib import Path
import uuid

import pytest

import engine.assumption_overrides as assumption_overrides
from engine.assumption_overrides import (
    AssumptionOverrideUpdate,
    get_applied_overrides_for_scenario,
    get_assumption_overrides,
)
from engine.assumptions import COOLING_PROFILES
from engine.cooling import compute_cop, compute_hourly_cooling
from engine.models import (
    CoolingType,
    DensityScenario,
    LoadType,
    RedundancyLevel,
    Scenario,
    Site,
)
from engine.power import compute_area_constrained
from engine.space import compute_space


EXPECTED_COOLING_OVERRIDE_PREFIXES = {
    "Air-Cooled CRAC (DX)": "cooling.crac_dx",
    "Air-Cooled AHU (No Economizer)": "cooling.ahu_no_econ",
    "Air-Cooled Chiller + Economizer": "cooling.air_chiller_econ",
    "Water-Cooled Chiller + Economizer": "cooling.water_chiller_econ",
    "Rear Door Heat Exchanger (RDHx)": "cooling.rdhx",
    "Direct Liquid Cooling (DLC / Cold Plate)": "cooling.dlc",
    "Immersion Cooling (Single-Phase)": "cooling.immersion",
    "Free Cooling — Dry Cooler (Chiller-less)": "cooling.dry_cooler",
}


@pytest.fixture
def isolated_assumption_overrides(monkeypatch):
    override_path = Path(assumption_overrides._BASE_DIR) / "data" / "settings" / (
        f"pytest-assumption-overrides-{uuid.uuid4().hex}.json"
    )
    history_path = Path(assumption_overrides._BASE_DIR) / "data" / "settings" / (
        f"pytest-assumption-history-{uuid.uuid4().hex}.json"
    )
    monkeypatch.setattr(
        assumption_overrides,
        "_OVERRIDES_PATH",
        override_path,
    )
    monkeypatch.setattr(
        assumption_overrides,
        "_HISTORY_PATH",
        history_path,
    )
    if override_path.exists():
        override_path.unlink()
    if history_path.exists():
        history_path.unlink()
    assumption_overrides.clear_assumption_override_cache()
    yield assumption_overrides
    if override_path.exists():
        override_path.unlink()
    if history_path.exists():
        history_path.unlink()
    assumption_overrides.clear_assumption_override_cache()


def test_catalog_covers_all_current_cooling_profiles(isolated_assumption_overrides):
    """Every Scenario Runner cooling family should expose the same core override keys."""
    response = get_assumption_overrides()
    cooling_keys = {
        entry.key
        for entry in response.assumptions
        if entry.section == "cooling"
    }
    expected_keys = {
        f"{prefix}.{suffix}"
        for prefix in EXPECTED_COOLING_OVERRIDE_PREFIXES.values()
        for suffix in ("pue_typical", "cop_ref", "k_fan")
    }

    assert set(COOLING_PROFILES) == set(EXPECTED_COOLING_OVERRIDE_PREFIXES)
    assert cooling_keys == expected_keys
    assert len(cooling_keys) == len(COOLING_PROFILES) * 3


def test_rdhx_overrides_change_static_and_hourly_resolution(
    isolated_assumption_overrides,
):
    """Newly covered RDHx keys should affect both static and hourly calculations."""
    isolated_assumption_overrides.save_assumption_override_updates([
        AssumptionOverrideUpdate(
            key="cooling.rdhx.pue_typical",
            override_value=1.24,
            source="Project RDHx design note",
            justification="The target RDHx deployment has a lower static PUE than the repo baseline.",
        ),
        AssumptionOverrideUpdate(
            key="cooling.rdhx.cop_ref",
            override_value=6.4,
            source="Shared chiller selection sheet",
            justification="The paired chiller reference point is better than the generic RDHx baseline.",
        ),
        AssumptionOverrideUpdate(
            key="cooling.rdhx.k_fan",
            override_value=0.06,
            source="Rack airflow review",
            justification="The chosen rear-door layout retains more fan overhead than the default assumption.",
        ),
    ])

    scenario = Scenario(
        load_type=LoadType.HPC,
        cooling_type=CoolingType.RDHX,
        redundancy=RedundancyLevel.TWO_N,
        density_scenario=DensityScenario.TYPICAL,
    )
    site = Site(name="RDHx Override Test", land_area_m2=25000)

    space = compute_space(site, cooling_type=scenario.cooling_type)
    power = compute_area_constrained(site, scenario, space)
    hourly_state = compute_hourly_cooling(
        T_db=30.0,
        RH=None,
        cooling_type=scenario.cooling_type.value,
        eta_chain=0.95,
    )

    assert power.pue_used == 1.24
    assert compute_cop(35.0, None, scenario.cooling_type.value) == 6.4
    assert hourly_state.k_fan == 0.06


def test_dry_cooler_hourly_overrides_appear_in_trace_metadata(
    isolated_assumption_overrides,
):
    """Hourly runs should report the newly added dry-cooler keys in scenario traces."""
    isolated_assumption_overrides.save_assumption_override_updates([
        AssumptionOverrideUpdate(
            key="cooling.dry_cooler.pue_typical",
            override_value=1.12,
            source="Concept dry-cooler estimate",
            justification="The target design uses a tighter static dry-cooler allowance than the repo baseline.",
        ),
        AssumptionOverrideUpdate(
            key="cooling.dry_cooler.cop_ref",
            override_value=13.5,
            source="Fan curve review",
            justification="The selected dry-cooler fan package performs above the baseline COP reference.",
        ),
        AssumptionOverrideUpdate(
            key="cooling.dry_cooler.k_fan",
            override_value=0.05,
            source="Fan power schedule",
            justification="The selected fan package carries slightly higher parasitic overhead than the default.",
        ),
    ])

    scenario = Scenario(
        load_type=LoadType.HYPERSCALE,
        cooling_type=CoolingType.DRY_COOLER,
        redundancy=RedundancyLevel.TWO_N,
        density_scenario=DensityScenario.TYPICAL,
    )

    static_keys = {
        item.key
        for item in get_applied_overrides_for_scenario(
            scenario,
            include_hourly_effects=False,
        )
    }
    hourly_keys = {
        item.key
        for item in get_applied_overrides_for_scenario(
            scenario,
            include_hourly_effects=True,
        )
    }

    assert static_keys == {"cooling.dry_cooler.pue_typical"}
    assert hourly_keys == {
        "cooling.dry_cooler.pue_typical",
        "cooling.dry_cooler.cop_ref",
        "cooling.dry_cooler.k_fan",
    }
