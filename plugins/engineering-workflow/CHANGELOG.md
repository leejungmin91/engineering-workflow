# 변경 이력

Keep the version in `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` in sync.

## 0.6.6 — 2026-11-18

사용자 요청: 한 프로젝트에서 이틀간 쓴 다중 세션 작업 방식(브리프 10가지 규칙)을 어느 프로젝트에나 쓸 수 있게 하네스에 넣는다.

- 추가: 스킬 본문에 "Keep going through the work list" 절. 작업 목록이 남아 있으면 멈추거나 묻지 않는다. 사용자만 정할 수 있는 결정은 "Waiting for the user" 목록에 기본값과 함께 적고 다음 작업을 한다. 되돌리기 어려운 작업의 확인 절차는 그대로다.
- 추가: `references/multi-session.md` — 세 갈래(구현 한 세션, 생산·읽기 병렬), `WORKING.md`, 잠금 훅 설치법과 한계, build·planner 메시지, 다른 세션의 메시지를 사용자 지시로 보지 않는 규칙, 실행되는 코드의 리뷰 두 번.
- 추가: `scripts/lane_guard.py`(`PreToolUse` 훅)와 `templates/multi-session/WORKING.md`. 프로젝트가 복사해서 쓴다. 지킬 경로는 `.claude/lane-guard.json`의 `open`·`guarded`로 정하고, 설정이 없으면 저장소 전체를 지킨다. 시험은 `tests/test_lane_guard.py`.
- 변경: `auto_commit_push`는 `WORKING.md`에 `## Lane 1` 절이 있으면 커밋하지 않고 로컬 커밋만 푸시한다. 전부 스테이징하면 다른 세션의 파일이 딸려 들어가기 때문이다.
- 변경: 스킬 본문에 모델 규칙(설계·새 시스템·저장 데이터·위험한 리뷰는 가장 강한 모델, 위임마다 모델 명시), 점검 규칙(전체 점검은 배치·저장·공유 상태 변경과 묶음마다 한 번, 커밋 메시지에 돌린 점검 기록, 점검 수정은 결함을 되돌려 실패를 확인), 디자인 규칙(유명 제품 조사 후 견본 하나 먼저)을 더했다. 교차검토 안내에는 한도가 없을 때의 대체 경로를 적었다.

## 0.6.5 — 2026-11-15

사용자 요청: 게임 개발에 필요한 스킬·플러그인 중 GitHub 스타가 많은 것을 하네스에 넣고 색인한다.

- 추가: `game-dev` 스킬. Claude-Code-Game-Studios(39k)의 balance-check, asset-audit, perf-profile, playtest-report, regression-suite, scope-check, art-bible, vertical-slice 규칙을 고정 커밋에서 읽어 옮겼다. 측정하지 못한 값은 추정하지 않고 `NOT ASSESSED`로 적는다는 규칙이 중심이다. 소리 검토와 MCP 사용 규칙을 더했다.
- 추가: `skills/game-dev/references/game-dev-sources.md` — 저장소, 스타, 라이선스, 고정 커밋, 반영 방식, MCP 텔레메트리 확인 결과.
- 추가: `docs/mcp-setup.md`에 Unity MCP(CoplayDev)와 Blender MCP(ahujasid) 설치 안내. 두 서버 모두 기본으로 사용 통계를 보내므로 끄는 설정을 필수로 적었다.
- 변경: 스킬 색인의 한국어 대응어에 게임 개발 용어를 추가했다.

## 0.6.4 — 2026-11-14

사용자 요청: 완성도를 요청했는데 에이전트가 3D 모델을 사용자가 직접 넣으라고 안내했다. 하네스가 이런 떠넘기기를 막아야 한다.

- 추가: 스킬 본문에 "Do the work yourself" 절. 에셋·패키지·도구는 정당한 출처(CC0 등)에서 직접 구해 연결하고 출처와 라이선스를 기록한다. 로그인, 비밀 값, 결제, 라이선스 동의, 실제 기기, 제품 결정처럼 사용자만 할 수 있는 단계만 넘기며, 그때는 시도한 것과 막힌 이유, 필요한 행동 하나를 적는다. 출처가 없으면 교체하기 쉬운 임시 대체물을 쓰고 남은 문제로 보고한다.

## 0.6.3 — 2026-11-14

- Register the Stop hook through the Codex compatibility manifest so Codex builds that skip hooks in the portable manifest can discover it.
- Push existing local commits at Stop, including hand-written commits and commits left behind by a failed push. Preserve the live Git index in dry-run mode.
- Update the workflow guide to describe the installed Stop hook.

## 0.6.2 — 2026-11-14

사용자 요청: 하네스의 사용량 표시를 Claude Code에서도 하단 바로 보이게 한다.

- 추가: `integrations/statusline/claude-usage.sh` — Claude Code 상태 줄 명령. 모델, 컨텍스트 사용 바(사용 토큰/용량, 비율이 없으면 `current_usage`로 계산), 5시간·7일 계정 한도와 초기화 시각을 한 줄로 그린다. 색약 테마를 고려해 청록·노랑·자홍을 쓴다. 값이 없으면 `?`로 표시한다. BSD·GNU `date` 모두 지원한다.
- 추가: 시험 `tools/hook_tests/test_claude_statusline.py`(`sh`와 `jq`가 없으면 건너뜀).
- 변경: README 두 개의 사용량 절을 Codex CLI와 Claude Code로 나눴다. 최종 보고 항목(적용한 스킬, 모델 설정, 사용량)을 개요와 보고 안내 표에 반영했다.

## 0.6.1 — 2026-11-14

- Codex 작업의 최종 보고에 현재 세션에서 확인한 모델, 컨텍스트, 누적 토큰, 계정 한도를 기록한다.
- Codex CLI의 기본 상태 줄을 설정하는 방법을 두 README에 추가했다.

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
