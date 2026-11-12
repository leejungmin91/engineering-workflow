"""UserPromptSubmit hook: store the actions approved in the Codex prompt.

Claude Code hooks can read the transcript, so nothing is stored there. Codex
transcripts differ, so PreToolUse guards read the approvals saved here instead.
This hook never blocks and never prints.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hook_common import is_codex, read_event, save_prompt_approvals  # noqa: E402


def main():
    event = read_event()
    if event.get("hook_event_name") != "UserPromptSubmit":
        return 0
    if not is_codex(event):
        return 0
    try:
        save_prompt_approvals(event)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
