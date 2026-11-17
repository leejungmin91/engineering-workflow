# Hooks

The plugin registers one hook on installation (`hooks/hooks.json`). The harness commits and pushes finished work on personal projects.

| Hook | Event | Purpose |
| --- | --- | --- |
| `auto_commit_push` | `Stop` | At the end of a turn, commit remaining changes and push local commits. |

How the hook behaves:

- It runs `git add -A`, so `.gitignore` excludes ignored untracked files. A clean worktree can still have local commits to push.
- The commit subject is `Update <up to three top-level paths>` with `(+N more)` when there are more; dotfiles sort last. The body lists the changed files (`git diff --cached --name-status`) and ends with a `Co-Authored-By` trailer. `AUTO_COMMIT_TRAILER` replaces the trailer.
- A branch with an upstream uses the repository's Git push configuration. A branch without an upstream is pushed to the same branch on `origin` when that remote exists.
- Staging, commit, and push failures appear as a `systemMessage`. A later Stop retries a failed push while the commits are still local. `--dry-run` previews the commit using a temporary index.
- When `WORKING.md` at the repository root has a `## Lane 1` section, the hook skips staging and committing and only pushes local commits. Several sessions share that worktree, and the commit would sweep in another session's files.
- The repository is `CLAUDE_PROJECT_DIR` when the host sets it, otherwise the current directory. A directory that is not a Git work tree is skipped.

The hook includes unfinished and unrelated changes left in the worktree. Keep the worktree dedicated to the current task. Codex requires the user to review and trust the bundled Stop hook after installation or a change to the hook.

## Optional lane guard

Projects where several sessions work at once can install the `PreToolUse` [lane guard](multi-session.md#the-lane-guard). It lets only the session named as the lane 1 holder in `WORKING.md` edit guarded paths and refuses staging everything at once. It is a rail for honest sessions with known limits, listed in the guide.

## Optional skill discovery hook

Projects can also register the [`UserPromptSubmit` example](https://github.com/leejungmin91/engineering-workflow/tree/main/integrations/hooks) that searches a local metadata index and adds up to three skill names to the prompt context. It runs locally without calling a model and never writes prompts to disk.

[Codex hooks](https://learn.chatgpt.com/docs/hooks) · [Claude Code hooks](https://code.claude.com/docs/en/hooks)
