import { useEffect, useState } from "react";
import { AlertCircle, Download, FileText, Loader2 } from "lucide-react";
import * as api from "../api/client";
import { loadSessionState } from "../lib/sessionState";
import { useAppStore } from "../store/useAppStore";
import type {
  LoadMixResult,
  PVGISProfileResult,
  ReportConfig,
  ReportPVGISProfile,
  ReportLayoutMode,
  ScenarioGreenDispatchResult,
  ScenarioResult,
  SiteResponse,
} from "../types";

const LOAD_MIX_STATE_KEY = "load-mix-state";
const GREEN_ENERGY_STATE_KEY = "green-energy-state";

type LoadMixSessionState = {
  result: LoadMixResult | null;
  resultSelectionKey: string | null;
};

type GreenEnergySessionState = {
  bessInitialSocKwh: string;
  co2Factor: string;
  pvProfileName: string | null;
  pvgisProfile: PVGISProfileResult | null;
  result: ScenarioGreenDispatchResult | null;
  resultSelectionKey: string | null;
};

const DEFAULT_LOAD_MIX_STATE: LoadMixSessionState = {
  result: null,
  resultSelectionKey: null,
};

const DEFAULT_GREEN_ENERGY_STATE: GreenEnergySessionState = {
  bessInitialSocKwh: "0",
  co2Factor: "0.256",
  pvProfileName: null,
  pvgisProfile: null,
  result: null,
  resultSelectionKey: null,
};


type StudiedSiteOption = {
  siteId: string;
  siteName: string;
  locationLabel: string;
  availablePowerMw: number | null;
  results: ScenarioResult[];
};


function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}


function buildResultSelectionKey(result: ScenarioResult): string {
  return JSON.stringify({
    site_id: result.site_id,
    load_type: result.scenario.load_type,
    cooling_type: result.scenario.cooling_type,
    redundancy: result.scenario.redundancy,
    density_scenario: result.scenario.density_scenario,
    backup_power: result.scenario.backup_power,
    pue_override: result.scenario.pue_override,
    assumption_override_preset_key: result.scenario.assumption_override_preset_key ?? null,
  });
}


function getCommittedItMw(result: ScenarioResult): number {
  return result.it_capacity_p99_mw ?? result.power.it_load_mw;
}


function describeScenarioChoice(result: ScenarioResult): string {
  return (
    `${result.scenario.load_type} | ` +
    `${result.scenario.cooling_type} | ` +
    `${result.scenario.redundancy} | ` +
    `${result.scenario.density_scenario} | ` +
    `IT ${getCommittedItMw(result).toFixed(2)} MW | ` +
    `score ${result.score.toFixed(1)}`
  );
}


function formatLocationLabel(site: SiteResponse["site"] | null): string {
  if (!site) {
    return "Saved site details unavailable in the current store";
  }
  const parts = [site.city, site.country].filter(Boolean);
  return parts.length > 0 ? parts.join(", ") : "Location not set";
}


function toReportPVGISProfile(profile: PVGISProfileResult): ReportPVGISProfile {
  return {
    site_id: profile.site_id,
    site_name: profile.site_name,
    profile_key: profile.profile_key,
    from_cache: profile.from_cache,
    latitude: profile.latitude,
    longitude: profile.longitude,
    start_year: profile.start_year,
    end_year: profile.end_year,
    years_averaged: profile.years_averaged,
    pv_technology: profile.pv_technology,
    mounting_place: profile.mounting_place,
    system_loss_pct: profile.system_loss_pct,
    use_horizon: profile.use_horizon,
    optimal_angles: profile.optimal_angles,
    surface_tilt_deg: profile.surface_tilt_deg,
    surface_azimuth_deg: profile.surface_azimuth_deg,
    source: profile.source,
    radiation_database: profile.radiation_database,
    elevation_m: profile.elevation_m,
    pv_module_info: profile.pv_module_info,
    hours: profile.hours,
  };
}


