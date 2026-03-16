"""
Tests for backup_power.py — Backup Power Analysis
===================================================
Every expected value is hand-calculated from the formulas in the
Architecture Agreement Section 3.8 and defaults in assumptions.py.

NO random values. NO approximate checks (except rounding tolerance).
"""

import math
import pytest

from engine.models import BackupPowerType
from engine.assumptions import BACKUP_POWER, FOOTPRINT
from engine.backup_power import (
    compute_backup_sizing,
    compare_technologies,
    co2_savings_vs_diesel,
    BackupPowerSizing,
    BackupPowerComparison,
    FUEL_ENERGY_DENSITY,
    DEFAULT_BACKUP_RUNTIME_HOURS,
    DEFAULT_PRIME_RUNTIME_HOURS,
)


# ─────────────────────────────────────────────────────────────
# Reference constants for hand calculations
# ─────────────────────────────────────────────────────────────

# Diesel
DIESEL_EFF_TYP = (0.35 + 0.40) / 2        # 0.375
DIESEL_CO2 = 0.267                          # kg CO₂ per kWh fuel
DIESEL_FUEL_DENSITY = 10.0                  # kWh per liter

# Natural Gas
NG_EFF_TYP = (0.38 + 0.42) / 2             # 0.40
NG_CO2 = 0.202                              # kg CO₂ per kWh fuel
NG_FUEL_DENSITY = 10.3                      # kWh per m³

# SOFC
SOFC_EFF_TYP = (0.55 + 0.65) / 2           # 0.60
SOFC_CO2 = 0.202                            # kg CO₂ per kWh fuel (NG basis)
SOFC_FUEL_DENSITY = 10.3                    # kWh per m³ (NG basis)

# PEM
PEM_EFF_TYP = (0.45 + 0.55) / 2            # 0.50
PEM_CO2 = 0.0                               # Zero (green H₂)
PEM_FUEL_DENSITY = 33.3                     # kWh per kg H₂

# Rotary UPS
ROTARY_EFF_TYP = (0.95 + 0.97) / 2         # 0.96


class TestDieselGenset:
    """Diesel genset: 40 MW procurement, 200 hours/year.

    Hand calculation:
        procurement_kw = 40,000
        η_typical = (0.35 + 0.40) / 2 = 0.375

        electrical_energy = 40,000 × 200 = 8,000,000 kWh = 8,000 MWh
        fuel_energy = 8,000,000 / 0.375 = 21,333,333.33 kWh = 21,333.33 MWh
        fuel_volume = 21,333,333.33 / 10.0 = 2,133,333.3 liters
        co2 = 21,333,333.33 × 0.267 = 5,695,999.999 kg = 5,696.0 tonnes

        Units: ceil(40,000 / 2,000) = 20
        Footprint: 40,000 × 0.008 = 320.0 m²
    """

    def test_sizing(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.DIESEL_GENSET,
            annual_runtime_hours=200,
        )
        assert isinstance(result, BackupPowerSizing)
        assert result.technology == "Diesel Genset"
        assert result.technology_type == "backup"
        assert result.fuel_type == "Diesel"

    def test_physical_sizing(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.DIESEL_GENSET,
            annual_runtime_hours=200,
        )
        assert result.num_units == 20
        assert result.unit_size_kw == 2000.0
        assert result.total_rated_kw == 40000.0
        assert result.footprint_m2 == 320.0
        assert result.ramp_time_seconds == 12.0

    def test_efficiency(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.DIESEL_GENSET,
            annual_runtime_hours=200,
        )
        assert result.efficiency_min == 0.35
        assert result.efficiency_max == 0.40
        assert result.efficiency_typical == pytest.approx(DIESEL_EFF_TYP)

    def test_energy(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.DIESEL_GENSET,
            annual_runtime_hours=200,
        )
        # electrical = 40,000 × 200 / 1000 = 8,000 MWh
        assert result.electrical_energy_mwh == 8000.0
        # fuel = 8,000,000 kWh / 0.375 / 1000 = 21,333.33 MWh
        assert result.fuel_energy_mwh == pytest.approx(21333.33, abs=0.01)

    def test_fuel_volume(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.DIESEL_GENSET,
            annual_runtime_hours=200,
        )
        # fuel_volume = 21,333,333.33 kWh / 10.0 kWh/L = 2,133,333.3 liters
        assert result.fuel_volume == pytest.approx(2133333.3, abs=0.1)
        assert result.fuel_volume_unit == "liters"

    def test_co2_emissions(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.DIESEL_GENSET,
            annual_runtime_hours=200,
        )
        # co2 = 21,333,333.33 × 0.267 / 1000 = 5,696.0 tonnes
        assert result.co2_tonnes_per_year == pytest.approx(5696.0, abs=0.1)
        assert result.co2_kg_per_kwh_fuel == 0.267
        assert result.emissions_category == "high"


