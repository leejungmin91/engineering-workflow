"""Build and query a metadata-only skill index."""

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

FIELD = re.compile(r"^(name|description):[ \t]*(.*)$")
SKILL_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}(?::[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63})?")
TERM = re.compile(r"[^\W_]+")
BLOCK_SCALAR = re.compile(r"[|>](?:[+-][1-9]?|[1-9][+-]?)?")
KOREAN_KEYWORDS = {
    "하네스": "harness", "루프": "loop", "그래프": "graph",
    "의존성": "dependency", "교차검토": "independent review",
    "코드리뷰": "code review", "검토": "review", "보고서": "report",
    "리포트": "report", "테스트": "test", "검증": "verification",
    "디버깅": "debug", "버그": "bug", "릴리즈": "release",
}
STOP_WORDS = {"a", "an", "the", "to", "for", "and", "of", "it", "in", "with", "this", "use", "when"}


def frontmatter(path):
    with path.open(encoding="utf-8-sig") as source:
        if source.readline().strip() != "---":
            return {}
        header = []
        for line in source:
            if line.rstrip() == "---":
                break
            if len(header) == 128:
                return {}
            header.append(line.rstrip())
        else:
            return {}
    fields = {}
    for index, line in enumerate(header):
        field = FIELD.fullmatch(line)
        if not field:
            continue
        key, value = field.groups()
        continuation = []
        for following in header[index + 1:]:
            if following and not following[0].isspace():
                break
            continuation.append(following.strip())
        if not value.startswith(('"', "'")):
            value = value.split(" #", 1)[0].rstrip()
        if BLOCK_SCALAR.fullmatch(value):
            value = " ".join(continuation).strip()
        elif continuation:
            value = " ".join([value, *continuation]).strip()
        if value.startswith('"') and value.endswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("''", "'")
        fields[key] = value
    return fields


def catalog_rows(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        result = payload.get("result", payload)
        if isinstance(result, dict) and isinstance(result.get("data"), list):
            return [row for entry in result["data"] if isinstance(entry, dict)
                    for row in entry.get("skills", [])]
    raise ValueError("Expected an array of skills or a Codex skills/list response.")


def build_index(roots, catalogs):
    rows = []
    for root in roots:
        for child in root.iterdir():
            path = child / "SKILL.md"
            if path.is_file():
                rows.append({**frontmatter(path), "path": str(path.resolve())})
    for path in catalogs:
        rows.extend(catalog_rows(json.loads(path.read_text(encoding="utf-8"))))

    unique = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("enabled") is False:
            continue
        fields = {key: row.get(key) for key in ("name", "description", "path")}
        if (all(isinstance(value, str) and value.strip() for value in fields.values())
                and SKILL_NAME.fullmatch(fields["name"])):
            unique[(fields["name"], fields["path"])] = fields
    return [unique[key] for key in sorted(unique)]


def terms(text):
    return set(TERM.findall(text.casefold())) - STOP_WORDS


def find(rows, query, limit, minimum_score=1):
    aliases = " ".join(english for korean, english in KOREAN_KEYWORDS.items() if korean in query)
    alias_terms = terms(aliases)
    keywords = terms(query) | alias_terms
    results = []
    for row in rows:
        if not SKILL_NAME.fullmatch(row["name"]):
            continue
        name = row["name"].casefold()
        name_hits = keywords & terms(name)
        description_hits = keywords & terms(row["description"])
        exact = query.strip().casefold() == name or query.strip().casefold() == name.split(":")[-1]
        score = 8 * exact + 3 * len(name_hits) + len(description_hits - name_hits)
        score += len(description_hits & alias_terms)
        if score >= minimum_score:
            results.append((-score, row["name"], row["path"], row))
    return [result[-1] for result in sorted(results)[:limit]]


def write_index(path, rows):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        json.dump(rows, file, ensure_ascii=False)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def prompt_hook(rows, event, limit):
    if not isinstance(event, dict) or event.get("hook_event_name") != "UserPromptSubmit":
        return None
    prompt = event.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    candidates = find(rows, prompt, len(rows), minimum_score=2)
    if not candidates:
        return None
    names = "; ".join(list(dict.fromkeys(row["name"] for row in candidates))[:limit])
    return {"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": f"Skill index candidates: {names}. Confirm relevance in the active catalog before loading a skill.",
    }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    build = commands.add_parser("build")
    build.add_argument("index", type=Path)
    build.add_argument("--root", type=Path, action="append", default=[])
    build.add_argument("--catalog", type=Path, action="append", default=[])
    search = commands.add_parser("find")
    search.add_argument("index", type=Path)
    search.add_argument("query")
    search.add_argument("--limit", type=int, choices=range(1, 21), default=5)
    hook = commands.add_parser("hook")
    hook.add_argument("index", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "build":
            if not args.root and not args.catalog:
                parser.error("build needs --root or --catalog")
            rows = build_index(args.root, args.catalog)
            write_index(args.index, rows)
            print(json.dumps({"skills": len(rows)}))
            return 0
        rows = json.loads(args.index.read_text(encoding="utf-8"))
        if args.action == "hook":
            output = prompt_hook(rows, json.load(sys.stdin.buffer), 3)
            if output:
                print(json.dumps(output))
        else:
            print(json.dumps(find(rows, args.query, args.limit)))
    except (OSError, ValueError, KeyError, TypeError):
        if args.action == "hook":
            return 0
        print("Could not read the skill metadata or index.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
