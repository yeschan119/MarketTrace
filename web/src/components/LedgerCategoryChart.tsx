"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { LedgerCategory } from "@/types/api";

type LedgerWindow = "month" | "year";

const BAR_COLORS = [
  "#6366f1",
  "#8b5cf6",
  "#ec4899",
  "#f43f5e",
  "#f59e0b",
  "#10b981",
  "#14b8a6",
  "#0ea5e9",
  "#a855f7",
  "#64748b",
];

interface Props {
  token: string;
  month: string;
}

export function LedgerCategoryChart({ token, month }: Props) {
  const { t, locale } = useI18n();
  const [window, setWindow] = useState<LedgerWindow>("month");

  const categories = useQuery({
    queryKey: ["ledger-categories", month, window],
    queryFn: () => api.getLedgerCategories(token, month, window),
    enabled: Boolean(token && month),
    retry: false,
  });

  const topCategories = (categories.data ?? [])
    .slice()
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 10);

  const chartHeight = Math.max(200, topCategories.length * 40);
  const formatWon = (value: number) => `${value.toLocaleString(locale)}원`;
  const compact = new Intl.NumberFormat(locale, { notation: "compact" });

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">
            {t("ledger.chartTitle")}
          </h2>
          <p className="mt-1 text-xs text-gray-500">
            {t("ledger.chartSubtitle")}
          </p>
        </div>
        <div
          role="group"
          className="inline-flex overflow-hidden rounded-lg border border-gray-300 text-sm"
        >
          {(["month", "year"] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={window === value}
              onClick={() => setWindow(value)}
              className={
                window === value
                  ? "bg-indigo-600 px-3 py-1.5 font-medium text-white"
                  : "bg-white px-3 py-1.5 text-gray-600 hover:bg-gray-50"
              }
            >
              {value === "month"
                ? t("ledger.windowMonth")
                : t("ledger.windowYear")}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4">
        {categories.isFetching ? (
          <div className="flex h-40 items-center justify-center text-sm text-gray-500">
            {t("ledger.chartLoading")}
          </div>
        ) : topCategories.length === 0 ? (
          <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500">
            {t("ledger.chartEmpty")}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart
              data={topCategories}
              layout="vertical"
              margin={{ top: 4, right: 24, left: 8, bottom: 4 }}
            >
              <XAxis
                type="number"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: number) => compact.format(v)}
              />
              <YAxis
                type="category"
                dataKey="category"
                width={92}
                tick={{ fontSize: 12 }}
              />
              <Tooltip
                cursor={{ fill: "#f3f4f6" }}
                formatter={(value, _name, item) => {
                  const raw = Array.isArray(value) ? value[0] : value;
                  const num = typeof raw === "number" ? raw : Number(raw);
                  const count = (item?.payload as LedgerCategory | undefined)
                    ?.count;
                  return [
                    `${formatWon(num)}${count != null ? ` · ${t("ledger.entries", { n: count })}` : ""}`,
                    t("ledger.chartAmount"),
                  ];
                }}
              />
              <Bar dataKey="amount" radius={[0, 4, 4, 0]}>
                {topCategories.map((entry, index) => (
                  <Cell
                    key={entry.category}
                    fill={BAR_COLORS[index % BAR_COLORS.length]}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
