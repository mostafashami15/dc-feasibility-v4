"""
Tests for sensitivity.py — Tornado Chart & Break-Even Analysis
================================================================
Every expected value is hand-calculated from the power chain formulas
in Architecture Agreement Sections 3.1, 3.3, 3.14.

NO random values.
"""

import pytest

from engine.sensitivity import (
    compute_tornado,
    compute_break_even,
    TornadoResult,
    TornadoBar,
    BreakEvenResult,
    DEFAULT_VARIATION_PCT,
    SENSITIVITY_PARAMETERS,
    _it_load_power_constrained,
    _it_load_area_constrained,
    _facility_power_from_it,
    _procurement_power,
)


# ─────────────────────────────────────────────────────────────
# Helper formula verification
# ─────────────────────────────────────────────────────────────

class TestHelperFormulas:
    """Verify the lightweight formula replicas used by sensitivity."""

    def test_it_load_power_constrained(self):
        """IT = facility × η / PUE = 20 × 0.95 / 1.25 = 15.2 MW."""
        result = _it_load_power_constrained(20.0, 0.95, 1.25)
        assert result == pytest.approx(15.2, abs=0.001)

    def test_it_load_power_constrained_pue_1(self):
        """IT = 20 × 0.95 / 1.0 = 19.0 MW."""
        result = _it_load_power_constrained(20.0, 0.95, 1.0)
        assert result == pytest.approx(19.0, abs=0.001)

    def test_it_load_power_constrained_zero_pue(self):
        """PUE = 0 → IT = 0 (avoid division by zero)."""
        result = _it_load_power_constrained(20.0, 0.95, 0.0)
        assert result == 0.0

    def test_it_load_area_constrained(self):
        """Area chain: land=25000, cov=0.50, 1 floor, ws=0.40, rack_fp=3.0, adj=1.0.

        buildable = 25000 × 0.50 = 12,500
        gross = 12,500 × 1 = 12,500
        whitespace = 12,500 × 0.40 = 5,000
        max_racks = int(5000 / 3.0) = 1666
        effective = int(1666 × 1.0) = 1666
        IT = 1666 × 7.0 / 1000 = 11.662 MW
        """
        result = _it_load_area_constrained(
            25000, 0.50, 1, 0.40, 3.0, 1.0, 7.0,
        )
        assert result == pytest.approx(11.662, abs=0.001)

    def test_facility_power_from_it(self):
        """facility = IT × PUE / η = 15.0 × 1.25 / 0.95 = 19.7368 MW."""
        result = _facility_power_from_it(15.0, 0.95, 1.25)
        assert result == pytest.approx(19.7368, abs=0.001)

    def test_procurement_power(self):
        """procurement = facility × factor = 20.0 × 2.0 = 40.0 MW."""
        result = _procurement_power(20.0, 2.0)
        assert result == 40.0


# ─────────────────────────────────────────────────────────────
# Tornado Chart Tests
# ─────────────────────────────────────────────────────────────

