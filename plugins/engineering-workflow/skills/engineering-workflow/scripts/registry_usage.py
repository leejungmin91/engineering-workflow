import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_CONFIG = Path.home() / ".config" / "engineering-workflow" / "registry.json"
SOURCES = {"claude": [str(Path.home() / ".claude" / "projects")],
           "codex": [str(Path.home() / ".codex" / "sessions"), str(Path.home() / ".codex" / "archived_sessions")]}
SKILL_PATH = re.compile(r"skills/([A-Za-z0-9_.-]+)/SKILL\.md")
SKILL_NAME = re.compile(r"[A-Za-z0-9_.-]{1,80}")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
CHUNK = 1 << 20
try:
    from compression import zstd
    BROKEN = (OSError, EOFError, ValueError, zstd.ZstdError)
except ImportError:
    zstd = None
    BROKEN = (OSError, EOFError, ValueError)


def app_for(folder, apps):
    if not isinstance(folder, str):
        return None
    best = None
    for name, root in apps:
        if folder == root or folder.startswith(root.rstrip("/") + "/"):
            if best is None or len(root) > len(best[1]):
                best = (name, root)
    return best[0] if best else None


def claude_calls(item):
    message = item.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    for part in content if isinstance(content, list) else []:
        if not isinstance(part, dict) or part.get("type") != "tool_use":
            continue
        given = part.get("input") if isinstance(part.get("input"), dict) else {}
        if part.get("name") == "Skill" and isinstance(given.get("skill"), str):
            name = given["skill"].split(":")[-1].strip()
            if SKILL_NAME.fullmatch(name):
                yield name
        for key in ("file_path", "path", "command"):
            if isinstance(given.get(key), str):
                yield from SKILL_PATH.findall(given[key])


def codex_calls(item):
    payload = item.get("payload")
    if item.get("type") != "response_item" or not isinstance(payload, dict):
        return
    if payload.get("type") not in ("function_call", "custom_tool_call", "local_shell_call"):
        return
    parts = [payload.get("arguments"), payload.get("input")]
    action = payload.get("action")
    if isinstance(action, dict):
        parts.append(action.get("command"))
    for part in parts:
        text = " ".join(part) if isinstance(part, list) and all(isinstance(x, str) for x in part) else part
        if isinstance(text, str):
            yield from SKILL_PATH.findall(text)


def folder_of(agent, item):
    if agent == "claude":
        return item.get("cwd")
    payload = item.get("payload")
    if item.get("type") == "session_meta" and isinstance(payload, dict):
        return payload.get("cwd")
    return None


def date_of(item):
    stamp = item.get("timestamp")
    if not isinstance(stamp, str) and isinstance(item.get("payload"), dict):
        stamp = item["payload"].get("timestamp")
    found = DATE.match(stamp) if isinstance(stamp, str) else None
    return found.group(0) if found else None


def read_packed(agent, path, entry):
    entry.clear()
    with zstd.open(path, "rb") as handle:
        for raw in handle:
            if raw.endswith(b"\n"):
                take(agent, raw[:-1], entry)
    entry["offset"] = path.stat().st_size
    return entry


def read_log(agent, path, entry):
    if path.name.endswith(".zst"):
        return read_packed(agent, path, entry)
    size = path.stat().st_size
    if size < entry.get("offset", 0):
        entry.clear()
    with path.open("rb", buffering=CHUNK) as handle:
        handle.seek(entry.get("offset", 0))
        for raw in handle:
            if not raw.endswith(b"\n"):
                break
            entry["offset"] = entry.get("offset", 0) + len(raw)
            take(agent, raw[:-1], entry)
    return entry


def take(agent, raw, entry):
    wanted = b"SKILL.md" in raw or (agent == "claude" and b'"Skill"' in raw)
    if not wanted and (entry.get("folder") is not None or b"cwd" not in raw):
        return
    try:
        item = json.loads(raw)
    except ValueError:
        return
    if not isinstance(item, dict):
        return
    if entry.get("folder") is None:
        entry["folder"] = folder_of(agent, item)
    calls = claude_calls(item) if agent == "claude" else codex_calls(item)
    found = sorted(set(calls))
    if found:
        when = date_of(item)
        days = entry.setdefault("skills", {})
        for skill in found:
            seen = days.setdefault(skill, [when, when])
            if when:
                seen[0] = min(filter(None, (seen[0], when)))
                seen[1] = max(filter(None, (seen[1], when)))


