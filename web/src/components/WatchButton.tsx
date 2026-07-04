"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

/**
 * Star toggle to add/remove an instrument from the watchlist. Visible to all,
 * but acting requires login (mutations are auth-gated). When logged out it links
 * to a login hint; when logged in it toggles and invalidates the watchlist +
 * unread-count queries so the header bell and star stay in sync.
 */
export function WatchButton({
  instrumentId,
}: {
  instrumentId: number | string;
}) {
  const { t } = useI18n();
  const { token } = useAuth();
  const qc = useQueryClient();

  const { data: watchlist } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api.listWatchlist(),
  });
  const watching =
    watchlist?.some((w) => String(w.instrument_id) === String(instrumentId)) ??
    false;

  const mutation = useMutation({
    mutationFn: async () => {
      if (!token) return;
      if (watching) await api.removeWatchlist(instrumentId, token);
      else await api.addWatchlist(instrumentId, token);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  if (!token) {
    return (
      <span className="text-xs text-gray-400" title={t("watch.loginToWatch")}>
        ☆ {t("watch.loginToWatch")}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={() => mutation.mutate()}
      disabled={mutation.isPending}
      className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
        watching
          ? "border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100"
          : "border-gray-300 bg-white text-gray-600 hover:bg-gray-50"
      }`}
    >
      <span aria-hidden>{watching ? "★" : "☆"}</span>
      {watching ? t("watch.watching") : t("watch.watch")}
    </button>
  );
}
