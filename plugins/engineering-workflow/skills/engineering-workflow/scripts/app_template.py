import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import registry_scan

DEFAULT_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "app"
RULE_FILES = ("CLAUDE.md", "AGENTS.md")
NAME = "{{app}}"


FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
TITLE = re.compile(r"^#(?:[ \t]|$)")


def fence_change(line, open_fence):
    match = FENCE.match(line)
    if not match:
        return open_fence
    marker = match.group(1)
    if open_fence is None:
        return marker
    if marker[0] == open_fence[0] and len(marker) >= len(open_fence) and not line.strip()[len(marker):].strip():
        return None
    return open_fence


def heading_key(title):
    return " ".join(title.casefold().split())


def sections(content):
    found, current, fence = {}, None, None
    for line in content.splitlines():
        before, fence = fence, fence_change(line, fence)
        heading = registry_scan.HEADING.match(line) if before is None and fence is None else None
        if heading or (before is None and fence is None and TITLE.match(line)):
            current = None
        if heading:
            title = registry_scan.TRAILING_NOTE.sub("", heading.group(1)) or heading.group(1)
            key = heading_key(title)
            current = None if key in found else key
            if current:
                found[key] = {"title": title, "lines": []}
            continue
        if current:
            found[current]["lines"].append(line)
    return {key: {"title": item["title"], "text": "\n".join(item["lines"]).strip()} for key, item in found.items()}


def words(text):
    paragraphs, current, fence = [], [], None
    for line in text.splitlines() + [""]:
        before, fence = fence, fence_change(line, fence)
        if before is not None or fence is not None:
            if current and before is None:
                paragraphs.append(" ".join(" ".join(current).split()))
                current = []
            paragraphs.append(line.rstrip())
        elif line.strip():
            current.append(line)
        elif current:
            paragraphs.append(" ".join(" ".join(current).split()))
            current = []
    return paragraphs


def template_entries(template):
    root = Path(template)
    if not root.is_dir():
        raise ValueError(f"template folder {root} not found")
    return sorted(path for path in root.rglob("*") if path.name != ".DS_Store" and (path.is_file() or path.is_dir()))


def filled(source, name):
    data = source.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    value = json.dumps(name, ensure_ascii=False)[1:-1] if source.suffix == ".json" else name
    return text.replace(NAME, value).encode("utf-8")


def inside(path, target):
    try:
        path.resolve().relative_to(target.resolve())
    except ValueError:
        return False
    return True


def create(template, destination, name):
    root, target = Path(template), Path(destination)
    written, kept = [], []
    target.mkdir(parents=True, exist_ok=True)
    for source in template_entries(root):
        relative = source.relative_to(root).as_posix()
        path = target / relative
        if not inside(path, target):
            kept.append(f"{relative} (outside the folder through a link, not written)")
            continue
        if source.is_dir():
            path.mkdir(parents=True, exist_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "xb") as handle:
                handle.write(filled(source, name))
        except FileExistsError:
            kept.append(f"{relative} (already there)")
            continue
        written.append(relative)
    return written, kept


def rules_of(folder):
    for name in RULE_FILES:
        path = Path(folder) / name
        if path.is_file():
            return path
    return None


def drift(template, apps):
    rules = rules_of(template)
    if rules is None:
        raise ValueError(f"template {template} has no {' or '.join(RULE_FILES)}")
    shared = rules.read_text(encoding="utf-8-sig")
    report = []
    for app in apps:
        own = rules_of(app["path"])
        wanted = sections(shared.replace(NAME, app["name"]))
        if own is None:
            report.append({"app": app["name"], "file": None, "rule": None, "state": "no rule file", "detail": None})
            continue
        have = sections(own.read_text(encoding="utf-8-sig"))
        for key, item in wanted.items():
            if key not in have:
                report.append({"app": app["name"], "file": str(own), "rule": item["title"], "state": "missing",
                               "detail": None})
                continue
            old, new = words(have[key]["text"]), words(item["text"])
            if old != new:
                change = next((line for line in difflib.unified_diff(old, new, lineterm="", n=0)
                               if line[:1] in "+-" and not line.startswith(("+++", "---"))), "")
                report.append({"app": app["name"], "file": str(own), "rule": item["title"], "state": "differs",
                               "detail": change[:160]})
    return report


def apps_from(args):
    if args.app:
        apps = []
        for value in args.app:
            name, separator, folder = value.partition("=")
            if not separator:
                name, folder = Path(value).expanduser().resolve().name, value
            apps.append({"name": name, "path": str(Path(folder).expanduser())})
        return apps
    path = Path(args.config or os.environ.get("HARNESS_REGISTRY_CONFIG")
                or Path.home() / ".config" / "engineering-workflow" / "registry.json")
    config = json.loads(path.read_text(encoding="utf-8"))
    items = config.get("apps") if isinstance(config, dict) else None
    if not isinstance(items, list) or not all(isinstance(item, dict) and isinstance(item.get("name"), str)
                                              and isinstance(item.get("path"), str) for item in items):
        raise ValueError(f"{path} needs an apps list of name and path")
    return [{"name": item["name"], "path": str(Path(item["path"]).expanduser())} for item in items]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start an app from the template, and list apps whose shared rules "
                                                 "no longer match it.")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE), help="template folder (default: the skill's)")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("new", help="copy the template into a folder; existing files are kept")
    start.add_argument("folder")
    start.add_argument("--name", help="app name (default: the folder name)")
    check = commands.add_parser("drift", help="compare each app's rule file with the template's sections")
    check.add_argument("--config", help="registry config with the app list")
    check.add_argument("--app", action="append", help="app folder or name=folder; repeat for more (instead of --config)")
    check.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            name = args.name or Path(args.folder).resolve().name
            written, kept = create(args.template, args.folder, name)
            lines = [f"wrote {item}" for item in written] + [f"kept {item}" for item in kept]
            sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))
            return 0
        report = drift(args.template, apps_from(args))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"TEMPLATE CHECK UNAVAILABLE: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    if args.json:
        output = json.dumps(report, ensure_ascii=False, indent=1)
    else:
        lines = [f"{row['app']}: {row['state']}" + (f": {row['rule']}" if row["rule"] else "")
                 + (f"  {row['detail']}" if row["detail"] else "") for row in report]
        output = "\n".join(lines or ["every app matches the template"])
    sys.stdout.buffer.write((output + "\n").encode("utf-8"))
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())
