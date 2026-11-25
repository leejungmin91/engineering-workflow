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
    {"title": "Ship to everyone, or behind a flag first?", "ask": "The refund fix is ready. A flag lets a few users try it before everyone gets it.",
     "default": "It stays behind the flag.", "look": "docs/release-plan.md", "detail": "T2, release-plan section 3"},
    {"ask": "Use ground sample 2: all, some, or none?", "default": "keep today's ground",
     "images": ["docs/review/31_ground_sample2_G2"],
     "why": "Problem: the user said the ground still looks awkward after sample A.\nResearch: ...\nSo the sample changes ... because ...\nChecked and worries: ...\nChoices: all, some (for example the patches only), none.",
     "history": [{"date": "11-17", "text": "Ground sample G1 made as A and B"},
                 {"date": "11-18", "text": "The user picked A"},
                 {"date": "now", "text": "Waiting for the user's word"}],
     "sources": ["docs/research/ground.md"]},
    {"title": "Which sound for the axe hit?", "ask": "Listen to the 40 options and tell me the number.",
     "default": "Option 1 stays.", "sounds": ["candidates/A3/sounds"], "sounds_label": "Listen to the options"}
  ]
}
```

- `status` is `todo`, `doing`, `done`, `blocked`, or `parked`. Progress is the share of tasks that are `done`, rounded down, so 100% means every task is done.
- IDs follow the [completion record](harness-record.md) rules, and `after` lists prerequisite task IDs. Use the same IDs in both files.
- `decisions` holds what only the user can decide: what is asked, the picture or file to look at, and the default in use meanwhile. Bullet lines under `## Waiting for the user` in `WORKING.md` are shown as well, wrapped lines included, so a multi-session project keeps one list there. Set `"working_decisions": false` in the board when the board's own `decisions` are the list and that section holds notes the page should not repeat.
- A decision that comes with pictures also says why the draft was made this way, in the user's language: `why` (one paragraph per line: the problem and the user's words, what was researched, what the draft changes and why this way, what was checked and what worries remain, the choices) and `history` (date and one line per step that led here). `sources` lists the documents behind it. These are written by the session that made the draft; nothing can generate them.
- `lang` selects the page labels: `en` or `ko`. `owner` and `note` are optional.

## Write it so anyone can read it

The user reads the board between other work and should understand a card without knowing the code. Write board text like an explanation to a newcomer (ELI5), in the user's language:

- `title`: the one thing to decide, as a short question ("가마 모습, 이대로 써도 될까요?"). No task codes, file paths or numbers.
- `ask`: two or three plain sentences: what changed and how it looks or behaves. Numbers only when they are the decision.
- `why`: why the user is asked, in a sentence or two ("모양은 눈으로 봐야 정할 수 있어서요."), not a rule's name.
- `default`: one sentence on what stays meanwhile ("지금 모습 그대로 둬요.").
- `detail`: task codes, measurements and other references; the page shows them with `look` in small print under the card.
- Task `title`: what the task does, in words ("초막의 보이는 크기와 실제로 부딪히는 범위 맞추기"); the `id` already carries the code. `note`: one plain sentence in the user's language; keep technical notes in the work record.
- Korean boards use 해요체 throughout, matching the page's labels; do not mix it with 합니다체 or with English notes.

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
- The decisions, numbered: the `title` in bold with the `ask` under it (or the `ask` alone), the default, and at the bottom a small "details" line with `detail` and `look`. On the page a decision also shows, in this order: why it was made this way, how it got here, its sources, an "about the drafts" line (the heading of the section that shows the pictures in the gallery page), the pictures with their captions, and folded evidence (earlier drafts in the same series, matched by the letter code and a shared word in the folder name, and the commits that changed those folders, oldest first). A comparison picture whose file name says `now_above_sample_below` or `before_left_after_right` (or whose caption says 위 = 지금, 아래 = 견본) carries "now" and "draft" labels on its halves, also when opened large. Pictures show as small previews: a picture path in `look` or in an optional `images` list, every picture in a folder named there, and the pictures a named `.html` or `.md` document shows (`<img src>`, `![](...)`, links to pictures, resolved from the document's folder); a click opens the picture large, with previous and next for the decision's other pictures, and Esc or a click outside closes it. Only files inside the project, up to 20 MB and eight per decision, are shown. They are copied to `assets/` beside the page, so the page also works when the board folder is served. The page does not reload while a picture is open. Sounds and videos go in an optional `sounds` list: files or folders inside the project (`.ogg .oga .opus .wav .mp3 .flac .m4a .aac .mp4 .webm .mov .m4v`; a folder gives its files sorted by name with numbers in order, so `2_fire` comes before `10_wind`). The card then shows a button (`sounds_label`, default "Listen to the options") that opens a separate listening page in a new tab: every file numbered (by the number its name starts with when those are all different, otherwise in order), with its name and a player, one playing at a time. That page does not reload, so playback is not cut by the board's refresh. Files are copied to `assets/`, up to 200 files, 100 MB each and 600 MB per decision; the page says how many were left out. Paths outside the project are ignored. Do not write the board address into `ask` or build your own page in the board folder; the button is the way in. Safari may not play `.ogg`; use `.mp3`, `.m4a` or `.wav` when the user listens in Safari.
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

The page opens in the browser the first time the project's board is drawn on the machine, and again only when a task newly goes to `doing`, so starting work brings it up and new sessions, turns, or edits do not. The tasks in progress at the last render are kept in `<project>.opened` beside the page. The browser is started detached, so it cannot hold the hook open. The hooks need `python3` on PATH and are skipped without it. They never block a prompt or a tool: an invalid board file is reported as a message and the previous page stays.

| Environment variable | Effect |
| --- | --- |
| `HARNESS_BOARD_OPEN=0` | Render without opening a browser (remote shells, CI) |
| `HARNESS_BOARD_HOME` | Folder for the pages instead of `~/.cache/engineering-workflow/boards` |

The project root is `CLAUDE_PROJECT_DIR` when the host sets it. Otherwise it is the nearest folder at or above the working directory that has a board file. `HARNESS_BOARD_HOME` must be an absolute path.
