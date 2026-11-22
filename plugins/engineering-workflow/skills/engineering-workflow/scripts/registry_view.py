import argparse
import collections
import json
import os
import re
import socket
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import registry
import registry_hook as hook
import registry_judge_jev as jev
import registry_neo4j as graph

HIDDEN = ["commit", "asset", "source", "license"]
PAGE_NAME = "registry.html"
LOG_ROWS = 200
WORDS = {
    "en": {
        "title": "Registry", "graph": "Graph", "shape": "Structure", "judge": "Judge", "models": "Models", "connect": "Connection",
        "search": "Find a node (name or id)", "hint": "Click a point to inspect it. Drag to move, wheel to zoom.",
        "reset": "Reset view", "links": "links", "hiddenToo": "including hidden types",
        "relHint": "click a relation to light it up and name its ends", "focus": "Neighbours only", "all": "Everything",
        "close": "Close", "more": "more", "cardsHint": "One card per node type; lines are the links between types with their counts. Cards can be dragged.",
        "prompts": "Logged prompts", "byJudge": "Outside / local", "latency": "Judge time p50 · p95",
        "attach": "Attached something (outside · local)", "whatJudge": "What the judge does",
        "s1": "Prompt", "s1d": "The hook receives the prompt. The log keeps no prompt text.",
        "s2": "Candidates", "s2d": "The registry finds skill, record and rule candidates by word score.",
        "s3": "Outside judge", "s3d": "The outside model picks the related ones (threshold {t}, limit {l}s). If it fails or is late, the local judge decides (score at least {ms}, at least {mr}% of the best).",
        "s4": "Hint", "s4d": "Up to {n} picks are attached to the prompt. The judge does not choose models.",
        "perDay": "Decisions per day", "timing": "Timing", "count": "Count", "rate": "Attached",
        "log": "Decisions", "every": "All", "outside": "Outside", "local": "Local", "failed": "Local after failure",
        "time": "Time", "who": "Judge", "secs": "Hook", "jsecs": "Judge", "decision": "Decision", "picked": "Attached",
        "pickedN": "attached {n} of {o}", "none": "{o} candidates, nothing fit", "empty": "no candidates",
        "how": "How a model is chosen", "m1": "Look at the role", "m1d": "A clear local edit, integration or debugging, or design, a new system, saved data and high-risk review.",
        "m2": "Follow the shared rule", "m2d": "Light work gets a light model, integration and debugging a standard one, the rest the strongest.",
        "m3": "Name it when work is handed out", "m3d": "A subagent's model, a board task's model and effort for run_queue.py. A session cannot change its own model and tells the user when it should.",
        "m4": "Record what ran", "m4d": "Work records name the model that ran (RAN_ON) and the one that reviewed (REVIEWED_BY); the registry adds them up.",
        "roles": "Roles in the rule", "role": "Role", "model": "Model", "r1": "Clear local edits", "r1m": "Light model",
        "r2": "Integration, debugging", "r2m": "Standard model", "r3": "Design, new systems, critical behaviour, saved data or schemas, high-risk review", "r3m": "Strongest model",
        "usage": "Use per model", "ran": "Records", "rev": "Reviews", "prefers": "Models skills ask for (PREFERS)",
        "noPrefers": "None yet. A skill names model, effort and fallback in its metadata to appear here.",
        "first": "first", "fallback": "fallback", "ruleText": "Rule text", "noRule": "No \"## Model selection\" section was found in the user's rules file.",
        "server": "Graph server", "state": "State", "up": "answering", "down": "not answering", "url": "HTTP address", "bolt": "Bolt address",
        "user": "User", "secret": "Password", "secretWhere": "not shown here; it is read from {where}", "nodesLinks": "Nodes · links · files",
        "version": "Version", "browser": "Neo4j Browser on this machine", "remote": "From another machine",
        "remoteText": "The server listens on this machine only. Open a tunnel over SSH, then use the addresses as if they were local:",
        "drawn": "Drawn {at}. The page is redrawn by registry_view.py; it reloads itself every minute.",
        "boards": "All boards",
    },
    "ko": {
        "title": "등록부", "graph": "그래프", "shape": "구성", "judge": "판단", "models": "모델", "connect": "연결",
        "search": "노드 찾기 (이름 또는 id)", "hint": "점을 누르면 자세히 보입니다. 끌어서 이동, 휠로 확대합니다.",
        "reset": "처음 보기", "links": "연결", "hiddenToo": "숨긴 종류 포함",
        "relHint": "관계를 누르면 그 관계만 밝혀지고 이름이 모두 보입니다", "focus": "이웃만 보기", "all": "전체 보기",
        "close": "닫기", "more": "개 더", "cardsHint": "점 종류마다 카드 하나. 선은 종류 사이의 연결과 개수입니다. 카드를 끌어 옮길 수 있습니다.",
        "prompts": "기록된 프롬프트", "byJudge": "외부 / 로컬 판단", "latency": "판단 시간 p50 · p95",
        "attach": "후보를 붙인 비율 (외부 · 로컬)", "whatJudge": "판단 단계가 하는 일",
        "s1": "프롬프트 입력", "s1d": "훅이 프롬프트를 받습니다. 기록에는 프롬프트 글을 남기지 않습니다.",
        "s2": "후보 찾기", "s2d": "등록부에서 단어 점수로 스킬·기록·규칙 후보를 찾습니다.",
        "s3": "외부 판단", "s3d": "외부 모델이 관련 있는 후보를 고릅니다(기준 {t}, 제한 {l}초). 답이 없거나 늦으면 로컬 판단(점수 {ms} 이상, 최고의 {mr}% 이상)이 대신합니다.",
        "s4": "힌트 붙이기", "s4d": "골라진 것을 {n}개까지 프롬프트에 붙입니다. 판단 단계는 모델을 고르지 않습니다.",
        "perDay": "날짜별 판단", "timing": "시간", "count": "건수", "rate": "붙인 비율",
        "log": "판단 기록", "every": "전체", "outside": "외부", "local": "로컬", "failed": "실패 후 로컬",
        "time": "시각", "who": "판단", "secs": "훅", "jsecs": "판단", "decision": "결정", "picked": "붙인 것",
        "pickedN": "후보 {o}개 중 {n}개를 붙임", "none": "후보 {o}개, 붙일 만한 것 없음", "empty": "후보 없음",
        "how": "모델은 이렇게 정해집니다", "m1": "작업의 역할을 본다", "m1d": "가벼운 편집인지, 통합·디버깅인지, 설계·새 시스템·저장 데이터·고위험 검토인지.",
        "m2": "공통 규칙에 맞춘다", "m2d": "가벼운 일은 가벼운 모델, 통합·디버깅은 표준 모델, 나머지는 가장 강한 모델.",
        "m3": "일을 나눌 때 이름으로 적는다", "m3d": "서브에이전트의 모델, run_queue.py 작업의 model·effort. 세션은 자기 모델을 바꿀 수 없어 필요하면 사용자에게 알립니다.",
        "m4": "실제 쓴 모델을 남긴다", "m4d": "작업 기록에 실행 모델(RAN_ON)과 검토 모델(REVIEWED_BY)을 적고 등록부가 모아 봅니다.",
        "roles": "역할별 기준 (규칙에서)", "role": "역할", "model": "모델", "r1": "뚜렷한 작은 편집", "r1m": "가벼운 모델",
        "r2": "통합, 디버깅", "r2m": "표준 모델", "r3": "설계, 새 시스템, 중요한 동작, 저장 데이터·스키마 변경, 고위험 검토", "r3m": "가장 강한 모델",
        "usage": "모델별 사용", "ran": "작업 기록", "rev": "검토", "prefers": "스킬이 원하는 모델 (PREFERS)",
        "noPrefers": "아직 없습니다. 스킬 머리말 metadata에 model, effort, fallback을 적으면 여기에 나옵니다.",
        "first": "기본", "fallback": "대체", "ruleText": "규칙 원문", "noRule": "사용자 규칙 파일에서 \"## Model selection\" 절을 찾지 못했습니다.",
        "server": "그래프 서버", "state": "상태", "up": "응답함", "down": "응답 없음", "url": "HTTP 주소", "bolt": "Bolt 주소",
        "user": "사용자", "secret": "비밀번호", "secretWhere": "여기에 보이지 않습니다. {where}에서 읽습니다", "nodesLinks": "점 · 선 · 파일",
        "version": "버전", "browser": "이 기기의 Neo4j Browser", "remote": "다른 기기에서",
        "remoteText": "서버는 이 기기에서만 듣습니다. SSH로 터널을 연 뒤, 아래 주소를 이 기기에서처럼 씁니다:",
        "drawn": "{at}에 그렸습니다. registry_view.py가 다시 그리고, 페이지는 1분마다 다시 읽습니다.",
        "boards": "전체 보드",
    },
}
TYPES = {
    "en": {},
    "ko": {"app": "앱", "skill": "스킬", "rule": "규칙", "plugin": "플러그인", "tool": "도구", "model": "모델", "task": "작업",
           "decision": "결정", "record": "작업 기록", "commit": "커밋", "asset": "에셋", "source": "출처", "license": "라이선스",
           "session": "세션", "machine": "기기", "term": "용어", "checkout": "작업 사본"},
}


