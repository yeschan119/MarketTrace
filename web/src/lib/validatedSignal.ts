import type { EventTypeSignificance } from "@/types/api";

// A single verdict comparing the model's directional read against the
// statistically validated historical drift for the same event type.
//   conflict — model and validated history point opposite ways
//   agree    — model and validated history point the same way
//   info     — model is neutral; validated history has a direction
//   none     — no statistically significant validated signal for this type
export type SignalVerdict = "conflict" | "agree" | "info" | "none";

export type AxisDir = "up" | "down";

// Sign of the validated mean abnormal return → market-relative direction.
export function histDir(mean: number | null): AxisDir | null {
  if (mean == null || mean === 0) return null;
  return mean > 0 ? "up" : "down";
}

// LLM direction → the same up/down axis (neutral has no axis).
export function llmDir(direction: string): AxisDir | null {
  const k = direction.toLowerCase();
  if (k === "positive") return "up";
  if (k === "negative") return "down";
  return null;
}

export interface SignalAssessment {
  verdict: SignalVerdict;
  // Validated significant rows for this event type, ordered by horizon.
  rows: EventTypeSignificance[];
  // The row the verdict is based on (horizon match, else lowest p-value).
  headline: EventTypeSignificance | null;
  histDirection: AxisDir | null;
}

// Reduce the significance table + an event's read into a single verdict.
// When `horizonDays` is given, the event's own horizon is preferred as the
// headline; otherwise the most significant (lowest p) row is used.
export function assessSignal(
  significance: EventTypeSignificance[],
  eventType: string,
  direction: string,
  horizonDays?: number,
): SignalAssessment {
  const rows = significance
    .filter(
      (r) =>
        r.event_type === eventType &&
        r.significant_5pct &&
        r.sufficient_sample,
    )
    .sort((a, b) => a.horizon_days - b.horizon_days);

  const headline =
    (horizonDays != null
      ? rows.find((r) => r.horizon_days === horizonDays)
      : undefined) ??
    [...rows].sort((a, b) => (a.p_value ?? 1) - (b.p_value ?? 1))[0] ??
    null;

  const hd = histDir(headline?.mean_abnormal_return ?? null);
  const ld = llmDir(direction);

  let verdict: SignalVerdict;
  if (!headline || hd == null) {
    verdict = "none";
  } else if (ld == null) {
    verdict = "info";
  } else {
    verdict = ld === hd ? "agree" : "conflict";
  }

  return { verdict, rows, headline, histDirection: hd };
}
