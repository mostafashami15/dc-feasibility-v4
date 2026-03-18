"""
DC Feasibility Tool v4 — Tests for climate.py
===============================================
Every expected value is hand-calculated. Test datasets have known
properties (exact hour counts per temperature band).

Test structure:
    1. Temperature statistics
    2. Free cooling hours — per cooling type
    3. Climate suitability classification
    4. Delta projection
    5. Monthly breakdown
    6. Full analyse_climate integration
    7. Edge cases
"""

import math
import pytest

from engine.climate import (
    compute_temperature_stats,
    compute_monthly_stats,
    count_free_cooling_hours,
    count_cooling_mode_hours,
    classify_suitability,
    analyse_free_cooling,
    analyse_climate,
    ClimateAnalysisResult,
    FreeCoolingAnalysis,
    TemperatureStats,
    MonthlyStats,
    HOURS_PER_MONTH,
)
from engine.assumptions import COOLING_PROFILES


# ═════════════════════════════════════════════════════════════
# Test datasets with known properties
# ═════════════════════════════════════════════════════════════

def make_8760_dataset():
    """8760-hour dataset with known free cooling hours.

    Structure:
        5500 hours at 10°C (below all thresholds)
        2000 hours at 18°C (below DLC/Immersion, above Air Chiller)
        1260 hours at 30°C (above most thresholds)
    Total: 8760 hours

    Free cooling hours:
        Air Chiller (T≤14°C): 5500
        DLC hybrid full-free cooling: 5500
        Immersion (T≤28°C): 5500 + 2000 = 7500
        Dry Cooler (T≤30°C): 5500 + 2000 + 1260 = 8760
        CRAC (no econ): 0
    """
    return [10.0] * 5500 + [18.0] * 2000 + [30.0] * 1260


def make_simple_dataset():
    """Simple 10-element dataset for basic stat tests.

    Values: [0, 5, 10, 15, 20, 25, 30, 35, 40, 45]
    Mean = 22.5, min = 0, max = 45, median = 25
    """
    return [0, 5, 10, 15, 20, 25, 30, 35, 40, 45]


# ═════════════════════════════════════════════════════════════
# 1. TEMPERATURE STATISTICS
# ═════════════════════════════════════════════════════════════

