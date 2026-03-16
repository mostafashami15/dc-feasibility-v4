import axios from "axios";
import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Battery, Leaf, Loader2, Play, Sun, Zap } from "lucide-react";
import { useAppStore } from "../store/useAppStore";
import * as api from "../api/client";
import { loadSessionState, saveSessionState } from "../lib/sessionState";
import type { PVGISProfileResult, ScenarioGreenDispatchResult, ScenarioResult } from "../types";

const GREEN_ENERGY_STATE_KEY = "green-energy-state";

type GreenEnergySessionState = {
  pvCapacityKwp: string;
  bessCapacityKwh: string;
  bessEfficiency: string;
  bessInitialSocKwh: string;
  fuelCellKw: string;
  co2Factor: string;
  hourlyPvKw?: number[];
  pvProfileName: string | null;
  pvgisProfile: PVGISProfileResult | null;
  pvgisStartYear: string;
  pvgisEndYear: string;
  pvgisTechnology: PVGISProfileResult["pv_technology"];
  pvgisMountingPlace: PVGISProfileResult["mounting_place"];
  pvgisSystemLossPct: string;
  pvgisUseHorizon: boolean;
  pvgisOptimalAngles: boolean;
  pvgisSurfaceTiltDeg: string;
  pvgisSurfaceAzimuthDeg: string;
  result: ScenarioGreenDispatchResult | null;
  resultSelectionKey: string | null;
};

const DEFAULT_GREEN_ENERGY_STATE: GreenEnergySessionState = {
  pvCapacityKwp: "0",
  bessCapacityKwh: "0",
  bessEfficiency: "0.875",
  bessInitialSocKwh: "0",
  fuelCellKw: "0",
  co2Factor: "0.256",
  hourlyPvKw: undefined,
  pvProfileName: null,
  pvgisProfile: null,
  pvgisStartYear: "2019",
  pvgisEndYear: "2023",
  pvgisTechnology: "crystSi",
  pvgisMountingPlace: "free",
  pvgisSystemLossPct: "14",
  pvgisUseHorizon: true,
  pvgisOptimalAngles: true,
  pvgisSurfaceTiltDeg: "0",
  pvgisSurfaceAzimuthDeg: "0",
  result: null,
  resultSelectionKey: null,
};


