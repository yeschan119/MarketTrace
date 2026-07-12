"use client";

import { useQuery } from "@tanstack/react-query";
import { AuthControls } from "@/components/AuthControls";
import { AlertBell } from "@/components/AlertBell";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LanguageToggle, useI18n } from "@/lib/i18n";

const NAV_ITEMS = [
  { ids: ["nav-search"], href: "/instruments", label: "nav.search" },
  { ids: ["nav-events"], href: "/events", label: "nav.events" },
  { ids: ["nav-rankings"], href: "/rankings", label: "nav.rankings" },
  { ids: ["nav-screener"], href: "/screener", label: "nav.screener" },
  { ids: ["nav-watchlist"], href: "/watchlist", label: "nav.watchlist" },
  { ids: ["nav-stats"], href: "/stats", label: "nav.stats" },
  { ids: ["nav-macro"], href: "/macro", label: "nav.macro" },
  { ids: ["nav-ledger"], href: "/ledger", label: "nav.ledger" },
  { ids: ["nav-passbook"], href: "/passbook", label: "nav.passbook" },
  {
    ids: ["admin-users", "admin-tabs"],
    href: "/admin",
    label: "nav.admin",
    adminOnly: true,
  },
];

export function SiteHeader() {
  const { t } = useI18n();
  const { user } = useAuth();
  const { data: tabCatalog } = useQuery({
    queryKey: ["tab-catalog"],
    queryFn: () => api.getTabCatalog(),
  });

  const allowedTabs = new Set(user?.allowed_tabs ?? []);
  const alertsVisible =
    (!tabCatalog || tabCatalog.statuses["nav-alerts"] !== false) &&
    (!user ||
      user.role === "admin" ||
      allowedTabs.size === 0 ||
      allowedTabs.has("nav-alerts"));

  function isVisible(item: (typeof NAV_ITEMS)[number]): boolean {
    if (item.adminOnly && user?.role !== "admin") return false;
    if (tabCatalog && !item.ids.some((id) => tabCatalog.statuses[id] !== false)) {
      return false;
    }
    if (user && user.role !== "admin" && allowedTabs.size > 0) {
      return item.ids.some((id) => allowedTabs.has(id));
    }
    return true;
  }

  return (
    <header className="border-b border-gray-200 bg-white px-6 py-4">
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 sm:gap-6">
        <a href="/" className="text-xl font-bold tracking-tight text-indigo-600">
          MarketTrace
        </a>
        {NAV_ITEMS.filter(isVisible).map((item) => (
          <a
            key={item.href}
            href={item.href}
            className="text-sm font-medium text-gray-600 hover:text-gray-900"
          >
            {t(item.label)}
          </a>
        ))}
        {/* Language toggle sits immediately left of the auth / Ingest controls. */}
        <div className="ml-auto flex items-center gap-3">
          {alertsVisible && <AlertBell />}
          <LanguageToggle />
          <AuthControls />
        </div>
      </nav>
    </header>
  );
}
