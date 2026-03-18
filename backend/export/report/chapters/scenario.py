"""Selected scenario, deep-dive, and advanced result block builders."""
from __future__ import annotations

from typing import Any

from engine.assumptions import evaluate_compatibility
from engine.backup_power import compare_technologies, compute_firm_capacity_advisory
from engine.expansion import compute_expansion_advisory
from engine.footprint import compute_footprint
from engine.green_energy import (
    find_max_firm_it_capacity,
    recommend_support_portfolios,
    simulate_firm_capacity_support,
)
from engine.models import LoadType, ScenarioResult, Site
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
from export.visual_assets import (
    build_daily_profile_chart,
    build_daily_pue_profile_chart,
    build_energy_decomposition_sankey,
    build_firm_capacity_chart,
    build_firm_capacity_deficit_chart,
    build_it_capacity_spectrum_chart,
    build_pie_chart,
    build_pue_minmax_chart,
    build_power_chain_waterfall,
    build_pue_breakdown_chart,
    build_tornado_chart,
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
            "energy_mwh": _display_number(item["energy_kwh"] / 1000, digits=1, suffix="MWh"),
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

    # Build pie chart visuals for component and mode breakdowns
    component_pie = build_pie_chart(
        [
            {"label": item["label"], "value": item["energy_kwh"]}
            for item in components
            if item["energy_kwh"] > 0
        ],
        title="PUE Overhead by Component",
        subtitle=f"Total overhead: {total_overhead / 1000:.1f} MWh",
    )
    mode_pie = build_pie_chart(
        [
            {"label": "Mechanical cooling", "value": sim.mech_hours, "color": "#ef4444"},
            {"label": "Partial economizer", "value": sim.econ_part_hours, "color": "#f59e0b"},
            {"label": "Full economizer", "value": sim.econ_full_hours, "color": "#16a34a"},
            {"label": "Overtemperature", "value": sim.overtemperature_hours, "color": "#7c3aed"},
        ],
        title="Cooling Mode Hours",
        subtitle="8,760-hour annual distribution",
    )

    # Build energy decomposition Sankey
    energy_sankey = build_energy_decomposition_sankey(
        components,
        total_facility_kwh=sim.total_facility_kwh,
        total_it_kwh=sim.total_it_kwh,
        total_overhead_kwh=total_overhead,
    )

    block = _build_advanced_block(
        "pue_decomposition",
        "PUE Energy Decomposition",
        summary_items=[
            _fact("Annual PUE", _display_number(sim.annual_pue, digits=3)),
            _fact("Total overhead", _display_number(total_overhead / 1000, digits=1, suffix="MWh")),
            _fact(
                "Facility energy",
                _display_number(sim.total_facility_kwh / 1000, digits=1, suffix="MWh"),
            ),
            _fact("IT energy", _display_number(sim.total_it_kwh / 1000, digits=1, suffix="MWh")),
        ],
        tables=[],
        notes=[
            "Derived from the representative hourly simulation used for the annual PUE result.",
        ],
    )
    block["component_pie_visual"] = component_pie
    block["mode_pie_visual"] = mode_pie
    block["energy_sankey_visual"] = energy_sankey
    return block


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


def _extract_green_energy_params(
    green_energy_data: dict[str, Any] | None,
    site_id: str,
) -> tuple[list[float] | None, float, float, float, float]:
    """Extract PV hourly, BESS, and fuel cell params from green energy data.

    Returns (hourly_pv_kw, bess_capacity_kwh, bess_roundtrip_eff,
             bess_initial_soc_kwh, fuel_cell_capacity_kw).
    """
    default_eff = 0.875
    if green_energy_data is None or green_energy_data.get("status") != "available":
        return None, 0.0, default_eff, 0.0, 0.0

    result = green_energy_data.get("result")
    if result is None:
        return None, 0.0, default_eff, 0.0, 0.0

    bess_kwh = float(result.get("bess_capacity_kwh") or 0)
    bess_eff = float(result.get("bess_roundtrip_efficiency") or default_eff)
    bess_soc = float(green_energy_data.get("bess_initial_soc_kwh") or 0)
    fc_kw = float(result.get("fuel_cell_capacity_kw") or 0)

    # Try to load cached PV hourly profile
    hourly_pv_kw = None
    pv_kwp = float(result.get("pv_capacity_kwp") or 0)
    pvgis_profile = green_energy_data.get("pvgis_profile")
    if pv_kwp > 0 and pvgis_profile is not None:
        profile_key = pvgis_profile.get("profile_key")
        if profile_key:
            try:
                from api.store import get_solar_profile
                cached = get_solar_profile(site_id, profile_key)
                if cached and "hourly_pv_kw_per_kwp" in cached:
                    hourly_pv_kw = [v * pv_kwp for v in cached["hourly_pv_kw_per_kwp"]]
            except Exception:
                pass

    return hourly_pv_kw, bess_kwh, bess_eff, bess_soc, fc_kw


def _build_firm_capacity_block(
    site: Site,
    result: ScenarioResult,
    hourly_analysis: dict[str, Any] | None,
    green_energy_data: dict[str, Any] | None = None,
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

    # Extract green energy parameters (PV, BESS, fuel cell) if available
    hourly_pv_kw, ge_bess_kwh, ge_bess_eff, ge_bess_soc, ge_fc_kw = (
        _extract_green_energy_params(green_energy_data, result.site_id)
    )
    has_green = hourly_pv_kw is not None or ge_bess_kwh > 0 or ge_fc_kw > 0

    # Compute capacity gap (Mean - Firm)
    mean_kw = sim.it_capacity_mean_kw if hasattr(sim, "it_capacity_mean_kw") and sim.it_capacity_mean_kw else (
        sum(sim.hourly_it_kw) / len(sim.hourly_it_kw) if sim.hourly_it_kw else 0
    )
    firm_kw = sim.it_capacity_p99_kw
    capacity_gap_kw = max(mean_kw - firm_kw, 0)
    peak_deficit_kw = max(mean_kw - sim.it_capacity_worst_kw, 0)

    # Deficit hours and energy: relative to MEAN capacity
    # These are hours where IT dips below mean due to weather anomaly.
    # Compensating this deficit raises guaranteed capacity from P99 to Mean.
    deficit_hours = sum(1 for it_kw in sim.hourly_it_kw if it_kw < mean_kw)
    deficit_energy_kwh = sum(max(mean_kw - it_kw, 0) for it_kw in sim.hourly_it_kw)

    # Compute mitigation strategies via the advisory engine
    try:
        advisory = compute_firm_capacity_advisory(
            hourly_it_kw=sim.hourly_it_kw,
            facility_power_kw=grid_capacity_kw,
            annual_pue=sim.annual_pue,
            cooling_type=result.scenario.cooling_type.value,
        )
        strategy_dicts = [
            {
                "key": s.key,
                "label": s.label,
                "description": s.description,
                "capacity_kw": s.capacity_kw,
                "capacity_mw": s.capacity_mw,
                "estimated_capex_usd": s.estimated_capex_usd,
                "sizing_summary": s.sizing_summary,
                "notes": s.notes,
            }
            for s in advisory.strategies
        ]
    except Exception:
        strategy_dicts = []

    notes = []
    if has_green:
        notes.append(
            "Analysis includes green energy assets "
            f"(PV: {'yes' if hourly_pv_kw else 'no'}, "
            f"BESS: {ge_bess_kwh / 1000:.1f} MWh, "
            f"Fuel cell: {ge_fc_kw / 1000:.2f} MW)."
        )

    # Build deficit visualization chart
    deficit_chart = build_firm_capacity_deficit_chart(
        hourly_it_kw=sim.hourly_it_kw,
        firm_kw=firm_kw,
        mean_kw=mean_kw,
    )

    block = _build_advanced_block(
        "firm_capacity",
        "Firm Capacity",
        summary_items=[
            _fact("Nominal IT target", _display_number(result.power.it_load_mw, digits=2, suffix="MW")),
            _fact("Mean IT capacity", _display_number(mean_kw / 1000, digits=2, suffix="MW")),
            _fact("P99 committed (Firm)", _display_number(firm_kw / 1000, digits=2, suffix="MW")),
            _fact("Worst-hour IT", _display_number(sim.it_capacity_worst_kw / 1000, digits=2, suffix="MW")),
            _fact("Capacity gap", _display_number(capacity_gap_kw / 1000, digits=2, suffix="MW")),
            _fact("Peak deficit", _display_number(peak_deficit_kw / 1000, digits=2, suffix="MW")),
            _fact("Deficit hours", _display_number(deficit_hours, digits=0, suffix="h")),
            _fact("Deficit energy", _display_number(deficit_energy_kwh / 1000, digits=1, suffix="MWh")),
        ],
        tables=[],
        notes=notes,
    )
    block["deficit_chart_visual"] = deficit_chart
    block["strategies"] = strategy_dicts
    return block


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

    # Build tornado chart visual
    tornado_chart = build_tornado_chart(
        [
            {
                "label": bar.parameter_label,
                "low": bar.output_at_low,
                "high": bar.output_at_high,
            }
            for bar in tornado.bars
        ],
        baseline=most_influential.output_at_baseline,
        output_unit=tornado.output_metric_unit,
        title="Sensitivity Tornado",
        subtitle=f"±{tornado.variation_pct}% parameter sweep — output: {tornado.output_metric_name}",
    )

    block = _build_advanced_block(
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
        tables=[],
    )
    block["tornado_chart_visual"] = tornado_chart
    return block


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


def _build_infrastructure_footprint_block(
    site: Site,
    result: ScenarioResult,
) -> dict[str, Any] | None:
    """Infrastructure Footprint box — matches the UI card exactly."""
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

    block = _build_advanced_block(
        "infrastructure_footprint",
        "Infrastructure Footprint",
        summary_items=[
            _fact(
                "Ground equipment",
                _display_number(footprint.total_ground_m2, digits=0, suffix="m²"),
            ),
            _fact(
                "Roof equipment",
                _display_number(footprint.total_roof_m2, digits=0, suffix="m²"),
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
                _display_number(footprint.available_outdoor_m2, digits=0, suffix="m²"),
            ),
            _fact(
                "Roof available",
                _display_number(footprint.building_roof_m2, digits=0, suffix="m²"),
            ),
            _fact(
                "Backup units",
                _display_number(footprint.backup_num_units, digits=0)
                if hasattr(footprint, "backup_num_units") and footprint.backup_num_units
                else "N/A",
            ),
            _fact(
                "Unit size",
                _display_number(footprint.backup_unit_size_kw, digits=0, suffix="kW")
                if hasattr(footprint, "backup_unit_size_kw") and footprint.backup_unit_size_kw
                else "N/A",
            ),
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
                        "area": _display_number(element.area_m2, digits=1, suffix="m²"),
                        "basis": _display_number(
                            element.sizing_basis_kw,
                            digits=0,
                            suffix="kW",
                        ),
                        "factor": _display_number(element.m2_per_kw_used, digits=3),
                        "units": (
                            f"{element.num_units} × {element.unit_size_kw:.0f} kW"
                            if element.num_units is not None and element.unit_size_kw is not None
                            else "N/A"
                        ),
                        "source": _display_text(element.source),
                    }
                    for element in footprint.elements
                ],
            ),
        ],
        notes=[f"Backup basis: {footprint.backup_power_type}."],
    )
    block["ground_fits"] = footprint.ground_fits
    block["roof_fits"] = footprint.roof_fits
    return block


