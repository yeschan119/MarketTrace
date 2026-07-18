"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { useCategoryCustomization } from "@/lib/useCategoryCustomization";
import { PassbookCategoryChart } from "@/components/PassbookCategoryChart";
import { CategoryEditControl } from "@/components/CategoryEditControl";
import { CategoryManager } from "@/components/CategoryManager";
import type {
  PassbookEntry,
  PassbookStatement,
  PassbookStatementSummary,
} from "@/types/api";

function formatWon(value: number | null, locale: string): string {
  if (value == null) return "-";
  return `${value.toLocaleString(locale)}원`;
}

function formatDate(value: string | null, locale: string): string {
  if (!value) return "-";
  return new Date(value).toLocaleDateString(locale);
}

function formatMonth(value: string | null, locale: string): string {
  if (!value) return "-";
  return new Date(`${toMonthValue(value)}-01T00:00:00`).toLocaleDateString(
    locale,
    { year: "numeric", month: "long" }
  );
}

function toMonthValue(value: string): string {
  return value.slice(0, 7);
}

function SummaryItem({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500">
        {label}
      </div>
      <div className="mt-1 break-all text-base font-semibold text-gray-900">
        {value}
      </div>
    </div>
  );
}

type PassbookCategorySection = {
  category: string;
  withdrawal: number;
  deposit: number;
  count: number;
  entries: PassbookEntry[];
};

function buildCategorySections(
  statement: PassbookStatement | undefined
): PassbookCategorySection[] {
  if (!statement) return [];

  const entriesByCategory = new Map<string, PassbookEntry[]>();
  for (const entry of statement.entries) {
    const entries = entriesByCategory.get(entry.category) ?? [];
    entries.push(entry);
    entriesByCategory.set(entry.category, entries);
  }

  const knownCategories = new Set(
    statement.categories.map((category) => category.category)
  );
  const sections: PassbookCategorySection[] = statement.categories.map(
    (category) => ({
      category: category.category,
      withdrawal: category.withdrawal,
      deposit: category.deposit,
      count: category.count,
      entries: entriesByCategory.get(category.category) ?? [],
    })
  );

  for (const [category, entries] of entriesByCategory) {
    if (knownCategories.has(category)) continue;
    sections.push({
      category,
      withdrawal: entries.reduce((sum, entry) => sum + entry.withdrawal, 0),
      deposit: entries.reduce((sum, entry) => sum + entry.deposit, 0),
      count: entries.length,
      entries,
    });
  }

  return sections;
}

