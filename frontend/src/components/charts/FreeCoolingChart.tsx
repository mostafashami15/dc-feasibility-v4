/**
 * FreeCoolingChart — Cooling mode hours breakdown
 * ==================================================
 * Stacked bar chart showing how many hours each cooling type
 * spends in free cooling, partial, and mechanical modes.
 *
 * CONCEPT — Stacked bars
 * A stacked bar chart layers multiple data series on top of each
 * other within each bar. Here: green (free) + yellow (partial) +
 * red (mechanical) = 8,760 total hours per cooling type.
 *
 * Used on the Climate & Weather page (Page 2).
 * Source data: ClimateAnalysis.free_cooling[] from routes_climate.py
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { FreeCoolingResult } from "../../types";


// Suitability badge colors
const SUIT_COLORS: Record<string, { bg: string; text: string }> = {
  EXCELLENT:        { bg: "bg-blue-100",   text: "text-blue-700" },
  GOOD:             { bg: "bg-green-100",  text: "text-green-700" },
  MARGINAL:         { bg: "bg-amber-100",  text: "text-amber-700" },
  NOT_RECOMMENDED:  { bg: "bg-red-100",    text: "text-red-700" },
};


interface FreeCoolingChartProps {
  freeCooling: FreeCoolingResult[];
}

export default function FreeCoolingChart({ freeCooling }: FreeCoolingChartProps) {
  if (!freeCooling || freeCooling.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
        No free cooling data available
      </div>
    );
  }

  // Shorten the cooling type labels for the chart x-axis
  function shortLabel(ct: string): string {
    return ct
      .replace("Air-Cooled ", "")
      .replace("Water-Cooled ", "W-")
      .replace(" + Economizer", "+Econ")
      .replace("Rear Door Heat Exchanger (RDHx)", "RDHx")
      .replace("Direct Liquid Cooling (DLC / Cold Plate)", "DLC")
      .replace("Immersion Cooling (Single-Phase)", "Immersion")
      .replace("Free Cooling — Dry Cooler (Chiller-less)", "Dry Cooler");
  }

  // Transform data for Recharts
  const data = freeCooling.map((fc) => ({
    name: shortLabel(fc.cooling_type),
    fullName: fc.cooling_type,
    free: fc.free_cooling_hours,
    partial: fc.partial_hours,
    mechanical: fc.mechanical_hours,
    suitability: fc.suitability,
    fraction: fc.free_cooling_fraction,
  }));

  return (
    <div>
      {/* Chart */}
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 11, fill: "#6b7280" }}
              interval={0}
              angle={-15}
              textAnchor="end"
              height={50}
            />
            <YAxis
              tick={{ fontSize: 12, fill: "#6b7280" }}
              label={{
                value: "Hours",
                position: "insideTopLeft",
                offset: -5,
                style: { fontSize: 12, fill: "#9ca3af" },
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#fff",
                border: "1px solid #e5e7eb",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              formatter={(value, name) => {
                const numericValue = typeof value === "number" ? value : Number(value ?? 0);
                const key = typeof name === "string" ? name : String(name ?? "");
                const labels: Record<string, string> = {
                  free: "Free Cooling",
                  partial: "Partial Econ.",
                  mechanical: "Mechanical",
                };
                return [`${numericValue.toLocaleString()} hrs`, labels[key] || key];
              }}
            />
            <Legend wrapperStyle={{ fontSize: "12px" }} />

            <Bar dataKey="free" name="Free Cooling" stackId="a" fill="#22c55e" radius={[0, 0, 0, 0]} />
            <Bar dataKey="partial" name="Partial" stackId="a" fill="#facc15" />
            <Bar dataKey="mechanical" name="Mechanical" stackId="a" fill="#ef4444" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Suitability badges below chart */}
      <div className="mt-3 flex flex-wrap gap-2">
        {freeCooling.map((fc) => {
          const colors = SUIT_COLORS[fc.suitability] || SUIT_COLORS.MARGINAL;
          return (
            <div
              key={fc.cooling_type}
              className="flex items-center gap-2 text-xs"
            >
              <span className={`px-2 py-0.5 rounded-full font-medium ${colors.bg} ${colors.text}`}>
                {fc.suitability.replace("_", " ")}
              </span>
              <span className="text-gray-600">
                {shortLabel(fc.cooling_type)} — {(fc.free_cooling_fraction * 100).toFixed(0)}% free
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
