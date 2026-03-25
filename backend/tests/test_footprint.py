"""
Tests for footprint.py — Infrastructure Footprint Calculation
==============================================================
Every expected value is hand-calculated from the formulas in the
Architecture Agreement Section 3.11 and defaults in assumptions.py.

New model: all equipment lives INSIDE the building.
    - Gray space: backup power, transformers, substation, and cooling
      (when roof is not usable)
    - Roof: cooling equipment only (when roof IS usable)

NO random values. NO approximate checks (except rounding).
"""

import math
import pytest

from engine.models import BackupPowerType
from engine.assumptions import FOOTPRINT, BACKUP_POWER
from engine.footprint import compute_footprint, FootprintResult, FootprintElement


# ─────────────────────────────────────────────────────────────
# Helper: reference values from assumptions.py for hand calcs
# ─────────────────────────────────────────────────────────────

COOLING_M2_PER_KW = FOOTPRINT["cooling_skid_m2_per_kw_rejected"]["default"]  # 0.15
DIESEL_M2_PER_KW = FOOTPRINT["diesel_genset_m2_per_kw"]["default"]  # 0.008
TRANSFORMER_M2_PER_KW = FOOTPRINT["transformer_m2_per_kw"]["default"]  # 0.004
SUBSTATION_M2_PER_KW = FOOTPRINT["substation_m2_per_kw"]["default"]  # 0.005
DIESEL_MODULE_KW = BACKUP_POWER["Diesel Genset"]["module_size_kw"]  # 2000


class TestComputeFootprintBasic:
    """Test basic footprint calculation with known inputs."""

    def test_20mw_facility_40mw_procurement(self):
        """Standard scenario: 20 MW facility, 40 MW procurement (2N).

        Hand calculation:
            facility_kw = 20,000 kW
            procurement_kw = 40,000 kW

            Cooling (roof):    20,000 × 0.15 = 3,000.0 m²
            Diesel gensets:    40,000 × 0.008 = 320.0 m²
            Transformers:      40,000 × 0.004 = 160.0 m²
            Substation:        40,000 × 0.005 = 200.0 m²

            Total gray space:  320 + 160 + 200 = 680.0 m²
            Total roof:        3,000.0 m²
            Total:             3,680.0 m²

            Genset units: ceil(40,000 / 2,000) = 20
        """
        result = compute_footprint(
            facility_power_mw=20.0,
            procurement_power_mw=40.0,
            buildable_footprint_m2=5000.0,
            gray_space_m2=7000.0,
            roof_usable=True,
        )

        assert isinstance(result, FootprintResult)

        # ── Per-element checks ──
        assert len(result.elements) == 4

        cooling = result.elements[0]
        assert cooling.name == "Cooling Equipment (Condensers / Dry Coolers)"
        assert cooling.area_m2 == 3000.0
        assert cooling.location == "roof"
        assert cooling.sizing_basis_kw == 20000.0
        assert cooling.m2_per_kw_used == 0.15

        backup = result.elements[1]
        assert backup.area_m2 == 320.0
        assert backup.location == "gray_space"
        assert backup.num_units == 20
        assert backup.unit_size_kw == 2000.0

        transformer = result.elements[2]
        assert transformer.area_m2 == 160.0

        substation = result.elements[3]
        assert substation.area_m2 == 200.0

        # ── Aggregates ──
        assert result.total_gray_space_equipment_m2 == 680.0
        assert result.total_roof_equipment_m2 == 3000.0
        assert result.total_infrastructure_m2 == 3680.0

        # ── Fit check ──
        assert result.gray_space_m2 == 7000.0
        assert result.building_roof_m2 == 5000.0

        # Gray space utilization: 680 / 7000 ≈ 0.0971
        assert result.gray_space_utilization_ratio == pytest.approx(680.0 / 7000.0, abs=0.0001)
        assert result.gray_space_fits is True

        # Roof utilization: 3000 / 5000 = 0.60
        assert result.roof_utilization_ratio == pytest.approx(0.60, abs=0.0001)
        assert result.roof_fits is True
        assert result.all_fits is True

        # ── Backward-compatible aliases ──
        assert result.ground_utilization_ratio == result.gray_space_utilization_ratio
        assert result.ground_fits == result.gray_space_fits

    def test_5mw_facility_5mw_procurement_n_redundancy(self):
        """Small site with N redundancy: 5 MW facility, 5 MW procurement.

        Hand calculation:
            facility_kw = 5,000 kW
            procurement_kw = 5,000 kW

            Cooling (roof):    5,000 × 0.15 = 750.0 m²
            Diesel gensets:    5,000 × 0.008 = 40.0 m²
            Transformers:      5,000 × 0.004 = 20.0 m²
            Substation:        5,000 × 0.005 = 25.0 m²

            Total gray space: 85.0 m²
            Genset units: ceil(5,000 / 2,000) = 3
        """
        result = compute_footprint(
            facility_power_mw=5.0,
            procurement_power_mw=5.0,
            buildable_footprint_m2=2000.0,
            gray_space_m2=3000.0,
            roof_usable=True,
        )

        assert result.total_gray_space_equipment_m2 == 85.0
        assert result.total_roof_equipment_m2 == 750.0
        assert result.backup_num_units == 3  # ceil(5000/2000) = 3


