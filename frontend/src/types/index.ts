/**
 * DC Feasibility Tool v4 — TypeScript Type Definitions
 * =====================================================
 * These types mirror the backend Pydantic models exactly.
 * When the backend sends JSON, TypeScript uses these types
 * to give us autocomplete and catch typos at compile time.
 *
 * PHASE 6 ADDITIONS:
 *   - FootprintElement, FootprintResult  (footprint.py)
 *   - BackupPowerSizing, BackupPowerComparison (backup_power.py)
 *   - TornadoBar (full), TornadoResult  (sensitivity.py)
 *   - BreakEvenResult                   (sensitivity.py)
 *   - GreenDispatchResult               (green_energy.py)
 *
 * Reference: backend/engine/models.py, backend/api/routes_*.py
 */

// ─────────────────────────────────────────────────────────────
// Enumerations — String union types
// ─────────────────────────────────────────────────────────────

export type SiteType = "Greenfield" | "Brownfield" | "Retrofit" | "Built-to-Suit";
export type BuildableAreaMode = "ratio" | "absolute";
export type PowerInputMode = "operational" | "grid_reservation";

export type LoadType =
  | "Colocation (Standard)"
  | "Colocation (High Density)"
  | "HPC"
  | "AI / GPU Clusters"
  | "Hyperscale / Cloud"
  | "Edge / Telco";

export type CoolingType =
  | "Air-Cooled CRAC (DX)"
  | "Air-Cooled AHU (No Economizer)"
  | "Air-Cooled Chiller + Economizer"
  | "Water-Cooled Chiller + Economizer"
  | "Rear Door Heat Exchanger (RDHx)"
  | "Direct Liquid Cooling (DLC / Cold Plate)"
  | "Immersion Cooling (Single-Phase)"
  | "Free Cooling — Dry Cooler (Chiller-less)";

export type RedundancyLevel = "N" | "N+1" | "2N" | "2N+1";
export type DensityScenario = "low" | "typical" | "high";
export type RAGStatus = "RED" | "AMBER" | "GREEN" | "BLUE";

export type BackupPowerType =
  | "Diesel Genset"
  | "Natural Gas Genset"
  | "SOFC Fuel Cell"
  | "PEM Fuel Cell (H₂)"
  | "Rotary UPS + Flywheel";


// ─────────────────────────────────────────────────────────────
// Site
// ─────────────────────────────────────────────────────────────

export type GridAssetType = "line" | "substation";
export type GridGeometryType = "point" | "line" | "polygon";
export type GridConfidence = "mapped_public" | "official_aggregate" | "user_confirmed";
export type GridAnalysisGrade = "screening_grade";

export interface Site {
  name: string;
  site_type: SiteType;
  latitude: number | null;
  longitude: number | null;
  imported_geometry: {
    geometry_type: "point" | "line" | "polygon";
    coordinates: Array<[number, number]>;
  } | null;
  country: string | null;
  city: string | null;
  land_area_m2: number;
  buildable_area_mode: BuildableAreaMode;
  site_coverage_ratio: number;
  buildable_area_m2: number | null;
  max_building_height_m: number | null;
  floor_to_floor_height_m: number;
  num_floors: number;
  num_expansion_floors: number;
  roof_usable: boolean;
  whitespace_ratio: number;
  rack_footprint_m2: number;
  available_power_mw: number;
  power_confirmed: boolean;
  power_input_mode: PowerInputMode;
  voltage: string | null;
  // Green Energy Facilities
  pv_capacity_kwp: number | null;
  bess_capacity_kwh: number | null;
  bess_efficiency: number | null;
  fuel_cell_kw: number | null;
  // PVGIS Configuration
  pvgis_start_year: number | null;
  pvgis_end_year: number | null;
  pvgis_technology: string | null;
  pvgis_mounting_place: string | null;
  pvgis_system_loss_pct: number | null;
  pvgis_use_horizon: boolean | null;
  pvgis_optimal_angles: boolean | null;
  pvgis_surface_tilt_deg: number | null;
  pvgis_surface_azimuth_deg: number | null;
  notes: string | null;
}

