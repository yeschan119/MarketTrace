"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type Lang = "en" | "ko";

const LANG_KEY = "markettrace_lang";

type Dict = { [key: string]: string | Dict };

const en: Dict = {
  nav: { events: "Events", stats: "Stats", macro: "Macro" },
  common: { unknownError: "Unknown error" },
  auth: {
    login: "Login",
    logout: "Logout",
    signInTitle: "Sign in",
    signIn: "Sign in",
    signingIn: "Signing in…",
    cancel: "Cancel",
    username: "Username",
    password: "Password",
    invalidCreds: "Invalid username or password.",
    loginFailed: "Login failed",
  },
  ingest: {
    button: "Ingest data",
    starting: "Starting…",
    ingesting: "Ingesting… (~1–2 min)",
    started: "Ingestion started — data will appear shortly",
    sessionExpired: "Session expired — please log in again.",
    errorPrefix: "Error: ",
    failed: "Ingest failed",
    refresh: "Refresh",
    eventsLoaded: "✓ {n} events loaded",
    inProgress: "Ingestion in progress — refresh to check for new data",
  },
  events: {
    loading: "Loading events...",
    failTitle: "Failed to load events",
    backendHint: "Make sure the backend is running at {url}",
    title: "Market Events",
    count: "{n} events",
    empty: "No events found. Run the pipeline to ingest disclosures.",
    th: {
      ticker: "Ticker",
      instrument: "Instrument",
      eventType: "Event Type",
      direction: "Direction",
      confidence: "Confidence",
      published: "Published",
    },
  },
  stats: {
    loading: "Loading statistics...",
    failTitle: "Failed to load statistics",
    title: "Event-Type Reaction Stats",
    buckets: "{n} buckets",
    subtitle:
      "Mean and dispersion of market-adjusted abnormal returns, grouped by event type and post-announcement horizon (trading days).",
    empty: "No statistics yet — ingest some events first.",
    th: {
      eventType: "Event Type",
      horizon: "Horizon",
      samples: "Samples",
      mean: "Mean Abnormal Return",
      std: "Std Dev",
    },
  },
  eventDetail: {
    loading: "Loading event...",
    failTitle: "Failed to load event",
    unknownInstrument: "Unknown Instrument",
    model: "Model",
    version: "Version",
    sourceDoc: "Source Document",
    evidence: "Supporting Evidence",
    industries: "Industries",
    channels: "Channels",
  },
  instrument: {
    loading: "Loading instrument timeline...",
    failTitle: "Failed to load instrument",
    timeline: "Event Timeline",
    eventsCount: "({n} events)",
    empty: "No events recorded for this instrument.",
    conf: "conf",
  },
  direction: { positive: "positive", negative: "negative", neutral: "neutral" },
  chart: {
    title: "Abnormal Returns (%)",
    noData: "No outcome data available",
    abnormalReturn: "Abnormal Return",
    rawReturn: "Raw Return",
    sectorAdjusted: "Sector-Adjusted",
    marketReturn: "Market Return",
    abnormal: "Abnormal",
    raw: "Raw",
    market: "Market",
  },
  scores: {
    title: "Score Components",
    confidence: "Confidence",
    surprise: "Surprise",
    novelty: "Novelty",
    sourceReliability: "Source Reliability",
  },
  macro: {
    title: "Macro Surprises",
    count: "{n} series",
    loading: "Loading macro data...",
    failTitle: "Failed to load macro data",
    subtitle:
      "Latest economic release per series with its standardized surprise vs the expected value (consensus when available, else a baseline forecast).",
    empty: "No macro data yet — run the macro ingest first.",
    th: {
      series: "Series",
      reference: "Reference",
      released: "Released",
      expected: "Expected",
      surprise: "Surprise (σ)",
    },
    baseline: "baseline",
    consensus: "consensus",
  },
};

