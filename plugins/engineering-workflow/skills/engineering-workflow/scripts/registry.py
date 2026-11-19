import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import registry_neo4j as graph
import registry_scan
import registry_usage

DEFAULT_CONFIG = Path.home() / ".config" / "engineering-workflow" / "registry.json"
NODE_COMMANDS = ("neighbors", "impact", "spread", "lineage", "needs", "latest", "sessions", "licenses")
ATTRIBUTION = {"no": "no attribution", "credit": "credit the author", "notice": "keep the license text",
               "check": "license not stated, check"}


def config_path(given):
    return Path(given or os.environ.get("HARNESS_REGISTRY_CONFIG") or DEFAULT_CONFIG)


def refresh(store, given, rebuild=False):
    scanned = registry_scan.scan(json.loads(config_path(given).read_text(encoding="utf-8")))
    return graph.sync(store, scanned, rebuild)


def join(*parts):
    return "  ".join(str(part) for part in parts if part not in (None, "", []))


def show_find(rows):
    if not rows:
        return ["no match"]
    return [join(row["id"], row["name"] if row["name"] != row["id"].split(":", 1)[1] else None,
                 f"score {row['score']}" if row["score"] is not None else "glossary", row["path"]) for row in rows]


def show_neighbors(rows):
    lines = []
    for row in rows:
        detail = [row[key] for key in ("status", "state", "version", "scope", "result", "license") if row[key]]
        lines.append(join("->" if row["outgoing"] else "<-", row["link"], row["id"],
                          row["name"] if row["name"] != row["id"].split(":", 1)[1] else None,
                          f"[{', '.join(detail)}]" if detail else None))
    return lines or ["no links"]


def show_apps(rows):
    return [join(row["id"], "; ".join(row["how"]), f"open tasks {row['open_tasks']}" if row["open_tasks"] else None)
            for row in rows]


def show_impact(data):
    lines = ["depends on it:"] + [f"  {item}" for item in data["dependents"]] if data["dependents"] else []
    lines += ["apps:"] + [f"  {line}" for line in show_apps(data["apps"])] if data["apps"] else ["apps: none"]
    if data.get("used"):
        lines.append("used by agents:")
        for row in data["used"]:
            lines.append("  " + join(row["id"], row["agent"], f"{row['sessions']} sessions",
                                     f"{row['first']} to {row['last']}" if row["first"] and row["last"] else None))
    if data["records"]:
        lines += ["records:"] + [f"  {join(row['id'], row['name'], ', '.join(row['links']))}" for row in data["records"]]
    return lines


def show_spread(data):
    if not data["concerns"]:
        return ["this record names nothing under concerns"]
    lines = [f"concerns: {', '.join(data['concerns'])}"]
    lines += ["needs the same fix:"] + [f"  {line}" for line in show_apps(data["needs"])] if data["needs"] else [
        "needs the same fix: none"]
    lines += ["already has a record:"] + [f"  {join(row['id'], ', '.join(row['records']))}" for row in data["done"]]
    return lines


def show_lineage(rows):
    lines = []
    for row in rows:
        lines.append(join("  " * row["step"] + row["id"], row["file"],
                          f"from {row['source']}" if row["source"] else None,
                          f"license {row['license']}" if row["license"] else None,
                          f"made by {', '.join(row['made_by'])}" if row["made_by"] else None,
                          f"approved: {'; '.join(row['approved_by'])}" if row["approved_by"] else None))
        lines += ["  " * row["step"] + f"  made in {commit}" for commit in row.get("commits") or []]
    return lines


def show_needs(rows):
    return [join("  " * (row["step"] - 1) + row["id"], None if row["known"] else "(not found in any scanned file)")
            for row in rows] or ["needs nothing"]


def show_unused(data):
    lines = ["no app reaches these skills:"] + [f"  {join(row['id'], row['path'])}" for row in data["unreachable"]]
    if not data["unreachable"]:
        lines = ["every skill is reachable from an app"]
    if data["records_with_skills"]:
        lines += ["never named in a work record:"] + [f"  {row['id']}" for row in data["never_recorded"]]
    else:
        lines.append("no work record names a skill yet, so use cannot be judged")
    if data.get("usage_configured"):
        lines += ["no agent session used:"] + [f"  {row['id']}" for row in data["never_used"]]
    else:
        lines.append("no usage file is configured, so agent sessions cannot be counted")
    return lines


def show_sessions(rows):
    lines = []
    for row in rows:
        lines.append(join(row["name"], f"on {', '.join(row['machines'])}" if row["machines"] else "machine unknown",
                          row["session_id"]))
        lines.append(f"  {row['text']}")
        lines += [f"  holds {item['lane']}: {item['work']}" for item in row["holds"]]
    return lines or ["no sessions in WORKING.md"]


