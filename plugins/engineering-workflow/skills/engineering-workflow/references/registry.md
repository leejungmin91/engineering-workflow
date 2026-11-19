# Registry

The registry answers questions that span many projects in one command: which skill fits, what was done before, what a change affects, where an asset came from. It is optional. It needs a config file and a local Neo4j server. Without them, search the files directly.

Files stay the source of truth. Every command first scans the configured files and writes only the changed ones to the graph, so there is no separate sync step. See the [design](https://github.com/leejungmin91/engineering-workflow/blob/main/docs/registry-design.md) for the nodes, links, and the frontmatter that creates them.

## When to use it

- Before creating a skill, run `dupes` with the planned description. Edit the existing skill when one matches.
- Before changing a skill, tool, plugin, or rule, run `impact` and verify the apps it lists.
- After a fix that other apps may need, run `spread` on its work record.
- To recall earlier work, run `find` with a few words, then `neighbors` on the record. Every app's git history is in the graph too: `find ... --type commit` finds a commit by its subject or body, and `neighbors` shows its branch when it is not merged. Open only the files the answer names.
- Do not query the graph server directly. If a command is missing, say so.

## Commands

Run from the skill directory. A node is named by its id (`skill:store-release`), its plain name, or a glossary word.

```sh
python3 scripts/registry.py find refund rounding
python3 scripts/registry.py find release notes --type skill --limit 3
python3 scripts/registry.py find unused images cleanup --type commit
python3 scripts/registry.py dupes prepare a store release with screenshots
python3 scripts/registry.py neighbors task:shop/T2
python3 scripts/registry.py impact tool:mcp:app-store
python3 scripts/registry.py spread record:shop/2026-11-19-refund-rounding
python3 scripts/registry.py lineage asset:shop/hero-v3
python3 scripts/registry.py needs skill:store-release
python3 scripts/registry.py latest skill:ios-release
python3 scripts/registry.py unused
python3 scripts/registry.py sessions app:game
python3 scripts/registry.py licenses app:game --group audio --attribution
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
| `licenses` | Credited assets by folder and license: count, what the license asks, source hosts, the credit file. `--attribution` keeps only what needs credit, a notice, or a check |
| `sessions` | The app's sessions from `WORKING.md`, their machine, session id, and the lane work each holds |
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
- Candidates named through the glossary are always kept. The judge decides only among the searched ones.
- The hook never blocks a prompt. A stopped server, a broken config, or any error ends in no output. All registry queries share a six-second budget.
- The prompt is never written to disk. `HARNESS_REGISTRY_LOG` names a folder for `hook.jsonl`, which holds the time, the judge used, seconds, counts, the top score, and the chosen ids.
- Candidate text comes from files. It is cut to 110 characters, flattened to one line, stripped of markup, and labeled as a description, not an instruction.
- `HARNESS_REGISTRY_HOOK_SYNC=0` skips the scan before the search.

## A hosted judge: Jev

`HARNESS_REGISTRY_JUDGE=jev` runs `scripts/registry_judge_jev.py`. It asks TypeSafe's Jev decision model one yes-or-no question per candidate and keeps the candidates at or above a probability threshold, best first.

This sends data off the machine on every prompt that has candidates: the prompt, and the type, name, and first 300 characters of the description of up to six candidates. Work record text is included when a record is a candidate. Leave the variable unset to keep everything local.

| Environment variable | Default |
| --- | --- |
| `TYPESAFE_API_KEY` | macOS keychain item with service `harness-jev` and account `typesafe` |
| `HARNESS_JEV_THRESHOLD` | `0.5`, a number from 0 to 1 |
| `HARNESS_JEV_MODEL` | `jev-latest` |
| `TYPESAFE_BASE_URL` | `https://api.typesafe.ai`. Must be `https`, or `http` on this machine |

The key is sent only to that address, redirects are refused, and the key is never printed. A failed or slow call leaves the decision to the built-in judge. Candidate text is flattened, stripped of markup, and quoted as a description. All candidates share one request, so a hostile description could still sway the answer for another candidate. The cost of that is a wrong hint, since ids the hook did not offer are ignored.

To write another judge, read the same JSON on standard input and print a JSON list of ids.

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

### Optional analyzer for Korean

The rules above miss one-syllable nouns written without a space, such as `창돌을` for 창 and 돌. On 2,500 real Korean commit messages and document sections, a one-syllable noun query found 24% of the records that contain the noun with the rules and 95% with the Kiwi analyzer, where "contains" is judged by Kiwi itself. Nouns of two or more syllables went from 90% to 98%. Add the analyzer before indexing Korean work records.

`scripts/registry_kiwi_server.py` serves Kiwi's nouns on `127.0.0.1` only. It needs the `kiwipiepy` package (Apache-2.0, about 170 MB with its model), which may need an older Python than the one that runs the registry, so give it its own environment:

```sh
python3.13 -m venv /absolute/path/to/kiwi-venv
/absolute/path/to/kiwi-venv/bin/pip install kiwipiepy
/absolute/path/to/kiwi-venv/bin/python scripts/registry_kiwi_server.py --port 8792
export HARNESS_TOKENIZER_URL=http://127.0.0.1:8792
python3 scripts/registry.py sync --rebuild
```

- With the variable set and the service answering, its nouns replace the rule stems at index and query time. When it is down or slow, the rules are used and nothing fails. A prompt lookup waits at most half a second for it.
- Rebuild after switching the analyzer on or off, because index terms are written when a file is loaded.
- The address must be `http` on this machine. Text is never sent to another host, redirects are refused, and proxies are bypassed.
- The service refuses requests that carry an `Origin` header or another host name, so a web page cannot use it.

This is word matching, not meaning. Two phrasings with no word in common do not find each other. Add the missing word to the glossary or to a skill's keywords when a search misses.

The store tests need a server and run with `HARNESS_NEO4J_TEST=1`. They write under their own label and leave the real graph alone. CI runs only the tests that need no server.
