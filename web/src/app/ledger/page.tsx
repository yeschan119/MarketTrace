"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { LedgerStatement, LedgerStatementSummary } from "@/types/api";

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

export default function LedgerPage() {
  const { token, logout } = useAuth();
  const { t, locale } = useI18n();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [authNotice, setAuthNotice] = useState("");
  const [validationError, setValidationError] = useState("");

  function toLedgerErrorMessage(err: unknown): string {
    if (isApiError(err) && err.status === 401) {
      const message = t("ledger.sessionExpired");
      setAuthNotice(message);
      logout();
      return message;
    }
    if (isApiError(err) && err.detail === "statement password required") {
      return t("ledger.passwordRequired");
    }
    if (isApiError(err) && err.detail === "invalid statement password") {
      return t("ledger.invalidPassword");
    }
    return err instanceof Error ? err.message : t("common.unknownError");
  }

  const statementSummaries = useQuery({
    queryKey: ["ledger-statements"],
    queryFn: async () => {
      try {
        return await api.listLedgerStatements(token ?? "");
      } catch (err) {
        throw new Error(toLedgerErrorMessage(err));
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
    queryKey: ["ledger-statement", selectedMonth],
    queryFn: async () => {
      if (!selectedMonth) throw new Error(t("ledger.noSavedStatements"));
      try {
        return await api.getLedgerStatementByMonth(token ?? "", selectedMonth);
      } catch (err) {
        throw new Error(toLedgerErrorMessage(err));
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
        return await api.uploadLedgerStatement(
          token ?? "",
          nextFile,
          nextPassword
        );
      } catch (err) {
        throw new Error(toLedgerErrorMessage(err));
      }
    },
    onSuccess: (statement) => {
      const month = statement.statement_month
        ? toMonthValue(statement.statement_month)
        : null;
      if (month) {
        queryClient.setQueryData(["ledger-statement", month], statement);
        setSelectedMonth(month);
      }
      void queryClient.invalidateQueries({ queryKey: ["ledger-statements"] });
    },
  });

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!file) {
      setValidationError(t("ledger.missingFile"));
      return;
    }
    const nextPassword = password.trim();
    if (!nextPassword) {
      setValidationError(t("ledger.passwordRequired"));
      return;
    }
    setAuthNotice("");
    setValidationError("");
    uploadStatement.mutate({ nextFile: file, nextPassword });
  }

  if (!token) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-8 text-sm text-gray-600 shadow-sm">
        {authNotice || t("ledger.loginRequired")}
      </div>
    );
  }

  const summaries: LedgerStatementSummary[] = statementSummaries.data ?? [];
  const selectedMonthUpload =
    uploadStatement.data?.statement_month &&
    toMonthValue(uploadStatement.data.statement_month) === selectedMonth
      ? uploadStatement.data
      : undefined;
  const statement: LedgerStatement | undefined =
    selectedStatement.data ?? selectedMonthUpload;
  const isFetching = selectedStatement.isFetching || statementSummaries.isFetching;
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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {t("ledger.title")}
          </h1>
          <p className="mt-2 text-sm text-gray-500">{t("ledger.subtitle")}</p>
        </div>
        {summaries.length > 0 && (
          <span className="text-sm text-gray-500">
            {t("ledger.savedMonths", { n: summaries.length })}
          </span>
        )}
      </div>

      {summaries.length > 0 && (
        <label className="block max-w-xs">
          <span className="mb-1 block text-sm font-medium text-gray-700">
            {t("ledger.monthLabel")}
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
            {t("ledger.fileLabel")}
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
            {file ? file.name : t("ledger.fileHelp")}
          </span>
        </label>
        <label className="flex-1">
          <span className="mb-1 block text-sm font-medium text-gray-700">
            {t("ledger.passwordLabel")}
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
            placeholder={t("ledger.passwordPlaceholder")}
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
          <span>{isParsing ? t("ledger.parsing") : t("ledger.load")}</span>
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
              ? t("ledger.parsing")
              : selectedMonth
                ? t("ledger.detailLoading")
                : t("ledger.listLoading")}
          </span>
        </div>
      )}

      {errorMessage && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
          <p className="font-semibold">{t("ledger.failTitle")}</p>
          <p className="mt-1 text-sm">{errorMessage}</p>
        </div>
      )}

      {statement && (
        <>
          <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-5">
            <SummaryItem
              label={t("ledger.statementMonth")}
              value={formatMonth(statement.statement_month, locale)}
            />
            <SummaryItem label={t("ledger.file")} value={statement.file_name} />
            <SummaryItem
              label={t("ledger.uploadedAt")}
              value={formatDate(statement.uploaded_at, locale)}
            />
            <SummaryItem
              label={t("ledger.period")}
              value={`${formatDate(statement.period_start, locale)} - ${formatDate(
                statement.period_end,
                locale
              )}`}
            />
            <SummaryItem
              label={t("ledger.paymentDue")}
              value={formatDate(statement.payment_due_date, locale)}
            />
            <SummaryItem
              label={t("ledger.billedTotal")}
              value={formatWon(statement.billed_total, locale)}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <SummaryItem
                  label={t("ledger.parsedTotal")}
                  value={formatWon(statement.parsed_total, locale)}
                />
                <SummaryItem
                  label={t("ledger.foreignTotal")}
                  value={formatWon(statement.foreign_total, locale)}
                />
              </div>

              {statement.entries.length === 0 ? (
                <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500">
                  {t("ledger.empty")}
                </div>
              ) : (
                <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        <th className="px-4 py-3">{t("ledger.th.date")}</th>
                        <th className="px-4 py-3">{t("ledger.th.category")}</th>
                        <th className="px-4 py-3">{t("ledger.th.description")}</th>
                        <th className="px-4 py-3">{t("ledger.th.card")}</th>
                        <th className="px-4 py-3 text-right">
                          {t("ledger.th.amount")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {statement.entries.map((entry, idx) => (
                        <tr
                          key={`${entry.date}-${entry.description}-${entry.amount}-${idx}`}
                          className="border-b border-gray-100 last:border-0 hover:bg-gray-50"
                        >
                          <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                            {formatDate(entry.date, locale)}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3">
                            <span className="rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-600">
                              {entry.category}
                            </span>
                          </td>
                          <td className="max-w-md px-4 py-3 text-gray-900">
                            <span className="block truncate">
                              {entry.description}
                            </span>
                          </td>
                          <td className="px-4 py-3 font-mono text-gray-500">
                            {entry.card_tail ? `***${entry.card_tail}` : "-"}
                          </td>
                          <td className="px-4 py-3 text-right font-mono font-semibold text-gray-900">
                            {formatWon(entry.amount, locale)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <aside className="space-y-4">
              <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                <h2 className="text-sm font-semibold text-gray-900">
                  {t("ledger.categories")}
                </h2>
                <div className="mt-3 space-y-3">
                  {statement.categories.map((category) => (
                    <div
                      key={category.category}
                      className="flex items-center justify-between gap-4 text-sm"
                    >
                      <div>
                        <div className="font-medium text-gray-800">
                          {category.category}
                        </div>
                        <div className="text-xs text-gray-500">
                          {t("ledger.entries", { n: category.count })}
                        </div>
                      </div>
                      <div className="font-mono font-semibold text-gray-900">
                        {formatWon(category.amount, locale)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {statement.warnings.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                  <h2 className="font-semibold">{t("ledger.warnings")}</h2>
                  <ul className="mt-2 list-disc space-y-1 pl-5">
                    {statement.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}
            </aside>
          </div>
        </>
      )}

      {!isFetching && !isParsing && !errorMessage && !statement && (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white text-sm text-gray-500">
          {t("ledger.noSavedStatements")}
        </div>
      )}
    </div>
  );
}
