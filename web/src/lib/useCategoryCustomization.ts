"use client";

import { useCallback, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  CategoryCustomization,
  CustomizationBase,
} from "@/types/api";

// Query-key prefixes each domain must refresh after a category change, so the
// statement view, category chart, and top-entries all pick up the new mapping.
const REFRESH_KEYS: Record<CustomizationBase, string[]> = {
  "/ledger": ["ledger-statement", "ledger-categories", "ledger-top-entries"],
  "/passbook": [
    "passbook-statement",
    "passbook-categories",
    "passbook-top-entries",
  ],
};

export interface CategoryCustomizationController {
  data: CategoryCustomization | undefined;
  isLoading: boolean;
  isMutating: boolean;
  error: Error | null;
  /** All assignable category names, custom ones first-class alongside built-ins. */
  categoryNames: string[];
  /** entry_key -> overridden category, for quick per-row lookup. */
  overrideByKey: Map<string, string>;
  setOverride: (
    entryKey: string,
    category: string | null,
    description?: string
  ) => Promise<void>;
  createRule: (keyword: string, category: string) => Promise<void>;
  deleteRule: (ruleId: number) => Promise<void>;
  createCategory: (name: string) => Promise<void>;
  deleteCategory: (name: string) => Promise<void>;
}

export function useCategoryCustomization(
  token: string | null,
  base: CustomizationBase
): CategoryCustomizationController {
  const queryClient = useQueryClient();
  const queryKey = useMemo(() => ["category-customization", base], [base]);

  const query = useQuery({
    queryKey,
    queryFn: () => api.getCategoryCustomization(token ?? "", base),
    enabled: Boolean(token),
    retry: false,
  });

  const applyResult = useCallback(
    (next: CategoryCustomization) => {
      queryClient.setQueryData(queryKey, next);
      for (const prefix of REFRESH_KEYS[base]) {
        void queryClient.invalidateQueries({ queryKey: [prefix] });
      }
    },
    [queryClient, queryKey, base]
  );

  const overrideMutation = useMutation({
    mutationFn: ({
      entryKey,
      category,
      description,
    }: {
      entryKey: string;
      category: string | null;
      description?: string;
    }) =>
      api.setCategoryOverride(
        token ?? "",
        base,
        entryKey,
        category,
        description
      ),
    onSuccess: applyResult,
  });

  const ruleMutation = useMutation({
    mutationFn: ({ keyword, category }: { keyword: string; category: string }) =>
      api.createCategoryRule(token ?? "", base, keyword, category),
    onSuccess: applyResult,
  });

  const ruleDeleteMutation = useMutation({
    mutationFn: (ruleId: number) =>
      api.deleteCategoryRule(token ?? "", base, ruleId),
    onSuccess: applyResult,
  });

  const categoryCreateMutation = useMutation({
    mutationFn: (name: string) =>
      api.createCustomCategory(token ?? "", base, name),
    onSuccess: applyResult,
  });

  const categoryDeleteMutation = useMutation({
    mutationFn: (name: string) =>
      api.deleteCustomCategory(token ?? "", base, name),
    onSuccess: applyResult,
  });

  const categoryNames = useMemo(
    () => (query.data?.available_categories ?? []).map((c) => c.name),
    [query.data]
  );

  const overrideByKey = useMemo(() => {
    const map = new Map<string, string>();
    for (const override of query.data?.overrides ?? []) {
      map.set(override.entry_key, override.category);
    }
    return map;
  }, [query.data]);

  const isMutating =
    overrideMutation.isPending ||
    ruleMutation.isPending ||
    ruleDeleteMutation.isPending ||
    categoryCreateMutation.isPending ||
    categoryDeleteMutation.isPending;

  return {
    data: query.data,
    isLoading: query.isLoading,
    isMutating,
    error: query.error instanceof Error ? query.error : null,
    categoryNames,
    overrideByKey,
    setOverride: async (entryKey, category, description) => {
      await overrideMutation.mutateAsync({ entryKey, category, description });
    },
    createRule: async (keyword, category) => {
      await ruleMutation.mutateAsync({ keyword, category });
    },
    deleteRule: async (ruleId) => {
      await ruleDeleteMutation.mutateAsync(ruleId);
    },
    createCategory: async (name) => {
      await categoryCreateMutation.mutateAsync(name);
    },
    deleteCategory: async (name) => {
      await categoryDeleteMutation.mutateAsync(name);
    },
  };
}
