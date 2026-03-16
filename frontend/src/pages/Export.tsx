import { useEffect, useState } from "react";
import {
  CheckCircle,
  ChevronRight,
  Download,
  Eye,
  FileText,
  Loader2,
  Settings,
  Sliders,
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

type WizardStep = 1 | 2 | 3;

// ── Helpers ──────────────────────────────────────────────────────────────────
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
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

// ── Wizard step header ───────────────────────────────────────────────────────
function StepHeader({
  step,
  activeStep,
  label,
  icon,
}: {
  step: WizardStep;
  activeStep: WizardStep;
  label: string;
  icon: React.ReactNode;
}) {
  const done = step < activeStep;
  const active = step === activeStep;
  return (
    <div
      className={`flex items-center gap-2.5 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
        active
          ? "bg-blue-600 text-white"
          : done
          ? "bg-green-50 text-green-700 border border-green-200"
          : "text-gray-400 bg-gray-50 border border-gray-200"
      }`}
    >
      {done ? (
        <CheckCircle size={16} className="shrink-0" />
      ) : (
        <span
          className={`flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold ${
            active ? "bg-white text-blue-600" : "bg-gray-200 text-gray-500"
          }`}
        >
          {step}
        </span>
      )}
      {icon}
      <span>{label}</span>
    </div>
  );
}

// ── Section title ────────────────────────────────────────────────────────────
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
      {children}
    </h3>
  );
}