class TestNaturalGasGenset:
    """NG genset: 10 MW procurement, 200 hours/year.

    Hand calculation:
        procurement_kw = 10,000
        η_typical = 0.40

        electrical_energy = 10,000 × 200 = 2,000,000 kWh = 2,000 MWh
        fuel_energy = 2,000,000 / 0.40 = 5,000,000 kWh = 5,000 MWh
        fuel_volume = 5,000,000 / 10.3 = 485,436.9 m³
        co2 = 5,000,000 × 0.202 / 1000 = 1,010.0 tonnes

        Units: ceil(10,000 / 2,500) = 4
    """

    def test_energy_and_emissions(self):
        result = compute_backup_sizing(
            procurement_power_mw=10.0,
            backup_type=BackupPowerType.NATURAL_GAS_GENSET,
            annual_runtime_hours=200,
        )
        assert result.electrical_energy_mwh == 2000.0
        assert result.fuel_energy_mwh == pytest.approx(5000.0, abs=0.01)
        assert result.fuel_volume == pytest.approx(485436.9, abs=0.1)
        assert result.fuel_volume_unit == "m³"
        assert result.co2_tonnes_per_year == pytest.approx(1010.0, abs=0.1)
        assert result.num_units == 4
        assert result.technology_type == "backup_or_prime"


class TestSOFCFuelCell:
    """SOFC fuel cell: 40 MW procurement, default runtime (prime = 8760h).

    Hand calculation:
        procurement_kw = 40,000
        η_typical = 0.60
        runtime = 8,760 hours (default for prime_power)

        electrical_energy = 40,000 × 8,760 = 350,400,000 kWh = 350,400 MWh
        fuel_energy = 350,400,000 / 0.60 = 584,000,000 kWh = 584,000 MWh
        fuel_volume = 584,000,000 / 10.3 = 56,699,029.1 m³
        co2 = 584,000,000 × 0.202 / 1000 = 117,968.0 tonnes

        Units: ceil(40,000 / 300) = 134
    """

    def test_default_prime_runtime(self):
        """SOFC type is 'prime_power' → default runtime should be 8760."""
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.SOFC_FUEL_CELL,
        )
        assert result.annual_runtime_hours == 8760.0

    def test_energy_and_emissions(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.SOFC_FUEL_CELL,
        )
        assert result.electrical_energy_mwh == pytest.approx(350400.0, abs=0.1)
        assert result.fuel_energy_mwh == pytest.approx(584000.0, abs=0.1)
        assert result.fuel_volume == pytest.approx(56699029.1, abs=1.0)
        assert result.co2_tonnes_per_year == pytest.approx(117968.0, abs=1.0)

    def test_unit_count(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.SOFC_FUEL_CELL,
        )
        # ceil(40,000 / 300) = 134
        assert result.num_units == 134
        assert result.unit_size_kw == 300.0

    def test_explicit_runtime_override(self):
        """When user specifies runtime, it overrides the default."""
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.SOFC_FUEL_CELL,
            annual_runtime_hours=200,
        )
        assert result.annual_runtime_hours == 200
        # electrical = 40,000 × 200 / 1000 = 8,000 MWh
        assert result.electrical_energy_mwh == 8000.0


class TestPEMFuelCell:
    """PEM fuel cell (H₂): 40 MW procurement, 200 hours/year.

    Hand calculation:
        procurement_kw = 40,000
        η_typical = 0.50
        runtime = 200 hours

        electrical_energy = 40,000 × 200 = 8,000,000 kWh = 8,000 MWh
        fuel_energy = 8,000,000 / 0.50 = 16,000,000 kWh = 16,000 MWh
        fuel_volume = 16,000,000 / 33.3 = 480,480.5 kg H₂
        co2 = 16,000,000 × 0.0 = 0 kg = 0 tonnes

        Units: ceil(40,000 / 250) = 160
    """

    def test_zero_emissions(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.PEM_FUEL_CELL,
            annual_runtime_hours=200,
        )
        assert result.co2_tonnes_per_year == 0.0
        assert result.co2_kg_per_kwh_fuel == 0.0
        assert result.emissions_category == "zero"

    def test_hydrogen_consumption(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.PEM_FUEL_CELL,
            annual_runtime_hours=200,
        )
        assert result.fuel_energy_mwh == pytest.approx(16000.0, abs=0.01)
        # 16,000,000 / 33.3 = 480,480.48
        assert result.fuel_volume == pytest.approx(480480.5, abs=1.0)
        assert result.fuel_volume_unit == "kg"

    def test_unit_count(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.PEM_FUEL_CELL,
            annual_runtime_hours=200,
        )
        assert result.num_units == 160  # ceil(40000/250)