def export(store):
    n = store.node
    nodes = store.run(f"MATCH (x:{n}) OPTIONAL MATCH (x)-[r]-() RETURN x.id AS id, x.type AS type, "
                      "coalesce(x.name, x.id) AS name, count(r) AS degree")
    for node in nodes:
        node["name"] = str(node["name"])[:120]
    return {
        "nodes": nodes,
        "links": store.run(f"MATCH (a:{n})-[r]->(b:{n}) RETURN a.id AS s, b.id AS t, type(r) AS k"),
        "shape": store.run(f"MATCH (a:{n})-[r]->(b:{n}) RETURN a.type AS f, type(r) AS k, b.type AS t, count(*) AS c"),
        "ran": store.run(f"MATCH (:{n}:Record)-[:RAN_ON]->(m:{n}) RETURN m.name AS model, count(*) AS c ORDER BY c DESC"),
        "reviewed": store.run(f"MATCH (:{n}:Commit)-[:REVIEWED_BY]->(m:{n}) RETURN m.name AS model, count(*) AS c "
                              "ORDER BY c DESC"),
        "prefers": store.run(f"MATCH (s:{n}:Skill)-[p:PREFERS]->(m:{n}) RETURN s.name AS skill, m.name AS model, "
                             "p.order AS rank, p.effort AS effort ORDER BY skill, rank"),
    }


def decisions(folder):
    path = Path(folder).expanduser() / "hook.jsonl" if folder else None
    rows = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path and path.is_file() else []
    except (OSError, UnicodeError):
        lines = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        chosen = item.get("chosen") if isinstance(item.get("chosen"), list) else []
        rows.append({"at": str(item.get("at", ""))[:19], "judge": str(item.get("judge", "local"))[:40],
                     "seconds": number(item.get("seconds")), "judge_seconds": number(item.get("judge_seconds")),
                     "offered": item.get("offered") if isinstance(item.get("offered"), int) else 0,
                     "chosen": [str(entry)[:200] for entry in chosen[:6]]})
    days = collections.defaultdict(lambda: {"outside": 0, "local": 0})
    for row in rows:
        days[row["at"][:10]]["outside" if row["judge"] == "outside" else "local"] += 1
    return {"rows": rows[::-1][:LOG_ROWS], "days": sorted(days.items())[-30:], "total": len(rows)}


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def rule_text(config):
    user = config.get("user")
    try:
        text = (Path(user) / "CLAUDE.md").read_text(encoding="utf-8") if user else ""
    except (OSError, UnicodeError):
        return ""
    found = re.search(r"^## Model selection[ \t]*\n(.*?)(?=^#{1,2}[ \t]|\Z)", text, re.S | re.M)
    return found.group(1).strip() if found else ""