class TestTemperatureStats:
    """Test compute_temperature_stats."""

    def test_simple_stats(self):
        """Known dataset: mean=22.5, min=0, max=45."""
        temps = make_simple_dataset()
        stats = compute_temperature_stats(temps)
        assert stats.count == 10
        assert stats.mean == 22.5
        assert stats.min == 0.0
        assert stats.max == 45.0

    def test_median(self):
        """Median of [0,5,10,15,20,25,30,35,40,45] = 25 (index 5)."""
        stats = compute_temperature_stats(make_simple_dataset())
        assert stats.median == 25.0

    def test_8760_stats(self):
        """8760-hour dataset: mean = (5500×10 + 2000×18 + 1260×30) / 8760."""
        temps = make_8760_dataset()
        stats = compute_temperature_stats(temps)
        expected_mean = (5500 * 10.0 + 2000 * 18.0 + 1260 * 30.0) / 8760
        assert stats.count == 8760
        assert stats.mean == pytest.approx(expected_mean, abs=0.01)
        assert stats.min == 10.0
        assert stats.max == 30.0

    def test_constant_temperature(self):
        """All same temperature → mean=min=max, std_dev=0."""
        stats = compute_temperature_stats([20.0] * 100)
        assert stats.mean == 20.0
        assert stats.min == 20.0
        assert stats.max == 20.0
        assert stats.std_dev == 0.0

    def test_empty_raises(self):
        """Empty input raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            compute_temperature_stats([])

    def test_std_dev(self):
        """Standard deviation of [0, 10] = 5.0 (population)."""
        stats = compute_temperature_stats([0.0, 10.0])
        assert stats.std_dev == 5.0


# ═════════════════════════════════════════════════════════════
# 2. FREE COOLING HOURS
# ═════════════════════════════════════════════════════════════

class TestFreeCoolingHours:
    """Test count_free_cooling_hours for each topology."""

    def setup_method(self):
        self.temps = make_8760_dataset()

    # ── Air Chiller + Econ ──
    # T_econ_full = CHWS(16) - ECO_full_approach(2) = 14°C
    # Hours ≤ 14°C: only the 10°C hours = 5500

    def test_air_chiller(self):
        """Air Chiller: 5500 hours ≤ 14°C."""
        hours = count_free_cooling_hours(
            self.temps, "Air-Cooled Chiller + Economizer"
        )
        assert hours == 5500

    # ── DLC ──
    # Hybrid model:
    #   DLC liquid path full-free threshold = 25°C
    #   residual air path full-free threshold = 14°C
    # Full-system ECON_FULL requires both paths to be in ECON_FULL.

    def test_dlc(self):
        """DLC hybrid: 5500 full-system ECON_FULL hours."""
        hours = count_free_cooling_hours(
            self.temps, "Direct Liquid Cooling (DLC / Cold Plate)"
        )
        assert hours == 5500

    # ── Immersion ──
    # T_econ_full = CHWS(34) - ECO_full_approach(6) = 28°C
    # Hours ≤ 28°C: 10°C (5500) + 18°C (2000) = 7500

    def test_immersion(self):
        """Immersion: 7500 hours ≤ 28°C."""
        hours = count_free_cooling_hours(
            self.temps, "Immersion Cooling (Single-Phase)"
        )
        assert hours == 7500

    # ── Dry Cooler ──
    # ASE_DB = 30°C
    # Hours ≤ 30°C: ALL hours (max temp = 30°C)

    def test_dry_cooler(self):
        """Dry Cooler: all 8760 hours ≤ 30°C."""
        hours = count_free_cooling_hours(
            self.temps, "Free Cooling — Dry Cooler (Chiller-less)"
        )
        assert hours == 8760

    # ── CRAC (no economizer) ──

    def test_crac_no_free_cooling(self):
        """CRAC: 0 hours (no economizer)."""
        hours = count_free_cooling_hours(
            self.temps, "Air-Cooled CRAC (DX)"
        )
        assert hours == 0

    # ── AHU (no economizer) ──

    def test_ahu_no_free_cooling(self):
        """AHU: 0 hours (no economizer)."""
        hours = count_free_cooling_hours(
            self.temps, "Air-Cooled AHU (No Economizer)"
        )
        assert hours == 0

    # ── Water Chiller (wet-bulb based) ──

    def test_water_chiller_with_rh(self):
        """Water Chiller: free cooling when T_wb ≤ 12.8°C.
        At T=10°C, RH=60%: T_wb ≈ 5.4°C ≤ 12.8 → free cooling.
        At T=18°C, RH=60%: T_wb ≈ 13.4°C > 12.8 → no free cooling.
        So only the 5500 hours at 10°C qualify.
        """
        rh = [60.0] * 8760
        hours = count_free_cooling_hours(
            self.temps, "Water-Cooled Chiller + Economizer",
            humidities=rh
        )
        assert hours == 5500

    def test_water_chiller_requires_rh(self):
        """Water Chiller without RH raises ValueError."""
        with pytest.raises(ValueError, match="RH required"):
            count_free_cooling_hours(
                self.temps, "Water-Cooled Chiller + Economizer"
            )


# ═════════════════════════════════════════════════════════════
# 3. SUITABILITY CLASSIFICATION
# ═════════════════════════════════════════════════════════════

class TestSuitability:
    """Test classify_suitability thresholds."""

    def test_excellent(self):
        """≥ 7000 hours → EXCELLENT."""
        assert classify_suitability(7000) == "EXCELLENT"
        assert classify_suitability(8760) == "EXCELLENT"

    def test_good(self):
        """5000–6999 hours → GOOD."""
        assert classify_suitability(5000) == "GOOD"
        assert classify_suitability(6999) == "GOOD"

    def test_marginal(self):
        """3000–4999 hours → MARGINAL."""
        assert classify_suitability(3000) == "MARGINAL"
        assert classify_suitability(4999) == "MARGINAL"

    def test_not_recommended(self):
        """< 3000 hours → NOT_RECOMMENDED."""
        assert classify_suitability(2999) == "NOT_RECOMMENDED"
        assert classify_suitability(0) == "NOT_RECOMMENDED"

    def test_boundaries(self):
        """Exact boundary values."""
        assert classify_suitability(6999) == "GOOD"
        assert classify_suitability(7000) == "EXCELLENT"
        assert classify_suitability(4999) == "MARGINAL"
        assert classify_suitability(5000) == "GOOD"
        assert classify_suitability(2999) == "NOT_RECOMMENDED"
        assert classify_suitability(3000) == "MARGINAL"


# ═════════════════════════════════════════════════════════════
# 4. DELTA PROJECTION
# ═════════════════════════════════════════════════════════════

class TestDeltaProjection:
    """Test climate change temperature delta application."""

    def test_delta_reduces_free_cooling(self):
        """+5°C delta: 10+5=15 > 14 → Air Chiller loses all free cooling."""
        temps = make_8760_dataset()
        hours = count_free_cooling_hours(
            temps, "Air-Cooled Chiller + Economizer", delta_C=5.0
        )
        # 10+5=15 > 14, 18+5=23 > 14, 30+5=35 > 14 → 0 hours
        assert hours == 0

    def test_delta_small_preserves_cold_hours(self):
        """+2°C delta: 10+2=12 ≤ 14 → Air Chiller keeps cold hours."""
        temps = make_8760_dataset()
        hours = count_free_cooling_hours(
            temps, "Air-Cooled Chiller + Economizer", delta_C=2.0
        )
        # 10+2=12 ≤ 14 → 5500 hours still qualify
        assert hours == 5500

    def test_delta_dlc_resilient(self):
        """DLC hybrid loses full free cooling once the residual air path exceeds 14°C.
        10+5=15 > 14, 18+5=23 > 14, 30+5=35 > 14 → 0 full-system ECON_FULL hours
        """
        temps = make_8760_dataset()
        hours = count_free_cooling_hours(
            temps, "Direct Liquid Cooling (DLC / Cold Plate)", delta_C=5.0
        )
        assert hours == 0

    def test_delta_zero_is_baseline(self):
        """Delta = 0 should give same result as no delta."""
        temps = make_8760_dataset()
        h_baseline = count_free_cooling_hours(
            temps, "Air-Cooled Chiller + Economizer"
        )
        h_zero = count_free_cooling_hours(
            temps, "Air-Cooled Chiller + Economizer", delta_C=0.0
        )
        assert h_baseline == h_zero

    def test_negative_delta_increases_free_cooling(self):
        """−5°C delta: 18−5=13 ≤ 14 → Air Chiller gains ECON_PART hours."""
        temps = make_8760_dataset()
        hours = count_free_cooling_hours(
            temps, "Air-Cooled Chiller + Economizer", delta_C=-5.0
        )
        # 10-5=5 ≤ 14 (5500), 18-5=13 ≤ 14 (2000), 30-5=25 > 14 (0)
        assert hours == 7500


# ═════════════════════════════════════════════════════════════
# 5. MONTHLY BREAKDOWN
# ═════════════════════════════════════════════════════════════

class TestMonthlyStats:
    """Test monthly temperature breakdown."""

    def test_non_8760_returns_none(self):
        """Short datasets don't get monthly breakdown."""
        result = compute_monthly_stats([20.0] * 100)
        assert result is None

    def test_8760_returns_12_months(self):
        """8760-hour dataset produces 12 monthly entries."""
        temps = [20.0] * 8760
        result = compute_monthly_stats(temps)
        assert result is not None
        assert len(result.monthly_mean) == 12
        assert len(result.monthly_min) == 12
        assert len(result.monthly_max) == 12

    def test_constant_temp_monthly(self):
        """Constant 20°C → all monthly means = 20."""
        result = compute_monthly_stats([20.0] * 8760)
        for mean in result.monthly_mean:
            assert mean == 20.0

    def test_hours_per_month_sum(self):
        """Hours per month must sum to 8760."""
        assert sum(HOURS_PER_MONTH) == 8760

    def test_january_hours(self):
        """January has 744 hours (31 days × 24 hours)."""
        assert HOURS_PER_MONTH[0] == 744

    def test_february_hours(self):
        """February has 672 hours (28 days × 24 hours)."""
        assert HOURS_PER_MONTH[1] == 672


