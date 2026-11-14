# Engineering Workflow

[한국어](README.ko.md)

One portable Agent Skill for harness engineering, verification loops, and task dependency graphs. Use it from a CLI or an app and add Slack or Discord context when the task needs it.

## Architecture

**Install.** Register the GitHub repository as a marketplace and install the plugin in Codex or Claude Code. The host keeps a local copy of the skill. Other Agent Skills hosts can load the same skill directory directly.

**Run.** The index is a local file (`skill-index.json`) with skill names, short descriptions, and file paths. When configured, the `UserPromptSubmit` hook searches it first and sends up to three candidate names to the host. The host confirms availability and reads the selected `SKILL.md` and relevant references. A plugin-only installation uses the host's own skill catalog.

**Language.** The bundled skill descriptions and operating instructions are written in English. Users can write prompts in their preferred language. The local search maps common Korean engineering terms to English keywords. Measure actual token use to quantify any savings.

**Solid arrows** show the main workflow. **Dotted arrows** show the extra lookup that runs when the prompt hook is configured. A review finding that requires a fix goes back to verification.

```mermaid
flowchart TB
    Prompt["User prompt"] --> Catalog["Check available skills"]
    Prompt -. runs first if enabled .-> Index["Search local<br/>skill index"]
    Index -. up to 3 candidates .-> Catalog
    Catalog --> Skill["Read selected skill"]
    Skill --> Harness["Harness<br/>Set pass criteria"]
    Harness --> Graph["Task graph<br/>Order the work"]
    Graph --> Loop["Verification loop<br/>Check, fix, repeat"]
    Loop --> Review["Review as needed"]
    Review -->|fix required| Loop
    Review --> Report["Report evidence"]
```

| Part | What it does | Example |
| --- | --- | --- |
| Harness | Defines scope, expected behavior, and the checks needed to finish. | A parser change must preserve valid input and return the expected error for invalid input. |
| Task graph | Records prerequisites and determines which steps can run independently. | Confirm the parser contract, update the parser, then check both callers in parallel. |
| Verification loop | Runs checks against the current change and rechecks the affected cases after a focused fix. | Reproduce a caller failure, fix the cause, and rerun its regression check. |

The task graph selects checks from the final diff. Copy-only and image-only changes get a direct content or display check and skip automated tests unless the project requires them. Mixed changes also run the tests for the affected behavior. [Verification paths](docs/workflow-flow.md)

Independent review checks the diff and evidence when requested or when shared contracts, data, permissions, or deployments change. The final report lists the result, checks run, open issues, applied skills, actual model settings, and observed usage. The workflow chooses the lightest suitable model for each role when the host offers a choice. For a fixed session, the report records the host's settings.

