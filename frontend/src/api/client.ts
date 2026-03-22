/**
 * DC Feasibility Tool v4 — API Client
 * =====================================
 * Axios-based HTTP client for talking to the FastAPI backend.
 *
 * CONCEPT — What is Axios?
 * Axios is a library for making HTTP requests (GET, POST, PUT, DELETE)
 * from JavaScript/TypeScript. It's like Python's "requests" library.
 * Instead of `requests.get(url)` you write `axios.get(url)`.
 *
 * CONCEPT — What is an API client?
 * Instead of scattering HTTP calls across every page component, we
 * centralize them here. Every page imports functions from this file.
 * If a URL changes, we fix it in one place.
 *
 * CONCEPT — Generics: `axios.get<SiteListResponse>(...)` tells
 * TypeScript "the response data will match this type." This gives
 * autocomplete when you use the response.
 *
 * The Vite dev server proxies `/api/*` to http://localhost:8000,
 * so we only need relative URLs like "/api/sites".
 */

import axios from "axios";
import type {
  Site,
  SiteResponse,
  SiteListResponse,
  SpacePreviewResponse,
  KMLUploadResponse,
  GeocodingResponse,
  ReferenceData,
  RunSingleRequest,
  BatchRequest,
  BatchResponse,
  ScoreRequest,
  ScoreResponse,
  ScenarioResult,
  ExpansionAdvisoryResponse,
  HourlyProfilesResult,
  TornadoResult,
  BreakEvenResult,
  WeatherStatus,
  ClimateAnalysis,
  HealthResponse,
  LoadType,
  CoolingType,
  DensityScenario,
  BackupPowerType,
  PUEBreakdownResult,
  FootprintResult,
  FirmCapacityResult,
  FirmCapacityAdvisoryResult,
  GreenDispatchResult,
  ScenarioGreenDispatchResult,
  LoadMixResult,
  PVGISProfileResult,
  ReportConfig,
  RuntimeStatus,
  ExternalServicesResult,
  CacheClearResult,
  AssumptionOverrideHistoryResponse,
  AssumptionOverridePresetsResponse,
  AssumptionOverridesResponse,
  AssumptionOverrideUpdate,
  GridContextRequest,
  GridContextResult,
  DeleteGridContextResponse,
  GridOfficialEvidence,
  GridOfficialEvidenceResponse,
  DeleteGridOfficialEvidenceResponse,
  GuidedPresetsResponse,
  GuidedRunResponse,
} from "../types";

type RawReferenceData = {
  load_profiles: Record<string, {
    density_kw?: { low: number; typical: number; high: number };
    density_low_kw?: number;
    density_typical_kw?: number;
    density_high_kw?: number;
    compatible_cooling: string[];
  }>;
  cooling_profiles: ReferenceData["cooling_profiles"];
};

// ─────────────────────────────────────────────────────────────
// Axios instance with base configuration
// ─────────────────────────────────────────────────────────────
// CONCEPT: An "instance" lets us set defaults (like the base URL
// and timeout) once, then every request inherits them.
//
// baseURL is "" because the Vite proxy already forwards /api/*
// to the backend. In production, you'd set this to the backend URL.

const api = axios.create({
  baseURL: "",
  timeout: 60000, // 60 seconds — some batch runs take a while
  headers: { "Content-Type": "application/json" },
});


// ─────────────────────────────────────────────────────────────
// Health Check
// ─────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>("/api/health");
  return data;
}

export async function getRuntimeStatus(): Promise<RuntimeStatus> {
  const { data } = await api.get<RuntimeStatus>("/api/settings/runtime-status");
  return data;
}

export async function testExternalServices(): Promise<ExternalServicesResult> {
  const { data } = await api.post<ExternalServicesResult>(
    "/api/settings/test-external-services"
  );
  return data;
}

export async function clearServerCache(target: "weather" | "solar" | "all"): Promise<CacheClearResult> {
  const { data } = await api.post<CacheClearResult>("/api/settings/clear-cache", {
    target,
  });
  return data;
}

export async function getAssumptionOverrides(): Promise<AssumptionOverridesResponse> {
  const { data } = await api.get<AssumptionOverridesResponse>(
    "/api/settings/assumption-overrides"
  );
  return data;
}

