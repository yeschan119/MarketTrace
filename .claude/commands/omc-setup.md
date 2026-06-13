---
description: oh-my-claudecode 한 번에 설치 — 마켓플레이스 추가 + 플러그인 설치 + OMC 셋업
argument-hint: "(인자 없음)"
---
사용자가 `/omc-setup` 을 실행했다. oh-my-claudecode(OMC)를 처음부터 끝까지 설치한다.
아래 세 단계를 **순서대로** 수행하라. 각 단계는 Bash 로 `claude` CLI 를 직접 호출한다
(`/plugin ...` 슬래시 명령은 대화형이라 직접 못 부른다 — CLI 서브커맨드로 대체).

1. **마켓플레이스 추가**
   `claude plugin marketplace add https://github.com/Yeachan-Heo/oh-my-claudecode`
   - 이미 추가돼 있으면("already exists" 류) 정상으로 보고 다음으로 넘어간다.

2. **플러그인 설치**
   `claude plugin install oh-my-claudecode@oh-my-claudecode`
   - 마켓플레이스 이름이 다르면 `claude plugin marketplace list` 로 확인 후 `<plugin>@<marketplace>` 형식으로 재시도한다.
   - 이미 설치돼 있으면 그대로 두고 넘어간다.

3. **OMC 셋업 실행**
   - 플러그인은 **세션 재시작 후** 로드된다. 현재 세션에서 `oh-my-claudecode:omc-setup`
     스킬이 이미 사용 가능하면 그 스킬을 호출해 셋업을 마친다.
   - 아직 안 보이면(재시작 필요) 사용자에게 이렇게 안내한다:
     "✅ 마켓플레이스 추가 + 플러그인 설치 완료. 세션을 재시작한 뒤 `/oh-my-claudecode:omc-setup` 을 한 번 실행하면 셋업이 끝납니다."

각 단계의 CLI 출력(성공/이미존재/오류)을 간단히 보고하고, 오류가 나면 멈추고 원인과
해결책을 알린다. 모두 끝나면 다음 행동(재시작 필요 여부)을 한 줄로 명확히 알린다.
