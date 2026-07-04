import { koreanName } from "@/lib/instrumentNames";

/**
 * Renders the Korean name for a ticker as faint text, or nothing when there is
 * no mapping. Meant to sit right after an instrument's English name, e.g.
 * `{name} <KoreanName ticker={ticker} />`.
 */
export function KoreanName({
  ticker,
  className = "",
}: {
  ticker: string | null | undefined;
  className?: string;
}) {
  const ko = koreanName(ticker);
  if (!ko) return null;
  return (
    <span className={`font-normal text-gray-400 ${className}`}>{ko}</span>
  );
}
