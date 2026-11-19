# One task per fresh session

Long sessions fill their context, and a compacted context loses detail. The harness keeps what a session needs in files (the board, the work records, `WORKING.md`, the queue and the done lines), so a new session can pick up the next task without the old conversation. `scripts/run_queue.py` does that in a loop: it starts a fresh agent session for one ready task, checks the result, and only then starts the next.

```sh
python3 scripts/run_queue.py /absolute/path/to/project --dry-run
python3 scripts/run_queue.py /absolute/path/to/project --max 3 --lane
```

## What one round does

1. Takes the first `todo` task on `.harness/board.json` whose `after` tasks are all `done` (`--owner` limits it to one owner).
2. Starts `claude -p` in the project with a new session id and a short prompt: read the project's rules and the board, do only this task, run its checks and reviews, mark it done, write its work record, commit by name, push; or mark it blocked or add a decision and stop. A task's optional `model` and `effort` fields are passed as `--model` and `--effort`.
3. When the session ends, stops anything the session left running, then checks for itself: the session exited 0, the task is `done` on the board, there is a new commit on top of where the session started, that commit is on the remote branch the local branch tracks (asked of the remote, not the local copy), a work record for the task was written during the session, and no tracked file is left uncommitted.
4. Starts the next round only when every check passed. Otherwise it stops, prints what failed and the session's last line, and keeps the full output in `~/.cache/engineering-workflow/runs/` (`HARNESS_RUN_LOGS` to change it).

## Lanes

When the project has `WORKING.md` with a `## Lane 1` section, the runner needs `--lane`. It writes the session's id on Lane 1 before the session starts, so the project's lane guard lets that session edit, and removes the line when the session ends. It refuses to start while another session holds Lane 1. A holder hands over by writing `STOPPED` right after its `session_id=...:` (bold is fine: `session_id=abc: **STOPPED** for the runner`); the word elsewhere in the line does not count, and a placeholder such as `session_id=<id>` is not a holder. Lane 1 is read again before every round. The runner's line is found by its session id, so it is removed even if the session edited it. If the session committed `WORKING.md` with that line in it, the runner removes the line from the working copy and stops: it never commits or pushes on the session's behalf. A lock in the repository's `.git` folder lets only one runner work in a repository at a time (exit 3 for a second one).

## Permissions

The runner adds no permission flags. The session runs with the project's and the user's settings, so an action those settings would ask about is not taken, and the round stops at the check. To let unattended sessions do more, widen the project's allowed commands deliberately; do not pass a bypass mode.

| Option | Default | Meaning |
| --- | --- | --- |
| `--max` | 1 | Tasks to run at most |
| `--minutes` | 90 | Time limit per session; at the limit, or when the runner itself is interrupted, the session and its process group are stopped. A process that deliberately starts its own session escapes this, as it would any parent |
| `--agent` | `claude` (`HARNESS_RUN_AGENT`) | Agent command; `-p`, the prompt and `--session-id` are added |
| `--dry-run` | off | Show the next task and the command, run nothing |

| Exit code | Meaning |
| --- | --- |
| 0 | Ran up to `--max` tasks or no ready task is left |
| 1 | Stopped at a task that did not finish cleanly |
| 2 | The board or repository is unusable, or `--lane` is missing |
| 3 | Lane 1 is held by another session, another runner works in the repository, or tracked files have uncommitted changes |
