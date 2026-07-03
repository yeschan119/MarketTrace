---
description: Render 배포 서버(api.miffy178.com / miffy178.com) 직접 스모크 테스트
argument-hint: "[API_BASE] [WEB_BASE] — 생략 시 prod"
allowed-tools: Bash(bash scripts/render-test.sh:*), Bash(./scripts/render-test.sh:*)
---
사용자가 `/render-test $ARGUMENTS` 를 실행했다. **로컬 코드가 아니라 Render에 배포된 실제
서버**를 직접 스모크 테스트하는 명령이다.

`bash scripts/render-test.sh $ARGUMENTS` 를 실행하라. (인자 없으면 prod 기본값
`https://api.miffy178.com` / `https://miffy178.com`. PR/스테이징 프리뷰를 테스트하려면
`/render-test <API_URL> [WEB_URL]` 로 URL을 넘긴다.)

스크립트가 하는 일 — 배포가 실제로 동작하는지 라이브 계약 검증:
- 백엔드 워밍업(Render 무료티어는 idle 후 spin-down → 첫 요청 콜드스타트, 최대 90s×5회 재시도)
- `/health` 200, `/events`·`/stats/event-types`·`/macro/observations` 비어있지 않음
- `/stats/significance` 유의 버킷 수(p<0.05·n≥5) 리포트
- `/stats/backtest?model=event_type_history` 5일 순수익, `llm_direction` 200, 미지 모델 400 거부
- 프론트 `/`·`/stats` 리다이렉트 따라가 200

실행 후:
- 결과를 간결히 요약하라 — PASS/FAIL 개수, 실패가 있으면 어떤 체크가 왜 깨졌는지, 그리고
  주요 지표값(events 건수, 유의 버킷 수, 5일 net 수익률).
- **콜드스타트로 인한 첫 실패와 진짜 회귀를 구분**하라: 워밍업조차 실패하면 서비스가 자거나
  배포가 죽은 것이니 재실행을 제안한다. 데이터 관련 실패(events 0건 등)면 적재(`markettrace-ingest`)가
  필요하다는 뜻이다.
- 종료코드 0=전부통과, 1=하나이상 실패. 실패 시 근본 원인을 추정해 다음 행동을 제안하라.

이 명령은 읽기 전용(GET/curl)이라 배포 상태를 바꾸지 않는다 — 안전하게 반복 실행 가능.
