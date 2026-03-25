/**
 * TornadoChart — Sensitivity tornado diagram
 * =============================================
 * Horizontal bars showing how each parameter affects the output.
 * The widest bar = most influential parameter.
 *
 * CONCEPT — Tornado chart
 * In engineering, a tornado chart shows sensitivity analysis.
 * For each input parameter, you vary it ±X% and measure the
 * output change. Parameters are sorted so the widest spread
 * (most influential) is at the top — forming a tornado shape.
 *
 * CONCEPT — Recharts BarChart layout="vertical"
 * Setting layout="vertical" rotates the chart so bars go
 * left-to-right instead of bottom-to-top. The Y-axis shows
 * category labels (parameter names) and X-axis shows values.
 *
 * Source data: TornadoResult from /api/scenarios/tornado
 * Reference: Architecture Agreement Section 3.11
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { TornadoBar } from "../../types";


interface TornadoChartProps {
  bars: TornadoBar[];
  baselineOutput: number;
  outputUnit: string;
}

export default function TornadoChart({
  bars,
  baselineOutput,
  outputUnit,
}: TornadoChartProps) {
  if (!bars || bars.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
        No sensitivity data available
      </div>
    );
  }

  // Transform data for Recharts.
  // Each bar needs a "low" portion (baseline to low output) and
  // "high" portion (baseline to high output). We use a trick:
  // render the full range as [min, max] and color each half.
  //
  // Actually, the simplest Recharts approach is two bars per parameter:
  // one for the "low" direction and one for the "high" direction,
  // both starting from the baseline.
  const data = bars.map((b) => ({
    name: b.parameter_label,
    param: b.parameter,
    lowDelta: b.output_at_low - baselineOutput,
    highDelta: b.output_at_high - baselineOutput,
    outputLow: b.output_at_low,
    outputHigh: b.output_at_high,
    spread: b.spread,
    lowValue: b.low_value,
    highValue: b.high_value,
    baseline: b.baseline_value,
    unit: b.unit,
  }));

  // Chart height scales with number of parameters
  const chartHeight = Math.max(240, bars.length * 50);

  return (
    <div style={{ height: chartHeight }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 10, right: 30, left: 140, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />

          <XAxis
            type="number"
            tick={{ fontSize: 11, fill: "#6b7280" }}
            label={{
              value: outputUnit,
              position: "insideBottom",
              offset: -2,
              style: { fontSize: 12, fill: "#9ca3af" },
            }}
          />

          <YAxis
            type="category"
            dataKey="name"
            tick={{ fontSize: 12, fill: "#374151" }}
            width={130}
          />

          <Tooltip
            contentStyle={{
              backgroundColor: "#fff",
              border: "1px solid #E7E6E6",
              borderRadius: "8px",
              fontSize: "12px",
            }}
            formatter={(_value, name, props) => {
              const d = props?.payload as (typeof data)[number] | undefined;
              const seriesName = typeof name === "string" ? name : String(name ?? "");

              if (!d) {
                return ["", seriesName];
              }

              if (seriesName === "Decrease") {
                return [
                  `${d.outputLow.toFixed(3)} ${outputUnit} (param: ${d.lowValue.toFixed(3)})`,
                  "−Δ Output",
                ];
              }
              return [
                `${d.outputHigh.toFixed(3)} ${outputUnit} (param: ${d.highValue.toFixed(3)})`,
                "+Δ Output",
              ];
            }}
          />

          {/* Baseline reference line */}
          <ReferenceLine
            x={0}
            stroke="#374151"
            strokeWidth={2}
            strokeDasharray="4 4"
            label={{
              value: `Baseline: ${baselineOutput.toFixed(2)}`,
              position: "top",
              style: { fontSize: 11, fill: "#6b7280" },
            }}
          />

          {/* Low delta bars (typically red/decrease) */}
          <Bar dataKey="lowDelta" name="Decrease" fill="#ef4444" barSize={20}>
            {data.map((_, i) => (
              <Cell key={`low-${i}`} fill={data[i].lowDelta < 0 ? "#ef4444" : "#5FE838"} />
            ))}
          </Bar>

          {/* High delta bars (typically green/increase) */}
          <Bar dataKey="highDelta" name="Increase" fill="#5FE838" barSize={20}>
            {data.map((_, i) => (
              <Cell key={`high-${i}`} fill={data[i].highDelta > 0 ? "#5FE838" : "#ef4444"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
