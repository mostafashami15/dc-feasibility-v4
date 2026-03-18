"""
DC Feasibility Tool v4 — Green Energy API Routes
===================================================
Hourly green energy dispatch simulation: PV → BESS → FC → grid.

Serves: Page 5 (Green Energy) in the Architecture Agreement Section 6.

Endpoints:
    POST /api/green/simulate           — Run the 6-step hourly dispatch simulation
    POST /api/green/scenario-dispatch  — Run green dispatch on real scenario hourly arrays
    POST /api/green/firm-capacity      — Solve firm IT capacity and support pathways

Flow (how the frontend uses this):
    1. User configures PV capacity, BESS size, fuel cell capacity
    2. Frontend sends hourly facility/IT arrays (from a scenario run)
       plus hourly PV generation supplied by the user or an external source
    3. Backend runs the dispatch simulation
    4. Frontend renders:
       - Hourly dispatch stacked area chart
       - Annual energy breakdown pie chart
       - Renewable fraction, overhead coverage, CO₂ avoided
       - BESS SoC time series

Engine function used:
    engine.green_energy.simulate_green_dispatch — Full 8,760-hour dispatch

Reference: Architecture Agreement v2.0, Section 3.9, 6 (Page 5)
"""

from dataclasses import asdict
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.green_energy import (
    simulate_green_dispatch,
    simulate_firm_capacity_support,
    find_max_firm_it_capacity,
    recommend_support_portfolios,
)
from engine.solar import (
    PVGISNormalizedProfile,
    build_representative_pvgis_profile,
    make_pvgis_profile_key,
    scale_normalized_profile,
)
from engine.models import Scenario
from engine.power import solve
from engine.pue_engine import simulate_hourly, build_hourly_facility_factors
from engine.assumptions import evaluate_compatibility
from api.store import (
    delete_solar_cache,
    get_site,
    get_solar_profile,
    get_weather,
    has_solar_profile,
    save_solar_profile,
)


# ─────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/green", tags=["Green Energy"])


# ─────────────────────────────────────────────────────────────
# Request Model
# ─────────────────────────────────────────────────────────────

class GreenSimulateRequest(BaseModel):
    """Request for green energy dispatch simulation.

    All hourly arrays must have the same length (typically 8,760
    for a full year). The hourly facility and IT power come from
    a previous scenario run (via pue_engine.simulate_hourly).

    If PV data is not available, pass a list of zeros for
    hourly_pv_kw — the simulation will show pure grid import.
    """

    # ── Hourly input arrays ──
    hourly_facility_kw: list[float] = Field(
        min_length=1,
        description=(
            "Hourly total facility power in kW. "
            "Source: pue_engine.py → HourlySimResult.hourly_facility_kw"
        ),
    )
    hourly_it_kw: list[float] = Field(
        min_length=1,
        description=(
            "Hourly IT load in kW. "
            "Source: pue_engine.py → HourlySimResult.hourly_it_kw"
        ),
    )
    hourly_pv_kw: list[float] = Field(
        min_length=1,
        description=(
            "Hourly PV AC output in kW. "
            "Source: caller-provided profile (manual upload or external data). "
            "Pass list of zeros if no PV installed."
        ),
    )

    # ── BESS configuration ──
    bess_capacity_kwh: float = Field(
        default=0.0, ge=0,
        description=(
            "Battery energy storage capacity in kWh. 0 = no BESS. "
            "Source: NREL ATB 2024 for typical sizing."
        ),
    )
    bess_roundtrip_efficiency: float = Field(
        default=0.875, gt=0, le=1.0,
        description=(
            "Round-trip efficiency. Default 0.875 (87.5%). "
            "Source: NREL ATB 2024, lithium-ion utility-scale (0.85–0.90)."
        ),
    )
    bess_initial_soc_kwh: float = Field(
        default=0.0, ge=0,
        description="Initial state of charge in kWh. Default: 0 (empty)."
    )

    # ── Fuel cell ──
    fuel_cell_capacity_kw: float = Field(
        default=0.0, ge=0,
        description=(
            "Maximum fuel cell dispatch power in kW. 0 = no fuel cell. "
            "Source: Architecture Agreement Section 3.9."
        ),
    )

    # ── Reporting metadata ──
    pv_capacity_kwp: float = Field(
        default=0.0, ge=0,
        description="Installed PV peak capacity in kWp (for reporting only)."
    )

    # ── CO₂ factor ──
    grid_co2_kg_per_kwh: float = Field(
        default=0.256, ge=0,
        description=(
            "Grid CO₂ emission factor in kg CO₂/kWh. "
            "Default: 0.256 (Italy 2022). "
            "Source: ISPRA (2023), 'Fattori di emissione atmosferica di gas a "
            "effetto serra nel settore elettrico nazionale e nei principali "
            "Paesi Europei'."
        ),
    )

    # ── Response options ──
    include_hourly_dispatch: bool = Field(
        default=False,
        description=(
            "Include the full hourly dispatch array in the response. "
            "This adds 8,760 objects to the response (~2 MB). "
            "Set True only when the frontend needs to render the "
            "hourly dispatch chart. Default False for bandwidth."
        ),
    )


