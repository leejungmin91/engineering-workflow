#!/bin/sh
# Claude Code status line: context, account limits, and cached model limits.
# Reads host JSON from stdin and usage metadata from Claude's local config.
# Colors avoid red/green (daltonized themes): cyan < 50% <= yellow < 80% <= magenta.

input=$(cat)

j() { printf '%s' "$input" | jq -r "$1" 2>/dev/null; }

bar() { # $1 = percent (integer or empty), $2 = width
  pct=$1; w=$2
  if [ -z "$pct" ]; then printf '%s' "$(printf '%*s' "$w" '' | tr ' ' '-')"; return; fi
  [ "$pct" -lt 0 ] && pct=0
  [ "$pct" -gt 100 ] && pct=100
  fill=$(( (pct * w + 50) / 100 )); [ "$fill" -gt "$w" ] && fill=$w
  if [ "$pct" -ge 80 ]; then c='35'; elif [ "$pct" -ge 50 ]; then c='33'; else c='36'; fi
  on=$(printf '%*s' "$fill" '' | sed 's/ /█/g')
  off=$(printf '%*s' $((w - fill)) '' | sed 's/ /░/g')
  printf '\033[%sm%s\033[2m%s\033[0m' "$c" "$on" "$off"
}

int() { [ -n "$1" ] && [ "$1" != "null" ] && printf '%.0f' "$1" 2>/dev/null; }

meter() {
  if [ -z "$1" ] || [ "$1" = '?' ]; then
    printf '%s — unavailable' "$(bar '' 10)"
  else
    remaining=$((100 - $1)); [ "$remaining" -lt 0 ] && remaining=0
    printf '%s \033[1m%s%% used\033[0m · %s%% left' "$(bar "$1" 10)" "$1" "$remaining"
  fi
}

k() { # tokens -> 12k / 1.2M
  [ -z "$1" ] && { printf '?'; return; }
  if [ "$1" -ge 1000000 ]; then awk -v n="$1" 'BEGIN{printf "%.1fM", n/1000000}'
  else printf '%dk' $(( ($1 + 500) / 1000 )); fi
}

model=$(j '.model.display_name // "?"')

ctx_pct=$(int "$(j '.context_window.used_percentage // empty')")
ctx_size=$(int "$(j '.context_window.context_window_size // empty')")
ctx_used=$(int "$(j '(.context_window.current_usage // empty)
  | (.input_tokens // 0) + (.cache_creation_input_tokens // 0) + (.cache_read_input_tokens // 0)')")
if [ -z "$ctx_pct" ] && [ -n "$ctx_used" ] && [ -n "$ctx_size" ] && [ "$ctx_size" -gt 0 ]; then
  ctx_pct=$(( ctx_used * 100 / ctx_size ))
fi

printf '\033[1m%s\033[0m' "$model"
printf ' │ Context %s · %s/%s' "$(meter "$ctx_pct")" "$(k "$ctx_used")" "$(k "$ctx_size")"

# The host omits model-scoped limits. Claude Code caches /usage locally;
# read only its usage snapshot, verify the account, and label its age.
config_file="${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json"
[ -z "$CLAUDE_CONFIG_DIR" ] && config_file="$HOME/.claude.json"
cache=$(jq -c '. as $config | .cachedUsageUtilization
  | select(.accountUuid != null and .accountUuid == $config.oauthAccount.accountUuid)
  | {fetchedAtMs, utilization}' "$config_file" 2>/dev/null)

jq -nr --argjson live "${input:-\{\}}" --argjson cache "${cache:-null}" --argjson now "$(date +%s)" '
  def epoch:
    if type == "number" then floor
    elif type == "string" then
      try (sub("\\.[0-9]+"; "") | sub("\\+00:00$"; "Z") | fromdateiso8601) catch 0
    else 0 end;
  def row($label; $p; $reset; $source):
    [$label, (if ($p | type) == "number" then ($p | round | tostring) else "?" end),
     ($reset | tostring), $source] | @tsv;
  ($cache.utilization | if type == "object" then . else {} end) as $usage |
  (if ($cache.fetchedAtMs | type) == "number" then
    "cached \((([0, ($now - $cache.fetchedAtMs / 1000)] | max) / 60) | floor)m"
   else "cached · age unknown" end) as $age |
  ([ ["five_hour", "All · 5h"], ["seven_day", "All · 7d"] ][] |
    .[0] as $key | .[1] as $label |
    $live.rate_limits[$key] as $host |
    ($usage[$key] | if type == "object" then . else {} end) as $saved |
    if ($host.used_percentage | type) == "number" then
      row($label; $host.used_percentage; ($host.resets_at | epoch); "live")
    elif ($saved.utilization | type) == "number" and ($saved.resets_at | epoch) > $now then
      row($label; $saved.utilization; ($saved.resets_at | epoch); $age)
    else empty end),
  ((try [$usage.limits[]? | select(.kind == "weekly_scoped" and
     (.scope.model.display_name | type) == "string")] catch []) as $scoped |
    if ($scoped | length) > 0 then
      $scoped[] | (.resets_at | epoch) as $reset |
      row("\(.scope.model.display_name) · 7d"; (if $reset > $now then .percent else null end); $reset; $age)
    elif (($live.model.display_name // "") | test("fable"; "i")) then
      row("Fable · 7d"; null; 0; "live")
    else empty end)
' 2>/dev/null | while IFS="$(printf '\t')" read -r label p reset source; do
  printf '\n\033[1m%-12s\033[0m %s' "$label" "$(meter "$p")"
  if [ "$reset" -gt 0 ] && [ "$p" != '?' ]; then
    fmt='%m/%d %H:%M'; [ "$label" = 'All · 5h' ] && fmt='%H:%M'
    when=$(date -r "$reset" "+$fmt" 2>/dev/null || date -d "@$reset" "+$fmt" 2>/dev/null)
    [ -n "$when" ] && printf ' · reset %s' "$when"
  fi
  [ "$source" != live ] && printf ' · %s' "$source"
done
printf '\n'
