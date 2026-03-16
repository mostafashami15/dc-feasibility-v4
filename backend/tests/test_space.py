"""
Tests for space.py — Site geometry calculations.

Every test uses hand-computed expected values so we can verify
the engine produces correct results. Run with:

    cd backend
    pytest tests/test_space.py -v
"""

import pytest
from engine.models import Site, CoolingType, BuildableAreaMode
from engine.space import compute_space, compute_it_load_from_space


# ─────────────────────────────────────────────────────────────
# Test 1: Basic site with default parameters
# ─────────────────────────────────────────────────────────────
def test_basic_site_defaults():
    """25,000 m² site with all defaults.

    Hand calculation:
        Buildable = 25000 × 0.50 = 12,500 m²
        Gross     = 12500 × 1 floor = 12,500 m²
        Whitespace = 12500 × 0.40 = 5,000 m²
        Max racks = 5000 / 3.0 = 1,666 racks
        No cooling adjustment → effective = 1,666
    """
    site = Site(name="Basic Test", land_area_m2=25000)
    result = compute_space(site)

    assert result.buildable_footprint_m2 == 12500.0
    assert result.gross_building_area_m2 == 12500.0
    assert result.it_whitespace_m2 == 5000.0
    assert result.support_area_m2 == 7500.0
    assert result.max_racks_by_space == 1666
    assert result.effective_racks == 1666  # No cooling type → factor 1.0
    assert result.active_floors == 1
    assert result.whitespace_adjustment_factor == 1.0


# ─────────────────────────────────────────────────────────────
# Test 2: Multi-floor site
# ─────────────────────────────────────────────────────────────
def test_multi_floor():
    """10,000 m² site, 3 floors.

    Hand calculation:
        Buildable = 10000 × 0.50 = 5,000 m²
        Gross     = 5000 × 3 = 15,000 m²
        Whitespace = 15000 × 0.40 = 6,000 m²
        Max racks = 6000 / 3.0 = 2,000 racks
    """
    site = Site(name="Multi Floor", land_area_m2=10000, num_floors=3)
    result = compute_space(site)

    assert result.buildable_footprint_m2 == 5000.0
    assert result.gross_building_area_m2 == 15000.0
    assert result.it_whitespace_m2 == 6000.0
    assert result.max_racks_by_space == 2000
    assert result.active_floors == 3


# ─────────────────────────────────────────────────────────────
# Test 3: Height-limited site
# ─────────────────────────────────────────────────────────────
def test_height_limited():
    """Site with 10m height limit and 4.5m floor-to-floor.

    Hand calculation:
        Max floors from height = floor(10.0 / 4.5) = 2
        User requested 5 floors → capped at 2
        Buildable = 20000 × 0.50 = 10,000 m²
        Gross     = 10000 × 2 = 20,000 m²
        Whitespace = 20000 × 0.40 = 8,000 m²
        Max racks = 8000 / 3.0 = 2,666 racks
    """
    site = Site(
        name="Height Limited",
        land_area_m2=20000,
        max_building_height_m=10.0,
        floor_to_floor_height_m=4.5,
        num_floors=5,  # Wants 5, but height only allows 2
    )
    result = compute_space(site)

    assert result.active_floors == 2
    assert result.gross_building_area_m2 == 20000.0
    assert result.max_racks_by_space == 2666


# ─────────────────────────────────────────────────────────────
# Test 4: Absolute buildable area mode
# ─────────────────────────────────────────────────────────────
def test_absolute_buildable_area():
    """Site with explicit buildable area from planning permission.

    Hand calculation:
        Buildable = 8000 m² (explicit, ignores ratio)
        Gross     = 8000 × 1 = 8,000 m²
        Whitespace = 8000 × 0.40 = 3,200 m²
        Max racks = 3200 / 3.0 = 1,066 racks
    """
    site = Site(
        name="Absolute Mode",
        land_area_m2=20000,
        buildable_area_mode=BuildableAreaMode.ABSOLUTE,
        buildable_area_m2=8000,
    )
    result = compute_space(site)

    assert result.buildable_footprint_m2 == 8000.0
    assert result.it_whitespace_m2 == 3200.0
    assert result.max_racks_by_space == 1066


