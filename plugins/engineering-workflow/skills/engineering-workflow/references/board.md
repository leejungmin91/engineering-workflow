# Progress board

The board is one local HTML page that shows progress, the task list, what is left, and the decisions waiting for the user. The agent edits a small JSON file. A script draws the page. Nobody edits the HTML.

## The board file

Keep `.harness/board.json` at the project root and commit it with the work. It is the source of truth for task state.

```json
{
  "title": "Checkout rewrite",
  "lang": "en",
  "tasks": [
    {"id": "T1", "title": "Reproduce the refund error", "status": "done", "after": []},
    {"id": "T2", "title": "Fix the rounding rule", "status": "doing", "after": ["T1"], "owner": "build", "note": "unit tests first"},
    {"id": "T3", "title": "Release notes", "status": "todo", "after": ["T2"]}
  ],
  "decisions": [
    {"ask": "Ship behind a flag or to everyone", "look": "docs/release-plan.md", "default": "behind a flag"}
  ]
}
```

- `status` is `todo`, `doing`, `done`, `blocked`, or `parked`. Progress is the share of tasks that are `done`, rounded down, so 100% means every task is done.
- IDs follow the [completion record](harness-record.md) rules, and `after` lists prerequisite task IDs. Use the same IDs in both files.
- `decisions` holds what only the user can decide: what is asked, the picture or file to look at, and the default in use meanwhile. Bullet lines under `## Waiting for the user` in `WORKING.md` are shown as well, wrapped lines included, so a multi-session project keeps one list there. Set `"working_decisions": false` in the board when the board's own `decisions` are the list and that section holds notes the page should not repeat.
- `lang` selects the page labels: `en` or `ko`. `owner` and `note` are optional.

## When to update it

- Before multi-step work starts, write the board with every known task, then start the first task.
- Change a task's status when it starts, finishes, or stops on something. Add tasks as they appear. Progress can go down when the list grows.
- Add a decision when you park one and remove it when the user settles it.

## Rendering

```sh
python3 scripts/board.py render /absolute/path/to/.harness/board.json --open
```

The page goes to `~/.cache/engineering-workflow/boards/`, outside the repository, so it is never committed. `index.html` in the same folder lists every board rendered on this machine with its progress and open decisions. Boards whose file is gone drop off the list. The page reloads itself every five seconds and loads nothing from the network. `--out <file>` writes one page elsewhere and skips the overview.

What the page shows, top first:

- The title with what needs the user: the number of decisions and of blocked tasks, or a "nothing blocked" chip. Beside it, how long ago the board file changed; it turns amber after a day.
- Three cards: what is in progress now; what comes next (todo tasks whose `after` tasks are done, or, when none is ready, the waiting ones with what they wait for); and progress as a percentage with a bar split by state and a legend that gives every count.
- The decisions, numbered, each with its default and the file to look at. Pictures named in `look` (a path ending in `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, or `.svg`) or listed in an optional `images` field show as small previews; a click opens the picture large, with previous and next for the decision's other pictures, and Esc or a click outside closes it. Only files inside the project, up to 20 MB and eight per decision, are shown. They are copied to `assets/` beside the page, so the page also works when the board folder is served. The page does not reload while a picture is open.
- The tasks grouped by state (in progress, blocked, parked, to do), each group with its count. A task waiting on others says which. Done tasks are folded. Long notes show one line and open on click. With two or more owners, buttons filter by owner.
- The newest five work records in `.harness/records/`.

The page reloads itself every 5 seconds and keeps open notes and the owner filter. It follows the system's light or dark mode and fits a phone screen.

`index.html` lists boards that need the user first (decisions and blocked tasks), then the rest by work in progress. Each row shows a signal chip, progress, what is in progress or next, and how long ago it changed. A board whose file changed after its page was drawn is drawn again when the overview is written, so the overview does not go stale when another project's hooks have not run.

| Exit code | Meaning |
| --- | --- |
| 0 | Page written |
| 2 | The board file is missing or invalid |

## Hooks

The plugin registers the same command on three events. Each does nothing when the project has no board file.

| Event | What it does |
| --- | --- |
| `SessionStart` | Renders the board, opens it in the default browser, and tells the agent where the board file is |
| `PostToolUse` (`Write`, `Edit`, `MultiEdit`) | Renders again when the edited file is the board file |
| `Stop` | Renders again at the end of the turn, which covers edits made through the shell |

The page opens once per session, also when several sessions work in one project. A board created in the middle of a session opens on its first render. The browser is started detached, so it cannot hold the hook open. The hooks need `python3` on PATH and are skipped without it. They never block a prompt or a tool: an invalid board file is reported as a message and the previous page stays.

| Environment variable | Effect |
| --- | --- |
| `HARNESS_BOARD_OPEN=0` | Render without opening a browser (remote shells, CI) |
| `HARNESS_BOARD_HOME` | Folder for the pages instead of `~/.cache/engineering-workflow/boards` |

The project root is `CLAUDE_PROJECT_DIR` when the host sets it. Otherwise it is the nearest folder at or above the working directory that has a board file. `HARNESS_BOARD_HOME` must be an absolute path.
