"""
DC Feasibility Tool v4 — Data Models
=====================================
Pydantic models for all data structures in the system.

Every site, scenario, and result flows through these models.
Pydantic validates all inputs automatically — if someone enters
a negative land area or a PUE below 1.0, it raises an error
before the data ever reaches the calculation engine.

Reference: Architecture Agreement v2.0, Sections 3.1, 3.5, 3.6, 3.14–3.17
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────
# Enumerations — constrained choices for dropdowns and config
# ─────────────────────────────────────────────────────────────

class SiteType(str, Enum):
    """Type of site — affects timeline expectations, not calculations."""
    GREENFIELD = "Greenfield"
    BROWNFIELD = "Brownfield"
    RETROFIT = "Retrofit"
    BUILT_TO_SUIT = "Built-to-Suit"


class BuildableAreaMode(str, Enum):
    """How buildable area is determined.
    
    RATIO: buildable = land_area × site_coverage_ratio
           Use when you only know the land boundary.
    
    ABSOLUTE: buildable = exact m² from planning permission
              Use when the permit specifies the allowed footprint.
    """
    RATIO = "ratio"
    ABSOLUTE = "absolute"


class PowerInputMode(str, Enum):
    """How to interpret the STMG power value entered by the user.
    
    This resolves the procurement power ambiguity described in
    Architecture Agreement Section 3.5.
    
    OPERATIONAL: The entered MW is what the facility draws from the grid
                 during normal operation. Redundancy is internal —
                 equipment is doubled but the grid delivers this amount.
                 Example: 100 MW entered → facility_power = 100 MW
    
    GRID_RESERVATION: The entered MW is the total grid capacity reserved,
                      which already includes redundancy.
                      Example: 100 MW entered with 2N → facility_power = 50 MW
    """
    OPERATIONAL = "operational"
    GRID_RESERVATION = "grid_reservation"


class LoadType(str, Enum):
    """Workload types with verified rack density ranges.
    
    Source: Architecture Agreement Section 3.16
    Densities verified March 2026 against NVIDIA, HPE, TrendForce data.
    """
    COLOCATION_STANDARD = "Colocation (Standard)"
    COLOCATION_HIGH_DENSITY = "Colocation (High Density)"
    HPC = "HPC"
    AI_GPU = "AI / GPU Clusters"
    HYPERSCALE = "Hyperscale / Cloud"
    EDGE_TELCO = "Edge / Telco"


class CoolingType(str, Enum):
    """Cooling system types — each maps to a topology and COP model.
    
    Source: Architecture Agreement Section 3.2 (COP defaults)
    and Section 3.15 (whitespace adjustment factors).
    """
    CRAC_DX = "Air-Cooled CRAC (DX)"
    AHU_NO_ECON = "Air-Cooled AHU (No Economizer)"
    AIR_CHILLER_ECON = "Air-Cooled Chiller + Economizer"
    WATER_CHILLER_ECON = "Water-Cooled Chiller + Economizer"
    RDHX = "Rear Door Heat Exchanger (RDHx)"
    DLC = "Direct Liquid Cooling (DLC / Cold Plate)"
    IMMERSION = "Immersion Cooling (Single-Phase)"
    DRY_COOLER = "Free Cooling — Dry Cooler (Chiller-less)"


class RedundancyLevel(str, Enum):
    """Power redundancy configuration.
    
    Redundancy has exactly two effects (Architecture Agreement Section 3.6):
    1. eta_chain_derate — small UPS partial-load efficiency penalty
    2. procurement_factor — grid capacity sizing multiplier
    
    Redundancy does NOT multiply PUE. This was a v1 bug, fixed in v2.
    
    Source: Uptime Institute Tier Standard: Topology (2018)
    """
    N = "N"
    N_PLUS_1 = "N+1"
    TWO_N = "2N"
    TWO_N_PLUS_1 = "2N+1"


class DensityScenario(str, Enum):
    """Rack power density scenario — low, typical, or high.
    
    Each load type has three density values. The user selects which
    scenario to use. 'typical' is the default for feasibility.
    """
    LOW = "low"
    TYPICAL = "typical"
    HIGH = "high"


class RAGStatus(str, Enum):
    """4-level feasibility status system.
    
    Source: Architecture Agreement Section 3.17
    
    RED:   Fatal — scenario not viable
    AMBER: Warning — viable but with significant constraints
    GREEN: Good — scenario viable and attractive
    BLUE:  Excellent — highlights best scenarios
    """
    RED = "RED"
    AMBER = "AMBER"
    GREEN = "GREEN"
    BLUE = "BLUE"


class BackupPowerType(str, Enum):
    """Backup/supplemental power technology.
    
    Source: Architecture Agreement Section 3.8
    """
    DIESEL_GENSET = "Diesel Genset"
    NATURAL_GAS_GENSET = "Natural Gas Genset"
    SOFC_FUEL_CELL = "SOFC Fuel Cell"
    PEM_FUEL_CELL = "PEM Fuel Cell (H₂)"
    ROTARY_UPS_FLYWHEEL = "Rotary UPS + Flywheel"


# ─────────────────────────────────────────────────────────────
# Site Model — represents a candidate data center location
# ─────────────────────────────────────────────────────────────

class GridAssetType(str, Enum):
    """External grid asset categories used for screening."""

    LINE = "line"
    SUBSTATION = "substation"


class GridGeometryType(str, Enum):
    """Map geometry categories for nearby public grid assets."""

    POINT = "point"
    LINE = "line"
    POLYGON = "polygon"


class GridConfidence(str, Enum):
    """Confidence/source label for grid-context evidence."""

    MAPPED_PUBLIC = "mapped_public"
    OFFICIAL_AGGREGATE = "official_aggregate"
    USER_CONFIRMED = "user_confirmed"


class GridAnalysisGrade(str, Enum):
    """High-level confidence framing shown to users."""

    SCREENING_GRADE = "screening_grade"


class ImportedGeometry(BaseModel):
    """Uploaded geometry preserved from KML/KMZ for exact map display."""

    geometry_type: str = Field(
        description="Original geometry type from KML: point, line, or polygon"
    )
    coordinates: list[list[float]] = Field(
        description="Geometry vertices as [latitude, longitude] pairs"
    )


class Site(BaseModel):
    """A candidate data center site.
    
    Contains all physical and electrical properties of the location.
    The site geometry (land area, buildable area, floors, whitespace)
    feeds into the space calculation. The power fields feed into the
    power chain calculation.
    """

    # ── Identity ──
    name: str = Field(..., min_length=1, description="Unique site name")
    site_type: SiteType = Field(
        default=SiteType.GREENFIELD,
        description="Development type — affects timeline, not calculations"
    )

    # ── Location ──
    latitude: Optional[float] = Field(
        default=None, ge=-90, le=90,
        description="Site latitude in decimal degrees"
    )
    longitude: Optional[float] = Field(
        default=None, ge=-180, le=180,
        description="Site longitude in decimal degrees"
    )
    imported_geometry: Optional[ImportedGeometry] = Field(
        default=None,
        description="Exact uploaded KML/KMZ geometry for map display"
    )
    country: Optional[str] = Field(default=None, description="Country (display only)")
    city: Optional[str] = Field(default=None, description="City or locality name")

    # ── Land ──
    land_area_m2: float = Field(
        ..., gt=0,
        description="Total land boundary area in m². Must be positive."
    )

    # ── Buildable Area ──
    buildable_area_mode: BuildableAreaMode = Field(
        default=BuildableAreaMode.RATIO,
        description="How to determine buildable footprint"
    )
    site_coverage_ratio: float = Field(
        default=0.50, gt=0, le=1.0,
        description=(
            "Building footprint / land area. Default 0.50 for industrial zones. "
            "Source: Italian 'indice di copertura' for Zone D (PRG/PGT): 0.30–0.60"
        )
    )
    buildable_area_m2: Optional[float] = Field(
        default=None, gt=0,
        description="Explicit buildable area from planning permission (absolute mode)"
    )

    # ── Building ──
    max_building_height_m: Optional[float] = Field(
        default=None, gt=0,
        description="Maximum building height from planning permission. 0 or None = no limit."
    )
    floor_to_floor_height_m: float = Field(
        default=4.5, gt=2.0, le=10.0,
        description=(
            "Floor-to-floor height in meters. Default 4.5m. "
            "Source: ASHRAE TC 9.9 minimum 4.0m; typical DC 4.5–5.5m."
        )
    )
    num_floors: int = Field(
        default=1, ge=1, le=10,
        description="Number of active floors. If max_building_height_m is set, this is derived."
    )
    num_expansion_floors: int = Field(
        default=0, ge=0, le=10,
        description="Floors reserved for future expansion phases"
    )

    # ── Roof ──
    roof_usable: bool = Field(
        default=True,
        description=(
            "Whether the building roof can host cooling equipment (condensers/dry coolers). "
            "If False, cooling equipment is placed inside the building gray space."
        )
    )

    # ── White Space ──
    whitespace_ratio: float = Field(
        default=0.40, gt=0, le=0.80,
        description=(
            "IT hall area / gross building area. Default 0.40. "
            "Source: Uptime Institute Tier III/IV: 40–45%. "
            "DCD Intelligence: 35–45% for European colocation."
        )
    )
    rack_footprint_m2: float = Field(
        default=3.0, gt=1.0, le=6.0,
        description=(
            "Floor area per rack including hot/cold aisle in m². Default 3.0. "
            "Source: ASHRAE TC 9.9 aisle width recommendations. "
            "Standard 42U rack (0.64 m²) + containment aisles = 2.5–3.5 m²."
        )
    )

    # ── Power ──
    available_power_mw: float = Field(
        default=0.0, ge=0,
        description="Available utility power in MW. 0 = not confirmed (area-constrained mode)."
    )
    power_confirmed: bool = Field(
        default=False,
        description="Whether the power availability has been confirmed via STMG or equivalent"
    )
    power_input_mode: PowerInputMode = Field(
        default=PowerInputMode.OPERATIONAL,
        description=(
            "How to interpret the power value. "
            "OPERATIONAL = facility draws this amount. "
            "GRID_RESERVATION = total grid capacity including redundancy. "
            "Source: Architecture Agreement Section 3.5"
        )
    )
    voltage: Optional[str] = Field(
        default=None,
        description="Grid connection voltage: HV (110kV+), MV (10–33kV), LV (400V), TBD"
    )

    # ── Notes ──
    notes: Optional[str] = Field(default=None, description="Free-text notes")

    # ── Validators ──
    @field_validator("buildable_area_m2")
    @classmethod
    def buildable_must_fit_land(cls, v, info):
        """Buildable area cannot exceed total land area."""
        if v is not None and "land_area_m2" in info.data:
            if v > info.data["land_area_m2"]:
                raise ValueError(
                    f"Buildable area ({v} m²) cannot exceed land area "
                    f"({info.data['land_area_m2']} m²)"
                )
        return v


# ─────────────────────────────────────────────────────────────
# Scenario Model — a specific configuration to evaluate
# ─────────────────────────────────────────────────────────────

class Scenario(BaseModel):
    """A scenario to evaluate for a given site.
    
    Combines a load type, cooling type, redundancy level, and density
    scenario. The engine runs this against a site to produce a Result.
    """

    load_type: LoadType = Field(..., description="Workload type")
    cooling_type: CoolingType = Field(..., description="Cooling system type")
    redundancy: RedundancyLevel = Field(
        default=RedundancyLevel.TWO_N,
        description="Power redundancy level"
    )
    density_scenario: DensityScenario = Field(
        default=DensityScenario.TYPICAL,
        description="Rack power density scenario"
    )
    pue_override: Optional[float] = Field(
        default=None, gt=1.0, le=3.0,
        description="Manual PUE override. None = use hourly engine or cooling profile default."
    )
    assumption_override_preset_key: Optional[str] = Field(
        default=None,
        description=(
            "Optional scenario-local preset key applied on top of the saved "
            "Settings-backed override catalog for this run only."
        ),
    )
    backup_power: BackupPowerType = Field(
        default=BackupPowerType.DIESEL_GENSET,
        description="Backup/supplemental power technology"
    )


class AppliedAssumptionOverride(BaseModel):
    """One persisted override that influenced a scenario calculation."""

    key: str = Field(description="Stable assumption override key")
    label: str = Field(description="Human-readable assumption label")
    scope_label: str = Field(description="Which cooling/redundancy scope was affected")
    parameter_label: str = Field(description="The parameter changed within that scope")
    unit: str = Field(description="Display unit for the value")
    baseline_value: float = Field(description="Default engine value before any override")
    previous_effective_value: float | None = Field(
        default=None,
        description=(
            "Effective value before the final applied override layer. This is "
            "primarily populated for scenario-local preset overlays."
        ),
    )
    effective_value: float = Field(description="Override value actually used at runtime")
    source: str = Field(description="User-supplied source or citation for the override")
    justification: str = Field(description="Why the override was applied")
    origin: str = Field(description="Whether the value came from Settings persistence or a scenario-local preset")
    preset_key: str | None = Field(default=None, description="Scenario-local preset key when the origin is preset-based")
    preset_label: str | None = Field(default=None, description="Scenario-local preset label when the origin is preset-based")
    updated_at_utc: str | None = Field(default=None, description="When the override was last saved, if persisted in Settings")


# ─────────────────────────────────────────────────────────────
# Space Result — output of the geometry calculation
# ─────────────────────────────────────────────────────────────

class SpaceResult(BaseModel):
    """Output of the site geometry calculation (space.py).
    
    Pure geometry — no power, no PUE, no cooling. Just how many
    racks physically fit in the building.
    """

    # ── Derived areas ──
    buildable_footprint_m2: float = Field(description="Building ground-floor footprint")
    gross_building_area_m2: float = Field(description="Total building area across active floors")
    it_whitespace_m2: float = Field(description="IT hall area (gross × whitespace_ratio)")
    support_area_m2: float = Field(description="Non-IT area (power rooms, corridors, etc.)")
    gray_space_m2: float = Field(
        description="Gray space area — same as support_area_m2 (power rooms, cooling plant, corridors, offices)"
    )
    gray_space_ratio: float = Field(
        description="Gray space / gross building area (complement of whitespace_ratio)"
    )

    # ── Rack capacity ──
    max_racks_by_space: int = Field(description="Maximum racks that physically fit")
    effective_racks: int = Field(
        description="Racks after cooling whitespace adjustment factor"
    )
    whitespace_adjustment_factor: float = Field(
        description="Cooling-type-specific reduction factor (0.85–1.00)"
    )

    # ── Parameters used ──
    site_coverage_used: float = Field(description="Coverage ratio actually applied")
    whitespace_ratio_used: float = Field(description="Whitespace ratio actually applied")
    rack_footprint_used: float = Field(description="Rack footprint actually applied")
    active_floors: int = Field(description="Number of active floors")
    floor_to_floor_height_used: float = Field(description="Floor height used")

    # ── Expansion ──
    expansion_floors: int = Field(default=0, description="Floors reserved for expansion")
    expansion_whitespace_m2: float = Field(
        default=0.0, description="IT whitespace in expansion floors"
    )
    expansion_racks: int = Field(
        default=0, description="Additional racks available in expansion floors"
    )


# ─────────────────────────────────────────────────────────────
# Power Result — output of the power chain calculation
# ─────────────────────────────────────────────────────────────

class PowerResult(BaseModel):
    """Output of the power chain calculation (power.py).
    
    Computes IT load, facility power, and procurement power.
    Works in both power-constrained and area-constrained modes.
    """

    # ── Core power values ──
    it_load_mw: float = Field(description="Achievable IT load in MW")
    facility_power_mw: float = Field(description="Total facility power in MW (IT × PUE)")
    procurement_power_mw: float = Field(
        description="Grid capacity to request in MW (facility × procurement_factor)"
    )

    # ── Rack deployment ──
    racks_by_power: Optional[int] = Field(
        default=None,
        description="Max racks supportable by power (power-constrained mode only)"
    )
    racks_deployed: int = Field(description="Actual racks deployed (min of power and space)")
    rack_density_kw: float = Field(description="Power per rack in kW")

    # ── Constraint analysis ──
    binding_constraint: str = Field(
        description="'POWER' or 'AREA' — which limits the deployment"
    )
    power_headroom_mw: Optional[float] = Field(
        default=None,
        description="Remaining power capacity in MW (power-constrained only)"
    )

    # ── Power chain parameters used ──
    eta_chain: float = Field(description="Power chain efficiency used")
    pue_used: float = Field(description="PUE value used for this calculation")
    procurement_factor: float = Field(description="Procurement factor for redundancy level")
    power_input_mode: PowerInputMode = Field(
        description="How the input power was interpreted"
    )

    # ── RAG status ──
    rag_status: RAGStatus = Field(description="Feasibility status")
    rag_reasons: list[str] = Field(
        default_factory=list,
        description="List of reasons for the RAG status"
    )


# ─────────────────────────────────────────────────────────────
# Combined Result — full scenario evaluation
# ─────────────────────────────────────────────────────────────

class ScenarioResult(BaseModel):
    """Complete result for one site + scenario combination.
    
    Combines space geometry, power chain, and (when available)
    hourly PUE simulation results. This is what the Results
    Dashboard displays.
    """

    # ── Identity ──
    site_id: str = Field(description="UUID of the saved site")
    site_name: str
    scenario: Scenario
    compatible_combination: bool = Field(
        default=True,
        description="Whether this cooling + load type combination is compatible"
    )

    # ── Sub-results ──
    space: SpaceResult
    power: PowerResult

    # ── Scoring ──
    score: float = Field(
        default=0.0,
        description="Composite ranking score for scenario comparison"
    )

    # ── Hourly engine results (populated when weather data available) ──
    annual_pue: Optional[float] = Field(
        default=None,
        description="Energy-weighted annual PUE from hourly simulation"
    )
    overtemperature_hours: Optional[int] = Field(
        default=None,
        description="Hours in the representative year where the cooling topology cannot hold setpoint"
    )
    pue_source: str = Field(
        default="static",
        description="'static' (from cooling profile) or 'hourly' (from 8760 simulation)"
    )

    # ── IT capacity spectrum (hourly engine only) ──
    it_capacity_worst_mw: Optional[float] = Field(
        default=None, description="Minimum IT capacity across all hours (hottest hour)"
    )
    it_capacity_p99_mw: Optional[float] = Field(
        default=None, description="IT capacity available 99% of the year — committed capacity"
    )
    it_capacity_p90_mw: Optional[float] = Field(
        default=None, description="IT capacity available 90% of the year"
    )
    it_capacity_mean_mw: Optional[float] = Field(
        default=None, description="Annual mean IT capacity"
    )
    it_capacity_best_mw: Optional[float] = Field(
        default=None, description="Maximum IT capacity (coolest hour)"
    )
    assumption_override_preset_label: str | None = Field(
        default=None,
        description="Resolved label for the scenario-local preset applied to this result, if any",
    )
    applied_assumption_overrides: list[AppliedAssumptionOverride] = Field(
        default_factory=list,
        description="Persisted assumption overrides that affected this scenario result",
    )


class GridAsset(BaseModel):
    """One nearby external grid asset normalized for screening and map display."""

    asset_id: str = Field(description="Stable asset identifier from the current source layer")
    asset_type: GridAssetType = Field(description="Nearby asset type: line or substation")
    name: Optional[str] = Field(default=None, description="Mapped asset name when available")
    operator: Optional[str] = Field(default=None, description="Mapped operator or owner label")
    voltage_kv: Optional[float] = Field(
        default=None,
        ge=0,
        description="Mapped nominal voltage in kV when tagged",
    )
    circuits: Optional[int] = Field(
        default=None,
        ge=1,
        description="Mapped circuit count when tagged",
    )
    distance_km: float = Field(
        ge=0,
        description="Approximate site-to-asset distance in kilometers",
    )
    geometry_type: GridGeometryType = Field(description="Geometry used for map overlay rendering")
    coordinates: list[list[float]] = Field(
        default_factory=list,
        description="Geometry coordinates as [latitude, longitude] pairs",
    )
    source: str = Field(description="Source layer label used to derive this asset")
    confidence: GridConfidence = Field(description="Confidence/source classification")


class GridContextSummary(BaseModel):
    """Top-level descriptive metrics for assets within the selected radius."""

    radius_km: float = Field(gt=0, description="Requested search radius in kilometers")
    nearby_line_count: int = Field(ge=0, description="Count of mapped lines within the radius")
    nearby_substation_count: int = Field(
        ge=0,
        description="Count of mapped substations within the radius",
    )
    nearest_line_km: Optional[float] = Field(
        default=None,
        ge=0,
        description="Distance to the nearest mapped line within the radius",
    )
    nearest_substation_km: Optional[float] = Field(
        default=None,
        ge=0,
        description="Distance to the nearest mapped substation within the radius",
    )
    max_voltage_kv: Optional[float] = Field(
        default=None,
        ge=0,
        description="Highest mapped voltage visible within the radius",
    )
    high_voltage_assets_within_radius: int = Field(
        ge=0,
        description="Count of assets at or above the high-voltage screening threshold",
    )


class GridContextScore(BaseModel):
    """Optional heuristic screening score for external power attractiveness."""

    overall_score: float = Field(ge=0, le=100, description="Composite heuristic score")
    voltage_score: float = Field(ge=0, le=100, description="Voltage-visibility contribution")
    distance_score: float = Field(ge=0, le=100, description="Proximity contribution")
    substation_score: float = Field(ge=0, le=100, description="Substation-access contribution")
    evidence_score: float = Field(ge=0, le=100, description="Evidence-layer contribution")
    notes: list[str] = Field(
        default_factory=list,
        description="Plain-language notes explaining the heuristic score",
    )


class GridEvidenceNote(BaseModel):
    """Explicit evidence or disclaimer note attached to a grid-context result."""

    label: str = Field(description="Short label for the evidence or disclaimer")
    detail: str = Field(description="Human-readable explanation")
    source: str = Field(description="Source or provider label")
    confidence: GridConfidence = Field(description="Confidence/source classification")


class GridOfficialEvidence(BaseModel):
    """Manual official-evidence overlay entered from utility or TSO documentation."""

    utility_or_tso_reference: Optional[str] = Field(
        default=None,
        description="Reference for the official utility, TSO, or study document",
    )
    reference_date: Optional[str] = Field(
        default=None,
        description="Date label copied from the official evidence when known",
    )
    confirmed_substation_name: Optional[str] = Field(
        default=None,
        description="Confirmed substation or point-of-connection name from the evidence",
    )
    confirmed_voltage_kv: Optional[float] = Field(
        default=None,
        ge=0,
        description="Confirmed connection voltage in kV when stated in official evidence",
    )
    confirmed_requested_mw: Optional[float] = Field(
        default=None,
        ge=0,
        description="Confirmed requested MW from official evidence when stated",
    )
    confirmed_available_mw: Optional[float] = Field(
        default=None,
        ge=0,
        description="Confirmed available MW from official evidence when stated",
    )
    connection_status: Optional[str] = Field(
        default=None,
        description="Connection status copied from official evidence",
    )
    timeline_status: Optional[str] = Field(
        default=None,
        description="Timeline or milestone wording copied from official evidence",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Free-text notes copied from the official evidence",
    )

    @field_validator(
        "utility_or_tso_reference",
        "reference_date",
        "confirmed_substation_name",
        "connection_status",
        "timeline_status",
        "notes",
        mode="before",
    )
    @classmethod
    def blank_strings_to_none(cls, value):
        """Normalize empty strings from forms into nulls for cleaner persistence."""
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class GridOfficialEvidenceResponse(BaseModel):
    """Response wrapper for one site's saved official-evidence overlay."""

    site_id: str = Field(description="UUID of the site tied to the official-evidence overlay")
    has_evidence: bool = Field(description="Whether any official evidence is saved for this site")
    evidence: Optional[GridOfficialEvidence] = Field(
        default=None,
        description="Saved manual official-evidence fields for this site",
    )