function buildStudiedSiteOptions(
  sites: SiteResponse[],
  batchResults: ScenarioResult[],
): StudiedSiteOption[] {
  const resultsBySite = new Map<string, ScenarioResult[]>();
  for (const result of batchResults) {
    const current = resultsBySite.get(result.site_id);
    if (current) {
      current.push(result);
    } else {
      resultsBySite.set(result.site_id, [result]);
    }
  }

  const options: StudiedSiteOption[] = [];
  const seenSiteIds = new Set<string>();

  for (const siteEntry of sites) {
    const siteResults = resultsBySite.get(siteEntry.id);
    if (!siteResults || siteResults.length === 0) {
      continue;
    }
    options.push({
      siteId: siteEntry.id,
      siteName: siteEntry.site.name,
      locationLabel: formatLocationLabel(siteEntry.site),
      availablePowerMw: siteEntry.site.available_power_mw,
      results: siteResults,
    });
    seenSiteIds.add(siteEntry.id);
  }

  for (const [siteId, siteResults] of resultsBySite.entries()) {
    if (seenSiteIds.has(siteId) || siteResults.length === 0) {
      continue;
    }
    options.push({
      siteId,
      siteName: siteResults[0].site_name,
      locationLabel: formatLocationLabel(null),
      availablePowerMw: null,
      results: siteResults,
    });
  }

  return options;
}


const LAYOUT_OPTIONS: Array<{
  value: ReportLayoutMode;
  label: string;
  description: string;
}> = [
  {
    value: "presentation_16_9",
    label: "Presentation 16:9",
    description: "Slide-style pages for review meetings and screen sharing.",
  },
  {
    value: "report_a4_portrait",
    label: "Report A4 Portrait",
    description: "Portrait pages tuned for formal document distribution and print.",
  },
];