def _build_backup_power_comparison_block(
    result: ScenarioResult,
) -> dict[str, Any] | None:
    """Backup Power Comparison box — matches the UI card exactly."""
    try:
        comparison = compare_technologies(
            procurement_power_mw=result.power.procurement_power_mw,
        )
    except ValueError:
        return None

    block = _build_advanced_block(
        "backup_power_comparison",
        "Backup Power Comparison",
        summary_items=[
            _fact(
                "Procurement basis",
                _display_number(comparison.procurement_power_mw, digits=2, suffix="MW"),
            ),
            _fact(
                "Runtime basis",
                _display_number(comparison.annual_runtime_hours, digits=0, suffix="h/yr"),
            ),
        ],
        tables=[
            _table(
                "Technology comparison",
                [
                    ("technology", "Technology"),
                    ("units", "Units"),
                    ("unit_size", "Unit size"),
                    ("co2", "CO₂ (t/yr)"),
                    ("footprint", "Footprint (m²)"),
                ],
                [
                    {
                        "technology": technology.technology,
                        "units": _display_number(technology.num_units, digits=0),
                        "unit_size": _display_number(technology.unit_size_kw, digits=0, suffix="kW"),
                        "co2": _display_number(technology.co2_tonnes_per_year, digits=1),
                        "footprint": _display_number(technology.footprint_m2, digits=0, suffix="m²"),
                    }
                    for technology in comparison.technologies
                ],
            ),
        ],
    )
    # Attach highlights for template
    block["lowest_co2"] = comparison.lowest_co2_technology
    block["smallest_footprint"] = comparison.lowest_footprint_technology
    block["fastest_ramp"] = comparison.fastest_ramp_technology
    return block


