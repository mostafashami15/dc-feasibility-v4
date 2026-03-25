import { useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Download,
  Eye,
  FileText,
  Loader2,
  Table2,
} from "lucide-react";
import * as api from "../api/client";
import { loadSessionState } from "../lib/sessionState";
import { useAppStore } from "../store/useAppStore";
import type {
  LoadMixResult,
  PVGISProfileResult,
  ReportConfig,
  ReportLayoutMode,
  ReportPVGISProfile,
  ScenarioGreenDispatchResult,
  ScenarioResult,
  SiteResponse,
} from "../types";

// ── Session state keys ───────────────────────────────────────────────────────
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
const DEFAULT_LOAD_MIX_STATE: LoadMixSessionState = { result: null, resultSelectionKey: null };
const DEFAULT_GREEN_ENERGY_STATE: GreenEnergySessionState = {
  bessInitialSocKwh: "0",
  co2Factor: "0.256",
  pvProfileName: null,
  pvgisProfile: null,
  result: null,
  resultSelectionKey: null,
};

// ── Types ───────────────────────────────────────────────────────────────────
type StudiedSiteOption = {
  siteId: string;
  siteName: string;
  locationLabel: string;
  availablePowerMw: number | null;
  results: ScenarioResult[];
};

// ── Helpers ──────────────────────────────────────────────────────────────────

type SaveTarget =
  | { kind: "file-system"; handle: any; filename: string }
  | { kind: "download"; filename: string };

/** Prompt for a destination while the click gesture is still active. */
async function promptSaveTarget(defaultFilename: string): Promise<SaveTarget | null> {
  if ("showSaveFilePicker" in window) {
    try {
      const ext = defaultFilename.split(".").pop() || "pdf";
      const mimeMap: Record<string, string> = {
        pdf: "application/pdf",
        xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      };
      const handle = await (window as any).showSaveFilePicker({
        suggestedName: defaultFilename,
        types: [
          {
            description: `${ext.toUpperCase()} file`,
            accept: { [mimeMap[ext] ?? "application/octet-stream"]: [`.${ext}`] },
          },
        ],
      });
      return { kind: "file-system", handle, filename: defaultFilename };
    } catch (err: any) {
      if (err?.name === "AbortError") return null; // user cancelled
      // fall through to legacy download
    }
  }
  return { kind: "download", filename: defaultFilename };
}

/** Persist the generated file to the chosen destination. */
async function saveOrDownloadBlob(blob: Blob, target: SaveTarget) {
  if (target.kind === "file-system") {
    const writable = await target.handle.createWritable();
    await writable.write(blob);
    await writable.close();
    return;
  }

  // Fallback: programmatic <a> download
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = target.filename;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function buildExportFilename(
  siteOptions: StudiedSiteOption[],
  selectedIds: string[],
  reportType: string,
  extension: string,
): string {
  const siteNames = selectedIds
    .map((id) => siteOptions.find((o) => o.siteId === id)?.siteName)
    .filter(Boolean)
    .map((name) => name!.replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, ""));
  const sitePart = siteNames.length > 0 ? siteNames.join("-") : "report";
  return `${sitePart}-dc-feasibility-${reportType}-report.${extension}`;
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
  if (!site) return "Location unavailable";
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
    if (current) current.push(result);
    else resultsBySite.set(result.site_id, [result]);
  }
  const options: StudiedSiteOption[] = [];
  const seenIds = new Set<string>();
  for (const siteEntry of sites) {
    const siteResults = resultsBySite.get(siteEntry.id);
    if (!siteResults || siteResults.length === 0) continue;
    options.push({
      siteId: siteEntry.id,
      siteName: siteEntry.site.name,
      locationLabel: formatLocationLabel(siteEntry.site),
      availablePowerMw: siteEntry.site.available_power_mw,
      results: siteResults,
    });
    seenIds.add(siteEntry.id);
  }
  for (const [siteId, siteResults] of resultsBySite.entries()) {
    if (seenIds.has(siteId) || siteResults.length === 0) continue;
    options.push({
      siteId,
      siteName: siteResults[0].site_name,
      locationLabel: "Location unavailable",
      availablePowerMw: null,
      results: siteResults,
    });
  }
  return options;
}

