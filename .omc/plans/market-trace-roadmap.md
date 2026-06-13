# MarketTrace 개발 로드맵 & 스캐폴딩 제안

> 상태: **pending approval** (계획 단계 — 코드 미작성)
> 출처 블루프린트: `stock-analysis-system-blueprint.md`
> 작성일: 2026-06-12

---

## 0. 결정 요약 (이번 인터뷰 기준)

| 항목 | 결정 | 근거 |
|---|---|---|
| 타깃 시장 | 한국 + 미국, **추상화 우선** | provider 인터페이스로 OpenDART/SEC EDGAR 교체. 슬라이스는 한 시장으로 먼저 검증 |
| 첫 구현 범위 | **Vertical slice** (블루프린트 §11) | 공시 1건 → 기업·사건 식별 → 영향 가설 저장 → 1/5/20일 시장조정 수익률 자동 계산 |
| LLM | **Claude API + 강제 tool-use 구조화 출력** | 사건 JSON 스키마(§3) 강제, 설명가능성·재현성 확보 |
| 산출물 | 로드맵 + 스캐폴딩 제안 | 본 문서. 승인 시 실행 |
| 프론트엔드 | **Next.js (처음부터)** + FastAPI API 경계 | Phase 1부터 FastAPI를 정식 계약으로, Next.js 대시보드 동시 구축 |

---

## 1. 요구사항 요약

블루프린트의 핵심 원칙을 코드 구조로 강제한다.

1. **LLM과 수치 모델 분리** — LLM은 추출만, 수익률·이상수익률은 수치 모듈이 계산
2. **시점 정보 보존** — 모든 레코드에 `occurred_at` / `published_at` / `first_seen_at` 저장, 백테스트는 당시 가용 데이터만
3. **근거 추적** — 원문 URL, 근거 문장, 모델·버전, 분석 시각, 입력 데이터 버전, 예측 vs 실제
4. **시장 추상화** — 신규 시장 추가가 provider 한 개 구현으로 끝나야 함

---

## 2. 아키텍처 결정

### 2.1 핵심 결정: Provider 추상화 레이어

dual-market을 "둘 다 구현"이 아니라 **공통 인터페이스 + 시장별 어댑터**로 설계한다. 슬라이스는 한 시장(권장: 미국 SEC EDGAR — 인증키 불필요, 영어 NLP, bulk 제공)으로 먼저 끝까지 관통하고, OpenDART 어댑터는 같은 인터페이스를 구현해 추가한다.

```text
DisclosureProvider (Protocol)
  ├─ list_recent(since) -> list[DocumentRef]
  ├─ fetch_raw(ref) -> RawDocument        # 원문 그대로
  └─ market: str

PriceProvider (Protocol)
  ├─ get_ohlcv(instrument, start, end) -> DataFrame
  └─ market: str
```

- `SecEdgarProvider` (US) → 슬라이스에서 우선 구현
- `OpenDartProvider` (KR) → 동일 인터페이스로 후속
- `registry.py`가 `market -> provider` 매핑

### 2.2 LLM 경계

`nlp/event_extractor.py`만 Claude API를 호출한다. 그 외 어떤 모듈도 LLM을 부르지 않는다 (원칙 1 강제).

- 모델: 추출 기본값 **`claude-sonnet-4-6`**, 어려운 케이스 escalation 옵션 **`claude-opus-4-8`**
- 구조화 출력: Anthropic Messages API에서 **`tool_choice`로 단일 도구 강제 호출** → 사건 스키마(JSON) 보장
- 결정성: `temperature=0`, 프롬프트·모델·버전을 `events.model` / `events.model_version`에 기록
- ⚠️ 구현 착수 시 `claude-api` 스킬로 모델 ID·tool-use 파라미터 최신값 재확인 (memory cutoff 이후 변경 가능)

### 2.3 슬라이스 단계에서 의도적으로 미루는 것

블루프린트 §5는 풀스택을 제시하지만, 슬라이스 검증 전에는 도입하지 않는다.

| 미루는 것 | 슬라이스 대체 | 도입 시점 |
|---|---|---|
| Prefect | 단일 CLI 엔트리포인트 (`pipeline/vertical_slice.py`) | Phase 2 (다건 배치) |
| MLflow | `model_runs` 테이블 + 로그 | Phase 4 (신호 모델) |
| ~~프론트엔드 보류~~ | **Next.js를 Phase 1부터 구축** (결정 변경) | Phase 1 |
| TimescaleDB / S3 | PostgreSQL + 로컬 파일 객체저장 추상화 | 규모 확대 시 |
| Kafka / K8s | Docker Compose | 블루프린트 §5 명시대로 한참 뒤 |

