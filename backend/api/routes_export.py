"""
DC Feasibility Tool v4 - Export API Routes
==========================================
Scoped report export endpoints for HTML, PDF, and Excel outputs.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.store import get_site
from engine.models import ScenarioResult, Site
from export.excel_export import build_excel_bytes
from export.html_report import render_report_html
from export.report_data import validate_report_selection
from export.terrain_map import generate_terrain_image

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/export", tags=["Export"])


class ReportConfig(BaseModel):
    """Configuration for scoped report generation."""

    report_type: str = Field(
        default="executive",
        description="'executive' (2-3 pages) or 'detailed' (8-15 pages)",
    )
    studied_site_ids: list[str] = Field(
        description="Explicitly selected studied sites to include in the report"
    )
    primary_result_keys: dict[str, str] = Field(
        default_factory=dict,
        description="Primary selected scenario/result key for each studied site",
    )
    layout_mode: Literal["presentation_16_9", "report_a4_portrait"] = Field(
        default="presentation_16_9",
        description="Report layout mode for HTML/PDF rendering",
    )
    scenario_results: Optional[list[dict]] = Field(
        default=None,
        description="Pre-computed scenario results to include",
    )
    load_mix_results: Optional[dict[str, dict]] = Field(
        default=None,
        description=(
            "Optional request-provided load-mix analyses keyed by site ID. "
            "Ignored when absent or when the payload does not match the selected primary result."
        ),
    )
    green_energy_results: Optional[dict[str, dict]] = Field(
        default=None,
        description=(
            "Optional request-provided green-energy analyses keyed by site ID. "
            "Ignored when absent or when the payload does not match the selected primary result."
        ),
    )
    include_all_scenarios: bool = Field(
        default=True,
        description="Include all scenario results per site for comparison. "
        "When False, only the selected primary result is included.",
    )
    primary_color: str = Field(default="#1a365d", description="Primary brand color (hex)")
    secondary_color: str = Field(default="#2b6cb0", description="Secondary brand color (hex)")
    logo_url: Optional[str] = Field(default=None, description="URL or path to company logo")
    font_family: str = Field(default="Inter, sans-serif", description="Report font family")


# ── Private helpers ──────────────────────────────────────────────────────────

def _normalize_results(raw_results: Optional[list[dict]]) -> list[ScenarioResult]:
    if not raw_results:
        return []
    return [ScenarioResult(**item) for item in raw_results]


def _load_sites(site_ids: list[str]) -> list[tuple[str, Site]]:
    site_entries = []
    for site_id in site_ids:
        loaded = get_site(site_id)
        if loaded is None:
            raise HTTPException(status_code=404, detail=f"Site not found: {site_id}")
        site_entries.append(loaded)
    return site_entries


def _get_site_names(site_ids: list[str]) -> list[str]:
    """Extract site names for filename generation (best-effort, no errors)."""
    names: list[str] = []
    for sid in site_ids:
        try:
            loaded = get_site(sid)
            if loaded:
                _, site = loaded
                names.append(site.name)
        except Exception:
            pass
    return names


def _make_filename(report_type: str, extension: str, site_names: list[str] | None = None) -> str:
    safe = report_type.lower().replace(" ", "-")
    if site_names:
        import re
        parts = [re.sub(r"[^a-zA-Z0-9]+", "-", n).strip("-") for n in site_names]
        site_slug = "-".join(p for p in parts if p)
        return f"{site_slug}-dc-feasibility-{safe}-report.{extension}"
    return f"dc-feasibility-{safe}-report.{extension}"


def _prepare_inputs(
    config: ReportConfig,
) -> tuple[list[tuple[str, Site]], list[ScenarioResult]]:
    if not config.studied_site_ids:
        raise HTTPException(
            status_code=400,
            detail="Select at least one studied site before exporting a report.",
        )
    scenario_results = _normalize_results(config.scenario_results)
    try:
        validate_report_selection(
            studied_site_ids=config.studied_site_ids,
            primary_result_keys=config.primary_result_keys,
            scenario_results=scenario_results,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    site_entries = _load_sites(config.studied_site_ids)
    return site_entries, scenario_results


def _build_html(config: ReportConfig) -> str:
    """Shared HTML rendering used by both HTML preview and PDF conversion."""
    site_entries, scenario_results = _prepare_inputs(config)
    return render_report_html(
        report_type=config.report_type,
        primary_color=config.primary_color,
        secondary_color=config.secondary_color,
        font_family=config.font_family,
        logo_url=config.logo_url,
        site_entries=site_entries,
        scenario_results=scenario_results,
        layout_mode=config.layout_mode,
        studied_site_ids=config.studied_site_ids,
        primary_result_keys=config.primary_result_keys,
        load_mix_results=config.load_mix_results,
        green_energy_results=config.green_energy_results,
        include_all_scenarios=config.include_all_scenarios,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/html", response_class=HTMLResponse)
async def export_html_endpoint(config: ReportConfig):
    """Generate an HTML report preview."""
    try:
        return HTMLResponse(content=_build_html(config))
    except HTTPException:
        raise
    except Exception as exc:
        import logging
        import traceback
        logging.getLogger(__name__).exception("HTML export failed")
        raise HTTPException(status_code=500, detail=traceback.format_exc()) from exc


def _ensure_weasyprint_libs():
    """Ensure Homebrew libraries are discoverable for WeasyPrint on macOS."""
    import os, sys
    if sys.platform == "darwin":
        brew_lib = "/opt/homebrew/lib"
        fallback = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        if brew_lib not in fallback:
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
                f"{brew_lib}:{fallback}" if fallback else brew_lib
            )


@router.post("/pdf")
async def export_pdf_endpoint(config: ReportConfig):
    """Generate a PDF report via WeasyPrint and return it as a downloadable file."""
    try:
        html = _build_html(config)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("PDF export: HTML generation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        _ensure_weasyprint_libs()
        from weasyprint import HTML as WeasyHTML
        from weasyprint.text.fonts import FontConfiguration

        font_config = FontConfiguration()
        pdf_bytes = WeasyHTML(string=html, media_type="print").write_pdf(
            font_config=font_config,
        )
    except ImportError:
        logger.error("WeasyPrint is not installed")
        raise HTTPException(
            status_code=503,
            detail="PDF generation unavailable: WeasyPrint is not installed.",
        )
    except Exception as exc:
        logger.exception("PDF export: WeasyPrint rendering failed")
        raise HTTPException(
            status_code=500,
            detail=f"PDF rendering failed: {exc}",
        ) from exc

    site_names = _get_site_names(config.studied_site_ids)
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{_make_filename(config.report_type, "pdf", site_names)}"'
        },
    )


@router.post("/excel")
async def export_excel_endpoint(config: ReportConfig):
    """Generate an Excel workbook with site and scenario summaries."""
    site_entries, scenario_results = _prepare_inputs(config)

    excel_bytes = build_excel_bytes(
        report_type=config.report_type,
        primary_color=config.primary_color,
        secondary_color=config.secondary_color,
        font_family=config.font_family,
        logo_url=config.logo_url,
        site_entries=site_entries,
        scenario_results=scenario_results,
        layout_mode=config.layout_mode,
        studied_site_ids=config.studied_site_ids,
        primary_result_keys=config.primary_result_keys,
        load_mix_results=config.load_mix_results,
        green_energy_results=config.green_energy_results,
        include_all_scenarios=config.include_all_scenarios,
    )

    site_names = _get_site_names(config.studied_site_ids)
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{_make_filename(config.report_type, "xlsx", site_names)}"'
        },
    )


@router.get("/terrain-preview")
async def terrain_preview_endpoint(site_id: str):
    """Return a PNG terrain image for the given site."""
    loaded = get_site(site_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail=f"Site not found: {site_id}")
    _, site = loaded
    if site.latitude is None or site.longitude is None:
        raise HTTPException(
            status_code=400,
            detail="Site does not have coordinates for terrain rendering.",
        )
    png_bytes = generate_terrain_image(site.latitude, site.longitude)
    if png_bytes is None:
        raise HTTPException(
            status_code=503,
            detail="Terrain image generation unavailable (staticmap not installed).",
        )
    return StreamingResponse(
        BytesIO(png_bytes),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
