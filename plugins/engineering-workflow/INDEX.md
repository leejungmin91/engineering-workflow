# Engineering Workflow 플러그인 색인

이 파일은 플러그인이 제공하는 스킬·훅·스크립트의 목차다. 스킬을 더하거나 빼면 여기와 `CHANGELOG.md`를 함께 고친다.

## 우선순위

사용자의 지금 지시 → 훅이 막거나 묻는 것 → 저장소의 `CLAUDE.md`·`AGENTS.md` → 이 플러그인의 스킬 본문 → 함께 설치한 다른 플러그인(superpowers 등)의 스킬. 사용자가 끈 스킬이나 플러그인을 피해 가지 않는다.

## 스킬

| 스킬 | 분류 | 한 줄 용도 | 핵심어 |
| --- | --- | --- | --- |
| `engineering-workflow` | 작업 절차 | 완료 기준·작업 순서·검증 루프·교차검토·보고를 한 흐름으로 진행한다 | 하네스, 검증, 의존성, 교차검토, 보고서, harness, verification, dependency graph, review, report |

## 훅 (설치하면 바로 동작)

| 훅 | 이벤트 | 동작 |
| --- | --- | --- |
| `guard_git` | `PreToolUse` (`Bash`, `PowerShell`) | 최근 사용자 메시지가 요청하지 않은 커밋·푸시·PR 생성을 막는다. 커밋이 더하는 내용에 비밀 값이 있으면 막는다 |
| `record_prompt` | `UserPromptSubmit` | Codex에서만 턴별 사용자 메시지를 저장한다. 아무것도 막지 않는다 |

훅은 명령 글자와 저장소 상태만 본다. 스크립트 파일 안의 동작이나 변수에 담긴 값은 보지 못한다. 자세한 범위는 `skills/engineering-workflow/references/hook-recommendations.md`에 있다.

## 스크립트

| 스크립트 | 용도 |
| --- | --- |
| `scripts/hooks/run.sh` | Python 3.9 이상 실행 파일을 골라 훅을 실행한다. 없으면 가드는 막힘으로 끝난다 |
| `scripts/hooks/hook_common.py` | 훅 입력 읽기, JSON 결정 출력, Codex 판별, 최근 사용자 메시지 읽기 |
| `scripts/hooks/approval.py` | 사용자 메시지에서 커밋·푸시·PR 요청 여부를 판정한다 (한국어·영어) |
| `scripts/hooks/shell_commands.py` | 셸 명령을 조각으로 나누고 git·PR 명령을 읽는다 |
| `scripts/hooks/secret_patterns.py` | 비밀 값 패턴과 자리표시 값 판별 |
| `skills/engineering-workflow/scripts/check_record.py` | 완료 기록의 검사 결과·작업본·의존성을 검사한다 |
| `skills/engineering-workflow/scripts/skill_index.py` | 스킬 메타데이터 색인을 만들고 찾는다 (선택형 훅의 입력) |
