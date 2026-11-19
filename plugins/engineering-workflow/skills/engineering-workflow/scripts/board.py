import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
STATUSES = ("doing", "todo", "blocked", "parked", "done")
MARKS = {"done": "✓", "doing": "▶", "todo": "○", "blocked": "✕", "parked": "⏸"}
BOARD = Path(".harness") / "board.json"
WAITING = re.compile(r"^## Waiting for the user.*?$(.*?)(?=^## |\Z)", re.S | re.M)
FENCED = re.compile(r"^```.*?^```[^\n]*$", re.S | re.M)
PAGE = re.compile(r"[A-Za-z0-9_.-]+\.html")
SEEN = 50
LABELS = {
    "en": {
        "progress": "Progress", "of": "of", "tasks": "tasks done", "doing": "In progress", "todo": "To do",
        "blocked": "Blocked", "parked": "Parked", "done": "Done", "decisions": "Waiting for your decision",
        "none": "Nothing is waiting for you.", "look": "Look at", "default": "Default in use", "task": "Task",
        "status": "Status", "after": "Needs", "owner": "Owner", "note": "Note", "updated": "Updated",
        "all": "All boards", "project": "Project", "waiting": "Decisions", "empty": "No boards yet.",
        "list": "Tasks",
    },
    "ko": {
        "progress": "전체 진행률", "of": "/", "tasks": "작업 완료", "doing": "진행 중", "todo": "남은 일",
        "blocked": "막힘", "parked": "보류", "done": "끝남", "decisions": "결정을 기다리는 일",
        "none": "기다리는 결정이 없습니다.", "look": "볼 것", "default": "지금 쓰는 기본값", "task": "작업",
        "status": "상태", "after": "선행", "owner": "담당", "note": "메모", "updated": "갱신",
        "all": "전체 보드", "project": "프로젝트", "waiting": "결정 대기", "empty": "아직 보드가 없습니다.",
        "list": "작업 목록",
    },
}
STYLE = """
:root{--surface:#fcfcfb;--panel:#ffffff;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--line:#e1e0d9;
--ring:rgba(11,11,11,.10);--track:#e1e0d9;--fill:#0b0b0b;--good:#0ca30c;--warning:#fab219;--critical:#d03b3b}
@media (prefers-color-scheme:dark){:root{--surface:#1a1a19;--panel:#222221;--ink:#f0efec;--ink2:#c3c2b7;
--line:#2c2c2a;--ring:rgba(255,255,255,.10);--track:#2c2c2a;--fill:#f0efec}}
*{box-sizing:border-box}
body{margin:0;background:var(--surface);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
main{max-width:1040px;margin:0 auto;padding:28px 20px 56px}
header{display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap}
h1{font-size:22px;margin:0}
h2{font-size:15px;margin:32px 0 10px;color:var(--ink2);font-weight:600}
a{color:inherit}
.meta{color:var(--muted);font-size:13px}
.tiles{display:grid;grid-template-columns:2fr repeat(4,1fr);gap:12px;margin-top:20px}
.tile{background:var(--panel);border:1px solid var(--ring);border-radius:10px;padding:14px 16px}
.tile .k{color:var(--ink2);font-size:13px}
.tile .v{font-size:28px;font-weight:650;font-variant-numeric:tabular-nums;line-height:1.2}
.tile .s{color:var(--muted);font-size:13px}
.meter{height:8px;background:var(--track);border-radius:4px;margin-top:10px;overflow:hidden}
.meter i{display:block;height:100%;background:var(--fill);border-radius:4px}
.decision{background:var(--panel);border:1px solid var(--ring);border-left:4px solid var(--warning);
border-radius:8px;padding:12px 16px;margin-bottom:8px}
.decision b{display:block}
.decision span{display:block;color:var(--ink2);font-size:13px}
.quiet{color:var(--muted)}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--ring);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:13px;color:var(--ink2);font-weight:600}
tr:last-child td{border-bottom:0}
td.id{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--ink2)}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.st{white-space:nowrap}
.st i{font-style:normal;display:inline-block;width:1.3em}
.st.done i{color:var(--good)}
.st.blocked i{color:var(--critical)}
tr.done td.title{color:var(--muted)}
.gap{margin-top:20px}
.mini{display:inline-block;width:90px;height:6px;background:var(--track);border-radius:3px;overflow:hidden;vertical-align:middle;margin-right:8px}
.mini i{display:block;height:100%;background:var(--fill)}
@media (max-width:760px){.tiles{grid-template-columns:1fr 1fr}.tile.wide{grid-column:1/-1}.opt{display:none}}
"""


