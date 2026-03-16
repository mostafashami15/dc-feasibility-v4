/**
 * DailyProfileChart - Daily trend chart for the representative year
 * ================================================================
 * Shows min / average / max daily values across the simulated year.
 * Used for:
 *   - Daily IT load profile
 *   - Daily PUE profile
 */

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HourlyProfilePoint } from "../../types";

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

interface DailyProfileChartProps {
  data: HourlyProfilePoint[];
  metric: "it" | "pue";
  referenceValue?: number;
  referenceLabel?: string;
}

function getMonthTicks(dayCount: number): { ticks: number[]; labels: Record<number, string> } {
  const isLeapYear = dayCount >= 366;
  const monthLengths = isLeapYear
    ? [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    : [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

  const ticks: number[] = [];
  const labels: Record<number, string> = {};
  let day = 1;

  MONTH_LABELS.forEach((label, index) => {
    if (day <= dayCount) {
      ticks.push(day);
      labels[day] = label;
    }
    day += monthLengths[index];
  });

  if (ticks.length === 0) {
    return { ticks: [1], labels: { 1: "Day 1" } };
  }

  return { ticks, labels };
}

export default function DailyProfileChart({
  data,
  metric,
  referenceValue,
  referenceLabel,
}: DailyProfileChartProps) {
  if (data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
        No daily profile data available
      </div>
    );
  }

  const { ticks, labels } = getMonthTicks(data.length);
  const avgKey = metric === "it" ? "it_avg_mw" : "pue_avg";
  const minKey = metric === "it" ? "it_min_mw" : "pue_min";
  const maxKey = metric === "it" ? "it_max_mw" : "pue_max";
  const unit = metric === "it" ? "MW" : "PUE";
  const avgLabel = metric === "it" ? "Daily Avg IT" : "Daily Avg PUE";
  const minLabel = metric === "it" ? "Daily Min IT" : "Daily Min PUE";
  const maxLabel = metric === "it" ? "Daily Max IT" : "Daily Max PUE";
  const avgColor = metric === "it" ? "#2563eb" : "#059669";

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="day"
            ticks={ticks}
            tickFormatter={(value) => labels[value] ?? ""}
            tick={{ fontSize: 12, fill: "#6b7280" }}
          />
          <YAxis
            tick={{ fontSize: 12, fill: "#6b7280" }}
            width={metric === "it" ? 56 : 44}
            tickFormatter={(value) =>
              metric === "it" ? Number(value).toFixed(1) : Number(value).toFixed(2)
            }
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#fff",
              border: "1px solid #e5e7eb",
              borderRadius: "8px",
              fontSize: "12px",
            }}
            labelFormatter={(label) => `Day ${label}`}
            formatter={(value, name) => {
              const numericValue = typeof value === "number" ? value : Number(value ?? 0);
              const formatted = metric === "it" ? numericValue.toFixed(3) : numericValue.toFixed(4);
              return [`${formatted} ${unit}`, name];
            }}
          />
          <Legend wrapperStyle={{ fontSize: "12px" }} />
          {referenceValue !== undefined && (
            <ReferenceLine
              y={referenceValue}
              stroke="#f59e0b"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              label={{
                value: referenceLabel,
                position: "insideTopRight",
                style: { fontSize: 10, fill: "#f59e0b" },
              }}
            />
          )}
          <Line
            type="monotone"
            dataKey={minKey}
            name={minLabel}
            stroke="#cbd5e1"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey={maxKey}
            name={maxLabel}
            stroke="#94a3b8"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey={avgKey}
            name={avgLabel}
            stroke={avgColor}
            strokeWidth={2.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
