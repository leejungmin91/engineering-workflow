"""Opt-in PreToolUse hook for direct, destructive Git commands."""

import json
import shlex
import sys


COMMAND_BOUNDARY = "();<>|&\n"
OPTIONS_WITH_VALUES = {
    "clean": {"-e", "--exclude"},
    "push": {"-o", "--push-option", "--receive-pack", "--exec", "--repo"},
}


def first_command(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=COMMAND_BOUNDARY)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    words = []
    for word in lexer:
        if word.startswith("#") or (word and all(char in COMMAND_BOUNDARY for char in word)):
            break
        words.append(word)
    return words


def flags_for(args, options_with_values):
    flags = set()
    tokens = iter(args)
    for arg in tokens:
        if arg == "--":
            break
        if arg.startswith("--"):
            name, separator, _ = arg.partition("=")
            flags.add(name)
            if name in options_with_values and not separator:
                next(tokens, None)
        elif arg.startswith("-"):
            for index, letter in enumerate(arg[1:], start=1):
                flag = "-" + letter
                flags.add(flag)
                if flag in options_with_values:
                    if index == len(arg) - 1:
                        next(tokens, None)
                    break
    return flags


def block_reason(event):
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return None
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return None
    try:
        words = first_command(command)
    except ValueError:
        return None
    if not words or words[0] != "git":
        return None

    operation_index = 1
    while words[operation_index:operation_index + 1] == ["-C"]:
        operation_index += 2
    if operation_index >= len(words):
        return None
    operation = words[operation_index]
    args = words[operation_index + 1:]
    flags = flags_for(args, OPTIONS_WITH_VALUES.get(operation, set()))
    if operation == "reset" and "--hard" in flags:
        return "git reset --hard"
    if "--dry-run" in flags or "-n" in flags:
        return None
    forced = "--force" in flags or "-f" in flags
    if operation == "clean" and forced and {"-d", "-x"} <= flags:
        return "git clean -fdx"
    if operation == "push" and forced:
        return "git push --force"
    return None

def main():
    try:
        event = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        return 0
    reason = block_reason(event)
    if reason:
        print(f"PreToolUse blocked {reason}. Check the repository state and choose a safer Git operation.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