class TestRotaryUPS:
    """Rotary UPS + Flywheel: bridge power, effectively zero fuel.

    Default runtime = 0 (bridge power runs for seconds only).
    All energy and fuel metrics should be zero.
    """

    def test_default_zero_runtime(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.ROTARY_UPS_FLYWHEEL,
        )
        assert result.annual_runtime_hours == 0.0
        assert result.technology_type == "bridge_power"

    def test_zero_energy_and_emissions(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.ROTARY_UPS_FLYWHEEL,
        )
        assert result.electrical_energy_mwh == 0.0
        assert result.fuel_energy_mwh == 0.0
        assert result.fuel_volume == 0.0
        assert result.co2_tonnes_per_year == 0.0
        assert result.emissions_category == "zero"

    def test_instant_ramp(self):
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.ROTARY_UPS_FLYWHEEL,
        )
        assert result.ramp_time_seconds == 0.0


class TestDefaultRuntimes:
    """Verify default runtime selection logic per technology type."""

    def test_backup_type_defaults_to_200h(self):
        """Diesel is 'backup' → 200 hours."""
        result = compute_backup_sizing(
            procurement_power_mw=10.0,
            backup_type=BackupPowerType.DIESEL_GENSET,
        )
        assert result.annual_runtime_hours == DEFAULT_BACKUP_RUNTIME_HOURS
        assert result.annual_runtime_hours == 200

    def test_backup_or_prime_defaults_to_200h(self):
        """NG genset is 'backup_or_prime' → defaults to backup (200h)."""
        result = compute_backup_sizing(
            procurement_power_mw=10.0,
            backup_type=BackupPowerType.NATURAL_GAS_GENSET,
        )
        assert result.annual_runtime_hours == 200

    def test_prime_power_defaults_to_8760h(self):
        """SOFC is 'prime_power' → 8760 hours."""
        result = compute_backup_sizing(
            procurement_power_mw=10.0,
            backup_type=BackupPowerType.SOFC_FUEL_CELL,
        )
        assert result.annual_runtime_hours == DEFAULT_PRIME_RUNTIME_HOURS
        assert result.annual_runtime_hours == 8760

    def test_bridge_defaults_to_0h(self):
        """Rotary UPS is 'bridge_power' → 0 hours."""
        result = compute_backup_sizing(
            procurement_power_mw=10.0,
            backup_type=BackupPowerType.ROTARY_UPS_FLYWHEEL,
        )
        assert result.annual_runtime_hours == 0

    def test_explicit_override_beats_default(self):
        """Explicit runtime always overrides the default for any type."""
        result = compute_backup_sizing(
            procurement_power_mw=10.0,
            backup_type=BackupPowerType.DIESEL_GENSET,
            annual_runtime_hours=500,
        )
        assert result.annual_runtime_hours == 500


