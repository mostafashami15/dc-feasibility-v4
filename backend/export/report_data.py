"""
DC Feasibility Tool v4 - Report Data Shaping
============================================
Transforms saved sites, scenario results, and optional analysis caches into
a stable structure consumed by the HTML, PDF, and Excel exporters.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import BaseModel, ValidationError

from api.store import GRID_CONTEXT_DIR, get_weather
from engine.assumptions import evaluate_compatibility
from engine.backup_power import compare_technologies
from engine.climate import analyse_climate
from engine.expansion import compute_expansion_advisory
from engine.footprint import compute_footprint
from engine.green_energy import (
    find_max_firm_it_capacity,
    recommend_support_portfolios,
    simulate_firm_capacity_support,
)
from engine.models import GridContextResult, ScenarioResult, Site
from engine.pue_engine import build_hourly_facility_factors, simulate_hourly
from engine.ranking import LoadMixResult
from engine.sensitivity import SENSITIVITY_PARAMETERS, compute_break_even, compute_tornado
from export.terrain_map import (
    generate_grid_context_base64,
    generate_site_location_base64,
    generate_terrain_base64,
)
from export.visual_assets import (
    build_free_cooling_chart,
    build_grid_context_map_visual,
    build_monthly_temperature_chart,
    build_site_map_visual,
)


LAYOUT_MODE_LABELS = {
    "presentation_16_9": "Presentation 16:9",
    "report_a4_portrait": "Report A4 Portrait",
}

MONTH_NAMES = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

SENSITIVITY_UNIT_SUFFIXES = {
    "pue": None,
    "eta_chain": None,
    "rack_density_kw": "kW/rack",
    "whitespace_ratio": None,
    "site_coverage_ratio": None,
    "available_power_mw": "MW",
}

NARRATIVE_POLICY = {
    "mode": "structured_guardrail_v1",
    "max_paragraphs": 2,
    "traceability": "basis_labels",
}


class LoadMixReportInput(BaseModel):
    result_key: str | None = None
    result: LoadMixResult


class GreenEnergyPVGISProfileInput(BaseModel):
    site_id: str | None = None
    site_name: str | None = None
    profile_key: str
    from_cache: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    start_year: int | None = None
    end_year: int | None = None
    years_averaged: list[int] | None = None
    pv_technology: str | None = None
    mounting_place: str | None = None
    system_loss_pct: float | None = None
    use_horizon: bool | None = None
    optimal_angles: bool | None = None
    surface_tilt_deg: float | None = None
    surface_azimuth_deg: float | None = None
    source: str | None = None
    radiation_database: str | None = None
    elevation_m: float | None = None
    pv_module_info: str | None = None
    hours: int | None = None


class GreenEnergyReportResultInput(BaseModel):
    total_overhead_kwh: float
    total_pv_generation_kwh: float
    total_pv_to_overhead_kwh: float
    total_pv_to_bess_kwh: float
    total_pv_curtailed_kwh: float
    total_bess_discharge_kwh: float
    total_fuel_cell_kwh: float
    total_grid_import_kwh: float
    overhead_coverage_fraction: float
    renewable_fraction: float
    pv_self_consumption_fraction: float
    bess_cycles_equivalent: float
    co2_avoided_tonnes: float
    pv_capacity_kwp: float
    bess_capacity_kwh: float
    bess_roundtrip_efficiency: float
    fuel_cell_capacity_kw: float
    total_facility_kwh: float
    total_it_kwh: float
    site_name: str | None = None
    hours: int | None = None
    annual_pue: float | None = None
    pue_source: str | None = None
    nominal_it_mw: float | None = None
    committed_it_mw: float | None = None
    pv_profile_source: str | None = None
    pvgis_profile_key: str | None = None


class GreenEnergyReportInput(BaseModel):
    result_key: str | None = None
    result: GreenEnergyReportResultInput
    pv_profile_name: str | None = None
    pvgis_profile: GreenEnergyPVGISProfileInput | None = None
    bess_initial_soc_kwh: float | None = None
    grid_co2_kg_per_kwh: float | None = None


def _display_number(
    value: float | int | None,
    *,
    digits: int = 2,
    suffix: str | None = None,
    default: str = "Not available",
) -> str:
    if value is None:
        return default
    formatted = f"{value:,.{digits}f}"
    if suffix:
        return f"{formatted} {suffix}"
    return formatted


def _display_percent(
    value: float | None,
    *,
    digits: int = 0,
    default: str = "Not available",
) -> str:
    if value is None:
        return default
    return f"{value * 100:.{digits}f}%"


def _display_energy_mwh(
    value_kwh: float | None,
    *,
    digits: int = 2,
    default: str = "Not available",
) -> str:
    if value_kwh is None:
        return default
    return _display_number(value_kwh / 1000.0, digits=digits, suffix="MWh")


def _display_bool(
    value: bool | None,
    *,
    true_label: str = "Yes",
    false_label: str = "No",
    default: str = "Not available",
) -> str:
    if value is None:
        return default
    return true_label if value else false_label


def _display_text(value: Any, default: str = "Not available") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or default
    return str(value)


def _display_coordinates(
    latitude: float | None,
    longitude: float | None,
    *,
    digits: int = 5,
    default: str = "Not available",
) -> str:
    if latitude is None or longitude is None:
        return default
    return f"{latitude:.{digits}f}, {longitude:.{digits}f}"


def _display_list(values: list[Any], default: str = "Not available") -> str:
    filtered = [_display_text(value, default="") for value in values if value is not None]
    filtered = [value for value in filtered if value]
    return ", ".join(filtered) if filtered else default


def _fact(label: str, value: Any) -> dict[str, str]:
    return {"label": label, "value": _display_text(value)}


def _safe_mean(values: list[float]) -> float | None:
    return round(mean(values), 3) if values else None


def _normalize_sentence(text: str | None) -> str:
    cleaned = _display_text(text, default="").strip()
    if not cleaned or cleaned == "Not available":
        return ""
    cleaned = " ".join(cleaned.split())
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _build_narrative(
    *,
    paragraphs: list[str | None],
    basis_labels: list[str | None],
    intents: list[str] | None = None,
) -> dict[str, Any]:
    cleaned_paragraphs: list[str] = []
    for paragraph in paragraphs:
        normalized = _normalize_sentence(paragraph)
        if normalized and normalized not in cleaned_paragraphs:
            cleaned_paragraphs.append(normalized)

    cleaned_basis: list[str] = []
    for label in basis_labels:
        normalized = _display_text(label, default="").strip()
        if normalized and normalized != "Not available" and normalized not in cleaned_basis:
            cleaned_basis.append(normalized)

    return {
        "available": bool(cleaned_paragraphs),
        "mode": NARRATIVE_POLICY["mode"],
        "paragraphs": cleaned_paragraphs[: NARRATIVE_POLICY["max_paragraphs"]],
        "basis_labels": cleaned_basis[:6],
        "intents": intents or ["summary", "recommendation"],
    }


def _best_result_key(result: ScenarioResult) -> tuple[float, float, float]:
    pue = result.annual_pue if result.annual_pue is not None else result.power.pue_used
    return (result.score, result.power.it_load_mw, -pue)


def _result_pue(result: ScenarioResult) -> float:
    return result.annual_pue if result.annual_pue is not None else result.power.pue_used


def _result_committed_it_mw(result: ScenarioResult) -> float:
    return (
        result.it_capacity_p99_mw
        if result.it_capacity_p99_mw is not None
        else result.power.it_load_mw
    )


def _result_identity(result: ScenarioResult) -> tuple[str, str]:
    return result.site_id, get_result_selection_key(result)


def _score_values(results: list[ScenarioResult]) -> list[float]:
    return [result.score for result in results if result.score > 0]


def _infer_weather_source_type(weather: dict[str, Any]) -> str:
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


def get_result_selection_key(result: ScenarioResult) -> str:
    """Create the stable per-result selection key shared with the frontend."""
    return json.dumps(
        {
            "site_id": result.site_id,
            "load_type": result.scenario.load_type.value,
            "cooling_type": result.scenario.cooling_type.value,
            "redundancy": result.scenario.redundancy.value,
            "density_scenario": result.scenario.density_scenario.value,
            "backup_power": result.scenario.backup_power.value,
            "pue_override": result.scenario.pue_override,
            "assumption_override_preset_key": (
                result.scenario.assumption_override_preset_key or None
            ),
        },
        separators=(",", ":"),
    )


def get_result_display_label(result: ScenarioResult) -> str:
    committed_it_mw = _result_committed_it_mw(result)
    return (
        f"{result.scenario.load_type.value} | "
        f"{result.scenario.cooling_type.value} | "
        f"{result.scenario.redundancy.value} | "
        f"{result.scenario.density_scenario.value} | "
        f"{committed_it_mw:.2f} MW IT"
    )


def validate_report_selection(
    studied_site_ids: list[str],
    primary_result_keys: dict[str, str] | None,
    scenario_results: list[ScenarioResult],
) -> None:
    """Validate the studied-site and primary-result scope requested by the UI."""
    primary_result_keys = primary_result_keys or {}
    studied_site_id_set = set(studied_site_ids)

    unexpected_sites = sorted(set(primary_result_keys) - studied_site_id_set)
    if unexpected_sites:
        raise ValueError(
            "Primary result keys were provided for unselected studied sites: "
            + ", ".join(unexpected_sites)
        )

    available_keys_by_site: dict[str, set[str]] = defaultdict(set)
    for result in scenario_results:
        if result.site_id in studied_site_id_set:
            available_keys_by_site[result.site_id].add(get_result_selection_key(result))

    missing_primary_sites = [
        site_id
        for site_id in studied_site_ids
        if available_keys_by_site.get(site_id) and site_id not in primary_result_keys
    ]
    if missing_primary_sites:
        raise ValueError(
            "Missing primary result selection for studied site(s): "
            + ", ".join(missing_primary_sites)
        )

    invalid_primary_sites = [
        site_id
        for site_id, result_key in primary_result_keys.items()
        if result_key not in available_keys_by_site.get(site_id, set())
    ]
    if invalid_primary_sites:
        raise ValueError(
            "Primary result selection did not match the current batch results for site(s): "
            + ", ".join(sorted(invalid_primary_sites))
        )


def _filter_site_entries(
    site_entries: list[tuple[str, Site]],
    studied_site_ids: list[str],
) -> list[tuple[str, Site]]:
    site_map = {site_id: site for site_id, site in site_entries}
    return [
        (site_id, site_map[site_id])
        for site_id in studied_site_ids
        if site_id in site_map
    ]


def _group_results_by_site(
    scenario_results: list[ScenarioResult],
    studied_site_ids: list[str],
) -> dict[str, list[ScenarioResult]]:
    studied_site_id_set = set(studied_site_ids)
    results_by_site: dict[str, list[ScenarioResult]] = defaultdict(list)
    for result in scenario_results:
        if result.site_id in studied_site_id_set:
            results_by_site[result.site_id].append(result)

    for site_id in list(results_by_site):
        results_by_site[site_id] = sorted(
            results_by_site[site_id],
            key=_best_result_key,
            reverse=True,
        )
    return results_by_site


def _resolve_primary_results(
    studied_site_ids: list[str],
    results_by_site: dict[str, list[ScenarioResult]],
    primary_result_keys: dict[str, str],
) -> tuple[dict[str, ScenarioResult], dict[str, str]]:
    primary_results_by_site: dict[str, ScenarioResult] = {}
    effective_primary_result_keys: dict[str, str] = {}

    for site_id in studied_site_ids:
        site_results = results_by_site.get(site_id, [])
        if not site_results:
            continue

        result_by_key = {
            get_result_selection_key(result): result for result in site_results
        }
        requested_key = primary_result_keys.get(site_id)
        selected_result = (
            result_by_key.get(requested_key)
            if requested_key is not None
            else site_results[0]
        )
        if selected_result is None:
            selected_result = site_results[0]

        effective_key = get_result_selection_key(selected_result)
        primary_results_by_site[site_id] = selected_result
        effective_primary_result_keys[site_id] = effective_key

    return primary_results_by_site, effective_primary_result_keys


def _build_display_results_by_site(
    studied_site_ids: list[str],
    results_by_site: dict[str, list[ScenarioResult]],
    primary_results_by_site: dict[str, ScenarioResult],
    primary_result_keys: dict[str, str],
) -> dict[str, list[ScenarioResult]]:
    if not primary_result_keys:
        return {
            site_id: list(results_by_site.get(site_id, []))
            for site_id in studied_site_ids
        }

    display_results_by_site: dict[str, list[ScenarioResult]] = {}
    for site_id in studied_site_ids:
        selected_result = primary_results_by_site.get(site_id)
        if selected_result is None or site_id not in primary_result_keys:
            display_results_by_site[site_id] = []
            continue
        display_results_by_site[site_id] = [selected_result]
    return display_results_by_site


def _normalize_site_data(site: Site) -> dict[str, Any]:
    imported_geometry = site.imported_geometry
    return {
        "name": site.name,
        "site_type": site.site_type.value,
        "location": {
            "country": site.country,
            "city": site.city,
            "latitude": site.latitude,
            "longitude": site.longitude,
            "coordinates_present": (
                site.latitude is not None and site.longitude is not None
            ),
        },
        "land": {
            "land_area_m2": site.land_area_m2,
            "buildable_area_mode": site.buildable_area_mode.value,
            "site_coverage_ratio": site.site_coverage_ratio,
            "buildable_area_m2": site.buildable_area_m2,
        },
        "building": {
            "max_building_height_m": site.max_building_height_m,
            "floor_to_floor_height_m": site.floor_to_floor_height_m,
            "num_floors": site.num_floors,
            "num_expansion_floors": site.num_expansion_floors,
            "whitespace_ratio": site.whitespace_ratio,
            "rack_footprint_m2": site.rack_footprint_m2,
        },
        "power": {
            "available_power_mw": site.available_power_mw,
            "power_confirmed": site.power_confirmed,
            "power_input_mode": site.power_input_mode.value,
            "voltage": site.voltage,
        },
        "imported_geometry": {
            "present": imported_geometry is not None,
            "geometry_type": (
                imported_geometry.geometry_type if imported_geometry is not None else None
            ),
            "coordinates": (
                list(imported_geometry.coordinates) if imported_geometry is not None else []
            ),
            "coordinate_count": (
                len(imported_geometry.coordinates) if imported_geometry is not None else 0
            ),
        },
        "notes": site.notes,
    }


def _build_cover_narrative(
    *,
    site_count: int,
    primary_result_count: int,
    layout_mode_label: str,
    analysis_availability: dict[str, Any],
) -> dict[str, Any]:
    optional_summary = (
        f"Optional chapters are available for "
        f"{analysis_availability['grid_context_available_site_count']} grid context site(s), "
        f"{analysis_availability['climate_available_site_count']} climate site(s), "
        f"{analysis_availability['load_mix_available_site_count']} load-mix site(s), and "
        f"{analysis_availability['green_energy_available_site_count']} green-energy site(s)"
    )
    if not any(
        analysis_availability[key]
        for key in (
            "grid_context_available_site_count",
            "climate_available_site_count",
            "load_mix_available_site_count",
            "green_energy_available_site_count",
        )
    ):
        optional_summary = (
            "This export contains only the fixed core chapters because no optional "
            "analysis chapters were available for the selected study scope"
        )

    return _build_narrative(
        paragraphs=[
            (
                f"This export covers {site_count} studied site(s) and "
                f"{primary_result_count} selected primary scenario(s) in "
                f"{layout_mode_label} format"
            ),
            optional_summary,
        ],
        basis_labels=[
            "Studied Sites",
            "Primary Scenarios",
            "Layout",
            "Grid context chapters",
            "Climate chapters",
            "Load mix chapters",
            "Green energy chapters",
        ],
        intents=["summary"],
    )


def _build_site_specifics_narrative(site_data: dict[str, Any]) -> dict[str, Any]:
    location = site_data["location"]
    land = site_data["land"]
    power = site_data["power"]
    imported_geometry = site_data["imported_geometry"]

    location_bits = [value for value in (location["city"], location["country"]) if value]
    location_label = ", ".join(location_bits) if location_bits else "an unspecific saved location"
    buildable_area = _display_number(land["buildable_area_m2"], digits=0, suffix="m2")
    available_power = _display_number(power["available_power_mw"], digits=2, suffix="MW")

    power_basis = (
        "Power is confirmed, so power-constrained outputs can use this site-power envelope as a governed basis"
        if power["power_confirmed"]
        else "Power is not yet confirmed, so power-driven conclusions should still be treated as screening-grade"
    )
    geometry_basis = (
        "Imported geometry is available for map framing"
        if imported_geometry["present"]
        else "No imported geometry was saved, so mapping falls back to the stored site point"
    )

    return _build_narrative(
        paragraphs=[
            (
                f"{site_data['name']} is recorded as a {site_data['site_type']} site in "
                f"{location_label} with {buildable_area} of buildable area and "
                f"{available_power} of declared site power"
            ),
            f"{power_basis}. {geometry_basis}",
        ],
        basis_labels=[
            "Site classification",
            "City",
            "Country",
            "Buildable area",
            "Available power",
            "Power confirmed",
            "Imported geometry present",
        ],
    )


def _build_grid_context_narrative(
    *,
    summary: dict[str, Any],
    score: dict[str, Any] | None,
    has_official_evidence: bool,
) -> dict[str, Any]:
    screening_sentence = (
        f"Screening found {summary.get('nearby_line_count', 0)} nearby line(s) and "
        f"{summary.get('nearby_substation_count', 0)} substation(s) inside "
        f"{_display_number(summary.get('radius_km'), digits=1, suffix='km')}, with the "
        f"closest substation at {_display_number(summary.get('nearest_substation_km'), digits=2, suffix='km')} "
        f"and the highest mapped voltage at {_display_number(summary.get('max_voltage_kv'), digits=0, suffix='kV')}"
    )
    if has_official_evidence:
        recommendation = (
            "Saved official evidence is present and should take precedence over the screening heuristic where the two differ"
        )
    elif score is not None:
        recommendation = (
            f"The current screening heuristic is {_display_number(score.get('overall_score'), digits=1)}, "
            "so treat this chapter as early power-access context until utility evidence is attached"
        )
    else:
        recommendation = (
            "No saved utility evidence is attached, so this chapter should be read as screening-grade context only"
        )

    return _build_narrative(
        paragraphs=[screening_sentence, recommendation],
        basis_labels=[
            "Search radius",
            "Nearby lines",
            "Nearby substations",
            "Nearest substation",
            "Maximum mapped voltage",
            "Heuristic score",
            "Reference",
        ],
    )


def _build_climate_narrative(
    *,
    weather_status: dict[str, Any],
    temperature_stats: dict[str, Any],
    selected_cooling_type: str | None,
    selected_free_cooling: dict[str, Any] | None,
    best_free_cooling: dict[str, Any],
) -> dict[str, Any]:
    source_label = _display_text(weather_status.get("source"), default="")
    source_type = _display_text(weather_status.get("source_type"), default="")
    climate_summary = (
        f"Weather inputs cover {_display_number(weather_status.get('hours'), digits=0)} hour(s) "
        f"from {source_type or 'the saved source'}"
    )
    if source_label:
        climate_summary += f" using {source_label}"
    climate_summary += (
        f", with mean dry-bulb at {_display_number(temperature_stats.get('mean'), digits=2, suffix='C')} "
        f"and a recorded maximum of {_display_number(temperature_stats.get('max'), digits=2, suffix='C')}"
    )

    if selected_free_cooling is not None and selected_cooling_type:
        recommendation = (
            f"For the selected {selected_cooling_type} path, free cooling reaches "
            f"{selected_free_cooling.get('free_cooling_fraction')} over "
            f"{selected_free_cooling.get('free_cooling_hours')}"
        )
    else:
        recommendation = (
            f"The strongest free-cooling fit in this dataset is "
            f"{_display_text(best_free_cooling.get('cooling_type'))} at "
            f"{_display_percent(best_free_cooling.get('free_cooling_fraction'), digits=1)}"
        )

    return _build_narrative(
        paragraphs=[climate_summary, recommendation],
        basis_labels=[
            "Weather source",
            "Source type",
            "Hours analysed",
            "Mean dry-bulb",
            "Maximum",
            "Best cooling type",
            "Best free cooling fraction",
        ],
    )


def _build_selected_scenario_narrative(
    *,
    scenario: dict[str, Any],
    feature_flags: dict[str, Any],
    override_count: int,
) -> dict[str, Any]:
    summary_sentence = (
        f"The selected scenario combines {scenario['load_type']}, {scenario['cooling_type']}, "
        f"{scenario['redundancy']} redundancy, {scenario['density_scenario']} density, and "
        f"{scenario['backup_power']} backup power"
    )
    if override_count > 0 or scenario.get("pue_override") is not None:
        recommendation = (
            f"Hourly simulation was {_display_bool(feature_flags['has_hourly_pue']).lower()} and "
            f"{override_count} saved assumption override(s) affect interpretation, so the override table should be read alongside the deep-dive metrics"
        )
    else:
        recommendation = (
            f"Hourly simulation was {_display_bool(feature_flags['has_hourly_pue']).lower()} with no saved assumption overrides, "
            "so this configuration can be used as the narrative anchor for the site"
        )

    return _build_narrative(
        paragraphs=[summary_sentence, recommendation],
        basis_labels=[
            "Load type",
            "Cooling type",
            "Redundancy",
            "Density scenario",
            "Backup power",
            "Hourly simulation used",
            "Applied assumption overrides",
        ],
    )


def _build_deep_dive_narrative(
    *,
    metrics: dict[str, Any],
    status: dict[str, Any],
    compatible_combination: bool,
) -> dict[str, Any]:
    summary_sentence = (
        f"This scenario reports {_display_number(metrics['committed_it_mw'], digits=2, suffix='MW')} of committed IT "
        f"at {_display_number(metrics['pue'], digits=2)} annual PUE with a score of "
        f"{_display_number(metrics['score'], digits=2)}"
    )
    constraint = _display_text(metrics.get("binding_constraint"))
    if status["rag_status"] in {"RED", "AMBER"}:
        recommendation = (
            f"The current RAG status is {status['rag_status']} with {constraint} as the active constraint, "
            "so this should be treated as a conditional scenario until the flagged limits are resolved"
        )
    elif not compatible_combination:
        recommendation = (
            f"The reported constraint is {constraint}, and the compatibility flag should be resolved before using this as a recommendation-grade scenario"
        )
    elif constraint == "POWER":
        recommendation = (
            "Power is the governing limit, so additional declared or secured power is the clearest lever for more committed IT capacity"
        )
    elif constraint == "SPACE":
        recommendation = (
            "Space is the governing limit, so geometry, whitespace, and floor-area efficiency are the clearest levers for more committed IT capacity"
        )
    else:
        recommendation = (
            f"The current RAG status is {status['rag_status']} with {constraint} as the governing limit, and the advanced blocks should be used to pressure-test downside cases"
        )

    return _build_narrative(
        paragraphs=[summary_sentence, recommendation],
        basis_labels=[
            "Committed IT capacity",
            "Annual PUE",
            "Score",
            "RAG status",
            "Binding constraint",
            "Scenario compatibility",
        ],
    )


def _build_load_mix_narrative(
    *,
    total_it_mw: Any,
    total_candidates_evaluated: Any,
    top_candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    if top_candidate is None:
        return _build_narrative(
            paragraphs=[
                (
                    f"The load-mix workflow was run for {_display_number(total_it_mw, digits=2, suffix='MW')} "
                    "of IT, but no ranked candidate combinations were returned"
                )
            ],
            basis_labels=[
                "Total IT target",
                "Candidates evaluated",
            ],
        )

    tradeoff_note = _clean_notes(top_candidate.get("trade_off_notes"))[:1]
    recommendation = (
        tradeoff_note[0]
        if tradeoff_note
        else "Use the ranked candidate table to compare workload-balance benefits against the blended-PUE trade-off"
    )
    return _build_narrative(
        paragraphs=[
            (
                f"The optimizer evaluated {_display_number(total_candidates_evaluated, digits=0)} candidate mix(es) "
                f"for {_display_number(total_it_mw, digits=2, suffix='MW')} of IT, and the top option returns "
                f"{_display_number(top_candidate.get('blended_pue'), digits=3)} blended PUE across "
                f"{_display_number(top_candidate.get('total_racks'), digits=0)} rack(s)"
            ),
            recommendation,
        ],
        basis_labels=[
            "Total IT target",
            "Candidates evaluated",
            "Top candidate blended PUE",
            "Top candidate racks",
            "Top candidate compatibility",
        ],
    )


def _build_green_energy_narrative(
    *,
    result: dict[str, Any],
    pv_profile_source: str,
) -> dict[str, Any]:
    summary_sentence = (
        f"The dispatch run reaches {_display_percent(result.get('renewable_fraction'), digits=1)} renewable fraction and "
        f"{_display_percent(result.get('overhead_coverage_fraction'), digits=1)} overhead coverage, "
        f"avoiding {_display_number(result.get('co2_avoided_tonnes'), digits=1, suffix='tCO2')} while still importing "
        f"{_display_energy_mwh(result.get('total_grid_import_kwh'))} from the grid"
    )
    if pv_profile_source == "pvgis":
        recommendation = (
            "The PV basis comes from a cached PVGIS normalized profile, so this chapter should be read as a weather-shaped decarbonization overlay rather than an off-grid design"
        )
    elif pv_profile_source == "manual":
        recommendation = (
            "The PV basis comes from a manual hourly profile, so the results should be interpreted against the provenance and quality of that uploaded series"
        )
    else:
        recommendation = (
            "No PV profile was applied, so this result should be read as a dispatch baseline for storage and firming assets rather than a full renewable design"
        )

    return _build_narrative(
        paragraphs=[summary_sentence, recommendation],
        basis_labels=[
            "Renewable fraction",
            "Overhead coverage",
            "CO2 avoided",
            "Grid import",
            "PV profile source",
            "PV source",
        ],
    )


def _build_site_specifics_chapter(
    site_data: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    location = site_data["location"]
    land = site_data["land"]
    building = site_data["building"]
    power = site_data["power"]
    imported_geometry = site_data["imported_geometry"]

    # Generate map imagery if coordinates are available
    terrain_image_uri = None
    location_map_uri = None
    lat = location.get("latitude")
    lon = location.get("longitude")
    if lat is not None and lon is not None:
        terrain_image_uri = generate_terrain_base64(lat, lon)
        location_map_uri = generate_site_location_base64(lat, lon)

    return {
        "title": "Site Specifics and Properties",
        "terrain_image": terrain_image_uri,
        "location_map": location_map_uri,
        "map_visual": build_site_map_visual(
            site_data,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "identity_items": [
            _fact("Site name", site_data["name"]),
            _fact("Site classification", site_data["site_type"]),
        ],
        "location_items": [
            _fact("Country", location["country"]),
            _fact("City", location["city"]),
            _fact(
                "Coordinates",
                _display_coordinates(location["latitude"], location["longitude"]),
            ),
        ],
        "property_items": [
            _fact("Land area", _display_number(land["land_area_m2"], digits=0, suffix="m2")),
            _fact("Buildable area mode", land["buildable_area_mode"]),
            _fact(
                "Site coverage ratio",
                _display_percent(land["site_coverage_ratio"], digits=0),
            ),
            _fact(
                "Buildable area",
                _display_number(land["buildable_area_m2"], digits=0, suffix="m2"),
            ),
            _fact(
                "Maximum building height",
                _display_number(building["max_building_height_m"], digits=1, suffix="m"),
            ),
            _fact(
                "Floor-to-floor height",
                _display_number(
                    building["floor_to_floor_height_m"],
                    digits=1,
                    suffix="m",
                ),
            ),
            _fact("Active floors", _display_number(building["num_floors"], digits=0)),
            _fact(
                "Expansion floors",
                _display_number(building["num_expansion_floors"], digits=0),
            ),
            _fact(
                "Whitespace ratio",
                _display_percent(building["whitespace_ratio"], digits=0),
            ),
            _fact(
                "Rack footprint",
                _display_number(building["rack_footprint_m2"], digits=1, suffix="m2"),
            ),
        ],
        "power_items": [
            _fact(
                "Available power",
                _display_number(power["available_power_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Power confirmed",
                _display_bool(power["power_confirmed"], true_label="Confirmed"),
            ),
            _fact("Power input mode", power["power_input_mode"]),
            _fact("Declared voltage", power["voltage"]),
        ],
        "geometry_items": [
            _fact(
                "Imported geometry present",
                _display_bool(imported_geometry["present"]),
            ),
            _fact("Geometry type", imported_geometry["geometry_type"]),
            _fact(
                "Coordinate count",
                _display_number(imported_geometry["coordinate_count"], digits=0),
            ),
        ],
        "notes": _display_text(site_data["notes"], default=""),
        "narrative": _build_site_specifics_narrative(site_data),
    }


def _grid_asset_report_key(asset: dict[str, Any]) -> tuple[int, int, float, float]:
    voltage = asset.get("voltage_kv")
    return (
        0 if voltage is not None else 1,
        0 if asset.get("asset_type") == "substation" else 1,
        -(voltage or 0.0),
        asset.get("distance_km", 0.0),
    )


def _select_grid_display_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked_assets = sorted(assets, key=_grid_asset_report_key)
    display_assets = [asset for asset in ranked_assets if asset.get("voltage_kv") is not None]
    if not display_assets:
        return ranked_assets[:4]
    return display_assets[:6]


def _build_grid_context_chapter(
    grid_context: dict[str, Any],
    site_data: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    if grid_context["status"] != "available" or grid_context["selected"] is None:
        return {
            "title": "Grid Context / Power Access Context",
            "included": False,
        }

    selected = grid_context["selected"]
    summary = selected["summary"]
    score = selected["score"]
    assets = list(selected["assets"])

    display_assets = _select_grid_display_assets(assets)
    display_asset_ids = {asset["asset_id"] for asset in display_assets}
    omitted_asset_count = sum(1 for asset in assets if asset["asset_id"] not in display_asset_ids)
    voltage_classes = sorted(
        {asset["voltage_kv"] for asset in display_assets if asset.get("voltage_kv") is not None},
        reverse=True,
    )

    official = selected["official_evidence"] or {}
    official_items = [
        _fact("Reference", official.get("utility_or_tso_reference")),
        _fact("Reference date", official.get("reference_date")),
        _fact("Confirmed substation", official.get("confirmed_substation_name")),
        _fact(
            "Confirmed voltage",
            _display_number(official.get("confirmed_voltage_kv"), digits=0, suffix="kV"),
        ),
        _fact(
            "Requested capacity",
            _display_number(official.get("confirmed_requested_mw"), digits=2, suffix="MW"),
        ),
        _fact(
            "Available capacity",
            _display_number(official.get("confirmed_available_mw"), digits=2, suffix="MW"),
        ),
        _fact("Connection status", official.get("connection_status")),
        _fact("Timeline status", official.get("timeline_status")),
        _fact("Notes", official.get("notes")),
    ]
    official_items = [item for item in official_items if item["value"] != "Not available"]

    asset_rows = [
        {
            "asset_type": _display_text(asset.get("asset_type")),
            "name": _display_text(asset.get("name")),
            "operator": _display_text(asset.get("operator")),
            "voltage": _display_number(asset.get("voltage_kv"), digits=0, suffix="kV"),
            "distance": _display_number(asset.get("distance_km"), digits=2, suffix="km"),
            "confidence": _display_text(asset.get("confidence")),
        }
        for asset in display_assets
    ]

    score_items = []
    score_notes: list[str] = []
    if score is not None:
        score_items = [
            _fact("Heuristic score", _display_number(score.get("overall_score"), digits=1)),
            _fact("Voltage score", _display_number(score.get("voltage_score"), digits=1)),
            _fact("Distance score", _display_number(score.get("distance_score"), digits=1)),
            _fact(
                "Substation score",
                _display_number(score.get("substation_score"), digits=1),
            ),
            _fact("Evidence score", _display_number(score.get("evidence_score"), digits=1)),
        ]
        score_notes = [
            _display_text(note, default="")
            for note in score.get("notes", [])
            if _display_text(note, default="")
        ]

    evidence_notes = [
        f'{_display_text(note.get("label"))}: {_display_text(note.get("detail"))}'
        for note in selected["evidence_notes"]
    ]
    evidence_notes.extend(
        _display_text(note, default="")
        for note in selected["official_context_notes"]
        if _display_text(note, default="")
    )
    if grid_context.get("message"):
        evidence_notes.append(grid_context["message"])

    # Generate real tile-based grid context map
    grid_map_uri = None
    grid_lat = selected.get("latitude") or site_data["location"].get("latitude")
    grid_lon = selected.get("longitude") or site_data["location"].get("longitude")
    if grid_lat is not None and grid_lon is not None:
        grid_map_uri = generate_grid_context_base64(
            grid_lat,
            grid_lon,
            assets=display_assets,
            radius_km=summary.get("radius_km"),
        )

    return {
        "title": "Grid Context / Power Access Context",
        "included": True,
        "grid_context_map": grid_map_uri,
        "map_visual": build_grid_context_map_visual(
            site_data,
            grid_center=(selected.get("latitude"), selected.get("longitude")),
            radius_km=summary.get("radius_km"),
            assets=display_assets,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "summary_items": [
            _fact("Search radius", _display_number(summary.get("radius_km"), digits=1, suffix="km")),
            _fact(
                "Nearby lines",
                _display_number(summary.get("nearby_line_count"), digits=0),
            ),
            _fact(
                "Nearby substations",
                _display_number(summary.get("nearby_substation_count"), digits=0),
            ),
            _fact(
                "Nearest line",
                _display_number(summary.get("nearest_line_km"), digits=2, suffix="km"),
            ),
            _fact(
                "Nearest substation",
                _display_number(summary.get("nearest_substation_km"), digits=2, suffix="km"),
            ),
            _fact(
                "Maximum mapped voltage",
                _display_number(summary.get("max_voltage_kv"), digits=0, suffix="kV"),
            ),
            _fact(
                "High-voltage assets within radius",
                _display_number(summary.get("high_voltage_assets_within_radius"), digits=0),
            ),
            _fact("Voltage classes shown", _display_list([f"{value:.0f} kV" for value in voltage_classes])),
            _fact("Confidence", selected["confidence"]),
            _fact("Source layers", _display_list(selected["source_layers"])),
        ],
        "score_items": score_items,
        "score_notes": score_notes,
        "official_items": official_items,
        "asset_rows": asset_rows,
        "asset_count": selected["asset_count"],
        "omitted_asset_count": omitted_asset_count,
        "evidence_notes": evidence_notes,
        "narrative": _build_grid_context_narrative(
            summary=summary,
            score=score,
            has_official_evidence=bool(selected["official_evidence"]),
        ),
    }


def _build_climate_delta_rows(
    delta_results: dict[str, list[dict[str, Any]]],
    selected_cooling_type: str | None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def _delta_sort_key(item: tuple[str, list[dict[str, Any]]]) -> float:
        try:
            return float(item[0])
        except (TypeError, ValueError):
            return float("inf")

    for delta, analyses in sorted(delta_results.items(), key=_delta_sort_key):
        chosen = None
        if selected_cooling_type is not None:
            chosen = next(
                (
                    item
                    for item in analyses
                    if item.get("cooling_type") == selected_cooling_type
                ),
                None,
            )
        if chosen is None and analyses:
            chosen = analyses[0]
        if chosen is None:
            continue
        rows.append(
            {
                "delta": f"+{delta} C",
                "cooling_type": _display_text(chosen.get("cooling_type")),
                "free_cooling_hours": _display_number(
                    chosen.get("free_cooling_hours"),
                    digits=0,
                ),
                "free_cooling_fraction": _display_percent(
                    chosen.get("free_cooling_fraction"),
                    digits=1,
                ),
                "suitability": _display_text(chosen.get("suitability")),
            }
        )
    return rows


def _build_climate_chapter(
    climate: dict[str, Any],
    primary_result: dict[str, Any] | None,
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    if climate["status"] != "available" or climate["analysis"] is None:
        return {
            "title": "Climate Study",
            "included": False,
        }

    weather_status = climate["weather_status"] or {}
    analysis = climate["analysis"]
    temperature_stats = analysis["temperature_stats"]
    monthly_stats = analysis["monthly_stats"] or {}
    selected_cooling_type = (
        primary_result["scenario"]["cooling_type"] if primary_result is not None else None
    )

    monthly_rows = []
    monthly_mean = monthly_stats.get("monthly_mean") or []
    monthly_min = monthly_stats.get("monthly_min") or []
    monthly_max = monthly_stats.get("monthly_max") or []
    for index, month_name in enumerate(MONTH_NAMES):
        if index >= len(monthly_mean):
            break
        monthly_rows.append(
            {
                "month": month_name,
                "mean": _display_number(monthly_mean[index], digits=1, suffix="C"),
                "min": _display_number(monthly_min[index], digits=1, suffix="C"),
                "max": _display_number(monthly_max[index], digits=1, suffix="C"),
            }
        )

    free_cooling_rows = [
        {
            "cooling_type": _display_text(item.get("cooling_type")),
            "threshold": _display_text(item.get("threshold_description")),
            "free_cooling_hours": _display_number(
                item.get("free_cooling_hours"),
                digits=0,
            ),
            "free_cooling_fraction": _display_percent(
                item.get("free_cooling_fraction"),
                digits=1,
            ),
            "suitability": _display_text(item.get("suitability")),
            "is_selected": item.get("cooling_type") == selected_cooling_type,
        }
        for item in analysis["free_cooling"]
    ]
    selected_free_cooling = next(
        (row for row in free_cooling_rows if row["is_selected"]),
        None,
    )

    best_free_cooling = analysis.get("best_free_cooling") or {}

    return {
        "title": "Climate Study",
        "included": True,
        "monthly_chart_visual": build_monthly_temperature_chart(
            monthly_stats if monthly_stats else None,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "free_cooling_chart_visual": build_free_cooling_chart(
            analysis["free_cooling"],
            selected_cooling_type=selected_cooling_type,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "weather_items": [
            _fact("Weather source", weather_status.get("source")),
            _fact("Source type", weather_status.get("source_type")),
            _fact("Hours analysed", _display_number(weather_status.get("hours"), digits=0)),
            _fact(
                "Humidity available",
                _display_bool(weather_status.get("has_humidity")),
            ),
            _fact("Uploaded file", weather_status.get("original_filename")),
            _fact(
                "Years averaged",
                _display_list(weather_status.get("years_averaged") or []),
            ),
            _fact(
                "Weather coordinates",
                _display_coordinates(
                    weather_status.get("latitude"),
                    weather_status.get("longitude"),
                ),
            ),
        ],
        "temperature_items": [
            _fact("Sample count", _display_number(temperature_stats.get("count"), digits=0)),
            _fact("Mean dry-bulb", _display_number(temperature_stats.get("mean"), digits=2, suffix="C")),
            _fact("Minimum", _display_number(temperature_stats.get("min"), digits=2, suffix="C")),
            _fact("Maximum", _display_number(temperature_stats.get("max"), digits=2, suffix="C")),
            _fact("Median", _display_number(temperature_stats.get("median"), digits=2, suffix="C")),
            _fact("P01", _display_number(temperature_stats.get("p1"), digits=2, suffix="C")),
            _fact("P99", _display_number(temperature_stats.get("p99"), digits=2, suffix="C")),
            _fact(
                "Standard deviation",
                _display_number(temperature_stats.get("std_dev"), digits=2, suffix="C"),
            ),
        ],
        "best_free_cooling_summary": [
            _fact("Best cooling type", best_free_cooling.get("cooling_type")),
            _fact(
                "Best free cooling hours",
                _display_number(best_free_cooling.get("free_cooling_hours"), digits=0),
            ),
            _fact(
                "Best free cooling fraction",
                _display_percent(best_free_cooling.get("free_cooling_fraction"), digits=1),
            ),
            _fact("Best suitability", best_free_cooling.get("suitability")),
        ],
        "monthly_rows": monthly_rows,
        "monthly_message": (
            ""
            if monthly_rows
            else "Monthly temperature breakout is only available when a full 8,760-hour weather year is present."
        ),
        "free_cooling_rows": free_cooling_rows,
        "delta_rows": _build_climate_delta_rows(
            analysis["delta_results"],
            selected_cooling_type,
        ),
        "narrative": _build_climate_narrative(
            weather_status=weather_status,
            temperature_stats=temperature_stats,
            selected_cooling_type=selected_cooling_type,
            selected_free_cooling=selected_free_cooling,
            best_free_cooling=best_free_cooling,
        ),
    }


def _build_selected_scenario_chapter(primary_result: dict[str, Any] | None) -> dict[str, Any]:
    if primary_result is None:
        return {
            "title": "Selected Scenario",
            "available": False,
            "message": "No primary scenario was selected for this site.",
        }

    scenario = primary_result["scenario"]
    feature_flags = primary_result["feature_flags"]
    overrides = primary_result["applied_assumption_overrides"]

    assumption_rows = [
        {
            "label": _display_text(override.get("label")),
            "scope": _display_text(override.get("scope_label")),
            "parameter": _display_text(override.get("parameter_label")),
            "effective_value": (
                f'{override.get("effective_value")} {override.get("unit") or ""}'.strip()
            ),
            "origin": _display_text(override.get("origin")),
            "source": _display_text(override.get("source")),
        }
        for override in overrides
    ]

    summary_items = [
        _fact("Load type", scenario["load_type"]),
        _fact("Cooling type", scenario["cooling_type"]),
        _fact("Redundancy", scenario["redundancy"]),
        _fact("Density scenario", scenario["density_scenario"]),
        _fact("Backup power", scenario["backup_power"]),
        _fact(
            "Hourly simulation used",
            _display_bool(
                feature_flags["has_hourly_pue"],
                true_label="Yes",
                false_label="No",
            ),
        ),
        _fact("PUE source", primary_result["metrics"]["pue_source"]),
        _fact(
            "Selected rank within site",
            _display_number(primary_result["rank_within_site"], digits=0),
        ),
        _fact(
            "Selected rank across studied sites",
            _display_number(primary_result["selected_primary_rank"], digits=0),
        ),
        _fact(
            "Scenario-local preset",
            scenario["assumption_override_preset_label"]
            or scenario["assumption_override_preset_key"],
        ),
        _fact(
            "Manual PUE override",
            _display_number(scenario["pue_override"], digits=2),
        ),
        _fact(
            "Applied assumption overrides",
            _display_number(len(overrides), digits=0),
        ),
    ]

    return {
        "title": "Selected Scenario",
        "available": True,
        "label": primary_result["label"],
        "summary_items": summary_items,
        "assumption_rows": assumption_rows,
        "narrative": _build_selected_scenario_narrative(
            scenario=scenario,
            feature_flags=feature_flags,
            override_count=len(overrides),
        ),
    }


def _build_deep_dive_chapter(
    primary_result: dict[str, Any] | None,
    site_data: dict[str, Any],
    *,
    site: Site | None = None,
    primary_scenario_result: ScenarioResult | None = None,
) -> dict[str, Any]:
    if primary_result is None:
        return {
            "title": "Scenario Results Deep Dive",
            "available": False,
            "message": "No primary scenario results are available for deep-dive reporting.",
        }

    metrics = primary_result["metrics"]
    space = primary_result["space"]
    power = primary_result["power"]
    status = primary_result["status"]
    feature_flags = primary_result["feature_flags"]
    advanced_blocks = (
        _build_advanced_result_blocks(
            site=site,
            primary_result=primary_scenario_result,
        )
        if site is not None and primary_scenario_result is not None
        else []
    )

    return {
        "title": "Scenario Results Deep Dive",
        "available": True,
        "headline_metrics": [
            _fact("Score", _display_number(metrics["score"], digits=2)),
            _fact(
                "Committed IT capacity",
                _display_number(metrics["committed_it_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Facility power",
                _display_number(metrics["facility_power_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Annual PUE",
                _display_number(metrics["pue"], digits=2),
            ),
            _fact(
                "Procurement power",
                _display_number(metrics["procurement_power_mw"], digits=2, suffix="MW"),
            ),
        ],
        "status_items": [
            _fact("RAG status", status["rag_status"]),
            _fact("Binding constraint", metrics["binding_constraint"]),
            _fact(
                "Scenario compatibility",
                _display_bool(
                    primary_result["compatible_combination"],
                    true_label="Compatible",
                    false_label="Compatibility flag raised",
                ),
            ),
            _fact(
                "Global rank across all results",
                _display_number(primary_result["global_rank"], digits=0),
            ),
            _fact(
                "Primary rank across studied sites",
                _display_number(primary_result["selected_primary_rank"], digits=0),
            ),
        ],
        "status_reasons": [
            _display_text(reason, default="")
            for reason in status["rag_reasons"]
            if _display_text(reason, default="")
        ],
        "capacity_items": [
            _fact(
                "IT load used for result",
                _display_number(metrics["it_load_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Worst-hour IT capacity",
                _display_number(metrics["it_capacity_worst_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "P99 IT capacity",
                _display_number(metrics["it_capacity_p99_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "P90 IT capacity",
                _display_number(metrics["it_capacity_p90_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Mean IT capacity",
                _display_number(metrics["it_capacity_mean_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Best-hour IT capacity",
                _display_number(metrics["it_capacity_best_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Overtemperature hours",
                _display_number(metrics["overtemperature_hours"], digits=0),
            ),
        ],
        "space_items": [
            _fact(
                "Buildable footprint",
                _display_number(space["buildable_footprint_m2"], digits=0, suffix="m2"),
            ),
            _fact(
                "Gross building area",
                _display_number(space["gross_building_area_m2"], digits=0, suffix="m2"),
            ),
            _fact(
                "IT whitespace",
                _display_number(space["it_whitespace_m2"], digits=0, suffix="m2"),
            ),
            _fact(
                "Support area",
                _display_number(space["support_area_m2"], digits=0, suffix="m2"),
            ),
            _fact(
                "Effective racks",
                _display_number(space["effective_racks"], digits=0),
            ),
            _fact(
                "Maximum racks by space",
                _display_number(space["max_racks_by_space"], digits=0),
            ),
            _fact(
                "Whitespace adjustment factor",
                _display_number(space["whitespace_adjustment_factor"], digits=2),
            ),
            _fact(
                "Expansion floors reserved",
                _display_number(space.get("expansion_floors"), digits=0),
            ),
            _fact(
                "Expansion racks",
                _display_number(space.get("expansion_racks"), digits=0),
            ),
        ],
        "power_items": [
            _fact(
                "Declared site power",
                _display_number(
                    site_data["power"]["available_power_mw"],
                    digits=2,
                    suffix="MW",
                ),
            ),
            _fact(
                "Facility power",
                _display_number(power["facility_power_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Procurement power",
                _display_number(power["procurement_power_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Racks deployed",
                _display_number(power["racks_deployed"], digits=0),
            ),
            _fact(
                "Racks by power",
                _display_number(power["racks_by_power"], digits=0),
            ),
            _fact(
                "Rack density",
                _display_number(power["rack_density_kw"], digits=1, suffix="kW"),
            ),
            _fact(
                "Power headroom",
                _display_number(power["power_headroom_mw"], digits=2, suffix="MW"),
            ),
            _fact("Power input mode", power["power_input_mode"]),
            _fact("Eta chain", _display_number(power["eta_chain"], digits=2)),
            _fact(
                "Procurement factor",
                _display_number(power["procurement_factor"], digits=2),
            ),
        ],
        "availability_items": [
            _fact(
                "Hourly PUE data",
                _display_bool(feature_flags["has_hourly_pue"]),
            ),
            _fact(
                "IT capacity spectrum",
                _display_bool(feature_flags["has_it_capacity_spectrum"]),
            ),
            _fact(
                "Manual PUE override",
                _display_bool(feature_flags["has_pue_override"]),
            ),
            _fact(
                "Assumption overrides applied",
                _display_bool(feature_flags["has_assumption_overrides"]),
            ),
        ],
        "advanced_blocks": advanced_blocks,
        "advanced_block_count": len(advanced_blocks),
        "narrative": _build_deep_dive_narrative(
            metrics=metrics,
            status=status,
            compatible_combination=primary_result["compatible_combination"],
        ),
    }


def _build_load_mix_chapter(
    load_mix: dict[str, Any],
    primary_result: dict[str, Any] | None,
) -> dict[str, Any]:
    result = load_mix.get("result")
    if load_mix.get("status") != "available" or result is None:
        return {
            "title": "Load Mix Scenario",
            "included": False,
        }

    candidates = result.get("top_candidates") or []
    top_candidate = candidates[0] if candidates else None
    allowed_load_types = result.get("allowed_load_types") or []

    input_items = [
        _fact(
            "Primary scenario context",
            primary_result["label"] if primary_result is not None else None,
        ),
        _fact(
            "Allowed load types",
            _display_list(allowed_load_types, default="Not available"),
        ),
        _fact(
            "Total IT target",
            _display_number(result.get("total_it_mw"), digits=2, suffix="MW"),
        ),
        _fact("Cooling type", result.get("cooling_type")),
        _fact("Density scenario", result.get("density_scenario")),
        _fact(
            "Step size",
            _display_number(result.get("step_pct"), digits=0, suffix="%"),
        ),
        _fact(
            "Minimum racks per type",
            _display_number(result.get("min_racks"), digits=0),
        ),
        _fact(
            "Candidates evaluated",
            _display_number(result.get("total_candidates_evaluated"), digits=0),
        ),
    ]

    if top_candidate is None:
        return {
            "title": "Load Mix Scenario",
            "included": True,
            "has_candidates": False,
            "input_items": input_items,
            "headline_items": [],
            "top_candidate_table": None,
            "ranked_candidates_table": None,
            "top_candidate_notes": [],
            "message": (
                "The load-mix optimizer data was available, but no ranked candidate "
                "mixes were returned for these assumptions."
            ),
            "narrative": _build_load_mix_narrative(
                total_it_mw=result.get("total_it_mw"),
                total_candidates_evaluated=result.get("total_candidates_evaluated"),
                top_candidate=None,
            ),
        }

    top_candidate_allocations = top_candidate.get("allocations") or []
    ranked_rows = [
        {
            "rank": _display_number(candidate.get("rank"), digits=0),
            "score": _display_number(candidate.get("score"), digits=1),
            "blended_pue": _display_number(candidate.get("blended_pue"), digits=3),
            "compatible": _display_bool(
                candidate.get("all_compatible"),
                true_label="Compatible",
                false_label="Needs review",
            ),
            "total_racks": _display_number(candidate.get("total_racks"), digits=0),
            "allocation_summary": _summarize_load_mix_allocations(
                candidate.get("allocations") or []
            ),
        }
        for candidate in candidates[:5]
    ]

    return {
        "title": "Load Mix Scenario",
        "included": True,
        "has_candidates": True,
        "input_items": input_items,
        "headline_items": [
            _fact(
                "Top candidate score",
                _display_number(top_candidate.get("score"), digits=1),
            ),
            _fact(
                "Top candidate blended PUE",
                _display_number(top_candidate.get("blended_pue"), digits=3),
            ),
            _fact(
                "Top candidate racks",
                _display_number(top_candidate.get("total_racks"), digits=0),
            ),
            _fact(
                "Top candidate compatibility",
                _display_bool(
                    top_candidate.get("all_compatible"),
                    true_label="Compatible",
                    false_label="Needs review",
                ),
            ),
        ],
        "top_candidate_table": _table(
            "Top candidate mix",
            [
                ("load_type", "Load Type"),
                ("share_pct", "Share"),
                ("it_load_mw", "IT MW"),
                ("rack_count", "Racks"),
                ("rack_density_kw", "Rack Density"),
            ],
            [
                {
                    "load_type": _display_text(allocation.get("load_type")),
                    "share_pct": _display_number(
                        allocation.get("share_pct"),
                        digits=0,
                        suffix="%",
                    ),
                    "it_load_mw": _display_number(
                        allocation.get("it_load_mw"),
                        digits=2,
                        suffix="MW",
                    ),
                    "rack_count": _display_number(
                        allocation.get("rack_count"),
                        digits=0,
                    ),
                    "rack_density_kw": _display_number(
                        allocation.get("rack_density_kw"),
                        digits=1,
                        suffix="kW/rack",
                    ),
                }
                for allocation in top_candidate_allocations
            ],
        ),
        "ranked_candidates_table": _table(
            "Ranked candidate overview",
            [
                ("rank", "Rank"),
                ("score", "Score"),
                ("blended_pue", "Blended PUE"),
                ("compatible", "Compatibility"),
                ("total_racks", "Total Racks"),
                ("allocation_summary", "Allocation Summary"),
            ],
            ranked_rows,
        ),
        "top_candidate_notes": _clean_notes(top_candidate.get("trade_off_notes")),
        "message": None,
        "narrative": _build_load_mix_narrative(
            total_it_mw=result.get("total_it_mw"),
            total_candidates_evaluated=result.get("total_candidates_evaluated"),
            top_candidate=top_candidate,
        ),
    }


def _build_green_energy_chapter(green_energy: dict[str, Any]) -> dict[str, Any]:
    result = green_energy.get("result")
    if green_energy.get("status") != "available" or result is None:
        return {
            "title": "Green Energy",
            "included": False,
        }

    pv_profile_source = _display_text(
        result.get("pv_profile_source"),
        default="zero",
    ).lower()
    pvgis_profile = green_energy.get("pvgis_profile")
    pv_profile_name = green_energy.get("pv_profile_name")

    if pv_profile_source == "pvgis":
        provenance_items = [
            _fact("PV source", "Cached PVGIS normalized profile"),
            _fact("PVGIS profile key", result.get("pvgis_profile_key")),
            _fact(
                "PVGIS years",
                _display_list((pvgis_profile or {}).get("years_averaged") or []),
            ),
            _fact("PV technology", (pvgis_profile or {}).get("pv_technology")),
            _fact("Mounting place", (pvgis_profile or {}).get("mounting_place")),
            _fact(
                "System loss",
                _display_number(
                    (pvgis_profile or {}).get("system_loss_pct"),
                    digits=1,
                    suffix="%",
                ),
            ),
            _fact(
                "Radiation database",
                (pvgis_profile or {}).get("radiation_database"),
            ),
            _fact("Source", (pvgis_profile or {}).get("source")),
        ]
    elif pv_profile_source == "manual":
        provenance_items = [
            _fact("PV source", "Manual hourly PV upload"),
            _fact("Uploaded profile", pv_profile_name),
        ]
    else:
        provenance_items = [
            _fact("PV source", "No PV profile applied"),
            _fact(
                "Provenance note",
                "Dispatch used the saved scenario load with zero PV generation input.",
            ),
        ]

    bess_initial_soc_kwh = green_energy.get("bess_initial_soc_kwh")

    return {
        "title": "Green Energy",
        "included": True,
        "headline_items": [
            _fact(
                "Renewable fraction",
                _display_percent(result.get("renewable_fraction"), digits=1),
            ),
            _fact(
                "Overhead coverage",
                _display_percent(
                    result.get("overhead_coverage_fraction"),
                    digits=1,
                ),
            ),
            _fact(
                "CO2 avoided",
                _display_number(
                    result.get("co2_avoided_tonnes"),
                    digits=1,
                    suffix="tCO2",
                ),
            ),
            _fact(
                "Grid import",
                _display_energy_mwh(result.get("total_grid_import_kwh")),
            ),
        ],
        "configuration_items": [
            _fact(
                "PV capacity",
                _display_number(result.get("pv_capacity_kwp"), digits=0, suffix="kWp"),
            ),
            _fact(
                "BESS capacity",
                _display_number(
                    (result.get("bess_capacity_kwh") or 0) / 1000.0,
                    digits=2,
                    suffix="MWh",
                ),
            ),
            _fact(
                "Initial BESS state of charge",
                _display_number(
                    (
                        bess_initial_soc_kwh / 1000.0
                        if bess_initial_soc_kwh is not None
                        else None
                    ),
                    digits=2,
                    suffix="MWh",
                ),
            ),
            _fact(
                "BESS round-trip efficiency",
                _display_percent(
                    result.get("bess_roundtrip_efficiency"),
                    digits=1,
                ),
            ),
            _fact(
                "Fuel cell capacity",
                _display_number(
                    result.get("fuel_cell_capacity_kw"),
                    digits=0,
                    suffix="kW",
                ),
            ),
            _fact(
                "Grid CO2 factor",
                _display_number(
                    green_energy.get("grid_co2_kg_per_kwh"),
                    digits=3,
                    suffix="kg/kWh",
                ),
            ),
        ],
        "context_items": [
            _fact(
                "Nominal IT capacity",
                _display_number(result.get("nominal_it_mw"), digits=2, suffix="MW"),
            ),
            _fact(
                "Committed IT capacity",
                _display_number(
                    result.get("committed_it_mw"),
                    digits=2,
                    suffix="MW",
                ),
            ),
            _fact(
                "Annual PUE",
                _display_number(result.get("annual_pue"), digits=3),
            ),
            _fact("PUE source", result.get("pue_source")),
            _fact("PV profile source", result.get("pv_profile_source")),
            _fact(
                "Dispatch hours",
                _display_number(result.get("hours"), digits=0),
            ),
            _fact(
                "PV self-consumption",
                _display_percent(
                    result.get("pv_self_consumption_fraction"),
                    digits=1,
                ),
            ),
            _fact(
                "BESS equivalent cycles",
                _display_number(
                    result.get("bess_cycles_equivalent"),
                    digits=2,
                ),
            ),
        ],
        "provenance_items": provenance_items,
        "energy_breakdown_table": _table(
            "Annual energy breakdown",
            [
                ("label", "Energy Stream"),
                ("value", "Annual Value"),
            ],
            [
                {
                    "label": "Total facility energy",
                    "value": _display_energy_mwh(result.get("total_facility_kwh")),
                },
                {
                    "label": "Total IT energy",
                    "value": _display_energy_mwh(result.get("total_it_kwh")),
                },
                {
                    "label": "Total overhead energy",
                    "value": _display_energy_mwh(result.get("total_overhead_kwh")),
                },
                {
                    "label": "PV generation",
                    "value": _display_energy_mwh(result.get("total_pv_generation_kwh")),
                },
                {
                    "label": "PV direct to overhead",
                    "value": _display_energy_mwh(result.get("total_pv_to_overhead_kwh")),
                },
                {
                    "label": "PV to BESS",
                    "value": _display_energy_mwh(result.get("total_pv_to_bess_kwh")),
                },
                {
                    "label": "PV curtailed",
                    "value": _display_energy_mwh(result.get("total_pv_curtailed_kwh")),
                },
                {
                    "label": "BESS discharge",
                    "value": _display_energy_mwh(result.get("total_bess_discharge_kwh")),
                },
                {
                    "label": "Fuel cell dispatch",
                    "value": _display_energy_mwh(result.get("total_fuel_cell_kwh")),
                },
                {
                    "label": "Grid import",
                    "value": _display_energy_mwh(result.get("total_grid_import_kwh")),
                },
            ],
        ),
        "narrative": _build_green_energy_narrative(
            result=result,
            pv_profile_source=pv_profile_source,
        ),
    }


def _table(
    title: str,
    columns: list[tuple[str, str]],
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "title": title,
        "columns": [{"key": key, "label": label} for key, label in columns],
        "rows": rows,
    }


def _clean_notes(values: list[Any] | None) -> list[str]:
    notes: list[str] = []
    for value in values or []:
        text = _display_text(value, default="")
        if text:
            notes.append(text)
    return notes


def _build_advanced_block(
    key: str,
    title: str,
    *,
    summary_items: list[dict[str, str]] | None = None,
    tables: list[dict[str, Any]] | None = None,
    notes: list[Any] | None = None,
) -> dict[str, Any] | None:
    cleaned_tables = [table for table in tables or [] if table.get("rows")]
    cleaned_notes = _clean_notes(notes)
    if not (summary_items or cleaned_tables or cleaned_notes):
        return None

    return {
        "key": key,
        "title": title,
        "summary_items": summary_items or [],
        "tables": cleaned_tables,
        "notes": cleaned_notes,
    }


def _analysis_land_area_m2(site: Site, result: ScenarioResult) -> float:
    coverage = result.space.site_coverage_used
    if coverage > 0:
        return result.space.buildable_footprint_m2 / coverage
    return site.land_area_m2


def _analysis_available_power_mw(result: ScenarioResult) -> float:
    procurement_factor = result.power.procurement_factor
    if procurement_factor > 0:
        return result.power.procurement_power_mw / procurement_factor
    return result.power.facility_power_mw


def _build_daily_profiles_from_sim(sim: Any) -> dict[str, Any]:
    daily_points: list[dict[str, Any]] = []

    for start in range(0, len(sim.hourly_pue), 24):
        day_number = start // 24 + 1
        pue_slice = sim.hourly_pue[start:start + 24]
        it_slice_kw = sim.hourly_it_kw[start:start + 24]

        if not pue_slice or not it_slice_kw:
            continue

        daily_points.append(
            {
                "day": day_number,
                "it_avg_mw": round(sum(it_slice_kw) / len(it_slice_kw) / 1000.0, 3),
                "it_min_mw": round(min(it_slice_kw) / 1000.0, 3),
                "it_max_mw": round(max(it_slice_kw) / 1000.0, 3),
                "pue_avg": round(sum(pue_slice) / len(pue_slice), 4),
                "pue_min": round(min(pue_slice), 4),
                "pue_max": round(max(pue_slice), 4),
            }
        )

    return {
        "hours": len(sim.hourly_pue),
        "day_count": len(daily_points),
        "annual_pue": round(sim.annual_pue, 4),
        "annual_mean_it_mw": round(sim.it_capacity_mean_kw / 1000.0, 3),
        "committed_it_mw": round(sim.it_capacity_p99_kw / 1000.0, 3),
        "worst_it_mw": round(sim.it_capacity_worst_kw / 1000.0, 3),
        "best_it_mw": round(sim.it_capacity_best_kw / 1000.0, 3),
        "days": daily_points,
    }


def _load_hourly_analysis(
    site_id: str,
    site: Site,
    result: ScenarioResult,
) -> dict[str, Any] | None:
    if result.pue_source != "hourly" or result.annual_pue is None:
        return None
    if not result.compatible_combination or result.power.it_load_mw <= 0:
        return None

    weather = get_weather(site_id)
    if weather is None:
        return None

    temperatures = weather.get("temperatures") or []
    humidities = weather.get("humidities")
    if not temperatures:
        return None

    try:
        if site.power_confirmed and site.available_power_mw > 0:
            sim = simulate_hourly(
                temperatures=temperatures,
                humidities=humidities,
                cooling_type=result.scenario.cooling_type.value,
                eta_chain=result.power.eta_chain,
                facility_power_kw=result.power.facility_power_mw * 1000,
                override_preset_key=result.scenario.assumption_override_preset_key,
            )
        else:
            sim = simulate_hourly(
                temperatures=temperatures,
                humidities=humidities,
                cooling_type=result.scenario.cooling_type.value,
                eta_chain=result.power.eta_chain,
                it_load_kw=result.power.it_load_mw * 1000,
                override_preset_key=result.scenario.assumption_override_preset_key,
            )
        hourly_factors = build_hourly_facility_factors(
            temperatures=temperatures,
            humidities=humidities,
            cooling_type=result.scenario.cooling_type.value,
            eta_chain=result.power.eta_chain,
        )
    except ValueError:
        return None

    return {
        "weather": weather,
        "sim": sim,
        "hourly_factors": hourly_factors,
        "daily_profiles": _build_daily_profiles_from_sim(sim),
    }


def _build_pue_decomposition_block(
    hourly_analysis: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if hourly_analysis is None:
        return None

    sim = hourly_analysis["sim"]
    total_overhead = sim.total_overhead_kwh
    components = [
        {
            "label": "Electrical losses",
            "energy_kwh": round(sim.total_electrical_losses_kwh, 1),
        },
        {
            "label": "Fans and pumps",
            "energy_kwh": round(sim.total_fan_pump_kwh, 1),
        },
        {
            "label": "Cooling compressor and heat rejection",
            "energy_kwh": round(sim.total_cooling_kwh, 1),
        },
        {
            "label": "Economizer overhead",
            "energy_kwh": round(sim.total_economizer_kwh, 1),
        },
        {
            "label": "Miscellaneous fixed loads",
            "energy_kwh": round(sim.total_misc_kwh, 1),
        },
    ]
    component_rows = [
        {
            "component": item["label"],
            "energy_kwh": _display_number(item["energy_kwh"], digits=0, suffix="kWh"),
            "share_of_overhead": _display_percent(
                item["energy_kwh"] / total_overhead if total_overhead > 0 else 0.0,
                digits=1,
            ),
        }
        for item in components
    ]
    mode_rows = [
        {
            "mode": "Mechanical cooling",
            "hours": _display_number(sim.mech_hours, digits=0),
        },
        {
            "mode": "Partial economizer",
            "hours": _display_number(sim.econ_part_hours, digits=0),
        },
        {
            "mode": "Full economizer",
            "hours": _display_number(sim.econ_full_hours, digits=0),
        },
        {
            "mode": "Overtemperature",
            "hours": _display_number(sim.overtemperature_hours, digits=0),
        },
    ]

    return _build_advanced_block(
        "pue_decomposition",
        "PUE Decomposition",
        summary_items=[
            _fact("Annual PUE", _display_number(sim.annual_pue, digits=3)),
            _fact("Total overhead", _display_number(total_overhead, digits=0, suffix="kWh")),
            _fact(
                "Facility energy",
                _display_number(sim.total_facility_kwh, digits=0, suffix="kWh"),
            ),
            _fact("IT energy", _display_number(sim.total_it_kwh, digits=0, suffix="kWh")),
        ],
        tables=[
            _table(
                "Annual overhead components",
                [
                    ("component", "Component"),
                    ("energy_kwh", "Energy"),
                    ("share_of_overhead", "Share of overhead"),
                ],
                component_rows,
            ),
            _table(
                "Cooling-mode hours",
                [("mode", "Mode"), ("hours", "Hours")],
                mode_rows,
            ),
        ],
        notes=[
            "Derived from the representative hourly simulation used for the annual PUE result.",
        ],
    )


def _build_hourly_profiles_block(
    hourly_analysis: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if hourly_analysis is None:
        return None

    profiles = hourly_analysis["daily_profiles"]
    days = profiles["days"]
    if not days:
        return None

    peak_it_day = max(days, key=lambda day: (day["it_max_mw"], -day["day"]))
    trough_it_day = min(days, key=lambda day: (day["it_min_mw"], day["day"]))
    peak_pue_day = max(days, key=lambda day: (day["pue_max"], -day["day"]))
    trough_pue_day = min(days, key=lambda day: (day["pue_min"], day["day"]))

    representative_rows = [
        ("Peak IT day", peak_it_day),
        ("Lowest IT day", trough_it_day),
        ("Peak PUE day", peak_pue_day),
        ("Lowest PUE day", trough_pue_day),
    ]
    rows = [
        {
            "marker": marker,
            "day": _display_number(day["day"], digits=0),
            "it_range": (
                f'{_display_number(day["it_min_mw"], digits=2)} - '
                f'{_display_number(day["it_max_mw"], digits=2)} MW'
            ),
            "it_avg": _display_number(day["it_avg_mw"], digits=2, suffix="MW"),
            "pue_range": (
                f'{_display_number(day["pue_min"], digits=3)} - '
                f'{_display_number(day["pue_max"], digits=3)}'
            ),
            "pue_avg": _display_number(day["pue_avg"], digits=3),
        }
        for marker, day in representative_rows
    ]

    return _build_advanced_block(
        "hourly_profiles",
        "Hourly Profiles",
        summary_items=[
            _fact(
                "Committed IT",
                _display_number(profiles["committed_it_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Annual mean IT",
                _display_number(profiles["annual_mean_it_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Worst-hour IT",
                _display_number(profiles["worst_it_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Best-hour IT",
                _display_number(profiles["best_it_mw"], digits=2, suffix="MW"),
            ),
            _fact("Annual PUE", _display_number(profiles["annual_pue"], digits=3)),
            _fact(
                "Peak daily IT",
                _display_number(peak_it_day["it_max_mw"], digits=2, suffix="MW"),
            ),
            _fact("Peak daily PUE", _display_number(peak_pue_day["pue_max"], digits=3)),
            _fact(
                "Representative days",
                _display_number(profiles["day_count"], digits=0),
            ),
        ],
        tables=[
            _table(
                "Representative daily operating markers",
                [
                    ("marker", "Marker"),
                    ("day", "Day"),
                    ("it_range", "IT range"),
                    ("it_avg", "IT average"),
                    ("pue_range", "PUE range"),
                    ("pue_avg", "PUE average"),
                ],
                rows,
            ),
        ],
        notes=[
            "Daily values aggregate 24-hour slices from the representative hourly weather year.",
        ],
    )


def _build_it_capacity_spectrum_block(result: ScenarioResult) -> dict[str, Any] | None:
    spectrum_rows = [
        ("Nominal design", result.power.it_load_mw),
        ("Worst hour", result.it_capacity_worst_mw),
        ("P99", result.it_capacity_p99_mw),
        ("P90", result.it_capacity_p90_mw),
        ("Mean", result.it_capacity_mean_mw),
        ("Best hour", result.it_capacity_best_mw),
    ]
    available_rows = [row for row in spectrum_rows if row[1] is not None]
    if len(available_rows) <= 1:
        return None

    nominal_it_mw = result.power.it_load_mw
    committed_it_mw = _result_committed_it_mw(result)
    numeric_values = [value for _, value in available_rows if value is not None]

    return _build_advanced_block(
        "it_capacity_spectrum",
        "IT Capacity Spectrum",
        summary_items=[
            _fact("Nominal design", _display_number(nominal_it_mw, digits=2, suffix="MW")),
            _fact(
                "Committed IT",
                _display_number(committed_it_mw, digits=2, suffix="MW"),
            ),
            _fact(
                "Worst-hour IT",
                _display_number(result.it_capacity_worst_mw, digits=2, suffix="MW"),
            ),
            _fact(
                "Best-hour IT",
                _display_number(result.it_capacity_best_mw, digits=2, suffix="MW"),
            ),
            _fact(
                "Hourly spread",
                _display_number(max(numeric_values) - min(numeric_values), digits=2, suffix="MW"),
            ),
            _fact(
                "Nominal derating",
                _display_number(committed_it_mw - nominal_it_mw, digits=2, suffix="MW"),
            ),
        ],
        tables=[
            _table(
                "Capacity checkpoints",
                [
                    ("checkpoint", "Checkpoint"),
                    ("it_capacity", "IT capacity"),
                    ("delta_vs_nominal", "Delta vs nominal"),
                    ("delta_vs_committed", "Delta vs committed"),
                ],
                [
                    {
                        "checkpoint": label,
                        "it_capacity": _display_number(value, digits=2, suffix="MW"),
                        "delta_vs_nominal": _display_number(
                            value - nominal_it_mw if value is not None else None,
                            digits=2,
                            suffix="MW",
                        ),
                        "delta_vs_committed": _display_number(
                            value - committed_it_mw if value is not None else None,
                            digits=2,
                            suffix="MW",
                        ),
                    }
                    for label, value in available_rows
                ],
            ),
        ],
        notes=[
            "Hourly checkpoints are taken from the stored selected-scenario result bundle.",
        ],
    )


def _build_expansion_advisory_block(
    site: Site,
    result: ScenarioResult,
) -> dict[str, Any] | None:
    compatibility_status, compatibility_reasons = evaluate_compatibility(
        result.scenario.load_type.value,
        result.scenario.cooling_type.value,
        density_scenario=result.scenario.density_scenario.value,
    )
    if compatibility_status == "incompatible":
        return None

    advisory = compute_expansion_advisory(
        site=site,
        scenario=result.scenario,
        space=result.space,
        power=result.power,
        annual_pue=result.annual_pue,
        pue_source=result.pue_source,
    )
    notes = list(advisory.notes)
    if compatibility_status == "conditional":
        notes = list(compatibility_reasons) + notes

    return _build_advanced_block(
        "expansion_advisory",
        "Expansion Advisory",
        summary_items=[
            _fact("Active floors", _display_number(advisory.active_floors, digits=0)),
            _fact(
                "Reserved floors",
                _display_number(advisory.declared_expansion_floors, digits=0),
            ),
            _fact(
                "Height uplift floors",
                _display_number(advisory.latent_height_floors, digits=0),
            ),
            _fact(
                "Total additional racks",
                _display_number(advisory.total_additional_racks, digits=0),
            ),
            _fact(
                "Current facility envelope",
                _display_number(advisory.current_facility_envelope_mw, digits=2, suffix="MW"),
            ),
            _fact(
                "Current procurement envelope",
                _display_number(
                    advisory.current_procurement_envelope_mw,
                    digits=2,
                    suffix="MW",
                ),
            ),
            _fact(
                "Extra grid request",
                _display_number(advisory.additional_grid_request_mw, digits=2, suffix="MW"),
            ),
            _fact("Binding constraint", advisory.binding_constraint),
        ],
        tables=[
            _table(
                "Capacity stages",
                [
                    ("stage", "Stage"),
                    ("racks", "Racks"),
                    ("it_load", "IT load"),
                    ("facility_power", "Facility power"),
                    ("procurement_power", "Procurement power"),
                ],
                [
                    {
                        "stage": "Current feasible",
                        "racks": _display_number(advisory.current_feasible.racks, digits=0),
                        "it_load": _display_number(
                            advisory.current_feasible.it_load_mw,
                            digits=2,
                            suffix="MW",
                        ),
                        "facility_power": _display_number(
                            advisory.current_feasible.facility_power_mw,
                            digits=2,
                            suffix="MW",
                        ),
                        "procurement_power": _display_number(
                            advisory.current_feasible.procurement_power_mw,
                            digits=2,
                            suffix="MW",
                        ),
                    },
                    {
                        "stage": "Future expandable",
                        "racks": _display_number(advisory.future_expandable.racks, digits=0),
                        "it_load": _display_number(
                            advisory.future_expandable.it_load_mw,
                            digits=2,
                            suffix="MW",
                        ),
                        "facility_power": _display_number(
                            advisory.future_expandable.facility_power_mw,
                            digits=2,
                            suffix="MW",
                        ),
                        "procurement_power": _display_number(
                            advisory.future_expandable.procurement_power_mw,
                            digits=2,
                            suffix="MW",
                        ),
                    },
                    {
                        "stage": "Total site potential",
                        "racks": _display_number(advisory.total_site_potential.racks, digits=0),
                        "it_load": _display_number(
                            advisory.total_site_potential.it_load_mw,
                            digits=2,
                            suffix="MW",
                        ),
                        "facility_power": _display_number(
                            advisory.total_site_potential.facility_power_mw,
                            digits=2,
                            suffix="MW",
                        ),
                        "procurement_power": _display_number(
                            advisory.total_site_potential.procurement_power_mw,
                            digits=2,
                            suffix="MW",
                        ),
                    },
                ],
            ),
        ],
        notes=notes,
    )


def _build_firm_capacity_block(
    site: Site,
    result: ScenarioResult,
    hourly_analysis: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if hourly_analysis is None:
        return None
    if not site.power_confirmed or site.available_power_mw <= 0:
        return None

    compatibility_status, _ = evaluate_compatibility(
        result.scenario.load_type.value,
        result.scenario.cooling_type.value,
        density_scenario=result.scenario.density_scenario.value,
    )
    if compatibility_status == "incompatible":
        return None

    sim = hourly_analysis["sim"]
    hourly_factors = hourly_analysis["hourly_factors"]
    grid_capacity_kw = result.power.facility_power_mw * 1000
    space_limit_kw = result.space.effective_racks * result.power.rack_density_kw

    try:
        supported = find_max_firm_it_capacity(
            hourly_facility_factors=hourly_factors,
            grid_capacity_kw=grid_capacity_kw,
            max_it_kw=space_limit_kw,
            hourly_pv_kw=None,
            bess_capacity_kwh=0.0,
            bess_roundtrip_efficiency=0.875,
            bess_initial_soc_kwh=0.0,
            fuel_cell_capacity_kw=0.0,
            backup_dispatch_capacity_kw=0.0,
            cyclic_bess=True,
        )
        target_evaluation = simulate_firm_capacity_support(
            hourly_facility_factors=hourly_factors,
            target_it_kw=result.power.it_load_mw * 1000,
            grid_capacity_kw=grid_capacity_kw,
            hourly_pv_kw=None,
            bess_capacity_kwh=0.0,
            bess_roundtrip_efficiency=0.875,
            bess_initial_soc_kwh=0.0,
            fuel_cell_capacity_kw=0.0,
            backup_dispatch_capacity_kw=0.0,
            cyclic_bess=True,
        )
        recommendations = recommend_support_portfolios(
            hourly_facility_factors=hourly_factors,
            target_it_kw=result.power.it_load_mw * 1000,
            grid_capacity_kw=grid_capacity_kw,
            baseline_p99_kw=sim.it_capacity_p99_kw,
            baseline_worst_kw=sim.it_capacity_worst_kw,
            hourly_pv_kw=None,
            bess_roundtrip_efficiency=0.875,
            cyclic_bess=True,
        )
    except ValueError:
        return None

    tables = [
        _table(
            "Firm-capacity checkpoints",
            [("benchmark", "Benchmark"), ("it_capacity", "IT capacity")],
            [
                {
                    "benchmark": "Nominal design",
                    "it_capacity": _display_number(
                        result.power.it_load_mw,
                        digits=2,
                        suffix="MW",
                    ),
                },
                {
                    "benchmark": "Worst-hour firm",
                    "it_capacity": _display_number(
                        sim.it_capacity_worst_kw / 1000,
                        digits=2,
                        suffix="MW",
                    ),
                },
                {
                    "benchmark": "P99 committed",
                    "it_capacity": _display_number(
                        sim.it_capacity_p99_kw / 1000,
                        digits=2,
                        suffix="MW",
                    ),
                },
                {
                    "benchmark": "Max constant firm IT",
                    "it_capacity": _display_number(
                        supported.target_it_kw / 1000,
                        digits=2,
                        suffix="MW",
                    ),
                },
            ],
        )
    ]

    if recommendations.candidates:
        tables.append(
            _table(
                "Deterministic support pathways to recover nominal IT",
                [
                    ("pathway", "Pathway"),
                    ("feasible", "Feasible"),
                    ("bess", "BESS"),
                    ("fuel_cell", "Fuel cell"),
                    ("backup", "Backup"),
                    ("peak_support", "Peak support"),
                    ("support_hours", "Support hours"),
                    ("unmet_energy", "Unmet energy"),
                    ("notes", "Notes"),
                ],
                [
                    {
                        "pathway": candidate.label,
                        "feasible": _display_bool(candidate.feasible),
                        "bess": _display_number(
                            candidate.bess_capacity_kwh / 1000,
                            digits=2,
                            suffix="MWh",
                        ),
                        "fuel_cell": _display_number(
                            candidate.fuel_cell_capacity_kw / 1000,
                            digits=2,
                            suffix="MW",
                        ),
                        "backup": _display_number(
                            candidate.backup_dispatch_capacity_kw / 1000,
                            digits=2,
                            suffix="MW",
                        ),
                        "peak_support": _display_number(
                            candidate.peak_support_kw / 1000,
                            digits=2,
                            suffix="MW",
                        ),
                        "support_hours": _display_number(
                            candidate.hours_with_capacity_support,
                            digits=0,
                        ),
                        "unmet_energy": _display_number(
                            candidate.total_unmet_kwh / 1000,
                            digits=2,
                            suffix="MWh",
                        ),
                        "notes": _display_list(candidate.notes, default=""),
                    }
                    for candidate in recommendations.candidates
                ],
            )
        )

    notes = []
    if recommendations.target_already_feasible:
        notes.append("The nominal design IT load is already feasible without support assets.")
    else:
        notes.append(
            "Support pathways target the scenario's nominal IT load and keep the selected grid cap fixed."
        )

    return _build_advanced_block(
        "firm_capacity",
        "Firm Capacity",
        summary_items=[
            _fact("Nominal IT target", _display_number(result.power.it_load_mw, digits=2, suffix="MW")),
            _fact(
                "Worst-hour firm IT",
                _display_number(sim.it_capacity_worst_kw / 1000, digits=2, suffix="MW"),
            ),
            _fact(
                "P99 committed IT",
                _display_number(sim.it_capacity_p99_kw / 1000, digits=2, suffix="MW"),
            ),
            _fact(
                "Max constant firm IT",
                _display_number(supported.target_it_kw / 1000, digits=2, suffix="MW"),
            ),
            _fact(
                "Gap vs nominal",
                _display_number(
                    (supported.target_it_kw / 1000) - result.power.it_load_mw,
                    digits=2,
                    suffix="MW",
                ),
            ),
            _fact(
                "Peak support at nominal",
                _display_number(target_evaluation.peak_unmet_kw / 1000, digits=2, suffix="MW"),
            ),
            _fact(
                "Hours above grid cap",
                _display_number(target_evaluation.hours_above_grid_cap, digits=0),
            ),
            _fact(
                "Annual support energy",
                _display_number(recommendations.annual_support_energy_kwh / 1000, digits=2, suffix="MWh"),
            ),
        ],
        tables=tables,
        notes=notes,
    )


def _build_footprint_block(site: Site, result: ScenarioResult) -> dict[str, Any] | None:
    try:
        footprint = compute_footprint(
            facility_power_mw=result.power.facility_power_mw,
            procurement_power_mw=result.power.procurement_power_mw,
            buildable_footprint_m2=result.space.buildable_footprint_m2,
            land_area_m2=_analysis_land_area_m2(site, result),
            backup_power_type=result.scenario.backup_power,
        )
    except ValueError:
        return None

    return _build_advanced_block(
        "footprint",
        "Footprint",
        summary_items=[
            _fact(
                "Ground equipment",
                _display_number(footprint.total_ground_m2, digits=0, suffix="m2"),
            ),
            _fact(
                "Roof equipment",
                _display_number(footprint.total_roof_m2, digits=0, suffix="m2"),
            ),
            _fact(
                "Ground utilization",
                _display_percent(footprint.ground_utilization_ratio, digits=0),
            ),
            _fact(
                "Roof utilization",
                _display_percent(footprint.roof_utilization_ratio, digits=0),
            ),
            _fact(
                "Outdoor available",
                _display_number(footprint.available_outdoor_m2, digits=0, suffix="m2"),
            ),
            _fact(
                "Roof available",
                _display_number(footprint.building_roof_m2, digits=0, suffix="m2"),
            ),
            _fact("Backup technology", footprint.backup_power_type),
            _fact("Ground fit", _display_bool(footprint.ground_fits)),
            _fact("Roof fit", _display_bool(footprint.roof_fits)),
        ],
        tables=[
            _table(
                "Infrastructure elements",
                [
                    ("element", "Element"),
                    ("location", "Location"),
                    ("area", "Area"),
                    ("basis", "Sizing basis"),
                    ("factor", "Factor"),
                    ("units", "Units"),
                    ("source", "Source"),
                ],
                [
                    {
                        "element": element.name,
                        "location": _display_text(element.location).title(),
                        "area": _display_number(element.area_m2, digits=1, suffix="m2"),
                        "basis": _display_number(
                            element.sizing_basis_kw,
                            digits=0,
                            suffix="kW",
                        ),
                        "factor": _display_number(element.m2_per_kw_used, digits=3),
                        "units": (
                            f"{element.num_units} x {element.unit_size_kw:.0f} kW"
                            if element.num_units is not None and element.unit_size_kw is not None
                            else "Not applicable"
                        ),
                        "source": _display_text(element.source),
                    }
                    for element in footprint.elements
                ],
            ),
        ],
    )


def _build_backup_comparison_block(result: ScenarioResult) -> dict[str, Any] | None:
    try:
        comparison = compare_technologies(
            procurement_power_mw=result.power.procurement_power_mw,
        )
    except ValueError:
        return None

    return _build_advanced_block(
        "backup_comparison",
        "Backup Comparison",
        summary_items=[
            _fact(
                "Procurement basis",
                _display_number(comparison.procurement_power_mw, digits=2, suffix="MW"),
            ),
            _fact(
                "Runtime basis",
                _display_number(comparison.annual_runtime_hours, digits=0, suffix="h/yr"),
            ),
            _fact("Lowest CO2", comparison.lowest_co2_technology),
            _fact("Smallest footprint", comparison.lowest_footprint_technology),
            _fact("Fastest ramp", comparison.fastest_ramp_technology),
        ],
        tables=[
            _table(
                "Technology comparison",
                [
                    ("technology", "Technology"),
                    ("fuel", "Fuel"),
                    ("units", "Units"),
                    ("unit_size", "Unit size"),
                    ("co2", "CO2"),
                    ("footprint", "Footprint"),
                    ("ramp", "Ramp"),
                ],
                [
                    {
                        "technology": technology.technology,
                        "fuel": technology.fuel_type,
                        "units": _display_number(technology.num_units, digits=0),
                        "unit_size": _display_number(technology.unit_size_kw, digits=0, suffix="kW"),
                        "co2": _display_number(
                            technology.co2_tonnes_per_year,
                            digits=0,
                            suffix="t/yr",
                        ),
                        "footprint": _display_number(technology.footprint_m2, digits=0, suffix="m2"),
                        "ramp": _display_number(technology.ramp_time_seconds, digits=0, suffix="s"),
                    }
                    for technology in comparison.technologies
                ],
            ),
        ],
    )


def _build_sensitivity_block(site: Site, result: ScenarioResult) -> dict[str, Any] | None:
    try:
        tornado = compute_tornado(
            pue=_result_pue(result),
            eta_chain=result.power.eta_chain,
            rack_density_kw=result.power.rack_density_kw,
            whitespace_ratio=result.space.whitespace_ratio_used,
            site_coverage_ratio=result.space.site_coverage_used,
            available_power_mw=_analysis_available_power_mw(result),
            land_area_m2=_analysis_land_area_m2(site, result),
            num_floors=result.space.active_floors,
            rack_footprint_m2=result.space.rack_footprint_used,
            whitespace_adjustment=result.space.whitespace_adjustment_factor,
            procurement_factor=result.power.procurement_factor,
            variation_pct=10,
            output_metric="it_load",
            power_constrained=result.power.binding_constraint == "POWER",
        )
    except ValueError:
        return None

    if not tornado.bars:
        return None

    most_influential = tornado.bars[0]
    least_influential = tornado.bars[-1]

    return _build_advanced_block(
        "sensitivity",
        "Sensitivity",
        summary_items=[
            _fact("Variation", _display_number(tornado.variation_pct, digits=0, suffix="%")),
            _fact("Output metric", tornado.output_metric_name),
            _fact(
                "Baseline output",
                _display_number(
                    most_influential.output_at_baseline,
                    digits=2,
                    suffix=tornado.output_metric_unit,
                ),
            ),
            _fact("Most influential", most_influential.parameter_label),
            _fact("Least influential", least_influential.parameter_label),
        ],
        tables=[
            _table(
                "One-at-a-time parameter sweep",
                [
                    ("parameter", "Parameter"),
                    ("baseline", "Baseline"),
                    ("low_case", "Low case"),
                    ("high_case", "High case"),
                    ("output_low", "Output at low"),
                    ("output_high", "Output at high"),
                    ("spread", "Spread"),
                ],
                [
                    {
                        "parameter": bar.parameter_label,
                        "baseline": _display_number(
                            bar.baseline_value,
                            digits=3,
                            suffix=SENSITIVITY_UNIT_SUFFIXES.get(bar.parameter),
                        ),
                        "low_case": _display_number(
                            bar.low_value,
                            digits=3,
                            suffix=SENSITIVITY_UNIT_SUFFIXES.get(bar.parameter),
                        ),
                        "high_case": _display_number(
                            bar.high_value,
                            digits=3,
                            suffix=SENSITIVITY_UNIT_SUFFIXES.get(bar.parameter),
                        ),
                        "output_low": _display_number(bar.output_at_low, digits=2, suffix=tornado.output_metric_unit),
                        "output_high": _display_number(bar.output_at_high, digits=2, suffix=tornado.output_metric_unit),
                        "spread": _display_number(bar.spread, digits=2, suffix=tornado.output_metric_unit),
                    }
                    for bar in tornado.bars
                ],
            ),
        ],
    )


def _build_break_even_block(site: Site, result: ScenarioResult) -> dict[str, Any] | None:
    if result.pue_source != "hourly" or result.annual_pue is None:
        return None

    target_it_load_mw = result.power.it_load_mw
    committed_it_mw = _result_committed_it_mw(result)
    if target_it_load_mw <= committed_it_mw + 1e-6:
        return None

    rows: list[dict[str, str]] = []
    feasible_count = 0

    for parameter in SENSITIVITY_PARAMETERS:
        try:
            break_even = compute_break_even(
                target_it_load_mw=target_it_load_mw,
                parameter=parameter,
                pue=_result_pue(result),
                eta_chain=result.power.eta_chain,
                rack_density_kw=result.power.rack_density_kw,
                whitespace_ratio=result.space.whitespace_ratio_used,
                site_coverage_ratio=result.space.site_coverage_used,
                available_power_mw=_analysis_available_power_mw(result),
                land_area_m2=_analysis_land_area_m2(site, result),
                num_floors=result.space.active_floors,
                rack_footprint_m2=result.space.rack_footprint_used,
                whitespace_adjustment=result.space.whitespace_adjustment_factor,
                power_constrained=result.power.binding_constraint == "POWER",
            )
        except ValueError:
            continue

        if break_even.feasible:
            feasible_count += 1

        unit_suffix = SENSITIVITY_UNIT_SUFFIXES.get(parameter)
        rows.append(
            {
                "parameter": break_even.parameter_label,
                "baseline": _display_number(
                    break_even.baseline_value,
                    digits=3,
                    suffix=unit_suffix,
                ),
                "break_even": _display_number(
                    break_even.break_even_value,
                    digits=3,
                    suffix=unit_suffix,
                ),
                "delta": _display_number(
                    break_even.change_from_baseline,
                    digits=3,
                    suffix=unit_suffix,
                ),
                "change_pct": _display_number(
                    break_even.change_pct,
                    digits=1,
                    suffix="%",
                ),
                "feasible": _display_bool(break_even.feasible),
                "note": _display_text(break_even.feasibility_note, default=""),
            }
        )

    if not rows:
        return None

    return _build_advanced_block(
        "break_even",
        "Break-Even",
        summary_items=[
            _fact("Target IT", _display_number(target_it_load_mw, digits=2, suffix="MW")),
            _fact("Current committed IT", _display_number(committed_it_mw, digits=2, suffix="MW")),
            _fact(
                "Recovery gap",
                _display_number(target_it_load_mw - committed_it_mw, digits=2, suffix="MW"),
            ),
            _fact("Feasible parameters", _display_number(feasible_count, digits=0)),
        ],
        tables=[
            _table(
                "Nominal IT recovery requirements",
                [
                    ("parameter", "Parameter"),
                    ("baseline", "Baseline"),
                    ("break_even", "Break-even"),
                    ("delta", "Delta"),
                    ("change_pct", "Change"),
                    ("feasible", "Feasible"),
                    ("note", "Feasibility note"),
                ],
                rows,
            ),
        ],
        notes=[
            "The target IT load is the scenario's nominal design load from the baseline power solve.",
        ],
    )


def _build_advanced_result_blocks(
    *,
    site: Site,
    primary_result: ScenarioResult,
) -> list[dict[str, Any]]:
    hourly_analysis = _load_hourly_analysis(primary_result.site_id, site, primary_result)
    blocks = [
        _build_pue_decomposition_block(hourly_analysis),
        _build_hourly_profiles_block(hourly_analysis),
        _build_it_capacity_spectrum_block(primary_result),
        _build_expansion_advisory_block(site, primary_result),
        _build_firm_capacity_block(site, primary_result, hourly_analysis),
        _build_footprint_block(site, primary_result),
        _build_backup_comparison_block(primary_result),
        _build_sensitivity_block(site, primary_result),
        _build_break_even_block(site, primary_result),
    ]
    return [block for block in blocks if block is not None]


def _normalize_result(
    result: ScenarioResult,
    *,
    rank_within_site: int | None,
    global_rank: int | None,
    selected_primary_rank: int | None,
    is_primary: bool,
    is_displayed_in_current_output: bool,
) -> dict[str, Any]:
    pue = _result_pue(result)
    committed_it_mw = _result_committed_it_mw(result)

    return {
        "site_id": result.site_id,
        "site_name": result.site_name,
        "result_key": get_result_selection_key(result),
        "label": get_result_display_label(result),
        "rank_within_site": rank_within_site,
        "global_rank": global_rank,
        "selected_primary_rank": selected_primary_rank,
        "is_primary": is_primary,
        "is_displayed_in_current_output": is_displayed_in_current_output,
        "compatible_combination": result.compatible_combination,
        "scenario": {
            "load_type": result.scenario.load_type.value,
            "cooling_type": result.scenario.cooling_type.value,
            "redundancy": result.scenario.redundancy.value,
            "density_scenario": result.scenario.density_scenario.value,
            "backup_power": result.scenario.backup_power.value,
            "pue_override": result.scenario.pue_override,
            "assumption_override_preset_key": (
                result.scenario.assumption_override_preset_key
            ),
            "assumption_override_preset_label": (
                result.assumption_override_preset_label
            ),
        },
        "space": result.space.model_dump(mode="json"),
        "power": result.power.model_dump(mode="json"),
        "metrics": {
            "score": result.score,
            "pue": pue,
            "annual_pue": result.annual_pue,
            "pue_source": result.pue_source,
            "it_load_mw": result.power.it_load_mw,
            "committed_it_mw": committed_it_mw,
            "facility_power_mw": result.power.facility_power_mw,
            "procurement_power_mw": result.power.procurement_power_mw,
            "binding_constraint": result.power.binding_constraint,
            "power_headroom_mw": result.power.power_headroom_mw,
            "overtemperature_hours": result.overtemperature_hours,
            "racks_deployed": result.power.racks_deployed,
            "racks_by_power": result.power.racks_by_power,
            "rack_density_kw": result.power.rack_density_kw,
            "it_capacity_worst_mw": result.it_capacity_worst_mw,
            "it_capacity_p99_mw": result.it_capacity_p99_mw,
            "it_capacity_p90_mw": result.it_capacity_p90_mw,
            "it_capacity_mean_mw": result.it_capacity_mean_mw,
            "it_capacity_best_mw": result.it_capacity_best_mw,
        },
        "status": {
            "rag_status": result.power.rag_status.value,
            "rag_reasons": list(result.power.rag_reasons),
        },
        "feature_flags": {
            "has_hourly_pue": result.annual_pue is not None,
            "has_overtemperature_hours": result.overtemperature_hours is not None,
            "has_it_capacity_spectrum": any(
                value is not None
                for value in (
                    result.it_capacity_worst_mw,
                    result.it_capacity_p99_mw,
                    result.it_capacity_p90_mw,
                    result.it_capacity_mean_mw,
                    result.it_capacity_best_mw,
                )
            ),
            "has_assumption_overrides": bool(result.applied_assumption_overrides),
            "has_pue_override": result.scenario.pue_override is not None,
        },
        "applied_assumption_overrides": [
            override.model_dump(mode="json")
            for override in result.applied_assumption_overrides
        ],
    }


def _normalize_grid_context_result(result: GridContextResult) -> dict[str, Any]:
    assets = []
    for asset in result.assets:
        item = asset.model_dump(mode="json")
        item["coordinate_count"] = len(asset.coordinates)
        assets.append(item)

    return {
        "site_id": result.site_id,
        "site_name": result.site_name,
        "latitude": result.latitude,
        "longitude": result.longitude,
        "analysis_grade": result.analysis_grade.value,
        "summary": result.summary.model_dump(mode="json"),
        "score": result.score.model_dump(mode="json") if result.score is not None else None,
        "assets": assets,
        "asset_count": len(assets),
        "evidence_notes": [
            note.model_dump(mode="json") for note in result.evidence_notes
        ],
        "official_evidence": (
            result.official_evidence.model_dump(mode="json")
            if result.official_evidence is not None
            else None
        ),
        "official_context_notes": list(result.official_context_notes),
        "source_layers": list(result.source_layers),
        "confidence": result.confidence.value,
        "generated_at_utc": result.generated_at_utc,
    }


def _grid_context_preference_key(result: GridContextResult) -> tuple[str, float, int, int]:
    return (
        result.generated_at_utc,
        result.summary.radius_km,
        len(result.assets),
        1 if result.score is not None else 0,
    )


def _load_grid_context_block(site_id: str) -> dict[str, Any]:
    site_dir = Path(GRID_CONTEXT_DIR) / site_id
    if not site_dir.exists():
        return {
            "status": "missing",
            "available": False,
            "message": None,
            "selected": None,
            "variants": [],
            "available_radius_km": [],
        }

    cached_results: list[GridContextResult] = []
    errors: list[str] = []

    for path in sorted(site_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            cached_results.append(GridContextResult(**payload))
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            errors.append(f"{path.name}: {exc}")

    if not cached_results:
        return {
            "status": "error" if errors else "missing",
            "available": False,
            "message": "; ".join(errors) if errors else None,
            "selected": None,
            "variants": [],
            "available_radius_km": [],
        }

    selected = max(cached_results, key=_grid_context_preference_key)
    variants = sorted(
        cached_results,
        key=lambda result: (
            result.summary.radius_km,
            result.generated_at_utc,
            len(result.assets),
        ),
    )
    message = None
    if errors:
        message = (
            f"Skipped {len(errors)} invalid cached grid-context payload(s) for this site."
        )

    return {
        "status": "available",
        "available": True,
        "message": message,
        "selected": _normalize_grid_context_result(selected),
        "variants": [
            {
                "radius_km": result.summary.radius_km,
                "asset_count": len(result.assets),
                "has_score": result.score is not None,
                "generated_at_utc": result.generated_at_utc,
            }
            for result in variants
        ],
        "available_radius_km": [result.summary.radius_km for result in variants],
    }


def _build_weather_status(weather: dict[str, Any]) -> dict[str, Any]:
    temperatures = weather.get("temperatures") or []
    humidities = weather.get("humidities")
    return {
        "source": weather.get("source", ""),
        "source_type": _infer_weather_source_type(weather),
        "hours": weather.get("hours", len(temperatures)),
        "years_averaged": weather.get("years_averaged", []),
        "has_humidity": humidities is not None,
        "original_filename": weather.get("original_filename"),
        "uploaded_at_utc": weather.get("uploaded_at_utc"),
        "latitude": weather.get("latitude"),
        "longitude": weather.get("longitude"),
    }


def _select_climate_cooling_types(
    primary_result: ScenarioResult | None,
    site_results: list[ScenarioResult],
) -> list[str] | None:
    ordered_cooling_types: list[str] = []
    seen: set[str] = set()

    candidate_results = []
    if primary_result is not None:
        candidate_results.append(primary_result)
    candidate_results.extend(site_results)

    for result in candidate_results:
        cooling_type = result.scenario.cooling_type.value
        if cooling_type not in seen:
            seen.add(cooling_type)
            ordered_cooling_types.append(cooling_type)

    return ordered_cooling_types or None


def _normalize_climate_analysis(result: Any) -> dict[str, Any]:
    free_cooling = [asdict(item) for item in result.free_cooling]
    delta_results = {
        str(delta): [asdict(item) for item in delta_items]
        for delta, delta_items in result.delta_results.items()
    }
    best_free_cooling = (
        max(free_cooling, key=lambda item: item["free_cooling_hours"])
        if free_cooling
        else None
    )

    return {
        "temperature_stats": asdict(result.temperature_stats),
        "monthly_stats": (
            asdict(result.monthly_stats) if result.monthly_stats is not None else None
        ),
        "free_cooling": free_cooling,
        "best_free_cooling": best_free_cooling,
        "delta_results": delta_results,
        "cooling_types_analyzed": [
            item["cooling_type"] for item in free_cooling
        ],
    }


def _load_climate_block(
    site_id: str,
    site_results: list[ScenarioResult],
    primary_result: ScenarioResult | None,
) -> dict[str, Any]:
    weather = get_weather(site_id)
    if weather is None:
        return {
            "status": "missing",
            "available": False,
            "message": None,
            "weather_status": None,
            "analysis": None,
        }

    weather_status = _build_weather_status(weather)
    temperatures = weather.get("temperatures") or []
    humidities = weather.get("humidities")
    cooling_types = _select_climate_cooling_types(primary_result, site_results)

    if not temperatures:
        return {
            "status": "error",
            "available": False,
            "message": "Cached weather data was present but contained no temperatures.",
            "weather_status": weather_status,
            "analysis": None,
        }

    try:
        analysis = analyse_climate(
            temperatures=temperatures,
            cooling_types=cooling_types,
            humidities=humidities,
        )
    except ValueError as exc:
        return {
            "status": "error",
            "available": False,
            "message": str(exc),
            "weather_status": weather_status,
            "analysis": None,
        }

    return {
        "status": "available",
        "available": True,
        "message": None,
        "weather_status": weather_status,
        "analysis": _normalize_climate_analysis(analysis),
    }


def _derive_load_mix_allowed_load_types(result: dict[str, Any]) -> list[str]:
    configured = [
        _display_text(load_type, default="")
        for load_type in result.get("allowed_load_types") or []
    ]
    configured = [load_type for load_type in configured if load_type]
    if configured:
        return configured

    ordered_types: list[str] = []
    seen: set[str] = set()
    for candidate in result.get("top_candidates") or []:
        for allocation in candidate.get("allocations") or []:
            load_type = _display_text(allocation.get("load_type"), default="")
            if load_type and load_type not in seen:
                seen.add(load_type)
                ordered_types.append(load_type)
    return ordered_types


def _summarize_load_mix_allocations(allocations: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for allocation in allocations:
        load_type = _display_text(allocation.get("load_type"), default="")
        if not load_type:
            continue
        share_pct = allocation.get("share_pct")
        it_load_mw = allocation.get("it_load_mw")
        parts.append(
            (
                f"{load_type} "
                f"{_display_number(share_pct, digits=0, default='0')}% / "
                f"{_display_number(it_load_mw, digits=2, suffix='MW')}"
            )
        )
    return "; ".join(parts) if parts else "Not available"


def _load_load_mix_block(
    raw_input: Any,
    effective_primary_result_key: str | None,
) -> dict[str, Any]:
    if not raw_input:
        return {
            "status": "missing",
            "available": False,
            "message": None,
            "result_key": None,
            "result": None,
        }

    try:
        parsed = LoadMixReportInput.model_validate(raw_input)
    except ValidationError as exc:
        return {
            "status": "error",
            "available": False,
            "message": str(exc),
            "result_key": None,
            "result": None,
        }

    if (
        effective_primary_result_key is not None
        and parsed.result_key is not None
        and parsed.result_key != effective_primary_result_key
    ):
        return {
            "status": "missing",
            "available": False,
            "message": (
                "Load mix analysis was supplied for a different primary result and "
                "was omitted from this export."
            ),
            "result_key": parsed.result_key,
            "result": None,
        }

    normalized = parsed.result.model_dump(mode="json")
    normalized["allowed_load_types"] = _derive_load_mix_allowed_load_types(normalized)

    return {
        "status": "available",
        "available": True,
        "message": None,
        "result_key": parsed.result_key,
        "result": normalized,
    }


def _load_green_energy_block(
    raw_input: Any,
    effective_primary_result_key: str | None,
) -> dict[str, Any]:
    if not raw_input:
        return {
            "status": "missing",
            "available": False,
            "message": None,
            "result_key": None,
            "result": None,
            "pv_profile_name": None,
            "pvgis_profile": None,
            "bess_initial_soc_kwh": None,
            "grid_co2_kg_per_kwh": None,
        }

    try:
        parsed = GreenEnergyReportInput.model_validate(raw_input)
    except ValidationError as exc:
        return {
            "status": "error",
            "available": False,
            "message": str(exc),
            "result_key": None,
            "result": None,
            "pv_profile_name": None,
            "pvgis_profile": None,
            "bess_initial_soc_kwh": None,
            "grid_co2_kg_per_kwh": None,
        }

    if (
        effective_primary_result_key is not None
        and parsed.result_key is not None
        and parsed.result_key != effective_primary_result_key
    ):
        return {
            "status": "missing",
            "available": False,
            "message": (
                "Green energy analysis was supplied for a different primary result "
                "and was omitted from this export."
            ),
            "result_key": parsed.result_key,
            "result": None,
            "pv_profile_name": None,
            "pvgis_profile": None,
            "bess_initial_soc_kwh": None,
            "grid_co2_kg_per_kwh": None,
        }

    return {
        "status": "available",
        "available": True,
        "message": None,
        "result_key": parsed.result_key,
        "result": parsed.result.model_dump(mode="json"),
        "pv_profile_name": parsed.pv_profile_name,
        "pvgis_profile": (
            parsed.pvgis_profile.model_dump(mode="json")
            if parsed.pvgis_profile is not None
            else None
        ),
        "bess_initial_soc_kwh": parsed.bess_initial_soc_kwh,
        "grid_co2_kg_per_kwh": parsed.grid_co2_kg_per_kwh,
    }


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
        },
        "theme": {
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "font_family": font_family,
            "logo_url": logo_url,
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
    )

    context = {key: value for key, value in assembled.items() if not key.startswith("_")}
    context["site_sections"] = assembled["_site_sections"]
    context["ranked_results"] = assembled["_legacy_ranked_results"]
    context["selected_primary_results"] = assembled["_selected_primary_results"]
    context["all_ranked_results"] = assembled["_all_ranked_results"]
    return context
