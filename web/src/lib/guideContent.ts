import type { Lang } from "@/lib/i18n";

// Long-form user-guide content lives here as a bilingual data structure rather
// than as flat i18n keys: it is document-shaped (sections → blocks), and both
// languages are kept side-by-side so neither can silently fall out of sync.

export type ChipTone = "pos" | "warn" | "neg" | "acc" | "mut";

export interface Chip {
  text: string;
  tone: ChipTone;
}

export type GuideBlock =
  | { kind: "p"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "defs"; items: { term: string; desc: string }[] }
  | { kind: "chips"; label?: string; items: Chip[] }
  | { kind: "note"; tone?: "accent" | "warn"; text: string }
  | { kind: "steps"; title?: string; items: string[] };

export interface GuideSection {
  id: string;
  band?: string;
  title: string;
  role?: string;
  blocks: GuideBlock[];
}

export interface GuideDoc {
  eyebrow: string;
  title: string;
  lede: string;
  thesis: string;
  tocLabel: string;
  footer: string;
  sections: GuideSection[];
}

const ko: GuideDoc = {
  eyebrow: "사용 가이드북",
  title: "MarketTrace 사용 가이드",
  lede: "공시에서 뽑아낸 **사건(event)**이 시장을 실제로 어떻게 움직였는지를 숫자로 검증해, 종목을 “먼저 살펴볼 순서”로 정리해 주는 도구입니다. 이 문서는 각 화면을 언제·어떻게 읽는지 설명합니다.",
  thesis:
    "먼저 알아둘 한 가지 — MarketTrace는 **매수 추천기가 아니라 검토·주의 도구**입니다. 지금까지 통계적으로 검증된 신호는 **전부 음(−) 방향**이라, 시스템은 “오른다”를 단정하지 않습니다. 모든 화면은 “이 종목/사건을 조심해서 봐야 하는가”를 돕기 위한 것입니다.",
  tocLabel: "목차",
  footer:
    "화면의 숫자·헤더·배지에 커서를 올리면 그 자리에서 설명이 나옵니다. 이 문서는 제품 UI 문구를 기준으로 작성되었습니다.",
  sections: [
    {
      id: "concepts",
      band: "먼저 읽기",
      title: "핵심 개념 5가지",
      role: "이 다섯 가지만 이해하면 모든 화면이 읽힙니다. 화면 곳곳의 숫자·헤더·배지에 **커서를 올리면(hover)** 그 자리에서 같은 설명이 뜹니다.",
      blocks: [
        {
          kind: "defs",
          items: [
            {
              term: "① 이벤트 (event)",
              desc: "공시(SEC EDGAR·OpenDART)에서 LLM이 뽑아낸 구조화된 사건 한 건. 각 이벤트는 **방향**(긍정/부정/중립)·**유형**·**신뢰도**·**서프라이즈**·**신규성**·**출처 신뢰도**를 가집니다. LLM은 “뽑기”만 하고, 수익률 계산은 전부 별도 수치 모듈이 합니다.",
            },
            {
              term: "② 초과수익률",
              desc: "종목의 실제 수익률 − 같은 기간 시장(지수) 수익률. 시장 전체 흐름을 걷어내고 **이 사건이 종목에 준 영향만** 본 값입니다. 공시 후 D+1 / 5 / 20 / 60 거래일 시점에서 집계합니다.",
            },
            {
              term: "③ 검증된 신호",
              desc: "표본이 충분하고(n≥5) 0과 통계적으로 구분되는(p<0.05) 사건유형만 “검증됨”. **지금까지 검증된 신호는 전부 음(−)** — 상승 신호는 아직 없습니다.",
            },
            {
              term: "④ 모델 vs 실측",
              desc: "모델(LLM)이 읽은 방향과, 그 사건유형의 검증된 과거 실측 방향을 비교합니다. 같으면 검증됨, 반대면 충돌, 실측은 있는데 모델이 중립이면 신호.",
            },
            {
              term: "⑤ 드리프트 (drift)",
              desc: "어떤 사건유형이 발생한 뒤 나타난 초과수익률의 평균. 랭킹·급락·종목 판정은 이 드리프트를 확신도·최근성으로 가중해 합산한 값을 씁니다.",
            },
          ],
        },
      ],
    },
    {
      id: "colors",
      title: "색상·배지 규약",
      role: "앱 전체가 같은 색 언어를 씁니다. 색만 봐도 방향과 주의도가 읽힙니다.",
      blocks: [
        {
          kind: "chips",
          label: "방향 (이벤트가 가리키는 쪽)",
          items: [
            { text: "긍정 positive", tone: "pos" },
            { text: "부정 negative", tone: "neg" },
            { text: "중립 neutral", tone: "mut" },
          ],
        },
        {
          kind: "chips",
          label: "검증 신호 배지",
          items: [
            { text: "충돌", tone: "warn" },
            { text: "검증됨", tone: "pos" },
            { text: "신호", tone: "acc" },
          ],
        },
        {
          kind: "p",
          text: "**충돌** = 모델 방향이 검증된 실측과 반대(한 번 더 확인). **검증됨** = 일치. **신호** = 유의한 실측은 있으나 모델은 중립. 배지가 없으면 아직 이 유형에 검증된 신호가 없다는 뜻입니다.",
        },
        {
          kind: "chips",
          label: "급락 진단",
          items: [
            { text: "지속 악재", tone: "warn" },
            { text: "원인 미상 하락", tone: "mut" },
            { text: "과잉반응 가능", tone: "acc" },
          ],
        },
        {
          kind: "p",
          text: "‘과잉반응 가능’은 초록이 아니라 파랑입니다 — 반등 **후보**일 뿐 상승 보장이 아니라는 뜻을 색으로 못박은 것입니다.",
        },
      ],
    },
    {
      id: "search",
      band: "매일 보는 화면",
      title: "검색 — 종목 찾기 · 새 종목 분석",
      role: "티커·회사명·별칭으로 종목을 찾습니다. 아직 데이터에 없는 회사라면 **회사명만으로 공시 분석을 즉시 실행**할 수 있습니다.",
      blocks: [
        {
          kind: "list",
          items: [
            "검색창에 입력하면 자동 검색됩니다. 국내는 숫자 종목코드(예: 005930), 미국은 티커(예: AAPL)를 인식합니다.",
            "결과 행의 **티커**를 누르면 종목 타임라인(상세)으로, 우측 이벤트 수로 데이터 유무를 확인합니다.",
            "결과가 없거나 새로 돌리고 싶으면 **공시 분석** 버튼으로 KR/US·티커·회사명을 넣어 추출을 시작합니다. 추출이 끝나면 이벤트에 나타납니다.",
          ],
        },
        {
          kind: "note",
          text: "**로그인이 필요합니다.** 공시 분석 실행은 계정이 있어야 합니다. SpaceX 같은 비상장사는 지원하지 않습니다.",
        },
      ],
    },
    {
      id: "picks",
      title: "추천종목 — 무엇부터 볼지",
      role: "급락 종목 중 **먼저 검토할 만한 순서**로 정렬합니다. 최근 가격 흐름 + 최근 회사 소식 + 비슷한 과거 사건의 결과를 함께 봅니다. 국내·해외로 나뉩니다.",
      blocks: [
        {
          kind: "chips",
          items: [
            { text: "우선 검토", tone: "acc" },
            { text: "추가 확인", tone: "mut" },
            { text: "추천 낮음", tone: "mut" },
          ],
        },
        {
          kind: "list",
          items: [
            "각 종목마다 **추천 이유**(낙폭·가격 신선도·최근 사건·요인)를 문장으로 풀어 줍니다. 단순히 가격만 보고 고른 게 아닙니다.",
            "기준: 최근 고점 대비 **15% 이상** 내려온 종목이 있으면 전부, 없으면 상대적으로 많이 내려온 5개만.",
          ],
        },
        {
          kind: "note",
          tone: "warn",
          text: "**이 목록은 “반드시 오른다”가 아닙니다.** 검토 우선순위일 뿐입니다. 각 종목의 이유를 읽고 최신 뉴스·공시를 확인한 뒤 판단하세요.",
        },
      ],
    },
    {
      id: "events",
      title: "이벤트 — 사건 목록과 상세",
      role: "모든 사건을 **기업별로 묶어** 보여줍니다. 시스템의 중심 화면입니다.",
      blocks: [
        {
          kind: "list",
          items: [
            "**국내(KR) / 해외(US)** 탭으로 시장을 고르고, 검색창으로 티커·회사·유형·방향을 거릅니다.",
            "신호 필터: 전체 / 충돌만 / 미검토 충돌 / 검증된 것만 — ‘미검토 충돌’이 사람이 손봐야 할 검토 큐입니다.",
            "각 사건 행: 유형 · 방향 · 신호 배지 · **신뢰도 %** · 공시일. 신뢰도 %와 배지에 커서를 올리면 뜻이 뜹니다. ‘✓ 검토됨’은 사람이 확인한 사건입니다.",
          ],
        },
        {
          kind: "defs",
          items: [
            {
              term: "검증신호 카드",
              desc: "이 사건유형이 과거 시장을 어떻게 움직였는지(기간별 평균 초과수익·t값·p값·표본수)와, 그것이 모델 판단과 일치/충돌하는지를 한 줄로 요약합니다.",
            },
            {
              term: "검토·수정",
              desc: "(로그인 시) 모델의 방향·유형·회사·신뢰도를 교정합니다. 방향/유형 수정은 통계에 즉시, 회사 변경은 가격을 다시 가져와 수익률을 재계산합니다.",
            },
            {
              term: "점수 구성",
              desc: "신뢰도·서프라이즈·신규성·출처 신뢰도를 0~100% 막대로. 제목 옆 ? 에 각 항목 뜻이 있습니다.",
            },
            {
              term: "초과수익률 그래프",
              desc: "기간별 초과·원·시장·섹터조정 수익률 추이. **비어 있으면** 아직 관측 기간이 안 지났거나 가격 데이터가 없다는 뜻입니다(오류 아님).",
            },
            {
              term: "근거·산업·채널",
              desc: "LLM이 판단 근거로 든 문장과 관련 산업·유통 채널 태그.",
            },
          ],
        },
      ],
    },
    {
      id: "rankings",
      title: "랭킹 — 종목 간 비교",
      role: "모든 종목을 **확신도·최근성 가중 검증 드리프트**로 줄 세운 종목 간 뷰. 과거 실측상 **가장 주의할 종목이 위로** 옵니다(최근·고확신 사건일수록 크게 반영, 반감기 180일).",
      blocks: [
        {
          kind: "defs",
          items: [
            { term: "판정 (lean)", desc: "검증된 실측을 종합한 방향 성향 — 주의 · 우호 · 혼조." },
            { term: "가중 드리프트", desc: "검증 사건들의 사건후 평균 수익률을 확신도·최근성으로 가중 합산. **정렬 기준**입니다." },
            { term: "단순 평균", desc: "같은 사건들을 가중 없이 평균. 가중값과 비교하면 최근성·확신도 보정 영향이 보입니다." },
            { term: "검증", desc: "유의한 검증 신호를 가진 사건 수(n≥5, p<0.05)." },
            { term: "충돌", desc: "모델 방향이 실측과 반대인 사건 수. 괄호 안은 아직 미검토 건수." },
            { term: "주요 요인", desc: "가중 드리프트에 가장 크게 기여한 사건유형과 그 평균 수익률." },
          ],
        },
      ],
    },
    {
      id: "screener",
      title: "급락 — 낙폭 스크리너",
      role: "20일 고점 대비 **15% 이상** 빠진 종목을, 검증된 사건 이력에 비추어 진단합니다.",
      blocks: [
        {
          kind: "defs",
          items: [
            { term: "지속 악재", desc: "최근 사건 + 검증된 음(−) 성향 — 하락이 이 종목 이력과 일치, 주의가 이어질 가능성." },
            { term: "원인 미상 하락", desc: "데이터상 하락을 설명할 최근 사건이 없음. 신호가 아니라 관찰 — 원인 확인이 먼저." },
            { term: "과잉반응 가능", desc: "최근 사건은 있으나 검증된 음(−) 근거는 없음. 백테스트 검증 전 반등 **후보**(매수 신호 아님)." },
          ],
        },
        {
          kind: "list",
          items: [
            "**반등 백테스트** 패널: “이런 하락 뒤 매수가 유효한가?”를 고정 규칙·표본외·비용 차감으로 검증. 데이터가 부족하면 ‘관찰’로 유지됩니다.",
            "**오래된 가격 포함** 체크박스로 신선하지 않은 가격의 종목까지 볼 수 있습니다(‘오래됨’ 태그 표시).",
          ],
        },
      ],
    },
    {
      id: "watchlist",
      band: "내 종목",
      title: "관심종목 · 알림",
      role: "신경 쓰는 종목만 모아 두고, 주목할 사건이 생기면 알림을 받습니다.",
      blocks: [
        {
          kind: "list",
          items: [
            "이벤트 목록·종목 페이지·랭킹의 **☆ 버튼**으로 관심종목에 넣습니다(로그인 필요).",
            "알림은 두 종류: **충돌**(모델 방향이 검증된 드리프트와 충돌) · **유의**(검증된 유의 사건유형). 헤더의 종 아이콘으로 확인하고 ‘모두 읽음’ 처리합니다.",
          ],
        },
      ],
    },
    {
      id: "stats",
      band: "근거·검증",
      title: "통계 — 시스템을 신뢰할 근거",
      role: "“이 도구를 믿어도 되나?”에 답하는 화면입니다. 개별 종목이 아니라 **방법론 전체의 성능**을 봅니다.",
      blocks: [
        {
          kind: "defs",
          items: [
            { term: "반응 통계", desc: "이벤트유형 × 공시후 기간(거래일)별 평균 초과수익률 히트맵(초록 상승·빨강 하락, n=표본수). **칸을 누르면** 그 평균의 근거가 된 실제 공시들이 펼쳐집니다." },
            { term: "검증된 신호", desc: "n≥5·p<0.05를 통과한 유형만. 지금까지 **전부 음(−)** — 매수보다 주의·회피 신호." },
            { term: "워크포워드 백테스트", desc: "지평별 표본외 성과(거래비용 반영, look-ahead 차단). 신호 모델을 이벤트유형/유의유형/거시국면/가격모멘텀/결합/LLM방향 중에서 골라 비교합니다." },
            { term: "신뢰도 캘리브레이션", desc: "“신뢰도 0.7 예측이 실제로 ~70% 맞나?”를 구간별로 점검. 과신/과소신뢰 여부, ECE·Brier 점수." },
            { term: "거시 국면 분해", desc: "거시 신호를 시리즈별로 따로 백테스트 — 엣지가 특정 시리즈에 몰리면 진짜 거시효과, 다 비슷하면 캘린더 프록시일 뿐." },
          ],
        },
      ],
    },
    {
      id: "macro",
      title: "거시 — 왜 필요한가",
      role: "경제지표(물가·고용·금리…)가 시장 예상과 **얼마나 다르게** 나왔는지를 모아 봅니다. 개별 종목·사건이 아니라, 그것들이 거래되는 **배경 국면**을 보는 탭입니다.",
      blocks: [
        {
          kind: "p",
          text: "시장 전체 분위기를 바꾸는 것은 발표값 자체가 아니라 **예상과의 차이(서프라이즈)**입니다 — 예상대로면 이미 가격에 반영돼 있어 안 움직이고, 벗어날 때만 움직입니다. 그래서 급락·이벤트를 해석할 때 “지금 배경이 우호적인가, 위축인가”를 함께 보게 해 줍니다. 통계탭의 거시 국면 백테스트 모델이 실제로 이 데이터를 신호로 씁니다.",
        },
        {
          kind: "defs",
          items: [
            { term: "발표값", desc: "실제로 발표된 지표 수치." },
            { term: "예상값", desc: "발표 전 시장 기대치. 컨센서스(전문가 합의)가 있으면 그것을, 없으면 추세 기준선 예측을." },
            { term: "서프라이즈 (σ)", desc: "(발표값 − 예상값) ÷ 과거 변동성. +면 예상보다 좋게/높게, −면 나쁘게/낮게. σ 단위는 “평소 오차의 몇 배냐”라, 물가·고용처럼 단위가 다른 지표를 같은 잣대로 비교하게 해 줍니다." },
          ],
        },
      ],
    },
    {
      id: "personal",
      band: "그 밖에",
      title: "가계부 · 통장관리",
      role: "주식 분석과 별개인 개인 금융 유틸리티입니다(로그인 필요).",
      blocks: [
        {
          kind: "list",
          items: [
            "**가계부**: 비밀번호 걸린 카드 명세서 PDF를 올리면 지출을 카테고리별로 정리하고, 상위 카테고리·최다 지출을 그래프로 보여줍니다.",
            "**통장관리**: 은행 거래내역 PDF를 올려 입출금을 정리합니다. 키워드 규칙으로 카테고리를 자동 재분류할 수 있습니다.",
          ],
        },
      ],
    },
    {
      id: "admin",
      title: "관리자",
      role: "관리자 계정만 보입니다. 사용자와 탭 노출 권한을 관리합니다 — 계정별로 어떤 탭을 볼 수 있는지 제어할 수 있습니다.",
      blocks: [],
    },
    {
      id: "workflows",
      band: "활용",
      title: "추천 사용 흐름",
      role: "상황별로 이렇게 이어서 보면 됩니다.",
      blocks: [
        {
          kind: "steps",
          title: "아침 시장 점검",
          items: [
            "**추천종목**에서 ‘우선 검토’부터 훑고, 이유 문장을 읽습니다.",
            "**급락**에서 진단(지속 악재/원인 미상/과잉반응)으로 성격을 나눕니다.",
            "눈에 걸린 종목은 **이벤트 상세**로 들어가 검증신호·근거를 확인합니다.",
            "계속 볼 종목은 **☆ 관심종목**에 넣어 알림을 받습니다.",
          ],
        },
        {
          kind: "steps",
          title: "특정 종목이 궁금할 때",
          items: [
            "**검색**에서 티커/회사명으로 찾습니다.",
            "데이터가 없으면 **공시 분석**을 실행해 이벤트를 만듭니다(로그인).",
            "종목 타임라인에서 상승·하락 요인과 종목 판정을 봅니다.",
            "모델이 틀렸으면 **검토·수정**으로 교정 — 통계에 반영됩니다.",
          ],
        },
        {
          kind: "steps",
          title: "“이 신호를 믿어도 되나” 판단",
          items: [
            "**통계 → 검증된 신호**로 그 사건유형이 유의한지 확인합니다.",
            "**백테스트**로 표본외 성과(순수익·적중률·IC)를 봅니다.",
            "**캘리브레이션**으로 모델 신뢰도가 실제 정확도와 맞는지 봅니다.",
          ],
        },
      ],
    },
    {
      id: "limits",
      title: "한계와 주의",
      role: "정직하게 알고 쓰세요. 이 도구가 **하지 않는 것**들입니다.",
      blocks: [
        {
          kind: "list",
          items: [
            "**상승 신호가 없습니다.** 검증된 신호는 전부 음(−) — 어떤 화면도 “오른다”를 단정하지 않습니다.",
            "**가격 예측이 아닙니다.** 과거 사건 뒤 평균 움직임(드리프트)일 뿐, 다음에도 그렇다는 보장은 없습니다.",
            "**최근 사건은 수익률이 비어 있을 수 있습니다.** D+N 기간이 지나야 계산됩니다.",
            "**가격 신선도를 확인하세요.** ‘오래됨’ 태그가 붙은 값은 실제 판단 전 갱신이 필요합니다.",
            "**상장폐지·생존편향은 아직 반영하지 않습니다.** 살아남은 종목 위주 데이터라는 점을 감안하세요.",
            "**최종 판단은 사람의 몫입니다.** 최신 뉴스·공시를 직접 확인하고 결정하세요.",
          ],
        },
      ],
    },
  ],
};