class TestBackupPowerTypes:
    """Test footprint calculation with each backup power technology.

    Each technology has different m²/kW and module sizes.
    All sourced from assumptions.py BACKUP_POWER and FOOTPRINT dicts.
    """

    def _make_result(self, backup_type):
        return compute_footprint(
            facility_power_mw=5.0,
            procurement_power_mw=10.0,
            buildable_footprint_m2=2000.0,
            gray_space_m2=3000.0,
            roof_usable=True,
            backup_power_type=backup_type,
        )

    def test_diesel_genset(self):
        """Diesel genset: 0.008 m²/kW, 2000 kW modules.

        procurement_kw = 10,000
        area = 10,000 × 0.008 = 80 m²
        units = ceil(10,000 / 2,000) = 5
        """
        result = self._make_result(BackupPowerType.DIESEL_GENSET)
        backup = result.elements[1]
        assert backup.area_m2 == 80.0
        assert backup.num_units == 5
        assert backup.unit_size_kw == 2000.0

    def test_natural_gas_genset(self):
        """Natural gas genset: 0.010 m²/kW, 2500 kW modules.

        procurement_kw = 10,000
        area = 10,000 × 0.010 = 100 m²
        units = ceil(10,000 / 2,500) = 4
        """
        result = self._make_result(BackupPowerType.NATURAL_GAS_GENSET)
        backup = result.elements[1]
        assert backup.area_m2 == 100.0
        assert backup.num_units == 4
        assert backup.unit_size_kw == 2500.0

    def test_sofc_fuel_cell(self):
        """SOFC fuel cell: 0.015 m²/kW, 300 kW modules.

        procurement_kw = 10,000
        area = 10,000 × 0.015 = 150 m²
        units = ceil(10,000 / 300) = 34
        """
        result = self._make_result(BackupPowerType.SOFC_FUEL_CELL)
        backup = result.elements[1]
        assert backup.area_m2 == 150.0
        assert backup.num_units == 34
        assert backup.unit_size_kw == 300.0

    def test_pem_fuel_cell(self):
        """PEM fuel cell (H₂): 0.020 m²/kW, 250 kW modules.

        procurement_kw = 10,000
        area = 10,000 × 0.020 = 200 m²
        units = ceil(10,000 / 250) = 40
        """
        result = self._make_result(BackupPowerType.PEM_FUEL_CELL)
        backup = result.elements[1]
        assert backup.area_m2 == 200.0
        assert backup.num_units == 40
        assert backup.unit_size_kw == 250.0

    def test_rotary_ups_flywheel(self):
        """Rotary UPS + Flywheel: 0.005 m²/kW, 2000 kW modules.

        procurement_kw = 10,000
        area = 10,000 × 0.005 = 50 m²
        units = ceil(10,000 / 2,000) = 5
        """
        result = self._make_result(BackupPowerType.ROTARY_UPS_FLYWHEEL)
        backup = result.elements[1]
        assert backup.area_m2 == 50.0
        assert backup.num_units == 5
        assert backup.unit_size_kw == 2000.0


