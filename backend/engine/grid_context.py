"""
DC Feasibility Tool v4 - Grid Context screening engine
======================================================
Nearby external power-network screening for a saved site.

This module is intentionally separate from power.py, footprint.py,
and pue_engine.py. It evaluates external mapped-public context
around a site rather than internal facility performance.

The provider boundary remains swappable, but the default provider now
queries a real mapped-public asset feed so site-to-site results are
based on public geography rather than deterministic fixtures.
"""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

logger = logging.getLogger(__name__)

from engine.models import (
    GridAnalysisGrade,
    GridAsset,
    GridAssetType,
    GridConfidence,
    GridContextResult,
    GridContextScore,
    GridContextSummary,
    GridEvidenceNote,
    GridGeometryType,
    GridOfficialEvidence,
    Site,
)


EARTH_RADIUS_KM = 6371.0088
GRID_CONTEXT_SOURCE_LAYER = "mapped_public_osm_overpass"
GRID_CONTEXT_FIXTURE_SOURCE_LAYER = "mapped_public_fixture"
GRID_CONTEXT_USER_CONFIRMED_SOURCE_LAYER = "user_confirmed_manual"
GRID_CONTEXT_SOURCE_VERSION = "v3"
HIGH_VOLTAGE_THRESHOLD_KV = 132.0
GRID_SCORE_MAX_VOLTAGE_POINTS = 30.0
GRID_SCORE_MAX_DISTANCE_POINTS = 35.0
GRID_SCORE_MAX_SUBSTATION_POINTS = 20.0
GRID_SCORE_MAX_EVIDENCE_POINTS = 15.0
OVERPASS_INTERPRETER_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY_TIMEOUT_SECONDS = 25
OVERPASS_REQUEST_TIMEOUT_SECONDS = 45
OVERPASS_MAX_RETRIES = 3
OVERPASS_BACKOFF_BASE_SECONDS = 1.0
OVERPASS_BACKOFF_FACTOR = 2.0
_OVERPASS_LINE_TAG_PATTERN = "^(line|minor_line|cable)$"
_OVERPASS_SUBSTATION_TAG_PATTERN = "^(substation|sub_station)$"
_VOLTAGE_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
_POSITIVE_INTEGER_PATTERN = re.compile(r"\d+")


@dataclass(frozen=True)
class ProviderAsset:
    """Provider-native nearby asset record before API normalization."""

    asset_id: str
    asset_type: GridAssetType
    name: str | None
    operator: str | None
    voltage_kv: float | None
    circuits: int | None
    geometry_type: GridGeometryType
    coordinates: list[tuple[float, float]]
    source: str = GRID_CONTEXT_SOURCE_LAYER
    confidence: GridConfidence = GridConfidence.MAPPED_PUBLIC


