"use client";

import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import type { CategoryCustomizationController } from "@/lib/useCategoryCustomization";

interface CategoryManagerProps {
  controller: CategoryCustomizationController;
}

/**
 * Collapsible panel for managing saved customizations: create/delete custom
 * categories and review/delete the keyword rules that auto-classify entries.
 */
export function CategoryManager({ controller }: CategoryManagerProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");

  const custom = (controller.data?.available_categories ?? []).filter(
    (c) => c.source === "custom"
  );
  const rules = controller.data?.rules ?? [];

  async function handleCreate() {
    const name = newName.trim();
    if (!name) {
      setError(t("customize.categoryRequired"));
      return;
    }
    setError("");
    try {
      await controller.createCategory(name);
      setNewName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.unknownError"));
    }
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-surface shadow-sm">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left hover:bg-gray-50"
      >
        <span className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="flex h-6 w-6 items-center justify-center rounded-full border border-gray-300 font-mono text-sm font-semibold text-gray-600"
          >
            {open ? "-" : "+"}
          </span>
          <span className="text-sm font-semibold text-gray-900">
            {t("customize.managerTitle")}
          </span>
        </span>
        <span className="text-xs text-gray-500">
          {t("customize.managerSummary", {
            categories: custom.length,
            rules: rules.length,
          })}
        </span>
      </button>

      {open && (
        <div className="space-y-5 border-t border-gray-200 px-4 py-4">
          {/* Create custom category */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
              {t("customize.customCategories")}
            </h3>
            <div className="flex gap-2">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void handleCreate();
                  }
                }}
                placeholder={t("customize.newCategoryPlaceholder")}
                className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <button
                type="button"
                onClick={handleCreate}
                disabled={controller.isMutating}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {t("customize.add")}
              </button>
            </div>
            {error && <p className="mt-1 text-xs text-red-600">{error}</p>}

            {custom.length > 0 ? (
              <ul className="mt-3 flex flex-wrap gap-2">
                {custom.map((category) => (
                  <li
                    key={category.name}
                    className="flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 py-1 pl-3 pr-1.5 text-xs text-indigo-700"
                  >
                    <span>{category.name}</span>
                    <button
                      type="button"
                      aria-label={t("customize.deleteCategory", {
                        name: category.name,
                      })}
                      onClick={() => void controller.deleteCategory(category.name)}
                      disabled={controller.isMutating}
                      className="flex h-4 w-4 items-center justify-center rounded-full text-indigo-500 hover:bg-indigo-200 hover:text-indigo-800 disabled:opacity-50"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-gray-400">
                {t("customize.noCustomCategories")}
              </p>
            )}
          </div>

          {/* Keyword rules */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
              {t("customize.rulesTitle")}
            </h3>
            {rules.length > 0 ? (
              <ul className="space-y-1">
                {rules.map((rule) => (
                  <li
                    key={rule.id}
                    className="flex items-center justify-between gap-3 rounded-md border border-gray-200 px-3 py-1.5 text-sm"
                  >
                    <span className="min-w-0 truncate text-gray-700">
                      <span className="font-mono text-gray-900">
                        {rule.keyword}
                      </span>
                      <span className="mx-2 text-gray-400">→</span>
                      <span className="font-medium text-indigo-700">
                        {rule.category}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => void controller.deleteRule(rule.id)}
                      disabled={controller.isMutating}
                      className="shrink-0 text-xs text-gray-400 underline hover:text-red-600 disabled:opacity-50"
                    >
                      {t("customize.delete")}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-gray-400">{t("customize.noRules")}</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
