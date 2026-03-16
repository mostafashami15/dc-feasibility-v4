/**
 * App.tsx — Application Root
 * ============================
 * Sets up React Router (URL-based navigation) and loads
 * initial data when the app first opens.
 *
 * CONCEPT — React Router
 * In a traditional website, clicking a link loads a new HTML
 * page from the server. In a React "Single Page Application"
 * (SPA), there's only ONE HTML page. React Router intercepts
 * link clicks and swaps components without a page reload.
 * This makes navigation instant.
 *
 * Routes are like a table:
 *   URL path        → Component to render
 *   "/"             → SiteManager
 *   "/scenarios"    → ScenarioRunner
 *   "/results"      → ResultsDashboard
 *
 * CONCEPT — useEffect
 * useEffect is a React "hook" that runs code when a component
 * first appears on screen (and optionally when dependencies
 * change). We use it to load data on startup.
 *
 * Think of it as: "when this component mounts, do this."
 * The empty array [] means "run once on mount, never again."

 * App.tsx — Application Root (Phase 6: all routes)
 * ===================================================
 * React Router setup with routes for all 7 pages.
 */

import { useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import SiteManager from "./pages/SiteManager";
import ScenarioRunner from "./pages/ScenarioRunner";
import ResultsDashboard from "./pages/ResultsDashboard";
import ClimateAnalysis from "./pages/ClimateAnalysis";
import GreenEnergy from "./pages/GreenEnergy";
import Export from "./pages/Export";
import Settings from "./pages/Settings";
// LoadMixPlanner is now embedded in ResultsDashboard > Expansion tab
import { useAppStore } from "./store/useAppStore";

export default function App() {
  const checkBackend = useAppStore((s) => s.checkBackend);
  const loadReferenceData = useAppStore((s) => s.loadReferenceData);
  const loadSites = useAppStore((s) => s.loadSites);

  useEffect(() => {
    checkBackend();
    loadReferenceData();
    loadSites();
  }, [checkBackend, loadReferenceData, loadSites]);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          {/* Page 1 */}
          <Route index element={<SiteManager />} />
          {/* Page 2 */}
          <Route path="climate" element={<ClimateAnalysis />} />
          {/* Page 3 */}
          <Route path="scenarios" element={<ScenarioRunner />} />
          {/* Page 4 */}
          <Route path="results" element={<ResultsDashboard />} />
          {/* Page 5 */}
          <Route path="green" element={<GreenEnergy />} />
          {/* Page 6 */}
          <Route path="export" element={<Export />} />
          {/* Page 7 */}
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