def server(store):
    info = {"url": os.environ.get("HARNESS_NEO4J_URL", "http://127.0.0.1:7474").rstrip("/"),
            "user": os.environ.get("HARNESS_NEO4J_USER", "neo4j"),
            "password_from": ("HARNESS_NEO4J_PASSWORD" if os.environ.get("HARNESS_NEO4J_PASSWORD")
                              else "keychain item harness-neo4j"),
            "host": socket.gethostname(), "up": False}
    try:
        rows = store.run("CALL dbms.components() YIELD name, versions, edition RETURN name, versions[0] AS version, edition")
        info["version"] = " ".join(str(rows[0][key]) for key in ("name", "version", "edition")) if rows else ""
        info.update(graph.counts(store))
        info["up"] = True
    except (graph.StoreError, OSError, ValueError, KeyError, IndexError):
        pass
    return info


def build(config_path=None, log=None, lang="en", space="N"):
    config = json.loads(registry.config_path(config_path).read_text(encoding="utf-8"))
    lang = lang if lang in WORDS else "en"
    store = graph.connect(space)
    connection = server(store)
    data = export(store) if connection["up"] else {"nodes": [], "links": [], "shape": [], "ran": [], "reviewed": [],
                                                   "prefers": []}
    data.update({"hidden": HIDDEN, "judge": decisions(log or os.environ.get("HARNESS_REGISTRY_LOG")),
                 "rule": rule_text(config), "server": connection, "types": TYPES[lang],
                 "limits": {"t": jev.THRESHOLD, "l": hook.JUDGE_SECONDS, "ms": 5, "mr": 70, "n": 3},
                 "at": datetime.now().strftime("%Y-%m-%d %H:%M")})
    text, words = script_json(data), script_json(WORDS[lang])
    return PAGE.replace("__LANG__", lang).replace("__WORDS__", words).replace("__DATA__", text)