class TestCompareAllTechnologies:
    """Test the side-by-side technology comparison function."""

    def test_comparison_returns_all_five(self):
        """compare_technologies must return all 5 technology types."""
        comp = compare_technologies(
            procurement_power_mw=40.0,
            annual_runtime_hours=200,
        )
        assert isinstance(comp, BackupPowerComparison)
        assert len(comp.technologies) == 5

    def test_comparison_at_common_runtime(self):
        """All technologies should use the specified runtime (200h)."""
        comp = compare_technologies(
            procurement_power_mw=40.0,
            annual_runtime_hours=200,
        )
        for tech in comp.technologies:
            assert tech.annual_runtime_hours == 200

    def test_diesel_baseline(self):
        """Diesel CO₂ baseline must match the diesel entry in the list.

        Diesel at 40 MW, 200h: co2 = 5,696.0 tonnes (see TestDieselGenset)
        """
        comp = compare_technologies(
            procurement_power_mw=40.0,
            annual_runtime_hours=200,
        )
        assert comp.diesel_co2_tonnes == pytest.approx(5696.0, abs=0.1)

    def test_pem_is_lowest_co2(self):
        """PEM (H₂) should have lowest CO₂ (zero) when all at same runtime."""
        comp = compare_technologies(
            procurement_power_mw=40.0,
            annual_runtime_hours=200,
        )
        # PEM and Rotary both have 0 CO₂, but PEM is listed first in enum order
        assert comp.lowest_co2_technology in [
            "PEM Fuel Cell (H₂)",
            "Rotary UPS + Flywheel",
        ]

    def test_rotary_is_fastest_ramp(self):
        """Rotary UPS has instant (0 second) ramp time."""
        comp = compare_technologies(
            procurement_power_mw=40.0,
            annual_runtime_hours=200,
        )
        assert comp.fastest_ramp_technology == "Rotary UPS + Flywheel"

    def test_rotary_is_smallest_footprint(self):
        """Rotary UPS at 0.005 m²/kW is the smallest footprint.

        40,000 kW × 0.005 = 200 m² (vs diesel: 320, NG: 400, SOFC: 600, PEM: 800)
        """
        comp = compare_technologies(
            procurement_power_mw=40.0,
            annual_runtime_hours=200,
        )
        assert comp.lowest_footprint_technology == "Rotary UPS + Flywheel"

    def test_co2_ordering(self):
        """CO₂ emissions should follow: PEM=Rotary < SOFC < NG < Diesel.

        At 200h, 40 MW procurement:
        - PEM: 0 tonnes (co2_factor = 0)
        - Rotary: 0 tonnes (runtime = 200h but co2_factor = 0)
        - SOFC: η=0.60, fuel=13,333,333 kWh, co2=2,693.33 t
        - NG: η=0.40, fuel=20,000,000 kWh, co2=4,040.0 t
        - Diesel: η=0.375, fuel=21,333,333 kWh, co2=5,696.0 t
        """
        comp = compare_technologies(
            procurement_power_mw=40.0,
            annual_runtime_hours=200,
        )
        co2_by_tech = {t.technology: t.co2_tonnes_per_year for t in comp.technologies}

        assert co2_by_tech["PEM Fuel Cell (H₂)"] == 0.0
        assert co2_by_tech["Rotary UPS + Flywheel"] == 0.0
        assert co2_by_tech["SOFC Fuel Cell"] < co2_by_tech["Natural Gas Genset"]
        assert co2_by_tech["Natural Gas Genset"] < co2_by_tech["Diesel Genset"]


class TestCO2Savings:
    """Test the CO₂ savings helper function."""

    def test_pem_vs_diesel(self):
        """PEM saves 100% vs diesel (zero emissions).

        savings = 5696.0 - 0.0 = 5696.0 tonnes
        percentage = 100.0%
        """
        savings = co2_savings_vs_diesel(0.0, 5696.0)
        assert savings["absolute_tonnes"] == 5696.0
        assert savings["percentage"] == 100.0

    def test_sofc_vs_diesel(self):
        """SOFC at 200h saves ~52.7% vs diesel at 200h.

        SOFC co2 at 200h, 40 MW:
            fuel_energy = 8,000,000 / 0.60 = 13,333,333.33 kWh
            co2 = 13,333,333.33 × 0.202 / 1000 = 2,693.33 tonnes
        Diesel co2 = 5,696.0 tonnes

        savings = 5,696.0 - 2,693.33 = 3,002.67 tonnes
        percentage = 3,002.67 / 5,696.0 × 100 = 52.7%
        """
        savings = co2_savings_vs_diesel(2693.33, 5696.0)
        assert savings["absolute_tonnes"] == pytest.approx(3002.67, abs=0.01)
        assert savings["percentage"] == pytest.approx(52.7, abs=0.1)

    def test_same_technology_zero_savings(self):
        """Diesel vs diesel = zero savings."""
        savings = co2_savings_vs_diesel(5696.0, 5696.0)
        assert savings["absolute_tonnes"] == 0.0
        assert savings["percentage"] == 0.0

    def test_diesel_baseline_zero_avoids_division_error(self):
        """If diesel baseline is 0 (e.g., zero runtime), percentage should be 0."""
        savings = co2_savings_vs_diesel(0.0, 0.0)
        assert savings["percentage"] == 0.0


