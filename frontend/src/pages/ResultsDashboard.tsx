/**
 * ResultsDashboard — Page 4: Full Results Dashboard
 * ====================================================
 * Renovated layout: full-width results table + tab-based detail panel.
 */

import { useState, useEffect, useMemo, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  AlertCircle,
  TrendingUp,
  Building2,
  Shield,
  Activity,
  Target,
  Loader2,
  BarChart3,
  Layers,
  Layers3,
} from "lucide-react";
import { useAppStore } from "../store/useAppStore";
import * as api from "../api/client";
import ITCapacityChart from "../components/charts/ITCapacityChart";
import DailyProfileChart from "../components/charts/DailyProfileChart";
import TornadoChart from "../components/charts/TornadoChart";
import FirmCapacityDeficitChart from "../components/charts/FirmCapacityDeficitChart";
import TabGroup from "../components/ui/TabGroup";
import type {
  ScenarioResult,
  RAGStatus,
  FootprintResult,
  BackupPowerComparison,
  TornadoResult,
  BreakEvenResult,
  BackupPowerType,
  PUEBreakdownResult,
  FirmCapacityResult,
  FirmCapacityAdvisoryResult,
  ExpansionAdvisoryResponse,
  HourlyProfilesResult,
  LoadMixResult,
  LoadType,
  CoolingType,
  DensityScenario,
} from "../types";


const RAG_COLORS: Record<RAGStatus, { bg: string; text: string; label: string }> = {
  RED:   { bg: "bg-red-100",    text: "text-red-700",    label: "Not Viable" },
  AMBER: { bg: "bg-amber-100",  text: "text-amber-700",  label: "Warning" },
  GREEN: { bg: "bg-green-100",  text: "text-green-700",  label: "Good" },
  BLUE:  { bg: "bg-blue-100",   text: "text-blue-700",   label: "Excellent" },
};

const BACKUP_POWER_OPTIONS: BackupPowerType[] = [
  "Diesel Genset",
  "Natural Gas Genset",
  "SOFC Fuel Cell",
  "PEM Fuel Cell (H₂)",
  "Rotary UPS + Flywheel",
];

const DETAIL_TABS = [
  { key: "overview", label: "Overview", icon: <BarChart3 size={14} /> },
  { key: "capacity", label: "Capacity & PUE", icon: <Activity size={14} /> },
  { key: "infrastructure", label: "Infrastructure", icon: <Building2 size={14} /> },
  { key: "sensitivity", label: "Sensitivity", icon: <TrendingUp size={14} /> },
  { key: "expansion", label: "Expansion", icon: <Layers size={14} /> },
  { key: "firm", label: "Firm Capacity", icon: <Target size={14} /> },
];