export async function getAssumptionOverridePresets(): Promise<AssumptionOverridePresetsResponse> {
  const { data } = await api.get<AssumptionOverridePresetsResponse>(
    "/api/settings/assumption-overrides/presets"
  );
  return data;
}

export async function getAssumptionOverrideHistory(
  limit = 20
): Promise<AssumptionOverrideHistoryResponse> {
  const { data } = await api.get<AssumptionOverrideHistoryResponse>(
    "/api/settings/assumption-overrides/history",
    { params: { limit } }
  );
  return data;
}

export async function saveAssumptionOverrides(
  overrides: AssumptionOverrideUpdate[]
): Promise<AssumptionOverridesResponse> {
  const { data } = await api.put<AssumptionOverridesResponse>(
    "/api/settings/assumption-overrides",
    { overrides }
  );
  return data;
}


// ─────────────────────────────────────────────────────────────
// Sites CRUD — maps to routes_site.py endpoints
// ─────────────────────────────────────────────────────────────

/** Create a new site → POST /api/sites */
export async function createSite(site: Site): Promise<SiteResponse> {
  const { data } = await api.post<SiteResponse>("/api/sites", site);
  return data;
}

/** List all sites → GET /api/sites */
export async function listSites(): Promise<SiteListResponse> {
  const { data } = await api.get<SiteListResponse>("/api/sites");
  return data;
}

/** Get one site → GET /api/sites/{id} */
export async function getSite(siteId: string): Promise<SiteResponse> {
  const { data } = await api.get<SiteResponse>(`/api/sites/${siteId}`);
  return data;
}

/** Update a site → PUT /api/sites/{id} */
export async function updateSite(siteId: string, site: Site): Promise<SiteResponse> {
  const { data } = await api.put<SiteResponse>(`/api/sites/${siteId}`, site);
  return data;
}

/** Delete a site → DELETE /api/sites/{id} */
export async function deleteSite(siteId: string): Promise<void> {
  await api.delete(`/api/sites/${siteId}`);
}

/** Quick geometry preview → GET /api/sites/{id}/space-preview */
export async function getSpacePreview(
  siteId: string,
  coolingType?: string
): Promise<SpacePreviewResponse> {
  const params = coolingType ? { cooling_type: coolingType } : {};
  const { data } = await api.get<SpacePreviewResponse>(
    `/api/sites/${siteId}/space-preview`,
    { params }
  );
  return data;
}

