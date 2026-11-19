import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

BODY_LIMIT = 4000
SKILL_DEPTH = 4
TARGET = re.compile(r"(app|plugin|skill|tool|model|rule|asset|record|task|decision|source|license):(.+)")
HEADING = re.compile(r"^## +(.+?)\s*$")
TRAILING_NOTE = re.compile(r"\s*\([^()]*\)\s*$")
FENCE = re.compile(r"^(```|~~~)")
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
TOP_HEADING = re.compile(r"^ {0,3}(#{1,2})[ \t]+(.+?)\s*$")
LANE_MARK = "~"
URL = re.compile(r"https?://([^/\s)>`|,;?#:]+?)\.?(?=[/\s)>`|,;?#:]|$)[^\s)>`|,;]*")
SEPARATOR = re.compile(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?")
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
CREDIT_BULLET = re.compile(r"- ((?:`[^`]+`\s*,?\s*)+):\s*(.+)")
TICKED = re.compile(r"`([^`]+)`")
LICENSES = (
    (re.compile(r"\bCC0\b|creative commons 0|public domain", re.I), "CC0", "no"),
    (re.compile(r"\bCC[- ]BY(?:[- ](?:SA|NC|ND))*(?:[- ]\d\.\d)?", re.I), None, "credit"),
    (re.compile(r"\bOFL\b|SIL Open Font License(?: \d\.\d)?", re.I), "OFL", "notice"),
    (re.compile(r"\bApache(?: License)?(?: \d\.\d)?", re.I), "Apache-2.0", "notice"),
    (re.compile(r"\bMIT\b"), "MIT", "notice"),
)
COLUMNS = {"file": "file", "files": "file", "licence": "license", "license": "license", "source": "source",
           "from": "source", "author": "author", "by": "author"}
CREDIT_FILES = "*CREDITS.md"
GIT_TIMEOUT = 5
SCANNER = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
SESSION_LINE = re.compile(r"([A-Za-z][\w-]{0,30}):\s+(.+)")
SESSION_ID = re.compile(r"session_id=([0-9a-fA-F-]{8,})")
LANE = re.compile(r"lane\s*(\d+)", re.IGNORECASE)
LINE_LIMIT = 400


def slug(value):
    return re.sub(r"[^\w]+", "-", value.casefold()).strip("-")[:80] or "unnamed"


def listed(value):
    return [item.strip() for item in value.split(",") if item.strip()] if isinstance(value, str) else []


def unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        if value[0] == '"':
            try:
                return str(json.loads(value))
            except ValueError:
                return value[1:-1]
        return value[1:-1].replace("''", "'")
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def frontmatter(content):
    lines = content.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.rstrip() == "---")
    except StopIteration:
        return {}, content
    fields, parent, child_indent, block = {}, None, None, None
    for line in lines[1:end]:
        indent = len(line) - len(line.lstrip(" \t"))
        if block:
            target, key, joiner, base = block
            if not line.strip() or indent > base:
                target[key] = f"{target[key]}{joiner if target[key] else ''}{line.strip()}"
                continue
            target[key] = target[key].strip()
            block = None
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if indent and parent is None:
            continue
        if indent:
            child_indent = indent if child_indent is None else child_indent
            if indent != child_indent:
                continue
        else:
            parent, child_indent = None, None
        if ":" not in line:
            continue
        key, _, value = line.strip().partition(":")
        if key[:1] in "\"'" and key[-1:] == key[:1]:
            key, _, value = line.strip()[1:].partition(key[0] + ":")
        key, value = unquote(key), value.strip()
        target = fields[parent] if indent else fields
        if value == "":
            if not indent:
                fields[key] = {}
                parent = key
        elif value[:1] in "|>" and len(value) <= 3:
            target[key] = ""
            block = (target, key, "\n" if value[0] == "|" else " ", indent)
        else:
            target[key] = unquote(value)
    if block:
        block[0][block[1]] = block[0][block[1]].strip()
    return fields, "\n".join(lines[end + 1:]).strip()


def node(category, key, name=None, **props):
    data = {"id": f"{category}:{key}", "type": category, "name": name or key}
    data.update({prop: value for prop, value in props.items() if value not in (None, "", [])})
    return data


