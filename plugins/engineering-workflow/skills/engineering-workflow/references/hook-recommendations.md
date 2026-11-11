# 선택형 훅

플러그인 설치 직후 활성화되는 훅은 0개다. [PreToolUse 예시](https://github.com/leejungmin91/codex-engineering-workflow/tree/main/integrations/hooks)는 프로젝트에서 선택해 등록한다. Codex와 Claude Code가 도구 실행 전에 전달하는 `Bash` 명령을 확인하고, 첫 직접 Git 명령이 `git reset --hard`, `git clean -fdx`, `git push --force` 또는 `git push -f`에 해당하면 종료 코드 2로 막는다. 정상 명령과 드라이런은 통과한다.

| 이벤트 | 현재 사용 |
| --- | --- |
| `PreToolUse` | 명시적으로 등록한 환경에서만 Git 명령을 제한 |
| `PostToolUse` | 검증은 실제 명령과 완료 기록으로 관리 |
| `Stop` | 검토 루프는 스킬의 작업 단계에서 관리 |

선택형 훅은 한 줄의 첫 직접 호출과 리터럴 옵션만 대상으로 삼는다. 줄 연속, 복잡한 인용, 셸 확장, 부정 플래그는 별도 보호 규칙에서 다룬다. 나중에 연결한 명령, 별칭, 래퍼, 다른 도구 경로는 샌드박스·Git 권한·보호 브랜치 같은 독립 제한을 사용한다. 명령 훅으로 보고서나 검토를 자동 실행하면 비용과 실행 시간이 늘 수 있어, 교차검토는 필요한 작업에서 한 번 요청하고 결과를 반영한다. [Codex 훅](https://learn.chatgpt.com/docs/hooks) · [Claude Code 훅](https://code.claude.com/docs/en/hooks)
