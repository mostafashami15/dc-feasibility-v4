"""
Tests for power.py — Power chain calculations.

Tests cover:
- Power-constrained mode (both operational and grid reservation input)
- Area-constrained mode
- Redundancy effects (eta_chain_derate and procurement_factor)
- RAG status system (RED/AMBER/GREEN/BLUE)
- The solve() entry point

Run with:
    cd backend
    pytest tests/test_power.py -v
"""

import pytest
from pathlib import Path
import uuid
import engine.assumption_overrides as assumption_overrides
from engine.assumption_overrides import AssumptionOverrideUpdate
from engine.models import (
    Site,
    Scenario,
    LoadType,
    CoolingType,
    RedundancyLevel,
    DensityScenario,
    PowerInputMode,
    RAGStatus,
    BuildableAreaMode,
)
from engine.power import (
    compute_power_constrained,
    compute_area_constrained,
    solve,
    apply_hourly_rag_adjustments,
    _get_eta_chain,
    _get_procurement_factor,
)
from engine.space import compute_space


@pytest.fixture
def isolated_assumption_overrides(monkeypatch):
    override_path = Path(assumption_overrides._BASE_DIR) / "data" / "settings" / (
        f"pytest-assumption-overrides-{uuid.uuid4().hex}.json"
    )
    monkeypatch.setattr(
        assumption_overrides,
        "_OVERRIDES_PATH",
        override_path,
    )
    if override_path.exists():
        override_path.unlink()
    assumption_overrides.clear_assumption_override_cache()
    yield assumption_overrides
    if override_path.exists():
        override_path.unlink()
    assumption_overrides.clear_assumption_override_cache()


# ─────────────────────────────────────────────────────────────
# Helper: create common test sites and scenarios
# ─────────────────────────────────────────────────────────────

def _make_power_site(power_mw=20.0, land_m2=25000, mode=PowerInputMode.OPERATIONAL):
    """Standard power-constrained test site."""
    return Site(
        name="Power Test",
        land_area_m2=land_m2,
        available_power_mw=power_mw,
        power_confirmed=True,
        power_input_mode=mode,
    )


def _make_area_site(land_m2=25000):
    """Standard area-constrained test site (no power)."""
    return Site(name="Area Test", land_area_m2=land_m2)


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


# ─────────────────────────────────────────────────────────────
# Test 1: Power-constrained — operational mode, standard colo
# ─────────────────────────────────────────────────────────────
def test_power_constrained_operational():
    """20 MW operational power, standard colo, 2N redundancy.

    Hand calculation:
        η_chain (2N) = 0.950
        PUE (Air Chiller+Econ typical) = 1.38
        IT load = 20.0 × 0.950 / 1.38 = 13.768 MW
        Racks by power = 13768 / 7 = 1966 racks
        Space gives 1666 effective racks (25000 m², default ratios)
        Binding = AREA (1966 > 1666)
        IT load from space = 1666 × 7 / 1000 = 11.662 MW
        Facility power = 11.662 × 1.38 / 0.950 = 16.929 MW
        Procurement = 20.0 × 2.0 = 40.0 MW
    """
    site = _make_power_site(power_mw=20.0)
    scenario = _make_scenario()
    space = compute_space(site, cooling_type=scenario.cooling_type)
    result = compute_power_constrained(site, scenario, space)

    assert result.facility_power_mw == 20.0  # Operational = entered value
    assert result.procurement_power_mw == 40.0  # 2N = 2×
    assert result.eta_chain == 0.950
    assert result.pue_used == 1.38
    assert result.power_input_mode == PowerInputMode.OPERATIONAL


# ─────────────────────────────────────────────────────────────
# Test 2: Power-constrained — grid reservation mode
# ─────────────────────────────────────────────────────────────
def test_power_constrained_grid_reservation():
    """100 MW grid reservation with 2N → facility = 50 MW.

    Hand calculation:
        procurement_factor (2N) = 2.0
        facility_power = 100 / 2.0 = 50.0 MW
        procurement_power = 100.0 MW (the entered value)
        IT load = 50.0 × 0.950 / 1.38 = 34.420 MW
    """
    site = _make_power_site(
        power_mw=100.0,
        land_m2=200000,  # Large site so power is binding
        mode=PowerInputMode.GRID_RESERVATION,
    )
    scenario = _make_scenario()
    space = compute_space(site, cooling_type=scenario.cooling_type)
    result = compute_power_constrained(site, scenario, space)

    assert result.procurement_power_mw == 100.0  # Grid reservation = entered value
    assert result.facility_power_mw == 50.0  # 100 / 2.0
    assert result.power_input_mode == PowerInputMode.GRID_RESERVATION


