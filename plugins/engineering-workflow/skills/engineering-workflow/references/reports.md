# Work reports

Use the project's report format and location where specified. Otherwise report in the chat. Write a file in the authorized workspace when requested or needed for handoff.

| Stage | Record | Who uses it |
| --- | --- | --- |
| Start | Goal, scope, dependencies, required checks | Implementer |
| After changes | Current snapshot, diff, commands, results, unverified checks | Reviewer |
| After review | Reviewer and model, snapshot, findings, disposition, rechecks | Implementer and user |
| Completion or stop | Outcome, evidence, open items, next action, applied skills, model settings, usage | User or next session |

For a complex task, include the outcome, a Mermaid diagram of dependencies or flow, and one concrete example. List check commands, the tested snapshot, and results. Distinguish synthetic checks from tests on real devices or services. Describe the reviewer and model actually used. Keep limitations and any remaining action visible.

The [completion checker](harness-record.md) checks recorded results and snapshot consistency. The project tools establish the actual results. Use Slack or Discord only when the task calls for those sources.

## Model and usage

- List the skills you applied. Report the actual model and reasoning level of the main session and any independent reviewer. In Codex, use the current session snapshot from `scripts/codex_usage.py`. The script reads metadata for `CODEX_THREAD_ID` under `CODEX_HOME` (default `~/.codex`). If the snapshot is unavailable, use model or usage values explicitly supplied by the host.
- Give the latest observation timestamp. Report the latest recorded context tokens, capacity, and used and remaining percentages. These percentages divide the reported count by capacity. The CLI footer can use a different baseline for its percentages. Report the cumulative session total separately.
- Report the duration and used and remaining percentages for each observed account quota window. Include reset times and any absolute values supplied by the host. Mark missing values unknown. The snapshot can precede the final response and can be unavailable in hosts without a local rollout.