export const DEFAULT_SITE: Site = {
  name: "",
  site_type: "Greenfield",
  latitude: null,
  longitude: null,
  imported_geometry: null,
  country: null,
  city: null,
  land_area_m2: 10000,
  buildable_area_mode: "ratio",
  site_coverage_ratio: 0.50,
  buildable_area_m2: null,
  max_building_height_m: null,
  floor_to_floor_height_m: 4.5,
  num_floors: 1,
  num_expansion_floors: 0,
  roof_usable: true,
  whitespace_ratio: 0.40,
  rack_footprint_m2: 3.0,
  available_power_mw: 0,
  power_confirmed: false,
  power_input_mode: "operational",
  voltage: null,
  pv_capacity_kwp: null,
  bess_capacity_kwh: null,
  bess_efficiency: null,
  fuel_cell_kw: null,
  pvgis_start_year: null,
  pvgis_end_year: null,
  pvgis_technology: null,
  pvgis_mounting_place: null,
  pvgis_system_loss_pct: null,
  pvgis_use_horizon: null,
  pvgis_optimal_angles: null,
  pvgis_surface_tilt_deg: null,
  pvgis_surface_azimuth_deg: null,
  notes: null,
};


// ─────────────────────────────────────────────────────────────
// Scenario
// ─────────────────────────────────────────────────────────────

export interface Scenario {
  load_type: LoadType;
  cooling_type: CoolingType;
  redundancy: RedundancyLevel;
  density_scenario: DensityScenario;
  pue_override: number | null;
  assumption_override_preset_key?: string | null;
  backup_power: BackupPowerType;
}


// ─────────────────────────────────────────────────────────────
// Results
// ─────────────────────────────────────────────────────────────

export interface SpaceResult {
  buildable_footprint_m2: number;
  gross_building_area_m2: number;
  it_whitespace_m2: number;
  support_area_m2: number;
  gray_space_m2: number;
  gray_space_ratio: number;
  max_racks_by_space: number;
  effective_racks: number;
  whitespace_adjustment_factor: number;
  site_coverage_used: number;
  whitespace_ratio_used: number;
  rack_footprint_used: number;
  active_floors: number;
  floor_to_floor_height_used: number;
  expansion_floors: number;
  expansion_whitespace_m2: number;
  expansion_racks: number;
}

export interface PowerResult {
  it_load_mw: number;
  facility_power_mw: number;
  procurement_power_mw: number;
  racks_by_power: number | null;
  racks_deployed: number;
  rack_density_kw: number;
  binding_constraint: "POWER" | "AREA";
  power_headroom_mw: number | null;
  eta_chain: number;
  pue_used: number;
  procurement_factor: number;
  power_input_mode: PowerInputMode;
  rag_status: RAGStatus;
  rag_reasons: string[];
}

export interface AppliedAssumptionOverride {
  key: string;
  label: string;
  scope_label: string;
  parameter_label: string;
  unit: string;
  baseline_value: number;
  previous_effective_value: number | null;
  effective_value: number;
  source: string;
  justification: string;
  origin: "settings_override" | "scenario_preset";
  preset_key: string | null;
  preset_label: string | null;
  updated_at_utc: string | null;
}

export interface ScenarioResult {
  site_id: string;
  site_name: string;
  scenario: Scenario;
  compatible_combination: boolean;
  space: SpaceResult;
  power: PowerResult;
  score: number;
  score_breakdown?: ScoreBreakdown;
  annual_pue: number | null;
  overtemperature_hours: number | null;
  pue_source: "static" | "hourly";
  it_capacity_worst_mw: number | null;
  it_capacity_p99_mw: number | null;
  it_capacity_p90_mw: number | null;
  it_capacity_mean_mw: number | null;
  it_capacity_best_mw: number | null;
  green_energy: GreenDispatchResult | null;
  assumption_override_preset_label: string | null;
  applied_assumption_overrides: AppliedAssumptionOverride[];
}

export interface ExpansionCapacitySnapshot {
  racks: number;
  it_load_mw: number;
  facility_power_mw: number;
  procurement_power_mw: number;
}

