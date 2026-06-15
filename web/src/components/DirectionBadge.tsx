"use client";

import { useI18n } from "@/lib/i18n";

interface Props {
  direction: string;
}

const directionStyles: Record<string, string> = {
  positive:
    "bg-emerald-100 text-emerald-800 border border-emerald-200",
  negative:
    "bg-red-100 text-red-800 border border-red-200",
  neutral:
    "bg-gray-100 text-gray-700 border border-gray-200",
};

export function DirectionBadge({ direction }: Props) {
  const { t } = useI18n();
  const key = direction.toLowerCase();
  const style =
    directionStyles[key] ?? "bg-gray-100 text-gray-700 border border-gray-200";
  const label = ["positive", "negative", "neutral"].includes(key)
    ? t(`direction.${key}`)
    : direction;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${style}`}
    >
      {label}
    </span>
  );
}
