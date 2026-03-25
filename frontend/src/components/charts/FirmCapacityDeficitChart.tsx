/**
 * FirmCapacityDeficitChart — Hourly IT capacity with deficit visualization
 * =========================================================================
 * Shows the 8760-hour IT capacity profile (sampled) with:
 *   - IT Capacity line (dark blue)
 *   - Mean and Firm (P99) horizontal reference lines
 *   - Red shaded area where IT capacity < Mean (deficit energy)
 *   - Blue shaded band between Firm and Mean (capacity gap / opportunity)
 *
 * Key concept: Deficit is relative to MEAN capacity.
 *   - Deficit hours = hours where hourly IT capacity < Mean
 *   - Capacity Gap = Mean - Firm (P99) — the opportunity zone
 *   - Compensating deficit energy raises firm capacity from P99 → Mean
 *
 * Source: POST /api/scenarios/firm-capacity-advisory → hourly_it_kw_sampled
 */

import { useMemo } from "react";
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { FirmCapacityAdvisoryResult } from "../../types";

interface Props {
  advisory: FirmCapacityAdvisoryResult;
}

export default function FirmCapacityDeficitChart({ advisory }: Props) {
  const samples = advisory.hourly_it_kw_sampled;
  if (!samples || samples.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
        Hourly data not available for deficit chart
      </div>
    );
  }

  const firmKw = advisory.firm_capacity_kw;
  const meanKw = advisory.mean_capacity_kw;
  const firmMw = firmKw / 1000;
  const meanMw = meanKw / 1000;

  const chartData = useMemo(() => {
    const totalHours = 8760;
    const step = Math.max(1, Math.round(totalHours / samples.length));
    return samples.map((itKw, i) => {
      const hour = i * step;
      const itMw = itKw / 1000;
      const belowMean = itKw < meanKw;
      return {
        hour,
        itMw,
        // For deficit shading between IT capacity and Mean line:
        // deficitLower = IT capacity (capped at mean), deficitUpper = mean
        // When IT < Mean, the gap between these two = deficit
        // When IT >= Mean, both equal meanMw so no visible area
        deficitLower: belowMean ? itMw : meanMw,
        deficitUpper: meanMw,
        // For capacity gap band between Firm and Mean:
        gapLower: firmMw,
        gapUpper: meanMw,
      };
    });
  }, [samples, firmKw, meanKw, firmMw, meanMw]);

  // Month labels for x-axis
  const monthTicks = [0, 744, 1416, 2160, 2880, 3624, 4344, 5088, 5832, 6552, 7296, 8016];
  const monthLabels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  const deficitMwh = advisory.deficit_energy_kwh / 1000;
  const gapMw = advisory.capacity_gap_mw;
  const deficitHours = advisory.deficit_hours;

  return (
    <div className="space-y-2">
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E7E6E6" />
            <XAxis
              dataKey="hour"
              ticks={monthTicks}
              tickFormatter={(h: number) => {
                const idx = monthTicks.indexOf(h);
                return idx >= 0 ? monthLabels[idx] : "";
              }}
              tick={{ fontSize: 10, fill: "#6b7280" }}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "#6b7280" }}
              label={{
                value: "MW",
                position: "insideTopLeft",
                offset: -5,
                style: { fontSize: 10, fill: "#9ca3af" },
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#fff",
                border: "1px solid #E7E6E6",
                borderRadius: "8px",
                fontSize: "11px",
              }}
              labelFormatter={(h) => `Hour ${h}`}
              formatter={(value: number, name: string) => {
                const labels: Record<string, string> = {
                  itMw: "IT Capacity",
                  deficitUpper: "Mean",
                  deficitLower: "IT (at deficit)",
                };
                if (name === "deficitLower" || name === "gapLower" || name === "gapUpper") {
                  return [null, null] as unknown as [string, string];
                }
                return [`${value.toFixed(3)} MW`, labels[name] || name];
              }}
              itemSorter={() => 0}
            />

            {/* Capacity gap band: light blue fill between Firm and Mean */}
            <Area
              type="stepAfter"
              dataKey="gapUpper"
              stroke="none"
              fill="#795AFD20"
              fillOpacity={1}
              name="gapUpper"
              legendType="none"
              isAnimationActive={false}
            />
            <Area
              type="stepAfter"
              dataKey="gapLower"
              stroke="none"
              fill="#ffffff"
              fillOpacity={1}
              name="gapLower"
              legendType="none"
              isAnimationActive={false}
            />

            {/* Deficit area: red fill between IT capacity and Mean line */}
            {/* We overlay two areas: deficitUpper (mean) with red fill, then
                deficitLower (IT capped at mean) with white fill to "erase"
                the non-deficit portion. The visual result is red only where
                IT < Mean. */}
            <Area
              type="monotone"
              dataKey="deficitUpper"
              stroke="none"
              fill="#ef444450"
              fillOpacity={1}
              name="deficitUpper"
              legendType="none"
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="deficitLower"
              stroke="none"
              fill="#ffffff"
              fillOpacity={1}
              name="deficitLower"
              legendType="none"
              isAnimationActive={false}
            />

            {/* IT capacity line — on top of the filled areas */}
            <Line
              type="monotone"
              dataKey="itMw"
              stroke="#0A2240"
              strokeWidth={1.2}
              dot={false}
              name="itMw"
              legendType="none"
              isAnimationActive={false}
            />

            {/* Firm (P99) reference line */}
            <ReferenceLine
              y={firmMw}
              stroke="#5FE838"
              strokeWidth={1.5}
              strokeDasharray="6 3"
              label={{
                value: `Firm P99: ${firmMw.toFixed(2)} MW`,
                position: "right",
                style: { fontSize: 9, fill: "#5FE838", fontWeight: 600 },
              }}
            />

            {/* Mean reference line */}
            <ReferenceLine
              y={meanMw}
              stroke="#795AFD"
              strokeWidth={1.5}
              strokeDasharray="6 3"
              label={{
                value: `Mean: ${meanMw.toFixed(2)} MW`,
                position: "right",
                style: { fontSize: 9, fill: "#795AFD", fontWeight: 600 },
              }}
            />

            <Legend
              content={() => (
                <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs mt-2 px-2">
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block w-4 h-0.5 bg-[#0A2240] rounded" />
                    IT Capacity
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block w-4 h-0.5 border-t-2 border-dashed" style={{ borderColor: "#5FE838" }} />
                    Firm P99: {firmMw.toFixed(2)} MW
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block w-4 h-0.5 border-t-2 border-dashed" style={{ borderColor: "#795AFD" }} />
                    Mean: {meanMw.toFixed(2)} MW
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block w-3.5 h-3.5 rounded-sm" style={{ backgroundColor: "rgba(239,68,68,0.35)" }} />
                    Deficit Energy: {deficitMwh.toFixed(1)} MWh
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block w-3.5 h-3.5 rounded-sm" style={{ backgroundColor: "rgba(121,90,253,0.15)" }} />
                    Capacity Gap: {gapMw.toFixed(2)} MW
                  </span>
                  <span className="flex items-center gap-1.5 text-gray-500">
                    Deficit Hours: {deficitHours.toLocaleString()} hrs
                  </span>
                </div>
              )}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
