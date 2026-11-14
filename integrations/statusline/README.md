# Claude Code usage status line

`claude-usage.sh` draws a one-line footer for Claude Code from the JSON the host passes to a status line command:

```
Opus 5.5 │ ctx ███░░░░░░░ 32% (64k/200k) │ 5h █████░░░ 63% ↻18:53 │ 7d ███████░ 88% ↻11/18 20:06
```

- `ctx` is the conversation context window: used percentage, occupied tokens, and capacity. When the host omits the percentage, the script computes it from `current_usage`.
- `5h` and `7d` are account usage windows with their reset times. They appear only when the host sends `rate_limits`.
- Bars avoid a red/green scale so they stay readable in daltonized themes: cyan below 50%, yellow below 80%, magenta from 80%.
- Missing values show as `?`. The script needs POSIX `sh` and `jq`.

## Install

A plugin cannot set the status line, so install it once in your user settings:

```sh
cp integrations/statusline/claude-usage.sh ~/.claude/statusline-usage.sh
```

Then add this to `~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "sh ~/.claude/statusline-usage.sh",
  "padding": 0
}
```

The footer updates from the next prompt. Try it without Claude Code:

```sh
echo '{"model":{"display_name":"Opus"},"context_window":{"context_window_size":200000,"used_percentage":32}}' | sh integrations/statusline/claude-usage.sh
```

[Claude Code status line](https://code.claude.com/docs/en/statusline)