def text(value, label, required=True):
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"{label} must be text")
    return value.strip()


def load(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("board must be an object")
    items = raw.get("tasks")
    if not isinstance(items, list) or not items:
        raise ValueError("board needs at least one task")
    tasks, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("task must be an object")
        key = item.get("id")
        if not isinstance(key, str) or not ID.fullmatch(key):
            raise ValueError("invalid task id")
        if key in seen:
            raise ValueError(f"duplicate task {key}")
        seen.add(key)
        status = item.get("status", "todo")
        if status not in STATUSES:
            raise ValueError(f"{key}: invalid status")
        after = item.get("after", [])
        if not isinstance(after, list) or not all(isinstance(dep, str) for dep in after):
            raise ValueError(f"{key}: after must be a list of task ids")
        tasks.append({"id": key, "title": text(item.get("title"), f"{key}: title"), "status": status,
                      "after": after, "owner": text(item.get("owner"), f"{key}: owner", False),
                      "note": text(item.get("note"), f"{key}: note", False)})
    for task in tasks:
        for dep in task["after"]:
            if dep not in seen:
                raise ValueError(f"{task['id']}: unknown dependency {dep}")
    decisions = []
    listed = raw.get("decisions", [])
    if not isinstance(listed, list):
        raise ValueError("decisions must be a list")
    for item in listed:
        if not isinstance(item, dict):
            raise ValueError("decision must be an object")
        decisions.append({"ask": text(item.get("ask"), "decision ask"),
                          "look": text(item.get("look"), "decision look", False),
                          "default": text(item.get("default"), "decision default", False)})
    lang = raw.get("lang", "en")
    return {"title": text(raw.get("title", "Work board"), "title"),
            "lang": lang if isinstance(lang, str) and lang in LABELS else "en",
            "tasks": tasks, "decisions": decisions}


def working_decisions(root):
    try:
        body = (Path(root) / "WORKING.md").read_text(encoding="utf-8")
    except OSError:
        return []
    section = WAITING.search(body)
    if not section:
        return []
    lines = FENCED.sub("", section.group(1)).splitlines()
    asks = [line[2:].strip() for line in lines if line.startswith("- ")]
    return [{"ask": ask, "look": "", "default": ""} for ask in asks if ask and ask.strip("().").lower() != "none"]


def counts(board):
    result = {status: 0 for status in STATUSES}
    for task in board["tasks"]:
        result[task["status"]] += 1
    total = len(board["tasks"])
    return result, total, 100 * result["done"] // total


def page(title, body, refresh):
    return ("<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<meta http-equiv=\"refresh\" content=\"{refresh}\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{html.escape(title)}</title><style>{STYLE}</style></head>"
            f"<body><main>{body}</main></body></html>")


def badge(status, words):
    return f"<span class=\"st {status}\"><i>{MARKS[status]}</i>{html.escape(words[status])}</span>"


def render(board, root, stamp, refresh=5):
    words = LABELS[board["lang"]]
    esc = html.escape
    tally, total, percent = counts(board)
    tiles = [f"<div class=\"tile wide\"><div class=\"k\">{esc(words['progress'])}</div>"
             f"<div class=\"v\">{percent}%</div><div class=\"s\">{tally['done']} {esc(words['of'])} {total} "
             f"{esc(words['tasks'])}</div><div class=\"meter\" role=\"progressbar\" aria-valuemin=\"0\" "
             f"aria-valuemax=\"100\" aria-valuenow=\"{percent}\"><i style=\"width:{percent}%\"></i></div></div>"]
    waiting = tally["parked"] + tally["blocked"]
    for key, value in (("doing", tally["doing"]), ("todo", tally["todo"]), ("parked", waiting),
                       ("decisions", len(board["decisions"]))):
        label = words["waiting"] if key == "decisions" else words[key]
        tiles.append(f"<div class=\"tile\"><div class=\"k\">{esc(label)}</div><div class=\"v\">{value}</div></div>")
    asks = []
    for item in board["decisions"]:
        extra = "".join(f"<span>{esc(words[key])}: {esc(item[key])}</span>" for key in ("look", "default") if item[key])
        asks.append(f"<div class=\"decision\"><b>{esc(item['ask'])}</b>{extra}</div>")
    if not asks:
        asks.append(f"<p class=\"quiet\">{esc(words['none'])}</p>")
    rows = []
    for task in sorted(board["tasks"], key=lambda item: STATUSES.index(item["status"])):
        rows.append(f"<tr class=\"{task['status']}\"><td class=\"id\">{esc(task['id'])}</td>"
                    f"<td class=\"title\">{esc(task['title'])}</td><td>{badge(task['status'], words)}</td>"
                    f"<td class=\"opt id\">{esc(', '.join(task['after']))}</td>"
                    f"<td class=\"opt\">{esc(task['owner'])}</td><td class=\"opt\">{esc(task['note'])}</td></tr>")
    columns = (("ID", ""), (words["task"], ""), (words["status"], ""), (words["after"], " class=\"opt\""),
               (words["owner"], " class=\"opt\""), (words["note"], " class=\"opt\""))
    head = "".join(f"<th{cls}>{esc(label)}</th>" for label, cls in columns)
    body = (f"<header><h1>{esc(board['title'])}</h1><div class=\"meta\">{esc(str(root))} · {esc(words['updated'])} "
            f"{esc(stamp)} · <a href=\"index.html\">{esc(words['all'])}</a></div></header>"
            f"<div class=\"tiles\">{''.join(tiles)}</div><h2>{esc(words['decisions'])}</h2>{''.join(asks)}"
            f"<h2>{esc(words['list'])}</h2><table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>")
    return page(board["title"], body, refresh)


def overview(entries, lang, refresh=5):
    words = LABELS[lang]
    esc = html.escape
    rows = []
    for entry in sorted(entries, key=lambda item: item["title"].casefold()):
        entry = {key: esc(str(value)) for key, value in entry.items()}
        rows.append(f"<tr><td><a href=\"{entry['page']}\">{entry['title']}</a>"
                    f"<div class=\"meta\">{entry['root']}</div></td>"
                    f"<td class=\"num\"><span class=\"mini\"><i style=\"width:{entry['percent']}%\"></i></span>"
                    f"{entry['percent']}% · {entry['done']} {esc(words['of'])} {entry['total']}</td>"
                    f"<td class=\"num\">{entry['doing']}</td><td class=\"num\">{entry['decisions']}</td>"
                    f"<td class=\"num opt\">{entry['stamp']}</td></tr>")
    if not rows:
        table = f"<p class=\"quiet\">{esc(words['empty'])}</p>"
    else:
        head = "".join(f"<th{cls}>{esc(words[key])}</th>" for key, cls in (
            ("project", ""), ("progress", ""), ("doing", ""), ("waiting", ""), ("updated", " class=\"opt\"")))
        table = f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    return page(words["all"], f"<header><h1>{esc(words['all'])}</h1></header><div class=\"gap\">{table}</div>", refresh)


def home():
    custom = os.environ.get("HARNESS_BOARD_HOME")
    if custom and Path(custom).expanduser().is_absolute():
        return Path(custom).expanduser()
    return Path.home() / ".cache" / "engineering-workflow" / "boards"


def slug(root):
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(root).name).strip("-.") or "project"
    return f"{name}-{hashlib.sha256(str(root).encode('utf-8')).hexdigest()[:8]}"


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def publish(board_path, root=None, out=None):
    board_path = Path(os.path.abspath(board_path))
    root = Path(os.path.abspath(root)) if root else (
        board_path.parent.parent if board_path.parent.name == BOARD.parent.name else board_path.parent)
    board = load(board_path)
    board["decisions"] = board["decisions"] + working_decisions(root)
    stamp = datetime.fromtimestamp(board_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    content = render(board, root, stamp)
    if out:
        write(Path(out), content)
        return Path(out)
    folder, name = home(), slug(root)
    write(folder / f"{name}.html", content)
    tally, total, percent = counts(board)
    write(folder / f"{name}.json", json.dumps({
        "title": board["title"], "root": str(root), "board": str(board_path), "page": f"{name}.html",
        "percent": percent, "done": tally["done"], "total": total, "doing": tally["doing"],
        "decisions": len(board["decisions"]), "stamp": stamp, "lang": board["lang"]}, ensure_ascii=False))
    entries = []
    for summary in sorted(folder.glob("*.json")):
        try:
            entry = json.loads(summary.read_text(encoding="utf-8"))
            texts = all(isinstance(entry[key], str) for key in ("title", "root", "board", "page", "stamp"))
            numbers = all(type(entry[key]) is int for key in ("percent", "done", "total", "doing", "decisions"))
            if texts and numbers and PAGE.fullmatch(entry["page"]) and Path(entry["board"]).is_file():
                entries.append(entry)
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            continue
    write(folder / "index.html", overview(entries, board["lang"]))
    return folder / f"{name}.html"


def launch(path):
    if os.environ.get("HARNESS_BOARD_OPEN", "1").strip().lower() in ("0", "false", "no", "off"):
        return
    target = str(Path(path).resolve())
    try:
        if sys.platform == "win32":
            os.startfile(target)
            return
        opener = "open" if sys.platform == "darwin" else shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, target], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return