class GridContextRequest(BaseModel):
    """Request payload for site-level nearby grid-asset discovery."""

    site_id: str = Field(description="UUID of the saved site")
    radius_km: float = Field(
        default=5.0,
        gt=0,
        le=50,
        description="Nearby-asset search radius in kilometers",
    )
    force_refresh: bool = Field(
        default=False,
        description="Bypass the cache and rebuild the screening result",
    )
    include_score: bool = Field(
        default=False,
        description="Include the heuristic screening attractiveness score",
    )


class GridContextResult(BaseModel):
    """Screening-grade nearby external power-network context for one saved site."""

    site_id: str = Field(description="UUID of the saved site")
    site_name: str = Field(description="Display name of the selected site")
    latitude: float = Field(ge=-90, le=90, description="Site latitude in decimal degrees")
    longitude: float = Field(ge=-180, le=180, description="Site longitude in decimal degrees")
    analysis_grade: GridAnalysisGrade = Field(
        default=GridAnalysisGrade.SCREENING_GRADE,
        description="High-level product framing for this result",
    )
    summary: GridContextSummary = Field(description="Nearby-asset summary metrics")
    score: Optional[GridContextScore] = Field(
        default=None,
        description="Optional heuristic score for screening attractiveness",
    )
    assets: list[GridAsset] = Field(
        default_factory=list,
        description="Normalized nearby public or user-confirmed grid assets",
    )
    evidence_notes: list[GridEvidenceNote] = Field(
        default_factory=list,
        description="Explicit evidence-layer notes and disclaimers",
    )
    official_evidence: Optional[GridOfficialEvidence] = Field(
        default=None,
        description="Optional manual official-evidence overlay tied to this site",
    )
    official_context_notes: list[str] = Field(
        default_factory=list,
        description="Supporting notes about evidence, aggregate context, or limitations",
    )
    source_layers: list[str] = Field(
        default_factory=list,
        description="Source layers used to build the result",
    )
    confidence: GridConfidence = Field(description="Overall confidence/source classification")
    data_quality_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Data quality confidence score (0.0–1.0) based on region coverage. "
            "Higher values indicate more mapped assets were found, suggesting "
            "better OSM coverage in the area. 0.0 = no data or API failure."
        ),
    )
    generated_at_utc: str = Field(description="UTC timestamp when the result was generated")