---

## 3. 스캐폴딩 제안 (디렉터리 구조)

모노레포: Python 백엔드(`backend/`) + Next.js 프론트(`web/`).

```text
MarketTrace/
├─ docker-compose.yml          # postgres + (선택) backend/web 서비스
├─ README.md
├─ backend/
│  ├─ pyproject.toml           # Python 3.12, 의존성, ruff/pytest 설정
│  ├─ .env.example             # ANTHROPIC_API_KEY, DB_URL, SEC_USER_AGENT 등
│  ├─ alembic.ini + alembic/   # DB 마이그레이션
│  ├─ src/markettrace/
│  │  ├─ config.py             # pydantic-settings 환경설정
│  │  ├─ db/
│  │  │  ├─ models.py          # SQLAlchemy ORM (§4 테이블)
│  │  │  └─ session.py
│  │  ├─ providers/            # ★ 추상화 레이어
│  │  │  ├─ base.py            # DisclosureProvider / PriceProvider Protocol + DTO
│  │  │  ├─ sec_edgar.py       # US (슬라이스 우선)
│  │  │  ├─ opendart.py        # KR (후속)
│  │  │  └─ registry.py
│  │  ├─ storage/
│  │  │  └─ object_store.py    # 원문 보존 (로컬→S3 추상화), 해시
│  │  ├─ ingest/
│  │  │  ├─ disclosures.py     # fetch + dedup(해시) + 3시각 저장
│  │  │  └─ prices.py
│  │  ├─ nlp/
│  │  │  ├─ schemas.py         # Pydantic 사건 스키마 (§3 JSON)
│  │  │  ├─ entity_linker.py   # 문서 → instrument (entity_aliases 매칭)
│  │  │  └─ event_extractor.py # ★ 유일한 Claude API 호출 지점
│  │  ├─ impact/
│  │  │  ├─ market_model.py    # 시장·산업 수익률 제거
│  │  │  └─ returns.py         # 이상수익률 1/5/20일
│  │  ├─ pipeline/
│  │  │  └─ vertical_slice.py  # 엔드투엔드 CLI 진입점
│  │  └─ api/
│  │     ├─ main.py            # FastAPI app (CORS, OpenAPI 스키마)
│  │     ├─ schemas.py         # 응답 Pydantic 모델 (프론트 계약)
│  │     └─ routes.py          # GET /events, /events/{id}, /instruments/{id}/timeline
│  └─ tests/
│     ├─ test_providers.py     # 인터페이스 계약 테스트 (fixture 원문)
│     ├─ test_event_extractor.py # 스키마 검증 (Claude 응답 mock)
│     ├─ test_returns.py       # 이상수익률 수치 검증 (합성 가격)
│     ├─ test_api.py           # 엔드포인트 응답 스키마 (TestClient)
│     └─ test_vertical_slice.py # 전 과정 통합 (record/replay)
└─ web/                        # ★ Next.js (App Router, TypeScript)
   ├─ package.json
   ├─ next.config.ts
   ├─ src/
   │  ├─ app/                  # 라우트: /events, /events/[id], /instruments/[id]
   │  ├─ components/           # 타임라인·점수카드·차트
   │  ├─ lib/api.ts            # FastAPI 호출 (OpenAPI 타입 생성)
   │  └─ types/api.d.ts        # openapi-typescript로 백엔드 스키마 자동 생성
   └─ .env.example             # NEXT_PUBLIC_API_BASE_URL
```

> **타입 안전 계약**: FastAPI가 OpenAPI 스키마를 발행 → `openapi-typescript`로 `web/src/types/api.d.ts` 자동 생성. 백엔드 응답 스키마 변경이 프론트 타입 에러로 즉시 드러나 dual-stack 재작업 위험을 차단.

### 기술 스택 (슬라이스 확정분)

**백엔드**
- 언어: Python 3.12
- DB: PostgreSQL + SQLAlchemy 2.x + Alembic
- 설정/검증: Pydantic v2, pydantic-settings
- HTTP: httpx · 데이터 처리: Polars
- LLM: `anthropic` SDK
- API: FastAPI + uvicorn (OpenAPI 스키마 발행)
- 테스트/품질: pytest, ruff

**프론트엔드 (처음부터)**
- Next.js (App Router) + TypeScript
- 데이터 패칭: TanStack Query
- 스타일: Tailwind CSS + shadcn/ui
- 차트: TradingView Lightweight Charts(시계열 가격·이상수익률) + Recharts(점수 구성요소)
- 타입 동기화: `openapi-typescript` (FastAPI 스키마 → TS 타입 자동 생성)

