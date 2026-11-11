# Engineering Workflow for Codex

A Codex plugin for three parts of software engineering work.

- **Harness engineering** sets acceptance criteria and checks that the completion record contains passing results for the work being reviewed.
- **Loop engineering** reproduces a failure, makes a focused change, and runs the check again with a clear stopping rule.
- **Graph engineering** maps dependencies between work items, detects invalid or cyclic dependencies, and identifies what needs to be verified again after an upstream change.

## Install

Run these commands in a terminal with the Codex CLI installed.

```sh
codex plugin marketplace add leejungmin91/codex-engineering-workflow --ref v0.1.0
codex plugin add engineering-workflow@engineering-workflow
```

In the ChatGPT desktop app, you can also restart the app after adding the marketplace, then install **Engineering Workflow** from the **Engineering Workflow** source in the Plugins Directory. Start a new chat after installation. See [OpenAI's plugin marketplace instructions](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli).

Select the **Engineering Workflow** skill or ask Codex:

> Use the Engineering Workflow skill to plan this change, verify the result, and report any remaining failures.

The workflow follows the current project's tools and instructions. Python 3.9 or later runs the optional completion checker. For each task, the checker evaluates the recorded dependency order, status, and evidence against the supplied snapshot. The project's own tools run the tests and determine the actual results.

## Try the checker

From a checkout of this repository, run:

```sh
python plugins/engineering-workflow/skills/engineering-workflow/scripts/check_record.py examples/incomplete.json --snapshot current
```

Use `python3` if that is the Python command on your machine. This example exits with code 1 because the parser regression failed, lint evidence is from an earlier snapshot, and the UI check is still pending. See the [record format](plugins/engineering-workflow/skills/engineering-workflow/references/harness-record.md) for all exit codes.

Run the regression suite with:

```sh
python -m unittest discover -s plugins/engineering-workflow/skills/engineering-workflow/tests
```

[Workflow sources](plugins/engineering-workflow/skills/engineering-workflow/references/source-skills.md) · [Optional Codex hook recommendations](plugins/engineering-workflow/skills/engineering-workflow/references/hook-recommendations.md)

## 한국어

이 플러그인은 작업의 **합격 기준**을 세우고, **선행 작업과 영향 범위**를 확인하고, **실패를 고친 뒤 다시 검사**하는 데 사용합니다. 위 설치 명령을 실행한 뒤 새 Codex 채팅에서 이렇게 요청하세요.

> Engineering Workflow 스킬로 작업 순서와 합격 기준을 정하고, 검증 결과와 남은 실패를 알려줘.

완료 검사기는 기록이 현재 작업본과 일치하는지 점검합니다. 필수 테스트는 프로젝트 도구로 실행합니다. 작업 그래프는 개발 작업 사이의 선행 관계를 표현합니다. 플러그인의 [훅 도입안](plugins/engineering-workflow/skills/engineering-workflow/references/hook-recommendations.md)에서 별도로 적용할 제한을 검토할 수 있습니다.
