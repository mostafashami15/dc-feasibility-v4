"""Selected scenario, deep-dive, and advanced result block builders."""
from __future__ import annotations

from typing import Any

from engine.assumptions import evaluate_compatibility
from engine.backup_power import compare_technologies
from engine.expansion import compute_expansion_advisory
from engine.footprint import compute_footprint
from engine.green_energy import (
    find_max_firm_it_capacity,
    recommend_support_portfolios,
    simulate_firm_capacity_support,
)
from engine.models import ScenarioResult, Site
from engine.sensitivity import SENSITIVITY_PARAMETERS, compute_break_even, compute_tornado

from export.report._constants import SENSITIVITY_UNIT_SUFFIXES
from export.report._loaders import _load_hourly_analysis
from export.report._narratives import (
    _build_deep_dive_narrative,
    _build_selected_scenario_narrative,
)
from export.report._selection import (
    _result_committed_it_mw,
    _result_pue,
)
from export.report._utils import (
    _build_advanced_block,
    _display_bool,
    _display_list,
    _display_number,
    _display_percent,
    _display_text,
    _fact,
    _table,
)


# ---------------------------------------------------------------------------
# Helpers that belong to scenario but are used internally
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Advanced blocks
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Chapter builders
# ---------------------------------------------------------------------------

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
