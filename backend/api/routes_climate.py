"""
DC Feasibility Tool v4 — Climate API Routes
=============================================
Weather data fetching, climate analysis, and delta projection.

Serves: Page 2 (Climate & Weather) in the Architecture Agreement Section 6.

Endpoints:
    POST /api/climate/fetch-weather     — Fetch 5-year weather from Open-Meteo
    GET  /api/climate/weather/{site_id} — Get cached weather for a site
    POST /api/climate/analyse           — Run climate analysis
    POST /api/climate/analyse-site      — Analyse using a site's cached weather

Flow (how the frontend uses these):
    1. User opens Climate & Weather page
    2. For each site without weather: frontend calls POST /fetch-weather
    3. Weather is cached server-side (linked to site_id)
    4. Frontend calls POST /analyse-site to get climate metrics
    5. User adjusts delta slider → frontend calls /analyse-site again

Engine functions used:
    engine.weather.build_representative_year — Fetch + average 5 years
    engine.climate.analyse_climate           — Full climate analysis

Reference: Architecture Agreement v2.0, Sections 3.10, 6 (Page 2)
"""

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from engine.climate import analyse_climate
from engine.weather import parse_manual_weather_csv
from api.store import clear_weather_cache, get_site, get_weather, save_weather, has_weather


# ─────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/climate", tags=["Climate"])


# ─────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────

class FetchWeatherRequest(BaseModel):
    """Request to fetch weather data for a site.

    The site must have coordinates (latitude/longitude). If they're
    missing, the frontend should prompt the user to set them first
    (via geocoding or manual entry on the Site Manager page).
    """
    site_id: str = Field(description="UUID of the site to fetch weather for")
    start_year: int = Field(
        default=2019, ge=2000, le=2025,
        description=(
            "First year of weather data. Default 2019. "
            "Source: Architecture Agreement Section 3.10 — "
            "5-year average (2019–2023) is the default strategy."
        ),
    )
    end_year: int = Field(
        default=2023, ge=2000, le=2025,
        description="Last year of weather data. Default 2023."
    )
    force_refresh: bool = Field(
        default=False,
        description="Re-fetch even if cached data exists"
    )


class WeatherStatusResponse(BaseModel):
    """Weather cache status for a site."""
    site_id: str
    has_weather: bool
    source: Optional[str] = None
    source_type: Optional[str] = None
    hours: Optional[int] = None
    years_averaged: Optional[list[int]] = None
    has_humidity: Optional[bool] = None
    original_filename: Optional[str] = None
    uploaded_at_utc: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class AnalyseRequest(BaseModel):
    """Request for climate analysis using raw temperature data.

    Use this when you have temperature data from a custom source
    (e.g., manual upload) rather than the Open-Meteo cache.
    """
    temperatures: list[float] = Field(
        min_length=1,
        description="Hourly dry-bulb temperatures in °C (typically 8,760 values)"
    )
    humidities: Optional[list[float]] = Field(
        default=None,
        description="Hourly relative humidity in % (0–100). Required for water-cooled."
    )
    cooling_types: Optional[list[str]] = Field(
        default=None,
        description=(
            "Cooling types to analyse for free cooling. "
            "If None, analyses all free-cooling-eligible types."
        ),
    )
    deltas: Optional[list[float]] = Field(
        default=None,
        description=(
            "Temperature deltas for climate projection (°C). "
            "Default: [0.5, 1.0, 1.5, 2.0]. "
            "Source: CIBSE TM49 delta approach, IPCC AR6 SSP2-4.5."
        ),
    )


class AnalyseSiteRequest(BaseModel):
    """Request for climate analysis using a site's cached weather.

    This is the typical flow: fetch weather first, then analyse.
    The frontend uses this for the Climate & Weather page.
    """
    site_id: str = Field(description="UUID of the site")
    cooling_types: Optional[list[str]] = Field(
        default=None,
        description="Cooling types to analyse. None = all free-cooling-eligible."
    )
    deltas: Optional[list[float]] = Field(
        default=None,
        description="Temperature deltas for projection. Default: [0.5, 1.0, 1.5, 2.0]."
    )


class DeleteWeatherResponse(BaseModel):
    site_id: str
    deleted: bool


