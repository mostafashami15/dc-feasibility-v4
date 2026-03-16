"""Regression tests for scenario route helpers."""

import asyncio
from pathlib import Path
import pytest
import uuid

import engine.assumption_overrides as assumption_overrides
from api import routes_scenario
from api.routes_scenario import BatchRequest, _run_single_scenario
from api.store import get_site
from engine.models import (
    Site,
    Scenario,
    LoadType,
    CoolingType,
    RedundancyLevel,
    DensityScenario,
    RAGStatus,
)
from engine.assumption_overrides import (
    AssumptionOverrideUpdate,
    get_assumption_override_history,
)


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


def test_run_single_scenario_captures_overtemperature_and_downgrades_dry_cooler():
    """Garbagnate dry-cooler hyperscale should no longer surface as BLUE."""
    site_id = "94f01936-befa-443f-9c6a-1c050cb5fab8"
    loaded = get_site(site_id)
    assert loaded is not None
    _, site = loaded

    scenario = Scenario(
        load_type=LoadType.HYPERSCALE,
        cooling_type=CoolingType.DRY_COOLER,
        redundancy=RedundancyLevel.TWO_N,
        density_scenario=DensityScenario.TYPICAL,
    )

    result = _run_single_scenario(
        site_id=site_id,
        site=site,
        scenario=scenario,
        include_hourly=True,
    )

    assert result.overtemperature_hours == 73
    assert result.power.rag_status == RAGStatus.AMBER
    assert any("73 hours" in reason for reason in result.power.rag_reasons)


def test_run_single_scenario_stamps_applied_assumption_overrides(isolated_assumption_overrides):
    isolated_assumption_overrides.save_assumption_override_updates([
        AssumptionOverrideUpdate(
            key="cooling.air_chiller_econ.pue_typical",
            override_value=1.33,
            source="Project design review",
            justification="The current feasibility run uses a tighter air-chiller target than the baseline.",
        ),
        AssumptionOverrideUpdate(
            key="redundancy.two_n.eta_chain_derate",
            override_value=0.962,
            source="UPS vendor curve",
            justification="Selected 2N UPS train performs above the default partial-load assumption.",
        ),
    ])

    site = Site(name="Override Test Site", land_area_m2=25000)
    scenario = Scenario(
        load_type=LoadType.COLOCATION_STANDARD,
        cooling_type=CoolingType.AIR_CHILLER_ECON,
        redundancy=RedundancyLevel.TWO_N,
        density_scenario=DensityScenario.TYPICAL,
    )

    result = _run_single_scenario(
        site_id="override-test",
        site=site,
        scenario=scenario,
        include_hourly=False,
    )

    assert result.power.pue_used == 1.33
    assert result.power.eta_chain == 0.962
    assert {item.key for item in result.applied_assumption_overrides} == {
        "cooling.air_chiller_econ.pue_typical",
        "redundancy.two_n.eta_chain_derate",
    }


def test_batch_run_threads_preset_key_and_records_history(
    isolated_assumption_overrides,
    monkeypatch,
):
    site = Site(name="Preset Batch Site", land_area_m2=25000)

    monkeypatch.setattr(
        routes_scenario,
        "get_site",
        lambda site_id: (site_id, site),
    )

    request = BatchRequest(
        site_ids=["preset-site"],
        load_types=[LoadType.COLOCATION_STANDARD],
        cooling_types=[CoolingType.AIR_CHILLER_ECON],
        redundancy_levels=[RedundancyLevel.TWO_N],
        density_scenarios=[DensityScenario.TYPICAL],
        assumption_override_preset_key="high_efficiency_envelope",
        include_hourly=False,
        skip_incompatible=True,
    )

    result = asyncio.run(routes_scenario.batch_run_endpoint(request))
    history = get_assumption_override_history(limit=5)

    assert result["computed"] == 1
    assert result["results"][0]["scenario"]["assumption_override_preset_key"] == (
        "high_efficiency_envelope"
    )
    assert result["results"][0]["assumption_override_preset_label"] == (
        "High-Efficiency Envelope"
    )
    assert history.entries[0].event_type == "scenario_preset_run"
    assert history.entries[0].preset_key == "high_efficiency_envelope"
    assert history.entries[0].scenario_count == 1