def _build_expansion_advisory_report_block(
    site: Site,
    result: ScenarioResult,
) -> dict[str, Any] | None:
    """Expansion Advisory box — matches the UI card with metrics + capacity snapshots."""
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

    block = _build_advanced_block(
        "expansion_advisory",
        "Expansion Advisory",
        summary_items=[
            _fact("Active floors", _display_number(advisory.active_floors, digits=0)),
            _fact("Reserved floors", _display_number(advisory.declared_expansion_floors, digits=0)),
            _fact("Height uplift floors", _display_number(advisory.latent_height_floors, digits=0)),
            _fact(
                "Max total floors",
                _display_number(advisory.max_total_floors, digits=0) if advisory.max_total_floors else "N/A",
            ),
            _fact("Unused active racks", _display_number(advisory.unused_active_racks, digits=0)),
            _fact("Reserved expansion racks", _display_number(advisory.declared_expansion_racks, digits=0)),
            _fact("Height uplift racks", _display_number(advisory.latent_height_racks, digits=0)),
            _fact("Total additional racks", _display_number(advisory.total_additional_racks, digits=0)),
            _fact(
                "Current facility envelope",
                _display_number(advisory.current_facility_envelope_mw, digits=2, suffix="MW"),
            ),
            _fact(
                "Current procurement envelope",
                _display_number(advisory.current_procurement_envelope_mw, digits=2, suffix="MW"),
            ),
            _fact(
                "Extra grid request",
                _display_number(advisory.additional_grid_request_mw, digits=2, suffix="MW"),
            ),
            _fact("Binding constraint", advisory.binding_constraint),
        ],
        tables=[],
    )

    # Attach capacity snapshots for template rendering
    block["capacity_snapshots"] = [
        {
            "label": "Current Feasible",
            "accent": "gray",
            "racks": _display_number(advisory.current_feasible.racks, digits=0),
            "it_load": _display_number(advisory.current_feasible.it_load_mw, digits=2, suffix="MW"),
            "facility_power": _display_number(advisory.current_feasible.facility_power_mw, digits=2, suffix="MW"),
            "procurement_power": _display_number(advisory.current_feasible.procurement_power_mw, digits=2, suffix="MW"),
        },
        {
            "label": "Future Expandable",
            "accent": "green",
            "racks": _display_number(advisory.future_expandable.racks, digits=0),
            "it_load": _display_number(advisory.future_expandable.it_load_mw, digits=2, suffix="MW"),
            "facility_power": _display_number(advisory.future_expandable.facility_power_mw, digits=2, suffix="MW"),
            "procurement_power": _display_number(advisory.future_expandable.procurement_power_mw, digits=2, suffix="MW"),
        },
        {
            "label": "Total Site Potential",
            "accent": "blue",
            "racks": _display_number(advisory.total_site_potential.racks, digits=0),
            "it_load": _display_number(advisory.total_site_potential.it_load_mw, digits=2, suffix="MW"),
            "facility_power": _display_number(advisory.total_site_potential.facility_power_mw, digits=2, suffix="MW"),
            "procurement_power": _display_number(advisory.total_site_potential.procurement_power_mw, digits=2, suffix="MW"),
        },
    ]
    notes = list(advisory.notes)
    if compatibility_status == "conditional":
        notes = list(compatibility_reasons) + notes
    block["notes"] = notes
    return block


