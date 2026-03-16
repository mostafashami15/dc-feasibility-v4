/**
 * ClimateAnalysis — Page 2: Climate & Weather
 * =============================================
 * Redesigned: collapsible data-source panels, reduced verbosity.
 *
 * Weather flow:
 *   1. Select a site
 *   2. Fetch from Open-Meteo OR upload manual CSV (collapsible panels)
 *   3. Once cached → auto-runs climate analysis
 *   4. Results: temperature stats, monthly chart, free cooling, delta projections
 *
 * How weather affects scenarios:
 *   The cached 8,760-hour temperature+humidity profile drives the hourly
 *   PUE simulation engine. Each hour's ambient temperature determines the
 *   cooling COP, which directly influences IT capacity and energy-weighted
 *   annual PUE. Without weather data, scenarios use static PUE defaults.
 */

import { useRef, useState } from "react";
import {
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Cloud,
  Download,
  FileText,
  Loader2,
  Thermometer,
  Trash2,
  Upload,
  Wind,
} from "lucide-react";
import { useAppStore } from "../store/useAppStore";
import * as api from "../api/client";
import type {
  ClimateAnalysis as ClimateAnalysisType,
  WeatherStatus,
} from "../types";
import TemperatureChart from "../components/charts/TemperatureChart";
import FreeCoolingChart from "../components/charts/FreeCoolingChart";


