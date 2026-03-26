/**
 * SiteManager — Page 1: Site CRUD + Maps + Grid Infrastructure
 * ==============================================================
 * Redesigned for clarity:
 *   - Form hidden by default, shown on "New Site" or site selection
 *   - 3-map layout: Overview, Terrain, Detail+Infrastructure
 *   - Grid context with smart filtering (unknown voltages hidden by default)
 *   - Collapsible sections throughout
 *
 * Architecture Agreement Section 6, Page 1.
 */

import { useState, useEffect, useRef } from "react";
import {
  Plus, Pencil, Trash2, Search, MapPin, Loader2, Upload,
  ChevronDown, ChevronUp, Zap, Eye, EyeOff, RefreshCw,
  Mountain, Info, AlertCircle, X,
} from "lucide-react";
import { useAppStore } from "../store/useAppStore";
import * as api from "../api/client";
import MapView from "../components/MapView";
import type {
  GridAnalysisGrade,
  GridConfidence,
  GridContextResult,
  GridOfficialEvidence,
  Site,
  SpaceResult,
  SiteType,
  BuildableAreaMode,
  PowerInputMode,
  KMLUploadResponse,
} from "../types";
import { DEFAULT_SITE } from "../types";


// ─── Constants ────────────────────────────────────────────────

const SITE_TYPES: SiteType[] = [
  "Greenfield", "Brownfield", "Retrofit", "Built-to-Suit"
];

const BUILDABLE_MODES: { value: BuildableAreaMode; label: string }[] = [
  { value: "ratio", label: "Ratio (land × coverage)" },
  { value: "absolute", label: "Absolute (from permit)" },
];

const POWER_MODES: { value: PowerInputMode; label: string }[] = [
  { value: "operational", label: "Operational (facility draws this)" },
  { value: "grid_reservation", label: "Grid Reservation (includes redundancy)" },
];

const GRID_RADIUS_OPTIONS = [
  { value: 0.5, label: "500 m" },
  { value: 1, label: "1 km" },
  { value: 2, label: "2 km" },
  { value: 5, label: "5 km" },
  { value: 10, label: "10 km" },
] as const;

const DEFAULT_GRID_OFFICIAL_EVIDENCE: GridOfficialEvidence = {
  utility_or_tso_reference: null,
  reference_date: null,
  confirmed_substation_name: null,
  confirmed_voltage_kv: null,
  confirmed_requested_mw: null,
  confirmed_available_mw: null,
  connection_status: null,
  timeline_status: null,
  notes: null,
};


// ─── Helpers ──────────────────────────────────────────────────

function getApiErrorDetail(error: unknown, fallback: string): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    return response?.data?.detail || fallback;
  }
  return fallback;
}

function getApiStatusCode(error: unknown): number | null {
  if (typeof error === "object" && error !== null && "response" in error) {
    return (error as { response?: { status?: number } }).response?.status ?? null;
  }
  return null;
}

function formatGridAnalysisGrade(analysisGrade: GridAnalysisGrade): string {
  return analysisGrade === "screening_grade" ? "Screening-grade" : analysisGrade;
}

function formatGridConfidence(confidence: GridConfidence): string {
  if (confidence === "mapped_public") return "Mapped-public";
  if (confidence === "official_aggregate") return "Official aggregate";
  if (confidence === "user_confirmed") return "User confirmed";
  return confidence;
}

function formatGridSourceLayer(source: string): string {
  if (source === "mapped_public_osm_overpass") return "OSM / Overpass";
  if (source === "mapped_public_fixture") return "Fixture";
  if (source === "user_confirmed_manual") return "Manual evidence";
  return source.split("_").map((t) => t.charAt(0).toUpperCase() + t.slice(1)).join(" ");
}

function formatGridGeneratedAt(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return `${new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium", timeStyle: "short", timeZone: "UTC",
  }).format(date)} UTC`;
}

function hasGridOfficialEvidence(evidence: GridOfficialEvidence | null): boolean {
  if (!evidence) return false;
  return Object.values(evidence).some((v) => v !== null && v !== "");
}

function describeGridScoreSignal(overallScore: number): string {
  if (overallScore >= 70) return "Strong signal for grid follow-up";
  if (overallScore >= 45) return "Moderate signal — needs utility confirmation";
  if (overallScore > 0) return "Limited signal in screening radius";
  return "No meaningful signal found";
}

function getGridScoreColor(overallScore: number): string {
  if (overallScore >= 70) return "text-emerald-700";
  if (overallScore >= 45) return "text-amber-700";
  if (overallScore > 0) return "text-slate-700";
  return "text-gray-500";
}


// ─── Collapsible Section ──────────────────────────────────────

function Section({
  title, badge, defaultOpen = false, icon, children,
}: {
  title: string;
  badge?: string;
  defaultOpen?: boolean;
  icon?: React.ReactNode;
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
          <h3 className="font-semibold text-gray-800">{title}</h3>
          {badge && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
              {badge}
            </span>
          )}
        </div>
        {open ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
      </button>
      {open && <div className="border-t border-gray-100">{children}</div>}
    </div>
  );
}


// ─── Metric Card ──────────────────────────────────────────────

