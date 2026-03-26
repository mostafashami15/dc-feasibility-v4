"""Green energy chapter builder."""
from __future__ import annotations

from typing import Any

from export.report._narratives import _build_green_energy_narrative
from export.report._utils import (
    _display_energy_mwh,
    _display_list,
    _display_number,
    _display_percent,
    _display_text,
    _fact,
    _table,
)


def _smart_power(kwp: float | None) -> str:
    """Format power with auto-scaled unit (kWp / MWp / GWp / TWp)."""
    if kwp is None:
        return "Not available"
    if kwp >= 1e9:
        return f"{kwp / 1e9:,.1f} TWp"
    if kwp >= 1e6:
        return f"{kwp / 1e6:,.1f} GWp"
    if kwp >= 1e3:
        return f"{kwp / 1e3:,.1f} MWp"
    return f"{kwp:,.0f} kWp"


def _smart_energy_kwh(kwh: float | None) -> str:
    """Format energy (input kWh) with auto-scaled unit (kWh / MWh / GWh / TWh)."""
    if kwh is None:
        return "Not available"
    if kwh >= 1e9:
        return f"{kwh / 1e9:,.1f} TWh"
    if kwh >= 1e6:
        return f"{kwh / 1e6:,.1f} GWh"
    if kwh >= 1e3:
        return f"{kwh / 1e3:,.1f} MWh"
    return f"{kwh:,.0f} kWh"


def _smart_energy_mwh(mwh: float | None) -> str:
    """Format energy (input MWh) with auto-scaled unit (MWh / GWh / TWh)."""
    if mwh is None:
        return "Not available"
    if mwh >= 1e6:
        return f"{mwh / 1e6:,.1f} TWh"
    if mwh >= 1e3:
        return f"{mwh / 1e3:,.1f} GWh"
    return f"{mwh:,.1f} MWh"
from export.visual_assets import (
    build_green_energy_breakdown_chart,
    build_green_dispatch_hourly_chart,
)


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

    pvgis_params = result.get("pvgis_params") or {}

    if pv_profile_source == "pvgis":
        provenance_items = [
            _fact("PV source", "Cached PVGIS normalized profile"),
            _fact("PVGIS profile key", result.get("pvgis_profile_key")),
            _fact(
                "PVGIS years",
                f"{pvgis_params.get('start_year', '—')}–{pvgis_params.get('end_year', '—')}"
                if pvgis_params
                else _display_list((pvgis_profile or {}).get("years_averaged") or []),
            ),
            _fact("PV technology", pvgis_params.get("pv_technology") or (pvgis_profile or {}).get("pv_technology")),
            _fact("Mounting place", pvgis_params.get("mounting_place") or (pvgis_profile or {}).get("mounting_place")),
            _fact(
                "System loss",
                _display_number(
                    pvgis_params.get("system_loss_pct") or (pvgis_profile or {}).get("system_loss_pct"),
                    digits=1,
                    suffix="%",
                ),
            ),
            _fact("Use horizon", "Yes" if pvgis_params.get("use_horizon", True) else "No"),
            _fact("Optimal angles", "Yes" if pvgis_params.get("optimal_angles", True) else "No"),
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
                "Grid import (overhead)",
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
        "energy_breakdown_chart_visual": build_green_energy_breakdown_chart(
            total_facility_kwh=result.get("total_facility_kwh"),
            total_it_kwh=result.get("total_it_kwh"),
            total_overhead_kwh=result.get("total_overhead_kwh"),
            total_pv_generation_kwh=result.get("total_pv_generation_kwh"),
            total_pv_to_overhead_kwh=result.get("total_pv_to_overhead_kwh"),
            total_pv_to_bess_kwh=result.get("total_pv_to_bess_kwh"),
            total_bess_discharge_kwh=result.get("total_bess_discharge_kwh"),
            total_fuel_cell_kwh=result.get("total_fuel_cell_kwh"),
            total_grid_import_kwh=result.get("total_grid_import_kwh"),
            total_pv_curtailed_kwh=result.get("total_pv_curtailed_kwh"),
        ),
        "dispatch_hourly_chart_visual": build_green_dispatch_hourly_chart(
            result.get("hourly_dispatch") or [],
        ),
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
                    "label": "Grid import (overhead)",
                    "value": _display_energy_mwh(result.get("total_grid_import_kwh")),
                },
            ],
        ),
        "narrative": _build_green_energy_narrative(
            result=result,
            pv_profile_source=pv_profile_source,
        ),
        "advisory_table": _build_advisory_table(green_energy.get("advisory_levels")),
    }


def _build_advisory_table(advisory_levels: list | None) -> dict[str, Any] | None:
    """Build advisory sizing table with PV-only and PV+BESS columns.

    Uses smart unit formatting and shows 'max X%' when PV-only hits its
    physical ceiling (no storage means nighttime hours can never be covered).
    """
    if not advisory_levels:
        return None

    rows: list[dict[str, str]] = []
    for level in advisory_levels:
        ceiling = level.get("pv_only_ceiling_reached", False)
        achieved = level.get("pv_only_coverage_achieved")

        if ceiling and achieved is not None:
            pv_only_display = f"max {achieved * 100:.0f}%"
        else:
            pv_only_display = _smart_power(level.get("pv_only_kwp_needed"))

        rows.append({
            "coverage": _display_percent(level.get("coverage_target"), digits=0),
            "pv_only": pv_only_display,
            "pv_kwp": _smart_power(level.get("pv_kwp_needed")),
            "bess_kwh": _smart_energy_kwh(level.get("bess_kwh_needed")),
            "gen_mwh": _smart_energy_mwh(level.get("annual_generation_mwh")),
            "co2_t": _display_number(level.get("co2_avoided_tonnes"), digits=1, suffix="t"),
        })

    return _table(
        "Advisory: Coverage Target Sizing (PV-Only vs PV+BESS)",
        [
            ("coverage", "Coverage Target"),
            ("pv_only", "PV-Only"),
            ("pv_kwp", "PV+BESS PV"),
            ("bess_kwh", "BESS"),
            ("gen_mwh", "Annual Gen"),
            ("co2_t", "CO₂ Avoided"),
        ],
        rows,
    )
