/**
 * DC Feasibility Tool v4 — Zustand Store
 * =========================================
 * Global application state managed by Zustand.
 *
 * CONCEPT — What is "state"?
 * State is the data your app needs to remember while the user
 * interacts with it. Example: the list of sites, which site is
 * selected, whether data is loading, and error messages.
 *
 * CONCEPT — What is Zustand?
 * Zustand (German for "state") is a tiny library for managing
 * shared state in React. Instead of passing data through 10
 * levels of component props ("prop drilling"), any component
 * can read from or write to this store directly.
 *
 * How it works:
 *   1. We define the store shape (what data it holds)
 *   2. We define actions (functions that update the data)
 *   3. Components call `useAppStore(state => state.sites)` to
 *      read data, and `useAppStore.getState().loadSites()` to
 *      trigger actions.
 *
 * When the store data changes, React automatically re-renders
 * any component that reads that data. This is "reactivity."
 *
 * Reference: Architecture Agreement Section 2 (Zustand for state)
 */

import { create } from "zustand";
import type {
  SiteResponse,
  ScenarioResult,
  ReferenceData,
  BatchRequest,
  HealthResponse,
} from "../types";
import * as api from "../api/client";


// ─────────────────────────────────────────────────────────────
// Store interface — the shape of our global state
// ─────────────────────────────────────────────────────────────
// CONCEPT: This interface says "the store holds these fields
// and has these methods." It's like a Python class signature.

interface AppState {
  // ── Connection ──
  backendConnected: boolean;
  backendHealth: HealthResponse | null;

  // ── Reference data (loaded once at startup) ──
  referenceData: ReferenceData | null;

  // ── Sites ──
  sites: SiteResponse[];
  selectedSiteId: string | null;
  sitesLoading: boolean;
  sitesError: string | null;

  // ── Scenario results ──
  batchResults: ScenarioResult[];
  resultsLoading: boolean;
  resultsError: string | null;
  selectedResultIndex: number | null;

  // ── Actions (functions that update state) ──
  checkBackend: () => Promise<void>;
  loadReferenceData: () => Promise<void>;
  loadSites: () => Promise<void>;
  selectSite: (id: string | null) => void;
  removeSite: (id: string) => Promise<void>;
  runBatch: (request: BatchRequest) => Promise<void>;
  selectResult: (index: number | null) => void;
  clearResults: () => void;
}


// ─────────────────────────────────────────────────────────────
// Create the store
// ─────────────────────────────────────────────────────────────
// CONCEPT: `create<AppState>()` creates a Zustand store.
// The function receives `set` — a function to update state.
// When you call `set({ sites: newSites })`, React re-renders
// any component reading `sites`.
//
// CONCEPT: `get` gives you the current state snapshot.
// Useful when one action needs to read another piece of state.

export const useAppStore = create<AppState>((set, get) => ({
  // ── Initial values ──
  backendConnected: false,
  backendHealth: null,
  referenceData: null,
  sites: [],
  selectedSiteId: null,
  sitesLoading: false,
  sitesError: null,
  batchResults: [],
  resultsLoading: false,
  resultsError: null,
  selectedResultIndex: null,


  // ── Check backend health ──
  // Called once when the app first loads. If this fails, we
  // show a "backend not connected" banner.
  checkBackend: async () => {
    try {
      const health = await api.checkHealth();
      set({ backendConnected: true, backendHealth: health });
    } catch {
      set({ backendConnected: false, backendHealth: null });
    }
  },


  // ── Load reference data (dropdown options) ──
  // Called once at startup. Populates load types, cooling types,
  // density ranges — everything the forms need.
  loadReferenceData: async () => {
    try {
      const data = await api.getReferenceData();
      set({ referenceData: data });
    } catch (err) {
      console.error("Failed to load reference data:", err);
    }
  },


  // ── Load all sites from backend ──
  loadSites: async () => {
    set({ sitesLoading: true, sitesError: null });
    try {
      const response = await api.listSites();
      set({ sites: response.sites, sitesLoading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load sites";
      set({ sitesError: message, sitesLoading: false });
    }
  },


  // ── Select a site (for editing or viewing) ──
  selectSite: (id) => {
    set({ selectedSiteId: id });
  },


  // ── Delete a site ──
  removeSite: async (id) => {
    try {
      await api.deleteSite(id);
      // Remove from local state immediately (optimistic update)
      const current = get().sites;
      set({
        sites: current.filter((s) => s.id !== id),
        selectedSiteId:
          get().selectedSiteId === id ? null : get().selectedSiteId,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to delete site";
      set({ sitesError: message });
    }
  },


  // ── Run batch scenarios ──
  // This is the main "run" action on the Scenario Runner page.
  // Sends the selected sites × load types × cooling types to
  // the backend, which computes all combinations.
  runBatch: async (request) => {
    set({ resultsLoading: true, resultsError: null, batchResults: [] });
    try {
      const response = await api.runBatch(request);
      // Score the results for ranking
      let results = response.results;
      if (results.length > 0) {
        try {
          const scored = await api.scoreResults({ results });
          results = scored.scored_results;
        } catch {
          // Scoring failed — use unscored results
          console.warn("Scoring failed, using unscored results");
        }
      }
      set({
        batchResults: results,
        resultsLoading: false,
        selectedResultIndex: results.length > 0 ? 0 : null,
      });
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Batch run failed";
      set({ resultsError: message, resultsLoading: false });
    }
  },


  // ── Select a specific result for detailed view ──
  selectResult: (index) => {
    set({ selectedResultIndex: index });
  },

  // ── Clear results ──
  clearResults: () => {
    set({ batchResults: [], selectedResultIndex: null, resultsError: null });
  },
}));
