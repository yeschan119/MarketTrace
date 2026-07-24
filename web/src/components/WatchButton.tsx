"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api";
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
  compact = false,
}: {
  instrumentId: number | string;
  compact?: boolean;
}) {
  const { t } = useI18n();
  const { token, logout } = useAuth();
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
    onError: (err) => {
      // A stale/expired token (12h TTL) 401s silently. Clear it so the UI
      // reverts to the login prompt instead of a dead star.
      if (isApiError(err) && err.status === 401) {
        logout();
      }
    },
  });

  const sessionExpired =
    isApiError(mutation.error) && mutation.error.status === 401;

  if (!token) {
    const hint = sessionExpired
      ? t("watch.sessionExpired")
      : t("watch.loginToWatch");
    if (compact) {
      // Just a dim star with a login hint tooltip; keeps the list row tidy.
      return (
        <span
          className={`text-lg ${sessionExpired ? "text-red-400" : "text-gray-300"}`}
          title={hint}
          aria-label={hint}
        >
          ☆
        </span>
      );
    }
    return (
      <span
        className={`text-xs ${sessionExpired ? "text-red-500" : "text-gray-400"}`}
        title={hint}
      >
        ☆ {hint}
      </span>
    );
  }

  if (compact) {
    return (
      <button
        type="button"
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
        title={watching ? t("watch.watching") : t("watch.watch")}
        aria-label={watching ? t("watch.watching") : t("watch.watch")}
        className={`text-lg transition-colors disabled:opacity-50 ${
          watching ? "text-amber-500 hover:text-amber-600" : "text-gray-300 hover:text-amber-400"
        }`}
      >
        {watching ? "★" : "☆"}
      </button>
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
          : "border-gray-300 bg-surface text-gray-600 hover:bg-gray-50"
      }`}
    >
      <span aria-hidden>{watching ? "★" : "☆"}</span>
      {watching ? t("watch.watching") : t("watch.watch")}
    </button>
  );
}