class FirmCapacityRequest(BaseModel):
    """Request for committed IT capacity with peak support compensation."""

    site_id: str = Field(description="UUID of the saved site")
    scenario: Scenario = Field(description="Scenario configuration")
    target_it_load_mw: Optional[float] = Field(
        default=None, gt=0,
        description=(
            "Optional IT target to test directly. If omitted, the backend "
            "solves for the maximum constant firm IT load."
        ),
    )
    hourly_pv_kw: Optional[list[float]] = Field(
        default=None,
        description=(
            "Optional hourly PV generation profile in kW. If omitted, "
            "PV support is assumed to be zero."
        ),
    )
    pvgis_profile_key: Optional[str] = Field(
        default=None,
        description=(
            "Optional cache key for a normalized PVGIS 1 kWp profile. "
            "If provided and hourly_pv_kw is omitted, the backend scales the "
            "cached profile by pv_capacity_kwp."
        ),
    )
    pv_capacity_kwp: float = Field(
        default=0.0, ge=0,
        description="Installed PV peak capacity in kWp for scaling a cached PVGIS profile."
    )
    bess_capacity_kwh: float = Field(default=0.0, ge=0)
    bess_roundtrip_efficiency: float = Field(default=0.875, gt=0, le=1.0)
    bess_initial_soc_kwh: float = Field(default=0.0, ge=0)
    fuel_cell_capacity_kw: float = Field(default=0.0, ge=0)
    backup_dispatch_capacity_kw: float = Field(
        default=0.0, ge=0,
        description="Dispatchable backup support (e.g. genset) in kW."
    )
    cyclic_bess: bool = Field(
        default=True,
        description=(
            "Iterate the representative year until the BESS start/end SoC "
            "converges, avoiding an arbitrary one-off initial state."
        ),
    )
    include_hourly_dispatch: bool = Field(
        default=False,
        description="Include the full hourly peak-support dispatch trace."
    )


class ScenarioGreenDispatchRequest(BaseModel):
    """Run green-energy dispatch from a saved site + scenario."""

    site_id: str = Field(description="UUID of the saved site")
    scenario: Scenario = Field(description="Scenario configuration")
    hourly_pv_kw: Optional[list[float]] = Field(
        default=None,
        description=(
            "Optional hourly PV profile in kW. If omitted, the dispatch "
            "simulation runs with zero PV generation."
        ),
    )
    pvgis_profile_key: Optional[str] = Field(
        default=None,
        description=(
            "Optional cache key for a normalized PVGIS 1 kWp profile. "
            "If provided and hourly_pv_kw is omitted, the backend scales the "
            "cached profile by pv_capacity_kwp."
        ),
    )
    bess_capacity_kwh: float = Field(default=0.0, ge=0)
    bess_roundtrip_efficiency: float = Field(default=0.875, gt=0, le=1.0)
    bess_initial_soc_kwh: float = Field(default=0.0, ge=0)
    fuel_cell_capacity_kw: float = Field(default=0.0, ge=0)
    pv_capacity_kwp: float = Field(default=0.0, ge=0)
    grid_co2_kg_per_kwh: float = Field(default=0.256, ge=0)
    include_hourly_dispatch: bool = Field(default=False)