class TestTornadoBasic:
    """Test tornado chart with known baseline and ±10% variation."""

    # Standard baseline for all tornado tests:
    # PUE=1.25, η=0.95, density=100 kW, ws=0.40, cov=0.50, power=20 MW
    # land=25000 m², 1 floor, rack_fp=3.0, ws_adj=1.0, proc_factor=2.0
    # Baseline IT (power): 20 × 0.95 / 1.25 = 15.2 MW
    # Baseline IT (area): 1666 × 100 / 1000 = 166.6 MW
    # Binding: power (15.2 < 166.6)

    BASELINE = dict(
        pue=1.25,
        eta_chain=0.95,
        rack_density_kw=100.0,
        whitespace_ratio=0.40,
        site_coverage_ratio=0.50,
        available_power_mw=20.0,
        land_area_m2=25000.0,
        num_floors=1,
        rack_footprint_m2=3.0,
        whitespace_adjustment=1.0,
        procurement_factor=2.0,
    )

    def test_returns_tornado_result(self):
        result = compute_tornado(**self.BASELINE)
        assert isinstance(result, TornadoResult)
        assert result.variation_pct == DEFAULT_VARIATION_PCT

    def test_correct_number_of_bars(self):
        """Power-constrained mode should have 6 bars (all parameters)."""
        result = compute_tornado(**self.BASELINE, power_constrained=True)
        assert len(result.bars) == 6

    def test_bars_sorted_by_spread_descending(self):
        result = compute_tornado(**self.BASELINE)
        for i in range(len(result.bars) - 1):
            assert result.bars[i].spread >= result.bars[i + 1].spread

    def test_most_and_least_influential(self):
        result = compute_tornado(**self.BASELINE)
        assert result.most_influential == result.bars[0].parameter
        assert result.least_influential == result.bars[-1].parameter

    def test_baseline_output_is_15_2(self):
        """All bars should have the same baseline output: 15.2 MW."""
        result = compute_tornado(**self.BASELINE)
        for bar in result.bars:
            assert bar.output_at_baseline == pytest.approx(15.2, abs=0.01)

    def test_pue_variation(self):
        """PUE ±10%: low=1.125, high=1.375.

        IT at PUE=1.125: 20 × 0.95 / 1.125 = 16.8889
        IT at PUE=1.375: 20 × 0.95 / 1.375 = 13.8182
        Spread = 16.8889 - 13.8182 = 3.0707
        """
        result = compute_tornado(**self.BASELINE)
        pue_bar = next(b for b in result.bars if b.parameter == "pue")

        assert pue_bar.low_value == pytest.approx(1.125, abs=0.001)
        assert pue_bar.high_value == pytest.approx(1.375, abs=0.001)
        assert pue_bar.output_at_low == pytest.approx(16.8889, abs=0.01)
        assert pue_bar.output_at_high == pytest.approx(13.8182, abs=0.01)
        assert pue_bar.spread == pytest.approx(3.0707, abs=0.01)

    def test_eta_chain_variation(self):
        """η ±10%: low=0.855, high=1.0 (clamped).

        IT at η=0.855: 20 × 0.855 / 1.25 = 13.68
        IT at η=1.0 (clamped from 1.045): 20 × 1.0 / 1.25 = 16.0
        Spread = 16.0 - 13.68 = 2.32
        """
        result = compute_tornado(**self.BASELINE)
        eta_bar = next(b for b in result.bars if b.parameter == "eta_chain")

        assert eta_bar.low_value == pytest.approx(0.855, abs=0.001)
        assert eta_bar.high_value == pytest.approx(1.0, abs=0.001)
        assert eta_bar.output_at_low == pytest.approx(13.68, abs=0.01)
        assert eta_bar.output_at_high == pytest.approx(16.0, abs=0.01)
        assert eta_bar.spread == pytest.approx(2.32, abs=0.01)

    def test_available_power_variation(self):
        """Power ±10%: low=18, high=22.

        IT at P=18: 18 × 0.95 / 1.25 = 13.68
        IT at P=22: 22 × 0.95 / 1.25 = 16.72
        Spread = 16.72 - 13.68 = 3.04
        """
        result = compute_tornado(**self.BASELINE)
        power_bar = next(b for b in result.bars if b.parameter == "available_power_mw")

        assert power_bar.output_at_low == pytest.approx(13.68, abs=0.01)
        assert power_bar.output_at_high == pytest.approx(16.72, abs=0.01)
        assert power_bar.spread == pytest.approx(3.04, abs=0.01)


class TestTornadoPowerBindingCheck:
    """When power is the binding constraint, area parameters have zero
    impact on IT load (varying coverage/whitespace doesn't help because
    power is the bottleneck, not space).

    Baseline: IT from power = 15.2 MW, IT from area = 166.6 MW.
    Power binds. Varying area params doesn't change the binding.
    """

    BASELINE = dict(
        pue=1.25,
        eta_chain=0.95,
        rack_density_kw=100.0,
        whitespace_ratio=0.40,
        site_coverage_ratio=0.50,
        available_power_mw=20.0,
        land_area_m2=25000.0,
        num_floors=1,
        rack_footprint_m2=3.0,
        whitespace_adjustment=1.0,
        procurement_factor=2.0,
    )

    def test_area_params_zero_spread_when_power_binds(self):
        """Coverage and whitespace should have 0 spread when power binds."""
        result = compute_tornado(**self.BASELINE)

        for param in ("whitespace_ratio", "site_coverage_ratio"):
            bar = next(b for b in result.bars if b.parameter == param)
            assert bar.spread == pytest.approx(0.0, abs=0.01), (
                f"{param} should have ~0 spread when power binds, got {bar.spread}"
            )


