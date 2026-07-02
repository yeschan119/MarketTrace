import type { Lang } from "./i18n";

// Human-readable label + one-line description for the machine event_type codes
// the LLM emits. The codes are free-form, so this covers the meaningful,
// well-sampled types and anything missing falls back to a humanized code.
export type EventTypeInfo = { label: string; desc: string };

type Entry = { en: EventTypeInfo; ko: EventTypeInfo };

const LABELS: Record<string, Entry> = {
  earnings_release: {
    en: { label: "Earnings Release", desc: "Quarterly or annual results — revenue and profit." },
    ko: { label: "실적 발표", desc: "분기·연간 실적(매출·이익) 공시." },
  },
  earnings_beat: {
    en: { label: "Earnings Beat", desc: "Results that came in above market expectations." },
    ko: { label: "어닝 서프라이즈", desc: "시장 예상을 웃돈 실적." },
  },
  earnings_guidance: {
    en: { label: "Earnings Guidance", desc: "Company's own forecast for upcoming results." },
    ko: { label: "실적 가이던스", desc: "회사가 제시한 향후 실적 전망." },
  },
  guidance_update: {
    en: { label: "Guidance Update", desc: "Revision to a previously issued forecast." },
    ko: { label: "가이던스 수정", desc: "기존 실적 전망 상향·하향 수정." },
  },
  earnings_conference_call: {
    en: { label: "Earnings Call", desc: "Post-results conference call with investors." },
    ko: { label: "실적 컨퍼런스콜", desc: "실적 발표 후 투자자 대상 설명회." },
  },
  regulatory_action: {
    en: { label: "Regulatory Action", desc: "Regulator-related action, approval, or sanction." },
    ko: { label: "규제·당국 조치", desc: "규제기관 관련 조치·승인·제재 공시." },
  },
  regulation_fd_disclosure: {
    en: { label: "Reg FD Disclosure", desc: "Fair-disclosure filing of material info (Reg FD)." },
    ko: { label: "공정공시(Reg FD)", desc: "미국 공정공시 규정에 따른 중요정보 공시." },
  },
  insider_trading_report: {
    en: { label: "Insider Trade Report", desc: "Insiders reporting their own buys/sells of the stock." },
    ko: { label: "내부자 거래 신고", desc: "임원·주요주주의 자사주 매매 신고." },
  },
  insider_trading_plan: {
    en: { label: "Insider Trading Plan", desc: "Pre-arranged insider trading plan (10b5-1)." },
    ko: { label: "내부자 거래계획", desc: "임원의 사전 약정 매매계획(10b5-1) 신고." },
  },
  trading_plan: {
    en: { label: "Trading Plan", desc: "Pre-arranged insider trading plan." },
    ko: { label: "거래계획 신고", desc: "사전 약정 매매계획 신고." },
  },
  management_change: {
    en: { label: "Management Change", desc: "Change in senior management (CEO, executives)." },
    ko: { label: "경영진 변경", desc: "대표·임원 등 경영진 교체." },
  },
  leadership_change: {
    en: { label: "Leadership Change", desc: "Change in company leadership." },
    ko: { label: "리더십 변경", desc: "회사 지도부 교체." },
  },
  management_appointment: {
    en: { label: "Management Appointment", desc: "New senior management appointment." },
    ko: { label: "경영진 선임", desc: "경영진 신규 선임." },
  },
  executive_appointment: {
    en: { label: "Executive Appointment", desc: "New executive officer appointed." },
    ko: { label: "임원 선임", desc: "임원 신규 선임." },
  },
  executive_departure: {
    en: { label: "Executive Departure", desc: "A key executive is leaving." },
    ko: { label: "임원 퇴임", desc: "핵심 임원의 사임·퇴사." },
  },
  executive_retirement: {
    en: { label: "Executive Retirement", desc: "A key executive is retiring." },
    ko: { label: "임원 은퇴", desc: "핵심 임원의 정년·은퇴." },
  },
  appointment_announcement: {
    en: { label: "Appointment", desc: "Appointment of an officer or director." },
    ko: { label: "선임 발표", desc: "임원·이사 선임 발표." },
  },
  new_appointment: {
    en: { label: "New Appointment", desc: "Appointment of a new officer or director." },
    ko: { label: "신규 선임", desc: "임원·이사 신규 선임." },
  },
  board_appointment: {
    en: { label: "Board Appointment", desc: "New director added to the board." },
    ko: { label: "이사 선임", desc: "이사회 신규 이사 선임." },
  },
  director_appointment: {
    en: { label: "Director Appointment", desc: "New director appointed." },
    ko: { label: "이사 선임", desc: "이사 신규 선임." },
  },
  board_nomination: {
    en: { label: "Board Nomination", desc: "Nominee proposed for a board seat." },
    ko: { label: "이사 후보 지명", desc: "이사회 이사 후보 지명." },
  },
  board_member_departure: {
    en: { label: "Board Departure", desc: "A director is leaving the board." },
    ko: { label: "이사 사임·퇴임", desc: "이사회 구성원의 사임·퇴임." },
  },
  board_resignation: {
    en: { label: "Board Resignation", desc: "A director resigned from the board." },
    ko: { label: "이사 사임", desc: "이사회 구성원의 사임." },
  },
  board_member_resignation: {
    en: { label: "Board Resignation", desc: "A board member resigned." },
    ko: { label: "이사 사임", desc: "이사회 구성원의 사임." },
  },
  board_member_retirement: {
    en: { label: "Board Retirement", desc: "A board member retired." },
    ko: { label: "이사 은퇴", desc: "이사회 구성원의 은퇴." },
  },
  debt_offering: {
    en: { label: "Debt Offering", desc: "Public offering of debt securities." },
    ko: { label: "회사채 공모", desc: "부채성 증권 공모 발행." },
  },
  debt_issuance: {
    en: { label: "Debt Issuance", desc: "Issuance of borrowings or notes." },
    ko: { label: "채무 발행", desc: "차입·사채 등 부채 발행." },
  },
  bond_issuance: {
    en: { label: "Bond Issuance", desc: "Issuance of bonds." },
    ko: { label: "채권 발행", desc: "사채 발행." },
  },
  preferred_stock_issuance: {
    en: { label: "Preferred Stock Issuance", desc: "Issuance of preferred shares." },
    ko: { label: "우선주 발행", desc: "우선주 발행." },
  },
  capital_increase: {
    en: { label: "Capital Increase", desc: "Raising capital by issuing new shares." },
    ko: { label: "유상증자", desc: "신주 발행을 통한 자본 확충." },
  },
  capital_raising: {
    en: { label: "Capital Raising", desc: "Raising new capital." },
    ko: { label: "자본 조달", desc: "신규 자본 조달." },
  },
  equity_offering: {
    en: { label: "Equity Offering", desc: "Public offering of shares." },
    ko: { label: "주식 공모", desc: "주식 공모 발행." },
  },
  shareholding_change: {
    en: { label: "Shareholding Change", desc: "Change in a major holder's stake." },
    ko: { label: "지분 변동", desc: "주요주주 지분율 변동 공시." },
  },
  ownership_change: {
    en: { label: "Ownership Change", desc: "Change in ownership / controlling holder." },
    ko: { label: "소유구조 변동", desc: "최대주주·소유구조 변동." },
  },
  ownership_structure_disclosure: {
    en: { label: "Ownership Disclosure", desc: "Disclosure of ownership structure." },
    ko: { label: "소유구조 공시", desc: "소유구조 관련 공시." },
  },
  holding_change: {
    en: { label: "Holding Change", desc: "Change in a holding position." },
    ko: { label: "보유 변동", desc: "보유 지분 변동." },
  },
  merger_announcement: {
    en: { label: "M&A Announcement", desc: "Announcement of a merger or acquisition." },
    ko: { label: "인수·합병 발표", desc: "M&A 계획 발표." },
  },
  dividend_announcement: {
    en: { label: "Dividend Announcement", desc: "Announcement of a dividend." },
    ko: { label: "배당 발표", desc: "배당 결정·계획 공시." },
  },
  dividend_declaration: {
    en: { label: "Dividend Declaration", desc: "Formal declaration of a dividend." },
    ko: { label: "배당 결의", desc: "배당 지급 결의." },
  },
  dividend_increase: {
    en: { label: "Dividend Increase", desc: "Increase in the dividend payout." },
    ko: { label: "배당 증액", desc: "배당금 인상." },
  },
  shareholder_meeting: {
    en: { label: "Shareholder Meeting", desc: "A shareholder meeting is being held." },
    ko: { label: "주주총회", desc: "주주총회 개최 관련." },
  },
  shareholder_meeting_announcement: {
    en: { label: "Shareholder Meeting Notice", desc: "Notice of an upcoming shareholder meeting." },
    ko: { label: "주총 소집 공고", desc: "주주총회 소집 안내." },
  },
  shareholder_meeting_results: {
    en: { label: "Shareholder Meeting Results", desc: "Voting results from a shareholder meeting." },
    ko: { label: "주총 결과", desc: "주주총회 안건 표결 결과." },
  },
  shareholder_meeting_result: {
    en: { label: "Shareholder Meeting Result", desc: "Result of a shareholder meeting." },
    ko: { label: "주총 결과", desc: "주주총회 결과." },
  },
  shareholder_approval: {
    en: { label: "Shareholder Approval", desc: "Shareholders approved a proposal." },
    ko: { label: "주주 승인", desc: "주총 안건 주주 승인." },
  },
  annual_meeting: {
    en: { label: "Annual Meeting", desc: "The company's annual shareholder meeting." },
    ko: { label: "정기 주주총회", desc: "연례 정기 주주총회." },
  },
  annual_meeting_results: {
    en: { label: "Annual Meeting Results", desc: "Voting results from the annual meeting." },
    ko: { label: "정기 주총 결과", desc: "정기 주주총회 표결 결과." },
  },
  general_meeting_announcement: {
    en: { label: "General Meeting Notice", desc: "Notice of a general meeting." },
    ko: { label: "총회 소집 공고", desc: "총회 소집 안내." },
  },
  proxy_solicitation: {
    en: { label: "Proxy Solicitation", desc: "Solicitation of shareholder proxies for a vote." },
    ko: { label: "의결권 위임 권유", desc: "표결 위한 의결권 위임 권유." },
  },
  investor_meeting: {
    en: { label: "Investor Meeting", desc: "Meeting with institutional investors." },
    ko: { label: "투자자 미팅", desc: "기관·투자자 대상 미팅." },
  },
  investor_conference: {
    en: { label: "Investor Conference", desc: "Company presenting at an investor conference." },
    ko: { label: "투자자 컨퍼런스", desc: "IR 컨퍼런스 참가." },
  },
  conference_announcement: {
    en: { label: "Conference Notice", desc: "Notice of participation in an investor conference." },
    ko: { label: "컨퍼런스 참가 안내", desc: "IR·투자자 컨퍼런스 참가 안내." },
  },
  conference_call_announcement: {
    en: { label: "Conference Call Notice", desc: "Notice of an upcoming conference call." },
    ko: { label: "컨퍼런스콜 안내", desc: "컨퍼런스콜 개최 안내." },
  },
  investor_relations_event: {
    en: { label: "IR Event", desc: "Investor-relations event." },
    ko: { label: "IR 행사", desc: "투자자 관계(IR) 행사." },
  },
  investor_day_announcement: {
    en: { label: "Investor Day Notice", desc: "Notice of an investor day." },
    ko: { label: "인베스터 데이 안내", desc: "투자자의 날 개최 안내." },
  },
  macro_data_release: {
    en: { label: "Macro Data Release", desc: "Release of a macroeconomic indicator (rates, CPI…)." },
    ko: { label: "거시지표 발표", desc: "금리·물가 등 거시 경제지표 발표." },
  },
  contract_award: {
    en: { label: "Contract Award", desc: "Won a significant contract or order." },
    ko: { label: "수주·계약 체결", desc: "주요 계약·수주 획득." },
  },
  asset_disposal: {
    en: { label: "Asset Disposal", desc: "Sale or disposal of a major asset." },
    ko: { label: "자산 매각", desc: "주요 자산 처분." },
  },
  investment_commitment: {
    en: { label: "Investment Commitment", desc: "Commitment to invest capital." },
    ko: { label: "투자 약정", desc: "투자 집행·약정 발표." },
  },
  investment: {
    en: { label: "Investment", desc: "An investment made by the company." },
    ko: { label: "투자", desc: "회사의 투자 집행." },
  },
  bylaw_amendment: {
    en: { label: "Bylaw Amendment", desc: "Amendment to corporate bylaws." },
    ko: { label: "정관 변경", desc: "정관·내규 개정." },
  },
  sustainability_report_release: {
    en: { label: "Sustainability Report", desc: "Release of an ESG / sustainability report." },
    ko: { label: "지속가능경영 보고서", desc: "ESG·지속가능 보고서 공개." },
  },
  esg_report_release: {
    en: { label: "ESG Report", desc: "Release of an ESG report." },
    ko: { label: "ESG 보고서", desc: "ESG 보고서 공개." },
  },
  treasury_stock_acquisition: {
    en: { label: "Treasury Stock Buyback", desc: "Company buying back its own shares." },
    ko: { label: "자기주식 취득", desc: "자사주 매입." },
  },
  share_buyback_announcement: {
    en: { label: "Share Buyback", desc: "Announcement of a share buyback." },
    ko: { label: "자사주 매입 발표", desc: "자기주식 매입 발표." },
  },
  related_party_transaction: {
    en: { label: "Related-Party Transaction", desc: "Transaction with a related party." },
    ko: { label: "특수관계자 거래", desc: "특수관계자와의 거래." },
  },
  registration_statement_filing: {
    en: { label: "Registration Statement", desc: "Securities registration statement filed." },
    ko: { label: "증권신고서 제출", desc: "증권 발행 등록 신고서 제출." },
  },
  partnership_announcement: {
    en: { label: "Partnership", desc: "Announcement of a business partnership." },
    ko: { label: "제휴 발표", desc: "사업 제휴 발표." },
  },
  product_launch: {
    en: { label: "Product Launch", desc: "Launch of a new product." },
    ko: { label: "제품 출시", desc: "신제품 출시." },
  },
  investment_plan_announcement: {
    en: { label: "Investment Plan", desc: "Announcement of an investment plan." },
    ko: { label: "투자계획 발표", desc: "투자 계획 발표." },
  },
  investment_decision: {
    en: { label: "Investment Decision", desc: "Decision to make an investment." },
    ko: { label: "투자 결정", desc: "투자 집행 결정." },
  },
  business_plan_update: {
    en: { label: "Business Plan Update", desc: "Update to the business plan." },
    ko: { label: "사업계획 변경", desc: "사업 계획 업데이트." },
  },
  corporate_strategy_update: {
    en: { label: "Corporate Strategy Update", desc: "Update to corporate strategy." },
    ko: { label: "사업전략 업데이트", desc: "회사 전략 방향 업데이트." },
  },
  company_update: {
    en: { label: "Company Update", desc: "General company update." },
    ko: { label: "회사 소식", desc: "회사 관련 일반 업데이트." },
  },
  company_disclosure: {
    en: { label: "Company Disclosure", desc: "General company disclosure." },
    ko: { label: "회사 공시", desc: "회사의 일반 공시." },
  },
  corporate_event: {
    en: { label: "Corporate Event", desc: "General corporate event." },
    ko: { label: "기업 이벤트", desc: "일반 기업 이벤트." },
  },
  report_release: {
    en: { label: "Report Release", desc: "Release of a report." },
    ko: { label: "보고서 공개", desc: "보고서 공개." },
  },
  sales_report: {
    en: { label: "Sales Report", desc: "Report of sales figures." },
    ko: { label: "매출 보고", desc: "매출 실적 보고." },
  },
  earnings_guide: {
    en: { label: "Earnings Guide", desc: "Guidance on upcoming results." },
    ko: { label: "실적 가이드", desc: "실적 전망 안내." },
  },
  guidance_reaffirmation: {
    en: { label: "Guidance Reaffirmation", desc: "Reaffirming previous guidance." },
    ko: { label: "가이던스 재확인", desc: "기존 실적 전망 재확인." },
  },
  donation_announcement: {
    en: { label: "Donation", desc: "Announcement of a donation." },
    ko: { label: "기부 발표", desc: "기부·후원 발표." },
  },
  redemption_announcement: {
    en: { label: "Redemption", desc: "Redemption of securities or notes." },
    ko: { label: "상환 발표", desc: "사채·증권 상환 발표." },
  },
  exchange_offer_announcement: {
    en: { label: "Exchange Offer", desc: "Securities exchange offer." },
    ko: { label: "교환공개매수 발표", desc: "증권 교환공개매수 발표." },
  },
  conversion_rate_adjustment: {
    en: { label: "Conversion Rate Adjustment", desc: "Adjustment to a conversion ratio." },
    ko: { label: "전환가액 조정", desc: "전환사채 등 전환비율 조정." },
  },
  credit_agreement: {
    en: { label: "Credit Agreement", desc: "A credit / lending agreement." },
    ko: { label: "신용 계약", desc: "여신·신용 계약 체결." },
  },
  loan_approval: {
    en: { label: "Loan Approval", desc: "Approval of a loan or borrowing." },
    ko: { label: "대출 승인", desc: "차입·대출 승인." },
  },
  financial_transaction: {
    en: { label: "Financial Transaction", desc: "A financial transaction." },
    ko: { label: "금융 거래", desc: "재무·금융 거래." },
  },
  stock_acquisition: {
    en: { label: "Stock Acquisition", desc: "Acquisition of shares." },
    ko: { label: "주식 취득", desc: "주식 취득." },
  },
  asset_transfer: {
    en: { label: "Asset Transfer", desc: "Transfer of an asset." },
    ko: { label: "자산 양도", desc: "자산 양도·이전." },
  },
  real_estate_purchase: {
    en: { label: "Real Estate Purchase", desc: "Purchase of real estate." },
    ko: { label: "부동산 취득", desc: "부동산 매입." },
  },
  ownership_report: {
    en: { label: "Ownership Report", desc: "Report of an ownership position." },
    ko: { label: "지분 보고", desc: "지분 보유 현황 보고." },
  },
  insider_sale: {
    en: { label: "Insider Sale", desc: "An insider selling shares." },
    ko: { label: "내부자 매도", desc: "내부자의 자사주 매도." },
  },
  internal_transaction: {
    en: { label: "Internal Transaction", desc: "An insider-related transaction." },
    ko: { label: "내부 거래", desc: "내부자 관련 거래." },
  },
  transaction_with_related_party: {
    en: { label: "Related-Party Transaction", desc: "Transaction with a related party." },
    ko: { label: "특수관계자 거래", desc: "특수관계자와의 거래." },
  },
  purchase_related_party_securities: {
    en: { label: "Related-Party Securities Purchase", desc: "Purchase of a related party's securities." },
    ko: { label: "특수관계자 증권 취득", desc: "특수관계자 증권 매입." },
  },
  director_dismissal: {
    en: { label: "Director Dismissal", desc: "Dismissal of a director." },
    ko: { label: "이사 해임", desc: "이사 해임." },
  },
  shareholder_vote: {
    en: { label: "Shareholder Vote", desc: "A shareholder vote." },
    ko: { label: "주주 투표", desc: "주주 표결." },
  },
  stock_plan_approval: {
    en: { label: "Stock Plan Approval", desc: "Approval of a stock-award plan." },
    ko: { label: "주식보상제도 승인", desc: "주식보상 계획 승인." },
  },
  equity_award_announcement: {
    en: { label: "Equity Award", desc: "Grant of equity awards to staff." },
    ko: { label: "주식보상 발표", desc: "임직원 주식보상 부여 발표." },
  },
  compensation_announcement: {
    en: { label: "Compensation Announcement", desc: "Executive compensation announcement." },
    ko: { label: "보수 발표", desc: "임원 보수 관련 발표." },
  },
  compensation_award: {
    en: { label: "Compensation Award", desc: "Award of executive compensation." },
    ko: { label: "보수 지급", desc: "임원 보수·상여 지급." },
  },
  compensation_change: {
    en: { label: "Compensation Change", desc: "Change to compensation terms." },
    ko: { label: "보수 변경", desc: "임원 보수 체계 변경." },
  },
  compensation_increase: {
    en: { label: "Compensation Increase", desc: "Increase in compensation." },
    ko: { label: "보수 인상", desc: "임원 보수 인상." },
  },
  compensation_plan_adoption: {
    en: { label: "Compensation Plan Adoption", desc: "Adoption of a compensation plan." },
    ko: { label: "보상제도 도입", desc: "임원 보상제도 채택." },
  },
  executive_compensation_change: {
    en: { label: "Executive Compensation Change", desc: "Change to executive compensation." },
    ko: { label: "임원 보수 변경", desc: "임원 보수 변경." },
  },
  employment_agreement_amendment: {
    en: { label: "Employment Agreement Amendment", desc: "Amendment to an employment agreement." },
    ko: { label: "고용계약 변경", desc: "임원 고용계약 개정." },
  },
};

function humanize(code: string): string {
  return code
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function describeEventType(code: string, lang: Lang): EventTypeInfo {
  const entry = LABELS[code];
  if (entry) return lang === "ko" ? entry.ko : entry.en;
  // Unknown / long-tail code: at least render it as readable words.
  return { label: humanize(code), desc: "" };
}
