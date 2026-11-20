import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None
    import msvcrt

BOARD = Path(".harness") / "board.json"
RECORDS = Path(".harness") / "records"
RUNNING = "run_queue.doing"
LANE = re.compile(r"^## Lane 1(?![0-9]).*?$(.*?)(?=^## |\Z)", re.S | re.M)
HOLDER = re.compile(r"session_id=([^\s,;:)`'\"<>]+)")
HANDED = re.compile(r"session_id=[^\s,;:)`'\"<>]+[^\n:]*:\s*\**STOPPED\b")
LOGS = Path(os.environ.get("HARNESS_RUN_LOGS") or Path.home() / ".cache" / "engineering-workflow" / "runs")
PROMPT = """You are a fresh session started by run_queue.py for exactly one task in this repository.

Task {id}: {title}
{note}
Read CLAUDE.md (or AGENTS.md), WORKING.md if it exists, and .harness/board.json first. Follow the project's rules.
Do only this task. Write its done line, implement it, run the checks the change needs, and get the reviews the rules
require. When it passes: set the task's status to "done" in .harness/board.json, write one work record with
`record.py new "<title>" --task {id}` from the engineering-workflow skill, commit only this task's files by name,
and push. If it cannot be finished, set the task to "blocked" with a note saying why, or add a decision for the
user with the default in use, commit that, and stop. Do not start another task.
Your last line must be either `DONE <commit hash>` or `STOPPED <reason>`."""


def load(root):
    data = json.loads((root / BOARD).read_text(encoding="utf-8"))
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list):
        raise ValueError("the board has no task list")
    tasks = [task for task in tasks if isinstance(task, dict) and isinstance(task.get("id"), str)]
    for task in tasks:
        after = task.get("after", [])
        if not isinstance(after, list) or not all(isinstance(name, str) for name in after):
            raise ValueError(f"task {task['id']}: after must be a list of task ids")
    return data, tasks


def next_task(tasks, owner=None):
    states = {task["id"]: task.get("status", "todo") for task in tasks}
    for task in tasks:
        after = task.get("after") if isinstance(task.get("after"), list) else []
        if task.get("status", "todo") != "todo" or (owner and task.get("owner") != owner):
            continue
        if all(states.get(name) == "done" for name in after):
            return task
    return None


def status_of(path, task_id):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    tasks = data.get("tasks") if isinstance(data, dict) else None
    for task in tasks if isinstance(tasks, list) else []:
        if isinstance(task, dict) and task.get("id") == task_id:
            return task.get("status")
    return None


def runner_dir(root):
    return Path(git(root, "rev-parse", "--absolute-git-dir"))


def refresh_page(root):
    try:
        subprocess.run([sys.executable, str(Path(__file__).with_name("board.py")), "render", str(root / BOARD)],
                       cwd=root, env={**os.environ, "HARNESS_BOARD_OPEN": "0"}, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        pass


def mark_doing(root, task_id, original):
    data = json.loads(original.decode("utf-8"))
    for task in data["tasks"]:
        if isinstance(task, dict) and task.get("id") == task_id:
            task["status"] = "doing"
    (root / BOARD).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (runner_dir(root) / RUNNING).write_text(json.dumps({"task": task_id, "pid": os.getpid(), "board": str((root / BOARD).resolve())}), encoding="utf-8")
    refresh_page(root)


def unmark(root, task_id, original):
    if status_of(root / BOARD, task_id) != "done":
        (root / BOARD).write_bytes(original)
    (runner_dir(root) / RUNNING).unlink(missing_ok=True)
    refresh_page(root)


def git(root, *args):
    return subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args], capture_output=True, text=True,
                          timeout=60, check=True).stdout.strip()


def upstream(root):
    branch = git(root, "symbolic-ref", "--short", "HEAD")
    remote = git(root, "config", "--get", f"branch.{branch}.remote")
    merge = git(root, "config", "--get", f"branch.{branch}.merge")
    return remote, merge


def pushed(root):
    head = git(root, "rev-parse", "HEAD")
    remote, merge = upstream(root)
    listed = git(root, "ls-remote", remote, merge).split()
    return bool(listed) and listed[0] == head


def advanced(root, start):
    if git(root, "rev-parse", "HEAD") == start:
        return False
    try:
        git(root, "merge-base", "--is-ancestor", start, "HEAD")
    except subprocess.CalledProcessError:
        return False
    return True


