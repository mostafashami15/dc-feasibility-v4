"""
DC Feasibility Tool v4 — Tests for cooling.py
===============================================
Every expected value is hand-calculated from Architecture Agreement
formulas. NO random or approximate values.

Test structure:
    1. Wet-bulb (Stull 2011) — accuracy vs. known psychrometric values
    2. COP model — linear formula, clamping at min/max
    3. Cooling mode determination — all 4 topologies
    4. Cooling load per kW IT — MECH, ECON_PART, ECON_FULL
    5. Full hourly cooling state — integration tests
    6. Edge cases and error handling
"""

import math
import pytest

from engine.cooling import (
    CoolingMode,
    HourlyCoolingState,
    compute_wet_bulb,
    compute_cop,
    determine_cooling_mode,
    compute_hourly_cooling,
    _compute_cooling_load_mech,
    _compute_blend_factor,
)
from engine.assumptions import COOLING_PROFILES


# ═════════════════════════════════════════════════════════════
# 1. WET-BULB TEMPERATURE — Stull (2011)
# ═════════════════════════════════════════════════════════════
# Source: Architecture Agreement Section 3.2
# Reference: Stull (2011), JAMC 50(11), 2267–2269
# Accuracy: ±1°C for most conditions

class TestWetBulb:
    """Test the Stull (2011) wet-bulb approximation."""

    def test_standard_conditions(self):
        """20°C, 50% RH → ~13.7°C (psychrometric chart reference)."""
        T_wb = compute_wet_bulb(20.0, 50.0)
        assert abs(T_wb - 13.6993) < 0.01

    def test_hot_dry(self):
        """35°C, 40% RH → ~24.5°C."""
        T_wb = compute_wet_bulb(35.0, 40.0)
        assert abs(T_wb - 24.5142) < 0.01

    def test_hot_humid(self):
        """30°C, 80% RH → ~27.1°C. High humidity = small depression."""
        T_wb = compute_wet_bulb(30.0, 80.0)
        assert abs(T_wb - 27.1297) < 0.01

    def test_cool_humid(self):
        """10°C, 90% RH → ~8.9°C."""
        T_wb = compute_wet_bulb(10.0, 90.0)
        assert abs(T_wb - 8.9197) < 0.01

    def test_cold(self):
        """0°C, 50% RH → ~−3.5°C. Wet-bulb below dry-bulb always."""
        T_wb = compute_wet_bulb(0.0, 50.0)
        assert abs(T_wb - (-3.4978)) < 0.01

    def test_wet_bulb_always_leq_dry_bulb(self):
        """Physical law: wet-bulb ≤ dry-bulb for all valid conditions."""
        test_cases = [
            (20, 50), (35, 40), (30, 80), (10, 90),
            (40, 20), (15, 70), (25, 60), (5, 95),
        ]
        for T, RH in test_cases:
            T_wb = compute_wet_bulb(T, RH)
            assert T_wb <= T + 0.01, (
                f"T_wb={T_wb:.2f} > T_db={T} at RH={RH}%"
            )

    def test_rh_100_wet_equals_dry(self):
        """At 100% RH, wet-bulb ≈ dry-bulb (within Stull accuracy)."""
        T_wb = compute_wet_bulb(20.0, 100.0)
        # Stull formula is ±1°C accurate; at RH=100% T_wb ≈ T_db
        assert abs(T_wb - 20.0) < 1.5

    def test_rh_out_of_range_raises(self):
        """RH outside 0–100 should raise ValueError."""
        with pytest.raises(ValueError, match="RH must be 0–100%"):
            compute_wet_bulb(20.0, -5.0)
        with pytest.raises(ValueError, match="RH must be 0–100%"):
            compute_wet_bulb(20.0, 105.0)

    def test_rh_fractional_raises(self):
        """Catch common mistake: passing 0.5 instead of 50%."""
        with pytest.raises(ValueError, match="looks fractional"):
            compute_wet_bulb(20.0, 0.5)


# ═════════════════════════════════════════════════════════════
# 2. COP MODEL
# ═════════════════════════════════════════════════════════════
# Formula: COP(T) = COP_ref + COP_slope × (T_ref − T_driver)
# Source: Architecture Agreement Section 3.2

