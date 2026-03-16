"""
Tests for green_energy.py — Green Energy Dispatch Simulation
==============================================================
Every expected value is hand-traced through the 6-step dispatch
algorithm with explicit BESS state-of-charge tracking.

NO random values.
"""

import math
import pytest

from engine.green_energy import (
    DEFAULT_BESS_ROUNDTRIP_EFF,
    DEFAULT_GRID_CO2_KG_PER_KWH,
    GreenEnergyResult,
    HourlyDispatchState,
    find_max_firm_it_capacity,
    find_minimum_bess_capacity,
    recommend_support_portfolios,
    simulate_firm_capacity_support,
    simulate_green_dispatch,
)


# ─────────────────────────────────────────────────────────────
# Reference constants
# ─────────────────────────────────────────────────────────────

ETA_RT = DEFAULT_BESS_ROUNDTRIP_EFF   # 0.875
ETA_OW = math.sqrt(ETA_RT)            # √0.875 ≈ 0.93541
GRID_CO2 = DEFAULT_GRID_CO2_KG_PER_KWH  # 0.256


class TestPVOnlyNoBESS:
    """PV generation only, no BESS, no fuel cell.
    
    3 hours: overhead=[5000, 5000, 5000], PV=[3000, 7000, 0]
    
    Hour 0: overhead=5000, PV=3000
        Step 1: pv_to_overhead=3000, deficit=2000, remaining_pv=0
        Steps 2-5: nothing
        Step 6: grid=2000

    Hour 1: overhead=5000, PV=7000
        Step 1: pv_to_overhead=5000, deficit=0, remaining_pv=2000
        Step 3: curtailed=2000
        Step 6: grid=0

    Hour 2: overhead=5000, PV=0
        Step 1: pv_to_overhead=0, deficit=5000
        Step 6: grid=5000
    """

    def test_dispatch_hour_by_hour(self):
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0, 25000.0, 25000.0],
            hourly_it_kw=[20000.0, 20000.0, 20000.0],
            hourly_pv_kw=[3000.0, 7000.0, 0.0],
        )
        assert len(result.hourly_dispatch) == 3

        h0 = result.hourly_dispatch[0]
        assert h0.overhead_kw == 5000.0
        assert h0.pv_to_overhead_kw == 3000.0
        assert h0.pv_curtailed_kw == 0.0
        assert h0.grid_import_kw == 2000.0

        h1 = result.hourly_dispatch[1]
        assert h1.pv_to_overhead_kw == 5000.0
        assert h1.pv_curtailed_kw == 2000.0
        assert h1.grid_import_kw == 0.0

        h2 = result.hourly_dispatch[2]
        assert h2.pv_to_overhead_kw == 0.0
        assert h2.grid_import_kw == 5000.0

    def test_annual_totals(self):
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0, 25000.0, 25000.0],
            hourly_it_kw=[20000.0, 20000.0, 20000.0],
            hourly_pv_kw=[3000.0, 7000.0, 0.0],
        )
        assert result.total_overhead_kwh == 15000.0
        assert result.total_pv_generation_kwh == 10000.0
        assert result.total_pv_to_overhead_kwh == 8000.0   # 3000+5000+0
        assert result.total_pv_curtailed_kwh == 2000.0
        assert result.total_grid_import_kwh == 7000.0       # 2000+0+5000

    def test_overhead_coverage(self):
        """Green used = 8000 kWh of 15000 kWh overhead → 53.33%."""
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0, 25000.0, 25000.0],
            hourly_it_kw=[20000.0, 20000.0, 20000.0],
            hourly_pv_kw=[3000.0, 7000.0, 0.0],
        )
        assert result.overhead_coverage_fraction == pytest.approx(8000 / 15000, abs=0.0001)

    def test_pv_self_consumption(self):
        """PV used on-site = 8000 of 10000 generated → 80%."""
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0, 25000.0, 25000.0],
            hourly_it_kw=[20000.0, 20000.0, 20000.0],
            hourly_pv_kw=[3000.0, 7000.0, 0.0],
        )
        assert result.pv_self_consumption_fraction == pytest.approx(0.80, abs=0.0001)


