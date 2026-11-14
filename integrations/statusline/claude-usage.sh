#!/bin/sh
# Claude Code status line: model, context window bar, and 5h / 7d usage bars.
# Reads the status line JSON from stdin. Missing fields show as "?".
# Colors avoid red/green (daltonized themes): cyan < 50% <= yellow < 80% <= magenta.

input=$(cat)

j() { printf '%s' "$input" | jq -r "$1" 2>/dev/null; }

bar() { # $1 = percent (integer or empty), $2 = width
  pct=$1; w=$2
  if [ -z "$pct" ]; then printf '%s' "$(printf '%*s' "$w" '' | tr ' ' '-')"; return; fi
  fill=$(( (pct * w + 50) / 100 )); [ "$fill" -gt "$w" ] && fill=$w
  if [ "$pct" -ge 80 ]; then c='35'; elif [ "$pct" -ge 50 ]; then c='33'; else c='36'; fi
  on=$(printf '%*s' "$fill" '' | sed 's/ /█/g')
  off=$(printf '%*s' $((w - fill)) '' | sed 's/ /░/g')
  printf '\033[%sm%s\033[2m%s\033[0m' "$c" "$on" "$off"
}

int() { [ -n "$1" ] && [ "$1" != "null" ] && printf '%.0f' "$1" 2>/dev/null; }

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

limit() { # $1 = five_hour | seven_day -> "bar pct% ↻reset"
  p=$(int "$(j ".rate_limits.$1.used_percentage // empty")")
  r=$(j ".rate_limits.$1.resets_at // empty")
  when=""
  if [ -n "$r" ]; then
    fmt='%H:%M'; [ "$1" = seven_day ] && fmt='%m/%d %H:%M'
    t=$(int "$r")
    # BSD date takes -r <epoch>; GNU date takes -d @<epoch>.
    when=" ↻$(date -r "$t" "+$fmt" 2>/dev/null || date -d "@$t" "+$fmt" 2>/dev/null)"
  fi
  printf '%s %s%s' "$(bar "$p" 8)" "${p:-?}%" "$when"
}

sep=' \033[2m│\033[0m '
printf '\033[1m%s\033[0m' "$model"
printf "$sep"'ctx %s %s%% (%s/%s)' "$(bar "$ctx_pct" 10)" "${ctx_pct:-?}" "$(k "$ctx_used")" "$(k "$ctx_size")"
if [ "$(j 'has("rate_limits")')" = "true" ]; then
  printf "$sep"'5h %s' "$(limit five_hour)"
  printf "$sep"'7d %s' "$(limit seven_day)"
fi
printf '\n'