def link(source, relation, target, **props):
    data = {"from": source, "type": relation, "to": target}
    data.update({prop: value for prop, value in props.items() if value not in (None, "", [])})
    return data


def reference(value, default):
    known = TARGET.fullmatch(value)
    if known and known.group(1) == "tool":
        return value
    if known:
        return f"{known.group(1)}:{known.group(2).strip()}"
    if ":" in value:
        return f"tool:{value}"
    return f"{default}:{value}"


def skill_facts(content, origin):
    fields, _ = frontmatter(content)
    name = fields.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("skill has no name")
    extra = fields.get("metadata") if isinstance(fields.get("metadata"), dict) else {}
    description = fields.get("description") if isinstance(fields.get("description"), str) else ""
    me = f"skill:{name.strip()}"
    nodes = [node("skill", name.strip(), text=description, model=extra.get("model"), effort=extra.get("effort"),
                  keywords=extra.get("keywords"))]
    owners = origin.get("owners") or ([origin["owner"]] if origin.get("owner") else [])
    links = [link(owner, origin["verb"], me, scope=origin.get("scope")) for owner in owners]
    for item in listed(extra.get("requires")):
        links.append(link(me, "REQUIRES", reference(item, "skill")))
    for item in listed(extra.get("supersedes")):
        links.append(link(me, "SUPERSEDES", reference(item, "skill")))
    choices = listed(extra.get("model")) + listed(extra.get("fallback"))
    for order, item in enumerate(choices):
        links.append(link(me, "PREFERS", f"model:{item}", order=order,
                          effort=extra.get("effort") if order == 0 else None))
    return nodes, links


def plugin_facts(content, origin):
    data = json.loads(content)
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str) or not name.strip():
        raise ValueError("plugin manifest has no name")
    return [node("plugin", name.strip(), text=data.get("description"), version=data.get("version"))], []


def hooks_facts(content, origin):
    data = json.loads(content).get("hooks", {})
    found = {}
    for event, groups in data.items():
        for group in groups if isinstance(groups, list) else []:
            for hook in group.get("hooks", []) if isinstance(group, dict) else []:
                command = hook.get("command", "") if isinstance(hook, dict) else ""
                scripts = re.findall(r"([\w.-]+)\.(?:sh|py|js|ts|rb)\b", command)
                if scripts:
                    found.setdefault(scripts[-1], []).append(event)
    nodes = [node("tool", f"hook:{name}", name=name, kind="hook",
                  text=f"hook {name} on {', '.join(sorted(set(found[name])))}") for name in sorted(found)]
    links = [link(origin["owner"], "PROVIDES", f"tool:hook:{name}", events=sorted(set(events)))
             for name, events in sorted(found.items())] if origin.get("owner") else []
    return nodes, links


def settings_facts(content, origin):
    enabled = json.loads(content).get("enabledPlugins", {})
    links = []
    for key, state in sorted(enabled.items()) if isinstance(enabled, dict) else []:
        plugin = f"plugin:{key.split('@')[0]}"
        for app in origin["apps"]:
            links.append(link(app, "USES" if state else "DISABLES", plugin, scope=origin["scope"]))
    return [], links


def installed_facts(content, origin):
    plugins = json.loads(content).get("plugins", {})
    by_path = origin["paths"]
    nodes, links = [], []
    for key, entries in sorted(plugins.items()) if isinstance(plugins, dict) else []:
        plugin = f"plugin:{key.split('@')[0]}"
        for entry in entries if isinstance(entries, list) else []:
            version, scope, where = entry.get("version"), entry.get("scope"), entry.get("projectPath")
            if scope == "user":
                targets = origin["apps"]
            elif where in by_path:
                targets = [by_path[where]]
            elif where:
                name = "/".join(Path(where).parts[-2:])
                nodes.append(node("checkout", name, path=where))
                targets = [f"checkout:{name}"]
            else:
                targets = []
            links.extend(link(target, "INSTALLED", plugin, version=version, scope=scope) for target in targets)
    return nodes, links