function getSelectedResult(results: ScenarioResult[], selectedIndex: number | null): ScenarioResult | null {
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


export default function GreenEnergy() {
  const results = useAppStore((s) => s.batchResults);
  const selectedIndex = useAppStore((s) => s.selectedResultIndex);
  const selectResult = useAppStore((s) => s.selectResult);

  const selectedResult = useMemo(
    () => getSelectedResult(results, selectedIndex),
    [results, selectedIndex]
  );
  const initialState = useMemo(
    () => loadSessionState(GREEN_ENERGY_STATE_KEY, DEFAULT_GREEN_ENERGY_STATE),
    []
  );

  const [pvCapacityKwp, setPvCapacityKwp] = useState(initialState.pvCapacityKwp);
  const [bessCapacityKwh, setBessCapacityKwh] = useState(initialState.bessCapacityKwh);
  const [bessEfficiency, setBessEfficiency] = useState(initialState.bessEfficiency);
  const [bessInitialSocKwh, setBessInitialSocKwh] = useState(initialState.bessInitialSocKwh);
  const [fuelCellKw, setFuelCellKw] = useState(initialState.fuelCellKw);
  const [co2Factor, setCo2Factor] = useState(initialState.co2Factor);
  const [hourlyPvKw, setHourlyPvKw] = useState<number[] | undefined>(initialState.hourlyPvKw);
  const [pvProfileName, setPvProfileName] = useState<string | null>(initialState.pvProfileName);
  const [pvgisProfile, setPvgisProfile] = useState<PVGISProfileResult | null>(initialState.pvgisProfile);
  const [pvgisStartYear, setPvgisStartYear] = useState(initialState.pvgisStartYear);
  const [pvgisEndYear, setPvgisEndYear] = useState(initialState.pvgisEndYear);
  const [pvgisTechnology, setPvgisTechnology] = useState<PVGISProfileResult["pv_technology"]>(initialState.pvgisTechnology);
  const [pvgisMountingPlace, setPvgisMountingPlace] = useState<PVGISProfileResult["mounting_place"]>(initialState.pvgisMountingPlace);
  const [pvgisSystemLossPct, setPvgisSystemLossPct] = useState(initialState.pvgisSystemLossPct);
  const [pvgisUseHorizon, setPvgisUseHorizon] = useState(initialState.pvgisUseHorizon);
  const [pvgisOptimalAngles, setPvgisOptimalAngles] = useState(initialState.pvgisOptimalAngles);
  const [pvgisSurfaceTiltDeg, setPvgisSurfaceTiltDeg] = useState(initialState.pvgisSurfaceTiltDeg);
  const [pvgisSurfaceAzimuthDeg, setPvgisSurfaceAzimuthDeg] = useState(initialState.pvgisSurfaceAzimuthDeg);
  const [pvgisLoading, setPvgisLoading] = useState(false);
  const [result, setResult] = useState<ScenarioGreenDispatchResult | null>(initialState.result);
  const [resultSelectionKey, setResultSelectionKey] = useState<string | null>(initialState.resultSelectionKey);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedScenarioKey = useMemo(
    () => (selectedResult ? getScenarioSelectionKey(selectedResult) : null),
    [selectedResult]
  );

  const parsedPvCapacityKwp = Number.parseFloat(pvCapacityKwp) || 0;
  const activePvSource = hourlyPvKw ? "manual" : pvgisProfile ? "pvgis" : "zero";
  const pvProfileSummary = getPvProfileSummary({
    activePvSource,
    hourlyPvKw,
    pvProfileName,
    pvgisProfile,
  });

  useEffect(() => {
    setError(null);
    setPvgisProfile((current) => {
      if (!current || !selectedResult) {
        return null;
      }
      return current.site_id === selectedResult.site_id ? current : null;
    });
    setResult((current) => {
      if (!current || !selectedScenarioKey || resultSelectionKey !== selectedScenarioKey) {
        return null;
      }
      return current;
    });
    setResultSelectionKey((current) => (
      current && selectedScenarioKey && current === selectedScenarioKey ? current : null
    ));
  }, [resultSelectionKey, selectedResult?.site_id, selectedScenarioKey, selectedIndex]);

  useEffect(() => {
    saveSessionState(GREEN_ENERGY_STATE_KEY, {
      pvCapacityKwp,
      bessCapacityKwh,
      bessEfficiency,
      bessInitialSocKwh,
      fuelCellKw,
      co2Factor,
      hourlyPvKw,
      pvProfileName,
      pvgisProfile,
      pvgisStartYear,
      pvgisEndYear,
      pvgisTechnology,
      pvgisMountingPlace,
      pvgisSystemLossPct,
      pvgisUseHorizon,
      pvgisOptimalAngles,
      pvgisSurfaceTiltDeg,
      pvgisSurfaceAzimuthDeg,
      result,
      resultSelectionKey,
    } satisfies GreenEnergySessionState);
  }, [
    bessCapacityKwh,
    bessEfficiency,
    bessInitialSocKwh,
    co2Factor,
    fuelCellKw,
    hourlyPvKw,
    pvCapacityKwp,
    pvProfileName,
    pvgisEndYear,
    pvgisMountingPlace,
    pvgisOptimalAngles,
    pvgisProfile,
    pvgisStartYear,
    pvgisSurfaceAzimuthDeg,
    pvgisSurfaceTiltDeg,
    pvgisSystemLossPct,
    pvgisTechnology,
    pvgisUseHorizon,
    result,
    resultSelectionKey,
  ]);

  async function handlePvFileChange(file: File | null) {
    if (!file) {
      setHourlyPvKw(undefined);
      setPvProfileName(null);
      return;
    }

    try {
      const text = await file.text();
      const values = parsePvSeries(text);
      if (values.length === 0) {
        throw new Error("No numeric PV values were found in the selected file.");
      }

      setHourlyPvKw(values);
      setPvProfileName(file.name);
    } catch (err: unknown) {
      setHourlyPvKw(undefined);
      setPvProfileName(null);
      setError(getApiErrorMessage(err, "The PV file could not be parsed."));
    }
  }

  async function handleFetchPVGIS(forceRefresh: boolean) {
    if (!selectedResult) {
      setError("Select a scenario result first so the backend can reuse the saved site coordinates.");
      return;
    }

    setPvgisLoading(true);
    setError(null);

    try {
      const data = await api.fetchPVGISProfile({
        site_id: selectedResult.site_id,
        start_year: Number.parseInt(pvgisStartYear, 10) || 2019,
        end_year: Number.parseInt(pvgisEndYear, 10) || 2023,
        pv_technology: pvgisTechnology,
        mounting_place: pvgisMountingPlace,
        system_loss_pct: Number.parseFloat(pvgisSystemLossPct) || 14,
        use_horizon: pvgisUseHorizon,
        optimal_angles: pvgisOptimalAngles,
        surface_tilt_deg: pvgisOptimalAngles
          ? undefined
          : Number.parseFloat(pvgisSurfaceTiltDeg) || 0,
        surface_azimuth_deg: pvgisOptimalAngles
          ? undefined
          : Number.parseFloat(pvgisSurfaceAzimuthDeg) || 0,
        force_refresh: forceRefresh,
      });
      setPvgisProfile(data);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "PVGIS profile fetch failed"));
    } finally {
      setPvgisLoading(false);
    }
  }

  function clearPVGISProfile() {
    setPvgisProfile(null);
  }

  async function handleFetchPVGISClick(forceRefresh: boolean) {
    await handleFetchPVGIS(forceRefresh);
  }

  async function handleSimulate() {
    if (!selectedResult) {
      setError("Run at least one scenario first so Green Energy can reuse a real site + scenario.");
      return;
    }

    if (!hourlyPvKw && pvgisProfile && parsedPvCapacityKwp <= 0) {
      setError("Set installed PV capacity above 0 kWp before using the cached PVGIS normalized profile.");
      return;
    }

    setRunning(true);
    setError(null);

    try {
      const data = await api.simulateScenarioGreen({
        site_id: selectedResult.site_id,
        scenario: selectedResult.scenario,
        hourly_pv_kw: hourlyPvKw,
        pvgis_profile_key: hourlyPvKw ? undefined : pvgisProfile?.profile_key,
        pv_capacity_kwp: parsedPvCapacityKwp,
        bess_capacity_kwh: Number.parseFloat(bessCapacityKwh) || 0,
        bess_roundtrip_efficiency: Number.parseFloat(bessEfficiency) || 0.875,
        bess_initial_soc_kwh: Number.parseFloat(bessInitialSocKwh) || 0,
        fuel_cell_capacity_kw: Number.parseFloat(fuelCellKw) || 0,
        grid_co2_kg_per_kwh: Number.parseFloat(co2Factor) || 0.256,
        include_hourly_dispatch: false,
      });
      setResult(data);
      setResultSelectionKey(selectedScenarioKey);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Green dispatch simulation failed"));
    } finally {
      setRunning(false);
    }
  }

  if (results.length === 0) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center text-gray-400">
          <Leaf size={48} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm text-gray-600">Run scenarios first so this page can consume a real saved site + scenario.</p>
          <p className="text-xs mt-2 text-gray-500">
            The placeholder constant-load mode has been removed. This page now uses verified hourly facility and IT arrays from the backend.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Green Energy</h2>
        <p className="text-sm text-gray-500 mt-1">
          Simulate PV, BESS, and fuel-cell dispatch on the real hourly facility and IT arrays of a selected scenario
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-4 space-y-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 space-y-4">
            <div>
              <h3 className="font-semibold text-gray-800">Scenario Source</h3>
              <p className="text-xs text-gray-500 mt-1">
                The backend recomputes the hourly weather-driven facility and IT arrays from this saved scenario.
              </p>
            </div>

            <label className="block">
              <span className="block text-xs font-medium text-gray-600 mb-1">Scenario Result</span>
              <select
                value={selectedIndex ?? 0}
                onChange={(e) => selectResult(Number.parseInt(e.target.value, 10))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none"
              >
                {results.map((entry, index) => (
                  <option key={`${entry.site_id}-${index}`} value={index}>
                    {entry.site_name} · {entry.scenario.load_type} · {entry.scenario.cooling_type}
                  </option>
                ))}
              </select>
            </label>

            {selectedResult && (
              <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-xs text-blue-800">
                <p className="font-medium">{selectedResult.site_name}</p>
                <p className="mt-1">{selectedResult.scenario.load_type}</p>
                <p className="mt-1">{selectedResult.scenario.cooling_type}</p>
                <p className="mt-1">
                  Committed IT {getCommittedItMw(selectedResult).toFixed(2)} MW · PUE source {selectedResult.pue_source}
                </p>
              </div>
            )}
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Sun size={18} className="text-amber-500" />
              <h3 className="font-semibold text-gray-800">PV Profile</h3>
            </div>

            <label className="block">
              <span className="block text-xs font-medium text-gray-600 mb-1">Installed PV Capacity (kWp)</span>
              <input
                type="number"
                min="0"
                value={pvCapacityKwp}
                onChange={(e) => setPvCapacityKwp(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </label>

            {selectedResult && (
              <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-900 space-y-1">
                <p className="font-medium">Saved site coordinates</p>
                <p>
                  {selectedResult.site_name} · {selectedResult.site_id}
                </p>
                <p>
                  PVGIS fetch uses the saved site latitude/longitude from the backend, including coordinates imported from KML/KMZ.
                </p>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">Start Year</span>
                <input
                  type="number"
                  value={pvgisStartYear}
                  onChange={(e) => setPvgisStartYear(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">End Year</span>
                <input
                  type="number"
                  value={pvgisEndYear}
                  onChange={(e) => setPvgisEndYear(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">PV Technology</span>
                <select
                  value={pvgisTechnology}
                  onChange={(e) => setPvgisTechnology(e.target.value as PVGISProfileResult["pv_technology"])}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none"
                >
                  <option value="crystSi">crystSi</option>
                  <option value="CIS">CIS</option>
                  <option value="CdTe">CdTe</option>
                  <option value="Unknown">Unknown</option>
                </select>
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">Mounting Place</span>
                <select
                  value={pvgisMountingPlace}
                  onChange={(e) => setPvgisMountingPlace(e.target.value as PVGISProfileResult["mounting_place"])}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none"
                >
                  <option value="free">free</option>
                  <option value="building">building</option>
                </select>
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">System Loss (%)</span>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={pvgisSystemLossPct}
                  onChange={(e) => setPvgisSystemLossPct(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </label>
              <label className="block col-span-2">
                <span className="block text-xs font-medium text-gray-600 mb-1">PVGIS Options</span>
                <div className="flex flex-wrap gap-4 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-700">
                  <label className="inline-flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={pvgisUseHorizon}
                      onChange={(e) => setPvgisUseHorizon(e.target.checked)}
                    />
                    Use horizon
                  </label>
                  <label className="inline-flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={pvgisOptimalAngles}
                      onChange={(e) => setPvgisOptimalAngles(e.target.checked)}
                    />
                    Use PVGIS optimal fixed angles
                  </label>
                </div>
              </label>
              {!pvgisOptimalAngles && (
                <>
                  <label className="block">
                    <span className="block text-xs font-medium text-gray-600 mb-1">Surface Tilt (deg)</span>
                    <input
                      type="number"
                      min="0"
                      max="90"
                      step="0.1"
                      value={pvgisSurfaceTiltDeg}
                      onChange={(e) => setPvgisSurfaceTiltDeg(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </label>
                  <label className="block">
                    <span className="block text-xs font-medium text-gray-600 mb-1">Surface Azimuth (deg)</span>
                    <input
                      type="number"
                      min="-180"
                      max="180"
                      step="0.1"
                      value={pvgisSurfaceAzimuthDeg}
                      onChange={(e) => setPvgisSurfaceAzimuthDeg(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                    />
                  </label>
                </>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => void handleFetchPVGISClick(false)}
                disabled={pvgisLoading || !selectedResult}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-amber-500 text-white rounded-lg hover:bg-amber-600 disabled:opacity-50 text-sm font-medium"
              >
                {pvgisLoading ? <Loader2 size={16} className="animate-spin" /> : <Sun size={16} />}
                {pvgisLoading ? "Fetching PVGIS..." : "Fetch PVGIS 1 kWp"}
              </button>
              <button
                type="button"
                onClick={() => void handleFetchPVGISClick(true)}
                disabled={pvgisLoading || !selectedResult}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-white text-amber-700 border border-amber-300 rounded-lg hover:bg-amber-50 disabled:opacity-50 text-sm font-medium"
              >
                Refresh PVGIS Cache
              </button>
            </div>

            <label className="block">
              <span className="block text-xs font-medium text-gray-600 mb-1">Hourly PV CSV (optional override)</span>
              <input
                type="file"
                accept=".csv,.txt"
                onChange={(e) => void handlePvFileChange(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-gray-600"
              />
            </label>

            <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-xs text-gray-600 space-y-2">
              <p>{pvProfileSummary}</p>
              {pvgisProfile && (
                <div className="grid grid-cols-2 gap-2 text-[11px] text-gray-500">
                  <p>Cache key: {pvgisProfile.profile_key}</p>
                  <p>{pvgisProfile.from_cache ? "Cache hit" : "Fresh PVGIS fetch"}</p>
                  <p>Latitude: {pvgisProfile.latitude.toFixed(6)}</p>
                  <p>Longitude: {pvgisProfile.longitude.toFixed(6)}</p>
                  <p>PVGIS years: {pvgisProfile.start_year}–{pvgisProfile.end_year}</p>
                  <p>Hours: {pvgisProfile.hours.toLocaleString()}</p>
                  <p>Tilt: {formatOptionalNumber(pvgisProfile.surface_tilt_deg)} deg</p>
                  <p>Azimuth: {formatOptionalNumber(pvgisProfile.surface_azimuth_deg)} deg</p>
                </div>
              )}
              <div className="flex flex-wrap gap-3">
                {pvProfileName && (
                  <button
                    type="button"
                    onClick={() => void handlePvFileChange(null)}
                    className="text-blue-600 hover:text-blue-800"
                  >
                    Clear Manual PV
                  </button>
                )}
                {pvgisProfile && (
                  <button
                    type="button"
                    onClick={clearPVGISProfile}
                    className="text-blue-600 hover:text-blue-800"
                  >
                    Clear PVGIS Profile
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Battery size={18} className="text-green-500" />
              <h3 className="font-semibold text-gray-800">Storage & Dispatch</h3>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">BESS Capacity (kWh)</span>
                <input
                  type="number"
                  min="0"
                  value={bessCapacityKwh}
                  onChange={(e) => setBessCapacityKwh(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">Initial SoC (kWh)</span>
                <input
                  type="number"
                  min="0"
                  value={bessInitialSocKwh}
                  onChange={(e) => setBessInitialSocKwh(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">BESS Roundtrip Efficiency</span>
                <input
                  type="number"
                  min="0.5"
                  max="1"
                  step="0.001"
                  value={bessEfficiency}
                  onChange={(e) => setBessEfficiency(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </label>
              <label className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">Fuel Cell (kW)</span>
                <input
                  type="number"
                  min="0"
                  value={fuelCellKw}
                  onChange={(e) => setFuelCellKw(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </label>
              <label className="block col-span-2">
                <span className="block text-xs font-medium text-gray-600 mb-1">Grid CO₂ (kg/kWh)</span>
                <input
                  type="number"
                  min="0"
                  step="0.001"
                  value={co2Factor}
                  onChange={(e) => setCo2Factor(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                />
              </label>
            </div>

            <button
              type="button"
              onClick={handleSimulate}
              disabled={running}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium"
            >
              {running ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {running ? "Simulating..." : "Run Green Dispatch"}
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
            <div className="space-y-6">
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
                <div className="flex items-start justify-between gap-4 mb-4">
                  <div>
                    <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                      <Leaf size={18} className="text-green-500" />
                      Dispatch Results
                    </h3>
                    <p className="text-xs text-gray-500 mt-1">
                      {result.site_name} · {result.hours.toLocaleString()} hours · annual PUE {result.annual_pue.toFixed(3)}
                    </p>
                  </div>
                  <div className="text-right text-xs text-gray-500">
                    <p>Nominal IT {result.nominal_it_mw.toFixed(2)} MW</p>
                    <p>Committed IT {result.committed_it_mw.toFixed(2)} MW</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  <GreenMetric label="Renewable Fraction" value={`${(result.renewable_fraction * 100).toFixed(1)}%`} highlight />
                  <GreenMetric label="Overhead Coverage" value={`${(result.overhead_coverage_fraction * 100).toFixed(1)}%`} highlight />
                  <GreenMetric label="CO₂ Avoided" value={`${result.co2_avoided_tonnes.toFixed(1)} t/yr`} />
                  <GreenMetric label="PV Self-Consumption" value={`${(result.pv_self_consumption_fraction * 100).toFixed(1)}%`} />
                  <GreenMetric label="BESS Cycles/Year" value={result.bess_cycles_equivalent.toFixed(1)} />
                  <GreenMetric label="Grid Import" value={`${(result.total_grid_import_kwh / 1000).toFixed(1)} MWh`} />
                </div>
              </div>

              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
                <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
                  <Zap size={18} className="text-purple-500" />
                  Annual Energy Breakdown
                </h3>
                <div className="space-y-2">
                  <EnergyRow label="Total Facility" value={result.total_facility_kwh} color="bg-gray-400" />
                  <EnergyRow label="Total IT" value={result.total_it_kwh} color="bg-gray-300" />
                  <EnergyRow label="Total Overhead" value={result.total_overhead_kwh} color="bg-gray-200" />
                  <div className="border-t border-gray-100 pt-2 mt-2" />
                  <EnergyRow label="PV Generation" value={result.total_pv_generation_kwh} color="bg-amber-400" />
                  <EnergyRow label="PV -> Overhead" value={result.total_pv_to_overhead_kwh} color="bg-green-400" />
                  <EnergyRow label="PV -> BESS" value={result.total_pv_to_bess_kwh} color="bg-blue-400" />
                  <EnergyRow label="BESS Discharge" value={result.total_bess_discharge_kwh} color="bg-purple-400" />
                  <EnergyRow label="Fuel Cell" value={result.total_fuel_cell_kwh} color="bg-indigo-400" />
                  <EnergyRow label="Grid Import" value={result.total_grid_import_kwh} color="bg-red-300" />
                  <EnergyRow label="PV Curtailed" value={result.total_pv_curtailed_kwh} color="bg-gray-200" />
                </div>
              </div>

              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
                <h3 className="font-semibold text-gray-800 mb-3">Configuration Used</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs text-gray-600">
                  <p>PV metadata: {result.pv_capacity_kwp.toFixed(0)} kWp</p>
                  <p>BESS: {result.bess_capacity_kwh.toFixed(0)} kWh</p>
                  <p>BESS η: {(result.bess_roundtrip_efficiency * 100).toFixed(1)}%</p>
                  <p>Fuel Cell: {result.fuel_cell_capacity_kw.toFixed(0)} kW</p>
                  <p>PV profile: {describeActivePvSource(result.pv_profile_source ?? activePvSource, pvProfileName)}</p>
                  <p>CO₂ factor: {Number.parseFloat(co2Factor || "0").toFixed(3)} kg/kWh</p>
                  {result.pvgis_profile_key && <p>PVGIS key: {result.pvgis_profile_key}</p>}
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center text-gray-400">
              <Leaf size={48} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">Configure support assets and optionally upload a PV profile, then run the simulation.</p>
              <p className="text-xs mt-1">This page now uses the selected scenario’s real hourly facility and IT arrays from the backend.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


function parsePvSeries(text: string): number[] {
  const values: number[] = [];

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;

    const cells = line.split(/[,;\t]/).map((cell) => cell.trim());
    const numericCells = cells
      .map((cell) => Number.parseFloat(cell))
      .filter((value) => Number.isFinite(value));

    if (numericCells.length > 0) {
      values.push(numericCells[numericCells.length - 1]);
    }
  }

  return values;
}


function getApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      return detail
        .map((item) => {
          if (typeof item === "string") {
            return item;
          }
          if (item && typeof item === "object" && "msg" in item) {
            return String(item.msg);
          }
          return JSON.stringify(item);
        })
        .join("; ");
    }
    if (typeof error.message === "string" && error.message.trim()) {
      return error.message;
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return fallback;
}


function getPvProfileSummary({
  activePvSource,
  hourlyPvKw,
  pvProfileName,
  pvgisProfile,
}: {
  activePvSource: "manual" | "pvgis" | "zero";
  hourlyPvKw?: number[];
  pvProfileName: string | null;
  pvgisProfile: PVGISProfileResult | null;
}): string {
  if (activePvSource === "manual" && hourlyPvKw && pvProfileName) {
    return (
      `${hourlyPvKw.length.toLocaleString()} hourly values loaded from ${pvProfileName}. ` +
      "Manual upload currently overrides the cached PVGIS profile."
    );
  }

  if (activePvSource === "pvgis" && pvgisProfile) {
    return (
      `${pvgisProfile.hours.toLocaleString()} hourly values loaded from ${pvgisProfile.source}. ` +
      `${pvgisProfile.from_cache ? "The cached profile is active." : "A fresh PVGIS fetch is active."}`
    );
  }

  return "No PV profile is active. The simulation will run with zero PV.";
}


function formatOptionalNumber(value: number | null): string {
  if (value === null) {
    return "auto";
  }
  return value.toFixed(1);
}


function describeActivePvSource(
  source: "manual" | "pvgis" | "zero",
  pvProfileName: string | null,
): string {
  if (source === "manual") {
    return pvProfileName ? `Manual CSV (${pvProfileName})` : "Manual CSV";
  }
  if (source === "pvgis") {
    return "PVGIS normalized profile";
  }
  return "Zero PV";
}


function GreenMetric({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-lg font-semibold mt-0.5 ${highlight ? "text-green-600" : "text-gray-900"}`}>
        {value}
      </p>
    </div>
  );
}


function EnergyRow({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <div className="flex items-center gap-2">
        <span className={`w-3 h-3 rounded-sm ${color}`} />
        <span className="text-gray-700">{label}</span>
      </div>
      <span className="font-mono text-gray-900">
        {(value / 1000).toFixed(1)} MWh
      </span>
    </div>
  );
}


function getCommittedItMw(result: ScenarioResult): number {
  return result.it_capacity_p99_mw ?? result.power.it_load_mw;
}
