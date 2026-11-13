"""Print usage metadata from the current Codex session as JSON."""

import json
import os
from pathlib import Path
import re


def read_events(thread_id):
    if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", thread_id):
        return
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    for path in (home / "sessions").glob(f"*/*/*/rollout-*-{thread_id}.jsonl"):
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                try:
                    meta = json.loads(next(stream, ""))
                except ValueError:
                    continue
                if not isinstance(meta, dict) or meta.get("type") != "session_meta":
                    continue
                payload = meta.get("payload")
                if not isinstance(payload, dict) or payload.get("id") != thread_id:
                    continue
                for line in stream:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        # The host can be writing the last line while we read.
                        continue
                    if isinstance(event, dict) and isinstance(event.get("payload"), dict):
                        yield event
                return
        except OSError:
            continue


def account_windows(limits, timestamp):
    windows = []
    for name in ("primary", "secondary"):
        window = limits.get(name)
        if not isinstance(window, dict):
            continue
        used = window.get("used_percent")
        windows.append({
            "observed_at": timestamp,
            "window_minutes": window.get("window_minutes"),
            "used_percent": used,
            "remaining_percent": round(max(0, 100 - used), 2) if used is not None else None,
            "resets_at_unix": window.get("resets_at"),
        })
    return windows


def read_usage(thread_id):
    model = effort = total = None
    context = dict.fromkeys(("observed_at", "tokens", "capacity", "used_percent", "remaining_percent"))
    windows = []
    for event in read_events(thread_id):
        payload = event["payload"]
        timestamp = event.get("timestamp")
        if event.get("type") == "turn_context":
            model = payload.get("model")
            effort = payload.get("effort")
        elif event.get("type") == "event_msg":
            if payload.get("type") == "model_reroute":
                model = payload.get("to_model") or model
            if payload.get("type") != "token_count":
                continue
            info = payload.get("info")
            if info:
                tokens = (info.get("last_token_usage") or {}).get("total_tokens")
                total = (info.get("total_token_usage") or {}).get("total_tokens")
                capacity = info.get("model_context_window")
                ratio = tokens / capacity * 100 if tokens is not None and capacity else None
                context = {
                    "observed_at": timestamp,
                    "tokens": tokens,
                    "capacity": capacity,
                    "used_percent": round(ratio, 2) if ratio is not None else None,
                    "remaining_percent": round(max(0, 100 - ratio), 2) if ratio is not None else None,
                }
            limits = payload.get("rate_limits")
            if limits and limits.get("limit_id") in (None, "codex"):
                observed = account_windows(limits, timestamp)
                if observed:
                    windows = observed
    return {
        "model": model,
        "reasoning_effort": effort,
        "context": context,
        "session_total_tokens": total,
        "account_windows": windows,
    }


if __name__ == "__main__":
    print(json.dumps(read_usage(os.environ.get("CODEX_THREAD_ID", "")), indent=2))