class TestFitCheck:
    """Test gray space and roof fit analysis."""

    def test_gray_space_overflow(self):
        """Gray space too small for equipment.

        gray_space = 500 m²
        procurement = 100 MW (100,000 kW):
            Diesel gensets:  100,000 × 0.008 = 800 m²
            Transformers:    100,000 × 0.004 = 400 m²
            Substation:      100,000 × 0.005 = 500 m²
            Total gray space equipment = 1,700 m² > 500 m² → DOES NOT FIT
        """
        result = compute_footprint(
            facility_power_mw=50.0,
            procurement_power_mw=100.0,
            buildable_footprint_m2=2500.0,
            gray_space_m2=500.0,
            roof_usable=True,
        )

        assert result.gray_space_m2 == 500.0
        assert result.total_gray_space_equipment_m2 == 1700.0
        assert result.gray_space_fits is False
        assert result.gray_space_utilization_ratio == pytest.approx(1700.0 / 500.0, abs=0.0001)
        assert result.all_fits is False
        assert len(result.warnings) > 0

    def test_roof_overflow(self):
        """Roof cooling exceeds building footprint.

        Building footprint = 1,000 m² (= roof area)
        Facility = 20 MW → cooling = 20,000 × 0.15 = 3,000 m²
        Roof utilization = 3,000 / 1,000 = 3.0 → DOES NOT FIT
        """
        result = compute_footprint(
            facility_power_mw=20.0,
            procurement_power_mw=40.0,
            buildable_footprint_m2=1000.0,
            gray_space_m2=10000.0,
            roof_usable=True,
        )

        assert result.total_roof_equipment_m2 == 3000.0
        assert result.building_roof_m2 == 1000.0
        assert result.roof_fits is False
        assert result.roof_utilization_ratio == pytest.approx(3.0, abs=0.0001)
        assert result.all_fits is False
        # Gray space may still fit
        assert result.gray_space_fits is True

    def test_generous_site_everything_fits(self):
        """Large site with modest power — everything fits easily.

        gray_space = 40,000 m², building footprint = 10,000 m²
        Facility = 10 MW, Procurement = 20 MW

        Gray space: 20,000 × (0.008 + 0.004 + 0.005) = 340 m² << 40,000
        Roof: 10,000 × 0.15 = 1,500 m² << 10,000
        """
        result = compute_footprint(
            facility_power_mw=10.0,
            procurement_power_mw=20.0,
            buildable_footprint_m2=10000.0,
            gray_space_m2=40000.0,
            roof_usable=True,
        )

        assert result.gray_space_fits is True
        assert result.roof_fits is True
        assert result.all_fits is True
        assert result.gray_space_utilization_ratio < 0.05  # Very low
        assert result.roof_utilization_ratio < 0.20

    def test_zero_gray_space(self):
        """Zero gray space — equipment cannot fit.

        gray_space = 0 m² → gray space utilization = inf
        """
        result = compute_footprint(
            facility_power_mw=5.0,
            procurement_power_mw=10.0,
            buildable_footprint_m2=5000.0,
            gray_space_m2=0.0,
            roof_usable=True,
        )

        assert result.gray_space_utilization_ratio == float("inf")
        assert result.gray_space_fits is False

    def test_roof_not_usable_cooling_in_gray_space(self):
        """When roof_usable=False, cooling goes to gray space.

        facility_kw = 10,000, procurement_kw = 20,000
        Cooling:       10,000 × 0.15 = 1,500 m² → gray_space (not roof)
        Diesel genset: 20,000 × 0.008 = 160.0 m²
        Transformer:   20,000 × 0.004 = 80.0 m²
        Substation:    20,000 × 0.005 = 100.0 m²
        Total gray space: 1,500 + 160 + 80 + 100 = 1,840 m²
        Total roof: 0 m²
        """
        result = compute_footprint(
            facility_power_mw=10.0,
            procurement_power_mw=20.0,
            buildable_footprint_m2=5000.0,
            gray_space_m2=5000.0,
            roof_usable=False,
        )

        cooling = result.elements[0]
        assert cooling.location == "gray_space"

        assert result.total_gray_space_equipment_m2 == 1840.0
        assert result.total_roof_equipment_m2 == 0.0
        assert result.roof_utilization_ratio == 0.0
        assert result.roof_fits is True  # No roof equipment
        assert result.gray_space_fits is True  # 1840 < 5000
        assert result.roof_usable is False
        # Should have a warning about roof not usable
        assert any("Roof not usable" in w for w in result.warnings)

    def test_tight_gray_space_warning(self):
        """Gray space > 85% utilized should produce a warning.

        gray_space = 800 m²
        procurement_kw = 10,000
        Gray space equipment = 10,000 × (0.008 + 0.004 + 0.005) = 170 m²
        Needs gray_space such that 170/gray_space > 0.85 → gray_space < 200
        """
        result = compute_footprint(
            facility_power_mw=5.0,
            procurement_power_mw=10.0,
            buildable_footprint_m2=2000.0,
            gray_space_m2=195.0,  # 170/195 ≈ 0.87
            roof_usable=True,
        )

        assert result.gray_space_fits is True
        assert result.gray_space_utilization_ratio > 0.85
        assert any("tight margin" in w for w in result.warnings)


