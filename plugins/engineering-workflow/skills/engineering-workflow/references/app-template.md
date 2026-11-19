# App template and drift check

With many apps, the shared rules (how to verify, where tasks and records go, how to commit) are copied into each
app's `CLAUDE.md` or `AGENTS.md`. Copies drift: one rule changes, and the apps started earlier keep the old text.
The template keeps one source for the shared sections and a check lists the apps that no longer match it.

## Start an app

```bash
python3 scripts/app_template.py new ~/Documents/shop
python3 scripts/app_template.py new ~/Documents/shop --name "Shop"
```

It copies every file of `templates/app/` into the folder, replaces `{{app}}` with the app name (the folder name by
default) in text files (escaped in `.json` files), and keeps any file that already exists. Empty folders are created. A path that would lead outside the folder through a symbolic link is not written. The shipped template has `CLAUDE.md` with the
shared sections, an empty `.harness/board.json`, and `.harness/records/`.

## Find drifted apps

```bash
python3 scripts/app_template.py drift                     # apps from the registry config
python3 scripts/app_template.py drift --app ~/Documents/shop --app Cafe=~/Documents/cafe
```

Every `## ` section of the template's rule file is a shared rule. For each app, the check reads `CLAUDE.md` (or
`AGENTS.md` when there is no `CLAUDE.md`) and reports:

| State | Meaning |
| --- | --- |
| `missing` | The app has no section with that heading |
| `differs` | The section text is different. The first changed line is shown |
| `no rule file` | The app has neither file |

`--app` takes a folder, or `name=folder` when the app was started with `--name`, so `{{app}}` is filled the same
way. Headings match without a trailing note such as `(user, 2026-11-19)`, ignoring case. Text matches by paragraph
with spaces and line wrapping ignored; lines inside code fences must match exactly. Sections only the app has are not reported. Exit 0 means every app matches, 1 means drift, 2
means the check could not run.

## Changing a shared rule

1. Edit the section in the template.
2. Run `drift`. Every app listed as `differs` still has the old text.
3. Update those apps, each in its own repository and by the session that owns it, then run `drift` again.

To keep a different version of a shared rule on purpose, give the app's section a different heading, so the shared
one shows as `missing` and the reason sits in the app's own text.

A template of your own works the same way: `--template <folder>`.