class TestEdgeCases:
    """Edge cases and input validation."""

    def test_zero_power(self):
        """Zero procurement power → all results should be zero."""
        result = compute_backup_sizing(
            procurement_power_mw=0.0,
            backup_type=BackupPowerType.DIESEL_GENSET,
            annual_runtime_hours=200,
        )
        assert result.num_units == 0
        assert result.electrical_energy_mwh == 0.0
        assert result.fuel_energy_mwh == 0.0
        assert result.fuel_volume == 0.0
        assert result.co2_tonnes_per_year == 0.0

    def test_negative_power_raises(self):
        """Negative procurement power should raise ValueError."""
        with pytest.raises(ValueError, match="procurement_power_mw cannot be negative"):
            compute_backup_sizing(
                procurement_power_mw=-10.0,
                backup_type=BackupPowerType.DIESEL_GENSET,
            )

    def test_compare_negative_power_raises(self):
        """compare_technologies also validates input."""
        with pytest.raises(ValueError, match="procurement_power_mw cannot be negative"):
            compare_technologies(procurement_power_mw=-5.0)

    def test_zero_runtime_explicit(self):
        """Explicit runtime of 0 → zero energy, zero emissions."""
        result = compute_backup_sizing(
            procurement_power_mw=40.0,
            backup_type=BackupPowerType.DIESEL_GENSET,
            annual_runtime_hours=0,
        )
        assert result.electrical_energy_mwh == 0.0
        assert result.fuel_energy_mwh == 0.0
        assert result.co2_tonnes_per_year == 0.0


class TestConsistencyWithAssumptions:
    """Verify backup_power.py uses values from assumptions.py, not hardcoded."""

    def test_all_technologies_have_sources(self):
        """Every BackupPowerSizing must have a non-empty source string."""
        for backup_type in BackupPowerType:
            result = compute_backup_sizing(
                procurement_power_mw=10.0,
                backup_type=backup_type,
                annual_runtime_hours=100,
            )
            assert result.source, f"{result.technology} has no source citation"
            assert len(result.source) > 5

    def test_efficiencies_match_assumptions(self):
        """Efficiency ranges must match BACKUP_POWER dict exactly."""
        for backup_type in BackupPowerType:
            result = compute_backup_sizing(
                procurement_power_mw=10.0,
                backup_type=backup_type,
                annual_runtime_hours=100,
            )
            profile = BACKUP_POWER[backup_type.value]
            assert result.efficiency_min == profile["efficiency_min"]
            assert result.efficiency_max == profile["efficiency_max"]

    def test_co2_factors_match_assumptions(self):
        """CO₂ emission factors must match BACKUP_POWER dict exactly."""
        for backup_type in BackupPowerType:
            result = compute_backup_sizing(
                procurement_power_mw=10.0,
                backup_type=backup_type,
                annual_runtime_hours=100,
            )
            profile = BACKUP_POWER[backup_type.value]
            assert result.co2_kg_per_kwh_fuel == profile["co2_kg_per_kwh_fuel"]

    def test_module_sizes_match_assumptions(self):
        """Module sizes must match BACKUP_POWER dict exactly."""
        for backup_type in BackupPowerType:
            result = compute_backup_sizing(
                procurement_power_mw=10.0,
                backup_type=backup_type,
                annual_runtime_hours=100,
            )
            profile = BACKUP_POWER[backup_type.value]
            assert result.unit_size_kw == float(profile["module_size_kw"])


class TestFuelEnergyDensities:
    """Verify fuel energy density constants are reasonable and sourced."""

    def test_diesel_density(self):
        """Diesel LHV ≈ 10 kWh/L. Source: EN 590."""
        assert FUEL_ENERGY_DENSITY["Diesel"]["density_kwh_per_unit"] == 10.0

    def test_ng_density(self):
        """Natural gas LHV ≈ 10.3 kWh/m³. Source: ISO 6976."""
        assert FUEL_ENERGY_DENSITY["Natural Gas"]["density_kwh_per_unit"] == 10.3

    def test_hydrogen_density(self):
        """Hydrogen LHV ≈ 33.3 kWh/kg. Source: NIST."""
        assert FUEL_ENERGY_DENSITY["Green H₂"]["density_kwh_per_unit"] == 33.3

    def test_all_fuels_have_sources(self):
        """Every fuel density entry must have a source citation."""
        for fuel, info in FUEL_ENERGY_DENSITY.items():
            assert "source" in info, f"Fuel '{fuel}' has no source"
            assert len(info["source"]) > 5, f"Fuel '{fuel}' has suspiciously short source"