export default function ResultsDashboard() {
  const navigate = useNavigate();
  const results = useAppStore((s) => s.batchResults);
  const selectedIndex = useAppStore((s) => s.selectedResultIndex);
  const selectResult = useAppStore((s) => s.selectResult);

  const selected: ScenarioResult | null =
    selectedIndex !== null && results[selectedIndex]
      ? results[selectedIndex]
      : null;

  if (results.length === 0) {
    return (
      <div className="max-w-5xl mx-auto">
        <div className="text-center py-16">
          <TrendingUp size={48} className="mx-auto mb-4 text-gray-300" />
          <h2 className="text-xl font-bold text-gray-900 mb-2">No Results Yet</h2>
          <p className="text-gray-500 mb-6">
            Run a batch scenario from the Scenario Runner to see results here.
          </p>
          <button
            onClick={() => navigate("/scenarios")}
            className="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
          >
            Go to Scenario Runner
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-none">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Results Dashboard</h2>
          <p className="text-sm text-gray-500 mt-1">
            {results.length} scenario{results.length !== 1 ? "s" : ""} — ranked by composite score
          </p>
        </div>
        <button
          onClick={() => navigate("/scenarios")}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft size={16} />
          Back to Runner
        </button>
      </div>

      {/* ── Results Table (full width) ── */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden mb-6">
        <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 sticky top-0 z-10">
              <tr>
                <th className="px-3 py-3 text-left font-medium text-gray-600">#</th>
                <th className="px-3 py-3 text-left font-medium text-gray-600">Site</th>
                <th className="px-3 py-3 text-left font-medium text-gray-600">Load</th>
                <th className="px-3 py-3 text-left font-medium text-gray-600">Cooling</th>
                <th className="px-3 py-3 text-right font-medium text-gray-600">IT Commit (MW)</th>
                <th className="px-3 py-3 text-right font-medium text-gray-600">PUE</th>
                <th className="px-3 py-3 text-right font-medium text-gray-600">Racks</th>
                <th className="px-3 py-3 text-center font-medium text-gray-600">RAG</th>
                <th className="px-3 py-3 text-right font-medium text-gray-600">Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {results.map((r, i) => {
                const rag = RAG_COLORS[r.power.rag_status];
                return (
                  <tr
                    key={i}
                    onClick={() => selectResult(i)}
                    className={`cursor-pointer transition-colors ${
                      i === selectedIndex ? "bg-blue-50" : "hover:bg-gray-50"
                    }`}
                  >
                    <td className="px-3 py-2.5 text-gray-400 text-xs">{i + 1}</td>
                    <td className="px-3 py-2.5 font-medium text-gray-900 max-w-[140px] truncate">{r.site_name}</td>
                    <td className="px-3 py-2.5 text-gray-700 max-w-[140px] truncate text-xs">{r.scenario.load_type}</td>
                    <td className="px-3 py-2.5 text-gray-700 max-w-[160px] truncate text-xs">{r.scenario.cooling_type}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-xs">
                      {getCommittedItMw(r).toFixed(2)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono text-xs">{(r.annual_pue ?? r.power.pue_used).toFixed(2)}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-xs">{r.power.racks_deployed.toLocaleString()}</td>
                    <td className="px-3 py-2.5 text-center">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${rag.bg} ${rag.text}`}>
                        {r.power.rag_status}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono font-medium text-xs">{r.score.toFixed(1)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Detail Panel (tab-based, full width) ── */}
      {selected ? (
        <DetailPanel result={selected} />
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center text-gray-400">
          Click a row above to see detailed analysis
        </div>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// DetailPanel — Tab-based full-width detail for one scenario
// ─────────────────────────────────────────────────────────────

function DetailPanel({ result }: { result: ScenarioResult }) {
  const r = result;
  const rag = RAG_COLORS[r.power.rag_status];
  const pue = r.annual_pue ?? r.power.pue_used;
  const [activeTab, setActiveTab] = useState("overview");

  // ── Lazy-loaded advanced data ──
  const [footprint, setFootprint] = useState<FootprintResult | null>(null);
  const [footprintLoading, setFootprintLoading] = useState(false);
  const [footprintError, setFootprintError] = useState<string | null>(null);
  const [footprintBackupType, setFootprintBackupType] = useState<BackupPowerType>(r.scenario.backup_power);
  const [coolingFootprintOverride, setCoolingFootprintOverride] = useState("");
  const [backup, setBackup] = useState<BackupPowerComparison | null>(null);
  const [backupLoading, setBackupLoading] = useState(false);
  const [tornado, setTornado] = useState<TornadoResult | null>(null);
  const [tornadoLoading, setTornadoLoading] = useState(false);
  const [breakEven, setBreakEven] = useState<BreakEvenResult | null>(null);
  const [beLoading, setBeLoading] = useState(false);
  const [beTarget, setBeTarget] = useState("");
  const [beParam, setBeParam] = useState("pue");
  const [pueBreakdown, setPueBreakdown] = useState<PUEBreakdownResult | null>(null);
  const [pueBreakdownLoading, setPueBreakdownLoading] = useState(false);
  const [pueBreakdownError, setPueBreakdownError] = useState<string | null>(null);
  const [hourlyProfiles, setHourlyProfiles] = useState<HourlyProfilesResult | null>(null);
  const [hourlyProfilesLoading, setHourlyProfilesLoading] = useState(false);
  const [hourlyProfilesError, setHourlyProfilesError] = useState<string | null>(null);
  const [expansionAdvisory, setExpansionAdvisory] = useState<ExpansionAdvisoryResponse | null>(null);
  const [expansionAdvisoryLoading, setExpansionAdvisoryLoading] = useState(false);
  const [expansionAdvisoryError, setExpansionAdvisoryError] = useState<string | null>(null);
  const [firmCapacity, setFirmCapacity] = useState<FirmCapacityResult | null>(null);
  const [firmCapacityLoading, setFirmCapacityLoading] = useState(false);
  const [firmCapacityError, setFirmCapacityError] = useState<string | null>(null);
  const [firmAdvisory, setFirmAdvisory] = useState<FirmCapacityAdvisoryResult | null>(null);
  const [firmAdvisoryLoading, setFirmAdvisoryLoading] = useState(false);
  const [firmAdvisoryError, setFirmAdvisoryError] = useState<string | null>(null);
  const [supportTarget, setSupportTarget] = useState("");
  const [bessCapacityKwh, setBessCapacityKwh] = useState("0");
  const [fuelCellKw, setFuelCellKw] = useState("0");
  const [backupDispatchKw, setBackupDispatchKw] = useState("0");
  const expansion = expansionAdvisory?.expansion_advisory ?? null;
  const peakDailyIt = hourlyProfiles
    ? Math.max(...hourlyProfiles.days.map((day) => day.it_max_mw))
    : null;
  const peakDailyPue = hourlyProfiles
    ? Math.max(...hourlyProfiles.days.map((day) => day.pue_max))
    : null;

  // Reset lazy data when result changes
  useEffect(() => {
    setFootprint(null);
    setFootprintError(null);
    setFootprintBackupType(r.scenario.backup_power);
    setCoolingFootprintOverride("");
    setBackup(null);
    setTornado(null);
    setBreakEven(null);
    setPueBreakdown(null);
    setPueBreakdownError(null);
    setHourlyProfiles(null);
    setHourlyProfilesError(null);
    setExpansionAdvisory(null);
    setExpansionAdvisoryError(null);
    setFirmCapacity(null);
    setFirmCapacityError(null);
    setFirmAdvisory(null);
    setFirmAdvisoryError(null);
    setSupportTarget("");
    setBessCapacityKwh("0");
    setFuelCellKw("0");
    setBackupDispatchKw("0");
    setActiveTab("overview");
  }, [
    r.site_id,
    r.scenario.cooling_type,
    r.scenario.load_type,
    r.scenario.redundancy,
    r.scenario.density_scenario,
    r.scenario.backup_power,
  ]);


  // ── Fetch functions ──
  async function loadFootprint() {
    setFootprintLoading(true);
    setFootprintError(null);
    try {
      const parsedOverride = coolingFootprintOverride.trim()
        ? Number.parseFloat(coolingFootprintOverride)
        : undefined;
      const data = await api.computeFootprint({
        facility_power_mw: r.power.facility_power_mw,
        procurement_power_mw: r.power.procurement_power_mw,
        buildable_footprint_m2: r.space.buildable_footprint_m2,
        land_area_m2: r.space.buildable_footprint_m2 / r.space.site_coverage_used,
        backup_power_type: footprintBackupType,
        cooling_m2_per_kw_override:
          parsedOverride !== undefined && Number.isFinite(parsedOverride)
            ? parsedOverride
            : undefined,
      });
      setFootprint(data);
    } catch (error) {
      setFootprintError(error instanceof Error ? error.message : "Footprint calculation failed");
    }
    setFootprintLoading(false);
  }

  async function loadBackup() {
    setBackupLoading(true);
    try {
      const data = await api.compareBackupPower({
        facility_power_mw: r.power.facility_power_mw,
        procurement_power_mw: r.power.procurement_power_mw,
      });
      setBackup(data as BackupPowerComparison);
    } catch { /* ignore */ }
    setBackupLoading(false);
  }

  async function loadTornado() {
    setTornadoLoading(true);
    try {
      const data = await api.computeTornado({
        pue: pue,
        eta_chain: r.power.eta_chain,
        rack_density_kw: r.power.rack_density_kw,
        whitespace_ratio: r.space.whitespace_ratio_used,
        site_coverage_ratio: r.space.site_coverage_used,
        available_power_mw: r.power.facility_power_mw / pue * r.power.eta_chain > 0
          ? r.power.procurement_power_mw / r.power.procurement_factor
          : 0,
        land_area_m2: r.space.buildable_footprint_m2 / r.space.site_coverage_used,
        num_floors: r.space.active_floors,
        rack_footprint_m2: r.space.rack_footprint_used,
        whitespace_adjustment: r.space.whitespace_adjustment_factor,
        procurement_factor: r.power.procurement_factor,
        variation_pct: 10,
        output_metric: "it_load",
        power_constrained: r.power.binding_constraint === "POWER",
      });
      setTornado(data);
    } catch { /* ignore */ }
    setTornadoLoading(false);
  }

  async function loadPUEBreakdown() {
    setPueBreakdownLoading(true);
    setPueBreakdownError(null);
    try {
      const data = await api.computePUEBreakdown({
        site_id: r.site_id,
        scenario: r.scenario,
      });
      setPueBreakdown(data);
    } catch (error) {
      setPueBreakdownError(
        error instanceof Error ? error.message : "PUE breakdown could not be computed"
      );
    }
    setPueBreakdownLoading(false);
  }

  async function loadHourlyProfiles() {
    setHourlyProfilesLoading(true);
    setHourlyProfilesError(null);
    try {
      const data = await api.computeHourlyProfiles({
        site_id: r.site_id,
        scenario: r.scenario,
      });
      setHourlyProfiles(data);
    } catch (error) {
      setHourlyProfilesError(
        error instanceof Error ? error.message : "Daily profile charts could not be computed"
      );
    }
    setHourlyProfilesLoading(false);
  }

  async function loadExpansionAdvisory() {
    setExpansionAdvisoryLoading(true);
    setExpansionAdvisoryError(null);
    try {
      const data = await api.computeExpansionAdvisory({
        site_id: r.site_id,
        scenario: r.scenario,
        include_hourly: r.pue_source === "hourly",
      });
      setExpansionAdvisory(data);
    } catch (error) {
      setExpansionAdvisoryError(
        error instanceof Error ? error.message : "Expansion advisory could not be computed"
      );
    }
    setExpansionAdvisoryLoading(false);
  }

  async function loadFirmCapacity() {
    setFirmCapacityLoading(true);
    setFirmCapacityError(null);
    try {
      const target = supportTarget.trim()
        ? Number.parseFloat(supportTarget)
        : undefined;
      const data = await api.computeFirmCapacity({
        site_id: r.site_id,
        scenario: r.scenario,
        target_it_load_mw: target,
        bess_capacity_kwh: Number.parseFloat(bessCapacityKwh) || 0,
        fuel_cell_capacity_kw: Number.parseFloat(fuelCellKw) || 0,
        backup_dispatch_capacity_kw: Number.parseFloat(backupDispatchKw) || 0,
        cyclic_bess: true,
      });
      setFirmCapacity(data);
    } catch (error) {
      setFirmCapacityError(
        error instanceof Error ? error.message : "Firm capacity analysis failed"
      );
    }
    setFirmCapacityLoading(false);
  }

  async function loadFirmAdvisory() {
    setFirmAdvisoryLoading(true);
    setFirmAdvisoryError(null);
    try {
      const data = await api.computeFirmCapacityAdvisory({
        site_id: r.site_id,
        scenario: r.scenario,
      });
      setFirmAdvisory(data);
    } catch (error) {
      setFirmAdvisoryError(
        error instanceof Error ? error.message : "Firm capacity advisory failed"
      );
    }
    setFirmAdvisoryLoading(false);
  }

  async function handleBreakEven() {
    if (!beTarget) return;
    setBeLoading(true);
    try {
      const data = await api.computeBreakEven({
        target_it_load_mw: parseFloat(beTarget),
        parameter: beParam,
        pue: pue,
        eta_chain: r.power.eta_chain,
        rack_density_kw: r.power.rack_density_kw,
        whitespace_ratio: r.space.whitespace_ratio_used,
        site_coverage_ratio: r.space.site_coverage_used,
        available_power_mw: r.power.procurement_power_mw / r.power.procurement_factor,
        land_area_m2: r.space.buildable_footprint_m2 / r.space.site_coverage_used,
        num_floors: r.space.active_floors,
        rack_footprint_m2: r.space.rack_footprint_used,
        whitespace_adjustment: r.space.whitespace_adjustment_factor,
        power_constrained: r.power.binding_constraint === "POWER",
      });
      setBreakEven(data);
    } catch { /* ignore */ }
    setBeLoading(false);
  }


  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200">
      {/* ── Scenario Header Bar ── */}
      <div className="p-5 border-b border-gray-200">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-4">
            <div>
              <h3 className="text-lg font-bold text-gray-900">{r.site_name}</h3>
              <p className="text-sm text-gray-500">
                {r.scenario.load_type} · {r.scenario.cooling_type} · {r.scenario.redundancy} · {r.scenario.density_scenario}
              </p>
            </div>
            <span className={`px-3 py-1 rounded-full text-xs font-bold ${rag.bg} ${rag.text}`}>
              {r.power.rag_status} — {rag.label}
            </span>
          </div>
          <div className="flex items-center gap-6 text-sm">
            <div className="text-center">
              <p className="text-xs text-gray-500">IT Commit</p>
              <p className="font-bold text-gray-900">{getCommittedItMw(r).toFixed(2)} MW</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-gray-500">PUE</p>
              <p className="font-bold text-gray-900">{pue.toFixed(3)}</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-gray-500">Score</p>
              <p className="font-bold text-gray-900">{r.score.toFixed(1)}</p>
            </div>
          </div>
        </div>
        {r.power.rag_reasons.length > 0 && (
          <div className="mt-3 p-2 bg-gray-50 rounded-lg">
            {r.power.rag_reasons.map((reason, i) => (
              <p key={i} className="text-xs text-gray-500 flex items-start gap-1.5">
                <AlertCircle size={12} className="mt-0.5 shrink-0 text-gray-400" />
                {reason}
              </p>
            ))}
          </div>
        )}
      </div>

      {/* ── Tab Navigation ── */}
      <TabGroup tabs={DETAIL_TABS} activeKey={activeTab} onChange={setActiveTab} />

      {/* ── Tab Content ── */}
      <div className="p-5">
        {activeTab === "overview" && (
          <OverviewTab r={r} pue={pue} />
        )}

        {activeTab === "capacity" && (
          <CapacityPueTab
            r={r}
            pue={pue}
            hourlyProfiles={hourlyProfiles}
            hourlyProfilesLoading={hourlyProfilesLoading}
            hourlyProfilesError={hourlyProfilesError}
            loadHourlyProfiles={loadHourlyProfiles}
            pueBreakdown={pueBreakdown}
            pueBreakdownLoading={pueBreakdownLoading}
            pueBreakdownError={pueBreakdownError}
            loadPUEBreakdown={loadPUEBreakdown}
            peakDailyIt={peakDailyIt}
            peakDailyPue={peakDailyPue}
          />
        )}

        {activeTab === "infrastructure" && (
          <InfrastructureTab
            r={r}
            footprint={footprint}
            footprintLoading={footprintLoading}
            footprintError={footprintError}
            footprintBackupType={footprintBackupType}
            setFootprintBackupType={setFootprintBackupType}
            coolingFootprintOverride={coolingFootprintOverride}
            setCoolingFootprintOverride={setCoolingFootprintOverride}
            loadFootprint={loadFootprint}
            backup={backup}
            backupLoading={backupLoading}
            loadBackup={loadBackup}
          />
        )}

        {activeTab === "sensitivity" && (
          <SensitivityTab
            r={r}
            pue={pue}
            tornado={tornado}
            tornadoLoading={tornadoLoading}
            loadTornado={loadTornado}
            breakEven={breakEven}
            beLoading={beLoading}
            beTarget={beTarget}
            setBeTarget={setBeTarget}
            beParam={beParam}
            setBeParam={setBeParam}
            handleBreakEven={handleBreakEven}
          />
        )}

        {activeTab === "expansion" && (
          <ExpansionTab
            r={r}
            expansion={expansion}
            expansionAdvisoryLoading={expansionAdvisoryLoading}
            expansionAdvisoryError={expansionAdvisoryError}
            loadExpansionAdvisory={loadExpansionAdvisory}
          />
        )}

        {activeTab === "firm" && (
          <FirmCapacityTab
            r={r}
            firmCapacity={firmCapacity}
            firmCapacityLoading={firmCapacityLoading}
            firmCapacityError={firmCapacityError}
            loadFirmCapacity={loadFirmCapacity}
            firmAdvisory={firmAdvisory}
            firmAdvisoryLoading={firmAdvisoryLoading}
            firmAdvisoryError={firmAdvisoryError}
            loadFirmAdvisory={loadFirmAdvisory}
            supportTarget={supportTarget}
            setSupportTarget={setSupportTarget}
            bessCapacityKwh={bessCapacityKwh}
            setBessCapacityKwh={setBessCapacityKwh}
            fuelCellKw={fuelCellKw}
            setFuelCellKw={setFuelCellKw}
            backupDispatchKw={backupDispatchKw}
            setBackupDispatchKw={setBackupDispatchKw}
          />
        )}
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Tab: Overview
// ─────────────────────────────────────────────────────────────

function OverviewTab({ r, pue }: { r: ScenarioResult; pue: number }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        <Metric
          label={r.pue_source === "hourly" ? "Committed IT (P99)" : "IT Load"}
          value={`${getCommittedItMw(r).toFixed(2)} MW`}
          sub={r.pue_source === "hourly" ? "What you can sell" : undefined}
        />
        {r.pue_source === "hourly" && (
          <Metric label="Worst-Hour IT" value={`${(r.it_capacity_worst_mw ?? r.power.it_load_mw).toFixed(2)} MW`} />
        )}
        {r.pue_source === "hourly" && (
          <Metric label="Annual Mean IT" value={`${(r.it_capacity_mean_mw ?? r.power.it_load_mw).toFixed(2)} MW`} />
        )}
        {r.pue_source === "hourly" && (
          <Metric label="Nominal IT" value={`${r.power.it_load_mw.toFixed(2)} MW`} sub="Static shortcut" />
        )}
        <Metric label="Facility Power" value={`${r.power.facility_power_mw.toFixed(2)} MW`} />
        <Metric label="Procurement" value={`${r.power.procurement_power_mw.toFixed(2)} MW`} />
        <Metric label="PUE" value={pue.toFixed(3)} sub={r.pue_source} />
        <Metric label="Racks" value={r.power.racks_deployed.toLocaleString()} />
        <Metric label="Rack Density" value={`${r.power.rack_density_kw.toFixed(1)} kW`} />
        <Metric label="Constraint" value={r.power.binding_constraint} />
        <Metric label="Score" value={r.score.toFixed(1)} />
      </div>

      {/* Space summary */}
      <div>
        <h4 className="text-sm font-semibold text-gray-700 mb-3">Space Summary</h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Metric label="Buildable Footprint" value={`${r.space.buildable_footprint_m2.toLocaleString()} m²`} />
          <Metric label="Active Floors" value={r.space.active_floors.toLocaleString()} />
          <Metric label="Whitespace Ratio" value={`${(r.space.whitespace_ratio_used * 100).toFixed(0)}%`} />
          <Metric label="Site Coverage" value={`${(r.space.site_coverage_used * 100).toFixed(0)}%`} />
        </div>
      </div>

      {/* IT Capacity Spectrum chart (if hourly) */}
      {r.pue_source === "hourly" && r.it_capacity_p99_mw !== null && (
        <div>
          <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <Activity size={14} className="text-blue-500" />
            IT Capacity Spectrum
          </h4>
          <ITCapacityChart result={r} />
        </div>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Tab: Capacity & PUE
// ─────────────────────────────────────────────────────────────

function CapacityPueTab({
  r, pue, hourlyProfiles, hourlyProfilesLoading, hourlyProfilesError, loadHourlyProfiles,
  pueBreakdown, pueBreakdownLoading, pueBreakdownError, loadPUEBreakdown,
  peakDailyIt, peakDailyPue,
}: {
  r: ScenarioResult;
  pue: number;
  hourlyProfiles: HourlyProfilesResult | null;
  hourlyProfilesLoading: boolean;
  hourlyProfilesError: string | null;
  loadHourlyProfiles: () => void;
  pueBreakdown: PUEBreakdownResult | null;
  pueBreakdownLoading: boolean;
  pueBreakdownError: string | null;
  loadPUEBreakdown: () => void;
  peakDailyIt: number | null;
  peakDailyPue: number | null;
}) {
  return (
    <div className="space-y-6">
      {/* Daily Operating Profiles */}
      <SectionCard
        title="Daily Operating Profiles"
        icon={<Activity size={16} className="text-sky-500" />}
        action={(
          <button
            type="button"
            onClick={loadHourlyProfiles}
            disabled={hourlyProfilesLoading || r.pue_source !== "hourly"}
            className="text-xs px-3 py-1 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            {hourlyProfilesLoading ? <Loader2 size={12} className="animate-spin" /> : "Load"}
          </button>
        )}
      >
        {r.pue_source !== "hourly" && (
          <p className="text-xs text-gray-500">
            Hourly weather simulation is required to show daily IT-load and PUE profiles.
          </p>
        )}
        {hourlyProfilesError && <p className="text-xs text-red-600 mb-3">{hourlyProfilesError}</p>}
        {hourlyProfiles && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Metric label="Committed IT" value={`${hourlyProfiles.committed_it_mw.toFixed(2)} MW`} />
              <Metric label="Annual Mean IT" value={`${hourlyProfiles.annual_mean_it_mw.toFixed(2)} MW`} />
              <Metric label="Peak Daily IT" value={`${(peakDailyIt ?? hourlyProfiles.best_it_mw).toFixed(2)} MW`} />
              <Metric label="Annual PUE" value={hourlyProfiles.annual_pue.toFixed(3)} />
              <Metric label="Worst-Hour IT" value={`${hourlyProfiles.worst_it_mw.toFixed(2)} MW`} />
              <Metric label="Best-Hour IT" value={`${hourlyProfiles.best_it_mw.toFixed(2)} MW`} />
              <Metric label="Peak Daily PUE" value={(peakDailyPue ?? hourlyProfiles.annual_pue).toFixed(3)} />
              <Metric label="Representative Days" value={hourlyProfiles.day_count.toLocaleString()} />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="rounded-lg border border-gray-200 p-3">
                <p className="text-sm font-medium text-gray-800 mb-2">Daily IT Load</p>
                <DailyProfileChart
                  data={hourlyProfiles.days}
                  metric="it"
                  referenceValue={getCommittedItMw(r)}
                  referenceLabel={`Committed ${getCommittedItMw(r).toFixed(2)} MW`}
                />
              </div>
              <div className="rounded-lg border border-gray-200 p-3">
                <p className="text-sm font-medium text-gray-800 mb-2">Daily PUE</p>
                <DailyProfileChart
                  data={hourlyProfiles.days}
                  metric="pue"
                  referenceValue={hourlyProfiles.annual_pue}
                  referenceLabel={`Annual ${hourlyProfiles.annual_pue.toFixed(3)}`}
                />
              </div>
            </div>
          </div>
        )}
      </SectionCard>

      {/* PUE Overhead Decomposition */}
      <SectionCard
        title="PUE Overhead Decomposition"
        icon={<Activity size={16} className="text-blue-500" />}
        action={(
          <button
            type="button"
            onClick={loadPUEBreakdown}
            disabled={pueBreakdownLoading || r.pue_source !== "hourly"}
            className="text-xs px-3 py-1 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            {pueBreakdownLoading ? <Loader2 size={12} className="animate-spin" /> : "Compute"}
          </button>
        )}
      >
        {r.pue_source !== "hourly" && (
          <p className="text-xs text-gray-500">
            Hourly weather simulation is required to show annual overhead decomposition.
          </p>
        )}
        {pueBreakdownError && <p className="text-xs text-red-600">{pueBreakdownError}</p>}
        {pueBreakdown && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Metric label="Annual PUE" value={pueBreakdown.annual_pue.toFixed(3)} />
              <Metric label="Total Overhead" value={formatKWh(pueBreakdown.total_overhead_kwh)} />
              <Metric label="Facility Energy" value={formatKWh(pueBreakdown.total_facility_kwh)} />
              <Metric label="IT Energy" value={formatKWh(pueBreakdown.total_it_kwh)} />
            </div>
            <div className="space-y-2">
              {pueBreakdown.components.map((component) => (
                <EnergyBreakdownRow
                  key={component.key}
                  label={component.label}
                  energyKwh={component.energy_kwh}
                  share={component.share_of_overhead}
                />
              ))}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Metric label="MECH Hours" value={pueBreakdown.cooling_mode_hours.mech.toLocaleString()} />
              <Metric label="ECON_PART Hours" value={pueBreakdown.cooling_mode_hours.econ_part.toLocaleString()} />
              <Metric label="ECON_FULL Hours" value={pueBreakdown.cooling_mode_hours.econ_full.toLocaleString()} />
              <Metric label="Overtemp Hours" value={pueBreakdown.cooling_mode_hours.overtemperature.toLocaleString()} />
            </div>
          </div>
        )}
      </SectionCard>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Tab: Infrastructure
// ─────────────────────────────────────────────────────────────

function InfrastructureTab({
  r, footprint, footprintLoading, footprintError, footprintBackupType,
  setFootprintBackupType, coolingFootprintOverride, setCoolingFootprintOverride,
  loadFootprint, backup, backupLoading, loadBackup,
}: {
  r: ScenarioResult;
  footprint: FootprintResult | null;
  footprintLoading: boolean;
  footprintError: string | null;
  footprintBackupType: BackupPowerType;
  setFootprintBackupType: (v: BackupPowerType) => void;
  coolingFootprintOverride: string;
  setCoolingFootprintOverride: (v: string) => void;
  loadFootprint: () => void;
  backup: BackupPowerComparison | null;
  backupLoading: boolean;
  loadBackup: () => void;
}) {
  return (
    <div className="space-y-6">
      <SectionCard
        title="Infrastructure Footprint"
        icon={<Building2 size={16} className="text-gray-500" />}
        action={(
          <button type="button" onClick={loadFootprint} disabled={footprintLoading}
            className="text-xs px-3 py-1 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            {footprintLoading ? <Loader2 size={12} className="animate-spin" /> : "Compute"}
          </button>
        )}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Backup technology</label>
            <select
              value={footprintBackupType}
              onChange={(e) => setFootprintBackupType(e.target.value as BackupPowerType)}
              className="w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none"
            >
              {BACKUP_POWER_OPTIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Cooling factor override (m²/kW)</label>
            <input
              type="number"
              value={coolingFootprintOverride}
              onChange={(e) => setCoolingFootprintOverride(e.target.value)}
              step="0.001" min="0" placeholder="Use backend default"
              className="w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>
          <div className="text-xs text-gray-500 self-end">
            Uses the engine's cited footprint factors. Override applies only to cooling equipment.
          </div>
        </div>
        {footprintError && <p className="text-xs text-red-600 mb-3">{footprintError}</p>}
        {footprint && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Metric label="Ground Equipment" value={`${footprint.total_ground_m2.toLocaleString()} m²`} />
              <Metric label="Roof Equipment" value={`${footprint.total_roof_m2.toLocaleString()} m²`} />
              <Metric label="Ground Utilization" value={`${(footprint.ground_utilization_ratio * 100).toFixed(0)}%`} />
              <Metric label="Roof Utilization" value={`${(footprint.roof_utilization_ratio * 100).toFixed(0)}%`} />
              <Metric label="Outdoor Available" value={`${footprint.available_outdoor_m2.toLocaleString()} m²`} />
              <Metric label="Roof Available" value={`${footprint.building_roof_m2.toLocaleString()} m²`} />
              <Metric label="Backup Units" value={footprint.backup_num_units.toLocaleString()} />
              <Metric label="Unit Size" value={`${footprint.backup_unit_size_kw.toLocaleString()} kW`} />
            </div>
            <div className="flex items-center gap-2 text-xs flex-wrap">
              <span className={`px-2 py-0.5 rounded-full font-medium ${
                footprint.ground_fits ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
              }`}>
                Ground {footprint.ground_fits ? "fits" : "does not fit"}
              </span>
              <span className={`px-2 py-0.5 rounded-full font-medium ${
                footprint.roof_fits ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
              }`}>
                Roof {footprint.roof_fits ? "fits" : "does not fit"}
              </span>
              <span className="text-gray-500">Backup basis: {footprint.backup_power_type}</span>
            </div>
            <div className="overflow-x-auto border border-gray-200 rounded-lg">
              <table className="w-full text-xs">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left text-gray-600">Element</th>
                    <th className="px-3 py-2 text-left text-gray-600">Location</th>
                    <th className="px-3 py-2 text-right text-gray-600">Area</th>
                    <th className="px-3 py-2 text-right text-gray-600">Sizing Basis</th>
                    <th className="px-3 py-2 text-right text-gray-600">Factor</th>
                    <th className="px-3 py-2 text-right text-gray-600">Units</th>
                    <th className="px-3 py-2 text-left text-gray-600">Source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {footprint.elements.map((element) => (
                    <tr key={`${element.name}-${element.location}`} className="align-top">
                      <td className="px-3 py-2 text-gray-700">{element.name}</td>
                      <td className="px-3 py-2 capitalize text-gray-500">{element.location}</td>
                      <td className="px-3 py-2 text-right font-mono">{element.area_m2.toFixed(1)} m²</td>
                      <td className="px-3 py-2 text-right font-mono">{element.sizing_basis_kw.toFixed(0)} kW</td>
                      <td className="px-3 py-2 text-right font-mono">{element.m2_per_kw_used.toFixed(3)}</td>
                      <td className="px-3 py-2 text-right font-mono">
                        {element.num_units ?? "—"}
                        {element.unit_size_kw ? ` × ${element.unit_size_kw.toFixed(0)} kW` : ""}
                      </td>
                      <td className="px-3 py-2 text-gray-500">{element.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Backup Power Comparison"
        icon={<Shield size={16} className="text-amber-500" />}
        action={(
          <button type="button" onClick={loadBackup} disabled={backupLoading}
            className="text-xs px-3 py-1 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            {backupLoading ? <Loader2 size={12} className="animate-spin" /> : "Compare"}
          </button>
        )}
      >
        {backup && (
          <div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-2 py-1.5 text-left text-gray-600">Technology</th>
                    <th className="px-2 py-1.5 text-right text-gray-600">Units</th>
                    <th className="px-2 py-1.5 text-right text-gray-600">Unit Size</th>
                    <th className="px-2 py-1.5 text-right text-gray-600">CO₂ (t/yr)</th>
                    <th className="px-2 py-1.5 text-right text-gray-600">Footprint</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {backup.technologies.map((t) => (
                    <tr key={t.technology} className="hover:bg-gray-50">
                      <td className="px-2 py-1.5 text-gray-700">{t.technology}</td>
                      <td className="px-2 py-1.5 text-right font-mono">{t.num_units}</td>
                      <td className="px-2 py-1.5 text-right font-mono">{t.unit_size_kw.toFixed(0)} kW</td>
                      <td className="px-2 py-1.5 text-right font-mono">{t.co2_tonnes_per_year.toFixed(0)}</td>
                      <td className="px-2 py-1.5 text-right font-mono">{t.footprint_m2.toFixed(0)} m²</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-2 text-xs text-gray-500 space-y-0.5">
              <p>Lowest CO₂: {backup.lowest_co2_technology}</p>
              <p>Smallest footprint: {backup.smallest_footprint_technology}</p>
              <p>Fastest ramp: {backup.fastest_ramp_technology}</p>
            </div>
          </div>
        )}
      </SectionCard>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Tab: Sensitivity
// ─────────────────────────────────────────────────────────────

function SensitivityTab({
  r, pue, tornado, tornadoLoading, loadTornado, breakEven,
  beLoading, beTarget, setBeTarget, beParam, setBeParam, handleBreakEven,
}: {
  r: ScenarioResult;
  pue: number;
  tornado: TornadoResult | null;
  tornadoLoading: boolean;
  loadTornado: () => void;
  breakEven: BreakEvenResult | null;
  beLoading: boolean;
  beTarget: string;
  setBeTarget: (v: string) => void;
  beParam: string;
  setBeParam: (v: string) => void;
  handleBreakEven: () => void;
}) {
  return (
    <div className="space-y-6">
      <SectionCard
        title="Sensitivity Analysis (±10%)"
        icon={<Activity size={16} className="text-purple-500" />}
        action={(
          <button type="button" onClick={loadTornado} disabled={tornadoLoading}
            className="text-xs px-3 py-1 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            {tornadoLoading ? <Loader2 size={12} className="animate-spin" /> : "Compute"}
          </button>
        )}
      >
        {tornado && (
          <TornadoChart
            bars={tornado.bars}
            baselineOutput={tornado.bars[0]?.output_at_baseline ?? r.power.it_load_mw}
            outputUnit={tornado.output_metric_unit}
          />
        )}
      </SectionCard>

      <SectionCard
        title="Break-Even Solver"
        icon={<Target size={16} className="text-green-500" />}
      >
        <p className="text-xs text-gray-500 mb-3">
          What value of parameter X achieves a target IT load?
        </p>
        <div className="flex items-end gap-3 flex-wrap">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Target IT (MW)</label>
            <input
              type="number" value={beTarget}
              onChange={(e) => setBeTarget(e.target.value)}
              placeholder="e.g. 15" step="0.1"
              className="w-28 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Solve for</label>
            <select
              value={beParam}
              onChange={(e) => setBeParam(e.target.value)}
              className="px-2 py-1.5 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 outline-none"
            >
              <option value="pue">PUE</option>
              <option value="eta_chain">η Chain</option>
              <option value="rack_density_kw">Rack Density (kW)</option>
              <option value="available_power_mw">Available Power (MW)</option>
              <option value="whitespace_ratio">Whitespace Ratio</option>
              <option value="site_coverage_ratio">Site Coverage</option>
            </select>
          </div>
          <button
            type="button" onClick={handleBreakEven}
            disabled={beLoading || !beTarget}
            className="px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm disabled:opacity-50"
          >
            {beLoading ? <Loader2 size={14} className="animate-spin" /> : "Solve"}
          </button>
        </div>
        {breakEven && (
          <div className={`mt-3 p-3 rounded-lg text-sm ${
            breakEven.feasible ? "bg-green-50 border border-green-200" : "bg-red-50 border border-red-200"
          }`}>
            <p className={breakEven.feasible ? "text-green-700" : "text-red-700"}>
              {breakEven.feasible
                ? `Break-even found for ${breakEven.parameter_label}.`
                : breakEven.feasibility_note || `No feasible break-even value for ${breakEven.parameter_label}.`}
            </p>
            {breakEven.feasible && (
              <p className="text-xs text-gray-600 mt-1">
                {breakEven.parameter_label}: {breakEven.baseline_value.toFixed(3)} → {breakEven.break_even_value.toFixed(3)}
                {" "}({breakEven.change_pct > 0 ? "+" : ""}{breakEven.change_pct.toFixed(1)}%)
              </p>
            )}
          </div>
        )}
      </SectionCard>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Tab: Expansion
// ─────────────────────────────────────────────────────────────

function ExpansionTab({
  r, expansion, expansionAdvisoryLoading, expansionAdvisoryError, loadExpansionAdvisory,
}: {
  r: ScenarioResult;
  expansion: ExpansionAdvisoryResponse["expansion_advisory"] | null;
  expansionAdvisoryLoading: boolean;
  expansionAdvisoryError: string | null;
  loadExpansionAdvisory: () => void;
}) {
  return (
    <div className="space-y-6">
      <SectionCard
        title="Expansion Advisory"
        icon={<TrendingUp size={16} className="text-emerald-500" />}
        action={(
          <button type="button" onClick={loadExpansionAdvisory} disabled={expansionAdvisoryLoading}
            className="text-xs px-3 py-1 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            {expansionAdvisoryLoading ? <Loader2 size={12} className="animate-spin" /> : "Compute"}
          </button>
        )}
      >
        <p className="text-xs text-gray-500 mb-3">
          Advisory only. Future floors and extra grid request are shown separately and do not change the main scenario score.
        </p>
        {expansionAdvisoryError && <p className="text-xs text-red-600 mb-3">{expansionAdvisoryError}</p>}
        {expansion && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Metric label="Active Floors" value={expansion.active_floors.toLocaleString()} />
              <Metric label="Reserved Floors" value={expansion.declared_expansion_floors.toLocaleString()} />
              <Metric label="Height Uplift Floors" value={expansion.latent_height_floors.toLocaleString()} />
              <Metric label="Max Total Floors" value={expansion.max_total_floors !== null ? expansion.max_total_floors.toLocaleString() : "N/A"} />
              <Metric label="Unused Active Racks" value={expansion.unused_active_racks.toLocaleString()} />
              <Metric label="Reserved Expansion Racks" value={expansion.declared_expansion_racks.toLocaleString()} />
              <Metric label="Height Uplift Racks" value={expansion.latent_height_racks.toLocaleString()} />
              <Metric label="Total Additional Racks" value={expansion.total_additional_racks.toLocaleString()} highlight />
              <Metric label="Current Facility Envelope" value={`${expansion.current_facility_envelope_mw.toFixed(2)} MW`} />
              <Metric label="Current Procurement Envelope" value={`${expansion.current_procurement_envelope_mw.toFixed(2)} MW`} />
              <Metric label="Extra Grid Request" value={`${expansion.additional_grid_request_mw.toFixed(2)} MW`} highlight />
              <Metric label="Binding Constraint" value={expansion.binding_constraint} />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <CapacitySnapshotCard title="Current Feasible" snapshot={expansion.current_feasible} />
              <CapacitySnapshotCard title="Future Expandable" snapshot={expansion.future_expandable} accent="green" />
              <CapacitySnapshotCard title="Total Site Potential" snapshot={expansion.total_site_potential} accent="blue" />
            </div>

            <div className="space-y-1.5">
              {expansion.notes.map((note) => (
                <p key={note} className="text-xs text-gray-600 flex items-start gap-1.5">
                  <AlertCircle size={12} className="mt-0.5 shrink-0 text-gray-400" />
                  <span>{note}</span>
                </p>
              ))}
            </div>
          </div>
        )}
      </SectionCard>

      {/* Load Mix Planner — embedded below expansion advisory */}
      <LoadMixSection r={r} />
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Load Mix Planner (embedded in Expansion tab)
// ─────────────────────────────────────────────────────────────

function LoadMixSection({ r }: { r: ScenarioResult }) {
  const referenceData = useAppStore((s) => s.referenceData);

  const availableLoadTypes = useMemo(
    () => (referenceData ? Object.keys(referenceData.load_profiles) as LoadType[] : []),
    [referenceData]
  );

  const [totalItMw, setTotalItMw] = useState(String(getCommittedItMw(r).toFixed(2)));
  const [coolingType, setCoolingType] = useState<CoolingType | "">(r.scenario.cooling_type);
  const [densityScenario, setDensityScenario] = useState<DensityScenario>(r.scenario.density_scenario);
  const [stepPct, setStepPct] = useState("10");
  const [minRacks, setMinRacks] = useState("10");
  const [topN, setTopN] = useState("5");
  const [allowedLoadTypes, setAllowedLoadTypes] = useState<LoadType[]>([]);
  const [result, setResult] = useState<LoadMixResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset when selected result changes
  useEffect(() => {
    setTotalItMw(String(getCommittedItMw(r).toFixed(2)));
    setCoolingType(r.scenario.cooling_type);
    setDensityScenario(r.scenario.density_scenario);
    setResult(null);
    setError(null);
  }, [r.site_id, r.scenario.load_type, r.scenario.cooling_type]);

  // Init allowed load types
  useEffect(() => {
    if (availableLoadTypes.length > 0 && allowedLoadTypes.length === 0) {
      setAllowedLoadTypes(availableLoadTypes.slice(0, Math.min(3, availableLoadTypes.length)));
    }
  }, [availableLoadTypes, allowedLoadTypes.length]);

  function toggleLoadType(lt: LoadType) {
    setAllowedLoadTypes((c) => c.includes(lt) ? c.filter((v) => v !== lt) : [...c, lt]);
  }

  async function handleOptimize() {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      if (!coolingType) throw new Error("Choose a cooling type.");
      if (allowedLoadTypes.length < 2) throw new Error("Select at least two load types.");
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
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Load mix optimization failed");
    } finally {
      setRunning(false);
    }
  }

  const availableCoolingTypes = useMemo(
    () => (referenceData ? Object.keys(referenceData.cooling_profiles) as CoolingType[] : []),
    [referenceData]
  );

  return (
    <SectionCard
      title="Load Mix Planner"
      icon={<Layers3 size={16} className="text-blue-500" />}
    >
      <p className="text-xs text-gray-500 mb-3">
        Explore blended workload allocations (e.g. HPC + Colo + AI) within the IT envelope.
        Pre-filled from the selected scenario.
      </p>

      {/* Compact inputs */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mb-3">
        <label className="block">
          <span className="block text-[11px] font-medium text-gray-500 mb-0.5">Total IT (MW)</span>
          <input type="number" min="0.1" step="0.1" value={totalItMw}
            onChange={(e) => setTotalItMw(e.target.value)}
            className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-blue-500 outline-none" />
        </label>
        <label className="block">
          <span className="block text-[11px] font-medium text-gray-500 mb-0.5">Cooling</span>
          <select value={coolingType} onChange={(e) => setCoolingType(e.target.value as CoolingType)}
            className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs bg-white focus:ring-2 focus:ring-blue-500 outline-none">
            <option value="">Select</option>
            {availableCoolingTypes.map((ct) => <option key={ct} value={ct}>{ct}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="block text-[11px] font-medium text-gray-500 mb-0.5">Density</span>
          <select value={densityScenario} onChange={(e) => setDensityScenario(e.target.value as DensityScenario)}
            className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs bg-white focus:ring-2 focus:ring-blue-500 outline-none">
            <option value="low">Low</option>
            <option value="typical">Typical</option>
            <option value="high">High</option>
          </select>
        </label>
        <label className="block">
          <span className="block text-[11px] font-medium text-gray-500 mb-0.5">Step %</span>
          <input type="number" min="5" max="50" step="5" value={stepPct}
            onChange={(e) => setStepPct(e.target.value)}
            className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-blue-500 outline-none" />
        </label>
        <label className="block">
          <span className="block text-[11px] font-medium text-gray-500 mb-0.5">Min Racks</span>
          <input type="number" min="1" value={minRacks}
            onChange={(e) => setMinRacks(e.target.value)}
            className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-blue-500 outline-none" />
        </label>
        <label className="block">
          <span className="block text-[11px] font-medium text-gray-500 mb-0.5">Top N</span>
          <input type="number" min="1" max="20" value={topN}
            onChange={(e) => setTopN(e.target.value)}
            className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:ring-2 focus:ring-blue-500 outline-none" />
        </label>
      </div>

      {/* Load type checkboxes — compact inline */}
      <div className="mb-3">
        <p className="text-[11px] font-medium text-gray-500 mb-1.5">Allowed Load Types</p>
        <div className="flex flex-wrap gap-1.5">
          {availableLoadTypes.map((lt) => (
            <label key={lt} className={`flex items-center gap-1.5 px-2 py-1 rounded border text-xs cursor-pointer ${
              allowedLoadTypes.includes(lt) ? "border-blue-300 bg-blue-50 text-blue-800" : "border-gray-200 bg-white text-gray-600"
            }`}>
              <input type="checkbox" checked={allowedLoadTypes.includes(lt)} onChange={() => toggleLoadType(lt)} className="w-3 h-3" />
              {lt}
            </label>
          ))}
        </div>
      </div>

      <button type="button" onClick={handleOptimize} disabled={running || !referenceData}
        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-xs font-medium">
        {running ? <Loader2 size={14} className="animate-spin" /> : <Target size={14} />}
        {running ? "Optimizing..." : "Suggest Load Mix"}
      </button>

      {error && (
        <p className="mt-2 text-xs text-red-600 flex items-center gap-1.5">
          <AlertCircle size={12} /> {error}
        </p>
      )}

      {/* Results */}
      {result && (
        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Metric label="Total IT" value={`${result.total_it_mw.toFixed(2)} MW`} />
            <Metric label="Cooling" value={result.cooling_type} />
            <Metric label="Density" value={result.density_scenario} />
            <Metric label="Evaluated" value={result.total_candidates_evaluated.toLocaleString()} />
          </div>

          {result.top_candidates.map((candidate) => (
            <div key={candidate.rank} className="rounded-lg border border-gray-200 p-3">
              <div className="flex items-center justify-between gap-3 mb-2">
                <p className="text-xs font-semibold text-gray-800">
                  #{candidate.rank} — Score {candidate.score.toFixed(1)} · PUE {candidate.blended_pue.toFixed(3)} · {candidate.total_racks.toLocaleString()} racks
                </p>
                <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
                  candidate.all_compatible ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"
                }`}>
                  {candidate.all_compatible ? "Compatible" : "Needs Review"}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-2 py-1.5 text-left text-gray-600">Load Type</th>
                      <th className="px-2 py-1.5 text-right text-gray-600">Share</th>
                      <th className="px-2 py-1.5 text-right text-gray-600">IT MW</th>
                      <th className="px-2 py-1.5 text-right text-gray-600">Racks</th>
                      <th className="px-2 py-1.5 text-right text-gray-600">Density</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {candidate.allocations.map((a) => (
                      <tr key={a.load_type}>
                        <td className="px-2 py-1.5 text-gray-700">{a.load_type}</td>
                        <td className="px-2 py-1.5 text-right font-mono">{a.share_pct.toFixed(0)}%</td>
                        <td className="px-2 py-1.5 text-right font-mono">{a.it_load_mw.toFixed(2)}</td>
                        <td className="px-2 py-1.5 text-right font-mono">{a.rack_count.toLocaleString()}</td>
                        <td className="px-2 py-1.5 text-right font-mono">{a.rack_density_kw.toFixed(1)} kW</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {candidate.trade_off_notes.length > 0 && (
                <div className="mt-2 space-y-1">
                  {candidate.trade_off_notes.map((note) => (
                    <p key={note} className="text-[11px] text-gray-500 flex items-start gap-1.5">
                      <AlertCircle size={10} className="mt-0.5 shrink-0 text-gray-400" />
                      {note}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}


// ─────────────────────────────────────────────────────────────
// Tab: Firm Capacity
// ─────────────────────────────────────────────────────────────

function FirmCapacityTab({
  r, firmCapacity, firmCapacityLoading, firmCapacityError, loadFirmCapacity,
  firmAdvisory, firmAdvisoryLoading, firmAdvisoryError, loadFirmAdvisory,
  supportTarget, setSupportTarget, bessCapacityKwh, setBessCapacityKwh,
  fuelCellKw, setFuelCellKw, backupDispatchKw, setBackupDispatchKw,
}: {
  r: ScenarioResult;
  firmCapacity: FirmCapacityResult | null;
  firmCapacityLoading: boolean;
  firmCapacityError: string | null;
  loadFirmCapacity: () => void;
  firmAdvisory: FirmCapacityAdvisoryResult | null;
  firmAdvisoryLoading: boolean;
  firmAdvisoryError: string | null;
  loadFirmAdvisory: () => void;
  supportTarget: string;
  setSupportTarget: (v: string) => void;
  bessCapacityKwh: string;
  setBessCapacityKwh: (v: string) => void;
  fuelCellKw: string;
  setFuelCellKw: (v: string) => void;
  backupDispatchKw: string;
  setBackupDispatchKw: (v: string) => void;
}) {
  // Auto-load advisory when tab opens (if hourly sim available and not yet loaded)
  useEffect(() => {
    if (r.pue_source === "hourly" && !firmAdvisory && !firmAdvisoryLoading && !firmAdvisoryError) {
      loadFirmAdvisory();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      {/* Auto-Advisory Section (no user input required) */}
      <SectionCard
        title="Firm Capacity Advisory"
        icon={<Target size={16} className="text-emerald-500" />}
        action={(
          <button type="button" onClick={loadFirmAdvisory}
            disabled={firmAdvisoryLoading || r.pue_source !== "hourly"}
            className="text-xs px-3 py-1 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50"
          >
            {firmAdvisoryLoading ? <Loader2 size={12} className="animate-spin" /> : "Re-analyse"}
          </button>
        )}
      >
        {r.pue_source !== "hourly" && (
          <p className="text-xs text-gray-500">
            Hourly weather simulation is required. Run a scenario with weather data first.
          </p>
        )}
        {r.pue_source === "hourly" && !firmAdvisory && firmAdvisoryLoading && (
          <div className="flex items-center gap-2 text-xs text-gray-500 py-4">
            <Loader2 size={14} className="animate-spin" /> Loading firm capacity analysis…
          </div>
        )}
        {firmAdvisoryError && <p className="text-xs text-red-600 mt-2">{firmAdvisoryError}</p>}
        {firmAdvisory && (
          <div className="space-y-4 mt-2">
            {/* Capacity spectrum */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Metric label="Firm Capacity (P99)" value={`${firmAdvisory.firm_capacity_mw.toFixed(2)} MW`} />
              <Metric label="Mean Capacity" value={`${firmAdvisory.mean_capacity_mw.toFixed(2)} MW`} />
              <Metric label="Worst Hour" value={`${firmAdvisory.worst_capacity_mw.toFixed(2)} MW`} />
              <Metric label="Best Hour" value={`${firmAdvisory.best_capacity_mw.toFixed(2)} MW`} />
              <Metric label="Capacity Gap" value={`${firmAdvisory.capacity_gap_mw.toFixed(2)} MW`}
                sub="Mean minus Firm (opportunity)" />
              <Metric label="Peak Deficit" value={`${firmAdvisory.peak_deficit_mw.toFixed(2)} MW`}
                sub="Firm minus Worst (to bridge)" />
              <Metric label="Deficit Hours" value={firmAdvisory.deficit_hours.toLocaleString()}
                sub={`${(firmAdvisory.deficit_hours / 8760 * 100).toFixed(1)}% of year`} />
              <Metric label="Deficit Energy" value={`${(firmAdvisory.deficit_energy_kwh / 1000).toFixed(1)} MWh`} />
            </div>

            {/* Deficit chart */}
            {firmAdvisory.hourly_it_kw_sampled && firmAdvisory.hourly_it_kw_sampled.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-800 mb-2">Hourly IT Capacity &amp; Deficit</h4>
                <FirmCapacityDeficitChart advisory={firmAdvisory} />
              </div>
            )}

            {/* Mitigation strategies */}
            {firmAdvisory.strategies.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-800 mb-2">Recommended Mitigation Strategies</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {firmAdvisory.strategies.map((s) => (
                    <div key={s.key} className="rounded-lg border border-gray-200 p-3 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-sm font-medium text-gray-900">{s.label}</p>
                          <p className="text-xs text-gray-500 mt-0.5">{s.description}</p>
                        </div>
                        <span className="shrink-0 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">
                          +{s.capacity_mw.toFixed(2)} MW
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <Metric label="IT Capacity Unlocked" value={`${s.capacity_mw.toFixed(2)} MW`} />
                        <Metric label="Estimated CapEx" value={
                          s.estimated_capex_usd > 0
                            ? `$${(s.estimated_capex_usd / 1000).toFixed(0)}k`
                            : "No CapEx"
                        } />
                      </div>
                      <p className="text-xs text-gray-600 font-mono bg-gray-50 rounded px-2 py-1">{s.sizing_summary}</p>
                      <div className="text-xs text-gray-500 space-y-0.5">
                        {s.notes.map((note, i) => (
                          <p key={i} className="flex items-start gap-1.5">
                            <AlertCircle size={10} className="mt-0.5 shrink-0 text-gray-400" />
                            <span>{note}</span>
                          </p>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {firmAdvisory.strategies.length === 0 && (
              <p className="text-xs text-green-700 bg-green-50 rounded-lg p-3">
                No mitigation needed. The firm capacity is close to the mean capacity, indicating
                minimal hourly variation in cooling overhead for this site and cooling topology.
              </p>
            )}
          </div>
        )}
      </SectionCard>

      {/* Manual Firm Capacity Section (existing, now secondary) */}
      <SectionCard
        title="Custom Peak Support Analysis"
        icon={<Target size={16} className="text-gray-400" />}
        action={(
          <button type="button" onClick={loadFirmCapacity}
            disabled={firmCapacityLoading || r.pue_source !== "hourly"}
            className="text-xs px-3 py-1 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            {firmCapacityLoading ? <Loader2 size={12} className="animate-spin" /> : "Compute"}
          </button>
        )}
      >
      {r.pue_source === "hourly" && (
        <div className="space-y-3">
          <p className="text-xs text-gray-500">
            Advanced: manually specify support assets (BESS, fuel cell, backup) to test custom configurations.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">BESS (kWh)</label>
              <input type="number" min="0" value={bessCapacityKwh}
                onChange={(e) => setBessCapacityKwh(e.target.value)}
                className="w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Fuel Cell (kW)</label>
              <input type="number" min="0" value={fuelCellKw}
                onChange={(e) => setFuelCellKw(e.target.value)}
                className="w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Backup Dispatch (kW)</label>
              <input type="number" min="0" value={backupDispatchKw}
                onChange={(e) => setBackupDispatchKw(e.target.value)}
                className="w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Target IT (MW)</label>
              <input type="number" min="0" step="0.1" value={supportTarget}
                onChange={(e) => setSupportTarget(e.target.value)}
                placeholder="Optional feasibility check"
                className="w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>
          </div>
        </div>
      )}
      {firmCapacityError && <p className="text-xs text-red-600 mt-3">{firmCapacityError}</p>}
      {firmCapacity && (
        <div className="space-y-3 mt-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Metric label="Nominal IT" value={`${firmCapacity.baseline.nominal_it_mw.toFixed(2)} MW`} />
            <Metric label="Grid-Only Worst" value={`${firmCapacity.baseline.worst_it_mw.toFixed(2)} MW`} />
            <Metric label="Grid-Only P99" value={`${firmCapacity.baseline.p99_it_mw.toFixed(2)} MW`} />
            <Metric label="Supported Firm IT" value={`${firmCapacity.supported.max_firm_it_mw.toFixed(2)} MW`} />
            <Metric label="Gain vs Worst" value={`${firmCapacity.supported.gain_vs_worst_mw.toFixed(2)} MW`} />
            <Metric label="Gain vs P99" value={`${firmCapacity.supported.gain_vs_p99_mw.toFixed(2)} MW`} />
            <Metric label="Peak Support" value={`${firmCapacity.supported.peak_support_mw.toFixed(2)} MW`} />
            <Metric label="Peak Facility Need" value={`${firmCapacity.supported.max_required_facility_mw.toFixed(2)} MW`} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Metric label="Hours Above Grid Cap" value={firmCapacity.supported.hours_above_grid_cap.toLocaleString()} />
            <Metric label="Support Hours" value={firmCapacity.supported.hours_with_capacity_support.toLocaleString()} />
            <Metric label="Grid -> BESS" value={`${firmCapacity.supported.grid_to_bess_mwh.toFixed(2)} MWh`} />
            <Metric label="BESS Discharge" value={`${firmCapacity.supported.bess_discharge_mwh.toFixed(2)} MWh`} />
            <Metric label="Fuel Cell" value={`${firmCapacity.supported.fuel_cell_mwh.toFixed(2)} MWh`} />
            <Metric label="Backup Dispatch" value={`${firmCapacity.supported.backup_dispatch_mwh.toFixed(2)} MWh`} />
            <Metric label="PV Direct" value={`${firmCapacity.supported.pv_direct_mwh.toFixed(2)} MWh`} />
            <Metric
              label="BESS Cycle State"
              value={firmCapacity.supported.cyclic_converged ? "Converged" : "Not Converged"}
              sub={firmCapacity.supported.cyclic_bess ? "Cyclic year solve" : undefined}
            />
          </div>
          {firmCapacity.target_evaluation && (
            <div className={`p-3 rounded-lg border text-sm ${
              firmCapacity.target_evaluation.feasible
                ? "bg-green-50 border-green-200"
                : "bg-red-50 border-red-200"
            }`}>
              <p className={firmCapacity.target_evaluation.feasible ? "text-green-700" : "text-red-700"}>
                {firmCapacity.target_evaluation.feasible
                  ? `The target ${firmCapacity.target_evaluation.target_it_mw.toFixed(2)} MW is feasible.`
                  : `The target ${firmCapacity.target_evaluation.target_it_mw.toFixed(2)} MW is not feasible.`}
              </p>
              <p className="text-xs text-gray-600 mt-1">
                Peak support: {firmCapacity.target_evaluation.peak_support_mw.toFixed(2)} MW
                {" · "}Unmet hours: {firmCapacity.target_evaluation.unmet_hours.toLocaleString()}
                {" · "}Unmet energy: {firmCapacity.target_evaluation.unmet_energy_mwh.toFixed(2)} MWh
              </p>
            </div>
          )}
          {firmCapacity.recommendations && (
            <div className="space-y-3">
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                <p className="text-sm font-medium text-gray-800">
                  Suggested compensation target: {firmCapacity.recommendations.target_it_mw.toFixed(2)} MW
                </p>
                <p className="text-xs text-gray-600 mt-1">
                  Gap vs P99 {firmCapacity.recommendations.gap_vs_p99_mw.toFixed(2)} MW ·
                  {" "}Gap vs worst hour {firmCapacity.recommendations.gap_vs_worst_mw.toFixed(2)} MW ·
                  {" "}Peak support need {firmCapacity.recommendations.peak_support_mw.toFixed(2)} MW ·
                  {" "}Annual support energy {firmCapacity.recommendations.annual_support_energy_mwh.toFixed(2)} MWh
                </p>
                {firmCapacity.recommendations.target_already_feasible && (
                  <p className="text-xs text-green-700 mt-2">
                    This target is already feasible without additional support.
                  </p>
                )}
              </div>

              {firmCapacity.recommendations.candidates.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {firmCapacity.recommendations.candidates.map((candidate) => (
                    <div key={candidate.key} className="rounded-lg border border-gray-200 p-3 space-y-2">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-gray-900">{candidate.label}</p>
                          <p className="text-xs text-gray-500 mt-1">{candidate.description}</p>
                        </div>
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          candidate.feasible ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                        }`}>
                          {candidate.feasible ? "Feasible" : "Not Feasible"}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <Metric label="BESS" value={`${candidate.bess_capacity_mwh.toFixed(2)} MWh`} />
                        <Metric label="Fuel Cell" value={`${candidate.fuel_cell_mw.toFixed(2)} MW`} />
                        <Metric label="Backup" value={`${candidate.backup_dispatch_mw.toFixed(2)} MW`} />
                        <Metric label="Peak Support" value={`${candidate.peak_support_mw.toFixed(2)} MW`} />
                        <Metric label="Support Hours" value={candidate.support_hours.toLocaleString()} />
                        <Metric label="Unmet Energy" value={`${candidate.unmet_energy_mwh.toFixed(2)} MWh`} />
                      </div>
                      <div className="text-xs text-gray-600 space-y-1">
                        <p>
                          Dispatch mix: BESS {candidate.bess_discharge_mwh.toFixed(2)} MWh ·
                          {" "}Fuel Cell {candidate.fuel_cell_mwh.toFixed(2)} MWh ·
                          {" "}Backup {candidate.backup_dispatch_mwh.toFixed(2)} MWh
                        </p>
                        {candidate.notes.map((note) => (
                          <p key={note} className="flex items-start gap-1.5">
                            <AlertCircle size={12} className="mt-0.5 shrink-0 text-gray-400" />
                            <span>{note}</span>
                          </p>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </SectionCard>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────
// Shared sub-components
// ─────────────────────────────────────────────────────────────

function SectionCard({
  title,
  icon,
  action,
  children,
}: {
  title: string;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h4 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          {icon}
          {title}
        </h4>
        {action}
      </div>
      {children}
    </div>
  );
}


function Metric({
  label,
  value,
  sub,
  highlight = false,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div className="bg-gray-50 rounded-lg p-2.5">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-sm font-semibold mt-0.5 ${highlight ? "text-blue-600" : "text-gray-900"}`}>
        {value}
      </p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>
  );
}


function CapacitySnapshotCard({
  title,
  snapshot,
  accent = "gray",
}: {
  title: string;
  snapshot: {
    racks: number;
    it_load_mw: number;
    facility_power_mw: number;
    procurement_power_mw: number;
  };
  accent?: "gray" | "green" | "blue";
}) {
  const accentClasses = {
    gray: "border-gray-200 bg-gray-50",
    green: "border-green-200 bg-green-50",
    blue: "border-blue-200 bg-blue-50",
  } as const;

  return (
    <div className={`rounded-lg border p-3 ${accentClasses[accent]}`}>
      <p className="text-sm font-medium text-gray-800 mb-2">{title}</p>
      <div className="grid grid-cols-2 gap-2">
        <Metric label="Racks" value={snapshot.racks.toLocaleString()} />
        <Metric label="IT Load" value={`${snapshot.it_load_mw.toFixed(2)} MW`} />
        <Metric label="Facility" value={`${snapshot.facility_power_mw.toFixed(2)} MW`} />
        <Metric label="Procurement" value={`${snapshot.procurement_power_mw.toFixed(2)} MW`} />
      </div>
    </div>
  );
}


function EnergyBreakdownRow({
  label,
  energyKwh,
  share,
}: {
  label: string;
  energyKwh: number;
  share: number;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="text-gray-600">{label}</span>
        <span className="font-mono text-gray-900">
          {formatKWh(energyKwh)} · {(share * 100).toFixed(1)}%
        </span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-500 rounded-full"
          style={{ width: `${Math.max(share * 100, 0)}%` }}
        />
      </div>
    </div>
  );
}


function formatKWh(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)} GWh`;
  }
  return `${(value / 1_000).toFixed(1)} MWh`;
}


function getCommittedItMw(result: ScenarioResult): number {
  return result.it_capacity_p99_mw ?? result.power.it_load_mw;
}