class PVGISFetchRequest(BaseModel):
    """Fetch and cache a normalized 1 kWp hourly PV profile from PVGIS."""

    site_id: str = Field(description="UUID of the saved site")
    start_year: int = Field(default=2019)
    end_year: int = Field(default=2023)
    pv_technology: Literal["crystSi", "CIS", "CdTe", "Unknown"] = Field(
        default="crystSi",
        description="PVGIS pvtechchoice parameter."
    )
    mounting_place: Literal["free", "building"] = Field(
        default="free",
        description="PVGIS mountingplace parameter."
    )
    system_loss_pct: float = Field(
        default=14.0, ge=0, le=100,
        description="Total system loss percentage sent to PVGIS."
    )
    use_horizon: bool = Field(
        default=True,
        description="Include PVGIS terrain horizon data when available."
    )
    optimal_angles: bool = Field(
        default=True,
        description="Let PVGIS calculate the optimal fixed tilt/azimuth."
    )
    surface_tilt_deg: Optional[float] = Field(default=None, ge=0, le=90)
    surface_azimuth_deg: Optional[float] = Field(default=None, ge=-180, le=180)
    force_refresh: bool = Field(
        default=False,
        description="Ignore the cache and refetch PVGIS for this exact parameter set."
    )


def _serialize_green_result(result, include_hourly_dispatch: bool) -> dict:
    """Convert a GreenEnergyResult dataclass to a JSON-safe response."""
    response = {
        "total_overhead_kwh": round(result.total_overhead_kwh, 1),
        "total_pv_generation_kwh": round(result.total_pv_generation_kwh, 1),
        "total_pv_to_overhead_kwh": round(result.total_pv_to_overhead_kwh, 1),
        "total_pv_to_bess_kwh": round(result.total_pv_to_bess_kwh, 1),
        "total_pv_curtailed_kwh": round(result.total_pv_curtailed_kwh, 1),
        "total_bess_discharge_kwh": round(result.total_bess_discharge_kwh, 1),
        "total_fuel_cell_kwh": round(result.total_fuel_cell_kwh, 1),
        "total_grid_import_kwh": round(result.total_grid_import_kwh, 1),
        "overhead_coverage_fraction": round(result.overhead_coverage_fraction, 4),
        "renewable_fraction": round(result.renewable_fraction, 4),
        "pv_self_consumption_fraction": round(result.pv_self_consumption_fraction, 4),
        "bess_cycles_equivalent": round(result.bess_cycles_equivalent, 1),
        "co2_avoided_tonnes": round(result.co2_avoided_tonnes, 2),
        "pv_capacity_kwp": result.pv_capacity_kwp,
        "bess_capacity_kwh": result.bess_capacity_kwh,
        "bess_roundtrip_efficiency": result.bess_roundtrip_efficiency,
        "fuel_cell_capacity_kw": result.fuel_cell_capacity_kw,
        "total_facility_kwh": round(result.total_facility_kwh, 1),
        "total_it_kwh": round(result.total_it_kwh, 1),
    }
    if include_hourly_dispatch:
        response["hourly_dispatch"] = [asdict(h) for h in result.hourly_dispatch]
    return response


def _serialize_pvgis_profile(
    profile: PVGISNormalizedProfile,
    *,
    site_name: str,
    from_cache: bool,
) -> dict:
    """Convert a normalized PVGIS profile dataclass to a JSON-safe response."""
    return {
        "site_id": profile.site_id,
        "site_name": site_name,
        "profile_key": profile.profile_key,
        "from_cache": from_cache,
        "latitude": round(profile.latitude, 6),
        "longitude": round(profile.longitude, 6),
        "start_year": profile.start_year,
        "end_year": profile.end_year,
        "years_averaged": profile.years_averaged,
        "pv_technology": profile.pv_technology,
        "mounting_place": profile.mounting_place,
        "system_loss_pct": round(profile.system_loss_pct, 3),
        "use_horizon": profile.use_horizon,
        "optimal_angles": profile.optimal_angles,
        "surface_tilt_deg": (
            round(profile.surface_tilt_deg, 3)
            if profile.surface_tilt_deg is not None
            else None
        ),
        "surface_azimuth_deg": (
            round(profile.surface_azimuth_deg, 3)
            if profile.surface_azimuth_deg is not None
            else None
        ),
        "source": profile.source,
        "radiation_database": profile.radiation_database,
        "elevation_m": (
            round(profile.elevation_m, 2)
            if profile.elevation_m is not None
            else None
        ),
        "pv_module_info": profile.pv_module_info,
        "hours": profile.hours,
        "hourly_pv_kw_per_kwp": profile.hourly_pv_kw_per_kwp,
    }


