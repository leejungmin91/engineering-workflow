# Work records

A work record is one small file per finished task, kept in the project at `.harness/records/`. It answers the
question a later session will ask: what was done here, why, and what was tried and dropped. Long history files
grow until nobody reads them. A record is found by search and read alone, so the cost of history stays flat.

## Format

```markdown
---
id: 2026-11-19-refund-rounding
title: "Round refunds per line item"
task: "T2"
skills: "engineering-workflow"
model: "sonnet"
review: "codex: no findings"
concerns: "skill:payments"
decisions: "Ship behind a flag"
---

Refund totals were off by one unit when an order mixed tax rates. Rounding moved from the order total to each line.
Dropped: rounding in the display layer, because exports use the stored value.
```

| Field | Meaning |
| --- | --- |
| `id` | The file name without `.md`. Starts with the date |
| `title` | One line, written as a commit subject |
| `task` | The task ID on the board |
| `skills`, `model` | What was used, comma separated |
| `review` | Reviewer, a colon, and the verdict |
| `concerns` | The skill, tool, or rule the work is about. `spread` uses it to find other apps that need the same fix |
| `decisions` | Decisions the user made during the task, comma separated |
| `commits` | Earlier commits of the same task. The commit that adds the record does not need to be listed |
| `keywords` | Extra search words |

Only `id` and `title` are required. Keep the body under about fifteen lines. Write it in the language the project
is discussed in, because that is the language it will be searched in.

## Writing and checking

```bash
python3 scripts/record.py new "Round refunds per line item" --task T2 --concerns skill:payments <<'TEXT'
Refund totals were off by one unit when an order mixed tax rates. Rounding moved from the order total to each line.
Dropped: rounding in the display layer, because exports use the stored value.
TEXT
python3 scripts/record.py check
```

`new` writes `.harness/records/<date>-<title words>.md` in the current folder (or `--root`) and prints the path. It
does not overwrite an existing record. `check` exits 1 when a record has no frontmatter, no title, no body, or an
`id` that differs from its file name.

## Commit subject

Write the record in the same change as the work. When the `auto_commit_push` hook commits a change that adds a
record, the record's title becomes the commit subject, so `git log` and the records say the same thing. With
several new records, the first title is used with `(+N more records)`. A change that only edits an old record, or a
record whose title is empty or longer than 200 bytes, gets the usual `Update <paths>` subject.

When you commit by hand, use the record title as the subject yourself.

## Finding a record later

With a [registry](registry.md) configured, `find` searches titles, bodies, and keywords, and `neighbors` on the
record shows its task, skills, model, and decisions. Without a registry, search the folder with the usual text
search. The files are the source either way.

## When to write one

- A task on the board is finished.
- A fix that other apps may need.
- A decision by the user that changes later work.

Skip it for a typo, a formatting change, or anything the commit subject already says in full.