# ═════════════════════════════════════════════════════════════
# 6. FULL INTEGRATION — analyse_climate
# ═════════════════════════════════════════════════════════════

class TestAnalyseClimate:
    """Integration tests for the main analyse_climate function."""

    def test_basic_analysis(self):
        """Run full analysis on 8760-hour dataset."""
        temps = make_8760_dataset()
        result = analyse_climate(
            temps,
            cooling_types=["Air-Cooled Chiller + Economizer"],
        )
        assert isinstance(result, ClimateAnalysisResult)
        assert result.temperature_stats.count == 8760
        assert len(result.free_cooling) == 1
        assert result.free_cooling[0].free_cooling_hours == 5500
        assert result.free_cooling[0].suitability == "GOOD"

    def test_multiple_cooling_types(self):
        """Analysis with multiple cooling types."""
        temps = make_8760_dataset()
        result = analyse_climate(
            temps,
            cooling_types=[
                "Air-Cooled Chiller + Economizer",
                "Direct Liquid Cooling (DLC / Cold Plate)",
            ],
        )
        assert len(result.free_cooling) == 2
        # Air Chiller: 5500 hours, DLC hybrid full-free cooling: 5500 hours
        fc_dict = {fc.cooling_type: fc for fc in result.free_cooling}
        assert fc_dict["Air-Cooled Chiller + Economizer"].free_cooling_hours == 5500
        assert fc_dict["Direct Liquid Cooling (DLC / Cold Plate)"].free_cooling_hours == 5500

    def test_delta_results_present(self):
        """Delta projection results are included."""
        temps = make_8760_dataset()
        result = analyse_climate(
            temps,
            cooling_types=["Air-Cooled Chiller + Economizer"],
            deltas=[1.0, 2.0],
        )
        assert 1.0 in result.delta_results
        assert 2.0 in result.delta_results
        # Each delta has one entry per cooling type
        assert len(result.delta_results[1.0]) == 1

    def test_default_cooling_types(self):
        """When no cooling types specified, analyses all eligible dry-bulb types.

        Water-side economizer needs humidity to compute wet-bulb, so it is
        intentionally excluded from the default set when RH is unavailable.
        """
        temps = [15.0] * 100
        result = analyse_climate(temps)
        # Should include all free-cooling-eligible types that do not require RH
        eligible = [n for n, p in COOLING_PROFILES.items()
                    if p.get("free_cooling_eligible", False)]
        eligible_without_rh = [
            n for n in eligible
            if COOLING_PROFILES[n]["topology"] != "water_side_economizer"
        ]
        assert len(result.free_cooling) == len(eligible_without_rh)

    def test_default_cooling_types_with_humidity(self):
        """When RH is available, all eligible cooling types are analysed."""
        temps = [15.0] * 100
        rh = [60.0] * 100
        result = analyse_climate(temps, humidities=rh)
        eligible = [n for n, p in COOLING_PROFILES.items()
                    if p.get("free_cooling_eligible", False)]
        assert len(result.free_cooling) == len(eligible)

    def test_monthly_stats_present(self):
        """8760-hour dataset includes monthly breakdown."""
        temps = make_8760_dataset()
        result = analyse_climate(temps, cooling_types=["Air-Cooled Chiller + Economizer"])
        assert result.monthly_stats is not None
        assert len(result.monthly_stats.monthly_mean) == 12

    def test_short_dataset_no_monthly(self):
        """Short dataset has no monthly breakdown."""
        result = analyse_climate([20.0] * 100, cooling_types=["Air-Cooled Chiller + Economizer"])
        assert result.monthly_stats is None

    def test_free_cooling_fraction(self):
        """Free cooling fraction = hours / total."""
        temps = make_8760_dataset()
        result = analyse_climate(
            temps,
            cooling_types=["Air-Cooled Chiller + Economizer"],
        )
        fc = result.free_cooling[0]
        assert fc.free_cooling_fraction == pytest.approx(5500 / 8760, abs=1e-3)

    def test_empty_raises(self):
        """Empty temperatures raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            analyse_climate([])


# ═════════════════════════════════════════════════════════════
# 7. EDGE CASES
# ═════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Boundary conditions and special scenarios."""

    def test_all_below_threshold(self):
        """All hours below threshold → 100% free cooling → EXCELLENT."""
        temps = [5.0] * 8760
        fc = analyse_free_cooling(temps, "Air-Cooled Chiller + Economizer")
        assert fc.free_cooling_hours == 8760
        assert fc.suitability == "EXCELLENT"
        assert fc.free_cooling_fraction == 1.0

    def test_all_above_threshold(self):
        """All hours above threshold → 0% free cooling → NOT_RECOMMENDED."""
        temps = [40.0] * 8760
        fc = analyse_free_cooling(temps, "Air-Cooled Chiller + Economizer")
        assert fc.free_cooling_hours == 0
        assert fc.suitability == "NOT_RECOMMENDED"
        assert fc.free_cooling_fraction == 0.0

    def test_exactly_at_threshold(self):
        """Temperature exactly at threshold → counts as free cooling (≤)."""
        # Air Chiller threshold = 14.0°C
        temps = [14.0] * 100
        hours = count_free_cooling_hours(
            temps, "Air-Cooled Chiller + Economizer"
        )
        assert hours == 100  # ≤ threshold

    def test_just_above_threshold(self):
        """Temperature just above threshold → not free cooling."""
        temps = [14.01] * 100
        hours = count_free_cooling_hours(
            temps, "Air-Cooled Chiller + Economizer"
        )
        assert hours == 0  # > threshold

    def test_single_hour(self):
        """Single-hour dataset works."""
        fc = analyse_free_cooling([10.0], "Air-Cooled Chiller + Economizer")
        assert fc.free_cooling_hours == 1

    def test_rdhx_same_thresholds_as_air_chiller(self):
        """RDHx uses same chiller as Air Chiller → same thresholds."""
        temps = make_8760_dataset()
        h_air = count_free_cooling_hours(temps, "Air-Cooled Chiller + Economizer")
        h_rdhx = count_free_cooling_hours(temps, "Rear Door Heat Exchanger (RDHx)")
        assert h_air == h_rdhx


