"""
DC Feasibility Tool v4 - Grid Context API Routes
================================================
Site-level nearby external power-network screening.

Milestone 1 focuses on a stable, cacheable API and a fixture-style
provider boundary. Results are explicitly screening-grade and
mapped-public unless the user later supplies confirmed evidence.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.store import (
    delete_grid_context,
    delete_grid_official_evidence,
    get_grid_context,
    get_grid_official_evidence,
    get_site,
    save_grid_context,
    save_grid_official_evidence,
)
from engine.grid_context import (
    GridContextProviderError,
    build_grid_context_result,
    get_default_grid_context_provider,
    has_grid_official_evidence,
    make_grid_context_cache_key,
)
from engine.models import (
    GridContextRequest,
    GridContextResult,
    GridOfficialEvidence,
    GridOfficialEvidenceResponse,
    Site,
)


router = APIRouter(prefix="/api/grid", tags=["Grid Context"])


class DeleteGridContextResponse(BaseModel):
    """Response from deleting cached grid-context payloads for a site."""

    site_id: str = Field(description="UUID of the site whose grid cache was targeted")
    deleted: bool = Field(description="Whether any cached payloads were removed")


class DeleteGridOfficialEvidenceResponse(BaseModel):
    """Response from deleting saved official-evidence overlay fields for a site."""

    site_id: str = Field(description="UUID of the site whose official evidence was targeted")
    deleted: bool = Field(description="Whether any saved official-evidence payload was removed")


def _load_site_or_404(site_id: str) -> Site:
    """Load a saved site or raise a clean 404 response."""
    result = get_site(site_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")
    _, site = result
    return site


def _load_cached_result(site_id: str, radius_km: float) -> GridContextResult | None:
    """Load and validate one cached grid-context payload."""
    cached_payload = get_grid_context(site_id, make_grid_context_cache_key(radius_km))
    if cached_payload is None:
        return None
    return GridContextResult(**cached_payload)


def _build_and_cache_result(
    *,
    site_id: str,
    site: Site,
    radius_km: float,
    include_score: bool,
) -> GridContextResult:
    """Build a grid-context response and persist it into the cache."""
    try:
        official_evidence_payload = get_grid_official_evidence(site_id)
        official_evidence = (
            GridOfficialEvidence(**official_evidence_payload)
            if official_evidence_payload is not None
            else None
        )
        result = build_grid_context_result(
            site_id=site_id,
            site=site,
            radius_km=radius_km,
            provider=get_default_grid_context_provider(),
            include_score=include_score,
            official_evidence=official_evidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GridContextProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    save_grid_context(
        site_id,
        make_grid_context_cache_key(radius_km),
        result.model_dump(mode="json"),
    )
    return result


@router.post("/context", response_model=GridContextResult)
async def fetch_grid_context_endpoint(request: GridContextRequest):
    """Fetch nearby grid context for a saved site, using cache when available."""
    site = _load_site_or_404(request.site_id)

    if not request.force_refresh:
        cached_result = _load_cached_result(request.site_id, request.radius_km)
        if cached_result is not None:
            if request.include_score and cached_result.score is None:
                return _build_and_cache_result(
                    site_id=request.site_id,
                    site=site,
                    radius_km=request.radius_km,
                    include_score=True,
                )
            return cached_result

    return _build_and_cache_result(
        site_id=request.site_id,
        site=site,
        radius_km=request.radius_km,
        include_score=request.include_score,
    )


@router.get("/context/{site_id}", response_model=GridContextResult)
async def get_grid_context_endpoint(
    site_id: str,
    radius_km: float = Query(
        default=5.0,
        gt=0,
        le=50,
        description="Radius key to look up in kilometers",
    ),
    include_score: bool = Query(
        default=False,
        description="Upgrade a cached score-less payload to include the heuristic score",
    ),
):
    """Return one cached grid-context payload for a site and radius."""
    site = _load_site_or_404(site_id)
    cached_result = _load_cached_result(site_id, radius_km)
    if cached_result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No cached grid context found for site '{site_id}' "
                f"and radius {radius_km:g} km."
            ),
        )

    if include_score and cached_result.score is None:
        return _build_and_cache_result(
            site_id=site_id,
            site=site,
            radius_km=radius_km,
            include_score=True,
        )
    return cached_result


@router.delete("/context/{site_id}", response_model=DeleteGridContextResponse)
async def delete_grid_context_endpoint(site_id: str):
    """Delete all cached grid-context payloads for a site."""
    deleted = delete_grid_context(site_id)
    return DeleteGridContextResponse(site_id=site_id, deleted=deleted)


@router.get("/evidence/{site_id}", response_model=GridOfficialEvidenceResponse)
async def get_grid_official_evidence_endpoint(site_id: str):
    """Return the saved manual official-evidence overlay for one site."""
    _load_site_or_404(site_id)
    payload = get_grid_official_evidence(site_id)
    evidence = GridOfficialEvidence(**payload) if payload is not None else None
    return GridOfficialEvidenceResponse(
        site_id=site_id,
        has_evidence=evidence is not None,
        evidence=evidence,
    )


@router.put("/evidence/{site_id}", response_model=GridOfficialEvidenceResponse)
async def save_grid_official_evidence_endpoint(site_id: str, evidence: GridOfficialEvidence):
    """Save manual official-evidence overlay fields for a site and invalidate grid caches."""
    _load_site_or_404(site_id)
    if not has_grid_official_evidence(evidence):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one official-evidence field or delete the overlay instead.",
        )

    save_grid_official_evidence(site_id, evidence.model_dump(mode="json"))
    delete_grid_context(site_id)
    return GridOfficialEvidenceResponse(
        site_id=site_id,
        has_evidence=True,
        evidence=evidence,
    )


@router.delete("/evidence/{site_id}", response_model=DeleteGridOfficialEvidenceResponse)
async def delete_grid_official_evidence_endpoint(site_id: str):
    """Delete saved manual official-evidence overlay fields for a site."""
    _load_site_or_404(site_id)
    deleted = delete_grid_official_evidence(site_id)
    delete_grid_context(site_id)
    return DeleteGridOfficialEvidenceResponse(site_id=site_id, deleted=deleted)
