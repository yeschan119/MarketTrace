"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { Outcome } from "@/types/api";

interface Props {
  outcomes: Outcome[];
}

export function AbnormalReturnChart({ outcomes }: Props) {
  if (!outcomes || outcomes.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500">
        No outcome data available
      </div>
    );
  }

  const sorted = [...outcomes].sort((a, b) => a.horizon_days - b.horizon_days);

  const data = sorted.map((o) => ({
    day: `D+${o.horizon_days}`,
    abnormal_return: parseFloat((o.abnormal_return * 100).toFixed(3)),
    raw_return: parseFloat((o.raw_return * 100).toFixed(3)),
    market_return: parseFloat((o.market_return * 100).toFixed(3)),
  }));

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-4 text-sm font-semibold text-gray-700">
        Abnormal Returns (%)
      </h3>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="day" tick={{ fontSize: 12 }} />
          <YAxis
            tick={{ fontSize: 12 }}
            tickFormatter={(v: number) => `${v.toFixed(1)}%`}
          />
          <Tooltip
            formatter={(value, name) => {
              const num = typeof value === "number" ? value : Array.isArray(value) ? (value[0] as number) : NaN;
              const pct = isNaN(num) ? "-" : `${num.toFixed(3)}%`;
              const label =
                name === "abnormal_return"
                  ? "Abnormal Return"
                  : name === "raw_return"
                  ? "Raw Return"
                  : "Market Return";
              return [pct, label];
            }}
          />
          <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="4 2" />
          <Line
            type="monotone"
            dataKey="abnormal_return"
            stroke="#6366f1"
            strokeWidth={2}
            dot={{ r: 4, fill: "#6366f1" }}
            name="abnormal_return"
          />
          <Line
            type="monotone"
            dataKey="raw_return"
            stroke="#10b981"
            strokeWidth={1.5}
            strokeDasharray="5 3"
            dot={{ r: 3, fill: "#10b981" }}
            name="raw_return"
          />
          <Line
            type="monotone"
            dataKey="market_return"
            stroke="#f59e0b"
            strokeWidth={1.5}
            strokeDasharray="5 3"
            dot={{ r: 3, fill: "#f59e0b" }}
            name="market_return"
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-3 flex gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-4 bg-indigo-500" /> Abnormal
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-4 bg-emerald-500" /> Raw
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-4 bg-amber-500" /> Market
        </span>
      </div>
    </div>
  );
}
