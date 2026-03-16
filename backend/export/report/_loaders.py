"""Loaders that read cached analysis data from disk/store and return normalised blocks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from api.store import GRID_CONTEXT_DIR, get_weather
from engine.climate import analyse_climate
from engine.models import GridContextResult, ScenarioResult
from engine.pue_engine import build_hourly_facility_factors, simulate_hourly

from export.report._constants import (
    GreenEnergyReportInput,
    LoadMixReportInput,
)
from export.report._normalize import (
    _normalize_climate_analysis,
    _normalize_grid_context_result,
)
from export.report._selection import _infer_weather_source_type
from export.report._utils import _display_text


# ---------------------------------------------------------------------------
# Grid context
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Climate
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Load mix
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Green energy
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Hourly analysis
# ---------------------------------------------------------------------------

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
    site: Any,
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
