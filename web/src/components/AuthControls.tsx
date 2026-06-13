"use client";

import { useState, useRef, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EventSummary } from "@/types/api";

type IngestState = "idle" | "loading" | "polling" | "done";

const POLL_INTERVAL_MS = 10_000;
const POLL_MAX_TICKS = 15; // 15 × 10s = 2.5 min

export function AuthControls() {
  const { token, login, logout } = useAuth();
  const queryClient = useQueryClient();

  // ── Login modal state ──────────────────────────────────────────────────────
  const [showModal, setShowModal] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

  // ── Ingest state ───────────────────────────────────────────────────────────
  const [ingestState, setIngestState] = useState<IngestState>("idle");
  const [ingestMessage, setIngestMessage] = useState("");
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCountRef = useRef(0);
  const initialCountRef = useRef(0);

  // Clear poll interval when component unmounts
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  // ── Login handlers ─────────────────────────────────────────────────────────
  function openModal() {
    setLoginError("");
    setUsername("");
    setPassword("");
    setShowModal(true);
  }

  function closeModal() {
    setShowModal(false);
    setLoginError("");
  }

  async function handleLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoginError("");
    setLoginLoading(true);
    try {
      await login(username, password);
      closeModal();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Login failed";
      setLoginError(
        msg.includes("401") ? "Invalid username or password." : msg
      );
    } finally {
      setLoginLoading(false);
    }
  }

  // ── Ingest handlers ────────────────────────────────────────────────────────
  async function handleIngest() {
    if (!token) return;

    setIngestState("loading");
    setIngestMessage("");

    try {
      await api.ingest(token);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Ingest failed";
      if (msg.includes("401")) {
        logout();
        setIngestMessage("Session expired — please log in again.");
      } else {
        setIngestMessage(`Error: ${msg}`);
      }
      setIngestState("idle");
      return;
    }

    // Snapshot current event count so we can detect new data
    const cached = queryClient.getQueryData<EventSummary[]>(["events"]);
    initialCountRef.current = Array.isArray(cached) ? cached.length : 0;
    pollCountRef.current = 0;

    setIngestState("polling");
    setIngestMessage("Ingestion started — data will appear shortly");

    pollIntervalRef.current = setInterval(() => {
      pollCountRef.current += 1;

      // Check if the cache already has more events than when we started
      const current = queryClient.getQueryData<EventSummary[]>(["events"]);
      const currentCount = Array.isArray(current) ? current.length : 0;
      const hasNewData = currentCount > initialCountRef.current;
      const timedOut = pollCountRef.current >= POLL_MAX_TICKS;

      if (hasNewData || timedOut) {
        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
        setIngestState("done");
        setIngestMessage(
          hasNewData
            ? `✓ ${currentCount} events loaded`
            : "Ingestion in progress — refresh to check for new data"
        );
      } else {
        // Trigger a background refetch of the events list
        void queryClient.invalidateQueries({ queryKey: ["events"] });
      }
    }, POLL_INTERVAL_MS);
  }

  function handleRefresh() {
    void queryClient.invalidateQueries({ queryKey: ["events"] });
  }

  // ── Logged-out view ────────────────────────────────────────────────────────
  if (!token) {
    return (
      <>
        <button
          onClick={openModal}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        >
          Login
        </button>

        {showModal && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="login-title"
            className="fixed inset-0 z-50 flex items-center justify-center"
          >
            {/* Backdrop */}
            <div
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={closeModal}
              aria-hidden="true"
            />

            {/* Card */}
            <div className="relative z-10 w-full max-w-sm rounded-xl bg-white p-8 shadow-2xl">
              <h2
                id="login-title"
                className="mb-6 text-xl font-bold text-gray-900"
              >
                Sign in
              </h2>

              <form onSubmit={handleLogin} className="space-y-4">
                <div>
                  <label
                    htmlFor="mt-username"
                    className="mb-1 block text-sm font-medium text-gray-700"
                  >
                    Username
                  </label>
                  <input
                    id="mt-username"
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    autoFocus
                    autoComplete="username"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                  />
                </div>

                <div>
                  <label
                    htmlFor="mt-password"
                    className="mb-1 block text-sm font-medium text-gray-700"
                  >
                    Password
                  </label>
                  <input
                    id="mt-password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                  />
                </div>

                {loginError && (
                  <p
                    role="alert"
                    className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600"
                  >
                    {loginError}
                  </p>
                )}

                <div className="flex gap-3 pt-1">
                  <button
                    type="submit"
                    disabled={loginLoading}
                    className="flex-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
                  >
                    {loginLoading ? "Signing in…" : "Sign in"}
                  </button>
                  <button
                    type="button"
                    onClick={closeModal}
                    className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </>
    );
  }

  // ── Logged-in view ─────────────────────────────────────────────────────────
  return (
    <div className="flex items-center gap-3">
      {ingestMessage && (
        <span className="max-w-xs truncate text-xs text-gray-500">
          {ingestMessage}
        </span>
      )}

      {(ingestState === "polling" || ingestState === "done") && (
        <button
          onClick={handleRefresh}
          className="text-xs text-indigo-500 underline hover:text-indigo-700"
        >
          Refresh
        </button>
      )}

      <button
        onClick={handleIngest}
        disabled={ingestState === "loading" || ingestState === "polling"}
        className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
      >
        {ingestState === "loading"
          ? "Starting…"
          : ingestState === "polling"
            ? "Ingesting… (~1–2 min)"
            : "Ingest data"}
      </button>

      <button
        onClick={logout}
        className="rounded-md border border-gray-200 px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
      >
        Logout
      </button>
    </div>
  );
}