export default function Export() {
  const sites = useAppStore((s) => s.sites);
  const batchResults = useAppStore((s) => s.batchResults);

  const [reportType, setReportType] = useState<"executive" | "detailed">("executive");
  const [layoutMode, setLayoutMode] = useState<ReportLayoutMode>("presentation_16_9");
  const [selectedSiteIds, setSelectedSiteIds] = useState<string[]>([]);
  const [primaryResultKeys, setPrimaryResultKeys] = useState<Record<string, string>>({});
  const [primaryColor, setPrimaryColor] = useState("#1a365d");
  const [secondaryColor, setSecondaryColor] = useState("#2b6cb0");
  const [fontFamily, setFontFamily] = useState("Inter, sans-serif");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeFormat, setActiveFormat] = useState<"html" | "pdf" | "excel" | null>(null);

  const studiedSiteOptions = buildStudiedSiteOptions(sites, batchResults);
  const orderedSelectedSiteIds = studiedSiteOptions
    .map((option) => option.siteId)
    .filter((siteId) => selectedSiteIds.includes(siteId));
  const selectedPrimaryCount = orderedSelectedSiteIds.filter((siteId) => Boolean(primaryResultKeys[siteId])).length;
  const missingPrimarySelectionCount = orderedSelectedSiteIds.length - selectedPrimaryCount;
  const canExport = orderedSelectedSiteIds.length > 0 && missingPrimarySelectionCount === 0;

  useEffect(() => {
    const options = buildStudiedSiteOptions(sites, batchResults);
    const optionMap = new Map(options.map((option) => [option.siteId, option]));

    setSelectedSiteIds((current) => current.filter((siteId) => optionMap.has(siteId)));
    setPrimaryResultKeys((current) => {
      const next: Record<string, string> = {};
      for (const [siteId, currentKey] of Object.entries(current)) {
        const option = optionMap.get(siteId);
        if (!option || option.results.length === 0) {
          continue;
        }
        const availableKeys = option.results.map(buildResultSelectionKey);
        next[siteId] = availableKeys.includes(currentKey) ? currentKey : availableKeys[0];
      }
      return next;
    });
  }, [batchResults, sites]);

  function buildConfig(): ReportConfig {
    const selectedPrimaryResultKeys = Object.fromEntries(
      orderedSelectedSiteIds
        .map((siteId) => [siteId, primaryResultKeys[siteId]] as const)
        .filter((entry): entry is [string, string] => Boolean(entry[1]))
    );
    const resultsBySelectionKey = new Map(
      batchResults.map((result) => [buildResultSelectionKey(result), result] as const)
    );
    const loadMixState = loadSessionState(LOAD_MIX_STATE_KEY, DEFAULT_LOAD_MIX_STATE);
    const greenEnergyState = loadSessionState(
      GREEN_ENERGY_STATE_KEY,
      DEFAULT_GREEN_ENERGY_STATE
    );
    const loadMixResults: ReportConfig["load_mix_results"] = {};
    const greenEnergyResults: ReportConfig["green_energy_results"] = {};

    if (loadMixState.result && loadMixState.resultSelectionKey) {
      const matchedResult = resultsBySelectionKey.get(loadMixState.resultSelectionKey);
      if (
        matchedResult &&
        selectedPrimaryResultKeys[matchedResult.site_id] === loadMixState.resultSelectionKey
      ) {
        loadMixResults[matchedResult.site_id] = {
          result_key: loadMixState.resultSelectionKey,
          result: loadMixState.result,
        };
      }
    }

    if (greenEnergyState.result && greenEnergyState.resultSelectionKey) {
      const matchedResult = resultsBySelectionKey.get(greenEnergyState.resultSelectionKey);
      if (
        matchedResult &&
        selectedPrimaryResultKeys[matchedResult.site_id] === greenEnergyState.resultSelectionKey
      ) {
        greenEnergyResults[matchedResult.site_id] = {
          result_key: greenEnergyState.resultSelectionKey,
          result: greenEnergyState.result,
          pv_profile_name: greenEnergyState.pvProfileName,
          pvgis_profile: greenEnergyState.pvgisProfile
            ? toReportPVGISProfile(greenEnergyState.pvgisProfile)
            : undefined,
          bess_initial_soc_kwh: Number.parseFloat(greenEnergyState.bessInitialSocKwh),
          grid_co2_kg_per_kwh: Number.parseFloat(greenEnergyState.co2Factor),
        };
      }
    }

    return {
      report_type: reportType,
      studied_site_ids: orderedSelectedSiteIds,
      primary_result_keys: selectedPrimaryResultKeys,
      scenario_results: batchResults,
      load_mix_results: Object.keys(loadMixResults).length > 0 ? loadMixResults : undefined,
      green_energy_results: (
        Object.keys(greenEnergyResults).length > 0 ? greenEnergyResults : undefined
      ),
      layout_mode: layoutMode,
      primary_color: primaryColor,
      secondary_color: secondaryColor,
      font_family: fontFamily,
    };
  }

  function handleToggleStudiedSite(option: StudiedSiteOption, isSelected: boolean) {
    if (isSelected) {
      setSelectedSiteIds((current) => current.filter((siteId) => siteId !== option.siteId));
      setPrimaryResultKeys((current) => {
        const next = { ...current };
        delete next[option.siteId];
        return next;
      });
      return;
    }

    setSelectedSiteIds((current) => (
      current.includes(option.siteId) ? current : [...current, option.siteId]
    ));
    setPrimaryResultKeys((current) => ({
      ...current,
      [option.siteId]: current[option.siteId] ?? buildResultSelectionKey(option.results[0]),
    }));
  }

  function handlePrimaryResultChange(siteId: string, resultKey: string) {
    setPrimaryResultKeys((current) => ({
      ...current,
      [siteId]: resultKey,
    }));
  }

  async function handlePreviewHtml() {
    if (!canExport) return;
    setError(null);
    setStatus("Generating HTML preview...");
    setActiveFormat("html");
    try {
      const html = await api.exportHtmlReport(buildConfig());
      const blob = new Blob([html], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setStatus("HTML preview opened in a new tab.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate HTML preview");
      setStatus(null);
    } finally {
      setActiveFormat(null);
    }
  }

  async function handleDownload(format: "pdf" | "excel") {
    if (!canExport) return;
    setError(null);
    setStatus(`Generating ${format.toUpperCase()} report...`);
    setActiveFormat(format);
    try {
      const blob = format === "pdf"
        ? await api.exportPdfReport(buildConfig())
        : await api.exportExcelReport(buildConfig());
      const extension = format === "pdf" ? "pdf" : "xlsx";
      downloadBlob(
        blob,
        `dc-feasibility-${reportType}-${layoutMode}-report.${extension}`
      );
      setStatus(`${format.toUpperCase()} download started.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to export ${format.toUpperCase()}`);
      setStatus(null);
    } finally {
      setActiveFormat(null);
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Reports & Export</h2>
        <p className="text-sm text-gray-500 mt-1">
          Generate HTML, PDF, and Excel outputs for the studied sites and primary scenarios you select below.
        </p>
      </div>

      <div className="mb-6 p-4 bg-sky-50 border border-sky-200 rounded-xl flex items-start gap-3">
        <AlertCircle size={20} className="text-sky-600 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-medium text-sky-900">Milestone 1 export scope is now explicit</p>
          <p className="text-xs text-sky-800 mt-1">
            Reports no longer export all saved sites by default. Select the studied sites you want,
            then choose one primary scenario/result for each selected site from the current batch results.
          </p>
        </div>
      </div>

      <div className="space-y-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h3 className="font-semibold text-gray-800">Study Scope</h3>
              <p className="text-xs text-gray-500 mt-1">
                Only sites present in the current batch results can be selected in Milestone 1.
              </p>
            </div>
            <div className="text-right text-xs text-gray-500">
              <p>{orderedSelectedSiteIds.length} studied site{orderedSelectedSiteIds.length !== 1 ? "s" : ""} selected</p>
              <p>{selectedPrimaryCount} primary result{selectedPrimaryCount !== 1 ? "s" : ""} ready</p>
            </div>
          </div>

          {studiedSiteOptions.length === 0 ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              Run a scenario batch first so you can choose the studied sites and primary scenarios for export.
            </div>
          ) : (
            <div className="space-y-3">
              {studiedSiteOptions.map((option) => {
                const isSelected = selectedSiteIds.includes(option.siteId);
                const selectedResultKey = primaryResultKeys[option.siteId] ?? buildResultSelectionKey(option.results[0]);

                return (
                  <div
                    key={option.siteId}
                    className={`rounded-xl border p-4 transition-colors ${
                      isSelected
                        ? "border-blue-500 bg-blue-50"
                        : "border-gray-200 bg-white"
                    }`}
                  >
                    <label className="flex items-start gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => handleToggleStudiedSite(option, isSelected)}
                        className="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                      <div className="flex-1">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="font-medium text-gray-900">{option.siteName}</p>
                            <p className="text-xs text-gray-500 mt-1">
                              {option.locationLabel} | {option.results.length} result
                              {option.results.length !== 1 ? "s" : ""} in the current batch
                            </p>
                          </div>
                          <p className="text-xs text-gray-500">
                            {option.availablePowerMw !== null
                              ? `${option.availablePowerMw.toFixed(1)} MW available power`
                              : "Saved power details unavailable"}
                          </p>
                        </div>
                      </div>
                    </label>

                    {isSelected && (
                      <div className="mt-4 pl-7">
                        <label className="block text-xs font-medium text-gray-600 mb-1">
                          Primary scenario/result for this studied site
                        </label>
                        <select
                          value={selectedResultKey}
                          onChange={(e) => handlePrimaryResultChange(option.siteId, e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none"
                        >
                          {option.results.map((result) => {
                            const resultKey = buildResultSelectionKey(result);
                            return (
                              <option key={`${option.siteId}-${resultKey}`} value={resultKey}>
                                {describeScenarioChoice(result)}
                              </option>
                            );
                          })}
                        </select>
                        <p className="text-xs text-gray-500 mt-2">
                          Milestone 1 exports only this selected primary result for the site. Full multi-scenario
                          report design remains in later milestones.
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="font-semibold text-gray-800 mb-4">Report Template</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label
              className={`p-4 rounded-lg border-2 cursor-pointer transition-colors ${
                reportType === "executive"
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200 hover:bg-gray-50"
              }`}
            >
              <input
                type="radio"
                name="reportType"
                value="executive"
                checked={reportType === "executive"}
                onChange={() => setReportType("executive")}
                className="sr-only"
              />
              <p className="font-medium text-gray-900">Executive Summary</p>
              <p className="text-xs text-gray-500 mt-1">
                Focused view for management: selected studied sites, chosen primary scenarios, and high-level feasibility signals.
              </p>
            </label>
            <label
              className={`p-4 rounded-lg border-2 cursor-pointer transition-colors ${
                reportType === "detailed"
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200 hover:bg-gray-50"
              }`}
            >
              <input
                type="radio"
                name="reportType"
                value="detailed"
                checked={reportType === "detailed"}
                onChange={() => setReportType("detailed")}
                className="sr-only"
              />
              <p className="font-medium text-gray-900">Detailed Technical</p>
              <p className="text-xs text-gray-500 mt-1">
                Includes the selected studied sites plus the chosen primary scenario/result for each site.
              </p>
            </label>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="font-semibold text-gray-800 mb-4">Layout Mode</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {LAYOUT_OPTIONS.map((option) => (
              <label
                key={option.value}
                className={`p-4 rounded-lg border-2 cursor-pointer transition-colors ${
                  layoutMode === option.value
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-200 hover:bg-gray-50"
                }`}
              >
                <input
                  type="radio"
                  name="layoutMode"
                  value={option.value}
                  checked={layoutMode === option.value}
                  onChange={() => setLayoutMode(option.value)}
                  className="sr-only"
                />
                <p className="font-medium text-gray-900">{option.label}</p>
                <p className="text-xs text-gray-500 mt-1">{option.description}</p>
              </label>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="font-semibold text-gray-800 mb-4">Theme & Branding</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Primary Color
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  className="w-8 h-8 rounded border border-gray-300 cursor-pointer"
                />
                <input
                  type="text"
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-sm font-mono"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Secondary Color
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={secondaryColor}
                  onChange={(e) => setSecondaryColor(e.target.value)}
                  className="w-8 h-8 rounded border border-gray-300 cursor-pointer"
                />
                <input
                  type="text"
                  value={secondaryColor}
                  onChange={(e) => setSecondaryColor(e.target.value)}
                  className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-sm font-mono"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Font Family
              </label>
              <input
                type="text"
                value={fontFamily}
                onChange={(e) => setFontFamily(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
              />
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="font-semibold text-gray-800 mb-3">Data Available</h3>
          <div className="text-sm text-gray-600 space-y-1">
            <p>{sites.length} saved site{sites.length !== 1 ? "s" : ""}</p>
            <p>{studiedSiteOptions.length} studied-site candidate{studiedSiteOptions.length !== 1 ? "s" : ""} from the current batch</p>
            <p>{batchResults.length} scenario result{batchResults.length !== 1 ? "s" : ""} in the current batch</p>
            <p className="text-xs text-gray-500">
              Export now stays scoped to the studied sites and primary results you select here.
            </p>
          </div>
        </div>

        {(status || error) && (
          <div className={`rounded-xl border p-4 text-sm ${error ? "border-rose-200 bg-rose-50 text-rose-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
            {error ?? status}
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          <button
            onClick={handlePreviewHtml}
            disabled={!canExport || activeFormat !== null}
            className="flex items-center gap-2 px-5 py-2.5 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {activeFormat === "html" ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
            Preview HTML
          </button>
          <button
            onClick={() => handleDownload("pdf")}
            disabled={!canExport || activeFormat !== null}
            className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {activeFormat === "pdf" ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
            Download PDF
          </button>
          <button
            onClick={() => handleDownload("excel")}
            disabled={!canExport || activeFormat !== null}
            className="flex items-center gap-2 px-5 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {activeFormat === "excel" ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
            Download Excel
          </button>
        </div>

        {!sites.length && (
          <p className="text-sm text-amber-700">
            Save at least one site, run a scenario batch, then select the studied sites you want to export.
          </p>
        )}

        {sites.length > 0 && studiedSiteOptions.length === 0 && (
          <p className="text-sm text-amber-700">
            Run a scenario batch before generating a report so you can select studied sites and primary results.
          </p>
        )}

        {studiedSiteOptions.length > 0 && orderedSelectedSiteIds.length === 0 && (
          <p className="text-sm text-amber-700">
            Select at least one studied site to enable export.
          </p>
        )}

        {orderedSelectedSiteIds.length > 0 && missingPrimarySelectionCount > 0 && (
          <p className="text-sm text-amber-700">
            Choose a primary scenario/result for each selected studied site before exporting.
          </p>
        )}
      </div>
    </div>
  );
}
