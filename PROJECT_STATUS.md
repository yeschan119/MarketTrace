# MarketTrace — 프로젝트 현황

> 최종 업데이트: 2026-07-04
> 설계 문서: [stock-analysis-system-blueprint.md](./stock-analysis-system-blueprint.md)
> 상세 로드맵: [plans/roadmap.html](./plans/roadmap.html)

공시 → 구조화된 사건 → 시장조정 이상수익률을 자동 계산하고, 거시지표 surprise까지
같은 사건 모델로 다루는 시스템. **1~3단계 완료, 4단계(신호·검증) ~90%, 5단계(사용자) ~76%.**
코퍼스 461건 완주로 검정력 확보 → **방향 A(측정·검증 우선) 검증 통과**: 유의 사건유형 9버킷,
워크포워드 백테스트 5일 순수익 +2.1%(표본외). 종목별 매수판단 화면(종합 판정 + 상승·하락 요인 분해)까지
완료 → 남은 트랙은 대부분 **데이터 수집·수동 라벨링·알림 인프라** 선행.

> ⚠️ **상태 확인은 항상 라이브 API 먼저** (`curl https://api.miffy178.com/events | jq length`).
> 정적 문서는 stale해지기 쉬움 — 실제로 이 파일이 6/16 "8건"에서 낡은 채로 방치됐었음.

---

## 1. 배포 현황

| 서비스 | URL | 런타임 | 비고 |
|---|---|---|---|
| 백엔드 (FastAPI) | https://api.miffy178.com | Python 3.12 / Render free | `alembic upgrade head && uvicorn` |
| 프론트엔드 (Next.js) | https://miffy178.com | Node / Render free | EN/KR 토글 |
| DB | Render Postgres (free) | — | `macro_observations`, `events`, `outcomes` 등 |

**설정 키 (Render 대시보드, `sync: false`)**: `OPENAI_API_KEY`, `TIINGO_API_KEY`,
`OPENDART_API_KEY`, `FRED_API_KEY`, `ADMIN_USERNAME`/`ADMIN_PASSWORD`/`AUTH_SECRET`,
`SEC_USER_AGENT`.

> ⚠️ **배포는 데이터를 채우지 않는다.** startCommand는 마이그레이션+서버 기동만 한다.
> 데이터 적재는 로그인 후 **웹 UI의 Ingest 버튼**(`POST /ingest`, 인증 필요)으로만 발생.

---

## 2. 블루프린트 단계별 진행

| 단계 | 상태 | 내용 |
|---|---|---|
| **1. 데이터 기반** | ✅ 완료 | 종목 마스터, 가격(Tiingo/US·Naver/KR), 공시(SEC EDGAR/OpenDART), 원문 저장·중복제거 |
| **2. 사건 엔진** | ✅ 완료 | LLM 사건 추출(gpt-4o-mini), 유형/방향/채널/기간, novelty, 분류 F1 eval |
| **3. 영향 측정** | ✅ 완료 | 시장·섹터 조정 이상수익률(1/5/20/60일), `event_impacts`, 거시 surprise(FRED/ALFRED) |
| **4. 신호와 검증** | 🟡 ~90% | 유의성 t검정 + 워크포워드 백테스트(거래비용) + **6개 신호모델 비교**(가격 모멘텀 추가·실측 한계적) + 거시 분해 + calibration + 검증신호 개별 노출(충돌 판정). 검증 통과. 남음(데이터 선행): 펀더·수급 모델·상폐 모델링 |
| **5. 사용자 기능** | 🟡 ~82% | 타임라인·상세·`/stats` + 사건 단위 검증신호 결합·검토 큐 + 종목별 매수판단 화면(판정+요인) + **종목 간 랭킹(확신도·최근성 가중)**. 남음: 관심종목 알림 |

---

## 3. 현재 데이터 상태 (프로덕션, 2026-07-03 라이브 API 확인)