def _infer_weather_source_type(weather: dict) -> str:
    """Backfill source metadata for legacy caches created before source_type existed."""
    source_type = weather.get("source_type")
    if isinstance(source_type, str) and source_type.strip():
        return source_type

    if weather.get("original_filename") or weather.get("uploaded_at_utc"):
        return "manual_upload"

    source = str(weather.get("source", "")).lower()
    if "manual" in source:
        return "manual_upload"
    if weather.get("years_averaged"):
        return "open_meteo_archive"
    return "cached"


def _build_weather_status_response(site_id: str, weather: dict) -> WeatherStatusResponse:
    """Return a consistent weather-cache status payload for fetch/upload/status routes."""
    temperatures = weather.get("temperatures") or []
    humidities = weather.get("humidities")
    return WeatherStatusResponse(
        site_id=site_id,
        has_weather=True,
        source=weather.get("source", ""),
        source_type=_infer_weather_source_type(weather),
        hours=weather.get("hours", len(temperatures)),
        years_averaged=weather.get("years_averaged", []),
        has_humidity=humidities is not None,
        original_filename=weather.get("original_filename"),
        uploaded_at_utc=weather.get("uploaded_at_utc"),
        latitude=weather.get("latitude"),
        longitude=weather.get("longitude"),
    )


# ─────────────────────────────────────────────────────────────
# Fetch Weather
# ─────────────────────────────────────────────────────────────

@router.post("/fetch-weather", response_model=WeatherStatusResponse)
async def fetch_weather_endpoint(request: FetchWeatherRequest):
    """Fetch 5-year weather data from Open-Meteo and cache it.

    This calls the Open-Meteo Archive API (free, no API key) to
    download hourly temperature and humidity data for the specified
    years, then averages them hour-by-hour to produce one
    representative 8,760-row year.

    The data is cached in backend/data/weather/{site_id}.json so
    subsequent scenario runs don't need to re-fetch.

    Engine function: engine.weather.build_representative_year()

    Typical timing: 3–8 seconds depending on network speed
    (fetches 5 years × 8,760 hours × 2 variables).

    Source: Open-Meteo Archive API (ERA5 reanalysis data)
    Reference: Architecture Agreement Section 3.10
    """
    # ── Load site ──
    result = get_site(request.site_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Site '{request.site_id}' not found"
        )
    _, site = result

    # ── Validate coordinates ──
    if site.latitude is None or site.longitude is None:
        raise HTTPException(
            status_code=400,
            detail="Site has no coordinates. Set latitude and longitude "
                   "on the Site Manager page before fetching weather."
        )

    # ── Check cache ──
    if not request.force_refresh and has_weather(request.site_id):
        existing = get_weather(request.site_id)
        return _build_weather_status_response(request.site_id, existing)

    # ── Fetch from Open-Meteo ──
    try:
        from engine.weather import build_representative_year

        weather_data = build_representative_year(
            latitude=site.latitude,
            longitude=site.longitude,
            start_year=request.start_year,
            end_year=request.end_year,
        )
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Weather fetch requires the 'requests' library. "
                   "Install with: pip install requests"
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Weather data fetch failed: {str(e)}"
        )

    # ── Cache the result ──
    # Convert dataclass to dict for JSON storage
    weather_dict = asdict(weather_data)
    save_weather(request.site_id, weather_dict)

    return _build_weather_status_response(request.site_id, weather_dict)


