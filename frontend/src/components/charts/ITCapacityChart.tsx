/**
 * ITCapacityChart — IT capacity spectrum visualization
 * ======================================================
 * Bar chart showing how IT capacity varies across the year
 * based on outdoor temperature. The five data points:
 *   Worst (hottest hour) → P99 → P90 → Mean → Best (coolest hour)
 *
 * P99 is the "committed capacity" — what you can promise to
 * customers. It's available 99% of the year (only 88 hours
 * out of 8,760 exceed this temperature).
 *
 * Source: Architecture Agreement Section 3.17, hourly engine output
 * Used on: Results Dashboard (Page 4), detail panel
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";
import type { ScenarioResult } from "../../types";


interface ITCapacityChartProps {
  result: ScenarioResult;
}

export default function ITCapacityChart({ result }: ITCapacityChartProps) {
  const r = result;

  // Only available when hourly simulation ran
  if (r.pue_source !== "hourly" || r.it_capacity_p99_mw === null) {
    return (
      <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
        Hourly simulation required for capacity spectrum
      </div>
    );
  }

  // Build chart data
  const data = [
    {
      label: "Worst",
      value: r.it_capacity_worst_mw ?? 0,
      color: "#ef4444",
      desc: "Hottest hour",
    },
    {
      label: "P99",
      value: r.it_capacity_p99_mw ?? 0,
      color: "#0A2240",
      desc: "Committed (99%)",
    },
    {
      label: "P90",
      value: r.it_capacity_p90_mw ?? 0,
      color: "#4E2589",
      desc: "90% of hours",
    },
    {
      label: "Mean",
      value: r.it_capacity_mean_mw ?? 0,
      color: "#795AFD",
      desc: "Annual average",
    },
    {
      label: "Best",
      value: r.it_capacity_best_mw ?? 0,
      color: "#5FE838",
      desc: "Coolest hour",
    },
  ];

  // The static IT load for reference
  const staticIT = r.power.it_load_mw;

  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 15, right: 20, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 12, fill: "#6b7280" }}
          />
          <YAxis
            tick={{ fontSize: 12, fill: "#6b7280" }}
            label={{
              value: "MW",
              position: "insideTopLeft",
              offset: -5,
              style: { fontSize: 12, fill: "#9ca3af" },
            }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#fff",
              border: "1px solid #E7E6E6",
              borderRadius: "8px",
              fontSize: "12px",
            }}
            formatter={(value, _name, props) => {
              const numericValue = typeof value === "number" ? value : Number(value ?? 0);
              const payload = props?.payload as (typeof data)[number] | undefined;
              return [`${numericValue.toFixed(3)} MW`, payload?.desc ?? ""];
            }}
          />

          {/* Static IT load reference line */}
          <ReferenceLine
            y={staticIT}
            stroke="#00F1F2"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            label={{
              value: `Static: ${staticIT.toFixed(2)} MW`,
              position: "right",
              style: { fontSize: 10, fill: "#00F1F2" },
            }}
          />

          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
