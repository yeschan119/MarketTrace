// Korean display names for the curated instrument corpus, keyed by ticker
// (US letter symbol or 6-digit KRX code). Rendered faintly next to the English
// instrument name so both markets read naturally for Korean users, e.g.
// "NAVER Corporation  네이버". A ticker with no mapping shows nothing extra.
//
// Frontend-only, mirroring the pattern of eventTypes.ts: the instrument set is a
// fixed curated corpus (backend _CORPUS_US_ISSUERS / _CORPUS_KR_ISSUERS), so a
// static map avoids a schema/migration and stays trivially editable.

const KOREAN_NAMES: Record<string, string> = {
  // --- US (common Korean rendering of the company name) ---
  AAPL: "애플",
  MSFT: "마이크로소프트",
  NVDA: "엔비디아",
  AMZN: "아마존",
  GOOGL: "알파벳(구글)",
  META: "메타",
  TSLA: "테슬라",
  JPM: "JP모건",
  XOM: "엑슨모빌",
  JNJ: "존슨앤드존슨",
  V: "비자",
  WMT: "월마트",
  UNH: "유나이티드헬스",
  PG: "프록터앤드갬블(P&G)",
  HD: "홈디포",
  BAC: "뱅크오브아메리카",
  KO: "코카콜라",
  PFE: "화이자",
  CVX: "셰브론",
  DIS: "디즈니",

  // --- KR (actual Korean company name) ---
  "005930": "삼성전자",
  "000660": "SK하이닉스",
  "373220": "LG에너지솔루션",
  "207940": "삼성바이오로직스",
  "005380": "현대차",
  "000270": "기아",
  "005490": "POSCO홀딩스",
  "035420": "네이버",
  "035720": "카카오",
  "051910": "LG화학",
  "006400": "삼성SDI",
  "028260": "삼성물산",
  "105560": "KB금융",
  "055550": "신한지주",
  "012330": "현대모비스",
  "068270": "셀트리온",
  "015760": "한국전력",
  "032830": "삼성생명",
  "003670": "포스코퓨처엠",
  "017670": "SK텔레콤",
};

/** Korean name for a ticker, or null when there is no mapping. */
export function koreanName(ticker: string | null | undefined): string | null {
  if (!ticker) return null;
  return KOREAN_NAMES[ticker] ?? KOREAN_NAMES[ticker.toUpperCase()] ?? null;
}
