import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Layers3, Loader2, Target } from "lucide-react";
import { useAppStore } from "../store/useAppStore";
import * as api from "../api/client";
import { loadSessionState, saveSessionState } from "../lib/sessionState";
import type {
  CoolingType,
  DensityScenario,
  LoadMixResult,
  LoadType,
  ScenarioResult,
} from "../types";

const LOAD_MIX_STATE_KEY = "load-mix-state";

type LoadMixSessionState = {
  result: LoadMixResult | null;
  resultSelectionKey: string | null;
};

const DEFAULT_LOAD_MIX_STATE: LoadMixSessionState = {
  result: null,
  resultSelectionKey: null,
};


function getDefaultResult(results: ScenarioResult[], selectedIndex: number | null): ScenarioResult | null {
  if (selectedIndex !== null && results[selectedIndex]) {
    return results[selectedIndex];
  }
  return results[0] ?? null;
}


function getScenarioSelectionKey(result: ScenarioResult): string {
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


export default function LoadMixPlanner() {
  const referenceData = useAppStore((s) => s.referenceData);
  const results = useAppStore((s) => s.batchResults);
  const selectedIndex = useAppStore((s) => s.selectedResultIndex);

  const selectedResult = useMemo(
    () => getDefaultResult(results, selectedIndex),
    [results, selectedIndex]
  );

  const availableLoadTypes = useMemo(
    () => (referenceData ? Object.keys(referenceData.load_profiles) as LoadType[] : []),
    [referenceData]
  );
  const availableCoolingTypes = useMemo(
    () => (referenceData ? Object.keys(referenceData.cooling_profiles) as CoolingType[] : []),
    [referenceData]
  );
  const initialState = useMemo(
    () => loadSessionState(LOAD_MIX_STATE_KEY, DEFAULT_LOAD_MIX_STATE),
    []
  );

  const [totalItMw, setTotalItMw] = useState("");
  const [coolingType, setCoolingType] = useState<CoolingType | "">("");
  const [densityScenario, setDensityScenario] = useState<DensityScenario>("typical");
  const [stepPct, setStepPct] = useState("10");
  const [minRacks, setMinRacks] = useState("10");
  const [topN, setTopN] = useState("5");
  const [allowedLoadTypes, setAllowedLoadTypes] = useState<LoadType[]>([]);
  const [result, setResult] = useState<LoadMixResult | null>(initialState.result);
  const [resultSelectionKey, setResultSelectionKey] = useState<string | null>(initialState.resultSelectionKey);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedScenarioKey = useMemo(
    () => (selectedResult ? getScenarioSelectionKey(selectedResult) : null),
    [selectedResult]
  );

  useEffect(() => {
    if (availableLoadTypes.length > 0 && allowedLoadTypes.length === 0) {
      setAllowedLoadTypes(availableLoadTypes.slice(0, Math.min(3, availableLoadTypes.length)));
    }
  }, [availableLoadTypes, allowedLoadTypes.length]);

  useEffect(() => {
    if (!selectedResult && availableCoolingTypes[0]) {
      setCoolingType((current) => current || availableCoolingTypes[0]);
    }
  }, [availableCoolingTypes, selectedResult]);

  useEffect(() => {
    if (!selectedResult) return;
    setTotalItMw(String(getCommittedItMw(selectedResult).toFixed(2)));
    setCoolingType(selectedResult.scenario.cooling_type);
    setDensityScenario(selectedResult.scenario.density_scenario);
  }, [selectedResult]);

  useEffect(() => {
    setResult((current) => {
      if (!current || !selectedScenarioKey || resultSelectionKey !== selectedScenarioKey) {
        return null;
      }
      return current;
    });
    setResultSelectionKey((current) => (
      current && selectedScenarioKey && current === selectedScenarioKey ? current : null
    ));
  }, [resultSelectionKey, selectedScenarioKey, selectedIndex]);

  useEffect(() => {
    saveSessionState(LOAD_MIX_STATE_KEY, {
      result,
      resultSelectionKey,
    } satisfies LoadMixSessionState);
  }, [result, resultSelectionKey]);

  function applySelectedResultDefaults() {
    if (!selectedResult) return;
    setTotalItMw(String(getCommittedItMw(selectedResult).toFixed(2)));
    setCoolingType(selectedResult.scenario.cooling_type);
    setDensityScenario(selectedResult.scenario.density_scenario);
  }

  function toggleLoadType(loadType: LoadType) {
    setAllowedLoadTypes((current) =>
      current.includes(loadType)
        ? current.filter((value) => value !== loadType)
        : [...current, loadType]
    );
  }

  async function handleOptimize() {
    setRunning(true);
    setError(null);
    setResult(null);

    try {
      if (!coolingType) {
        throw new Error("Choose a cooling type before running the optimizer.");
      }
      if (allowedLoadTypes.length < 2) {
        throw new Error("Select at least two load types for the mix optimizer.");
      }

      const data = await api.optimizeLoadMix({
        total_it_mw: Number.parseFloat(totalItMw),
        allowed_load_types: allowedLoadTypes,
        cooling_type: coolingType,
        density_scenario: densityScenario,
        step_pct: Number.parseInt(stepPct, 10),
        min_racks: Number.parseInt(minRacks, 10),
        top_n: Number.parseInt(topN, 10),
      });
      setResult(data);
      setResultSelectionKey(selectedScenarioKey);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Load mix optimization failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="max-w-7xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Load Mix Planner</h2>
        <p className="text-sm text-gray-500 mt-1">
          Explore blended workload allocations such as HPC + colocation + AI within one IT envelope
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-4 space-y-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                  <Layers3 size={18} className="text-blue-500" />
                  Mix Inputs
                </h3>
                <p className="text-xs text-gray-500 mt-1">
                  The optimizer ranks deterministic share combinations that sum to 100%.
                </p>
              </div>
              {selectedResult && (
                <button
                  type="button"
                  onClick={applySelectedResultDefaults}
                  className="text-xs px-3 py-1 bg-gray-100 rounded-lg hover:bg-gray-200"
                >
                  Use Selected Result
                </button>
              )}
            </div>

            {selectedResult && (
              <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-xs text-blue-800">
                <p className="font-medium">{selectedResult.site_name}</p>
                <p className="mt-1">
                  Prefill source: {selectedResult.scenario.cooling_type} ·{" "}
                  {selectedResult.scenario.density_scenario} ·{" "}
                  {getCommittedItMw(selectedResult).toFixed(2)} MW IT
                </p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">Total IT (MW)</span>
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={totalItMw}
                  onChange={(e) => setTotalItMw(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">Cooling</span>
                <select
                  value={coolingType}
                  onChange={(e) => setCoolingType(e.target.value as CoolingType)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none"
                >
                  <option value="">Select cooling</option>
                  {availableCoolingTypes.map((type) => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">Density</span>
                <select
                  value={densityScenario}
                  onChange={(e) => setDensityScenario(e.target.value as DensityScenario)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none"
                >
                  <option value="low">Low</option>
                  <option value="typical">Typical</option>
                  <option value="high">High</option>
                </select>
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">Step (%)</span>
                <input
                  type="number"
                  min="5"
                  max="50"
                  step="5"
                  value={stepPct}
                  onChange={(e) => setStepPct(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">Min Racks / Type</span>
                <input
                  type="number"
                  min="1"
                  value={minRacks}
                  onChange={(e) => setMinRacks(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">Top Candidates</span>
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={topN}
                  onChange={(e) => setTopN(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </label>
            </div>

            <div>
              <p className="text-xs font-medium text-gray-600 mb-2">Allowed Load Types</p>
              <div className="space-y-2">
                {availableLoadTypes.map((loadType) => (
                  <label
                    key={loadType}
                    className={`flex items-start gap-3 p-3 rounded-lg border ${
                      allowedLoadTypes.includes(loadType)
                        ? "border-blue-300 bg-blue-50"
                        : "border-gray-200 bg-white"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={allowedLoadTypes.includes(loadType)}
                      onChange={() => toggleLoadType(loadType)}
                      className="mt-0.5"
                    />
                    <span className="text-sm text-gray-700">{loadType}</span>
                  </label>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={handleOptimize}
              disabled={running || !referenceData}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              {running ? <Loader2 size={16} className="animate-spin" /> : <Target size={16} />}
              {running ? "Optimizing..." : "Suggest Load Mix"}
            </button>

            {error && (
              <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm flex items-start gap-2">
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}
          </div>
        </div>

        <div className="xl:col-span-8">
          {result ? (
            <div className="space-y-4">
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <SummaryMetric label="Total IT" value={`${result.total_it_mw.toFixed(2)} MW`} />
                  <SummaryMetric label="Cooling" value={result.cooling_type} />
                  <SummaryMetric label="Density" value={result.density_scenario} />
                  <SummaryMetric label="Candidates" value={result.total_candidates_evaluated.toLocaleString()} />
                </div>
              </div>

              {result.top_candidates.map((candidate) => (
                <div key={candidate.rank} className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
                  <div className="flex items-start justify-between gap-4 mb-4">
                    <div>
                      <h3 className="font-semibold text-gray-900">Candidate #{candidate.rank}</h3>
                      <p className="text-xs text-gray-500 mt-1">
                        Score {candidate.score.toFixed(1)} · Blended PUE {candidate.blended_pue.toFixed(3)} ·{" "}
                        {candidate.total_racks.toLocaleString()} racks
                      </p>
                    </div>
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-medium ${
                        candidate.all_compatible
                          ? "bg-green-100 text-green-700"
                          : "bg-amber-100 text-amber-700"
                      }`}
                    >
                      {candidate.all_compatible ? "Compatible" : "Needs Review"}
                    </span>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-3 py-2 text-left text-gray-600">Load Type</th>
                          <th className="px-3 py-2 text-right text-gray-600">Share</th>
                          <th className="px-3 py-2 text-right text-gray-600">IT MW</th>
                          <th className="px-3 py-2 text-right text-gray-600">Racks</th>
                          <th className="px-3 py-2 text-right text-gray-600">Density</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {candidate.allocations.map((allocation) => (
                          <tr key={allocation.load_type}>
                            <td className="px-3 py-2 text-gray-800">{allocation.load_type}</td>
                            <td className="px-3 py-2 text-right font-mono">{allocation.share_pct.toFixed(0)}%</td>
                            <td className="px-3 py-2 text-right font-mono">{allocation.it_load_mw.toFixed(2)}</td>
                            <td className="px-3 py-2 text-right font-mono">{allocation.rack_count.toLocaleString()}</td>
                            <td className="px-3 py-2 text-right font-mono">{allocation.rack_density_kw.toFixed(1)} kW</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {candidate.trade_off_notes.length > 0 && (
                    <div className="mt-4 space-y-2">
                      {candidate.trade_off_notes.map((note) => (
                        <p key={note} className="text-xs text-gray-600 flex items-start gap-2">
                          <AlertCircle size={12} className="mt-0.5 shrink-0 text-gray-400" />
                          <span>{note}</span>
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center text-gray-400">
              <Layers3 size={48} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">Choose a cooling topology and at least two load types, then run the optimizer.</p>
              <p className="text-xs mt-1">This feature is separate from scenario ranking and can be used with or without a selected result.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-sm font-semibold text-gray-900 mt-1">{value}</p>
    </div>
  );
}


function getCommittedItMw(result: ScenarioResult): number {
  return result.it_capacity_p99_mw ?? result.power.it_load_mw;
}