def _build_load_mix_report_block(
    result: ScenarioResult,
) -> dict[str, Any] | None:
    """Load Mix Planner box — auto-computes optimal load mix for the scenario."""
    from engine.ranking import optimize_load_mix

    committed_it_mw = _result_committed_it_mw(result)
    if committed_it_mw <= 0:
        return None

    # Auto-compute with all load types, using scenario's cooling and density
    all_load_types = list(LoadType)
    try:
        mix_result = optimize_load_mix(
            total_it_mw=committed_it_mw,
            allowed_load_types=all_load_types,
            cooling_type=result.scenario.cooling_type,
            density_scenario=result.scenario.density_scenario,
            step_pct=10,
            min_racks=10,
            top_n=5,
        )
    except Exception:
        return None

    if not mix_result.top_candidates:
        return None

    block = _build_advanced_block(
        "load_mix_planner",
        "Load Mix Planner",
        summary_items=[
            _fact("Total IT", _display_number(mix_result.total_it_mw, digits=2, suffix="MW")),
            _fact("Cooling", mix_result.cooling_type),
            _fact("Density", mix_result.density_scenario),
            _fact("Evaluated", _display_number(mix_result.total_candidates_evaluated, digits=0)),
        ],
        tables=[],
    )

    # Attach candidates for template rendering
    candidates = []
    for candidate in mix_result.top_candidates:
        allocations = [
            {
                "load_type": alloc.load_type,
                "share_pct": f"{alloc.share_pct:.0f}%",
                "it_load_mw": _display_number(alloc.it_load_mw, digits=2),
                "rack_count": _display_number(alloc.rack_count, digits=0),
                "rack_density_kw": _display_number(alloc.rack_density_kw, digits=1, suffix="kW"),
            }
            for alloc in candidate.allocations
        ]
        candidates.append({
            "rank": candidate.rank,
            "score": f"{candidate.score:.1f}",
            "blended_pue": f"{candidate.blended_pue:.3f}",
            "total_racks": _display_number(candidate.total_racks, digits=0),
            "all_compatible": candidate.all_compatible,
            "allocations": allocations,
            "trade_off_notes": candidate.trade_off_notes,
        })
    block["candidates"] = candidates
    return block