# ─────────────────────────────────────────────────────────────
# Test 5: CRAC cooling adjustment (0.92)
# ─────────────────────────────────────────────────────────────
def test_crac_whitespace_adjustment():
    """CRAC units consume ~8% of white space.

    Hand calculation:
        Same as test_basic with 25,000 m²:
        Max racks = 1,666
        CRAC adjustment = 0.92
        Effective = floor(1666 × 0.92) = 1,532
    """
    site = Site(name="CRAC Test", land_area_m2=25000)
    result = compute_space(site, cooling_type=CoolingType.CRAC_DX)

    assert result.whitespace_adjustment_factor == 0.92
    assert result.max_racks_by_space == 1666  # Before adjustment
    assert result.effective_racks == 1532  # After adjustment


# ─────────────────────────────────────────────────────────────
# Test 6: DLC cooling adjustment (0.92)
# ─────────────────────────────────────────────────────────────
def test_dlc_whitespace_adjustment():
    """DLC in-row CDUs take ~8% of rack slots.

    Same site as above:
        Effective = floor(1666 × 0.92) = 1,532
    """
    site = Site(name="DLC Test", land_area_m2=25000)
    result = compute_space(site, cooling_type=CoolingType.DLC)

    assert result.whitespace_adjustment_factor == 0.92
    assert result.effective_racks == 1532


# ─────────────────────────────────────────────────────────────
# Test 7: Immersion cooling adjustment (0.85)
# ─────────────────────────────────────────────────────────────
def test_immersion_whitespace_adjustment():
    """Immersion tanks are wider than racks, need service access.

    Hand calculation:
        Max racks = 1,666
        Immersion adjustment = 0.85
        Effective = floor(1666 × 0.85) = 1,416
    """
    site = Site(name="Immersion Test", land_area_m2=25000)
    result = compute_space(site, cooling_type=CoolingType.IMMERSION)

    assert result.whitespace_adjustment_factor == 0.85
    assert result.effective_racks == 1416


# ─────────────────────────────────────────────────────────────
# Test 8: Air chiller — no adjustment (1.00)
# ─────────────────────────────────────────────────────────────
def test_air_chiller_no_adjustment():
    """AHU/chiller in separate plant room — no IT hall impact."""
    site = Site(name="Air Chiller Test", land_area_m2=25000)
    result = compute_space(site, cooling_type=CoolingType.AIR_CHILLER_ECON)

    assert result.whitespace_adjustment_factor == 1.00
    assert result.effective_racks == 1666


# ─────────────────────────────────────────────────────────────
# Test 9: Expansion floors
# ─────────────────────────────────────────────────────────────
def test_expansion_floors():
    """Site with 1 active floor and 2 expansion floors.

    Hand calculation:
        Buildable = 15000 × 0.50 = 7,500 m²
        Active gross = 7500 × 1 = 7,500 m²
        Active whitespace = 7500 × 0.40 = 3,000 m²
        Active racks = 3000 / 3.0 = 1,000

        Expansion gross = 7500 × 2 = 15,000 m²
        Expansion whitespace = 15000 × 0.40 = 6,000 m²
        Expansion racks = 6000 / 3.0 = 2,000
    """
    site = Site(
        name="Expansion Test",
        land_area_m2=15000,
        num_floors=1,
        num_expansion_floors=2,
    )
    result = compute_space(site)

    assert result.active_floors == 1
    assert result.max_racks_by_space == 1000
    assert result.expansion_floors == 2
    assert result.expansion_whitespace_m2 == 6000.0
    assert result.expansion_racks == 2000


