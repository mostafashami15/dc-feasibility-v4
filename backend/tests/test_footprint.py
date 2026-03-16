"""
Tests for footprint.py — Infrastructure Footprint Calculation
==============================================================
Every expected value is hand-calculated from the formulas in the
Architecture Agreement Section 3.11 and defaults in assumptions.py.

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

            Total ground:  320 + 160 + 200 = 680.0 m²
            Total roof:    3,000.0 m²
            Total:         3,680.0 m²

            Genset units: ceil(40,000 / 2,000) = 20
        """
        result = compute_footprint(
            facility_power_mw=20.0,
            procurement_power_mw=40.0,
            buildable_footprint_m2=5000.0,
            land_area_m2=12000.0,
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
        assert backup.location == "ground"
        assert backup.num_units == 20
        assert backup.unit_size_kw == 2000.0

        transformer = result.elements[2]
        assert transformer.area_m2 == 160.0

        substation = result.elements[3]
        assert substation.area_m2 == 200.0

        # ── Aggregates ──
        assert result.total_ground_m2 == 680.0
        assert result.total_roof_m2 == 3000.0
        assert result.total_infrastructure_m2 == 3680.0

        # ── Fit check ──
        # Available outdoor = 12,000 - 5,000 = 7,000 m²
        assert result.available_outdoor_m2 == 7000.0
        assert result.building_roof_m2 == 5000.0

        # Ground utilization: 680 / 7000 ≈ 0.0971
        assert result.ground_utilization_ratio == pytest.approx(680.0 / 7000.0, abs=0.0001)
        assert result.ground_fits is True

        # Roof utilization: 3000 / 5000 = 0.60
        assert result.roof_utilization_ratio == pytest.approx(0.60, abs=0.0001)
        assert result.roof_fits is True
        assert result.all_fits is True

    def test_5mw_facility_5mw_procurement_n_redundancy(self):
        """Small site with N redundancy: 5 MW facility, 5 MW procurement.

        Hand calculation:
            facility_kw = 5,000 kW
            procurement_kw = 5,000 kW

            Cooling (roof):    5,000 × 0.15 = 750.0 m²
            Diesel gensets:    5,000 × 0.008 = 40.0 m²
            Transformers:      5,000 × 0.004 = 20.0 m²
            Substation:        5,000 × 0.005 = 25.0 m²

            Total ground: 85.0 m²
            Genset units: ceil(5,000 / 2,000) = 3
        """
        result = compute_footprint(
            facility_power_mw=5.0,
            procurement_power_mw=5.0,
            buildable_footprint_m2=2000.0,
            land_area_m2=5000.0,
        )

        assert result.total_ground_m2 == 85.0
        assert result.total_roof_m2 == 750.0
        assert result.backup_num_units == 3  # ceil(5000/2000) = 3


class TestBackupPowerTypes:
    """Test footprint calculation with each backup power technology.

    Each technology has different m²/kW and module sizes.
    All sourced from assumptions.py BACKUP_POWER and FOOTPRINT dicts.
    """

    def test_diesel_genset(self):
        """Diesel genset: 0.008 m²/kW, 2000 kW modules.

        procurement_kw = 10,000
        area = 10,000 × 0.008 = 80 m²
        units = ceil(10,000 / 2,000) = 5
        """
        result = compute_footprint(
            facility_power_mw=5.0,
            procurement_power_mw=10.0,
            buildable_footprint_m2=2000.0,
            land_area_m2=5000.0,
            backup_power_type=BackupPowerType.DIESEL_GENSET,
        )
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
        result = compute_footprint(
            facility_power_mw=5.0,
            procurement_power_mw=10.0,
            buildable_footprint_m2=2000.0,
            land_area_m2=5000.0,
            backup_power_type=BackupPowerType.NATURAL_GAS_GENSET,
        )
        backup = result.elements[1]
        assert backup.area_m2 == 100.0
        assert backup.num_units == 4
        assert backup.unit_size_kw == 2500.0

    def test_sofc_fuel_cell(self):
        """SOFC fuel cell: 0.015 m²/kW, 300 kW modules.

        procurement_kw = 10,000
        area = 10,000 × 0.015 = 150 m²
        units = ceil(10,000 / 300) = 34
        Source: Bloom Energy Server ES5 datasheet (2023)
        """
        result = compute_footprint(
            facility_power_mw=5.0,
            procurement_power_mw=10.0,
            buildable_footprint_m2=2000.0,
            land_area_m2=5000.0,
            backup_power_type=BackupPowerType.SOFC_FUEL_CELL,
        )
        backup = result.elements[1]
        assert backup.area_m2 == 150.0
        assert backup.num_units == 34  # ceil(10000/300)
        assert backup.unit_size_kw == 300.0

    def test_pem_fuel_cell(self):
        """PEM fuel cell (H₂): 0.020 m²/kW, 250 kW modules.

        procurement_kw = 10,000
        area = 10,000 × 0.020 = 200 m²
        units = ceil(10,000 / 250) = 40
        Source: Ballard/Plug Power datasheets
        """
        result = compute_footprint(
            facility_power_mw=5.0,
            procurement_power_mw=10.0,
            buildable_footprint_m2=2000.0,
            land_area_m2=5000.0,
            backup_power_type=BackupPowerType.PEM_FUEL_CELL,
        )
        backup = result.elements[1]
        assert backup.area_m2 == 200.0
        assert backup.num_units == 40  # ceil(10000/250)
        assert backup.unit_size_kw == 250.0

    def test_rotary_ups_flywheel(self):
        """Rotary UPS + Flywheel: 0.005 m²/kW, 2000 kW modules.

        procurement_kw = 10,000
        area = 10,000 × 0.005 = 50 m²
        units = ceil(10,000 / 2,000) = 5
        Source: Hitec/Piller DRUPS datasheets
        """
        result = compute_footprint(
            facility_power_mw=5.0,
            procurement_power_mw=10.0,
            buildable_footprint_m2=2000.0,
            land_area_m2=5000.0,
            backup_power_type=BackupPowerType.ROTARY_UPS_FLYWHEEL,
        )
        backup = result.elements[1]
        assert backup.area_m2 == 50.0
        assert backup.num_units == 5
        assert backup.unit_size_kw == 2000.0


class TestFitCheck:
    """Test site fit analysis — does the infrastructure fit?"""

    def test_tight_site_ground_overflow(self):
        """Site where ground equipment exceeds available outdoor area.

        Land = 3,000 m², Building = 2,500 m²
        Available outdoor = 500 m²

        With procurement = 100 MW (100,000 kW):
            Diesel gensets:  100,000 × 0.008 = 800 m²
            Transformers:    100,000 × 0.004 = 400 m²
            Substation:      100,000 × 0.005 = 500 m²
            Total ground = 1,700 m² > 500 m² → DOES NOT FIT
        """
        result = compute_footprint(
            facility_power_mw=50.0,
            procurement_power_mw=100.0,
            buildable_footprint_m2=2500.0,
            land_area_m2=3000.0,
        )

        assert result.available_outdoor_m2 == 500.0
        assert result.total_ground_m2 == 1700.0
        assert result.ground_fits is False
        assert result.ground_utilization_ratio == pytest.approx(1700.0 / 500.0, abs=0.0001)
        assert result.all_fits is False

    def test_roof_overflow(self):
        """Site where roof cooling exceeds building footprint.

        Building footprint = 1,000 m²
        Facility = 20 MW → cooling = 20,000 × 0.15 = 3,000 m²
        Roof utilization = 3,000 / 1,000 = 3.0 → DOES NOT FIT
        """
        result = compute_footprint(
            facility_power_mw=20.0,
            procurement_power_mw=40.0,
            buildable_footprint_m2=1000.0,
            land_area_m2=10000.0,
        )

        assert result.total_roof_m2 == 3000.0
        assert result.building_roof_m2 == 1000.0
        assert result.roof_fits is False
        assert result.roof_utilization_ratio == pytest.approx(3.0, abs=0.0001)
        assert result.all_fits is False
        # Ground may still fit — check separately
        assert result.ground_fits is True

    def test_generous_site_everything_fits(self):
        """Large site with modest power — everything fits easily.

        Land = 50,000 m², Building = 10,000 m²
        Available outdoor = 40,000 m²
        Facility = 10 MW, Procurement = 20 MW

        Ground: 20,000 × (0.008 + 0.004 + 0.005) = 340 m² << 40,000
        Roof: 10,000 × 0.15 = 1,500 m² << 10,000
        """
        result = compute_footprint(
            facility_power_mw=10.0,
            procurement_power_mw=20.0,
            buildable_footprint_m2=10000.0,
            land_area_m2=50000.0,
        )

        assert result.ground_fits is True
        assert result.roof_fits is True
        assert result.all_fits is True
        assert result.ground_utilization_ratio < 0.05  # Very low
        assert result.roof_utilization_ratio < 0.20

    def test_zero_outdoor_area(self):
        """Building covers 100% of land — no outdoor area available.

        available_outdoor = 0 m² → ground utilization = inf
        """
        result = compute_footprint(
            facility_power_mw=5.0,
            procurement_power_mw=10.0,
            buildable_footprint_m2=5000.0,
            land_area_m2=5000.0,  # Building fills entire site
        )

        assert result.available_outdoor_m2 == 0.0
        assert result.ground_utilization_ratio == float("inf")
        assert result.ground_fits is False


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
            land_area_m2=15000.0,
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
            land_area_m2=15000.0,
            cooling_m2_per_kw_override=0.10,
        )

        cooling = result.elements[0]
        assert cooling.area_m2 == 1000.0
        assert cooling.m2_per_kw_used == 0.10


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_power(self):
        """Zero power — all footprints should be zero.

        This can happen during early site exploration when power
        is not yet confirmed.
        """
        result = compute_footprint(
            facility_power_mw=0.0,
            procurement_power_mw=0.0,
            buildable_footprint_m2=5000.0,
            land_area_m2=12000.0,
        )

        assert result.total_ground_m2 == 0.0
        assert result.total_roof_m2 == 0.0
        assert result.total_infrastructure_m2 == 0.0
        assert result.backup_num_units == 0
        assert result.ground_fits is True
        assert result.roof_fits is True
        assert result.all_fits is True

    def test_negative_facility_power_raises(self):
        """Negative facility power should raise ValueError."""
        with pytest.raises(ValueError, match="facility_power_mw cannot be negative"):
            compute_footprint(
                facility_power_mw=-5.0,
                procurement_power_mw=10.0,
                buildable_footprint_m2=5000.0,
                land_area_m2=12000.0,
            )

    def test_negative_procurement_power_raises(self):
        """Negative procurement power should raise ValueError."""
        with pytest.raises(ValueError, match="procurement_power_mw cannot be negative"):
            compute_footprint(
                facility_power_mw=5.0,
                procurement_power_mw=-10.0,
                buildable_footprint_m2=5000.0,
                land_area_m2=12000.0,
            )

    def test_genset_unit_count_rounding(self):
        """Verify ceil rounding for non-integer unit counts.

        procurement_kw = 5,001 (not evenly divisible by 2,000)
        units = ceil(5,001 / 2,000) = 3 (not 2.5 or 2)
        """
        result = compute_footprint(
            facility_power_mw=2.5,
            procurement_power_mw=5.001,
            buildable_footprint_m2=2000.0,
            land_area_m2=5000.0,
        )
        assert result.backup_num_units == 3

    def test_exactly_divisible_unit_count(self):
        """When procurement is exactly divisible by module size.

        procurement_kw = 6,000
        units = ceil(6,000 / 2,000) = 3 (exactly, no rounding needed)
        """
        result = compute_footprint(
            facility_power_mw=3.0,
            procurement_power_mw=6.0,
            buildable_footprint_m2=2000.0,
            land_area_m2=5000.0,
        )
        assert result.backup_num_units == 3

    def test_very_small_power(self):
        """Very small power (0.1 MW) — still produces valid results.

        facility_kw = 100 kW
        procurement_kw = 200 kW

        Cooling:       100 × 0.15 = 15.0 m²
        Diesel genset: 200 × 0.008 = 1.6 m²
        Transformer:   200 × 0.004 = 0.8 m²
        Substation:    200 × 0.005 = 1.0 m²

        Units: ceil(200 / 2000) = 1
        """
        result = compute_footprint(
            facility_power_mw=0.1,
            procurement_power_mw=0.2,
            buildable_footprint_m2=500.0,
            land_area_m2=2000.0,
        )

        assert result.total_roof_m2 == 15.0
        assert result.total_ground_m2 == pytest.approx(3.4, abs=0.1)
        assert result.backup_num_units == 1


