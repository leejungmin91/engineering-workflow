# Independent review and handoff

Use a fresh, read-only reviewer. Confirm tool and model availability and repository access.

| Implementer | Preferred reviewer | Fallback |
| --- | --- | --- |
| Codex | A separate Claude Code session | A fresh Codex subagent or chat using Sol |
| Claude Code | The official OpenAI Codex plugin or a verified read-only bridge | A fresh Claude Code subagent or session using Opus |

Use `/codex:review` for a general diff review. When acceptance criteria or focus areas must be passed to Codex, use `/codex:adversarial-review` or a read-only bridge that accepts the handoff. Use the same packet in a fresh app chat or subagent when supported. Record the route used. If no independent session is available, record independent review as unverified and continue the checks you can run. Use MCP only when a supported connection already exists and the shared data is within the user's scope.

[Official Codex plugin](https://github.com/openai/codex-plugin-cc) · [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) · [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)

Provide the goal and acceptance criteria, behaviors to preserve, base and work snapshot, diff location, checks run, and unverified areas. Give the reviewer the evidence without the implementer's verdict. Ask for severity, file and line, trigger, user impact, and a check for each finding.

The reviewer does not edit or commit. The implementer records each finding as addressed, declined with evidence, or deferred. Rerun checks affected by fixes and request a focused re-review when the final change materially alters what was reviewed. Mark required review passed only after findings are handled for the current snapshot.