**공통**
- 배포: Docker Compose (postgres + backend + web)

---

## 4. 데이터 모델 (슬라이스 최소 서브셋)

블루프린트 §4의 13개 테이블 중 슬라이스에 필요한 8개만 먼저 생성. 나머지(`fundamentals`, `macro_observations`, `features`, `signals`, `event_impacts`)는 Phase별로 추가.

| 테이블 | 슬라이스 필수 컬럼 |
|---|---|
| `instruments` | id, market, ticker, name, industry, listed_at, delisted_at |
| `entity_aliases` | instrument_id, alias, alias_type |
| `documents` | id, source, url, raw_object_key, content_hash, market, **occurred_at, published_at, first_seen_at** |
| `document_entities` | document_id, instrument_id, confidence |
| `events` | id, document_id, event_type, entities(jsonb), industries(jsonb), channels(jsonb), direction, horizon_days, surprise_score, novelty_score, source_reliability, confidence, evidence(jsonb), **model, model_version, analyzed_at** |
| `prices` | instrument_id, date, open, high, low, close, adj_close, volume |
| `outcomes` | event_id, instrument_id, horizon_days, raw_return, market_return, abnormal_return, computed_at |
| `model_runs` | id, kind, params(jsonb), data_version, created_at |

---

## 5. 개발 로드맵

### Phase 0 — 스캐폴딩 (승인 후 첫 작업)

- [ ] `backend/pyproject.toml`, `docker-compose.yml`(postgres), `.env.example`, `config.py`
- [ ] `db/models.py` §4 8개 테이블 + Alembic 초기 마이그레이션
- [ ] `providers/base.py` Protocol + DTO 정의
- [ ] `api/main.py` FastAPI 부트 + `/health`, OpenAPI 발행
- [ ] `web/` Next.js 부트스트랩 (App Router, Tailwind, TanStack Query) + `openapi-typescript` 타입 생성 파이프라인
- **완료 기준**: `alembic upgrade head` 성공, `pytest` 통과, postgres 컨테이너 기동, `web` dev 서버가 `/health`를 호출해 백엔드 연결 표시

### Phase 1 — Vertical Slice (블루프린트 §11) ★ 최우선 목표

- [ ] `SecEdgarProvider.list_recent / fetch_raw` (US, `data.sec.gov` submissions JSON)
- [ ] `ingest/disclosures.py` — 원문 보존 + content_hash 중복 제거 + 3시각 저장
- [ ] `nlp/entity_linker.py` — 문서 → instrument (CIK/ticker 매칭)
- [ ] `nlp/event_extractor.py` — Claude 강제 tool-use로 사건 스키마 추출
- [ ] `ingest/prices.py` + `impact/market_model.py` + `impact/returns.py` — 발표 후 1/5/20일 시장·산업 조정 이상수익률
- [ ] `pipeline/vertical_slice.py` — CLI로 공시 1건 → outcomes 저장까지 관통
- [ ] `api/routes.py` — `GET /events`, `/events/{id}`(사건+근거+영향), `/instruments/{id}/timeline`
- [ ] `web/` — 사건 타임라인 화면 + 사건 상세(점수 구성요소·근거 링크·1/5/20일 이상수익률 차트)
- **완료 기준**: 실제 SEC 공시 1건을 입력하면 `events` 1행 + `outcomes` 3행(1/5/20일)이 근거(URL·근거문장·모델버전) 포함해 저장되고, **Next.js 화면에서 해당 사건과 이상수익률 차트가 렌더링**된다. 통합 테스트가 record/replay로 재현 가능.

### Phase 2 — 사건 엔진 확장 (블루프린트 §7-2단계)

- [ ] `OpenDartProvider` 추가 (KR, 동일 인터페이스 — 추상화 검증)
- [ ] 다건 배치 (Prefect 도입), 동일 사건 다문서 묶기(novelty)
- [ ] 사람 검토·수정 화면 (entity/event correction)
- **완료 기준**: 기업 연결 정확도·사건 분류 macro F1 측정 가능 (§8)

### Phase 3 — 영향 측정 (블루프린트 §7-3단계)

- [ ] `event_impacts` 테이블, 사건 유형별 평균 반응·분산
- [ ] surprise feature (예상 대비 실제, FRED/ALFRED 빈티지 데이터)
- **완료 기준**: 사건별 예측과 실제 결과 자동 연결

### Phase 4 — 신호 & 검증 (블루프린트 §7-4단계)

