import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

BODY_LIMIT = 4000
SKILL_DEPTH = 4
TARGET = re.compile(r"(app|plugin|skill|tool|model|rule|asset|record|task|decision|source):(.+)")
HEADING = re.compile(r"^## +(.+?)\s*$")
TRAILING_NOTE = re.compile(r"\s*\([^()]*\)\s*$")
FENCE = re.compile(r"^(```|~~~)")


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
    nodes = [node("skill", name.strip(), text=description, model=extra.get("model"), effort=extra.get("effort"))]
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
    nodes = [node("tool", f"hook:{name}", name=name, kind="hook") for name in sorted(found)]
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


READERS = {"skill": skill_facts, "plugin": plugin_facts, "hooks": hooks_facts, "settings": settings_facts,
           "installed": installed_facts, "board": board_facts, "record": record_facts, "asset": asset_facts,
           "rules": rules_facts, "glossary": glossary_facts}


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
                raw + json.dumps([kind, scope], sort_keys=True).encode("utf-8")).hexdigest()
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