class TestTornadoAreaConstrained:
    """Test tornado in area-constrained mode."""

    def test_area_mode_excludes_available_power(self):
        """In area mode, available_power_mw is not a sensitivity parameter."""
        result = compute_tornado(
            pue=1.25, eta_chain=0.95, rack_density_kw=7.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=0.0,  # Not used in area mode
            land_area_m2=25000.0,
            power_constrained=False,
        )
        params = [b.parameter for b in result.bars]
        assert "available_power_mw" not in params

    def test_area_mode_has_5_bars(self):
        """Area mode: 5 bars (no available_power_mw)."""
        result = compute_tornado(
            pue=1.25, eta_chain=0.95, rack_density_kw=7.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=0.0,
            land_area_m2=25000.0,
            power_constrained=False,
        )
        assert len(result.bars) == 5


class TestTornadoOutputMetrics:
    """Test different output metrics."""

    BASELINE = dict(
        pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
        whitespace_ratio=0.40, site_coverage_ratio=0.50,
        available_power_mw=20.0, land_area_m2=25000.0,
    )

    def test_facility_power_metric(self):
        """Output=facility_power: baseline = 15.2 × 1.25 / 0.95 = 20.0 MW."""
        result = compute_tornado(**self.BASELINE, output_metric="facility_power")
        assert result.output_metric_name == "Facility Power (MW)"
        # facility_power = IT × PUE / η = 15.2 × 1.25 / 0.95 = 20.0
        for bar in result.bars:
            assert bar.output_at_baseline == pytest.approx(20.0, abs=0.1)

    def test_procurement_power_metric(self):
        """Output=procurement_power: baseline = 20.0 × 2.0 = 40.0 MW."""
        result = compute_tornado(**self.BASELINE, output_metric="procurement_power")
        assert result.output_metric_name == "Procurement Power (MW)"
        for bar in result.bars:
            assert bar.output_at_baseline == pytest.approx(40.0, abs=0.1)


class TestTornadoCustomVariation:
    """Test custom variation percentages."""

    def test_5_pct_variation(self):
        """±5% variation → narrower spreads than ±10%."""
        result_5 = compute_tornado(
            pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
            variation_pct=5.0,
        )
        result_10 = compute_tornado(
            pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
            variation_pct=10.0,
        )
        # Every bar's spread should be narrower at 5% than 10%
        for b5, b10 in zip(result_5.bars, result_10.bars):
            if b5.parameter == b10.parameter:
                assert b5.spread <= b10.spread + 0.01


# ─────────────────────────────────────────────────────────────
# Break-Even Tests
# ─────────────────────────────────────────────────────────────

class TestBreakEvenPUE:
    """Break-even: solve for PUE to achieve target IT load."""

    def test_solve_pue_for_15mw(self):
        """Target 15 MW IT. PUE = 20 × 0.95 / 15 = 1.2667.

        Baseline PUE = 1.25.
        Change = 1.2667 - 1.25 = +0.0167.
        Need slightly HIGHER PUE to get to 15 MW (target is less than
        baseline 15.2 MW, so PUE can be worse).
        """
        result = compute_break_even(
            target_it_load_mw=15.0,
            parameter="pue",
            pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
        )
        assert isinstance(result, BreakEvenResult)
        # PUE = 20 × 0.95 / 15.0 = 1.2667
        assert result.break_even_value == pytest.approx(1.2667, abs=0.001)
        assert result.feasible is True

    def test_solve_pue_for_19mw(self):
        """Target 19 MW IT. PUE = 20 × 0.95 / 19 = 1.0.

        This is the theoretical minimum PUE.
        """
        result = compute_break_even(
            target_it_load_mw=19.0,
            parameter="pue",
            pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
        )
        assert result.break_even_value == pytest.approx(1.0, abs=0.001)
        assert result.feasible is True

    def test_pue_infeasible_above_max_it(self):
        """Target 20 MW IT > max possible (19 MW at PUE=1.0).

        PUE = 20 × 0.95 / 20 = 0.95 < 1.0 → infeasible.
        """
        result = compute_break_even(
            target_it_load_mw=20.0,
            parameter="pue",
            pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
        )
        assert result.break_even_value == pytest.approx(0.95, abs=0.001)
        assert result.feasible is False
        assert "below theoretical minimum" in result.feasibility_note