/** Upload KML file → POST /api/sites/upload-kml */
export async function uploadKML(file: File): Promise<KMLUploadResponse> {
  // CONCEPT: For file uploads, we use FormData instead of JSON.
  // FormData is how browsers encode files for HTTP upload — like
  // a multipart/form-data form in HTML.
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<KMLUploadResponse>(
    "/api/sites/upload-kml",
    formData,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data;
}

/** Geocode a city name → GET /api/geocode */
export async function geocode(query: string): Promise<GeocodingResponse> {
  const { data } = await api.get<GeocodingResponse>("/api/geocode", {
    params: { q: query },
  });
  return data;
}

/** Get reference data for dropdowns → GET /api/reference-data */
export async function getReferenceData(): Promise<ReferenceData> {
  const { data } = await api.get<RawReferenceData>("/api/reference-data");
  return {
    load_profiles: Object.fromEntries(
      Object.entries(data.load_profiles).map(([name, profile]) => [
        name,
        {
          ...profile,
          density_kw: profile.density_kw ?? {
            low: profile.density_low_kw ?? 0,
            typical: profile.density_typical_kw ?? 0,
            high: profile.density_high_kw ?? 0,
          },
        },
      ])
    ),
    cooling_profiles: data.cooling_profiles,
  };
}


// ─────────────────────────────────────────────────────────────
// Scenarios — maps to routes_scenario.py endpoints
// ─────────────────────────────────────────────────────────────

/** Run a single scenario → POST /api/scenarios/run */
export async function fetchGridContext(
  request: GridContextRequest
): Promise<GridContextResult> {
  const { data } = await api.post<GridContextResult>("/api/grid/context", request);
  return data;
}

export async function getCachedGridContext(
  siteId: string,
  radiusKm = 5,
  includeScore = false
): Promise<GridContextResult> {
  const { data } = await api.get<GridContextResult>(`/api/grid/context/${siteId}`, {
    params: {
      radius_km: radiusKm,
      include_score: includeScore,
    },
  });
  return data;
}

export async function deleteGridContext(
  siteId: string
): Promise<DeleteGridContextResponse> {
  const { data } = await api.delete<DeleteGridContextResponse>(
    `/api/grid/context/${siteId}`
  );
  return data;
}

export async function getGridOfficialEvidence(
  siteId: string
): Promise<GridOfficialEvidenceResponse> {
  const { data } = await api.get<GridOfficialEvidenceResponse>(
    `/api/grid/evidence/${siteId}`
  );
  return data;
}

export async function saveGridOfficialEvidence(
  siteId: string,
  evidence: GridOfficialEvidence
): Promise<GridOfficialEvidenceResponse> {
  const { data } = await api.put<GridOfficialEvidenceResponse>(
    `/api/grid/evidence/${siteId}`,
    evidence
  );
  return data;
}

export async function deleteGridOfficialEvidence(
  siteId: string
): Promise<DeleteGridOfficialEvidenceResponse> {
  const { data } = await api.delete<DeleteGridOfficialEvidenceResponse>(
    `/api/grid/evidence/${siteId}`
  );
  return data;
}

export async function runSingle(request: RunSingleRequest): Promise<ScenarioResult> {
  const { data } = await api.post<ScenarioResult>("/api/scenarios/run", request);
  return data;
}

/** Run batch scenarios → POST /api/scenarios/batch */
export async function runBatch(request: BatchRequest): Promise<BatchResponse> {
  const { data } = await api.post<BatchResponse>("/api/scenarios/batch", request);
  return data;
}

/** Get guided mode preset table → GET /api/scenarios/guided-presets */
export async function getGuidedPresets(): Promise<GuidedPresetsResponse> {
  const { data } = await api.get<GuidedPresetsResponse>("/api/scenarios/guided-presets");
  return data;
}

/** Run guided mode analysis → POST /api/scenarios/guided-run */
export async function runGuidedAnalysis(siteIds: string[]): Promise<GuidedRunResponse> {
  const { data } = await api.post<GuidedRunResponse>("/api/scenarios/guided-run", {
    site_ids: siteIds,
  });
  return data;
}

/** Score and rank results → POST /api/scenarios/score */
export async function scoreResults(request: ScoreRequest): Promise<ScoreResponse> {
  const { data } = await api.post<ScoreResponse>("/api/scenarios/score", request);
  return data;
}

/** Advisory-only future build-out potential -> POST /api/scenarios/expansion-advisory */
export async function computeExpansionAdvisory(
  request: RunSingleRequest
): Promise<ExpansionAdvisoryResponse> {
  const { data } = await api.post<ExpansionAdvisoryResponse>(
    "/api/scenarios/expansion-advisory",
    request
  );
  return data;
}

/** Daily IT-load and PUE profiles from the hourly year -> POST /api/scenarios/hourly-profiles */
export async function computeHourlyProfiles(request: {
  site_id: string;
  scenario: RunSingleRequest["scenario"];
}): Promise<HourlyProfilesResult> {
  const { data } = await api.post<HourlyProfilesResult>(
    "/api/scenarios/hourly-profiles",
    request
  );
  return data;
}

/** Load mix optimization → POST /api/scenarios/load-mix */
export async function optimizeLoadMix(request: {
  total_it_mw: number;
  allowed_load_types: LoadType[];
  cooling_type: CoolingType;
  density_scenario?: DensityScenario;
  step_pct?: number;
  min_racks?: number;
  top_n?: number;
}): Promise<LoadMixResult> {
  const { data } = await api.post<LoadMixResult>("/api/scenarios/load-mix", request);
  return data;
}

/** Tornado sensitivity analysis → POST /api/scenarios/tornado */
export async function computeTornado(request: Record<string, unknown>): Promise<TornadoResult> {
  const { data } = await api.post<TornadoResult>("/api/scenarios/tornado", request);
  return data;
}

/** Break-even solver → POST /api/scenarios/break-even */
export async function computeBreakEven(
  request: Record<string, unknown>
): Promise<BreakEvenResult> {
  const { data } = await api.post<BreakEvenResult>(
    "/api/scenarios/break-even",
    request
  );
  return data;
}

/** Backup power comparison → POST /api/scenarios/backup-power */
export async function compareBackupPower(request: {
  procurement_power_mw: number;
  annual_runtime_hours?: number;
}): Promise<unknown> {
  const { data } = await api.post("/api/scenarios/backup-power", request);
  return data;
}

/** Infrastructure footprint → POST /api/scenarios/footprint */
export async function computeFootprint(request: {
  facility_power_mw: number;
  procurement_power_mw: number;
  buildable_footprint_m2: number;
  land_area_m2: number;
  backup_power_type?: BackupPowerType;
  cooling_m2_per_kw_override?: number;
}): Promise<FootprintResult> {
  const { data } = await api.post<FootprintResult>("/api/scenarios/footprint", request);
  return data;
}

/** Annual PUE overhead decomposition → POST /api/scenarios/pue-breakdown */
export async function computePUEBreakdown(request: {
  site_id: string;
  scenario: RunSingleRequest["scenario"];
}): Promise<PUEBreakdownResult> {
  const { data } = await api.post<PUEBreakdownResult>(
    "/api/scenarios/pue-breakdown",
    request
  );
  return data;
}

/** Firm IT capacity with peak support → POST /api/green/firm-capacity */
export async function computeFirmCapacity(request: {
  site_id: string;
  scenario: RunSingleRequest["scenario"];
  target_it_load_mw?: number;
  hourly_pv_kw?: number[];
  pvgis_profile_key?: string;
  pv_capacity_kwp?: number;
  bess_capacity_kwh?: number;
  bess_roundtrip_efficiency?: number;
  bess_initial_soc_kwh?: number;
  fuel_cell_capacity_kw?: number;
  backup_dispatch_capacity_kw?: number;
  cyclic_bess?: boolean;
  include_hourly_dispatch?: boolean;
}): Promise<FirmCapacityResult> {
  const { data } = await api.post<FirmCapacityResult>(
    "/api/green/firm-capacity",
    request
  );
  return data;
}


/** Auto-computed firm capacity advisory → POST /api/scenarios/firm-capacity-advisory */
export async function computeFirmCapacityAdvisory(request: {
  site_id: string;
  scenario: RunSingleRequest["scenario"];
}): Promise<FirmCapacityAdvisoryResult> {
  const { data } = await api.post<FirmCapacityAdvisoryResult>(
    "/api/scenarios/firm-capacity-advisory",
    request
  );
  return data;
}


// ─────────────────────────────────────────────────────────────
// Climate — maps to routes_climate.py endpoints
// ─────────────────────────────────────────────────────────────

/** Fetch weather data from Open-Meteo → POST /api/climate/fetch-weather */
export async function fetchWeather(request: {
  site_id: string;
  start_year?: number;
  end_year?: number;
  force_refresh?: boolean;
}): Promise<WeatherStatus> {
  const { data } = await api.post<WeatherStatus>(
    "/api/climate/fetch-weather",
    request
  );
  return data;
}

/** Upload a manual hourly weather CSV → POST /api/climate/upload-weather */
export async function uploadWeatherFile(siteId: string, file: File): Promise<WeatherStatus> {
  const formData = new FormData();
  formData.append("site_id", siteId);
  formData.append("file", file);
  const { data } = await api.post<WeatherStatus>(
    "/api/climate/upload-weather",
    formData,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data;
}

/** Get cached weather status → GET /api/climate/weather/{id} */
export async function getWeatherStatus(
  siteId: string,
  includeHourly = false
): Promise<WeatherStatus> {
  const { data } = await api.get<WeatherStatus>(
    `/api/climate/weather/${siteId}`,
    { params: { include_hourly: includeHourly } }
  );
  return data;
}

export async function deleteWeatherCache(
  siteId: string
): Promise<{ site_id: string; deleted: boolean }> {
  const { data } = await api.delete<{ site_id: string; deleted: boolean }>(
    `/api/climate/weather/${siteId}`
  );
  return data;
}

/** Climate analysis from site's cached weather → POST /api/climate/analyse-site */
export async function analyseSite(request: {
  site_id: string;
  cooling_types?: string[];
  deltas?: number[];
}): Promise<ClimateAnalysis> {
  const { data } = await api.post<ClimateAnalysis>(
    "/api/climate/analyse-site",
    request
  );
  return data;
}


// ─────────────────────────────────────────────────────────────
// Green Energy — maps to routes_green.py endpoints
// ─────────────────────────────────────────────────────────────

/** Run green energy dispatch simulation → POST /api/green/simulate */
export async function simulateGreen(
  request: Record<string, unknown>
): Promise<GreenDispatchResult> {
  const { data } = await api.post<GreenDispatchResult>("/api/green/simulate", request);
  return data;
}

/** Fetch/cache a normalized 1 kWp PVGIS profile → POST /api/green/fetch-pvgis-profile */
export async function fetchPVGISProfile(request: {
  site_id: string;
  start_year?: number;
  end_year?: number;
  pv_technology?: "crystSi" | "CIS" | "CdTe" | "Unknown";
  mounting_place?: "free" | "building";
  system_loss_pct?: number;
  use_horizon?: boolean;
  optimal_angles?: boolean;
  surface_tilt_deg?: number;
  surface_azimuth_deg?: number;
  force_refresh?: boolean;
}): Promise<PVGISProfileResult> {
  const { data } = await api.post<PVGISProfileResult>(
    "/api/green/fetch-pvgis-profile",
    request
  );
  return data;
}

/** Run green dispatch from a saved scenario → POST /api/green/scenario-dispatch */
export async function simulateScenarioGreen(request: {
  site_id: string;
  scenario: RunSingleRequest["scenario"];
  hourly_pv_kw?: number[];
  pvgis_profile_key?: string;
  bess_capacity_kwh?: number;
  bess_roundtrip_efficiency?: number;
  bess_initial_soc_kwh?: number;
  fuel_cell_capacity_kw?: number;
  pv_capacity_kwp?: number;
  grid_co2_kg_per_kwh?: number;
  include_hourly_dispatch?: boolean;
}): Promise<ScenarioGreenDispatchResult> {
  const { data } = await api.post<ScenarioGreenDispatchResult>(
    "/api/green/scenario-dispatch",
    request
  );
  return data;
}

/** Extracts a human-readable message from an axios error response. */
function extractApiError(err: unknown): Error {
  if (err && typeof err === "object" && "response" in err) {
    const response = (err as { response?: { data?: unknown; status?: number } }).response;
    if (response?.data) {
      const data = response.data;
      if (typeof data === "string" && data.length < 500) return new Error(data);
      if (typeof data === "object" && data !== null && "detail" in data) {
        const detail = (data as { detail: unknown }).detail;
        if (typeof detail === "string") return new Error(detail.slice(0, 400));
      }
    }
  }
  if (err instanceof Error) return err;
  return new Error("Unknown error");
}

/** HTML preview report for explicitly selected studied sites -> POST /api/export/html */
export async function exportHtmlReport(config: ReportConfig): Promise<string> {
  try {
    const { data } = await api.post("/api/export/html", config, { responseType: "text" });
    return data as string;
  } catch (err) {
    throw extractApiError(err);
  }
}

/** PDF report via WeasyPrint -> POST /api/export/pdf */
export async function exportPdfReport(config: ReportConfig): Promise<Blob> {
  try {
    const { data } = await api.post("/api/export/pdf", config, { responseType: "blob" });
    return data as Blob;
  } catch (err) {
    throw extractApiError(err);
  }
}

/** Excel workbook for explicitly selected studied sites -> POST /api/export/excel */
export async function exportExcelReport(config: ReportConfig): Promise<Blob> {
  try {
    const { data } = await api.post("/api/export/excel", config, { responseType: "blob" });
    return data as Blob;
  } catch (err) {
    throw extractApiError(err);
  }
}

/** Get terrain preview image URL for a site */
export function getTerrainPreviewUrl(siteId: string): string {
  return `/api/export/terrain-preview?site_id=${encodeURIComponent(siteId)}`;
}
