"""
DC Feasibility Tool v4 - HTML Report Renderer
=============================================
Renders executive and detailed reports using Jinja2 templates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape, Undefined

from engine.models import ScenarioResult, Site
from export.report_data import build_report_context

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
    undefined=Undefined,  # silently ignore undefined variables
)


def _fmt(value: Any, digits: int = 2, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return f"{value:,.{digits}f}"
    return str(value)


def _default_if_none(value: Any, default: Any = "") -> Any:
    """Jinja2 filter: return default if value is None."""
    return default if value is None else value


_env.filters["fmt"] = _fmt
_env.filters["default_if_none"] = _default_if_none


def render_report_html(
    report_type: str,
    primary_color: str,
    secondary_color: str,
    font_family: str,
    logo_url: str | None,
    site_entries: list[tuple[str, Site]],
    scenario_results: list[ScenarioResult],
    layout_mode: str = "presentation_16_9",
    studied_site_ids: list[str] | None = None,
    primary_result_keys: dict[str, str] | None = None,
    load_mix_results: dict[str, Any] | None = None,
    green_energy_results: dict[str, Any] | None = None,
    include_all_scenarios: bool = True,
) -> str:
    logger.info(
        "Building report context: type=%s, sites=%d, results=%d",
        report_type,
        len(site_entries),
        len(scenario_results),
    )
    context = build_report_context(
        report_type=report_type,
        primary_color=primary_color,
        secondary_color=secondary_color,
        font_family=font_family,
        logo_url=logo_url,
        site_entries=site_entries,
        scenario_results=scenario_results,
        layout_mode=layout_mode,
        studied_site_ids=studied_site_ids,
        primary_result_keys=primary_result_keys,
        load_mix_results=load_mix_results,
        green_energy_results=green_energy_results,
        include_all_scenarios=include_all_scenarios,
    )
    template_name = (
        "executive_summary.html"
        if report_type == "executive"
        else "detailed_report.html"
    )
    logger.info("Rendering template: %s", template_name)
    try:
        html = _env.get_template(template_name).render(**context)
        logger.info("Template rendered successfully: %d chars", len(html))
        return html
    except Exception:
        logger.exception("Template rendering failed for %s", template_name)
        raise
