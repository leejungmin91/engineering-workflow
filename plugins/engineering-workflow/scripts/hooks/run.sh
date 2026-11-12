#!/bin/sh
# Run a hook script with the first Python 3.9+ interpreter that actually works.
# On Windows, "python3" may be a Microsoft Store stub, so each candidate is tested.
# Usage: run.sh <script-name-without-.py>
dir=$(dirname "$0")
name="$1"
for candidate in "python3" "python" "py -3"; do
  if $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
    exec $candidate "$dir/$name.py"
  fi
done
case "$name" in
  guard_*)
    # Fail closed: a guard that cannot run must not let the call through silently.
    printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"engineering-workflow hooks need Python 3.9 or newer on PATH (python3, python, or py). Install Python and retry."}}'
    ;;
esac
exit 0
