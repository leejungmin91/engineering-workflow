# Hooks

The plugin registers two hooks on installation (`hooks/hooks.json`). They are safeguards that do not depend on the model remembering a rule.

| Hook | Event | Purpose |
| --- | --- | --- |
| `guard_git` | `PreToolUse` on `Bash` and `PowerShell` | Deny commit, push, or PR/MR creation that the latest user message did not request. Deny a commit that would add a secret. |
| `record_prompt` | `UserPromptSubmit` | Codex only: save the current turn's prompt so `guard_git` can read it. Never blocks. |

How the guard decides:

- It splits the command at `&&`, `||`, `|`, `;`, `&`, newlines, and parentheses, and reads only segments that start with `git` (any case, with or without `.exe` or a path, after `-C`, `-c`, and other global options), `gh`, `glab`, `hub`, or an HTTP client that writes to a pulls or merge_requests path. Text inside quotes such as `grep "git commit"` is not a command.
- Each action needs its own request in the latest user message. Negated or deferred phrases are not requests. A request in a previous message does not carry over. See the README for examples.
- Before a commit, it scans added lines of the staged and working-tree diffs of tracked files, and untracked files when the same command runs `git add` (up to 200 files, 1 MB each). It reports the kind of secret only. Values that are placeholders or references (`${TOKEN}`, `process.env.X`) pass; a default inside `${X:-value}` is checked.
- Every decision is written as JSON on stdout with exit code 0, which both Claude Code and Codex honour. Codex ignores exit code 2 and the `ask` decision, so an ask becomes a deny there.

Known limits: the guard sees command text and repository state only. Scripts, aliases, and variables are opaque to it. Keep host permissions and branch protection for those paths. When the user message cannot be read, the guard denies and says why rather than guessing.

## Optional skill discovery hook

Projects can also register the [`UserPromptSubmit` example](https://github.com/leejungmin91/engineering-workflow/tree/main/integrations/hooks) that searches a local metadata index and adds up to three skill names to the prompt context. It runs locally without calling a model and never writes prompts to disk.

[Codex hooks](https://learn.chatgpt.com/docs/hooks) · [Claude Code hooks](https://code.claude.com/docs/en/hooks)
