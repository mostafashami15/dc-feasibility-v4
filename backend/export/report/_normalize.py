"""Normalization functions for site data, scenario results, grid context, and climate."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from engine.models import GridContextResult, ScenarioResult, Site

from export.report._selection import (
    _result_committed_it_mw,
    _result_pue,
    get_result_display_label,
    get_result_selection_key,
)


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