@router.post("/upload-weather", response_model=WeatherStatusResponse)
async def upload_weather_endpoint(
    site_id: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload a manual hourly weather CSV and save it into the per-site cache."""
    result = get_site(site_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")
    _, site = result

    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(
            status_code=400,
            detail="The uploaded weather file must include a filename.",
        )
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Manual weather upload currently supports CSV files only.",
        )

    try:
        payload = await file.read()
    finally:
        await file.close()

    try:
        csv_text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Manual weather CSV must be UTF-8 encoded.",
        ) from exc

    try:
        weather_data = parse_manual_weather_csv(
            csv_text,
            latitude=site.latitude,
            longitude=site.longitude,
            source_name=filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    weather_dict = asdict(weather_data)
    save_weather(site_id, weather_dict)
    return _build_weather_status_response(site_id, weather_dict)


# ─────────────────────────────────────────────────────────────
# Get Cached Weather
# ─────────────────────────────────────────────────────────────

@router.get("/weather/{site_id}")
async def get_weather_endpoint(
    site_id: str,
    include_hourly: bool = Query(
        default=False,
        description=(
            "Include the full hourly temperature/humidity arrays. "
            "Set to False for a quick status check (saves bandwidth)."
        ),
    ),
):
    """Get cached weather data for a site.

    By default, returns metadata only (source, hours, years) without
    the full 8,760-element temperature array. Set include_hourly=True
    to get the raw data (needed for custom analysis or charts).

    Returns 404 if no weather is cached for this site.
    """
    weather = get_weather(site_id)
    if weather is None:
        raise HTTPException(
            status_code=404,
            detail=f"No weather data cached for site '{site_id}'. "
                   f"Call POST /api/climate/fetch-weather first."
        )

    if include_hourly:
        payload = dict(weather)
        payload["source_type"] = _infer_weather_source_type(payload)
        payload["has_humidity"] = payload.get("humidities") is not None
        return payload
    else:
        return _build_weather_status_response(site_id, weather)


@router.delete("/weather/{site_id}", response_model=DeleteWeatherResponse)
async def delete_weather_endpoint(site_id: str):
    """Delete the cached weather payload for one site."""
    removed = clear_weather_cache(site_id)
    if removed == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No weather data cached for site '{site_id}'.",
        )
    return DeleteWeatherResponse(site_id=site_id, deleted=True)


# ─────────────────────────────────────────────────────────────
# Climate Analysis (raw data)
# ─────────────────────────────────────────────────────────────

@router.post("/analyse")
async def analyse_endpoint(request: AnalyseRequest):
    """Run climate analysis on raw temperature data.

    Use this when you have temperature data from a custom source
    (e.g., uploaded CSV) rather than the Open-Meteo cache.

    Engine function: engine.climate.analyse_climate()

    Returns:
        - Temperature statistics (mean, min, max, P1, P99, std dev)
        - Monthly breakdown (if 8,760 hours)
        - Free cooling analysis per cooling type
        - Delta projections (impact of +0.5°C, +1.0°C, etc.)
    """
    if request.humidities is not None:
        if len(request.humidities) != len(request.temperatures):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"temperatures ({len(request.temperatures)}) and "
                    f"humidities ({len(request.humidities)}) must have "
                    f"the same length"
                ),
            )

    try:
        result = analyse_climate(
            temperatures=request.temperatures,
            cooling_types=request.cooling_types,
            humidities=request.humidities,
            deltas=request.deltas,
        )
        return _serialize_climate_result(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────
# Climate Analysis (from site's cached weather)
# ─────────────────────────────────────────────────────────────

@router.post("/analyse-site")
async def analyse_site_endpoint(request: AnalyseSiteRequest):
    """Run climate analysis using a site's cached weather data.

    This is the typical flow for the Climate & Weather page:
        1. User fetches weather (POST /fetch-weather)
        2. User opens Climate page → frontend calls this endpoint
        3. Frontend renders temperature charts, free cooling analysis,
           suitability ratings, and delta projections

    Returns 404 if no weather data is cached for the site.
    """
    weather = get_weather(request.site_id)
    if weather is None:
        raise HTTPException(
            status_code=404,
            detail=f"No weather data cached for site '{request.site_id}'. "
                   f"Call POST /api/climate/fetch-weather first."
        )

    temperatures = weather["temperatures"]
    humidities = weather.get("humidities")

    try:
        result = analyse_climate(
            temperatures=temperatures,
            cooling_types=request.cooling_types,
            humidities=humidities,
            deltas=request.deltas,
        )
        return _serialize_climate_result(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────
# Serialization Helper
# ─────────────────────────────────────────────────────────────
# The climate module uses dataclasses (not Pydantic), so we
# need to manually convert to dicts for JSON serialization.
# This is intentional — the engine uses dataclasses to stay
# lightweight and framework-independent.

def _serialize_climate_result(result) -> dict:
    """Convert ClimateAnalysisResult dataclasses to a JSON-safe dict.

    The engine's climate module uses Python dataclasses rather than
    Pydantic models. This keeps the engine framework-independent
    (Architecture Agreement Principle #1: engine has ZERO UI deps).
    The API layer handles the serialization.
    """
    temp_stats = asdict(result.temperature_stats)
    monthly = asdict(result.monthly_stats) if result.monthly_stats else None

    free_cooling = [asdict(fc) for fc in result.free_cooling]

    # Delta results: convert float keys to strings for JSON
    # (JSON keys must be strings)
    delta_results = {}
    for delta, fc_list in result.delta_results.items():
        delta_results[str(delta)] = [asdict(fc) for fc in fc_list]

    return {
        "temperature_stats": temp_stats,
        "monthly_stats": monthly,
        "free_cooling": free_cooling,
        "delta_results": delta_results,
    }
