---
description: 위험 작업 게이트 — 비가역/파괴 명령 기본 차단, 한시 허용 (on/off/status)
argument-hint: "on [분] | off | status"
---
사용자가 `/danger $ARGUMENTS` 를 실행했다. 위험 작업 게이트 파일 `.claude/.danger-unlock`
(만료 epoch 초 한 줄)을 아래에 따라 처리하라. 게이트가 열려 있어야 비가역/파괴 패턴
(`git push --force`, `git reset --hard`, `git clean`, `docker compose down -v`,
`docker * prune`, `rm -rf`, SQL `DROP/TRUNCATE`, 마이그레이션 다운 등)이 담긴 Bash 명령이
PreToolUse 훅(`.claude/hooks/danger-guard.sh`)을 통과한다.

- **on [분]** (분 생략 시 15):
  `EXP=$(( $(date +%s) + <분>*60 )); echo "$EXP" > .claude/.danger-unlock`
  를 실행하고, "⚠️ 위험 작업 <분>분 허용 (만료 HH:MM)" 를 출력한다.
- **off**:
  `rm -f .claude/.danger-unlock` 를 실행하고 "🛑 위험 작업 잠금" 을 출력한다.
- **status** 또는 인자 없음:
  게이트 파일 존재 여부와 만료까지 남은 시간(`.claude/.danger-unlock` 의 epoch − 현재시각)을
  계산해 출력한다. 없거나 만료면 "🛑 잠김".

게이트를 연 뒤에도 **CLAUDE.md의 Dangerous Action Safety Rules** 를 따른다 — 실행 전
영향받는 대상과 복구 방법을 알리고, 작업이 끝나면 `/danger off` 로 다시 잠그도록 안내한다.
게이트는 짧게(기본 15분) 열고 즉시 닫는 것을 원칙으로 한다.