- [ ] 펀더멘털/이벤트/거시/가격/수급 모델 분리, MLflow
- [ ] 워크포워드 백테스트 (거래비용·슬리피지·거래정지·상폐 반영)
- **완료 기준**: 표본 외 구간에서 벤치마크 대비 개선 확인 (look-ahead/survivorship bias 차단)

### Phase 5 — 사용자 기능 (블루프린트 §7-5단계)

- [ ] Next.js 제품화: 관심종목 알림, 인증, 시나리오별 상승·하락 요인, 데이터·모델 상태 대시보드
  (타임라인·사건 상세는 Phase 1에서 이미 구축됨 → 여기선 확장)

---

## 6. 수용 기준 (테스트 가능)

| # | 기준 | 검증 방법 |
|---|---|---|
| AC1 | provider 추상화로 시장 추가가 어댑터 1개로 끝난다 | `test_providers.py`가 SEC/OpenDART 양쪽에 동일 계약 테스트 통과 |
| AC2 | 모든 `documents` 행에 3시각이 NOT NULL | DB 제약 + 마이그레이션 테스트 |
| AC3 | LLM 호출이 `event_extractor.py`에만 존재 | `grep -r anthropic src/markettrace/` 결과가 nlp/만 매치 |
| AC4 | 사건 추출 결과가 Pydantic 스키마(§3)를 100% 통과 | mock 응답 + 실제 응답 스키마 검증 테스트 |
| AC5 | 이상수익률 = raw − market_return 이 합성 데이터로 정확 | `test_returns.py` 수치 단언 |
| AC6 | 슬라이스가 공시 1건 → events 1 + outcomes 3행 생성 | `test_vertical_slice.py` 통합 (record/replay) |
| AC7 | 모든 `events` 행에 model·model_version·evidence 기록 | 통합 테스트 단언 |
| AC8 | FastAPI 스키마 → `web` TS 타입 자동 생성, 불일치 시 빌드 실패 | `openapi-typescript` 생성 후 `tsc --noEmit` 통과 |
| AC9 | Next.js에서 사건 상세 + 1/5/20일 이상수익률 차트 렌더 | `/events/[id]` 화면 수동 확인 + 컴포넌트 테스트 |

---

## 7. 리스크 & 완화

| 리스크 | 영향 | 완화 |
|---|---|---|
| Look-ahead bias (블루프린트 §9) | 백테스트 과대평가 | 모든 쿼리에 as-of 시각 파라미터 강제, 3시각 저장. Phase 1부터 `first_seen_at` 기준 조회 |
| Survivorship bias | 성과 과대평가 | `instruments.delisted_at` 보존, 상폐 종목 포함 유니버스 |
| 기업행동 미반영 | 수익률 오류 | `prices.adj_close` + 수정 전후 모두 저장 |
| Claude 출력 스키마 이탈 | 파이프라인 중단 | 강제 tool-use + Pydantic 검증 + 실패 시 재시도/격리 큐 |
| 모델 ID/파라미터 변경 | 호출 실패 | 착수 시 `claude-api` 스킬 재확인, config로 외부화 |
| KRX/뉴스 재배포 라이선스 (§10) | 법적 위험 | 슬라이스는 공식 공시(SEC/OpenDART)만, 뉴스·KRX 시세는 라이선스 확인 후 |
| 중복 기사 다중 신호 | 신호 왜곡 | content_hash dedup + novelty_score |

---

## 8. 검증 절차

1. `docker compose up -d postgres && alembic upgrade head` → 스키마 생성 확인
2. `pytest -q` → 단위·통합 전부 통과 (AC1–AC7)
3. `python -m markettrace.pipeline.vertical_slice --doc <SEC accession>` → events/outcomes 행 생성 확인
4. `grep -rn "anthropic" src/markettrace/` → nlp/ 외 매치 없음 (AC3)
5. DB에서 `outcomes` 조회 → 1/5/20일 이상수익률 + 근거 메타데이터 존재 확인
6. `cd web && npm run gen:types && npx tsc --noEmit` → API 타입 동기화 확인 (AC8)
7. `npm run dev` → `/events/[id]` 접속, 사건·근거·이상수익률 차트 렌더 확인 (AC9)

---

## 9. 다음 단계

이 계획 승인 시 권장 실행 경로:

- **`/koa-speed` (ultrawork)** — Phase 0 스캐폴딩 + Phase 1 슬라이스를 병렬 에이전트로 구현
- 또는 **`/koa-loop` (ralph)** — 수용 기준(AC1–AC7) 전부 통과까지 반복 검증

승인 의사를 주시면 실행 모드로 넘기겠습니다. 슬라이스 우선 시장을 미국(SEC)이 아닌 한국(OpenDART)으로 시작하고 싶으시면 그 점도 말씀해 주세요.

