# The method: running many apps with several agents

This is how I run about ten apps with several agent sessions (Claude Code and Codex, on more than one machine), and
how I plan to run a hundred. Everything here is in this repository and works without my private parts. Korean:
[method.ko.md](method.ko.md).

## The problem

With one app, a long `CLAUDE.md` and a chat history are enough. With many apps and many sessions they fail in
predictable ways:

- History files grow until every session pays to read them, and old decisions are lost anyway.
- Shared rules are copied into each app and drift apart.
- A fix in one app is not carried to the others that need it.
- Nobody sees at a glance what is done, what is next, and what waits for a decision.
- Agents write Korean that mixes speech levels and drops the app's own terms.

## The pieces

Each piece is a file format plus a small script. Files are always the source of truth. Anything derived from them
(a page, an index, a graph) can be deleted and rebuilt.

| Piece | File | Script | Needs |
| --- | --- | --- | --- |
| Workflow rules | `SKILL.md` of `engineering-workflow` | - | nothing |
| Progress board | `.harness/board.json` | `board.py` | nothing |
| Work records | `.harness/records/*.md` | `record.py` | nothing |
| Commit subjects from records | the record title | `auto_commit_push` hook | Git |
| Shared rules and drift | `templates/app/` | `app_template.py` | nothing |
| Korean copy | `.harness/copy-style.json`, `.harness/copy-corrections.md` | `copy_check.py` | nothing |
| One task per fresh session | the board, `WORKING.md` | `run_queue.py` | an agent CLI (`claude -p`) |
| Registry (search and graph questions) | all of the above, `WORKING.md`, `CREDITS.md`, Git history | `registry_scan.py`, `registry.py` | Neo4j, optional |
| Skill use counts | local session logs (Claude, Codex) | `registry_usage.py` | the registry |
| Prompt hint | the registry | `registry_hook.py` | the registry |
| Korean nouns for search | - | `registry_kiwi_server.py` | `kiwipiepy`, optional |
| Judge for the hint | - | `registry_judge_jev.py` | a hosted model, optional, sends data |

Start from the top of the table. Each row is useful alone, and the rows below it build on the files above.

### Workflow rules

The skill tells every session the same things: decide what "done" means before editing, run the checks the change
needs, prove a check by putting the defect back, have a different tool review the diff, and report the model,
checks, and open items. Decisions only the user can make are parked with a default, and work goes on.

### Progress board

One JSON file per app lists tasks, their prerequisites, and the decisions waiting for the user. A hook draws it as
a local HTML page, opens it once per session, and redraws it when the file changes. Sessions edit the JSON, never
the page. The page leads with what needs the user (decisions with their pictures, blocked tasks), then what is in
progress and what comes next, and groups the rest by state; an overview lists every board, the ones that need the
user first. See [board.md](../plugins/engineering-workflow/skills/engineering-workflow/references/board.md).

### Work records

One file of about fifteen lines per finished task: what was done, why, and what was dropped. The title becomes the
commit subject, so `git log` and the records agree. History stays cheap because a session reads only the record a
search returns, not a growing log. See
[records.md](../plugins/engineering-workflow/skills/engineering-workflow/references/records.md).

### One task per fresh session

A long session fills its context, and a compacted context loses detail. Because the board, the records, and
`WORKING.md` hold everything a session needs, `run_queue.py` can start a new agent session for each ready task,
check its result itself (task done, a new commit on the remote, a record, nothing left over), and only then start
the next. It adds no permissions and stops at the first problem. See
[run-queue.md](../plugins/engineering-workflow/skills/engineering-workflow/references/run-queue.md).

### Choosing models

The rule is the same in every session: the lightest model that can do the role, a standard one for integration
and debugging, the strongest for design, new systems, saved data, and high-risk review. A session cannot change its
own model, so the choice is made where work is handed out: a delegation names its model and reasoning level, a board
task may carry `model` and `effort` for `run_queue.py`, and a skill may name its preferred model, effort, and
fallback in its metadata. Every record states the model that ran and the one that reviewed, so the registry can show
what was actually used.

### Shared rules and drift

New apps start from one template. When a shared rule changes in the template, `drift` lists the apps that still
have the old text, and each app's own session updates it. See
[app-template.md](../plugins/engineering-workflow/skills/engineering-workflow/references/app-template.md).

### Korean copy

Each app keeps its speech level and terms in a style sheet, and every correction the user makes goes into a log.
A script fails when the old wording comes back or the levels mix; a person-like read is still required. See the
[korean-copy skill](../plugins/engineering-workflow/skills/korean-copy/SKILL.md).

### Registry

When there are enough apps that "which apps use this skill", "what else needs this fix", and "where did this asset
come from" take several searches, the files are scanned into a graph and asked with fixed commands. Besides the
harness files it reads each app's `WORKING.md` (sessions and what they hold), its `CREDITS.md` files (assets and
licenses), its Git history, and the counts of which skills agent sessions actually used. Only one sync writes at a
time, and a sync cut short is finished by the next. Every file is
read on each scan, and only the files whose content changed are written to the graph again. Plain text search over the same files still works when the server is down. See
[registry.md](../plugins/engineering-workflow/skills/engineering-workflow/references/registry.md) and the
[design](registry-design.md).

The prompt hook asks the registry for at most three skills, rules, or records that fit the prompt and attaches them
as a hint. A judge step can be swapped in; the built-in one is local. The optional hosted judge sends the prompt and
candidate descriptions off the machine, so it is off unless you turn it on.

## Try it

From a fresh checkout, with Python 3 and nothing else:

```bash
python3 examples/harness-demo/run.py
```

It runs every piece that needs no database on two sample apps: draws the shop board, checks its work record, scans
both apps into nodes and links, finds that the cafe app's shared rule drifted, and finds the mixed speech level and
an avoided term in the cafe's Korean strings. `--check` makes it exit 1 if any step gives an unexpected result; CI
runs it that way.

## Applying it to your own apps

1. Install the plugin, or copy the skill folders.
2. Start new apps with `app_template.py new`, or add the template's shared sections to an existing rules file.
3. Keep a board in each app and write a record when a task is done.
4. For Korean apps, write the style sheet once from the existing strings.
5. When search across apps becomes slow, add the registry: a local Neo4j server and a config listing your apps.
6. When sessions run long, let `run_queue.py` start one fresh session per task.

What stays private in my setup: the list of my apps, the database itself, keys (in the macOS keychain), and any
measurement of hosted services. None of it is needed to use the method.
