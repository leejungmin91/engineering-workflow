import argparse
import hashlib
import html
import json
import os
import re
import shutil
import stat
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
PAGE = re.compile(r"[A-Za-z0-9_.-]+\.html")
SEEN = 50
LABELS = {
    "en": {
        "progress": "Progress", "of": "of", "tasks": "tasks done", "doing": "In progress", "todo": "To do",
        "blocked": "Blocked", "parked": "Parked", "done": "Done", "decisions": "Waiting for your decision",
        "none": "Nothing is waiting for you.", "look": "Look at", "default": "Default", "updated": "Updated",
        "all": "All boards", "project": "Project", "waiting": "Decisions", "empty": "No boards yet.",
        "list": "Tasks", "now": "Now", "next": "Next", "idle": "Nothing is in progress.",
        "clear": "Nothing left to start.", "after": "after", "everyone": "Everyone", "records": "Recent work records",
        "need": "Decisions", "ok": "Nothing blocked", "signal": "Signal", "focus": "Now", "on": "On track",
        "order": "Boards with decisions or blocked work come first", "close": "Close", "picture": "Picture",
        "prev": "Previous", "nextpic": "Next",
    },
    "ko": {
        "progress": "전체 진행률", "of": "/", "tasks": "작업 완료", "doing": "진행 중", "todo": "남은 일",
        "blocked": "막힘", "parked": "보류", "done": "끝남", "decisions": "결정을 기다리는 일",
        "none": "기다리는 결정이 없습니다.", "look": "볼 것", "default": "기본값", "updated": "갱신",
        "all": "전체 보드", "project": "프로젝트", "waiting": "결정 대기", "empty": "아직 보드가 없습니다.",
        "list": "작업", "now": "지금 하는 일", "next": "다음 차례", "idle": "진행 중인 작업이 없습니다.",
        "clear": "남은 작업이 없습니다.", "after": "다음", "everyone": "전체", "records": "최근 작업 기록",
        "need": "결정 필요", "ok": "막힌 것 없음", "signal": "신호", "focus": "지금", "on": "순조",
        "order": "결정이나 막힘이 있는 보드가 위에 옵니다", "close": "닫기", "picture": "그림",
        "prev": "이전", "nextpic": "다음",
    },
}
BAR_ORDER = ("done", "doing", "parked", "blocked", "todo")
PICTURE = re.compile(r"`([^`\n]+\.(?:png|jpe?g|gif|webp|svg))`|([^\s`'\"()<>,;]+\.(?:png|jpe?g|gif|webp|svg))(?![\w.])", re.I)
PICTURE_BYTES = 20 * 1024 * 1024
PICTURES = 8
RECORDS = 5
STALE_HOURS = 24
STYLE = """
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--line:#e1e0d9;
--ring:rgba(11,11,11,.10);--done:#008300;--doing:#2a78d6;--parked:#eda100;--blocked:#d03b3b;--todo:#e1e0d9;
--warn-bg:#fdf3dc;--warn-ink:#7a5200;--bad-bg:#fbe5e5;--bad-ink:#9c1f1f;--good-bg:#e3f2e3;--good-ink:#006300}
@media (prefers-color-scheme:dark){:root{--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--line:#2c2c2a;--ring:rgba(255,255,255,.10);--done:#0ca30c;--doing:#3987e5;--parked:#c98500;--todo:#383835;
--warn-bg:#3a2c0a;--warn-ink:#f5c45a;--bad-bg:#3a1414;--bad-ink:#f08a8a;--good-bg:#12290f;--good-ink:#0ca30c}}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 20px 48px;overflow-wrap:anywhere}
header{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin-bottom:20px}
h1{font-size:22px;margin:0;font-weight:650}
h2{font-size:13px;margin:0 0 10px;color:var(--ink2);font-weight:600;display:flex;align-items:center;gap:8px}
a{color:inherit}.spacer{flex:1}.meta{color:var(--muted);font-size:12px}.wide{flex-basis:100%}
.chip{display:inline-flex;align-items:center;gap:4px;padding:1px 8px;border-radius:999px;font-size:12px;
background:var(--surface);box-shadow:inset 0 0 0 1px var(--ring);color:var(--ink2);white-space:nowrap;text-decoration:none}
.chip.warn{background:var(--warn-bg);color:var(--warn-ink);box-shadow:none}
.chip.bad{background:var(--bad-bg);color:var(--bad-ink);box-shadow:none}
.chip.good{background:var(--good-bg);color:var(--good-ink);box-shadow:none}
.card{background:var(--surface);border-radius:12px;box-shadow:inset 0 0 0 1px var(--ring);padding:16px;min-width:0}
.top{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:12px}
.top ul{list-style:none;padding:0;margin:0}.top li{margin:6px 0}
.id{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);margin-right:6px}
.owner{font-size:12px;color:var(--muted);margin-left:6px}.sub{color:var(--ink2);font-size:13px}.quiet{color:var(--muted)}
.big{font-size:40px;font-weight:650;line-height:1.1;font-variant-numeric:tabular-nums}
.bar{display:flex;gap:2px;height:8px;margin:12px 0 8px}.bar span{border-radius:999px;min-width:4px}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--ink2)}
.legend i{display:inline-block;width:8px;height:8px;border-radius:999px;margin-right:5px}
section{margin-top:24px}.decisions{display:grid;gap:8px}
.decision{display:grid;grid-template-columns:28px 1fr;gap:2px 10px;padding:12px 14px;background:var(--surface);
border-radius:12px;box-shadow:inset 0 0 0 1px var(--ring)}
.decision .n{grid-row:span 2;color:var(--warn-ink);font-weight:650;font-size:13px}.decision b{font-weight:600}
.decision .more{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12px;color:var(--muted)}
.filters{display:flex;gap:6px;margin:0 0 10px;flex-wrap:wrap}
.filters button{font:inherit;font-size:12px;border:0;border-radius:999px;padding:3px 10px;background:var(--surface);
color:var(--ink2);box-shadow:inset 0 0 0 1px var(--ring);cursor:pointer}
.filters button[aria-pressed=true]{background:var(--ink);color:var(--page);box-shadow:none}
.group{margin-bottom:14px}.rows{background:var(--surface);border-radius:12px;box-shadow:inset 0 0 0 1px var(--ring)}
.row{display:grid;grid-template-columns:22px 92px 1fr auto;gap:2px 10px;padding:10px 14px;border-top:1px solid var(--line)}
.row[hidden]{display:none}.row>*{min-width:0}.row:first-child{border-top:0}.row .title{font-weight:500}.row.done .title{color:var(--ink2)}
.row .after{font-size:12px;color:var(--muted)}.row details{grid-column:3/5;font-size:12px;color:var(--ink2)}
.row summary{cursor:pointer;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;list-style:none}
.row summary::-webkit-details-marker{display:none}.row details[open] summary{white-space:normal}
details.fold>summary{cursor:pointer;color:var(--ink2);font-weight:600;font-size:13px;margin-bottom:8px}
.mark{color:var(--muted)}.mark.doing{color:var(--doing)}.mark.done{color:var(--done)}
.mark.blocked{color:var(--blocked)}.mark.parked{color:var(--warn-ink)}
.thumbs{grid-column:2;display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.thumb{padding:0;border:0;background:none;cursor:zoom-in;border-radius:8px;box-shadow:inset 0 0 0 1px var(--ring)}
.thumb img{display:block;width:96px;height:72px;object-fit:cover;border-radius:8px}
.thumb:focus-visible{outline:2px solid var(--doing);outline-offset:2px}
dialog.viewer{border:0;padding:0;background:transparent;max-width:96vw;max-height:96vh;color:var(--ink)}
dialog.viewer::backdrop{background:rgba(0,0,0,.82)}
dialog.viewer img{display:block;max-width:96vw;max-height:84vh;object-fit:contain;margin:0 auto;border-radius:8px}
dialog.viewer .bar2{display:flex;gap:8px;align-items:center;justify-content:center;margin-top:10px;color:#f0efec;font-size:13px}
dialog.viewer button{font:inherit;font-size:13px;border:0;border-radius:999px;padding:4px 12px;background:#2c2c2a;color:#f0efec;cursor:pointer}
.records{padding-left:18px;margin:0;color:var(--ink2)}.records li{margin:4px 0}
table{width:100%;border-collapse:collapse}th{text-align:left;font-size:12px;color:var(--muted);font-weight:600;padding:8px 14px}
td{padding:12px 14px;border-top:1px solid var(--line);vertical-align:top}td .bar{margin:4px 0 0;max-width:160px}
@media (max-width:760px){.top{grid-template-columns:1fr}.row{grid-template-columns:22px 1fr}.row .id,.row .owner{display:none}
.row details{grid-column:2}.opt{display:none}}
"""
SCRIPT = """
(() => {
const ko = document.documentElement.lang === 'ko';
const words = ko ? ['방금', '분 전', '시간 전', '일 전'] : ['just now', 'm ago', 'h ago', 'd ago'];
const ago = (t) => { const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return words[0]; if (s < 3600) return Math.floor(s / 60) + words[1];
  if (s < 86400) return Math.floor(s / 3600) + words[2]; return Math.floor(s / 86400) + words[3]; };
const tick = () => document.querySelectorAll('[data-at]').forEach((el) => { const t = Number(el.dataset.at);
  el.textContent = el.dataset.label + ' ' + ago(t); el.title = new Date(t).toLocaleString();
  el.classList.toggle('warn', Date.now() - t > Number(el.dataset.stale)); });
tick(); setInterval(tick, 30000);
const key = 'board:' + location.pathname;
let saved = {}; try { saved = JSON.parse(sessionStorage.getItem(key) || '{}'); } catch (e) {}
document.querySelectorAll('details[id]').forEach((d) => { if (typeof saved[d.id] === 'boolean') d.open = saved[d.id]; });
const owner = (name) => { saved.owner = name;
  document.querySelectorAll('.filters button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.owner === name)));
  document.querySelectorAll('.row[data-owner]').forEach((r) => { r.hidden = name !== '*' && r.dataset.owner !== name; }); };
document.querySelectorAll('.filters button').forEach((b) => b.addEventListener('click', () => owner(b.dataset.owner)));
if (typeof saved.owner === 'string' && document.querySelector(`.filters button[data-owner="${CSS.escape(saved.owner)}"]`)) owner(saved.owner);
const viewer = document.querySelector('dialog.viewer');
if (viewer) {
  const big = viewer.querySelector('img'), caption = viewer.querySelector('.name');
  let group = [], at = 0;
  const show = (i) => { at = (i + group.length) % group.length; const b = group[at];
    big.src = b.dataset.full; big.alt = b.dataset.name; caption.textContent = b.dataset.name + (group.length > 1 ? ' (' + (at + 1) + '/' + group.length + ')' : ''); };
  document.querySelectorAll('.thumb').forEach((b) => b.addEventListener('click', () => {
    group = [...b.closest('.thumbs').querySelectorAll('.thumb')]; show(group.indexOf(b)); viewer.showModal(); }));
  viewer.querySelector('.prev').addEventListener('click', (e) => { e.stopPropagation(); show(at - 1); });
  viewer.querySelector('.next').addEventListener('click', (e) => { e.stopPropagation(); show(at + 1); });
  viewer.querySelector('.close').addEventListener('click', () => viewer.close());
  viewer.addEventListener('click', (e) => { if (e.target === viewer) viewer.close(); });
  viewer.addEventListener('keydown', (e) => { if (e.key === 'ArrowLeft') show(at - 1); if (e.key === 'ArrowRight') show(at + 1); });
}
const refresh = Number(document.body.dataset.refresh);
if (refresh > 0) setInterval(() => { if (document.querySelector('dialog[open]')) return; document.querySelectorAll('details[id]').forEach((d) => { saved[d.id] = d.open; });
  try { sessionStorage.setItem(key, JSON.stringify(saved)); } catch (e) {} location.reload(); }, refresh * 1000);
})();
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
                          "default": text(item.get("default"), "decision default", False),
                          "images": images(item.get("images", []))})
    lang = raw.get("lang", "en")
    merge = raw.get("working_decisions", True)
    if not isinstance(merge, bool):
        raise ValueError("working_decisions must be true or false")
    return {"title": text(raw.get("title", "Work board"), "title"),
            "lang": lang if isinstance(lang, str) and lang in LABELS else "en",
            "tasks": tasks, "decisions": decisions, "working_decisions": merge}


def images(value):
    if not isinstance(value, list) or not all(isinstance(entry, str) and 0 < len(entry) <= 500 for entry in value):
        raise ValueError("decision images must be a list of paths")
    return list(value)


def pictures(item, root, folder):
    base = Path(root).resolve()
    found, seen = [], set()
    named = [quoted or plain for quoted, plain in PICTURE.findall(item.get("look", ""))]
    for given in item.get("images", []) + named:
        try:
            path = Path(given) if Path(given).is_absolute() else base / given
            path = path.resolve()
            path.relative_to(base)
            info = path.stat()
        except (OSError, ValueError, RuntimeError):
            continue
        if path in seen or not path.is_file() or info.st_size > PICTURE_BYTES or len(found) >= PICTURES:
            continue
        seen.add(path)
        name = hashlib.sha256(f"{path}\n{info.st_mtime_ns}\n{info.st_size}".encode("utf-8")).hexdigest()[:16]
        target = Path(folder) / "assets" / f"{name}{path.suffix.lower()}"
        try:
            if not target.is_file():
                copy_inside(path, base, target)
        except OSError:
            continue
        found.append({"src": f"assets/{target.name}", "name": str(path.relative_to(base))})
    return found


def copy_inside(path, base, target):
    handle = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(handle)
        now = Path(os.path.realpath(path))
        now.relative_to(base)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > PICTURE_BYTES or \
                (opened.st_dev, opened.st_ino) != (now.stat().st_dev, now.stat().st_ino):
            raise OSError("the picture changed while it was read")
        target.parent.mkdir(parents=True, exist_ok=True)
        spare = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        with os.fdopen(os.dup(handle), "rb") as source, open(spare, "wb") as sink:
            shutil.copyfileobj(source, sink, 1 << 20)
        spare.replace(target)
    except ValueError as error:
        raise OSError("the picture left the project") from error
    finally:
        os.close(handle)


def working_decisions(root):
    try:
        body = (Path(root) / "WORKING.md").read_text(encoding="utf-8")
    except OSError:
        return []
    section = WAITING.search(body)
    if not section:
        return []
    asks, fence = [], None
    for line in section.group(1).splitlines():
        mark = re.match(r"\s*(`{3,}|~{3,})", line)
        if fence is None and mark:
            fence = mark.group(1)
            continue
        if fence is not None:
            if mark and mark.group(1)[0] == fence[0] and len(mark.group(1)) >= len(fence):
                fence = None
            continue
        if line.startswith("- "):
            asks.append(line[2:].strip())
        elif asks and line[:1].isspace() and line.strip():
            asks[-1] = f"{asks[-1]} {line.strip()}"
    return [{"ask": ask, "look": "", "default": "", "images": []} for ask in asks
            if ask and ask.strip("().").lower() != "none"]


def counts(board):
    result = {status: 0 for status in STATUSES}
    for task in board["tasks"]:
        result[task["status"]] += 1
    total = len(board["tasks"])
    return result, total, 100 * result["done"] // total


def page(title, body, refresh, lang="en"):
    return (f"<!doctype html><html lang=\"{lang}\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{html.escape(title)}</title><style>{STYLE}</style></head>"
            f"<body data-refresh=\"{int(refresh)}\"><main>{body}</main><script>{SCRIPT}</script></body></html>")


def fill(status):
    return f"var(--{status})"


def bar(tally, total, percent, words):
    parts = "".join(f"<span style=\"flex:{tally[status]};background:{fill(status)}\" "
                    f"title=\"{html.escape(words[status])} {tally[status]}\"></span>"
                    for status in BAR_ORDER if tally[status])
    label = ", ".join(f"{words[status]} {tally[status]}" for status in BAR_ORDER if tally[status])
    return (f"<div class=\"bar\" role=\"progressbar\" aria-valuemin=\"0\" aria-valuemax=\"100\" "
            f"aria-valuenow=\"{percent}\" aria-label=\"{html.escape(label)}\">{parts}</div>")


def legend(tally, words):
    return "<div class=\"legend\">" + "".join(
        f"<span><i style=\"background:{fill(status)}\"></i>{MARKS[status]} {html.escape(words[status])} "
        f"{tally[status]}</span>" for status in BAR_ORDER if tally[status]) + "</div>"


def fresh(at, words):
    return (f"<span class=\"chip\" data-at=\"{int(at)}\" data-stale=\"{STALE_HOURS * 3600000}\" "
            f"data-label=\"{html.escape(words['updated'])}\">{html.escape(words['updated'])}</span>")


def signals(decisions, blocked, words, link=""):
    found = []
    if decisions:
        found.append(f"<a class=\"chip warn\" href=\"{link}#decisions\">{html.escape(words['need'])} {decisions}</a>")
    if blocked:
        found.append(f"<span class=\"chip bad\">{MARKS['blocked']} {html.escape(words['blocked'])} {blocked}</span>")
    return found


def ready(task, states):
    return all(states.get(name) == "done" for name in task["after"])


def recent(root):
    folder = Path(root) / ".harness" / "records"
    found = []
    try:
        files = sorted(folder.glob("*.md"), key=lambda path: (path.name[:10], path.stat().st_mtime), reverse=True)[:RECORDS]
    except OSError:
        return found
    for path in files:
        try:
            head = re.search(r'^title:[ \t]*"?(.*?)"?[ \t]*$', path.read_text(encoding="utf-8")[:4000], re.M)
        except (OSError, UnicodeError):
            continue
        found.append((path.name[:10], head.group(1) if head and head.group(1) else path.stem))
    return found


def focus(board):
    states = {task["id"]: task["status"] for task in board["tasks"]}
    doing = [task for task in board["tasks"] if task["status"] == "doing"]
    upcoming = [task for task in board["tasks"] if task["status"] == "todo" and ready(task, states)]
    waiting = [task for task in board["tasks"] if task["status"] == "todo" and not ready(task, states)]
    return states, doing, upcoming, waiting


def render(board, root, stamp, refresh=5, at=0):
    words = LABELS[board["lang"]]
    esc = html.escape
    tally, total, percent = counts(board)
    states, doing, upcoming, waiting = focus(board)

    def line(task, note=""):
        return (f"<li><span class=\"id\">{esc(task['id'])}</span>{esc(task['title'])}"
                f"<span class=\"owner\">{esc(task['owner'])}</span>{note}</li>")

    def held(task):
        before = ", ".join(name for name in task["after"] if states.get(name) != "done")
        return line(task, f"<div class=\"sub\">{esc(before)} {esc(words['after'])}</div>")

    marks = signals(len(board["decisions"]), tally["blocked"], words) or [
        f"<span class=\"chip good\">{MARKS['done']} {esc(words['ok'])}</span>"]
    head = (f"<header><h1>{esc(board['title'])}</h1>{''.join(marks)}<span class=\"spacer\"></span>"
            f"{fresh(at, words)}<a class=\"meta\" href=\"index.html\">{esc(words['all'])}</a>"
            f"<div class=\"meta wide\">{esc(str(root))} · {esc(stamp)}</div></header>")
    now = (f"<div class=\"card\"><h2>{esc(words['now'])}</h2><ul>"
           + ("".join(line(task) for task in doing) or f"<li class=\"quiet\">{esc(words['idle'])}</li>") + "</ul></div>")
    upcoming_html = "".join(line(task) for task in upcoming[:3]) or "".join(held(task) for task in waiting[:2])
    nxt = (f"<div class=\"card\"><h2>{esc(words['next'])}</h2><ul>"
           + (upcoming_html or f"<li class=\"quiet\">{esc(words['clear'])}</li>") + "</ul></div>")
    progress = (f"<div class=\"card\"><h2>{esc(words['progress'])}</h2><div class=\"big\">{percent}%</div>"
                f"<div class=\"sub\">{tally['done']} {esc(words['of'])} {total} {esc(words['tasks'])}</div>"
                f"{bar(tally, total, percent, words)}{legend(tally, words)}</div>")
    body = head + f"<div class=\"top\">{now}{nxt}{progress}</div>"

    asks = []
    for number, item in enumerate(board["decisions"], 1):
        extra = (f"<span class=\"chip\">{esc(words['default'])}: {esc(item['default'])}</span>" if item["default"] else "")
        extra += f"<span>{esc(words['look'])}: {esc(item['look'])}</span>" if item["look"] else ""
        thumbs = "".join(
            f"<button class=\"thumb\" type=\"button\" data-full=\"{esc(pic['src'])}\" data-name=\"{esc(pic['name'])}\" "
            f"aria-label=\"{esc(words['picture'])}: {esc(pic['name'])}\"><img src=\"{esc(pic['src'])}\" alt=\"\" "
            f"loading=\"lazy\"></button>" for pic in item.get("pictures", []))
        thumbs = f"<div class=\"thumbs\">{thumbs}</div>" if thumbs else ""
        asks.append(f"<div class=\"decision\"><span class=\"n\">{number}</span><b>{esc(item['ask'])}</b>"
                    f"<div class=\"more\">{extra}</div>{thumbs}</div>")
    count = f"<span class=\"chip warn\">{len(asks)}</span>" if asks else ""
    if any(item.get("pictures") for item in board["decisions"]):
        body += (f"<dialog class=\"viewer\" aria-label=\"{esc(words['picture'])}\"><img alt=\"\"><div class=\"bar2\">"
                 f"<button class=\"prev\" type=\"button\">{esc(words['prev'])}</button><span class=\"name\"></span>"
                 f"<button class=\"next\" type=\"button\">{esc(words['nextpic'])}</button>"
                 f"<button class=\"close\" type=\"button\">{esc(words['close'])}</button></div></dialog>")
    body += (f"<section id=\"decisions\"><h2>{esc(words['decisions'])} {count}</h2>"
             + (f"<div class=\"decisions\">{''.join(asks)}</div>" if asks else f"<p class=\"quiet\">{esc(words['none'])}</p>")
             + "</section>")

    owners = sorted({task["owner"] for task in board["tasks"] if task["owner"] and task["status"] != "done"})
    filters = ""
    if len(owners) > 1:
        filters = (f"<div class=\"filters\"><button data-owner=\"*\" aria-pressed=\"true\">{esc(words['everyone'])}</button>"
                   + "".join(f"<button data-owner=\"{esc(name)}\" aria-pressed=\"false\">{esc(name)}</button>"
                             for name in owners) + "</div>")

    def row(number, task):
        status = task["status"]
        before = [name for name in task["after"] if states.get(name) != "done"]
        after = (f" <span class=\"after\">{esc(', '.join(before))} {esc(words['after'])}</span>"
                 if before and status != "done" else "")
        note = (f"<details id=\"note-{esc(task['id'])}\"><summary>{esc(task['note'])}</summary>{esc(task['note'])}</details>"
                if task["note"] else "")
        return (f"<div class=\"row {status}\" data-owner=\"{esc(task['owner'])}\"><span class=\"mark {status}\" "
                f"aria-label=\"{esc(words[status])}\">{MARKS[status]}</span><span class=\"id\">{esc(task['id'])}</span>"
                f"<span class=\"title\">{esc(task['title'])}{after}</span><span class=\"owner\">{esc(task['owner'])}</span>"
                f"{note}</div>")

    numbered = list(enumerate(board["tasks"]))
    groups = ""
    for status in ("doing", "blocked", "parked", "todo"):
        rows = [row(number, task) for number, task in numbered if task["status"] == status]
        if rows:
            groups += (f"<div class=\"group\"><h2><span class=\"mark {status}\">{MARKS[status]}</span>"
                       f"{esc(words[status])} <span class=\"chip\">{len(rows)}</span></h2>"
                       f"<div class=\"rows\">{''.join(rows)}</div></div>")
    finished = [row(number, task) for number, task in numbered if task["status"] == "done"]
    if finished:
        groups += (f"<details class=\"fold\" id=\"done\"><summary>{MARKS['done']} {esc(words['done'])} "
                   f"{len(finished)}</summary><div class=\"rows\">{''.join(finished)}</div></details>")
    body += f"<section><h2>{esc(words['list'])}</h2>{filters}{groups}</section>"

    written = recent(root)
    if written:
        body += (f"<section><h2>{esc(words['records'])}</h2><ul class=\"records\">"
                 + "".join(f"<li><span class=\"id\">{esc(day)}</span>{esc(title)}</li>" for day, title in written)
                 + "</ul></section>")
    return page(board["title"], body, refresh, board["lang"])


def overview(entries, lang, refresh=5):
    words = LABELS[lang]
    esc = html.escape

    def order(entry):
        return (-(entry["decisions"] + entry.get("blocked", 0)), -entry["doing"], entry["title"].casefold())

    rows = []
    for entry in sorted(entries, key=order):
        tally = {status: 0 for status in STATUSES}
        tally.update({key: value for key, value in entry.get("tally", {}).items() if key in tally})
        if not any(tally.values()):
            tally.update({"done": entry["done"], "doing": entry["doing"], "todo": entry["total"] - entry["done"] - entry["doing"]})
        marks = signals(entry["decisions"], entry.get("blocked", 0), words, esc(entry["page"])) or [
            f"<span class=\"chip good\">{MARKS['done']} {esc(words['on'])}</span>"]
        rows.append(f"<tr><td><a href=\"{esc(entry['page'])}\"><b>{esc(entry['title'])}</b></a>"
                    f"<div class=\"meta\">{esc(entry['root'])}</div></td><td>{''.join(marks)}</td>"
                    f"<td>{entry['percent']}% · {entry['done']} {esc(words['of'])} {entry['total']}"
                    f"{bar(tally, entry['total'], entry['percent'], words)}</td>"
                    f"<td class=\"opt sub\">{esc(entry.get('focus', ''))}</td>"
                    f"<td>{fresh(entry.get('at', 0), words)}</td></tr>")
    if not rows:
        table = f"<p class=\"quiet\">{esc(words['empty'])}</p>"
    else:
        head = "".join(f"<th{cls}>{esc(words[key])}</th>" for key, cls in (
            ("project", ""), ("signal", ""), ("progress", ""), ("focus", " class=\"opt\""), ("updated", "")))
        table = (f"<div class=\"card\" style=\"padding:0\"><table><thead><tr>{head}</tr></thead>"
                 f"<tbody>{''.join(rows)}</tbody></table></div>")
    body = (f"<header><h1>{esc(words['all'])}</h1><span class=\"spacer\"></span>"
            f"<span class=\"meta\">{esc(words['order'])}</span></header>{table}")
    return page(words["all"], body, refresh, lang)


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


def summary(board, root, board_path, name, stamp, at):
    tally, total, percent = counts(board)
    _, doing, upcoming, _ = focus(board)
    now = (f"{MARKS['doing']} {doing[0]['title']}" if doing else
           f"{LABELS[board['lang']]['next']}: {upcoming[0]['title']}" if upcoming else "")
    return {"title": board["title"], "root": str(root), "board": str(board_path), "page": f"{name}.html",
            "percent": percent, "done": tally["done"], "total": total, "doing": tally["doing"],
            "decisions": len(board["decisions"]), "blocked": tally["blocked"], "tally": tally, "focus": now,
            "stamp": stamp, "at": at, "lang": board["lang"]}


def draw(board_path, root, folder):
    board = load(board_path)
    if board["working_decisions"]:
        board["decisions"] = board["decisions"] + working_decisions(root)
    for item in board["decisions"]:
        item["pictures"] = pictures(item, root, folder)
    moment = board_path.stat().st_mtime
    stamp = datetime.fromtimestamp(moment).strftime("%Y-%m-%d %H:%M")
    return board, stamp, int(moment * 1000)


def publish(board_path, root=None, out=None):
    board_path = Path(os.path.abspath(board_path))
    root = Path(os.path.abspath(root)) if root else (
        board_path.parent.parent if board_path.parent.name == BOARD.parent.name else board_path.parent)
    folder, name = (Path(out).parent, None) if out else (home(), slug(root))
    board, stamp, at = draw(board_path, root, folder)
    content = render(board, root, stamp, at=at)
    if out:
        write(Path(out), content)
        return Path(out)
    write(folder / f"{name}.html", content)
    write(folder / f"{name}.json", json.dumps(summary(board, root, board_path, name, stamp, at), ensure_ascii=False))
    entries = []
    for listed in sorted(folder.glob("*.json")):
        try:
            entry = json.loads(listed.read_text(encoding="utf-8"))
            texts = all(isinstance(entry[key], str) for key in ("title", "root", "board", "page", "stamp"))
            numbers = all(type(entry[key]) is int for key in ("percent", "done", "total", "doing", "decisions"))
            if not (texts and numbers and PAGE.fullmatch(entry["page"]) and Path(entry["board"]).is_file()):
                continue
            other = Path(entry["board"])
            stale = other.stat().st_mtime > listed.stat().st_mtime or "tally" not in entry or "at" not in entry
            if listed.stem != name and stale and slug(entry["root"]) == listed.stem:
                again, again_stamp, again_at = draw(other, Path(entry["root"]), folder)
                write(folder / f"{listed.stem}.html", render(again, Path(entry["root"]), again_stamp, at=again_at))
                entry = summary(again, Path(entry["root"]), other, listed.stem, again_stamp, again_at)
                write(listed, json.dumps(entry, ensure_ascii=False))
            entry.setdefault("blocked", 0)
            entry.setdefault("at", 0)
            entry.setdefault("focus", "")
            tally = entry.get("tally", {})
            if not (type(entry["blocked"]) is int and type(entry["at"]) is int and isinstance(entry["focus"], str)
                    and isinstance(tally, dict) and all(type(value) is int and value >= 0 for value in tally.values())):
                continue
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
