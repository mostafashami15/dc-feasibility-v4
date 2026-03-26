"""
DC Feasibility Tool v4 — Site API Routes
==========================================
CRUD operations for candidate data center sites, plus KML upload,
geocoding, and geometry preview.

Serves: Page 1 (Site Manager) in the Architecture Agreement Section 6.

Endpoints:
    POST   /api/sites                      — Create a new site
    GET    /api/sites                      — List all sites
    GET    /api/sites/{site_id}            — Get one site by ID
    PUT    /api/sites/{site_id}            — Update a site
    DELETE /api/sites/{site_id}            — Delete a site
    POST   /api/sites/upload-kml           — Upload KML → extract coordinates
    GET    /api/geocode                    — City name → coordinates
    GET    /api/sites/{site_id}/space-preview — Quick geometry preview

Design:
    Every endpoint returns a consistent JSON shape. Errors return
    FastAPI's standard HTTPException format ({"detail": "message"}).
    All inputs are validated by Pydantic before reaching the engine.

Engine functions used:
    engine.space.compute_space         — Geometry calculation
    engine.weather.parse_kml_string    — KML file parsing
    engine.weather.geocode             — City → coordinates
    engine.assumptions.LOAD_PROFILES   — For compatible cooling types
    engine.assumptions.COOLING_PROFILES — For whitespace adjustment factors

Reference: Architecture Agreement v2.0, Sections 6 (Page 1), 8 (Phase 4)
"""

from typing import Optional
import io
import logging
import zipfile

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field

