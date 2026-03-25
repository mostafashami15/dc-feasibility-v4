"""
DC Feasibility Tool v4 — Scenario API Routes
===============================================
Run scenarios, compute results, score and rank, sensitivity analysis,
backup power comparison, footprint analysis, and load mix optimization.

Serves: Pages 3–4 (Scenario Configuration + Results Dashboard)
        in the Architecture Agreement Section 6.

Endpoints:
    POST /api/scenarios/run            — Run one site × scenario combination
    POST /api/scenarios/batch          — Run all combinations for selected sites/scenarios
    POST /api/scenarios/score          — Score and rank a set of results
    POST /api/scenarios/expansion-advisory — Advisory future build-out potential
    POST /api/scenarios/hourly-profiles — Daily IT/PUE profiles from the hourly year
    POST /api/scenarios/load-mix       — Load mix optimization (Section 3.12)
    POST /api/scenarios/tornado        — Tornado chart (Section 3.11)
    POST /api/scenarios/break-even     — Break-even solver (Section 3.11)
    POST /api/scenarios/backup-power   — Backup power comparison (Section 3.8)
    POST /api/scenarios/footprint      — Infrastructure footprint (Section 3.13)
    POST /api/scenarios/firm-capacity-advisory — Auto-computed firm capacity advisory

Engine functions used:
    engine.power.solve                     — Space + power chain
    engine.pue_engine.simulate_hourly      — 8,760-hour PUE simulation
    engine.ranking.score_scenario          — 5-component composite scoring
    engine.ranking.optimize_load_mix       — Load mix optimizer
    engine.sensitivity.compute_tornado     — One-at-a-time parameter variation
    engine.sensitivity.compute_break_even  — Algebraic break-even solver
    engine.backup_power.compare_technologies — 5-technology comparison
    engine.footprint.compute_footprint     — Infrastructure area calculations
    engine.assumptions — LOAD_PROFILES, COOLING_PROFILES, REDUNDANCY_PROFILES

Reference: Architecture Agreement v2.0, Sections 3.1–3.17, 6, 8
"""

from typing import Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException

from engine.models import (
    Site,
    Scenario,
    ScenarioResult,
    SpaceResult,
    PowerResult,
    LoadType,
    CoolingType,
    RedundancyLevel,
    DensityScenario,
    RAGStatus,
    BackupPowerType,
)
from engine.power import solve, apply_hourly_rag_adjustments
from engine.pue_engine import simulate_hourly
from engine.ranking import score_scenario, optimize_load_mix
from engine.sensitivity import compute_tornado, compute_break_even
from engine.backup_power import compare_technologies, compute_firm_capacity_advisory
from engine.expansion import compute_expansion_advisory
from engine.footprint import compute_footprint
from engine.assumptions import (
    evaluate_compatibility,
)
from engine.assumption_overrides import (
    get_applied_overrides_for_scenario,
    get_assumption_override_preset_label,
    record_assumption_override_preset_run,
    validate_assumption_override_preset_key,
)
from engine.smart_preset import get_guided_presets, build_guided_scenarios
from api.store import get_site, get_weather


# ─────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/scenarios", tags=["Scenarios"])


# ─────────────────────────────────────────────────────────────
# Request Models
# ─────────────────────────────────────────────────────────────
# These define what the frontend sends in the request body.
# Pydantic validates everything before the engine sees it.

class RunSingleRequest(BaseModel):
    """Request to run one site × scenario combination.

    The frontend sends the site_id (to load from storage) and a
    Scenario object. If include_hourly=True and the site has cached
    weather data, the full 8,760-hour simulation runs.
    """
    site_id: str = Field(description="UUID of the saved site")
    scenario: Scenario = Field(description="Scenario configuration")
    include_hourly: bool = Field(
        default=True,
        description=(
            "Run the 8,760-hour PUE simulation if weather data is available. "
            "When False, uses static PUE from cooling profile."
        ),
    )


class BatchRequest(BaseModel):
    """Request to run multiple site × scenario combinations.

    This is the main workhorse for the Scenario Configuration page.
    The user selects sites, load types, cooling types, and redundancy
    levels. The backend generates all combinations and runs them.

    The frontend sends lists of selected options, and the backend
    computes the Cartesian product: every site × every load type ×
    every cooling type × every redundancy level × every density.
    """
    site_ids: list[str] = Field(
        description="UUIDs of sites to evaluate"
    )
    load_types: list[LoadType] = Field(
        description="Workload types to include"
    )
    cooling_types: list[CoolingType] = Field(
        description="Cooling system types to include"
    )
    redundancy_levels: list[RedundancyLevel] = Field(
        default=[RedundancyLevel.TWO_N],
        description="Power redundancy levels to evaluate"
    )
    density_scenarios: list[DensityScenario] = Field(
        default=[DensityScenario.TYPICAL],
        description="Rack density scenarios to evaluate"
    )
    assumption_override_preset_key: Optional[str] = Field(
        default=None,
        description=(
            "Optional scenario-local preset key applied on top of the saved "
            "Settings-backed override catalog for this batch only."
        ),
    )
    include_hourly: bool = Field(
        default=True,
        description="Run 8,760-hour simulation where weather is available"
    )
    skip_incompatible: bool = Field(
        default=True,
        description=(
            "Skip combinations where cooling type is incompatible "
            "with load type (instead of returning RED status)"
        ),
    )


