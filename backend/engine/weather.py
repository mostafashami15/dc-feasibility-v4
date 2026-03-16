"""
DC Feasibility Tool v4 — Weather Data Module
==============================================
Fetches, parses, and prepares hourly weather data for the PUE engine.

Functions:
    1. fetch_open_meteo() — Download hourly weather from Open-Meteo API
    2. parse_kml() — Extract coordinates from KML/KMZ files
    3. geocode() — Convert city/address to coordinates via Open-Meteo
    4. average_multi_year() — Average 5 years to one representative year
    5. build_representative_year() — Full pipeline: fetch → average → return

The representative year is 8,760 hours of T_db (and optionally RH),
computed by averaging the same hour across multiple years. This smooths
out year-to-year variability while preserving diurnal and seasonal patterns.

Source: Architecture Agreement Section 3.10:
    "Fetch 5 years (2019–2023), average hour-by-hour to produce one
    representative 8,760-row year."

Dependencies:
    Standard library only (for parsing/computation).
    requests (for API calls) — imported inside functions so the module
    loads without network dependencies.

Reference: Architecture Agreement v2.0, Section 3.10
"""

import csv
import json
import math
import zipfile
import io
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────

@dataclass
class WeatherData:
    """Hourly weather data for one year.

    Attributes:
        temperatures: Dry-bulb temperature in °C, one per hour.
        humidities: Relative humidity in % (0–100), one per hour.
            None if RH data is unavailable.
        latitude: Site latitude, if known.
        longitude: Site longitude, if known.
        source: Data source description.
        source_type: Stable source key for cache metadata and UI display.
        years_averaged: List of years used (e.g., [2019,2020,2021,2022,2023]).
        original_filename: Original uploaded CSV filename for manual uploads.
        uploaded_at_utc: Upload timestamp for manual uploads.
        hours: Number of hours (should be 8760 for a full year).
    """
    temperatures: list[float]
    humidities: Optional[list[float]]
    latitude: Optional[float]
    longitude: Optional[float]
    source: str
    source_type: str = "open_meteo_archive"
    years_averaged: list[int] = field(default_factory=list)
    original_filename: Optional[str] = None
    uploaded_at_utc: Optional[str] = None
    hours: int = 0

    def __post_init__(self):
        self.hours = len(self.temperatures)
        if self.humidities is not None and len(self.humidities) != self.hours:
            raise ValueError(
                f"temperatures ({self.hours}) and humidities "
                f"({len(self.humidities)}) must have the same length"
            )


@dataclass
class KMLCoordinates:
    """Coordinates extracted from a KML/KMZ file.

    Attributes:
        latitude: Decimal degrees.
        longitude: Decimal degrees.
        name: Placemark name (if available).
        description: Placemark description (if available).
    """
    latitude: float
    longitude: float
    name: Optional[str] = None
    description: Optional[str] = None
    geometry_type: str = "point"
    coordinates: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class GeocodingResult:
    """Result of a geocoding lookup.

    Attributes:
        latitude: Decimal degrees.
        longitude: Decimal degrees.
        name: Resolved place name.
        country: Country name.
        admin1: Administrative region (state/province).
    """
    latitude: float
    longitude: float
    name: str
    country: Optional[str] = None
    admin1: Optional[str] = None


MANUAL_WEATHER_STANDARD_HOURS = 8760
MANUAL_WEATHER_LEAP_HOURS = 8784
_MANUAL_WEATHER_REQUIRED_COLUMN = "dry_bulb_c"
_MANUAL_WEATHER_OPTIONAL_HUMIDITY_COLUMN = "relative_humidity_pct"
_MANUAL_WEATHER_OPTIONAL_TIMESTAMP_COLUMN = "timestamp_utc"


def _normalize_weather_csv_headers(fieldnames: Sequence[str | None]) -> dict[str, str]:
    """Map lowercase header names to their original CSV column names."""
    normalized: dict[str, str] = {}
    for fieldname in fieldnames:
        if fieldname is None:
            continue
        key = fieldname.strip().lower()
        if key:
            normalized[key] = fieldname
    return normalized


def _parse_weather_float(value: str, *, row_number: int, column_name: str) -> float:
    """Parse one numeric weather cell with a row-aware error message."""
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(
            f"Row {row_number}: '{column_name}' must be numeric, got '{value}'."
        ) from exc