const ko: Dict = {
  nav: { events: "이벤트", stats: "통계", macro: "거시" },
  common: { unknownError: "알 수 없는 오류" },
  auth: {
    login: "로그인",
    logout: "로그아웃",
    signInTitle: "로그인",
    signIn: "로그인",
    signingIn: "로그인 중…",
    cancel: "취소",
    username: "아이디",
    password: "비밀번호",
    invalidCreds: "아이디 또는 비밀번호가 올바르지 않습니다.",
    loginFailed: "로그인 실패",
  },
  ingest: {
    button: "데이터 수집",
    starting: "시작 중…",
    ingesting: "수집 중… (~1–2분)",
    started: "수집을 시작했습니다 — 곧 데이터가 표시됩니다",
    sessionExpired: "세션이 만료되었습니다 — 다시 로그인해 주세요.",
    errorPrefix: "오류: ",
    failed: "수집 실패",
    refresh: "새로고침",
    eventsLoaded: "✓ 이벤트 {n}건 로드됨",
    inProgress: "수집 진행 중 — 새로고침해 새 데이터를 확인하세요",
  },
  events: {
    loading: "이벤트 불러오는 중...",
    failTitle: "이벤트를 불러오지 못했습니다",
    backendHint: "백엔드가 {url} 에서 실행 중인지 확인하세요",
    title: "마켓 이벤트",
    count: "이벤트 {n}건",
    empty: "이벤트가 없습니다. 파이프라인을 실행해 공시를 수집하세요.",
    th: {
      ticker: "티커",
      instrument: "종목",
      eventType: "이벤트 유형",
      direction: "방향",
      confidence: "신뢰도",
      published: "공시일",
    },
  },
  stats: {
    loading: "통계 불러오는 중...",
    failTitle: "통계를 불러오지 못했습니다",
    title: "이벤트 유형별 반응 통계",
    buckets: "버킷 {n}개",
    subtitle:
      "이벤트 유형과 공시 후 기간(거래일)별로 묶은 시장조정 초과수익률의 평균과 분산.",
    empty: "아직 통계가 없습니다 — 먼저 이벤트를 수집하세요.",
    th: {
      eventType: "이벤트 유형",
      horizon: "기간",
      samples: "표본 수",
      mean: "평균 초과수익률",
      std: "표준편차",
    },
  },
  eventDetail: {
    loading: "이벤트 불러오는 중...",
    failTitle: "이벤트를 불러오지 못했습니다",
    unknownInstrument: "알 수 없는 종목",
    model: "모델",
    version: "버전",
    sourceDoc: "원본 문서",
    evidence: "근거",
    industries: "산업",
    channels: "채널",
  },
  instrument: {
    loading: "종목 타임라인 불러오는 중...",
    failTitle: "종목을 불러오지 못했습니다",
    timeline: "이벤트 타임라인",
    eventsCount: "(이벤트 {n}건)",
    empty: "이 종목에 기록된 이벤트가 없습니다.",
    conf: "신뢰도",
  },
  direction: { positive: "긍정", negative: "부정", neutral: "중립" },
  chart: {
    title: "초과수익률 (%)",
    noData: "수익률 데이터가 없습니다",
    abnormalReturn: "초과수익률",
    rawReturn: "원수익률",
    sectorAdjusted: "섹터조정",
    marketReturn: "시장수익률",
    abnormal: "초과",
    raw: "원",
    market: "시장",
  },
  scores: {
    title: "점수 구성",
    confidence: "신뢰도",
    surprise: "서프라이즈",
    novelty: "신규성",
    sourceReliability: "출처 신뢰도",
  },
  macro: {
    title: "거시 서프라이즈",
    count: "{n}개 시리즈",
    loading: "거시 지표 불러오는 중...",
    failTitle: "거시 지표를 불러오지 못했습니다",
    subtitle:
      "시리즈별 최신 경제지표 발표값과 예상 대비 표준화 서프라이즈(컨센서스가 있으면 컨센서스, 없으면 기준선 예측).",
    empty: "아직 거시 데이터가 없습니다 — 먼저 거시 수집을 실행하세요.",
    th: {
      series: "시리즈",
      reference: "기준일",
      released: "발표값",
      expected: "예상값",
      surprise: "서프라이즈 (σ)",
    },
    baseline: "기준선",
    consensus: "컨센서스",
  },
};

const dicts: Record<Lang, Dict> = { en, ko };
const locales: Record<Lang, string> = { en: "en-US", ko: "ko-KR" };

function lookup(dict: Dict, key: string): string {
  const value = key.split(".").reduce<string | Dict | undefined>(
    (acc, part) => (acc && typeof acc === "object" ? acc[part] : undefined),
    dict
  );
  return typeof value === "string" ? value : key;
}

interface I18nContextValue {
  lang: Lang;
  locale: string;
  setLang: (lang: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  // Default to English to match the server-rendered markup; the stored choice
  // is applied after mount (same pattern as AuthProvider) to avoid hydration
  // mismatches.
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem(LANG_KEY);
    if (stored === "en" || stored === "ko") setLangState(stored);
  }, []);

  useEffect(() => {
    if (typeof document !== "undefined") document.documentElement.lang = lang;
  }, [lang]);

  function setLang(next: Lang): void {
    setLangState(next);
    if (typeof window !== "undefined") localStorage.setItem(LANG_KEY, next);
  }

  function t(key: string, vars?: Record<string, string | number>): string {
    let str = lookup(dicts[lang], key);
    if (vars) {
      for (const [name, value] of Object.entries(vars)) {
        str = str.replace(`{${name}}`, String(value));
      }
    }
    return str;
  }

  return (
    <I18nContext.Provider value={{ lang, locale: locales[lang], setLang, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within <I18nProvider>");
  return ctx;
}

/** Segmented EN | 한국어 control used in the site header. */
export function LanguageToggle() {
  const { lang, setLang } = useI18n();
  const options: { value: Lang; label: string }[] = [
    { value: "en", label: "EN" },
    { value: "ko", label: "한국어" },
  ];
  return (
    <div
      role="group"
      aria-label="Language"
      className="inline-flex rounded-md border border-gray-200 bg-gray-50 p-0.5 text-xs font-medium"
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => setLang(opt.value)}
          aria-pressed={lang === opt.value}
          className={`rounded px-2.5 py-1 transition-colors ${
            lang === opt.value
              ? "bg-white text-indigo-600 shadow-sm"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