class TestBreakEvenEtaChain:
    """Break-even: solve for η_chain."""

    def test_solve_eta_for_15mw(self):
        """η = target_IT × PUE / facility = 15 × 1.25 / 20 = 0.9375.

        Slightly below baseline 0.95.
        """
        result = compute_break_even(
            target_it_load_mw=15.0,
            parameter="eta_chain",
            pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
        )
        assert result.break_even_value == pytest.approx(0.9375, abs=0.001)
        assert result.feasible is True

    def test_eta_infeasible_too_high(self):
        """Target requires η > 1.0 → infeasible.

        η = 18 × 1.25 / 20 = 1.125 > 1.0
        """
        result = compute_break_even(
            target_it_load_mw=18.0,
            parameter="eta_chain",
            pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
        )
        assert result.break_even_value == pytest.approx(1.125, abs=0.001)
        assert result.feasible is False
        assert "exceeds theoretical maximum" in result.feasibility_note


class TestBreakEvenPower:
    """Break-even: solve for available_power_mw."""

    def test_solve_power_for_15mw(self):
        """power = target_IT × PUE / η = 15 × 1.25 / 0.95 = 19.7368 MW."""
        result = compute_break_even(
            target_it_load_mw=15.0,
            parameter="available_power_mw",
            pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
        )
        assert result.break_even_value == pytest.approx(19.7368, abs=0.001)
        assert result.feasible is True


class TestBreakEvenRackDensity:
    """Break-even: solve for rack_density_kw."""

    def test_solve_density_for_target(self):
        """density = target_IT × 1000 / effective_racks.

        eff_racks (from geometry) = int(25000×0.5×1×0.4/3.0) × 1.0 = 1666
        target = 10 MW → density = 10,000 / 1666 = 6.002 kW/rack
        """
        result = compute_break_even(
            target_it_load_mw=10.0,
            parameter="rack_density_kw",
            pue=1.25, eta_chain=0.95, rack_density_kw=7.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
            power_constrained=False,
        )
        # density = 10000 / 1666 = 6.002
        assert result.break_even_value == pytest.approx(6.002, abs=0.01)
        assert result.feasible is True


class TestBreakEvenWhitespaceRatio:
    """Break-even: solve for whitespace_ratio."""

    def test_solve_whitespace_for_target(self):
        """ws = racks_needed × rack_fp / (land × coverage × floors × ws_adj).

        target = 10 MW, density = 7 kW/rack
        racks_needed = 10,000 / 7 = 1428.57
        ws = 1428.57 × 3.0 / (25000 × 0.50 × 1 × 1.0)
           = 4285.71 / 12500 = 0.3429
        """
        result = compute_break_even(
            target_it_load_mw=10.0,
            parameter="whitespace_ratio",
            pue=1.25, eta_chain=0.95, rack_density_kw=7.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
            power_constrained=False,
        )
        assert result.break_even_value == pytest.approx(0.3429, abs=0.001)
        assert result.feasible is True

    def test_whitespace_infeasible_above_1(self):
        """Target requires ws_ratio > 1.0 → infeasible.

        target = 50 MW, density = 7 kW/rack
        racks_needed = 50000 / 7 = 7142.86
        ws = 7142.86 × 3.0 / 12500 = 1.714 > 1.0
        """
        result = compute_break_even(
            target_it_load_mw=50.0,
            parameter="whitespace_ratio",
            pue=1.25, eta_chain=0.95, rack_density_kw=7.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=100.0, land_area_m2=25000.0,
            power_constrained=False,
        )
        assert result.feasible is False
        assert "exceeds maximum" in result.feasibility_note


