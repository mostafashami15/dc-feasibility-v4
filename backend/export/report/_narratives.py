"""All _build_*_narrative functions."""
from __future__ import annotations

from typing import Any

from export.report._utils import (
    _build_narrative,
    _clean_notes,
    _display_bool,
    _display_number,
    _display_percent,
    _display_text,
    _display_energy_mwh,
)


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
