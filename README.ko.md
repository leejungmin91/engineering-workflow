# Engineering Workflow

[English](README.md)

완료 기준, 작업 순서, 검증 결과를 한 흐름으로 관리하는 Agent Skill입니다. 사용자 범위로 설치하면 여러 프로젝트에서 사용할 수 있습니다.

## 아키텍처

**설치할 때.** Codex나 Claude Code에 GitHub 저장소를 마켓플레이스로 등록하고 플러그인을 설치하면, 도구가 로컬에 스킬 사본을 보관합니다. 다른 Agent Skills 지원 도구에는 같은 스킬 폴더를 직접 설치할 수 있습니다.

**프롬프트를 보낼 때.** 인덱스는 설치된 스킬의 **이름·짧은 설명·파일 경로**를 모은 목차입니다. 프롬프트를 보낼 때 실행되는 훅(`UserPromptSubmit`)을 설정하면 내 컴퓨터의 목차 파일(`skill-index.json`)을 먼저 검색해 후보 이름을 최대 3개 전달합니다. 도구가 현재 사용 가능한 후보를 확인한 뒤 선택한 `SKILL.md`와 필요한 참고 문서만 읽습니다. 플러그인만 설치한 경우에는 도구 자체의 스킬 목록을 사용합니다.

**영어로 쓰는 부분.** 이 플러그인의 스킬 설명과 실행 지침은 영어입니다. 프롬프트는 한국어로 쓸 수 있습니다. 예를 들어 “하네스랑 교차검토 써 줘”라고 하면 로컬 검색이 `하네스`를 `harness`로, `교차검토`를 `independent review`로 찾아봅니다. 영어 지침과 필요한 파일만 읽는 방식의 토큰 절감량은 별도로 측정해야 합니다.

**실선**은 기본 작업 흐름입니다. **점선**은 훅을 설정했을 때 추가되는 검색 경로입니다. 교차검토에서 수정이 필요하면 실선을 따라 재검사로 돌아갑니다.

```mermaid
flowchart TB
    Prompt["사용자 프롬프트"] --> Catalog["사용 가능한<br/>스킬 목록 확인"]
    Prompt -. 훅을 켜면 먼저 실행 .-> Index["내 컴퓨터의<br/>스킬 목차 검색"]
    Index -. 후보 최대 3개 .-> Catalog
    Catalog --> Skill["선택한 스킬 읽기"]
    Skill --> Harness["하네스<br/>합격 기준 정하기"]
    Harness --> Graph["작업 그래프<br/>작업 순서 정하기"]
    Graph --> Loop["검증 루프<br/>검사·수정·재검사"]
    Loop --> Review["필요시 교차검토"]
    Review -->|수정 필요| Loop
    Review --> Report["결과와 근거 보고"]
```

공용 입력 처리기(파서)를 고치는 경우를 예로 들면, 세 부분은 이렇게 연결됩니다.

| 구성 | 역할 | 예시 |
| --- | --- | --- |
| 하네스 | 작업 범위와 완료에 필요한 검사를 정합니다. | 정상 입력은 기존대로 처리하고, 잘못된 입력에는 정해진 오류를 돌려줘야 합니다. |
| 작업 그래프 | 선행 조건을 적고 동시에 진행할 수 있는 작업을 찾습니다. | 파서의 입력·출력 약속을 확인하고 파서를 수정한 뒤, 파서를 쓰는 두 기능을 각각 확인합니다. |
| 검증 루프 | 현재 변경을 검사하고 실패 원인을 고친 뒤 영향받은 검사를 다시 돌립니다. | 한 기능에서 오류가 나면 재현 입력을 만들고, 원인을 고친 뒤 그 입력으로 다시 확인합니다. |

작업 그래프는 최종 변경 사항을 보고 검사 경로를 고릅니다. 문구나 이미지만 교체하면 변경 내용과 표시를 직접 확인하고, 프로젝트가 요구하는 경우에 자동 테스트를 실행합니다. 동작 변경이 포함되면 해당 동작도 테스트합니다. [검증 흐름](docs/workflow-flow.md)

요청이 있거나 공용 계약, 데이터, 권한, 배포에 영향이 있으면 교차검토로 최종 변경과 검증 근거를 확인합니다. 마지막 보고에는 결과, 실행한 검사, 남은 문제가 들어갑니다. 모델 선택이 가능한 도구에서는 역할마다 해당 작업을 감당할 수 있는 가장 가벼운 모델을 사용합니다.