The plugin installs one hook: when the assistant finishes a turn, the work left in the repository is committed and pushed. This harness is for personal projects, so finished work is never held back waiting for a commit request. See [Hooks](#hooks). Slack and Discord MCP can provide task context and stay optional. See the [skill index guide](plugins/engineering-workflow/skills/engineering-workflow/references/skill-index.md) and [MCP setup](docs/mcp-setup.md).

## Install

### Codex CLI and desktop app

```sh
codex plugin marketplace add leejungmin91/engineering-workflow --ref main
codex plugin add engineering-workflow@engineering-workflow
```

If you registered a previous pinned version, run `codex plugin marketplace remove engineering-workflow` before adding the new version.

In Codex desktop, restart after adding the marketplace and install **Engineering Workflow** from the **Engineering Workflow** source in the Plugins Directory. Open a new chat to use the skill. [Codex marketplace docs](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)

### Claude Code

```sh
claude plugin marketplace add https://github.com/leejungmin91/engineering-workflow.git
claude plugin install engineering-workflow@engineering-workflow
```

In a new session, run `/engineering-workflow:engineering-workflow`. On Claude Code 2.1.275 or later, the in-session command below opens the installation screen.

```text
/plugin install engineering-workflow --marketplace leejungmin91/engineering-workflow
```

To update an existing installation, run `claude plugin marketplace update engineering-workflow` and then `claude plugin update engineering-workflow@engineering-workflow`. Restart Claude Code to apply the update.

[Claude Code marketplace docs](https://code.claude.com/docs/en/plugin-marketplaces)

### Claude Desktop, web, and Cowork

Open **Customize → Plugins → Add → Add marketplace**. Add `leejungmin91/engineering-workflow` as a repository, then add **Engineering Workflow** from that source. Your plan and organization policy control which marketplaces and tools are available. [Claude app plugin docs](https://support.claude.com/en/articles/13837440-use-plugins-in-claude)

### Cursor, Gemini CLI, and other Agent Skills hosts

Copy the entire [engineering-workflow skill directory](plugins/engineering-workflow/skills/engineering-workflow) into your tool's Agent Skills directory. Cursor and Gemini CLI both document `~/.agents/skills/` for user-wide use. For other hosts, use their documented location. In a chat app that only accepts text, provide the SKILL.md as instructions and use the app's available tools. [Cursor](https://prod.cursor.com/docs/skills) · [Gemini CLI](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/using-agent-skills.md)

## Hooks

Installing the plugin registers this hook in Claude Code. Codex asks you to trust plugin hooks once; until you do, they do not run, and check that your Codex version fires `Stop` before relying on it there.

| Hook | Event | What it does |
| --- | --- | --- |
| `auto_commit_push` | `Stop` | When the assistant finishes a turn, runs `git add -A`, commits with the subject `Update <top-level paths>` and a file list in the body, and pushes to the tracked upstream (`-u origin <branch>` when the branch has none). A clean tree produces no commit. |

The hook is a convenience for personal projects, not a safeguard. Write a hand-written commit yourself when the work deserves one; the hook then finds nothing to commit. It never blocks the turn: failures are shown as a message and the exit code stays 0. `AUTO_COMMIT_TRAILER` replaces the default `Co-Authored-By` trailer, and `--dry-run` prints the plan without changing anything.

Requirements and limits:

- POSIX `sh` and `git` on PATH (Git for Windows provides both). No Python is needed for the hook.
- Everything not ignored by `.gitignore` is committed, including half-finished edits left at the end of a turn. Secrets are not scanned; keep `.gitignore`, host permissions, and branch protection for that.
- To stop the hook, disable or uninstall the plugin. That also turns off the skill.

The hook tests live in [`tools/hook_tests`](tools/hook_tests) and run with `python -m unittest discover -s tools/hook_tests`. They create throwaway Git repositories with a bare remote and run the hook against them.

## Use

> Use Engineering Workflow to identify what depends on this change, run the required checks, and report the result with a diagram.

The workflow defines the acceptance checks, orders the work, and revisits failed checks after a focused change. The optional checker uses Python 3.9 or later to validate the completion record against the current work snapshot.

```sh
python plugins/engineering-workflow/skills/engineering-workflow/scripts/check_record.py examples/incomplete.json --snapshot current
```

The example reports a failed regression, stale lint evidence, and a pending UI check. See the [record format](plugins/engineering-workflow/skills/engineering-workflow/references/harness-record.md).

### Usage display

#### Codex CLI

Run `/statusline` to choose fields for your terminal footer, or set this array under the existing `[tui]` section in `~/.codex/config.toml` and reopen Codex CLI. [Codex CLI commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli#configure-footer-items-with-statusline)

```toml
[tui]
status_line = ["model-with-reasoning", "context-used", "context-remaining", "context-window-size", "used-tokens", "five-hour-limit", "weekly-limit"]
```

The footer shows the model and reasoning level, context usage and capacity, cumulative session tokens, and available account limits. The engineering workflow also reads the latest local usage snapshot for its final report when Python 3 and the current Codex session log are available.

#### Claude Code

[`integrations/statusline/claude-usage.sh`](integrations/statusline/README.md) draws the model, a context window bar with occupied tokens and capacity, and the 5-hour and 7-day account limits with reset times. Copy it to `~/.claude/statusline-usage.sh` and add a `statusLine` command to `~/.claude/settings.json`. A plugin cannot set the status line, so this is a one-time manual step. The script needs `sh` and `jq`.

```json
"statusLine": { "type": "command", "command": "sh ~/.claude/statusline-usage.sh", "padding": 0 }
```

## Source skills

The plugin ships one skill, `engineering-workflow`. Its workflow adapts techniques from these ten source skills.

| Source skill | Technique used here |
| --- | --- |
| Matt Pocock · `diagnosing-bugs` | Reproduce the failure with the smallest useful input before editing. |
| Superpowers · `verification-before-completion` | Use passing results from the final work snapshot as completion evidence. |
| ECC · `eval-harness` | Define success and regression cases, then compare the same cases before and after a workflow change. |
| Karpathy Skills · `karpathy-guidelines` | Set a clear scope and checks, and keep the diff focused. |
| Anthropic · `webapp-testing` | Verify the affected user flow in the actual interface when available. |
| Ponytail · `ponytail` | Look for existing code and tools before adding new ones. |
| UI UX Pro Max · `ui-ux-pro-max` | Include accessibility and relevant viewport sizes in UI checks. |
| Graphify · `graphify` | Mark task dependencies as confirmed or inferred. |
| gstack · `review` | Inspect the final diff for impact on shared contracts, data, and permissions. |
| Caveman · `caveman` | Lead with results and evidence while keeping important conditions visible. |

See the [source notes](plugins/engineering-workflow/skills/engineering-workflow/references/source-skills.md) for the selection method and links to the exact source revisions.

## Further reading

- [Workflow, cross-review, and report diagrams](docs/workflow-flow.md)
- [Multi-host implementation report](docs/implementation-report.md)
- [Hook scope and the optional skill index hook](plugins/engineering-workflow/skills/engineering-workflow/references/hook-recommendations.md)
- [Plugin index](plugins/engineering-workflow/INDEX.md) · [Changelog](plugins/engineering-workflow/CHANGELOG.md)