# ─────────────────────────────────────────────────────────────
# Test 3: Power-constrained — power is binding
# ─────────────────────────────────────────────────────────────
def test_power_binding():
    """Small power on large site → power binds.

    5 MW on 50,000 m² site with standard colo at 7 kW/rack:
        IT load from power = 5.0 × 0.950 / 1.38 ≈ 3.442 MW
        Racks by power = 3442 / 7 ≈ 491
        Racks by space = much more (50000 m²)
        Binding = POWER
    """
    site = _make_power_site(power_mw=5.0, land_m2=50000)
    scenario = _make_scenario()
    space = compute_space(site, cooling_type=scenario.cooling_type)
    result = compute_power_constrained(site, scenario, space)

    assert result.binding_constraint == "POWER"
    assert result.racks_by_power is not None
    assert result.racks_by_power < space.effective_racks
    assert result.power_headroom_mw is not None


# ─────────────────────────────────────────────────────────────
# Test 4: Power-constrained — area is binding
# ─────────────────────────────────────────────────────────────
def test_area_binding():
    """Large power on small site → area binds.

    100 MW on 5,000 m² site:
        Racks by space ≈ 333
        Racks by power = much more
        Binding = AREA
    """
    site = _make_power_site(power_mw=100.0, land_m2=5000)
    scenario = _make_scenario()
    space = compute_space(site, cooling_type=scenario.cooling_type)
    result = compute_power_constrained(site, scenario, space)

    assert result.binding_constraint == "AREA"
    assert result.racks_deployed == space.effective_racks


# ─────────────────────────────────────────────────────────────
# Test 5: Area-constrained mode
# ─────────────────────────────────────────────────────────────
def test_area_constrained():
    """No power confirmed — compute required power from space.

    Hand calculation:
        25,000 m² site, defaults → 1666 effective racks
        IT load = 1666 × 7 / 1000 = 11.662 MW
        Facility = 11.662 × 1.38 / 0.950 = 16.929 MW
        Procurement = 16.929 × 2.0 = 33.859 MW
    """
    site = _make_area_site()
    scenario = _make_scenario()
    space = compute_space(site, cooling_type=scenario.cooling_type)
    result = compute_area_constrained(site, scenario, space)

    assert result.it_load_mw == 11.662
    assert result.racks_deployed == 1666
    assert result.binding_constraint == "AREA"
    assert result.racks_by_power is None  # Not applicable
    assert result.power_headroom_mw is None  # Not applicable

    # Verify facility power calculation
    expected_facility = round(11.662 * 1.38 / 0.950, 3)
    assert result.facility_power_mw == expected_facility

    # Verify procurement — computed from unrounded intermediate, not from rounded facility
    expected_procurement = round(11.662 * 1.38 / 0.950 * 2.0, 3)
    assert result.procurement_power_mw == expected_procurement


# ─────────────────────────────────────────────────────────────
# Test 6: Redundancy — N (no redundancy)
# ─────────────────────────────────────────────────────────────
def test_redundancy_n():
    """N redundancy: η=0.970, procurement_factor=1.0."""
    site = _make_area_site()
    scenario = _make_scenario(redundancy=RedundancyLevel.N)
    space = compute_space(site, cooling_type=scenario.cooling_type)
    result = compute_area_constrained(site, scenario, space)

    assert result.eta_chain == 0.970
    assert result.procurement_factor == 1.0
    # Procurement = facility (no multiplier)
    assert result.procurement_power_mw == result.facility_power_mw


# ─────────────────────────────────────────────────────────────
# Test 7: Redundancy — N+1
# ─────────────────────────────────────────────────────────────
def test_redundancy_n_plus_1():
    """N+1 redundancy: η=0.965, procurement_factor=1.15."""
    assert _get_eta_chain("N+1") == 0.965
    assert _get_procurement_factor("N+1") == 1.15


def test_eta_chain_override_changes_power_result(isolated_assumption_overrides):
    """Controlled overrides should change the live engine path, not just Settings payloads."""
    isolated_assumption_overrides.save_assumption_override_updates([
        AssumptionOverrideUpdate(
            key="redundancy.two_n.eta_chain_derate",
            override_value=0.965,
            source="UPS vendor partial-load curve",
            justification="Project-specific UPS selection performs better than the baseline 2N derate.",
        )
    ])

    site = _make_area_site()
    scenario = _make_scenario(redundancy=RedundancyLevel.TWO_N)
    space = compute_space(site, cooling_type=scenario.cooling_type)
    result = compute_area_constrained(site, scenario, space)

    assert result.eta_chain == 0.965
    assert result.procurement_factor == 2.0