const en: GuideDoc = {
  eyebrow: "User Handbook",
  title: "MarketTrace User Guide",
  lede: "MarketTrace pulls structured **events** out of official filings, measures how those events actually moved the market, and orders instruments by which deserve a look first. This guide explains when and how to read each screen.",
  thesis:
    "One thing up front — MarketTrace is a **review-and-caution tool, not a buy recommender**. Every statistically validated signal so far points **negative**, so the system never asserts a stock will rise. Every screen exists to help you decide whether an instrument or event needs careful scrutiny.",
  tocLabel: "Contents",
  footer:
    "Hover any number, header, or badge in the app to get the same explanation in place. This guide follows the product's own UI wording.",
  sections: [
    {
      id: "concepts",
      band: "Start here",
      title: "Five core concepts",
      role: "Understand these five and every screen becomes readable. Throughout the app, **hovering** a number, header, or badge shows the same explanation in place.",
      blocks: [
        {
          kind: "defs",
          items: [
            {
              term: "① Event",
              desc: "One structured event an LLM extracted from a filing (SEC EDGAR / OpenDART). Each carries a **direction** (positive/negative/neutral), **type**, **confidence**, **surprise**, **novelty**, and **source reliability**. The LLM only extracts; all return math lives in separate numeric modules.",
            },
            {
              term: "② Abnormal return",
              desc: "The instrument's actual return minus the market (index) return over the same window. It strips out the overall market move so you see **only the effect of this event**. Measured at D+1 / 5 / 20 / 60 trading days after the filing.",
            },
            {
              term: "③ Validated signal",
              desc: "Only event types with enough samples (n≥5) and a mean distinguishable from zero (p<0.05) count as validated. **Every validated signal so far is negative** — there is no bullish signal yet.",
            },
            {
              term: "④ Model vs history",
              desc: "The model's (LLM's) read compared against the event type's validated historical direction. Match = Confirmed, opposite = Conflict, history exists but the model is neutral = Signal.",
            },
            {
              term: "⑤ Drift",
              desc: "The average abnormal return following a given event type. Rankings, drops, and instrument leans use this drift weighted by confidence and recency.",
            },
          ],
        },
      ],
    },
    {
      id: "colors",
      title: "Color & badge conventions",
      role: "The whole app speaks one color language. Color alone tells you direction and how much caution is warranted.",
      blocks: [
        {
          kind: "chips",
          label: "Direction (which way the event points)",
          items: [
            { text: "positive", tone: "pos" },
            { text: "negative", tone: "neg" },
            { text: "neutral", tone: "mut" },
          ],
        },
        {
          kind: "chips",
          label: "Validated-signal badge",
          items: [
            { text: "Conflict", tone: "warn" },
            { text: "Confirmed", tone: "pos" },
            { text: "Signal", tone: "acc" },
          ],
        },
        {
          kind: "p",
          text: "**Conflict** = model direction is opposite to validated history (look again). **Confirmed** = match. **Signal** = a significant history exists but the model read neutral. No badge means there is no validated signal for this type yet.",
        },
        {
          kind: "chips",
          label: "Drop diagnosis",
          items: [
            { text: "Persistent risk", tone: "warn" },
            { text: "Unexplained drop", tone: "mut" },
            { text: "Possible overreaction", tone: "acc" },
          ],
        },
        {
          kind: "p",
          text: "‘Possible overreaction’ is blue, not green — it marks a rebound **candidate**, not an assured rise, and the color says so on purpose.",
        },
      ],
    },
    {
      id: "search",
      band: "Everyday screens",
      title: "Search — find instruments · analyze new ones",
      role: "Find a stock by ticker, name, or alias. If a company isn't in the data yet, you can **run filing analysis from just its name**.",
      blocks: [
        {
          kind: "list",
          items: [
            "Typing searches automatically. Korea recognizes a numeric code (e.g. 005930); the US recognizes a ticker (e.g. AAPL).",
            "Click a result's **ticker** for the instrument timeline; the count on the right shows whether it has data.",
            "If there's no match or you want a fresh run, use **Analyze filings** with market/ticker/name to start extraction. New events appear in Events when it finishes.",
          ],
        },
        {
          kind: "note",
          text: "**Login required.** Running analysis needs an account. Private companies such as SpaceX are not supported.",
        },
      ],
    },
    {
      id: "picks",
      title: "Picks — what to look at first",
      role: "Sharp-drop stocks ordered by **which deserve review first**, combining recent price moves, recent company events, and how similar past events played out. Split into domestic and overseas.",
      blocks: [
        {
          kind: "chips",
          items: [
            { text: "Review first", tone: "acc" },
            { text: "Needs checking", tone: "mut" },
            { text: "Low priority", tone: "mut" },
          ],
        },
        {
          kind: "list",
          items: [
            "Each stock spells out **why it appears** (drawdown, price freshness, recent events, factors) in plain sentences — not picked on price alone.",
            "Rule: if any stock is down **15%+** from its recent high, show all of them; otherwise show the 5 largest relative drops.",
          ],
        },
        {
          kind: "note",
          tone: "warn",
          text: "**This list is not a promise that a stock will rise.** It is a review order. Read each reason and check fresh news / filings before deciding.",
        },
      ],
    },
    {
      id: "events",
      title: "Events — the list and the detail",
      role: "Every event **grouped by company**. This is the system's central screen.",
      blocks: [
        {
          kind: "list",
          items: [
            "Pick a market with the **Domestic (KR) / Overseas (US)** tabs, and filter by ticker/company/type/direction in the search box.",
            "Signal filters: All / Conflicts only / Needs review / Validated only — ‘Needs review’ is the queue of conflicts a human hasn't handled.",
            "Each row: type · direction · signal badge · **confidence %** · date. Hover the % or the badge for its meaning. ‘✓ Reviewed’ marks human-checked events.",
          ],
        },
        {
          kind: "defs",
          items: [
            { term: "Validated-signal card", desc: "How this event type has historically moved the market (per-horizon mean abnormal return, t-stat, p-value, sample size) and whether that agrees or conflicts with the model's read." },
            { term: "Review & correct", desc: "(When logged in) fix the model's direction/type/company/confidence. Direction/type edits hit the stats immediately; a company change refetches prices and recomputes returns." },
            { term: "Score components", desc: "Confidence, surprise, novelty, source reliability as 0–100% bars. The ? next to the title defines each." },
            { term: "Abnormal-return chart", desc: "Abnormal / raw / market / sector-adjusted returns per horizon. **If empty**, the horizons haven't elapsed yet or price data hasn't been collected (not an error)." },
            { term: "Evidence · industries · channels", desc: "The sentences the LLM cited as its basis, plus related industry and distribution-channel tags." },
          ],
        },
      ],
    },
    {
      id: "rankings",
      title: "Rankings — comparing instruments",
      role: "Every instrument sorted by its **confidence- and recency-weighted validated drift** — a cross-stock view. The **most cautionary names sit at the top** (recent, high-confidence events count more; half-life 180 days).",
      blocks: [
        {
          kind: "defs",
          items: [
            { term: "Lean", desc: "Overall direction from validated history — Caution · Favorable · Mixed." },
            { term: "Weighted drift", desc: "Post-event average returns of validated events, summed weighted by confidence and recency. **This is the sort key.**" },
            { term: "Simple mean", desc: "The same events averaged with no weighting. Compare to the weighted drift to see how much recency/confidence changed things." },
            { term: "Validated", desc: "Count of events carrying a significant validated signal (n≥5, p<0.05)." },
            { term: "Conflicts", desc: "Events where the model's direction is opposite to history. The number in parentheses is how many are still unreviewed." },
            { term: "Top factor", desc: "The event type contributing most to the weighted drift, with its average post-event return." },
          ],
        },
      ],
    },
    {
      id: "screener",
      title: "Drops — drawdown screener",
      role: "Stocks down **15%+** from their 20-day high, diagnosed against validated event history.",
      blocks: [
        {
          kind: "defs",
          items: [
            { term: "Persistent risk", desc: "Recent event(s) + a validated-negative lean — the fall fits this name's history; caution likely continues." },
            { term: "Unexplained drop", desc: "No recent event in the data explains the fall. An observation, not a signal — find the cause first." },
            { term: "Possible overreaction", desc: "Recent event(s) but no validated-negative basis. A rebound **candidate** pending backtest validation (not a buy call)." },
          ],
        },
        {
          kind: "list",
          items: [
            "**Rebound backtest** panel: “does buying after such a drop pay off?” — fixed rule, out-of-sample, net of costs. Stays an ‘observation’ when data is thin.",
            "**Include stale prices** checkbox brings in instruments whose prices aren't fresh (marked ‘stale’).",
          ],
        },
      ],
    },
    {
      id: "watchlist",
      band: "Your instruments",
      title: "Watchlist · Alerts",
      role: "Keep the instruments you care about, and get notified when something notable happens.",
      blocks: [
        {
          kind: "list",
          items: [
            "Add with the **☆ button** on the Events list, an instrument page, or Rankings (login required).",
            "Two alert kinds: **Conflict** (model direction conflicts with validated drift) · **Significant** (a validated significant event type). Check the bell in the header and ‘Mark all read’.",
          ],
        },
      ],
    },
    {
      id: "stats",
      band: "Evidence & validation",
      title: "Stats — why you can trust the system",
      role: "This screen answers “can I trust this tool?” It shows the **performance of the methodology as a whole**, not a single stock.",
      blocks: [
        {
          kind: "defs",
          items: [
            { term: "Reaction stats", desc: "Heatmap of mean abnormal return by event type × horizon (green up, red down, n = samples). **Click a cell** to expand the actual filings behind that average." },
            { term: "Validated signals", desc: "Only types passing n≥5, p<0.05. All negative so far — caution/avoid rather than buy." },
            { term: "Walk-forward backtest", desc: "Out-of-sample performance per horizon (net of costs, look-ahead blocked). Compare signal models: event-type history / significant only / macro regime / price momentum / combined / LLM direction." },
            { term: "Confidence calibration", desc: "“Does a 0.7 confidence actually hit ~70%?”, binned by band — over/under-confidence, ECE and Brier score." },
            { term: "Macro regime decomposition", desc: "The macro signal backtested per series — if the edge concentrates in one series it's real macro content; if all look alike it's just a calendar proxy." },
          ],
        },
      ],
    },
    {
      id: "macro",
      title: "Macro — why it's here",
      role: "How far economic releases (inflation, jobs, rates…) landed from expectations. Not individual stocks or events, but the **regime backdrop** they trade against.",
      blocks: [
        {
          kind: "p",
          text: "What shifts the overall market mood isn't the raw figure but **how it differs from expectations (the surprise)** — an in-line print is already priced in and moves nothing; only a miss moves the market. So it lets you read drops and events against “is the backdrop favorable or risk-off right now?” The Stats tab's macro-regime backtest actually uses this data as a signal.",
        },
        {
          kind: "defs",
          items: [
            { term: "Released", desc: "The actual figure that was published." },
            { term: "Expected", desc: "What the market anticipated. Uses consensus (pooled expert forecast) when available, otherwise a trend baseline." },
            { term: "Surprise (σ)", desc: "(released − expected) ÷ historical volatility. Positive = better/higher than expected, negative = worse/lower. The σ unit means “how many times the usual wobble”, so indicators with different units compare on one scale." },
          ],
        },
      ],
    },
    {
      id: "personal",
      band: "Also here",
      title: "Ledger · Passbook",
      role: "Personal-finance utilities, separate from the stock analysis (login required).",
      blocks: [
        {
          kind: "list",
          items: [
            "**Ledger**: upload a password-protected card-statement PDF to organize spend by category, with top categories and biggest spends charted.",
            "**Passbook**: upload a bank-transaction PDF to organize in/out flows. Keyword rules can auto-recategorize entries.",
          ],
        },
      ],
    },
    {
      id: "admin",
      title: "Admin",
      role: "Visible to admin accounts only. Manage users and per-account tab visibility — control which tabs each account can see.",
      blocks: [],
    },
    {
      id: "workflows",
      band: "Putting it together",
      title: "Suggested workflows",
      role: "Chain the screens like this, depending on your goal.",
      blocks: [
        {
          kind: "steps",
          title: "Morning market check",
          items: [
            "Scan **Picks** from ‘Review first’ down, reading the reason sentences.",
            "Use **Drops** to sort by diagnosis (persistent risk / unexplained / overreaction).",
            "Open **event detail** for anything that catches your eye to check the validated signal and evidence.",
            "Add names worth following to your **☆ Watchlist** for alerts.",
          ],
        },
        {
          kind: "steps",
          title: "Investigating a specific stock",
          items: [
            "Find it by ticker/name in **Search**.",
            "If there's no data, run **Analyze filings** to create events (login).",
            "Read its upside/downside factors and lean on the instrument timeline.",
            "If the model is wrong, fix it with **Review & correct** — it feeds the stats.",
          ],
        },
        {
          kind: "steps",
          title: "Deciding whether to trust a signal",
          items: [
            "Check **Stats → Validated signals** to confirm the event type is significant.",
            "Check the **backtest** for out-of-sample performance (net return, hit rate, IC).",
            "Check **calibration** to see if the model's confidence matches actual accuracy.",
          ],
        },
      ],
    },
    {
      id: "limits",
      title: "Limits & cautions",
      role: "Use it with eyes open. Here is what this tool **does not** do.",
      blocks: [
        {
          kind: "list",
          items: [
            "**There is no bullish signal.** Every validated signal is negative — no screen asserts a rise.",
            "**It is not a price prediction.** It's the average move after past events (drift), with no guarantee the next one repeats.",
            "**Recent events may show empty returns.** They compute only after the D+N windows elapse.",
            "**Check price freshness.** Values tagged ‘stale’ need refreshing before you act.",
            "**Delisting / survivorship bias isn't modeled yet.** The data leans toward survivors.",
            "**The final call is yours.** Confirm fresh news and filings and decide for yourself.",
          ],
        },
      ],
    },
  ],
};

export function getGuide(lang: Lang): GuideDoc {
  return lang === "ko" ? ko : en;
}