def front(text):
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end > 0 else ""


def recorded(root, task_id, since):
    folder = root / RECORDS
    if not folder.is_dir():
        return False
    pattern = re.compile(rf'^task:[ \t]*"?{re.escape(task_id)}"?[ \t]*$', re.M)
    for path in folder.glob("*.md"):
        try:
            if path.stat().st_mtime >= since and pattern.search(front(path.read_text(encoding="utf-8"))):
                return True
        except (OSError, UnicodeError):
            continue
    return False


def holders(root):
    try:
        text = (root / "WORKING.md").read_text(encoding="utf-8")
    except OSError:
        return None
    found = LANE.search(text)
    if not found:
        return None
    lines = re.split(r"\n(?=- )", found.group(1))
    return [name for line in lines if not HANDED.search(line) for name in HOLDER.findall(line)]


def take_lane(root, session, task):
    path = root / "WORKING.md"
    text = path.read_text(encoding="utf-8")
    found = LANE.search(text)
    line = (f"- runner (run_queue.py), session_id={session}: task {task['id']} ({task.get('title', '')}), started "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')}. Removed when the session ends.\n")
    head_end = text.find("\n", found.start())
    added = head_end < 0
    if added:
        text, head_end = text + "\n", len(text) + 1
    else:
        head_end += 1
    path.write_text(text[:head_end] + line + text[head_end:], encoding="utf-8")
    return added


def give_lane(root, session, added=False):
    path = root / "WORKING.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    cleaned = "".join(line for line in text.splitlines(keepends=True) if f"session_id={session}" not in line)
    if added and cleaned.endswith("\n"):
        cleaned = cleaned[:-1]
    if cleaned != text:
        path.write_text(cleaned, encoding="utf-8")
    committed = subprocess.run(["git", "-C", str(root), "show", "HEAD:./WORKING.md"], capture_output=True, text=True)
    return committed.returncode == 0 and f"session_id={session}" in committed.stdout


def command(agent, prompt, session, task):
    argv = shlex.split(agent) + ["-p", prompt, "--session-id", session]
    for key, flag in (("model", "--model"), ("effort", "--effort")):
        if isinstance(task.get(key), str) and re.fullmatch(r"[A-Za-z0-9._-]{1,60}", task[key]):
            argv += [flag, task[key]]
    return argv


def stop_group(process):
    for sig, wait in ((signal.SIGTERM, 5), (getattr(signal, "SIGKILL", signal.SIGTERM), 5)):
        try:
            if hasattr(os, "killpg"):
                os.killpg(process.pid, sig)
            else:
                process.kill()
        except (ProcessLookupError, PermissionError, OSError):
            return
        try:
            process.wait(timeout=wait)
            if not hasattr(os, "killpg"):
                return
        except subprocess.TimeoutExpired:
            continue


def launch(argv, root, minutes):
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as sink:
        try:
            process = subprocess.Popen(argv, cwd=root, stdout=sink, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                       start_new_session=hasattr(os, "killpg"))
        except OSError as error:
            return f"could not start the agent: {error}", 127
        try:
            code = process.wait(timeout=minutes * 60)
            note = ""
        except subprocess.TimeoutExpired:
            code, note = 124, f"\nTIMEOUT after {minutes} min"
        except BaseException:
            stop_group(process)
            raise
        stop_group(process)
        sink.seek(0)
        return sink.read() + note, code


def check(root, task, start_head, started, code):
    problems = []
    if code != 0:
        problems.append(f"the session exited with {code}")
    try:
        _, tasks = load(root)
        state = next((item.get("status") for item in tasks if item["id"] == task["id"]), None)
        if state != "done":
            problems.append(f"the task is {state or 'gone'} on the board, not done")
    except (OSError, ValueError) as error:
        problems.append(f"the board cannot be read ({error})")
    try:
        if not advanced(root, start_head):
            problems.append("no new commit on top of where the session started")
        elif not pushed(root):
            problems.append("the commit is not on the remote")
        if git(root, "status", "--porcelain", "--untracked-files=no"):
            problems.append("tracked files are left uncommitted")
    except (OSError, subprocess.SubprocessError) as error:
        problems.append(f"git could not be checked ({error})")
    if not recorded(root, task["id"], started):
        problems.append("no work record for the task")
    return problems


def run_one(root, task, agent, minutes, log, lane):
    session = str(uuid.uuid4())
    note = f"Note: {task['note']}\n" if isinstance(task.get("note"), str) and task["note"] else ""
    prompt = PROMPT.format(id=task["id"], title=task.get("title", ""), note=note)
    start_head = git(root, "rev-parse", "HEAD")
    started = time.time()
    problems, added = [], False
    original = (root / BOARD).read_bytes()
    try:
        mark_doing(root, task["id"], original)
        if lane:
            added = take_lane(root, session, task)
        output, code = launch(command(agent, prompt, session, task), root, minutes)
    finally:
        if lane:
            try:
                if give_lane(root, session, added):
                    problems.append("the session committed its Lane 1 line; WORKING.md needs a commit without it")
            except (OSError, subprocess.SubprocessError) as error:
                problems.append(f"lane 1 could not be released ({error})")
        if status_of(root / BOARD, task["id"]) is None:
            problems.append("the board cannot be read or the task is gone after the session")
        try:
            unmark(root, task["id"], original)
        except (OSError, subprocess.SubprocessError) as error:
            problems.append(f"the board could not be restored to todo ({error})")
    log.write(f"\n=== {task['id']} session {session} exit {code}\n{output}\n")
    log.flush()
    problems = check(root, task, start_head, started, code) + problems
    last = output.strip().splitlines()[-1] if output.strip() else ""
    return session, problems, last


class Busy(RuntimeError):
    pass


def hold(root):
    path = Path(git(root, "rev-parse", "--absolute-git-dir")) / "run_queue.lock"
    handle = open(path, "a+")
    try:
        if fcntl:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as error:
        handle.close()
        raise Busy("another run_queue.py is working in this repository") from error
    return handle


def main(argv=None):
    parser = argparse.ArgumentParser(description="Work through the board one task per fresh agent session: start a new "
                                                 "session for the next ready task, check its commit, push, record "
                                                 "and board state, then start the next. Stops at the first problem.")
    parser.add_argument("root", nargs="?", default=".", help="project root with .harness/board.json")
    parser.add_argument("--max", type=int, default=1, help="tasks to run at most (default 1)")
    parser.add_argument("--owner", help="only tasks with this owner")
    parser.add_argument("--minutes", type=int, default=90, help="time limit per session")
    parser.add_argument("--agent", default=os.environ.get("HARNESS_RUN_AGENT", "claude"),
                        help="agent command; -p, the prompt and --session-id are added")
    parser.add_argument("--lane", action="store_true", help="write the session on WORKING.md's Lane 1 while it runs")
    parser.add_argument("--dry-run", action="store_true", help="show the next task and the command, run nothing")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        load(root)
        git(root, "rev-parse", "HEAD")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    if args.dry_run:
        _, tasks = load(root)
        task = next_task(tasks, args.owner)
        if not task:
            print("no ready task left")
            return 0
        print(f"next: {task['id']} {task.get('title', '')}")
        print("command: " + shlex.join(command(args.agent, "<prompt>", "<new uuid>", task)))
        return 0
    try:
        lock = hold(root)
    except (Busy, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 3
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"{root.name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    ran = 0
    with lock, log_path.open("a", encoding="utf-8") as log:
        while ran < args.max:
            held = holders(root)
            if held is not None and not args.lane:
                print("WORKING.md has a Lane 1 section: run with --lane so the session may edit lane 1 files",
                      file=sys.stderr)
                return 2
            if held:
                print(f"Lane 1 already lists {', '.join(held)}: the runner starts only when no other session holds it",
                      file=sys.stderr)
                return 3
            if git(root, "status", "--porcelain", "--untracked-files=no"):
                print("tracked files have uncommitted changes: commit or stash them first", file=sys.stderr)
                return 3
            try:
                _, tasks = load(root)
            except (OSError, ValueError) as error:
                print(f"STOP: the board cannot be read ({error})")
                return 1
            task = next_task(tasks, args.owner)
            if not task:
                print("no ready task left")
                break
            print(f"start {task['id']}: {task.get('title', '')}", flush=True)
            session, problems, last = run_one(root, task, args.agent, args.minutes, log, held is not None)
            if problems:
                print(f"STOP at {task['id']} (session {session}): " + "; ".join(problems))
                print(f"agent said: {last}")
                print(f"log: {log_path}")
                return 1
            print(f"done {task['id']}: {last}")
            ran += 1
    print(f"log: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
