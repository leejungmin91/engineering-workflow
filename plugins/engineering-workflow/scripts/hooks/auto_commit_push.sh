#!/bin/sh
# Stop hook: commit and push whatever the turn left in the working tree.
#
# Runs when the assistant finishes a turn. Stages every change (.gitignore
# still applies), commits with a generated subject and a file list, and pushes
# to the tracked upstream. When the branch has no upstream and a remote named
# origin exists, it pushes with -u to origin/<branch>. It never blocks the turn:
# the exit code is always 0 and failures are reported as a systemMessage.
#
# Usage: sh auto_commit_push.sh [--dry-run]
#   --dry-run  print what would be committed and change nothing
#
# Environment: CLAUDE_PROJECT_DIR (set by Claude Code) selects the repository;
# otherwise the current directory is used. AUTO_COMMIT_TRAILER replaces the
# default Co-Authored-By trailer.

dry_run=0
[ "$1" = "--dry-run" ] && dry_run=1

# Drain the hook input so the host never blocks on a full pipe.
cat >/dev/null 2>&1

cd "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

say() {
  # Print a systemMessage JSON object; backslashes and quotes are escaped.
  msg=$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ')
  printf '{"systemMessage":"auto_commit_push: %s"}\n' "$msg"
}

git add -A >/dev/null 2>&1
if git diff --cached --quiet; then
  exit 0
fi

count=$(git diff --cached --name-only | wc -l | tr -d ' ')
all_tops=$(git diff --cached --name-only | sed 's#/.*##' | sort -u)
# Visible paths first, dotfiles and dot-directories last.
tops=$( { printf '%s\n' "$all_tops" | grep -v '^\.'; printf '%s\n' "$all_tops" | grep '^\.'; } | sed '/^$/d')
top_count=$(printf '%s\n' "$tops" | wc -l | tr -d ' ')
head3=$(printf '%s\n' "$tops" | head -3 | paste -sd ',' - | sed 's/,/, /g')
if [ "$top_count" -gt 3 ]; then
  subject="Update $head3 (+$((top_count - 3)) more)"
else
  subject="Update $head3"
fi
body=$(git diff --cached --name-status)
stamp=$(date '+%Y-%m-%d %H:%M %Z')
trailer="${AUTO_COMMIT_TRAILER:-Co-Authored-By: Claude <noreply@anthropic.com>}"

if [ "$dry_run" -eq 1 ]; then
  printf 'DRY RUN - would commit %s file(s):\n%s\n\nSubject: %s\n' "$count" "$body" "$subject"
  git reset -q >/dev/null 2>&1
  exit 0
fi

errfile=$(mktemp 2>/dev/null || printf '%s' "${TMPDIR:-/tmp}/auto_commit_push.$$")
trap 'rm -f "$errfile"' EXIT

if ! git -c core.safecrlf=false commit -q -F - <<MSG 2>"$errfile"
$subject

Auto-committed by the engineering-workflow Stop hook at $stamp.

$body

$trailer
MSG
then
  say "commit failed: $(cut -c1-300 "$errfile")"
  exit 0
fi

sha=$(git rev-parse --short HEAD)
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if git rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; then
  push_args=""
elif git remote get-url origin >/dev/null 2>&1 && [ "$branch" != "HEAD" ]; then
  push_args="-u origin $branch"
else
  say "committed $sha ($count file(s)) but there is no upstream or origin to push to."
  exit 0
fi

# shellcheck disable=SC2086
if git push -q $push_args 2>"$errfile"; then
  say "committed $sha ($count file(s)) and pushed."
else
  say "committed $sha but push failed: $(cut -c1-300 "$errfile")"
fi
exit 0
