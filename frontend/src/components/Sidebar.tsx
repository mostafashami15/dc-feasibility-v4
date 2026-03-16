import { NavLink } from "react-router-dom";
import {
  BarChart3,
  Cloud,
  FileText,
  Leaf,
  MapPin,
  Play,
  Settings,
} from "lucide-react";
import { useAppStore } from "../store/useAppStore";


const NAV_ITEMS = [
  { to: "/", label: "Site Manager", icon: MapPin },
  { to: "/climate", label: "Climate & Weather", icon: Cloud },
  { to: "/scenarios", label: "Scenario Runner", icon: Play },
  { to: "/results", label: "Results", icon: BarChart3 },
  { to: "/green", label: "Green Energy", icon: Leaf },
  { to: "/export", label: "Reports & Export", icon: FileText },
  { to: "/settings", label: "Settings", icon: Settings },
];


export default function Sidebar() {
  const connected = useAppStore((s) => s.backendConnected);
  const siteCount = useAppStore((s) => s.sites.length);
  const resultCount = useAppStore((s) => s.batchResults.length);

  return (
    <aside className="w-60 bg-gray-900 text-gray-100 flex flex-col h-screen fixed left-0 top-0">
      <div className="p-5 border-b border-gray-700">
        <h1 className="text-lg font-bold tracking-tight text-white">
          DC Feasibility
        </h1>
        <p className="text-xs text-gray-400 mt-1">v4.1.4 - Site Analysis Tool</p>
      </div>

      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-blue-600 text-white font-medium"
                  : "text-gray-300 hover:bg-gray-800 hover:text-white"
              }`
            }
          >
            <item.icon size={18} />
            <span>{item.label}</span>
            {item.to === "/results" && resultCount > 0 && (
              <span className="ml-auto text-xs bg-blue-500 text-white px-1.5 py-0.5 rounded-full">
                {resultCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-gray-700 space-y-2">
        <div className="text-xs text-gray-400">
          {siteCount} site{siteCount !== 1 ? "s" : ""} saved
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              connected ? "bg-green-400" : "bg-red-400"
            }`}
          />
          <span className={connected ? "text-green-400" : "text-red-400"}>
            {connected ? "Backend connected" : "Backend offline"}
          </span>
        </div>
      </div>
    </aside>
  );
}