---

## 10. 변경 이력 — 멀티 provider LLM & Render 배포 (2026-06-13)

슬라이스 구현 이후 추가된 작업. 두 갈래: **(A) LLM provider 추상화 확장**, **(B) Render 배포 준비**.

### 10.1 LLM provider 멀티화 (Anthropic + OpenAI)

§2.2의 "LLM 경계"는 유지하되(`event_extractor.py`만 LLM 호출), **provider를 설정으로 선택**하도록 확장.

- `config.py`
  - `llm_provider: "anthropic" | "openai"` (기본 `anthropic`) 추가
  - `openai_api_key` 추가, `extraction_model`은 `None` 기본 → provider별 기본 모델 자동 해석
    (`anthropic→claude-sonnet-4-6`, `openai→gpt-4o`)
  - 헬퍼: `resolved_extraction_model`, `active_api_key`
- `nlp/schemas.py` — 동일 `EVENT_TOOL_SCHEMA`를 두 포맷으로 노출:
  Anthropic `input_schema`(`event_tool_definition`) / OpenAI `parameters`(`event_function_definition`)
- `nlp/event_extractor.py`
  - provider 분기: `_call_anthropic`(`messages.create`+`tool_use` 파싱) / `_call_openai`(`chat.completions.create`+`tool_calls` JSON 파싱)
  - 공개 `model`/`provider` 속성 추가 → **provenance 버그 수정**
    (기존 `vertical_slice.py`가 `getattr(extractor,"model")`로 읽었으나 속성이 없어 항상
    하드코딩 `claude-sonnet-4-6`로 기록되던 문제. 이제 실제 모델 기록)
- 의존성: `openai` 추가. 테스트는 fake client라 키 없이 통과(OpenAI 경로 테스트 신설)
- **검증 완료**: 실제 OpenAI 키로 Apple 8-K(`0000320193-26-000011`) 라이브 추출 성공
  (`gpt-4o-mini-2024-07-18`, `earnings_release`/AAPL/positive)

> **§2.2 모델 정책 갱신**: "Claude API 전용" → "provider 선택형(Anthropic/OpenAI)". LLM 단일 경계 원칙(AC3)은
> `event_extractor.py` 한 곳에 호출이 모이므로 그대로 충족.

### 10.2 Render 배포 준비

- `render.yaml` (저장소 루트) — Blueprint: 관리형 **PostgreSQL + 백엔드(web) + 웹(web)** 한 번에 정의
  - 백엔드 startCommand에서 `alembic upgrade head` 자동 실행(부팅 시 스키마 생성)
  - `OPENAI_API_KEY`는 `sync: false`(대시보드 입력, git 미포함), `DATABASE_URL`은 DB에서 자동 주입
- **배포용 수정 (테스트만으론 안 드러나던 갭)**:
  - `pyproject.toml`에 `psycopg[binary]` 추가 (config은 `postgresql+psycopg`를 쓰는데 미설치였음 — 테스트는 sqlite)
  - `config.py`: `DATABASE_URL` 스킴 정규화 validator (`postgres://`·`postgresql://` → `postgresql+psycopg://`)
  - `config.py` + `api/main.py`: CORS를 `CORS_ALLOW_ORIGINS` 설정 기반으로 (기존 `localhost:3000` 하드코딩 → 운영 도메인 허용)
- **시크릿 관리 원칙**: 키는 코드/이미지/git에 두지 않고 **배포 플랫폼 시크릿 → 환경변수 주입**.
  웹의 `NEXT_PUBLIC_*`은 브라우저 번들에 노출되므로 비밀값 금지(백엔드 URL만). `.gitignore`로 `.env`·`*.db`·시크릿 차단.

### 10.3 미해결 / 후속 과제

| 항목 | 상태 | 비고 |
|---|---|---|
| 운영 가격 provider | ⚠️ 필요 | **Stooq가 JS proof-of-work 안티봇 도입** → 자동 클라이언트 차단. 라이브 슬라이스는 가격 단계에서 실패. yfinance/Alpha Vantage/Tiingo 등으로 교체 검토 |
| Instrument 시드 | ⚠️ 없음 | 콘솔 스크립트는 `markettrace-slice`뿐. 운영 DB에 instrument를 멱등 시딩하는 명령(`markettrace-seed`) 필요 |
| 운영 DB 데이터 적재 | 수동 | 권장: 로컬에서 Render Postgres **External URL**로 시딩+슬라이스 실행 |
| 무료 플랜 한계 | 참고 | Render 무료 web 콜드스타트(~50s), 무료 Postgres 90일 만료 |