class ScoreRequest(BaseModel):
    """Request to score and rank a set of scenario results.

    The frontend sends results from a batch run. The backend computes
    composite scores and returns them sorted (highest first).

    The max_it_load_mw is needed for IT capacity normalization —
    each scenario's IT load is scored relative to the maximum
    across all scenarios being compared.
    """
    results: list[ScenarioResult] = Field(
        description="Scenario results to score"
    )
    weights: Optional[dict[str, float]] = Field(
        default=None,
        description=(
            "Custom scoring weights. If None, uses defaults: "
            "pue=0.30, it_capacity=0.30, space_utilization=0.15, "
            "rag_status=0.15, infrastructure_fit=0.10"
        ),
    )


class LoadMixRequest(BaseModel):
    """Request for load mix optimization (Architecture Agreement Section 3.12).

    Given total IT capacity and allowed workload types, find the
    optimal allocation across types.
    """
    total_it_mw: float = Field(gt=0, description="Total IT capacity to allocate (MW)")
    allowed_load_types: list[LoadType] = Field(
        min_length=2,
        description="Workload types to include (need at least 2)"
    )
    cooling_type: CoolingType = Field(description="Cooling system for compatibility checks")
    density_scenario: DensityScenario = Field(
        default=DensityScenario.TYPICAL,
        description="Rack density scenario"
    )
    step_pct: int = Field(default=10, ge=5, le=50, description="Step size in %")
    min_racks: int = Field(default=10, ge=1, description="Minimum racks per type")
    top_n: int = Field(default=5, ge=1, le=20, description="Number of top results")
    assumption_override_preset_key: str | None = Field(
        default=None,
        description="Optional assumption override preset key for PUE lookup",
    )


class TornadoRequest(BaseModel):
    """Request for tornado chart sensitivity analysis (Section 3.11).

    All parameters are the baseline values. The engine varies each
    one by ±variation_pct while holding others constant.
    """
    # Baseline values
    pue: float = Field(gt=1.0, description="Baseline PUE")
    eta_chain: float = Field(gt=0, le=1.0, description="Baseline power chain efficiency")
    rack_density_kw: float = Field(gt=0, description="Baseline rack density (kW)")
    whitespace_ratio: float = Field(gt=0, le=1.0, description="Baseline whitespace ratio")
    site_coverage_ratio: float = Field(gt=0, le=1.0, description="Baseline site coverage")
    available_power_mw: float = Field(ge=0, description="Baseline available power (MW)")

    # Fixed geometry
    land_area_m2: float = Field(gt=0, description="Total land area (m²)")
    num_floors: int = Field(default=1, ge=1, description="Number of active floors")
    rack_footprint_m2: float = Field(default=3.0, gt=0, description="Floor area per rack (m²)")
    whitespace_adjustment: float = Field(
        default=1.0, gt=0, le=1.0,
        description="Cooling-type whitespace adjustment factor"
    )
    procurement_factor: float = Field(default=2.0, ge=1.0, description="Procurement factor")

    # Options
    variation_pct: float = Field(default=10.0, gt=0, le=50.0, description="±% variation")
    output_metric: str = Field(
        default="it_load",
        description="Output to measure: 'it_load', 'facility_power', or 'procurement_power'"
    )
    power_constrained: bool = Field(
        default=True,
        description="True = power mode (STMG known), False = area mode"
    )


class BreakEvenRequest(BaseModel):
    """Request for break-even analysis (Section 3.11).

    "What value of parameter X achieves target Y MW of IT load?"
    """
    target_it_load_mw: float = Field(gt=0, description="Target IT load in MW")
    parameter: str = Field(
        description=(
            "Parameter to solve for. Must be one of: "
            "'pue', 'eta_chain', 'rack_density_kw', "
            "'whitespace_ratio', 'site_coverage_ratio', 'available_power_mw'"
        )
    )

    # Current baseline values
    pue: float = Field(gt=1.0, description="Current PUE")
    eta_chain: float = Field(gt=0, le=1.0, description="Current chain efficiency")
    rack_density_kw: float = Field(gt=0, description="Current rack density (kW)")
    whitespace_ratio: float = Field(gt=0, le=1.0, description="Current whitespace ratio")
    site_coverage_ratio: float = Field(gt=0, le=1.0, description="Current site coverage")
    available_power_mw: float = Field(ge=0, description="Current available power (MW)")

    # Fixed geometry
    land_area_m2: float = Field(gt=0, description="Total land area (m²)")
    num_floors: int = Field(default=1, ge=1, description="Number of floors")
    rack_footprint_m2: float = Field(default=3.0, gt=0, description="Area per rack (m²)")
    whitespace_adjustment: float = Field(default=1.0, gt=0, le=1.0)
    power_constrained: bool = Field(default=True)


class BackupPowerRequest(BaseModel):
    """Request for backup power technology comparison (Section 3.8)."""
    procurement_power_mw: float = Field(
        gt=0, description="Grid capacity in MW (sizing basis)"
    )
    annual_runtime_hours: Optional[float] = Field(
        default=None, ge=0,
        description="Hours per year. None = use per-technology defaults."
    )


class FootprintRequest(BaseModel):
    """Request for infrastructure footprint analysis (Section 3.13)."""
    facility_power_mw: float = Field(gt=0, description="Total facility power (MW)")
    procurement_power_mw: float = Field(gt=0, description="Grid capacity (MW)")
    buildable_footprint_m2: float = Field(gt=0, description="Building footprint (m²)")
    gray_space_m2: float = Field(gt=0, description="Available gray space (m²)")
    roof_usable: bool = Field(default=True, description="Whether roof can host cooling equipment")
    backup_power_type: BackupPowerType = Field(
        default=BackupPowerType.DIESEL_GENSET,
        description="Backup power technology"
    )
    cooling_m2_per_kw_override: Optional[float] = Field(
        default=None, gt=0,
        description="Override for cooling footprint factor (m²/kW)"
    )


