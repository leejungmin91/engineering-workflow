# Optional hooks

The plugin has no active hooks on installation. Projects can register the [hook examples](https://github.com/leejungmin91/codex-engineering-workflow/tree/main/integrations/hooks) with their host.

| Event | Purpose |
| --- | --- |
| `UserPromptSubmit` | Search a local metadata index and add up to three skill names to the prompt context. |
| `PreToolUse` | Reject a small set of destructive options on the first direct Git command in a Bash tool call. |

The Git hook covers simple literal commands such as `git reset --hard`, `git clean -fdx`, and `git push --force`. Normal commands and dry runs pass. Use host permissions and repository protections for shell expansion, aliases, wrappers, and unsupported tool paths. Review and reporting run in the workflow steps.

[Codex hooks](https://learn.chatgpt.com/docs/hooks) · [Claude Code hooks](https://code.claude.com/docs/en/hooks)
