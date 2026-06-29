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
  nav: {
    events: "Events",
    stats: "Stats",
    macro: "Macro",
    ledger: "Ledger",
    passbook: "Passbook",
  },
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
  ledger: {
    title: "Card Ledger",
    subtitle: "Upload a password-protected card statement PDF to organize spend entries.",
    loginRequired: "Sign in to view the ledger.",
    fileLabel: "Statement PDF",
    fileHelp: "Select a PDF statement",
    missingFile: "Select a statement PDF first.",
    passwordLabel: "Statement password",
    passwordPlaceholder: "Enter PDF password",
    passwordRequired: "Enter the statement password.",
    invalidPassword: "The statement password is incorrect.",
    load: "Upload and parse",
    loading: "Loading ledger...",
    parsing: "Uploading and parsing statement...",
    failTitle: "Failed to load ledger",
    sessionExpired: "Session expired. Please sign in again, then upload the statement.",
    monthLabel: "Statement month",
    savedMonths: "{n} saved months",
    listLoading: "Loading saved months...",
    detailLoading: "Loading selected statement...",
    noSavedStatements: "No saved statements yet.",
    file: "File",
    uploadedAt: "Uploaded",
    statementMonth: "Statement month",
    period: "Period",
    paymentDue: "Payment due",
    billedTotal: "Billed total",
    foreignTotal: "Foreign total",
    parsedTotal: "Parsed total",
    entries: "{n} entries",
    warnings: "Warnings",
    categories: "Category totals",
    th: {
      date: "Date",
      category: "Category",
      description: "Merchant",
      card: "Card",
      amount: "Amount",
    },
    empty: "No parsed ledger entries.",
    chartTitle: "Top spending categories",
    chartSubtitle: "Top 10 categories by amount",
    windowMonth: "This month",
    windowYear: "Last 12 months",
    chartLoading: "Loading category totals...",
    chartEmpty: "No category totals to chart yet.",
    chartAmount: "Amount",
    topTitle: "Biggest spends",
    topSubtitle: "Top 10 transactions by amount (date + place)",
    topEmpty: "No transactions to rank yet.",
  },
  passbook: {
    title: "Bank Passbook",
    subtitle: "Upload a password-protected bank-account PDF to organize transactions.",
    loginRequired: "Sign in to view the passbook.",
    fileLabel: "Passbook PDF",
    fileHelp: "Select a PDF transaction export",
    missingFile: "Select a passbook PDF first.",
    passwordLabel: "PDF password",
    passwordPlaceholder: "Enter PDF password",
    passwordRequired: "Enter the PDF password.",
    invalidPassword: "The PDF password is incorrect.",
    load: "Upload and parse",
    parsing: "Uploading and parsing passbook...",
    failTitle: "Failed to load passbook",
    sessionExpired: "Session expired. Please sign in again, then upload the passbook.",
    monthLabel: "Statement month",
    savedMonths: "{n} saved months",
    listLoading: "Loading saved months...",
    detailLoading: "Loading selected statement...",
    noSavedStatements: "No saved statements yet.",
    file: "File",
    uploadedAt: "Uploaded",
    statementMonth: "Statement month",
    account: "Account",
    holder: "Holder",
    period: "Period",
    closingBalance: "Closing balance",
    withdrawalTotal: "Total out",
    depositTotal: "Total in",
    entries: "{n} transactions",
    warnings: "Warnings",
    th: {
      date: "Date",
      time: "Time",
      summary: "Type",
      description: "Counterparty",
      withdrawal: "Out",
      deposit: "In",
      balance: "Balance",
      branch: "Branch",
    },
    empty: "No parsed transactions.",
    chartTitle: "Top categories",
    chartSubtitle: "Top 10 categories by amount",
    windowMonth: "This month",
    windowYear: "Last 12 months",
    directionOut: "Withdrawals",
    directionIn: "Deposits",
    chartLoading: "Loading category totals...",
    chartEmpty: "No category totals to chart yet.",
    chartAmount: "Amount",
    topTitleOut: "Biggest withdrawals",
    topTitleIn: "Biggest deposits",
    topSubtitle: "Top 10 transactions by amount (date + counterparty)",
    topEmpty: "No transactions to rank yet.",
  },
};

