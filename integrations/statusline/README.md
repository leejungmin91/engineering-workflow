# Claude Code usage status line

`claude-usage.sh` draws separate rows for conversation context, account limits, and model-specific weekly limits:

```
Fable 5 │ Context ███░░░░░░░ 32% used · 68% left · 320k/1.0M
All · 5h    ██████░░░░ 63% used · 37% left · reset 18:53
All · 7d    ████░░░░░░ 44% used · 56% left · reset 11/16 13:00
Fable · 7d  ████████░░ 75% used · 25% left · reset 11/16 13:00 · cached 3m
```

- `Context` is the conversation context window: used and remaining percentages, occupied tokens, and capacity. When the host omits the percentage, the script computes it from `current_usage`.
- `All · 5h` and `All · 7d` are account usage windows, independent of the current model. Host `rate_limits` values take precedence over cached account values. Missing windows are omitted.
- `Fable · 7d` (or another model name) is that model's own weekly allowance. It has a different denominator from the account limit; the two percentages must not be substituted for each other.
- Claude Code currently passes only account windows to status line scripts. Model rows come from `cachedUsageUtilization.utilization.limits` in `~/.claude.json` (or `$CLAUDE_CONFIG_DIR/.claude.json`). The script checks the cache's account ID against the signed-in account, reads only local metadata, and makes no network or credential requests. This cache schema is internal to Claude Code and can change.
- `cached 3m` means the snapshot was fetched three minutes ago. It is not a live measurement; run `/usage` in Claude Code to refresh its cache. Expired model windows show `— unavailable`. Fable sessions also show an unavailable row when no model snapshot exists, rather than substituting the account percentage.
- Reset times use the local timezone. Each limit gets its own row to avoid a single long footer being clipped in narrow terminals.
- Bars avoid a red/green scale so they stay readable in daltonized themes: cyan below 50%, yellow below 80%, magenta from 80%.
- Missing token counts show as `?`; missing percentages show `— unavailable`. The script needs POSIX `sh` and `jq`.

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