class TestCOP:
    """Test the linear COP model with clamping."""

    # ── CRAC (DX): COP_ref=3.5, slope=0.12, T_ref=35°C, [2.0, 5.5] ──

    def test_crac_at_reference(self):
        """At T_ref: COP = COP_ref = 3.5 (no delta)."""
        cop = compute_cop(35.0, None, "Air-Cooled CRAC (DX)")
        assert cop == 3.5

    def test_crac_below_reference(self):
        """25°C: COP = 3.5 + 0.12 × (35−25) = 4.7"""
        cop = compute_cop(25.0, None, "Air-Cooled CRAC (DX)")
        assert cop == pytest.approx(4.7, abs=1e-6)

    def test_crac_above_reference(self):
        """45°C: COP = 3.5 + 0.12 × (35−45) = 2.3 (above COP_min)."""
        cop = compute_cop(45.0, None, "Air-Cooled CRAC (DX)")
        assert cop == pytest.approx(2.3, abs=1e-6)

    def test_crac_clamped_to_min(self):
        """50°C: raw = 3.5 − 1.8 = 1.7 → clamped to COP_min = 2.0."""
        cop = compute_cop(50.0, None, "Air-Cooled CRAC (DX)")
        assert cop == 2.0

    def test_crac_clamped_to_max(self):
        """0°C: raw = 3.5 + 4.2 = 7.7 → clamped to COP_max = 5.5."""
        cop = compute_cop(0.0, None, "Air-Cooled CRAC (DX)")
        assert cop == 5.5

    # ── Air Chiller + Econ: COP_ref=5.5, slope=0.15, T_ref=35°C ──

    def test_air_chiller_at_reference(self):
        """35°C: COP = 5.5."""
        cop = compute_cop(35.0, None, "Air-Cooled Chiller + Economizer")
        assert cop == 5.5

    def test_air_chiller_partial_econ_temp(self):
        """18°C: COP = 5.5 + 0.15 × (35−18) = 8.05. Below max 9.0."""
        cop = compute_cop(18.0, None, "Air-Cooled Chiller + Economizer")
        assert cop == pytest.approx(8.05, abs=1e-6)

    def test_air_chiller_clamped_to_max(self):
        """10°C: raw = 5.5 + 0.15 × 25 = 9.25 → clamped to 9.0."""
        cop = compute_cop(10.0, None, "Air-Cooled Chiller + Economizer")
        assert cop == 9.0

    # ── Water Chiller: COP driven by wet-bulb ──

    def test_water_chiller_uses_wet_bulb(self):
        """25°C/60%RH → T_wb=19.5027 → COP = 7.0 + 0.20×(35−19.5027) = 10.0995."""
        cop = compute_cop(25.0, 60.0, "Water-Cooled Chiller + Economizer")
        assert cop == pytest.approx(10.0995, abs=0.01)

    def test_water_chiller_requires_rh(self):
        """Water-cooled topology must receive RH (raises without it)."""
        with pytest.raises(ValueError, match="RH is required"):
            compute_cop(25.0, None, "Water-Cooled Chiller + Economizer")

    # ── DLC: COP_ref=7.0, slope=0.18, T_ref=35°C, [4.0, 12.0] ──

    def test_dlc_at_30(self):
        """30°C: COP = 7.0 + 0.18 × (35−30) = 7.9."""
        cop = compute_cop(30.0, None, "Direct Liquid Cooling (DLC / Cold Plate)")
        assert cop == pytest.approx(7.9, abs=1e-6)


# ═════════════════════════════════════════════════════════════
# 3. COOLING MODE DETERMINATION
# ═════════════════════════════════════════════════════════════
# Source: Architecture Agreement Section 3.3