const ko: Dict = {
  nav: {
    events: "이벤트",
    stats: "통계",
    macro: "거시",
    ledger: "가계부",
    passbook: "통장관리",
  },
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
  ledger: {
    title: "가계부",
    subtitle: "카드 명세서 PDF를 업로드해 지출 내역으로 정리합니다.",
    loginRequired: "가계부를 보려면 로그인하세요.",
    fileLabel: "명세서 PDF",
    fileHelp: "PDF 명세서를 선택하세요",
    missingFile: "먼저 명세서 PDF를 선택하세요.",
    passwordLabel: "명세서 비밀번호",
    passwordPlaceholder: "PDF 비밀번호 입력",
    passwordRequired: "명세서 비밀번호를 입력하세요.",
    invalidPassword: "명세서 비밀번호가 올바르지 않습니다.",
    load: "업로드 후 파싱",
    loading: "가계부 불러오는 중...",
    parsing: "명세서 업로드 및 파싱 중...",
    failTitle: "가계부를 불러오지 못했습니다",
    sessionExpired: "세션이 만료되었습니다. 다시 로그인한 뒤 명세서를 업로드해 주세요.",
    monthLabel: "명세월",
    savedMonths: "저장된 월 {n}개",
    listLoading: "저장된 월 불러오는 중...",
    detailLoading: "선택한 명세서 불러오는 중...",
    noSavedStatements: "저장된 명세서가 없습니다.",
    file: "파일",
    uploadedAt: "업로드일",
    statementMonth: "명세월",
    period: "이용기간",
    paymentDue: "결제일",
    billedTotal: "청구금액",
    foreignTotal: "해외 청구",
    parsedTotal: "파싱 거래합계",
    entries: "거래 {n}건",
    warnings: "확인 필요",
    categories: "카테고리 합계",
    th: {
      date: "일자",
      category: "분류",
      description: "사용처",
      card: "카드",
      amount: "금액",
    },
    empty: "파싱된 거래 내역이 없습니다.",
    chartTitle: "카드값 순위",
    chartSubtitle: "금액 기준 상위 10개 카테고리",
    windowMonth: "이번 달",
    windowYear: "최근 1년",
    chartLoading: "카테고리 합계 불러오는 중...",
    chartEmpty: "그래프로 표시할 카테고리 합계가 없습니다.",
    chartAmount: "금액",
    topTitle: "최다 지출 내역",
    topSubtitle: "금액 기준 상위 10건 (날짜 + 사용처)",
    topEmpty: "순위로 표시할 거래가 없습니다.",
  },
  passbook: {
    title: "통장관리",
    subtitle: "은행 거래내역 PDF를 업로드해 입출금 내역으로 정리합니다.",
    loginRequired: "통장 내역을 보려면 로그인하세요.",
    fileLabel: "거래내역 PDF",
    fileHelp: "PDF 거래내역을 선택하세요",
    missingFile: "먼저 거래내역 PDF를 선택하세요.",
    passwordLabel: "PDF 비밀번호",
    passwordPlaceholder: "PDF 비밀번호 입력",
    passwordRequired: "PDF 비밀번호를 입력하세요.",
    invalidPassword: "PDF 비밀번호가 올바르지 않습니다.",
    load: "업로드 후 파싱",
    parsing: "거래내역 업로드 및 파싱 중...",
    failTitle: "통장 내역을 불러오지 못했습니다",
    sessionExpired: "세션이 만료되었습니다. 다시 로그인한 뒤 거래내역을 업로드해 주세요.",
    monthLabel: "거래월",
    savedMonths: "저장된 월 {n}개",
    listLoading: "저장된 월 불러오는 중...",
    detailLoading: "선택한 거래내역 불러오는 중...",
    noSavedStatements: "저장된 거래내역이 없습니다.",
    file: "파일",
    uploadedAt: "업로드일",
    statementMonth: "거래월",
    account: "계좌번호",
    holder: "예금주",
    period: "조회기간",
    closingBalance: "총잔액",
    withdrawalTotal: "출금 합계",
    depositTotal: "입금 합계",
    entries: "거래 {n}건",
    warnings: "확인 필요",
    th: {
      date: "일자",
      time: "시간",
      summary: "적요",
      description: "내용",
      withdrawal: "출금",
      deposit: "입금",
      balance: "잔액",
      branch: "거래점",
    },
    empty: "파싱된 거래 내역이 없습니다.",
    chartTitle: "카테고리 순위",
    chartSubtitle: "금액 기준 상위 10개 카테고리",
    windowMonth: "이번 달",
    windowYear: "최근 1년",
    directionOut: "출금",
    directionIn: "입금",
    chartLoading: "카테고리 합계 불러오는 중...",
    chartEmpty: "그래프로 표시할 카테고리 합계가 없습니다.",
    chartAmount: "금액",
    topTitleOut: "최다 출금 내역",
    topTitleIn: "최다 입금 내역",
    topSubtitle: "금액 기준 상위 10건 (날짜 + 내용)",
    topEmpty: "순위로 표시할 거래가 없습니다.",
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