class GuidedRunRequest(BaseModel):
    """Request for guided mode — runs all 6 load types with preset params.

    The user only selects site(s). Everything else is auto-configured
    from the guided preset table (smart_preset.py).
    """
    site_ids: list[str] = Field(
        description="UUIDs of sites to evaluate"
    )


class PUEBreakdownRequest(BaseModel):
    """Request for annual PUE overhead decomposition."""
    site_id: str = Field(description="UUID of the saved site")
    scenario: Scenario = Field(description="Scenario configuration")


class HourlyProfilesRequest(BaseModel):
    """Request for daily profiles derived from the representative hourly year."""
    site_id: str = Field(description="UUID of the saved site")
    scenario: Scenario = Field(description="Scenario configuration")


class FirmCapacityAdvisoryRequest(BaseModel):
    """Request for auto-computed firm capacity advisory.

    No user input for BESS/fuel cell/backup sizes required.
    The backend uses preset engineering assumptions to auto-suggest
    mitigation strategies and their costs.
    """
    site_id: str = Field(description="UUID of the saved site")
    scenario: Scenario = Field(description="Scenario configuration")


# ─────────────────────────────────────────────────────────────
# Helper: Run one scenario (used by both single and batch)
# ─────────────────────────────────────────────────────────────

def _run_single_scenario(
    site_id: str,
    site: Site,
    scenario: Scenario,
    include_hourly: bool,
) -> ScenarioResult:
    """Execute one site × scenario combination.

    Steps:
        1. Check cooling/load compatibility
        2. Run space + power (engine.power.solve)
        3. If include_hourly and weather is cached, run 8,760-hour sim
        4. Assemble ScenarioResult

    This is the core function — everything else calls this.
    """

    # ── Step 1: Compatibility check ──
    validate_assumption_override_preset_key(scenario.assumption_override_preset_key)

    compatibility_status, _ = evaluate_compatibility(
        scenario.load_type.value,
        scenario.cooling_type.value,
        density_scenario=scenario.density_scenario.value,
    )
    compatible = compatibility_status != "incompatible"

    # ── Step 2: Static space + power calculation ──
    space, power = solve(site, scenario)

    # ── Step 3: Hourly simulation (if weather available) ──
    annual_pue = None
    pue_source = "static"
    overtemperature_hours = None
    it_worst = it_p99 = it_p90 = it_mean = it_best = None
    hourly_simulated = False

    if include_hourly and compatible and power.it_load_mw > 0:
        weather = get_weather(site_id)
        if weather is not None:
            temperatures = weather["temperatures"]
            humidities = weather.get("humidities")
            eta_chain = power.eta_chain

            # Determine simulation mode
            # When binding constraint is AREA, the space-derived IT load
            # is the true cap — run in area-constrained mode even if
            # power is confirmed, otherwise the hourly engine would
            # compute IT values that far exceed the space limit.
            if (
                site.power_confirmed
                and site.available_power_mw > 0
                and power.binding_constraint == "POWER"
            ):
                # Power-constrained: facility power is fixed
                sim = simulate_hourly(
                    temperatures=temperatures,
                    humidities=humidities,
                    cooling_type=scenario.cooling_type.value,
                    eta_chain=eta_chain,
                    facility_power_kw=power.facility_power_mw * 1000,
                    override_preset_key=scenario.assumption_override_preset_key,
                )
            else:
                # Area-constrained: IT load is fixed
                sim = simulate_hourly(
                    temperatures=temperatures,
                    humidities=humidities,
                    cooling_type=scenario.cooling_type.value,
                    eta_chain=eta_chain,
                    it_load_kw=power.it_load_mw * 1000,
                    override_preset_key=scenario.assumption_override_preset_key,
                )

            annual_pue = round(sim.annual_pue, 4)
            overtemperature_hours = sim.overtemperature_hours
            pue_source = "hourly"

            # Cap IT capacity spectrum at the space-derived IT load.
            # In power-constrained mode the hourly sim may report
            # values that exceed what the physical space can host.
            space_cap_mw = power.it_load_mw  # Already min(power, space)
            it_worst = min(round(sim.it_capacity_worst_kw / 1000, 3), space_cap_mw)
            it_p99 = min(round(sim.it_capacity_p99_kw / 1000, 3), space_cap_mw)
            it_p90 = min(round(sim.it_capacity_p90_kw / 1000, 3), space_cap_mw)
            it_mean = min(round(sim.it_capacity_mean_kw / 1000, 3), space_cap_mw)
            it_best = min(round(sim.it_capacity_best_kw / 1000, 3), space_cap_mw)
            hourly_simulated = True
            power = apply_hourly_rag_adjustments(
                power=power,
                scenario=scenario,
                overtemperature_hours=overtemperature_hours,
            )

    # ── Step 4: Assemble result ──
    return ScenarioResult(
        site_id=site_id,
        site_name=site.name,
        scenario=scenario,
        compatible_combination=compatible,
        space=space,
        power=power,
        score=0.0,  # Scored later in the score endpoint
        annual_pue=annual_pue,
        overtemperature_hours=overtemperature_hours,
        pue_source=pue_source,
        it_capacity_worst_mw=it_worst,
        it_capacity_p99_mw=it_p99,
        it_capacity_p90_mw=it_p90,
        it_capacity_mean_mw=it_mean,
        it_capacity_best_mw=it_best,
        assumption_override_preset_label=get_assumption_override_preset_label(
            scenario.assumption_override_preset_key
        ),
        applied_assumption_overrides=get_applied_overrides_for_scenario(
            scenario,
            include_hourly_effects=hourly_simulated,
        ),
    )