class TestCoolingMode:
    """Test mode determination for all 4 topologies."""

    # ── mechanical_only ──

    def test_crac_always_mech(self):
        """CRAC has no economizer → always MECH regardless of temperature."""
        for T in [-10, 0, 10, 20, 30, 40]:
            mode = determine_cooling_mode(T, None, "Air-Cooled CRAC (DX)")
            assert mode == CoolingMode.MECH, f"T={T}: expected MECH"

    def test_ahu_always_mech(self):
        """AHU (no economizer) → always MECH."""
        mode = determine_cooling_mode(15.0, None, "Air-Cooled AHU (No Economizer)")
        assert mode == CoolingMode.MECH

    # ── chiller_integral_economizer ──
    # Air Chiller: CHWS=16, CHWR=24, ECO_full_approach=2, ECO_enable_dT=2
    # T_econ_full = 16 − 2 = 14°C,  T_mech = 24 − 2 = 22°C

    def test_air_chiller_econ_full(self):
        """10°C ≤ 14°C → ECON_FULL."""
        mode = determine_cooling_mode(10.0, None, "Air-Cooled Chiller + Economizer")
        assert mode == CoolingMode.ECON_FULL

    def test_air_chiller_econ_full_boundary(self):
        """14°C = T_econ_full → ECON_FULL (≤ threshold)."""
        mode = determine_cooling_mode(14.0, None, "Air-Cooled Chiller + Economizer")
        assert mode == CoolingMode.ECON_FULL

    def test_air_chiller_econ_part(self):
        """18°C: 14 < 18 ≤ 22 → ECON_PART."""
        mode = determine_cooling_mode(18.0, None, "Air-Cooled Chiller + Economizer")
        assert mode == CoolingMode.ECON_PART

    def test_air_chiller_econ_part_boundary(self):
        """22°C = T_mech → ECON_PART (≤ threshold)."""
        mode = determine_cooling_mode(22.0, None, "Air-Cooled Chiller + Economizer")
        assert mode == CoolingMode.ECON_PART

    def test_air_chiller_mech(self):
        """30°C > 22°C → MECH."""
        mode = determine_cooling_mode(30.0, None, "Air-Cooled Chiller + Economizer")
        assert mode == CoolingMode.MECH

    # ── DLC hybrid:
    # primary DLC path thresholds: 25°C / 35°C
    # residual air path thresholds: 14°C / 22°C

    def test_dlc_econ_full(self):
        """10°C keeps both DLC and residual air path in ECON_FULL."""
        mode = determine_cooling_mode(10.0, None, "Direct Liquid Cooling (DLC / Cold Plate)")
        assert mode == CoolingMode.ECON_FULL

    def test_dlc_econ_part(self):
        """20°C: DLC is ECON_FULL but residual air path is ECON_PART → hybrid ECON_PART."""
        mode = determine_cooling_mode(20.0, None, "Direct Liquid Cooling (DLC / Cold Plate)")
        assert mode == CoolingMode.ECON_PART

    def test_dlc_econ_part_hot(self):
        """30°C: DLC is ECON_PART and residual air path is MECH → hybrid ECON_PART."""
        mode = determine_cooling_mode(30.0, None, "Direct Liquid Cooling (DLC / Cold Plate)")
        assert mode == CoolingMode.ECON_PART

    def test_dlc_mech(self):
        """40°C > 35°C → MECH."""
        mode = determine_cooling_mode(40.0, None, "Direct Liquid Cooling (DLC / Cold Plate)")
        assert mode == CoolingMode.MECH

    # ── Immersion: CHWS=34, CHWR=45, ECO_full_approach=6, ECO_enable_dT=6
    # T_econ_full = 34 − 6 = 28°C,  T_mech = 45 − 6 = 39°C

    def test_immersion_econ_full(self):
        """20°C ≤ 28°C → ECON_FULL. Widest economizer window."""
        mode = determine_cooling_mode(20.0, None, "Immersion Cooling (Single-Phase)")
        assert mode == CoolingMode.ECON_FULL

    def test_immersion_mech(self):
        """42°C > 39°C → MECH."""
        mode = determine_cooling_mode(42.0, None, "Immersion Cooling (Single-Phase)")
        assert mode == CoolingMode.MECH

    # ── water_side_economizer ──
    # WSE_WB_C = 12.8°C — uses wet-bulb

    def test_water_chiller_econ_full(self):
        """15°C/60%RH → T_wb=10.52°C ≤ 12.8 → ECON_FULL."""
        mode = determine_cooling_mode(15.0, 60.0, "Water-Cooled Chiller + Economizer")
        assert mode == CoolingMode.ECON_FULL

    def test_water_chiller_mech(self):
        """25°C/60%RH → T_wb=19.50°C > 12.8 → MECH."""
        mode = determine_cooling_mode(25.0, 60.0, "Water-Cooled Chiller + Economizer")
        assert mode == CoolingMode.MECH

    def test_water_chiller_requires_rh(self):
        """Water-side economizer needs RH for wet-bulb calculation."""
        with pytest.raises(ValueError, match="RH required"):
            determine_cooling_mode(15.0, None, "Water-Cooled Chiller + Economizer")

    # ── air_side_economizer (Dry Cooler) ──
    # ASE_DB_C = 30°C

    def test_dry_cooler_econ_full(self):
        """25°C ≤ 30°C → ECON_FULL (free cooling)."""
        mode = determine_cooling_mode(25.0, None, "Free Cooling — Dry Cooler (Chiller-less)")
        assert mode == CoolingMode.ECON_FULL

    def test_dry_cooler_mech_overtemp(self):
        """35°C > 30°C → MECH (overtemperature — no compressor to help)."""
        mode = determine_cooling_mode(35.0, None, "Free Cooling — Dry Cooler (Chiller-less)")
        assert mode == CoolingMode.MECH


