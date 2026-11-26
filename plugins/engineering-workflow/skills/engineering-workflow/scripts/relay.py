import argparse
import json
import os
try:
    import pwd
except ImportError:
    pwd = None
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import talk_save

OPENING = re.compile(r"<pasted_content\b([^>]*)>")
REMINDERS = re.compile(r"<system-reminder>.*</system-reminder>", re.S)
TYPED = ("typed", "queued")
MIN_QUOTE = 6
ASKED_CHARS = 1500
FIND_DAYS = 3
FIND_LIMIT = 3
TYPING = re.compile(r"\btmux\b.*?\b(send-keys|send|paste-buffer|pasteb)\b|\bherdr\b.*?\bsend-(text|keys)\b"
                    r"|\bosascript\b.*?\b(keystroke|key code)\b|\bscreen\b.*?\bstuff\b", re.S)
PANE_TOOLS = re.compile(r"\b(tmux|herdr|osascript|screen)\b")
WRITES = re.compile(r"(<>|>&\s*[^\d\s-]|(?<![<>=!])\d*>{1,2}\|?(?![=>&])(?!\s*/dev/null\b)|write_text|write_bytes|\.write\(|"
                    r"\bos\.(replace|rename|remove|unlink|truncate)|\bshutil\.|\bunlink\b|\btee\b|\bsed\s+-i|\bperl\s+-[a-z]*i|\bmv\b|\bcp\b|\brm\b|\btruncate\b|\bdd\b|\bln\b|"
                    r"\binstall\b|\brsync\b|open\([^)]*['\"][rwax]?\+?[wax+])")


def user_home():
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, AttributeError, OSError):
        return Path.home()


def homes(existing=True):
    found = []
    for name in (".claude", ".claude-2"):
        place = user_home() / name / "projects"
        if existing and not place.is_dir():
            continue
        if place.resolve() not in [item.resolve() for item in found]:
            found.append(place)
    return found


def transcripts():
    for home in homes():
        yield from home.glob("*/*.jsonl")


def transcript(session):
    if not talk_save.SESSION.fullmatch(session or ""):
        return None
    for home in homes():
        for path in home.glob(f"*/{session}.jsonl"):
            if path.is_file():
                return path
    return None


def without_pasted(text):
    kept = []
    while True:
        opening = OPENING.search(text)
        if not opening:
            kept.append(text)
            return " ".join(kept)
        kept.append(text[:opening.start()])
        closing = text.rfind(f"</pasted_content{opening.group(1)}>", opening.end())
        if closing < 0:
            return " ".join(kept)
        text = text[closing + len(f"</pasted_content{opening.group(1)}>"):]


def said(content):
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        parts = [block.get("text") for block in content
                 if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)]
    else:
        parts = []
    text = without_pasted(REMINDERS.sub(" ", "\n".join(parts)))
    if "<system-reminder>" in text:
        text = text[:text.index("<system-reminder>")]
    text = " ".join(text.split())
    return "" if text.startswith(talk_save.SKIP_START) else text


def human(entry):
    origin = entry.get("origin") if isinstance(entry.get("origin"), dict) else {}
    message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
    return (entry.get("type") == "user" and message.get("role", "user") == "user" and entry.get("entrypoint") == "cli"
            and origin.get("kind") == "human" and entry.get("promptSource") in TYPED
            and not entry.get("isMeta") and not entry.get("isSidechain") and not entry.get("isCompactSummary"))


def tail(text):
    text = " ".join(text.split())
    return text if len(text) <= ASKED_CHARS else "…" + text[-(ASKED_CHARS - 1):]


def messages(path):
    asked = ""
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict) or entry.get("isSidechain"):
                continue
            message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
            if entry.get("type") == "assistant":
                text = talk_save.plain_text(message.get("content"))
                if text:
                    asked = text
            elif human(entry):
                text = said(message.get("content"))
                if text:
                    yield {"at": str(entry.get("timestamp") or ""), "text": text, "asked": tail(asked)}


def matches(quote, text):
    quote = " ".join(quote.split())
    if not quote:
        return False
    if quote == text:
        return True
    return len(quote) >= MIN_QUOTE and quote in text


