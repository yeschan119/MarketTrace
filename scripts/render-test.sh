#!/usr/bin/env bash
# render-test.sh — smoke-test the DEPLOYED MarketTrace services on Render, end to end.
#
# Hits the live backend + frontend and checks each contract against real data,
# so you can confirm a deploy actually works without opening the Render shell.
#
# Usage:
#   scripts/render-test.sh [API_BASE] [WEB_BASE]
# Defaults to production (api.miffy178.com / miffy178.com). Pass a preview URL to
# test a staging/PR deploy instead, e.g.
#   scripts/render-test.sh https://markettrace-backend-pr-12.onrender.com
#
# Render free tier spins services down when idle; the first request cold-starts
# (can take ~50s), so we warm up with a long timeout + retries before testing.
#
# Exit code: 0 if every check passes, 1 otherwise.

set -uo pipefail

API_BASE="${1:-https://api.miffy178.com}"
WEB_BASE="${2:-https://miffy178.com}"

# ---- output helpers -------------------------------------------------------
if [ -t 1 ]; then
  G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; DIM=$'\033[2m'; Z=$'\033[0m'
else
  G=""; R=""; Y=""; DIM=""; Z=""
fi
PASS=0
FAIL=0
pass() { PASS=$((PASS + 1)); printf "  ${G}✓${Z} %s\n" "$1"; }
fail() { FAIL=$((FAIL + 1)); printf "  ${R}✗${Z} %s${DIM}%s${Z}\n" "$1" "${2:+  — $2}"; }
info() { printf "  ${DIM}%s${Z}\n" "$1"; }

# curl_status <url>  -> prints HTTP status code (000 on connection failure)
curl_status() { curl -s -o /dev/null -w "%{http_code}" --max-time 30 "$1"; }
# curl_status_follow <url> -> status AFTER following redirects (home pages 30x -> locale)
curl_status_follow() { curl -sL -o /dev/null -w "%{http_code}" --max-time 30 "$1"; }
# curl_body <url>    -> prints response body (empty on failure)
curl_body() { curl -s --max-time 30 "$1"; }

need_jq=1
command -v jq >/dev/null 2>&1 || { need_jq=0; printf "${Y}! jq not found — JSON assertions will be skipped${Z}\n"; }

printf "\n${DIM}MarketTrace · Render smoke test${Z}\n"
printf "  API: %s\n  WEB: %s\n\n" "$API_BASE" "$WEB_BASE"

# ---- warmup (cold-start tolerant) -----------------------------------------
printf "Warming up backend (Render free tier cold-starts)...\n"
warm=0
for attempt in 1 2 3 4 5; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 90 "$API_BASE/health")
  if [ "$code" = "200" ]; then warm=1; break; fi
  info "attempt $attempt: /health -> $code, retrying..."
  sleep 3
done
if [ "$warm" = "1" ]; then pass "backend awake (/health 200)"; else fail "backend did not wake" "/health never returned 200"; fi

# ---- backend contract checks ----------------------------------------------
printf "\nBackend (%s)\n" "$API_BASE"

# /events — must be a non-empty array
body=$(curl_body "$API_BASE/events")
if [ "$need_jq" = "1" ]; then
  n=$(printf '%s' "$body" | jq 'if type=="array" then length else -1 end' 2>/dev/null || echo -1)
  if [ "${n:-ethod}" -gt 0 ] 2>/dev/null; then pass "/events returns $n events"; else fail "/events" "expected non-empty array, got $n"; fi
else
  [ -n "$body" ] && pass "/events responded" || fail "/events" "empty body"
fi

# /stats/event-types — non-empty
n=$(curl_body "$API_BASE/stats/event-types" | jq 'if type=="array" then length else -1 end' 2>/dev/null || echo -1)
if [ "$need_jq" = "1" ]; then
  [ "${n:-0}" -gt 0 ] 2>/dev/null && pass "/stats/event-types: $n buckets" || fail "/stats/event-types" "empty/invalid"
fi

# /stats/significance — array; report how many are validated signals
if [ "$need_jq" = "1" ]; then
  sig=$(curl_body "$API_BASE/stats/significance")
  total=$(printf '%s' "$sig" | jq 'if type=="array" then length else -1 end' 2>/dev/null || echo -1)
  nsig=$(printf '%s' "$sig" | jq '[.[]|select(.significant_5pct==true and .sufficient_sample==true)]|length' 2>/dev/null || echo -1)
  if [ "${total:-0}" -gt 0 ] 2>/dev/null; then
    pass "/stats/significance: $total buckets, ${nsig} validated (p<0.05, n≥5)"
  else
    fail "/stats/significance" "expected array, got $total"
  fi
fi

# /stats/backtest — event_type_history: array with a 5-day row
if [ "$need_jq" = "1" ]; then
  bt=$(curl_body "$API_BASE/stats/backtest?model=event_type_history")
  net5=$(printf '%s' "$bt" | jq -r '.[]|select(.horizon_days==5)|.mean_strategy_return_net' 2>/dev/null || echo "")
  if [ -n "$net5" ] && [ "$net5" != "null" ]; then
    pass "/stats/backtest event_type_history: 5d net=$net5"
  else
    fail "/stats/backtest?model=event_type_history" "no 5d row"
  fi
fi

# /stats/backtest — llm_direction responds
code=$(curl_status "$API_BASE/stats/backtest?model=llm_direction")
[ "$code" = "200" ] && pass "/stats/backtest?model=llm_direction -> 200" || fail "/stats/backtest?model=llm_direction" "HTTP $code"

# /stats/backtest — unknown model must be rejected (contract: 400)
code=$(curl_status "$API_BASE/stats/backtest?model=__nope__")
[ "$code" = "400" ] && pass "/stats/backtest rejects unknown model (400)" || fail "unknown-model rejection" "expected 400, got $code"

# /macro/observations — non-empty
if [ "$need_jq" = "1" ]; then
  n=$(curl_body "$API_BASE/macro/observations" | jq 'if type=="array" then length else -1 end' 2>/dev/null || echo -1)
  [ "${n:-0}" -gt 0 ] 2>/dev/null && pass "/macro/observations: $n rows" || fail "/macro/observations" "empty/invalid ($n)"
fi

# ---- frontend checks ------------------------------------------------------
printf "\nFrontend (%s)\n" "$WEB_BASE"
code=$(curl_status_follow "$WEB_BASE/")
[ "$code" = "200" ] && pass "/ (home) serves 200" || fail "/ (home)" "HTTP $code after redirects"
code=$(curl_status_follow "$WEB_BASE/stats")
[ "$code" = "200" ] && pass "/stats serves 200" || fail "/stats" "HTTP $code after redirects"

# ---- summary --------------------------------------------------------------
printf "\n${DIM}────────────────────────────${Z}\n"
if [ "$FAIL" -eq 0 ]; then
  printf "${G}ALL PASS${Z}  (%d checks)\n\n" "$PASS"
  exit 0
else
  printf "${R}%d FAILED${Z}, %d passed\n\n" "$FAIL" "$PASS"
  exit 1
fi
