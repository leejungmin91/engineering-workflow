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

The store uses the HTTP query API and the standard library only. Text search uses the server's `cjk` analyzer, which matches Korean, Japanese, and Chinese by character pairs. Words in one language do not find text in another unless the glossary links them.

The store tests need a server and run with `HARNESS_NEO4J_TEST=1`. They write under their own label and leave the real graph alone. CI runs only the tests that need no server.
