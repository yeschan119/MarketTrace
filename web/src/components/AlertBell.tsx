"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/**
 * Header bell linking to /alerts, with an unread-count badge. Polls the
 * unread-count endpoint so a new alert (created on the next ingest) shows up
 * without a reload. Read-only + public, so no auth needed to see the count.
 */
export function AlertBell() {
  const { t } = useI18n();
  const { data } = useQuery({
    queryKey: ["alerts", "unread-count"],
    queryFn: () => api.getUnreadCount(),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
  const count = data?.count ?? 0;

  return (
    <a
      href="/alerts"
      className="relative inline-flex items-center text-gray-500 hover:text-gray-900"
      aria-label={t("alerts.title")}
      title={t("alerts.title")}
    >
      <svg
        className="h-5 w-5"
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={1.8}
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0"
        />
      </svg>
      {count > 0 && (
        <span className="absolute -right-2 -top-2 inline-flex min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1 text-[11px] font-bold leading-[18px] text-white">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </a>
  );
}
