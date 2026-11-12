"""PreToolUse guard for Git: deny unrequested commit, push, or PR creation, and
deny commits that would add secrets.

Approval comes only from the latest user message of the current turn. In Claude
Code that message is read from the transcript; in Codex it is the prompt saved by
record_prompt.py for the same turn_id. The guard reads command text and repository
state only; it cannot see inside scripts or variables.
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from approval import ACTIONS, approved_actions  # noqa: E402
from hook_common import emit_decision, last_user_message, read_event, shell_tool_command  # noqa: E402
from secret_patterns import find_secret_kinds  # noqa: E402
from shell_commands import (  # noqa: E402
    git_operation,
    http_pr_write,
    leading_cd,
    pr_tool_operation,
    push_opens_pr,
    segments,
    tokens,
)

GIT_TIMEOUT_SECONDS = 10
MAX_UNTRACKED_FILES = 200
MAX_UNTRACKED_BYTES = 1024 * 1024
LABELS = {"commit": "commit", "push": "push", "pr": "PR/MR creation"}
EXAMPLES = {"commit": "'커밋해 줘' / 'commit it'", "push": "'푸시해 줘' / 'push it'", "pr": "'PR 만들어 줘' / 'open a PR'"}


def _dry_run(args):
    return "--dry-run" in args or "-n" in args


def detect(command):
    """Return (actions, repo_hint, has_git_add) found in the command text."""
    actions, repo_hint, has_add = set(), None, False
    parts = segments(command)
    for part in parts:
        words = tokens(part)
        operation = git_operation(words)
        if operation:
            subcommand, args, repo = operation
            if repo and repo_hint is None:
                repo_hint = repo
            if subcommand == "commit" and not _dry_run(args):
                actions.add("commit")
            elif subcommand == "push" and not _dry_run(args):
                actions.add("push")
                if push_opens_pr(args):
                    actions.add("pr")
            elif subcommand == "add":
                has_add = True
            continue
        if pr_tool_operation(words) or http_pr_write(words):
            actions.add("pr")
    return actions, repo_hint, has_add, leading_cd(parts)


def resolve_repo(repo_hint, cd_path, cwd):
    base = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    for candidate in (repo_hint, cd_path):
        if candidate:
            path = Path(os.path.expanduser(candidate))
            return path if path.is_absolute() else base / path
    return base


def _git(repo, *args):
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def _added_lines(diff_text):
    lines = []
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
    return "\n".join(lines)


def commit_secret_kinds(repo, include_untracked):
    """Kinds of secrets the commit would add. Empty when none or when repo is not git."""
    if _git(repo, "rev-parse", "--is-inside-work-tree") is None:
        return []
    text = []
    for scope in (("diff", "--cached"), ("diff",)):
        diff = _git(repo, *scope, "-U0", "--no-color", "--no-ext-diff")
        if diff:
            text.append(_added_lines(diff))
    if include_untracked:
        listing = _git(repo, "ls-files", "--others", "--exclude-standard", "-z")
        if listing:
            names = [name for name in listing.split("\0") if name][:MAX_UNTRACKED_FILES]
            for name in names:
                path = repo / name
                try:
                    if path.is_file() and path.stat().st_size <= MAX_UNTRACKED_BYTES:
                        text.append(path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
    return find_secret_kinds("\n".join(text))


def main():
    event = read_event()
    command = shell_tool_command(event)
    if command is None:
        return 0
    actions, repo_hint, has_add, cd_path = detect(command)
    if not actions:
        return 0

    message = last_user_message(event)
    approved = approved_actions(message) if message else set()
    missing = [action for action in ACTIONS if action in actions and action not in approved]
    if missing:
        names = ", ".join(LABELS[action] for action in missing)
        examples = "; ".join(EXAMPLES[action] for action in missing)
        source = (
            "the latest user message does not request it"
            if message
            else "the latest user message could not be read, so no request is on record"
        )
        emit_decision(
            event,
            "deny",
            f"engineering-workflow guard: {names} blocked because {source}. "
            f"Do not work around this. The user must ask for it explicitly in their next message ({examples}).",
        )
        return 0

    if "commit" in actions:
        repo = resolve_repo(repo_hint, cd_path, event.get("cwd"))
        kinds = commit_secret_kinds(repo, has_add)
        if kinds:
            emit_decision(
                event,
                "deny",
                "engineering-workflow guard: the commit would add a secret ("
                + ", ".join(kinds)
                + "). Remove it, move it to an ignored file, or replace it with a reference. "
                "The value was not printed.",
            )
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