def show_licenses(rows, filtered=False):
    lines = [join(row["group"], row["license"], f"{row['assets']} assets", ATTRIBUTION.get(row["attribution"], row["attribution"]),
                  ", ".join(item.split(":", 1)[1] for item in row["sources"]), ", ".join(row["files"])) for row in rows]
    return lines or ["nothing here needs credit, a notice, or a check" if filtered else "no credited assets"]


def show_status(data):
    lines = [f"nodes {data['nodes']}  links {data['links']}  files {data['files']}",
             "  ".join(f"{kind} {total}" for kind, total in data["types"].items())]
    lines += [f"skipped {row['path']}: {row['error']}" for row in data["skipped"]]
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ask the registry. Files are scanned first, and only changed files "
                                                 "are written to the graph server.")
    parser.add_argument("--config", help="registry config (default: HARNESS_REGISTRY_CONFIG, then "
                                         "~/.config/engineering-workflow/registry.json)")
    parser.add_argument("--space", default=os.environ.get("HARNESS_REGISTRY_SPACE", "N"), help=argparse.SUPPRESS)
    parser.add_argument("--no-sync", action="store_true", help="answer from the graph as it is")
    parser.add_argument("--json", action="store_true", help="print the raw result")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("find", "dupes"):
        search = commands.add_parser(name)
        search.add_argument("words", nargs="+")
        search.add_argument("--limit", type=int, default=5)
        if name == "find":
            search.add_argument("--type", dest="kind")
    for name in NODE_COMMANDS:
        one = commands.add_parser(name)
        one.add_argument("node")
        if name == "neighbors":
            one.add_argument("--type", dest="kind")
        if name == "licenses":
            one.add_argument("--group")
            one.add_argument("--attribution", action="store_true", help="only what needs credit, a notice, or a check")
    commands.add_parser("unused")
    commands.add_parser("status")
    commands.add_parser("sync").add_argument("--rebuild", action="store_true")
    args = parser.parse_args(argv)
    try:
        store = graph.connect(args.space)
        if args.command == "sync":
            settings = json.loads(config_path(args.config).read_text(encoding="utf-8"))
            if settings.get("usage"):
                try:
                    registry_usage.update(settings)
                except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                    print(f"registry: usage not counted ({type(error).__name__}: {error})", file=sys.stderr)
            report = refresh(store, args.config, args.rebuild)
            result = {**report, "changed": len(report["changed"]), "removed": len(report["removed"])}
            lines = [f"changed {result['changed']}  removed {result['removed']}  nodes {result['nodes']}  "
                     f"links {result['links']}  files {result['files']}"] + [f"skipped {path}" for path in report["skipped"]]
        else:
            if not args.no_sync:
                try:
                    refresh(store, args.config)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    print(f"registry: files not scanned ({type(error).__name__}: {error}); answering from the graph "
                          "as it is", file=sys.stderr)
            if args.command in NODE_COMMANDS:
                matches = graph.resolve(store, args.node)
                if len(matches) != 1:
                    print("NOT FOUND" if not matches else "AMBIGUOUS, use one of:\n" + "\n".join(matches))
                    return 1
                node = matches[0]
            if args.command == "find":
                result = graph.find(store, args.words, args.kind, args.limit)
                lines = show_find(result)
            elif args.command == "dupes":
                result = graph.find(store, args.words, "skill", args.limit)
                lines = show_find(result)
            elif args.command == "neighbors":
                result = graph.neighbors(store, node, args.kind)
                lines = [node] + show_neighbors(result)
            elif args.command == "impact":
                result = graph.impact(store, node)
                lines = [node] + show_impact(result)
            elif args.command == "spread":
                result = graph.spread(store, node)
                lines = [node] + show_spread(result)
            elif args.command == "lineage":
                result = graph.lineage(store, node)
                lines = show_lineage(result)
            elif args.command == "needs":
                result = graph.needs(store, node)
                lines = [node] + show_needs(result)
            elif args.command == "latest":
                result = graph.latest(store, node)
                lines = [row["id"] for row in result]
            elif args.command == "sessions":
                result = graph.sessions(store, node)
                lines = [node] + show_sessions(result)
            elif args.command == "licenses":
                result = graph.licenses(store, node, args.group, args.attribution)
                lines = [node] + show_licenses(result, args.attribution)
            elif args.command == "unused":
                try:
                    usage = bool(json.loads(config_path(args.config).read_text(encoding="utf-8")).get("usage"))
                except (OSError, ValueError, AttributeError):
                    usage = False
                result = graph.unused(store, usage)
                lines = show_unused(result)
            else:
                result = graph.status(store)
                lines = show_status(result)
    except (graph.StoreError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"REGISTRY UNAVAILABLE: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    output = json.dumps(result, ensure_ascii=False, indent=1) if args.json else "\n".join(lines)
    sys.stdout.buffer.write((output + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
