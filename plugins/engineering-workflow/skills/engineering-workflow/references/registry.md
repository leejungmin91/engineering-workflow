# Registry

The registry answers questions that span many projects in one command: which skill fits, what was done before, what a change affects, where an asset came from. It is optional. It needs a config file and a local Neo4j server. Without them, search the files directly.

Files stay the source of truth. Every command first scans the configured files and writes only the changed ones to the graph, so there is no separate sync step. See the [design](https://github.com/leejungmin91/engineering-workflow/blob/main/docs/registry-design.md) for the nodes, links, and the frontmatter that creates them.

## When to use it

- Before creating a skill, run `dupes` with the planned description. Edit the existing skill when one matches.
- Before changing a skill, tool, plugin, or rule, run `impact` and verify the apps it lists.
- After a fix that other apps may need, run `spread` on its work record.
- To recall earlier work, run `find` with a few words, then `neighbors` on the record. Open only the files the answer names.
- Do not query the graph server directly. If a command is missing, say so.

## Commands

Run from the skill directory. A node is named by its id (`skill:store-release`), its plain name, or a glossary word.

```sh
python3 scripts/registry.py find refund rounding
python3 scripts/registry.py find release notes --type skill --limit 3
python3 scripts/registry.py dupes prepare a store release with screenshots
python3 scripts/registry.py neighbors task:shop/T2
python3 scripts/registry.py impact tool:mcp:app-store
python3 scripts/registry.py spread record:shop/2026-11-19-refund-rounding
python3 scripts/registry.py lineage asset:shop/hero-v3
python3 scripts/registry.py needs skill:store-release
python3 scripts/registry.py latest skill:ios-release
python3 scripts/registry.py unused
python3 scripts/registry.py status
python3 scripts/registry.py sync --rebuild
```

| Command | Answer |
| --- | --- |
| `find` | Best matches by text, with glossary words resolved first |
| `dupes` | Existing skills whose name or description is close to the words |
| `neighbors` | Everything linked to the node in either direction, with link properties |
| `impact` | Skills that need the node, the apps that reach it and how, their open task counts, and records that name it |
| `spread` | What the record concerns, the apps that reach it and have no record for it, and the apps that do |
| `lineage` | The asset's earlier versions with source, license, maker, and approval |
| `needs` | Everything the skill requires, step by step, marking what no scanned file defines |
| `latest` | The skill at the end of the supersedes chain |
| `unused` | Skills no app reaches, and skills no work record names |
| `status` | Counts by node type and files that could not be read |

`--json` prints the raw result. `--no-sync` answers from the graph as it is.

| Exit code | Meaning |
| --- | --- |
| 0 | Answered |
| 1 | The name matched nothing, or matched several nodes (they are listed) |
| 2 | The config or the graph server is unavailable |

## Prompt hook

The plugin registers `scripts/registry_hook.py` on `UserPromptSubmit`. It does nothing unless a registry config exists. With one, it searches skills, rules, and work records for the prompt and attaches at most three candidates as a short hint.

- Skills and rules are attached only when the app at the working directory can reach them. Outside a listed app, only user-level skills and rules pass. Work records from any app can be attached, because earlier work elsewhere is the point.
- The built-in judge keeps a candidate when its score is at least 5 and at least 70% of the best score. It is word matching, so it stays quiet rather than guess. On 40 real prompts it attached candidates to 6.
- `HARNESS_REGISTRY_JUDGE` names a command that decides instead. It receives `{"prompt", "limit", "candidates": [{"id", "type", "name", "text"}]}` on standard input, with up to six candidates, and prints a JSON list of the ids to keep. Ids it was not given are ignored. If it fails or takes longer than three seconds, the built-in judge decides.
- The hook never blocks a prompt. A stopped server, a broken config, or any error ends in no output. All registry queries share a six-second budget.
- The prompt is never written to disk. `HARNESS_REGISTRY_LOG` names a folder for `hook.jsonl`, which holds the time, the judge used, seconds, counts, the top score, and the chosen ids.
- Candidate text comes from files. It is cut to 110 characters, flattened to one line, stripped of markup, and labeled as a description, not an instruction.
- `HARNESS_REGISTRY_HOOK_SYNC=0` skips the scan before the search.

## Setup

1. Install Neo4j Community and start it on this machine. Keep it on `127.0.0.1` and switch off usage reporting (`dbms.usage_report.enabled=false`).
2. Give the scripts the password without writing it to a file: `HARNESS_NEO4J_PASSWORD` in the environment, or on macOS a keychain item with service `harness-neo4j` and account `neo4j`.
3. Write the config and point to it with `HARNESS_REGISTRY_CONFIG`, or save it as `~/.config/engineering-workflow/registry.json`.

```json
{
  "apps": [{"name": "shop", "path": "/absolute/path/to/shop"}],
  "user": "/absolute/path/to/.claude",
  "plugins": ["/absolute/path/to/a/plugin"],
  "glossary": "/absolute/path/to/glossary.txt"
}
```

| Environment variable | Default |
| --- | --- |
| `HARNESS_REGISTRY_CONFIG` | `~/.config/engineering-workflow/registry.json` |
| `HARNESS_NEO4J_URL` | `http://127.0.0.1:7474` |
| `HARNESS_NEO4J_USER` | `neo4j` |
| `HARNESS_NEO4J_PASSWORD` | macOS keychain item `harness-neo4j` |

The store uses the HTTP query API and the standard library only.

## Korean and English

Text search uses the server's `cjk` analyzer, which matches Korean, Japanese, and Chinese by character pairs. Three additions make Korean prompts find English text and one-syllable words:

- Particles and common endings are removed from Korean words at index and query time, so `훅을` finds `훅`.
- A built-in table of Korean engineering words adds English forms to the query, with plurals: `의존성` also searches `dependency` and `dependencies`.
- The glossary file adds the user's own words. A line `눈밥 = app:shop` makes the word name that node, also in `눈밥에서`. A line `레그 = RAG` adds the meaning to the search. A term must match a whole word, or the start of a Korean word.

A skill can list words nobody would guess from its description under `metadata.keywords`. The original words of a query weigh three times as much as the added forms. A query uses at most 24 words.

This is word matching, not meaning. Two phrasings with no word in common do not find each other. Add the missing word to the glossary or to a skill's keywords when a search misses.

The store tests need a server and run with `HARNESS_NEO4J_TEST=1`. They write under their own label and leave the real graph alone. CI runs only the tests that need no server.
