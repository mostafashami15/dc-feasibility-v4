"""
DC Feasibility Tool v4 — Tests for weather.py
===============================================
Tests for pure computation and file parsing. Network-dependent
functions (fetch_open_meteo, geocode, build_representative_year)
are tested manually on the developer's machine.

Test structure:
    1. Multi-year averaging
    2. Leap year handling
    3. KML parsing
    4. WeatherData validation
    5. Edge cases
"""

import math
from datetime import datetime, timedelta, timezone
import pytest

from engine.weather import (
    average_multi_year,
    parse_manual_weather_csv,
    parse_kml_string,
    WeatherData,
    KMLCoordinates,
)

# KML tag helper — prevents tag stripping during file creation
_NT = "na" + "me"  # builds "name" at runtime


# ═════════════════════════════════════════════════════════════
# 1. MULTI-YEAR AVERAGING
# ═════════════════════════════════════════════════════════════

class TestMultiYearAveraging:
    """Test average_multi_year with synthetic data."""

    def test_two_years_simple(self):
        """Average of two identical years = same values."""
        yearly = {2020: [10.0] * 8760, 2021: [10.0] * 8760}
        result = average_multi_year(yearly)
        assert len(result) == 8760
        assert all(v == 10.0 for v in result)

    def test_two_years_different(self):
        """Average of 10 and 20 = 15 for every hour."""
        yearly = {2020: [10.0] * 8760, 2021: [20.0] * 8760}
        result = average_multi_year(yearly)
        assert len(result) == 8760
        assert all(v == 15.0 for v in result)

    def test_three_years(self):
        """Average of 10, 20, 30 = 20.0 for every hour."""
        yearly = {2019: [10.0]*8760, 2020: [20.0]*8760, 2021: [30.0]*8760}
        result = average_multi_year(yearly)
        assert all(v == 20.0 for v in result)

    def test_per_hour_averaging(self):
        """Hour 0 averaged across years, hour 1 separately, etc."""
        year_a = [float(i) for i in range(8760)]
        year_b = [float(i + 10) for i in range(8760)]
        yearly = {2020: year_a, 2021: year_b}
        result = average_multi_year(yearly)
        assert result[0] == 5.0
        assert result[100] == 105.0
        assert result[8759] == 8764.0

    def test_single_year(self):
        """Single year → result is that year."""
        data = [float(i % 24) for i in range(8760)]
        yearly = {2023: data}
        result = average_multi_year(yearly)
        assert result == data

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            average_multi_year({})

    def test_wrong_length_raises(self):
        yearly = {2020: [10.0]*8760, 2021: [10.0]*5000}
        with pytest.raises(ValueError, match="8760"):
            average_multi_year(yearly)

    def test_output_length(self):
        yearly = {y: [15.0]*8760 for y in range(2019, 2024)}
        result = average_multi_year(yearly)
        assert len(result) == 8760


# ═════════════════════════════════════════════════════════════
# 2. LEAP YEAR HANDLING
# ═════════════════════════════════════════════════════════════

class TestLeapYear:
    def test_leap_year_truncated(self):
        """8784-hour leap year → Feb 29 removed → 8760 result."""
        yearly = {2023: [20.0]*8760, 2024: [20.0]*8784}
        result = average_multi_year(yearly)
        assert len(result) == 8760

    def test_leap_year_feb29_removed(self):
        """Feb 29 hours (1416-1439) removed, not other hours."""
        leap_data = [float(i) for i in range(8784)]
        yearly = {2024: leap_data}
        result = average_multi_year(yearly)
        assert len(result) == 8760
        assert result[0] == 0.0
        assert result[1415] == 1415.0
        assert result[1416] == 1440.0  # First hour of Mar 1

    def test_all_leap_years(self):
        yearly = {2020: [10.0]*8784, 2024: [20.0]*8784}
        result = average_multi_year(yearly)
        assert len(result) == 8760
        assert all(v == 15.0 for v in result)


# ═════════════════════════════════════════════════════════════
# 3. KML PARSING
# ═════════════════════════════════════════════════════════════

def _make_kml_with_ns():
    """Build KML string with namespace, preserving XML tag integrity."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2">'
        '<Document>'
        '<' + _NT + '>Test Sites</' + _NT + '>'
        '<Placemark>'
        '<' + _NT + '>Milan Data Center</' + _NT + '>'
        '<description>Candidate site in Milan</description>'
        '<Point><coordinates>9.1900,45.4642,0</coordinates></Point>'
        '</Placemark>'
        '<Placemark>'
        '<' + _NT + '>Rome Site</' + _NT + '>'
        '<Point><coordinates>12.4964,41.9028,0</coordinates></Point>'
        '</Placemark>'
        '</Document>'
        '</kml>'
    )

def _make_kml_no_ns():
    """KML without namespace."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml><Document>'
        '<Placemark>'
        '<' + _NT + '>Simple Site</' + _NT + '>'
        '<Point><coordinates>2.3522,48.8566</coordinates></Point>'
        '</Placemark>'
        '</Document></kml>'
    )


