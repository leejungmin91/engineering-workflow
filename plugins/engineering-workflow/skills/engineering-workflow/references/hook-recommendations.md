# Hooks

The plugin registers one hook on installation (`hooks/hooks.json`). It is a convenience for personal projects, not a safeguard: the harness assumes that finished work is always committed and pushed.

| Hook | Event | Purpose |
| --- | --- | --- |
| `auto_commit_push` | `Stop` | When the assistant finishes a turn, stage every change in the repository, commit it, and push to the tracked upstream. |

How the hook behaves:

- It runs `git add -A`, so `.gitignore` decides what is excluded. When the tree is clean it exits without output.
- The commit subject is `Update <up to three top-level paths>` with `(+N more)` when there are more; dotfiles sort last. The body lists the changed files (`git diff --cached --name-status`) and ends with a `Co-Authored-By` trailer. `AUTO_COMMIT_TRAILER` replaces the trailer.
- It pushes to the branch's upstream. A branch without an upstream is pushed with `-u origin <branch>` when a remote named `origin` exists.
- It never blocks the turn. Commit or push failures are reported as a `systemMessage` and the exit code stays 0. `--dry-run` prints the plan and leaves the index untouched.
- The repository is `CLAUDE_PROJECT_DIR` when the host sets it, otherwise the current directory. A directory that is not a Git work tree is skipped.

Known limits: the hook commits whatever the turn left behind, so a half-finished edit at the end of a turn is committed too. Write a hand-written commit yourself when the work deserves one; the hook then finds a clean tree and does nothing. Secrets are not scanned; keep host permissions, `.gitignore`, and branch protection for that. Claude Code fires `Stop`; check your Codex version's hook events before relying on it there.

## Optional skill discovery hook

Projects can also register the [`UserPromptSubmit` example](https://github.com/leejungmin91/engineering-workflow/tree/main/integrations/hooks) that searches a local metadata index and adds up to three skill names to the prompt context. It runs locally without calling a model and never writes prompts to disk.

[Codex hooks](https://learn.chatgpt.com/docs/hooks) · [Claude Code hooks](https://code.claude.com/docs/en/hooks)
