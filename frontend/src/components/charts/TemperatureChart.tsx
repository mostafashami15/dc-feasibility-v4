/**
 * TemperatureChart — Monthly temperature bar chart
 * ===================================================
 * Renders a bar chart with monthly mean, min, and max temperatures.
 * Used on the Climate & Weather page (Page 2).
 *
 * CONCEPT — Recharts
 * Recharts is a React charting library. Instead of writing
 * imperative chart code, you compose charts from components:
 *   <BarChart data={...}>
 *     <Bar dataKey="mean" />
 *   </BarChart>
 *
 * Each Recharts component maps to a visual element:
 *   BarChart    → the chart container
 *   CartesianGrid → the gray grid lines
 *   XAxis/YAxis → the axis labels
 *   Tooltip     → hover info box
 *   Bar         → the actual bars
 *   Legend      → the color legend
 *
 * CONCEPT — data format
 * Recharts expects an array of objects. Each object is one
 * "data point" (in our case, one month). The `dataKey` prop
 * tells the <Bar> which object field to use for bar height.
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

// Month labels for the X axis
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

interface TemperatureChartProps {
  /**
   * Monthly stats from the ClimateAnalysis response.
   * Structure: { monthly_mean: [12 values], monthly_min: [12], monthly_max: [12] }
   * Each array has 12 numbers, one per month.
   */
  monthlyStats: {
    monthly_mean: number[];
    monthly_min: number[];
    monthly_max: number[];
  } | null;
}

export default function TemperatureChart({ monthlyStats }: TemperatureChartProps) {
  if (!monthlyStats) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
        No monthly data available (requires 8,760 hours)
      </div>
    );
  }

  // Transform the backend data into Recharts format.
  // Backend sends: { monthly_mean: [12], monthly_min: [12], monthly_max: [12] }
  // Recharts wants: [{ month: "Jan", mean: 5.2, min: -1.3, max: 12.1 }, ...]
  const data = MONTHS.map((month, i) => ({
    month,
    mean: parseFloat((monthlyStats.monthly_mean?.[i] ?? 0).toFixed(1)),
    min: parseFloat((monthlyStats.monthly_min?.[i] ?? 0).toFixed(1)),
    max: parseFloat((monthlyStats.monthly_max?.[i] ?? 0).toFixed(1)),
  }));

  return (
    <div className="h-72">
      {/*
        CONCEPT — ResponsiveContainer
        Wraps the chart and makes it resize when the parent changes.
        width="100%" means it fills the parent's width.
        height="100%" means it fills the parent's height (set by the
        outer div's h-72 class = 288px).
      */}
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 12, fill: "#6b7280" }}
          />
          <YAxis
            tick={{ fontSize: 12, fill: "#6b7280" }}
            label={{
              value: "°C",
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
            formatter={(value) => {
              const numericValue = typeof value === "number" ? value : Number(value ?? 0);
              return `${numericValue}°C`;
            }}
          />
          <Legend wrapperStyle={{ fontSize: "12px" }} />

          <Bar
            dataKey="max"
            name="Max"
            fill="#ef4444"
            opacity={0.6}
            radius={[2, 2, 0, 0]}
          />
          <Bar
            dataKey="mean"
            name="Mean"
            fill="#3b82f6"
            radius={[2, 2, 0, 0]}
          />
          <Bar
            dataKey="min"
            name="Min"
            fill="#06b6d4"
            opacity={0.6}
            radius={[2, 2, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