def _simulate_for_breakdown(site_id: str, site: Site, scenario: Scenario):
    """Run the exact hourly simulation used for dashboard breakdowns."""
    validate_assumption_override_preset_key(scenario.assumption_override_preset_key)
    compatibility_status, reasons = evaluate_compatibility(
        scenario.load_type.value,
        scenario.cooling_type.value,
        density_scenario=scenario.density_scenario.value,
    )
    if compatibility_status == "incompatible":
        raise ValueError(
            "; ".join(reasons) or "Cooling type is incompatible with the selected load type"
        )

    space, power = solve(site, scenario)
    if power.it_load_mw <= 0:
        raise ValueError("Scenario produced zero IT load; no PUE breakdown available")

    weather = get_weather(site_id)
    if weather is None:
        raise ValueError("Hourly weather is not available for this site")

    temperatures = weather["temperatures"]
    humidities = weather.get("humidities")

    # When binding constraint is AREA, the space-derived IT load is the true
    # cap — run in area-constrained mode even if power is confirmed.
    if (
        site.power_confirmed
        and site.available_power_mw > 0
        and power.binding_constraint == "POWER"
    ):
        return simulate_hourly(
            temperatures=temperatures,
            humidities=humidities,
            cooling_type=scenario.cooling_type.value,
            eta_chain=power.eta_chain,
            facility_power_kw=power.facility_power_mw * 1000,
            override_preset_key=scenario.assumption_override_preset_key,
        )

    return simulate_hourly(
        temperatures=temperatures,
        humidities=humidities,
        cooling_type=scenario.cooling_type.value,
        eta_chain=power.eta_chain,
        it_load_kw=power.it_load_mw * 1000,
        override_preset_key=scenario.assumption_override_preset_key,
    )


def _build_daily_profiles(sim) -> dict:
    """Aggregate hourly simulation arrays into daily IT and PUE profiles."""
    daily_points: list[dict] = []

    for start in range(0, len(sim.hourly_pue), 24):
        day_number = start // 24 + 1
        pue_slice = sim.hourly_pue[start:start + 24]
        it_slice_kw = sim.hourly_it_kw[start:start + 24]

        if not pue_slice or not it_slice_kw:
            continue

        daily_points.append({
            "day": day_number,
            "it_avg_mw": round(sum(it_slice_kw) / len(it_slice_kw) / 1000.0, 3),
            "it_min_mw": round(min(it_slice_kw) / 1000.0, 3),
            "it_max_mw": round(max(it_slice_kw) / 1000.0, 3),
            "pue_avg": round(sum(pue_slice) / len(pue_slice), 4),
            "pue_min": round(min(pue_slice), 4),
            "pue_max": round(max(pue_slice), 4),
        })

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


# ─────────────────────────────────────────────────────────────
# Run Single Scenario
# ─────────────────────────────────────────────────────────────

@router.post("/run")
async def run_single_endpoint(request: RunSingleRequest):
    """Run one site × scenario combination.

    This is the simplest execution path. The frontend sends a site_id
    and a Scenario, and gets back a complete ScenarioResult.

    Use this for:
        - Quick preview while configuring a scenario
        - Testing a specific combination before a full batch run

    If include_hourly=True and the site has cached weather data,
    the 8,760-hour PUE simulation runs automatically. Otherwise,
    the static PUE from the cooling profile is used.
    """
    result = get_site(request.site_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Site '{request.site_id}' not found"
        )
    _, site = result

    scenario_result = _run_single_scenario(
        site_id=request.site_id,
        site=site,
        scenario=request.scenario,
        include_hourly=request.include_hourly,
    )
    record_assumption_override_preset_run(
        preset_key=request.scenario.assumption_override_preset_key,
        site_count=1,
        scenario_count=1,
        applied_overrides=scenario_result.applied_assumption_overrides,
    )

    return scenario_result.model_dump(mode="json")


# ─────────────────────────────────────────────────────────────
# Guided Mode
# ─────────────────────────────────────────────────────────────

@router.get("/guided-presets")
async def guided_presets_endpoint():
    """Return the fixed guided preset table.

    Shows which cooling, density, and redundancy will be used for
    each load type in Guided Mode. This is a read-only display
    endpoint for the frontend to show the preset summary.
    """
    return {"presets": get_guided_presets()}


