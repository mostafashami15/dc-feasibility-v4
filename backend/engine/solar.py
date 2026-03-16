"""
DC Feasibility Tool v4 — PVGIS Solar Profile Module
=====================================================
Fetches and prepares normalized hourly PV generation profiles from PVGIS.

Why a normalized 1 kWp profile:
    - The site coordinates come from the saved site (including KML/KMZ uploads).
    - The installed PV size is a user decision, not implied by the site.
    - A 1 kWp normalized profile can be cached once and then scaled by any
      installed PV capacity later without refetching PVGIS.

Source basis:
    - PVGIS non-interactive API (backend/server-side only; browser AJAX is not
      supported by PVGIS)
    - PVGIS seriescalc endpoint for hourly PV output

Reference: Architecture Agreement Section 3.9 / Green Energy extension
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional, TypedDict

from engine.weather import average_multi_year


PVGIS_SERIESCALC_URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"
PVGIS_API_VERSION = "5.3"

PVGIS_ALLOWED_TECHNOLOGIES = {"crystSi", "CIS", "CdTe", "Unknown"}
PVGIS_ALLOWED_MOUNTING_PLACES = {"free", "building"}

PVGIS_DEFAULT_START_YEAR = 2019
PVGIS_DEFAULT_END_YEAR = 2023
PVGIS_DEFAULT_TECHNOLOGY = "crystSi"
PVGIS_DEFAULT_MOUNTING_PLACE = "free"
PVGIS_DEFAULT_SYSTEM_LOSS_PCT = 14.0
PVGIS_DEFAULT_USE_HORIZON = True
PVGIS_DEFAULT_OPTIMAL_ANGLES = True


@dataclass
class PVGISNormalizedProfile:
    """Representative-year hourly PV output normalized to 1 kWp."""

    site_id: str
    latitude: float
    longitude: float
    profile_key: str
    start_year: int
    end_year: int
    years_averaged: list[int]
    pv_technology: str
    mounting_place: str
    system_loss_pct: float
    use_horizon: bool
    optimal_angles: bool
    surface_tilt_deg: Optional[float]
    surface_azimuth_deg: Optional[float]
    hourly_pv_kw_per_kwp: list[float]
    source: str
    radiation_database: Optional[str] = None
    elevation_m: Optional[float] = None
    pv_module_info: Optional[str] = None
    hours: int = field(init=False)

    def __post_init__(self) -> None:
        self.hours = len(self.hourly_pv_kw_per_kwp)
        if self.hours not in (8760, 8784):
            raise ValueError(
                "hourly_pv_kw_per_kwp must contain 8760 or 8784 hourly values; "
                f"got {self.hours}"
            )


class PVGISResponseMetadata(TypedDict):
    """Normalized PVGIS metadata extracted from one API response."""

    radiation_database: str | None
    elevation_m: float | None
    pv_module_info: str | None
    resolved_slope: float | None
    resolved_azimuth: float | None


def _rounded_coordinate(value: float) -> float:
    """Stabilize cache keys for coordinates stored as floating-point numbers."""
    return round(float(value), 6)


def _optional_float(value: object) -> float | None:
    """Convert a JSON scalar to float when present."""
    if value is None:
        return None
    return float(value)


def _optional_text(value: object) -> str | None:
    """Convert a JSON scalar to text when present."""
    if value is None:
        return None
    return str(value)


def make_pvgis_profile_key(
    *,
    site_id: str,
    latitude: float,
    longitude: float,
    start_year: int,
    end_year: int,
    pv_technology: str,
    mounting_place: str,
    system_loss_pct: float,
    use_horizon: bool,
    optimal_angles: bool,
    surface_tilt_deg: Optional[float],
    surface_azimuth_deg: Optional[float],
) -> str:
    """Create a deterministic cache key for a PVGIS normalized profile."""
    tilt_value = None
    azimuth_value = None
    if not optimal_angles:
        tilt_value = (
            round(float(surface_tilt_deg), 4)
            if surface_tilt_deg is not None
            else None
        )
        azimuth_value = (
            round(float(surface_azimuth_deg), 4)
            if surface_azimuth_deg is not None
            else None
        )

    payload = {
        "site_id": site_id,
        "latitude": _rounded_coordinate(latitude),
        "longitude": _rounded_coordinate(longitude),
        "start_year": start_year,
        "end_year": end_year,
        "pv_technology": pv_technology,
        "mounting_place": mounting_place,
        "system_loss_pct": round(float(system_loss_pct), 4),
        "use_horizon": bool(use_horizon),
        "optimal_angles": bool(optimal_angles),
        "surface_tilt_deg": tilt_value,
        "surface_azimuth_deg": azimuth_value,
        "pvgis_api_version": PVGIS_API_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _validate_pvgis_inputs(
    *,
    start_year: int,
    end_year: int,
    pv_technology: str,
    mounting_place: str,
    system_loss_pct: float,
    use_horizon: bool,
    optimal_angles: bool,
    surface_tilt_deg: Optional[float],
    surface_azimuth_deg: Optional[float],
) -> None:
    """Validate PVGIS request parameters against the documented API contract."""
    if start_year > end_year:
        raise ValueError(
            f"start_year ({start_year}) cannot be greater than end_year ({end_year})"
        )
    if pv_technology not in PVGIS_ALLOWED_TECHNOLOGIES:
        raise ValueError(
            f"pv_technology must be one of {sorted(PVGIS_ALLOWED_TECHNOLOGIES)}"
        )
    if mounting_place not in PVGIS_ALLOWED_MOUNTING_PLACES:
        raise ValueError(
            f"mounting_place must be one of {sorted(PVGIS_ALLOWED_MOUNTING_PLACES)}"
        )
    if system_loss_pct < 0 or system_loss_pct > 100:
        raise ValueError(
            f"system_loss_pct must be between 0 and 100; got {system_loss_pct}"
        )
    if not isinstance(use_horizon, bool):
        raise ValueError("use_horizon must be a boolean")
    if not isinstance(optimal_angles, bool):
        raise ValueError("optimal_angles must be a boolean")
    if not optimal_angles:
        if surface_tilt_deg is None:
            raise ValueError(
                "surface_tilt_deg is required when optimal_angles is False"
            )
        if surface_azimuth_deg is None:
            raise ValueError(
                "surface_azimuth_deg is required when optimal_angles is False"
            )
        if surface_tilt_deg < 0 or surface_tilt_deg > 90:
            raise ValueError(
                f"surface_tilt_deg must be between 0 and 90; got {surface_tilt_deg}"
            )
        if surface_azimuth_deg < -180 or surface_azimuth_deg > 180:
            raise ValueError(
                "surface_azimuth_deg must be between -180 and 180; "
                f"got {surface_azimuth_deg}"
            )


def _parse_pvgis_hourly_response(data: dict) -> tuple[list[float], PVGISResponseMetadata]:
    """Extract hourly normalized PV output from PVGIS seriescalc JSON."""
    outputs = data.get("outputs")
    if not isinstance(outputs, dict):
        raise ValueError("PVGIS response is missing the 'outputs' object")

    hourly = outputs.get("hourly")
    if not isinstance(hourly, list):
        raise ValueError("PVGIS response is missing the 'outputs.hourly' array")

    profile_kw_per_kwp: list[float] = []
    for entry in hourly:
        if not isinstance(entry, dict) or "P" not in entry:
            raise ValueError("PVGIS hourly entry is missing the 'P' PV output field")
        pv_output_w = float(entry["P"])
        profile_kw_per_kwp.append(round(pv_output_w / 1000.0, 6))

    inputs = data.get("inputs", {}) if isinstance(data.get("inputs"), dict) else {}
    meteo = inputs.get("meteo_data", {}) if isinstance(inputs.get("meteo_data"), dict) else {}
    mounting = (
        inputs.get("mounting_system", {})
        if isinstance(inputs.get("mounting_system"), dict)
        else {}
    )
    fixed_mount = mounting.get("fixed", {}) if isinstance(mounting.get("fixed"), dict) else {}
    pv_module = inputs.get("pv_module", {}) if isinstance(inputs.get("pv_module"), dict) else {}
    location = inputs.get("location", {}) if isinstance(inputs.get("location"), dict) else {}
    slope = fixed_mount.get("slope", {}) if isinstance(fixed_mount.get("slope"), dict) else {}
    azimuth = fixed_mount.get("azimuth", {}) if isinstance(fixed_mount.get("azimuth"), dict) else {}

    metadata: PVGISResponseMetadata = {
        "radiation_database": _optional_text(meteo.get("radiation_db")),
        "elevation_m": _optional_float(location.get("elevation")),
        "pv_module_info": _optional_text(pv_module.get("technology")),
        "resolved_slope": _optional_float(slope.get("value")),
        "resolved_azimuth": _optional_float(azimuth.get("value")),
    }
    return profile_kw_per_kwp, metadata


def fetch_pvgis_hourly_year(
    *,
    latitude: float,
    longitude: float,
    year: int,
    pv_technology: str,
    mounting_place: str,
    system_loss_pct: float,
    use_horizon: bool,
    optimal_angles: bool,
    surface_tilt_deg: Optional[float],
    surface_azimuth_deg: Optional[float],
) -> tuple[list[float], PVGISResponseMetadata]:
    """Fetch one calendar year of normalized hourly PV output from PVGIS."""
    try:
        import requests
    except ImportError as exc:
        raise ImportError(
            "The 'requests' library is required for PVGIS fetching. "
            "Install with: pip install requests"
        ) from exc

    _validate_pvgis_inputs(
        start_year=year,
        end_year=year,
        pv_technology=pv_technology,
        mounting_place=mounting_place,
        system_loss_pct=system_loss_pct,
        use_horizon=use_horizon,
        optimal_angles=optimal_angles,
        surface_tilt_deg=surface_tilt_deg,
        surface_azimuth_deg=surface_azimuth_deg,
    )

    params: dict[str, str | int | float] = {
        "lat": latitude,
        "lon": longitude,
        "startyear": year,
        "endyear": year,
        "pvcalculation": 1,
        "peakpower": 1,
        "pvtechchoice": pv_technology,
        "mountingplace": mounting_place,
        "loss": system_loss_pct,
        "components": 0,
        "usehorizon": 1 if use_horizon else 0,
        "trackingtype": 0,
        "outputformat": "json",
    }
    if optimal_angles:
        params["optimalangles"] = 1
    else:
        assert surface_tilt_deg is not None
        assert surface_azimuth_deg is not None
        params["angle"] = surface_tilt_deg
        params["aspect"] = surface_azimuth_deg

    response = requests.get(PVGIS_SERIESCALC_URL, params=params, timeout=60)
    response.raise_for_status()
    return _parse_pvgis_hourly_response(response.json())


def build_representative_pvgis_profile(
    *,
    site_id: str,
    latitude: float,
    longitude: float,
    start_year: int = PVGIS_DEFAULT_START_YEAR,
    end_year: int = PVGIS_DEFAULT_END_YEAR,
    pv_technology: str = PVGIS_DEFAULT_TECHNOLOGY,
    mounting_place: str = PVGIS_DEFAULT_MOUNTING_PLACE,
    system_loss_pct: float = PVGIS_DEFAULT_SYSTEM_LOSS_PCT,
    use_horizon: bool = PVGIS_DEFAULT_USE_HORIZON,
    optimal_angles: bool = PVGIS_DEFAULT_OPTIMAL_ANGLES,
    surface_tilt_deg: Optional[float] = None,
    surface_azimuth_deg: Optional[float] = None,
) -> PVGISNormalizedProfile:
    """Build a representative-year normalized PV profile from PVGIS."""
    _validate_pvgis_inputs(
        start_year=start_year,
        end_year=end_year,
        pv_technology=pv_technology,
        mounting_place=mounting_place,
        system_loss_pct=system_loss_pct,
        use_horizon=use_horizon,
        optimal_angles=optimal_angles,
        surface_tilt_deg=surface_tilt_deg,
        surface_azimuth_deg=surface_azimuth_deg,
    )

    yearly_data: dict[int, list[float]] = {}
    metadata: PVGISResponseMetadata | None = None
    for year in range(start_year, end_year + 1):
        hourly_profile, year_metadata = fetch_pvgis_hourly_year(
            latitude=latitude,
            longitude=longitude,
            year=year,
            pv_technology=pv_technology,
            mounting_place=mounting_place,
            system_loss_pct=system_loss_pct,
            use_horizon=use_horizon,
            optimal_angles=optimal_angles,
            surface_tilt_deg=surface_tilt_deg,
            surface_azimuth_deg=surface_azimuth_deg,
        )
        yearly_data[year] = hourly_profile
        if metadata is None:
            metadata = year_metadata

    assert metadata is not None

    representative = average_multi_year(yearly_data)
    profile_key = make_pvgis_profile_key(
        site_id=site_id,
        latitude=latitude,
        longitude=longitude,
        start_year=start_year,
        end_year=end_year,
        pv_technology=pv_technology,
        mounting_place=mounting_place,
        system_loss_pct=system_loss_pct,
        use_horizon=use_horizon,
        optimal_angles=optimal_angles,
        surface_tilt_deg=surface_tilt_deg,
        surface_azimuth_deg=surface_azimuth_deg,
    )

    resolved_tilt = None if optimal_angles else surface_tilt_deg
    resolved_azimuth = None if optimal_angles else surface_azimuth_deg
    if optimal_angles:
        resolved_tilt = metadata["resolved_slope"]
        resolved_azimuth = metadata["resolved_azimuth"]

    return PVGISNormalizedProfile(
        site_id=site_id,
        latitude=latitude,
        longitude=longitude,
        profile_key=profile_key,
        start_year=start_year,
        end_year=end_year,
        years_averaged=list(range(start_year, end_year + 1)),
        pv_technology=pv_technology,
        mounting_place=mounting_place,
        system_loss_pct=float(system_loss_pct),
        use_horizon=use_horizon,
        optimal_angles=optimal_angles,
        surface_tilt_deg=resolved_tilt,
        surface_azimuth_deg=resolved_azimuth,
        hourly_pv_kw_per_kwp=representative,
        source=(
            f"PVGIS {PVGIS_API_VERSION} seriescalc "
            f"({start_year}-{end_year}), representative-year average, "
            "normalized to 1 kWp"
        ),
        radiation_database=metadata["radiation_database"],
        elevation_m=metadata["elevation_m"],
        pv_module_info=metadata["pv_module_info"],
    )


def scale_normalized_profile(
    hourly_pv_kw_per_kwp: list[float],
    pv_capacity_kwp: float,
) -> list[float]:
    """Scale a normalized 1 kWp hourly PV profile to an installed capacity."""
    if pv_capacity_kwp < 0:
        raise ValueError(f"pv_capacity_kwp cannot be negative: {pv_capacity_kwp}")
    return [round(value * pv_capacity_kwp, 6) for value in hourly_pv_kw_per_kwp]