function describeApiError(err: unknown, fallback: string) {
  if (typeof err === "object" && err !== null && "response" in err) {
    return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? fallback;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}


function formatWeatherSourceBadge(status: WeatherStatus | null) {
  if (!status?.source_type) return "Cached";
  if (status.source_type === "manual_upload") return "Manual CSV";
  if (status.source_type === "open_meteo_archive") return "Open-Meteo";
  return status.source_type;
}

function formatWeatherSourceSummary(status: WeatherStatus | null) {
  if (!status) return "No weather cached.";
  if (status.source_type === "manual_upload") {
    return status.original_filename ? `Manual CSV: ${status.original_filename}` : "Manual CSV cached.";
  }
  if (status.source_type === "open_meteo_archive") {
    const years = status.years_averaged?.length ? ` (${status.years_averaged.join(", ")})` : "";
    return `Open-Meteo representative year${years}`;
  }
  return status.source ?? "Weather cached.";
}


// ── Collapsible Panel ──
function Panel({
  title, icon, defaultOpen = false, badge, children,
}: {
  title: string;
  icon: React.ReactNode;
  defaultOpen?: boolean;
  badge?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full p-4 flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-2">
          {icon}
          <h3 className="font-semibold text-gray-800 text-sm">{title}</h3>
          {badge && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium">
              {badge}
            </span>
          )}
        </div>
        {open ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
      </button>
      {open && <div className="border-t border-gray-100 p-4">{children}</div>}
    </div>
  );
}


export default function ClimateAnalysis() {
  const sites = useAppStore((s) => s.sites);
  const loadSites = useAppStore((s) => s.loadSites);

  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);
  const [weatherStatus, setWeatherStatus] = useState<WeatherStatus | null>(null);
  const [selectedUploadFile, setSelectedUploadFile] = useState<File | null>(null);
  const [uploadInputKey, setUploadInputKey] = useState(0);
  const [fetching, setFetching] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [analysing, setAnalysing] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<ClimateAnalysisType | null>(null);
  const [deltaOffset, setDeltaOffset] = useState(0);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);

  const selectedSite = sites.find((site) => site.id === selectedSiteId);
  const hasCachedWeather = weatherStatus?.has_weather ?? selectedSite?.has_weather ?? false;
  const siteHasCoordinates =
    selectedSite?.site.latitude != null && selectedSite?.site.longitude != null;


  // ── Actions ──

  async function refreshWeatherStatus(siteId: string) {
    try {
      const status = await api.getWeatherStatus(siteId);
      setWeatherStatus(status);
      return status;
    } catch {
      setWeatherStatus(null);
      return null;
    }
  }

  async function runAnalysis(siteId: string, delta: number) {
    setAnalysing(true);
    setAnalysisError(null);
    try {
      const deltas = delta > 0 ? [delta] : [0.5, 1.0, 1.5, 2.0];
      const result = await api.analyseSite({ site_id: siteId, deltas });
      setAnalysis(result);
    } catch (err: unknown) {
      setAnalysis(null);
      setAnalysisError(describeApiError(err, "Climate analysis failed."));
    } finally {
      setAnalysing(false);
    }
  }

  async function handleFetchWeather() {
    if (!selectedSiteId) return;
    if (weatherStatus?.source_type === "manual_upload" &&
        !window.confirm("Replace manual CSV with Open-Meteo data?")) return;

    setFetching(true);
    setFetchError(null);
    try {
      const status = await api.fetchWeather({
        site_id: selectedSiteId,
        force_refresh: weatherStatus?.source_type === "manual_upload",
      });
      setWeatherStatus(status);
      await runAnalysis(selectedSiteId, deltaOffset);
      await loadSites();
    } catch (err: unknown) {
      setFetchError(describeApiError(err, "Weather fetch failed."));
    } finally {
      setFetching(false);
    }
  }

  async function handleUploadWeather() {
    if (!selectedSiteId || !selectedUploadFile) return;
    if (hasCachedWeather && !window.confirm("Replace current weather cache with this CSV?")) return;

    setUploading(true);
    setUploadError(null);
    try {
      const status = await api.uploadWeatherFile(selectedSiteId, selectedUploadFile);
      setWeatherStatus(status);
      setSelectedUploadFile(null);
      setUploadInputKey((c) => c + 1);
      await runAnalysis(selectedSiteId, deltaOffset);
      await loadSites();
    } catch (err: unknown) {
      setUploadError(describeApiError(err, "Upload failed."));
    } finally {
      setUploading(false);
    }
  }

  function clearSelectedUploadFile() {
    setSelectedUploadFile(null);
    setUploadInputKey((c) => c + 1);
    setUploadError(null);
  }

  async function handleDeleteCachedWeather() {
    if (!selectedSiteId || !hasCachedWeather) return;
    if (!window.confirm("Delete cached weather for this site?")) return;

    setUploading(true);
    try {
      await api.deleteWeatherCache(selectedSiteId);
      setWeatherStatus({ site_id: selectedSiteId, has_weather: false });
      setAnalysis(null);
      clearSelectedUploadFile();
      await loadSites();
    } catch (err: unknown) {
      setUploadError(describeApiError(err, "Failed to delete cached weather."));
    } finally {
      setUploading(false);
    }
  }

  async function handleSiteChange(siteId: string) {
    if (!siteId) {
      setSelectedSiteId(null);
      setWeatherStatus(null);
      clearSelectedUploadFile();
      setAnalysis(null);
      setFetchError(null);
      setAnalysisError(null);
      return;
    }

    setSelectedSiteId(siteId);
    setWeatherStatus(null);
    clearSelectedUploadFile();
    setAnalysis(null);
    setFetchError(null);
    setAnalysisError(null);

    const site = sites.find((e) => e.id === siteId);
    if (site?.has_weather) {
      await refreshWeatherStatus(siteId);
      await runAnalysis(siteId, deltaOffset);
    }
  }

  async function handleDeltaChange(value: number) {
    setDeltaOffset(value);
    if (selectedSiteId && hasCachedWeather) await runAnalysis(selectedSiteId, value);
  }


  // ── Render ──

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Climate & Weather</h2>
        <p className="text-sm text-gray-500 mt-1">
          Fetch or upload hourly weather data — drives the 8,760-hour PUE simulation in scenarios.
        </p>
      </div>

      {/* Site Selector + Weather Status */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 mb-6">
        <div className="flex items-end gap-4 flex-wrap">
          <div className="flex-1 min-w-[220px]">
            <label className="block text-xs font-medium text-gray-600 mb-1">Select Site</label>
            <select
              value={selectedSiteId ?? ""}
              onChange={(e) => void handleSiteChange(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none"
            >
              <option value="">Choose a site...</option>
              {sites.map((site) => (
                <option key={site.id} value={site.id}>
                  {site.site.name}
                  {site.has_weather ? " ✓" : ""}
                  {site.site.latitude == null ? " (no coords)" : ""}
                </option>
              ))}
            </select>
          </div>

          {hasCachedWeather && (
            <div className="flex items-center gap-2 pb-2">
              <span className="text-xs text-green-700 flex items-center gap-1">
                <Cloud size={14} /> {formatWeatherSourceBadge(weatherStatus)}
              </span>
              <button
                type="button"
                onClick={handleDeleteCachedWeather}
                disabled={uploading}
                className="text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
                title="Delete cached weather"
              >
                <Trash2 size={13} />
              </button>
            </div>
          )}
        </div>

        {/* Compact weather status */}
        {selectedSiteId && weatherStatus && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-gray-600">
            <span className="font-medium">{formatWeatherSourceSummary(weatherStatus)}</span>
            <span className="text-gray-300">·</span>
            <span>{(weatherStatus.hours ?? 0).toLocaleString()} hours</span>
            <span className="text-gray-300">·</span>
            <span>{weatherStatus.has_humidity ? "With humidity" : "Dry-bulb only"}</span>
            {weatherStatus.years_averaged && weatherStatus.years_averaged.length > 0 && (
              <>
                <span className="text-gray-300">·</span>
                <span>Years: {weatherStatus.years_averaged.join(", ")}</span>
              </>
            )}
          </div>
        )}

        {!selectedSiteId && (
          <p className="mt-2 text-xs text-gray-400">Select a site to manage its weather data.</p>
        )}
      </div>

      {/* ── Data Source Panels (collapsible) ── */}
      {selectedSiteId && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-6">
          {/* Open-Meteo Fetch */}
          <Panel
            title="Open-Meteo Fetch"
            icon={<Cloud size={16} className="text-blue-500" />}
            defaultOpen={!hasCachedWeather}
            badge={siteHasCoordinates ? undefined : "No coords"}
          >
            <p className="text-xs text-gray-500 mb-3">
              Downloads a representative-year hourly profile from Open-Meteo based on site coordinates.
            </p>
            <button
              type="button"
              onClick={handleFetchWeather}
              disabled={!selectedSiteId || fetching || !siteHasCoordinates}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
            >
              {fetching ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
              {fetching ? "Fetching..." : "Fetch Weather"}
            </button>
            {!siteHasCoordinates && (
              <p className="mt-2 text-[11px] text-amber-600">Site needs coordinates for Open-Meteo. Use manual CSV instead.</p>
            )}
            {fetchError && (
              <div className="mt-3 p-2.5 bg-red-50 border border-red-200 text-red-700 rounded-lg text-xs flex items-center gap-2">
                <AlertCircle size={14} /> {fetchError}
              </div>
            )}
          </Panel>

          {/* Manual CSV Upload */}
          <Panel
            title="Manual Weather CSV"
            icon={<Upload size={16} className="text-emerald-600" />}
            defaultOpen={false}
          >
            <p className="text-xs text-gray-500 mb-3">
              Upload site-specific hourly data (8,760 rows). Required column: <code className="px-1 py-0.5 bg-gray-100 rounded text-[10px]">dry_bulb_c</code>. Optional: <code className="px-1 py-0.5 bg-gray-100 rounded text-[10px]">relative_humidity_pct</code>.
            </p>
            <input
              ref={uploadInputRef}
              key={uploadInputKey}
              type="file"
              accept=".csv"
              onChange={(e) => setSelectedUploadFile(e.target.files?.[0] ?? null)}
              className="hidden"
            />
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => uploadInputRef.current?.click()}
                className="flex items-center gap-1.5 px-3 py-2 bg-white text-emerald-700 border border-emerald-300 rounded-lg hover:bg-emerald-50 text-xs font-medium"
              >
                <FileText size={14} /> Choose CSV
              </button>
              {selectedUploadFile && (
                <>
                  <span className="text-xs text-gray-600 truncate max-w-[150px]">{selectedUploadFile.name}</span>
                  <button
                    type="button"
                    onClick={handleUploadWeather}
                    disabled={uploading}
                    className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 text-xs font-medium"
                  >
                    {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                    Upload
                  </button>
                  <button type="button" onClick={clearSelectedUploadFile} className="text-xs text-gray-400 hover:text-gray-600">
                    Clear
                  </button>
                </>
              )}
            </div>
            {uploadError && (
              <div className="mt-3 p-2.5 bg-red-50 border border-red-200 text-red-700 rounded-lg text-xs flex items-center gap-2">
                <AlertCircle size={14} /> {uploadError}
              </div>
            )}
          </Panel>
        </div>
      )}

      {/* Info when no weather */}
      {selectedSiteId && !hasCachedWeather && !fetchError && !uploadError && (
        <div className="mb-6 rounded-xl border border-gray-200 bg-white px-4 py-3 text-xs text-gray-500">
          No weather cached. Fetch from Open-Meteo or upload a CSV to enable climate analysis and hourly PUE simulation.
        </div>
      )}

      {analysisError && (
        <div className="mb-6 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm flex items-center gap-2">
          <AlertCircle size={16} /> {analysisError}
        </div>
      )}

      {analysing && (
        <div className="text-center py-8 text-gray-400">
          <Loader2 className="animate-spin mx-auto mb-2" size={24} />
          Analysing climate data...
        </div>
      )}

      {/* ── Analysis Results ── */}
      {analysis && !analysing && (
        <div className="space-y-5">
          {/* Temperature Stats */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2 text-sm">
              <Thermometer size={16} className="text-red-500" />
              Temperature Statistics
            </h3>
            <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
              <StatCard label="Mean" value={`${analysis.temperature_stats.mean.toFixed(1)}°C`} />
              <StatCard label="Min" value={`${analysis.temperature_stats.min.toFixed(1)}°C`} />
              <StatCard label="Max" value={`${analysis.temperature_stats.max.toFixed(1)}°C`} />
              <StatCard label="P1 (cold)" value={`${analysis.temperature_stats.p1.toFixed(1)}°C`} />
              <StatCard label="P99 (hot)" value={`${analysis.temperature_stats.p99.toFixed(1)}°C`} />
            </div>
          </div>

          {/* Monthly Chart */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
            <h3 className="font-semibold text-gray-800 mb-3 text-sm">Monthly Temperature Profile</h3>
            <TemperatureChart monthlyStats={analysis.monthly_stats} />
          </div>

          {/* Free Cooling */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2 text-sm">
              <Wind size={16} className="text-green-500" />
              Free Cooling Analysis
            </h3>
            <FreeCoolingChart freeCooling={analysis.free_cooling} />
          </div>

          {/* Delta Projections */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
            <h3 className="font-semibold text-gray-800 mb-1 text-sm">Climate Projection (Delta Approach)</h3>
            <p className="text-[11px] text-gray-500 mb-3">
              CIBSE TM49 / IPCC AR6 SSP2-4.5 — uniform temperature shift on hourly profile.
            </p>

            <div className="flex items-center gap-4 mb-3">
              <label className="text-sm text-gray-700 font-medium whitespace-nowrap">
                ΔT = +{deltaOffset.toFixed(1)}°C
              </label>
              <input
                type="range" min={0} max={3} step={0.5}
                value={deltaOffset}
                onChange={(e) => void handleDeltaChange(Number.parseFloat(e.target.value))}
                className="flex-1 accent-blue-600"
              />
              <span className="text-xs text-gray-400">+3.0°C</span>
            </div>

            {Object.keys(analysis.delta_results).length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-gray-600">Delta</th>
                      <th className="px-3 py-2 text-left text-gray-600">Cooling Type</th>
                      <th className="px-3 py-2 text-right text-gray-600">Free Hours</th>
                      <th className="px-3 py-2 text-right text-gray-600">%</th>
                      <th className="px-3 py-2 text-center text-gray-600">Rating</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {Object.entries(analysis.delta_results).map(([delta, fcList]) =>
                      fcList.map((fc, index) => (
                        <tr key={`${delta}-${index}`} className="hover:bg-gray-50">
                          <td className="px-3 py-2 text-gray-700 font-mono">+{Number.parseFloat(delta).toFixed(1)}°C</td>
                          <td className="px-3 py-2 text-gray-700">{fc.cooling_type}</td>
                          <td className="px-3 py-2 text-right font-mono">{fc.free_cooling_hours.toLocaleString()}</td>
                          <td className="px-3 py-2 text-right font-mono">{(fc.free_cooling_fraction * 100).toFixed(1)}%</td>
                          <td className="px-3 py-2 text-center">
                            <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${
                              fc.suitability === "EXCELLENT" ? "bg-blue-100 text-blue-700" :
                              fc.suitability === "GOOD" ? "bg-green-100 text-green-700" :
                              fc.suitability === "MARGINAL" ? "bg-amber-100 text-amber-700" :
                              "bg-red-100 text-red-700"
                            }`}>
                              {fc.suitability.replace("_", " ")}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}


function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 rounded-lg p-2.5">
      <p className="text-[10px] text-gray-500">{label}</p>
      <p className="text-sm font-semibold text-gray-900 mt-0.5">{value}</p>
    </div>
  );
}
