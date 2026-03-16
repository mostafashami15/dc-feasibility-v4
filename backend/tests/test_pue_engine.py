"""
DC Feasibility Tool v4 — Tests for pue_engine.py
==================================================
Every expected value is hand-calculated from Architecture Agreement
formulas. Uses a 4-hour micro-dataset for tractable arithmetic.

Test structure:
    1. Area-constrained simulation (P_IT fixed)
    2. Power-constrained simulation (P_facility fixed)
    3. IT capacity spectrum and percentiles
    4. Cooling mode breakdown
    5. Overtemperature tracking (dry cooler)
    6. Edge cases and validation
    7. Consistency checks
"""

import pytest

from engine.pue_engine import (
    HourlySimResult,
    _percentile_low,
    build_hourly_facility_factors,
    simulate_hourly,
)


# ═════════════════════════════════════════════════════════════
# Common test fixtures
# ═════════════════════════════════════════════════════════════
# 4-hour micro-dataset covering all 3 cooling modes for
# Air-Cooled Chiller + Economizer.
# Thresholds: T_econ_full=14°C, T_mech=22°C

WEATHER_4H_TEMPS = [10.0, 18.0, 30.0, 35.0]
WEATHER_4H_RH = None  # Air-cooled, no RH needed

COOLING_TYPE = "Air-Cooled Chiller + Economizer"
ETA_CHAIN = 0.95
F_MISC = 0.025

# Expected modes per hour:
# Hour 0: 10°C ≤ 14 → ECON_FULL
# Hour 1: 14 < 18 ≤ 22 → ECON_PART
# Hour 2: 30 > 22 → MECH
# Hour 3: 35 > 22 → MECH


# ═════════════════════════════════════════════════════════════
# 1. AREA-CONSTRAINED SIMULATION
# ═════════════════════════════════════════════════════════════
# P_IT = 10,000 kW (fixed), compute P_facility(t) per hour.
#
# Hand-calculated values:
# elec_loss = 1/0.95 - 1 = 0.052632
# numerator = 1 + 0.052632 + 0.05 + 0.025 = 1.127632 (for heat rejection)
# b = 10000 × 0.025 = 250 kW
#
# Hour 0: ECON_FULL, cool=0, k_econ=0.015
#   a(0) = 0.052632 + 0.05 + 0 + 0.015 = 0.117632
#   P_fac = 10000×(1+0.117632) + 250 = 11426.32 kW
#
# Hour 1: ECON_PART, COP=8.05, blend=0.5
#   cool = 0.5 × (1.127632/8.05) = 0.070039
#   a(1) = 0.052632 + 0.05 + 0.070039 + 0.015 = 0.187671
#   P_fac = 10000×(1+0.187671) + 250 = 12126.71 kW
#
# Hour 2: MECH, COP=6.25
#   cool = 1.127632/6.25 = 0.180421
#   a(2) = 0.052632 + 0.05 + 0.180421 + 0 = 0.283053
#   P_fac = 10000×(1+0.283053) + 250 = 13080.53 kW
#
# Hour 3: MECH, COP=5.5
#   cool = 1.127632/5.5 = 0.205024
#   a(3) = 0.052632 + 0.05 + 0.205024 + 0 = 0.307656
#   P_fac = 10000×(1+0.307656) + 250 = 13326.56 kW
#
# Annual PUE = (11426.32+12126.71+13080.53+13326.56) / (4×10000)
#            = 49960.11 / 40000 = 1.249003