@router.post("/guided-run")
async def guided_run_endpoint(request: GuidedRunRequest):
    """Run all 6 load types with preset parameters for selected sites.

    This is the Guided Mode workhorse. The user only selects sites.
    The backend runs all 6 load types × 1 preset cooling/density/redundancy
    per load type, using full 8,760-hour hourly simulation.

    Results are returned scored and ranked by composite score, with
    the best-fit load types highlighted per site.
    """
    # ── Load all sites ──
    sites: dict[str, Site] = {}
    for site_id in request.site_ids:
        result = get_site(site_id)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Site '{site_id}' not found"
            )
        _, site = result
        sites[site_id] = site

    # ── Run all preset combinations ──
    results: list[dict] = []
    guided_scenarios = build_guided_scenarios()

    for site_id, site in sites.items():
        for preset_params in guided_scenarios:
            scenario = Scenario(
                load_type=preset_params["load_type"],
                cooling_type=preset_params["cooling_type"],
                redundancy=preset_params["redundancy"],
                density_scenario=preset_params["density_scenario"],
            )

            scenario_result = _run_single_scenario(
                site_id=site_id,
                site=site,
                scenario=scenario,
                include_hourly=True,  # Always use hourly for guided mode
            )
            results.append(scenario_result.model_dump(mode="json"))

    # ── Score results ──
    scored_results = []
    if results:
        max_it = max(
            (r.get("it_capacity_p99_mw") or r["power"]["it_load_mw"])
            for r in results
        )
        if max_it <= 0:
            max_it = 1.0

        for r in results:
            ground_util = 0.0
            roof_util = 0.0

            # Use committed IT capacity (hourly p99 or static) to compute
            # actual power needed — not the grid availability envelope.
            pue_used = r.get("annual_pue") or r["power"]["pue_used"]
            it_mw = r.get("it_capacity_p99_mw") or r["power"]["it_load_mw"]
            eta = r["power"].get("eta_chain", 1.0)
            pf = r["power"].get("procurement_factor", 1.0)
            actual_facility_mw = it_mw * pue_used / eta
            actual_procurement_mw = actual_facility_mw * pf

            try:
                fp = compute_footprint(
                    facility_power_mw=actual_facility_mw,
                    procurement_power_mw=actual_procurement_mw,
                    buildable_footprint_m2=r["space"]["buildable_footprint_m2"],
                    gray_space_m2=r["space"].get("gray_space_m2", r["space"]["support_area_m2"]),
                    roof_usable=getattr(site, "roof_usable", True),
                )
                ground_util = fp.ground_utilization_ratio
                roof_util = fp.roof_utilization_ratio
            except (ValueError, KeyError, ZeroDivisionError):
                pass

            breakdown = score_scenario(
                pue=pue_used,
                it_load_mw=it_mw,
                max_it_load_mw=max_it,
                racks_deployed=r["power"]["racks_deployed"],
                effective_racks=r["space"]["effective_racks"],
                rag_status=RAGStatus(r["power"]["rag_status"]),
                ground_utilization_ratio=ground_util,
                roof_utilization_ratio=roof_util,
                gray_space_ratio=r["space"].get("gray_space_ratio", 0.60),
            )

            r["score"] = round(breakdown.composite_score, 2)
            r["score_breakdown"] = breakdown.model_dump(mode="json")

            # Override RAG when infrastructure doesn't fit
            if not breakdown.equipment_fits:
                r["power"]["rag_status"] = "RED"
                if "Equipment does not fit" not in " ".join(r["power"].get("rag_reasons", [])):
                    r["power"].setdefault("rag_reasons", []).append(
                        f"Equipment does not fit in gray space "
                        f"(utilization {ground_util:.0%}). Scenario not feasible."
                    )

            scored_results.append(r)

        scored_results.sort(key=lambda x: x.get("score", 0), reverse=True)

    return {
        "total_combinations": len(sites) * len(guided_scenarios),
        "skipped_incompatible": 0,
        "computed": len(results),
        "results": scored_results,
        "presets": get_guided_presets(),
    }


# ─────────────────────────────────────────────────────────────
# Batch Run
# ─────────────────────────────────────────────────────────────

@router.post("/batch")
async def batch_run_endpoint(request: BatchRequest):
    """Run all combinations of sites × scenarios.

    This is the workhorse endpoint. The Scenario Configuration page
    (Page 3) sends the user's selections, and this endpoint computes
    the Cartesian product of all combinations.

    Example: 2 sites × 3 load types × 4 cooling types × 1 redundancy
    = 24 scenarios computed in one call.

    If skip_incompatible=True (default), combinations where the cooling
    type doesn't support the load type are silently skipped instead of
    being returned with RED status.

    Results are returned UN-scored — call POST /api/scenarios/score
    to rank them. This separation lets the frontend apply custom
    weights without re-running the engine.

    Response shape:
        {
            "total_combinations": 24,
            "skipped_incompatible": 3,
            "results": [ ... ScenarioResult objects ... ]
        }
    """
    # ── Load all sites ──
    validate_assumption_override_preset_key(request.assumption_override_preset_key)

    sites: dict[str, Site] = {}
    for site_id in request.site_ids:
        result = get_site(site_id)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Site '{site_id}' not found"
            )
        _, site = result
        sites[site_id] = site

    # ── Generate and run all combinations ──
    results: list[dict] = []
    total_combinations = 0
    skipped = 0
    preset_run_overrides = []

    for site_id, site in sites.items():
        for load_type in request.load_types:
            for cooling_type in request.cooling_types:
                for redundancy in request.redundancy_levels:
                    for density in request.density_scenarios:
                        total_combinations += 1

                        # Skip incompatible combinations
                        if request.skip_incompatible:
                            compatibility_status, _ = evaluate_compatibility(
                                load_type.value,
                                cooling_type.value,
                                density_scenario=density.value,
                            )
                            if compatibility_status == "incompatible":
                                skipped += 1
                                continue

                        scenario = Scenario(
                            load_type=load_type,
                            cooling_type=cooling_type,
                            redundancy=redundancy,
                            density_scenario=density,
                            assumption_override_preset_key=request.assumption_override_preset_key,
                        )

                        scenario_result = _run_single_scenario(
                            site_id=site_id,
                            site=site,
                            scenario=scenario,
                            include_hourly=request.include_hourly,
                        )
                        preset_run_overrides.extend(
                            scenario_result.applied_assumption_overrides
                        )
                        results.append(scenario_result.model_dump(mode="json"))

    record_assumption_override_preset_run(
        preset_key=request.assumption_override_preset_key,
        site_count=len(sites),
        scenario_count=len(results),
        applied_overrides=preset_run_overrides,
    )

    return {
        "total_combinations": total_combinations,
        "skipped_incompatible": skipped,
        "computed": len(results),
        "results": results,
    }


# ─────────────────────────────────────────────────────────────
# Score and Rank
# ─────────────────────────────────────────────────────────────

