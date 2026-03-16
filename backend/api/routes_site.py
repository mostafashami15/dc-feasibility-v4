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
import zipfile

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
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
)


# ─────────────────────────────────────────────────────────────
# Router setup
# ─────────────────────────────────────────────────────────────
# prefix="/api/sites" means all routes here start with /api/sites
# tags=["Sites"] groups these endpoints together in the auto-generated
# API docs at http://localhost:8000/docs

router = APIRouter(prefix="/api", tags=["Sites"])


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
    return SiteResponse(
        id=site_id,
        site=saved_site,
        has_weather=False,  # New site never has cached weather
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
        site_responses.append(SiteResponse(
            id=entry["id"],
            site=site,
            has_weather=has_weather(entry["id"]),
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
    return SiteResponse(
        id=sid,
        site=site,
        has_weather=has_weather(sid),
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
    return SiteResponse(
        id=site_id,
        site=updated,
        has_weather=has_weather(site_id),
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

    try:
        from engine.weather import parse_kml_string
        content = await file.read()

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
