# Work reports

Use the project's report format and location where specified. Otherwise report in the chat. Write a file in the authorized workspace when requested or needed for handoff.

| Stage | Record | Who uses it |
| --- | --- | --- |
| Start | Goal, scope, dependencies, required checks | Implementer |
| After changes | Current snapshot, diff, commands, results, unverified checks | Reviewer |
| After review | Reviewer and model, snapshot, findings, disposition, rechecks | Implementer and user |
| Completion or stop | Outcome, evidence, open items, next action | User or next session |

For a complex task, include the outcome, a Mermaid diagram of dependencies or flow, and one concrete example. List check commands, the tested snapshot, and results. Distinguish synthetic checks from tests on real devices or services. Describe the reviewer and model actually used. Keep limitations and any remaining action visible.

The [completion checker](harness-record.md) checks recorded results and snapshot consistency. The project tools establish the actual results. Use Slack or Discord only when the task calls for those sources.