export default function PassbookPage() {
  const { token, logout } = useAuth();
  const { t, locale } = useI18n();
  const queryClient = useQueryClient();
  const customization = useCategoryCustomization(token, "/passbook");
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [authNotice, setAuthNotice] = useState("");
  const [validationError, setValidationError] = useState("");
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    () => new Set()
  );

  function toPassbookErrorMessage(err: unknown): string {
    if (isApiError(err) && err.status === 401) {
      const message = t("passbook.sessionExpired");
      setAuthNotice(message);
      logout();
      return message;
    }
    if (isApiError(err) && err.detail === "statement password required") {
      return t("passbook.passwordRequired");
    }
    if (isApiError(err) && err.detail === "invalid statement password") {
      return t("passbook.invalidPassword");
    }
    return err instanceof Error ? err.message : t("common.unknownError");
  }

  const statementSummaries = useQuery({
    queryKey: ["passbook-statements"],
    queryFn: async () => {
      try {
        return await api.listPassbookStatements(token ?? "");
      } catch (err) {
        throw new Error(toPassbookErrorMessage(err));
      }
    },
    enabled: Boolean(token),
    retry: false,
  });

  useEffect(() => {
    if (selectedMonth || !statementSummaries.data?.length) return;
    setSelectedMonth(toMonthValue(statementSummaries.data[0].statement_month));
  }, [selectedMonth, statementSummaries.data]);

  const selectedStatement = useQuery({
    queryKey: ["passbook-statement", selectedMonth],
    queryFn: async () => {
      if (!selectedMonth) throw new Error(t("passbook.noSavedStatements"));
      try {
        return await api.getPassbookStatementByMonth(token ?? "", selectedMonth);
      } catch (err) {
        throw new Error(toPassbookErrorMessage(err));
      }
    },
    enabled: Boolean(token && selectedMonth),
    retry: false,
  });

  const uploadStatement = useMutation({
    mutationFn: async ({
      nextFile,
      nextPassword,
    }: {
      nextFile: File;
      nextPassword: string;
    }) => {
      try {
        return await api.uploadPassbookStatement(
          token ?? "",
          nextFile,
          nextPassword
        );
      } catch (err) {
        throw new Error(toPassbookErrorMessage(err));
      }
    },
    onSuccess: (statement) => {
      const month = statement.statement_month
        ? toMonthValue(statement.statement_month)
        : null;
      if (month) {
        queryClient.setQueryData(["passbook-statement", month], statement);
        setSelectedMonth(month);
      }
      void queryClient.invalidateQueries({ queryKey: ["passbook-statements"] });
    },
  });

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!file) {
      setValidationError(t("passbook.missingFile"));
      return;
    }
    const nextPassword = password.trim();
    if (!nextPassword) {
      setValidationError(t("passbook.passwordRequired"));
      return;
    }
    setAuthNotice("");
    setValidationError("");
    uploadStatement.mutate({ nextFile: file, nextPassword });
  }

  const summaries: PassbookStatementSummary[] = statementSummaries.data ?? [];
  const selectedMonthUpload =
    uploadStatement.data?.statement_month &&
    toMonthValue(uploadStatement.data.statement_month) === selectedMonth
      ? uploadStatement.data
      : undefined;
  const statement: PassbookStatement | undefined =
    selectedStatement.data ?? selectedMonthUpload;
  const statementIdentity =
    statement?.uploaded_at ?? statement?.statement_month ?? "";
  const categorySections = useMemo(
    () => buildCategorySections(statement),
    [statement]
  );
  const statementCategoryNames = useMemo(
    () => categorySections.map((section) => section.category),
    [categorySections]
  );
  const isFetching =
    selectedStatement.isFetching || statementSummaries.isFetching;
  const isParsing = uploadStatement.isPending;
  const errorMessage = validationError
    ? validationError
    : uploadStatement.isError && uploadStatement.error instanceof Error
      ? uploadStatement.error.message
      : selectedStatement.isError && selectedStatement.error instanceof Error
        ? selectedStatement.error.message
        : statementSummaries.isError && statementSummaries.error instanceof Error
          ? statementSummaries.error.message
          : "";

  useEffect(() => {
    setExpandedCategories(new Set());
  }, [statementIdentity]);

  function toggleCategory(category: string) {
    setExpandedCategories((current) => {
      const next = new Set(current);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  }

  if (!token) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-8 text-sm text-gray-600 shadow-sm">
        {authNotice || t("passbook.loginRequired")}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {t("passbook.title")}
          </h1>
          <p className="mt-2 text-sm text-gray-500">{t("passbook.subtitle")}</p>
        </div>
        {summaries.length > 0 && (
          <span className="text-sm text-gray-500">
            {t("passbook.savedMonths", { n: summaries.length })}
          </span>
        )}
      </div>

      {summaries.length > 0 && (
        <label className="block max-w-xs">
          <span className="mb-1 block text-sm font-medium text-gray-700">
            {t("passbook.monthLabel")}
          </span>
          <select
            value={selectedMonth ?? ""}
            disabled={isParsing}
            onChange={(e) => {
              setValidationError("");
              setSelectedMonth(e.target.value || null);
            }}
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          >
            {summaries.map((summary) => {
              const monthValue = toMonthValue(summary.statement_month);
              return (
                <option key={monthValue} value={monthValue}>
                  {formatMonth(summary.statement_month, locale)}
                </option>
              );
            })}
          </select>
        </label>
      )}

      <form
        onSubmit={handleSubmit}
        noValidate
        className="grid gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm md:grid-cols-[minmax(0,1.2fr)_minmax(220px,0.8fr)_auto] md:items-end"
      >
        <label>
          <span className="mb-1 block text-sm font-medium text-gray-700">
            {t("passbook.fileLabel")}
          </span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            required
            disabled={isParsing}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setValidationError("");
            }}
            className="block w-full text-sm text-gray-700 file:mr-3 file:rounded-md file:border-0 file:bg-gray-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-gray-700 hover:file:bg-gray-200"
          />
          <span className="mt-1 block truncate text-xs text-gray-500">
            {file ? file.name : t("passbook.fileHelp")}
          </span>
        </label>
        <label className="flex-1">
          <span className="mb-1 block text-sm font-medium text-gray-700">
            {t("passbook.passwordLabel")}
          </span>
          <input
            type="password"
            value={password}
            required
            disabled={isParsing}
            onChange={(e) => {
              setPassword(e.target.value);
              setValidationError("");
            }}
            placeholder={t("passbook.passwordPlaceholder")}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          />
        </label>
        <button
          type="submit"
          disabled={isParsing || !file}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isParsing && (
            <span
              aria-hidden="true"
              className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
            />
          )}
          <span>{isParsing ? t("passbook.parsing") : t("passbook.load")}</span>
        </button>
      </form>

      {(isParsing || isFetching) && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center gap-3 rounded-lg border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-700"
        >
          <span
            aria-hidden="true"
            className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600"
          />
          <span>
            {isParsing
              ? t("passbook.parsing")
              : selectedMonth
                ? t("passbook.detailLoading")
                : t("passbook.listLoading")}
          </span>
        </div>
      )}

      {errorMessage && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
          <p className="font-semibold">{t("passbook.failTitle")}</p>
          <p className="mt-1 text-sm">{errorMessage}</p>
        </div>
      )}

      {statement && (
        <>
          <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-4">
            <SummaryItem
              label={t("passbook.account")}
              value={statement.account_no ?? "-"}
            />
            <SummaryItem
              label={t("passbook.holder")}
              value={statement.account_holder ?? "-"}
            />
            <SummaryItem
              label={t("passbook.statementMonth")}
              value={formatMonth(statement.statement_month, locale)}
            />
            <SummaryItem
              label={t("passbook.period")}
              value={`${formatDate(statement.period_start, locale)} - ${formatDate(
                statement.period_end,
                locale
              )}`}
            />
            <SummaryItem
              label={t("passbook.closingBalance")}
              value={formatWon(statement.closing_balance, locale)}
            />
            <SummaryItem
              label={t("passbook.withdrawalTotal")}
              value={formatWon(statement.withdrawal_total, locale)}
            />
            <SummaryItem
              label={t("passbook.depositTotal")}
              value={formatWon(statement.deposit_total, locale)}
            />
            <SummaryItem
              label={t("passbook.uploadedAt")}
              value={formatDate(statement.uploaded_at, locale)}
            />
          </div>

          <div className="space-y-4">
            {selectedMonth && (
              <PassbookCategoryChart token={token} month={selectedMonth} />
            )}

            <CategoryManager controller={customization} />

            {statement.entries.length === 0 ? (
              <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500">
                {t("passbook.empty")}
              </div>
            ) : (
              <div className="max-h-[28rem] space-y-3 overflow-y-auto pr-1">
                {categorySections.map((section, sectionIndex) => {
                  const isExpanded = expandedCategories.has(section.category);
                  const sectionId = `passbook-category-${sectionIndex}`;
                  return (
                    <section
                      key={section.category}
                      className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm"
                    >
                      <button
                        type="button"
                        aria-expanded={isExpanded}
                        aria-controls={sectionId}
                        onClick={() => toggleCategory(section.category)}
                        className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                      >
                        <span className="flex min-w-0 items-center gap-3">
                          <span
                            aria-hidden="true"
                            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-gray-300 font-mono text-sm font-semibold text-gray-600"
                          >
                            {isExpanded ? "-" : "+"}
                          </span>
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-semibold text-gray-900">
                              {section.category}
                            </span>
                            <span className="block text-xs text-gray-500">
                              {t("passbook.entries", { n: section.count })}
                            </span>
                          </span>
                        </span>
                        <span className="shrink-0 text-right text-xs">
                          {section.withdrawal > 0 && (
                            <span className="block font-mono font-semibold text-rose-600">
                              -{formatWon(section.withdrawal, locale)}
                            </span>
                          )}
                          {section.deposit > 0 && (
                            <span className="block font-mono font-semibold text-emerald-600">
                              +{formatWon(section.deposit, locale)}
                            </span>
                          )}
                        </span>
                      </button>

                      {isExpanded && (
                        <div
                          id={sectionId}
                          className="overflow-x-auto border-t border-gray-200"
                        >
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                                <th className="px-4 py-3">
                                  {t("passbook.th.date")}
                                </th>
                                <th className="px-4 py-3">
                                  {t("passbook.th.summary")}
                                </th>
                                <th className="px-4 py-3">
                                  {t("passbook.th.description")}
                                </th>
                                <th className="px-4 py-3 text-right">
                                  {t("passbook.th.withdrawal")}
                                </th>
                                <th className="px-4 py-3 text-right">
                                  {t("passbook.th.deposit")}
                                </th>
                                <th className="px-4 py-3 text-right">
                                  {t("passbook.th.balance")}
                                </th>
                                <th className="px-4 py-3 text-right">
                                  {t("customize.th.category")}
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {section.entries.map((entry, idx) => (
                                <tr
                                  key={`${entry.date}-${entry.time}-${entry.description}-${idx}`}
                                  className="border-b border-gray-100 last:border-0 hover:bg-gray-50"
                                >
                                  <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                                    {formatDate(entry.date, locale)}
                                  </td>
                                  <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                                    {entry.summary}
                                  </td>
                                  <td className="max-w-xs px-4 py-3 text-gray-900">
                                    <span className="block truncate">
                                      {entry.description}
                                    </span>
                                  </td>
                                  <td className="whitespace-nowrap px-4 py-3 text-right font-mono text-rose-600">
                                    {entry.withdrawal > 0
                                      ? formatWon(entry.withdrawal, locale)
                                      : "-"}
                                  </td>
                                  <td className="whitespace-nowrap px-4 py-3 text-right font-mono text-emerald-600">
                                    {entry.deposit > 0
                                      ? formatWon(entry.deposit, locale)
                                      : "-"}
                                  </td>
                                  <td className="whitespace-nowrap px-4 py-3 text-right font-mono text-gray-500">
                                    {formatWon(entry.balance, locale)}
                                  </td>
                                  <td className="whitespace-nowrap px-4 py-3 text-right">
                                    <CategoryEditControl
                                      controller={customization}
                                      entryKey={entry.entry_key}
                                      keywordSuggestion={
                                        entry.description &&
                                        entry.description !== "내용 없음"
                                          ? entry.description
                                          : entry.summary
                                      }
                                      currentCategory={entry.category}
                                      extraCategories={statementCategoryNames}
                                    />
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </section>
                  );
                })}
              </div>
            )}

            {statement.warnings.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                <h2 className="font-semibold">{t("passbook.warnings")}</h2>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {statement.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </>
      )}

      {!isFetching && !isParsing && !errorMessage && !statement && (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white text-sm text-gray-500">
          {t("passbook.noSavedStatements")}
        </div>
      )}
    </div>
  );
}