@router.post("/score")
async def score_endpoint(request: ScoreRequest):
    """Score and rank a set of scenario results.

    Takes the results from a batch run and computes composite scores
    using the 5-component weighted formula from Section 3.12.

    Returns results sorted by score (highest first), each with a
    detailed score breakdown showing per-component contributions.

    The scoring is separated from execution so the frontend can:
        1. Run batch once (expensive)
        2. Re-score with different weights (cheap) without re-running
    """
    if not request.results:
        return {"scored_results": [], "count": 0}

    # Find max IT load for normalization
    max_it = max(
        r.it_capacity_p99_mw if r.it_capacity_p99_mw is not None else r.power.it_load_mw
        for r in request.results
    )
    if max_it <= 0:
        max_it = 1.0  # Avoid division by zero

    # Cache site lookups for roof_usable
    _site_cache: dict[str, bool] = {}

    scored: list[dict] = []
    for r in request.results:
        ground_utilization_ratio = 0.0
        roof_utilization_ratio = 0.0

        # Resolve roof_usable from site config
        if r.site_id not in _site_cache:
            site_data = get_site(r.site_id)
            _site_cache[r.site_id] = (
                getattr(site_data[1], "roof_usable", True)
                if site_data else True
            )
        roof_usable = _site_cache[r.site_id]

        # Use committed IT capacity to compute actual power needed for
        # footprint sizing — not the grid availability envelope.
        pue_for_score = r.annual_pue if r.annual_pue is not None else r.power.pue_used
        it_for_score = (
            r.it_capacity_p99_mw
            if r.it_capacity_p99_mw is not None
            else r.power.it_load_mw
        )
        actual_facility_mw = it_for_score * pue_for_score / r.power.eta_chain
        actual_procurement_mw = actual_facility_mw * r.power.procurement_factor

        try:
            footprint = compute_footprint(
                facility_power_mw=actual_facility_mw,
                procurement_power_mw=actual_procurement_mw,
                buildable_footprint_m2=r.space.buildable_footprint_m2,
                gray_space_m2=r.space.gray_space_m2,
                roof_usable=roof_usable,
                backup_power_type=r.scenario.backup_power,
            )
            ground_utilization_ratio = footprint.ground_utilization_ratio
            roof_utilization_ratio = footprint.roof_utilization_ratio
        except ValueError:
            # If footprint sizing fails, keep the historical score fallback.
            pass

        # Compute per-component score
        breakdown = score_scenario(
            pue=pue_for_score,
            it_load_mw=it_for_score,
            max_it_load_mw=max_it,
            racks_deployed=r.power.racks_deployed,
            effective_racks=r.space.effective_racks,
            rag_status=r.power.rag_status,
            ground_utilization_ratio=ground_utilization_ratio,
            roof_utilization_ratio=roof_utilization_ratio,
            gray_space_ratio=r.space.gray_space_ratio,
            weights=request.weights,
        )

        # Attach score to result
        result_dict = r.model_dump(mode="json")
        result_dict["score"] = round(breakdown.composite_score, 2)
        result_dict["score_breakdown"] = breakdown.model_dump(mode="json")

        # Override RAG when infrastructure doesn't fit
        if not breakdown.equipment_fits:
            result_dict["power"]["rag_status"] = "RED"
            existing_reasons = result_dict["power"].get("rag_reasons", [])
            fit_reason = (
                f"Equipment does not fit in gray space "
                f"(utilization {ground_utilization_ratio:.0%}). Scenario not feasible."
            )
            if fit_reason not in existing_reasons:
                existing_reasons.append(fit_reason)
                result_dict["power"]["rag_reasons"] = existing_reasons

        scored.append(result_dict)

    # Sort by score descending (best first)
    scored.sort(key=lambda x: x["score"], reverse=True)

    return {
        "scored_results": scored,
        "count": len(scored),
    }


@router.post("/expansion-advisory")
async def expansion_advisory_endpoint(request: RunSingleRequest):
    """Compute advisory-only future build-out potential for one site/scenario."""
    result = get_site(request.site_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Site '{request.site_id}' not found"
        )
    _, site = result

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

    scenario_result = _run_single_scenario(
        site_id=request.site_id,
        site=site,
        scenario=request.scenario,
        include_hourly=request.include_hourly,
    )
    advisory = compute_expansion_advisory(
        site=site,
        scenario=request.scenario,
        space=scenario_result.space,
        power=scenario_result.power,
        annual_pue=scenario_result.annual_pue,
        pue_source=scenario_result.pue_source,
    )
    if compatibility_status == "conditional":
        advisory.notes = compatibility_reasons + advisory.notes

    return {
        "site_id": request.site_id,
        "site_name": site.name,
        "scenario": request.scenario.model_dump(mode="json"),
        "baseline_result": scenario_result.model_dump(mode="json"),
        "expansion_advisory": advisory.model_dump(mode="json"),
    }


# ─────────────────────────────────────────────────────────────
# Load Mix Optimizer
# ─────────────────────────────────────────────────────────────

@router.post("/load-mix")
async def load_mix_endpoint(request: LoadMixRequest):
    """Find optimal workload allocation across load types.

    Implements Section 3.12 of the Architecture Agreement. Given X MW
    of total IT and a set of allowed workload types, generates all
    combinations in step_pct increments and ranks them.

    Example: "How should I split 20 MW between AI/GPU, HPC, and
    Hyperscale workloads using DLC cooling?"

    Returns top N candidates with rack counts, compatibility flags,
    blended PUE, and trade-off notes.
    """
    try:
        result = optimize_load_mix(
            total_it_mw=request.total_it_mw,
            allowed_load_types=request.allowed_load_types,
            cooling_type=request.cooling_type,
            density_scenario=request.density_scenario,
            step_pct=request.step_pct,
            min_racks=request.min_racks,
            top_n=request.top_n,
            assumption_override_preset_key=request.assumption_override_preset_key,
        )
        return result.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────