def _parse_timestamp_utc(value: str, *, row_number: int) -> datetime:
    """Parse an ISO-like timestamp and normalize it to UTC."""
    candidate = value.strip()
    if not candidate:
        raise ValueError(f"Row {row_number}: 'timestamp_utc' cannot be blank.")

    normalized = candidate.replace("Z", "+00:00")
    if " " in normalized and "T" not in normalized:
        normalized = normalized.replace(" ", "T", 1)

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            "The 'timestamp_utc' column must use an ISO-like hourly timestamp such as "
            "'2025-01-01T00:00:00Z'."
        ) from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _drop_feb_29(values: list[float]) -> list[float]:
    """Normalize a leap-year hourly series to 8,760 hours by removing Feb 29."""
    return values[:1416] + values[1440:]


def parse_manual_weather_csv(
    csv_text: str,
    *,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    source_name: Optional[str] = None,
    uploaded_at_utc: Optional[str] = None,
) -> WeatherData:
    """Parse a manual hourly weather CSV into the standard cache shape.

    Supported schema:
        - dry_bulb_c (required)
        - relative_humidity_pct (optional)
        - timestamp_utc (optional but recommended)

    The file must represent a complete hourly year in chronological order:
        - 8,760 rows for a standard year
        - 8,784 rows for a leap year, which is normalized by removing Feb 29
    """
    if not csv_text.strip():
        raise ValueError("The uploaded weather CSV is empty.")

    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise ValueError(
            "CSV header row not found. Expected at least a 'dry_bulb_c' column."
        )

    header_map = _normalize_weather_csv_headers(reader.fieldnames)
    dry_bulb_header = header_map.get(_MANUAL_WEATHER_REQUIRED_COLUMN)
    humidity_header = header_map.get(_MANUAL_WEATHER_OPTIONAL_HUMIDITY_COLUMN)
    timestamp_header = header_map.get(_MANUAL_WEATHER_OPTIONAL_TIMESTAMP_COLUMN)

    if dry_bulb_header is None:
        raise ValueError(
            "CSV must include a 'dry_bulb_c' column with hourly dry-bulb temperature in degC."
        )

    temperatures: list[float] = []
    humidity_values: list[Optional[float]] = []
    timestamps: list[datetime] = []

    for row_number, row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue

        temp_raw = (row.get(dry_bulb_header) or "").strip()
        if not temp_raw:
            raise ValueError(f"Row {row_number}: '{_MANUAL_WEATHER_REQUIRED_COLUMN}' is required.")
        temperatures.append(
            _parse_weather_float(
                temp_raw,
                row_number=row_number,
                column_name=_MANUAL_WEATHER_REQUIRED_COLUMN,
            )
        )

        if humidity_header is not None:
            humidity_raw = (row.get(humidity_header) or "").strip()
            if not humidity_raw:
                humidity_values.append(None)
            else:
                humidity = _parse_weather_float(
                    humidity_raw,
                    row_number=row_number,
                    column_name=_MANUAL_WEATHER_OPTIONAL_HUMIDITY_COLUMN,
                )
                if humidity < 0 or humidity > 100:
                    raise ValueError(
                        f"Row {row_number}: 'relative_humidity_pct' must be between 0 and 100."
                    )
                humidity_values.append(humidity)

        if timestamp_header is not None:
            timestamps.append(
                _parse_timestamp_utc(
                    row.get(timestamp_header) or "",
                    row_number=row_number,
                )
            )

    if not temperatures:
        raise ValueError("CSV contains no hourly weather rows.")

    raw_hours = len(temperatures)
    if raw_hours not in (MANUAL_WEATHER_STANDARD_HOURS, MANUAL_WEATHER_LEAP_HOURS):
        raise ValueError(
            "CSV must contain exactly 8760 hourly rows for a standard year or 8784 rows "
            f"for a leap year. Received {raw_hours} rows."
        )

    if timestamps:
        if len(timestamps) != raw_hours:
            raise ValueError("Each non-empty weather row must include 'timestamp_utc'.")

        if timestamps[0].month != 1 or timestamps[0].day != 1 or timestamps[0].hour != 0:
            raise ValueError(
                "When provided, 'timestamp_utc' must start at January 1 00:00 for the uploaded year."
            )

        if timestamps[-1].month != 12 or timestamps[-1].day != 31 or timestamps[-1].hour != 23:
            raise ValueError(
                "When provided, 'timestamp_utc' must end at December 31 23:00 for the uploaded year."
            )

        for previous, current in zip(timestamps, timestamps[1:]):
            if current - previous != timedelta(hours=1):
                raise ValueError(
                    "The 'timestamp_utc' column must advance in 1-hour increments without gaps or duplicates."
                )

    humidities: Optional[list[float]] = None
    if humidity_header is not None:
        missing_humidity = sum(value is None for value in humidity_values)
        if 0 < missing_humidity < raw_hours:
            raise ValueError(
                "The optional 'relative_humidity_pct' column must be filled for every row or omitted entirely."
            )
        if missing_humidity == 0:
            humidities = [value for value in humidity_values if value is not None]

    if raw_hours == MANUAL_WEATHER_LEAP_HOURS:
        temperatures = _drop_feb_29(temperatures)
        if humidities is not None:
            humidities = _drop_feb_29(humidities)

    filename = (source_name or "").strip() or None
    uploaded_at = uploaded_at_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    source = "Manual CSV upload" if filename is None else f"Manual CSV upload ({filename})"

    return WeatherData(
        temperatures=temperatures,
        humidities=humidities,
        latitude=latitude,
        longitude=longitude,
        source=source,
        source_type="manual_upload",
        years_averaged=[],
        original_filename=filename,
        uploaded_at_utc=uploaded_at,
    )