// ── Reusable UI pieces ──────────────────────────────────────────────────────
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
      {children}
    </h3>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white rounded-xl border border-gray-200 shadow-sm p-5 ${className}`}>
      {children}
    </div>
  );
}

function ToggleButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
        active
          ? "bg-blue-600 text-white shadow-sm"
          : "bg-gray-50 text-gray-600 hover:bg-gray-100 border border-gray-200"
      }`}
    >
      {children}
    </button>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
export default function Export() {
  const sites = useAppStore((s) => s.sites);
  const batchResults = useAppStore((s) => s.batchResults);

  // Core state
  const [selectedSiteIds, setSelectedSiteIds] = useState<string[]>([]);
  const [primaryResultKeys, setPrimaryResultKeys] = useState<Record<string, string>>({});
  const [reportType, setReportType] = useState<"executive" | "detailed">("executive");

  // Advanced state (hidden by default)
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [layoutMode, setLayoutMode] = useState<ReportLayoutMode>("presentation_16_9");
  const [includeAllScenarios, setIncludeAllScenarios] = useState(true);
  const [primaryColor, setPrimaryColor] = useState("#0A2240");
  const [secondaryColor, setSecondaryColor] = useState("#795AFD");
  const [fontFamily, setFontFamily] = useState("'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif");
  const [logoUrl, setLogoUrl] = useState("");

  // Export state
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeFormat, setActiveFormat] = useState<"html" | "pdf" | "excel" | null>(null);

  const studiedSiteOptions = buildStudiedSiteOptions(sites, batchResults);
  const orderedSelectedSiteIds = studiedSiteOptions
    .map((o) => o.siteId)
    .filter((id) => selectedSiteIds.includes(id));
  const selectedPrimaryCount = orderedSelectedSiteIds.filter(
    (id) => Boolean(primaryResultKeys[id])
  ).length;
  const missingPrimaryCount = orderedSelectedSiteIds.length - selectedPrimaryCount;
  const canExport = orderedSelectedSiteIds.length > 0 && missingPrimaryCount === 0;

  // Sync selections with batch results
  useEffect(() => {
    const optionMap = new Map(studiedSiteOptions.map((o) => [o.siteId, o]));
    setSelectedSiteIds((cur) => cur.filter((id) => optionMap.has(id)));
    setPrimaryResultKeys((cur) => {
      const next: Record<string, string> = {};
      for (const [siteId, curKey] of Object.entries(cur)) {
        const option = optionMap.get(siteId);
        if (!option || option.results.length === 0) continue;
        const keys = option.results.map(buildResultSelectionKey);
        next[siteId] = keys.includes(curKey) ? curKey : keys[0];
      }
      return next;
    });
  }, [batchResults, sites]);

  function buildConfig(): ReportConfig {
    const selectedKeys = Object.fromEntries(
      orderedSelectedSiteIds
        .map((id) => [id, primaryResultKeys[id]] as const)
        .filter((e): e is [string, string] => Boolean(e[1]))
    );
    const bySelectionKey = new Map(
      batchResults.map((r) => [buildResultSelectionKey(r), r] as const)
    );
    const loadMixState = loadSessionState(LOAD_MIX_STATE_KEY, DEFAULT_LOAD_MIX_STATE);
    const greenState = loadSessionState(GREEN_ENERGY_STATE_KEY, DEFAULT_GREEN_ENERGY_STATE);
    const loadMixResults: ReportConfig["load_mix_results"] = {};
    const greenEnergyResults: ReportConfig["green_energy_results"] = {};

    if (loadMixState.result && loadMixState.resultSelectionKey) {
      const matched = bySelectionKey.get(loadMixState.resultSelectionKey);
      if (matched && selectedKeys[matched.site_id] === loadMixState.resultSelectionKey) {
        loadMixResults[matched.site_id] = {
          result_key: loadMixState.resultSelectionKey,
          result: loadMixState.result,
        };
      }
    }
    if (greenState.result && greenState.resultSelectionKey) {
      const matched = bySelectionKey.get(greenState.resultSelectionKey);
      if (matched && selectedKeys[matched.site_id] === greenState.resultSelectionKey) {
        greenEnergyResults[matched.site_id] = {
          result_key: greenState.resultSelectionKey,
          result: greenState.result,
          pv_profile_name: greenState.pvProfileName,
          pvgis_profile: greenState.pvgisProfile
            ? toReportPVGISProfile(greenState.pvgisProfile)
            : undefined,
          bess_initial_soc_kwh: Number.parseFloat(greenState.bessInitialSocKwh),
          grid_co2_kg_per_kwh: Number.parseFloat(greenState.co2Factor),
        };
      }
    }

    return {
      report_type: reportType,
      studied_site_ids: orderedSelectedSiteIds,
      primary_result_keys: selectedKeys,
      scenario_results: batchResults,
      load_mix_results: Object.keys(loadMixResults).length > 0 ? loadMixResults : undefined,
      green_energy_results:
        Object.keys(greenEnergyResults).length > 0 ? greenEnergyResults : undefined,
      layout_mode: layoutMode,
      include_all_scenarios: includeAllScenarios,
      primary_color: primaryColor,
      secondary_color: secondaryColor,
      font_family: fontFamily,
      logo_url: logoUrl || undefined,
    };
  }

  function handleToggleSite(option: StudiedSiteOption, isSelected: boolean) {
    if (isSelected) {
      setSelectedSiteIds((cur) => cur.filter((id) => id !== option.siteId));
      setPrimaryResultKeys((cur) => {
        const next = { ...cur };
        delete next[option.siteId];
        return next;
      });
    } else {
      setSelectedSiteIds((cur) =>
        cur.includes(option.siteId) ? cur : [...cur, option.siteId]
      );
      setPrimaryResultKeys((cur) => ({
        ...cur,
        [option.siteId]: cur[option.siteId] ?? buildResultSelectionKey(option.results[0]),
      }));
    }
  }

  async function handlePreviewHtml() {
    if (!canExport) return;
    setError(null);
    setStatus("Generating HTML preview…");
    setActiveFormat("html");
    try {
      const html = await api.exportHtmlReport(buildConfig());
      const blob = new Blob([html], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setStatus("HTML preview opened in a new tab.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate HTML preview.");
      setStatus(null);
    } finally {
      setActiveFormat(null);
    }
  }

  async function handleDownloadPdf() {
    if (!canExport) return;
    const filename = buildExportFilename(studiedSiteOptions, orderedSelectedSiteIds, reportType, "pdf");
    const target = await promptSaveTarget(filename);
    if (!target) {
      setError(null);
      setStatus(null);
      return;
    }
    setError(null);
    setStatus("Generating PDF — this may take a moment…");
    setActiveFormat("pdf");
    try {
      const blob = await api.exportPdfReport(buildConfig());
      await saveOrDownloadBlob(blob, target);
      setStatus(target.kind === "file-system" ? "PDF saved." : "PDF download started.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate PDF report.");
      setStatus(null);
    } finally {
      setActiveFormat(null);
    }
  }

  async function handleDownloadExcel() {
    if (!canExport) return;
    const filename = buildExportFilename(studiedSiteOptions, orderedSelectedSiteIds, reportType, "xlsx");
    const target = await promptSaveTarget(filename);
    if (!target) {
      setError(null);
      setStatus(null);
      return;
    }
    setError(null);
    setStatus("Generating Excel…");
    setActiveFormat("excel");
    try {
      const blob = await api.exportExcelReport(buildConfig());
      await saveOrDownloadBlob(blob, target);
      setStatus(target.kind === "file-system" ? "Excel saved." : "Excel download started.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to export Excel.");
      setStatus(null);
    } finally {
      setActiveFormat(null);
    }
  }

  // ── Empty state ─────────────────────────────────────────────────────────
  if (studiedSiteOptions.length === 0) {
    return (
      <div className="max-w-2xl mx-auto py-12 text-center">
        <div className="w-14 h-14 rounded-full bg-amber-50 border border-amber-200 flex items-center justify-center mx-auto mb-4">
          <FileText size={24} className="text-amber-500" />
        </div>
        <h2 className="text-xl font-bold text-gray-800 mb-2">No results to export</h2>
        <p className="text-sm text-gray-500">
          Run a scenario batch first. Once you have results, come back here to configure and
          download your feasibility report.
        </p>
      </div>
    );
  }

  // ── Main render ────────────────────────────────────────────────────────
  return (
    <div className="max-w-3xl mx-auto">
      {/* Page header */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Reports &amp; Export</h2>
        <p className="text-sm text-gray-500 mt-1">
          Select your sites, choose a report type, and export.
        </p>
      </div>

      {/* ── 1. SELECT SITES ─────────────────────────────────────────────── */}
      <Card className="mb-4">
        <div className="flex items-start justify-between mb-4">
          <SectionTitle>Select Sites</SectionTitle>
          <span className="text-xs text-gray-400 shrink-0">
            {orderedSelectedSiteIds.length} site{orderedSelectedSiteIds.length !== 1 ? "s" : ""} selected
          </span>
        </div>

        <div className="space-y-3">
          {studiedSiteOptions.map((option) => {
            const isSelected = selectedSiteIds.includes(option.siteId);
            const resultKey =
              primaryResultKeys[option.siteId] ??
              buildResultSelectionKey(option.results[0]);
            return (
              <div
                key={option.siteId}
                className={`rounded-xl border-2 p-4 transition-colors ${
                  isSelected
                    ? "border-blue-400 bg-blue-50"
                    : "border-gray-200 bg-white hover:border-gray-300"
                }`}
              >
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => handleToggleSite(option, isSelected)}
                    className="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="font-semibold text-gray-900 text-sm">{option.siteName}</p>
                        <p className="text-xs text-gray-500 mt-0.5">{option.locationLabel}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-xs font-medium text-gray-600">
                          {option.availablePowerMw !== null
                            ? `${option.availablePowerMw.toFixed(1)} MW available`
                            : "Power TBC"}
                        </p>
                        <p className="text-xs text-gray-400">
                          {option.results.length} scenario{option.results.length !== 1 ? "s" : ""}
                        </p>
                      </div>
                    </div>
                  </div>
                </label>

                {isSelected && (
                  <div className="mt-3 pl-7">
                    <label className="block text-xs font-medium text-gray-600 mb-1.5">
                      Primary scenario
                    </label>
                    <select
                      value={resultKey}
                      onChange={(e) =>
                        setPrimaryResultKeys((cur) => ({
                          ...cur,
                          [option.siteId]: e.target.value,
                        }))
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs bg-white focus:ring-2 focus:ring-blue-500 outline-none"
                    >
                      {option.results.map((r) => {
                        const key = buildResultSelectionKey(r);
                        return (
                          <option key={key} value={key}>
                            {describeScenarioChoice(r)}
                          </option>
                        );
                      })}
                    </select>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {orderedSelectedSiteIds.length > 0 && missingPrimaryCount > 0 && (
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2 mt-3">
            Select a primary scenario for each chosen site to continue.
          </p>
        )}
      </Card>

      {/* ── 2. REPORT TYPE ─────────────────────────────────────────────── */}
      <Card className="mb-4">
        <SectionTitle>Report Type</SectionTitle>
        <div className="flex gap-2">
          <ToggleButton active={reportType === "executive"} onClick={() => setReportType("executive")}>
            Executive Summary
          </ToggleButton>
          <ToggleButton active={reportType === "detailed"} onClick={() => setReportType("detailed")}>
            Detailed Technical
          </ToggleButton>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          {reportType === "executive"
            ? "Concise view for leadership — key feasibility signals, site map, headline metrics."
            : "Full report with all chapters: grid, climate, scenario deep-dive, advanced analysis."}
        </p>
      </Card>

      {/* ── 3. EXPORT ──────────────────────────────────────────────────── */}
      {(status || error) && (
        <div
          className={`rounded-xl border px-4 py-3 text-sm mb-4 ${
            error
              ? "border-rose-200 bg-rose-50 text-rose-700"
              : "border-emerald-200 bg-emerald-50 text-emerald-700"
          }`}
        >
          {error ?? status}
        </div>
      )}

      <Card className="mb-4">
        <SectionTitle>Export</SectionTitle>

        {/* Primary action */}
        <button
          onClick={handleDownloadPdf}
          disabled={!canExport || activeFormat !== null}
          className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-blue-600 text-white rounded-xl hover:bg-blue-700 text-base font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-colors mb-4"
        >
          {activeFormat === "pdf" ? (
            <Loader2 size={20} className="animate-spin" />
          ) : (
            <Download size={20} />
          )}
          Download PDF
        </button>

        {/* Secondary actions */}
        <div className="flex gap-3">
          <button
            onClick={handlePreviewHtml}
            disabled={!canExport || activeFormat !== null}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-gray-200 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {activeFormat === "html" ? (
              <Loader2 size={16} className="animate-spin text-blue-500" />
            ) : (
              <Eye size={16} className="text-gray-400" />
            )}
            Preview in Browser
          </button>
          <button
            onClick={handleDownloadExcel}
            disabled={!canExport || activeFormat !== null}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-gray-200 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {activeFormat === "excel" ? (
              <Loader2 size={16} className="animate-spin text-green-500" />
            ) : (
              <Table2 size={16} className="text-gray-400" />
            )}
            Download Excel
          </button>
        </div>
      </Card>

      {/* ── ADVANCED SETTINGS (collapsed by default) ───────────────────── */}
      <button
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 font-medium mb-2 transition-colors"
      >
        {showAdvanced ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        Advanced Settings
      </button>

      {showAdvanced && (
        <Card>
          {/* Layout mode */}
          <div className="mb-5">
            <label className="block text-xs font-medium text-gray-600 mb-2">Layout Mode</label>
            <div className="flex gap-2">
              <ToggleButton
                active={layoutMode === "presentation_16_9"}
                onClick={() => setLayoutMode("presentation_16_9")}
              >
                Presentation (Landscape)
              </ToggleButton>
              <ToggleButton
                active={layoutMode === "report_a4_portrait"}
                onClick={() => setLayoutMode("report_a4_portrait")}
              >
                A4 Portrait
              </ToggleButton>
            </div>
          </div>

          {/* Scenario scope */}
          <div className="mb-5">
            <label className="block text-xs font-medium text-gray-600 mb-2">Scenario Scope</label>
            <div className="flex gap-2">
              <ToggleButton
                active={includeAllScenarios}
                onClick={() => setIncludeAllScenarios(true)}
              >
                All Scenarios
              </ToggleButton>
              <ToggleButton
                active={!includeAllScenarios}
                onClick={() => setIncludeAllScenarios(false)}
              >
                Primary Only
              </ToggleButton>
            </div>
            <p className="text-xs text-gray-400 mt-1.5">
              {includeAllScenarios
                ? "Shows a ranked comparison table of all scenarios per site."
                : "Only the selected primary scenario per site — focused view."}
            </p>
          </div>

          {/* Theme */}
          <label className="block text-xs font-medium text-gray-600 mb-2">Theme &amp; Branding</label>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Primary Color</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  className="w-8 h-8 rounded-md border border-gray-300 cursor-pointer"
                />
                <input
                  type="text"
                  value={primaryColor}
                  onChange={(e) => setPrimaryColor(e.target.value)}
                  className="flex-1 px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Secondary Color</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={secondaryColor}
                  onChange={(e) => setSecondaryColor(e.target.value)}
                  className="w-8 h-8 rounded-md border border-gray-300 cursor-pointer"
                />
                <input
                  type="text"
                  value={secondaryColor}
                  onChange={(e) => setSecondaryColor(e.target.value)}
                  className="flex-1 px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Font Family</label>
              <input
                type="text"
                value={fontFamily}
                onChange={(e) => setFontFamily(e.target.value)}
                className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                placeholder="Inter, sans-serif"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">
                Logo URL <span className="text-gray-400">(optional)</span>
              </label>
              <input
                type="url"
                value={logoUrl}
                onChange={(e) => setLogoUrl(e.target.value)}
                className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                placeholder="https://example.com/logo.png"
              />
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