# ─────────────────────────────────────────────────────────────
# Test 8: solve() auto-selects mode
# ─────────────────────────────────────────────────────────────
def test_solve_power_mode():
    """solve() should use power-constrained when power is confirmed."""
    site = _make_power_site(power_mw=20.0)
    scenario = _make_scenario()
    space, power = solve(site, scenario)

    assert power.facility_power_mw == 20.0  # Operational mode default


def test_solve_area_mode():
    """solve() should use area-constrained when power is not confirmed."""
    site = _make_area_site()
    scenario = _make_scenario()
    space, power = solve(site, scenario)

    assert power.binding_constraint == "AREA"
    assert power.racks_by_power is None


# ─────────────────────────────────────────────────────────────
# Test 9: PUE override
# ─────────────────────────────────────────────────────────────
def test_pue_override():
    """Manual PUE override should take priority over cooling profile."""
    site = _make_area_site()
    scenario = _make_scenario()
    scenario_with_override = Scenario(
        load_type=LoadType.COLOCATION_STANDARD,
        cooling_type=CoolingType.AIR_CHILLER_ECON,
        pue_override=1.50,
    )
    space = compute_space(site, cooling_type=scenario_with_override.cooling_type)
    result = compute_area_constrained(site, scenario_with_override, space)

    assert result.pue_used == 1.50  # Override, not profile typical (1.38)


# ─────────────────────────────────────────────────────────────
# RAG STATUS TESTS
# ─────────────────────────────────────────────────────────────

def test_rag_red_incompatible():
    """CRAC + AI racks → RED (incompatible combination)."""
    site = _make_power_site(power_mw=50.0, land_m2=50000)
    scenario = _make_scenario(
        load=LoadType.AI_GPU,
        cooling=CoolingType.CRAC_DX,
    )
    _, power = solve(site, scenario)

    assert power.rag_status == RAGStatus.RED
    assert any("not supported" in r for r in power.rag_reasons)


def test_rag_red_density_exceeds():
    """AI at 100 kW/rack on water chillers exceeds the cooling density limit."""
    site = _make_power_site(power_mw=50.0, land_m2=50000)
    scenario = _make_scenario(
        load=LoadType.AI_GPU,
        cooling=CoolingType.WATER_CHILLER_ECON,
        density=DensityScenario.TYPICAL,  # 100 kW
    )
    _, power = solve(site, scenario)

    assert power.rag_status == RAGStatus.RED
    assert any("exceeds" in r for r in power.rag_reasons)


def test_rag_amber_conditional_ai_water_chiller_low_density():
    """Low-density AI on water-cooled chillers is allowed only as an edge case."""
    site = _make_power_site(power_mw=50.0, land_m2=50000)
    scenario = _make_scenario(
        load=LoadType.AI_GPU,
        cooling=CoolingType.WATER_CHILLER_ECON,
        density=DensityScenario.LOW,
    )
    _, power = solve(site, scenario)

    assert power.rag_status == RAGStatus.AMBER
    assert any("conditional edge case" in r.lower() for r in power.rag_reasons)


def test_rag_amber_small_it_load():
    """Very small site → IT load < 1 MW → AMBER."""
    site = Site(
        name="Tiny",
        land_area_m2=500,
        available_power_mw=50.0,
        power_confirmed=True,
    )
    scenario = _make_scenario(
        load=LoadType.EDGE_TELCO,
        cooling=CoolingType.CRAC_DX,
    )
    _, power = solve(site, scenario)

    # Small site with edge telco → few racks, low IT load
    if power.it_load_mw < 1.0:
        assert power.rag_status == RAGStatus.AMBER
        assert any("economically viable" in r for r in power.rag_reasons)


def test_rag_green_normal():
    """Normal viable scenario → GREEN."""
    site = _make_power_site(power_mw=20.0, land_m2=100000)  # Large site so power binds, not area
    scenario = _make_scenario(
        load=LoadType.COLOCATION_STANDARD,
        cooling=CoolingType.AIR_CHILLER_ECON,
    )
    _, power = solve(site, scenario)

    assert power.rag_status in (RAGStatus.GREEN, RAGStatus.BLUE)