class TestBreakEvenCoverageRatio:
    """Break-even: solve for site_coverage_ratio."""

    def test_solve_coverage_for_target(self):
        """coverage = racks_needed × rack_fp / (land × floors × ws_ratio × ws_adj).

        target = 10 MW, density = 7 kW/rack
        racks_needed = 10000 / 7 = 1428.57
        coverage = 1428.57 × 3.0 / (25000 × 1 × 0.40 × 1.0)
                 = 4285.71 / 10000 = 0.4286
        """
        result = compute_break_even(
            target_it_load_mw=10.0,
            parameter="site_coverage_ratio",
            pue=1.25, eta_chain=0.95, rack_density_kw=7.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
            power_constrained=False,
        )
        assert result.break_even_value == pytest.approx(0.4286, abs=0.001)
        assert result.feasible is True


class TestBreakEvenEdgeCases:
    """Edge cases for break-even."""

    def test_unknown_parameter_raises(self):
        with pytest.raises(ValueError, match="Unknown parameter"):
            compute_break_even(
                target_it_load_mw=15.0,
                parameter="nonexistent",
                pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
                whitespace_ratio=0.40, site_coverage_ratio=0.50,
                available_power_mw=20.0, land_area_m2=25000.0,
            )

    def test_negative_target_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            compute_break_even(
                target_it_load_mw=-5.0,
                parameter="pue",
                pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
                whitespace_ratio=0.40, site_coverage_ratio=0.50,
                available_power_mw=20.0, land_area_m2=25000.0,
            )

    def test_zero_target_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            compute_break_even(
                target_it_load_mw=0.0,
                parameter="pue",
                pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
                whitespace_ratio=0.40, site_coverage_ratio=0.50,
                available_power_mw=20.0, land_area_m2=25000.0,
            )

    def test_change_pct_computed_correctly(self):
        """Verify change_pct = (break_even - baseline) / baseline × 100.

        PUE break-even for 15 MW: 1.2667. Baseline: 1.25.
        Change: +0.0167. Pct: +1.33%.
        """
        result = compute_break_even(
            target_it_load_mw=15.0,
            parameter="pue",
            pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
        )
        expected_change_pct = (1.2667 - 1.25) / 1.25 * 100
        assert result.change_pct == pytest.approx(expected_change_pct, abs=0.1)


class TestBreakEvenConsistency:
    """Break-even value should produce the target when plugged back in."""

    def test_pue_roundtrip(self):
        """Plug break-even PUE back into IT formula → get target."""
        result = compute_break_even(
            target_it_load_mw=15.0,
            parameter="pue",
            pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
        )
        # IT = 20 × 0.95 / break_even_pue should ≈ 15.0
        it_check = 20.0 * 0.95 / result.break_even_value
        assert it_check == pytest.approx(15.0, abs=0.01)

    def test_eta_roundtrip(self):
        """Plug break-even η back → get target."""
        result = compute_break_even(
            target_it_load_mw=15.0,
            parameter="eta_chain",
            pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
        )
        it_check = 20.0 * result.break_even_value / 1.25
        assert it_check == pytest.approx(15.0, abs=0.01)

    def test_power_roundtrip(self):
        """Plug break-even power back → get target."""
        result = compute_break_even(
            target_it_load_mw=15.0,
            parameter="available_power_mw",
            pue=1.25, eta_chain=0.95, rack_density_kw=100.0,
            whitespace_ratio=0.40, site_coverage_ratio=0.50,
            available_power_mw=20.0, land_area_m2=25000.0,
        )
        it_check = result.break_even_value * 0.95 / 1.25
        assert it_check == pytest.approx(15.0, abs=0.01)
