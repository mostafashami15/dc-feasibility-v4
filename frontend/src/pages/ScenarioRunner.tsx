/**
 * ScenarioRunner — Page 3: Batch Scenario Configuration
 * =======================================================
 * This page lets the user:
 *   1. Select which sites to evaluate (checkboxes)
 *   2. Select load types, cooling types, redundancy, density
 *   3. See the total number of combinations
 *   4. Click "Run" to compute all combinations
 *   5. Navigate to Results Dashboard when complete
 *
 * Architecture Agreement Section 6, Page 3.
 *
 * CONCEPT — Checkbox multi-select pattern
 * The user selects multiple items from lists. We store the
 * selected items as arrays in state. When a checkbox toggles,
 * we add/remove the item from the array.
 *
 * CONCEPT — useNavigate
 * React Router's useNavigate() returns a function that changes
 * the URL programmatically. After a batch run completes, we
 * navigate to "/results" to show the results.
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Play, Loader2, AlertCircle, Zap, Settings2 } from "lucide-react";
import { useAppStore } from "../store/useAppStore";
import * as api from "../api/client";
import { loadSessionState, saveSessionState } from "../lib/sessionState";
import type {
  AssumptionOverrideEntry,
  AssumptionOverridePreset,
  AssumptionOverridePresetsResponse,
  AssumptionOverridesResponse,
  GuidedPreset,
  LoadType,
  CoolingType,
  RedundancyLevel,
  DensityScenario,
} from "../types";


// ─────────────────────────────────────────────────────────────
// All enum values — for rendering checkboxes
// ─────────────────────────────────────────────────────────────
// These match the Python Enum values exactly.

const ALL_LOAD_TYPES: LoadType[] = [
  "Colocation (Standard)",
  "Colocation (High Density)",
  "HPC",
  "AI / GPU Clusters",
  "Hyperscale / Cloud",
  "Edge / Telco",
];

const ALL_COOLING_TYPES: CoolingType[] = [
  "Air-Cooled CRAC (DX)",
  "Air-Cooled AHU (No Economizer)",
  "Air-Cooled Chiller + Economizer",
  "Water-Cooled Chiller + Economizer",
  "Rear Door Heat Exchanger (RDHx)",
  "Direct Liquid Cooling (DLC / Cold Plate)",
  "Immersion Cooling (Single-Phase)",
  "Free Cooling — Dry Cooler (Chiller-less)",
];

const ALL_REDUNDANCY: RedundancyLevel[] = ["N", "N+1", "2N", "2N+1"];

const ALL_DENSITY: DensityScenario[] = ["low", "typical", "high"];

const SCENARIO_RUNNER_STATE_KEY = "scenario-runner-state";

type ScenarioRunnerMode = "guided" | "advanced";

type ScenarioRunnerSessionState = {
  mode: ScenarioRunnerMode;
  selectedSiteIds: string[];
  selectedLoads: LoadType[];
  selectedCooling: CoolingType[];
  selectedRedundancy: RedundancyLevel[];
  selectedDensity: DensityScenario[];
  selectedPresetKey: string | null;
  includeHourly: boolean;
  skipIncompatible: boolean;
};

const DEFAULT_SCENARIO_RUNNER_STATE: ScenarioRunnerSessionState = {
  mode: "guided",
  selectedSiteIds: [],
  selectedLoads: [],
  selectedCooling: [],
  selectedRedundancy: ["2N"],
  selectedDensity: ["typical"],
  selectedPresetKey: null,
  includeHourly: true,
  skipIncompatible: true,
};


function describeApiError(err: unknown, fallback: string) {
  if (
    typeof err === "object" &&
    err !== null &&
    "response" in err &&
    typeof (err as { response?: { data?: { detail?: string } } }).response?.data?.detail === "string"
  ) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? fallback;
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return fallback;
}


export default function ScenarioRunner() {
  const navigate = useNavigate();
  const initialState = useMemo(
    () => loadSessionState(SCENARIO_RUNNER_STATE_KEY, DEFAULT_SCENARIO_RUNNER_STATE),
    []
  );

  // ── Global state ──
  const sites = useAppStore((s) => s.sites);
  const resultsLoading = useAppStore((s) => s.resultsLoading);
  const resultsError = useAppStore((s) => s.resultsError);
  const runBatch = useAppStore((s) => s.runBatch);
  const batchResults = useAppStore((s) => s.batchResults);

  // ── Mode ──
  const [mode, setMode] = useState<ScenarioRunnerMode>(initialState.mode ?? "guided");

  // ── Guided mode state ──
  const [guidedPresets, setGuidedPresets] = useState<GuidedPreset[]>([]);
  const [guidedPresetsLoading, setGuidedPresetsLoading] = useState(true);
  const [guidedRunning, setGuidedRunning] = useState(false);
  const [guidedError, setGuidedError] = useState<string | null>(null);

  // ── Local selections ──
  const [selectedSiteIds, setSelectedSiteIds] = useState<string[]>(initialState.selectedSiteIds);
  const [selectedLoads, setSelectedLoads] = useState<LoadType[]>(initialState.selectedLoads);
  const [selectedCooling, setSelectedCooling] = useState<CoolingType[]>(initialState.selectedCooling);
  const [selectedRedundancy, setSelectedRedundancy] = useState<RedundancyLevel[]>(initialState.selectedRedundancy);
  const [selectedDensity, setSelectedDensity] = useState<DensityScenario[]>(initialState.selectedDensity);
  const [selectedPresetKey, setSelectedPresetKey] = useState<string | null>(
    initialState.selectedPresetKey ?? null
  );
  const [includeHourly, setIncludeHourly] = useState(initialState.includeHourly);
  const [skipIncompatible, setSkipIncompatible] = useState(initialState.skipIncompatible);
  const [assumptionSummaryLoading, setAssumptionSummaryLoading] = useState(true);
  const [assumptionSummary, setAssumptionSummary] = useState<AssumptionOverridesResponse | null>(null);
  const [assumptionSummaryError, setAssumptionSummaryError] = useState<string | null>(null);
  const [presetCatalogLoading, setPresetCatalogLoading] = useState(true);
  const [presetCatalog, setPresetCatalog] = useState<AssumptionOverridePresetsResponse | null>(null);
  const [presetCatalogError, setPresetCatalogError] = useState<string | null>(null);

  useEffect(() => {
    const validSiteIds = new Set(sites.map((site) => site.id));
    const filtered = selectedSiteIds.filter((siteId) => validSiteIds.has(siteId));
    if (filtered.length !== selectedSiteIds.length) {
      setSelectedSiteIds(filtered);
    }
  }, [sites, selectedSiteIds]);

  useEffect(() => {
    saveSessionState(SCENARIO_RUNNER_STATE_KEY, {
      mode,
      selectedSiteIds,
      selectedLoads,
      selectedCooling,
      selectedRedundancy,
      selectedDensity,
      selectedPresetKey,
      includeHourly,
      skipIncompatible,
    } satisfies ScenarioRunnerSessionState);
  }, [
    mode,
    includeHourly,
    selectedCooling,
    selectedDensity,
    selectedLoads,
    selectedPresetKey,
    selectedRedundancy,
    selectedSiteIds,
    skipIncompatible,
  ]);

  useEffect(() => {
    let cancelled = false;

    api.getAssumptionOverrides()
      .then((response) => {
        if (cancelled) {
          return;
        }
        setAssumptionSummary(response);
        setAssumptionSummaryError(null);
        setAssumptionSummaryLoading(false);
      })
      .catch((err) => {
        if (cancelled) {
          return;
        }
        setAssumptionSummaryError(
          describeApiError(err, "Could not load active assumption overrides.")
        );
        setAssumptionSummaryLoading(false);
      });

    api.getAssumptionOverridePresets()
      .then((response) => {
        if (cancelled) {
          return;
        }
        setPresetCatalog(response);
        setPresetCatalogError(null);
        setPresetCatalogLoading(false);
      })
      .catch((err) => {
        if (cancelled) {
          return;
        }
        setPresetCatalogError(
          describeApiError(err, "Could not load scenario-local presets.")
        );
        setPresetCatalogLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (
      selectedPresetKey &&
      presetCatalog &&
      !presetCatalog.presets.some((preset) => preset.key === selectedPresetKey)
    ) {
      setSelectedPresetKey(null);
    }
  }, [presetCatalog, selectedPresetKey]);

  // ── Load guided presets on mount ──
  useEffect(() => {
    let cancelled = false;
    api.getGuidedPresets()
      .then((res) => {
        if (!cancelled) {
          setGuidedPresets(res.presets);
          setGuidedPresetsLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setGuidedPresetsLoading(false);
      });
    return () => { cancelled = true; };
  }, []);


  // ── Generic toggle function ──
  function toggle<T>(list: T[], item: T, setter: (v: T[]) => void) {
    if (list.includes(item)) {
      setter(list.filter((x) => x !== item));
    } else {
      setter([...list, item]);
    }
  }


  // ── Combination count ──
  // CONCEPT — useMemo
  // useMemo caches a computed value and only recalculates when
  // its dependencies change. Without it, this multiplication
  // would run on every render (wasteful for expensive calculations).
  // For a simple multiply it's not critical, but it's good practice.
  const combinationCount = useMemo(() => {
    return (
      selectedSiteIds.length *
      selectedLoads.length *
      selectedCooling.length *
      selectedRedundancy.length *
      selectedDensity.length
    );
  }, [selectedSiteIds, selectedLoads, selectedCooling, selectedRedundancy, selectedDensity]);
  const activeAssumptionOverrides = assumptionSummary?.assumptions.filter(
    (entry) => entry.override !== null
  ) ?? [];
  const selectedPreset = presetCatalog?.presets.find(
    (preset) => preset.key === selectedPresetKey
  ) ?? null;


  // ── Run batch ──
  async function handleRun() {
    if (selectedSiteIds.length === 0) return;
    if (selectedLoads.length === 0) return;
    if (selectedCooling.length === 0) return;

    await runBatch({
      site_ids: selectedSiteIds,
      load_types: selectedLoads,
      cooling_types: selectedCooling,
      redundancy_levels: selectedRedundancy,
      density_scenarios: selectedDensity,
      assumption_override_preset_key: selectedPresetKey,
      include_hourly: includeHourly,
      skip_incompatible: skipIncompatible,
    });

    // Navigate only when results were produced successfully.
    if (useAppStore.getState().batchResults.length > 0) {
      navigate("/results");
    }
  }


  // ── Run guided mode ──
  async function handleGuidedRun() {
    if (selectedSiteIds.length === 0) return;
    setGuidedRunning(true);
    setGuidedError(null);
    try {
      const response = await api.runGuidedAnalysis(selectedSiteIds);
      // Set results directly into the store so ResultsDashboard can display them
      useAppStore.setState({
        batchResults: response.results,
        selectedResultIndex: response.results.length > 0 ? 0 : null,
        resultsError: null,
      });
      if (response.results.length > 0) {
        navigate("/results");
      }
    } catch (err: unknown) {
      setGuidedError(describeApiError(err, "Guided analysis failed"));
    } finally {
      setGuidedRunning(false);
    }
  }

  // ── Select all / deselect all helpers ──
  function selectAllSites() {
    setSelectedSiteIds(sites.map((s) => s.id));
  }
  function deselectAllSites() {
    setSelectedSiteIds([]);
  }


  // ── Render ──
  return (
    <div className="max-w-5xl mx-auto">
      {/* Header + Mode Toggle */}
      <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Scenario Runner</h2>
          <p className="text-sm text-gray-500 mt-1">
            {mode === "guided"
              ? "Select sites — all load types run automatically with best-practice presets"
              : "Select sites and parameters, then run all combinations"}
          </p>
        </div>
        <div className="flex bg-gray-100 rounded-lg p-1">
          <button
            onClick={() => setMode("guided")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              mode === "guided"
                ? "bg-white text-blue-700 shadow-sm"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            <Zap size={14} />
            Guided
          </button>
          <button
            onClick={() => setMode("advanced")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              mode === "advanced"
                ? "bg-white text-blue-700 shadow-sm"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            <Settings2 size={14} />
            Advanced
          </button>
        </div>
      </div>

      {/* Error banners */}
      {resultsError && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm flex items-center gap-2">
          <AlertCircle size={16} />
          {resultsError}
        </div>
      )}
      {guidedError && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm flex items-center gap-2">
          <AlertCircle size={16} />
          {guidedError}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════
          GUIDED MODE
         ═══════════════════════════════════════════════════════════ */}
      {mode === "guided" && (
        <div className="space-y-6">
          {/* ── Site Selection (Guided) ── */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between">
              <h3 className="font-semibold text-gray-800">Select Sites</h3>
              <div className="flex gap-2">
                <button type="button" onClick={selectAllSites} className="text-xs text-blue-600 hover:text-blue-800">Select All</button>
                <span className="text-gray-300">|</span>
                <button type="button" onClick={deselectAllSites} className="text-xs text-gray-500 hover:text-gray-700">Clear</button>
              </div>
            </div>
            <div className="p-4">
              {sites.length === 0 ? (
                <p className="text-sm text-gray-400">
                  No sites created yet. Go to <Link to="/sites" className="text-blue-600 hover:underline">Site Manager</Link> to add sites.
                </p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {sites.map((s) => (
                    <label
                      key={s.id}
                      className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                        selectedSiteIds.includes(s.id)
                          ? "bg-blue-50 border-blue-300"
                          : "bg-white border-gray-200 hover:bg-gray-50"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedSiteIds.includes(s.id)}
                        onChange={() => toggle(selectedSiteIds, s.id, setSelectedSiteIds)}
                        className="mt-0.5 w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">{s.site.name}</p>
                        <p className="text-xs text-gray-500">
                          {s.site.city || "No location"} · {s.site.available_power_mw > 0 ? `${s.site.available_power_mw} MW` : "Area-only"}
                        </p>
                        {s.has_weather && <span className="text-xs text-green-600">Weather ✓</span>}
                        {!s.has_weather && <span className="text-xs text-amber-500">No weather data</span>}
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ── Preset Summary Table ── */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200">
            <div className="p-4 border-b border-gray-100">
              <h3 className="font-semibold text-gray-800">What Will Run</h3>
              <p className="text-xs text-gray-500 mt-1">
                All 6 load types with fixed best-practice cooling, typical density, and N redundancy — using full 8,760-hour climate simulation
              </p>
            </div>
            <div className="p-4">
              {guidedPresetsLoading ? (
                <div className="text-sm text-gray-500 flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin" />
                  Loading presets...
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200">
                        <th className="text-left py-2 pr-4 font-medium text-gray-600">Load Type</th>
                        <th className="text-left py-2 pr-4 font-medium text-gray-600">Cooling Topology</th>
                        <th className="text-left py-2 pr-4 font-medium text-gray-600">Density</th>
                        <th className="text-left py-2 font-medium text-gray-600">Redundancy</th>
                      </tr>
                    </thead>
                    <tbody>
                      {guidedPresets.map((p) => (
                        <tr key={p.load_type} className="border-b border-gray-100 last:border-0">
                          <td className="py-2.5 pr-4 font-medium text-gray-900">{p.load_type}</td>
                          <td className="py-2.5 pr-4 text-gray-700">{p.cooling_type}</td>
                          <td className="py-2.5 pr-4 text-gray-700">{p.density_kw} kW/rack</td>
                          <td className="py-2.5 text-gray-700">{p.redundancy}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          {/* ── Guided Run Button ── */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">
                  <span className="font-semibold text-gray-900">
                    {selectedSiteIds.length * 6}
                  </span>{" "}
                  scenarios ({selectedSiteIds.length} site{selectedSiteIds.length !== 1 ? "s" : ""} × 6 load types)
                </p>
                {selectedSiteIds.length === 0 && (
                  <p className="text-xs text-amber-600 mt-1">Select at least one site to run</p>
                )}
              </div>
              <div className="flex items-center gap-3">
                {batchResults.length > 0 && (
                  <button
                    onClick={() => navigate("/results")}
                    className="px-4 py-2.5 text-sm text-blue-600 hover:text-blue-800 font-medium"
                  >
                    View Previous Results ({batchResults.length})
                  </button>
                )}
                <button
                  onClick={handleGuidedRun}
                  disabled={guidedRunning || selectedSiteIds.length === 0}
                  className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium transition-colors"
                >
                  {guidedRunning ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Running...
                    </>
                  ) : (
                    <>
                      <Zap size={16} />
                      Run Analysis
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════
          ADVANCED MODE
         ═══════════════════════════════════════════════════════════ */}
      {mode === "advanced" && <div className="space-y-6">
        {/* ── Site Selection ── */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-100 flex items-center justify-between">
            <h3 className="font-semibold text-gray-800">
              1. Select Sites
            </h3>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={selectAllSites}
                className="text-xs text-blue-600 hover:text-blue-800"
              >
                Select All
              </button>
              <span className="text-gray-300">|</span>
              <button
                type="button"
                onClick={deselectAllSites}
                className="text-xs text-gray-500 hover:text-gray-700"
              >
                Clear
              </button>
            </div>
          </div>
          <div className="p-4">
            {sites.length === 0 ? (
              <p className="text-sm text-gray-400">
                No sites created yet. Go to Site Manager to add sites.
              </p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {sites.map((s) => (
                  <label
                    key={s.id}
                    className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                      selectedSiteIds.includes(s.id)
                        ? "bg-blue-50 border-blue-300"
                        : "bg-white border-gray-200 hover:bg-gray-50"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedSiteIds.includes(s.id)}
                      onChange={() =>
                        toggle(selectedSiteIds, s.id, setSelectedSiteIds)
                      }
                      className="mt-0.5 w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {s.site.name}
                      </p>
                      <p className="text-xs text-gray-500">
                        {s.site.city || "No location"} ·{" "}
                        {s.site.available_power_mw > 0
                          ? `${s.site.available_power_mw} MW`
                          : "Area-only"}
                      </p>
                      {s.has_weather && (
                        <span className="text-xs text-green-600">Weather ✓</span>
                      )}
                    </div>
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>


        {/* ── Load Types ── */}
        <CheckboxGroup
          title="2. Load Types"
          items={ALL_LOAD_TYPES}
          selected={selectedLoads}
          onToggle={(item) =>
            toggle(selectedLoads, item as LoadType, setSelectedLoads)
          }
        />

        {/* ── Cooling Types ── */}
        <CheckboxGroup
          title="3. Cooling Types"
          items={ALL_COOLING_TYPES}
          selected={selectedCooling}
          onToggle={(item) =>
            toggle(selectedCooling, item as CoolingType, setSelectedCooling)
          }
        />

        {/* ── Redundancy + Density (side by side) ── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <CheckboxGroup
            title="4. Redundancy"
            items={ALL_REDUNDANCY}
            selected={selectedRedundancy}
            onToggle={(item) =>
              toggle(
                selectedRedundancy,
                item as RedundancyLevel,
                setSelectedRedundancy
              )
            }
          />
          <CheckboxGroup
            title="5. Density Scenario"
            items={ALL_DENSITY}
            selected={selectedDensity}
            onToggle={(item) =>
              toggle(
                selectedDensity,
                item as DensityScenario,
                setSelectedDensity
              )
            }
          />
        </div>


        {/* ── Options ── */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
          <h3 className="font-semibold text-gray-800 mb-3">Options</h3>
          <div className="flex flex-wrap gap-6">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={includeHourly}
                onChange={(e) => setIncludeHourly(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              Run 8,760-hour simulation (if weather available)
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={skipIncompatible}
                onChange={(e) => setSkipIncompatible(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              Skip incompatible cooling × load combinations
            </label>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <div>
              <h3 className="font-semibold text-gray-800">6. Scenario-Local Preset</h3>
              <p className="text-xs text-gray-500 mt-1">
                Presets overlay the saved Settings overrides for this batch only. They do not change the persisted baseline configuration.
              </p>
            </div>

            {selectedPresetKey && (
              <button
                type="button"
                onClick={() => setSelectedPresetKey(null)}
                className="text-sm text-blue-600 hover:text-blue-800 font-medium"
              >
                Clear Preset
              </button>
            )}
          </div>

          {presetCatalogLoading ? (
            <div className="mt-4 text-sm text-gray-500 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin" />
              Loading scenario-local presets...
            </div>
          ) : presetCatalogError ? (
            <div className="mt-4 p-3 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg text-sm flex items-start gap-2">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span>{presetCatalogError}</span>
            </div>
          ) : presetCatalog && presetCatalog.presets.length > 0 ? (
            <div className="mt-4 space-y-4">
              <button
                type="button"
                onClick={() => setSelectedPresetKey(null)}
                className={`w-full text-left rounded-lg border px-4 py-3 transition-colors ${
                  selectedPresetKey === null
                    ? "bg-blue-50 border-blue-300"
                    : "bg-white border-gray-200 hover:bg-gray-50"
                }`}
              >
                <p className="text-sm font-medium text-gray-900">Use Saved Settings Only</p>
                <p className="text-xs text-gray-500 mt-1">
                  Run with the active controlled overrides from Settings and no additional preset overlay.
                </p>
              </button>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {presetCatalog.presets.map((preset) => (
                  <PresetOptionCard
                    key={preset.key}
                    preset={preset}
                    selected={preset.key === selectedPresetKey}
                    onSelect={setSelectedPresetKey}
                  />
                ))}
              </div>

              {selectedPreset && (
                <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3">
                  <p className="text-sm font-medium text-blue-900">
                    {selectedPreset.label} selected for this batch
                  </p>
                  <p className="text-xs text-blue-800 mt-1">
                    {selectedPreset.description}
                  </p>
                  <p className="text-xs text-blue-700 mt-2">
                    {selectedPreset.override_count} curated override key
                    {selectedPreset.override_count === 1 ? "" : "s"} will be layered on top of the saved Settings overrides where they affect the chosen scenarios.
                  </p>
                </div>
              )}
            </div>
          ) : (
            <p className="mt-4 text-sm text-gray-500">
              No scenario-local presets are currently available.
            </p>
          )}
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <div>
              <h3 className="font-semibold text-gray-800">Active Assumption Overrides</h3>
              <p className="text-xs text-gray-500 mt-1">
                Any saved controlled overrides from Settings are applied automatically to this batch run. If a preset is selected above, it overlays those values for this batch only and both layers are stamped onto the resulting scenario metadata.
              </p>
            </div>

            <Link
              to="/settings"
              className="text-sm text-blue-600 hover:text-blue-800 font-medium"
            >
              Manage in Settings
            </Link>
          </div>

          {assumptionSummaryLoading ? (
            <div className="mt-4 text-sm text-gray-500 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin" />
              Loading controlled override summary...
            </div>
          ) : assumptionSummaryError ? (
            <div className="mt-4 p-3 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg text-sm flex items-start gap-2">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span>{assumptionSummaryError}</span>
            </div>
          ) : activeAssumptionOverrides.length > 0 ? (
            <div className="mt-4 space-y-3">
              <p className="text-sm text-gray-700">
                <span className="font-semibold text-gray-900">
                  {activeAssumptionOverrides.length}
                </span>{" "}
                controlled override{activeAssumptionOverrides.length === 1 ? "" : "s"} currently active
              </p>

              {activeAssumptionOverrides.slice(0, 4).map((entry) => (
                <ActiveOverrideSummary key={entry.key} entry={entry} />
              ))}

              {activeAssumptionOverrides.length > 4 && (
                <p className="text-xs text-gray-500">
                  {activeAssumptionOverrides.length - 4} more override
                  {activeAssumptionOverrides.length - 4 === 1 ? "" : "s"} are active and can be reviewed on the Settings page.
                </p>
              )}
            </div>
          ) : (
            <p className="mt-4 text-sm text-gray-500">
              No controlled overrides are active. Runs will use the repo baseline assumptions.
            </p>
          )}
        </div>


        {/* ── Run Button ── */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">
                <span className="font-semibold text-gray-900">
                  {combinationCount}
                </span>{" "}
                combination{combinationCount !== 1 ? "s" : ""} to evaluate
              </p>
              {selectedSiteIds.length === 0 && (
                <p className="text-xs text-amber-600 mt-1">
                  Select at least one site to run
                </p>
              )}
            </div>

            <div className="flex items-center gap-3">
              {batchResults.length > 0 && (
                <button
                  onClick={() => navigate("/results")}
                  className="px-4 py-2.5 text-sm text-blue-600 hover:text-blue-800 font-medium"
                >
                  View Previous Results ({batchResults.length})
                </button>
              )}
              <button
                onClick={handleRun}
                disabled={
                  resultsLoading ||
                  selectedSiteIds.length === 0 ||
                  selectedLoads.length === 0 ||
                  selectedCooling.length === 0
                }
                className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium transition-colors"
              >
                {resultsLoading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Running...
                  </>
                ) : (
                  <>
                    <Play size={16} />
                    Run Batch
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Reusable CheckboxGroup component
// ─────────────────────────────────────────────────────────────
// CONCEPT — Component reuse
// This component renders a titled card with checkboxes for
// each item in a list. We use it four times above (load types,
// cooling types, redundancy, density).
//
// CONCEPT — Props
// Props are the arguments to a React component. They flow
// down from parent to child (like function parameters).
// The parent decides what data and handlers to pass in.

function ActiveOverrideSummary({
  entry,
}: {
  entry: AssumptionOverrideEntry;
}) {
  return (
    <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-3">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-blue-900">
            {entry.scope_label} - {entry.parameter_label}
          </p>
          <p className="text-xs text-blue-800 mt-1">
            {entry.override?.source}
          </p>
          <p className="text-xs text-blue-700 mt-1">
            {entry.override?.justification}
          </p>
        </div>

        <div className="text-xs text-blue-900 shrink-0">
          <span className="font-medium">
            {formatScenarioOverrideValue(entry.baseline_value, entry.unit)}
          </span>{" "}
          baseline -{" "}
          <span className="font-medium">
            {formatScenarioOverrideValue(entry.effective_value, entry.unit)}
          </span>
        </div>
      </div>
    </div>
  );
}


function PresetOptionCard({
  preset,
  selected,
  onSelect,
}: {
  preset: AssumptionOverridePreset;
  selected: boolean;
  onSelect: (key: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(preset.key)}
      className={`text-left rounded-lg border px-4 py-3 transition-colors ${
        selected
          ? "bg-blue-50 border-blue-300"
          : "bg-white border-gray-200 hover:bg-gray-50"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-gray-900">{preset.label}</p>
          <p className="text-xs text-gray-500 mt-1">{preset.description}</p>
        </div>
        <span className="text-xs text-gray-600 bg-gray-100 rounded-full px-2 py-0.5 shrink-0">
          {preset.override_count} keys
        </span>
      </div>

      <p className="text-xs text-gray-500 mt-3">{preset.source}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {preset.overrides.slice(0, 3).map((override) => (
          <span
            key={override.key}
            className="px-2 py-0.5 rounded-full bg-gray-50 border border-gray-200 text-[11px] text-gray-600"
          >
            {override.scope_label} - {override.parameter_label}
          </span>
        ))}
        {preset.overrides.length > 3 && (
          <span className="px-2 py-0.5 rounded-full bg-gray-50 border border-gray-200 text-[11px] text-gray-600">
            +{preset.overrides.length - 3} more
          </span>
        )}
      </div>
    </button>
  );
}


function formatScenarioOverrideValue(value: number, unit: string) {
  if (unit === "PUE" || unit === "COP") {
    return `${value.toFixed(2)} ${unit}`;
  }
  if (unit === "fraction" || unit === "eta") {
    return `${value.toFixed(3)} ${unit}`;
  }
  return `${value} ${unit}`;
}


function CheckboxGroup({
  title,
  items,
  selected,
  onToggle,
}: {
  title: string;
  items: string[];
  selected: string[];
  onToggle: (item: string) => void;
}) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200">
      <div className="p-4 border-b border-gray-100">
        <h3 className="font-semibold text-gray-800">{title}</h3>
      </div>
      <div className="p-4">
        <div className="flex flex-wrap gap-3">
          {items.map((item) => (
            <label
              key={item}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm cursor-pointer transition-colors ${
                selected.includes(item)
                  ? "bg-blue-50 border-blue-300 text-blue-800"
                  : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50"
              }`}
            >
              <input
                type="checkbox"
                checked={selected.includes(item)}
                onChange={() => onToggle(item)}
                className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              {item}
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}
