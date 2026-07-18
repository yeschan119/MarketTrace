"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import type { CategoryCustomizationController } from "@/lib/useCategoryCustomization";

const NEW_CATEGORY_VALUE = "__new__";

interface CategoryEditControlProps {
  controller: CategoryCustomizationController;
  entryKey: string;
  /** Merchant / 적요 text used to prefill the keyword when creating a rule. */
  keywordSuggestion: string;
  currentCategory: string;
  /** Categories present in the current statement but maybe not in the catalog. */
  extraCategories?: string[];
  disabled?: boolean;
}

export function CategoryEditControl({
  controller,
  entryKey,
  keywordSuggestion,
  currentCategory,
  extraCategories = [],
  disabled = false,
}: CategoryEditControlProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"single" | "rule">("single");
  const [selected, setSelected] = useState(currentCategory);
  const [newCategory, setNewCategory] = useState("");
  const [keyword, setKeyword] = useState(keywordSuggestion);
  const [error, setError] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  const isOverridden = controller.overrideByKey.has(entryKey);

  const options = useMemo(() => {
    const names = new Set<string>([
      ...controller.categoryNames,
      ...extraCategories,
      currentCategory,
    ]);
    return Array.from(names).filter(Boolean).sort((a, b) => a.localeCompare(b));
  }, [controller.categoryNames, extraCategories, currentCategory]);

  useEffect(() => {
    if (!open) return;
    setMode("single");
    setSelected(currentCategory);
    setNewCategory("");
    setKeyword(keywordSuggestion);
    setError("");
  }, [open, currentCategory, keywordSuggestion]);

  useEffect(() => {
    if (!open) return;
    function onClick(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  function resolveCategory(): string {
    if (selected === NEW_CATEGORY_VALUE) return newCategory.trim();
    return selected;
  }

  async function handleApply() {
    const category = resolveCategory();
    if (!category) {
      setError(t("customize.categoryRequired"));
      return;
    }
    try {
      if (mode === "rule") {
        const cleanedKeyword = keyword.trim();
        if (!cleanedKeyword) {
          setError(t("customize.keywordRequired"));
          return;
        }
        await controller.createRule(cleanedKeyword, category);
      } else {
        await controller.setOverride(entryKey, category, keywordSuggestion);
      }
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.unknownError"));
    }
  }

  async function handleClear() {
    setError("");
    try {
      await controller.setOverride(entryKey, null);
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.unknownError"));
    }
  }

  return (
    <div ref={rootRef} className="relative inline-block text-left">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className={`rounded-md border px-2 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
          isOverridden
            ? "border-indigo-300 bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
            : "border-gray-300 bg-white text-gray-600 hover:bg-gray-50"
        }`}
      >
        {isOverridden ? t("customize.edited") : t("customize.edit")}
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-2 w-72 rounded-lg border border-gray-200 bg-white p-3 shadow-lg">
          <div className="mb-2 text-xs font-semibold text-gray-700">
            {t("customize.reassignTitle")}
          </div>

          <label className="mb-1 block text-xs text-gray-500">
            {t("customize.categoryLabel")}
          </label>
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="mb-2 w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            {options.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
            <option value={NEW_CATEGORY_VALUE}>
              {t("customize.newCategoryOption")}
            </option>
          </select>

          {selected === NEW_CATEGORY_VALUE && (
            <input
              type="text"
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              placeholder={t("customize.newCategoryPlaceholder")}
              className="mb-2 w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          )}

          <div className="mb-2 space-y-1">
            <label className="flex items-center gap-2 text-xs text-gray-600">
              <input
                type="radio"
                name={`scope-${entryKey}`}
                checked={mode === "single"}
                onChange={() => setMode("single")}
              />
              {t("customize.scopeSingle")}
            </label>
            <label className="flex items-center gap-2 text-xs text-gray-600">
              <input
                type="radio"
                name={`scope-${entryKey}`}
                checked={mode === "rule"}
                onChange={() => setMode("rule")}
              />
              {t("customize.scopeRule")}
            </label>
          </div>

          {mode === "rule" && (
            <div className="mb-2">
              <label className="mb-1 block text-xs text-gray-500">
                {t("customize.keywordLabel")}
              </label>
              <input
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <p className="mt-1 text-[11px] leading-tight text-gray-400">
                {t("customize.ruleHint")}
              </p>
            </div>
          )}

          {error && <p className="mb-2 text-xs text-red-600">{error}</p>}

          <div className="flex items-center justify-between gap-2">
            {isOverridden ? (
              <button
                type="button"
                onClick={handleClear}
                disabled={controller.isMutating}
                className="text-xs text-gray-500 underline hover:text-gray-700 disabled:opacity-50"
              >
                {t("customize.revert")}
              </button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50"
              >
                {t("customize.cancel")}
              </button>
              <button
                type="button"
                onClick={handleApply}
                disabled={controller.isMutating}
                className="rounded-md bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {t("customize.apply")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
