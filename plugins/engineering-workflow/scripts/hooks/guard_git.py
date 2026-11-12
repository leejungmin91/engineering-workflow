"""PreToolUse guard for Git: deny unrequested commit, push, or PR creation, and
deny commits that would add secrets.

Approval comes only from the latest user message of the current turn. In Claude
Code that message is read from the transcript; in Codex the approved actions
are saved by record_prompt.py for the same turn_id. The guard reads command text and repository
state only; it cannot see inside scripts or variables.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from approval import ACTIONS  # noqa: E402
from hook_common import action_approvals, emit_decision, read_event, shell_tool_command  # noqa: E402
from secret_patterns import find_secret_kinds  # noqa: E402
from shell_commands import (  # noqa: E402
    directory_change,
    git_operation,
    http_pr_write,
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


def _dry_run(subcommand, args):
    positive = {"--dry-run", "-n"} if subcommand == "push" else {"--dry-run"}
    dry_run = False
    takes_value = {"-m", "-F", "-C", "-c", "-t", "-o", "--message", "--file", "--reuse-message",
                   "--reedit-message", "--template", "--author", "--date", "--push-option"}
    options = iter(args)
    for arg in options:
        if arg == "--":
            break
        if arg in takes_value:
            next(options, None)
        elif arg == "--no-dry-run" or arg in positive:
            dry_run = arg in positive
    return dry_run


def detect(command, cwd):
    """Return the requested actions and the repositories each commit would write."""
    actions, additions, commits = set(), set(), {}
    base = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    outer_directories = []
    for part in segments(command):
        if part == "(":
            outer_directories.append(base)
            continue
        if part == ")" and outer_directories:
            base = outer_directories.pop()
            continue
        words = tokens(part)
        directory = directory_change(words)
        if directory:
            base = base / Path(directory).expanduser()
            continue
        operation = git_operation(words)
        if operation:
            subcommand, args, repo = operation
            repo = (base / Path(repo).expanduser()).resolve() if repo else base.resolve()
            if subcommand == "commit" and not _dry_run(subcommand, args):
                actions.add("commit")
                commits[repo] = repo in additions
            elif subcommand == "push" and not _dry_run(subcommand, args):
                actions.add("push")
                if push_opens_pr(args):
                    actions.add("pr")
            elif subcommand == "add":
                additions.add(repo)
            continue
        if pr_tool_operation(words) or http_pr_write(words):
            actions.add("pr")
    return actions, commits


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
    tool_cwd = event["tool_input"].get("workdir") or event.get("cwd")
    actions, commits = detect(command, tool_cwd)
    if not actions:
        return 0

    approved = action_approvals(event)
    missing = [action for action in ACTIONS if action in actions and action not in (approved or ())]
    if missing:
        names = ", ".join(LABELS[action] for action in missing)
        examples = "; ".join(EXAMPLES[action] for action in missing)
        source = (
            "the latest user message does not request it"
            if approved is not None
            else "the latest user message could not be read, so no request is on record"
        )
        emit_decision(
            event,
            "deny",
            f"engineering-workflow guard: {names} blocked because {source}. "
            f"Do not work around this. The user must ask for it explicitly in their next message ({examples}).",
        )
        return 0

    for repo, include_untracked in commits.items():
        kinds = commit_secret_kinds(repo, include_untracked)
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