class TestAreaConstrained:
    """Tests for area-constrained mode (P_IT fixed)."""

    def setup_method(self):
        """Run the simulation once for all tests in this class."""
        self.result = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=WEATHER_4H_RH,
            cooling_type=COOLING_TYPE,
            eta_chain=ETA_CHAIN,
            it_load_kw=10000.0,
            f_misc=F_MISC,
        )

    def test_annual_pue(self):
        """Energy-weighted annual PUE = 1.249003."""
        assert self.result.annual_pue == pytest.approx(1.249003, abs=1e-4)

    def test_total_facility_kwh(self):
        """Sum of facility power across all hours."""
        assert self.result.total_facility_kwh == pytest.approx(49960.1, abs=1.0)

    def test_total_it_kwh(self):
        """IT energy = 4 hours × 10,000 kW = 40,000 kWh."""
        assert self.result.total_it_kwh == pytest.approx(40000.0, abs=0.1)

    def test_it_constant_in_area_mode(self):
        """IT load is constant at 10,000 kW every hour."""
        for kw in self.result.hourly_it_kw:
            assert kw == pytest.approx(10000.0, abs=0.1)

    def test_facility_power_hour_0(self):
        """Hour 0 (ECON_FULL): P_fac = 11426.32 kW."""
        assert self.result.hourly_facility_kw[0] == pytest.approx(11426.3, abs=1.0)

    def test_facility_power_hour_1(self):
        """Hour 1 (ECON_PART): P_fac = 12126.71 kW."""
        assert self.result.hourly_facility_kw[1] == pytest.approx(12126.7, abs=1.0)

    def test_facility_power_hour_2(self):
        """Hour 2 (MECH): P_fac = 13080.53 kW."""
        assert self.result.hourly_facility_kw[2] == pytest.approx(13080.5, abs=1.0)

    def test_facility_power_hour_3(self):
        """Hour 3 (MECH): P_fac = 13326.56 kW."""
        assert self.result.hourly_facility_kw[3] == pytest.approx(13326.6, abs=1.0)

    def test_facility_power_increases_with_temperature(self):
        """Hotter hours need more facility power (more cooling)."""
        fac = self.result.hourly_facility_kw
        assert fac[0] < fac[1] < fac[2] < fac[3]

    def test_pue_increases_with_temperature(self):
        """PUE is higher in hotter hours (less efficient cooling)."""
        pue = self.result.hourly_pue
        assert pue[0] < pue[1] < pue[2] < pue[3]


# ═════════════════════════════════════════════════════════════
# 2. POWER-CONSTRAINED SIMULATION
# ═════════════════════════════════════════════════════════════
# P_facility = 15,000 kW (fixed), compute P_IT(t) per hour.
#
# b = 15000 × 0.025 = 375 kW
#
# Hour 0: P_IT = (15000−375) / (1+0.117632) = 13085.71 kW
# Hour 1: P_IT = (15000−375) / (1+0.187671) = 12314.02 kW
# Hour 2: P_IT = (15000−375) / (1+0.283053) = 11398.60 kW
# Hour 3: P_IT = (15000−375) / (1+0.307656) = 11184.14 kW
#
# Annual PUE = (4×15000) / (13085.71+12314.02+11398.60+11184.14)
#            = 60000 / 47982.46 = 1.250457

class TestPowerConstrained:
    """Tests for power-constrained mode (P_facility fixed)."""

    def setup_method(self):
        self.result = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=WEATHER_4H_RH,
            cooling_type=COOLING_TYPE,
            eta_chain=ETA_CHAIN,
            facility_power_kw=15000.0,
            f_misc=F_MISC,
        )

    def test_annual_pue(self):
        """Energy-weighted annual PUE = 1.250457."""
        assert self.result.annual_pue == pytest.approx(1.2505, abs=1e-3)

    def test_total_facility_kwh(self):
        """Facility energy = 4 × 15,000 = 60,000 kWh."""
        assert self.result.total_facility_kwh == pytest.approx(60000.0, abs=0.1)

    def test_total_it_kwh(self):
        """Sum of IT energy across all hours."""
        assert self.result.total_it_kwh == pytest.approx(47982.5, abs=1.0)

    def test_facility_constant_in_power_mode(self):
        """Facility power is constant at 15,000 kW every hour."""
        for kw in self.result.hourly_facility_kw:
            assert kw == pytest.approx(15000.0, abs=0.1)

    def test_it_load_hour_0(self):
        """Hour 0 (ECON_FULL): P_IT = 13085.71 kW (most IT available)."""
        assert self.result.hourly_it_kw[0] == pytest.approx(13085.7, abs=1.0)

    def test_it_load_hour_3(self):
        """Hour 3 (MECH, hot): P_IT = 11184.14 kW (least IT available)."""
        assert self.result.hourly_it_kw[3] == pytest.approx(11184.1, abs=1.0)

    def test_it_decreases_with_temperature(self):
        """Hotter hours have less available IT (more power to cooling)."""
        it = self.result.hourly_it_kw
        assert it[0] > it[1] > it[2] > it[3]