// ── Card ─────────────────────────────────────────────────────────────────────
function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white rounded-xl border border-gray-200 shadow-sm p-5 ${className}`}>
      {children}
    </div>
  );
}

// ── Layout option card ───────────────────────────────────────────────────────
function OptionCard<T extends string>({
  value,
  selected,
  onSelect,
  title,
  description,
}: {
  value: T;
  selected: T;
  onSelect: (v: T) => void;
  title: string;
  description: string;
}) {
  const isSelected = value === selected;
  return (
    <label
      className={`block p-4 rounded-xl border-2 cursor-pointer transition-all select-none ${
        isSelected
          ? "border-blue-500 bg-blue-50"
          : "border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50"
      }`}
    >
      <input
        type="radio"
        name={`option-${title}`}
        value={value}
        checked={isSelected}
        onChange={() => onSelect(value)}
        className="sr-only"
      />
      <div className="flex items-start gap-2">
        <span
          className={`mt-0.5 w-4 h-4 rounded-full border-2 flex-shrink-0 flex items-center justify-center ${
            isSelected ? "border-blue-500 bg-blue-500" : "border-gray-300"
          }`}
        >
          {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-white" />}
        </span>
        <div>
          <p className={`font-medium text-sm ${isSelected ? "text-blue-900" : "text-gray-800"}`}>
            {title}
          </p>
          <p className="text-xs text-gray-500 mt-0.5">{description}</p>
        </div>
      </div>
    </label>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
export default function Export() {
  const sites = useAppStore((s) => s.sites);
  const batchResults = useAppStore((s) => s.batchResults);

  // Wizard state
  const [step, setStep] = useState<WizardStep>(1);

  // Step 1: Scope
  const [selectedSiteIds, setSelectedSiteIds] = useState<string[]>([]);
  const [primaryResultKeys, setPrimaryResultKeys] = useState<Record<string, string>>({});

  // Step 2: Options
  const [reportType, setReportType] = useState<"executive" | "detailed">("executive");
  const [layoutMode, setLayoutMode] = useState<ReportLayoutMode>("presentation_16_9");
  const [includeAllScenarios, setIncludeAllScenarios] = useState(true);
  const [primaryColor, setPrimaryColor] = useState("#1a365d");
  const [secondaryColor, setSecondaryColor] = useState("#2b6cb0");
  const [fontFamily, setFontFamily] = useState("Inter, sans-serif");
  const [logoUrl, setLogoUrl] = useState("");

  // Step 3: Export
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
  const step1Complete = orderedSelectedSiteIds.length > 0 && missingPrimaryCount === 0;
  const canExport = step1Complete;

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

  async function handleDownload(format: "pdf" | "excel") {
    if (!canExport) return;
    setError(null);
    setStatus(`Generating ${format.toUpperCase()}…`);
    setActiveFormat(format);
    try {
      const blob =
        format === "pdf"
          ? await api.exportPdfReport(buildConfig())
          : await api.exportExcelReport(buildConfig());
      const ext = format === "pdf" ? "pdf" : "xlsx";
      downloadBlob(blob, `dc-feasibility-${reportType}-report.${ext}`);
      setStatus(`${format.toUpperCase()} download started.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to export ${format.toUpperCase()}.`);
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

  // ── Wizard progress bar ─────────────────────────────────────────────────
  const progressSteps: { step: WizardStep; label: string; icon: React.ReactNode }[] = [
    { step: 1, label: "Study Scope", icon: <Sliders size={14} /> },
    { step: 2, label: "Report Options", icon: <Settings size={14} /> },
    { step: 3, label: "Export", icon: <Download size={14} /> },
  ];

  return (
    <div className="max-w-3xl mx-auto">
      {/* ── Page header ─────────────────────────────────────────────────── */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Reports &amp; Export</h2>
        <p className="text-sm text-gray-500 mt-1">
          Configure your report, select sites and scenarios, then download in HTML, PDF, or Excel.
        </p>
      </div>

      {/* ── Step navigation ─────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 mb-6">
        {progressSteps.map(({ step: s, label, icon }, i) => (
          <div key={s} className="flex items-center gap-2">
            <button
              onClick={() => {
                if (s < step || (s === 2 && step1Complete) || s === step) setStep(s);
              }}
              className="focus:outline-none"
            >
              <StepHeader step={s} activeStep={step} label={label} icon={icon} />
            </button>
            {i < progressSteps.length - 1 && (
              <ChevronRight size={14} className="text-gray-300 shrink-0" />
            )}
          </div>
        ))}
      </div>

      {/* ══════════════════════════════════════════════════════════════════
          STEP 1: STUDY SCOPE
         ══════════════════════════════════════════════════════════════════ */}
      {step === 1 && (
        <div className="space-y-4">
          <Card>
            <div className="flex items-start justify-between mb-4">
              <div>
                <SectionTitle>Select Studied Sites</SectionTitle>
                <p className="text-xs text-gray-500 -mt-2">
                  Choose which sites and primary scenarios to include in the report.
                </p>
              </div>
              <div className="text-right text-xs text-gray-400 shrink-0">
                <div>{orderedSelectedSiteIds.length} site{orderedSelectedSiteIds.length !== 1 ? "s" : ""} selected</div>
                <div>{selectedPrimaryCount} scenario{selectedPrimaryCount !== 1 ? "s" : ""} ready</div>
              </div>
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
                              {option.results.length} result{option.results.length !== 1 ? "s" : ""}
                            </p>
                          </div>
                        </div>
                      </div>
                    </label>

                    {isSelected && (
                      <div className="mt-3 pl-7">
                        <label className="block text-xs font-medium text-gray-600 mb-1.5">
                          Primary scenario for this site
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
                        <p className="text-xs text-gray-400 mt-1">
                          This scenario will be featured as the primary result for this site.
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Validation hint */}
          {orderedSelectedSiteIds.length > 0 && missingPrimaryCount > 0 && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2">
              Select a primary scenario for each chosen site to continue.
            </p>
          )}

          <div className="flex justify-end">
            <button
              onClick={() => setStep(2)}
              disabled={!step1Complete}
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Next: Report Options
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          STEP 2: REPORT OPTIONS
         ══════════════════════════════════════════════════════════════════ */}
      {step === 2 && (
        <div className="space-y-4">
          {/* Report template */}
          <Card>
            <SectionTitle>Report Template</SectionTitle>
            <div className="grid grid-cols-2 gap-3">
              <OptionCard
                value="executive"
                selected={reportType}
                onSelect={setReportType}
                title="Executive Summary"
                description="Concise view for leadership — key feasibility signals, site map, headline metrics."
              />
              <OptionCard
                value="detailed"
                selected={reportType}
                onSelect={setReportType}
                title="Detailed Technical"
                description="Full report with all chapters: grid, climate, scenario deep-dive, advanced analysis."
              />
            </div>
          </Card>

          {/* Layout mode */}
          <Card>
            <SectionTitle>Layout Mode</SectionTitle>
            <div className="grid grid-cols-2 gap-3">
              <OptionCard
                value="presentation_16_9"
                selected={layoutMode}
                onSelect={setLayoutMode}
                title="Presentation 16:9"
                description="Slide-style pages — great for screen sharing and review meetings."
              />
              <OptionCard
                value="report_a4_portrait"
                selected={layoutMode}
                onSelect={setLayoutMode}
                title="Report A4 Portrait"
                description="Formal document format for print and distribution."
              />
            </div>
          </Card>

          {/* Scenario scope */}
          <Card>
            <SectionTitle>Scenario Scope</SectionTitle>
            <div className="grid grid-cols-2 gap-3">
              <OptionCard
                value="all"
                selected={includeAllScenarios ? "all" : "primary"}
                onSelect={() => setIncludeAllScenarios(true)}
                title="All Scenarios"
                description="Include every scenario result per site — shows a ranked comparison table in the report."
              />
              <OptionCard
                value="primary"
                selected={includeAllScenarios ? "all" : "primary"}
                onSelect={() => setIncludeAllScenarios(false)}
                title="Primary Only"
                description="Include only the selected primary scenario per site — focused, single-scenario view."
              />
            </div>
          </Card>

          {/* Theme & Branding */}
          <Card>
            <SectionTitle>Theme &amp; Branding</SectionTitle>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1.5">
                  Primary Color
                </label>
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
                <label className="block text-xs font-medium text-gray-600 mb-1.5">
                  Secondary Color
                </label>
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
                <label className="block text-xs font-medium text-gray-600 mb-1.5">
                  Font Family
                </label>
                <input
                  type="text"
                  value={fontFamily}
                  onChange={(e) => setFontFamily(e.target.value)}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                  placeholder="Inter, sans-serif"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1.5">
                  Logo URL{" "}
                  <span className="text-gray-400 font-normal">(optional)</span>
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

          <div className="flex justify-between">
            <button
              onClick={() => setStep(1)}
              className="px-5 py-2.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm font-medium transition-colors"
            >
              ← Back
            </button>
            <button
              onClick={() => setStep(3)}
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium transition-colors"
            >
              Next: Export
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          STEP 3: EXPORT
         ══════════════════════════════════════════════════════════════════ */}
      {step === 3 && (
        <div className="space-y-4">
          {/* Report summary */}
          <Card>
            <SectionTitle>Report Summary</SectionTitle>
            <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
              <div className="flex justify-between py-1.5 border-b border-gray-100">
                <span className="text-gray-500">Template</span>
                <span className="font-medium text-gray-800">
                  {reportType === "executive" ? "Executive Summary" : "Detailed Technical"}
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-gray-100">
                <span className="text-gray-500">Layout</span>
                <span className="font-medium text-gray-800">
                  {layoutMode === "presentation_16_9" ? "Presentation 16:9" : "Report A4 Portrait"}
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-gray-100">
                <span className="text-gray-500">Sites</span>
                <span className="font-medium text-gray-800">
                  {orderedSelectedSiteIds
                    .map((id) => studiedSiteOptions.find((o) => o.siteId === id)?.siteName ?? id)
                    .join(", ")}
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-gray-100">
                <span className="text-gray-500">Primary scenarios</span>
                <span className="font-medium text-gray-800">{selectedPrimaryCount}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-gray-100">
                <span className="text-gray-500">Scenario scope</span>
                <span className="font-medium text-gray-800">
                  {includeAllScenarios ? "All scenarios (comparison)" : "Primary only"}
                </span>
              </div>
              {logoUrl && (
                <div className="flex justify-between py-1.5 border-b border-gray-100">
                  <span className="text-gray-500">Logo</span>
                  <span className="font-medium text-gray-800 truncate max-w-[180px]">{logoUrl}</span>
                </div>
              )}
            </div>

            {/* Color preview */}
            <div className="flex items-center gap-3 mt-4">
              <div
                className="w-8 h-8 rounded-lg border border-gray-200"
                style={{ background: primaryColor }}
                title="Primary"
              />
              <div
                className="w-8 h-8 rounded-lg border border-gray-200"
                style={{ background: secondaryColor }}
                title="Secondary"
              />
              <span className="text-xs text-gray-500">Brand colors</span>
            </div>
          </Card>

          {/* Status / error */}
          {(status || error) && (
            <div
              className={`rounded-xl border px-4 py-3 text-sm ${
                error
                  ? "border-rose-200 bg-rose-50 text-rose-700"
                  : "border-emerald-200 bg-emerald-50 text-emerald-700"
              }`}
            >
              {error ?? status}
            </div>
          )}

          {/* Export buttons */}
          <Card>
            <SectionTitle>Download</SectionTitle>
            <div className="grid grid-cols-3 gap-3">
              <button
                onClick={handlePreviewHtml}
                disabled={!canExport || activeFormat !== null}
                className="flex flex-col items-center gap-2 p-4 rounded-xl border-2 border-gray-200 hover:border-gray-300 hover:bg-gray-50 text-sm font-medium text-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {activeFormat === "html" ? (
                  <Loader2 size={22} className="animate-spin text-blue-500" />
                ) : (
                  <Eye size={22} className="text-gray-500" />
                )}
                <span>Preview HTML</span>
                <span className="text-xs text-gray-400 font-normal">Opens in browser</span>
              </button>

              <button
                onClick={() => handleDownload("pdf")}
                disabled={!canExport || activeFormat !== null}
                className="flex flex-col items-center gap-2 p-4 rounded-xl border-2 border-blue-100 bg-blue-50 hover:bg-blue-100 hover:border-blue-300 text-sm font-medium text-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {activeFormat === "pdf" ? (
                  <Loader2 size={22} className="animate-spin" />
                ) : (
                  <FileText size={22} />
                )}
                <span>Download PDF</span>
                <span className="text-xs font-normal text-blue-400">
                  {reportType === "executive" ? "2–3 pages" : "8–15 pages"}
                </span>
              </button>

              <button
                onClick={() => handleDownload("excel")}
                disabled={!canExport || activeFormat !== null}
                className="flex flex-col items-center gap-2 p-4 rounded-xl border-2 border-green-100 bg-green-50 hover:bg-green-100 hover:border-green-300 text-sm font-medium text-green-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {activeFormat === "excel" ? (
                  <Loader2 size={22} className="animate-spin" />
                ) : (
                  <Table2 size={22} />
                )}
                <span>Download Excel</span>
                <span className="text-xs font-normal text-green-500">15+ data sheets</span>
              </button>
            </div>
          </Card>

          <div className="flex justify-start">
            <button
              onClick={() => setStep(2)}
              className="px-5 py-2.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm font-medium transition-colors"
            >
              ← Back to Options
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