class TestElementSources:
    """Verify that every element has a non-empty source citation.

    Rule: Every number has a source (Architecture Agreement principle #2).
    """

    def test_all_elements_have_sources(self):
        """Every FootprintElement must have a non-empty source string."""
        result = compute_footprint(
            facility_power_mw=10.0,
            procurement_power_mw=20.0,
            buildable_footprint_m2=5000.0,
            land_area_m2=15000.0,
        )

        for element in result.elements:
            assert element.source, f"Element '{element.name}' has no source citation"
            assert len(element.source) > 5, (
                f"Element '{element.name}' has suspiciously short source: '{element.source}'"
            )

    def test_element_locations_are_valid(self):
        """Each element location must be 'ground' or 'roof'."""
        result = compute_footprint(
            facility_power_mw=10.0,
            procurement_power_mw=20.0,
            buildable_footprint_m2=5000.0,
            land_area_m2=15000.0,
        )

        for element in result.elements:
            assert element.location in ("ground", "roof"), (
                f"Element '{element.name}' has invalid location: '{element.location}'"
            )


class TestConsistencyWithAssumptions:
    """Verify footprint.py uses values from assumptions.py, not hardcoded."""

    def test_cooling_default_matches_assumptions(self):
        """Cooling m²/kW default must match FOOTPRINT dict."""
        result = compute_footprint(
            facility_power_mw=1.0,
            procurement_power_mw=2.0,
            buildable_footprint_m2=500.0,
            land_area_m2=2000.0,
        )
        cooling = result.elements[0]
        expected = FOOTPRINT["cooling_skid_m2_per_kw_rejected"]["default"]
        assert cooling.m2_per_kw_used == expected

    def test_transformer_default_matches_assumptions(self):
        """Transformer m²/kW default must match FOOTPRINT dict."""
        result = compute_footprint(
            facility_power_mw=1.0,
            procurement_power_mw=2.0,
            buildable_footprint_m2=500.0,
            land_area_m2=2000.0,
        )
        transformer = result.elements[2]
        expected = FOOTPRINT["transformer_m2_per_kw"]["default"]
        assert transformer.m2_per_kw_used == expected

    def test_substation_default_matches_assumptions(self):
        """Substation m²/kW default must match FOOTPRINT dict."""
        result = compute_footprint(
            facility_power_mw=1.0,
            procurement_power_mw=2.0,
            buildable_footprint_m2=500.0,
            land_area_m2=2000.0,
        )
        substation = result.elements[3]
        expected = FOOTPRINT["substation_m2_per_kw"]["default"]
        assert substation.m2_per_kw_used == expected

    def test_diesel_module_size_matches_assumptions(self):
        """Diesel genset module size must match BACKUP_POWER dict."""
        result = compute_footprint(
            facility_power_mw=1.0,
            procurement_power_mw=2.0,
            buildable_footprint_m2=500.0,
            land_area_m2=2000.0,
            backup_power_type=BackupPowerType.DIESEL_GENSET,
        )
        expected = float(BACKUP_POWER["Diesel Genset"]["module_size_kw"])
        assert result.backup_unit_size_kw == expected