# ═════════════════════════════════════════════════════════════
# 3. IT CAPACITY SPECTRUM
# ═════════════════════════════════════════════════════════════

class TestITCapacitySpectrum:
    """Test the IT capacity spectrum for power-constrained mode."""

    def setup_method(self):
        self.result = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=WEATHER_4H_RH,
            cooling_type=COOLING_TYPE,
            eta_chain=ETA_CHAIN,
            facility_power_kw=15000.0,
            f_misc=F_MISC,
        )

    def test_worst_is_minimum(self):
        """Worst = minimum IT across all hours = 11184.14 kW."""
        assert self.result.it_capacity_worst_kw == pytest.approx(11184.1, abs=1.0)

    def test_best_is_maximum(self):
        """Best = maximum IT = 13085.71 kW."""
        assert self.result.it_capacity_best_kw == pytest.approx(13085.7, abs=1.0)

    def test_mean(self):
        """Mean IT = sum / 4 = 11995.62 kW."""
        assert self.result.it_capacity_mean_kw == pytest.approx(11995.6, abs=1.0)

    def test_worst_less_than_mean(self):
        """Worst case is always below the mean."""
        assert self.result.it_capacity_worst_kw < self.result.it_capacity_mean_kw

    def test_mean_less_than_best(self):
        """Mean is always below best case."""
        assert self.result.it_capacity_mean_kw < self.result.it_capacity_best_kw

    def test_area_mode_spectrum_all_equal(self):
        """In area-constrained mode, all spectrum values = fixed IT."""
        result = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=WEATHER_4H_RH,
            cooling_type=COOLING_TYPE,
            eta_chain=ETA_CHAIN,
            it_load_kw=10000.0,
        )
        assert result.it_capacity_worst_kw == pytest.approx(10000.0, abs=0.1)
        assert result.it_capacity_best_kw == pytest.approx(10000.0, abs=0.1)
        assert result.it_capacity_mean_kw == pytest.approx(10000.0, abs=0.1)


# ═════════════════════════════════════════════════════════════
# 4. PERCENTILE HELPER
# ═════════════════════════════════════════════════════════════

