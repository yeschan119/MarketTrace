"use client";

import { AuthControls } from "@/components/AuthControls";
import { LanguageToggle, useI18n } from "@/lib/i18n";

export function SiteHeader() {
  const { t } = useI18n();

  return (
    <header className="border-b border-gray-200 bg-white px-6 py-4">
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 sm:gap-6">
        <a href="/" className="text-xl font-bold tracking-tight text-indigo-600">
          MarketTrace
        </a>
        <a
          href="/events"
          className="text-sm font-medium text-gray-600 hover:text-gray-900"
        >
          {t("nav.events")}
        </a>
        <a
          href="/stats"
          className="text-sm font-medium text-gray-600 hover:text-gray-900"
        >
          {t("nav.stats")}
        </a>
        <a
          href="/macro"
          className="text-sm font-medium text-gray-600 hover:text-gray-900"
        >
          {t("nav.macro")}
        </a>
        <a
          href="/ledger"
          className="text-sm font-medium text-gray-600 hover:text-gray-900"
        >
          {t("nav.ledger")}
        </a>
        <a
          href="/passbook"
          className="text-sm font-medium text-gray-600 hover:text-gray-900"
        >
          {t("nav.passbook")}
        </a>
        {/* Language toggle sits immediately left of the auth / Ingest controls. */}
        <div className="ml-auto flex items-center gap-3">
          <LanguageToggle />
          <AuthControls />
        </div>
      </nav>
    </header>
  );
}