from engine.models import Site, CoolingType, SpaceResult
from engine.space import compute_space
from engine.assumptions import LOAD_PROFILES, COOLING_PROFILES
from api.store import (
    create_site,
    get_site,
    list_sites,
    update_site,
    delete_site,
    has_weather,
    has_any_solar_profile,
    has_solar_profile,
    save_solar_profile,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Router setup
# ─────────────────────────────────────────────────────────────
# prefix="/api/sites" means all routes here start with /api/sites
# tags=["Sites"] groups these endpoints together in the auto-generated
# API docs at http://localhost:8000/docs

router = APIRouter(prefix="/api", tags=["Sites"])


# ── In-memory PVGIS fetch status tracker ──
# Tracks background PVGIS fetch status per site_id.
# Possible values: "loading", "cached", "error", "none"
_pvgis_fetch_status: dict[str, str] = {}


def _get_solar_status(site_id: str) -> tuple[bool, str]:
    """Return (has_solar, solar_fetch_status) for a site."""
    if has_any_solar_profile(site_id):
        return True, "cached"
    status = _pvgis_fetch_status.get(site_id, "none")
    return False, status


# Default PVGIS parameters — used as fallback when site has no overrides
_DEFAULT_PVGIS_KEY_PARAMS = dict(
    start_year=2019,
    end_year=2023,
    pv_technology="crystSi",
    mounting_place="free",
    system_loss_pct=14.0,
    use_horizon=True,
    optimal_angles=True,
    surface_tilt_deg=None,
    surface_azimuth_deg=None,
)


def _get_pvgis_params(site: Site) -> dict:
    """Return PVGIS key params from site overrides with defaults as fallback."""
    return dict(
        start_year=site.pvgis_start_year if site.pvgis_start_year is not None else 2019,
        end_year=site.pvgis_end_year if site.pvgis_end_year is not None else 2023,
        pv_technology=site.pvgis_technology or "crystSi",
        mounting_place=site.pvgis_mounting_place or "free",
        system_loss_pct=site.pvgis_system_loss_pct if site.pvgis_system_loss_pct is not None else 14.0,
        use_horizon=site.pvgis_use_horizon if site.pvgis_use_horizon is not None else True,
        optimal_angles=site.pvgis_optimal_angles if site.pvgis_optimal_angles is not None else True,
        surface_tilt_deg=site.pvgis_surface_tilt_deg,
        surface_azimuth_deg=site.pvgis_surface_azimuth_deg,
    )


def _pvgis_background_fetch(site_id: str, latitude: float, longitude: float, pvgis_params: dict | None = None) -> None:
    """Background task: fetch PVGIS normalized profile and cache it."""
    try:
        from engine.solar import build_representative_pvgis_profile, make_pvgis_profile_key
        from dataclasses import asdict

        params = pvgis_params or _DEFAULT_PVGIS_KEY_PARAMS

        profile_key = make_pvgis_profile_key(
            site_id=site_id,
            latitude=latitude,
            longitude=longitude,
            **params,
        )

        # Skip if already cached
        if has_solar_profile(site_id, profile_key):
            _pvgis_fetch_status[site_id] = "cached"
            return

        _pvgis_fetch_status[site_id] = "loading"

        profile = build_representative_pvgis_profile(
            latitude=latitude,
            longitude=longitude,
            site_id=site_id,
            **params,
        )

        save_solar_profile(site_id, profile_key, asdict(profile))
        _pvgis_fetch_status[site_id] = "cached"
        logger.info("PVGIS auto-fetch complete for site %s (key=%s)", site_id, profile_key)

    except Exception as e:
        _pvgis_fetch_status[site_id] = "error"
        logger.warning("PVGIS auto-fetch failed for site %s: %s", site_id, e)


# BackgroundTasks instance — set by endpoint handlers
_background_tasks: BackgroundTasks | None = None


def _maybe_trigger_pvgis_background(site_id: str, site: Site) -> None:
    """Trigger PVGIS background fetch if site has valid coordinates and no cached profile."""
    if site.latitude is None or site.longitude is None:
        return
    if has_any_solar_profile(site_id):
        return
    if _pvgis_fetch_status.get(site_id) == "loading":
        return  # Already fetching

    _pvgis_fetch_status[site_id] = "loading"
    pvgis_params = _get_pvgis_params(site)

    import threading
    thread = threading.Thread(
        target=_pvgis_background_fetch,
        args=(site_id, site.latitude, site.longitude, pvgis_params),
        daemon=True,
    )
    thread.start()


# ─────────────────────────────────────────────────────────────
# Response Models
# ─────────────────────────────────────────────────────────────
# These Pydantic models define the exact JSON shape the frontend
# receives. This is important for TypeScript — the frontend team
# can generate types directly from these models.

class SiteResponse(BaseModel):
    """Response for a single site — includes the server-assigned ID."""
    id: str = Field(description="Server-assigned UUID for this site")
    site: Site = Field(description="Full site data")
    has_weather: bool = Field(
        default=False,
        description="Whether cached weather data exists for this site"
    )
    has_solar: bool = Field(
        default=False,
        description="Whether a cached PVGIS solar profile exists for this site"
    )
    solar_fetch_status: str = Field(
        default="none",
        description="PVGIS fetch status: none, loading, cached, error"
    )


class SiteListResponse(BaseModel):
    """Response for listing all sites."""
    count: int = Field(description="Number of sites")
    sites: list[SiteResponse] = Field(description="All saved sites")


class SpacePreviewResponse(BaseModel):
    """Quick geometry preview — returned when the user edits site parameters.

    This lets the Site Manager page show a live preview of rack capacity
    as the user adjusts land area, floors, whitespace ratio, etc.
    """
    space: SpaceResult = Field(description="Geometry calculation result")
    cooling_type_used: Optional[str] = Field(
        default=None,
        description="Cooling type used for whitespace adjustment (None = no adjustment)"
    )


class KMLUploadResponse(BaseModel):
    """Response from KML file upload — extracted coordinates."""
    coordinates: list[dict] = Field(
        description=(
            "List of extracted placemarks, each with "
            "'latitude', 'longitude', 'name', 'description', "
            "'geometry_type', and 'geometry_coordinates'"
        )
    )
    count: int = Field(description="Number of placemarks found")


class GeocodingResponse(BaseModel):
    """Response from geocoding — city name → coordinates."""
    results: list[dict] = Field(
        description="Geocoding results with lat, lon, name, country, admin1"
    )
    count: int = Field(description="Number of results")


class ReferenceDataResponse(BaseModel):
    """Static reference data for dropdowns and form fields.

    The frontend calls this once on load to populate dropdown options
    for load types, cooling types, etc. This avoids hardcoding these
    values in the React code — if we add a new cooling type in the
    engine, the frontend picks it up automatically.
    """
    load_profiles: dict = Field(description="All load types with density ranges")
    cooling_profiles: dict = Field(
        description="All cooling types with PUE defaults and properties"
    )


# ─────────────────────────────────────────────────────────────
# CRUD Endpoints
# ─────────────────────────────────────────────────────────────

@router.post("/sites", response_model=SiteResponse, status_code=201)
async def create_site_endpoint(site: Site):
    """Create a new candidate site.

    The frontend sends a Site object (JSON body). Pydantic validates
    all fields automatically — if land_area_m2 is negative, you get
    a 422 error before the data ever reaches the engine.

    Returns the site with its server-assigned UUID. The frontend uses
    this UUID for all subsequent operations on this site.

    Example request body:
        {
            "name": "Milan Site A",
            "land_area_m2": 25000,
            "latitude": 45.4642,
            "longitude": 9.19,
            "available_power_mw": 20.0,
            "power_confirmed": true
        }
    """
    # Check for duplicate names
    existing = list_sites()
    for entry in existing:
        if entry["site"]["name"] == site.name:
            raise HTTPException(
                status_code=409,
                detail=f"A site named '{site.name}' already exists. "
                       f"Site names must be unique."
            )

    site_id, saved_site = create_site(site)

    # Trigger background PVGIS fetch if site has valid coordinates
    _maybe_trigger_pvgis_background(site_id, saved_site)

    return SiteResponse(
        id=site_id,
        site=saved_site,
        has_weather=False,
        has_solar=False,
        solar_fetch_status=_pvgis_fetch_status.get(site_id, "none"),
    )


@router.get("/sites", response_model=SiteListResponse)
async def list_sites_endpoint():
    """List all saved sites.

    Returns sites sorted alphabetically by name. Each site includes
    a 'has_weather' flag so the Site Manager page can show weather
    fetch status icons (green check or grey clock).

    The frontend calls this when the Site Manager page loads.
    """
    entries = list_sites()
    site_responses = []
    for entry in entries:
        site = Site(**entry["site"])
        sid = entry["id"]
        hs, ss = _get_solar_status(sid)
        site_responses.append(SiteResponse(
            id=sid,
            site=site,
            has_weather=has_weather(sid),
            has_solar=hs,
            solar_fetch_status=ss,
        ))
    return SiteListResponse(
        count=len(site_responses),
        sites=site_responses,
    )


@router.get("/sites/{site_id}", response_model=SiteResponse)
async def get_site_endpoint(site_id: str):
    """Get a single site by its ID.

    Returns 404 if the site doesn't exist.

    The frontend calls this when the user clicks on a site in the
    list to view or edit its details.
    """
    result = get_site(site_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")
    sid, site = result
    hs, ss = _get_solar_status(sid)
    return SiteResponse(
        id=sid,
        site=site,
        has_weather=has_weather(sid),
        has_solar=hs,
        solar_fetch_status=ss,
    )


@router.put("/sites/{site_id}", response_model=SiteResponse)
async def update_site_endpoint(site_id: str, site: Site):
    """Update an existing site.

    Replaces all site data with the new values. The frontend sends
    the complete Site object — partial updates are not supported
    (simpler to implement and reason about).

    Returns 404 if the site doesn't exist.
    """
    # Check for duplicate names (excluding the site being updated)
    existing = list_sites()
    for entry in existing:
        if entry["id"] != site_id and entry["site"]["name"] == site.name:
            raise HTTPException(
                status_code=409,
                detail=f"A site named '{site.name}' already exists. "
                       f"Site names must be unique."
            )

    updated = update_site(site_id, site)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")

    # Trigger background PVGIS fetch if coordinates changed/added
    _maybe_trigger_pvgis_background(site_id, updated)

    hs, ss = _get_solar_status(site_id)
    return SiteResponse(
        id=site_id,
        site=updated,
        has_weather=has_weather(site_id),
        has_solar=hs,
        solar_fetch_status=ss,
    )


@router.delete("/sites/{site_id}")
async def delete_site_endpoint(site_id: str):
    """Delete a site and its cached weather data.

    Returns 404 if the site doesn't exist.
    The frontend removes the site from its local state after this succeeds.
    """
    deleted = delete_site(site_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")
    return {"status": "deleted", "id": site_id}


# ─────────────────────────────────────────────────────────────
# KML Upload
# ─────────────────────────────────────────────────────────────

@router.post("/sites/upload-kml", response_model=KMLUploadResponse)
async def upload_kml_endpoint(file: UploadFile = File(...)):
    """Upload a KML or KMZ file and extract coordinates.

    The frontend uses this when the user drags a KML file onto the
    Site Manager page or clicks an upload button. The extracted
    coordinates are returned so the user can select which placemark
    to use for the site location.

    Supports:
        - .kml files (plain XML)
        - .kmz files (ZIP archive containing one or more .kml files)

    Engine function: engine.weather.parse_kml_string()

    Returns:
        List of placemarks with coordinates, name, and description.
    """
    # Validate file extension
    if file.filename and not file.filename.lower().endswith((".kml", ".kmz")):
        raise HTTPException(
            status_code=400,
            detail="Only .kml and .kmz files are supported"
        )

    # File size limit: 10 MB max to prevent resource exhaustion
    KML_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

    try:
        from engine.weather import parse_kml_string
        content = await file.read()

        if len(content) > KML_MAX_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). Maximum allowed: 10 MB."
            )

        if file.filename and file.filename.lower().endswith(".kmz"):
            with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                kml_names = [name for name in zf.namelist() if name.lower().endswith(".kml")]
                if not kml_names:
                    raise HTTPException(
                        status_code=400,
                        detail="No .kml file found inside the KMZ archive."
                    )
                kml_string = zf.read(kml_names[0]).decode("utf-8")
        else:
            kml_string = content.decode("utf-8")

        coordinates = parse_kml_string(kml_string)
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Could not decode the uploaded KML/KMZ content as UTF-8."
        )
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400,
            detail="Invalid KMZ archive."
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse KML file: {str(e)}"
        )

    results = [
        {
            "latitude": c.latitude,
            "longitude": c.longitude,
            "name": c.name,
            "description": c.description,
            "geometry_type": c.geometry_type,
            "geometry_coordinates": [
                [lat, lon] for lon, lat in c.coordinates
            ],
        }
        for c in coordinates
    ]

    return KMLUploadResponse(
        coordinates=results,
        count=len(results),
    )