# ═════════════════════════════════════════════════════════════
# MULTI-YEAR AVERAGING (pure computation — no network)
# ═════════════════════════════════════════════════════════════

def average_multi_year(
    yearly_data: dict[int, list[float]],
) -> list[float]:
    """Average multiple years of hourly data into one representative year.

    For each hour h (0–8759), computes the mean across all years:
        representative[h] = mean(year_data[h] for year in years)

    This produces a "typical meteorological year" that smooths out
    year-to-year noise while preserving the diurnal cycle and
    seasonal pattern.

    Handles leap years by truncating February 29 data (hours 1416–1439)
    so all years have exactly 8,760 hours.

    Source: Architecture Agreement Section 3.10.

    Args:
        yearly_data: Dict mapping year → list of hourly values.
            Each list should be 8,760 or 8,784 hours (leap year).

    Returns:
        List of 8,760 averaged hourly values.

    Raises:
        ValueError: If any year has fewer than 8,760 hours.
    """
    if not yearly_data:
        raise ValueError("yearly_data must not be empty")

    years = sorted(yearly_data.keys())

    # Normalize all years to 8760 hours
    normalized = {}
    for year, data in yearly_data.items():
        if len(data) == 8784:
            # Leap year: remove Feb 29 (hours 1416–1439 = 24 hours)
            # Jan: 744 hours (0–743)
            # Feb 1–28: 672 hours (744–1415)
            # Feb 29: 24 hours (1416–1439) ← REMOVE
            # Mar onwards: (1440–8783)
            normalized[year] = data[:1416] + data[1440:]
        elif len(data) == 8760:
            normalized[year] = data
        else:
            raise ValueError(
                f"Year {year} has {len(data)} hours. "
                f"Expected 8760 (standard) or 8784 (leap year)."
            )

    # Average hour-by-hour
    n_years = len(years)
    representative = []
    for h in range(8760):
        total = sum(normalized[y][h] for y in years)
        representative.append(round(total / n_years, 2))

    return representative


# ═════════════════════════════════════════════════════════════
# KML / KMZ PARSING (pure computation — file I/O only)
# ═════════════════════════════════════════════════════════════

# KML namespaces
KML_NS = {
    "kml": "http://www.opengis.net/kml/2.2",
    "gx": "http://www.google.com/kml/ext/2.2",
}


def _find_first(elem: ET.Element, paths: list[str]) -> Optional[ET.Element]:
    """Return the first matching subelement for any of the given paths."""
    for path in paths:
        found = elem.find(path, KML_NS)
        if found is not None:
            return found
    return None


def _parse_coordinate_text(coord_text: str) -> list[tuple[float, float]]:
    """Parse KML coordinate text into [(lon, lat), ...].

    KML stores coordinates as:
        lon,lat[,alt] lon,lat[,alt] ...
    """
    pattern = re.compile(
        r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)(?:\s*,\s*-?\d+(?:\.\d+)?)?"
    )

    coordinates: list[tuple[float, float]] = []
    for lon_text, lat_text in pattern.findall(coord_text):
        coordinates.append((float(lon_text), float(lat_text)))

    return coordinates


