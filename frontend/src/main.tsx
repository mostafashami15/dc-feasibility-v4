/**
 * main.tsx — Application Entry Point
 * =====================================
 * This is the very first file the browser runs.
 *
 * CONCEPT — How React starts
 * 1. The browser loads index.html
 * 2. index.html has a <div id="root"></div> and a <script> tag
 * 3. The script loads this file (main.tsx)
 * 4. We find the #root div and tell React to render our App inside it
 * 5. React takes over — it manages everything inside #root
 *
 * CONCEPT — StrictMode
 * React.StrictMode is a development-only wrapper that:
 *   - Runs effects twice to catch bugs (only in dev mode)
 *   - Warns about deprecated patterns
 *   - Does NOT affect production builds at all
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "leaflet/dist/leaflet.css";
import "./index.css";

// Find the HTML element with id="root" and render our App into it
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