def board_facts(content, origin):
    data = json.loads(content)
    app, name = origin["app"], origin["app"].split(":", 1)[1]
    nodes, links = [], []
    for task in data.get("tasks", []):
        if str(task["id"]).startswith(LANE_MARK):
            continue
        key = f"{name}/{task['id']}"
        nodes.append(node("task", key, name=task.get("title") or task["id"], status=task.get("status", "todo"),
                          owner=task.get("owner"), text=task.get("note")))
        links.append(link(f"task:{key}", "IN", app))
        links.extend(link(f"task:{key}", "AFTER", f"task:{name}/{dep}") for dep in task.get("after", []))
    for decision in data.get("decisions", []):
        key = f"{name}/{slug(decision['ask'])}"
        nodes.append(node("decision", key, name=decision["ask"], state="open", look=decision.get("look"),
                          default=decision.get("default")))
        links.append(link(f"decision:{key}", "IN", app))
    return nodes, links


def record_facts(content, origin):
    fields, body = frontmatter(content)
    app, name = origin["app"], origin["app"].split(":", 1)[1]
    key = f"{name}/{fields['id']}"
    me = f"record:{key}"
    nodes = [node("record", key, name=fields.get("title") or fields["id"], text=body[:BODY_LIMIT],
                  date=str(fields["id"])[:10] if re.match(r"\d{4}-\d{2}-\d{2}", str(fields["id"])) else None)]
    links = [link(me, "IN", app)]
    task = f"task:{name}/{fields['task']}" if fields.get("task") else None
    if task:
        links.append(link(me, "FOR", task))
    links.extend(link(me, "USED", reference(item, "skill")) for item in listed(fields.get("skills")))
    links.extend(link(me, "RAN_ON", f"model:{item}") for item in listed(fields.get("model")))
    links.extend(link(me, "CONCERNS", reference(item, "skill")) for item in listed(fields.get("concerns")))
    reviewer, _, verdict = (fields.get("review") or "").partition(":")
    for commit in listed(fields.get("commits")):
        nodes.append(node("commit", f"{name}/{commit}", name=commit))
        links.append(link(me, "PRODUCED", f"commit:{name}/{commit}"))
        if reviewer.strip():
            links.append(link(f"commit:{name}/{commit}", "REVIEWED_BY", f"model:{reviewer.strip()}",
                              result=verdict.strip()))
    for decision in listed(fields.get("decisions")):
        decided = f"{name}/{slug(decision)}"
        nodes.append(node("decision", decided, name=decision, state="settled"))
        links.append(link(f"decision:{decided}", "IN", app))
        if task:
            links.append(link(f"decision:{decided}", "AFFECTS", task))
    return nodes, links


def asset_facts(content, origin):
    fields, body = frontmatter(content)
    app, name = origin["app"], origin["app"].split(":", 1)[1]
    key = f"{name}/{fields['id']}"
    me = f"asset:{key}"
    nodes = [node("asset", key, name=fields["id"], file=fields.get("file"), text=body[:BODY_LIMIT])]
    links = [link(me, "IN", app)]
    if fields.get("version_of"):
        links.append(link(me, "VERSION_OF", f"asset:{name}/{fields['version_of']}"))
    if fields.get("source"):
        origin_key = slug(fields["source"])
        nodes.append(node("source", origin_key, name=fields["source"], license=fields.get("license")))
        links.append(link(me, "FROM", f"source:{origin_key}", license=fields.get("license")))
    links.extend(link(me, "MADE_BY", f"model:{item}") for item in listed(fields.get("made_by")))
    if fields.get("approved_by"):
        decided = f"{name}/{slug(fields['approved_by'])}"
        nodes.append(node("decision", decided, name=fields["approved_by"], state="settled"))
        links.append(link(f"decision:{decided}", "IN", app))
        links.append(link(f"decision:{decided}", "APPROVED", me))
    return nodes, links