def logs(sources):
    for agent, folders in sources.items():
        for folder in [folders] if isinstance(folders, str) else folders:
            yield from logs_in(agent, Path(folder))


def logs_in(agent, root):
    if root.is_dir():
        for path in sorted([*root.rglob("*.jsonl"), *root.rglob("*.jsonl.zst")]):
            if path.is_file():
                yield agent, root, path


def session_for(agent, root, path):
    parts = path.relative_to(root).parts
    if "subagents" in parts[:-1]:
        return f"{agent}:{root.joinpath(*parts[:parts.index('subagents')])}"
    return f"{agent}:{path.with_name(path.name.removesuffix('.zst').removesuffix('.jsonl'))}"


def summary(state, apps):
    usage = {}
    for key, entry in state.items():
        agent = key.split(":", 1)[0]
        app = app_for(entry.get("folder"), apps)
        if not app:
            continue
        for skill, (first, last) in entry.get("skills", {}).items():
            row = usage.setdefault(f"{app}\t{skill}\t{agent}", {"app": app, "skill": skill, "agent": agent,
                                                                 "sessions": set(), "first": first, "last": last})
            row["sessions"].add(entry.get("session") or key)
            row["first"] = min(filter(None, (row["first"], first)), default=None)
            row["last"] = max(filter(None, (row["last"], last)), default=None)
    rows = [{**row, "sessions": len(row["sessions"])} for row in usage.values()]
    return sorted(rows, key=lambda row: (row["app"], row["skill"], row["agent"]))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    spare = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    spare.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(spare, path)


def update(config):
    target = config.get("usage")
    if not isinstance(target, str) or not target:
        raise ValueError("the registry config has no \"usage\" file path")
    target = Path(target)
    keep = target.with_name(target.name + ".state.json")
    try:
        state = json.loads(keep.read_text(encoding="utf-8"))
        state = state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        state = {}
    sources = config.get("usage_sources") or SOURCES
    if not isinstance(sources, dict) or not all(
            agent in SOURCES and (isinstance(folder, str) or (isinstance(folder, list) and folder and all(
                isinstance(item, str) for item in folder))) for agent, folder in sources.items()):
        raise ValueError("usage_sources must map claude or codex to a folder or a list of folders")
    seen, read, packed = set(), 0, 0
    for agent, root, path in logs(sources):
        if path.name.endswith(".zst") and zstd is None:
            packed += 1
            continue
        key = f"{agent}:{path}"
        seen.add(key)
        entry = state.get(key) if isinstance(state.get(key), dict) else {}
        try:
            if path.stat().st_size != entry.get("offset"):
                state[key] = read_log(agent, path, entry)
                read += 1
            state[key]["session"] = session_for(agent, root, path)
        except BROKEN:
            state.pop(key, None)
            seen.discard(key)
            continue
    state = {key: entry for key, entry in state.items() if key in seen}
    apps = [(item["name"], str(Path(item["path"]))) for item in config.get("apps", [])]
    rows = summary(state, apps)
    write(keep, state)
    write(target, {"usage": rows})
    return {"logs": len(seen), "read": read, "rows": len(rows), "skipped_packed": packed}


def main():
    parser = argparse.ArgumentParser(description="Count, per app, how many agent sessions used each skill. Reads only "
                                                 "tool calls and working folders from local session logs, never the "
                                                 "prompts, and writes the counts to the config's usage file.")
    parser.add_argument("--config", help="registry config (default: HARNESS_REGISTRY_CONFIG, then "
                                         "~/.config/engineering-workflow/registry.json)")
    args = parser.parse_args()
    path = Path(args.config or os.environ.get("HARNESS_REGISTRY_CONFIG") or DEFAULT_CONFIG)
    try:
        report = update(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"INVALID: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(f"logs {report['logs']}  read {report['read']}  rows {report['rows']}"
          + (f"  skipped {report['skipped_packed']} compressed logs (this Python has no zstd)"
             if report["skipped_packed"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