# ═════════════════════════════════════════════════════════════
# 4. COOLING LOAD PER kW IT
# ═════════════════════════════════════════════════════════════
# Source: Architecture Agreement Section 3.3

class TestCoolingLoad:
    """Test cooling load calculations for each mode."""

    # Common parameters for all tests:
    # eta_chain = 0.95 (2N redundancy)
    # elec_loss = 1/0.95 − 1 = 0.052632
    # f_misc = 0.025

    ETA = 0.95
    ELEC_LOSS = (1.0 / 0.95) - 1.0  # 0.052632
    F_MISC = 0.025

    def test_mech_load_formula(self):
        """Direct test of _compute_cooling_load_mech.
        CRAC: k_fan=0.08, COP=3.5 at 35°C.
        numerator = 1 + 0.052632 + 0.08 + 0.025 = 1.157632
        result = 1.157632 / 3.5 = 0.330752
        """
        result = _compute_cooling_load_mech(
            cop=3.5, elec_loss=self.ELEC_LOSS, k_fan=0.08, f_misc=0.025
        )
        assert result == pytest.approx(0.330752, abs=1e-4)

    def test_blend_factor_midpoint(self):
        """T=18, T_econ_full=14, T_mech=22 → blend = 4/8 = 0.5."""
        blend = _compute_blend_factor(18.0, 14.0, 22.0)
        assert blend == pytest.approx(0.5, abs=1e-6)

    def test_blend_factor_at_econ_full(self):
        """At T_econ_full boundary → blend = 0."""
        blend = _compute_blend_factor(14.0, 14.0, 22.0)
        assert blend == 0.0

    def test_blend_factor_at_mech(self):
        """At T_mech boundary → blend = 1."""
        blend = _compute_blend_factor(22.0, 14.0, 22.0)
        assert blend == pytest.approx(1.0, abs=1e-6)

    def test_blend_factor_clamped_below(self):
        """Below T_econ_full → clamped to 0."""
        blend = _compute_blend_factor(10.0, 14.0, 22.0)
        assert blend == 0.0

    def test_blend_factor_clamped_above(self):
        """Above T_mech → clamped to 1."""
        blend = _compute_blend_factor(30.0, 14.0, 22.0)
        assert blend == 1.0


# ═════════════════════════════════════════════════════════════
# 5. FULL HOURLY COOLING STATE — Integration tests
# ═════════════════════════════════════════════════════════════
# These test compute_hourly_cooling() end-to-end.