def script_json(value):
    return (json.dumps(value, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c")
            .replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def write(page, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    spare = folder / f".{PAGE_NAME}.{os.getpid()}.tmp"
    spare.write_text(page, encoding="utf-8")
    spare.replace(folder / PAGE_NAME)
    return folder / PAGE_NAME


def main(argv=None):
    import board
    parser = argparse.ArgumentParser(description="Draw the registry as one local page: the graph, its node types, the "
                                                 "prompt hook's judge decisions, how models are chosen and used, and "
                                                 "how to reach the graph server. Never shows a password.")
    parser.add_argument("--config", help="registry config (default as for registry.py)")
    parser.add_argument("--log", help="the hook's log folder (default: HARNESS_REGISTRY_LOG)")
    parser.add_argument("--lang", default=os.environ.get("HARNESS_REGISTRY_LANG", "en"), choices=sorted(WORDS))
    parser.add_argument("--out", help="folder for registry.html (default: the board pages folder)")
    args = parser.parse_args(argv)
    try:
        path = write(build(args.config, args.log, args.lang), args.out or board.home())
    except (OSError, ValueError, KeyError, TypeError, graph.StoreError) as error:
        print(f"INVALID: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(path)
    return 0


PAGE = r"""<!doctype html><html lang="__LANG__"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Registry</title><style>
:root{--page:#0b0f14;--panel:#121820;--ink:#e8ecef;--ink2:#a9b3bb;--muted:#6f7a83;--line:#1f2a33;--ring:rgba(255,255,255,.09);--glow:#7fd1c1}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1200px 700px at 50% -10%,#16222c,var(--page));color:var(--ink);
font:14px/1.5 system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;min-height:100vh}
nav{display:flex;justify-content:center;gap:24px;padding:22px 12px 0;flex-wrap:wrap}
nav button{font:inherit;font-size:15px;background:none;border:0;color:var(--muted);padding:6px 2px 10px;cursor:pointer;border-bottom:2px solid transparent}
nav button[aria-selected=true]{color:var(--ink);border-color:var(--ink)}nav a{color:var(--muted);font-size:13px;align-self:center;margin-left:12px}
main{max-width:1180px;margin:0 auto;padding:18px 20px 40px}.tab{display:none}.tab.on{display:block}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}
input[type=search]{font:inherit;background:var(--panel);border:1px solid var(--ring);color:var(--ink);border-radius:10px;padding:8px 12px;width:320px}
.chip{font:inherit;font-size:12px;border:1px solid var(--ring);background:var(--panel);color:var(--ink2);border-radius:999px;padding:3px 10px;cursor:pointer}
.chip[aria-pressed=false]{opacity:.45}.hint{color:var(--muted);font-size:12px;margin-left:auto}
.stage{position:relative;background:#0a0e12;border:1px solid var(--ring);border-radius:16px;overflow:hidden;height:640px}
canvas{display:block;width:100%;height:100%;cursor:grab}
.zoom{position:absolute;top:12px;right:12px;display:flex;gap:6px}.zoom button{font:inherit;background:#151c23;color:var(--ink);border:1px solid var(--ring);border-radius:8px;padding:4px 10px;cursor:pointer}
.side{position:absolute;right:12px;top:58px;bottom:12px;width:340px;background:rgba(18,24,32,.94);border:1px solid var(--ring);border-radius:12px;padding:12px 14px;display:none;overflow:auto}
.side h3{margin:0 0 4px;font-size:14px}.side .t{color:var(--muted);font-size:12px}.side li{font-size:12px;color:var(--ink2)}.side ul{padding-left:16px;margin:6px 0}
.side .grp button{font:inherit;font-size:12px;width:100%;display:flex;justify-content:space-between;background:#151c23;border:1px solid var(--ring);color:var(--ink2);border-radius:8px;padding:5px 8px;cursor:pointer;margin-top:4px}
.side .grp button[aria-pressed=true]{border-color:var(--glow);color:var(--ink)}.side .acts{display:flex;gap:6px;margin-top:10px}
.side .acts button{font:inherit;font-size:12px;background:#151c23;border:1px solid var(--ring);color:var(--ink);border-radius:8px;padding:4px 10px;cursor:pointer}
.cards{position:relative;height:800px;background:#0a0e12;border:1px solid var(--ring);border-radius:16px;overflow:hidden;
background-image:linear-gradient(var(--line) 1px,transparent 1px),linear-gradient(90deg,var(--line) 1px,transparent 1px);background-size:40px 40px}
.card{position:absolute;width:160px;transform:translate(-50%,-50%);background:rgba(20,27,35,.95);border:1px solid var(--ring);border-radius:12px;padding:10px 12px;cursor:move;box-shadow:0 8px 24px rgba(0,0,0,.35)}
.card b{display:flex;align-items:center;gap:6px;font-size:13px}.card b i{width:8px;height:8px;border-radius:2px;display:inline-block;transform:rotate(45deg)}
.card .n{font-size:22px;font-weight:650;margin:2px 0}.card .ex{font-size:11px;color:var(--muted);line-height:1.4;max-height:44px;overflow:hidden}
svg.wires{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.tile{background:var(--panel);border:1px solid var(--ring);border-radius:12px;padding:14px}.tile .k{color:var(--ink2);font-size:12px}.tile .v{font-size:24px;font-weight:650;font-variant-numeric:tabular-nums}
.box{background:var(--panel);border:1px solid var(--ring);border-radius:12px;padding:14px 16px;margin-bottom:14px}
.box h2{font-size:13px;margin:0 0 10px;color:var(--ink2)}table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--muted);font-weight:600;font-size:12px;padding:6px 8px}td{padding:6px 8px;border-top:1px solid var(--line);vertical-align:top}
td.n,th.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}td.decision,th.decision{min-width:220px;white-space:normal;word-break:keep-all}td.mono.picked,th.picked{white-space:normal;word-break:break-all;min-width:240px}.scroll{overflow-x:auto}td.mono{white-space:nowrap}
.steps{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(4,1fr);gap:10px;counter-reset:s}
.steps li{counter-increment:s;background:#151c23;border:1px solid var(--ring);border-radius:10px;padding:10px 12px;min-width:0}
.steps li::before{content:counter(s);display:inline-grid;place-items:center;width:20px;height:20px;border-radius:50%;background:#1f2a33;color:var(--glow);font-size:12px;margin-right:8px}
.steps b{font-size:13px}.steps p{margin:6px 0 0;color:var(--muted);font-size:12px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}.two .box{margin:0}
.days{display:flex;align-items:flex-end;gap:6px;height:120px}.days div{display:flex;flex-direction:column-reverse;gap:2px;width:22px}.days span{display:block;border-radius:3px}
.legend{font-size:12px;color:var(--ink2);display:flex;gap:14px;margin-top:8px}.legend i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:5px}
.meter{height:8px;border-radius:4px;background:#1f2a33;overflow:hidden;min-width:80px}.meter i{display:block;height:100%;border-radius:4px}
.pill{display:inline-block;white-space:nowrap;font-size:11px;padding:1px 8px;border-radius:999px;background:#1f2a33;color:var(--ink2)}.pill.out{background:#173b35;color:#7fd1c1}
.filters{display:flex;gap:6px;margin-bottom:10px}.quote{white-space:pre-wrap;color:var(--ink2);font-size:13px;margin:0}
.mono{font:12px ui-monospace,Menlo,monospace;color:var(--ink2)}pre{background:#0a0e12;border:1px solid var(--ring);border-radius:8px;padding:10px;overflow:auto;font:12px ui-monospace,Menlo,monospace;color:var(--ink)}
.ok{color:#0ca30c}.bad{color:#f08a8a}.foot{color:var(--muted);font-size:12px;text-align:center;margin-top:18px}
@media (max-width:760px){.steps,.two,.grid{grid-template-columns:1fr}.side{width:auto;left:12px;top:auto;max-height:45%}input[type=search]{width:100%}}
</style></head><body>
<nav role="tablist"></nav><main>
<section class="tab on" id="graph"><div class="bar"><input type="search" id="q"><span id="types"></span><span class="hint" id="hint"></span></div>
<div class="stage"><canvas id="cv"></canvas><div class="zoom"><button id="zo">−</button><button id="zi">+</button><button id="zr"></button></div><div class="side" id="side"></div></div></section>
<section class="tab" id="shape"><div class="bar"><span class="hint" id="cardsHint" style="margin-left:0"></span></div><div class="cards" id="cards"><svg class="wires" id="wires"></svg></div></section>
<section class="tab" id="judge"></section><section class="tab" id="models"></section><section class="tab" id="connect"></section>
<p class="foot" id="foot"></p></main>
<script>
(() => {
const D = __DATA__, W = __WORDS__;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const fill = (s, o) => s.replace(/\{(\w+)\}/g, (_, k) => esc(o[k]));
const tabs = ['graph', 'shape', 'judge', 'models', 'connect'];
const nav = document.querySelector('nav');
const saved = (() => { try { return JSON.parse(sessionStorage.getItem('registry-view') || '{}'); } catch (e) { return {}; } })();
nav.innerHTML = tabs.map(t => `<button role="tab" data-tab="${t}" aria-selected="false">${esc(W[t === 'judge' ? 'judge' : t])}</button>`).join('') + `<a href="index.html">${esc(W.boards)}</a>`;
const open = t => { nav.querySelectorAll('button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === t)));
  document.querySelectorAll('.tab').forEach(s => s.classList.toggle('on', s.id === t)); saved.tab = t;
  try { sessionStorage.setItem('registry-view', JSON.stringify(saved)); } catch (e) {} if (t === 'shape') wires(); };
nav.querySelectorAll('button').forEach(b => b.onclick = () => open(b.dataset.tab));
document.getElementById('q').placeholder = W.search; document.getElementById('hint').textContent = W.hint;
document.getElementById('zr').textContent = W.reset; document.getElementById('cardsHint').textContent = W.cardsHint;
document.getElementById('foot').textContent = fill(W.drawn, {at: D.at});
const typeName = t => D.types[t] || t;
const HUES = ['#7fd1c1', '#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#9085e9', '#e66767', '#9aa5ad'];
const count = {}; D.nodes.forEach(n => { count[n.type] = (count[n.type] || 0) + 1; });
const order = Object.keys(count).sort((a, b) => count[b] - count[a]);
const hue = Object.fromEntries(order.map((t, i) => [t, HUES[Math.min(i, HUES.length - 1)]]));

const shown = new Set(order.filter(t => !D.hidden.includes(t)));
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
let Wd = 0, Ht = 0, view = {x: 0, y: 0, k: .55}, nodes = [], links = [], byId = {}, picked = null, query = '', relation = null, focus = false, heat = 1, drag = null, pan = null, moved = false;
function chips() { document.getElementById('types').innerHTML = order.map(t => `<button class="chip" data-t="${esc(t)}" aria-pressed="${shown.has(t)}"><span style="color:${hue[t]}">●</span> ${esc(typeName(t))} ${count[t]}</button>`).join(' ');
  document.querySelectorAll('#types .chip').forEach(b => b.onclick = () => { const t = b.dataset.t; shown.has(t) ? shown.delete(t) : shown.add(t); picked = null; side(); build(); chips(); }); }
function build() {
  const old = byId; byId = {};
  nodes = D.nodes.filter(n => shown.has(n.type)).map(n => { const o = old[n.id]; const m = Object.assign({}, n, o ? {x: o.x, y: o.y} : {x: (Math.random() - .5) * 900, y: (Math.random() - .5) * 600}, {vx: 0, vy: 0}); byId[n.id] = m; return m; });
  links = D.links.filter(l => byId[l.s] && byId[l.t]).map(l => ({a: byId[l.s], b: byId[l.t], k: l.k}));
  const deg = {}; links.forEach(l => { deg[l.a.id] = (deg[l.a.id] || 0) + 1; deg[l.b.id] = (deg[l.b.id] || 0) + 1; });
  nodes.forEach(n => { n.seen = deg[n.id] || 0; n.r = 2.5 + Math.min(11, Math.sqrt(n.seen) * 1.3); }); heat = 1; }
function step() {
  const cell = 160, grid = new Map();
  for (const n of nodes) { const key = Math.floor(n.x / cell) + ',' + Math.floor(n.y / cell); (grid.get(key) || grid.set(key, []).get(key)).push(n); }
  for (const n of nodes) { const cx = Math.floor(n.x / cell), cy = Math.floor(n.y / cell);
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (const m of grid.get((cx + dx) + ',' + (cy + dy)) || []) {
      if (m === n) continue; const x = n.x - m.x, y = n.y - m.y, d2 = x * x + y * y + 64; if (d2 > cell * cell) continue;
      const f = 2600 / d2; n.vx += x * f * .02; n.vy += y * f * .02; } n.vx -= n.x * .0006; n.vy -= n.y * .0006; }
  for (const l of links) { const x = l.b.x - l.a.x, y = l.b.y - l.a.y, d = Math.hypot(x, y) + .01, f = (d - 90) * .003;
    l.a.vx += x / d * f * 8; l.a.vy += y / d * f * 8; l.b.vx -= x / d * f * 8; l.b.vy -= y / d * f * 8; }
  for (const n of nodes) { if (n === drag) continue; n.vx = Math.max(-30, Math.min(30, n.vx)); n.vy = Math.max(-30, Math.min(30, n.vy)); n.x += n.vx * heat; n.y += n.vy * heat; n.vx *= .6; n.vy *= .6; }
  heat = Math.max(.02, heat * .985); }
function size() { const r = cv.getBoundingClientRect(); Wd = r.width; Ht = r.height; cv.width = Wd * devicePixelRatio; cv.height = Ht * devicePixelRatio; }
function draw() {
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0); ctx.clearRect(0, 0, Wd, Ht);
  ctx.save(); ctx.translate(Wd / 2 + view.x, Ht / 2 + view.y); ctx.scale(view.k, view.k);
  const mine = picked ? links.filter(l => (l.a === picked || l.b === picked) && (!relation || l.k === relation)) : [];
  const near = picked ? new Set([picked, ...mine.flatMap(l => [l.a, l.b])]) : null;
  const named = near ? new Set(near.size <= 26 || relation ? near : [picked, ...[...near].sort((a, b) => b.seen - a.seen).slice(0, 15)]) : null;
  const hit = query ? new Set(nodes.filter(n => (n.name + ' ' + n.id).toLowerCase().includes(query))) : null;
  ctx.lineWidth = .6 / view.k;
  for (const l of links) { if (focus && near && !(near.has(l.a) && near.has(l.b))) continue; const on = !near || mine.includes(l);
    ctx.strokeStyle = on ? 'rgba(127,209,193,' + (near ? .7 : .18) + ')' : 'rgba(127,209,193,.04)';
    ctx.beginPath(); ctx.moveTo(l.a.x, l.a.y); ctx.lineTo(l.b.x, l.b.y); ctx.stroke(); }
  for (const n of nodes) { if (focus && near && !near.has(n)) continue; const dim = (near && !near.has(n)) || (hit && !hit.has(n));
    ctx.globalAlpha = dim ? .15 : 1;
    if (n.r > 8 && !dim) { const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r * 2.4); g.addColorStop(0, hue[n.type] + '55'); g.addColorStop(1, 'transparent');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(n.x, n.y, n.r * 2.4, 0, 7); ctx.fill(); }
    ctx.fillStyle = hue[n.type]; ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 7); ctx.fill();
    ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(n.x, n.y, Math.max(1, n.r * .35), 0, 7); ctx.fill();
    if (!dim && ((!near && n.r * view.k > 7) || (named && named.has(n)) || (hit && hit.has(n)))) {
      ctx.fillStyle = '#d7e3e0'; ctx.font = `${(n.r > 9 ? 12 : 10) / view.k}px ui-monospace,Menlo,monospace`; ctx.textAlign = 'center';
      const label = n.name.length > 34 ? n.name.slice(0, 33) + '…' : n.name; ctx.fillText(n.r > 9 ? label.toUpperCase() : label, n.x, n.y + n.r + 12 / view.k); } }
  ctx.globalAlpha = 1; ctx.restore(); }
function loop() { if (document.getElementById('graph').classList.contains('on')) { step(); step(); draw(); } requestAnimationFrame(loop); }
const at = e => { const r = cv.getBoundingClientRect(); return {x: (e.clientX - r.left - Wd / 2 - view.x) / view.k, y: (e.clientY - r.top - Ht / 2 - view.y) / view.k}; };
const find = p => nodes.find(n => (n.x - p.x) ** 2 + (n.y - p.y) ** 2 < (n.r + 4 / view.k) ** 2);
cv.onmousedown = e => { drag = find(at(e)); pan = drag ? null : {x: e.clientX - view.x, y: e.clientY - view.y}; moved = false; };
addEventListener('mousemove', e => { if (drag) { const p = at(e); drag.x = p.x; drag.y = p.y; heat = .3; moved = true; } else if (pan) { view.x = e.clientX - pan.x; view.y = e.clientY - pan.y; moved = true; } });
addEventListener('mouseup', e => { if (!moved && e.target === cv) { const got = find(at(e)); if (got !== picked) relation = null; picked = got || null; if (!picked) focus = false; side(); } drag = null; pan = null; });
cv.addEventListener('wheel', e => { e.preventDefault(); view.k = Math.min(6, Math.max(.15, view.k * (e.deltaY < 0 ? 1.12 : .89))); }, {passive: false});
document.getElementById('zi').onclick = () => view.k = Math.min(6, view.k * 1.2);
document.getElementById('zo').onclick = () => view.k = Math.max(.15, view.k / 1.2);
document.getElementById('zr').onclick = () => { view = {x: 0, y: 0, k: .55}; picked = null; relation = null; focus = false; side(); };
document.getElementById('q').oninput = e => { query = e.target.value.trim().toLowerCase(); };
function side() { const el = document.getElementById('side'); if (!picked) { el.style.display = 'none'; return; }
  const all = D.links.filter(l => l.s === picked.id || l.t === picked.id), groups = {};
  all.forEach(l => { const k = (l.s === picked.id ? '→ ' : '← ') + l.k; (groups[k] = groups[k] || []).push(l); });
  el.innerHTML = `<h3>${esc(picked.name)}</h3><div class="t">${esc(typeName(picked.type))} · <span class="mono">${esc(picked.id)}</span></div>` +
    `<div class="t" style="margin-top:4px">${W.links} ${all.length} (${esc(W.hiddenToo)}) · ${esc(W.relHint)}</div><div class="grp">` +
    Object.entries(groups).sort((a, b) => b[1].length - a[1].length).map(([k, list]) => `<button data-k="${esc(k.slice(2))}" aria-pressed="${relation === k.slice(2)}"><span>${esc(k)}</span><span>${list.length}</span></button>` +
      (relation === k.slice(2) ? '<ul>' + list.slice(0, 30).map(l => `<li class="mono">${esc(l.s === picked.id ? l.t : l.s)}</li>`).join('') + (list.length > 30 ? `<li>+${list.length - 30} ${esc(W.more)}</li>` : '') + '</ul>' : '')).join('') +
    `</div><div class="acts"><button id="fx">${esc(focus ? W.all : W.focus)}</button><button id="cx">${esc(W.close)}</button></div>`;
  el.querySelectorAll('.grp button').forEach(b => b.onclick = () => { relation = relation === b.dataset.k ? null : b.dataset.k; side(); });
  el.querySelector('#fx').onclick = () => { focus = !focus; side(); };
  el.querySelector('#cx').onclick = () => { picked = null; relation = null; focus = false; side(); };
  el.style.display = 'block'; }
size(); addEventListener('resize', size); chips(); build(); for (let i = 0; i < 300; i++) step(); loop();

const cards = document.getElementById('cards'), pos = {};
function placeCards() { const CW = cards.clientWidth || 1140, CH = cards.clientHeight || 800, cx = CW / 2, cy = CH / 2;
  const ring = order.filter(t => t !== 'app'), inner = ring.slice(0, 8), outer = ring.slice(8);
  const place = (list, rx, ry, turn) => list.forEach((t, i) => { const a = i / list.length * Math.PI * 2 - Math.PI / 2 + turn; pos[t] = [cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]; });
  place(inner, Math.min(300, CW * .27), 205, 0); place(outer, CW / 2 - 100, CH / 2 - 75, Math.PI / Math.max(outer.length, 1)); pos.app = [cx, cy]; }
let placed = false;
function wires() { if (!placed) { placeCards(); order.forEach(t => {
    const ex = D.nodes.filter(n => n.type === t).sort((a, b) => b.degree - a.degree).slice(0, 3).map(n => esc(n.name.slice(0, 40))).join(' · ');
    const c = document.createElement('div'); c.className = 'card'; c.dataset.t = t; c.style.left = pos[t][0] + 'px'; c.style.top = pos[t][1] + 'px';
    c.innerHTML = `<b><i style="background:${hue[t]}"></i>${esc(typeName(t))} <span class="mono" style="margin-left:auto">${esc(t)}</span></b><div class="n">${count[t]}</div><div class="ex">${ex}</div>`;
    cards.appendChild(c);
    c.onmousedown = e => { const sx = e.clientX - c.offsetLeft, sy = e.clientY - c.offsetTop;
      const mv = ev => { c.style.left = (ev.clientX - sx) + 'px'; c.style.top = (ev.clientY - sy) + 'px'; wires(); };
      addEventListener('mousemove', mv); addEventListener('mouseup', () => removeEventListener('mousemove', mv), {once: true}); }; }); placed = true; }
  const pairs = {}; D.shape.forEach(s => { (pairs[s.f + '>' + s.t] = pairs[s.f + '>' + s.t] || []).push(s); });
  document.getElementById('wires').innerHTML = Object.values(pairs).map(list => {
    const a = cards.querySelector(`[data-t="${CSS.escape(list[0].f)}"]`), b = cards.querySelector(`[data-t="${CSS.escape(list[0].t)}"]`);
    if (!a || !b) return ''; const x1 = a.offsetLeft, y1 = a.offsetTop, x2 = b.offsetLeft, y2 = b.offsetTop; const label = list.map(s => s.k + ' ' + s.c).join(', ');
    if (a === b) return `<text x="${x1 + 70}" y="${y1 - 40}" fill="#6f7a83" font-size="10" font-family="ui-monospace,Menlo">↻ ${esc(label)}</text>`;
    const w = Math.min(3, .6 + Math.log10(list.reduce((s, x) => s + x.c, 0) + 1));
    return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#2fb57f" stroke-opacity=".55" stroke-width="${w}" stroke-dasharray="5 5"/>` +
      `<text x="${(x1 + x2) / 2}" y="${(y1 + y2) / 2 - 4}" fill="#5fcf9a" font-size="10" text-anchor="middle" font-family="ui-monospace,Menlo">${esc(label)}</text>`; }).join(''); }

const J = D.judge, isOut = r => r.judge === 'outside', failed = r => r.judge !== 'outside' && r.judge !== 'local';
const outRows = J.rows.filter(isOut), localRows = J.rows.filter(r => !isOut(r));
const pct = (list, key, q) => { const v = list.map(r => r[key]).filter(x => typeof x === 'number').sort((a, b) => a - b); return v.length ? v[Math.min(v.length - 1, Math.floor(q * v.length))].toFixed(2) + 's' : '-'; };
const rate = list => list.length ? Math.round(100 * list.filter(r => r.chosen.length).length / list.length) + '%' : '-';
const peak = Math.max(1, ...J.days.map(d => d[1].outside + d[1].local));
let filter = 'all';
function judgeTab() {
  const rows = J.rows.filter(r => filter === 'all' || (filter === 'outside') === isOut(r)).slice(0, 60);
  document.getElementById('judge').innerHTML = `
<div class="grid"><div class="tile"><div class="k">${esc(W.prompts)}</div><div class="v">${J.total}</div></div>
<div class="tile"><div class="k">${esc(W.byJudge)}</div><div class="v">${outRows.length} / ${localRows.length}</div></div>
<div class="tile"><div class="k">${esc(W.latency)}</div><div class="v" style="font-size:20px">${pct(outRows, 'judge_seconds', .5)} · ${pct(outRows, 'judge_seconds', .95)}</div></div>
<div class="tile"><div class="k">${esc(W.attach)}</div><div class="v" style="font-size:20px">${rate(outRows)} · ${rate(localRows)}</div></div></div>
<div class="box"><h2>${esc(W.whatJudge)}</h2><ol class="steps">${[1, 2, 3, 4].map(i => `<li><b>${esc(W['s' + i])}</b><p>${fill(W['s' + i + 'd'], D.limits)}</p></li>`).join('')}</ol></div>
<div class="two"><div class="box"><h2>${esc(W.perDay)}</h2><div class="days">${J.days.map(([d, c]) => `<div title="${esc(d)}: ${c.outside} / ${c.local}"><span style="height:${c.outside / peak * 110}px;background:#7fd1c1"></span><span style="height:${c.local / peak * 110}px;background:#3a4650"></span></div>`).join('')}</div>
<div class="legend"><span><i style="background:#7fd1c1"></i>${esc(W.outside)}</span><span><i style="background:#3a4650"></i>${esc(W.local)}</span></div></div>
<div class="box"><h2>${esc(W.timing)}</h2><table><thead><tr><th>${esc(W.who)}</th><th class="n">${esc(W.count)}</th><th class="n">${esc(W.secs)} p50</th><th class="n">${esc(W.secs)} p95</th><th class="n">${esc(W.jsecs)} p50</th><th class="n">${esc(W.jsecs)} p95</th><th class="n">${esc(W.rate)}</th></tr></thead><tbody>
${[[W.outside, outRows, 'out'], [W.local, localRows, '']].map(([name, list, cls]) => `<tr><td><span class="pill ${cls}">${esc(name)}</span></td><td class="n">${list.length}</td><td class="n">${pct(list, 'seconds', .5)}</td><td class="n">${pct(list, 'seconds', .95)}</td><td class="n">${pct(list, 'judge_seconds', .5)}</td><td class="n">${pct(list, 'judge_seconds', .95)}</td><td class="n">${rate(list)}</td></tr>`).join('')}</tbody></table></div></div>
<div class="box"><h2>${esc(W.log)}</h2><div class="filters">${[['all', W.every], ['outside', W.outside], ['local', W.local]].map(([k, v]) => `<button class="chip" data-j="${k}" aria-pressed="${filter === k}">${esc(v)}</button>`).join('')}</div>
<div class="scroll"><table><thead><tr><th>${esc(W.time)}</th><th>${esc(W.who)}</th><th class="n">${esc(W.secs)}</th><th class="n">${esc(W.jsecs)}</th><th class="decision">${esc(W.decision)}</th><th class="picked">${esc(W.picked)}</th></tr></thead><tbody>
${rows.map(r => `<tr><td class="mono">${esc(r.at.replace('T', ' '))}</td><td><span class="pill ${isOut(r) ? 'out' : ''}">${esc(isOut(r) ? W.outside : failed(r) ? W.failed : W.local)}</span></td>
<td class="n">${r.seconds ?? '-'}s</td><td class="n">${r.judge_seconds ?? '-'}${r.judge_seconds == null ? '' : 's'}</td>
<td class="decision">${r.chosen.length ? fill(W.pickedN, {n: r.chosen.length, o: r.offered}) : r.offered ? fill(W.none, {o: r.offered}) : esc(W.empty)}</td><td class="mono picked">${r.chosen.map(esc).join('<br>')}</td></tr>`).join('')}</tbody></table></div></div>`;
  document.querySelectorAll('[data-j]').forEach(b => b.onclick = () => { filter = b.dataset.j; judgeTab(); }); }
judgeTab();

const usage = {}; D.ran.forEach(r => { (usage[r.model] = usage[r.model] || {ran: 0, rev: 0}).ran = r.c; });
D.reviewed.forEach(r => { (usage[r.model] = usage[r.model] || {ran: 0, rev: 0}).rev = r.c; });
const most = Math.max(1, ...Object.values(usage).map(u => u.ran + u.rev));
document.getElementById('models').innerHTML = `
<div class="box"><h2>${esc(W.how)}</h2><ol class="steps">${[1, 2, 3, 4].map(i => `<li><b>${esc(W['m' + i])}</b><p>${esc(W['m' + i + 'd'])}</p></li>`).join('')}</ol></div>
<div class="two"><div class="box"><h2>${esc(W.roles)}</h2><table><thead><tr><th>${esc(W.role)}</th><th>${esc(W.model)}</th></tr></thead><tbody>
${[1, 2, 3].map(i => `<tr><td>${esc(W['r' + i])}</td><td>${esc(W['r' + i + 'm'])}</td></tr>`).join('')}</tbody></table></div>
<div class="box"><h2>${esc(W.usage)}</h2><table><thead><tr><th>${esc(W.model)}</th><th class="n">${esc(W.ran)}</th><th class="n">${esc(W.rev)}</th><th style="width:40%"></th></tr></thead><tbody>
${Object.entries(usage).sort((a, b) => (b[1].ran + b[1].rev) - (a[1].ran + a[1].rev)).map(([m, u]) => `<tr><td class="mono">${esc(m)}</td><td class="n">${u.ran}</td><td class="n">${u.rev}</td>
<td><div class="meter"><i style="width:${(u.ran + u.rev) / most * 100}%;background:linear-gradient(90deg,#3987e5 ${u.ran / Math.max(1, u.ran + u.rev) * 100}%,#7fd1c1 0)"></i></div></td></tr>`).join('')}</tbody></table>
<div class="legend"><span><i style="background:#3987e5"></i>${esc(W.ran)}</span><span><i style="background:#7fd1c1"></i>${esc(W.rev)}</span></div></div></div>
<div class="box"><h2>${esc(W.prefers)}</h2>${D.prefers.length ? '<table>' + D.prefers.map(p => `<tr><td>${esc(p.skill)}</td><td class="mono">${esc(p.model)}</td><td>${p.rank === 0 ? esc(W.first) : esc(W.fallback) + ' ' + esc(p.rank)}</td><td>${esc(p.effort || '')}</td></tr>`).join('') + '</table>' : `<p class="quote">${esc(W.noPrefers)}</p>`}</div>
<details class="box"><summary style="cursor:pointer;color:var(--ink2);font-size:13px">${esc(W.ruleText)}</summary><p class="quote" style="margin-top:10px">${esc(D.rule || W.noRule)}</p></details>`;

const S = D.server, http = S.url, host = (() => { try { return new URL(http).hostname; } catch (e) { return '127.0.0.1'; } })();
const bolt = `bolt://${host}:7687`;
document.getElementById('connect').innerHTML = `
<div class="box"><h2>${esc(W.server)}</h2><table>
<tr><td>${esc(W.state)}</td><td class="${S.up ? 'ok' : 'bad'}">${esc(S.up ? W.up : W.down)}</td></tr>
<tr><td>${esc(W.version)}</td><td class="mono">${esc(S.version || '-')}</td></tr>
<tr><td>${esc(W.url)}</td><td class="mono">${esc(http)}</td></tr><tr><td>${esc(W.bolt)}</td><td class="mono">${esc(bolt)}</td></tr>
<tr><td>${esc(W.user)}</td><td class="mono">${esc(S.user)}</td></tr><tr><td>${esc(W.secret)}</td><td>${fill(W.secretWhere, {where: S.password_from})}</td></tr>
<tr><td>${esc(W.nodesLinks)}</td><td class="mono">${S.up ? `${S.nodes} · ${S.links} · ${S.files}` : '-'}</td></tr>
<tr><td>${esc(W.browser)}</td><td class="mono">${esc(http.replace(/\/$/, ''))}/browser/</td></tr></table></div>
<div class="box"><h2>${esc(W.remote)}</h2><p class="quote">${esc(W.remoteText)}</p>
<pre>ssh -N -L 7474:${esc(host)}:7474 -L 7687:${esc(host)}:7687 ${esc(S.host)}</pre>
<pre>http://localhost:7474/browser/   (Connect URL: bolt://localhost:7687, ${esc(W.user)}: ${esc(S.user)})</pre></div>`;

open(tabs.includes(saved.tab) ? saved.tab : 'graph');
setInterval(() => { if (!document.hidden && !picked && !query) location.reload(); }, 60000);
})();
</script></body></html>"""


if __name__ == "__main__":
    sys.exit(main())