def _build_manual_weather_csv(
    *,
    hours: int = 8760,
    include_humidity: bool = False,
    include_timestamp: bool = False,
    blank_humidity_index: int | None = None,
    start_year: int = 2025,
) -> str:
    header = []
    if include_timestamp:
        header.append("timestamp_utc")
    header.append("dry_bulb_c")
    if include_humidity:
        header.append("relative_humidity_pct")

    start = datetime(start_year, 1, 1, tzinfo=timezone.utc)
    rows = [",".join(header)]
    for hour in range(hours):
        cells: list[str] = []
        if include_timestamp:
            stamp = start + timedelta(hours=hour)
            cells.append(stamp.isoformat().replace("+00:00", "Z"))
        cells.append(f"{10 + (hour % 24) * 0.5:.2f}")
        if include_humidity:
            if blank_humidity_index is not None and hour == blank_humidity_index:
                cells.append("")
            else:
                cells.append(f"{55 + (hour % 10):.1f}")
        rows.append(",".join(cells))
    return "\n".join(rows)


class TestKMLParsing:
    """Test KML string parsing for coordinate extraction."""

    def test_parse_two_placemarks(self):
        results = parse_kml_string(_make_kml_with_ns())
        assert len(results) == 2

    def test_first_placemark_coords(self):
        """Milan: lon=9.19, lat=45.4642."""
        results = parse_kml_string(_make_kml_with_ns())
        assert results[0].latitude == pytest.approx(45.4642, abs=1e-4)
        assert results[0].longitude == pytest.approx(9.1900, abs=1e-4)

    def test_second_placemark_coords(self):
        """Rome: lon=12.4964, lat=41.9028."""
        results = parse_kml_string(_make_kml_with_ns())
        assert results[1].latitude == pytest.approx(41.9028, abs=1e-4)
        assert results[1].longitude == pytest.approx(12.4964, abs=1e-4)

    def test_placemark_names(self):
        results = parse_kml_string(_make_kml_with_ns())
        assert results[0].name == "Milan Data Center"
        assert results[1].name == "Rome Site"

    def test_placemark_description(self):
        results = parse_kml_string(_make_kml_with_ns())
        assert results[0].description == "Candidate site in Milan"
        assert results[1].description is None

    def test_kml_without_namespace(self):
        results = parse_kml_string(_make_kml_no_ns())
        assert len(results) == 1
        assert results[0].latitude == pytest.approx(48.8566, abs=1e-4)
        assert results[0].longitude == pytest.approx(2.3522, abs=1e-4)

    def test_kml_coordinate_order(self):
        """KML format is longitude,latitude (NOT lat,lon)."""
        kml = (
            '<?xml version="1.0"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2">'
            '<Placemark><Point><coordinates>12.0,45.0,0</coordinates></Point></Placemark>'
            '</kml>'
        )
        results = parse_kml_string(kml)
        assert results[0].longitude == 12.0
        assert results[0].latitude == 45.0

    def test_empty_kml(self):
        kml = (
            '<?xml version="1.0"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2">'
            '<Document><' + _NT + '>Empty</' + _NT + '></Document>'
            '</kml>'
        )
        results = parse_kml_string(kml)
        assert results == []

    def test_invalid_xml_raises(self):
        with pytest.raises(ValueError, match="Invalid KML"):
            parse_kml_string("not xml at all <<<>>>")

    def test_coordinates_without_altitude(self):
        kml = (
            '<?xml version="1.0"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2">'
            '<Placemark><Point><coordinates>9.19,45.46</coordinates></Point></Placemark>'
            '</kml>'
        )
        results = parse_kml_string(kml)
        assert len(results) == 1
        assert results[0].latitude == pytest.approx(45.46, abs=0.01)

    def test_linestring_returns_representative_point(self):
        kml = (
            '<?xml version="1.0"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2">'
            '<Placemark>'
            '<LineString><coordinates>9.0,45.0 11.0,47.0</coordinates></LineString>'
            '</Placemark>'
            '</kml>'
        )
        results = parse_kml_string(kml)
        assert len(results) == 1
        assert results[0].longitude == pytest.approx(10.0, abs=1e-4)
        assert results[0].latitude == pytest.approx(46.0, abs=1e-4)

    def test_polygon_returns_representative_point(self):
        kml = (
            '<?xml version="1.0"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2">'
            '<Placemark>'
            '<Polygon><outerBoundaryIs><LinearRing>'
            '<coordinates>'
            '10.0,45.0 12.0,45.0 12.0,47.0 10.0,47.0 10.0,45.0'
            '</coordinates>'
            '</LinearRing></outerBoundaryIs></Polygon>'
            '</Placemark>'
            '</kml>'
        )
        results = parse_kml_string(kml)
        assert len(results) == 1
        assert results[0].longitude == pytest.approx(11.0, abs=1e-4)
        assert results[0].latitude == pytest.approx(46.0, abs=1e-4)