class TestPercentile:
    """Test the _percentile_low helper function."""

    def test_p1_of_100_values(self):
        """P1 of [1..100] → index floor(100×0.01) = 1 → value 2."""
        vals = list(range(1, 101))  # [1, 2, ..., 100]
        assert _percentile_low(vals, 1.0) == 2

    def test_p10_of_100_values(self):
        """P10 of [1..100] → index floor(100×0.10) = 10 → value 11."""
        vals = list(range(1, 101))
        assert _percentile_low(vals, 10.0) == 11

    def test_p0_returns_first(self):
        """P0 → index 0 → smallest value."""
        vals = [5, 10, 15, 20]
        assert _percentile_low(vals, 0.0) == 5

    def test_single_value(self):
        """Single-element list → always returns that value."""
        assert _percentile_low([42.0], 1.0) == 42.0
        assert _percentile_low([42.0], 50.0) == 42.0

    def test_empty_raises(self):
        """Empty list raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            _percentile_low([], 1.0)


# ═════════════════════════════════════════════════════════════
# 5. COOLING MODE BREAKDOWN
# ═════════════════════════════════════════════════════════════

class TestModeBreakdown:
    """Test cooling mode hour counts and energy fractions."""

    def setup_method(self):
        self.result = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=WEATHER_4H_RH,
            cooling_type=COOLING_TYPE,
            eta_chain=ETA_CHAIN,
            it_load_kw=10000.0,
        )

    def test_mech_hours(self):
        """2 hours in MECH (30°C and 35°C > T_mech=22°C)."""
        assert self.result.mech_hours == 2

    def test_econ_part_hours(self):
        """1 hour in ECON_PART (18°C: 14 < 18 ≤ 22)."""
        assert self.result.econ_part_hours == 1

    def test_econ_full_hours(self):
        """1 hour in ECON_FULL (10°C ≤ 14)."""
        assert self.result.econ_full_hours == 1

    def test_hours_sum_to_total(self):
        """Mode hours must sum to total hours."""
        total = self.result.mech_hours + self.result.econ_part_hours + self.result.econ_full_hours
        assert total == 4

    def test_hourly_mode_strings(self):
        """Verify the per-hour mode strings."""
        assert self.result.hourly_mode == ["ECON_FULL", "ECON_PART", "MECH", "MECH"]

    def test_mech_energy_fraction(self):
        """MECH carries ~84.6% of cooling energy.
        MECH cooling = 0.180421 + 0.205024 = 0.385445
        Total cooling = 0.385445 + 0.070039 = 0.455484
        Fraction = 0.385445 / 0.455484 = 0.846231
        """
        assert self.result.mech_energy_frac == pytest.approx(0.8462, abs=1e-3)

    def test_econ_part_energy_fraction(self):
        """ECON_PART carries ~15.4% of cooling energy."""
        assert self.result.econ_part_energy_frac == pytest.approx(0.1538, abs=1e-3)

    def test_econ_full_energy_always_zero(self):
        """ECON_FULL contributes 0% cooling energy (compressor off)."""
        assert self.result.econ_full_energy_frac == 0.0

    def test_energy_fractions_sum_to_one(self):
        """MECH + ECON_PART + ECON_FULL energy fractions = 1.0 (or 0 if all ECON_FULL)."""
        total = (self.result.mech_energy_frac
                 + self.result.econ_part_energy_frac
                 + self.result.econ_full_energy_frac)
        assert total == pytest.approx(1.0, abs=1e-4)


# ═════════════════════════════════════════════════════════════
# 6. OVERTEMPERATURE TRACKING
# ═════════════════════════════════════════════════════════════

class TestOvertemperature:
    """Test overtemperature detection for dry cooler topology."""

    def test_no_overtemp_with_chiller(self):
        """Air Chiller never reports overtemperature (has compressor)."""
        result = simulate_hourly(
            temperatures=[40.0, 42.0, 45.0],
            humidities=None,
            cooling_type="Air-Cooled Chiller + Economizer",
            eta_chain=0.95,
            it_load_kw=5000.0,
        )
        assert result.overtemperature_hours == 0

    def test_dry_cooler_overtemp(self):
        """Dry cooler at 35°C (> ASE_DB=30°C) → overtemperature.
        3 hours above threshold out of 5.
        """
        result = simulate_hourly(
            temperatures=[20.0, 25.0, 32.0, 35.0, 38.0],
            humidities=None,
            cooling_type="Free Cooling — Dry Cooler (Chiller-less)",
            eta_chain=0.95,
            it_load_kw=5000.0,
        )
        # Hours above 30°C: 32, 35, 38 → 3 overtemp hours
        assert result.overtemperature_hours == 3

    def test_dry_cooler_no_overtemp_cool_climate(self):
        """Dry cooler in cool climate — no overtemperature."""
        result = simulate_hourly(
            temperatures=[10.0, 15.0, 20.0, 25.0],
            humidities=None,
            cooling_type="Free Cooling — Dry Cooler (Chiller-less)",
            eta_chain=0.95,
            it_load_kw=5000.0,
        )
        assert result.overtemperature_hours == 0


# ═════════════════════════════════════════════════════════════
# 7. EDGE CASES AND VALIDATION
# ═════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Input validation and boundary conditions."""

    def test_empty_temperatures_raises(self):
        """Empty input raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            simulate_hourly(
                temperatures=[],
                humidities=None,
                cooling_type=COOLING_TYPE,
                eta_chain=0.95,
                it_load_kw=10000.0,
            )

    def test_length_mismatch_raises(self):
        """Different length temps and humidities raises ValueError."""
        with pytest.raises(ValueError, match="same length"):
            simulate_hourly(
                temperatures=[20.0, 25.0],
                humidities=[50.0],
                cooling_type=COOLING_TYPE,
                eta_chain=0.95,
                it_load_kw=10000.0,
            )

    def test_both_power_modes_raises(self):
        """Providing both facility_power_kw and it_load_kw raises."""
        with pytest.raises(ValueError, match="Exactly one"):
            simulate_hourly(
                temperatures=[20.0],
                humidities=None,
                cooling_type=COOLING_TYPE,
                eta_chain=0.95,
                facility_power_kw=15000.0,
                it_load_kw=10000.0,
            )

    def test_neither_power_mode_raises(self):
        """Providing neither facility_power_kw nor it_load_kw raises."""
        with pytest.raises(ValueError, match="Exactly one"):
            simulate_hourly(
                temperatures=[20.0],
                humidities=None,
                cooling_type=COOLING_TYPE,
                eta_chain=0.95,
            )

    def test_single_hour(self):
        """Simulation works with a single hour."""
        result = simulate_hourly(
            temperatures=[20.0],
            humidities=None,
            cooling_type=COOLING_TYPE,
            eta_chain=0.95,
            it_load_kw=10000.0,
        )
        assert len(result.hourly_pue) == 1
        assert result.annual_pue > 1.0

    def test_returns_correct_type(self):
        """Result is HourlySimResult dataclass."""
        result = simulate_hourly(
            temperatures=[20.0],
            humidities=None,
            cooling_type=COOLING_TYPE,
            eta_chain=0.95,
            it_load_kw=10000.0,
        )
        assert isinstance(result, HourlySimResult)

    def test_pue_always_above_one(self):
        """PUE > 1.0 always (physically: facility > IT by definition)."""
        result = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=WEATHER_4H_RH,
            cooling_type=COOLING_TYPE,
            eta_chain=ETA_CHAIN,
            it_load_kw=10000.0,
        )
        assert result.annual_pue > 1.0
        for pue in result.hourly_pue:
            assert pue > 1.0


# ═════════════════════════════════════════════════════════════
# 8. CONSISTENCY CHECKS
# ═════════════════════════════════════════════════════════════

class TestConsistency:
    """Cross-checks between modes and physical constraints."""

    def test_pue_consistent_between_modes(self):
        """Area and power-constrained PUE should be similar
        (not identical — different b computation).
        Both should be in the range 1.2–1.3 for this weather.
        """
        area = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=None,
            cooling_type=COOLING_TYPE,
            eta_chain=ETA_CHAIN,
            it_load_kw=10000.0,
        )
        power = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=None,
            cooling_type=COOLING_TYPE,
            eta_chain=ETA_CHAIN,
            facility_power_kw=15000.0,
        )
        # Both should produce PUE in the 1.2–1.3 range
        assert 1.2 < area.annual_pue < 1.35
        assert 1.2 < power.annual_pue < 1.35

    def test_energy_weighted_pue_not_arithmetic_mean(self):
        """Verify that energy-weighted PUE ≠ simple average of hourly PUE.
        The Architecture Agreement (Section 3.4) explicitly warns:
        'The arithmetic average of hourly PUE values is NOT the same
        and must NOT be used.'
        """
        result = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=None,
            cooling_type=COOLING_TYPE,
            eta_chain=ETA_CHAIN,
            facility_power_kw=15000.0,
        )
        arithmetic_mean_pue = sum(result.hourly_pue) / len(result.hourly_pue)
        # They should be different (energy-weighted ≠ arithmetic mean)
        assert result.annual_pue != pytest.approx(arithmetic_mean_pue, abs=1e-6)
        # Both should be in reasonable range
        assert 1.0 < arithmetic_mean_pue < 2.0
        assert 1.0 < result.annual_pue < 2.0

    def test_higher_eta_chain_lower_pue(self):
        """Higher power chain efficiency → lower PUE."""
        result_95 = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=None,
            cooling_type=COOLING_TYPE,
            eta_chain=0.95,
            it_load_kw=10000.0,
        )
        result_97 = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=None,
            cooling_type=COOLING_TYPE,
            eta_chain=0.97,
            it_load_kw=10000.0,
        )
        assert result_97.annual_pue < result_95.annual_pue

    def test_water_cooled_with_rh(self):
        """Water-cooled chiller simulation works with humidity data."""
        result = simulate_hourly(
            temperatures=[15.0, 20.0, 25.0, 30.0],
            humidities=[60.0, 60.0, 60.0, 60.0],
            cooling_type="Water-Cooled Chiller + Economizer",
            eta_chain=0.95,
            it_load_kw=10000.0,
        )
        assert result.annual_pue > 1.0
        assert result.annual_pue < 1.5  # Water-cooled is efficient

    def test_dlc_more_efficient_than_crac(self):
        """DLC should produce lower PUE than CRAC for same weather."""
        result_crac = simulate_hourly(
            temperatures=[20.0, 25.0, 30.0, 35.0],
            humidities=None,
            cooling_type="Air-Cooled CRAC (DX)",
            eta_chain=0.95,
            it_load_kw=5000.0,
        )
        result_dlc = simulate_hourly(
            temperatures=[20.0, 25.0, 30.0, 35.0],
            humidities=None,
            cooling_type="Direct Liquid Cooling (DLC / Cold Plate)",
            eta_chain=0.95,
            it_load_kw=5000.0,
        )
        assert result_dlc.annual_pue < result_crac.annual_pue

    def test_all_econ_full_no_cooling_energy(self):
        """When all hours are ECON_FULL, mech and econ_part fracs = 0."""
        # DLC hybrid with very cold weather → both liquid and residual air paths ECON_FULL
        result = simulate_hourly(
            temperatures=[10.0, 12.0, 13.0],
            humidities=None,
            cooling_type="Direct Liquid Cooling (DLC / Cold Plate)",
            eta_chain=0.95,
            it_load_kw=5000.0,
        )
        assert result.econ_full_hours == 3
        assert result.mech_hours == 0
        assert result.mech_energy_frac == 0.0
        assert result.econ_part_energy_frac == 0.0

    def test_hourly_arrays_correct_length(self):
        """All hourly arrays have the same length as input."""
        result = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=None,
            cooling_type=COOLING_TYPE,
            eta_chain=ETA_CHAIN,
            it_load_kw=10000.0,
        )
        n = len(WEATHER_4H_TEMPS)
        assert len(result.hourly_pue) == n
        assert len(result.hourly_it_kw) == n
        assert len(result.hourly_facility_kw) == n
        assert len(result.hourly_mode) == n
        assert len(result.hourly_cop) == n
        assert len(result.hourly_cool_kw_per_kw_it) == n


class TestFacilityFactors:
    """Shared hourly factor helper used by the peak-support solver."""

    def test_matches_area_mode_facility_over_it_ratio(self):
        """For fixed IT, facility_factor(t) must equal P_facility(t) / P_IT."""
        result = simulate_hourly(
            temperatures=WEATHER_4H_TEMPS,
            humidities=None,
            cooling_type=COOLING_TYPE,
            eta_chain=ETA_CHAIN,
            it_load_kw=10000.0,
            f_misc=F_MISC,
        )
        factors = build_hourly_facility_factors(
            temperatures=WEATHER_4H_TEMPS,
            humidities=None,
            cooling_type=COOLING_TYPE,
            eta_chain=ETA_CHAIN,
            f_misc=F_MISC,
        )

        for factor, facility_kw, it_kw in zip(
            factors,
            result.hourly_facility_kw,
            result.hourly_it_kw,
            strict=True,
        ):
            assert factor == pytest.approx(facility_kw / it_kw, abs=1e-6)

    def test_empty_temperatures_raise(self):
        with pytest.raises(ValueError, match="must not be empty"):
            build_hourly_facility_factors(
                temperatures=[],
                humidities=None,
                cooling_type=COOLING_TYPE,
                eta_chain=ETA_CHAIN,
            )
