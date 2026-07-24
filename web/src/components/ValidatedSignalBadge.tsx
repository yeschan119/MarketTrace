"use client";

import { useI18n } from "@/lib/i18n";
import { InfoTip } from "@/components/InfoTip";
import type { SignalVerdict } from "@/lib/validatedSignal";

const styles: Record<SignalVerdict, string> = {
  conflict: "bg-amber-100 text-amber-800 border border-amber-200",
  agree: "bg-emerald-100 text-emerald-800 border border-emerald-200",
  info: "bg-indigo-100 text-indigo-700 border border-indigo-200",
  none: "bg-gray-100 text-gray-500 border border-gray-200",
};

// Compact chip form of a signal verdict, for dense lists.
// `none` (no validated signal) renders nothing to avoid noise.
// Hovering the chip explains what the verdict means.
export function ValidatedSignalBadge({ verdict }: { verdict: SignalVerdict }) {
  const { t } = useI18n();
  if (verdict === "none") return null;
  return (
    <InfoTip text={t(`eventDetail.signal.badge.${verdict}`)}>
      <span
        className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${styles[verdict]}`}
      >
        {t(`eventDetail.signal.short.${verdict}`)}
      </span>
    </InfoTip>
  );
}
