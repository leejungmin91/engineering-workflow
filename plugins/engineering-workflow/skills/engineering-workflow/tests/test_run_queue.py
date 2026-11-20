import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import unittest.mock
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_queue.py"
FAKE = textwrap.dedent('''
    import json, os, re, subprocess, sys, time
    from pathlib import Path
    prompt = sys.argv[sys.argv.index("-p") + 1]
    session = sys.argv[sys.argv.index("--session-id") + 1]
    task = re.search(r"Task (\\S+):", prompt).group(1)
    mode = os.environ.get("FAKE_MODE", "ok")
    Path(".seen").write_text(Path("WORKING.md").read_text() if Path("WORKING.md").exists() else "", encoding="utf-8")
    Path(".seen_board").write_text(Path(".harness/board.json").read_text(encoding="utf-8"), encoding="utf-8")
    pages = Path(os.environ.get("HARNESS_BOARD_HOME", "/nonexistent"))
    Path(".seen_html").write_text("".join(page.read_text(encoding="utf-8") for page in sorted(pages.rglob("*.html"))) if pages.is_dir() else "", encoding="utf-8")
    Path(".args").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
    if mode == "sleep":
        time.sleep(5)
    if mode == "sleepmark":
        time.sleep(3)
        Path("late.txt").write_text("x")
    if mode == "child":
        subprocess.Popen([sys.executable, "-c", "import time, pathlib; time.sleep(2); pathlib.Path('late.txt').write_text('x')"])
        time.sleep(30)
    if mode in ("commitworking", "editclaim"):
        text = Path("WORKING.md").read_text()
        if mode == "editclaim":
            text = text.replace("Removed when the session ends.", "now halfway")
        Path("WORKING.md").write_text(text)
        if mode == "commitworking":
            subprocess.run(["git", "add", "WORKING.md"], check=True)
    if mode == "addlane":
        Path("WORKING.md").write_text("## Lane 1: build\\n\\n## Lane 2\\n")
        subprocess.run(["git", "add", "WORKING.md"], check=True)
    if mode == "fail":
        print("STOPPED broke"); sys.exit(3)
    board = json.loads(Path(".harness/board.json").read_text())
    for item in board["tasks"]:
        if item["id"] == task and mode != "notdone":
            item["status"] = "done"
    Path(".harness/board.json").write_text(json.dumps(board))
    if mode == "wrongrecord":
        Path(f".harness/records/{task}.md").write_text(f"---\\nid: {task}\\ntitle: t\\ntask: T2\\n---\\ntask: {task}\\n")
    elif mode != "norecord":
        Path(f".harness/records/{task}.md").write_text(f"---\\nid: {task}\\ntitle: t\\ntask: {task}\\n---\\nbody\\n")
    if mode == "badboard":
        Path(".harness/board.json").write_text("{")
    if mode == "dirty":
        Path("tracked.txt").write_text("changed")
    run = lambda *a: subprocess.run(["git", *a], check=True, capture_output=True)
    run("add", ".harness")
    run("commit", "-q", "-m", f"work {task}")
    if mode != "nopush":
        run("push", "-q")
    print(f"DONE {task}")
''')


class RunQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root, remote = base / "app", base / "remote.git"
        env = {**os.environ, "GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@a", "GIT_COMMITTER_NAME": "a",
               "GIT_COMMITTER_EMAIL": "a@a"}
        self.env = {**env, "HARNESS_RUN_LOGS": str(base / "logs"), "HARNESS_BOARD_HOME": str(base / "boards")}
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        (self.root / ".harness" / "records").mkdir(parents=True)
        self.board([{"id": "T1", "title": "first", "status": "todo"},
                    {"id": "T2", "title": "second", "status": "todo", "after": ["T1"], "model": "sonnet",
                     "effort": "low"},
                    {"id": "T3", "title": "third", "status": "todo", "after": ["T9"]}])
        (self.root / "tracked.txt").write_text("x")
        (self.root / ".gitignore").write_text(".seen\n.seen_board\n.seen_html\n.args\n")
        self.git = lambda *a: subprocess.run(["git", "-C", str(self.root), *a], check=True, capture_output=True,
                                             env=env, text=True).stdout
        self.git("add", ".")
        self.git("commit", "-q", "-m", "start")
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "-u", "origin", "main")
        self.agent = base / "fake_agent.py"
        self.agent.write_text(FAKE)

    def board(self, tasks):
        (self.root / ".harness" / "board.json").write_text(json.dumps({"title": "x", "tasks": tasks}))

    def run_queue(self, *args, mode="ok"):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.root), "--agent",
                               f"{sys.executable} {self.agent}", *args], capture_output=True, text=True,
                              env={**self.env, "FAKE_MODE": mode}, cwd=self.root)

    def states(self):
        tasks = json.loads((self.root / ".harness" / "board.json").read_text())["tasks"]
        return {task["id"]: task["status"] for task in tasks}

    def test_runs_ready_tasks_one_session_each_and_passes_model_and_effort(self):
        result = self.run_queue("--max", "5")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.states(), {"T1": "done", "T2": "done", "T3": "todo"})
        self.assertIn("no ready task left", result.stdout)
        args = json.loads((self.root / ".args").read_text())
        self.assertEqual(args[args.index("--model") + 1], "sonnet")
        self.assertEqual(args[args.index("--effort") + 1], "low")
        self.assertEqual(self.git("log", "--format=%s", "-3").split("\n")[:2], ["work T2", "work T1"])

    def test_a_running_task_is_marked_doing_and_restored_to_todo_when_it_fails(self):
        result = self.run_queue("--max", "5", mode="fail")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        seen = json.loads((self.root / ".seen_board").read_text(encoding="utf-8"))
        self.assertEqual({task["id"]: task["status"] for task in seen["tasks"]}["T1"], "doing")
        self.assertEqual(self.states()["T1"], "todo")
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=no").strip(), "")
        marker = Path(self.git("rev-parse", "--absolute-git-dir").strip()) / "run_queue.doing"
        self.assertFalse(marker.exists())

    def test_a_failed_run_restores_the_board_bytes_exactly_even_with_crlf(self):
        original = json.dumps({"title": "x", "tasks": [{"id": "T1", "title": "first", "status": "todo"}]},
                              indent=2).replace("\n", "\r\n").encode("utf-8")
        board_file = self.root / ".harness" / "board.json"
        board_file.write_bytes(original)
        self.git("add", ".harness/board.json")
        self.git("commit", "-q", "-m", "crlf board")
        self.git("push", "-q")
        result = self.run_queue("--max", "5", mode="fail")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(board_file.read_bytes(), original)

    def test_the_board_page_is_rebuilt_while_a_task_runs_and_after_it_ends(self):
        self.board([{"id": "T1", "title": "first", "status": "todo"}])
        self.git("add", ".harness/board.json")
        self.git("commit", "-q", "-m", "one task")
        self.git("push", "-q")
        result = self.run_queue("--max", "5", mode="fail")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        during = (self.root / ".seen_html").read_text(encoding="utf-8")
        self.assertIn('class="spin"', during)
        after = "".join(page.read_text(encoding="utf-8") for page in Path(self.env["HARNESS_BOARD_HOME"]).rglob("*.html"))
        self.assertTrue(after)
        self.assertNotIn('class="spin"', after)

    def test_stops_at_the_first_task_that_did_not_finish_cleanly(self):
        for mode, words in (("notdone", "not done"), ("nopush", "not on the remote"), ("norecord", "no work record"),
                            ("fail", "exited with 3"), ("dirty", "uncommitted"), ("wrongrecord", "no work record"),
                            ("badboard", "board cannot be read")):
            with self.subTest(mode=mode):
                self.setUp()
                result = self.run_queue("--max", "5", mode=mode)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("STOP at T1", result.stdout)
                self.assertIn(words, result.stdout)
                self.assertNotIn("start T2", result.stdout)

    def test_time_limit_stops_the_run(self):
        sys.path.insert(0, str(SCRIPT.parent))
        import run_queue
        log = Path(self.tmp.name) / "log.txt"
        with log.open("w") as handle, unittest.mock.patch.dict(os.environ, {"FAKE_MODE": "sleep"}):
            _, problems, _ = run_queue.run_one(self.root, {"id": "T1", "title": "first"},
                                               f"{sys.executable} {self.agent}", 0.02, handle, False)
        self.assertIn("the session exited with 124", problems)

    def test_lane_one_is_taken_for_the_session_and_given_back(self):
        working = "# Who\n\n## Lane 1: build\n\n- build, session_id=old-1: **STOPPED** for the runner\n\n## Lane 2\n"
        (self.root / "WORKING.md").write_text(working)
        self.git("add", "WORKING.md")
        self.git("commit", "-q", "-m", "working")
        self.git("push", "-q")
        refused = self.run_queue()
        self.assertEqual(refused.returncode, 2)
        result = self.run_queue("--lane")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        args = json.loads((self.root / ".args").read_text())
        session = args[args.index("--session-id") + 1]
        self.assertIn(f"session_id={session}", (self.root / ".seen").read_text())
        self.assertEqual((self.root / "WORKING.md").read_text(), working)
        (self.root / "WORKING.md").write_text(working.replace("**STOPPED** for the runner", "working"))
        self.git("commit", "-q", "-am", "busy")
        self.git("push", "-q")
        busy = self.run_queue("--lane")
        self.assertEqual(busy.returncode, 3)
        self.assertIn("old-1", busy.stderr)

    def test_a_timeout_also_stops_what_the_session_started(self):
        sys.path.insert(0, str(SCRIPT.parent))
        import run_queue
        log = Path(self.tmp.name) / "log2.txt"
        with log.open("w") as handle, unittest.mock.patch.dict(os.environ, {"FAKE_MODE": "child"}):
            _, problems, _ = run_queue.run_one(self.root, {"id": "T1", "title": "first"},
                                               f"{sys.executable} {self.agent}", 0.02, handle, False)
        self.assertIn("the session exited with 124", problems)
        time.sleep(3)
        self.assertFalse((self.root / "late.txt").exists())

    def test_a_claim_committed_or_edited_by_the_session_is_still_released(self):
        working = "## Lane 1: build\n\n- build, session_id=old: STOPPED\n\n## Lane 2\n"
        (self.root / "WORKING.md").write_text(working)
        self.git("add", "WORKING.md")
        self.git("commit", "-q", "-m", "working")
        self.git("push", "-q")
        self.board([{"id": "Tedit", "title": "x", "status": "todo"}, {"id": "Tcommit", "title": "y", "status": "todo"}])
        self.git("commit", "-q", "-am", "board")
        self.git("push", "-q")
        result = self.run_queue("--lane", mode="editclaim")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / "WORKING.md").read_text(), working)
        result = self.run_queue("--lane", mode="commitworking")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("committed its Lane 1 line", result.stdout)
        self.assertNotIn("runner", (self.root / "WORKING.md").read_text())
        self.assertIn("runner", self.git("show", "origin/main:WORKING.md"))

    def test_lane_markers_placeholders_and_a_heading_without_a_newline(self):
        for text, code in (("## Lane 1\n\n- alice, session_id=live: fix STOPPED status rendering\n", 3),
                           ("## Lane 1\n\n(none. One line: session name, session_id=<id>, the task.)\n", 0),
                           ("## Lane 1", 0)):
            with self.subTest(text=text):
                self.setUp()
                (self.root / "WORKING.md").write_text(text)
                self.git("add", "WORKING.md")
                self.git("commit", "-q", "-m", "working")
                self.git("push", "-q")
                result = self.run_queue("--lane")
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                self.assertEqual((self.root / "WORKING.md").read_text(), text)

    def test_an_interrupted_runner_stops_its_session_and_a_bad_board_is_refused(self):
        process = subprocess.Popen([sys.executable, str(SCRIPT), str(self.root), "--agent", f"{sys.executable} {self.agent}"],
                                   env={**self.env, "FAKE_MODE": "sleepmark"}, cwd=self.root,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(1.5)
        process.send_signal(2)
        process.wait(timeout=20)
        time.sleep(3)
        self.assertFalse((self.root / "late.txt").exists())
        self.board([{"id": "T1", "title": "x", "status": "blocked"}, {"id": "T2", "title": "y", "after": "T1"}])
        self.git("commit", "-q", "-am", "bad after")
        self.git("push", "-q")
        self.assertEqual(self.run_queue().returncode, 2)

    def test_a_lane_section_added_by_a_session_is_honoured_in_the_next_round(self):
        result = self.run_queue("--max", "2", mode="addlane")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.states()["T1"], "done")
        self.assertNotEqual(self.states()["T2"], "done")

    def test_only_one_runner_per_repository_and_a_new_commit_must_build_on_the_start(self):
        sys.path.insert(0, str(SCRIPT.parent))
        import run_queue
        held = run_queue.hold(self.root)
        try:
            self.assertEqual(self.run_queue().returncode, 3)
        finally:
            held.close()
        start = self.git("rev-parse", "HEAD").strip()
        (self.root / "tracked.txt").write_text("y")
        self.git("commit", "-q", "-am", "next")
        self.assertTrue(run_queue.advanced(self.root, start))
        self.git("reset", "-q", "--hard", "HEAD~1")
        self.git("commit", "-q", "--allow-empty", "-m", "sibling")
        later = self.git("rev-parse", "HEAD").strip()
        self.git("reset", "-q", "--hard", "HEAD~1")
        (self.root / "tracked.txt").write_text("z")
        self.git("commit", "-q", "-am", "other")
        self.assertFalse(run_queue.advanced(self.root, later))

    def test_a_remote_with_a_slash_in_its_name(self):
        remote = self.git("remote", "get-url", "origin").strip()
        self.git("remote", "rename", "origin", "team/origin")
        self.git("branch", "-q", "--set-upstream-to", "team/origin/main")
        self.assertEqual(self.git("config", "branch.main.remote").strip(), "team/origin")
        self.assertTrue(remote)
        result = self.run_queue()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_committed_claim_is_found_in_a_project_below_the_repository_root(self):
        sys.path.insert(0, str(SCRIPT.parent))
        import run_queue
        mono = Path(self.tmp.name) / "mono"
        app = mono / "apps" / "app"
        app.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(mono)], check=True)
        (app / "WORKING.md").write_text("## Lane 1\n- runner, session_id=abc: task\n")
        (mono / "WORKING.md").write_text("## Lane 1\n")
        subprocess.run(["git", "-C", str(mono), "add", "."], check=True)
        subprocess.run(["git", "-C", str(mono), "commit", "-q", "-m", "x"], check=True, env=self.env)
        self.assertTrue(run_queue.give_lane(app, "abc"))
        self.assertEqual((app / "WORKING.md").read_text(), "## Lane 1\n")

    def test_dry_run_and_bad_input(self):
        result = self.run_queue("--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertIn("next: T1 first", result.stdout)
        self.assertIn("--session-id", result.stdout)
        self.assertFalse((Path(self.tmp.name) / "logs").exists())
        (self.root / "tracked.txt").write_text("dirty")
        self.assertEqual(self.run_queue().returncode, 3)
        (self.root / ".harness" / "board.json").write_text("{")
        self.assertEqual(self.run_queue().returncode, 2)


if __name__ == "__main__":
    unittest.main()