class TestCoolingOverride:
    """Test cooling m²/kW override for different cooling technologies."""

    def test_override_to_air_cooled_condenser_high(self):
        """Override cooling factor to 0.25 m²/kW (large air-cooled condensers).

        facility_kw = 10,000
        cooling area = 10,000 × 0.25 = 2,500 m²
        """
        result = compute_footprint(
            facility_power_mw=10.0,
            procurement_power_mw=20.0,
            buildable_footprint_m2=5000.0,
            gray_space_m2=5000.0,
            cooling_m2_per_kw_override=0.25,
        )

        cooling = result.elements[0]
        assert cooling.area_m2 == 2500.0
        assert cooling.m2_per_kw_used == 0.25

    def test_override_to_compact_cooling(self):
        """Override to 0.10 m²/kW (compact cooling, e.g. water-cooled towers).

        facility_kw = 10,000
        cooling area = 10,000 × 0.10 = 1,000 m²
        """
        result = compute_footprint(
            facility_power_mw=10.0,
            procurement_power_mw=20.0,
            buildable_footprint_m2=5000.0,
            gray_space_m2=5000.0,
            cooling_m2_per_kw_override=0.10,
        )

        cooling = result.elements[0]
        assert cooling.area_m2 == 1000.0
        assert cooling.m2_per_kw_used == 0.10


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_power(self):
        """Zero power — all footprints should be zero."""
        result = compute_footprint(
            facility_power_mw=0.0,
            procurement_power_mw=0.0,
            buildable_footprint_m2=5000.0,
            gray_space_m2=7000.0,
        )

        assert result.total_gray_space_equipment_m2 == 0.0
        assert result.total_roof_equipment_m2 == 0.0
        assert result.total_infrastructure_m2 == 0.0
        assert result.backup_num_units == 0
        assert result.gray_space_fits is True
        assert result.roof_fits is True
        assert result.all_fits is True

    def test_negative_facility_power_raises(self):
        """Negative facility power should raise ValueError."""
        with pytest.raises(ValueError, match="facility_power_mw cannot be negative"):
            compute_footprint(
                facility_power_mw=-5.0,
                procurement_power_mw=10.0,
                buildable_footprint_m2=5000.0,
                gray_space_m2=7000.0,
            )

    def test_negative_procurement_power_raises(self):
        """Negative procurement power should raise ValueError."""
        with pytest.raises(ValueError, match="procurement_power_mw cannot be negative"):
            compute_footprint(
                facility_power_mw=5.0,
                procurement_power_mw=-10.0,
                buildable_footprint_m2=5000.0,
                gray_space_m2=7000.0,
            )

    def test_genset_unit_count_rounding(self):
        """Verify ceil rounding for non-integer unit counts.

        procurement_kw = 5,001 (not evenly divisible by 2,000)
        units = ceil(5,001 / 2,000) = 3
        """
        result = compute_footprint(
            facility_power_mw=2.5,
            procurement_power_mw=5.001,
            buildable_footprint_m2=2000.0,
            gray_space_m2=3000.0,
        )
        assert result.backup_num_units == 3

    def test_exactly_divisible_unit_count(self):
        """When procurement is exactly divisible by module size.

        procurement_kw = 6,000
        units = ceil(6,000 / 2,000) = 3
        """
        result = compute_footprint(
            facility_power_mw=3.0,
            procurement_power_mw=6.0,
            buildable_footprint_m2=2000.0,
            gray_space_m2=3000.0,
        )
        assert result.backup_num_units == 3

    def test_very_small_power(self):
        """Very small power (0.1 MW) — still produces valid results.

        facility_kw = 100 kW
        procurement_kw = 200 kW

        Cooling (roof): 100 × 0.15 = 15.0 m²
        Diesel genset:  200 × 0.008 = 1.6 m²
        Transformer:    200 × 0.004 = 0.8 m²
        Substation:     200 × 0.005 = 1.0 m²

        Units: ceil(200 / 2000) = 1
        """
        result = compute_footprint(
            facility_power_mw=0.1,
            procurement_power_mw=0.2,
            buildable_footprint_m2=500.0,
            gray_space_m2=2000.0,
        )

        assert result.total_roof_equipment_m2 == 15.0
        assert result.total_gray_space_equipment_m2 == pytest.approx(3.4, abs=0.1)
        assert result.backup_num_units == 1


