# Registry design

Status: the [progress board](../plugins/engineering-workflow/skills/engineering-workflow/references/board.md) and the [scanner](#scanner) are shipped. The query commands, the language layer, and the prompt hook are design and not shipped yet. Session and Machine nodes are not read yet.

The registry answers questions that span many projects: which skill fits this prompt, what did we do about this six months ago, what breaks if this skill changes, where did this asset come from. An agent that works these out by itself searches again and again, and every search result stays in its context. The registry follows the links once and returns a few lines.

## Rules

1. Files are the source of truth. Skills, settings, work records, and boards stay in files under version control. The registry is rebuilt from them and is never edited by hand. Deleting it loses nothing.
2. Every link comes from something written in a file. A relation nobody wrote down does not exist in the registry. The frontmatter conventions below are therefore part of the method.
3. Agents and hooks call fixed commands. They do not write database queries. The store behind the commands can change without touching skills or hooks.
4. A changed file is indexed again when the next query runs. No separate sync step.
5. A hook that queries the registry never blocks a prompt. When the store is down, the prompt goes through without candidates.
6. The running store, its data, keys, personal glossaries, and usage logs stay out of public repositories.

## Nodes

| Node | What it is | Read from |
| --- | --- | --- |
| App | One project repository | The repository root and its `CLAUDE.md` or `AGENTS.md` |
| Plugin | A set of skills and hooks with a version | `plugin.json` |
| Skill | One `SKILL.md` | Skill folders in plugins, projects, and the user folder |
| Tool | An MCP server, hook, or script a skill needs | Skill frontmatter, `hooks.json`, MCP settings |
| Model | A model with a reasoning level | Skill frontmatter, work records |
| Task | One unit of planned work | `.harness/board.json` |
| Decision | Something the user decided or is asked to decide | Board decisions, work records |
| Record | What was done for one task and why | `.harness/records/*.md` |
| Commit | One commit | Git, through the record that names it |
| Asset | An image, model, sound, or other produced file | `.harness/assets/*.md` |
| Source | Where an asset came from and its license | Asset records |
| Session | One agent session and its role | `WORKING.md` |
| Machine | A computer that runs sessions | `WORKING.md` |
| Rule | One rule in an instruction file | Headings in `CLAUDE.md` and `AGENTS.md` |
| Term | A word the user says for something | The glossary file |
| Checkout | A worktree or copy of an app that has its own plugin install | `installed_plugins.json` entries whose path is not a listed app |

## Links

| From | Link | To | Written in |
| --- | --- | --- | --- |
| App | USES | Plugin | Enabled plugins in the app's settings (`scope: project`) or the user settings (`scope: user`) |
| App | DISABLES | Plugin | A plugin switched off in the app's settings |
| App or Checkout | INSTALLED | Plugin | `installed_plugins.json`, with the installed `version` and `scope` |
| Plugin | PROVIDES | Tool | Hook scripts registered in the plugin's `hooks.json`, with their events |
| Plugin | PROVIDES | Skill | The plugin's skill folder |
| App | HAS | Skill | The app's own skill folder |
| Skill | REQUIRES | Tool or Skill | Skill frontmatter `requires` |
| Skill | SUPERSEDES | Skill | Skill frontmatter `supersedes` |
| Skill | PREFERS | Model | Skill frontmatter `model`, `effort`, `fallback` |
| Task | AFTER | Task | Board `after` |
| Task | IN | App | The board's repository |
| Decision | IN | App | Open decisions on the board, settled ones in records |
| Decision | AFFECTS | Task | Record frontmatter `decisions` |
| Record | FOR | Task | Record frontmatter `task` |
| Record | IN | App | The record's repository |
| Record | USED | Skill | Record frontmatter `skills` |
| Record | RAN_ON | Model | Record frontmatter `model` |
| Record | PRODUCED | Commit | Record frontmatter `commits` |
| Record | CONCERNS | Skill or Tool | Record frontmatter `concerns` |
| Commit | REVIEWED_BY | Model | Record frontmatter `review` |
| Asset | IN | App | The asset record's repository |
| Asset | VERSION_OF | Asset | Asset frontmatter `version_of` |
| Asset | FROM | Source | Asset frontmatter `source`, `license` |
| Asset | MADE_BY | Model | Asset frontmatter `made_by` |
| Decision | APPROVED | Asset | Asset frontmatter `approved_by` |
| Session | HOLDS | Task | `WORKING.md` lane lines |
| Session | ON | Machine | `WORKING.md` session lines |
| Rule | APPLIES_TO | App | The file the rule is in. A rule in the user folder applies to every app |
| Term | ALIAS_OF | Any node | The glossary file |

## Frontmatter

Skill files keep `name` and `description` as they are. Registry fields go under `metadata` as text values, which the Agent Skills format allows. Lists are comma-separated.

```markdown
---
name: store-release
description: "Use when preparing a store release: build numbers, screenshots, review notes."
metadata:
  requires: "mcp:app-store, skill:engineering-workflow"
  supersedes: "ios-release"
  model: "sonnet"
  effort: "medium"
  fallback: "opus"
---
```

A work record is one small file per finished task. Keep the body under about fifteen lines: what was done, why, and what was tried and dropped. The commit subject is the record title.

```markdown
---
id: 2026-11-19-refund-rounding
title: Round refunds per line item
task: T2
skills: "engineering-workflow"
model: "sonnet"
commits: "a1b2c3d"
review: "codex: no findings"
concerns: "skill:payments"
decisions: "Ship behind a flag"
---

Refund totals were off by one unit when an order mixed tax rates. Rounding moved from the order total to each line.
Dropped: rounding in the display layer, because exports use the stored value.
```

An asset record sits beside the board, one file per asset that matters for licensing or review.

```markdown
---
id: hero-portrait-v3
file: "Assets/Art/hero_portrait.png"
version_of: hero-portrait-v2
source: "generated"
license: "own work"
made_by: "image-model-name"
approved_by: "2026-11-17 portrait review"
---
```

The glossary is one line per term: the user's word, then the real name.

```text
레그 = RAG
눈밥 = app:slopes
```

## Scanner

`scripts/registry_scan.py` in the skill folder reads the files above and prints nodes and links grouped by the file each one came from. It uses the standard library only, runs nothing it reads, and needs no database.

```sh
python3 scripts/registry_scan.py /absolute/path/to/registry.json --out /absolute/path/to/graph.json
```

```json
{
  "apps": [{"name": "shop", "path": "/absolute/path/to/shop"}],
  "user": "/absolute/path/to/.claude",
  "plugins": ["/absolute/path/to/a/plugin"],
  "glossary": "/absolute/path/to/glossary.txt"
}
```

Only `apps` is required. The output has one entry per file with its `kind`, a `hash`, and the `nodes` and `links` it states. A file that cannot be read gets an `error` and no facts, and the rest is still read.

A store adapter keeps the hash of every file it loaded. On the next run it replaces the facts of files whose hash changed, drops the facts of files that are gone, and leaves the rest alone. The hash covers the file content and which apps the file applies to, so adding an app re-reads the user-level files. A node that several files state stays until the last of them is gone. This repository does not ship an adapter: the author's runs against a local graph server and is kept private with its data.

## Commands

| Command | Question it answers | Path it follows |
| --- | --- | --- |
| `find <words>` | Which skill, record, or asset matches these words | Text search, then glossary aliases |
| `neighbors <node>` | What is directly linked to this | One step in every direction |
| `impact <skill or tool>` | What is affected if this changes | REQUIRES and USES backwards to apps, then open tasks and releases |
| `spread <record>` | Which other apps need the same fix | CONCERNS to the skill or tool, then USES backwards, minus apps with a matching record |
| `lineage <asset>` | Where did this asset come from and who approved it | VERSION_OF repeatedly, then FROM, MADE_BY, APPROVED |
| `needs <skill>` | What must be enabled for this skill to work | REQUIRES repeatedly |
| `latest <skill>` | What replaced this skill | SUPERSEDES backwards repeatedly |
| `dupes <description>` | Does a similar skill already exist | Text search over skill descriptions |
| `unused` | Which skills does no app use and no record mention | Skills without USES, HAS, or USED links |

Each command prints a few lines with node names and file paths. The agent opens only the files it needs.

## Question shapes

These come from six days of real prompts across three projects. They are the acceptance test for the scanner and the commands: each must be answered by one command.

| Question | Command | Steps |
| --- | --- | --- |
| How far along is this app and what is left | board, no query | 1 |
| Which model and reasoning level for this kind of task, and what is the fallback | `neighbors` on the skill | 2 |
| Was this commit cross-reviewed, and by what | `neighbors` on the record | 2 to 3 |
| Which version of this asset was approved, from which reference, made by what | `lineage` | 3 to 4 |
| Which tasks does this decision hold up | `neighbors` on the decision | 2 to 3 |
| What did we do about this months ago | `find`, then `neighbors` | 2 |
| Which projects still carry the old version of this rule | `impact` on the rule | 2 to 3 |
| This fix: which other apps need it | `spread` | 3 to 4 |
| This skill changes: which apps must be verified again | `impact` | 3 to 4 |
| Which shipped apps contain assets under this license | `neighbors` on the source, then releases | 3 |

## Order of work

1. Board (shipped).
2. Scanner: files to nodes and links, changed files only (shipped).
3. Commands, checked against the question shapes with real answers.
4. Language layer: morpheme tokens and the glossary for non-English prompts.
5. Prompt hook: search, a judge step that can be swapped, at most three candidates.
6. Work records and commit subjects taken from them.
