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
import { useI18n } from "@/lib/i18n";
import { InfoTip } from "@/components/InfoTip";

interface ScoreEntry {
  label: string;
  value: number;
  color: string;
}

interface Props {
  confidence: number;
  surprise_score: number | null;
  novelty_score: number | null;
  source_reliability: number | null;
}

export function ScoreBars({
  confidence,
  surprise_score,
  novelty_score,
  source_reliability,
}: Props) {
  const { t } = useI18n();
  // Optional scores (surprise/novelty/source_reliability) may be null when the
  // model omits them; drop those bars rather than rendering a misleading 0%.
  const scores: ScoreEntry[] = (
    [
      { label: t("scores.confidence"), value: confidence, color: "#6366f1" },
      { label: t("scores.surprise"), value: surprise_score, color: "#f59e0b" },
      { label: t("scores.novelty"), value: novelty_score, color: "#10b981" },
      { label: t("scores.sourceReliability"), value: source_reliability, color: "#3b82f6" },
    ] as { label: string; value: number | null; color: string }[]
  ).filter((s): s is ScoreEntry => s.value != null);

  const data = scores.map((s) => ({
    ...s,
    displayValue: parseFloat((s.value * 100).toFixed(1)),
  }));

  return (
    <div className="rounded-lg border border-gray-200 bg-surface p-4">
      <h3 className="mb-4 flex items-center gap-1.5 text-sm font-semibold text-gray-700">
        {t("scores.title")}
        <InfoTip text={t("scores.titleTip")} />
      </h3>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 0, right: 32, left: 80, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--chart-grid)" />
          <XAxis
            type="number"
            domain={[0, 100]}
            tick={{ fontSize: 11, fill: "var(--chart-axis)" }}
            stroke="var(--chart-axis)"
            tickFormatter={(v: number) => `${v}%`}
          />
          <YAxis
            type="category"
            dataKey="label"
            tick={{ fontSize: 12, fill: "var(--chart-axis)" }}
            stroke="var(--chart-axis)"
            width={80}
          />
          <Tooltip
            cursor={{ fill: "rgb(var(--c-gray-100))" }}
            contentStyle={{
              backgroundColor: "rgb(var(--c-surface))",
              border: "1px solid rgb(var(--c-gray-200))",
              borderRadius: 8,
              color: "rgb(var(--c-gray-900))",
            }}
            labelStyle={{ color: "rgb(var(--c-gray-900))" }}
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