function MetricCard({ label, value, highlight }: {
  label: string; value: string; highlight?: boolean;
}) {
  return (
    <div className={`rounded-lg p-3 ${highlight ? "bg-blue-50 border border-blue-200" : "bg-gray-50"}`}>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-lg font-bold mt-0.5 ${highlight ? "text-blue-700" : "text-gray-900"}`}>{value}</p>
    </div>
  );
}


// ═════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═════════════════════════════════════════════════════════════

export default function SiteManager() {
  const kmlInputRef = useRef<HTMLInputElement | null>(null);
  const gridRequestVersionRef = useRef(0);
  const sites = useAppStore((s) => s.sites);
  const selectedSiteId = useAppStore((s) => s.selectedSiteId);
  const sitesLoading = useAppStore((s) => s.sitesLoading);
  const sitesError = useAppStore((s) => s.sitesError);
  const selectSite = useAppStore((s) => s.selectSite);
  const removeSite = useAppStore((s) => s.removeSite);
  const loadSites = useAppStore((s) => s.loadSites);

  // ── Form state ──
  const [formData, setFormData] = useState<Site>({ ...DEFAULT_SITE });
  const [isEditing, setIsEditing] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [preview, setPreview] = useState<SpaceResult | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // ── Geocoding ──
  const [geocodeQuery, setGeocodeQuery] = useState("");
  const [geocodeResults, setGeocodeResults] = useState<
    Array<{ latitude: number; longitude: number; name: string; country: string; admin1: string }>
  >([]);
  const [geocoding, setGeocoding] = useState(false);
  const [geocodeError, setGeocodeError] = useState<string | null>(null);

  // ── KML Upload ──
  const [uploadingKml, setUploadingKml] = useState(false);
  const [kmlError, setKmlError] = useState<string | null>(null);
  const [kmlResults, setKmlResults] = useState<KMLUploadResponse["coordinates"]>([]);

  // ── Grid Context ──
  const [gridRadiusKm, setGridRadiusKm] = useState(5);
  const [gridCacheLoading, setGridCacheLoading] = useState(false);
  const [gridLoading, setGridLoading] = useState(false);
  const [gridError, setGridError] = useState<string | null>(null);
  const [gridContext, setGridContext] = useState<GridContextResult | null>(null);
  const [gridOfficialEvidence, setGridOfficialEvidence] = useState<GridOfficialEvidence>({
    ...DEFAULT_GRID_OFFICIAL_EVIDENCE,
  });
  const [gridEvidenceLoading, setGridEvidenceLoading] = useState(false);
  const [gridEvidenceSaving, setGridEvidenceSaving] = useState(false);
  const [gridEvidenceDeleting, setGridEvidenceDeleting] = useState(false);
  const [gridEvidenceError, setGridEvidenceError] = useState<string | null>(null);
  const [gridFocusedAssetId, setGridFocusedAssetId] = useState<string | null>(null);
  const [showGridOverlay, setShowGridOverlay] = useState(true);
  const [showUnknownVoltage, setShowUnknownVoltage] = useState(false);
  const [showEvidenceForm, setShowEvidenceForm] = useState(false);


  // ── Derived ──
  const selectedSite = selectedSiteId
    ? sites.find((site) => site.id === selectedSiteId) ?? null
    : null;
  const selectedSiteHasCoordinates = (
    selectedSite?.site.latitude != null && selectedSite?.site.longitude != null
  );
  const gridSiteCenter = selectedSiteHasCoordinates
    ? { lat: selectedSite!.site.latitude!, lon: selectedSite!.site.longitude! }
    : null;

  // Grid asset filtering — hide unknown voltage by default
  const filteredGridAssets = gridContext
    ? gridContext.assets.filter((asset) => {
        if (!showUnknownVoltage && asset.voltage_kv === null) return false;
        return true;
      })
    : [];
  const sortedGridAssets = [...filteredGridAssets].sort((a, b) => {
    // Sort: substations first, then by voltage desc, then by distance
    if (a.asset_type !== b.asset_type) {
      return a.asset_type === "substation" ? -1 : 1;
    }
    return (b.voltage_kv ?? 0) - (a.voltage_kv ?? 0) || a.distance_km - b.distance_km;
  });

  const unknownVoltageCount = gridContext
    ? gridContext.assets.filter((a) => a.voltage_kv === null).length
    : 0;
  const knownVoltageAssets = gridContext
    ? gridContext.assets.filter((a) => a.voltage_kv !== null)
    : [];

  const formPoint =
    formData.latitude !== null && formData.longitude !== null && !editingId
      ? { lat: formData.latitude, lon: formData.longitude }
      : null;
  const formGeometry = formData.imported_geometry;
  const detailSites = selectedSite ? [selectedSite] : [];


  // ── Effects ──

  // Load cached grid context when site selection changes
  useEffect(() => {
    setGridFocusedAssetId(null);
    if (!selectedSite || !selectedSiteHasCoordinates) {
      gridRequestVersionRef.current += 1;
      setGridCacheLoading(false);
      setGridContext(null);
      setGridError(null);
      return;
    }

    const requestVersion = gridRequestVersionRef.current + 1;
    gridRequestVersionRef.current = requestVersion;
    let cancelled = false;

    setGridCacheLoading(true);
    setGridError(null);
    setGridContext(null);

    void api.getCachedGridContext(selectedSite.id, gridRadiusKm, true)
      .then((result) => {
        if (cancelled || gridRequestVersionRef.current !== requestVersion) return;
        setGridContext(result);
      })
      .catch((error: unknown) => {
        if (cancelled || gridRequestVersionRef.current !== requestVersion) return;
        if (getApiStatusCode(error) === 404) { setGridContext(null); return; }
        setGridContext(null);
        setGridError(getApiErrorDetail(error, "Failed to load cached grid context."));
      })
      .finally(() => {
        if (!cancelled && gridRequestVersionRef.current === requestVersion) {
          setGridCacheLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [gridRadiusKm, selectedSite?.id, selectedSiteHasCoordinates]);

  // Load official evidence when site changes
  useEffect(() => {
    if (!selectedSite) {
      setGridOfficialEvidence({ ...DEFAULT_GRID_OFFICIAL_EVIDENCE });
      setGridEvidenceError(null);
      setGridEvidenceLoading(false);
      return;
    }

    let cancelled = false;
    setGridEvidenceLoading(true);
    setGridEvidenceError(null);

    void api.getGridOfficialEvidence(selectedSite.id)
      .then((response) => {
        if (cancelled) return;
        setGridOfficialEvidence(response.evidence ?? { ...DEFAULT_GRID_OFFICIAL_EVIDENCE });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setGridOfficialEvidence({ ...DEFAULT_GRID_OFFICIAL_EVIDENCE });
        setGridEvidenceError(getApiErrorDetail(error, "Failed to load official evidence."));
      })
      .finally(() => { if (!cancelled) setGridEvidenceLoading(false); });

    return () => { cancelled = true; };
  }, [selectedSite?.id]);

  // Clear focused asset if it's filtered out
  useEffect(() => {
    if (gridFocusedAssetId && !sortedGridAssets.some((a) => a.asset_id === gridFocusedAssetId)) {
      setGridFocusedAssetId(null);
    }
  }, [gridFocusedAssetId, sortedGridAssets]);


  // ── Handlers ──

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) {
    const { name, value, type } = e.target;
    let parsed: string | number | boolean | null = value;
    if (type === "number") parsed = value === "" ? null : parseFloat(value);
    if (type === "checkbox") parsed = (e.target as HTMLInputElement).checked;
    setFormData((prev) => ({
      ...prev,
      [name]: parsed,
      imported_geometry: (name === "latitude" || name === "longitude") ? null : prev.imported_geometry,
    }));
  }

  function resetFormState() {
    setFormData({ ...DEFAULT_SITE });
    setIsEditing(false);
    setEditingId(null);
    setShowForm(false);
    setSaveError(null);
    setGeocodeResults([]);
    setGeocodeError(null);
    setKmlResults([]);
    setKmlError(null);
  }

  function clearSelectedSiteView() {
    gridRequestVersionRef.current += 1;
    selectSite(null);
    setPreview(null);
    setPreviewLoading(false);
    setGridCacheLoading(false);
    setGridContext(null);
    setGridError(null);
    setGridOfficialEvidence({ ...DEFAULT_GRID_OFFICIAL_EVIDENCE });
    setGridEvidenceError(null);
    setGridFocusedAssetId(null);
    setShowEvidenceForm(false);
  }

  function handleCloseForm() {
    resetFormState();
  }

  async function handleSave() {
    if (!formData.name.trim()) { setSaveError("Site name is required."); return; }
    if (formData.land_area_m2 <= 0) { setSaveError("Land area must be positive."); return; }
    setSaving(true);
    setSaveError(null);
    try {
      let savedSiteId: string | null = editingId;
      if (editingId) {
        await api.updateSite(editingId, formData);
      } else {
        const created = await api.createSite(formData);
        savedSiteId = created.id;
      }
      await loadSites();
      if (savedSiteId) {
        handleCloseForm();
        selectSite(savedSiteId);
        await loadPreview(savedSiteId);
      } else {
        resetForm();
      }
    } catch (err: unknown) {
      const resp = (err as { response?: { data?: { detail?: string } } })?.response;
      setSaveError(resp?.data?.detail || "Failed to save site.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string, name: string) {
    if (window.confirm(`Delete site "${name}"? This cannot be undone.`)) {
      if (editingId === id) {
        handleCloseForm();
      }
      await removeSite(id);
    }
  }

  function resetForm() {
    resetFormState();
    clearSelectedSiteView();
  }

  function handleNewSite() {
    resetForm();
    setShowForm(true);
  }

  function handleSelectSite(siteId: string) {
    handleCloseForm();
    selectSite(siteId);
    void loadPreview(siteId);
  }

  function handleEditSite(siteId: string) {
    const found = sites.find((site) => site.id === siteId);
    if (!found) return;
    selectSite(siteId);
    setFormData({ ...found.site });
    setIsEditing(true);
    setEditingId(siteId);
    setShowForm(true);
    setSaveError(null);
    setGeocodeResults([]);
    setGeocodeError(null);
    setKmlResults([]);
    setKmlError(null);
    void loadPreview(siteId);
  }

  async function handleGeocode() {
    if (!geocodeQuery.trim()) return;
    setGeocoding(true);
    setGeocodeError(null);
    try {
      const result = await api.geocode(geocodeQuery);
      setGeocodeResults(result.results);
      if (result.results.length === 0) setGeocodeError("No matching locations found.");
    } catch (err: unknown) {
      setGeocodeResults([]);
      setGeocodeError(getApiErrorDetail(err, "Geocoding failed."));
    } finally {
      setGeocoding(false);
    }
  }

  function applyGeocode(result: { latitude: number; longitude: number; name: string; country: string }) {
    setFormData((prev) => ({
      ...prev,
      latitude: result.latitude,
      longitude: result.longitude,
      imported_geometry: null,
      city: result.name,
      country: result.country,
    }));
    setGeocodeResults([]);
    setGeocodeQuery("");
    setGeocodeError(null);
  }

  async function handleKmlUpload(file: File) {
    setUploadingKml(true);
    setKmlError(null);
    setKmlResults([]);
    try {
      const result = await api.uploadKML(file);
      setKmlResults(result.coordinates);
      if (result.coordinates.length === 0) setKmlError("No placemarks found in file.");
    } catch (err: unknown) {
      setKmlError(getApiErrorDetail(err, "Failed to parse KML/KMZ file."));
    } finally {
      setUploadingKml(false);
      if (kmlInputRef.current) kmlInputRef.current.value = "";
    }
  }

  function applyUploadedCoordinate(result: KMLUploadResponse["coordinates"][number]) {
    setFormData((prev) => ({
      ...prev,
      latitude: result.latitude,
      longitude: result.longitude,
      imported_geometry: {
        geometry_type: result.geometry_type,
        coordinates: result.geometry_coordinates,
      },
      city: result.name ?? prev.city,
    }));
    setKmlError(null);
  }

  async function loadPreview(siteId: string) {
    setPreviewLoading(true);
    setPreview(null);
    try {
      const result = await api.getSpacePreview(siteId);
      setPreview(result.space);
    } catch {
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  }

  async function handleGridContextAnalysis(forceRefresh = false) {
    if (!selectedSite) return;
    if (!selectedSiteHasCoordinates) {
      setGridError("Grid Context requires saved site coordinates.");
      return;
    }

    const requestVersion = gridRequestVersionRef.current + 1;
    gridRequestVersionRef.current = requestVersion;

    setGridCacheLoading(false);
    setGridLoading(true);
    setGridError(null);
    setGridFocusedAssetId(null);
    try {
      const result = await api.fetchGridContext({
        site_id: selectedSite.id,
        radius_km: gridRadiusKm,
        include_score: true,
        force_refresh: forceRefresh,
      });
      if (gridRequestVersionRef.current !== requestVersion) return;
      setGridContext(result);
      setShowGridOverlay(true);
    } catch (err: unknown) {
      if (gridRequestVersionRef.current !== requestVersion) return;
      setGridError(getApiErrorDetail(err, "Failed to load grid context."));
      setGridContext(null);
    } finally {
      if (gridRequestVersionRef.current === requestVersion) setGridLoading(false);
    }
  }

  function handleGridOfficialEvidenceChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) {
    const { name, value, type } = e.target;
    setGridOfficialEvidence((prev) => ({
      ...prev,
      [name]: type === "number"
        ? (value === "" ? null : Number(value))
        : (value.trim() === "" ? null : value),
    }));
  }

  async function handleSaveGridOfficialEvidence() {
    if (!selectedSite) return;
    if (!hasGridOfficialEvidence(gridOfficialEvidence)) {
      setGridEvidenceError("Enter at least one field before saving.");
      return;
    }
    setGridEvidenceSaving(true);
    setGridEvidenceError(null);
    try {
      const response = await api.saveGridOfficialEvidence(selectedSite.id, gridOfficialEvidence);
      setGridOfficialEvidence(response.evidence ?? { ...DEFAULT_GRID_OFFICIAL_EVIDENCE });
      if (selectedSiteHasCoordinates) await handleGridContextAnalysis(true);
    } catch (err: unknown) {
      setGridEvidenceError(getApiErrorDetail(err, "Failed to save official evidence."));
    } finally {
      setGridEvidenceSaving(false);
    }
  }

  async function handleDeleteGridOfficialEvidence() {
    if (!selectedSite) return;
    setGridEvidenceDeleting(true);
    setGridEvidenceError(null);
    try {
      await api.deleteGridOfficialEvidence(selectedSite.id);
      setGridOfficialEvidence({ ...DEFAULT_GRID_OFFICIAL_EVIDENCE });
      if (selectedSiteHasCoordinates && gridContext) await handleGridContextAnalysis(true);
    } catch (err: unknown) {
      setGridEvidenceError(getApiErrorDetail(err, "Failed to delete official evidence."));
    } finally {
      setGridEvidenceDeleting(false);
    }
  }


  // ═══════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════

  return (
    <div className="max-w-7xl mx-auto">
      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Site Manager</h2>
          <p className="text-sm text-gray-500 mt-1">
            {sites.length} site{sites.length !== 1 ? "s" : ""} configured
          </p>
        </div>
        <button
          type="button"
          onClick={handleNewSite}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          <Plus size={16} />
          New Site
        </button>
      </div>

      {sitesError && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm flex items-center gap-2">
          <AlertCircle size={16} />
          {sitesError}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════
          THREE-MAP LAYOUT
         ═══════════════════════════════════════════════════════ */}
      <div className="mb-6 grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* Map 1: Overview */}
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-100 px-4 py-2.5">
            <h3 className="text-sm font-semibold text-gray-800">Overview Map</h3>
            <p className="text-xs text-gray-500">All saved sites</p>
          </div>
          <MapView
            sites={sites}
            selectedId={selectedSiteId}
            onSelect={handleSelectSite}
            height="h-64"
            mode="overview"
          />
        </div>

        {/* Map 2: Terrain */}
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-100 px-4 py-2.5 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-1.5">
                <Mountain size={14} className="text-green-600" />
                Terrain
              </h3>
              <p className="text-xs text-gray-500">
                {selectedSite ? selectedSite.site.name : "Select a site"}
              </p>
            </div>
          </div>
          {selectedSite && selectedSiteHasCoordinates ? (
            <MapView
              sites={detailSites}
              selectedId={selectedSiteId}
              onSelect={handleSelectSite}
              height="h-64"
              mode="detail"
              tileUrl="https://tile.opentopomap.org/{z}/{x}/{y}.png"
              tileAttribution={'Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="https://viewfinderpanoramas.org">SRTM</a> | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)'}
              markerTone="detail"
              selectedMarkerTone="terrain"
              singlePointZoom={13}
              fitMaxZoom={15}
            />
          ) : (
            <div className="h-64 flex items-center justify-center text-sm text-gray-400">
              {selectedSite ? "No coordinates set" : "Select a site to view terrain"}
            </div>
          )}
        </div>

        {/* Map 3: Detail + Infrastructure */}
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-100 px-4 py-2.5 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-1.5">
                <Zap size={14} className="text-amber-500" />
                Site Detail + Grid
              </h3>
              <p className="text-xs text-gray-500">
                {selectedSite
                  ? `${selectedSite.site.city || "Location"} · Infrastructure overlay`
                  : formPoint ? "Draft location preview" : "Select a site"}
              </p>
            </div>
            {gridContext && (
              <button
                type="button"
                onClick={() => setShowGridOverlay(!showGridOverlay)}
                className="text-xs flex items-center gap-1 text-gray-500 hover:text-gray-700"
                title={showGridOverlay ? "Hide grid overlay" : "Show grid overlay"}
              >
                {showGridOverlay ? <EyeOff size={12} /> : <Eye size={12} />}
                Grid
              </button>
            )}
          </div>
          <MapView
            sites={detailSites}
            selectedId={selectedSiteId}
            onSelect={handleSelectSite}
            singlePoint={selectedSite ? null : formPoint}
            singleGeometry={selectedSite ? null : formGeometry}
            gridAssets={sortedGridAssets}
            focusedGridAssetId={gridFocusedAssetId}
            showGridOverlay={showGridOverlay && !!gridContext && !!selectedSite}
            gridRadiusKm={gridContext?.summary.radius_km ?? gridRadiusKm}
            gridSiteCenter={gridSiteCenter}
            height="h-64"
            mode="detail"
          />
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════
          TWO-COLUMN: Site List + Form/Details
         ═══════════════════════════════════════════════════════ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* LEFT: Saved Sites List */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200">
            <div className="p-4 border-b border-gray-100 flex items-center justify-between">
              <h3 className="font-semibold text-gray-800">Saved Sites</h3>
              <span className="text-xs text-gray-400">{sites.length} total</span>
            </div>
            {sitesLoading ? (
              <div className="p-8 text-center text-gray-400">
                <Loader2 className="animate-spin mx-auto mb-2" size={24} />
                Loading...
              </div>
            ) : sites.length === 0 ? (
              <div className="p-8 text-center text-gray-400 text-sm">
                No sites yet. Click <strong>New Site</strong> to create one.
              </div>
            ) : (
              <ul className="divide-y divide-gray-100 max-h-[600px] overflow-y-auto">
                {sites.map((s) => (
                  <li
                    key={s.id}
                    className={`p-3.5 cursor-pointer hover:bg-gray-50 transition-colors ${
                      selectedSiteId === s.id ? "bg-blue-50 border-l-4 border-blue-600" : ""
                    }`}
                    onClick={() => handleSelectSite(s.id)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="min-w-0">
                        <p className="font-medium text-gray-900 truncate text-sm">{s.site.name}</p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {s.site.city || "No location"} · {s.site.land_area_m2.toLocaleString()} m²
                        </p>
                        <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                            {s.site.site_type}
                          </span>
                          {s.has_weather && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-100 text-green-700">Weather ✓</span>
                          )}
                          {s.has_solar && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">Solar ✓</span>
                          )}
                          {s.solar_fetch_status === "loading" && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-100 text-yellow-700 flex items-center gap-0.5"><Loader2 size={8} className="animate-spin" /> PVGIS</span>
                          )}
                          {s.site.available_power_mw > 0 && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                              {s.site.available_power_mw} MW
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-0.5 ml-2 shrink-0">
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); handleEditSite(s.id); }}
                          className="p-1.5 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-700"
                          title="Edit"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); handleDelete(s.id, s.site.name); }}
                          className="p-1.5 rounded hover:bg-red-100 text-gray-400 hover:text-red-600"
                          title="Delete"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* RIGHT: Form + Preview + Grid */}
        <div className="lg:col-span-2 space-y-5">

          {selectedSite && !showForm && (
            <Section title="Selected Site" defaultOpen={true}>
              <div className="p-4 space-y-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900">{selectedSite.site.name}</h3>
                    <p className="mt-1 text-sm text-gray-500">
                      {selectedSite.site.city || "Location pending"}
                      {selectedSite.site.country ? `, ${selectedSite.site.country}` : ""}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleEditSite(selectedSite.id)}
                    className="inline-flex items-center gap-2 self-start rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    <Pencil size={14} />
                    Edit Site
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <MetricCard label="Site Type" value={selectedSite.site.site_type} />
                  <MetricCard
                    label="Land Area"
                    value={`${selectedSite.site.land_area_m2.toLocaleString()} m²`}
                    highlight
                  />
                  <MetricCard
                    label="Available Power"
                    value={
                      selectedSite.site.available_power_mw > 0
                        ? `${selectedSite.site.available_power_mw} MW`
                        : "Area-only"
                    }
                    highlight={selectedSite.site.available_power_mw > 0}
                  />
                  <MetricCard
                    label="Weather"
                    value={selectedSite.has_weather ? "Cached" : "Not fetched"}
                  />
                  <MetricCard
                    label="Solar (PVGIS)"
                    value={selectedSite.has_solar ? "Cached" : selectedSite.solar_fetch_status === "loading" ? "Loading..." : selectedSite.solar_fetch_status === "error" ? "Error" : "Not fetched"}
                  />
                </div>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="space-y-2 rounded-lg bg-gray-50 p-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Location</p>
                    <p className="text-sm text-gray-700">
                      Coordinates:{" "}
                      {selectedSiteHasCoordinates
                        ? `${selectedSite.site.latitude!.toFixed(5)}, ${selectedSite.site.longitude!.toFixed(5)}`
                        : "Not set"}
                    </p>
                    <p className="text-sm text-gray-700">
                      Voltage: {selectedSite.site.voltage ?? "TBD"}
                    </p>
                    <p className="text-sm text-gray-700">
                      Power confirmed: {selectedSite.site.power_confirmed ? "Yes" : "No"}
                    </p>
                  </div>

                  <div className="space-y-2 rounded-lg bg-gray-50 p-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Building Assumptions</p>
                    <p className="text-sm text-gray-700">
                      Buildable mode: {selectedSite.site.buildable_area_mode}
                    </p>
                    <p className="text-sm text-gray-700">
                      Floors: {selectedSite.site.num_floors} active
                      {selectedSite.site.num_expansion_floors > 0
                        ? ` + ${selectedSite.site.num_expansion_floors} expansion`
                        : ""}
                    </p>
                    <p className="text-sm text-gray-700">
                      Whitespace: {(selectedSite.site.whitespace_ratio * 100).toFixed(0)}%
                    </p>
                  </div>
                </div>

                {/* Green Energy Facilities summary */}
                {(selectedSite.site.pv_capacity_kwp || selectedSite.site.bess_capacity_kwh || selectedSite.site.fuel_cell_kw) && (
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-emerald-700 mb-1">Green Energy Facilities</p>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm text-gray-700">
                      {selectedSite.site.pv_capacity_kwp != null && selectedSite.site.pv_capacity_kwp > 0 && (
                        <div><span className="text-xs text-gray-500">PV:</span> {selectedSite.site.pv_capacity_kwp.toLocaleString()} kWp</div>
                      )}
                      {selectedSite.site.bess_capacity_kwh != null && selectedSite.site.bess_capacity_kwh > 0 && (
                        <div><span className="text-xs text-gray-500">BESS:</span> {selectedSite.site.bess_capacity_kwh.toLocaleString()} kWh</div>
                      )}
                      {selectedSite.site.bess_efficiency != null && (
                        <div><span className="text-xs text-gray-500">Eff:</span> {(selectedSite.site.bess_efficiency * 100).toFixed(1)}%</div>
                      )}
                      {selectedSite.site.fuel_cell_kw != null && selectedSite.site.fuel_cell_kw > 0 && (
                        <div><span className="text-xs text-gray-500">FC:</span> {selectedSite.site.fuel_cell_kw.toLocaleString()} kW</div>
                      )}
                    </div>
                  </div>
                )}

                {selectedSite.site.notes && (
                  <div className="rounded-lg border border-gray-200 bg-white p-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Notes</p>
                    <p className="mt-1 text-sm text-gray-700">{selectedSite.site.notes}</p>
                  </div>
                )}
              </div>
            </Section>
          )}

          {/* ── SITE FORM (collapsed by default) ── */}
          {showForm && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200">
              <div className="p-4 border-b border-gray-100 flex items-center justify-between">
                <h3 className="font-semibold text-gray-800">
                  {isEditing ? `Edit: ${formData.name || "Untitled"}` : "New Site"}
                </h3>
                <button
                  type="button"
                  onClick={handleCloseForm}
                  className="text-gray-400 hover:text-gray-600"
                  title="Close form"
                >
                  <X size={18} />
                </button>
              </div>
              <div className="p-5 space-y-5">
                {/* Identity */}
                <fieldset>
                  <legend className="text-sm font-medium text-gray-700 mb-2">Identity</legend>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Site Name *</label>
                      <input type="text" name="name" value={formData.name} onChange={handleChange}
                        placeholder="e.g. Milan North Campus"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Site Type</label>
                      <select name="site_type" value={formData.site_type} onChange={handleChange}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none bg-white">
                        {SITE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </div>
                  </div>
                </fieldset>

                {/* Location */}
                <fieldset>
                  <legend className="text-sm font-medium text-gray-700 mb-2">Location</legend>
                  {/* Geocode search */}
                  <div className="mb-3">
                    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void handleGeocode(); }}>
                      <input type="text" value={geocodeQuery} onChange={(e) => setGeocodeQuery(e.target.value)}
                        placeholder="Search city... (e.g. Milan, Italy)"
                        className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                      <button type="submit" disabled={geocoding}
                        className="px-3 py-2 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200 text-sm disabled:opacity-50">
                        {geocoding ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
                      </button>
                    </form>
                    {geocodeResults.length > 0 && (
                      <div className="mt-2 border border-gray-200 rounded-lg overflow-hidden max-h-40 overflow-y-auto">
                        {geocodeResults.map((r, i) => (
                          <button type="button" key={i} onClick={() => applyGeocode(r)}
                            className="w-full px-3 py-2 text-left text-sm hover:bg-blue-50 flex items-center gap-2 border-b border-gray-100 last:border-0">
                            <MapPin size={14} className="text-gray-400 shrink-0" />
                            <span className="truncate">{r.name}, {r.admin1}, {r.country}</span>
                            <span className="text-gray-400 ml-auto text-xs shrink-0">{r.latitude.toFixed(2)}°, {r.longitude.toFixed(2)}°</span>
                          </button>
                        ))}
                      </div>
                    )}
                    {geocodeError && <p className="mt-1 text-xs text-red-600">{geocodeError}</p>}
                  </div>

                  {/* KML Upload (compact) */}
                  <div className="mb-3 flex items-center gap-3">
                    <button type="button" onClick={() => kmlInputRef.current?.click()} disabled={uploadingKml}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200 text-xs disabled:opacity-50">
                      {uploadingKml ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                      Upload KML/KMZ
                    </button>
                    <span className="text-xs text-gray-400">or enter coordinates manually below</span>
                    <input ref={kmlInputRef} type="file"
                      accept=".kml,.kmz,application/vnd.google-earth.kml+xml,application/vnd.google-earth.kmz"
                      className="hidden"
                      onChange={(e) => { const file = e.target.files?.[0]; if (file) void handleKmlUpload(file); }} />
                  </div>
                  {kmlError && <p className="mb-2 text-xs text-red-600">{kmlError}</p>}
                  {kmlResults.length > 0 && (
                    <div className="mb-3 border border-gray-200 rounded-lg overflow-hidden max-h-32 overflow-y-auto">
                      {kmlResults.map((r, i) => (
                        <button type="button" key={`${r.latitude}-${r.longitude}-${i}`} onClick={() => applyUploadedCoordinate(r)}
                          className="w-full px-3 py-2 text-left text-sm hover:bg-blue-50 flex items-center gap-2 border-b border-gray-100 last:border-0">
                          <MapPin size={14} className="text-gray-400" />
                          <span>{r.name || `Placemark ${i + 1}`}</span>
                          <span className="text-gray-400 ml-auto text-xs">{r.latitude.toFixed(2)}°, {r.longitude.toFixed(2)}°</span>
                        </button>
                      ))}
                    </div>
                  )}

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Latitude</label>
                      <input type="number" name="latitude" value={formData.latitude ?? ""} onChange={handleChange} step="0.0001"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Longitude</label>
                      <input type="number" name="longitude" value={formData.longitude ?? ""} onChange={handleChange} step="0.0001"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">City</label>
                      <input type="text" name="city" value={formData.city ?? ""} onChange={handleChange}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Country</label>
                      <input type="text" name="country" value={formData.country ?? ""} onChange={handleChange}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                    </div>
                  </div>
                </fieldset>

                {/* Land & Building */}
                <fieldset>
                  <legend className="text-sm font-medium text-gray-700 mb-2">Land & Building</legend>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Land Area (m²) *</label>
                      <input type="number" name="land_area_m2" value={formData.land_area_m2} onChange={handleChange} min={1}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Buildable Mode</label>
                      <select name="buildable_area_mode" value={formData.buildable_area_mode} onChange={handleChange}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none bg-white">
                        {BUILDABLE_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                      </select>
                    </div>
                    {formData.buildable_area_mode === "ratio" ? (
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Coverage Ratio</label>
                        <input type="number" name="site_coverage_ratio" value={formData.site_coverage_ratio} onChange={handleChange}
                          step="0.05" min={0.01} max={1}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                      </div>
                    ) : (
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Buildable Area (m²)</label>
                        <input type="number" name="buildable_area_m2" value={formData.buildable_area_m2 ?? ""} onChange={handleChange} min={1}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                      </div>
                    )}
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mt-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Max Height (m)</label>
                      <input type="number" name="max_building_height_m" value={formData.max_building_height_m ?? ""} onChange={handleChange}
                        step="0.5" min={0} placeholder="No limit"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                      <p className="text-[10px] text-gray-400 mt-0.5">Planning permission</p>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Floors</label>
                      <input type="number" name="num_floors" value={formData.num_floors} onChange={handleChange} min={1} max={10}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Floor Height (m)</label>
                      <input type="number" name="floor_to_floor_height_m" value={formData.floor_to_floor_height_m} onChange={handleChange}
                        step="0.1" min={2} max={10}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Whitespace</label>
                      <input type="number" name="whitespace_ratio" value={formData.whitespace_ratio} onChange={handleChange}
                        step="0.05" min={0.01} max={0.80}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Rack m²</label>
                      <input type="number" name="rack_footprint_m2" value={formData.rack_footprint_m2} onChange={handleChange}
                        step="0.1" min={1} max={6}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Expansion Floors</label>
                      <input type="number" name="num_expansion_floors" value={formData.num_expansion_floors} onChange={handleChange}
                        min={0} max={10}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                      <p className="text-[10px] text-gray-400 mt-0.5">Reserved for future phases</p>
                    </div>
                    <div className="flex items-center gap-2 self-center pt-4">
                      <input type="checkbox" id="roof_usable" name="roof_usable"
                        checked={formData.roof_usable ?? true}
                        onChange={(e) => setFormData((prev) => ({ ...prev, roof_usable: e.target.checked }))}
                        className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                      <label htmlFor="roof_usable" className="text-xs font-medium text-gray-600">Roof usable for equipment</label>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Voltage Level</label>
                      <select name="voltage" value={formData.voltage ?? ""} onChange={handleChange}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none bg-white">
                        <option value="">TBD</option>
                        <option value="HV">HV (110 kV+)</option>
                        <option value="MV">MV (10–33 kV)</option>
                        <option value="LV">LV (400 V)</option>
                      </select>
                    </div>
                  </div>
                </fieldset>

                {/* Power */}
                <fieldset>
                  <legend className="text-sm font-medium text-gray-700 mb-2">Power</legend>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Available Power (MW)</label>
                      <input type="number" name="available_power_mw" value={formData.available_power_mw} onChange={handleChange}
                        step="0.1" min={0}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none" />
                      <p className="text-[10px] text-gray-400 mt-0.5">0 = area-constrained</p>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Power Input Mode</label>
                      <select name="power_input_mode" value={formData.power_input_mode} onChange={handleChange}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none bg-white">
                        {POWER_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                      </select>
                    </div>
                    <div className="flex items-end">
                      <label className="flex items-center gap-2 text-sm text-gray-700 pb-2">
                        <input type="checkbox" name="power_confirmed" checked={formData.power_confirmed} onChange={handleChange}
                          className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                        Power Confirmed (STMG)
                      </label>
                    </div>
                  </div>
                </fieldset>

                {/* Green Energy Facilities */}
                <fieldset>
                  <legend className="text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
                    Green Energy Facilities
                    <span className="text-[10px] font-normal text-gray-400">(optional site-level defaults)</span>
                  </legend>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">PV Capacity (kWp)</label>
                      <input type="number" name="pv_capacity_kwp" value={formData.pv_capacity_kwp ?? ""} onChange={handleChange}
                        step="1" min={0}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                        placeholder="e.g. 2400" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">BESS Capacity (kWh)</label>
                      <input type="number" name="bess_capacity_kwh" value={formData.bess_capacity_kwh ?? ""} onChange={handleChange}
                        step="1" min={0}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                        placeholder="e.g. 1200" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">BESS Efficiency (%)</label>
                      <input type="number" name="bess_efficiency" value={formData.bess_efficiency != null ? formData.bess_efficiency * 100 : ""}
                        onChange={(e) => {
                          const pct = e.target.value === "" ? null : parseFloat(e.target.value);
                          setFormData((prev) => ({ ...prev, bess_efficiency: pct != null ? pct / 100 : null }));
                        }}
                        step="0.1" min={0} max={100}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                        placeholder="87.5" />
                      <p className="text-[10px] text-gray-400 mt-0.5">Default: 87.5% (NREL ATB 2024)</p>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Fuel Cell (kW)</label>
                      <input type="number" name="fuel_cell_kw" value={formData.fuel_cell_kw ?? ""} onChange={handleChange}
                        step="1" min={0}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                        placeholder="e.g. 500" />
                    </div>
                  </div>
                  {/* PVGIS status indicator */}
                  {isEditing && editingId && (
                    <div className="mt-2 flex items-center gap-2">
                      {(() => {
                        const siteEntry = sites.find((s) => s.id === editingId);
                        const status = siteEntry?.solar_fetch_status ?? "none";
                        if (status === "cached") return <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-100 text-green-700">PVGIS Profile Cached</span>;
                        if (status === "loading") return <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-100 text-yellow-700 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Fetching PVGIS...</span>;
                        if (status === "error") return <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 text-red-700">PVGIS Fetch Failed</span>;
                        return <span className="text-[10px] text-gray-400">PVGIS auto-fetches on save when coordinates are set</span>;
                      })()}
                    </div>
                  )}

                  {/* PVGIS Configuration (collapsible) */}
                  <details className="mt-3">
                    <summary className="text-xs font-medium text-gray-500 cursor-pointer hover:text-gray-700 select-none">
                      PVGIS Solar Profile Parameters (Advanced)
                    </summary>
                    <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Start Year</label>
                        <input type="number" value={formData.pvgis_start_year ?? ""} onChange={(e) => setFormData((p) => ({ ...p, pvgis_start_year: e.target.value === "" ? null : parseInt(e.target.value) }))}
                          min={2005} max={2023} step={1}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                          placeholder="2019" />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">End Year</label>
                        <input type="number" value={formData.pvgis_end_year ?? ""} onChange={(e) => setFormData((p) => ({ ...p, pvgis_end_year: e.target.value === "" ? null : parseInt(e.target.value) }))}
                          min={2005} max={2023} step={1}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                          placeholder="2023" />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">PV Technology</label>
                        <select value={formData.pvgis_technology ?? ""} onChange={(e) => setFormData((p) => ({ ...p, pvgis_technology: e.target.value || null }))}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                          <option value="">crystSi (default)</option>
                          <option value="crystSi">Crystalline Silicon</option>
                          <option value="CIS">CIS</option>
                          <option value="CdTe">CdTe</option>
                          <option value="Unknown">Unknown</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Mounting</label>
                        <select value={formData.pvgis_mounting_place ?? ""} onChange={(e) => setFormData((p) => ({ ...p, pvgis_mounting_place: e.target.value || null }))}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                          <option value="">Free-standing (default)</option>
                          <option value="free">Free-standing</option>
                          <option value="building">Building-integrated</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">System Loss (%)</label>
                        <input type="number" value={formData.pvgis_system_loss_pct ?? ""} onChange={(e) => setFormData((p) => ({ ...p, pvgis_system_loss_pct: e.target.value === "" ? null : parseFloat(e.target.value) }))}
                          min={0} max={50} step={0.1}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                          placeholder="14.0" />
                      </div>
                      <div className="flex items-center gap-2 pt-4">
                        <input type="checkbox" checked={formData.pvgis_use_horizon ?? true}
                          onChange={(e) => setFormData((p) => ({ ...p, pvgis_use_horizon: e.target.checked }))}
                          className="rounded border-gray-300" />
                        <label className="text-xs text-gray-600">Use Horizon</label>
                      </div>
                      <div className="flex items-center gap-2 pt-4">
                        <input type="checkbox" checked={formData.pvgis_optimal_angles ?? true}
                          onChange={(e) => setFormData((p) => ({ ...p, pvgis_optimal_angles: e.target.checked }))}
                          className="rounded border-gray-300" />
                        <label className="text-xs text-gray-600">Optimal Angles</label>
                      </div>
                      {!(formData.pvgis_optimal_angles ?? true) && (
                        <>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Surface Tilt (°)</label>
                            <input type="number" value={formData.pvgis_surface_tilt_deg ?? ""} onChange={(e) => setFormData((p) => ({ ...p, pvgis_surface_tilt_deg: e.target.value === "" ? null : parseFloat(e.target.value) }))}
                              min={0} max={90} step={1}
                              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                              placeholder="35" />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Surface Azimuth (°)</label>
                            <input type="number" value={formData.pvgis_surface_azimuth_deg ?? ""} onChange={(e) => setFormData((p) => ({ ...p, pvgis_surface_azimuth_deg: e.target.value === "" ? null : parseFloat(e.target.value) }))}
                              min={-180} max={180} step={1}
                              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                              placeholder="0 (south)" />
                          </div>
                        </>
                      )}
                    </div>
                    <p className="text-[10px] text-gray-400 mt-1">Leave blank for defaults. Changing these will require a new PVGIS fetch on next save.</p>
                  </details>
                </fieldset>

                {/* Notes */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
                  <textarea name="notes" value={formData.notes ?? ""} onChange={handleChange} rows={2}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none resize-none"
                    placeholder="Optional notes..." />
                </div>

                {/* Save / Cancel */}
                {saveError && (
                  <div className="p-2.5 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">{saveError}</div>
                )}
                <div className="flex items-center gap-3">
                  <button type="button" onClick={handleSave} disabled={saving}
                    className="flex items-center gap-2 px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium transition-colors">
                    {saving && <Loader2 size={16} className="animate-spin" />}
                    {isEditing ? "Update Site" : "Create Site"}
                  </button>
                  <button type="button" onClick={handleCloseForm} className="px-4 py-2 text-gray-600 hover:text-gray-900 text-sm">
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ── GEOMETRY PREVIEW ── */}
          {preview && selectedSite && (
            <Section title="Geometry Preview" defaultOpen={true}>
              <div className="p-4">
                {previewLoading ? (
                  <div className="text-center py-4 text-gray-400"><Loader2 className="animate-spin mx-auto" size={20} /></div>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <MetricCard label="Buildable Footprint" value={`${preview.buildable_footprint_m2.toLocaleString()} m²`} />
                    <MetricCard label="Gross Building Area" value={`${preview.gross_building_area_m2.toLocaleString()} m²`} />
                    <MetricCard label="IT Whitespace" value={`${preview.it_whitespace_m2.toLocaleString()} m²`} />
                    <MetricCard label="Active Floors" value={String(preview.active_floors)} />
                    <MetricCard label="Max Racks (Space)" value={preview.max_racks_by_space.toLocaleString()} highlight />
                    <MetricCard label="Effective Racks" value={preview.effective_racks.toLocaleString()} highlight />
                    <MetricCard label="WS Adjustment" value={`×${preview.whitespace_adjustment_factor.toFixed(2)}`} />
                    {preview.expansion_racks > 0 && (
                      <MetricCard label="Expansion Racks" value={preview.expansion_racks.toLocaleString()} />
                    )}
                  </div>
                )}
              </div>
            </Section>
          )}

          {/* ── GRID INFRASTRUCTURE ── */}
          {selectedSite && (
            <Section
              title="Grid & Power Infrastructure"
              icon={<Zap size={16} className="text-amber-500" />}
              badge={gridContext ? `${knownVoltageAssets.length} known-voltage assets` : undefined}
              defaultOpen={true}
            >
              <div className="p-4 space-y-4">
                {/* Controls bar */}
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-medium text-gray-600">Radius:</label>
                    <select
                      value={gridRadiusKm}
                      onChange={(e) => setGridRadiusKm(Number(e.target.value))}
                      className="px-2 py-1.5 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                    >
                      {GRID_RADIUS_OPTIONS.map((r) => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </select>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleGridContextAnalysis(false)}
                    disabled={gridLoading || !selectedSiteHasCoordinates}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg hover:bg-amber-100 text-xs font-medium disabled:opacity-50"
                  >
                    {gridLoading ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />}
                    {gridContext ? "Re-scan" : "Scan Infrastructure"}
                  </button>

                  {gridContext && (
                    <button
                      type="button"
                      onClick={() => handleGridContextAnalysis(true)}
                      disabled={gridLoading}
                      className="inline-flex items-center gap-1 px-2 py-1.5 text-xs text-gray-500 hover:text-gray-700"
                    >
                      <RefreshCw size={11} /> Force refresh
                    </button>
                  )}

                  {gridCacheLoading && (
                    <span className="text-xs text-gray-400 flex items-center gap-1">
                      <Loader2 size={12} className="animate-spin" /> Loading cache...
                    </span>
                  )}
                </div>

                {gridError && (
                  <div className="p-2.5 bg-red-50 border border-red-200 text-red-700 rounded-lg text-xs flex items-center gap-2">
                    <AlertCircle size={14} />
                    {gridError}
                  </div>
                )}

                {!selectedSiteHasCoordinates && (
                  <div className="p-3 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg text-xs flex items-center gap-2">
                    <Info size={14} />
                    Save site coordinates first to scan nearby grid infrastructure.
                  </div>
                )}

                {/* Grid Results */}
                {gridContext && (
                  <>
                    {/* Score Summary */}
                    {gridContext.score && (
                      <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-semibold text-gray-800">
                            Grid Screening Score
                          </span>
                          <span className={`text-lg font-bold ${getGridScoreColor(gridContext.score.overall_score)}`}>
                            {gridContext.score.overall_score.toFixed(0)}/100
                          </span>
                        </div>
                        <p className="text-xs text-gray-600 mb-2">
                          {describeGridScoreSignal(gridContext.score.overall_score)}
                        </p>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                          {[
                            { label: "Voltage", value: gridContext.score.voltage_score },
                            { label: "Proximity", value: gridContext.score.distance_score },
                            { label: "Substations", value: gridContext.score.substation_score },
                            { label: "Evidence", value: gridContext.score.evidence_score },
                          ].map((item) => (
                            <div key={item.label} className="text-center">
                              <div className="text-xs text-gray-500">{item.label}</div>
                              <div className="text-sm font-semibold text-gray-900">{item.value.toFixed(0)}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Summary Stats */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="rounded-lg bg-gray-50 p-2.5 text-center">
                        <div className="text-xs text-gray-500">Lines</div>
                        <div className="text-lg font-bold text-gray-900">{gridContext.summary.nearby_line_count}</div>
                      </div>
                      <div className="rounded-lg bg-gray-50 p-2.5 text-center">
                        <div className="text-xs text-gray-500">Substations</div>
                        <div className="text-lg font-bold text-gray-900">{gridContext.summary.nearby_substation_count}</div>
                      </div>
                      <div className="rounded-lg bg-gray-50 p-2.5 text-center">
                        <div className="text-xs text-gray-500">Max Voltage</div>
                        <div className="text-lg font-bold text-gray-900">
                          {gridContext.summary.max_voltage_kv != null
                            ? `${gridContext.summary.max_voltage_kv} kV`
                            : "—"}
                        </div>
                      </div>
                      <div className="rounded-lg bg-gray-50 p-2.5 text-center">
                        <div className="text-xs text-gray-500">HV Assets</div>
                        <div className="text-lg font-bold text-gray-900">
                          {gridContext.summary.high_voltage_assets_within_radius}
                        </div>
                      </div>
                    </div>

                    {/* Asset List */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="text-sm font-medium text-gray-700">
                          Nearby Assets
                          <span className="ml-1.5 text-xs text-gray-400 font-normal">
                            ({sortedGridAssets.length} shown{unknownVoltageCount > 0 && !showUnknownVoltage
                              ? `, ${unknownVoltageCount} unknown-voltage hidden`
                              : ""})
                          </span>
                        </h4>
                        {unknownVoltageCount > 0 && (
                          <button
                            type="button"
                            onClick={() => setShowUnknownVoltage(!showUnknownVoltage)}
                            className="text-xs text-blue-600 hover:text-blue-800"
                          >
                            {showUnknownVoltage ? "Hide" : "Show"} {unknownVoltageCount} unknown-voltage
                          </button>
                        )}
                      </div>

                      {sortedGridAssets.length > 0 ? (
                        <div className="border border-gray-200 rounded-lg overflow-hidden max-h-64 overflow-y-auto">
                          <table className="w-full text-xs">
                            <thead className="bg-gray-50 sticky top-0">
                              <tr>
                                <th className="text-left px-3 py-2 font-medium text-gray-600">Type</th>
                                <th className="text-left px-3 py-2 font-medium text-gray-600">Name</th>
                                <th className="text-right px-3 py-2 font-medium text-gray-600">Voltage</th>
                                <th className="text-right px-3 py-2 font-medium text-gray-600">Distance</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {sortedGridAssets.map((asset) => (
                                <tr
                                  key={asset.asset_id}
                                  className={`hover:bg-blue-50 cursor-pointer transition-colors ${
                                    gridFocusedAssetId === asset.asset_id ? "bg-blue-50" : ""
                                  }`}
                                  onClick={() => setGridFocusedAssetId(
                                    gridFocusedAssetId === asset.asset_id ? null : asset.asset_id
                                  )}
                                >
                                  <td className="px-3 py-2">
                                    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${
                                      asset.asset_type === "substation"
                                        ? "bg-purple-100 text-purple-700"
                                        : "bg-orange-100 text-orange-700"
                                    }`}>
                                      {asset.asset_type === "substation" ? "⚡" : "━"}
                                      {asset.asset_type === "substation" ? "Substation" : "Line"}
                                    </span>
                                  </td>
                                  <td className="px-3 py-2 text-gray-800 truncate max-w-[150px]">
                                    {asset.name || <span className="text-gray-400 italic">Unnamed</span>}
                                    {asset.operator && (
                                      <span className="text-gray-400 ml-1">({asset.operator})</span>
                                    )}
                                  </td>
                                  <td className="px-3 py-2 text-right font-medium">
                                    {asset.voltage_kv != null ? (
                                      <span className={
                                        asset.voltage_kv >= 380 ? "text-red-600" :
                                        asset.voltage_kv >= 150 ? "text-orange-600" :
                                        asset.voltage_kv >= 50 ? "text-amber-600" : "text-gray-600"
                                      }>
                                        {asset.voltage_kv} kV
                                      </span>
                                    ) : (
                                      <span className="text-gray-300">—</span>
                                    )}
                                  </td>
                                  <td className="px-3 py-2 text-right text-gray-600">
                                    {asset.distance_km.toFixed(1)} km
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="text-xs text-gray-400 py-3">
                          No assets to display. Try increasing the search radius or showing unknown-voltage assets.
                        </p>
                      )}
                    </div>

                    {/* Evidence Notes */}
                    {gridContext.evidence_notes.length > 0 && (
                      <div className="space-y-1.5">
                        {gridContext.evidence_notes.map((note, i) => (
                          <div key={i} className="text-xs text-gray-600 flex items-start gap-1.5">
                            <Info size={12} className="text-gray-400 mt-0.5 shrink-0" />
                            <span><strong>{note.label}:</strong> {note.detail}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Metadata */}
                    <div className="flex flex-wrap gap-2 text-[10px] text-gray-400">
                      <span>{formatGridAnalysisGrade(gridContext.analysis_grade)}</span>
                      <span>·</span>
                      <span>{formatGridConfidence(gridContext.confidence)}</span>
                      <span>·</span>
                      <span>{gridContext.source_layers.map(formatGridSourceLayer).join(", ")}</span>
                      <span>·</span>
                      <span>{formatGridGeneratedAt(gridContext.generated_at_utc)}</span>
                    </div>
                  </>
                )}

                {/* Official Evidence (collapsible) */}
                {selectedSite && (
                  <div className="border-t border-gray-200 pt-3">
                    <button
                      type="button"
                      onClick={() => setShowEvidenceForm(!showEvidenceForm)}
                      className="flex items-center gap-2 text-sm font-medium text-gray-700 hover:text-gray-900"
                    >
                      {showEvidenceForm ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      Official Evidence
                      {hasGridOfficialEvidence(gridOfficialEvidence) && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700">Active</span>
                      )}
                    </button>
                    <p className="text-xs text-gray-400 mt-0.5">
                      Attach confirmed utility/TSO data to strengthen the screening result.
                    </p>

                    {showEvidenceForm && (
                      <div className="mt-3 space-y-3">
                        {gridEvidenceLoading ? (
                          <div className="text-xs text-gray-400 flex items-center gap-1">
                            <Loader2 size={12} className="animate-spin" /> Loading evidence...
                          </div>
                        ) : (
                          <>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Utility/TSO Reference</label>
                                <input type="text" name="utility_or_tso_reference"
                                  value={gridOfficialEvidence.utility_or_tso_reference ?? ""}
                                  onChange={handleGridOfficialEvidenceChange}
                                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none" />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Reference Date</label>
                                <input type="text" name="reference_date"
                                  value={gridOfficialEvidence.reference_date ?? ""}
                                  onChange={handleGridOfficialEvidenceChange}
                                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none" />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Confirmed Substation</label>
                                <input type="text" name="confirmed_substation_name"
                                  value={gridOfficialEvidence.confirmed_substation_name ?? ""}
                                  onChange={handleGridOfficialEvidenceChange}
                                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none" />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Confirmed Voltage (kV)</label>
                                <input type="number" name="confirmed_voltage_kv"
                                  value={gridOfficialEvidence.confirmed_voltage_kv ?? ""}
                                  onChange={handleGridOfficialEvidenceChange}
                                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none" />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Requested MW</label>
                                <input type="number" name="confirmed_requested_mw"
                                  value={gridOfficialEvidence.confirmed_requested_mw ?? ""}
                                  onChange={handleGridOfficialEvidenceChange}
                                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none" />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Available MW</label>
                                <input type="number" name="confirmed_available_mw"
                                  value={gridOfficialEvidence.confirmed_available_mw ?? ""}
                                  onChange={handleGridOfficialEvidenceChange}
                                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none" />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Connection Status</label>
                                <input type="text" name="connection_status"
                                  value={gridOfficialEvidence.connection_status ?? ""}
                                  onChange={handleGridOfficialEvidenceChange}
                                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none" />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Timeline</label>
                                <input type="text" name="timeline_status"
                                  value={gridOfficialEvidence.timeline_status ?? ""}
                                  onChange={handleGridOfficialEvidenceChange}
                                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none" />
                              </div>
                            </div>
                            <div>
                              <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
                              <textarea name="notes"
                                value={gridOfficialEvidence.notes ?? ""}
                                onChange={handleGridOfficialEvidenceChange}
                                rows={2}
                                className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 outline-none resize-none" />
                            </div>

                            {gridEvidenceError && (
                              <p className="text-xs text-red-600">{gridEvidenceError}</p>
                            )}

                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={handleSaveGridOfficialEvidence}
                                disabled={gridEvidenceSaving}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700 disabled:opacity-50"
                              >
                                {gridEvidenceSaving && <Loader2 size={12} className="animate-spin" />}
                                Save Evidence
                              </button>
                              {hasGridOfficialEvidence(gridOfficialEvidence) && (
                                <button
                                  type="button"
                                  onClick={handleDeleteGridOfficialEvidence}
                                  disabled={gridEvidenceDeleting}
                                  className="inline-flex items-center gap-1 px-3 py-1.5 text-xs text-red-600 hover:text-red-800 disabled:opacity-50"
                                >
                                  {gridEvidenceDeleting && <Loader2 size={12} className="animate-spin" />}
                                  Delete Evidence
                                </button>
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </Section>
          )}

          {/* Prompt when no site selected and form hidden */}
          {!showForm && !selectedSite && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
              <MapPin size={40} className="mx-auto text-gray-300 mb-3" />
              <p className="text-gray-500 text-sm">
                Select a site from the list or click <strong>New Site</strong> to begin.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