def _representative_point(coords: list[tuple[float, float]]) -> Optional[tuple[float, float]]:
    """Compute a representative lon/lat point for a geometry.

    For site-level KML uploads this is sufficient: the Site Manager needs
    a stable location pin for the uploaded site geometry, not a full shape.
    We use the mean of all vertices, ignoring a duplicated closing point.
    """
    if not coords:
        return None

    normalized = coords[:]
    if len(normalized) > 1 and normalized[0] == normalized[-1]:
        normalized = normalized[:-1]

    lon = sum(c[0] for c in normalized) / len(normalized)
    lat = sum(c[1] for c in normalized) / len(normalized)
    return (lon, lat)


def parse_kml_string(kml_content: str) -> list[KMLCoordinates]:
    """Parse KML XML string and extract placemark coordinates.

    Looks for <Placemark> elements with supported geometries:
        - Point
        - LineString
        - Polygon (outer boundary ring)

    For lines and polygons, returns a representative point computed from
    the geometry vertices so the frontend can place the site on the map.
    KML coordinates format: longitude,latitude[,altitude]

    Args:
        kml_content: KML XML as string.

    Returns:
        List of KMLCoordinates (may be empty if no placemarks found).
    """
    results = []

    try:
        root = ET.fromstring(kml_content)
    except ET.ParseError as e:
        raise ValueError(f"Invalid KML XML: {e}")

    # Find all Placemark elements (with or without namespace)
    placemarks = root.findall(".//kml:Placemark", KML_NS)
    if not placemarks:
        # Try without namespace (some KML files omit it)
        placemarks = root.findall(".//{http://www.opengis.net/kml/2.2}Placemark")
    if not placemarks:
        placemarks = root.findall(".//Placemark")

    for pm in placemarks:
        # Get name
        # IMPORTANT: Do NOT use `elem or fallback` with ElementTree!
        # An Element with no children evaluates to False in Python,
        # even if it has text content. Always use `is not None`.
        name_elem = _find_first(pm, [
            "kml:name",
            "{http://www.opengis.net/kml/2.2}name",
            "name",
        ])
        name = name_elem.text.strip() if name_elem is not None and name_elem.text else None

        # Get description
        desc_elem = _find_first(pm, [
            "kml:description",
            "{http://www.opengis.net/kml/2.2}description",
            "description",
        ])
        description = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else None

        geometry_candidates = [
            ("point", [
                ".//kml:Point/kml:coordinates",
                ".//{http://www.opengis.net/kml/2.2}Point/{http://www.opengis.net/kml/2.2}coordinates",
                ".//Point/coordinates",
            ]),
            ("line", [
                ".//kml:LineString/kml:coordinates",
                ".//{http://www.opengis.net/kml/2.2}LineString/{http://www.opengis.net/kml/2.2}coordinates",
                ".//LineString/coordinates",
            ]),
            ("polygon", [
                ".//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates",
                ".//{http://www.opengis.net/kml/2.2}Polygon/{http://www.opengis.net/kml/2.2}outerBoundaryIs/{http://www.opengis.net/kml/2.2}LinearRing/{http://www.opengis.net/kml/2.2}coordinates",
                ".//Polygon/outerBoundaryIs/LinearRing/coordinates",
            ]),
        ]

        geometry_type = None
        coord_elem = None
        for candidate_type, candidate_paths in geometry_candidates:
            found = _find_first(pm, candidate_paths)
            if found is not None and found.text:
                geometry_type = candidate_type
                coord_elem = found
                break

        if coord_elem is None or not coord_elem.text or geometry_type is None:
            continue

        coords = _parse_coordinate_text(coord_elem.text.strip())
        representative = _representative_point(coords)
        if representative is None:
            continue

        lon, lat = representative
        results.append(KMLCoordinates(
            latitude=lat,
            longitude=lon,
            name=name,
            description=description,
            geometry_type=geometry_type,
            coordinates=coords,
        ))

    return results


def parse_kml_file(file_path: str) -> list[KMLCoordinates]:
    """Parse a KML or KMZ file and extract coordinates.

    KMZ files are ZIP archives containing a doc.kml file.

    Args:
        file_path: Path to .kml or .kmz file.

    Returns:
        List of KMLCoordinates.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If file format is invalid.
    """
    if file_path.lower().endswith(".kmz"):
        # KMZ is a ZIP containing doc.kml
        with zipfile.ZipFile(file_path, "r") as zf:
            # Look for doc.kml or any .kml file
            kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError(f"No .kml file found in KMZ archive: {file_path}")
            kml_content = zf.read(kml_names[0]).decode("utf-8")
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            kml_content = f.read()

    return parse_kml_string(kml_content)