def test_expansion_floors_capped_by_height():
    """Expansion floors cannot exceed the remaining height allowance."""
    site = Site(
        name="Height Capped Expansion",
        land_area_m2=15000,
        num_floors=2,
        num_expansion_floors=2,
        max_building_height_m=13.5,  # 3 floors total at 4.5 m
        floor_to_floor_height_m=4.5,
    )
    result = compute_space(site)

    assert result.active_floors == 2
    assert result.expansion_floors == 1
    assert result.expansion_whitespace_m2 == 3000.0
    assert result.expansion_racks == 1000


# ─────────────────────────────────────────────────────────────
# Test 10: Custom site coverage and whitespace ratios
# ─────────────────────────────────────────────────────────────
def test_custom_ratios():
    """Site with non-default coverage (0.60) and whitespace (0.45).

    Hand calculation:
        Buildable = 10000 × 0.60 = 6,000 m²
        Gross     = 6000 × 2 = 12,000 m²
        Whitespace = 12000 × 0.45 = 5,400 m²
        Max racks = 5400 / 3.0 = 1,800
    """
    site = Site(
        name="Custom Ratios",
        land_area_m2=10000,
        site_coverage_ratio=0.60,
        whitespace_ratio=0.45,
        num_floors=2,
    )
    result = compute_space(site)

    assert result.buildable_footprint_m2 == 6000.0
    assert result.it_whitespace_m2 == 5400.0
    assert result.max_racks_by_space == 1800
    assert result.site_coverage_used == 0.60
    assert result.whitespace_ratio_used == 0.45


# ─────────────────────────────────────────────────────────────
# Test 11: IT load from space
# ─────────────────────────────────────────────────────────────
def test_it_load_from_space():
    """Convert racks to IT load in MW.

    Hand calculation:
        1666 racks × 7 kW/rack = 11,662 kW = 11.662 MW
    """
    it_mw = compute_it_load_from_space(effective_racks=1666, rack_density_kw=7.0)
    assert it_mw == 11.662


def test_it_load_ai_racks():
    """AI racks at 100 kW typical.

    Hand calculation:
        500 racks × 100 kW/rack = 50,000 kW = 50.0 MW
    """
    it_mw = compute_it_load_from_space(effective_racks=500, rack_density_kw=100.0)
    assert it_mw == 50.0


# ─────────────────────────────────────────────────────────────
# Test 12: Very small site
# ─────────────────────────────────────────────────────────────
def test_small_site():
    """1,000 m² site — might be too small for a viable DC.

    Hand calculation:
        Buildable = 1000 × 0.50 = 500 m²
        Whitespace = 500 × 0.40 = 200 m²
        Max racks = 200 / 3.0 = 66 racks
    """
    site = Site(name="Small Site", land_area_m2=1000)
    result = compute_space(site)

    assert result.max_racks_by_space == 66


# ─────────────────────────────────────────────────────────────
# Test 13: Expansion floors with cooling adjustment
# ─────────────────────────────────────────────────────────────
def test_expansion_with_cooling_adjustment():
    """Expansion racks should also be adjusted for cooling type.

    Hand calculation (immersion, factor 0.85):
        Active racks = floor(1000 × 0.85) = 850
        Expansion racks = floor(2000 × 0.85) = 1,700
    """
    site = Site(
        name="Expansion + Immersion",
        land_area_m2=15000,
        num_floors=1,
        num_expansion_floors=2,
    )
    result = compute_space(site, cooling_type=CoolingType.IMMERSION)

    assert result.effective_racks == 850
    assert result.expansion_racks == 1700


# ─────────────────────────────────────────────────────────────
# Test 14: Validation — buildable area can't exceed land area
# ─────────────────────────────────────────────────────────────
def test_buildable_exceeds_land_raises():
    """Should raise validation error if buildable > land."""
    with pytest.raises(Exception):
        Site(
            name="Invalid",
            land_area_m2=5000,
            buildable_area_mode=BuildableAreaMode.ABSOLUTE,
            buildable_area_m2=10000,  # More than land area — invalid
        )