class TestHourlyCooling:
    """Integration tests for the main hourly function."""

    ETA = 0.95  # 2N redundancy

    # ── CRAC at 35°C — MECH mode ──

    def test_crac_mech(self):
        """CRAC at 35°C: always MECH.
        COP = 3.5, k_fan = 0.08
        cool = (1 + 0.052632 + 0.08 + 0.025) / 3.5 = 0.330752
        k_econ = 0 (no economizer)
        """
        state = compute_hourly_cooling(
            T_db=35.0, RH=None,
            cooling_type="Air-Cooled CRAC (DX)",
            eta_chain=self.ETA,
        )
        assert state.mode == CoolingMode.MECH
        assert state.cop == pytest.approx(3.5, abs=1e-4)
        assert state.cool_kw_per_kw_it == pytest.approx(0.3308, abs=1e-3)
        assert state.k_fan == 0.08
        assert state.k_econ == 0.0  # MECH mode → no econ overhead
        assert state.is_overtemperature is False

    # ── Air Chiller at 18°C — ECON_PART mode ──

    def test_air_chiller_econ_part(self):
        """Air Chiller at 18°C: ECON_PART.
        COP = 8.05, k_fan = 0.05
        blend = (18−14)/(22−14) = 0.5
        full_mech = (1 + 0.052632 + 0.05 + 0.025) / 8.05 = 0.140078
        cool = 0.5 × 0.140078 = 0.070039
        k_econ = 0.015 (economizer active)
        """
        state = compute_hourly_cooling(
            T_db=18.0, RH=None,
            cooling_type="Air-Cooled Chiller + Economizer",
            eta_chain=self.ETA,
        )
        assert state.mode == CoolingMode.ECON_PART
        assert state.cop == pytest.approx(8.05, abs=1e-3)
        assert state.cool_kw_per_kw_it == pytest.approx(0.0700, abs=1e-3)
        assert state.k_fan == 0.05
        assert state.k_econ == 0.015  # Economizer active
        assert state.is_overtemperature is False

    # ── Air Chiller at 10°C — ECON_FULL mode ──

    def test_air_chiller_econ_full(self):
        """Air Chiller at 10°C: ECON_FULL.
        Compressor OFF → COP = 0, cool_kw = 0.
        Only k_econ (pump/fan) overhead applies.
        Source: Architecture Agreement Section 3.3 — ECON_FULL = 0.
        """
        state = compute_hourly_cooling(
            T_db=10.0, RH=None,
            cooling_type="Air-Cooled Chiller + Economizer",
            eta_chain=self.ETA,
        )
        assert state.mode == CoolingMode.ECON_FULL
        assert state.cop == 0.0  # Compressor off
        assert state.cool_kw_per_kw_it == 0.0  # No compressor power
        assert state.k_econ == 0.015  # Economizer pump/fans still running
        assert state.is_overtemperature is False

    # ── Air Chiller at 30°C — MECH mode ──

    def test_air_chiller_mech(self):
        """Air Chiller at 30°C: full MECH.
        COP = 5.5 + 0.15×(35−30) = 6.25
        cool = (1 + 0.052632 + 0.05 + 0.025) / 6.25 = 0.180421
        """
        state = compute_hourly_cooling(
            T_db=30.0, RH=None,
            cooling_type="Air-Cooled Chiller + Economizer",
            eta_chain=self.ETA,
        )
        assert state.mode == CoolingMode.MECH
        assert state.cop == pytest.approx(6.25, abs=1e-3)
        assert state.cool_kw_per_kw_it == pytest.approx(0.1804, abs=1e-3)
        assert state.k_econ == 0.0  # MECH → no econ overhead

    # ── DLC at 30°C — ECON_PART mode ──

    def test_dlc_econ_part(self):
        """DLC hybrid at 30°C: ECON_PART.
        Primary DLC branch:
            cool = 0.070103
        Residual air branch:
            cool = 0.180421
        Weighted 75% / 25%:
            cool = 0.097683
            k_fan = 0.035
            k_econ = 0.009
            effective COP = 7.4875
        """
        state = compute_hourly_cooling(
            T_db=30.0, RH=None,
            cooling_type="Direct Liquid Cooling (DLC / Cold Plate)",
            eta_chain=self.ETA,
        )
        assert state.mode == CoolingMode.ECON_PART
        assert state.cop == pytest.approx(7.4875, abs=1e-3)
        assert state.cool_kw_per_kw_it == pytest.approx(0.0977, abs=1e-3)
        assert state.k_fan == pytest.approx(0.035, abs=1e-6)
        assert state.k_econ == pytest.approx(0.009, abs=1e-6)

    # ── DLC at 10°C — ECON_FULL ──

    def test_dlc_econ_full(self):
        """DLC hybrid at 10°C: both branches ECON_FULL."""
        state = compute_hourly_cooling(
            T_db=10.0, RH=None,
            cooling_type="Direct Liquid Cooling (DLC / Cold Plate)",
            eta_chain=self.ETA,
        )
        assert state.mode == CoolingMode.ECON_FULL
        assert state.cool_kw_per_kw_it == 0.0
        assert state.k_econ == pytest.approx(0.01275, abs=1e-6)

    # ── Water Chiller at 25°C/60% — MECH (wet-bulb > threshold) ──

    def test_water_chiller_mech(self):
        """Water Chiller at 25°C/60%RH: MECH.
        T_wb = 19.5027°C > WSE_WB=12.8 → MECH
        COP(T_wb) = 7.0 + 0.20×(35−19.5027) = 10.0995
        k_fan = 0.06
        cool = (1 + 0.052632 + 0.06 + 0.025) / 10.0995 = 0.112643
        """
        state = compute_hourly_cooling(
            T_db=25.0, RH=60.0,
            cooling_type="Water-Cooled Chiller + Economizer",
            eta_chain=self.ETA,
        )
        assert state.mode == CoolingMode.MECH
        assert state.cop == pytest.approx(10.10, abs=0.05)
        assert state.cool_kw_per_kw_it == pytest.approx(0.1126, abs=1e-3)
        assert state.k_fan == 0.06
        assert state.k_econ == 0.0  # MECH

    # ── Water Chiller at 15°C/60% — ECON_FULL ──

    def test_water_chiller_econ_full(self):
        """Water Chiller at 15°C/60%RH: ECON_FULL.
        T_wb = 10.5167°C ≤ WSE_WB=12.8 → ECON_FULL
        """
        state = compute_hourly_cooling(
            T_db=15.0, RH=60.0,
            cooling_type="Water-Cooled Chiller + Economizer",
            eta_chain=self.ETA,
        )
        assert state.mode == CoolingMode.ECON_FULL
        assert state.cool_kw_per_kw_it == 0.0
        assert state.k_econ == 0.015

    # ── Dry Cooler at 25°C — ECON_FULL ──

    def test_dry_cooler_econ_full(self):
        """Dry Cooler at 25°C ≤ 30°C: ECON_FULL (free cooling)."""
        state = compute_hourly_cooling(
            T_db=25.0, RH=None,
            cooling_type="Free Cooling — Dry Cooler (Chiller-less)",
            eta_chain=self.ETA,
        )
        assert state.mode == CoolingMode.ECON_FULL
        assert state.cool_kw_per_kw_it == 0.0
        assert state.is_overtemperature is False

    # ── Dry Cooler at 35°C — overtemperature ──

    def test_dry_cooler_overtemperature(self):
        """Dry Cooler at 35°C > 30°C: MECH mode with overtemperature flag.
        This system has no compressor — it CANNOT maintain setpoint.
        The is_overtemperature flag is the critical output here.
        """
        state = compute_hourly_cooling(
            T_db=35.0, RH=None,
            cooling_type="Free Cooling — Dry Cooler (Chiller-less)",
            eta_chain=self.ETA,
        )
        assert state.mode == CoolingMode.MECH
        assert state.is_overtemperature is True
        # COP still computed (fan power), but system is in distress
        assert state.cop > 0

    # ── Immersion at 20°C — ECON_FULL ──

    def test_immersion_econ_full(self):
        """Immersion at 20°C ≤ 28°C: ECON_FULL. Widest free cooling window."""
        state = compute_hourly_cooling(
            T_db=20.0, RH=None,
            cooling_type="Immersion Cooling (Single-Phase)",
            eta_chain=self.ETA,
        )
        assert state.mode == CoolingMode.ECON_FULL
        assert state.cool_kw_per_kw_it == 0.0