class TestElementSources:
    """Verify that every element has a non-empty source citation."""

    def test_all_elements_have_sources(self):
        """Every FootprintElement must have a non-empty source string."""
        result = compute_footprint(
            facility_power_mw=10.0,
            procurement_power_mw=20.0,
            buildable_footprint_m2=5000.0,
            gray_space_m2=5000.0,
        )

        for element in result.elements:
            assert element.source, f"Element '{element.name}' has no source citation"
            assert len(element.source) > 5, (
                f"Element '{element.name}' has suspiciously short source: '{element.source}'"
            )

    def test_element_locations_are_valid(self):
        """Each element location must be 'gray_space' or 'roof'."""
        result = compute_footprint(
            facility_power_mw=10.0,
            procurement_power_mw=20.0,
            buildable_footprint_m2=5000.0,
            gray_space_m2=5000.0,
        )

        for element in result.elements:
            assert element.location in ("gray_space", "roof"), (
                f"Element '{element.name}' has invalid location: '{element.location}'"
            )


class TestConsistencyWithAssumptions:
    """Verify footprint.py uses values from assumptions.py, not hardcoded."""

    def _make_result(self, **kwargs):
        defaults = dict(
            facility_power_mw=1.0,
            procurement_power_mw=2.0,
            buildable_footprint_m2=500.0,
            gray_space_m2=2000.0,
        )
        defaults.update(kwargs)
        return compute_footprint(**defaults)

    def test_cooling_default_matches_assumptions(self):
        result = self._make_result()
        cooling = result.elements[0]
        expected = FOOTPRINT["cooling_skid_m2_per_kw_rejected"]["default"]
        assert cooling.m2_per_kw_used == expected

    def test_transformer_default_matches_assumptions(self):
        result = self._make_result()
        transformer = result.elements[2]
        expected = FOOTPRINT["transformer_m2_per_kw"]["default"]
        assert transformer.m2_per_kw_used == expected

    def test_substation_default_matches_assumptions(self):
        result = self._make_result()
        substation = result.elements[3]
        expected = FOOTPRINT["substation_m2_per_kw"]["default"]
        assert substation.m2_per_kw_used == expected

    def test_diesel_module_size_matches_assumptions(self):
        result = self._make_result(backup_power_type=BackupPowerType.DIESEL_GENSET)
        expected = float(BACKUP_POWER["Diesel Genset"]["module_size_kw"])
        assert result.backup_unit_size_kw == expected
