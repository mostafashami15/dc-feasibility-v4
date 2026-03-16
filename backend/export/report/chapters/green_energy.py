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
