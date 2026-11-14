#!/bin/sh
# Stop hook: commit remaining changes and push unpublished commits.
#
# Runs when the assistant finishes a turn. Stages every change (.gitignore
# still applies), commits with a generated subject and a file list, and pushes
# using Git's push configuration. When the branch has no upstream and a remote named
# origin exists, it pushes with -u to origin/<branch>. It never blocks the turn:
# the exit code is always 0 and failures are reported as a systemMessage.
#
# Usage: sh auto_commit_push.sh [--dry-run]
#   --dry-run  print what would be committed without updating the live index
#
# Environment: CLAUDE_PROJECT_DIR (set by Claude Code) selects the repository;
# otherwise the current directory is used. AUTO_COMMIT_TRAILER replaces the
# default Co-Authored-By trailer.

dry_run=0
[ "$1" = "--dry-run" ] && dry_run=1

# Drain the hook input so the host never blocks on a full pipe.
cat >/dev/null 2>&1

cd "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null || exit 0
[ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" = true ] || exit 0

say() {
  # Print a systemMessage JSON object; backslashes and quotes are escaped.
  msg=$(printf '%s' "$1" | tr '[:cntrl:]' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')
  printf '{"systemMessage":"auto_commit_push: %s"}\n' "$msg"
}

tempdir=$(mktemp -d) || { say "could not create a temporary directory."; exit 0; }
trap 'rm -rf "$tempdir"' EXIT
errfile="$tempdir/git-error"

if [ "$dry_run" -eq 1 ]; then
  index=$(git rev-parse --git-path index) || exit 0
  if [ -f "$index" ]; then
    cp "$index" "$tempdir/index" || exit 0
  fi
  export GIT_INDEX_FILE="$tempdir/index"
fi

if ! git add -A >"$errfile" 2>&1; then
  say "staging failed: $(cut -c1-300 "$errfile")"
  exit 0
fi

commit_summary=""
if ! git diff --cached --quiet; then
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
    exit 0
  fi

  if ! git -c core.safecrlf=false commit -q -F - <<MSG >"$errfile" 2>&1
$subject

Auto-committed by the engineering-workflow Stop hook at $stamp.

$body

$trailer
MSG
  then
    say "commit failed: $(cut -c1-300 "$errfile")"
    exit 0
  fi

  commit_summary="committed $count file(s) and "
fi

[ "$dry_run" -eq 1 ] && exit 0
sha=$(git rev-parse --short HEAD 2>/dev/null) || exit 0
branch_ref=$(git symbolic-ref --quiet HEAD)
upstream=
[ -n "$branch_ref" ] && upstream=$(git for-each-ref --format='%(upstream)' "$branch_ref")

if [ -n "$upstream" ]; then
  push_ref=$(git for-each-ref --format='%(push)' "$branch_ref")
  if [ -z "$commit_summary" ] &&
    [ -n "$push_ref" ] &&
    ahead=$(git rev-list -1 "$push_ref..HEAD" 2>/dev/null) &&
    [ -z "$ahead" ]; then
    exit 0
  fi
  set --
elif [ -n "$branch_ref" ] && git remote get-url origin >/dev/null 2>&1; then
  set -- -u origin "$branch_ref"
else
  if [ -n "$commit_summary" ]; then
    say "committed $sha locally. The checkout needs a branch and an upstream or origin to push."
  fi
  exit 0
fi

if git push --porcelain "$@" >"$errfile" 2>&1; then
  if [ -n "$commit_summary" ] || [ "$(awk -F '\t' '$1 ~ /^[ *+!-]$/ {print $1; exit}' "$errfile")" ]; then
    say "${commit_summary}pushed $sha."
  fi
else
  say "commit $sha is local. push failed: $(cut -c1-300 "$errfile")"
fi
exit 0
