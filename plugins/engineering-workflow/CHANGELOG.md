# 변경 이력

버전마다 무엇을, 왜, 누가 요청해서 바꿨는지 적는다. 플러그인 버전은 `.claude-plugin/plugin.json`과 `plugin.json`의 `version`과 같아야 한다.

## 0.6.0 — 2026-11-13

사용자 요청: 이 하네스는 개인 프로젝트용이므로 커밋·푸시를 묻지 말고, 작업이 끝나면 항상 커밋·푸시해야 한다. `guard_git`이 사용자의 승인 문구를 인식하지 못해 정상 작업의 커밋을 반복해서 막은 것이 계기다.

- 제거: `guard_git`(요청 없는 커밋·푸시·PR 차단, 비밀 값 검사)과 Codex 승인 기록 훅 `record_prompt`, 그리고 둘이 쓰던 `approval.py`, `hook_common.py`, `shell_commands.py`, `secret_patterns.py`, `run.sh`. 훅 시험 `test_guard_git.py`도 지웠다.
- 추가: `auto_commit_push` — `Stop` 이벤트에서 작업 트리의 변경을 모두 스테이징해 커밋하고 추적 중인 원격 브랜치로 푸시한다. 제목은 `Update <최상위 경로 최대 3개>`, 본문은 변경 파일 목록, 끝에 `Co-Authored-By` 트레일러(`AUTO_COMMIT_TRAILER`로 교체 가능). 업스트림이 없으면 `origin/<branch>`로 `-u` 푸시한다. 턴을 막지 않으며 실패는 `systemMessage`로 알린다. `--dry-run`을 지원한다. POSIX `sh`만 필요하고 Python은 더 이상 쓰지 않는다.
- 추가: 훅 시험 `tools/hook_tests/test_auto_commit_push.py`(임시 저장소와 bare 원격으로 커밋·푸시·업스트림 설정·실패 보고를 확인).
- 변경: 스킬 본문의 "Commit, push, and PR" 절을 "항상 커밋·푸시한다"로 바꿨다. README 두 개, INDEX, 훅 안내, 워크플로 그림에서 가드 설명을 지웠다.
- 참고: 비밀 값 검사는 가드와 함께 사라졌다. 필요하면 별도 훅으로 다시 넣는다.

## 0.5.0 — 2026-11-12

사용자 요청: 개인 프로젝트 하네스 설계서(2026-11-12) 2단계. 범용 하네스로 가고, 도구는 Claude Code·Codex 모두 지원하며, 모델은 가능한 가벼운 것을 쓴다는 방향을 확정했다.

- 추가: 플러그인 훅 등록(`hooks/hooks.json`). 설치하면 바로 동작한다.
- 추가: `guard_git` — 최근 사용자 메시지가 요청하지 않은 커밋·푸시·PR 생성을 막는다(한국어·영어 요청 문구 판정, 부정·보류 표현 제외). 커밋이 더하는 줄과 `git add` 대상 미추적 파일에서 비밀 값을 찾으면 막는다. 명령 위치(`;` `&&` `|` `(` 뒤)의 git만 보고, 대소문자·`.exe`·`-C`·`-c` 옵션을 처리한다. `Bash`와 `PowerShell` 도구 모두 검사한다.
- 추가: `record_prompt` — Codex에서 턴 ID와 승인된 동작을 `~/.engineering-workflow/prompts/`에 저장한다. 저장할 때 7일 지난 기록을 정리한다. 가드는 같은 `turn_id`의 기록을 사용한다.
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