def show_once(path, root, session):
    marker = home() / f"{slug(root)}.opened"
    try:
        seen = marker.read_text(encoding="utf-8").split("\n")
    except OSError:
        seen = None
    if seen is not None and (not session or session in seen):
        return False
    launch(path)
    write(marker, "\n".join(([session] if session else []) + (seen or [])[:SEEN - 1]))
    return True


def find_root(event):
    cwd = event.get("cwd")
    start = Path(os.path.abspath(cwd if isinstance(cwd, str) and cwd else os.getcwd()))
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        return Path(os.path.abspath(project)), start
    for folder in (start, *start.parents):
        if (folder / BOARD).is_file():
            return folder, start
    return start, start


def same_file(first, second):
    try:
        return os.path.samefile(first, second)
    except OSError:
        return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def hook(event):
    if not isinstance(event, dict):
        return None
    name = event.get("hook_event_name")
    if name not in ("SessionStart", "PostToolUse", "Stop"):
        return None
    root, start = find_root(event)
    board_path = root / BOARD
    if not board_path.is_file():
        return None
    if name == "PostToolUse":
        tool_input = event.get("tool_input")
        target = tool_input.get("file_path") if isinstance(tool_input, dict) else None
        if not isinstance(target, str) or not target or not same_file(start / target, board_path):
            return None
    try:
        output = publish(board_path, root)
    except Exception as error:
        return {"systemMessage": f"board: {BOARD.as_posix()} was not rendered: {type(error).__name__}: {error}"}
    session = event.get("session_id")
    show_once(output, root, session if isinstance(session, str) else "")
    if name == "SessionStart":
        return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": (
            f"Progress board: {BOARD.as_posix()} renders to {output}. Edit the JSON when a task changes state "
            "or a decision is parked or settled. Never edit the HTML.")}}
    return None


def main():
    parser = argparse.ArgumentParser(description="Render a task board from .harness/board.json to one local HTML page.")
    commands = parser.add_subparsers(dest="command", required=True)
    draw = commands.add_parser("render", help="render a board file")
    draw.add_argument("board", nargs="?", default=str(BOARD))
    draw.add_argument("--out", help="write the page here and skip the shared overview")
    draw.add_argument("--open", action="store_true", help="open the page in the default browser")
    commands.add_parser("hook", help="read a SessionStart, PostToolUse, or Stop hook event from standard input")
    args = parser.parse_args()
    if args.command == "hook":
        try:
            result = hook(json.load(sys.stdin))
        except Exception:
            return 0
        if result:
            print(json.dumps(result, ensure_ascii=False))
        return 0
    try:
        output = publish(args.board, out=args.out)
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(f"INVALID: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(output)
    if args.open:
        launch(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
