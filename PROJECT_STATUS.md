# MarketTrace — 프로젝트 현황

> 최종 업데이트: 2026-07-03
> 설계 문서: [stock-analysis-system-blueprint.md](./stock-analysis-system-blueprint.md)
> 상세 로드맵: [plans/roadmap.html](./plans/roadmap.html)

공시 → 구조화된 사건 → 시장조정 이상수익률을 자동 계산하고, 거시지표 surprise까지
같은 사건 모델로 다루는 시스템. **1~3단계 완료, 4단계(신호·검증) ~60%.**
코퍼스 461건 완주로 검정력 확보 → **방향 A(측정·검증 우선) 검증 통과**: 유의 사건유형 9버킷,
워크포워드 백테스트 5일 순수익 +2.1%(표본외). 초점은 이제 **검증된 신호의 결합·UI 노출**.

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
| **4. 신호와 검증** | 🟡 ~60% | 유의성 t검정·워크포워드 백테스트(거래비용 반영) 완성·가동, 코퍼스 461건 검증 통과. 남음: 신호 결합·잔여 모델·UI 노출 |
| **5. 사용자 기능** | 🟡 일부 | 사건 타임라인·`/stats`·Macro 탭·관심종목 일부 구현, 알림/시나리오/신호 대시보드 미구현 |

---

## 3. 현재 데이터 상태 (프로덕션, 2026-07-03 라이브 API 확인)

- **Events: 461건** — KR 253 · US 208 (earnings 68 · regulatory 59 · insider 54 · shareholding_change 16 · debt_offering 15 …)
- **Macro: 4종 정상** — CPIAUCSL / UNRATE / FEDFUNDS / DGS10, surprise 점수 포함 ✅
- **유의 사건유형 9버킷** (`/stats/significance`, p<0.05 · 표본충분) — 전부 **음(−)** 초과수익 드리프트:
  - `insider_trading_report` 5일 **−6.6%** (t=−5.8, p<1e-6), 1일 −1.5%
  - `regulatory_action` 5일 −3.8%, 1일 −1.2% · `earnings_release` 5일 −1.8%, 20일 −3.1% · `debt_offering` 20일 −4.3%
- **백테스트** (`/stats/backtest`, look-ahead 차단·거래비용 반영):
  - `event_type_history` 5일 적중 **64.5%** · 순수익 **+2.1%** · IC 0.12 (표본외)
  - `llm_direction`(LLM 방향 신호)은 적중<50%·순손실 → 경험적 사건유형 통계가 우월

---

## 4. 다음 단계 — 4단계 마무리 + 신호 노출

> 검증(방향 A)은 통과. 이제 검증된 신호를 결합하고 사용자 매수판단에 노출한다.

1. **검증된 신호 UI 노출** — `/stats/significance`·`/stats/backtest`를 매수판단 대시보드에(Phase 5). 유의 사건유형·표본외 성과 표시
2. **신호 결합·잔여 모델** — `event_type_history`(impact/signal.py) 기준선으로 거시(surprise)·가격·수급을 동일 `SignalModel` 인터페이스로 추가 + combiner + calibration
3. **상폐 모델링** — 현재는 커버리지 보고(n_dropped_no_outcome)만. 거래정지·상장폐지를 수익률 계산에 반영
4. **사건 중요도 필터** — governance 잡무 노이즈 제거 + Phase 2 사람 검토·수정 UI

평가 지표(§8): IC, 방향 적중률, 시장·섹터 조정 이상수익률, Sharpe/MDD,
신뢰도 구간별 실제 적중률(calibration: `confidence=0.7` ≈ 실제 70%).

**적재 트리거**: `markettrace-ingest` CLI(동기 포그라운드, 멱등) — Render Shell에서 실행하면
prod DATABASE_URL/키가 이미 있음. 무료티어 BackgroundTask spin-down 회피용으로 도입됨.

---

## 6. 이번 세션에 한 일 (Macro 적재 버그 수정 + 코퍼스 도입)

| 커밋 | 내용 |
|---|---|
| `6d0f40a` | `POST /ingest`에 macro ingest 연결(FRED 키 있을 때만) + FRED 증분 조회(증분 fetch + DB 히스토리 시드) |
| `d90d18e` | DGS10(일별) ALFRED vintage-cap 초과 400 → output_type=1 fallback + 시리즈별 에러 격리 |
| `2874647` | US 대형주 5종(AAPL/MSFT/NVDA/JPM/XOM) 최근 8-K 검증 코퍼스를 `/ingest`에 추가 + SEC `forms` 필터 |
| `a223f4a` | SEC EDGAR 429 해결 — 요청 간격 throttle(0.2s) + 429/503 지수 백오프 재시도(Retry-After 존중) |

- 테스트 287개 통과, ruff 클린
- 핵심 교훈: **macro 빈 화면·코퍼스 0건의 근본 원인은 모두 "배포 ≠ 적재" + 외부 API 제약**
  (FRED vintage-cap, SEC rate-limit)이었음

---

## 7. 운영 메모

- **Ingest 트리거**: 웹 로그인(admin) → Ingest 버튼. 멱등(기존 문서 skip), 필링별 commit → 중단돼도 재클릭으로 재개.
- **소요 시간**: 첫 코퍼스 적재는 8-K 다수 × LLM 추출이라 수 분. 무료 티어 타임아웃 시 여러 번 클릭.
- **상태 확인 엔드포인트**: `/health`, `/events`, `/stats/event-types`, `/macro/observations`, `/instruments/{id}/timeline`.
- **재배포 확인**: Render → backend 서비스 → Deploys에서 최신 커밋 해시 확인(이전에 backend 미배포로 corpus가 안 올라간 정황 있었음).
