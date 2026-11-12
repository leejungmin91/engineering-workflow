"""Split a shell command into segments and read Git / HTTP operations from them.

The parser only looks at command text. It cannot see inside scripts or variables.
"""

import re
from pathlib import Path

BOUNDARY_TOKENS = ("&&", "||", "|", ";", "&", "\n", "(", ")")
GIT_NAME = re.compile(r"(?i)^(?:.*[\\/])?git(?:\.exe)?$")
SKIP_LEADERS = {"sudo", "command", "exec", "time", "nohup", "env", "builtin", "&", "doas"}
GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
GIT_GLOBAL_FLAGS = {
    "-p", "--paginate", "-P", "--no-pager", "--no-replace-objects", "--bare",
    "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs",
    "--no-optional-locks", "--no-lazy-fetch", "--no-advice",
}
HTTP_CLIENTS = {"curl", "wget", "http", "https", "xh", "invoke-restmethod", "irm", "invoke-webrequest", "iwr"}
PR_API_PATH = re.compile(r"/(?:pulls|merge_requests|pullrequests)(?:[/?#]|$)", re.IGNORECASE)
WRITE_METHOD = re.compile(r"(?i)^(?:post|put|patch)$")
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def segments(command):
    """Split on shell boundaries outside quotes, retaining subshell delimiters."""
    parts, current, quote, i = [], [], None, 0
    while i < len(command):
        ch = command[i]
        if quote:
            current.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(command):
                current.append(command[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < len(command):
            current.append(ch)
            current.append(command[i + 1])
            i += 2
            continue
        if ch == "#":
            end = command.find("\n", i)
            i = len(command) if end < 0 else end
            continue
        matched = None
        for token in BOUNDARY_TOKENS:
            if command.startswith(token, i):
                matched = token
                break
        if matched:
            parts.append("".join(current))
            if matched in ("(", ")"):
                parts.append(matched)
            current = []
            i += len(matched)
            continue
        current.append(ch)
        i += 1
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def tokens(segment):
    """Whitespace split that honours quotes and keeps backslashes (Windows paths)."""
    result, current, quote, i = [], [], None, 0
    while i < len(segment):
        ch = segment[i]
        if quote:
            if ch == quote:
                quote = None
            else:
                current.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        if ch.isspace():
            if current:
                result.append("".join(current))
                current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    if current:
        result.append("".join(current))
    return result


def _strip_leaders(words):
    index = 0
    while index < len(words):
        word = words[index]
        if word in SKIP_LEADERS or ENV_ASSIGNMENT.match(word):
            index += 1
            continue
        break
    return words[index:]


def _program_name(word):
    name = word.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return re.sub(r"(?i)\.exe$", "", name).lower()


def git_operation(words):
    """Return (subcommand, args, repo_path) when words run git, else None."""
    words = _strip_leaders(words)
    if not words or not GIT_NAME.match(words[0]):
        return None
    repo = Path()
    index = 1
    while index < len(words):
        word = words[index]
        if word in GIT_GLOBAL_WITH_VALUE:
            if word == "-C" and index + 1 < len(words):
                repo /= words[index + 1]
            index += 2
            continue
        if word.startswith("-C") and len(word) > 2:
            repo /= word[2:]
            index += 1
            continue
        if word.startswith("-c") and len(word) > 2 and "=" in word:
            index += 1
            continue
        if "=" in word and word.split("=", 1)[0] in GIT_GLOBAL_WITH_VALUE:
            index += 1
            continue
        if word in GIT_GLOBAL_FLAGS:
            index += 1
            continue
        if word.startswith("-"):
            index += 1
            continue
        return word, words[index + 1:], repo
    return None


def push_opens_pr(args):
    """True when push options ask the host to open a merge request."""
    for index, arg in enumerate(args):
        value = None
        if arg in ("-o", "--push-option") and index + 1 < len(args):
            value = args[index + 1]
        elif arg.startswith("--push-option="):
            value = arg.split("=", 1)[1]
        elif arg.startswith("-o") and len(arg) > 2:
            value = arg[2:]
        if value and re.search(r"(?i)merge_request\.create|pr\.create", value):
            return True
    return False


def pr_tool_operation(words):
    """True when words create a pull/merge request with gh, glab or hub."""
    words = _strip_leaders(words)
    if len(words) < 2:
        return False
    name = _program_name(words[0])
    rest = [word for word in words[1:] if not word.startswith("-")]
    if name == "gh" and len(rest) >= 2 and rest[0] == "pr" and rest[1] in ("create", "new"):
        return True
    if name == "glab" and len(rest) >= 2 and rest[0] == "mr" and rest[1] in ("create", "new"):
        return True
    if name == "hub" and rest and rest[0] == "pull-request":
        return True
    return False


def http_pr_write(words):
    """True when an HTTP client at the start of the segment writes to a PR/MR API path."""
    words = _strip_leaders(words)
    if not words:
        return False
    if _program_name(words[0]) not in HTTP_CLIENTS:
        return False
    if not any(PR_API_PATH.search(word) for word in words[1:]):
        return False
    method, has_body, forced_get = None, False, False
    for index, word in enumerate(words[1:], start=1):
        lowered = word.lower()
        if lowered in ("-x", "--request", "-method", "--method") and index + 1 < len(words):
            method = words[index + 1]
        elif lowered.startswith("--request="):
            method = word.split("=", 1)[1]
        elif lowered.startswith("-x") and len(word) > 2 and not lowered.startswith("-xh"):
            method = word[2:]
        elif lowered in ("-d", "--data", "--data-raw", "--data-binary", "--data-urlencode", "--json",
                         "-f", "--form", "-body", "--body", "--post-data", "--post-file", "-infile"):
            has_body = True
        elif lowered.startswith("--data") or lowered.startswith("--json=") or lowered.startswith("--post-"):
            has_body = True
        elif lowered in ("-g", "--get"):
            forced_get = True
    if method is not None:
        return bool(WRITE_METHOD.match(method))
    return has_body and not forced_get


def directory_change(words):
    """Path from a `cd <path>` segment, if any."""
    words = _strip_leaders(words)
    if len(words) >= 2 and words[0].lower() in ("cd", "set-location", "pushd", "sl"):
        return words[-1]
    return None