# ═════════════════════════════════════════════════════════════
# 6. EDGE CASES AND CONSISTENCY
# ═════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Boundary conditions and consistency checks."""

    def test_all_cooling_types_have_profiles(self):
        """Every CoolingType enum value must exist in COOLING_PROFILES."""
        from engine.models import CoolingType
        for ct in CoolingType:
            assert ct.value in COOLING_PROFILES, (
                f"CoolingType.{ct.name} ('{ct.value}') missing from COOLING_PROFILES"
            )

    def test_all_profiles_have_required_keys(self):
        """Every COOLING_PROFILES entry must have all COP model keys."""
        required = {
            "topology", "COP_ref", "COP_min", "COP_max",
            "T_ref_C", "COP_slope", "k_fan", "k_econ",
            "whitespace_adjustment_factor",
        }
        for name, profile in COOLING_PROFILES.items():
            missing = required - set(profile.keys())
            assert not missing, f"'{name}' missing keys: {missing}"

    def test_cop_min_less_than_max(self):
        """COP_min < COP_max for all profiles (sanity check)."""
        for name, profile in COOLING_PROFILES.items():
            assert profile["COP_min"] < profile["COP_max"], (
                f"'{name}': COP_min={profile['COP_min']} >= COP_max={profile['COP_max']}"
            )

    def test_hourly_cooling_returns_namedtuple(self):
        """Verify return type is HourlyCoolingState (NamedTuple)."""
        state = compute_hourly_cooling(
            T_db=20.0, RH=None,
            cooling_type="Air-Cooled Chiller + Economizer",
            eta_chain=0.95,
        )
        assert isinstance(state, HourlyCoolingState)
        # Verify all fields accessible
        _ = state.mode, state.cop, state.cool_kw_per_kw_it
        _ = state.k_fan, state.k_econ, state.is_overtemperature

    def test_econ_full_always_zero_cooling_load(self):
        """In ECON_FULL, cooling load must be exactly 0.0 for all types."""
        cases = [
            ("Air-Cooled Chiller + Economizer", 5.0, None),
            ("Direct Liquid Cooling (DLC / Cold Plate)", 10.0, None),
            ("Immersion Cooling (Single-Phase)", 15.0, None),
            ("Free Cooling — Dry Cooler (Chiller-less)", 20.0, None),
            ("Water-Cooled Chiller + Economizer", 5.0, 50.0),  # T_wb ≈ 2°C
        ]
        for ct, T, RH in cases:
            state = compute_hourly_cooling(T, RH, ct, eta_chain=0.95)
            assert state.mode == CoolingMode.ECON_FULL, (
                f"Expected ECON_FULL for {ct} at T={T}"
            )
            assert state.cool_kw_per_kw_it == 0.0, (
                f"ECON_FULL cooling load must be 0 for {ct}"
            )

    def test_mech_always_positive_cooling_load(self):
        """In MECH mode, cooling load must be > 0."""
        cases = [
            ("Air-Cooled CRAC (DX)", 35.0, None),
            ("Air-Cooled Chiller + Economizer", 30.0, None),
            ("Water-Cooled Chiller + Economizer", 30.0, 70.0),
        ]
        for ct, T, RH in cases:
            state = compute_hourly_cooling(T, RH, ct, eta_chain=0.95)
            assert state.mode == CoolingMode.MECH
            assert state.cool_kw_per_kw_it > 0

    def test_different_eta_chain_changes_load(self):
        """Higher eta_chain (less loss) → lower cooling load."""
        state_2n = compute_hourly_cooling(
            35.0, None, "Air-Cooled CRAC (DX)", eta_chain=0.95
        )
        state_n = compute_hourly_cooling(
            35.0, None, "Air-Cooled CRAC (DX)", eta_chain=0.97
        )
        # N (0.97) has less electrical loss → less heat to reject → less cooling
        assert state_n.cool_kw_per_kw_it < state_2n.cool_kw_per_kw_it