def verify(session, at, quote):
    path = transcript(session)
    if path is None:
        return {"verified": False, "reason": "no transcript for this session id on this machine"}
    if not at:
        return {"verified": False, "reason": "give the message time (--at) from the relay"}
    for item in messages(path):
        if item["at"].startswith(at) and matches(quote, item["text"]):
            return {"verified": True, "session": session, **item}
    return {"verified": False, "session": session,
            "reason": "no message the user typed in that session at that time contains this quote"}


def find(quote, days=FIND_DAYS, now=None):
    now = time.time() if now is None else now
    found = []
    for path in sorted(transcripts(), key=lambda item: item.stat().st_mtime, reverse=True):
        if path.stat().st_mtime < now - days * 86400:
            continue
        for item in messages(path):
            if matches(quote, item["text"]):
                found.append({"session": path.stem, **item})
    found.sort(key=lambda item: item["at"], reverse=True)
    return found[:FIND_LIMIT]


def unquoted(command):
    return re.sub(r"[\"'\\]", "", command)


def types_into_a_pane(command):
    if TYPING.search(command) or TYPING.search(unquoted(command)):
        return True
    return "$'" in command and bool(PANE_TOOLS.search(command))


def guarded(path):
    try:
        target = Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    for home in homes(existing=False):
        try:
            parts = target.relative_to(home.resolve()).parts
        except (ValueError, OSError):
            continue
        return not (len(parts) >= 2 and parts[1] == "memory")
    return False


def transcript_places(command):
    names = [re.escape(str(home)) for home in homes(existing=False)] + [r"[^\s;|&()<>]*/\.claude(?:-2)?/projects"]
    return re.findall(r"(?:%s)[^\s;|&()<>]*" % "|".join(names), unquoted(command))


def memory(place):
    if any(mark in place for mark in ("$", "`", "*", "?", "[", "..")):
        return False
    try:
        target = Path(os.path.expanduser(place)).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    for home in homes(existing=False):
        try:
            parts = target.relative_to(home.resolve()).parts
        except (ValueError, OSError):
            continue
        return len(parts) >= 2 and parts[1] == "memory"
    parts = os.path.normpath(place).split("/projects", 1)[-1].strip("/").split("/")
    return len(parts) >= 2 and parts[1] == "memory" and ".." not in parts


def check_tool(event):
    tool = event.get("tool_name")
    given = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = given.get("file_path") or given.get("notebook_path")
        if isinstance(path, str) and guarded(path):
            return "Session transcripts are the record of what the user typed; they are never edited."
    if tool == "Bash":
        command = given.get("command")
        if not isinstance(command, str):
            return None
        if types_into_a_pane(command):
            return ("Typing into another terminal pane would look like the user typed it. Send a message "
                    "or a relay with the user's quoted words instead.")
        if (WRITES.search(command) or WRITES.search(unquoted(command))) and any(not memory(place) for place in transcript_places(command)):
            return ("Session transcripts are the record of what the user typed; shell commands may only read them. If this "
                    "command only reads a transcript, run the write part as a separate command.")
    return None


def hook(stream):
    try:
        event = json.load(stream)
    except ValueError:
        return 0
    reason = check_tool(event) if isinstance(event, dict) else None
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Relay the user's own words between sessions and check them.")
    commands = parser.add_subparsers(dest="command", required=True)
    looking = commands.add_parser("find", help="find messages the user typed that contain the quote")
    looking.add_argument("quote")
    looking.add_argument("--days", type=float, default=FIND_DAYS)
    checking = commands.add_parser("verify", help="check a relayed quote against the sender's transcript")
    checking.add_argument("--session", required=True)
    checking.add_argument("--at", required=True)
    checking.add_argument("quote")
    commands.add_parser("hook")
    args = parser.parse_args(argv)
    if args.command == "hook":
        return hook(sys.stdin)
    if args.command == "find":
        result = find(args.quote, args.days)
        code = 0 if result else 1
    else:
        result = verify(args.session, args.at, args.quote)
        code = 0 if result["verified"] else 1
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return code


if __name__ == "__main__":
    sys.exit(main())