# ═════════════════════════════════════════════════════════════
# 4. WEATHER DATA VALIDATION
# ═════════════════════════════════════════════════════════════

class TestWeatherData:
    def test_basic_creation(self):
        wd = WeatherData([20.0]*8760, [60.0]*8760, 45.0, 9.0, "test")
        assert wd.hours == 8760
        assert wd.latitude == 45.0

    def test_hours_auto_computed(self):
        wd = WeatherData([20.0]*100, None, 45.0, 9.0, "test")
        assert wd.hours == 100

    def test_none_humidity_allowed(self):
        wd = WeatherData([20.0]*8760, None, 45.0, 9.0, "test")
        assert wd.humidities is None

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="same length"):
            WeatherData([20.0]*100, [60.0]*50, 45.0, 9.0, "test")

    def test_years_averaged(self):
        wd = WeatherData([20.0]*8760, None, 45.0, 9.0, "test",
                         years_averaged=[2019, 2020, 2021, 2022, 2023])
        assert wd.years_averaged == [2019, 2020, 2021, 2022, 2023]


class TestManualWeatherCsv:
    def test_parse_manual_weather_csv_without_humidity(self):
        csv_text = _build_manual_weather_csv(hours=8760)

        result = parse_manual_weather_csv(
            csv_text,
            latitude=None,
            longitude=None,
            source_name="site-weather.csv",
        )

        assert result.hours == 8760
        assert result.humidities is None
        assert result.source_type == "manual_upload"
        assert result.original_filename == "site-weather.csv"

    def test_parse_manual_weather_csv_with_humidity_and_timestamps(self):
        csv_text = _build_manual_weather_csv(
            hours=8760,
            include_humidity=True,
            include_timestamp=True,
        )

        result = parse_manual_weather_csv(
            csv_text,
            latitude=45.0,
            longitude=9.0,
            source_name="weather.csv",
            uploaded_at_utc="2026-03-12T12:00:00+00:00",
        )

        assert result.hours == 8760
        assert result.humidities is not None
        assert len(result.humidities) == 8760
        assert result.latitude == 45.0
        assert result.uploaded_at_utc == "2026-03-12T12:00:00+00:00"

    def test_parse_manual_weather_csv_requires_dry_bulb_column(self):
        with pytest.raises(ValueError, match="dry_bulb_c"):
            parse_manual_weather_csv("timestamp_utc,relative_humidity_pct\n2025-01-01T00:00:00Z,55")

    def test_parse_manual_weather_csv_rejects_partial_humidity_column(self):
        csv_text = _build_manual_weather_csv(
            hours=8760,
            include_humidity=True,
            blank_humidity_index=10,
        )

        with pytest.raises(ValueError, match="filled for every row or omitted entirely"):
            parse_manual_weather_csv(csv_text)

    def test_parse_manual_weather_csv_rejects_wrong_row_count(self):
        csv_text = _build_manual_weather_csv(hours=8759)

        with pytest.raises(ValueError, match="exactly 8760 hourly rows"):
            parse_manual_weather_csv(csv_text)

    def test_parse_manual_weather_csv_normalizes_leap_year(self):
        csv_text = _build_manual_weather_csv(
            hours=8784,
            include_humidity=True,
            include_timestamp=True,
            start_year=2024,
        )

        result = parse_manual_weather_csv(csv_text)

        assert result.hours == 8760
        assert result.humidities is not None
        assert len(result.humidities) == 8760


# ═════════════════════════════════════════════════════════════
# 5. EDGE CASES
# ═════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_averaging_preserves_diurnal_pattern(self):
        pattern = [float(h % 24) for h in range(8760)]
        yearly = {2020: pattern, 2021: pattern}
        result = average_multi_year(yearly)
        for h in range(8760):
            assert result[h] == float(h % 24)

    def test_averaging_rounding(self):
        """10/3 = 3.333... → rounded to 3.33."""
        yearly = {2019: [0.0]*8760, 2020: [0.0]*8760, 2021: [10.0]*8760}
        result = average_multi_year(yearly)
        assert result[0] == 3.33

    def test_five_year_averaging(self):
        yearly = {y: [float(y-2019)]*8760 for y in range(2019, 2024)}
        result = average_multi_year(yearly)
        assert all(v == 2.0 for v in result)

    def test_kml_whitespace_in_coordinates(self):
        kml = (
            '<?xml version="1.0"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2">'
            '<Placemark><Point><coordinates>  9.19 , 45.46 , 0  </coordinates></Point></Placemark>'
            '</kml>'
        )
        results = parse_kml_string(kml)
        assert len(results) == 1
        assert results[0].latitude == pytest.approx(45.46, abs=0.01)
