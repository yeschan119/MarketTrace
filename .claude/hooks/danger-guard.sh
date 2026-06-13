#!/usr/bin/env bash
# Dangerous action guard (PreToolUse hook).
# 비가역/파괴적 Bash 명령은 기본 차단. /danger on 으로 게이트(.claude/.danger-unlock)를
# 열어야 한시적으로 허용된다. 게이트 파일에는 만료 epoch(초) 한 줄이 들어있다.
# 차단 = exit 2 (+ stderr 사유). 허용/무관 = exit 0.
# (확인 티어 git commit/push, docker up/down 등은 settings.json permissions.ask 가 담당)

payload="$(cat)"

# tool_input.command 추출 (Bash 외 도구는 command 비어 통과)
cmd="$(printf '%s' "$payload" | python3 -c 'import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("command", ""))
except Exception:
    print("")' 2>/dev/null)"

[ -z "$cmd" ] && exit 0

# ── 비가역/파괴 패턴 (대소문자 무시) ──────────────────────────────
#  git: 강제푸시 / 하드리셋 / clean / amend / 브랜치·태그 삭제 / restore·checkout 되돌리기
#  docker: 볼륨삭제 down -v / prune / rm / down|stop
#  파일: rm -rf, 대량 삭제
#  DB/SQL: drop / truncate / delete from (전체) / 마이그레이션 다운
danger_re='git push.*(--force|--force-with-lease| -f)|git reset .*--hard|git clean|git commit .*--amend|git (branch|tag) .*-(d|D)|git checkout .*--|git restore|docker (compose )?down.*-v|docker (system|volume|image) prune|docker (compose )?rm |rm -rf|rm -fr|\bDROP (TABLE|DATABASE|SCHEMA)|\bTRUNCATE\b|alembic downgrade|migrate.*down'

if ! printf '%s\n' "$cmd" | grep -Eiq "$danger_re"; then
    exit 0
fi

proj="${CLAUDE_PROJECT_DIR:-$PWD}"
gate="$proj/.claude/.danger-unlock"
now="$(date +%s)"

if [ -f "$gate" ]; then
    exp="$(tr -dc '0-9' < "$gate" 2>/dev/null)"
    if [ -n "$exp" ] && [ "$now" -lt "$exp" ]; then
        exit 0  # 게이트 열림(만료 전) → 허용. 단 Dangerous Action Safety Rules 준수.
    fi
fi

echo " x 비가역/파괴 명령이 기본 차단되어 있습니다 (CLAUDE.md / Dangerous Action Safety Rules)." >&2
echo "   영향·복구방법을 사용자에게 먼저 설명하고, 승인 시 사용자가 /danger on [분] 으로 허용해야 합니다." >&2
echo "   차단된 명령: ${cmd:0:200}" >&2
exit 2