class GridContextProvider(Protocol):
    """Provider boundary so a real public-data ingestion path can swap in later."""

    def get_assets(
        self,
        *,
        site_id: str,
        site_name: str,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> list[ProviderAsset]:
        """Return provider-native assets around the site."""
        ...


class GridContextProviderError(RuntimeError):
    """Raised when a provider cannot return a reliable mapped-public result."""


def make_grid_context_cache_key(
    radius_km: float,
    source_version: str = GRID_CONTEXT_SOURCE_VERSION,
) -> str:
    """Build a stable per-radius cache key such as '5km_v1'."""
    radius_value = float(radius_km)
    if radius_value.is_integer():
        radius_token = str(int(radius_value))
    else:
        radius_token = str(round(radius_value, 3)).replace(".", "p")
    return f"{radius_token}km_{source_version}"


def _offset_point_km(
    latitude: float,
    longitude: float,
    *,
    north_km: float,
    east_km: float,
) -> tuple[float, float]:
    """Convert local kilometer offsets into latitude/longitude."""
    delta_lat = north_km / 110.574
    cos_lat = max(math.cos(math.radians(latitude)), 0.01)
    delta_lon = east_km / (111.320 * cos_lat)
    return latitude + delta_lat, longitude + delta_lon


class FixtureGridContextProvider:
    """Deterministic placeholder provider shaped like a mapped-public asset feed."""

    def get_assets(
        self,
        *,
        site_id: str,
        site_name: str,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> list[ProviderAsset]:
        del site_name, radius_km

        def coords(offsets: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
            return [
                _offset_point_km(
                    latitude,
                    longitude,
                    north_km=north_km,
                    east_km=east_km,
                )
                for north_km, east_km in offsets
            ]

        source = GRID_CONTEXT_FIXTURE_SOURCE_LAYER
        operator = "Mapped public placeholder"

        return [
            ProviderAsset(
                asset_id=f"{site_id}-line-132",
                asset_type=GridAssetType.LINE,
                name="Mapped 132 kV corridor",
                operator=operator,
                voltage_kv=132.0,
                circuits=1,
                geometry_type=GridGeometryType.LINE,
                coordinates=coords([(-1.2, 0.4), (2.3, 1.0), (4.2, 1.2)]),
                source=source,
            ),
            ProviderAsset(
                asset_id=f"{site_id}-substation-132",
                asset_type=GridAssetType.SUBSTATION,
                name="Mapped 132 kV substation",
                operator=operator,
                voltage_kv=132.0,
                circuits=None,
                geometry_type=GridGeometryType.POINT,
                coordinates=coords([(1.4, -0.9)]),
                source=source,
            ),
            ProviderAsset(
                asset_id=f"{site_id}-line-220",
                asset_type=GridAssetType.LINE,
                name="Mapped 220 kV transmission line",
                operator=operator,
                voltage_kv=220.0,
                circuits=2,
                geometry_type=GridGeometryType.LINE,
                coordinates=coords([(-2.5, -2.0), (1.0, -1.5), (4.2, -0.8)]),
                source=source,
            ),
            ProviderAsset(
                asset_id=f"{site_id}-substation-220",
                asset_type=GridAssetType.SUBSTATION,
                name="Mapped 220 kV switching station",
                operator=operator,
                voltage_kv=220.0,
                circuits=None,
                geometry_type=GridGeometryType.POINT,
                coordinates=coords([(3.8, 2.3)]),
                source=source,
            ),
            ProviderAsset(
                asset_id=f"{site_id}-line-380",
                asset_type=GridAssetType.LINE,
                name="Mapped 380 kV backbone corridor",
                operator=operator,
                voltage_kv=380.0,
                circuits=2,
                geometry_type=GridGeometryType.LINE,
                coordinates=coords([(-8.5, 6.2), (0.0, 6.4), (8.5, 6.5)]),
                source=source,
            ),
        ]

def _parse_voltage_kv(raw_voltage: str | None) -> float | None:
    """Convert common OSM voltage tag formats into nominal kV."""
    if raw_voltage is None:
        return None

    values_kv: list[float] = []
    for token in _VOLTAGE_NUMBER_PATTERN.findall(raw_voltage):
        numeric = float(token)
        if numeric <= 0:
            continue
        values_kv.append(numeric / 1000.0 if numeric > 1000.0 else numeric)

    if not values_kv:
        return None
    return round(max(values_kv), 3)


def _parse_circuits(raw_circuits: str | None) -> int | None:
    """Convert common OSM circuits tag formats into an integer when practical."""
    if raw_circuits is None:
        return None

    compact = raw_circuits.strip().replace(" ", "")
    if not compact:
        return None

    if ";" in compact:
        tokens = [token for token in compact.split(";") if token]
        if tokens and all(token.isdigit() for token in tokens):
            total = sum(int(token) for token in tokens)
            return total or None

    match = _POSITIVE_INTEGER_PATTERN.search(compact)
    if match is None:
        return None

    value = int(match.group())
    return value or None


def _is_closed_ring(coordinates: Sequence[tuple[float, float]]) -> bool:
    """Return True when the geometry looks like a closed polygon ring."""
    return len(coordinates) >= 4 and coordinates[0] == coordinates[-1]


def _extract_coordinates_from_overpass_element(
    element: dict[str, Any],
    *,
    allow_center_fallback: bool = True,
) -> tuple[GridGeometryType, list[tuple[float, float]]] | None:
    """Extract normalized geometry from one Overpass element."""
    element_type = element.get("type")

    if element_type == "node":
        latitude = element.get("lat")
        longitude = element.get("lon")
        if latitude is None or longitude is None:
            return None
        return GridGeometryType.POINT, [(float(latitude), float(longitude))]

    geometry = element.get("geometry")
    if isinstance(geometry, list):
        coordinates = [
            (float(point["lat"]), float(point["lon"]))
            for point in geometry
            if isinstance(point, dict) and "lat" in point and "lon" in point
        ]
        if coordinates:
            if len(coordinates) == 1:
                return GridGeometryType.POINT, coordinates
            geometry_type = (
                GridGeometryType.POLYGON
                if _is_closed_ring(coordinates)
                else GridGeometryType.LINE
            )
            return geometry_type, coordinates

    center = element.get("center")
    if (
        allow_center_fallback
        and isinstance(center, dict)
        and "lat" in center
        and "lon" in center
    ):
        return GridGeometryType.POINT, [(float(center["lat"]), float(center["lon"]))]

    return None


def _classify_overpass_asset_type(power_tag: str | None) -> GridAssetType | None:
    """Map OSM power tags into the narrower screening asset types."""
    if power_tag is None:
        return None

    normalized = power_tag.strip().lower()
    if normalized in {"substation", "sub_station"}:
        return GridAssetType.SUBSTATION
    if normalized in {"line", "minor_line", "cable"}:
        return GridAssetType.LINE
    return None


def _build_overpass_query(latitude: float, longitude: float, radius_km: float) -> str:
    """Build the Overpass QL query for nearby mapped-public grid assets."""
    radius_m = max(100, int(math.ceil(radius_km * 1000.0)))
    return f"""
[out:json][timeout:{OVERPASS_QUERY_TIMEOUT_SECONDS}];
(
  way["power"~"{_OVERPASS_LINE_TAG_PATTERN}"](around:{radius_m},{latitude:.6f},{longitude:.6f});
);
out body geom;
(
  node["power"~"{_OVERPASS_SUBSTATION_TAG_PATTERN}"](around:{radius_m},{latitude:.6f},{longitude:.6f});
  way["power"~"{_OVERPASS_SUBSTATION_TAG_PATTERN}"](around:{radius_m},{latitude:.6f},{longitude:.6f});
);
out body geom center;
""".strip()


def _normalize_overpass_element(element: dict[str, Any]) -> ProviderAsset | None:
    """Convert one raw Overpass JSON element into the provider-native asset shape."""
    tags = element.get("tags")
    if not isinstance(tags, dict):
        return None

    asset_type = _classify_overpass_asset_type(tags.get("power"))
    if asset_type is None:
        return None

    geometry = _extract_coordinates_from_overpass_element(
        element,
        allow_center_fallback=asset_type != GridAssetType.LINE,
    )
    if geometry is None:
        return None

    geometry_type, coordinates = geometry
    if asset_type == GridAssetType.LINE and geometry_type != GridGeometryType.LINE:
        return None

    name = tags.get("name") or tags.get("ref")
    operator = tags.get("operator") or tags.get("owner")
    voltage_kv = _parse_voltage_kv(tags.get("voltage"))
    circuits = _parse_circuits(tags.get("circuits"))

    if not name:
        if asset_type == GridAssetType.SUBSTATION:
            name = (
                f"Mapped {voltage_kv:.0f} kV substation"
                if voltage_kv is not None
                else "Mapped substation"
            )
        else:
            name = (
                f"Mapped {voltage_kv:.0f} kV line"
                if voltage_kv is not None
                else "Mapped power line"
            )

    element_type = str(element.get("type", "element"))
    element_id = str(element.get("id", "unknown"))

    return ProviderAsset(
        asset_id=f"osm-{element_type}-{element_id}",
        asset_type=asset_type,
        name=name,
        operator=operator,
        voltage_kv=voltage_kv,
        circuits=circuits,
        geometry_type=geometry_type,
        coordinates=coordinates,
        source=GRID_CONTEXT_SOURCE_LAYER,
        confidence=GridConfidence.MAPPED_PUBLIC,
    )


class OverpassGridContextProvider:
    """Mapped-public provider backed by live OpenStreetMap/Overpass queries."""

    def __init__(
        self,
        *,
        endpoint_url: str = OVERPASS_INTERPRETER_URL,
        request_timeout_seconds: int = OVERPASS_REQUEST_TIMEOUT_SECONDS,
    ):
        self.endpoint_url = endpoint_url
        self.request_timeout_seconds = request_timeout_seconds

    def get_assets(
        self,
        *,
        site_id: str,
        site_name: str,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> list[ProviderAsset]:
        del site_id, site_name

        try:
            import requests
        except ImportError as exc:
            raise GridContextProviderError(
                "The 'requests' package is required for Grid Context public asset queries."
            ) from exc

        query = _build_overpass_query(latitude, longitude, radius_km)

        # Retry with exponential backoff
        last_exc: Exception | None = None
        for attempt in range(OVERPASS_MAX_RETRIES):
            try:
                response = requests.post(
                    self.endpoint_url,
                    data={"data": query},
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "dc-feasibility-v4-grid-context/1.0",
                    },
                    timeout=self.request_timeout_seconds,
                )
                response.raise_for_status()
                break  # Success
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < OVERPASS_MAX_RETRIES - 1:
                    wait = OVERPASS_BACKOFF_BASE_SECONDS * (OVERPASS_BACKOFF_FACTOR ** attempt)
                    logger.warning(
                        "Overpass API attempt %d/%d failed (%s), retrying in %.1fs",
                        attempt + 1, OVERPASS_MAX_RETRIES, exc, wait,
                    )
                    time.sleep(wait)
        else:
            # All retries exhausted — graceful degradation: return empty list
            logger.error(
                "Overpass API failed after %d retries: %s. "
                "Returning empty asset list (graceful degradation).",
                OVERPASS_MAX_RETRIES, last_exc,
            )
            return []

        try:
            payload = response.json()
        except ValueError:
            logger.error("Overpass API returned invalid JSON. Returning empty asset list.")
            return []

        elements = payload.get("elements")
        if not isinstance(elements, list):
            logger.error("Overpass API returned unexpected payload shape. Returning empty asset list.")
            return []

        assets: list[ProviderAsset] = []
        for element in elements:
            if not isinstance(element, dict):
                continue
            asset = _normalize_overpass_element(element)
            if asset is not None:
                assets.append(asset)
        return assets


_DEFAULT_PROVIDER = OverpassGridContextProvider()


def get_default_grid_context_provider() -> GridContextProvider:
    """Return the default nearby-grid asset provider."""
    return _DEFAULT_PROVIDER


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points in kilometers."""
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))
    return EARTH_RADIUS_KM * c


def _project_to_local_km(
    latitude: float,
    longitude: float,
    reference_latitude: float,
    reference_longitude: float,
) -> tuple[float, float]:
    """Project latitude/longitude into local x/y kilometers around a reference point."""
    mean_lat = math.radians((latitude + reference_latitude) / 2.0)
    x_km = (
        math.radians(longitude - reference_longitude)
        * EARTH_RADIUS_KM
        * math.cos(mean_lat)
    )
    y_km = math.radians(latitude - reference_latitude) * EARTH_RADIUS_KM
    return x_km, y_km


def _point_to_segment_distance_km(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Shortest distance from a point to a line segment in local kilometers."""
    px, py = point
    ax, ay = start
    bx, by = end

    dx = bx - ax
    dy = by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)

    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    closest_x = ax + t * dx
    closest_y = ay + t * dy
    return math.hypot(px - closest_x, py - closest_y)


def _point_in_polygon(point: tuple[float, float], polygon: Sequence[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test in local projected coordinates."""
    x, y = point
    inside = False
    point_count = len(polygon)
    if point_count < 3:
        return False

    for index in range(point_count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % point_count]
        intersects = ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
        )
        if intersects:
            inside = not inside
    return inside


def geometry_distance_km(
    site_latitude: float,
    site_longitude: float,
    geometry_type: GridGeometryType,
    coordinates: Sequence[Sequence[float]],
) -> float:
    """Approximate distance from the site point to a point/line/polygon asset."""
    if not coordinates:
        return math.inf

    if geometry_type == GridGeometryType.POINT or len(coordinates) == 1:
        point_latitude, point_longitude = float(coordinates[0][0]), float(coordinates[0][1])
        return haversine_km(
            site_latitude,
            site_longitude,
            point_latitude,
            point_longitude,
        )

    projected = [
        _project_to_local_km(
            float(latitude),
            float(longitude),
            site_latitude,
            site_longitude,
        )
        for latitude, longitude in coordinates
    ]
    origin = (0.0, 0.0)

    if geometry_type == GridGeometryType.POLYGON:
        if _point_in_polygon(origin, projected):
            return 0.0
        ring = list(projected)
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        return min(
            _point_to_segment_distance_km(origin, ring[index], ring[index + 1])
            for index in range(len(ring) - 1)
        )

    return min(
        _point_to_segment_distance_km(origin, projected[index], projected[index + 1])
        for index in range(len(projected) - 1)
    )


def _normalize_provider_assets(
    *,
    site_latitude: float,
    site_longitude: float,
    radius_km: float,
    provider_assets: Sequence[ProviderAsset],
) -> list[GridAsset]:
    """Convert provider-native assets into cacheable API models."""
    normalized_assets: list[GridAsset] = []
    for provider_asset in provider_assets:
        distance_km = geometry_distance_km(
            site_latitude,
            site_longitude,
            provider_asset.geometry_type,
            provider_asset.coordinates,
        )
        if distance_km > radius_km:
            continue

        normalized_assets.append(
            GridAsset(
                asset_id=provider_asset.asset_id,
                asset_type=provider_asset.asset_type,
                name=provider_asset.name,
                operator=provider_asset.operator,
                voltage_kv=provider_asset.voltage_kv,
                circuits=provider_asset.circuits,
                distance_km=round(distance_km, 3),
                geometry_type=provider_asset.geometry_type,
                coordinates=[
                    [round(float(latitude), 6), round(float(longitude), 6)]
                    for latitude, longitude in provider_asset.coordinates
                ],
                source=provider_asset.source,
                confidence=provider_asset.confidence,
            )
        )

    normalized_assets.sort(
        key=lambda asset: (
            asset.distance_km,
            0 if asset.asset_type == GridAssetType.SUBSTATION else 1,
            -(asset.voltage_kv or 0.0),
        )
    )
    return normalized_assets


def build_grid_context_summary(
    *,
    radius_km: float,
    assets: Sequence[GridAsset],
) -> GridContextSummary:
    """Aggregate nearby assets into descriptive screening metrics."""
    lines = [asset for asset in assets if asset.asset_type == GridAssetType.LINE]
    substations = [
        asset for asset in assets if asset.asset_type == GridAssetType.SUBSTATION
    ]
    max_voltage = max(
        (asset.voltage_kv for asset in assets if asset.voltage_kv is not None),
        default=None,
    )
    return GridContextSummary(
        radius_km=round(radius_km, 3),
        nearby_line_count=len(lines),
        nearby_substation_count=len(substations),
        nearest_line_km=lines[0].distance_km if lines else None,
        nearest_substation_km=substations[0].distance_km if substations else None,
        max_voltage_kv=max_voltage,
        high_voltage_assets_within_radius=sum(
            1
            for asset in assets
            if (asset.voltage_kv or 0.0) >= HIGH_VOLTAGE_THRESHOLD_KV
        ),
    )


def has_grid_official_evidence(official_evidence: GridOfficialEvidence | None) -> bool:
    """Return True when any manual official-evidence field is populated."""
    if official_evidence is None:
        return False
    return any(value is not None for value in official_evidence.model_dump().values())


def _score_distance_band(
    distance_km: float | None,
    *,
    max_points: float,
    full_points_km: float,
    zero_points_km: float,
) -> float:
    """Score distance with a coarse linear falloff to avoid false precision."""
    if distance_km is None:
        return 0.0
    if distance_km <= full_points_km:
        return max_points
    if distance_km >= zero_points_km:
        return 0.0

    span_km = max(zero_points_km - full_points_km, 0.1)
    return max_points * (1.0 - ((distance_km - full_points_km) / span_km))


def _score_voltage_visibility(max_voltage_kv: float | None) -> float:
    """Translate visible voltage bands into a coarse screening signal."""
    if max_voltage_kv is None or max_voltage_kv <= 0.0:
        return 0.0
    if max_voltage_kv >= 380.0:
        return GRID_SCORE_MAX_VOLTAGE_POINTS
    if max_voltage_kv >= 220.0:
        return 24.0
    if max_voltage_kv >= 150.0:
        return 18.0
    if max_voltage_kv >= HIGH_VOLTAGE_THRESHOLD_KV:
        return 14.0
    if max_voltage_kv >= 63.0:
        return 8.0
    return 4.0


def _score_official_evidence(official_evidence: GridOfficialEvidence | None) -> float:
    """Boost the score only when manual official evidence is explicitly present."""
    if official_evidence is None or not has_grid_official_evidence(official_evidence):
        return 0.0

    score = 6.0
    if (
        official_evidence.confirmed_substation_name is not None
        or official_evidence.confirmed_voltage_kv is not None
    ):
        score += 4.0
    if (
        official_evidence.confirmed_requested_mw is not None
        or official_evidence.confirmed_available_mw is not None
    ):
        score += 3.0
    if (
        official_evidence.connection_status is not None
        or official_evidence.timeline_status is not None
    ):
        score += 2.0
    return min(GRID_SCORE_MAX_EVIDENCE_POINTS, score)


def compute_grid_context_score(
    summary: GridContextSummary,
    official_evidence: GridOfficialEvidence | None = None,
) -> GridContextScore:
    """Compute a heuristic screening-attractiveness score."""
    voltage_score = _score_voltage_visibility(summary.max_voltage_kv)
    line_proximity_score = 0.0
    if summary.high_voltage_assets_within_radius > 0:
        line_proximity_score = _score_distance_band(
            summary.nearest_line_km,
            max_points=20.0,
            full_points_km=0.5,
            zero_points_km=5.0,
        )
    hv_density_score = min(
        GRID_SCORE_MAX_DISTANCE_POINTS - line_proximity_score,
        summary.high_voltage_assets_within_radius * 5.0,
    )
    distance_score = min(
        GRID_SCORE_MAX_DISTANCE_POINTS,
        line_proximity_score + hv_density_score,
    )
    substation_score = _score_distance_band(
        summary.nearest_substation_km,
        max_points=GRID_SCORE_MAX_SUBSTATION_POINTS,
        full_points_km=1.0,
        zero_points_km=8.0,
    )
    evidence_score = _score_official_evidence(official_evidence)
    overall_score = voltage_score + distance_score + substation_score + evidence_score

    notes = [
        "Heuristic screening signal only; it is not confirmed connection capacity or connectable MW.",
        "The score highlights visible voltage, nearby mapped assets, and mapped substation proximity inside the chosen radius.",
    ]
    if evidence_score > 0:
        notes.append(
            f"User-confirmed official evidence contributes {evidence_score:.0f} of {GRID_SCORE_MAX_EVIDENCE_POINTS:.0f} evidence points."
        )
    else:
        notes.append(
            "No user-confirmed official evidence is active, so the evidence component stays at 0."
        )
    if summary.max_voltage_kv is None:
        notes.append("No mapped voltage tags were visible inside the selected radius.")
    elif summary.max_voltage_kv >= 220.0:
        notes.append("220 kV or higher mapped assets are visible within the selected radius.")
    elif summary.max_voltage_kv >= HIGH_VOLTAGE_THRESHOLD_KV:
        notes.append("At least one 132 kV or higher mapped asset is visible within the selected radius.")
    else:
        notes.append("Only lower-voltage mapped assets are visible within the selected radius.")

    if summary.nearest_substation_km is None:
        notes.append("No mapped substation is visible inside the selected radius.")
    else:
        notes.append(
            f"Nearest mapped substation is approximately {summary.nearest_substation_km:.1f} km away."
        )
    if summary.high_voltage_assets_within_radius == 0:
        notes.append("No high-voltage mapped assets were counted inside the selected radius.")

    return GridContextScore(
        overall_score=round(overall_score, 1),
        voltage_score=round(voltage_score, 1),
        distance_score=round(distance_score, 1),
        substation_score=round(substation_score, 1),
        evidence_score=round(evidence_score, 1),
        notes=notes,
    )


def compute_data_quality_confidence(summary: GridContextSummary) -> float:
    """Estimate data quality confidence based on region coverage (0.0–1.0).

    A region with many mapped assets is likely well-covered in OSM.
    A region with zero assets could mean poor coverage OR genuinely no grid.
    We use asset count, voltage presence, and substation presence as signals.

    Returns:
        Float in [0.0, 1.0]. Higher = more confidence in data completeness.
    """
    score = 0.0
    total_assets = summary.nearby_line_count + summary.nearby_substation_count

    # Asset count signal: 0 assets = 0.0, 1–2 = 0.3, 3–5 = 0.5, 6–10 = 0.7, >10 = 0.8
    if total_assets == 0:
        return 0.0
    elif total_assets <= 2:
        score = 0.3
    elif total_assets <= 5:
        score = 0.5
    elif total_assets <= 10:
        score = 0.7
    else:
        score = 0.8

    # Bonus: voltage data present (tagged assets = better data quality)
    if summary.max_voltage_kv is not None:
        score += 0.1

    # Bonus: substation present (substations are well-mapped in good regions)
    if summary.nearby_substation_count > 0:
        score += 0.1

    return min(1.0, round(score, 2))


def _derive_overall_confidence(
    assets: Sequence[GridAsset],
    official_evidence: GridOfficialEvidence | None = None,
) -> GridConfidence:
    """Pick the highest-confidence label present in the current result."""
    if has_grid_official_evidence(official_evidence):
        return GridConfidence.USER_CONFIRMED

    for confidence in (
        GridConfidence.USER_CONFIRMED,
        GridConfidence.OFFICIAL_AGGREGATE,
        GridConfidence.MAPPED_PUBLIC,
    ):
        if any(asset.confidence == confidence for asset in assets):
            return confidence
    return GridConfidence.MAPPED_PUBLIC


def _build_user_confirmed_evidence_notes(
    official_evidence: GridOfficialEvidence,
) -> list[GridEvidenceNote]:
    """Build explicit notes for manual official evidence entered by the user."""
    detail_bits: list[str] = []
    if official_evidence.confirmed_substation_name is not None:
        detail_bits.append(f"Substation: {official_evidence.confirmed_substation_name}")
    if official_evidence.confirmed_voltage_kv is not None:
        detail_bits.append(f"Voltage: {official_evidence.confirmed_voltage_kv:g} kV")
    if official_evidence.confirmed_requested_mw is not None:
        detail_bits.append(f"Requested: {official_evidence.confirmed_requested_mw:g} MW")
    if official_evidence.confirmed_available_mw is not None:
        detail_bits.append(f"Available: {official_evidence.confirmed_available_mw:g} MW")

    notes = [
        GridEvidenceNote(
            label="User-confirmed official evidence",
            detail=(
                "Manual official-evidence fields are saved for this site. Treat only those "
                "confirmed fields as user-confirmed; mapped geometry remains screening-grade."
            ),
            source=GRID_CONTEXT_USER_CONFIRMED_SOURCE_LAYER,
            confidence=GridConfidence.USER_CONFIRMED,
        )
    ]

    if official_evidence.utility_or_tso_reference is not None or official_evidence.reference_date is not None:
        reference_bits = [
            bit
            for bit in [
                official_evidence.utility_or_tso_reference,
                official_evidence.reference_date,
            ]
            if bit is not None
        ]
        notes.append(
            GridEvidenceNote(
                label="Evidence reference",
                detail=" | ".join(reference_bits),
                source=GRID_CONTEXT_USER_CONFIRMED_SOURCE_LAYER,
                confidence=GridConfidence.USER_CONFIRMED,
            )
        )

    if detail_bits:
        notes.append(
            GridEvidenceNote(
                label="Confirmed connection details",
                detail=" | ".join(detail_bits),
                source=GRID_CONTEXT_USER_CONFIRMED_SOURCE_LAYER,
                confidence=GridConfidence.USER_CONFIRMED,
            )
        )

    status_bits = [
        bit
        for bit in [
            official_evidence.connection_status,
            official_evidence.timeline_status,
            official_evidence.notes,
        ]
        if bit is not None
    ]
    if status_bits:
        notes.append(
            GridEvidenceNote(
                label="Status and timeline",
                detail=" | ".join(status_bits),
                source=GRID_CONTEXT_USER_CONFIRMED_SOURCE_LAYER,
                confidence=GridConfidence.USER_CONFIRMED,
            )
        )

    return notes


def _build_evidence_notes(
    source_layers: Sequence[str],
    official_evidence: GridOfficialEvidence | None = None,
) -> list[GridEvidenceNote]:
    """Build the standard screening notes for the current mapped-public source mix."""
    if GRID_CONTEXT_FIXTURE_SOURCE_LAYER in source_layers and GRID_CONTEXT_SOURCE_LAYER not in source_layers:
        provider_label = "Mapped-public fixture provider"
        provider_detail = (
            "This result was built from a deterministic fixture provider shaped like "
            "mapped-public grid data."
        )
        provider_source = GRID_CONTEXT_FIXTURE_SOURCE_LAYER
    else:
        provider_label = "Mapped-public OSM screening layer"
        provider_detail = (
            "This result uses OpenStreetMap-derived power features queried through "
            "an Overpass interpreter and normalized for screening use."
        )
        provider_source = GRID_CONTEXT_SOURCE_LAYER

    notes = [
        GridEvidenceNote(
            label="Screening-grade only",
            detail=(
                "Grid Context results are screening-grade and should be used to decide "
                "whether deeper utility engagement is worthwhile."
            ),
            source=provider_source,
            confidence=GridConfidence.MAPPED_PUBLIC,
        ),
        GridEvidenceNote(
            label=provider_label,
            detail=provider_detail,
            source=provider_source,
            confidence=GridConfidence.MAPPED_PUBLIC,
        ),
        GridEvidenceNote(
            label="No exact capacity claim",
            detail=(
                "Nearby lines or substations do not imply spare connection capacity; "
                "exact available MW requires official utility or TSO evidence."
            ),
            source=provider_source,
            confidence=GridConfidence.MAPPED_PUBLIC,
        ),
    ]

    if official_evidence is not None and has_grid_official_evidence(official_evidence):
        notes.extend(_build_user_confirmed_evidence_notes(official_evidence))
    return notes


def build_grid_context_result(
    *,
    site_id: str,
    site: Site,
    radius_km: float,
    provider: GridContextProvider | None = None,
    include_score: bool = False,
    official_evidence: GridOfficialEvidence | None = None,
) -> GridContextResult:
    """Build one cacheable grid-context result for a saved site."""
    if site.latitude is None or site.longitude is None:
        raise ValueError(
            "Site has no coordinates. Set latitude and longitude before analysing Grid Context."
        )

    resolved_provider = provider or get_default_grid_context_provider()
    provider_assets = resolved_provider.get_assets(
        site_id=site_id,
        site_name=site.name,
        latitude=site.latitude,
        longitude=site.longitude,
        radius_km=radius_km,
    )
    assets = _normalize_provider_assets(
        site_latitude=site.latitude,
        site_longitude=site.longitude,
        radius_km=radius_km,
        provider_assets=provider_assets,
    )
    summary = build_grid_context_summary(radius_km=radius_km, assets=assets)
    score = compute_grid_context_score(summary, official_evidence) if include_score else None
    confidence = _derive_overall_confidence(assets, official_evidence)
    source_layers = sorted(
        {
            *{asset.source for asset in assets},
            *(
                {GRID_CONTEXT_USER_CONFIRMED_SOURCE_LAYER}
                if has_grid_official_evidence(official_evidence)
                else set()
            ),
        }
    ) or [GRID_CONTEXT_SOURCE_LAYER]
    evidence_notes = _build_evidence_notes(source_layers, official_evidence)

    data_quality = compute_data_quality_confidence(summary)

    return GridContextResult(
        site_id=site_id,
        site_name=site.name,
        latitude=site.latitude,
        longitude=site.longitude,
        analysis_grade=GridAnalysisGrade.SCREENING_GRADE,
        summary=summary,
        score=score,
        assets=assets,
        evidence_notes=evidence_notes,
        official_evidence=official_evidence if has_grid_official_evidence(official_evidence) else None,
        official_context_notes=[note.detail for note in evidence_notes],
        source_layers=source_layers,
        confidence=confidence,
        data_quality_confidence=data_quality,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
    )