export interface ExpansionAdvisoryResult {
  advisory_only: boolean;
  binding_constraint: "POWER" | "AREA";
  rack_density_kw: number;
  pue_used: number;
  pue_source: "static" | "hourly";
  eta_chain: number;
  procurement_factor: number;
  active_floors: number;
  declared_expansion_floors: number;
  latent_height_floors: number;
  max_total_floors: number | null;
  current_floor_capacity_racks: number;
  unused_active_racks: number;
  declared_expansion_racks: number;
  latent_height_racks: number;
  total_additional_racks: number;
  current_facility_envelope_mw: number;
  current_procurement_envelope_mw: number;
  additional_grid_request_mw: number;
  current_feasible: ExpansionCapacitySnapshot;
  future_expandable: ExpansionCapacitySnapshot;
  total_site_potential: ExpansionCapacitySnapshot;
  notes: string[];
}

export interface ExpansionAdvisoryResponse {
  site_id: string;
  site_name: string;
  scenario: Scenario;
  baseline_result: ScenarioResult;
  expansion_advisory: ExpansionAdvisoryResult;
}

export interface HourlyProfilePoint {
  day: number;
  it_avg_mw: number;
  it_min_mw: number;
  it_max_mw: number;
  pue_avg: number;
  pue_min: number;
  pue_max: number;
}

export interface HourlyProfilesResult {
  site_id: string;
  site_name: string;
  scenario: Scenario;
  hours: number;
  day_count: number;
  annual_pue: number;
  annual_mean_it_mw: number;
  committed_it_mw: number;
  worst_it_mw: number;
  best_it_mw: number;
  days: HourlyProfilePoint[];
}


// ─────────────────────────────────────────────────────────────
// API Response shapes
// ─────────────────────────────────────────────────────────────

export interface SiteResponse {
  id: string;
  site: Site;
  has_weather: boolean;
  has_solar: boolean;
  solar_fetch_status: "none" | "loading" | "cached" | "error";
}

export interface SiteListResponse {
  count: number;
  sites: SiteResponse[];
}

export interface SpacePreviewResponse {
  space: SpaceResult;
  cooling_type_used: string | null;
}

export interface KMLUploadResponse {
  coordinates: Array<{
    latitude: number;
    longitude: number;
    name: string | null;
    description: string | null;
    geometry_type: "point" | "line" | "polygon";
    geometry_coordinates: Array<[number, number]>;
  }>;
  count: number;
}

export interface GeocodingResponse {
  results: Array<{
    latitude: number;
    longitude: number;
    name: string;
    country: string;
    admin1: string;
  }>;
  count: number;
}

export interface ReferenceData {
  load_profiles: Record<string, {
    density_kw: { low: number; typical: number; high: number };
    compatible_cooling: string[];
  }>;
  cooling_profiles: Record<string, {
    pue_typical: number;
    free_cooling_eligible: boolean;
    whitespace_adjustment_factor: number;
    max_rack_density_kw: number;
    description: string;
  }>;
}


// ─────────────────────────────────────────────────────────────
// Scenario API Request/Response types
// ─────────────────────────────────────────────────────────────

export interface GridAsset {
  asset_id: string;
  asset_type: GridAssetType;
  name: string | null;
  operator: string | null;
  voltage_kv: number | null;
  circuits: number | null;
  distance_km: number;
  geometry_type: GridGeometryType;
  coordinates: Array<[number, number]>;
  source: string;
  confidence: GridConfidence;
}

export interface GridContextSummary {
  radius_km: number;
  nearby_line_count: number;
  nearby_substation_count: number;
  nearest_line_km: number | null;
  nearest_substation_km: number | null;
  max_voltage_kv: number | null;
  high_voltage_assets_within_radius: number;
}

export interface GridContextScore {
  overall_score: number;
  voltage_score: number;
  distance_score: number;
  substation_score: number;
  evidence_score: number;
  notes: string[];
}

export interface GridEvidenceNote {
  label: string;
  detail: string;
  source: string;
  confidence: GridConfidence;
}

export interface GridOfficialEvidence {
  utility_or_tso_reference: string | null;
  reference_date: string | null;
  confirmed_substation_name: string | null;
  confirmed_voltage_kv: number | null;
  confirmed_requested_mw: number | null;
  confirmed_available_mw: number | null;
  connection_status: string | null;
  timeline_status: string | null;
  notes: string | null;
}