def rules_facts(content, origin):
    nodes, links, fenced, seen = [], [], False, set()
    for number, line in enumerate(content.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
        heading = None if fenced else HEADING.match(line)
        if not heading:
            continue
        title = TRAILING_NOTE.sub("", heading.group(1)) or heading.group(1)
        key = slug(title)
        if key in seen:
            continue
        seen.add(key)
        nodes.append(node("rule", key, name=title))
        links.extend(link(f"rule:{key}", "APPLIES_TO", app, scope=origin["scope"], line=number)
                     for app in origin["apps"])
    return nodes, links


def glossary_facts(content, origin):
    nodes, links = [], []
    for line in content.splitlines():
        word, separator, meaning = line.partition("=")
        word, meaning = word.strip(), meaning.strip()
        if not separator or not word or not meaning or word.startswith("#"):
            continue
        nodes.append(node("term", word, means=meaning))
        if TARGET.fullmatch(meaning):
            links.append(link(f"term:{word}", "ALIAS_OF", reference(meaning, "skill")))
    return nodes, links


def fence_mark(line, opened):
    found = FENCE_OPEN.match(line)
    if not found:
        return opened
    mark = found.group(1)
    if opened is None:
        return mark
    if mark[0] == opened[0] and len(mark) >= len(opened) and not line.strip()[len(mark):].strip():
        return None
    return opened


def bullets(content):
    sections, current, opened = {}, None, None
    for line in content.splitlines():
        was = opened
        opened = fence_mark(line, opened)
        if was is not None or opened is not None:
            continue
        heading = TOP_HEADING.match(line)
        if heading:
            current = sections.setdefault(heading.group(2), []) if len(heading.group(1)) == 2 else None
        elif current is None:
            continue
        elif line.startswith("- "):
            current.append(line[2:].strip())
        elif current and line[:1].isspace() and line.strip():
            current[-1] = f"{current[-1]} {line.strip()}"
    return sections


def license_of(text):
    for pattern, name, attribution in LICENSES:
        found = pattern.search(text or "")
        if found:
            return name or re.sub(r"[- ]+", " ", found.group(0)).upper(), attribution
    return None, "check"


def unfenced(lines):
    opened = None
    for line in lines:
        was = opened
        opened = fence_mark(line, opened)
        yield None if was is not None or opened is not None else line


def first_paragraph(lines):
    block = []
    for line in unfenced(lines):
        if line is None or line.startswith("#") or not line.strip() or line.lstrip().startswith(("|", "- ")) or (
                "|" in line):
            if block:
                break
            continue
        block.append(line)
    return " ".join(block)


def cells(line):
    text = line.strip()
    text = text[1:] if text.startswith("|") else text
    text = text[:-1] if text.endswith("|") and not text.endswith("\\|") else text
    return [cell.strip().replace("\\|", "|") for cell in UNESCAPED_PIPE.split(text)]


def credit_rows(lines):
    rows, header, plain = [], None, list(unfenced(lines))
    for index, line in enumerate(plain):
        if line is None or "|" not in line:
            header = None
            if line:
                item = CREDIT_BULLET.match(line.strip())
                if item:
                    rows.append({"file": item.group(1), "title": item.group(2)})
            continue
        if SEPARATOR.fullmatch(line.strip()):
            continue
        following = plain[index + 1] if index + 1 < len(plain) else None
        if following is not None and SEPARATOR.fullmatch(following.strip()):
            header = [COLUMNS.get(cell.lower(), "title" if position else "file")
                      for position, cell in enumerate(cells(line))]
        elif header is not None:
            rows.append(dict(zip(header, cells(line))))
    return rows


def credits_facts(content, origin):
    app, name = origin["app"], origin["app"].split(":", 1)[1]
    folder = origin["folder"]
    group = slug(Path(folder).name or name)
    place = f"{group}-{hashlib.sha256(folder.encode('utf-8')).hexdigest()[:6]}"
    lines = content.splitlines()
    opening = first_paragraph(lines)
    default, fallback = license_of(opening), URL.search(opening)
    nodes, links, licenses = [], [], {}
    for row in credit_rows(lines):
        named = TICKED.findall(row.get("file", "")) or ([row["file"]] if row.get("file") else [])
        licence, attribution = license_of(row["license"]) if row.get("license") else default
        where = URL.search(row.get("source", "")) or URL.search(" ".join(row.values())) or fallback
        for item in named:
            key = f"{name}/{place}/{item}"
            me = f"asset:{key}"
            nodes.append(node("asset", key, name=item, file=f"{folder}/{item}" if folder else item,
                              text=" ".join(value for field, value in row.items() if field in ("title", "author")),
                              group=group))
            links.append(link(me, "IN", app))
            if licence:
                licenses[licence] = attribution
                links.append(link(me, "UNDER", f"license:{slug(licence)}"))
            if where:
                host = where.group(1).lower()
                nodes.append(node("source", host, url=where.group(0)))
                links.append(link(me, "FROM", f"source:{host}", license=licence))
    nodes.extend(node("license", slug(licence), name=licence, attribution=attribution)
                 for licence, attribution in licenses.items())
    return nodes, links


def credit_files(root, ignore):
    try:
        listed_files = subprocess.run(["git", "--no-optional-locks", "-C", str(root), "ls-files", "-z", "--",
                                       CREDIT_FILES], capture_output=True, timeout=GIT_TIMEOUT, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for relative in listed_files.decode("utf-8", "replace").split("\0"):
        parts = Path(relative).parts
        if not relative or parts[-1] != "CREDITS.md" or any(part.startswith(".") for part in parts[:-1]):
            continue
        if any(fnmatch.fnmatch(relative, pattern) for pattern in ignore):
            continue
        found.append(relative)
    return sorted(found)


def working_facts(content, origin):
    app, name = origin["app"], origin["app"].split(":", 1)[1]
    sections = bullets(content)
    people, notes = {}, []
    for title, lines in sections.items():
        if title.strip().lower() != "sessions":
            continue
        for line in lines:
            shaped = SESSION_LINE.match(line)
            if shaped:
                people[shaped.group(1)] = [shaped.group(2)]
            else:
                notes.append(line)
    for note in notes:
        for who, text in people.items():
            if re.search(rf"\b{re.escape(who)}\b", note):
                text.append(note)
    nodes, links = [], []
    machine = origin.get("machine")
    if machine:
        nodes.append(node("machine", machine))
    for who, text in people.items():
        me = f"session:{name}/{who}"
        found = SESSION_ID.search(text[0])
        nodes.append(node("session", f"{name}/{who}", name=who, session_id=found.group(1) if found else None,
                          text=" ".join(text)[:BODY_LIMIT]))
        links.append(link(me, "IN", app))
        if machine:
            links.append(link(me, "ON", f"machine:{machine}"))
    for title, lines in sections.items():
        lane = LANE.match(title.strip())
        if not lane:
            continue
        label = TRAILING_NOTE.sub("", title).strip() or title.strip()
        for line in lines:
            who = re.match(r"[\w-]+", line)
            if not who or who.group(0) not in people:
                continue
            work = line.split(": ", 1)[1] if ": " in line else line
            digest = hashlib.sha256(f"{who.group(0)}\n{work}".encode("utf-8")).hexdigest()[:12]
            key = f"{name}/{LANE_MARK}lane{lane.group(1)}-{digest}"
            nodes.append(node("task", key, name=work[:LINE_LIMIT], status="doing", lane=label))
            links.append(link(f"task:{key}", "IN", app))
            links.append(link(f"session:{name}/{who.group(0)}", "HOLDS", f"task:{key}", lane=label))
    return nodes, links


READERS = {"skill": skill_facts, "plugin": plugin_facts, "hooks": hooks_facts, "settings": settings_facts,
           "installed": installed_facts, "board": board_facts, "record": record_facts, "asset": asset_facts,
           "rules": rules_facts, "glossary": glossary_facts, "working": working_facts,
           "credits": credits_facts}


def skill_files(folder):
    if not folder.is_dir():
        return []
    found = []
    for path in folder.rglob("SKILL.md"):
        if len(path.relative_to(folder).parts) <= SKILL_DEPTH and path.is_file():
            found.append(path)
    return sorted(found)


def discover(config):
    apps = [(item["name"], Path(item["path"])) for item in config.get("apps", [])]
    every = [f"app:{name}" for name, _ in apps]
    machines = {item["name"]: item.get("machine") or config.get("machine") for item in config.get("apps", [])}
    ignores = {item["name"]: list(item.get("ignore") or []) for item in config.get("apps", [])}
    sources = []

    def add(path, kind, **origin):
        if Path(path).is_file():
            sources.append((Path(path), kind, origin))

    for name, root in apps:
        app = f"app:{name}"
        add(root / ".harness" / "board.json", "board", app=app)
        for path in sorted((root / ".harness" / "records").glob("*.md")) if (root / ".harness" / "records").is_dir() else []:
            add(path, "record", app=app)
        for path in sorted((root / ".harness" / "assets").glob("*.md")) if (root / ".harness" / "assets").is_dir() else []:
            add(path, "asset", app=app)
        add(root / "WORKING.md", "working", app=app, machine=machines.get(name))
        for relative in credit_files(root, ignores.get(name, [])):
            add(root / relative, "credits", app=app, folder=str(Path(relative).parent.as_posix()).strip("."))
        for rules in ("CLAUDE.md", "AGENTS.md"):
            add(root / rules, "rules", apps=[app], scope="project")
        add(root / ".claude" / "settings.json", "settings", apps=[app], scope="project")
        for path in skill_files(root / ".claude" / "skills"):
            add(path, "skill", owner=app, verb="HAS")
    user = config.get("user")
    if user:
        user = Path(user)
        add(user / "CLAUDE.md", "rules", apps=every, scope="user")
        add(user / "settings.json", "settings", apps=every, scope="user")
        add(user / "plugins" / "installed_plugins.json", "installed", apps=every,
            paths={str(root): f"app:{name}" for name, root in apps})
        for path in skill_files(user / "skills"):
            add(path, "skill", owners=every, verb="HAS", scope="user")
    for folder in config.get("plugins", []):
        folder = Path(folder)
        manifest = folder / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            continue
        try:
            name = json.loads(manifest.read_text(encoding="utf-8"))["name"]
            owner = f"plugin:{name.strip()}" if isinstance(name, str) and name.strip() else None
        except Exception:
            owner = None
        add(manifest, "plugin")
        add(folder / "hooks" / "hooks.json", "hooks", owner=owner)
        for path in skill_files(folder / "skills"):
            add(path, "skill", owner=owner, verb="PROVIDES")
    if config.get("glossary"):
        add(config["glossary"], "glossary")
    return apps, sources


def scan(config):
    apps, sources = discover(config)
    files = {"config:apps": {"kind": "apps", "hash": hashlib.sha256(
        json.dumps(sorted((name, str(root)) for name, root in apps)).encode("utf-8")).hexdigest(),
        "nodes": [node("app", name, path=str(root)) for name, root in apps], "links": []}}
    for path, kind, origin in sources:
        entry = {"kind": kind}
        try:
            raw = path.read_bytes()
            scope = {key: sorted(value) if isinstance(value, list) else value for key, value in origin.items()}
            entry["hash"] = hashlib.sha256(
                raw + json.dumps([kind, scope, SCANNER], sort_keys=True).encode("utf-8")).hexdigest()
            entry["nodes"], entry["links"] = READERS[kind](raw.decode("utf-8"), origin)
            for item in entry["nodes"]:
                if item["id"].split(":")[0] in ("skill", "record", "asset") and "path" not in item:
                    item["path"] = str(path)
        except Exception as error:
            entry.update({"nodes": [], "links": [], "error": f"{type(error).__name__}: {error}"})
            entry.setdefault("hash", "unreadable")
        files[str(path)] = entry
    return {"files": files}


def main():
    parser = argparse.ArgumentParser(description="Read skills, plugins, boards, records, assets, rules, and a glossary "
                                                 "into nodes and links, grouped by the file each one came from.")
    parser.add_argument("config", help="JSON file with apps, and optionally user, plugins, and glossary paths")
    parser.add_argument("--out", help="write the result here instead of standard output")
    args = parser.parse_args()
    try:
        result = scan(json.loads(Path(args.config).read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"INVALID: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    output = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
    else:
        sys.stdout.buffer.write((output + "\n").encode("utf-8"))
    failed = [path for path, entry in result["files"].items() if entry.get("error")]
    for path in failed:
        print(f"SKIPPED {path}: {result['files'][path]['error']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
