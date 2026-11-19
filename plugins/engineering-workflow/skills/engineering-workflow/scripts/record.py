import argparse
import datetime
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import registry_scan

FIELDS = ("task", "skills", "model", "commits", "review", "concerns", "decisions", "keywords")
BODY_LINES = 15
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def flat(value):
    return " ".join(str(value).replace('"', "'").split())


def render(key, title, fields, body):
    lines = ["---", f"id: {key}", f'title: "{flat(title)}"']
    lines += [f'{name}: "{flat(fields[name])}"' for name in FIELDS if fields.get(name)]
    return "\n".join(lines + ["---", "", body.strip(), ""])


def new(args, body):
    title = flat(args.title)
    date = args.date or datetime.date.today().isoformat()
    if not title:
        return 2, "the title is empty"
    if not DATE.fullmatch(date):
        return 2, "the date must look like 2026-11-19"
    if not body.strip():
        return 2, "the record needs a body: what was done, why, and what was dropped"
    folder = Path(args.root) / ".harness" / "records"
    key = f"{date}-{registry_scan.slug(title)[:60].strip('-')}"
    path = folder / f"{key}.md"
    folder.mkdir(parents=True, exist_ok=True)
    fields = {name: getattr(args, name) for name in FIELDS}
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(render(key, title, fields, body))
    except FileExistsError:
        return 1, f"{path} exists; pick another title or edit that record"
    return 0, str(path)


def problems(path):
    try:
        content = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        return [f"cannot be read: {error}"], []
    fields, body = registry_scan.frontmatter(content)
    errors, warnings = [], []
    if not fields:
        return ["has no frontmatter"], []
    if str(fields.get("id") or "") != path.stem:
        errors.append(f"id is '{fields.get('id')}', the file name says '{path.stem}'")
    if not isinstance(fields.get("title"), str) or not fields["title"].strip():
        errors.append("has no title")
    if not body.strip():
        errors.append("has no body")
    for name in FIELDS:
        if name in fields and not isinstance(fields[name], str):
            errors.append(f"{name} must be one line of text")
    if not DATE.match(path.stem):
        warnings.append("file name does not start with a date, so it has no place in time")
    count = len([line for line in body.strip().splitlines() if line.strip()])
    if count > BODY_LINES:
        warnings.append(f"body has {count} lines; keep it under about {BODY_LINES}")
    return errors, warnings


def check(root):
    folder = Path(root) / ".harness" / "records"
    lines, failed = [], False
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        errors, warnings = problems(path)
        failed = failed or bool(errors)
        lines += [f"{path.name}: error: {item}" for item in errors]
        lines += [f"{path.name}: warning: {item}" for item in warnings]
    return (1 if failed else 0), lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write and check work records: one small file per finished task in "
                                                 ".harness/records.")
    parser.add_argument("--root", default=".", help="repository folder (default: the current folder)")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("new", help="write a record; the body comes from --body or standard input")
    create.add_argument("title")
    create.add_argument("--body")
    create.add_argument("--date")
    for name in FIELDS:
        create.add_argument(f"--{name}")
    commands.add_parser("check", help="check every record in the folder")
    args = parser.parse_args(argv)
    if args.command == "new":
        body = args.body if args.body is not None else ("" if sys.stdin.isatty() else sys.stdin.read())
        code, message = new(args, body)
        print(message, file=sys.stdout if code == 0 else sys.stderr)
        return code
    code, lines = check(args.root)
    sys.stdout.buffer.write(("\n".join(lines + ["records ok" if code == 0 else "records have errors"]) + "\n")
                            .encode("utf-8"))
    return code


if __name__ == "__main__":
    sys.exit(main())