def _load_cached_pvgis_profile(
    *,
    site_id: str,
    profile_key: str,
) -> PVGISNormalizedProfile:
    """Load one cached normalized PVGIS profile or raise a 404."""
    cached = get_solar_profile(site_id, profile_key)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Cached PVGIS profile not found for this site and parameter set. "
                "Fetch the profile again from the Green Energy page."
            ),
        )
    cached_payload = dict(cached)
    # The dataclass computes `hours` from the hourly series on load, so cached
    # JSON from a previous save must not pass it back into the constructor.
    cached_payload.pop("hours", None)
    return PVGISNormalizedProfile(**cached_payload)


def _resolve_hourly_pv_input(
    *,
    site_id: str,
    expected_hours: int,
    hourly_pv_kw: Optional[list[float]],
    pvgis_profile_key: Optional[str],
    pv_capacity_kwp: float,
) -> tuple[list[float], str]:
    """Resolve manual PV input vs. cached normalized PVGIS profile vs. zero PV."""
    if hourly_pv_kw is not None:
        if len(hourly_pv_kw) != expected_hours:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"hourly_pv_kw ({len(hourly_pv_kw)}) must have the same "
                    f"length as hourly weather ({expected_hours})"
                ),
            )
        return hourly_pv_kw, "manual"

    if pvgis_profile_key is not None:
        profile = _load_cached_pvgis_profile(site_id=site_id, profile_key=pvgis_profile_key)
        if profile.hours != expected_hours:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cached PVGIS profile has {profile.hours} hours but the "
                    f"site weather/scenario expects {expected_hours} hours"
                ),
            )
        try:
            return scale_normalized_profile(
                profile.hourly_pv_kw_per_kwp,
                pv_capacity_kwp,
            ), "pvgis"
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return [0.0] * expected_hours, "zero"


# ─────────────────────────────────────────────────────────────
# Simulate
# ─────────────────────────────────────────────────────────────

@router.post("/fetch-pvgis-profile")
async def fetch_pvgis_profile_endpoint(request: PVGISFetchRequest):
    """Fetch and cache a normalized 1 kWp representative-year PVGIS profile."""
    site_result = get_site(request.site_id)
    if site_result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Site '{request.site_id}' not found"
        )
    _, site = site_result

    if site.latitude is None or site.longitude is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "The selected site does not have saved coordinates. "
                "Set the site location first before fetching PVGIS data."
            ),
        )

    profile_key = make_pvgis_profile_key(
        site_id=request.site_id,
        latitude=site.latitude,
        longitude=site.longitude,
        start_year=request.start_year,
        end_year=request.end_year,
        pv_technology=request.pv_technology,
        mounting_place=request.mounting_place,
        system_loss_pct=request.system_loss_pct,
        use_horizon=request.use_horizon,
        optimal_angles=request.optimal_angles,
        surface_tilt_deg=request.surface_tilt_deg,
        surface_azimuth_deg=request.surface_azimuth_deg,
    )

    if request.force_refresh and has_solar_profile(request.site_id, profile_key):
        delete_solar_cache(request.site_id, profile_key)

    if has_solar_profile(request.site_id, profile_key):
        cached = _load_cached_pvgis_profile(
            site_id=request.site_id,
            profile_key=profile_key,
        )
        return _serialize_pvgis_profile(cached, site_name=site.name, from_cache=True)

    try:
        profile = build_representative_pvgis_profile(
            site_id=request.site_id,
            latitude=site.latitude,
            longitude=site.longitude,
            start_year=request.start_year,
            end_year=request.end_year,
            pv_technology=request.pv_technology,
            mounting_place=request.mounting_place,
            system_loss_pct=request.system_loss_pct,
            use_horizon=request.use_horizon,
            optimal_angles=request.optimal_angles,
            surface_tilt_deg=request.surface_tilt_deg,
            surface_azimuth_deg=request.surface_azimuth_deg,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"PVGIS fetch failed: {exc}",
        )

    save_solar_profile(
        request.site_id,
        profile.profile_key,
        asdict(profile),
    )
    return _serialize_pvgis_profile(profile, site_name=site.name, from_cache=False)


