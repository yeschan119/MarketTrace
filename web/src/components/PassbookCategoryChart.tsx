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
import type {
  PassbookCategory,
  PassbookDirection,
  PassbookEntry,
} from "@/types/api";

type PassbookWindow = "month" | "year";

const OUT_COLORS = [
  "#f43f5e",
  "#f97316",
  "#f59e0b",
  "#ec4899",
  "#ef4444",
  "#fb7185",
  "#fdba74",
  "#fca5a5",
  "#e11d48",
  "#9f1239",
];

const IN_COLORS = [
  "#10b981",
  "#14b8a6",
  "#0ea5e9",
  "#22c55e",
  "#06b6d4",
  "#34d399",
  "#2dd4bf",
  "#38bdf8",
  "#059669",
  "#0d9488",
];

interface Props {
  token: string;
  month: string;
}

export function PassbookCategoryChart({ token, month }: Props) {
  const { t, locale } = useI18n();
  const [window, setWindow] = useState<PassbookWindow>("month");
  const [direction, setDirection] = useState<PassbookDirection>("out");

  const categories = useQuery({
    queryKey: ["passbook-categories", month, window],
    queryFn: () => api.getPassbookCategories(token, month, window),
    enabled: Boolean(token && month),
    retry: false,
  });

  const topEntries = useQuery({
    queryKey: ["passbook-top-entries", month, window, direction],
    queryFn: () => api.getPassbookTopEntries(token, month, window, direction, 10),
    enabled: Boolean(token && month),
    retry: false,
  });

  const amountOf = (category: PassbookCategory) =>
    direction === "in" ? category.deposit : category.withdrawal;

  const topCategories = (categories.data ?? [])
    .filter((category) => amountOf(category) > 0)
    .slice()
    .sort((a, b) => amountOf(b) - amountOf(a))
    .slice(0, 10)
    .map((category) => ({ ...category, value: amountOf(category) }));
  const rankedEntries: PassbookEntry[] = topEntries.data ?? [];
  const palette = direction === "in" ? IN_COLORS : OUT_COLORS;

  const chartHeight = Math.max(200, topCategories.length * 40);
  const formatWon = (value: number) => `${value.toLocaleString(locale)}원`;
  const formatDate = (value: string) =>
    new Date(value).toLocaleDateString(locale, {
      month: "short",
      day: "numeric",
    });
  const compact = new Intl.NumberFormat(locale, { notation: "compact" });

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">
            {t("passbook.chartTitle")}
          </h2>
          <p className="mt-1 text-xs text-gray-500">
            {t("passbook.chartSubtitle")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div
            role="group"
            className="inline-flex overflow-hidden rounded-lg border border-gray-300 text-sm"
          >
            {(["out", "in"] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={direction === value}
                onClick={() => setDirection(value)}
                className={
                  direction === value
                    ? "bg-gray-900 px-3 py-1.5 font-medium text-white"
                    : "bg-white px-3 py-1.5 text-gray-600 hover:bg-gray-50"
                }
              >
                {value === "out"
                  ? t("passbook.directionOut")
                  : t("passbook.directionIn")}
              </button>
            ))}
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
                  ? t("passbook.windowMonth")
                  : t("passbook.windowYear")}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4">
        {categories.isFetching ? (
          <div className="flex h-40 items-center justify-center text-sm text-gray-500">
            {t("passbook.chartLoading")}
          </div>
        ) : topCategories.length === 0 ? (
          <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500">
            {t("passbook.chartEmpty")}
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
                  const count = (item?.payload as PassbookCategory | undefined)
                    ?.count;
                  return [
                    `${formatWon(num)}${count != null ? ` · ${t("passbook.entries", { n: count })}` : ""}`,
                    t("passbook.chartAmount"),
                  ];
                }}
              />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {topCategories.map((entry, index) => (
                  <Cell
                    key={entry.category}
                    fill={palette[index % palette.length]}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="mt-6 border-t border-gray-200 pt-4">
        <h3 className="text-sm font-semibold text-gray-900">
          {direction === "in"
            ? t("passbook.topTitleIn")
            : t("passbook.topTitleOut")}
        </h3>
        <p className="mt-1 text-xs text-gray-500">{t("passbook.topSubtitle")}</p>

        <div className="mt-3">
          {topEntries.isFetching ? (
            <div className="flex h-24 items-center justify-center text-sm text-gray-500">
              {t("passbook.chartLoading")}
            </div>
          ) : rankedEntries.length === 0 ? (
            <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500">
              {t("passbook.topEmpty")}
            </div>
          ) : (
            <ol className="space-y-1">
              {rankedEntries.map((entry, index) => (
                <li
                  key={`${entry.date}-${entry.time}-${entry.description}-${index}`}
                  className="flex items-center gap-3 rounded-lg px-2 py-1.5 odd:bg-gray-50"
                >
                  <span
                    className={
                      direction === "in"
                        ? "flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 font-mono text-xs font-semibold text-emerald-700"
                        : "flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-rose-100 font-mono text-xs font-semibold text-rose-700"
                    }
                  >
                    {index + 1}
                  </span>
                  <span className="w-16 shrink-0 text-xs text-gray-500">
                    {formatDate(entry.date)}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm text-gray-900">
                    {entry.description}
                  </span>
                  <span className="shrink-0 font-mono text-sm font-semibold text-gray-900">
                    {formatWon(direction === "in" ? entry.deposit : entry.withdrawal)}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}
