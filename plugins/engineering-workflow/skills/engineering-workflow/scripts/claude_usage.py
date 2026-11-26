import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

SESSION = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
TAIL = 4 * 1024 * 1024
SNAPSHOT_AGE = 6 * 3600


def config_root():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()


def config_file():
    folder = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(folder).expanduser() / ".claude.json" if folder else Path.home() / ".claude.json"


def snapshot_folder():
    return Path(os.environ.get("HARNESS_USAGE_CACHE") or Path.home() / ".cache/engineering-workflow/usage").expanduser()


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds")


def percent(used, capacity):
    if not isinstance(used, (int, float)) or not isinstance(capacity, (int, float)) or capacity <= 0:
        return None, None
    ratio = used / capacity * 100
    return round(ratio, 2), round(max(0.0, 100 - ratio), 2)


def load(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def transcript(session):
    for path in (config_root() / "projects").glob(f"*/{session}.jsonl"):
        if path.is_file():
            return path
    return None


def last_usage(path):
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - TAIL))
            lines = handle.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"usage"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        message = entry.get("message") if isinstance(entry, dict) else None
        usage = message.get("usage") if isinstance(message, dict) else None
        if entry.get("type") != "assistant" or entry.get("isSidechain") or not isinstance(usage, dict):
            continue
        tokens = sum(usage.get(key) or 0 for key in ("input_tokens", "cache_creation_input_tokens",
                                                     "cache_read_input_tokens", "output_tokens")
                     if isinstance(usage.get(key) or 0, (int, float)))
        return {"observed_at": entry.get("timestamp"), "model": message.get("model"), "tokens": tokens}
    return None


def live_snapshot(session, now):
    data = load(snapshot_folder() / f"{session}.json")
    if not isinstance(data, dict) or data.get("session_id") != session:
        return None
    at = data.get("at")
    if not isinstance(at, (int, float)) or now - at > SNAPSHOT_AGE:
        return None
    window = data.get("context_window") if isinstance(data.get("context_window"), dict) else {}
    current = window.get("current_usage") if isinstance(window.get("current_usage"), dict) else {}
    used = sum(current.get(key) or 0 for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
               if isinstance(current.get(key) or 0, (int, float))) or None
    capacity = window.get("context_window_size")
    model = data.get("model") if isinstance(data.get("model"), dict) else {}
    return {"observed_at": stamp(at), "tokens": used, "capacity": capacity if isinstance(capacity, int) else None,
            "model": model.get("id") or model.get("display_name")}


def context(session, now):
    empty = dict.fromkeys(("observed_at", "tokens", "capacity", "used_percent", "remaining_percent", "source"))
    if not session:
        return empty, None
    live = live_snapshot(session, now)
    path = transcript(session)
    last = last_usage(path) if path else None
    if live and live["tokens"] is not None:
        chosen, source = live, "status line"
    elif last:
        chosen, source = dict(last, capacity=live["capacity"] if live else None), "transcript"
    else:
        return empty, live["model"] if live else None
    used, left = percent(chosen["tokens"], chosen.get("capacity"))
    return ({"observed_at": chosen["observed_at"], "tokens": chosen["tokens"], "capacity": chosen.get("capacity"),
             "used_percent": used, "remaining_percent": left, "source": source},
            (last or {}).get("model") or chosen.get("model"))


def account(now):
    data = load(config_file())
    if not isinstance(data, dict):
        return [], "no Claude config file"
    cached = data.get("cachedUsageUtilization")
    owner = (data.get("oauthAccount") or {}).get("accountUuid") if isinstance(data.get("oauthAccount"), dict) else None
    if not isinstance(cached, dict):
        return [], "no cached usage; open /usage once"
    if not owner or cached.get("accountUuid") != owner:
        return [], "cached usage belongs to another account"
    fetched = cached.get("fetchedAtMs")
    observed = stamp(fetched / 1000) if isinstance(fetched, (int, float)) else None
    age = int(max(0, now - fetched / 1000) // 60) if isinstance(fetched, (int, float)) else None
    windows = []
    for name, window in (cached.get("utilization") or {}).items():
        if not isinstance(window, dict) or not isinstance(window.get("utilization"), (int, float)):
            continue
        used = window["utilization"]
        windows.append({"window": name, "used_percent": used, "remaining_percent": round(max(0, 100 - used), 2),
                        "resets_at": window.get("resets_at"), "observed_at": observed, "age_minutes": age})
    return windows, None if windows else "cached usage has no windows"


def read_usage(session, now=None):
    now = time.time() if now is None else now
    session = session if session and SESSION.fullmatch(session) else None
    ctx, model = context(session, now)
    windows, note = account(now)
    return {"session": session, "model": model, "context": ctx, "account_windows": windows, "account_note": note,
            "measured_at": stamp(now)}


def main():
    parser = argparse.ArgumentParser(description="Print the Claude Code session's context and account usage as JSON.")
    parser.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    args = parser.parse_args()
    print(json.dumps(read_usage(args.session), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