- **Events: 461건** — KR 253 · US 208 (earnings 68 · regulatory 59 · insider 54 · shareholding_change 16 · debt_offering 15 …)
- **Macro: 4종 정상** — CPIAUCSL / UNRATE / FEDFUNDS / DGS10, surprise 점수 포함 ✅
- **유의 사건유형 9버킷** (`/stats/significance`, p<0.05 · 표본충분) — 전부 **음(−)** 초과수익 드리프트:
  - `insider_trading_report` 5일 **−6.6%** (t=−5.8, p<1e-6), 1일 −1.5%
  - `regulatory_action` 5일 −3.8%, 1일 −1.2% · `earnings_release` 5일 −1.8%, 20일 −3.1% · `debt_offering` 20일 −4.3%
- **백테스트 — 5모델** (`/stats/backtest?model=`, look-ahead 차단·거래비용 반영, 표본외):
  - `significant_event_type`(유의 유형만 매매) 5일 순 **+4.4%**·적중 68% (매매 200→56건, 정밀도↑) ← 최고
  - `event_type_history` 5일 순 **+2.1%**·적중 64.5%·IC 0.12
  - `macro_surprise`/`combined` — 넓게 커버하나 **거시 IC는 캘린더/국면 프록시로 판명**(아래)
  - `llm_direction` 적중<50%·순손실 → 배제
- **거시 분해** (`/stats/macro-decomposition`): 거시 국면 신호를 시리즈별로 백테스트 → D+5 IC가 CPI·금리·실업·10Y **모두 0.12~0.21로 동일**, D+60 음전환 → 특정 거시효과 아니라 **캘린더/시장국면 프록시**로 확증. ⇒ 신뢰 신호는 **사건 기반**만.

---

## 4. 다음 단계 — 남은 트랙은 데이터·인프라 선행

> 검증신호 전 층위 노출(사건·목록·통계·종목) + 사람 검토 루프 + 종목 매수판단(판정+요인) + **종목 간 랭킹(확신도·최근성 가중)**까지 완료.
> 순수 코드로 낼 수 있는 가시적 가치는 대체로 소진 → 남은 건 데이터 수집·수동 라벨링·외부 인프라.

1. **잔여 SignalModel (데이터 선행)** — 펀더멘털·수급을 동일 `SignalModel`로. **재무·수급 데이터 수집 선행 필요**(가격 모멘텀은 완료, 실측 한계적). 상폐는 delisted_at 미채움·provider 미수집으로 모델링 불가 → KRX/OpenDART 상폐목록 수집 선행.
2. **골드셋 확대 → 라이브 F1** ✅ 1차 완료 — 정규 택소노미(110→18계열) + 정적 골드셋 6→26건 + 배포 추출기 오프라인 F1(`markettrace-eval-live`, 실 이벤트 97건·독립 어노테이터 2인 검수 **일치도 97.9%**). **베이스라인 77.3%(75/97)** → 오류패턴(macro/regulatory 과적용·insider↔ownership·특수관계인) 도출 → 추출 프롬프트/스키마 교정 → **라이브 재추출 실측 91.8%(89/97)·+14.5%p** (gpt-4o-mini, 명확케이스 회귀 0). 잔여 8건 중 6건은 gold='other' 본질 모호. ⚠️ 개선은 **향후 추출만** 적용(기존 486건은 재적재 시 반영). 엔티티 교정 UI + `original_primary_instrument_id` 스냅샷 + outcomes 재계산은 구현됨. 남음: entity_linking F1 독립 라벨링 운영(gold_ticker/gold_entities sample 필요)·기존코퍼스 재추출.
3. **관심종목 알림** — 알림 인프라(Telegram 등) 필요.
4. ~~종목 매수판단 정교화(확신도·최근성 가중, 종목 간 랭킹)~~ — ✅ 완료(`/rankings` + `GET /stats/instrument-ranking`).

평가 지표(§8): IC, 방향 적중률, 시장·섹터 조정 이상수익률, Sharpe/MDD,
신뢰도 구간별 실제 적중률(calibration: `confidence=0.7` ≈ 실제 70%).

