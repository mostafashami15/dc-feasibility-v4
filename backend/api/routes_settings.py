"""
DC Feasibility Tool v4 - Settings API Routes
============================================
Runtime diagnostics and data-management helpers for the Settings page.

Serves:
    - external service reachability checks (Open-Meteo + PVGIS)
    - cache counts for weather and solar data
    - cache-clearing actions for maintenance/debugging
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.store import (
    clear_all_solar_cache,
    clear_weather_cache,
    count_sites,
    count_solar_profiles,
    count_solar_sites,
    count_weather_caches,
)
from engine.assumption_overrides import (
    AssumptionOverrideHistoryResponse,
    AssumptionOverridePresetsResponse,
    AssumptionOverridesResponse,
    AssumptionOverridesUpdateRequest,
    get_assumption_override_history,
    get_assumption_override_presets,
    get_assumption_overrides,
    save_assumption_override_updates,
)


router = APIRouter(prefix="/api/settings", tags=["Settings"])

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_TEMPLATES_DIR = _BACKEND_DIR / "export" / "templates"

_OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_PVGIS_SERIESCALC_URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"


class RuntimeStatusResponse(BaseModel):
    """Snapshot of local runtime state that the Settings page can show."""

    sites_stored: int
    weather_cached: int
    solar_sites_cached: int
    solar_profiles_cached: int
    report_templates_available: int
    report_template_names: list[str]


class ExternalServiceProbe(BaseModel):
    """Result of one outbound connectivity check."""

    key: str
    label: str
    ok: bool
    status_code: Optional[int] = None
    latency_ms: Optional[int] = None
    detail: str


class ExternalServicesResponse(BaseModel):
    """Settings response for all external-service probes."""

    checked_at_utc: str
    services: list[ExternalServiceProbe]


class CacheClearRequest(BaseModel):
    """Request to clear one or more server-side caches."""

    target: Literal["weather", "solar", "all"] = Field(
        description="Which cache group to clear."
    )


class CacheClearResponse(BaseModel):
    """How many cached files/profiles were removed by the clear action."""

    target: Literal["weather", "solar", "all"]
    removed_weather_files: int
    removed_solar_profiles: int


def _template_names() -> list[str]:
    """Return the available HTML report templates on disk."""
    if not _TEMPLATES_DIR.exists():
        return []
    return sorted(path.name for path in _TEMPLATES_DIR.glob("*.html"))


def _probe_http_service(
    *,
    key: str,
    label: str,
    url: str,
    params: Optional[dict[str, object]] = None,
    timeout: int = 20,
) -> ExternalServiceProbe:
    """Execute one outbound HTTP probe and capture status + latency."""
    try:
        import requests
    except ImportError as exc:
        return ExternalServiceProbe(
            key=key,
            label=label,
            ok=False,
            detail=(
                "The 'requests' package is required for external service checks. "
                f"Original error: {exc}"
            ),
        )

    started = perf_counter()
    try:
        response = requests.get(url, params=params, timeout=timeout)
        latency_ms = int((perf_counter() - started) * 1000)
        ok = 200 <= response.status_code < 300
        detail = (
            "Reachable"
            if ok
            else f"Service returned HTTP {response.status_code}"
        )
        return ExternalServiceProbe(
            key=key,
            label=label,
            ok=ok,
            status_code=response.status_code,
            latency_ms=latency_ms,
            detail=detail,
        )
    except Exception as exc:
        latency_ms = int((perf_counter() - started) * 1000)
        return ExternalServiceProbe(
            key=key,
            label=label,
            ok=False,
            latency_ms=latency_ms,
            detail=str(exc),
        )


@router.get("/runtime-status", response_model=RuntimeStatusResponse)
async def runtime_status_endpoint():
    """Return local cache counts and report-template availability."""
    templates = _template_names()
    return RuntimeStatusResponse(
        sites_stored=count_sites(),
        weather_cached=count_weather_caches(),
        solar_sites_cached=count_solar_sites(),
        solar_profiles_cached=count_solar_profiles(),
        report_templates_available=len(templates),
        report_template_names=templates,
    )


@router.get("/assumption-overrides", response_model=AssumptionOverridesResponse)
async def assumption_overrides_endpoint():
    """Return the curated override catalog with baseline and effective values."""
    return get_assumption_overrides()


@router.get(
    "/assumption-overrides/presets",
    response_model=AssumptionOverridePresetsResponse,
)
async def assumption_override_presets_endpoint():
    """Return the curated scenario-local preset catalog."""
    return get_assumption_override_presets()


@router.get(
    "/assumption-overrides/history",
    response_model=AssumptionOverrideHistoryResponse,
)
async def assumption_override_history_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return recent controlled-override and preset-run history entries."""
    return get_assumption_override_history(limit=limit)


@router.put("/assumption-overrides", response_model=AssumptionOverridesResponse)
async def update_assumption_overrides_endpoint(request: AssumptionOverridesUpdateRequest):
    """Persist validated assumption overrides for the Settings page."""
    try:
        return save_assumption_override_updates(request.overrides)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/test-external-services", response_model=ExternalServicesResponse)
async def test_external_services_endpoint():
    """Probe the external data services the project depends on."""
    services = [
        _probe_http_service(
            key="open_meteo_archive",
            label="Open-Meteo Archive",
            url=_OPEN_METEO_ARCHIVE_URL,
            params={
                "latitude": 45.4642,
                "longitude": 9.19,
                "start_date": "2023-01-01",
                "end_date": "2023-01-01",
                "hourly": "temperature_2m",
                "timezone": "UTC",
            },
        ),
        _probe_http_service(
            key="open_meteo_geocoding",
            label="Open-Meteo Geocoding",
            url=_OPEN_METEO_GEOCODING_URL,
            params={
                "name": "Milan",
                "count": 1,
                "language": "en",
                "format": "json",
            },
        ),
        _probe_http_service(
            key="pvgis_seriescalc",
            label="PVGIS SeriesCalc",
            url=_PVGIS_SERIESCALC_URL,
            params={
                "lat": 45.4642,
                "lon": 9.19,
                "startyear": 2023,
                "endyear": 2023,
                "pvcalculation": 1,
                "peakpower": 1,
                "pvtechchoice": "crystSi",
                "mountingplace": "free",
                "loss": 14,
                "usehorizon": 1,
                "trackingtype": 0,
                "components": 0,
                "optimalangles": 1,
                "outputformat": "json",
            },
            timeout=30,
        ),
    ]

    return ExternalServicesResponse(
        checked_at_utc=datetime.now(timezone.utc).isoformat(),
        services=services,
    )


@router.post("/clear-cache", response_model=CacheClearResponse)
async def clear_cache_endpoint(request: CacheClearRequest):
    """Clear weather cache, solar cache, or both."""
    removed_weather = 0
    removed_solar = 0

    if request.target in {"weather", "all"}:
        removed_weather = clear_weather_cache()
    if request.target in {"solar", "all"}:
        removed_solar = clear_all_solar_cache()

    if request.target not in {"weather", "solar", "all"}:
        raise HTTPException(status_code=400, detail="Unsupported cache target")

    return CacheClearResponse(
        target=request.target,
        removed_weather_files=removed_weather,
        removed_solar_profiles=removed_solar,
    )
