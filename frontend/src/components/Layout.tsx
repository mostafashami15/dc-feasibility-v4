/**
 * Layout — Sidebar + Main Content Area
 * =======================================
 * This component arranges the page: sidebar on the left,
 * content area on the right. The content area renders whatever
 * page matches the current URL.
 *
 * CONCEPT — What is <Outlet />?
 * React Router's <Outlet /> is a placeholder. It says:
 * "Render the child route's component here." When the URL is
 * "/", Outlet renders SiteManager. When it's "/scenarios",
 * Outlet renders ScenarioRunner. The Layout stays the same.
 *
 * Think of it like a picture frame — the frame (Layout) stays
 * fixed, and the picture (page content) swaps in and out.
 */

import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";

export default function Layout() {
  return (
    // CONCEPT — Flexbox layout
    // "flex" makes children sit side by side (horizontal).
    // The sidebar has a fixed width (w-60 = 240px).
    // The main area uses "flex-1" to take all remaining space.
    // "ml-60" adds a left margin equal to the sidebar width
    // so content doesn't hide behind the fixed sidebar.
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar />
      <main className="flex-1 ml-60 p-6 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