# Tornado Chart (Sensitivity)
# ─────────────────────────────────────────────────────────────

@router.post("/tornado")
async def tornado_endpoint(request: TornadoRequest):
    """Compute tornado chart data for sensitivity analysis.

    Implements Section 3.11 — one-at-a-time (OAT) parameter variation.
    For each of the 6 sensitivity parameters, varies it by ±variation_pct
    while holding all others at baseline.

    Returns bars sorted by spread (widest = most influential).
    The frontend renders this as a horizontal tornado chart.
    """
    try:
        result = compute_tornado(
            pue=request.pue,
            eta_chain=request.eta_chain,
            rack_density_kw=request.rack_density_kw,
            whitespace_ratio=request.whitespace_ratio,
            site_coverage_ratio=request.site_coverage_ratio,
            available_power_mw=request.available_power_mw,
            land_area_m2=request.land_area_m2,
            num_floors=request.num_floors,
            rack_footprint_m2=request.rack_footprint_m2,
            whitespace_adjustment=request.whitespace_adjustment,
            procurement_factor=request.procurement_factor,
            variation_pct=request.variation_pct,
            output_metric=request.output_metric,
            power_constrained=request.power_constrained,
        )
        return result.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────
# Break-Even Solver
# ─────────────────────────────────────────────────────────────

@router.post("/break-even")
async def break_even_endpoint(request: BreakEvenRequest):
    """Find the parameter value that achieves a target IT load.

    Implements Section 3.11 — algebraic break-even solver.
    "What PUE do I need to reach 15 MW of IT load?"
    "How much power do I need for 25 MW of IT?"

    Uses direct algebra on the power chain formulas (no iteration).
    """
    try:
        result = compute_break_even(
            target_it_load_mw=request.target_it_load_mw,
            parameter=request.parameter,
            pue=request.pue,
            eta_chain=request.eta_chain,
            rack_density_kw=request.rack_density_kw,
            whitespace_ratio=request.whitespace_ratio,
            site_coverage_ratio=request.site_coverage_ratio,
            available_power_mw=request.available_power_mw,
            land_area_m2=request.land_area_m2,
            num_floors=request.num_floors,
            rack_footprint_m2=request.rack_footprint_m2,
            whitespace_adjustment=request.whitespace_adjustment,
            power_constrained=request.power_constrained,
        )
        return result.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────
# Backup Power Comparison
# ─────────────────────────────────────────────────────────────

@router.post("/backup-power")
async def backup_power_endpoint(request: BackupPowerRequest):
    """Compare all 5 backup power technologies side by side.

    Implements Section 3.8 — diesel, natural gas, SOFC, PEM H₂,
    and flywheel. All sized to the same procurement power for
    fair comparison.

    Returns sizing, fuel consumption, CO₂ emissions, footprint,
    and rankings (lowest CO₂, smallest footprint, fastest ramp).
    """
    try:
        comparison = compare_technologies(
            procurement_power_mw=request.procurement_power_mw,
            annual_runtime_hours=request.annual_runtime_hours,
        )
        return comparison.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────
# Infrastructure Footprint
# ─────────────────────────────────────────────────────────────

@router.post("/footprint")
async def footprint_endpoint(request: FootprintRequest):
    """Compute infrastructure footprint and site fit analysis.

    Implements Section 3.13 — calculates the physical area needed
    for cooling equipment, backup power, transformers, and substation.
    Checks whether everything fits on the site.

    Returns per-element breakdown, ground/roof utilization ratios,
    and fit status (True/False for ground, roof, and overall).
    """
    try:
        result = compute_footprint(
            facility_power_mw=request.facility_power_mw,
            procurement_power_mw=request.procurement_power_mw,
            buildable_footprint_m2=request.buildable_footprint_m2,
            gray_space_m2=request.gray_space_m2,
            roof_usable=request.roof_usable,
            backup_power_type=request.backup_power_type,
            cooling_m2_per_kw_override=request.cooling_m2_per_kw_override,
        )
        return result.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pue-breakdown")
