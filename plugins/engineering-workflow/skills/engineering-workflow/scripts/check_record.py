"""Check declared workflow evidence without running any recorded command."""

import argparse
import json
import re
import sys
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
STATUSES = ("passed", "failed", "blocked", "unverified")


def identifier(value, label):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError(f"invalid {label} ID")
    return value


def entries(value, kind, location="record"):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{location}: expected at least one {kind}")
    result = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{location}: expected a {kind} object")
        key = identifier(item.get("id"), kind)
        if key in result:
            raise ValueError(f"{location}: duplicate {kind} {key}")
        result[key] = item
    return result


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def issues(record, snapshot):
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    tasks = entries(record.get("tasks"), "task")
    dependencies, findings = {}, {}
    for task_id, task in tasks.items():
        needs = task.get("after")
        if not isinstance(needs, list):
            raise ValueError(f"{task_id}: after must be a list")
        dependencies[task_id] = [identifier(dep, "dependency") for dep in needs]
        for dep in dependencies[task_id]:
            if dep not in tasks:
                raise ValueError(f"{task_id}: unknown dependency {dep}")

        findings[task_id] = []
        for check_id, check in entries(task.get("checks"), "check", task_id).items():
            status = check.get("status")
            if status not in STATUSES:
                raise ValueError(f"{task_id}/{check_id}: invalid status")
            label = f"{task_id}/{check_id}"
            if status != "passed":
                findings[task_id].append(f"{label}: {status}")
                continue
            if not nonempty(check.get("evidence")):
                findings[task_id].append(f"{label}: missing evidence")
            if check.get("snapshot") != snapshot:
                findings[task_id].append(f"{label}: stale evidence")

    try:
        ordered = list(TopologicalSorter(dependencies).static_order())
    except CycleError:
        raise ValueError("dependency cycle") from None

    pending, result = set(), []
    for task_id in ordered:
        blockers = sorted(set(dependencies[task_id]) & pending)
        if blockers:
            result.append(f"{task_id}: waiting for {', '.join(blockers)}")
        result.extend(findings[task_id])
        if blockers or findings[task_id]:
            pending.add(task_id)
    return result


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", help="UTF-8 JSON file, or '-' for standard input")
    parser.add_argument("--snapshot", required=True, help="identity of the current work")
    args = parser.parse_args()
    if not nonempty(args.snapshot):
        parser.error("--snapshot must not be blank")
    try:
        raw = sys.stdin.read() if args.record == "-" else Path(args.record).read_text(encoding="utf-8")
        problems = issues(json.loads(raw, object_pairs_hook=unique_keys), args.snapshot)
    except (OSError, ValueError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    if problems:
        print("NOT READY")
        for problem in problems:
            print(problem)
        return 1
    print("READY: all declared checks record a pass for this snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