export interface GridOfficialEvidenceResponse {
  site_id: string;
  has_evidence: boolean;
  evidence: GridOfficialEvidence | null;
}

export interface GridContextRequest {
  site_id: string;
  radius_km?: number;
  force_refresh?: boolean;
  include_score?: boolean;
}

export interface GridContextResult {
  site_id: string;
  site_name: string;
  latitude: number;
  longitude: number;
  analysis_grade: GridAnalysisGrade;
  summary: GridContextSummary;
  score: GridContextScore | null;
  assets: GridAsset[];
  evidence_notes: GridEvidenceNote[];
  official_evidence: GridOfficialEvidence | null;
  official_context_notes: string[];
  source_layers: string[];
  confidence: GridConfidence;
  generated_at_utc: string;
}

export interface DeleteGridContextResponse {
  site_id: string;
  deleted: boolean;
}

export interface DeleteGridOfficialEvidenceResponse {
  site_id: string;
  deleted: boolean;
}

export interface RunSingleRequest {
  site_id: string;
  scenario: Scenario;
  include_hourly?: boolean;
}

export interface BatchRequest {
  site_ids: string[];
  load_types: LoadType[];
  cooling_types: CoolingType[];
  redundancy_levels?: RedundancyLevel[];
  density_scenarios?: DensityScenario[];
  assumption_override_preset_key?: string | null;
  include_hourly?: boolean;
  skip_incompatible?: boolean;
}

export interface BatchResponse {
  total_combinations: number;
  computed: number;
  skipped_incompatible: number;
  results: ScenarioResult[];
}

// ── Guided Mode Types ──

export interface GuidedPreset {
  load_type: string;
  cooling_type: string;
  density_scenario: string;
  density_kw: number;
  redundancy: string;
  rationale: string;
}

export interface GuidedPresetsResponse {
  presets: GuidedPreset[];
}

export interface GuidedRunResponse {
  total_combinations: number;
  skipped_incompatible: number;
  computed: number;
  results: ScenarioResult[];
  presets: GuidedPreset[];
}

export interface ScoreBreakdown {
  pue_score: number;
  it_capacity_score: number;
  space_utilization_score: number;
  rag_score: number;
  infrastructure_fit_score: number;
  weights: Record<string, number>;
  composite_score: number;
  equipment_fits: boolean;
  score_capped: boolean;
  score_cap_reason: string | null;
  component_reasons: Record<string, string>;
}

export interface ScoreRequest {
  results: ScenarioResult[];
  weights?: Record<string, number>;
}

export interface ScoreResponse {
  scored_results: Array<ScenarioResult & { score_breakdown?: ScoreBreakdown }>;
  count: number;
}

export type ReportLayoutMode = "presentation_16_9" | "report_a4_portrait";

export interface ReportPVGISProfile {
  site_id: string;
  site_name: string;
  profile_key: string;
  from_cache: boolean;
  latitude: number;
  longitude: number;
  start_year: number;
  end_year: number;
  years_averaged: number[];
  pv_technology: "crystSi" | "CIS" | "CdTe" | "Unknown";
  mounting_place: "free" | "building";
  system_loss_pct: number;
  use_horizon: boolean;
  optimal_angles: boolean;
  surface_tilt_deg: number | null;
  surface_azimuth_deg: number | null;
  source: string;
  radiation_database: string | null;
  elevation_m: number | null;
  pv_module_info: string | null;
  hours: number;
}

export interface ReportLoadMixAnalysis {
  result_key?: string | null;
  result: LoadMixResult;
}

export interface ReportGreenEnergyAnalysis {
  result_key?: string | null;
  result: ScenarioGreenDispatchResult;
  pv_profile_name?: string | null;
  pvgis_profile?: ReportPVGISProfile | null;
  bess_initial_soc_kwh?: number | null;
  grid_co2_kg_per_kwh?: number | null;
}

export interface ReportConfig {
  report_type: "executive" | "detailed";
  studied_site_ids: string[];
  primary_result_keys?: Record<string, string>;
  scenario_results?: ScenarioResult[];
  load_mix_results?: Record<string, ReportLoadMixAnalysis>;
  green_energy_results?: Record<string, ReportGreenEnergyAnalysis>;
  layout_mode: ReportLayoutMode;
  primary_color?: string;
  secondary_color?: string;
  logo_url?: string | null;
  font_family?: string;
  include_all_scenarios?: boolean;
}