async def pue_breakdown_endpoint(request: PUEBreakdownRequest):
    """Compute annual overhead decomposition from the hourly PUE engine."""
    result = get_site(request.site_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Site '{request.site_id}' not found"
        )
    _, site = result

    try:
        sim = _simulate_for_breakdown(
            site_id=request.site_id,
            site=site,
            scenario=request.scenario,
        )
        components = [
            {
                "key": "electrical_losses",
                "label": "Electrical Losses",
                "energy_kwh": round(sim.total_electrical_losses_kwh, 1),
            },
            {
                "key": "fan_pump",
                "label": "Fans / Pumps",
                "energy_kwh": round(sim.total_fan_pump_kwh, 1),
            },
            {
                "key": "cooling",
                "label": "Cooling Compressor / Heat Rejection",
                "energy_kwh": round(sim.total_cooling_kwh, 1),
            },
            {
                "key": "economizer",
                "label": "Economizer Overhead",
                "energy_kwh": round(sim.total_economizer_kwh, 1),
            },
            {
                "key": "misc",
                "label": "Miscellaneous Fixed Loads",
                "energy_kwh": round(sim.total_misc_kwh, 1),
            },
        ]
        total_overhead = sim.total_overhead_kwh
        for component in components:
            component["share_of_overhead"] = round(
                component["energy_kwh"] / total_overhead, 4
            ) if total_overhead > 0 else 0.0

        return {
            "annual_pue": round(sim.annual_pue, 4),
            "total_facility_kwh": round(sim.total_facility_kwh, 1),
            "total_it_kwh": round(sim.total_it_kwh, 1),
            "total_overhead_kwh": round(total_overhead, 1),
            "components": components,
            "cooling_mode_hours": {
                "mech": sim.mech_hours,
                "econ_part": sim.econ_part_hours,
                "econ_full": sim.econ_full_hours,
                "overtemperature": sim.overtemperature_hours,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hourly-profiles")
async def hourly_profiles_endpoint(request: HourlyProfilesRequest):
    """Return daily IT-load and PUE profiles from the representative hourly year."""
    result = get_site(request.site_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Site '{request.site_id}' not found"
        )
    _, site = result

    try:
        sim = _simulate_for_breakdown(
            site_id=request.site_id,
            site=site,
            scenario=request.scenario,
        )
        payload = _build_daily_profiles(sim)
        payload["site_id"] = request.site_id
        payload["site_name"] = site.name
        payload["scenario"] = request.scenario.model_dump(mode="json")
        return payload
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────
# Combination Count (Preview)
# ─────────────────────────────────────────────────────────────

@router.post("/combination-count")
async def combination_count_endpoint(request: BatchRequest):
    """Preview the number of combinations without running them.

    The Scenario Configuration page (Page 3) shows the combination
    count as the user selects options: "3 sites × 2 loads × 4 cooling
    × 1 redundancy = 24 scenarios"

    This is a lightweight endpoint — no engine calls, just math.
    """
    total = (
        len(request.site_ids)
        * len(request.load_types)
        * len(request.cooling_types)
        * len(request.redundancy_levels)
        * len(request.density_scenarios)
    )

    # Count incompatible combinations
    incompatible = 0
    if request.skip_incompatible:
        for lt in request.load_types:
            for ct in request.cooling_types:
                for density in request.density_scenarios:
                    compatibility_status, _ = evaluate_compatibility(
                        lt.value,
                        ct.value,
                        density_scenario=density.value,
                    )
                    if compatibility_status == "incompatible":
                        incompatible += (
                            len(request.site_ids)
                            * len(request.redundancy_levels)
                        )

    return {
        "total_combinations": total,
        "incompatible": incompatible,
        "to_compute": total - incompatible,
    }


# ─────────────────────────────────────────────────────────────
# Firm Capacity Advisory (Preset Methodology)
# ─────────────────────────────────────────────────────────────

@router.post("/firm-capacity-advisory")
async def firm_capacity_advisory_endpoint(request: FirmCapacityAdvisoryRequest):
    """Auto-compute firm capacity advisory with preset engineering assumptions.

    Unlike POST /api/green/firm-capacity which requires manual user input
    for BESS/fuel cell/backup sizes, this endpoint uses built-in engineering
    methodology to automatically suggest mitigation strategies.

    Requires:
        - Confirmed site power
        - Cached weather data (for hourly PUE simulation)

    Returns:
        - Firm capacity (P99 from hourly sim)
        - Capacity gap (mean - P99)
        - Recommended mitigation strategies with quantities and costs
        - How much additional IT capacity each strategy unlocks
    """
    from dataclasses import asdict

    result = get_site(request.site_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Site '{request.site_id}' not found"
        )
    _, site = result

    if not site.power_confirmed or site.available_power_mw <= 0:
        raise HTTPException(
            status_code=400,
            detail="Firm capacity advisory requires confirmed available power"
        )

    weather = get_weather(request.site_id)
    if weather is None:
        raise HTTPException(
            status_code=400,
            detail="Hourly weather data is required for firm capacity advisory. "
                   "Fetch or upload weather on the Climate & Weather page first."
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

    space, power = solve(site, request.scenario)
    temperatures = weather["temperatures"]
    humidities = weather.get("humidities")

    try:
        sim = simulate_hourly(
            temperatures=temperatures,
            humidities=humidities,
            cooling_type=request.scenario.cooling_type.value,
            eta_chain=power.eta_chain,
            facility_power_kw=power.facility_power_mw * 1000,
            override_preset_key=request.scenario.assumption_override_preset_key,
        )

        advisory = compute_firm_capacity_advisory(
            hourly_it_kw=sim.hourly_it_kw,
            facility_power_kw=power.facility_power_mw * 1000,
            annual_pue=sim.annual_pue,
            cooling_type=request.scenario.cooling_type.value,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Sample hourly IT capacity for frontend chart (every 12h → ~730 pts)
    step = max(1, len(sim.hourly_it_kw) // 730)
    sampled_it_kw = [round(v, 1) for v in sim.hourly_it_kw[::step]]

    return {
        "firm_capacity_mw": advisory.firm_capacity_mw,
        "firm_capacity_kw": advisory.firm_capacity_kw,
        "mean_capacity_mw": advisory.mean_capacity_mw,
        "mean_capacity_kw": advisory.mean_capacity_kw,
        "worst_capacity_mw": advisory.worst_capacity_mw,
        "worst_capacity_kw": advisory.worst_capacity_kw,
        "best_capacity_mw": advisory.best_capacity_mw,
        "best_capacity_kw": advisory.best_capacity_kw,
        "capacity_gap_mw": advisory.capacity_gap_mw,
        "capacity_gap_kw": advisory.capacity_gap_kw,
        "peak_deficit_mw": advisory.peak_deficit_mw,
        "peak_deficit_kw": advisory.peak_deficit_kw,
        "deficit_hours": advisory.deficit_hours,
        "deficit_energy_kwh": advisory.deficit_energy_kwh,
        "annual_pue": round(sim.annual_pue, 4),
        "facility_power_mw": round(power.facility_power_mw, 3),
        "hourly_it_kw_sampled": sampled_it_kw,
        "strategies": [
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
        ],
    }
