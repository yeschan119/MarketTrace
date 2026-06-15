#!/usr/bin/env bash
# i18n reminder (PostToolUse hook on Edit/Write/MultiEdit).
#
# 웹 UI 소스(web/src/app/**, web/src/components/**)를 수정하면, 새로 추가/변경한
# 사용자 노출 문자열을 web/src/lib/i18n.tsx 의 en/ko 사전 양쪽에 추가하도록
# 모델에게 상기시킨다. i18n 번역은 적절한 문구 작성이 필요한 판단 작업이라
# 강제 차단(exit 2)이 아니라 additionalContext 로 컨텍스트만 주입한다.
#
# 대상이 아니면(또는 사전 파일 자체면) 조용히 통과(exit 0).

payload="$(cat)"

fp="$(printf '%s' "$payload" | python3 -c 'import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("file_path", ""))
except Exception:
    print("")' 2>/dev/null)"

[ -z "$fp" ] && exit 0

case "$fp" in
    */web/src/lib/i18n.tsx) exit 0 ;;                 # 사전 파일 자체는 제외
    */web/src/app/*.tsx|*/web/src/components/*.tsx) ;;  # UI 페이지/컴포넌트만 대상
    *) exit 0 ;;
esac

python3 - "$fp" <<'PY'
import json, sys
fp = sys.argv[1]
msg = (
    "i18n 규약 알림 — 방금 웹 UI 파일(%s)을 수정했습니다. "
    "새로 추가하거나 바꾼 사용자 노출 문자열이 있으면 반드시 "
    "web/src/lib/i18n.tsx 의 `en` 과 `ko` 사전 양쪽에 같은 키를 추가하고, "
    "컴포넌트에서는 하드코딩 리터럴 대신 useI18n()의 t('...')(필요 시 {var} 보간)로 "
    "렌더하세요. 한쪽 언어만 추가하거나 영어/한국어 리터럴을 그대로 남기지 마세요. "
    "순수 데이터 값(티커·모델명 등 번역 불필요한 것)은 예외입니다." % fp
)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": msg,
    }
}))
PY
exit 0
