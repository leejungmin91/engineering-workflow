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

Independent review checks the diff and evidence when requested or when shared contracts, data, permissions, or deployments change. The final report lists the result, checks run, and open issues. When the host offers model selection, the workflow uses the lightest model suited to each role.

The plugin installs two hooks that act as mechanical safeguards: commit, push, and PR creation run only when the latest user message asks for them, and a commit that would add a secret is denied. See [Hooks](#hooks). Slack and Discord MCP can provide task context and stay optional. See the [skill index guide](plugins/engineering-workflow/skills/engineering-workflow/references/skill-index.md) and [MCP setup](docs/mcp-setup.md).

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

Installing the plugin registers these hooks in Claude Code and Codex. Codex asks you to trust plugin hooks once; until you do, they do not run.

| Hook | Event | What it does |
| --- | --- | --- |
| `guard_git` | `PreToolUse` on `Bash` and `PowerShell` | Denies `git commit`, `git push`, and PR/MR creation (`gh pr create`, `glab mr create`, push options, HTTP writes to a pulls or merge_requests API) unless the latest user message requests that action. Denies a commit whose added lines, or untracked files named by `git add`, contain a secret. |
| `record_prompt` | `UserPromptSubmit` | Codex only. Saves the current turn ID and requested Git actions under `~/.engineering-workflow/prompts/`. Each successful save removes files older than seven days. |

Use a direct request in the latest message, such as `커밋해 줘`, `푸시해`, `커밋 푸시`, `올려 줘` (commit and push), `commit it`, `push the changes`, `PR 만들어 줘`, or `open a pull request`. The guard ignores read-only, negated, and deferred requests. PR creation needs its own request in the current turn. Dry runs pass with `--dry-run` or the push-specific shorthand `git push -n`.

Requirements and limits:

- Python 3.9 or newer on PATH as `python3`, `python`, or `py`, and `sh` (Git for Windows provides it). When no interpreter runs, the guard denies the call and says so rather than failing open.
- The guard reads command text and repository state only. It cannot see inside scripts, aliases, or variables. Keep host permissions and branch protection for those.
- Claude Code reads the latest user message from the session transcript. Codex reads the current turn's action record. If the source is unavailable, the guard denies and explains why.
- To stop the hooks, disable or uninstall the plugin. That also turns off the skill. A user hook cannot override a denial.

The hook tests live in [`tools/hook_tests`](tools/hook_tests) and run with `python -m unittest discover -s tools/hook_tests`. They feed synthetic JSON to the hooks and create throwaway Git repositories; they never run the guarded commands.

## Use

> Use Engineering Workflow to identify what depends on this change, run the required checks, and report the result with a diagram.

The workflow defines the acceptance checks, orders the work, and revisits failed checks after a focused change. The optional checker uses Python 3.9 or later to validate the completion record against the current work snapshot.

```sh
python plugins/engineering-workflow/skills/engineering-workflow/scripts/check_record.py examples/incomplete.json --snapshot current
```

The example reports a failed regression, stale lint evidence, and a pending UI check. See the [record format](plugins/engineering-workflow/skills/engineering-workflow/references/harness-record.md).

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
