import { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle,
  Cloud,
  Database,
  ChevronDown,
  ChevronRight,
  History as HistoryIcon,
  Loader2,
  RefreshCw,
  Save,
  Settings as SettingsIcon,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  Wifi,
  WifiOff,
  Zap,
} from "lucide-react";
import CollapsibleSection from "../components/ui/CollapsibleSection";
import * as api from "../api/client";
import { useAppStore } from "../store/useAppStore";
import type {
  CacheClearResult,
  AssumptionOverrideEntry,
  AssumptionOverrideHistoryEntry,
  AssumptionOverrideHistoryResponse,
  AssumptionOverridePresetsResponse,
  AssumptionOverridesResponse,
  ExternalServicesResult,
  RuntimeStatus,
} from "../types";


type NoticeTone = "success" | "error" | "info";

type OverrideDraft = {
  overrideValue: string;
  source: string;
  justification: string;
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


function buildOverrideDrafts(entries: AssumptionOverrideEntry[]): Record<string, OverrideDraft> {
  return Object.fromEntries(
    entries.map((entry) => [
      entry.key,
      {
        overrideValue: entry.override ? String(entry.override.value) : "",
        source: entry.override?.source ?? "",
        justification: entry.override?.justification ?? "",
      },
    ])
  );
}


function formatAssumptionValue(value: number, unit: string) {
  if (unit === "fraction") {
    return value.toFixed(3);
  }
  if (unit === "eta") {
    return value.toFixed(3);
  }
  if (unit === "PUE" || unit === "COP") {
    return value.toFixed(2);
  }
  return String(value);
}


function formatImpactScope(impactScope: AssumptionOverrideEntry["impact_scope"]) {
  return impactScope === "hourly_only"
    ? "Hourly weather runs only"
    : "Static solve + hourly runs";
}


function formatHistoryAction(action: "activated" | "updated" | "cleared" | "preset_applied") {
  if (action === "activated") {
    return "Activated";
  }
  if (action === "updated") {
    return "Updated";
  }
  if (action === "cleared") {
    return "Cleared";
  }
  return "Preset Applied";
}


function getDensityValue(
  profile: {
    density_kw?: { low: number; typical: number; high: number };
    density_low_kw?: number;
    density_typical_kw?: number;
    density_high_kw?: number;
  },
  key: "low" | "typical" | "high"
) {
  if (profile.density_kw) {
    return profile.density_kw[key];
  }
  if (key === "low") {
    return profile.density_low_kw ?? 0;
  }
  if (key === "typical") {
    return profile.density_typical_kw ?? 0;
  }
  return profile.density_high_kw ?? 0;
}


export default function Settings() {
  const backendConnected = useAppStore((s) => s.backendConnected);
  const backendHealth = useAppStore((s) => s.backendHealth);
  const checkBackend = useAppStore((s) => s.checkBackend);
  const referenceData = useAppStore((s) => s.referenceData);
  const sites = useAppStore((s) => s.sites);
  const loadSites = useAppStore((s) => s.loadSites);

  const [testingBackend, setTestingBackend] = useState(false);
  const [serviceTesting, setServiceTesting] = useState(false);
  const [maintenanceAction, setMaintenanceAction] = useState<
    "weather" | "solar" | "sites" | null
  >(null);
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [serviceStatus, setServiceStatus] = useState<ExternalServicesResult | null>(null);
  const [assumptionState, setAssumptionState] = useState<AssumptionOverridesResponse | null>(null);
  const [presetCatalog, setPresetCatalog] = useState<AssumptionOverridePresetsResponse | null>(null);
  const [historyState, setHistoryState] = useState<AssumptionOverrideHistoryResponse | null>(null);
  const [assumptionDrafts, setAssumptionDrafts] = useState<Record<string, OverrideDraft>>({});
  const [assumptionLoading, setAssumptionLoading] = useState(false);
  const [assumptionSaving, setAssumptionSaving] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);
  const [statusTone, setStatusTone] = useState<NoticeTone>("info");
  const [assumptionNotice, setAssumptionNotice] = useState<string | null>(null);
  const [assumptionTone, setAssumptionTone] = useState<NoticeTone>("info");
  const [maintenanceNotice, setMaintenanceNotice] = useState<string | null>(null);
  const [maintenanceTone, setMaintenanceTone] = useState<NoticeTone>("info");

  async function refreshRuntimeStatus() {
    try {
      const status = await api.getRuntimeStatus();
      setRuntimeStatus(status);
    } catch {
      // Leave the previous snapshot in place if runtime status is unavailable.
    }
  }

  async function refreshAssumptionOverrides() {
    setAssumptionLoading(true);
    setAssumptionNotice(null);
    try {
      const response = await api.getAssumptionOverrides();
      setAssumptionState(response);
      setAssumptionDrafts(buildOverrideDrafts(response.assumptions));
    } catch (err) {
      setAssumptionTone("error");
      setAssumptionNotice(describeApiError(err, "Failed to load controlled assumption overrides."));
    } finally {
      setAssumptionLoading(false);
    }
  }

  async function refreshAssumptionPresets() {
    try {
      const response = await api.getAssumptionOverridePresets();
      setPresetCatalog(response);
    } catch {
      // Preset browsing is additive to Settings; keep the rest of the page usable.
    }
  }

  async function refreshAssumptionHistory() {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const response = await api.getAssumptionOverrideHistory(20);
      setHistoryState(response);
    } catch (err) {
      setHistoryError(describeApiError(err, "Failed to load override history."));
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    refreshRuntimeStatus();
    refreshAssumptionOverrides();
    refreshAssumptionPresets();
    refreshAssumptionHistory();
  }, []);

  async function refreshAfterMaintenance() {
    await Promise.all([
      refreshRuntimeStatus(),
      checkBackend(),
      loadSites(),
    ]);
  }

  async function handleTestConnection() {
    setTestingBackend(true);
    setStatusNotice(null);
    try {
      await checkBackend();
      const health = await api.checkHealth();
      await refreshRuntimeStatus();
      setStatusTone("success");
      setStatusNotice(
        `Connected - v${health.version}, ${health.sites_stored} sites, ${health.weather_cached} weather caches, ${health.solar_profiles_cached} solar profiles`
      );
    } catch (err) {
      setStatusTone("error");
      setStatusNotice(describeApiError(err, "Connection failed. Is the backend running on port 8000?"));
    } finally {
      setTestingBackend(false);
    }
  }

  async function handleTestExternalServices() {
    setServiceTesting(true);
    setStatusNotice(null);
    try {
      const result = await api.testExternalServices();
      setServiceStatus(result);
      const failed = result.services.filter((service) => !service.ok);
      if (failed.length === 0) {
        setStatusTone("success");
        setStatusNotice("All external services responded successfully.");
      } else {
        setStatusTone("info");
        setStatusNotice(
          `${failed.length} external service check${failed.length === 1 ? "" : "s"} need attention.`
        );
      }
    } catch (err) {
      setStatusTone("error");
      setStatusNotice(describeApiError(err, "External service checks failed."));
    } finally {
      setServiceTesting(false);
    }
  }

  async function handleClearCache(target: "weather" | "solar") {
    const label = target === "weather" ? "weather cache" : "solar cache";
    if (!window.confirm(`Clear the ${label} for all sites?`)) {
      return;
    }

    setMaintenanceAction(target);
    setMaintenanceNotice(null);
    try {
      const result = await api.clearServerCache(target);
      await refreshAfterMaintenance();
      setMaintenanceTone("success");
      setMaintenanceNotice(formatCacheNotice(result));
    } catch (err) {
      setMaintenanceTone("error");
      setMaintenanceNotice(describeApiError(err, `Failed to clear ${label}.`));
    } finally {
      setMaintenanceAction(null);
    }
  }

  async function handleClearAllSites() {
    if (!window.confirm(`Delete all ${sites.length} sites? This cannot be undone.`)) {
      return;
    }

    setMaintenanceAction("sites");
    setMaintenanceNotice(null);
    try {
      for (const site of sites) {
        await api.deleteSite(site.id);
      }
      await refreshAfterMaintenance();
      setMaintenanceTone("success");
      setMaintenanceNotice(`Deleted ${sites.length} site${sites.length === 1 ? "" : "s"} and their linked caches.`);
    } catch (err) {
      await refreshAfterMaintenance();
      setMaintenanceTone("error");
      setMaintenanceNotice(describeApiError(err, "Failed to delete all sites cleanly."));
    } finally {
      setMaintenanceAction(null);
    }
  }

  function updateDraft(
    key: string,
    field: keyof OverrideDraft,
    value: string
  ) {
    setAssumptionDrafts((current) => ({
      ...current,
      [key]: {
        ...(current[key] ?? { overrideValue: "", source: "", justification: "" }),
        [field]: value,
      },
    }));
  }

  function clearDraft(key: string) {
    setAssumptionDrafts((current) => ({
      ...current,
      [key]: {
        overrideValue: "",
        source: "",
        justification: "",
      },
    }));
  }

  async function handleSaveAssumptions() {
    if (!assumptionState) {
      return;
    }

    setAssumptionSaving(true);
    setAssumptionNotice(null);

    try {
      const updates = assumptionState.assumptions.map((entry) => {
        const draft = assumptionDrafts[entry.key] ?? {
          overrideValue: "",
          source: "",
          justification: "",
        };
        const rawValue = draft.overrideValue.trim();
        if (rawValue === "") {
          return {
            key: entry.key,
            override_value: null,
          };
        }

        const parsed = Number.parseFloat(rawValue);
        if (!Number.isFinite(parsed)) {
          throw new Error(`Override for ${entry.scope_label} - ${entry.parameter_label} must be numeric.`);
        }

        return {
          key: entry.key,
          override_value: parsed,
          source: draft.source.trim(),
          justification: draft.justification.trim(),
        };
      });

      const response = await api.saveAssumptionOverrides(updates);
      setAssumptionState(response);
      setAssumptionDrafts(buildOverrideDrafts(response.assumptions));
      await refreshAssumptionHistory();
      setAssumptionTone("success");
      setAssumptionNotice(
        `Saved ${response.active_override_count} active override${response.active_override_count === 1 ? "" : "s"} with traceable metadata.`
      );
    } catch (err) {
      setAssumptionTone("error");
      setAssumptionNotice(describeApiError(err, "Failed to save controlled assumption overrides."));
    } finally {
      setAssumptionSaving(false);
    }
  }

  const weatherCount = runtimeStatus?.weather_cached ?? backendHealth?.weather_cached ?? 0;
  const solarProfileCount =
    runtimeStatus?.solar_profiles_cached ?? backendHealth?.solar_profiles_cached ?? 0;
  const groupedAssumptions = (assumptionState?.assumptions ?? []).reduce<Record<string, AssumptionOverrideEntry[]>>(
    (groups, entry) => {
      const key = entry.section;
      if (!groups[key]) {
        groups[key] = [];
      }
      groups[key].push(entry);
      return groups;
    },
    {}
  );

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Settings</h2>
        <p className="text-sm text-gray-500 mt-1">
          Inspect runtime health, test external services, and manage cached project data.
        </p>
      </div>

      <div className="space-y-6">
        <CollapsibleSection
          title="Runtime Overview"
          defaultOpen={false}
          icon={backendConnected ? <Wifi size={18} className="text-green-500" /> : <WifiOff size={18} className="text-red-500" />}
          badge={backendConnected ? "Connected" : "Offline"}
        >
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <MetricCard
              label="Backend"
              value={backendConnected ? "Connected" : "Offline"}
              tone={backendConnected ? "green" : "red"}
            />
            <MetricCard label="Sites" value={String(runtimeStatus?.sites_stored ?? backendHealth?.sites_stored ?? sites.length)} />
            <MetricCard label="Weather Cache" value={String(weatherCount)} />
            <MetricCard label="Solar Profiles" value={String(solarProfileCount)} />
            <MetricCard
              label="Report Templates"
              value={String(runtimeStatus?.report_templates_available ?? 0)}
            />
          </div>

          {backendHealth && (
            <p className="text-xs text-gray-500 mt-4">
              Backend reports {backendHealth.phase} on version {backendHealth.version}.
            </p>
          )}

          {runtimeStatus && runtimeStatus.report_template_names.length > 0 && (
            <p className="text-xs text-gray-500 mt-1">
              Templates: {runtimeStatus.report_template_names.join(", ")}
            </p>
          )}

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              onClick={handleTestConnection}
              disabled={testingBackend}
              className="flex items-center gap-2 px-4 py-2 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200 text-sm disabled:opacity-50"
            >
              {testingBackend ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              Refresh Backend Status
            </button>
          </div>

          {statusNotice && (
            <Notice tone={statusTone} className="mt-4">
              {statusNotice}
            </Notice>
          )}
        </CollapsibleSection>

        <CollapsibleSection
          title="External Service Diagnostics"
          defaultOpen={false}
          icon={<ShieldCheck size={18} className="text-sky-600" />}
        >
          <p className="text-xs text-gray-500 mb-4">
            This checks the live services the app depends on for weather, geocoding, and PV generation.
          </p>

          <button
            onClick={handleTestExternalServices}
            disabled={serviceTesting}
            className="flex items-center gap-2 px-4 py-2 bg-sky-600 text-white rounded-lg hover:bg-sky-700 text-sm disabled:opacity-50"
          >
            {serviceTesting ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Zap size={14} />
            )}
            Run Service Checks
          </button>

          {serviceStatus && (
            <div className="mt-4 space-y-3">
              <p className="text-xs text-gray-500">
                Last checked: {new Date(serviceStatus.checked_at_utc).toLocaleString()}
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {serviceStatus.services.map((service) => (
                  <div
                    key={service.key}
                    className={`rounded-xl border p-4 ${
                      service.ok
                        ? "border-green-200 bg-green-50"
                        : "border-amber-200 bg-amber-50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-gray-900">{service.label}</p>
                        <p className="text-xs text-gray-600 mt-1">{service.detail}</p>
                      </div>
                      {service.ok ? (
                        <CheckCircle size={18} className="text-green-600 shrink-0" />
                      ) : (
                        <AlertCircle size={18} className="text-amber-600 shrink-0" />
                      )}
                    </div>
                    <div className="mt-3 flex gap-2 flex-wrap text-xs text-gray-600">
                      {service.status_code !== null && service.status_code !== undefined && (
                        <span className="px-2 py-0.5 rounded-full bg-white border border-gray-200">
                          HTTP {service.status_code}
                        </span>
                      )}
                      {service.latency_ms !== null && service.latency_ms !== undefined && (
                        <span className="px-2 py-0.5 rounded-full bg-white border border-gray-200">
                          {service.latency_ms} ms
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CollapsibleSection>

        <CollapsibleSection
          title="Controlled Assumption Overrides"
          defaultOpen={true}
          icon={<SlidersHorizontal size={18} className="text-indigo-600" />}
          badge={assumptionState ? `${assumptionState.assumptions.filter(e => e.override !== null).length} active` : undefined}
        >
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-4">
            <p className="text-xs text-gray-500 max-w-3xl">
              This curated workflow covers every cooling family currently exposed in Scenario Runner, plus redundancy chain efficiency and hourly misc overhead. Every saved override stays within a validated range and carries a source plus justification.
            </p>

            <div className="flex flex-wrap gap-3">
              <button
                onClick={refreshAssumptionOverrides}
                disabled={assumptionLoading || assumptionSaving}
                className="flex items-center gap-2 px-4 py-2 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200 text-sm disabled:opacity-50"
              >
                {assumptionLoading ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <RefreshCw size={14} />
                )}
                Reload Overrides
              </button>
              <button
                onClick={handleSaveAssumptions}
                disabled={assumptionLoading || assumptionSaving || !assumptionState}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm disabled:opacity-50"
              >
                {assumptionSaving ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Save size={14} />
                )}
                Save Overrides
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mt-4">
            <MetricCard
              label="Active Overrides"
              value={String(assumptionState?.active_override_count ?? 0)}
            />
            <MetricCard
              label="Curated Keys"
              value={String(assumptionState?.assumptions.length ?? 0)}
            />
            <MetricCard
              label="Scenario Presets"
              value={String(presetCatalog?.presets.length ?? 0)}
            />
            <MetricCard
              label="Last Saved"
              value={
                assumptionState?.updated_at_utc
                  ? new Date(assumptionState.updated_at_utc).toLocaleString()
                  : "Not yet saved"
              }
            />
          </div>

          {assumptionNotice && (
            <Notice tone={assumptionTone} className="mt-4">
              {assumptionNotice}
            </Notice>
          )}

          {assumptionLoading && !assumptionState ? (
            <div className="mt-6 rounded-xl border border-gray-200 bg-gray-50 p-6 text-sm text-gray-500 flex items-center gap-2">
              <Loader2 size={16} className="animate-spin" />
              Loading curated override catalog...
            </div>
          ) : assumptionState ? (
            <div className="mt-6 space-y-5">
              {Object.entries(groupedAssumptions).map(([sectionKey, entries]) => (
                <div key={sectionKey} className="rounded-xl border border-gray-200">
                  <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 rounded-t-xl">
                    <h4 className="text-sm font-medium text-gray-800">
                      {entries[0].section_label}
                    </h4>
                    <p className="text-xs text-gray-500 mt-1">
                      {sectionKey === "cooling"
                        ? "Focused on high-impact cooling assumptions used by the static and hourly engine."
                        : sectionKey === "redundancy"
                          ? "These values affect power-chain efficiency for each redundancy topology."
                          : "These fixed loads only affect the hourly PUE path."}
                    </p>
                  </div>

                  <div className="p-2 flex flex-col gap-1">
                    {entries.map((entry) => (
                      <AssumptionOverrideCard
                        key={entry.key}
                        entry={entry}
                        draft={assumptionDrafts[entry.key] ?? {
                          overrideValue: "",
                          source: "",
                          justification: "",
                        }}
                        onChange={updateDraft}
                        onClear={clearDraft}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-6 text-sm text-gray-500">
              The override catalog is currently unavailable.
            </p>
          )}
        </CollapsibleSection>

        <CollapsibleSection
          title="Override History"
          defaultOpen={false}
          icon={<HistoryIcon size={18} className="text-slate-600" />}
        >
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-4">
            <p className="text-xs text-gray-500 max-w-3xl">
              This timeline records both saved Settings overrides and scenario-local preset runs.
            </p>

            <button
              onClick={refreshAssumptionHistory}
              disabled={historyLoading}
              className="flex items-center gap-2 px-4 py-2 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200 text-sm disabled:opacity-50"
            >
              {historyLoading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              Reload History
            </button>
          </div>

          {historyError && (
            <Notice tone="error" className="mt-4">
              {historyError}
            </Notice>
          )}

          {historyLoading && !historyState ? (
            <div className="mt-6 rounded-xl border border-gray-200 bg-gray-50 p-6 text-sm text-gray-500 flex items-center gap-2">
              <Loader2 size={16} className="animate-spin" />
              Loading override history...
            </div>
          ) : historyState && historyState.entries.length > 0 ? (
            <div className="mt-6 space-y-4">
              {historyState.entries.map((entry) => (
                <OverrideHistoryCard key={entry.id} entry={entry} />
              ))}
            </div>
          ) : (
            <p className="mt-6 text-sm text-gray-500">
              No override history has been recorded yet.
            </p>
          )}
        </CollapsibleSection>

        <CollapsibleSection
          title="Default Assumptions"
          defaultOpen={false}
          icon={<SettingsIcon size={18} className="text-gray-500" />}
        >
          <p className="text-xs text-gray-500 mb-4">
            Repo baseline assumptions. Controlled overrides are applied at runtime without changing these references.
          </p>

          <div className="mb-6">
            <h4 className="text-sm font-medium text-gray-700 mb-2">Site Geometry</h4>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left text-gray-600">Parameter</th>
                    <th className="px-3 py-2 text-right text-gray-600">Default</th>
                    <th className="px-3 py-2 text-left text-gray-600">Source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  <AssRow param="Site Coverage Ratio" value="0.50" source="Italian PRG/PGT Zone D: 0.30-0.60 for industrial" />
                  <AssRow param="Whitespace Ratio" value="0.40" source="Uptime Tier III/IV: 40-45%; DCD Intelligence: 35-45%" />
                  <AssRow param="Rack Footprint" value="3.0 m2" source="ASHRAE TC 9.9 aisle recommendations; 42U rack + containment" />
                  <AssRow param="Floor-to-Floor Height" value="4.5 m" source="ASHRAE TC 9.9 minimum 4.0 m; typical DC 4.5-5.5 m" />
                  <AssRow param="Power Chain Efficiency" value="0.925" source="Schneider WP110: UPS 96% x switchgear 99.5% x PDU 99% x cabling 99%" />
                  <AssRow param="Misc PUE Component" value="0.02" source="Uptime Institute 2023 Global Survey: lighting/security 1-3%" />
                </tbody>
              </table>
            </div>
          </div>

          {referenceData && (
            <div className="mb-6">
              <h4 className="text-sm font-medium text-gray-700 mb-2">
                Load Types and Rack Densities
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-gray-600">Load Type</th>
                      <th className="px-3 py-2 text-right text-gray-600">Low (kW)</th>
                      <th className="px-3 py-2 text-right text-gray-600">Typical (kW)</th>
                      <th className="px-3 py-2 text-right text-gray-600">High (kW)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {Object.entries(referenceData.load_profiles).map(([name, profile]) => (
                      <tr key={name} className="hover:bg-gray-50">
                        <td className="px-3 py-2 text-gray-700">{name}</td>
                        <td className="px-3 py-2 text-right font-mono">{getDensityValue(profile, "low")}</td>
                        <td className="px-3 py-2 text-right font-mono font-medium">{getDensityValue(profile, "typical")}</td>
                        <td className="px-3 py-2 text-right font-mono">{getDensityValue(profile, "high")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {referenceData && (
            <div>
              <h4 className="text-sm font-medium text-gray-700 mb-2">Cooling Types</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-gray-600">Cooling Type</th>
                      <th className="px-3 py-2 text-right text-gray-600">PUE (typ)</th>
                      <th className="px-3 py-2 text-right text-gray-600">WS Factor</th>
                      <th className="px-3 py-2 text-center text-gray-600">Free Cool?</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {Object.entries(referenceData.cooling_profiles).map(([name, profile]) => (
                      <tr key={name} className="hover:bg-gray-50">
                        <td className="px-3 py-2 text-gray-700">{name}</td>
                        <td className="px-3 py-2 text-right font-mono">{profile.pue_typical.toFixed(2)}</td>
                        <td className="px-3 py-2 text-right font-mono">x{profile.whitespace_adjustment_factor.toFixed(2)}</td>
                        <td className="px-3 py-2 text-center">
                          {profile.free_cooling_eligible ? (
                            <span className="text-green-600">Yes</span>
                          ) : (
                            <span className="text-gray-400">No</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </CollapsibleSection>

        <CollapsibleSection
          title="Data Management"
          defaultOpen={false}
          icon={<Database size={18} className="text-amber-600" />}
        >
          <p className="text-sm text-gray-600 mb-4">
            Server-side data lives in <code className="px-1 py-0.5 rounded bg-gray-100 text-xs">backend/data/</code>.
            Weather and solar caches can be rebuilt from source services; site records cannot.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
            <MetricCard label="Saved Sites" value={String(runtimeStatus?.sites_stored ?? sites.length)} />
            <MetricCard label="Weather Cache Files" value={String(weatherCount)} />
            <MetricCard label="Solar Profiles" value={String(solarProfileCount)} />
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => handleClearCache("weather")}
              disabled={maintenanceAction !== null || weatherCount === 0}
              className="flex items-center gap-2 px-4 py-2 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg hover:bg-amber-100 text-sm disabled:opacity-50"
            >
              {maintenanceAction === "weather" ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Cloud size={14} />
              )}
              Clear Weather Cache
            </button>
            <button
              onClick={() => handleClearCache("solar")}
              disabled={maintenanceAction !== null || solarProfileCount === 0}
              className="flex items-center gap-2 px-4 py-2 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg hover:bg-amber-100 text-sm disabled:opacity-50"
            >
              {maintenanceAction === "solar" ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Zap size={14} />
              )}
              Clear Solar Cache
            </button>
            <button
              onClick={handleClearAllSites}
              disabled={maintenanceAction !== null || sites.length === 0}
              className="flex items-center gap-2 px-4 py-2 bg-red-50 border border-red-200 text-red-700 rounded-lg hover:bg-red-100 text-sm disabled:opacity-50"
            >
              {maintenanceAction === "sites" ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Trash2 size={14} />
              )}
              Clear All Sites
            </button>
          </div>

          {maintenanceNotice && (
            <Notice tone={maintenanceTone} className="mt-4">
              {maintenanceNotice}
            </Notice>
          )}
        </CollapsibleSection>
      </div>
    </div>
  );
}


function MetricCard({
  label,
  value,
  tone = "gray",
}: {
  label: string;
  value: string;
  tone?: "gray" | "green" | "red";
}) {
  const valueClass =
    tone === "green"
      ? "text-green-700"
      : tone === "red"
        ? "text-red-700"
        : "text-gray-900";

  return (
    <div className="bg-gray-50 rounded-xl p-3 border border-gray-200">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-lg font-semibold mt-1 ${valueClass}`}>{value}</p>
    </div>
  );
}


function Notice({
  tone,
  className = "",
  children,
}: {
  tone: NoticeTone;
  className?: string;
  children: string;
}) {
  const classes =
    tone === "success"
      ? "bg-green-50 border-green-200 text-green-700"
      : tone === "error"
        ? "bg-red-50 border-red-200 text-red-700"
        : "bg-sky-50 border-sky-200 text-sky-800";

  const Icon =
    tone === "success" ? CheckCircle : tone === "error" ? AlertCircle : RefreshCw;

  return (
    <div className={`rounded-lg border p-3 text-sm flex items-center gap-2 ${classes} ${className}`}>
      <Icon size={16} />
      {children}
    </div>
  );
}


function AssumptionOverrideCard({
  entry,
  draft,
  onChange,
  onClear,
}: {
  entry: AssumptionOverrideEntry;
  draft: OverrideDraft;
  onChange: (key: string, field: keyof OverrideDraft, value: string) => void;
  onClear: (key: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const overrideActive = draft.overrideValue.trim() !== "";
  const parsedOverride = Number.parseFloat(draft.overrideValue);
  const effectiveDisplayValue =
    overrideActive && Number.isFinite(parsedOverride)
      ? parsedOverride
      : entry.baseline_value;

  return (
    <div
      className={`rounded-lg border bg-white transition-colors ${
        overrideActive ? "border-indigo-300 bg-indigo-50/30" : "border-gray-200"
      }`}
    >
      {/* Compact header row — always visible */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-gray-50/50 rounded-lg"
      >
        {expanded ? (
          <ChevronDown size={14} className="text-gray-400 shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-gray-400 shrink-0" />
        )}

        {/* Override active indicator dot */}
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${
            overrideActive ? "bg-indigo-500" : "bg-gray-300"
          }`}
        />

        <span className="text-xs font-medium text-gray-700 truncate min-w-0 flex-1">
          {entry.scope_label}
        </span>

        <span className="text-[11px] text-gray-500 truncate hidden sm:inline">
          {entry.parameter_label}
        </span>

        <span className="text-xs font-mono text-gray-800 shrink-0 ml-auto pl-2">
          {formatAssumptionValue(effectiveDisplayValue, entry.unit)} {entry.unit}
        </span>
      </button>

      {/* Expanded edit area */}
      {expanded && (
        <div className="px-3 pb-3 border-t border-gray-100">
          {/* Info pills */}
          <div className="flex flex-wrap gap-1.5 mt-2 text-[11px] text-gray-500">
            <span className="px-1.5 py-0.5 rounded bg-gray-50 border border-gray-200">
              Baseline: {formatAssumptionValue(entry.baseline_value, entry.unit)} {entry.unit}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-gray-50 border border-gray-200">
              Range: {formatAssumptionValue(entry.min_value, entry.unit)}–{formatAssumptionValue(entry.max_value, entry.unit)}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-gray-50 border border-gray-200">
              {formatImpactScope(entry.impact_scope)}
            </span>
          </div>

          <p className="text-[11px] text-gray-500 mt-2">{entry.description}</p>

          {/* Inline edit fields — single row on larger screens */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3">
            <label className="block">
              <span className="block text-[11px] font-medium text-gray-500 mb-0.5">
                Value ({entry.unit})
              </span>
              <input
                type="number"
                step="any"
                min={entry.min_value}
                max={entry.max_value}
                value={draft.overrideValue}
                onChange={(e) => onChange(entry.key, "overrideValue", e.target.value)}
                placeholder={formatAssumptionValue(entry.baseline_value, entry.unit)}
                className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
              />
            </label>
            <label className="block">
              <span className="block text-[11px] font-medium text-gray-500 mb-0.5">
                Source
              </span>
              <input
                type="text"
                value={draft.source}
                onChange={(e) => onChange(entry.key, "source", e.target.value)}
                placeholder="Vendor datasheet, study..."
                className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
              />
            </label>
            <label className="block">
              <span className="block text-[11px] font-medium text-gray-500 mb-0.5">
                Justification
              </span>
              <input
                type="text"
                value={draft.justification}
                onChange={(e) => onChange(entry.key, "justification", e.target.value)}
                placeholder="Reason for override..."
                className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
              />
            </label>
          </div>

          {/* Footer: last saved + clear */}
          <div className="mt-2 flex items-center justify-between text-[11px] text-gray-400">
            <span>
              {entry.override?.updated_at_utc
                ? `Saved ${new Date(entry.override.updated_at_utc).toLocaleString()}`
                : "Not saved"}
            </span>
            <button
              type="button"
              onClick={() => onClear(entry.key)}
              className="px-2 py-1 rounded bg-gray-100 hover:bg-gray-200 text-gray-600 text-[11px]"
            >
              Clear
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


function OverrideHistoryCard({
  entry,
}: {
  entry: AssumptionOverrideHistoryEntry;
}) {
  return (
    <div className="rounded-xl border border-gray-200 p-4 bg-white">
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-gray-900">{entry.title}</p>
          <p className="text-xs text-gray-500 mt-1">{entry.summary}</p>
        </div>
        <div className="text-xs text-gray-500 shrink-0">
          {new Date(entry.recorded_at_utc).toLocaleString()}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-600">
        <span className="px-2 py-0.5 rounded-full bg-gray-50 border border-gray-200">
          {entry.event_type === "settings_update" ? "Settings Update" : "Preset Run"}
        </span>
        {entry.preset_label && (
          <span className="px-2 py-0.5 rounded-full bg-gray-50 border border-gray-200">
            {entry.preset_label}
          </span>
        )}
        {entry.active_override_count !== null && entry.active_override_count !== undefined && (
          <span className="px-2 py-0.5 rounded-full bg-gray-50 border border-gray-200">
            {entry.active_override_count} active override
            {entry.active_override_count === 1 ? "" : "s"}
          </span>
        )}
        {entry.site_count !== null && entry.site_count !== undefined && (
          <span className="px-2 py-0.5 rounded-full bg-gray-50 border border-gray-200">
            {entry.site_count} site{entry.site_count === 1 ? "" : "s"}
          </span>
        )}
        {entry.scenario_count !== null && entry.scenario_count !== undefined && (
          <span className="px-2 py-0.5 rounded-full bg-gray-50 border border-gray-200">
            {entry.scenario_count} scenario run{entry.scenario_count === 1 ? "" : "s"}
          </span>
        )}
      </div>

      <div className="mt-4 space-y-3">
        {entry.changes.slice(0, 6).map((change) => (
          <div
            key={`${entry.id}-${change.key}-${change.action}`}
            className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-3"
          >
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
              <div>
                <p className="text-xs font-medium text-gray-900">{change.label}</p>
                <p className="text-xs text-gray-500 mt-1">
                  {change.previous_value !== null && change.previous_value !== undefined
                    ? `${formatAssumptionValue(change.previous_value, change.unit)} -> `
                    : ""}
                  {formatAssumptionValue(change.effective_value, change.unit)} {change.unit}
                </p>
              </div>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-white border border-gray-200 text-gray-600">
                {formatHistoryAction(change.action)}
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-2">{change.source}</p>
            <p className="text-xs text-gray-500 mt-1">{change.justification}</p>
          </div>
        ))}

        {entry.changes.length > 6 && (
          <p className="text-xs text-gray-500">
            {entry.changes.length - 6} more change{entry.changes.length - 6 === 1 ? "" : "s"} are attached to this event.
          </p>
        )}
      </div>
    </div>
  );
}


function AssRow({
  param,
  value,
  source,
}: {
  param: string;
  value: string;
  source: string;
}) {
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-3 py-2 text-gray-700">{param}</td>
      <td className="px-3 py-2 text-right font-mono font-medium">{value}</td>
      <td className="px-3 py-2 text-gray-500">{source}</td>
    </tr>
  );
}


function formatCacheNotice(result: CacheClearResult) {
  if (result.target === "weather") {
    return `Removed ${result.removed_weather_files} weather cache file${result.removed_weather_files === 1 ? "" : "s"}.`;
  }
  if (result.target === "solar") {
    return `Removed ${result.removed_solar_profiles} solar profile${result.removed_solar_profiles === 1 ? "" : "s"}.`;
  }
  return `Removed ${result.removed_weather_files} weather cache file(s) and ${result.removed_solar_profiles} solar profile(s).`;
}