class TestBESSChargeDischarge:
    """PV + BESS, no fuel cell. Verify SoC tracking with η_oneway.

    Setup: BESS capacity = 10,000 kWh, η_rt = 0.875, η_ow = √0.875 ≈ 0.93541
    
    4 hours: overhead=[5000, 5000, 5000, 5000]
             PV=      [8000, 8000,    0,    0]
    
    Hour 0: overhead=5000, PV=8000
        Step 1: pv_to_overhead=5000, remaining_pv=3000, deficit=0
        Step 2: charge BESS. headroom=10000, max_charge=10000/0.93541=10690.
                pv_to_bess=3000, SoC += 3000×0.93541 = 2806.23
                SoC = 2806.23
        Step 3: curtailed=0

    Hour 1: overhead=5000, PV=8000 (same)
        Step 1: pv_to_overhead=5000, remaining_pv=3000
        Step 2: headroom=10000-2806.23=7193.77, max_charge=7193.77/0.93541=7691.
                pv_to_bess=3000, SoC += 3000×0.93541 = 2806.23
                SoC = 5612.46
        Step 3: curtailed=0

    Hour 2: overhead=5000, PV=0
        Step 1: pv_to_overhead=0, deficit=5000
        Step 4: max_deliver = 5612.46 × 0.93541 = 5249.82.
                bess_discharge = min(5000, 5249.82) = 5000.
                soc_withdrawn = 5000 / 0.93541 = 5345.37
                SoC = 5612.46 - 5345.37 = 267.09
                deficit = 0
        Step 6: grid=0

    Hour 3: overhead=5000, PV=0
        Step 1: deficit=5000
        Step 4: max_deliver = 267.09 × 0.93541 = 249.82
                bess_discharge = 249.82, deficit = 4750.18
                soc_withdrawn = 249.82 / 0.93541 = 267.09
                SoC = 0
        Step 6: grid = 4750.18
    """

    def setup_method(self):
        self.result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0] * 4,
            hourly_it_kw=[20000.0] * 4,
            hourly_pv_kw=[8000.0, 8000.0, 0.0, 0.0],
            bess_capacity_kwh=10000.0,
            bess_roundtrip_efficiency=ETA_RT,
            bess_initial_soc_kwh=0.0,
        )

    def test_hour_0_charge(self):
        h = self.result.hourly_dispatch[0]
        assert h.pv_to_overhead_kw == 5000.0
        assert h.pv_to_bess_kw == 3000.0
        assert h.pv_curtailed_kw == pytest.approx(0.0, abs=0.01)
        assert h.grid_import_kw == pytest.approx(0.0, abs=0.01)
        # SoC = 3000 × η_ow ≈ 2806.23
        assert h.bess_soc_kwh == pytest.approx(3000 * ETA_OW, abs=0.1)

    def test_hour_1_charge(self):
        h = self.result.hourly_dispatch[1]
        assert h.pv_to_bess_kw == 3000.0
        # SoC = 2 × 3000 × η_ow ≈ 5612.46
        assert h.bess_soc_kwh == pytest.approx(2 * 3000 * ETA_OW, abs=0.1)

    def test_hour_2_discharge(self):
        h = self.result.hourly_dispatch[2]
        assert h.pv_to_overhead_kw == 0.0
        # BESS covers the full 5000 deficit (has enough)
        assert h.bess_discharge_kw == pytest.approx(5000.0, abs=0.1)
        assert h.grid_import_kw == pytest.approx(0.0, abs=0.1)
        # SoC after = 5612.46 - 5000/η_ow
        expected_soc = 2 * 3000 * ETA_OW - 5000 / ETA_OW
        assert h.bess_soc_kwh == pytest.approx(expected_soc, abs=0.2)

    def test_hour_3_partial_discharge(self):
        h = self.result.hourly_dispatch[3]
        # BESS can only deliver what's left (SoC × η_ow)
        soc_before = 2 * 3000 * ETA_OW - 5000 / ETA_OW
        max_deliver = soc_before * ETA_OW
        assert h.bess_discharge_kw == pytest.approx(max_deliver, abs=0.2)
        # Grid covers the rest
        expected_grid = 5000 - max_deliver
        assert h.grid_import_kw == pytest.approx(expected_grid, abs=0.2)
        # SoC should be 0 (fully drained)
        assert h.bess_soc_kwh == pytest.approx(0.0, abs=0.1)