def test_rag_blue_excellent():
    """DLC + AI on large site with headroom → BLUE.

    DLC has PUE typical 1.12 (< 1.20) ✓
    Free cooling eligible ✓
    That's 2 criteria → should be BLUE.
    """
    site = _make_power_site(power_mw=100.0, land_m2=100000)
    scenario = _make_scenario(
        load=LoadType.AI_GPU,
        cooling=CoolingType.DLC,
    )
    _, power = solve(site, scenario)

    assert power.rag_status == RAGStatus.BLUE
    assert len(power.rag_reasons) >= 2


def test_rag_amber_mainstream_dry_cooler():
    """Mainstream hyperscale + chiller-less dry cooler stays advisory."""
    site = _make_power_site(power_mw=50.0, land_m2=50000)
    scenario = _make_scenario(
        load=LoadType.HYPERSCALE,
        cooling=CoolingType.DRY_COOLER,
    )
    _, power = solve(site, scenario)

    assert power.rag_status == RAGStatus.AMBER
    assert any("climate-limited niche" in r.lower() for r in power.rag_reasons)


def test_rag_blue_ai_immersion_typical_density():
    """Typical-density AI immersion is a valid liquid-cooling path, not a blanket AMBER."""
    site = _make_power_site(power_mw=100.0, land_m2=100000)
    scenario = _make_scenario(
        load=LoadType.AI_GPU,
        cooling=CoolingType.IMMERSION,
    )
    _, power = solve(site, scenario)

    assert power.rag_status == RAGStatus.BLUE
    assert all("specialized design" not in r.lower() for r in power.rag_reasons)
    assert all("supported for ai/gpu clusters" not in r.lower() for r in power.rag_reasons)


def test_rag_amber_specialized_hpc_immersion_typical_density():
    """Typical-density HPC immersion remains advisory rather than the default baseline."""
    site = _make_power_site(power_mw=50.0, land_m2=50000)
    scenario = _make_scenario(
        load=LoadType.HPC,
        cooling=CoolingType.IMMERSION,
    )
    _, power = solve(site, scenario)

    assert power.rag_status == RAGStatus.AMBER
    assert any("specialized design" in r.lower() for r in power.rag_reasons)


def test_rag_amber_colocation_high_density_dlc():
    """High-density colo with DLC should stay viable but constrained to dedicated suites."""
    site = _make_power_site(power_mw=100.0, land_m2=100000)
    scenario = _make_scenario(
        load=LoadType.COLOCATION_HIGH_DENSITY,
        cooling=CoolingType.DLC,
    )
    _, power = solve(site, scenario)

    assert power.rag_status == RAGStatus.AMBER
    assert any("single-tenant" in r.lower() for r in power.rag_reasons)


def test_hourly_dry_cooler_many_overtemp_hours_escalates_to_red():
    """Hourly robustness can escalate a fragile dry-cooler design to RED."""
    site = _make_power_site(power_mw=50.0, land_m2=50000)
    scenario = _make_scenario(
        load=LoadType.HYPERSCALE,
        cooling=CoolingType.DRY_COOLER,
    )
    _, power = solve(site, scenario)

    adjusted = apply_hourly_rag_adjustments(power, scenario, overtemperature_hours=250)

    assert adjusted.rag_status == RAGStatus.RED
    assert any("250 hours" in r for r in adjusted.rag_reasons)


# ─────────────────────────────────────────────────────────────
# Test: AI racks with DLC (realistic scenario)
# ─────────────────────────────────────────────────────────────
def test_ai_dlc_scenario():
    """50 MW site for AI with DLC cooling.

    This is a realistic scenario: GB200-class racks at 100 kW,
    DLC cooling, 2N redundancy.

    Key checks:
    - IT load should be reasonable (not more than facility power)
    - Procurement should be 2× facility
    - PUE should be DLC typical (1.12)
    """
    site = _make_power_site(power_mw=50.0, land_m2=50000)
    scenario = _make_scenario(
        load=LoadType.AI_GPU,
        cooling=CoolingType.DLC,
    )
    space, power = solve(site, scenario)

    # IT load must be less than facility power
    assert power.it_load_mw < power.facility_power_mw
    # Procurement = 2× facility for 2N
    assert power.procurement_power_mw == round(power.facility_power_mw * 2.0, 3)
    # PUE should be DLC typical
    assert power.pue_used == 1.12
    # DLC whitespace adjustment applied
    assert space.whitespace_adjustment_factor == 0.92