# ═════════════════════════════════════════════════════════════
# OPEN-METEO API (network-dependent)
# ═════════════════════════════════════════════════════════════

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def fetch_open_meteo(
    latitude: float,
    longitude: float,
    start_year: int = 2019,
    end_year: int = 2023,
) -> dict[int, dict[str, list[float]]]:
    """Fetch hourly weather data from Open-Meteo Archive API.

    Downloads temperature_2m and relative_humidity_2m for each year
    in the range [start_year, end_year].

    Source: Open-Meteo Archive API (free, no API key needed).
    Reference: Architecture Agreement Section 3.10.

    Args:
        latitude: Site latitude in decimal degrees.
        longitude: Site longitude in decimal degrees.
        start_year: First year to fetch (default 2019).
        end_year: Last year to fetch (default 2023).

    Returns:
        Dict mapping year → {"temperature": [...], "humidity": [...]}.
        Each list has 8,760 or 8,784 (leap year) hourly values.

    Raises:
        ImportError: If requests library is not installed.
        ConnectionError: If Open-Meteo API is unreachable.
    """
    try:
        import requests
    except ImportError:
        raise ImportError(
            "The 'requests' library is required for API fetching. "
            "Install with: pip install requests"
        )

    result = {}

    for year in range(start_year, end_year + 1):
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": "temperature_2m,relative_humidity_2m",
            "timezone": "UTC",
        }

        response = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        hourly = data.get("hourly", {})
        temps = hourly.get("temperature_2m", [])
        rh = hourly.get("relative_humidity_2m", [])

        if not temps:
            raise ValueError(
                f"No temperature data returned for year {year} "
                f"at ({latitude}, {longitude})"
            )

        result[year] = {
            "temperature": temps,
            "humidity": rh if rh else None,
        }

    return result


def geocode(query: str) -> list[GeocodingResult]:
    """Geocode a place name using Open-Meteo Geocoding API.

    Converts a city name, address, or place name to coordinates.

    Args:
        query: Search string (e.g., "Milan, Italy").

    Returns:
        List of GeocodingResult (up to 5 results, ranked by relevance).

    Raises:
        ImportError: If requests library not installed.
    """
    try:
        import requests
    except ImportError:
        raise ImportError(
            "The 'requests' library is required for geocoding. "
            "Install with: pip install requests"
        )

    params = {
        "name": query,
        "count": 5,
        "language": "en",
        "format": "json",
    }

    response = requests.get(OPEN_METEO_GEOCODING_URL, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()

    results = []
    for item in data.get("results", []):
        results.append(GeocodingResult(
            latitude=item.get("latitude", 0.0),
            longitude=item.get("longitude", 0.0),
            name=item.get("name", ""),
            country=item.get("country"),
            admin1=item.get("admin1"),
        ))

    return results


# ═════════════════════════════════════════════════════════════
# FULL PIPELINE
# ═════════════════════════════════════════════════════════════

def build_representative_year(
    latitude: float,
    longitude: float,
    start_year: int = 2019,
    end_year: int = 2023,
) -> WeatherData:
    """Full pipeline: fetch multi-year data → average → WeatherData.

    This is the main function called by the API layer when the user
    triggers weather data fetch for a site.

    Args:
        latitude: Site latitude.
        longitude: Site longitude.
        start_year: First year (default 2019).
        end_year: Last year (default 2023).

    Returns:
        WeatherData with 8,760 hours of representative temperatures
        and humidities.
    """
    # Step 1: Fetch all years from Open-Meteo
    raw_data = fetch_open_meteo(latitude, longitude, start_year, end_year)

    years = sorted(raw_data.keys())

    # Step 2: Average temperatures
    temp_yearly = {y: raw_data[y]["temperature"] for y in years}
    avg_temps = average_multi_year(temp_yearly)

    # Step 3: Average humidities (if available for all years)
    avg_rh = None
    if all(raw_data[y]["humidity"] is not None for y in years):
        rh_yearly = {y: raw_data[y]["humidity"] for y in years}
        avg_rh = average_multi_year(rh_yearly)

    return WeatherData(
        temperatures=avg_temps,
        humidities=avg_rh,
        latitude=latitude,
        longitude=longitude,
        source=f"Open-Meteo Archive ({start_year}–{end_year}), hour-by-hour average",
        years_averaged=years,
    )