class TestFuelCellDispatch:
    """PV + BESS + Fuel Cell.

    1 hour: overhead=5000, PV=0, BESS empty, FC capacity=2000.
    
    Step 1: deficit=5000
    Step 4: BESS empty → discharge=0
    Step 5: FC = min(5000, 2000) = 2000, deficit=3000
    Step 6: grid=3000
    """

    def test_fuel_cell_caps_at_capacity(self):
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0],
            hourly_it_kw=[20000.0],
            hourly_pv_kw=[0.0],
            bess_capacity_kwh=0.0,
            fuel_cell_capacity_kw=2000.0,
        )
        h = result.hourly_dispatch[0]
        assert h.fuel_cell_kw == 2000.0
        assert h.grid_import_kw == 3000.0

    def test_fuel_cell_covers_all_if_large_enough(self):
        """FC capacity ≥ overhead → grid import = 0."""
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0],
            hourly_it_kw=[20000.0],
            hourly_pv_kw=[0.0],
            fuel_cell_capacity_kw=6000.0,
        )
        h = result.hourly_dispatch[0]
        assert h.fuel_cell_kw == 5000.0
        assert h.grid_import_kw == 0.0


class TestFullDispatchChain:
    """All three sources: PV + BESS + FC working together.

    2 hours: overhead=[5000, 5000], PV=[3000, 0],
             BESS=5000 kWh, FC=1000 kW
    
    Hour 0: overhead=5000, PV=3000
        Step 1: pv_to_overhead=3000, deficit=2000, remaining_pv=0
        Step 2: no surplus PV
        Step 4: BESS empty (SoC=0) → discharge=0
        Step 5: FC = min(2000, 1000) = 1000, deficit=1000
        Step 6: grid=1000

    Hour 1: overhead=5000, PV=0
        Step 1: deficit=5000
        Step 4: BESS still empty → 0
        Step 5: FC = 1000, deficit=4000
        Step 6: grid=4000
    """

    def test_combined_dispatch(self):
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0, 25000.0],
            hourly_it_kw=[20000.0, 20000.0],
            hourly_pv_kw=[3000.0, 0.0],
            bess_capacity_kwh=5000.0,
            bess_initial_soc_kwh=0.0,
            fuel_cell_capacity_kw=1000.0,
        )
        h0 = result.hourly_dispatch[0]
        assert h0.pv_to_overhead_kw == 3000.0
        assert h0.fuel_cell_kw == 1000.0
        assert h0.grid_import_kw == pytest.approx(1000.0, abs=0.1)

        h1 = result.hourly_dispatch[1]
        assert h1.fuel_cell_kw == 1000.0
        assert h1.grid_import_kw == pytest.approx(4000.0, abs=0.1)

    def test_totals(self):
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0, 25000.0],
            hourly_it_kw=[20000.0, 20000.0],
            hourly_pv_kw=[3000.0, 0.0],
            bess_capacity_kwh=5000.0,
            bess_initial_soc_kwh=0.0,
            fuel_cell_capacity_kw=1000.0,
        )
        # Total green = PV(3000) + FC(1000+1000) = 5000
        # Total overhead = 10000
        assert result.total_pv_to_overhead_kwh == 3000.0
        assert result.total_fuel_cell_kwh == 2000.0
        assert result.overhead_coverage_fraction == pytest.approx(5000 / 10000, abs=0.001)


class TestEnergyBalance:
    """For every scenario, energy must balance:
    overhead = pv_to_overhead + bess_discharge + fuel_cell + grid_import.

    This is the fundamental conservation law.
    """

    def test_balance_pv_only(self):
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0] * 24,
            hourly_it_kw=[20000.0] * 24,
            hourly_pv_kw=[3000.0] * 12 + [0.0] * 12,
        )
        supplied = (
            result.total_pv_to_overhead_kwh
            + result.total_bess_discharge_kwh
            + result.total_fuel_cell_kwh
            + result.total_grid_import_kwh
        )
        assert supplied == pytest.approx(result.total_overhead_kwh, abs=0.1)

    def test_balance_all_sources(self):
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0] * 24,
            hourly_it_kw=[20000.0] * 24,
            hourly_pv_kw=[8000.0] * 12 + [0.0] * 12,
            bess_capacity_kwh=20000.0,
            fuel_cell_capacity_kw=1000.0,
        )
        supplied = (
            result.total_pv_to_overhead_kwh
            + result.total_bess_discharge_kwh
            + result.total_fuel_cell_kwh
            + result.total_grid_import_kwh
        )
        assert supplied == pytest.approx(result.total_overhead_kwh, abs=1.0)

    def test_pv_balance(self):
        """PV generation = pv_to_overhead + pv_to_bess + pv_curtailed."""
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0] * 24,
            hourly_it_kw=[20000.0] * 24,
            hourly_pv_kw=[8000.0] * 12 + [0.0] * 12,
            bess_capacity_kwh=10000.0,
        )
        pv_accounted = (
            result.total_pv_to_overhead_kwh
            + result.total_pv_to_bess_kwh
            + result.total_pv_curtailed_kwh
        )
        assert pv_accounted == pytest.approx(result.total_pv_generation_kwh, abs=0.1)


