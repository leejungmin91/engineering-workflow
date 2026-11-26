import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

GLOBS = ("*_checks*", "*_work")
DAYS = 2
MIN_GB = 10.0


def free_gb(path):
    stats = os.statvfs(path)
    return stats.f_bavail * stats.f_frsize / 1024 ** 3


def newest(path):
    latest = path.lstat().st_mtime
    for root, folders, files in os.walk(path):
        for name in folders + files:
            try:
                latest = max(latest, os.lstat(os.path.join(root, name)).st_mtime)
            except OSError:
                continue
    return latest


def size(path):
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total


def tracked(project, path):
    try:
        result = subprocess.run(["git", "-C", str(project), "ls-files", "--", str(path.relative_to(project))],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return True
    return result.returncode != 0 or bool(result.stdout.strip())


def busy(path):
    if not shutil.which("lsof"):
        return False
    try:
        result = subprocess.run(["lsof", "+D", str(path)], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return True
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(result.stdout.strip())


def mentioned(project):
    working = project / "WORKING.md"
    try:
        return working.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def old(project, folder, globs, days, now):
    base = project / folder
    if not base.is_dir():
        return []
    text = mentioned(project)
    limit = now - days * 86400
    found = []
    for path in sorted(base.iterdir()):
        if path.is_symlink() or not path.is_dir() or path.name.endswith(".moving"):
            continue
        if not any(fnmatch.fnmatch(path.name, pattern) for pattern in globs):
            continue
        if path.name in text or newest(path) > limit or tracked(project, path):
            continue
        found.append(path)
    return found


def equal(one, two):
    with open(one, "rb") as a, open(two, "rb") as b:
        while True:
            chunk = a.read(1 << 20)
            if chunk != b.read(1 << 20):
                return False
            if not chunk:
                return True


def entries(path):
    found = {}
    for root, folders, files in os.walk(path):
        for name in folders + files:
            full = os.path.join(root, name)
            found[os.path.relpath(full, path)] = full
    return found


def kind(path):
    if os.path.islink(path):
        return "link"
    return "folder" if os.path.isdir(path) else "file"


def same(left, right):
    one, two = entries(left), entries(right)
    if one.keys() != two.keys():
        return False
    for key, path in one.items():
        other = two[key]
        if kind(path) != kind(other):
            return False
        if kind(path) == "link" and os.readlink(path) != os.readlink(other):
            return False
        if kind(path) == "file" and not equal(path, other):
            return False
    return True


def changed_since(spare, target, since):
    copied = entries(target)
    for key, path in entries(spare).items():
        if key not in copied or os.lstat(path).st_mtime >= since:
            return True
    return os.lstat(spare).st_mtime >= since


def links_outside(path):
    root = path.resolve()
    for key, full in entries(path).items():
        if not os.path.islink(full):
            continue
        aim = os.readlink(full)
        if os.path.isabs(aim):
            continue
        written = os.path.normpath(os.path.join(os.path.dirname(key), aim))
        if written == ".." or written.startswith(".." + os.sep):
            return True
        try:
            (Path(full).parent / aim).resolve().relative_to(root)
        except ValueError:
            return True
    return False


def move(source, target):
    if target.exists() or target.is_symlink():
        return "target exists"
    spare = source.with_name(source.name + ".moving")
    if spare.exists() or spare.is_symlink():
        return "spare exists"
    if links_outside(source):
        return "has relative links that point outside the folder"
    if busy(source):
        return "in use"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=True)
    since = time.time()
    if not same(source, target) or busy(source):
        shutil.rmtree(target)
        return "changed during copy; left in place"
    os.rename(source, spare)
    try:
        os.symlink(target, source)
    except OSError as error:
        os.rename(spare, source)
        shutil.rmtree(target, ignore_errors=True)
        return f"could not link: {error}; left in place"
    if changed_since(spare, target, since) or busy(spare):
        return f"changed during move; original kept at {spare.name}"
    shutil.rmtree(spare)
    return "moved"


def archive(project, to, folder, globs, days, dry_run, now):
    rows = []
    for path in old(project, folder, globs, days, now):
        target = to / project.name / path.relative_to(project)
        bytes_ = size(path)
        try:
            status = "would move" if dry_run else move(path, target)
        except OSError as error:
            status = f"failed: {error}"
        rows.append({"path": str(path), "target": str(target), "bytes": bytes_, "status": status})
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check free disk space and move old check folders to an archive "
                                                 "disk, leaving a link at the old path.")
    sub = parser.add_subparsers(dest="command", required=True)
    space = sub.add_parser("space", help="exit 1 when free space is below --min-gb")
    space.add_argument("path", nargs="?", default="/")
    space.add_argument("--min-gb", type=float, default=float(os.environ.get("HARNESS_DISK_MIN_GB", MIN_GB)))
    for name in ("old", "archive"):
        command = sub.add_parser(name)
        command.add_argument("project")
        command.add_argument("--folder", default=".harness")
        command.add_argument("--glob", action="append")
        command.add_argument("--days", type=float, default=DAYS)
        if name == "archive":
            command.add_argument("--to", required=True)
            command.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "space":
        gb = free_gb(args.path)
        print(json.dumps({"path": args.path, "free_gb": round(gb, 1), "min_gb": args.min_gb}))
        return 0 if gb >= args.min_gb else 1
    project = Path(args.project).expanduser().resolve()
    globs = tuple(args.glob or GLOBS)
    now = time.time()
    if args.command == "old":
        rows = [{"path": str(path), "bytes": size(path)} for path in old(project, args.folder, globs, args.days, now)]
    else:
        to = Path(args.to).expanduser()
        if not to.is_dir():
            print(f"archive folder {to} is missing; is the disk mounted?", file=sys.stderr)
            return 2
        rows = archive(project, to.resolve(), args.folder, globs, args.days, args.dry_run, now)
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 1 if any(row.get("status") not in (None, "moved", "would move") for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
