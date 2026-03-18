"""Constants and Pydantic input models for report data shaping."""
from __future__ import annotations

from pydantic import BaseModel

from engine.ranking import LoadMixResult


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
    hourly_dispatch: list[dict[str, float]] | None = None


class GreenEnergyReportInput(BaseModel):
    result_key: str | None = None
    result: GreenEnergyReportResultInput
    pv_profile_name: str | None = None
    pvgis_profile: GreenEnergyPVGISProfileInput | None = None
    bess_initial_soc_kwh: float | None = None
    grid_co2_kg_per_kwh: float | None = None