# ═════════════════════════════════════════════════════════════
# 8. COOLING MODE HOURS (ECON_FULL + ECON_PART + MECH)
# ═════════════════════════════════════════════════════════════

class TestCoolingModeHours:
    """Test count_cooling_mode_hours returns correct per-mode breakdown."""

    def setup_method(self):
        self.temps = make_8760_dataset()

    def test_air_chiller_three_modes(self):
        """Air Chiller + Econ has three modes: ECON_FULL, ECON_PART, MECH.

        Thresholds from assumptions.py:
            ECON_FULL: T_db <= 14 (CHWS=16 - ECO_full_approach=2)
            ECON_PART: 14 < T_db <= 22 (CHWR=24 - ECO_enable_dT=2)
            MECH: T_db > 22

        Dataset: 5500 @ 10, 2000 @ 18, 1260 @ 30
            10 <= 14 -> ECON_FULL: 5500
            18 > 14 and 18 <= 22 -> ECON_PART: 2000
            30 > 22 -> MECH: 1260
        """
        full, part, mech = count_cooling_mode_hours(
            self.temps, "Air-Cooled Chiller + Economizer"
        )
        assert full == 5500
        assert part == 2000
        assert mech == 1260
        assert full + part + mech == 8760

    def test_immersion_three_modes(self):
        """Immersion has wider economizer window.

        Thresholds: ECON_FULL <= 28 (CHWS=34 - ECO_full_approach=6),
                    ECON_PART 28 < T <= 39 (CHWR=45 - ECO_enable_dT=6)
                    MECH > 39

        Dataset: 5500 @ 10, 2000 @ 18, 1260 @ 30
            10 <= 28 -> ECON_FULL: 5500
            18 <= 28 -> ECON_FULL: 2000
            30 > 28 and 30 <= 39 -> ECON_PART: 1260
        """
        full, part, mech = count_cooling_mode_hours(
            self.temps, "Immersion Cooling (Single-Phase)"
        )
        assert full == 7500
        assert part == 1260
        assert mech == 0
        assert full + part + mech == 8760

    def test_dry_cooler_two_modes(self):
        """Dry Cooler (air_side_economizer) has only ECON_FULL and MECH.

        Threshold: ASE_DB = 30. Dataset max = 30. All hours <= 30 -> ECON_FULL.
        """
        full, part, mech = count_cooling_mode_hours(
            self.temps, "Free Cooling — Dry Cooler (Chiller-less)"
        )
        assert full == 8760
        assert part == 0
        assert full + part + mech == 8760

    def test_crac_all_mechanical(self):
        """CRAC (mechanical_only) has no economizer -- all hours are MECH."""
        full, part, mech = count_cooling_mode_hours(
            self.temps, "Air-Cooled CRAC (DX)"
        )
        assert full == 0
        assert part == 0
        assert mech == 8760

    def test_modes_sum_to_total(self):
        """For any topology, ECON_FULL + ECON_PART + MECH = total hours."""
        for ct in ["Air-Cooled Chiller + Economizer",
                    "Immersion Cooling (Single-Phase)",
                    "Free Cooling — Dry Cooler (Chiller-less)",
                    "Air-Cooled CRAC (DX)"]:
            full, part, mech = count_cooling_mode_hours(self.temps, ct)
            assert full + part + mech == 8760, f"Mismatch for {ct}"

    def test_analyse_free_cooling_includes_partial_and_mech(self):
        """analyse_free_cooling returns partial_hours and mechanical_hours."""
        fc = analyse_free_cooling(self.temps, "Air-Cooled Chiller + Economizer")
        assert fc.partial_hours == 2000
        assert fc.mechanical_hours == 1260
        assert fc.free_cooling_hours + fc.partial_hours + fc.mechanical_hours == 8760

    def test_different_topologies_have_different_values(self):
        """Each topology should produce different free cooling breakdowns
        due to different economizer thresholds."""
        fc_air = analyse_free_cooling(self.temps, "Air-Cooled Chiller + Economizer")
        fc_imm = analyse_free_cooling(self.temps, "Immersion Cooling (Single-Phase)")
        fc_dry = analyse_free_cooling(self.temps, "Free Cooling — Dry Cooler (Chiller-less)")

        # Each topology must have different free cooling hours
        assert fc_air.free_cooling_hours != fc_imm.free_cooling_hours
        assert fc_imm.free_cooling_hours != fc_dry.free_cooling_hours

        # Partial hours should also differ
        assert fc_air.partial_hours != fc_imm.partial_hours