class TestBESSCycles:
    """Verify equivalent cycle count."""

    def test_one_full_cycle(self):
        """Charge 10000 kWh (stored), discharge all → ~0.9354 cycles.

        Need overhead large enough to fully drain the BESS.
        Use facility=30000, IT=20000 → overhead=10000 kW per hour.

        Hour 0: PV=30000, overhead=10000.
            Step 1: pv_to_overhead=10000, remaining_pv=20000
            Step 2: BESS charges to SoC=10000 (fills up completely)
            Step 3: curtail the rest

        Hour 1: PV=0, overhead=10000.
            Step 4: max_deliver = 10000 × η_ow ≈ 9354.
                    discharge = min(10000, 9354) = 9354.
                    BESS fully drained (SoC → 0).
            Step 6: grid = 10000 - 9354 = 646

        cycles = 9354 / 10000 = η_ow ≈ 0.9354
        """
        result = simulate_green_dispatch(
            hourly_facility_kw=[30000.0, 30000.0],
            hourly_it_kw=[20000.0, 20000.0],
            hourly_pv_kw=[30000.0, 0.0],  # Huge PV hour 0, none hour 1
            bess_capacity_kwh=10000.0,
        )
        # BESS fully charged then fully drained
        assert result.bess_cycles_equivalent == pytest.approx(ETA_OW, abs=0.01)


class TestCO2Avoided:
    """Verify CO₂ avoidance calculation."""

    def test_co2_with_known_green_kwh(self):
        """3 hours, PV covers 8000 kWh of overhead.
        CO₂ avoided = 8000 × 0.256 / 1000 = 2.048 tonnes.
        """
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0, 25000.0, 25000.0],
            hourly_it_kw=[20000.0, 20000.0, 20000.0],
            hourly_pv_kw=[3000.0, 7000.0, 0.0],
        )
        # Green used = pv_to_overhead = 3000+5000+0 = 8000
        expected_co2 = 8000 * GRID_CO2 / 1000  # 2.048
        assert result.co2_avoided_tonnes == pytest.approx(expected_co2, abs=0.01)

    def test_co2_with_custom_factor(self):
        """Custom grid factor: 0.5 kg/kWh."""
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0],
            hourly_it_kw=[20000.0],
            hourly_pv_kw=[5000.0],  # Covers all overhead
            grid_co2_kg_per_kwh=0.5,
        )
        # Green = 5000 kWh. CO₂ = 5000 × 0.5 / 1000 = 2.5 tonnes
        assert result.co2_avoided_tonnes == pytest.approx(2.5, abs=0.01)


