import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/board.py"
SPEC = importlib.util.spec_from_file_location("board", SCRIPT)
board = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(board)


def task(id, status="todo", after=None, title=None):
    return {"id": id, "title": title or f"task {id}", "status": status, "after": after or []}


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "app"
        self.home = Path(self.tmp.name).resolve() / "boards"
        (self.root / ".harness").mkdir(parents=True)
        self.path = self.root / ".harness" / "board.json"
        patch = mock.patch.dict(os.environ, {"HARNESS_BOARD_HOME": str(self.home), "HARNESS_BOARD_OPEN": "0",
                                             "CLAUDE_PROJECT_DIR": str(self.root)})
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def save(self, tasks, **extra):
        self.path.write_text(json.dumps({"title": "Demo", "tasks": tasks, **extra}), encoding="utf-8")

    def page(self):
        return board.publish(self.path).read_text(encoding="utf-8")


class BoardTests(Case):
    def test_progress_counts_done_tasks(self):
        self.save([task("a", "done"), task("b", "doing"), task("c"), task("d", "done")])
        content = self.page()
        self.assertIn(">50%<", content)
        self.assertIn("2 of 4 tasks done", content)
        self.assertIn('aria-valuenow="50"', content)

    def test_progress_reaches_100_only_when_everything_is_done(self):
        self.save([task(f"t{n}", "done") for n in range(199)] + [task("last")])
        self.assertIn(">99%<", self.page())

    def test_every_text_field_is_escaped_on_both_pages(self):
        mark = "<script>alert(1)</script>"
        self.root = self.root.parent / "a&b"
        (self.root / ".harness").mkdir(parents=True)
        self.path = self.root / ".harness" / "board.json"
        self.path.write_text(json.dumps({
            "title": f"title {mark}",
            "tasks": [{"id": "a", "title": f"t {mark}", "status": "todo", "owner": f"o {mark}", "note": f"n {mark}"},
                      {"id": "b", "title": "plain", "after": ["a"]}],
            "decisions": [{"ask": f"ask {mark}", "look": f"look {mark}", "default": f"default {mark}"}]}),
            encoding="utf-8")
        content = self.page()
        listing = (self.home / "index.html").read_text(encoding="utf-8")
        for output in (content, listing):
            self.assertNotIn(mark, output)
            self.assertNotIn("a&b", output)
            self.assertIn("a&amp;b", output)
        self.assertEqual(content.count("&lt;script&gt;alert(1)&lt;/script&gt;"), 8)
        self.assertIn("title &lt;script&gt;", listing)

    def test_decisions_come_from_the_board_and_working_file(self):
        self.save([task("a")], decisions=[{"ask": "Pick a store", "look": "docs/a.md", "default": "none"}])
        (self.root / "WORKING.md").write_text(
            "# Who\n\n## Waiting for the user (parked)\n\n- Approve the icon\n- None\n(none)\n```\n- in a fence\n```\n"
            "\n## Sessions\n\n- not this\n", encoding="utf-8")
        content = self.page()
        self.assertIn("Pick a store", content)
        self.assertIn("Approve the icon", content)
        self.assertNotIn("not this", content)
        self.assertNotIn("in a fence", content)
        self.assertEqual(content.count('class="decision"'), 2)

    def test_working_file_bullets_keep_their_wrapped_lines_and_can_be_left_out(self):
        (self.root / "WORKING.md").write_text(
            "## Waiting for the user\n\n- Pick the ground sample:\n  all, some, or none.\n  ```text\n  example only\n  ~~~\n  ```\n"
            "- Second\n", encoding="utf-8")
        self.save([task("a")])
        content = self.page()
        self.assertIn("Pick the ground sample: all, some, or none.</", content)
        self.assertNotIn("example only", content)
        self.assertEqual(content.count('class="decision"'), 2)
        self.save([task("a")], working_decisions=False)
        self.assertEqual(self.page().count('class="decision"'), 0)
        self.save([task("a")], working_decisions="no")
        with self.assertRaises(ValueError):
            board.load(self.root / ".harness" / "board.json")

    def test_korean_labels_and_unknown_language_falls_back(self):
        self.save([task("a", "done")], lang="ko")
        self.assertIn("전체 진행률", self.page())
        self.save([task("a", "done")], lang=["ko"])
        self.assertIn("Progress", self.page())

    def test_overview_lists_boards_and_drops_removed_ones(self):
        self.save([task("a", "done"), task("b")])
        board.publish(self.path)
        other = self.root.parent / "other"
        (other / ".harness").mkdir(parents=True)
        second = other / ".harness" / "board.json"
        second.write_text(json.dumps({"title": "Second", "tasks": [task("x")]}), encoding="utf-8")
        board.publish(second)
        listing = (self.home / "index.html").read_text(encoding="utf-8")
        self.assertIn("Demo", listing)
        self.assertIn("Second", listing)
        second.unlink()
        board.publish(self.path)
        self.assertNotIn("Second", (self.home / "index.html").read_text(encoding="utf-8"))

    def test_overview_ignores_summaries_it_did_not_write(self):
        self.save([task("a")])
        board.publish(self.path)
        good = json.loads(next(self.home.glob("app-*.json")).read_text(encoding="utf-8"))
        for number, change in enumerate(({"page": "javascript:alert(1)"}, {"percent": "<img src=x>"}, {"title": None},
                                         {"page": "../x.html"})):
            (self.home / f"foreign{number}.json").write_text(json.dumps({**good, "title": "Foreign", **change}),
                                                             encoding="utf-8")
        (self.home / "broken.json").write_text("{", encoding="utf-8")
        board.publish(self.path)
        listing = (self.home / "index.html").read_text(encoding="utf-8")
        self.assertIn("Demo", listing)
        self.assertNotIn("Foreign", listing)
        self.assertNotIn("javascript:", listing)
        self.assertNotIn("<img", listing)

    def test_invalid_boards_are_rejected(self):
        cases = [[], [task("a"), task("a")], [task("a", "finished")], [task("a", after=["missing"])],
                 [{"id": "a", "status": "todo"}], [task("bad id")]]
        for tasks in cases:
            self.save(tasks)
            with self.assertRaises(ValueError):
                board.publish(self.path)

    def test_command_reports_invalid_input_with_exit_2(self):
        for content in (json.dumps({"tasks": [task("a", "finished")]}), "{", "[" * 100000, json.dumps({"tasks": [{"id": ["a"]}]})):
            self.path.write_text(content, encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "render", str(self.path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr[-300:])
            self.assertIn("INVALID", result.stderr)

    def test_out_writes_one_page_and_no_overview(self):
        self.save([task("a")])
        target = self.root.parent / "page.html"
        board.publish(self.path, out=target)
        self.assertTrue(target.is_file())
        self.assertFalse(self.home.exists())

    def test_relative_page_folder_is_ignored(self):
        self.assertTrue(board.home().is_absolute())
        with mock.patch.dict(os.environ, {"HARNESS_BOARD_HOME": "pages"}):
            self.assertTrue(board.home().is_absolute())
            self.assertNotEqual(board.home().name, "pages")


class HookTests(Case):
    def event(self, name, **extra):
        return {"hook_event_name": name, "cwd": str(self.root), "session_id": "s1", **extra}

    def pages(self):
        return list(self.home.glob("app-*.html")) if self.home.exists() else []

    def test_no_board_means_no_output_and_no_files(self):
        self.assertIsNone(board.hook(self.event("SessionStart")))
        self.assertFalse(self.home.exists())

    def test_session_start_renders_and_tells_the_agent(self):
        self.save([task("a")])
        result = board.hook(self.event("SessionStart"))
        self.assertIn("board.json", result["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(len(self.pages()), 1)

    def test_edit_of_the_board_renders_and_other_edits_do_not(self):
        self.save([task("a")])
        board.hook(self.event("PostToolUse", tool_name="Edit", tool_input={"file_path": "README.md"}))
        self.assertEqual(self.pages(), [])
        board.hook(self.event("PostToolUse", tool_name="Edit", tool_input={"file_path": ".harness/board.json"}))
        self.assertEqual(len(self.pages()), 1)
        self.save([task("a", "done")])
        board.hook(self.event("PostToolUse", tool_name="Write", tool_input={"file_path": str(self.path)}))
        self.assertIn(">100%<", self.pages()[0].read_text(encoding="utf-8"))

    def test_relative_paths_are_read_from_the_working_directory(self):
        self.save([task("a")])
        sub = self.root / "sub"
        (sub / ".harness").mkdir(parents=True)
        (sub / ".harness" / "board.json").write_text("{}", encoding="utf-8")
        board.hook(self.event("PostToolUse", cwd=str(sub), tool_input={"file_path": ".harness/board.json"}))
        self.assertEqual(self.pages(), [])
        board.hook(self.event("PostToolUse", cwd=str(sub), tool_input={"file_path": "../.harness/board.json"}))
        self.assertEqual(len(self.pages()), 1)

    def test_root_is_found_from_a_subfolder_without_the_project_variable(self):
        self.save([task("a")])
        sub = self.root / "src" / "deep"
        sub.mkdir(parents=True)
        with mock.patch.dict(os.environ):
            del os.environ["CLAUDE_PROJECT_DIR"]
            board.hook(self.event("Stop", cwd=str(sub)))
        self.assertEqual(len(self.pages()), 1)

    @unittest.skipIf(os.name == "nt", "needs symlinks")
    def test_linked_board_folder_still_matches(self):
        real = self.root.parent / "state"
        self.save([task("a")])
        (self.root / ".harness").rename(real)
        os.symlink(real, self.root / ".harness")
        board.hook(self.event("PostToolUse", tool_input={"file_path": str(real / "board.json")}))
        self.assertEqual(len(self.pages()), 1)

    def test_page_opens_once_per_session_even_when_sessions_alternate(self):
        self.save([task("a")])
        with mock.patch.object(board, "launch") as launch:
            board.hook(self.event("SessionStart"))
            board.hook(self.event("Stop"))
            board.hook(self.event("PostToolUse", tool_input={"file_path": str(self.path)}))
            self.assertEqual(launch.call_count, 1)
            for session in ("s2", "s1", "s2", "s1"):
                board.hook(self.event("Stop", session_id=session))
            self.assertEqual(launch.call_count, 2)

    def test_page_opens_once_without_a_session_id(self):
        self.save([task("a")])
        with mock.patch.object(board, "launch") as launch:
            for _ in range(3):
                event = self.event("Stop")
                del event["session_id"]
                board.hook(event)
            self.assertEqual(launch.call_count, 1)

    def test_broken_board_reports_and_does_not_raise(self):
        for content in ("{", json.dumps({"tasks": [{"id": ["a"]}]}), "[" * 100000):
            self.path.write_text(content, encoding="utf-8")
            result = board.hook(self.event("Stop"))
            self.assertIn("was not rendered", result["systemMessage"])

    def test_hook_command_never_fails(self):
        payloads = ["", "[]", "{", json.dumps(self.event("Unknown"))]
        for payload in payloads:
            result = subprocess.run([sys.executable, str(SCRIPT), "hook"], input=payload, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
        self.path.write_text("{", encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPT), "hook"], input=json.dumps(self.event("Stop")),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("was not rendered", json.loads(result.stdout)["systemMessage"])

    def test_browser_is_detached_and_can_be_switched_off(self):
        with mock.patch.object(board.subprocess, "Popen") as popen, mock.patch.object(board.sys, "platform", "darwin"):
            board.launch(self.path)
            self.assertEqual(popen.call_count, 0)
            with mock.patch.dict(os.environ, {"HARNESS_BOARD_OPEN": "1"}):
                board.launch(self.path)
            self.assertEqual(popen.call_count, 1)
            options = popen.call_args.kwargs
            self.assertEqual(options["stdout"], subprocess.DEVNULL)
            self.assertEqual(options["stderr"], subprocess.DEVNULL)
            popen.side_effect = OSError("no opener")
            with mock.patch.dict(os.environ, {"HARNESS_BOARD_OPEN": "1"}):
                board.launch(self.path)


if __name__ == "__main__":
    unittest.main()
