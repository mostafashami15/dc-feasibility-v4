/**
 * GreenDispatchChart - Stacked area chart for hourly PV+BESS dispatch
 * ====================================================================
 * Shows how the hourly overhead demand is met by PV, BESS, fuel cell,
 * and grid import as stacked areas, with total overhead as an overlay line.
 *
 * The 8760-entry hourly_dispatch array is sampled every 12 hours for
 * performance (~730 data points).
 */

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface GreenDispatchChartProps {
  hourlyDispatch: Array<Record<string, number>>;
  totalOverheadMwh: number;
  pvToOverheadMwh: number;
  bessDischargeMwh: number;
  fuelCellMwh: number;
  gridImportMwh: number;
}

const SAMPLE_INTERVAL = 12;

const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** Cumulative hours at the start of each month (non-leap year). */
const MONTH_HOUR_STARTS = [0, 744, 1416, 2160, 2880, 3624, 4344, 5088, 5832, 6552, 7296, 8016];

interface ChartDataPoint {
  hour: number;
  pvOverhead: number;
  bess: number;
  fuelCell: number;
  grid: number;
  totalOverhead: number;
}

function buildChartData(hourlyDispatch: Array<Record<string, number>>): ChartDataPoint[] {
  const points: ChartDataPoint[] = [];
  for (let i = 0; i < hourlyDispatch.length; i += SAMPLE_INTERVAL) {
    const row = hourlyDispatch[i];
    const pvOverhead = row.pv_to_overhead_kw ?? 0;
    const bess = row.bess_discharge_kw ?? 0;
    const fuelCell = row.fuel_cell_kw ?? 0;
    const grid = row.grid_import_kw ?? 0;
    const totalOverhead = row.total_overhead_kw ?? (pvOverhead + bess + fuelCell + grid);
    points.push({ hour: i, pvOverhead, bess, fuelCell, grid, totalOverhead });
  }
  return points;
}

function getMonthTicks(): { ticks: number[]; labels: Record<number, string> } {
  const ticks: number[] = [];
  const labels: Record<number, string> = {};
  for (let m = 0; m < 12; m++) {
    ticks.push(MONTH_HOUR_STARTS[m]);
    labels[MONTH_HOUR_STARTS[m]] = MONTH_LABELS[m];
  }
  return { ticks, labels };
}

function formatMwh(value: number): string {
  return `${(value / 1000).toFixed(1)} MWh`;
}

export default function GreenDispatchChart({
  hourlyDispatch,
  totalOverheadMwh,
  pvToOverheadMwh,
  bessDischargeMwh,
  fuelCellMwh,
  gridImportMwh,
}: GreenDispatchChartProps) {
  const chartData = useMemo(() => buildChartData(hourlyDispatch), [hourlyDispatch]);
  const { ticks, labels } = useMemo(() => getMonthTicks(), []);

  // Determine if we should show MW instead of kW
  const maxVal = useMemo(() => {
    let max = 0;
    for (const pt of chartData) {
      const sum = pt.pvOverhead + pt.bess + pt.fuelCell + pt.grid;
      if (sum > max) max = sum;
      if (pt.totalOverhead > max) max = pt.totalOverhead;
    }
    return max;
  }, [chartData]);

  const useMW = maxVal >= 1000;
  const unitLabel = useMW ? "MW" : "kW";
  const scale = useMW ? 1 / 1000 : 1;

  // If using MW, transform the data
  const displayData = useMemo(() => {
    if (!useMW) return chartData;
    return chartData.map((pt) => ({
      hour: pt.hour,
      pvOverhead: pt.pvOverhead * scale,
      bess: pt.bess * scale,
      fuelCell: pt.fuelCell * scale,
      grid: pt.grid * scale,
      totalOverhead: pt.totalOverhead * scale,
    }));
  }, [chartData, useMW, scale]);

  if (chartData.length === 0) {
    return (
      <div className="h-72 flex items-center justify-center text-gray-400 text-sm">
        No hourly dispatch data available
      </div>
    );
  }

  return (
    <div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={displayData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="hour"
              ticks={ticks}
              tickFormatter={(value: number) => labels[value] ?? ""}
              tick={{ fontSize: 12, fill: "#6b7280" }}
            />
            <YAxis
              tick={{ fontSize: 12, fill: "#6b7280" }}
              width={56}
              tickFormatter={(value: number) => Number(value).toFixed(useMW ? 1 : 0)}
              label={{
                value: unitLabel,
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 12, fill: "#6b7280" },
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#fff",
                border: "1px solid #E7E6E6",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              labelFormatter={(label: number) => `Hour ${label}`}
              formatter={(value: number, name: string) => {
                const formatted = useMW
                  ? `${value.toFixed(2)} MW`
                  : `${value.toFixed(0)} kW`;
                return [formatted, name];
              }}
            />
            <Area
              type="monotone"
              dataKey="pvOverhead"
              name="PV to Overhead"
              stackId="dispatch"
              stroke="#5FE838"
              fill="#5FE838"
              fillOpacity={0.7}
              dot={false}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="bess"
              name="BESS Discharge"
              stackId="dispatch"
              stroke="#795AFD"
              fill="#795AFD"
              fillOpacity={0.7}
              dot={false}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="fuelCell"
              name="Fuel Cell"
              stackId="dispatch"
              stroke="#4E2589"
              fill="#4E2589"
              fillOpacity={0.7}
              dot={false}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="grid"
              name="Grid Import"
              stackId="dispatch"
              stroke="#ef4444"
              fill="#ef4444"
              fillOpacity={0.7}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="totalOverhead"
              name="Total Overhead"
              stroke="#0A2240"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Legend
              wrapperStyle={{ fontSize: "12px" }}
              formatter={(value: string) => {
                const mwhMap: Record<string, number> = {
                  "PV to Overhead": pvToOverheadMwh,
                  "BESS Discharge": bessDischargeMwh,
                  "Fuel Cell": fuelCellMwh,
                  "Grid Import": gridImportMwh,
                  "Total Overhead": totalOverheadMwh,
                };
                const mwh = mwhMap[value];
                if (mwh !== undefined) {
                  return `${value} (${formatMwh(mwh)})`;
                }
                return value;
              }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
