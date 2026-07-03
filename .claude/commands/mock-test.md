---
description: 최근 반영한 변경 요약 + 각각 어떻게 테스트하는지 안내 (현재 git 상태 기반)
argument-hint: "[커밋범위|기능명] — 생략 시 최근/미push 변경"
allowed-tools: Bash(git log:*), Bash(git status:*), Bash(git diff:*), Bash(git rev-list:*), Bash(git show:*)
---
사용자가 `/mock-test $ARGUMENTS` 를 실행했다. **최근 무엇을 반영했고 어떻게 테스트하는지**를
설명하는 명령이다 — 코드를 바꾸거나 테스트를 실제로 돌리는 게 아니라, 지금 상태를 읽어
"반영 내용 + 검증 방법"을 짚어주는 리허설/가이드다.

먼저 현재 상태를 파악하라(읽기 전용):
- `git status --short` — 미커밋 작업트리
- `git rev-list --left-right --count origin/main...HEAD` — push 여부(배포 반영 여부의 핵심)
- `git log origin/main..HEAD --oneline` — 아직 push 안 된 커밋(=아직 라이브 아님)
- `$ARGUMENTS` 가 있으면 그 범위/기능으로 좁힌다. 없으면 미push 커밋 + 최근 3~5개.
- 필요하면 `git show --stat <sha>` 로 무엇이 바뀌었는지 확인.

그 다음, 각 변경 묶음마다 아래 두 가지를 간결히 설명하라:

**1) 무엇을 반영했나** — 사용자 관점에서 한두 줄. 커밋 메시지를 그대로 옮기지 말고
   "이게 뭘 가능하게/바꾸게 하는지"로 번역.

**2) 어떻게 테스트하나** — 변경 성격에 맞는 구체 명령/URL. 아래 팔레트에서 해당되는 것만:
   - 백엔드 로직: `cd backend && .venv/bin/python -m pytest -q` (특정 파일이면 경로 지정),
     `.venv/bin/ruff check src tests`
   - 웹: `cd web && npx tsc --noEmit && npm run build`; 로컬 실물은 `npm run dev`
     (prod API로 보려면 `NEXT_PUBLIC_API_BASE_URL=https://api.miffy178.com npm run dev`)
   - 배포 서버 스모크: `/render-test` (또는 `bash scripts/render-test.sh`)
   - 특정 API 계약: 직접 curl 예시 — 예 새 백테스트 모델이면
     `curl -s "https://api.miffy178.com/stats/backtest?model=significant_event_type" | jq`
   - 프론트 화면: 브라우저에서 `https://miffy178.com/<경로>` (예 `/stats`) — 클라이언트
     렌더라 curl로는 확인 안 되는 부분은 브라우저로 안내.

**반드시 push/배포 상태를 반영하라**: 아직 push 안 된 커밋은 "로컬 테스트만 가능, 라이브
검증은 push→Render 배포 후"라고 분명히 하라. 백엔드 미변경 커밋은 API가 그대로이니
render-test로는 신·구 구분이 안 된다는 점도 짚어라(프론트만 재빌드되는 경우).

끝에 **바로 실행 가능한 체크리스트**를 한 블록으로 제시하라(복붙용). 실제 실행은 하지 말고
사용자가 고르게 둔다 — 다만 사용자가 "돌려줘/실행해"라고 하면 그때 해당 명령을 실행하라.