// ─────────────────────────────────────────────────────────────
// Sensitivity — Tornado + Break-Even (sensitivity.py)
// ─────────────────────────────────────────────────────────────

/** One bar in the tornado chart (full model from sensitivity.py) */
export interface TornadoBar {
  parameter: string;
  parameter_label: string;
  baseline_value: number;
  low_value: number;
  high_value: number;
  output_at_low: number;
  output_at_baseline: number;
  output_at_high: number;
  spread: number;
  unit: string;
}

/** Complete tornado chart response */
export interface TornadoResult {
  output_metric_name: string;
  output_metric_unit: string;
  variation_pct: number;
  bars: TornadoBar[];
  most_influential: string;
  least_influential: string;
}

/** Break-even solver response (sensitivity.py) */
export interface BreakEvenResult {
  parameter: string;
  parameter_label: string;
  target_metric: string;
  target_value: number;
  break_even_value: number;
  baseline_value: number;
  change_from_baseline: number;
  change_pct: number;
  feasible: boolean;
  feasibility_note: string;
}


// ─────────────────────────────────────────────────────────────
// Infrastructure Footprint (footprint.py)
// ─────────────────────────────────────────────────────────────

export interface FootprintElement {
  name: string;
  area_m2: number;
  location: "gray_space" | "roof";
  sizing_basis_kw: number;
  m2_per_kw_used: number;
  num_units: number | null;
  unit_size_kw: number | null;
  source: string;
}

export interface FootprintResult {
  elements: FootprintElement[];
  total_gray_space_equipment_m2: number;
  total_roof_equipment_m2: number;
  total_infrastructure_m2: number;
  gray_space_m2: number;
  building_roof_m2: number;
  roof_usable: boolean;
  gray_space_utilization_ratio: number;
  roof_utilization_ratio: number;
  gray_space_fits: boolean;
  roof_fits: boolean;
  all_fits: boolean;
  gray_space_remaining_m2: number;
  ground_utilization_ratio: number;
  ground_fits: boolean;
  backup_power_type: string;
  backup_num_units: number;
  backup_unit_size_kw: number;
  warnings: string[];
}


// ─────────────────────────────────────────────────────────────
// Backup Power Comparison (backup_power.py)
// ─────────────────────────────────────────────────────────────

export interface BackupPowerSizing {
  technology: string;
  technology_type: string;
  fuel_type: string;
  num_units: number;
  unit_size_kw: number;
  total_rated_kw: number;
  footprint_m2: number;
  ramp_time_seconds: number;
  efficiency_min: number;
  efficiency_max: number;
  efficiency_typical: number;
  annual_runtime_hours: number;
  electrical_energy_mwh: number;
  fuel_energy_mwh: number;
  fuel_volume: number;
  fuel_volume_unit: string;
  co2_tonnes_per_year: number;
  co2_kg_per_kwh_fuel: number;
  emissions_category: string;
  source: string;
}

export interface BackupPowerComparison {
  procurement_power_mw: number;
  annual_runtime_hours: number;
  technologies: BackupPowerSizing[];
  diesel_co2_tonnes: number;
  lowest_co2_technology: string;
  lowest_footprint_technology: string;
  fastest_ramp_technology: string;
}

export interface PUEBreakdownComponent {
  key: string;
  label: string;
  energy_kwh: number;
  share_of_overhead: number;
}

export interface PUEBreakdownResult {
  annual_pue: number;
  total_facility_kwh: number;
  total_it_kwh: number;
  total_overhead_kwh: number;
  components: PUEBreakdownComponent[];
  cooling_mode_hours: {
    mech: number;
    econ_part: number;
    econ_full: number;
    overtemperature: number;
  };
}


// ─────────────────────────────────────────────────────────────
// Climate API types
// ─────────────────────────────────────────────────────────────

