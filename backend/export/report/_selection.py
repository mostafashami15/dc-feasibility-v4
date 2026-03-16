"""Selection, validation, and grouping of scenario results."""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from engine.models import ScenarioResult, Site


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
    include_all_scenarios: bool = True,
) -> dict[str, list[ScenarioResult]]:
    if include_all_scenarios:
        return {
            site_id: list(results_by_site.get(site_id, []))
            for site_id in studied_site_ids
        }

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