플러그인을 설치하면 기계적 안전장치인 훅 두 개가 함께 등록됩니다. 커밋·푸시·PR 생성은 최근 사용자 메시지가 요청했을 때만 실행되고, 비밀 값이 들어가는 커밋은 막힙니다. [훅](#훅) 절을 보세요. Slack·Discord MCP는 필요할 때 관련 맥락을 읽는 선택 사항입니다. [스킬 인덱스 안내](plugins/engineering-workflow/skills/engineering-workflow/references/skill-index.md) · [MCP 연동](docs/mcp-setup.md)

## 설치

### Codex CLI와 데스크톱 앱

```sh
codex plugin marketplace add leejungmin91/engineering-workflow --ref main
codex plugin add engineering-workflow@engineering-workflow
```

이전 태그를 고정해 등록했다면 `codex plugin marketplace remove engineering-workflow`를 실행한 뒤 새 버전을 등록합니다.

Codex 데스크톱 앱에서는 마켓플레이스를 등록한 뒤 앱을 재시작합니다. 플러그인 디렉터리의 **Engineering Workflow** 소스에서 같은 이름의 플러그인을 설치하고 새 채팅을 엽니다. [Codex 마켓플레이스 공식 문서](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)

### Claude Code

```sh
claude plugin marketplace add https://github.com/leejungmin91/engineering-workflow.git
claude plugin install engineering-workflow@engineering-workflow
```

새 세션에서 `/engineering-workflow:engineering-workflow`로 실행합니다. Claude Code 2.1.275 이상에서는 세션 안에서 다음 명령으로 설치 화면을 열 수 있습니다.

```text
/plugin install engineering-workflow --marketplace leejungmin91/engineering-workflow
```

업데이트하려면 `claude plugin marketplace update engineering-workflow`와 `claude plugin update engineering-workflow@engineering-workflow`를 차례로 실행하고 Claude Code를 재시작합니다. [Claude Code 마켓플레이스 공식 문서](https://code.claude.com/docs/en/plugin-marketplaces)

### Claude 데스크톱, 웹, Cowork

**Customize → Plugins → Add → Add marketplace**에서 `leejungmin91/engineering-workflow` 저장소를 등록하고, 해당 소스의 **Engineering Workflow**를 추가합니다. 사용 가능한 마켓플레이스와 도구는 요금제 및 조직 설정에 따라 달라집니다. [Claude 앱 플러그인 공식 문서](https://support.claude.com/en/articles/13837440-use-plugins-in-claude)

### Cursor, Gemini CLI, 그 외 Agent Skills 지원 도구

[engineering-workflow 스킬 폴더](plugins/engineering-workflow/skills/engineering-workflow) 전체를 사용하는 도구의 스킬 경로에 복사합니다. Cursor와 Gemini CLI에서 사용자 범위 경로는 `~/.agents/skills/`입니다. 텍스트 지침만 받는 앱에서는 `SKILL.md`를 지침으로 제공하고 앱에서 제공하는 도구로 실행합니다. [Cursor](https://prod.cursor.com/docs/skills) · [Gemini CLI](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/using-agent-skills.md)

## 훅

플러그인을 설치하면 Claude Code와 Codex에 아래 훅이 등록됩니다. Codex는 플러그인 훅을 한 번 신뢰로 승인해야 하며, 승인 전에는 돌지 않습니다.

| 훅 | 이벤트 | 동작 |
| --- | --- | --- |
| `guard_git` | `Bash`·`PowerShell` 도구의 `PreToolUse` | 최근 사용자 메시지가 요청하지 않은 `git commit`, `git push`, PR/MR 생성(`gh pr create`, `glab mr create`, 푸시 옵션, pulls·merge_requests API에 쓰기 요청)을 막습니다. 커밋이 더하는 줄이나 `git add` 대상 미추적 파일에 비밀 값이 있으면 막습니다. |
| `record_prompt` | `UserPromptSubmit` | Codex 전용. 현재 턴 ID와 요청된 Git 동작을 `~/.engineering-workflow/prompts/`에 저장합니다. 새 기록을 저장할 때 7일이 지난 파일을 지웁니다. |

최근 메시지에서 `커밋해 줘`, `푸시해`, `커밋 푸시`, `올려 줘`(커밋과 푸시), `commit it`, `push the changes`, `PR 만들어 줘`, `open a pull request`처럼 직접 요청합니다. 조회·부정·보류 문구는 승인으로 처리하지 않습니다. PR 생성은 현재 턴에서 따로 요청해야 합니다. `--dry-run`과 푸시 전용 축약형 `git push -n`은 통과합니다.

필요한 것과 한계:

- PATH에 Python 3.9 이상(`python3`, `python`, `py` 중 하나)과 `sh`(Git for Windows에 포함)가 있어야 합니다. 실행할 인터프리터가 없으면 가드는 조용히 통과시키지 않고 막은 뒤 이유를 알립니다.
- 가드는 명령 글자와 저장소 상태만 봅니다. 스크립트 파일 안의 동작, 별칭, 변수에 담긴 값은 보지 못합니다. 그 부분은 호스트 권한과 브랜치 보호 규칙으로 막습니다.
- Claude Code에서는 세션 기록의 최근 사용자 메시지를, Codex에서는 현재 턴의 동작 승인 기록을 읽습니다. 해당 기록을 읽지 못하면 차단하고 이유를 알립니다.
- 훅을 끄려면 플러그인을 끄거나 지워야 하며, 그러면 스킬도 함께 꺼집니다. 사용자 훅으로 막힌 것을 풀 수 없습니다.

훅 시험은 [`tools/hook_tests`](tools/hook_tests)에 있고 `python -m unittest discover -s tools/hook_tests`로 실행합니다. 가짜 JSON 입력과 임시 Git 저장소만 쓰며, 막는 대상 명령은 실행하지 않습니다.

## 사용 예시

> Engineering Workflow로 이 변경이 영향을 주는 기능을 찾아 줘. 작업 순서와 합격 기준을 정하고, 실행한 검사와 남은 문제를 구조도와 함께 보고해 줘.

저장소를 내려받았다면 Python 3.9 이상에서 선택형 검사 도구를 실행할 수 있습니다. 아래 예제는 회귀 검사 실패, 이전 변경 상태에서 실행된 린트, 대기 중인 UI 검사를 보고합니다.

```sh
python plugins/engineering-workflow/skills/engineering-workflow/scripts/check_record.py examples/incomplete.json --snapshot current
```

[검증 기록 형식](plugins/engineering-workflow/skills/engineering-workflow/references/harness-record.md)

## 참고한 스킬 10개

플러그인이 제공하는 스킬은 `engineering-workflow` 하나입니다. 아래 스킬에서 가져온 작업 방식을 이 스킬에 반영했습니다.

| 참고 스킬 | 가져온 작업 방식 |
| --- | --- |
| Matt Pocock · `diagnosing-bugs` | 수정 전에 같은 오류를 재현하는 가장 작은 입력부터 찾습니다. |
| Superpowers · `verification-before-completion` | 마지막 변경 상태에서 통과한 검사를 완료 근거로 사용합니다. |
| ECC · `eval-harness` | 성공 조건과 회귀 사례를 정하고, 같은 사례로 워크플로 변경 전후를 비교합니다. |
| Karpathy Skills · `karpathy-guidelines` | 작업 범위와 확인 기준을 먼저 정해 필요한 부분만 수정합니다. |
| Anthropic · `webapp-testing` | 실행 환경이 있으면 실제 화면에서 영향받은 사용자 경로를 확인합니다. |
| Ponytail · `ponytail` | 새 코드나 도구를 추가하기 전에 기존에 쓸 수 있는 것을 찾습니다. |
| UI UX Pro Max · `ui-ux-pro-max` | UI 검사에 접근성과 영향받는 화면 크기를 포함합니다. |
| Graphify · `graphify` | 확인한 작업 의존성과 아직 추정에 그치는 의존성을 표시합니다. |
| gstack · `review` | 최종 변경에서 공용 계약, 데이터, 권한에 미치는 영향을 검토합니다. |
| Caveman · `caveman` | 결과와 근거부터 짧게 전달하고 중요한 조건을 함께 남깁니다. |

[스킬 선정 기준과 원본 커밋](plugins/engineering-workflow/skills/engineering-workflow/references/source-skills.md)

## 더 읽기

- [전체 실행 흐름·교차검토·보고서 구조도](docs/workflow-flow.md)
- [여러 도구로 배포한 작업 보고서](docs/implementation-report.md)
- [훅 범위와 선택형 스킬 색인 훅](plugins/engineering-workflow/skills/engineering-workflow/references/hook-recommendations.md)
- [플러그인 색인](plugins/engineering-workflow/INDEX.md) · [변경 이력](plugins/engineering-workflow/CHANGELOG.md)