# ─────────────────────────────────────────────────────────────
# Geocoding
# ─────────────────────────────────────────────────────────────

@router.get("/geocode", response_model=GeocodingResponse)
async def geocode_endpoint(
    q: str = Query(
        ...,
        min_length=2,
        description="City name, address, or place (e.g., 'Milan, Italy')"
    ),
):
    """Convert a city name or address to coordinates.

    The frontend calls this when the user types a location in the
    search box and presses Enter (or clicks search). Results are
    displayed as a dropdown — the user clicks one to set the site
    coordinates.

    Uses the Open-Meteo Geocoding API (free, no API key).
    Engine function: engine.weather.geocode()

    Returns up to 5 results ranked by relevance.
    """
    try:
        from engine.weather import geocode
        results = geocode(q)
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Geocoding requires the 'requests' library. "
                   "Install with: pip install requests"
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Geocoding service error: {str(e)}"
        )

    return GeocodingResponse(
        results=[
            {
                "latitude": r.latitude,
                "longitude": r.longitude,
                "name": r.name,
                "country": r.country,
                "admin1": r.admin1,
            }
            for r in results
        ],
        count=len(results),
    )


# ─────────────────────────────────────────────────────────────
# Space Preview
# ─────────────────────────────────────────────────────────────

@router.get(
    "/sites/{site_id}/space-preview",
    response_model=SpacePreviewResponse,
)
async def space_preview_endpoint(
    site_id: str,
    cooling_type: Optional[str] = Query(
        default=None,
        description=(
            "Cooling type for whitespace adjustment factor. "
            "Pass the CoolingType enum value string. "
            "If omitted, no cooling adjustment is applied (factor=1.0)."
        ),
    ),
):
    """Quick geometry preview for a saved site.

    This is called by the Site Manager page to show a live preview
    of rack capacity. As the user changes land area, floors, or
    whitespace ratio, the frontend saves the site (PUT) and then
    calls this endpoint to get the updated geometry.

    Engine function: engine.space.compute_space()

    The cooling_type parameter is optional. When provided, it applies
    the whitespace adjustment factor for that cooling type (e.g.,
    immersion cooling reduces effective racks by 15%). When omitted,
    no adjustment is applied — useful for a "maximum possible" preview.

    Returns:
        SpaceResult with all derived geometry values and rack counts.
    """
    result = get_site(site_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")
    _, site = result

    # Validate cooling type if provided
    ct = None
    if cooling_type is not None:
        try:
            ct = CoolingType(cooling_type)
        except ValueError:
            valid_types = [c.value for c in CoolingType]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cooling_type '{cooling_type}'. "
                       f"Valid options: {valid_types}"
            )

    space = compute_space(site, cooling_type=ct)

    return SpacePreviewResponse(
        space=space,
        cooling_type_used=cooling_type,
    )


