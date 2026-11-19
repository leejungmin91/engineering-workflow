# Engineering Workflow 플러그인 색인

이 파일은 플러그인이 제공하는 스킬·훅·스크립트의 목차다. 스킬을 더하거나 빼면 여기와 `CHANGELOG.md`를 함께 고친다.

## 우선순위

사용자의 지금 지시 → 저장소의 `CLAUDE.md`·`AGENTS.md` → 이 플러그인의 스킬 본문 → 함께 설치한 다른 플러그인(superpowers 등)의 스킬. 사용자가 끈 스킬이나 플러그인을 피해 가지 않는다.

## 스킬

| 스킬 | 분류 | 한 줄 용도 | 핵심어 |
| --- | --- | --- | --- |
| `engineering-workflow` | 작업 절차 | 완료 기준·작업 순서·검증 루프·교차검토·보고를 한 흐름으로 진행한다. 여러 세션이 한 저장소에서 일할 때의 갈래와 점유 규칙을 포함한다 | 하네스, 검증, 의존성, 교차검토, 보고서, 다중 세션, 점유, harness, multi-session, lanes, verification, dependency graph, review, report |
| `game-dev` | 게임 개발 | 밸런스·진행, 에셋 예산 감사, 성능 예산, 플레이 보고, 회귀 시험, 범위 점검, 아트 방향, 소리 검토, Unity·Blender MCP 사용 규칙 | 게임, 밸런스, 에셋, 성능, 플레이테스트, 사운드, 유니티, 블렌더, game, balance, asset audit, performance, playtest, sound, Unity, Blender, MCP |

## 훅 (설치하면 바로 동작)

| 훅 | 이벤트 | 동작 |
| --- | --- | --- |
| `auto_commit_push` | `Stop` | 턴이 끝나면 남은 변경을 커밋하고 Git의 푸시 설정에 따라 로컬 커밋을 푸시한다. |
| `board` | `SessionStart`·`PostToolUse`·`Stop` | 프로젝트에 `.harness/board.json`이 있으면 진행 보드를 그려 세션마다 한 번 브라우저에 띄우고, 파일이 바뀌면 다시 그린다. |

`WORKING.md`에 `## Lane 1` 절이 있는 저장소에서는 커밋하지 않고 푸시만 한다. `auto_commit_push`는 안전장치가 아니라 개인 프로젝트용 편의 장치다. 작업이 끝나면 항상 커밋·푸시한다는 전제를 기계적으로 보장한다. 자세한 동작과 한계는 `skills/engineering-workflow/references/hook-recommendations.md`에 있다.

## 스크립트

| 스크립트 | 용도 |
| --- | --- |
| `scripts/hooks/auto_commit_push.sh` | `Stop` 훅 본체. POSIX `sh`로 돌며 `--dry-run`을 지원한다 |
| `skills/engineering-workflow/scripts/board.py` | 진행 보드. `.harness/board.json`을 읽어 진행률·작업 목록·결정 대기를 로컬 HTML 한 장으로 그린다. 훅 본체를 겸한다 (`references/board.md`) |
| `skills/engineering-workflow/scripts/check_record.py` | 완료 기록의 검사 결과·작업본·의존성을 검사한다 |
| `skills/engineering-workflow/scripts/lane_guard.py` | 선택형 `PreToolUse` 훅. 구현 담당 세션만 지키는 경로를 고치게 하고 전부 스테이징을 막는다 (프로젝트에 복사해서 등록, `references/multi-session.md`) |
| `skills/engineering-workflow/templates/multi-session/WORKING.md` | 세션 역할, 구현 담당, 사용자 결정 대기 목록을 적는 틀 |
| `skills/engineering-workflow/scripts/skill_index.py` | 스킬 메타데이터 색인을 만들고 찾는다 (선택형 훅의 입력) |
| `skills/engineering-workflow/scripts/codex_usage.py` | 현재 Codex 세션의 모델, 토큰, 계정 한도 메타데이터를 출력한다 |
| `../../integrations/statusline/claude-usage.sh` | Claude Code 상태 줄에 모델, 컨텍스트 바, 5시간·7일 한도를 표시한다 (수동 설치, 플러그인에 포함되지 않음) |