export interface WeatherStatus {
  site_id: string;
  has_weather: boolean;
  source?: string;
  source_type?: "open_meteo_archive" | "manual_upload" | "cached" | string;
  hours?: number;
  years_averaged?: number[];
  has_humidity?: boolean;
  original_filename?: string | null;
  uploaded_at_utc?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface TemperatureStats {
  count: number;
  mean: number;
  min: number;
  max: number;
  median: number;
  p1: number;
  p99: number;
  std_dev: number;
}

export interface FreeCoolingResult {
  cooling_type: string;
  free_cooling_hours: number;
  free_cooling_fraction: number;
  partial_hours: number;
  mechanical_hours: number;
  suitability: string;
}

export interface ClimateAnalysis {
  temperature_stats: TemperatureStats;
  monthly_stats: {
    monthly_mean: number[];
    monthly_min: number[];
    monthly_max: number[];
  } | null;
  free_cooling: FreeCoolingResult[];
  delta_results: Record<string, FreeCoolingResult[]>;
}


// ─────────────────────────────────────────────────────────────
// Green Energy Dispatch (green_energy.py)
// ─────────────────────────────────────────────────────────────

export interface GreenDispatchResult {
  total_overhead_kwh: number;
  total_pv_generation_kwh: number;
  total_pv_to_overhead_kwh: number;
  total_pv_to_bess_kwh: number;
  total_pv_curtailed_kwh: number;
  total_bess_discharge_kwh: number;
  total_fuel_cell_kwh: number;
  total_grid_import_kwh: number;
  overhead_coverage_fraction: number;
  renewable_fraction: number;
  pv_self_consumption_fraction: number;
  bess_cycles_equivalent: number;
  co2_avoided_tonnes: number;
  pv_capacity_kwp: number;
  bess_capacity_kwh: number;
  bess_roundtrip_efficiency: number;
  fuel_cell_capacity_kw: number;
  total_facility_kwh: number;
  total_it_kwh: number;
  hourly_dispatch?: Array<Record<string, number>>;
  pv_profile_source?: "zero" | "manual" | "pvgis";
  pvgis_params?: {
    start_year: number;
    end_year: number;
    pv_technology: string;
    mounting_place: string;
    system_loss_pct: number;
    use_horizon: boolean;
    optimal_angles: boolean;
    surface_tilt_deg: number | null;
    surface_azimuth_deg: number | null;
  };
}

export interface PVGISProfileResult {
  site_id: string;
  site_name: string;
  profile_key: string;
  from_cache: boolean;
  latitude: number;
  longitude: number;
  start_year: number;
  end_year: number;
  years_averaged: number[];
  pv_technology: "crystSi" | "CIS" | "CdTe" | "Unknown";
  mounting_place: "free" | "building";
  system_loss_pct: number;
  use_horizon: boolean;
  optimal_angles: boolean;
  surface_tilt_deg: number | null;
  surface_azimuth_deg: number | null;
  source: string;
  radiation_database: string | null;
  elevation_m: number | null;
  pv_module_info: string | null;
  hours: number;
  hourly_pv_kw_per_kwp: number[];
}

export interface ScenarioGreenDispatchResult extends GreenDispatchResult {
  site_name: string;
  hours: number;
  annual_pue: number;
  pue_source: "hourly";
  nominal_it_mw: number;
  committed_it_mw: number;
  pv_profile_source?: "zero" | "manual" | "pvgis";
  pvgis_profile_key?: string | null;
}

/** Advisory mode: auto-sizing for target coverage levels */
export interface GreenAdvisoryCoverageLevel {
  coverage_target: number;
  // PV-only sizing
  pv_only_kwp_needed: number;
  pv_only_annual_gen_mwh: number;
  pv_only_co2_avoided_tonnes: number;
  pv_only_coverage_achieved: number;
  pv_only_ceiling_reached: boolean;
  // PV + BESS sizing
  pv_kwp_needed: number;
  bess_kwh_needed: number;
  annual_generation_mwh: number;
  co2_avoided_tonnes: number;
  renewable_fraction: number;
}

export interface GreenAdvisoryResult {
  site_id: string;
  site_name: string;
  scenario_key: string;
  total_overhead_kwh: number;
  levels: GreenAdvisoryCoverageLevel[];
}

export interface GreenCustomCoverageResult {
  coverage_target: number;
  pv_only_kwp_needed: number;
  pv_only_annual_gen_mwh: number;
  pv_only_co2_avoided_tonnes: number;
  pv_only_coverage_achieved: number;
  pv_only_ceiling_reached: boolean;
  pv_kwp_needed: number;
  bess_kwh_needed: number;
  annual_generation_mwh: number;
  co2_avoided_tonnes: number;
  renewable_fraction: number;
}

export interface FirmCapacityBaseline {
  nominal_it_mw: number;
  worst_it_mw: number;
  p99_it_mw: number;
  p90_it_mw: number;
  mean_it_mw: number;
  best_it_mw: number;
  annual_pue: number;
  facility_power_mw: number;
  procurement_power_mw: number;
}

export interface FirmCapacitySupported {
  max_firm_it_mw: number;
  gain_vs_worst_mw: number;
  gain_vs_p99_mw: number;
  max_required_facility_mw: number;
  peak_support_mw: number;
  hours_above_grid_cap: number;
  hours_with_capacity_support: number;
  grid_to_bess_mwh: number;
  pv_direct_mwh: number;
  pv_to_bess_mwh: number;
  bess_discharge_mwh: number;
  fuel_cell_mwh: number;
  backup_dispatch_mwh: number;
  cyclic_bess: boolean;
  cyclic_converged: boolean;
  initial_bess_soc_mwh: number;
  final_bess_soc_mwh: number;
}

export interface FirmCapacityTargetEvaluation {
  target_it_mw: number;
  feasible: boolean;
  peak_support_mw: number;
  peak_unmet_mw: number;
  hours_above_grid_cap: number;
  hours_with_capacity_support: number;
  unmet_hours: number;
  unmet_energy_mwh: number;
  grid_to_bess_mwh: number;
  pv_direct_mwh: number;
  bess_discharge_mwh: number;
  fuel_cell_mwh: number;
  backup_dispatch_mwh: number;
  cyclic_bess: boolean;
  cyclic_converged: boolean;
  hourly_dispatch?: Array<Record<string, number>>;
}

export interface FirmCapacityRecommendationCandidate {
  key: string;
  label: string;
  description: string;
  target_it_mw: number;
  feasible: boolean;
  bess_capacity_mwh: number;
  fuel_cell_mw: number;
  backup_dispatch_mw: number;
  peak_support_mw: number;
  support_hours: number;
  grid_to_bess_mwh: number;
  bess_discharge_mwh: number;
  fuel_cell_mwh: number;
  backup_dispatch_mwh: number;
  unmet_energy_mwh: number;
  notes: string[];
}

export interface FirmCapacityRecommendations {
  target_it_mw: number;
  target_already_feasible: boolean;
  annual_support_energy_mwh: number;
  peak_support_mw: number;
  hours_above_grid_cap: number;
  gap_vs_p99_mw: number;
  gap_vs_worst_mw: number;
  candidates: FirmCapacityRecommendationCandidate[];
}

export interface FirmCapacityResult {
  baseline: FirmCapacityBaseline;
  supported: FirmCapacitySupported;
  target_evaluation: FirmCapacityTargetEvaluation | null;
  recommendations: FirmCapacityRecommendations | null;
}


// ---------------------------------------------------------------------------
// Firm Capacity Advisory (Preset Methodology)
// ---------------------------------------------------------------------------

export interface MitigationStrategy {
  key: string;
  label: string;
  description: string;
  capacity_kw: number;
  capacity_mw: number;
  estimated_capex_usd: number;
  sizing_summary: string;
  notes: string[];
}

export interface FirmCapacityAdvisoryResult {
  firm_capacity_mw: number;
  firm_capacity_kw: number;
  mean_capacity_mw: number;
  mean_capacity_kw: number;
  worst_capacity_mw: number;
  worst_capacity_kw: number;
  best_capacity_mw: number;
  best_capacity_kw: number;
  capacity_gap_mw: number;
  capacity_gap_kw: number;
  peak_deficit_mw: number;
  peak_deficit_kw: number;
  deficit_hours: number;
  deficit_energy_kwh: number;
  annual_pue: number;
  facility_power_mw: number;
  hourly_it_kw_sampled?: number[];
  strategies: MitigationStrategy[];
}


// ---------------------------------------------------------------------------
// Settings / Runtime Operations
// ---------------------------------------------------------------------------

export interface RuntimeStatus {
  sites_stored: number;
  weather_cached: number;
  solar_sites_cached: number;
  solar_profiles_cached: number;
  report_templates_available: number;
  report_template_names: string[];
}

export interface ExternalServiceProbe {
  key: string;
  label: string;
  ok: boolean;
  status_code?: number | null;
  latency_ms?: number | null;
  detail: string;
}

export interface ExternalServicesResult {
  checked_at_utc: string;
  services: ExternalServiceProbe[];
}

export interface CacheClearResult {
  target: "weather" | "solar" | "all";
  removed_weather_files: number;
  removed_solar_profiles: number;
}

export interface PersistedAssumptionOverride {
  value: number;
  source: string;
  justification: string;
  updated_at_utc: string;
}

export interface AssumptionOverrideEntry {
  key: string;
  section: "cooling" | "redundancy" | "misc";
  section_label: string;
  scope_label: string;
  parameter_label: string;
  unit: string;
  impact_scope: "static_and_hourly" | "hourly_only";
  baseline_value: number;
  effective_value: number;
  min_value: number;
  max_value: number;
  baseline_source: string;
  description: string;
  override: PersistedAssumptionOverride | null;
}

export interface AssumptionOverridesResponse {
  updated_at_utc: string | null;
  active_override_count: number;
  assumptions: AssumptionOverrideEntry[];
}

export interface AssumptionOverridePresetValue {
  key: string;
  section: "cooling" | "redundancy" | "misc";
  scope_label: string;
  parameter_label: string;
  unit: string;
  impact_scope: "static_and_hourly" | "hourly_only";
  baseline_value: number;
  preset_value: number;
  justification: string;
}

export interface AssumptionOverridePreset {
  key: string;
  label: string;
  description: string;
  source: string;
  override_count: number;
  overrides: AssumptionOverridePresetValue[];
}

export interface AssumptionOverridePresetsResponse {
  presets: AssumptionOverridePreset[];
}

export interface AssumptionOverrideHistoryItem {
  action: "activated" | "updated" | "cleared" | "preset_applied";
  key: string;
  label: string;
  scope_label: string;
  parameter_label: string;
  unit: string;
  origin: "settings_override" | "scenario_preset";
  previous_value: number | null;
  effective_value: number;
  source: string;
  justification: string;
}

export interface AssumptionOverrideHistoryEntry {
  id: string;
  recorded_at_utc: string;
  event_type: "settings_update" | "scenario_preset_run";
  title: string;
  summary: string;
  preset_key: string | null;
  preset_label: string | null;
  active_override_count?: number | null;
  site_count?: number | null;
  scenario_count?: number | null;
  changes: AssumptionOverrideHistoryItem[];
}

export interface AssumptionOverrideHistoryResponse {
  entries: AssumptionOverrideHistoryEntry[];
}

export interface AssumptionOverrideUpdate {
  key: string;
  override_value: number | null;
  source?: string | null;
  justification?: string | null;
}


// ─────────────────────────────────────────────────────────────
// Load Mix Optimizer
// ─────────────────────────────────────────────────────────────

export interface LoadMixAllocation {
  load_type: string;
  share_pct: number;
  it_load_mw: number;
  rack_count: number;
  rack_density_kw: number;
}

export interface LoadMixCandidate {
  rank: number;
  allocations: LoadMixAllocation[];
  total_racks: number;
  all_compatible: boolean;
  blended_pue: number;
  score: number;
  trade_off_notes: string[];
}

export interface LoadMixResult {
  total_it_mw: number;
  allowed_load_types: string[];
  cooling_type: string;
  density_scenario: string;
  step_pct: number;
  min_racks: number;
  total_candidates_evaluated: number;
  top_candidates: LoadMixCandidate[];
  assumption_override_preset_key?: string | null;
}


// ─────────────────────────────────────────────────────────────
// Health check
// ─────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  version: string;
  phase: string;
  sites_stored: number;
  weather_cached: number;
  solar_profiles_cached: number;
}