# ─────────────────────────────────────────────────────────────
# Solar Status
# ─────────────────────────────────────────────────────────────

@router.get("/sites/{site_id}/solar-status")
async def solar_status_endpoint(site_id: str):
    """Check PVGIS fetch status for a site.

    The frontend polls this after site creation to show loading/cached/error.
    """
    result = get_site(site_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")
    hs, ss = _get_solar_status(site_id)
    return {"site_id": site_id, "has_solar": hs, "solar_fetch_status": ss}


# ─────────────────────────────────────────────────────────────
# Reference Data
# ─────────────────────────────────────────────────────────────

@router.get("/reference-data", response_model=ReferenceDataResponse)
async def reference_data_endpoint():
    """Get static reference data for form dropdowns.

    The frontend calls this once when the app loads. It populates
    all dropdown menus:
        - Load types (with density ranges and compatible cooling)
        - Cooling types (with PUE defaults and whitespace factors)

    This avoids hardcoding values in the React code. If we add a
    new cooling type or update densities in assumptions.py, the
    frontend picks it up automatically on next load.

    Source: engine.assumptions.LOAD_PROFILES, COOLING_PROFILES
    """
    return ReferenceDataResponse(
        load_profiles=LOAD_PROFILES,
        cooling_profiles={
            name: {
                "pue_typical": profile["pue_typical"],
                "free_cooling_eligible": profile.get("free_cooling_eligible", False),
                "whitespace_adjustment_factor": profile["whitespace_adjustment_factor"],
                "max_rack_density_kw": profile["max_rack_density_kw"],
                "description": profile.get("description", ""),
            }
            for name, profile in COOLING_PROFILES.items()
        },
    )