@router.post("/simulate")
async def simulate_green_endpoint(request: GreenSimulateRequest):
    """Run the 6-step hourly green energy dispatch simulation.

    Dispatch priority (Architecture Agreement Section 3.9):
        1. PV generation → apply to overhead (facility − IT)
        2. Surplus PV → charge BESS (bounded by capacity × η_oneway)
        3. Remaining surplus → curtail / export to grid
        4. Remaining deficit → discharge BESS
        5. Remaining deficit → fuel cell dispatch
        6. Remaining deficit → grid import

    The simulation runs for every hour in the input arrays.
    Overhead = P_facility − P_IT (the non-IT load that green
    energy can offset: cooling, fans, lighting, losses).

    Returns:
        - Annual energy totals (kWh) per source
        - Overhead coverage fraction (0–1)
        - Renewable fraction (0–1)
        - PV self-consumption fraction
        - BESS equivalent cycles
        - CO₂ avoided (tonnes)
        - Optionally: full hourly dispatch detail
    """
    # ── Validate array lengths ──
    n = len(request.hourly_facility_kw)
    if len(request.hourly_it_kw) != n:
        raise HTTPException(
            status_code=400,
            detail=(
                f"hourly_facility_kw ({n}) and hourly_it_kw "
                f"({len(request.hourly_it_kw)}) must have the same length"
            ),
        )
    if len(request.hourly_pv_kw) != n:
        raise HTTPException(
            status_code=400,
            detail=(
                f"hourly_facility_kw ({n}) and hourly_pv_kw "
                f"({len(request.hourly_pv_kw)}) must have the same length"
            ),
        )

    # ── Validate BESS initial SoC ──
    if request.bess_initial_soc_kwh > request.bess_capacity_kwh:
        raise HTTPException(
            status_code=400,
            detail=(
                f"bess_initial_soc_kwh ({request.bess_initial_soc_kwh}) "
                f"cannot exceed bess_capacity_kwh ({request.bess_capacity_kwh})"
            ),
        )

    # ── Run simulation ──
    try:
        result = simulate_green_dispatch(
            hourly_facility_kw=request.hourly_facility_kw,
            hourly_it_kw=request.hourly_it_kw,
            hourly_pv_kw=request.hourly_pv_kw,
            bess_capacity_kwh=request.bess_capacity_kwh,
            bess_roundtrip_efficiency=request.bess_roundtrip_efficiency,
            bess_initial_soc_kwh=request.bess_initial_soc_kwh,
            fuel_cell_capacity_kw=request.fuel_cell_capacity_kw,
            pv_capacity_kwp=request.pv_capacity_kwp,
            grid_co2_kg_per_kwh=request.grid_co2_kg_per_kwh,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _serialize_green_result(result, request.include_hourly_dispatch)


@router.post("/scenario-dispatch")
async def scenario_dispatch_endpoint(request: ScenarioGreenDispatchRequest):
    """Run green dispatch using the real hourly arrays of a saved scenario."""
    site_result = get_site(request.site_id)
    if site_result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Site '{request.site_id}' not found"
        )
    _, site = site_result

    compatibility_status, compatibility_reasons = evaluate_compatibility(
        request.scenario.load_type.value,
        request.scenario.cooling_type.value,
        density_scenario=request.scenario.density_scenario.value,
    )
    if compatibility_status == "incompatible":
        raise HTTPException(
            status_code=400,
            detail="; ".join(compatibility_reasons),
        )

    weather = get_weather(request.site_id)
    if weather is None:
        raise HTTPException(
            status_code=400,
            detail="Hourly weather data is required for scenario green dispatch"
        )

    temperatures = weather["temperatures"]
    humidities = weather.get("humidities")

    space, power = solve(site, request.scenario)
    del space  # Only the hourly facility and IT arrays are needed here.

    try:
        # When binding constraint is AREA, the space-derived IT load is the
        # true cap — run in area-constrained mode even if power is confirmed.
        if (
            site.power_confirmed
            and site.available_power_mw > 0
            and power.binding_constraint == "POWER"
        ):
            hourly = simulate_hourly(
                temperatures=temperatures,
                humidities=humidities,
                cooling_type=request.scenario.cooling_type.value,
                eta_chain=power.eta_chain,
                facility_power_kw=power.facility_power_mw * 1000,
            )
        else:
            hourly = simulate_hourly(
                temperatures=temperatures,
                humidities=humidities,
                cooling_type=request.scenario.cooling_type.value,
                eta_chain=power.eta_chain,
                it_load_kw=power.it_load_mw * 1000,
            )

        resolved_hourly_pv_kw, pv_profile_source = _resolve_hourly_pv_input(
            site_id=request.site_id,
            expected_hours=len(hourly.hourly_facility_kw),
            hourly_pv_kw=request.hourly_pv_kw,
            pvgis_profile_key=request.pvgis_profile_key,
            pv_capacity_kwp=request.pv_capacity_kwp,
        )

        result = simulate_green_dispatch(
            hourly_facility_kw=hourly.hourly_facility_kw,
            hourly_it_kw=hourly.hourly_it_kw,
            hourly_pv_kw=resolved_hourly_pv_kw,
            bess_capacity_kwh=request.bess_capacity_kwh,
            bess_roundtrip_efficiency=request.bess_roundtrip_efficiency,
            bess_initial_soc_kwh=request.bess_initial_soc_kwh,
            fuel_cell_capacity_kw=request.fuel_cell_capacity_kw,
            pv_capacity_kwp=request.pv_capacity_kwp,
            grid_co2_kg_per_kwh=request.grid_co2_kg_per_kwh,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    response = _serialize_green_result(result, request.include_hourly_dispatch)
    response["site_name"] = site.name
    response["hours"] = len(hourly.hourly_facility_kw)
    response["annual_pue"] = round(hourly.annual_pue, 4)
    response["pue_source"] = "hourly"
    response["nominal_it_mw"] = round(power.it_load_mw, 3)
    response["committed_it_mw"] = round(hourly.it_capacity_p99_kw / 1000, 3)
    response["pv_profile_source"] = pv_profile_source
    response["pvgis_profile_key"] = (
        request.pvgis_profile_key if pv_profile_source == "pvgis" else None
    )
    return response


@router.post("/firm-capacity")
async def firm_capacity_endpoint(request: FirmCapacityRequest):
    """Solve committed IT capacity under a fixed grid cap plus support assets."""
    site_result = get_site(request.site_id)
    if site_result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Site '{request.site_id}' not found"
        )
    _, site = site_result

    if not site.power_confirmed or site.available_power_mw <= 0:
        raise HTTPException(
            status_code=400,
            detail="Firm capacity support analysis requires confirmed available power"
        )

    compatibility_status, compatibility_reasons = evaluate_compatibility(
        request.scenario.load_type.value,
        request.scenario.cooling_type.value,
        density_scenario=request.scenario.density_scenario.value,
    )
    if compatibility_status == "incompatible":
        raise HTTPException(
            status_code=400,
            detail="; ".join(compatibility_reasons),
        )

    weather = get_weather(request.site_id)
    if weather is None:
        raise HTTPException(
            status_code=400,
            detail="Hourly weather data is required for firm capacity support analysis"
        )

    space, power = solve(site, request.scenario)
    temperatures = weather["temperatures"]
    humidities = weather.get("humidities")

    grid_capacity_kw = power.facility_power_mw * 1000
    space_limit_kw = space.effective_racks * power.rack_density_kw

    try:
        resolved_hourly_pv_kw, _ = _resolve_hourly_pv_input(
            site_id=request.site_id,
            expected_hours=len(temperatures),
            hourly_pv_kw=request.hourly_pv_kw,
            pvgis_profile_key=request.pvgis_profile_key,
            pv_capacity_kwp=request.pv_capacity_kwp,
        )
        baseline = simulate_hourly(
            temperatures=temperatures,
            humidities=humidities,
            cooling_type=request.scenario.cooling_type.value,
            eta_chain=power.eta_chain,
            facility_power_kw=grid_capacity_kw,
        )
        factors = build_hourly_facility_factors(
            temperatures=temperatures,
            humidities=humidities,
            cooling_type=request.scenario.cooling_type.value,
            eta_chain=power.eta_chain,
        )
        supported = find_max_firm_it_capacity(
            hourly_facility_factors=factors,
            grid_capacity_kw=grid_capacity_kw,
            max_it_kw=space_limit_kw,
            hourly_pv_kw=resolved_hourly_pv_kw,
            bess_capacity_kwh=request.bess_capacity_kwh,
            bess_roundtrip_efficiency=request.bess_roundtrip_efficiency,
            bess_initial_soc_kwh=request.bess_initial_soc_kwh,
            fuel_cell_capacity_kw=request.fuel_cell_capacity_kw,
            backup_dispatch_capacity_kw=request.backup_dispatch_capacity_kw,
            cyclic_bess=request.cyclic_bess,
        )
        target_eval = None
        if request.target_it_load_mw is not None:
            target_eval = simulate_firm_capacity_support(
                hourly_facility_factors=factors,
                target_it_kw=request.target_it_load_mw * 1000,
                grid_capacity_kw=grid_capacity_kw,
                hourly_pv_kw=resolved_hourly_pv_kw,
                bess_capacity_kwh=request.bess_capacity_kwh,
                bess_roundtrip_efficiency=request.bess_roundtrip_efficiency,
                bess_initial_soc_kwh=request.bess_initial_soc_kwh,
                fuel_cell_capacity_kw=request.fuel_cell_capacity_kw,
                backup_dispatch_capacity_kw=request.backup_dispatch_capacity_kw,
                cyclic_bess=request.cyclic_bess,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    response = {
        "baseline": {
            "nominal_it_mw": round(power.it_load_mw, 3),
            "worst_it_mw": round(baseline.it_capacity_worst_kw / 1000, 3),
            "p99_it_mw": round(baseline.it_capacity_p99_kw / 1000, 3),
            "p90_it_mw": round(baseline.it_capacity_p90_kw / 1000, 3),
            "mean_it_mw": round(baseline.it_capacity_mean_kw / 1000, 3),
            "best_it_mw": round(baseline.it_capacity_best_kw / 1000, 3),
            "annual_pue": round(baseline.annual_pue, 4),
            "facility_power_mw": round(power.facility_power_mw, 3),
            "procurement_power_mw": round(power.procurement_power_mw, 3),
        },
        "supported": {
            "max_firm_it_mw": round(supported.target_it_kw / 1000, 3),
            "gain_vs_worst_mw": round(
                (supported.target_it_kw - baseline.it_capacity_worst_kw) / 1000, 3
            ),
            "gain_vs_p99_mw": round(
                (supported.target_it_kw - baseline.it_capacity_p99_kw) / 1000, 3
            ),
            "max_required_facility_mw": round(
                supported.max_required_facility_kw / 1000, 3
            ),
            "peak_support_mw": round(supported.peak_support_kw / 1000, 3),
            "hours_above_grid_cap": supported.hours_above_grid_cap,
            "hours_with_capacity_support": supported.hours_with_capacity_support,
            "grid_to_bess_mwh": round(supported.total_grid_to_bess_kwh / 1000, 3),
            "pv_direct_mwh": round(supported.total_pv_direct_kwh / 1000, 3),
            "pv_to_bess_mwh": round(supported.total_pv_to_bess_kwh / 1000, 3),
            "bess_discharge_mwh": round(supported.total_bess_discharge_kwh / 1000, 3),
            "fuel_cell_mwh": round(supported.total_fuel_cell_kwh / 1000, 3),
            "backup_dispatch_mwh": round(
                supported.total_backup_dispatch_kwh / 1000, 3
            ),
            "cyclic_bess": supported.cyclic_bess,
            "cyclic_converged": supported.cyclic_converged,
            "initial_bess_soc_mwh": round(supported.initial_bess_soc_kwh / 1000, 3),
            "final_bess_soc_mwh": round(supported.final_bess_soc_kwh / 1000, 3),
        },
        "target_evaluation": None,
        "recommendations": None,
    }

    if target_eval is not None:
        response["target_evaluation"] = {
            "target_it_mw": round(target_eval.target_it_kw / 1000, 3),
            "feasible": target_eval.feasible,
            "peak_support_mw": round(target_eval.peak_support_kw / 1000, 3),
            "peak_unmet_mw": round(target_eval.peak_unmet_kw / 1000, 3),
            "hours_above_grid_cap": target_eval.hours_above_grid_cap,
            "hours_with_capacity_support": target_eval.hours_with_capacity_support,
            "unmet_hours": target_eval.unmet_hours,
            "unmet_energy_mwh": round(target_eval.total_unmet_kwh / 1000, 3),
            "grid_to_bess_mwh": round(target_eval.total_grid_to_bess_kwh / 1000, 3),
            "pv_direct_mwh": round(target_eval.total_pv_direct_kwh / 1000, 3),
            "bess_discharge_mwh": round(target_eval.total_bess_discharge_kwh / 1000, 3),
            "fuel_cell_mwh": round(target_eval.total_fuel_cell_kwh / 1000, 3),
            "backup_dispatch_mwh": round(
                target_eval.total_backup_dispatch_kwh / 1000, 3
            ),
            "cyclic_bess": target_eval.cyclic_bess,
            "cyclic_converged": target_eval.cyclic_converged,
        }
        if request.include_hourly_dispatch:
            response["target_evaluation"]["hourly_dispatch"] = [
                asdict(h) for h in target_eval.hourly_dispatch
            ]

    recommendation_target_kw = (
        request.target_it_load_mw * 1000
        if request.target_it_load_mw is not None
        else power.it_load_mw * 1000
    )
    recommendations = recommend_support_portfolios(
        hourly_facility_factors=factors,
        target_it_kw=recommendation_target_kw,
        grid_capacity_kw=grid_capacity_kw,
        baseline_p99_kw=baseline.it_capacity_p99_kw,
        baseline_worst_kw=baseline.it_capacity_worst_kw,
        hourly_pv_kw=resolved_hourly_pv_kw,
        bess_roundtrip_efficiency=request.bess_roundtrip_efficiency,
        cyclic_bess=request.cyclic_bess,
    )
    response["recommendations"] = {
        "target_it_mw": round(recommendations.target_it_kw / 1000, 3),
        "target_already_feasible": recommendations.target_already_feasible,
        "annual_support_energy_mwh": round(
            recommendations.annual_support_energy_kwh / 1000, 3
        ),
        "peak_support_mw": round(recommendations.peak_support_kw / 1000, 3),
        "hours_above_grid_cap": recommendations.hours_above_grid_cap,
        "gap_vs_p99_mw": round(recommendations.gap_vs_p99_kw / 1000, 3),
        "gap_vs_worst_mw": round(recommendations.gap_vs_worst_kw / 1000, 3),
        "candidates": [
            {
                "key": candidate.key,
                "label": candidate.label,
                "description": candidate.description,
                "target_it_mw": round(candidate.target_it_kw / 1000, 3),
                "feasible": candidate.feasible,
                "bess_capacity_mwh": round(candidate.bess_capacity_kwh / 1000, 3),
                "fuel_cell_mw": round(candidate.fuel_cell_capacity_kw / 1000, 3),
                "backup_dispatch_mw": round(
                    candidate.backup_dispatch_capacity_kw / 1000, 3
                ),
                "peak_support_mw": round(candidate.peak_support_kw / 1000, 3),
                "support_hours": candidate.hours_with_capacity_support,
                "grid_to_bess_mwh": round(candidate.total_grid_to_bess_kwh / 1000, 3),
                "bess_discharge_mwh": round(
                    candidate.total_bess_discharge_kwh / 1000, 3
                ),
                "fuel_cell_mwh": round(candidate.total_fuel_cell_kwh / 1000, 3),
                "backup_dispatch_mwh": round(
                    candidate.total_backup_dispatch_kwh / 1000, 3
                ),
                "unmet_energy_mwh": round(candidate.total_unmet_kwh / 1000, 3),
                "notes": candidate.notes,
            }
            for candidate in recommendations.candidates
        ],
    }

    return response
