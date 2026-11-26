import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

SESSION = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
EVENTS = ("PreCompact", "SessionEnd")
FIRST_READ = 50 * 1024 * 1024
CHUNK = 3500
USER_CHARS = 1500
REPLY_CHARS = 1200
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
SKIP_START = ("<local-command", "<command-name>", "<command-message>", "Caveat:", "[Request interrupted")


def root():
    return Path(os.environ.get("HARNESS_TALK") or Path.home() / ".cache/engineering-workflow/talk").expanduser()


def registry_apps():
    folder = os.environ.get("HARNESS_REGISTRY_CONFIG")
    path = Path(folder).expanduser() if folder else Path.home() / ".config/engineering-workflow/registry.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    apps = data.get("apps") if isinstance(data, dict) else None
    return [(item["name"], Path(item["path"]).expanduser()) for item in apps or []
            if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("path"), str)]


def app_for(folder):
    if not folder:
        return "unknown"
    here = Path(folder).expanduser().resolve()
    best = None
    for name, path in registry_apps():
        try:
            here.relative_to(path.resolve())
        except (ValueError, OSError):
            continue
        if best is None or len(str(path)) > len(str(best[1])):
            best = (name, path)
    if best:
        return best[0]
    return re.sub(r"[^\w.-]+", "-", here.name).strip("-") or "unknown"


def plain_text(content):
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        parts = [block.get("text") for block in content
                 if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)]
    else:
        parts = []
    text = REMINDER.sub(" ", "\n".join(parts)).strip()
    return "" if not text or text.startswith(SKIP_START) else text


def clip(text, limit):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def read_from(path, offset):
    size = path.stat().st_size
    if offset > size:
        offset = 0
    start = offset if offset else max(0, size - FIRST_READ)
    with open(path, "rb") as handle:
        handle.seek(start)
        data = handle.read()
    if start and not offset:
        cut = data.find(b"\n")
        data = data[cut + 1:] if cut >= 0 else b""
        start = size - len(data)
    end = data.rfind(b"\n")
    if end < 0:
        return [], offset
    lines, place = [], start
    for raw in data[:end + 1].split(b"\n")[:-1]:
        lines.append((place, raw.decode("utf-8", "replace")))
        place += len(raw) + 1
    return lines, start + end + 1


def exchanges(lines):
    found, current = [], None
    for place, line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("isSidechain") or entry.get("isMeta") or entry.get("isCompactSummary"):
            continue
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        if entry.get("type") == "user" and message.get("role", "user") == "user":
            text = plain_text(message.get("content"))
            if text:
                current = {"at": str(entry.get("timestamp") or ""), "user": text, "reply": "", "place": place}
                found.append(current)
        elif entry.get("type") == "assistant" and current is not None:
            text = plain_text(message.get("content"))
            if text:
                current["reply"] = text
    return found


def local(stamp):
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return stamp[:16].replace("T", " ")


def chunks(items):
    group, size = [], 0
    for item in items:
        block = f"- 사용자 ({local(item['at'])}): {clip(item['user'], USER_CHARS)}\n"
        if item["reply"]:
            block += f"  - 답: {clip(item['reply'], REPLY_CHARS)}\n"
        if group and size + len(block) > CHUNK:
            yield group
            group, size = [], 0
        group.append(block)
        size += len(block)
    if group:
        yield group


def inside_repository(folder):
    for place in [folder, *folder.parents]:
        if (place / ".git").exists():
            return True
    return False


def safe_folder(app):
    base = root().resolve()
    name = re.sub(r"[^\w.-]+", "-", app).strip("-.") or "unknown"
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)
    real = folder.resolve()
    try:
        real.relative_to(base)
    except ValueError:
        return None
    return None if inside_repository(real) else real


def put(folder, name, text):
    handle, spare = tempfile.mkstemp(dir=folder, prefix=".", suffix=".part")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(spare, folder / name)
    except BaseException:
        try:
            os.unlink(spare)
        except OSError:
            pass
        raise


def write_notes(app, session, items, now):
    folder = safe_folder(app)
    if folder is None:
        return None
    stamp = datetime.fromtimestamp(now).strftime("%Y-%m-%d-%H%M%S")
    written = []
    for number, group in enumerate(chunks(items), 1):
        line = group[0].split("\n", 1)[0]
        first = line.split("): ", 1)[1] if "): " in line else line
        key = f"{stamp}-{session[:8]}-{items[0]['place']:x}-{number:02}"
        title = clip(first, 70).replace('"', "'")
        head = (f"---\nid: {key}\ntitle: \"{title}\"\nsession: {session}\napp: {app}\n"
                f"date: {stamp[:10]}\n---\n\n")
        put(folder, f"{key}.md", head + "".join(group))
        written.append(folder / f"{key}.md")
    return written


def state_file(session):
    return root() / ".state" / f"{session}.json"


def load_offset(session):
    try:
        data = json.loads(state_file(session).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    value = data.get("offset") if isinstance(data, dict) else None
    return value if isinstance(value, int) and value >= 0 else 0


def save_offset(session, offset):
    path = state_file(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    put(path.parent, path.name, json.dumps({"offset": offset, "at": int(time.time())}))


def save(event, now=None):
    now = time.time() if now is None else now
    if not isinstance(event, dict) or event.get("hook_event_name") not in EVENTS:
        return []
    session, transcript = event.get("session_id"), event.get("transcript_path")
    if not isinstance(session, str) or not SESSION.fullmatch(session) or not isinstance(transcript, str):
        return []
    path = Path(transcript).expanduser()
    if path.name != f"{session}.jsonl" or not path.is_file():
        return []
    base = root()
    if not base.is_absolute() or inside_repository(base.resolve()):
        return []
    lines, offset = read_from(path, load_offset(session))
    items = exchanges(lines)
    if items and event.get("hook_event_name") == "PreCompact":
        offset = items[-1]["place"]
        items = items[:-1]
    elif items and not items[-1]["reply"]:
        offset = items[-1]["place"]
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd")
    written = write_notes(app_for(cwd if isinstance(cwd, str) else None), session, items, now) if items else []
    if written is None:
        return []
    save_offset(session, offset)
    return written


def main():
    try:
        save(json.load(sys.stdin))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
