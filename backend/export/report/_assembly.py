"""Assembly functions: build site bundles, site summaries, and the public API entry points."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def _asset_data_uri(filename: str) -> str | None:
    """Return a base64 data URI for an image file in the assets directory."""
    path = _ASSETS_DIR / filename
    if not path.is_file():
        return None
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    suffix = path.suffix.lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}.get(suffix, "image/png")
    return f"data:{mime};base64,{b64}"

from engine.models import ScenarioResult, Site

from export.report._constants import LAYOUT_MODE_LABELS, NARRATIVE_POLICY
from export.report._loaders import (
    _load_climate_block,
    _load_green_energy_block,
    _load_grid_context_block,
    _load_load_mix_block,
)
from export.report._narratives import _build_cover_narrative
from export.report._normalize import _normalize_result, _normalize_site_data
from export.report._selection import (
    _best_result_key,
    _build_display_results_by_site,
    _filter_site_entries,
    _group_results_by_site,
    _resolve_primary_results,
    _result_identity,
    _result_pue,
    _score_values,
    get_result_display_label,
    get_result_selection_key,
)
from export.report._utils import _safe_mean
from export.report.chapters.climate import _build_climate_chapter
from export.report.chapters.green_energy import _build_green_energy_chapter
from export.report.chapters.grid_context import _build_grid_context_chapter
from export.report.chapters.load_mix import _build_load_mix_chapter
from export.report.chapters.scenario import (
    _build_deep_dive_chapter,
    _build_selected_scenario_chapter,
)
from export.report.chapters.site_specifics import _build_site_specifics_chapter
from export.visual_assets import build_scenario_comparison_chart


def _build_site_bundle(
    *,
    site_id: str,
    site: Site,
    primary_color: str,
    secondary_color: str,
    site_results: list[ScenarioResult],
    display_results: list[ScenarioResult],
    primary_result: ScenarioResult | None,
    requested_primary_result_key: str | None,
    effective_primary_result_key: str | None,
    load_mix_input: dict[str, Any] | None,
    green_energy_input: dict[str, Any] | None,
    all_rank_lookup: dict[tuple[str, str], int],
    selected_rank_lookup: dict[tuple[str, str], int],
) -> dict[str, Any]:
    alternatives: list[ScenarioResult] = []
    primary_identity = (
        (site_id, effective_primary_result_key)
        if effective_primary_result_key is not None
        else None
    )
    for result in site_results:
        if primary_identity is not None and _result_identity(result) == primary_identity:
            continue
        alternatives.append(result)

    grid_context = _load_grid_context_block(site_id)
    climate = _load_climate_block(site_id, site_results, primary_result)
    load_mix = _load_load_mix_block(load_mix_input, effective_primary_result_key)
    green_energy = _load_green_energy_block(
        green_energy_input,
        effective_primary_result_key,
    )
    normalized_site_data = _normalize_site_data(site)

    normalized_all_results = []
    normalized_display_results = []
    normalized_alternatives = []
    normalized_primary = None

    display_identities = {_result_identity(result) for result in display_results}

    for index, result in enumerate(site_results, start=1):
        identity = _result_identity(result)
        normalized = _normalize_result(
            result,
            rank_within_site=index,
            global_rank=all_rank_lookup.get(identity),
            selected_primary_rank=selected_rank_lookup.get(identity),
            is_primary=identity == primary_identity,
            is_displayed_in_current_output=identity in display_identities,
        )
        normalized_all_results.append(normalized)

        if normalized["is_primary"]:
            normalized_primary = normalized

        if not normalized["is_primary"]:
            normalized_alternatives.append(normalized)

        if identity in display_identities:
            normalized_display_results.append(normalized)

    annual_pues = [_result_pue(result) for result in site_results]
    scores = _score_values(site_results)
    it_loads = [result.power.it_load_mw for result in site_results]

    # Build scenario comparison chart from normalized results
    scenario_comparison_chart = build_scenario_comparison_chart(
        normalized_all_results[:8],
        primary_color=primary_color,
        secondary_color=secondary_color,
    )

    chapters = {
        "site_specifics": _build_site_specifics_chapter(
            normalized_site_data,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "grid_context": _build_grid_context_chapter(
            grid_context,
            normalized_site_data,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "climate": _build_climate_chapter(
            climate,
            normalized_primary,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "selected_scenario": _build_selected_scenario_chapter(normalized_primary),
        "deep_dive": _build_deep_dive_chapter(
            normalized_primary,
            normalized_site_data,
            site=site,
            primary_scenario_result=primary_result,
            primary_color=primary_color,
            secondary_color=secondary_color,
            green_energy_data=green_energy,
        ),
        "load_mix": _build_load_mix_chapter(load_mix, normalized_primary),
        "green_energy": _build_green_energy_chapter(green_energy),
    }

    return {
        "site_id": site_id,
        "site_data": normalized_site_data,
        "summary": {
            "available_result_count": len(site_results),
            "display_result_count": len(display_results),
            "alternative_count": len(alternatives),
            "resolved_primary_result_key": effective_primary_result_key,
            "requested_primary_result_key": requested_primary_result_key,
            "avg_available_pue": _safe_mean(annual_pues),
            "avg_available_score": round(mean(scores), 2) if scores else None,
            "max_available_it_load_mw": (
                round(max(it_loads), 3) if it_loads else None
            ),
        },
        "results": {
            "primary": normalized_primary,
            "display_results": normalized_display_results,
            "alternatives": normalized_alternatives,
            "all_ranked": normalized_all_results,
        },
        "grid_context": grid_context,
        "climate": climate,
        "load_mix": load_mix,
        "green_energy": green_energy,
        "scenario_comparison_chart": scenario_comparison_chart,
        "chapters": chapters,
    }


def _build_site_summary(
    *,
    site_id: str,
    site: Site,
    display_results: list[ScenarioResult],
    site_results: list[ScenarioResult],
    primary_result: ScenarioResult | None,
    effective_primary_result_key: str | None,
    site_bundle: dict[str, Any],
) -> dict[str, Any]:
    best_result = display_results[0] if display_results else None
    best_available_result = site_results[0] if site_results else None

    annual_pues = [_result_pue(result) for result in display_results]
    available_annual_pues = [_result_pue(result) for result in site_results]
    it_loads = [result.power.it_load_mw for result in display_results]
    available_it_loads = [result.power.it_load_mw for result in site_results]
    scores = _score_values(display_results)
    available_scores = _score_values(site_results)

    return {
        "site_id": site_id,
        "site": site,
        "site_data": site_bundle["site_data"],
        "result_count": len(display_results),
        "available_result_count": len(site_results),
        "best_result": best_result,
        "best_available_result": best_available_result,
        "selected_result": primary_result,
        "selected_result_key": effective_primary_result_key,
        "selected_result_label": (
            get_result_display_label(primary_result) if primary_result is not None else None
        ),
        "avg_annual_pue": _safe_mean(annual_pues),
        "available_avg_annual_pue": _safe_mean(available_annual_pues),
        "max_it_load_mw": round(max(it_loads), 3) if it_loads else None,
        "available_max_it_load_mw": (
            round(max(available_it_loads), 3) if available_it_loads else None
        ),
        "avg_score": round(mean(scores), 2) if scores else None,
        "available_avg_score": (
            round(mean(available_scores), 2) if available_scores else None
        ),
        "results": display_results,
        "all_results": site_results,
        "alternative_results": [
            result
            for result in site_results
            if effective_primary_result_key is None
            or get_result_selection_key(result) != effective_primary_result_key
        ],
        "grid_context": site_bundle["grid_context"],
        "climate": site_bundle["climate"],
    }


def _assemble_report_data(
    *,
    report_type: str,
    primary_color: str,
    secondary_color: str,
    font_family: str,
    logo_url: str | None,
    site_entries: list[tuple[str, Site]],
    scenario_results: list[ScenarioResult],
    layout_mode: str,
    studied_site_ids: list[str],
    primary_result_keys: dict[str, str],
    load_mix_results: dict[str, Any],
    green_energy_results: dict[str, Any],
    include_all_scenarios: bool = True,
) -> dict[str, Any]:
    generated_at_utc = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    filtered_site_entries = _filter_site_entries(site_entries, studied_site_ids)
    results_by_site = _group_results_by_site(scenario_results, studied_site_ids)
    primary_results_by_site, effective_primary_result_keys = _resolve_primary_results(
        studied_site_ids=studied_site_ids,
        results_by_site=results_by_site,
        primary_result_keys=primary_result_keys,
    )
    display_results_by_site = _build_display_results_by_site(
        studied_site_ids=studied_site_ids,
        results_by_site=results_by_site,
        primary_results_by_site=primary_results_by_site,
        primary_result_keys=primary_result_keys,
        include_all_scenarios=include_all_scenarios,
    )

    all_ranked_results = sorted(
        [
            result
            for site_id in studied_site_ids
            for result in results_by_site.get(site_id, [])
        ],
        key=_best_result_key,
        reverse=True,
    )
    selected_primary_results = sorted(
        list(primary_results_by_site.values()),
        key=_best_result_key,
        reverse=True,
    )
    legacy_ranked_results = sorted(
        [
            result
            for site_id in studied_site_ids
            for result in display_results_by_site.get(site_id, [])
        ],
        key=_best_result_key,
        reverse=True,
    )

    all_rank_lookup = {
        _result_identity(result): index
        for index, result in enumerate(all_ranked_results, start=1)
    }
    selected_rank_lookup = {
        _result_identity(result): index
        for index, result in enumerate(selected_primary_results, start=1)
    }

    studied_sites = []
    site_sections = []
    for site_id, site in filtered_site_entries:
        site_results = results_by_site.get(site_id, [])
        display_results = display_results_by_site.get(site_id, [])
        primary_result = primary_results_by_site.get(site_id)
        effective_primary_result_key = effective_primary_result_keys.get(site_id)

        site_bundle = _build_site_bundle(
            site_id=site_id,
            site=site,
            primary_color=primary_color,
            secondary_color=secondary_color,
            site_results=site_results,
            display_results=display_results,
            primary_result=primary_result,
            requested_primary_result_key=primary_result_keys.get(site_id),
            effective_primary_result_key=effective_primary_result_key,
            load_mix_input=load_mix_results.get(site_id),
            green_energy_input=green_energy_results.get(site_id),
            all_rank_lookup=all_rank_lookup,
            selected_rank_lookup=selected_rank_lookup,
        )
        studied_sites.append(site_bundle)
        site_sections.append(
            _build_site_summary(
                site_id=site_id,
                site=site,
                display_results=display_results,
                site_results=site_results,
                primary_result=primary_result,
                effective_primary_result_key=effective_primary_result_key,
                site_bundle=site_bundle,
            )
        )

    all_annual_pues = [_result_pue(result) for result in all_ranked_results]
    all_it_loads = [result.power.it_load_mw for result in all_ranked_results]
    display_annual_pues = [_result_pue(result) for result in legacy_ranked_results]
    display_it_loads = [result.power.it_load_mw for result in legacy_ranked_results]

    report_bundle = {
        "studied_sites": studied_sites,
        "selected_primary_results": sorted(
            [
                site_bundle["results"]["primary"]
                for site_bundle in studied_sites
                if site_bundle["results"]["primary"] is not None
            ],
            key=lambda result: (
                result["selected_primary_rank"]
                if result["selected_primary_rank"] is not None
                else float("inf")
            ),
        ),
        "ranked_alternatives": sorted(
            [
                alternative
                for site_bundle in studied_sites
                for alternative in site_bundle["results"]["alternatives"]
            ],
            key=lambda result: (
                result["global_rank"] if result["global_rank"] is not None else float("inf")
            ),
        ),
        "all_ranked_results": sorted(
            [
                result
                for site_bundle in studied_sites
                for result in site_bundle["results"]["all_ranked"]
            ],
            key=lambda result: (
                result["global_rank"] if result["global_rank"] is not None else float("inf")
            ),
        ),
        "analysis_availability": {
            "grid_context_available_site_count": sum(
                1
                for site_bundle in studied_sites
                if site_bundle["grid_context"]["status"] == "available"
            ),
            "climate_available_site_count": sum(
                1
                for site_bundle in studied_sites
                if site_bundle["climate"]["status"] == "available"
            ),
            "load_mix_available_site_count": sum(
                1
                for site_bundle in studied_sites
                if site_bundle["chapters"]["load_mix"]["included"]
            ),
            "green_energy_available_site_count": sum(
                1
                for site_bundle in studied_sites
                if site_bundle["chapters"]["green_energy"]["included"]
            ),
            "site_count_with_primary_results": sum(
                1
                for site_bundle in studied_sites
                if site_bundle["results"]["primary"] is not None
            ),
            "site_count_with_ranked_alternatives": sum(
                1
                for site_bundle in studied_sites
                if site_bundle["results"]["alternatives"]
            ),
        },
        "requested_primary_result_keys": primary_result_keys,
        "resolved_primary_result_keys": effective_primary_result_keys,
    }
    cover_narrative = _build_cover_narrative(
        site_count=len(filtered_site_entries),
        primary_result_count=len(selected_primary_results),
        layout_mode_label=LAYOUT_MODE_LABELS.get(layout_mode, layout_mode),
        analysis_availability=report_bundle["analysis_availability"],
    )
    studied_site_names = [site.name for _, site in filtered_site_entries]
    cover_scope_label = (
        studied_site_names[0]
        if len(studied_site_names) == 1
        else f"{len(studied_site_names)} studied sites"
        if studied_site_names
        else "No studied sites selected"
    )

    return {
        "report": {
            "type": report_type,
            "title": (
                "Executive Feasibility Summary"
                if report_type == "executive"
                else "Detailed Technical Feasibility Report"
            ),
            "layout_mode": layout_mode,
            "layout_mode_label": LAYOUT_MODE_LABELS.get(layout_mode, layout_mode),
            "generated_at_utc": generated_at_utc,
            "generated_on": generated_at_utc[:10],
            "narrative_policy": NARRATIVE_POLICY,
            "narrative": cover_narrative,
            "include_all_scenarios": include_all_scenarios,
        },
        "theme": {
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "font_family": font_family,
            "logo_url": logo_url,
            "cover_image_url": _asset_data_uri("Metlen_report_cover.png"),
            "page_logo_url": _asset_data_uri("Metlen_logo.png"),
        },
        "study_scope": {
            "studied_site_ids": studied_site_ids,
            "studied_site_names": studied_site_names,
            "cover_scope_label": cover_scope_label,
            "displayed_result_count": len(legacy_ranked_results),
            "available_result_count": len(all_ranked_results),
            "selected_primary_result_count": len(selected_primary_results),
            "primary_result_keys": primary_result_keys,
            "resolved_primary_result_keys": effective_primary_result_keys,
            "selected_primary_results": [
                {
                    "site_id": result.site_id,
                    "site_name": result.site_name,
                    "result_key": get_result_selection_key(result),
                    "label": get_result_display_label(result),
                }
                for result in selected_primary_results
            ],
        },
        "summary": {
            "site_count": len(filtered_site_entries),
            "scenario_count": len(legacy_ranked_results),
            "available_scenario_count": len(all_ranked_results),
            "primary_result_count": len(selected_primary_results),
            "best_result": legacy_ranked_results[0] if legacy_ranked_results else None,
            "best_available_result": (
                all_ranked_results[0] if all_ranked_results else None
            ),
            "avg_pue": _safe_mean(display_annual_pues),
            "available_avg_pue": _safe_mean(all_annual_pues),
            "max_it_load_mw": (
                round(max(display_it_loads), 3) if display_it_loads else None
            ),
            "available_max_it_load_mw": (
                round(max(all_it_loads), 3) if all_it_loads else None
            ),
        },
        "report_bundle": report_bundle,
        "_site_sections": site_sections,
        "_legacy_ranked_results": legacy_ranked_results,
        "_selected_primary_results": selected_primary_results,
        "_all_ranked_results": all_ranked_results,
    }


def build_report_bundle(
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
) -> dict[str, Any]:
    """Build the normalized report bundle used across export surfaces."""
    if studied_site_ids is None:
        studied_site_ids = [site_id for site_id, _ in site_entries]
    primary_result_keys = primary_result_keys or {}
    load_mix_results = load_mix_results or {}
    green_energy_results = green_energy_results or {}

    assembled = _assemble_report_data(
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
    return {key: value for key, value in assembled.items() if not key.startswith("_")}


def build_report_context(
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
) -> dict[str, Any]:
    """Create the view model shared by HTML and Excel export."""
    if studied_site_ids is None:
        studied_site_ids = [site_id for site_id, _ in site_entries]
    primary_result_keys = primary_result_keys or {}
    load_mix_results = load_mix_results or {}
    green_energy_results = green_energy_results or {}

    assembled = _assemble_report_data(
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

    context = {key: value for key, value in assembled.items() if not key.startswith("_")}
    context["site_sections"] = assembled["_site_sections"]
    context["ranked_results"] = assembled["_legacy_ranked_results"]
    context["selected_primary_results"] = assembled["_selected_primary_results"]
    context["all_ranked_results"] = assembled["_all_ranked_results"]
    return context