**적재 트리거**: `markettrace-ingest` CLI(동기 포그라운드, 멱등) — Render Shell에서 실행하면
prod DATABASE_URL/키가 이미 있음. 무료티어 BackgroundTask spin-down 회피용으로 도입됨.

---

## 6. 이번 세션에 한 일 (2026-07-04 — 검증신호 전층 노출 → 검토 루프 → 종목 매수판단)

| 커밋 | 내용 |
|---|---|
| `fb118f9` | 검증신호 노출 — **이벤트 상세**: 그 유형의 검증 실측 vs LLM 방향 일치/충돌 배너 |
| `a6a891c` | 검증신호 노출 — **이벤트 목록**: 행별 배지 + "충돌만" 필터(판정 로직 공유 유틸로 추출) |
| `86aeac2` | **Phase 2 검토·수정 UI** — `PATCH /events/{id}`(auth) + 편집폼, 방향/유형/신뢰도 교정, 원본 스냅샷(마이그레이션 0006), EventImpact 재빌드로 통계 즉시 반영 |
| `99d6590` | **검토 큐** — `EventSummary.reviewed_at` 노출, ✓검토됨 마커 + "미검토 충돌" 필터(실제 검토 대기열) |
| `7abf9de` | **종목 판정 카드** — 종목 뷰에 검증신호 집계(주의/우호/혼조 + 평균 드리프트·검증사건수·충돌수) |
| `eeb07fd` | **가격 모멘텀 모델(6번째)** — 사건 전 20일 모멘텀 조건부. 실측 D+5 net +0.99%·IC 0.15 → 한계적, 채택 안 함 |
| `1e5e12f` | **상승·하락 요인 분해** — 종목이 왜 오르내리나(유형별 검증 드리프트 버킷) |
| `ff2c310` | **종목 간 랭킹 + 매수판단 정교화** — 단순평균→확신도×최근성 가중(반감기 180일). `impact/instrument_ranking.py`(ORM-free·14 테스트) + `GET /stats/instrument-ranking` + `/rankings` 페이지. 실측 38종목 랭킹 |
| `60e1a2d` | **감사(ralph)** — roadmap·blueprint 정합성 점검(독립 코드 리뷰 2회). 드리프트 없음. AC2/AC3 문구만 교정(occurred_at nullable·ledger 별개 LLM경계) |
| `5a07bcb` | **골드셋 확대 + 라이브 F1** — 정규 택소노미(110→18) + 골드셋 6→25 + `markettrace-eval-live`(배포 추출기 오프라인 F1). 첫 실측 85.7%·macro F1 0.771, 오류패턴 도출. 513 테스트 |
| `bb85d13` | 로드맵/status 갱신 |

- 백엔드 446 테스트 통과·ruff 클린, 프론트 tsc·build 통과
- **상폐 모델링 조사 → 데이터 부재로 보류**: `delisted_at` 미채움·provider 상폐 미수집·drop 3원인 구분 불가 → KRX/OpenDART 상폐목록 수집이 선행돼야 하는 별도 트랙
- 아크: 검증신호 전 층위 노출(사건·목록·통계·종목) → 사람 검토 루프·검토 큐 → 종목 매수판단(판정+요인) → 가격 모멘텀(한계적)

---

## 7. 운영 메모

- **Ingest 트리거**: 웹 로그인(admin) → Ingest 버튼. 멱등(기존 문서 skip), 필링별 commit → 중단돼도 재클릭으로 재개.
- **소요 시간**: 첫 코퍼스 적재는 8-K 다수 × LLM 추출이라 수 분. 무료 티어 타임아웃 시 여러 번 클릭.
- **상태 확인 엔드포인트**: `/health`, `/events`, `/stats/event-types`, `/macro/observations`, `/instruments/{id}/timeline`.
- **재배포 확인**: Render → backend 서비스 → Deploys에서 최신 커밋 해시 확인(이전에 backend 미배포로 corpus가 안 올라간 정황 있었음).
