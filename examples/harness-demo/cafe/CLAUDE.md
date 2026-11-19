# Project rules: cafe

App-specific rules go in their own sections below the shared ones. The shared sections come from the app template
of the engineering-workflow skill; change them there and run `app_template.py drift` to find the apps that still
have the old text.

## Workflow

Use the engineering-workflow skill for code, configuration, and technical documentation changes. Run the full test
suite before every commit.

## Progress board

Keep `.harness/board.json` current: every known task with its prerequisites, and the decisions waiting for the
user with the default in use meanwhile.

## Work records

When a board task is finished, write one record in `.harness/records/` in the same change with
`python3 scripts/record.py new "<title>" --task <id>`. The title is the commit subject.

## Commit and push

Commit only the task's files, by name, and confirm the push reached the remote before reporting it.
