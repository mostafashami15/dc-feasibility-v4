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
  Leaf,
  HelpCircle,
  X,
} from "lucide-react";
import { useAppStore } from "../store/useAppStore";
import * as api from "../api/client";
import ITCapacityChart from "../components/charts/ITCapacityChart";
import DailyProfileChart from "../components/charts/DailyProfileChart";
import TornadoChart from "../components/charts/TornadoChart";
import FirmCapacityDeficitChart from "../components/charts/FirmCapacityDeficitChart";
import GreenDispatchChart from "../components/charts/GreenDispatchChart";
import TabGroup from "../components/ui/TabGroup";
import type {
  ScenarioResult,
  ScoreBreakdown,
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
  GreenAdvisoryResult,
  GreenDispatchResult,
  GreenCustomCoverageResult,
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
  { key: "green", label: "Green Energy", icon: <Leaf size={14} /> },
  { key: "firm", label: "Firm Capacity", icon: <Target size={14} /> },
];


// ─────────────────────────────────────────────────────────────
// Score & RAG Info Popover
// ─────────────────────────────────────────────────────────────

function ScoreInfoButton({ result }: { result: ScenarioResult }) {
  const [open, setOpen] = useState(false);
  const bd = result.score_breakdown;

  const WEIGHT_LABELS: Record<string, string> = {
    pue_efficiency: "PUE Efficiency",
    it_capacity: "IT Capacity",
    space_utilization: "Space Utilization",
    rag_status: "Feasibility (RAG)",
    infrastructure_fit: "Infrastructure Fit",
  };
  const SCORE_KEYS: Array<{ key: string; field: keyof ScoreBreakdown }> = [
    { key: "pue_efficiency", field: "pue_score" },
    { key: "it_capacity", field: "it_capacity_score" },
    { key: "space_utilization", field: "space_utilization_score" },
    { key: "rag_status", field: "rag_score" },
    { key: "infrastructure_fit", field: "infrastructure_fit_score" },
  ];

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        className="ml-1 text-gray-400 hover:text-gray-600 transition-colors"
        title="Score & RAG breakdown"
      >
        <HelpCircle size={13} />
      </button>
      {open && (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 z-40" onClick={(e) => { e.stopPropagation(); setOpen(false); }} />
          {/* Popover */}
          <div
            className="absolute right-0 top-6 z-50 w-80 bg-white rounded-xl shadow-xl border border-gray-200 p-4 text-left"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-bold text-gray-900">Score Breakdown</h4>
              <button type="button" onClick={() => setOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X size={14} />
              </button>
            </div>

            {bd ? (
              <div className="space-y-2">
                {/* Component score bars */}
                {SCORE_KEYS.map(({ key, field }) => {
                  const score = bd[field] as number;
                  const weight = bd.weights[key] ?? 0;
                  const reason = bd.component_reasons?.[key];
                  return (
                    <div key={key}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gray-600">{WEIGHT_LABELS[key]}</span>
                        <span className="font-mono text-gray-800">{score.toFixed(0)} <span className="text-gray-400">× {(weight * 100).toFixed(0)}%</span></span>
                      </div>
                      <div className="w-full bg-gray-100 rounded-full h-1.5 mt-0.5">
                        <div
                          className={`h-1.5 rounded-full ${score >= 70 ? "bg-green-500" : score >= 40 ? "bg-amber-400" : "bg-red-400"}`}
                          style={{ width: `${Math.min(100, score)}%` }}
                        />
                      </div>
                      {reason && <p className="text-[10px] text-gray-400 mt-0.5 leading-tight">{reason}</p>}
                    </div>
                  );
                })}

                {/* Composite */}
                <div className="border-t border-gray-100 pt-2 mt-2">
                  <div className="flex items-center justify-between text-xs font-bold">
                    <span className="text-gray-800">Composite Score</span>
                    <span className={`font-mono ${bd.score_capped ? "text-red-600" : "text-gray-900"}`}>
                      {bd.composite_score.toFixed(1)}
                    </span>
                  </div>
                  {bd.score_capped && bd.score_cap_reason && (
                    <p className="text-[10px] text-red-500 mt-1 bg-red-50 rounded p-1.5 leading-tight">
                      {bd.score_cap_reason}
                    </p>
                  )}
                </div>

                {/* RAG reasons */}
                {result.power.rag_reasons.length > 0 && (
                  <div className="border-t border-gray-100 pt-2 mt-2">
                    <p className="text-xs font-semibold text-gray-700 mb-1">RAG Reasons ({result.power.rag_status})</p>
                    <ul className="space-y-0.5">
                      {result.power.rag_reasons.map((reason, i) => (
                        <li key={i} className="text-[10px] text-gray-500 leading-tight flex gap-1">
                          <span className="text-gray-300 shrink-0">•</span>
                          <span>{reason}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                {/* Fallback: just show RAG reasons when no score breakdown */}
                <p className="text-xs text-gray-500">Score breakdown not available for this run.</p>
                {result.power.rag_reasons.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-gray-700 mb-1">RAG Reasons ({result.power.rag_status})</p>
                    <ul className="space-y-0.5">
                      {result.power.rag_reasons.map((reason, i) => (
                        <li key={i} className="text-[10px] text-gray-500 leading-tight flex gap-1">
                          <span className="text-gray-300 shrink-0">•</span>
                          <span>{reason}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </span>
  );
}


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
                    <td className="px-3 py-2.5 text-right font-mono font-medium text-xs">
                      <span className={r.score_breakdown?.score_capped ? "text-red-600" : ""}>
                        {r.score.toFixed(1)}
                      </span>
                      <ScoreInfoButton result={r} />
                    </td>
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
  const sites = useAppStore((s) => s.sites);
  const siteRoofUsable = useMemo(() => {
    const site = sites.find((s) => s.id === r.site_id);
    return site?.site?.roof_usable ?? true;
  }, [sites, r.site_id]);

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


  // ── Actual power values for footprint sizing ──
  // Use committed IT capacity (p99 hourly or static) to derive actual
  // facility and procurement power — not the grid availability envelope.
  const committedItMw = r.it_capacity_p99_mw ?? r.power.it_load_mw;
  const effectivePue = r.annual_pue ?? r.power.pue_used;
  const actualFacilityMw = committedItMw * effectivePue / r.power.eta_chain;
  const actualProcurementMw = actualFacilityMw * r.power.procurement_factor;

  // ── Fetch functions ──
  async function loadFootprint() {
    setFootprintLoading(true);
    setFootprintError(null);
    try {
      const parsedOverride = coolingFootprintOverride.trim()
        ? Number.parseFloat(coolingFootprintOverride)
        : undefined;
      const data = await api.computeFootprint({
        facility_power_mw: actualFacilityMw,
        procurement_power_mw: actualProcurementMw,
        buildable_footprint_m2: r.space.buildable_footprint_m2,
        gray_space_m2: r.space.gray_space_m2,
        roof_usable: siteRoofUsable,
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
            <div className="text-center relative">
              <p className="text-xs text-gray-500">Score</p>
              <p className={`font-bold ${r.score_breakdown?.score_capped ? "text-red-600" : "text-gray-900"}`}>
                {r.score.toFixed(1)}
                <ScoreInfoButton result={r} />
              </p>
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
            siteRoofUsable={siteRoofUsable}
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

        {activeTab === "green" && (
          <GreenEnergyTab r={r} />
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

      {/* Gray space breakdown */}
      <div>
        <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
          Building Area Split
          {r.space.gray_space_ratio < 0.55 && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800">
              Gray space tight
            </span>
          )}
        </h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
          <Metric label="Gross Building Area" value={`${r.space.gross_building_area_m2.toLocaleString()} m²`} />
          <Metric label="IT Whitespace" value={`${r.space.it_whitespace_m2.toLocaleString()} m²`} />
          <Metric label="Gray Space" value={`${r.space.gray_space_m2.toLocaleString()} m²`} />
          <Metric label="Gray Space Ratio" value={`${(r.space.gray_space_ratio * 100).toFixed(0)}%`} />
        </div>
        {/* Stacked bar: whitespace vs gray space */}
        <div className="w-full h-6 rounded-md overflow-hidden flex" title={`Whitespace: ${(r.space.whitespace_ratio_used * 100).toFixed(0)}% | Gray: ${(r.space.gray_space_ratio * 100).toFixed(0)}%`}>
          <div
            className="h-full bg-blue-500 flex items-center justify-center text-[10px] text-white font-medium"
            style={{ width: `${r.space.whitespace_ratio_used * 100}%` }}
          >
            {r.space.whitespace_ratio_used >= 0.15 && `IT ${(r.space.whitespace_ratio_used * 100).toFixed(0)}%`}
          </div>
          <div
            className="h-full bg-gray-400 flex items-center justify-center text-[10px] text-white font-medium"
            style={{ width: `${r.space.gray_space_ratio * 100}%` }}
          >
            {r.space.gray_space_ratio >= 0.15 && `Gray ${(r.space.gray_space_ratio * 100).toFixed(0)}%`}
          </div>
        </div>
        <div className="flex gap-4 mt-1 text-[10px] text-gray-500">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-blue-500 inline-block"></span>IT Whitespace</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-gray-400 inline-block"></span>Gray Space (Support)</span>
        </div>
        {r.space.gray_space_ratio < 0.55 && (
          <p className="mt-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            Gray space ratio is {(r.space.gray_space_ratio * 100).toFixed(0)}% (below 55% threshold for Tier III).
            Support infrastructure (power rooms, cooling plant, corridors) may be constrained.
          </p>
        )}
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
  setFootprintBackupType, siteRoofUsable,
  coolingFootprintOverride, setCoolingFootprintOverride,
  loadFootprint, backup, backupLoading, loadBackup,
}: {
  r: ScenarioResult;
  footprint: FootprintResult | null;
  footprintLoading: boolean;
  footprintError: string | null;
  footprintBackupType: BackupPowerType;
  setFootprintBackupType: (v: BackupPowerType) => void;
  siteRoofUsable: boolean;
  coolingFootprintOverride: string;
  setCoolingFootprintOverride: (v: string) => void;
  loadFootprint: () => void;
  backup: BackupPowerComparison | null;
  backupLoading: boolean;
  loadBackup: () => void;
}) {
  // Auto-load footprint and backup comparison when tab opens
  useEffect(() => {
    if (!footprint && !footprintLoading && !footprintError) {
      loadFootprint();
    }
    if (!backup && !backupLoading) {
      loadBackup();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-6">
      <SectionCard
        title="Infrastructure Footprint"
        icon={<Building2 size={16} className="text-gray-500" />}
        action={(
          <button type="button" onClick={loadFootprint} disabled={footprintLoading}
            className="text-xs px-3 py-1 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            {footprintLoading ? <Loader2 size={12} className="animate-spin" /> : "Recompute"}
          </button>
        )}
      >
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
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
          <div className="flex items-center gap-2 self-end pb-1">
            <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${siteRoofUsable ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
              Roof {siteRoofUsable ? "usable" : "not usable"}
            </span>
            <span className="text-xs text-gray-400">(set in Site Manager)</span>
          </div>
          <div className="text-xs text-gray-500 self-end">
            All equipment placed in gray space. Cooling on roof only if usable.
          </div>
        </div>
        {footprintError && <p className="text-xs text-red-600 mb-3">{footprintError}</p>}
        {footprint && (
          <div className="space-y-3">
            {/* Warnings */}
            {footprint.warnings.length > 0 && (
              <div className="space-y-1">
                {footprint.warnings.map((w, i) => (
                  <p key={i} className={`text-xs px-3 py-2 rounded border ${
                    !footprint.all_fits
                      ? "text-red-700 bg-red-50 border-red-200"
                      : "text-amber-700 bg-amber-50 border-amber-200"
                  }`}>{w}</p>
                ))}
              </div>
            )}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Metric label="Gray Space Equipment" value={`${footprint.total_gray_space_equipment_m2.toLocaleString()} m²`} />
              <Metric label="Roof Equipment" value={`${footprint.total_roof_equipment_m2.toLocaleString()} m²`} />
              <Metric label="Gray Space Available" value={`${footprint.gray_space_m2.toLocaleString()} m²`} />
              <Metric label="Gray Space Remaining" value={`${footprint.gray_space_remaining_m2.toLocaleString()} m²`} />
              <Metric label="Gray Space Utilization" value={`${(footprint.gray_space_utilization_ratio * 100).toFixed(0)}%`} />
              <Metric label="Roof Utilization" value={footprint.roof_usable ? `${(footprint.roof_utilization_ratio * 100).toFixed(0)}%` : "N/A"} />
              <Metric label="Backup Units" value={footprint.backup_num_units.toLocaleString()} />
              <Metric label="Unit Size" value={`${footprint.backup_unit_size_kw.toLocaleString()} kW`} />
            </div>
            <div className="flex items-center gap-2 text-xs flex-wrap">
              <span className={`px-2 py-0.5 rounded-full font-medium ${
                footprint.gray_space_fits ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
              }`}>
                Gray space {footprint.gray_space_fits ? "fits" : "does NOT fit"}
              </span>
              {footprint.roof_usable && (
                <span className={`px-2 py-0.5 rounded-full font-medium ${
                  footprint.roof_fits ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                }`}>
                  Roof {footprint.roof_fits ? "fits" : "does NOT fit"}
                </span>
              )}
              {!footprint.roof_usable && (
                <span className="px-2 py-0.5 rounded-full font-medium bg-gray-100 text-gray-600">
                  Roof not usable — cooling in gray space
                </span>
              )}
              <span className="text-gray-500">Backup: {footprint.backup_power_type}</span>
            </div>
            {/* Gray space utilization bar */}
            <div>
              <div className="text-[10px] text-gray-500 mb-1">Gray Space Utilization</div>
              <div className="w-full h-5 rounded-md overflow-hidden flex bg-gray-100">
                <div
                  className={`h-full flex items-center justify-center text-[10px] text-white font-medium ${
                    footprint.gray_space_fits ? "bg-blue-500" : "bg-red-500"
                  }`}
                  style={{ width: `${Math.min(100, footprint.gray_space_utilization_ratio * 100)}%` }}
                >
                  {footprint.gray_space_utilization_ratio >= 0.15 && `${(footprint.gray_space_utilization_ratio * 100).toFixed(0)}%`}
                </div>
              </div>
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
                      <td className="px-3 py-2 text-gray-500">
                        {element.location === "gray_space" ? "Gray Space" : "Roof"}
                      </td>
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
              <p>Smallest footprint: {backup.lowest_footprint_technology}</p>
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
// Tab: Green Energy
// ─────────────────────────────────────────────────────────────

/** Smart unit formatting: auto-scales k → M → G → T based on magnitude */
function smartPower(kwp: number): string {
  if (kwp >= 1e9) return `${(kwp / 1e9).toFixed(1)} TWp`;
  if (kwp >= 1e6) return `${(kwp / 1e6).toFixed(1)} GWp`;
  if (kwp >= 1e3) return `${(kwp / 1e3).toFixed(1)} MWp`;
  return `${kwp.toFixed(0)} kWp`;
}
function smartEnergy(kwh: number): string {
  if (kwh >= 1e9) return `${(kwh / 1e9).toFixed(1)} TWh`;
  if (kwh >= 1e6) return `${(kwh / 1e6).toFixed(1)} GWh`;
  if (kwh >= 1e3) return `${(kwh / 1e3).toFixed(1)} MWh`;
  return `${kwh.toFixed(0)} kWh`;
}
function smartEnergyMwh(mwh: number): string {
  if (mwh >= 1e6) return `${(mwh / 1e6).toFixed(1)} TWh`;
  if (mwh >= 1e3) return `${(mwh / 1e3).toFixed(1)} GWh`;
  return `${mwh.toFixed(1)} MWh`;
}

function GreenEnergyTab({ r }: { r: ScenarioResult }) {
  const green = r.green_energy as GreenDispatchResult | null;
  const [advisory, setAdvisory] = useState<GreenAdvisoryResult | null>(null);
  const [advisoryLoading, setAdvisoryLoading] = useState(false);
  const [advisoryError, setAdvisoryError] = useState<string | null>(null);
  const [customCoverage, setCustomCoverage] = useState(50);
  const [customResult, setCustomResult] = useState<GreenCustomCoverageResult | null>(null);
  const [customLoading, setCustomLoading] = useState(false);
  const [customError, setCustomError] = useState<string | null>(null);

  function loadAdvisory() {
    setAdvisoryLoading(true);
    setAdvisoryError(null);
    api.fetchGreenAdvisory(r.site_id, r.scenario)
      .then(setAdvisory)
      .catch((e) => setAdvisoryError(e?.response?.data?.detail || "Failed to load advisory"))
      .finally(() => setAdvisoryLoading(false));
  }

  function loadCustomCoverage() {
    setCustomLoading(true);
    setCustomError(null);
    api.fetchGreenCustomCoverage(r.site_id, r.scenario, customCoverage / 100)
      .then(setCustomResult)
      .catch((e) => setCustomError(e?.response?.data?.detail || "Failed to compute custom coverage"))
      .finally(() => setCustomLoading(false));
  }

  if (!green) {
    return (
      <div className="text-center py-10">
        <Leaf size={40} className="mx-auto text-gray-300 mb-3" />
        <p className="text-gray-500 text-sm">No green energy configuration for this site.</p>
        <p className="text-gray-400 text-xs mt-1">
          Add PV capacity, BESS, or fuel cell in Site Manager to enable green dispatch.
        </p>
      </div>
    );
  }

  const fmtMWh = (kwh: number) => (kwh / 1000).toFixed(1) + " MWh";
  const fmtPct = (v: number) => (v * 100).toFixed(1) + "%";
  const pvParams = green.pvgis_params;

  // Detect PV-only physical ceiling from advisory results
  const pvOnlyMaxCoverage = advisory
    ? Math.max(...advisory.levels.filter(l => l.pv_only_ceiling_reached).map(l => l.pv_only_coverage_achieved), 0)
    : 0;

  return (
    <div className="space-y-6">
      {/* Headline metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <MetricBox label="Renewable Fraction" value={fmtPct(green.renewable_fraction)} color="emerald" />
        <MetricBox label="Overhead Coverage" value={fmtPct(green.overhead_coverage_fraction)} color="emerald" />
        <MetricBox label="CO2 Avoided" value={`${green.co2_avoided_tonnes.toFixed(1)} tCO2`} color="green" />
        <MetricBox label="Grid Import (Overhead)" value={fmtMWh(green.total_grid_import_kwh)} color="gray" />
      </div>

      {/* Configuration summary */}
      <div className="bg-gray-50 rounded-lg p-4">
        <h4 className="text-sm font-medium text-gray-700 mb-2">Green Energy Configuration</h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <div><span className="text-gray-500">PV Capacity:</span> {green.pv_capacity_kwp.toLocaleString()} kWp</div>
          <div><span className="text-gray-500">BESS:</span> {green.bess_capacity_kwh.toLocaleString()} kWh</div>
          <div><span className="text-gray-500">BESS Eff:</span> {fmtPct(green.bess_roundtrip_efficiency)}</div>
          <div><span className="text-gray-500">Fuel Cell:</span> {green.fuel_cell_capacity_kw.toLocaleString()} kW</div>
        </div>
        {/* PVGIS assumptions */}
        {pvParams && green.pv_profile_source === "pvgis" && (
          <div className="mt-3 pt-3 border-t border-gray-200">
            <h5 className="text-xs font-medium text-gray-500 mb-1.5">PVGIS Solar Profile Parameters</h5>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-gray-600">
              <div><span className="text-gray-400">Years:</span> {pvParams.start_year}–{pvParams.end_year}</div>
              <div><span className="text-gray-400">Technology:</span> {pvParams.pv_technology}</div>
              <div><span className="text-gray-400">Mounting:</span> {pvParams.mounting_place}</div>
              <div><span className="text-gray-400">System Loss:</span> {pvParams.system_loss_pct}%</div>
              <div><span className="text-gray-400">Horizon:</span> {pvParams.use_horizon ? "Yes" : "No"}</div>
              <div><span className="text-gray-400">Optimal Angles:</span> {pvParams.optimal_angles ? "Yes" : "No"}</div>
              {!pvParams.optimal_angles && pvParams.surface_tilt_deg != null && (
                <div><span className="text-gray-400">Tilt:</span> {pvParams.surface_tilt_deg}°</div>
              )}
              {!pvParams.optimal_angles && pvParams.surface_azimuth_deg != null && (
                <div><span className="text-gray-400">Azimuth:</span> {pvParams.surface_azimuth_deg}°</div>
              )}
            </div>
          </div>
        )}
        {green.pv_profile_source === "zero" && (
          <p className="mt-2 text-[10px] text-gray-400">PV profile: None (zero generation)</p>
        )}
        {green.pv_profile_source === "manual" && (
          <p className="mt-2 text-[10px] text-gray-400">PV profile: Manual hourly upload</p>
        )}
      </div>

      {/* Hourly dispatch chart */}
      {green.hourly_dispatch && green.hourly_dispatch.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h4 className="text-sm font-medium text-gray-700 mb-3">Hourly Overhead Dispatch Profile</h4>
          <GreenDispatchChart
            hourlyDispatch={green.hourly_dispatch}
            totalOverheadMwh={green.total_overhead_kwh / 1000}
            pvToOverheadMwh={green.total_pv_to_overhead_kwh / 1000}
            bessDischargeMwh={green.total_bess_discharge_kwh / 1000}
            fuelCellMwh={green.total_fuel_cell_kwh / 1000}
            gridImportMwh={green.total_grid_import_kwh / 1000}
          />
        </div>
      )}

      {/* Dispatch breakdown */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h4 className="text-sm font-medium text-gray-700 mb-3">Annual Energy Dispatch</h4>
        <div className="space-y-2">
          {[
            { label: "PV Generation", value: green.total_pv_generation_kwh, color: "bg-yellow-400" },
            { label: "PV to Overhead", value: green.total_pv_to_overhead_kwh, color: "bg-green-400" },
            { label: "PV to BESS", value: green.total_pv_to_bess_kwh, color: "bg-emerald-400" },
            { label: "PV Curtailed", value: green.total_pv_curtailed_kwh, color: "bg-gray-300" },
            { label: "BESS Discharge", value: green.total_bess_discharge_kwh, color: "bg-blue-400" },
            { label: "Fuel Cell", value: green.total_fuel_cell_kwh, color: "bg-purple-400" },
            { label: "Grid Import (OH)", value: green.total_grid_import_kwh, color: "bg-red-300" },
          ].map(({ label, value, color }) => {
            const total = green.total_facility_kwh || 1;
            const pct = (value / total) * 100;
            return (
              <div key={label} className="flex items-center gap-3 text-xs">
                <span className="w-28 text-gray-600 text-right">{label}</span>
                <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
                  <div className={`h-full ${color} rounded-full`} style={{ width: `${Math.min(pct, 100)}%` }} />
                </div>
                <span className="w-24 text-gray-700">{fmtMWh(value)}</span>
                <span className="w-12 text-gray-400 text-right">{pct.toFixed(1)}%</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Additional metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
        <div className="bg-gray-50 rounded-lg p-3">
          <p className="text-xs text-gray-500">PV Self-Consumption</p>
          <p className="font-medium">{fmtPct(green.pv_self_consumption_fraction)}</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3">
          <p className="text-xs text-gray-500">BESS Equivalent Cycles/yr</p>
          <p className="font-medium">{green.bess_cycles_equivalent.toFixed(1)}</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3">
          <p className="text-xs text-gray-500">Total Overhead</p>
          <p className="font-medium">{fmtMWh(green.total_overhead_kwh)}</p>
        </div>
      </div>

      {/* Advisory Mode */}
      <div className="border-t border-gray-200 pt-5">
        <h4 className="text-sm font-medium text-gray-700 mb-2">Advisory Mode: Coverage Target Sizing</h4>
        <p className="text-xs text-gray-500 mb-3">
          Compare PV-only vs PV+BESS sizing to reach 10%–100% overhead coverage from renewables.
        </p>
        {!advisory && !advisoryLoading && (
          <button onClick={loadAdvisory}
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm hover:bg-emerald-700">
            Compute Advisory Sizing
          </button>
        )}
        {advisoryLoading && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Loader2 size={16} className="animate-spin" /> Computing advisory sizing...
          </div>
        )}
        {advisoryError && (
          <p className="text-sm text-red-600">{advisoryError}</p>
        )}
        {advisory && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-gray-50 text-center">
                    <th rowSpan={2} className="px-3 py-2 text-xs font-medium text-gray-500 text-left border-r border-gray-200">Coverage<br/>Target</th>
                    <th className="px-3 py-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 border-r border-gray-200">PV Only</th>
                    <th colSpan={2} className="px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 border-r border-gray-200">PV + BESS</th>
                    <th colSpan={2} className="px-3 py-1.5 text-xs font-medium text-gray-500">Output (PV+BESS)</th>
                  </tr>
                  <tr className="bg-gray-50 text-left">
                    <th className="px-3 py-1.5 text-xs font-medium text-gray-500 border-r border-gray-200">PV Needed</th>
                    <th className="px-3 py-1.5 text-xs font-medium text-gray-500">PV Needed</th>
                    <th className="px-3 py-1.5 text-xs font-medium text-gray-500 border-r border-gray-200">BESS Needed</th>
                    <th className="px-3 py-1.5 text-xs font-medium text-gray-500">Annual Gen</th>
                    <th className="px-3 py-1.5 text-xs font-medium text-gray-500">CO2 Avoided</th>
                  </tr>
                </thead>
                <tbody>
                  {advisory.levels.map((level) => {
                    const isCeiling = level.pv_only_ceiling_reached;
                    return (
                      <tr key={level.coverage_target} className="border-t border-gray-100 text-center">
                        <td className="px-3 py-2 font-medium text-left border-r border-gray-200">{(level.coverage_target * 100).toFixed(0)}%</td>
                        <td className={`px-3 py-2 border-r border-gray-200 ${isCeiling ? "bg-amber-50/50" : "bg-emerald-50/30"}`}>
                          {isCeiling ? (
                            <span className="text-amber-600" title="PV alone cannot reach this coverage (limited by nighttime hours with zero solar)">
                              max {fmtPct(level.pv_only_coverage_achieved)}
                            </span>
                          ) : (
                            smartPower(level.pv_only_kwp_needed)
                          )}
                        </td>
                        <td className="px-3 py-2 bg-blue-50/30">{smartPower(level.pv_kwp_needed)}</td>
                        <td className="px-3 py-2 bg-blue-50/30 border-r border-gray-200">{smartEnergy(level.bess_kwh_needed)}</td>
                        <td className="px-3 py-2">{smartEnergyMwh(level.annual_generation_mwh)}</td>
                        <td className="px-3 py-2">{level.co2_avoided_tonnes.toFixed(1)} t</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {pvOnlyMaxCoverage > 0 && (
              <p className="text-[10px] text-amber-600 mt-2">
                PV-only maximum achievable coverage: ~{fmtPct(pvOnlyMaxCoverage)} — limited by nighttime hours with zero solar generation. BESS enables storing daytime surplus for nighttime use.
              </p>
            )}

            {/* Advisory visualization — PV+BESS capacity breakdown */}
            <div className="mt-4 bg-white border border-gray-200 rounded-lg p-4">
              <h5 className="text-xs font-medium text-gray-600 mb-3">PV + BESS Required Capacity by Coverage Target</h5>
              <div className="space-y-2">
                {advisory.levels.map((level) => {
                  const maxCap = Math.max(...advisory.levels.map(l => l.pv_kwp_needed + l.bess_kwh_needed)) || 1;
                  const pvPct = (level.pv_kwp_needed / maxCap) * 100;
                  const bessPct = (level.bess_kwh_needed / maxCap) * 100;
                  return (
                    <div key={level.coverage_target} className="flex items-center gap-2">
                      <span className="w-10 text-xs font-medium text-gray-600 text-right">{(level.coverage_target * 100).toFixed(0)}%</span>
                      <div className="flex-1 h-6 bg-gray-100 rounded-md overflow-hidden flex">
                        <div className="h-full bg-emerald-400 flex items-center justify-center text-[9px] text-white font-medium"
                          style={{ width: `${Math.max(pvPct, 0)}%`, minWidth: pvPct > 3 ? "auto" : "0" }}>
                          {pvPct > 8 && smartPower(level.pv_kwp_needed)}
                        </div>
                        <div className="h-full bg-blue-400 flex items-center justify-center text-[9px] text-white font-medium"
                          style={{ width: `${Math.max(bessPct, 0)}%`, minWidth: bessPct > 3 ? "auto" : "0" }}>
                          {bessPct > 8 && smartEnergy(level.bess_kwh_needed)}
                        </div>
                      </div>
                      <span className="w-20 text-[10px] text-gray-500 text-right">{smartPower(level.pv_kwp_needed)}</span>
                    </div>
                  );
                })}
              </div>
              <div className="flex justify-center gap-4 mt-3 text-[10px] text-gray-500">
                <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-400 inline-block" /> PV Capacity</span>
                <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-blue-400 inline-block" /> BESS Capacity</span>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Custom Coverage Slider */}
      <div className="border-t border-gray-200 pt-5">
        <h4 className="text-sm font-medium text-gray-700 mb-2">Custom Coverage Target</h4>
        <p className="text-xs text-gray-500 mb-3">
          Select a specific overhead coverage percentage and compute the required sizing.
        </p>
        <div className="flex items-center gap-4">
          <input
            type="range" min={0} max={100} step={1}
            value={customCoverage}
            onChange={(e) => setCustomCoverage(parseInt(e.target.value))}
            className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-emerald-600"
          />
          <span className="text-sm font-semibold w-12 text-right">{customCoverage}%</span>
          <button onClick={loadCustomCoverage} disabled={customLoading}
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-2">
            {customLoading && <Loader2 size={14} className="animate-spin" />}
            Calculate
          </button>
        </div>
        {customError && <p className="text-sm text-red-600 mt-2">{customError}</p>}
        {customResult && (
          <div className="mt-3 bg-gray-50 rounded-lg p-4">
            <p className="text-xs font-medium text-gray-600 mb-2">
              Results for {(customResult.coverage_target * 100).toFixed(0)}% overhead coverage:
            </p>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-emerald-700">PV Only</p>
                {customResult.pv_only_ceiling_reached ? (
                  <>
                    <div className="text-amber-600 text-xs font-medium">Cannot reach target with PV alone</div>
                    <div><span className="text-gray-500 text-xs">Max Coverage:</span> <span className="font-medium">{fmtPct(customResult.pv_only_coverage_achieved)}</span></div>
                    <div><span className="text-gray-500 text-xs">PV at plateau:</span> <span className="font-medium">{smartPower(customResult.pv_only_kwp_needed)}</span></div>
                  </>
                ) : (
                  <>
                    <div><span className="text-gray-500 text-xs">PV Needed:</span> <span className="font-medium">{smartPower(customResult.pv_only_kwp_needed)}</span></div>
                    <div><span className="text-gray-500 text-xs">Annual Gen:</span> <span className="font-medium">{smartEnergyMwh(customResult.pv_only_annual_gen_mwh)}</span></div>
                    <div><span className="text-gray-500 text-xs">CO2 Avoided:</span> <span className="font-medium">{customResult.pv_only_co2_avoided_tonnes.toFixed(1)} t</span></div>
                  </>
                )}
              </div>
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-blue-700">PV + BESS</p>
                <div><span className="text-gray-500 text-xs">PV Needed:</span> <span className="font-medium">{smartPower(customResult.pv_kwp_needed)}</span></div>
                <div><span className="text-gray-500 text-xs">BESS Needed:</span> <span className="font-medium">{smartEnergy(customResult.bess_kwh_needed)}</span></div>
                <div><span className="text-gray-500 text-xs">Annual Gen:</span> <span className="font-medium">{smartEnergyMwh(customResult.annual_generation_mwh)}</span></div>
                <div><span className="text-gray-500 text-xs">CO2 Avoided:</span> <span className="font-medium">{customResult.co2_avoided_tonnes.toFixed(1)} t</span></div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function MetricBox({ label, value, color = "blue" }: { label: string; value: string; color?: string }) {
  const colorMap: Record<string, string> = {
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-700",
    green: "bg-green-50 border-green-200 text-green-700",
    blue: "bg-blue-50 border-blue-200 text-blue-700",
    gray: "bg-gray-50 border-gray-200 text-gray-700",
  };
  return (
    <div className={`rounded-lg border p-3 ${colorMap[color] || colorMap.blue}`}>
      <p className="text-xs opacity-75">{label}</p>
      <p className="text-lg font-semibold mt-0.5">{value}</p>
    </div>
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