class TestZeroInputs:
    """Edge case: no green sources installed."""

    def test_no_pv_no_bess_no_fc(self):
        """All zeros → grid imports everything."""
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0] * 24,
            hourly_it_kw=[20000.0] * 24,
            hourly_pv_kw=[0.0] * 24,
        )
        assert result.total_pv_generation_kwh == 0.0
        assert result.total_grid_import_kwh == result.total_overhead_kwh
        assert result.overhead_coverage_fraction == 0.0
        assert result.renewable_fraction == 0.0
        assert result.co2_avoided_tonnes == 0.0

    def test_zero_overhead(self):
        """If facility = IT (PUE = 1.0), overhead = 0, nothing to dispatch.

        With no BESS, all PV is curtailed since there is no overhead to offset.
        (If BESS were present, surplus PV would charge it per Step 2 — that's
        correct dispatch behavior but not what this test verifies.)
        """
        result = simulate_green_dispatch(
            hourly_facility_kw=[20000.0] * 24,
            hourly_it_kw=[20000.0] * 24,
            hourly_pv_kw=[5000.0] * 24,
            bess_capacity_kwh=0.0,  # No BESS — all PV is curtailed
        )
        assert result.total_overhead_kwh == 0.0
        # All PV is curtailed (no overhead to offset, no BESS to charge)
        assert result.total_pv_curtailed_kwh == result.total_pv_generation_kwh

    def test_zero_overhead_with_bess_charges(self):
        """With BESS present and zero overhead, surplus PV charges BESS.

        This is correct behavior: Step 2 (charge BESS) runs before
        Step 3 (curtail), so the BESS absorbs PV even when overhead=0.
        PV balance must still hold: gen = to_overhead + to_bess + curtailed.
        """
        result = simulate_green_dispatch(
            hourly_facility_kw=[20000.0] * 24,
            hourly_it_kw=[20000.0] * 24,
            hourly_pv_kw=[5000.0] * 24,
            bess_capacity_kwh=10000.0,
        )
        assert result.total_overhead_kwh == 0.0
        assert result.total_pv_to_overhead_kwh == 0.0
        # BESS absorbs some PV before it fills up
        assert result.total_pv_to_bess_kwh > 0
        # PV balance still holds
        pv_accounted = (
            result.total_pv_to_overhead_kwh
            + result.total_pv_to_bess_kwh
            + result.total_pv_curtailed_kwh
        )
        assert pv_accounted == pytest.approx(result.total_pv_generation_kwh, abs=0.1)


class TestInputValidation:
    """Input validation edge cases."""

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError, match="length"):
            simulate_green_dispatch(
                hourly_facility_kw=[25000.0] * 10,
                hourly_it_kw=[20000.0] * 8,  # Wrong length
                hourly_pv_kw=[0.0] * 10,
            )

    def test_negative_bess_capacity_raises(self):
        with pytest.raises(ValueError, match="bess_capacity_kwh cannot be negative"):
            simulate_green_dispatch(
                hourly_facility_kw=[25000.0],
                hourly_it_kw=[20000.0],
                hourly_pv_kw=[0.0],
                bess_capacity_kwh=-1000.0,
            )

    def test_soc_exceeds_capacity_raises(self):
        with pytest.raises(ValueError, match="bess_initial_soc_kwh"):
            simulate_green_dispatch(
                hourly_facility_kw=[25000.0],
                hourly_it_kw=[20000.0],
                hourly_pv_kw=[0.0],
                bess_capacity_kwh=5000.0,
                bess_initial_soc_kwh=6000.0,
            )

    def test_invalid_efficiency_raises(self):
        with pytest.raises(ValueError, match="bess_roundtrip_efficiency"):
            simulate_green_dispatch(
                hourly_facility_kw=[25000.0],
                hourly_it_kw=[20000.0],
                hourly_pv_kw=[0.0],
                bess_capacity_kwh=5000.0,
                bess_roundtrip_efficiency=1.5,
            )

    def test_negative_fc_capacity_raises(self):
        with pytest.raises(ValueError, match="fuel_cell_capacity_kw cannot be negative"):
            simulate_green_dispatch(
                hourly_facility_kw=[25000.0],
                hourly_it_kw=[20000.0],
                hourly_pv_kw=[0.0],
                fuel_cell_capacity_kw=-100.0,
            )


class TestRenewableFraction:
    """Verify renewable_fraction = green_used / total_facility."""

    def test_renewable_fraction_calculation(self):
        """1 hour: facility=25000, IT=20000, PV=5000 (covers all overhead).
        Green used = 5000. Renewable fraction = 5000/25000 = 0.20.
        """
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0],
            hourly_it_kw=[20000.0],
            hourly_pv_kw=[5000.0],
        )
        assert result.renewable_fraction == pytest.approx(5000 / 25000, abs=0.0001)


