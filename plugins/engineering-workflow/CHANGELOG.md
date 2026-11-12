# 변경 이력

버전마다 무엇을, 왜, 누가 요청해서 바꿨는지 적는다. 플러그인 버전은 `.claude-plugin/plugin.json`과 `plugin.json`의 `version`과 같아야 한다.

## 0.5.0 — 2026-11-12

사용자 요청: 개인 프로젝트 하네스 설계서(2026-11-12) 2단계. 범용 하네스로 가고, 도구는 Claude Code·Codex 모두 지원하며, 모델은 가능한 가벼운 것을 쓴다는 방향을 확정했다.

- 추가: 플러그인 훅 등록(`hooks/hooks.json`). 설치하면 바로 동작한다.
- 추가: `guard_git` — 최근 사용자 메시지가 요청하지 않은 커밋·푸시·PR 생성을 막는다(한국어·영어 요청 문구 판정, 부정·보류 표현 제외). 커밋이 더하는 줄과 `git add` 대상 미추적 파일에서 비밀 값을 찾으면 막는다. 명령 위치(`;` `&&` `|` `(` 뒤)의 git만 보고, 대소문자·`.exe`·`-C`·`-c` 옵션을 처리한다. `Bash`와 `PowerShell` 도구 모두 검사한다.
- 추가: `record_prompt` — Codex에서 턴별 사용자 메시지를 `~/.engineering-workflow/prompts/`에 저장한다(7일 뒤 삭제). 가드는 같은 `turn_id`일 때만 그 메시지를 믿는다.
- 변경: 모든 훅은 stdout JSON `deny`와 종료 코드 0으로 막는다. Codex는 종료 코드 2와 `ask`를 무시하기 때문이다(설계서 4.1 실측).
- 변경: 실행 래퍼 `scripts/hooks/run.sh`가 `python3`·`python`·`py -3` 중 실제로 도는 것을 고른다. Windows의 Store 스텁 `python3`를 건너뛴다. Python이 없으면 가드는 막힘으로 끝난다.
- 제거: 선택형 `integrations/hooks/guard_git.py`(첫 git 명령의 `reset --hard`·`clean -fdx`·`push --force`만 종료 코드 2로 막던 훅). 플러그인 훅으로 대체했다. 파괴적 명령 앞에서 묻는 가드는 3단계(`guard_shell`)에서 저장소 상태를 보고 만든다.
- 추가: `INDEX.md`, 이 변경 이력. 훅 시험 `tools/hook_tests/`(배포하지 않음)를 CI에 연결했다.
- 정리: 플러그인 메타데이터 세 곳의 설명을 통일하고 옛 저장소 이름(`codex-engineering-workflow`)을 지웠다.

## 0.4.0 — 2026-11-11

- 스킬 색인 설명과 워크플로 화살표를 명확히 했다. 한국어 README를 추가하고 구조를 설명했다.

## 0.3.0 — 2026-11-11

- 교차검토 안내, 보고 흐름, 선택형 Git 훅(`integrations/hooks`)을 추가했다. 메타데이터 전용 스킬 색인(`skill_index.py`)을 추가했다.

## 0.2.0 — 2026-11-11

- Codex와 Claude 마켓플레이스를 함께 지원하고, Slack·Discord MCP 연결을 선택 사항으로 문서화했다.

## 0.1.0 — 2026-11-11

- Engineering Workflow Codex 마켓플레이스를 처음 공개했다. 스킬 `engineering-workflow`와 완료 기록 검사기 `check_record.py`를 포함한다.
