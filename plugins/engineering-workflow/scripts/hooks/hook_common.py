"""Shared helpers for engineering-workflow hooks.

Works for Claude Code and Codex. Both hosts accept a JSON decision on stdout with
exit code 0; Codex ignores exit code 2 and the "ask" decision, so every hook denies
through JSON and downgrades "ask" to "deny" when it runs under Codex.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

PROMPT_RETENTION_SECONDS = 7 * 24 * 60 * 60
SESSION_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def _force_utf8_stdout():
    """Hosts read hook stdout as UTF-8; on Windows Python would default to the locale code page."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def read_event():
    """Return the hook input as a dict, or an empty dict when it is unreadable.

    stdin is decoded as UTF-8 explicitly: hosts send UTF-8, while Python on Windows
    would otherwise decode with the locale code page and corrupt Korean text.
    """
    _force_utf8_stdout()
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except (OSError, AttributeError, UnicodeError):
        return {}
    if not raw.strip():
        return {}
    try:
        event = json.loads(raw)
    except ValueError:
        return {}
    return event if isinstance(event, dict) else {}


def is_codex(event):
    """Codex adds turn_id to every hook input; Claude Code does not."""
    return "turn_id" in event


def emit_decision(event, decision, reason):
    """Print a PreToolUse decision. Codex cannot ask, so ask becomes deny there."""
    if decision == "ask" and is_codex(event):
        decision = "deny"
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def emit_context(text):
    """Add context to the prompt from a UserPromptSubmit hook."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": text,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def state_dir():
    """Per-user state directory. ENGINEERING_WORKFLOW_HOME overrides it (tests)."""
    override = os.environ.get("ENGINEERING_WORKFLOW_HOME")
    base = Path(override) if override else Path.home() / ".engineering-workflow"
    return base


def prompts_dir():
    return state_dir() / "prompts"


def _session_file(event):
    session = event.get("session_id")
    if not isinstance(session, str) or not SESSION_FILE.fullmatch(session):
        return None
    return prompts_dir() / f"{session}.json"


def save_prompt(event):
    """Store the Codex prompt for this turn so PreToolUse hooks can read it."""
    path = _session_file(event)
    prompt = event.get("prompt")
    turn = event.get("turn_id")
    if path is None or not isinstance(prompt, str) or not isinstance(turn, str):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"turn_id": turn, "prompt": prompt, "saved_at": time.time()}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    prune_prompts()
    return True


def prune_prompts(now=None):
    """Delete recorded prompts older than the retention window."""
    folder = prompts_dir()
    if not folder.is_dir():
        return
    now = time.time() if now is None else now
    for file in folder.glob("*.json"):
        try:
            if now - file.stat().st_mtime > PROMPT_RETENTION_SECONDS:
                file.unlink()
        except OSError:
            continue


def recorded_prompt(event):
    """Return the Codex prompt recorded for the same turn, else None."""
    path = _session_file(event)
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("turn_id") != event.get("turn_id"):
        return None
    prompt = data.get("prompt")
    return prompt if isinstance(prompt, str) else None


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def transcript_last_user_message(path):
    """Return the last human-written message from a Claude Code transcript (jsonl)."""
    if not isinstance(path, str) or not path:
        return None
    file = Path(path)
    if not file.is_file():
        return None
    last = None
    try:
        with file.open(encoding="utf-8", errors="replace") as source:
            for line in source:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or entry.get("type") != "user":
                    continue
                if entry.get("isMeta"):
                    continue
                message = entry.get("message")
                if not isinstance(message, dict):
                    continue
                text = _text_of(message.get("content")).strip()
                if text:
                    last = text
    except OSError:
        return None
    return last


def last_user_message(event):
    """Latest user message for this turn. None when it cannot be determined."""
    if is_codex(event):
        return recorded_prompt(event)
    return transcript_last_user_message(event.get("transcript_path"))


def shell_tool_command(event):
    """Return the shell command string for Bash/PowerShell tool calls, else None."""
    if event.get("hook_event_name") not in (None, "PreToolUse"):
        return None
    if event.get("tool_name") not in ("Bash", "PowerShell"):
        return None
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    return command if isinstance(command, str) else None