class TestConfigurationEcho:
    """Verify that input configuration is echoed in the result."""

    def test_config_echoed(self):
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0],
            hourly_it_kw=[20000.0],
            hourly_pv_kw=[3000.0],
            bess_capacity_kwh=10000.0,
            bess_roundtrip_efficiency=0.90,
            fuel_cell_capacity_kw=2000.0,
            pv_capacity_kwp=500.0,
        )
        assert result.pv_capacity_kwp == 500.0
        assert result.bess_capacity_kwh == 10000.0
        assert result.bess_roundtrip_efficiency == 0.90
        assert result.fuel_cell_capacity_kw == 2000.0
        assert result.total_facility_kwh == 25000.0
        assert result.total_it_kwh == 20000.0


class TestBESSInitialSoC:
    """Test starting with non-zero BESS state of charge."""

    def test_initial_soc_available_for_discharge(self):
        """Start with SoC=5000, no PV → BESS discharges immediately.
        
        Hour 0: overhead=5000, SoC=5000.
        max_deliver = 5000 × η_ow ≈ 4677
        discharge = 4677, deficit = 323
        grid = 323
        """
        result = simulate_green_dispatch(
            hourly_facility_kw=[25000.0],
            hourly_it_kw=[20000.0],
            hourly_pv_kw=[0.0],
            bess_capacity_kwh=10000.0,
            bess_initial_soc_kwh=5000.0,
        )
        h = result.hourly_dispatch[0]
        expected_discharge = 5000 * ETA_OW
        assert h.bess_discharge_kw == pytest.approx(expected_discharge, abs=0.1)
        assert h.grid_import_kw == pytest.approx(5000 - expected_discharge, abs=0.1)


class TestFirmCapacitySupport:
    """Peak-support solver for maintaining a constant IT target."""

    FACTORS = [0.875, 1.5]
    GRID_KW = 100.0

    def test_without_support_target_is_infeasible(self):
        """Target 80 kW IT needs 70 kW then 120 kW facility.

        With a 100 kW grid cap and no support assets:
        - Hour 0: 30 kW headroom, no deficit
        - Hour 1: 20 kW unmet
        """
        result = simulate_firm_capacity_support(
            hourly_facility_factors=self.FACTORS,
            target_it_kw=80.0,
            grid_capacity_kw=self.GRID_KW,
            cyclic_bess=False,
        )
        assert result.feasible is False
        assert result.hours_above_grid_cap == 1
        assert result.unmet_hours == 1
        assert result.peak_unmet_kw == pytest.approx(20.0, abs=0.001)
        assert result.total_unmet_kwh == pytest.approx(20.0, abs=0.001)

    def test_bess_charges_from_grid_headroom_and_covers_peak(self):
        """Hour 0 headroom charges the BESS; hour 1 discharge covers the deficit.

        Target = 80 kW
        Required facility:
            h0 = 80 × 0.875 = 70 kW
            h1 = 80 × 1.5   = 120 kW

        Hour 0:
            grid_to_load = 70
            grid headroom = 30
            BESS charge input = 30
            SoC = 30 × η_ow

        Hour 1:
            deficit before support = 20
            BESS discharge = 20
            final SoC = 30×η_ow − 20/η_ow
        """
        result = simulate_firm_capacity_support(
            hourly_facility_factors=self.FACTORS,
            target_it_kw=80.0,
            grid_capacity_kw=self.GRID_KW,
            bess_capacity_kwh=50.0,
            cyclic_bess=False,
        )
        assert result.feasible is True
        h0 = result.hourly_dispatch[0]
        h1 = result.hourly_dispatch[1]
        assert h0.grid_to_load_kw == pytest.approx(70.0, abs=0.001)
        assert h0.grid_to_bess_kw == pytest.approx(30.0, abs=0.001)
        assert h1.bess_discharge_kw == pytest.approx(20.0, abs=0.001)
        expected_final_soc = 30.0 * ETA_OW - 20.0 / ETA_OW
        assert result.final_bess_soc_kwh == pytest.approx(expected_final_soc, abs=0.01)
        assert result.total_unmet_kwh == pytest.approx(0.0, abs=0.001)

    def test_dispatchable_sources_cover_remaining_deficit(self):
        """Fuel cell and backup dispatch combine after BESS in deficit hours."""
        result = simulate_firm_capacity_support(
            hourly_facility_factors=[1.5],
            target_it_kw=80.0,
            grid_capacity_kw=self.GRID_KW,
            fuel_cell_capacity_kw=10.0,
            backup_dispatch_capacity_kw=10.0,
            cyclic_bess=False,
        )
        assert result.feasible is True
        h = result.hourly_dispatch[0]
        assert h.fuel_cell_kw == pytest.approx(10.0, abs=0.001)
        assert h.backup_dispatch_kw == pytest.approx(10.0, abs=0.001)
        assert h.unmet_kw == pytest.approx(0.0, abs=0.001)

    def test_find_max_firm_it_capacity_with_bess(self):
        """Solve the exact headroom-vs-deficit balance point.

        With factors [0.875, 1.5], grid cap 100, and a large enough BESS:

            deficit(h1) = 1.5x - 100
            headroom(h0) = 100 - 0.875x
            BESS deliverable = headroom × η_rt

        Feasibility limit:
            1.5x - 100 = (100 - 0.875x) × 0.875
            x = 187.5 / 2.265625 = 82.7586 kW
        """
        result = find_max_firm_it_capacity(
            hourly_facility_factors=self.FACTORS,
            grid_capacity_kw=self.GRID_KW,
            max_it_kw=100.0,
            bess_capacity_kwh=50.0,
            cyclic_bess=False,
            resolution_kw=0.001,
        )
        assert result.feasible is True
        assert result.target_it_kw == pytest.approx(82.7586, abs=0.01)