def _build_advanced_result_blocks(
    *,
    site: Site,
    primary_result: ScenarioResult,
    green_energy_data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    hourly_analysis = _load_hourly_analysis(primary_result.site_id, site, primary_result)
    blocks = [
        _build_pue_decomposition_block(hourly_analysis),
        _build_firm_capacity_block(site, primary_result, hourly_analysis, green_energy_data),
        _build_infrastructure_footprint_block(site, primary_result),
        _build_backup_power_comparison_block(primary_result),
        _build_expansion_advisory_report_block(site, primary_result),
        _build_load_mix_report_block(primary_result),
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


def _build_daily_profile_chart_visual(
    *,
    site: Site | None,
    primary_scenario_result: ScenarioResult | None,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Build daily profile chart from hourly analysis."""
    _empty = {"available": False, "title": "Daily Operating Profiles", "message": "No hourly data.", "svg_markup": None}
    if site is None or primary_scenario_result is None:
        return _empty
    hourly_analysis = _load_hourly_analysis(primary_scenario_result.site_id, site, primary_scenario_result)
    if hourly_analysis is None:
        return _empty
    return build_daily_profile_chart(
        hourly_analysis["daily_profiles"],
        primary_color=primary_color,
        secondary_color=secondary_color,
    )


def _build_daily_pue_profile_chart_visual(
    *,
    site: Site | None,
    primary_scenario_result: ScenarioResult | None,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Build daily PUE profile chart from hourly analysis."""
    _empty = {"available": False, "title": "Daily PUE Profile", "message": "No hourly data.", "svg_markup": None}
    if site is None or primary_scenario_result is None:
        return _empty
    hourly_analysis = _load_hourly_analysis(primary_scenario_result.site_id, site, primary_scenario_result)
    if hourly_analysis is None:
        return _empty
    return build_daily_pue_profile_chart(
        hourly_analysis["daily_profiles"],
        primary_color=primary_color,
        secondary_color=secondary_color,
    )


def _build_firm_capacity_chart_visual(
    *,
    site: Site | None,
    primary_scenario_result: ScenarioResult | None,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Build firm capacity spectrum chart from hourly analysis."""
    _empty = {"available": False, "title": "Firm Capacity", "message": "No hourly data.", "svg_markup": None}
    if site is None or primary_scenario_result is None:
        return _empty
    hourly_analysis = _load_hourly_analysis(primary_scenario_result.site_id, site, primary_scenario_result)
    if hourly_analysis is None:
        return _empty
    sim = hourly_analysis["sim"]
    advisory_data = {
        "firm_capacity_mw": round(sim.it_capacity_p99_kw / 1000, 3) if sim.it_capacity_p99_kw else 0,
        "mean_capacity_mw": round(sim.annual_mean_it_kw / 1000, 3) if hasattr(sim, "annual_mean_it_kw") and sim.annual_mean_it_kw else round(sum(sim.hourly_it_kw) / len(sim.hourly_it_kw) / 1000, 3) if sim.hourly_it_kw else 0,
        "worst_capacity_mw": round(sim.it_capacity_worst_kw / 1000, 3) if sim.it_capacity_worst_kw else 0,
        "best_capacity_mw": round(sim.it_capacity_best_kw / 1000, 3) if sim.it_capacity_best_kw else 0,
    }
    return build_firm_capacity_chart(
        advisory_data,
        primary_color=primary_color,
        secondary_color=secondary_color,
    )


def _build_pue_minmax_chart_visual(
    *,
    site: Site | None,
    primary_scenario_result: ScenarioResult | None,
    primary_color: str,
) -> dict[str, Any]:
    """Build PUE min/avg/max gauge from hourly analysis."""
    _empty = {"available": False, "title": "PUE Range", "message": "No hourly data.", "svg_markup": None}
    if site is None or primary_scenario_result is None:
        return _empty
    hourly_analysis = _load_hourly_analysis(primary_scenario_result.site_id, site, primary_scenario_result)
    if hourly_analysis is None:
        return _empty
    profiles = hourly_analysis["daily_profiles"]
    days = profiles.get("days", [])
    if not days:
        return _empty
    pue_min = min(d["pue_min"] for d in days)
    pue_max = max(d["pue_max"] for d in days)
    pue_avg = profiles.get("annual_pue", sum(d["pue_avg"] for d in days) / len(days))
    return build_pue_minmax_chart(
        pue_min=pue_min,
        pue_avg=pue_avg,
        pue_max=pue_max,
        primary_color=primary_color,
    )


def _build_deep_dive_chapter(
    primary_result: dict[str, Any] | None,
    site_data: dict[str, Any],
    *,
    site: Site | None = None,
    primary_scenario_result: ScenarioResult | None = None,
    primary_color: str = "#1a365d",
    secondary_color: str = "#2b6cb0",
    green_energy_data: dict[str, Any] | None = None,
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
            green_energy_data=green_energy_data,
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
        "it_capacity_chart_visual": build_it_capacity_spectrum_chart(
            metrics,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "pue_breakdown_chart_visual": build_pue_breakdown_chart(
            metrics.get("pue"),
            power,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "pue_minmax_chart_visual": _build_pue_minmax_chart_visual(
            site=site,
            primary_scenario_result=primary_scenario_result,
            primary_color=primary_color,
        ),
        "power_chain_chart_visual": build_power_chain_waterfall(
            power,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "daily_profile_chart_visual": _build_daily_profile_chart_visual(
            site=site,
            primary_scenario_result=primary_scenario_result,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "daily_pue_profile_chart_visual": _build_daily_pue_profile_chart_visual(
            site=site,
            primary_scenario_result=primary_scenario_result,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "firm_capacity_chart_visual": _build_firm_capacity_chart_visual(
            site=site,
            primary_scenario_result=primary_scenario_result,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "advanced_blocks": advanced_blocks,
        "advanced_block_count": len(advanced_blocks),
        "narrative": _build_deep_dive_narrative(
            metrics=metrics,
            status=status,
            compatible_combination=primary_result["compatible_combination"],
        ),
    }
