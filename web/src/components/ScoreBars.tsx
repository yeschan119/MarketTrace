"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface ScoreEntry {
  label: string;
  value: number;
  color: string;
}

interface Props {
  confidence: number;
  surprise_score: number;
  novelty_score: number;
  source_reliability: number;
}

export function ScoreBars({
  confidence,
  surprise_score,
  novelty_score,
  source_reliability,
}: Props) {
  const scores: ScoreEntry[] = [
    { label: "Confidence", value: confidence, color: "#6366f1" },
    { label: "Surprise", value: surprise_score, color: "#f59e0b" },
    { label: "Novelty", value: novelty_score, color: "#10b981" },
    { label: "Source Reliability", value: source_reliability, color: "#3b82f6" },
  ];

  const data = scores.map((s) => ({
    ...s,
    displayValue: parseFloat((s.value * 100).toFixed(1)),
  }));

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-4 text-sm font-semibold text-gray-700">Score Components</h3>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 0, right: 32, left: 80, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f0f0f0" />
          <XAxis
            type="number"
            domain={[0, 100]}
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => `${v}%`}
          />
          <YAxis
            type="category"
            dataKey="label"
            tick={{ fontSize: 12 }}
            width={80}
          />
          <Tooltip
            formatter={(value) => {
              const num = typeof value === "number" ? value : Array.isArray(value) ? (value[0] as number) : NaN;
              const pct = isNaN(num) ? "-" : `${num.toFixed(1)}%`;
              return [pct];
            }}
          />
          <Bar dataKey="displayValue" radius={[0, 4, 4, 0]}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