class TestSupportRecommendations:
    """Deterministic recommendation layer built on the firm-capacity solver."""

    FACTORS = [0.875, 1.5]
    GRID_KW = 100.0
    TARGET_KW = 80.0

    def test_minimum_bess_capacity_solves_same_20_kw_peak(self):
        """BESS-only solution must be solved, not guessed.

        For the 2-hour micro-case:
        - Hour 0 headroom = 30 kWh available for charging
        - Hour 1 deficit = 20 kWh

        So a feasible BESS-only solution exists and must require less than
        the available 30 kWh charging window.
        """
        solved = find_minimum_bess_capacity(
            hourly_facility_factors=self.FACTORS,
            target_it_kw=self.TARGET_KW,
            grid_capacity_kw=self.GRID_KW,
            cyclic_bess=False,
            resolution_kwh=0.001,
        )
        assert solved is not None
        bess_kwh, result = solved
        assert result.feasible is True
        assert bess_kwh > 0
        assert bess_kwh < 30.0

    def test_recommendations_include_exact_dispatch_pathways(self):
        """Dispatch-only recommendations must use the exact worst-hour deficit."""
        recommendations = recommend_support_portfolios(
            hourly_facility_factors=self.FACTORS,
            target_it_kw=self.TARGET_KW,
            grid_capacity_kw=self.GRID_KW,
            baseline_p99_kw=70.0,
            baseline_worst_kw=60.0,
            cyclic_bess=False,
        )
        assert recommendations.target_already_feasible is False
        assert recommendations.peak_support_kw == pytest.approx(20.0, abs=0.001)
        assert recommendations.gap_vs_p99_kw == pytest.approx(10.0, abs=0.001)
        assert recommendations.gap_vs_worst_kw == pytest.approx(20.0, abs=0.001)

        fuel_cell = next(c for c in recommendations.candidates if c.key == "fuel_cell_only")
        backup = next(c for c in recommendations.candidates if c.key == "backup_only")

        assert fuel_cell.fuel_cell_capacity_kw == pytest.approx(20.0, abs=0.001)
        assert fuel_cell.feasible is True
        assert backup.backup_dispatch_capacity_kw == pytest.approx(20.0, abs=0.001)
        assert backup.feasible is True

    def test_hybrid_recommendation_uses_mean_deficit(self):
        """Hybrid FC+BESS must size FC from the exact mean deficit."""
        recommendations = recommend_support_portfolios(
            hourly_facility_factors=[0.5, 0.5, 1.2, 1.5],
            target_it_kw=100.0,
            grid_capacity_kw=self.GRID_KW,
            baseline_p99_kw=80.0,
            baseline_worst_kw=60.0,
            cyclic_bess=False,
        )
        hybrid = next(c for c in recommendations.candidates if c.key == "hybrid_fc_bess")
        # Deficits are 20 kW and 50 kW -> mean deficit = 35 kW.
        assert hybrid.fuel_cell_capacity_kw == pytest.approx(35.0, abs=0.001)
        assert hybrid.bess_capacity_kwh > 0.0
        assert hybrid.feasible is True
