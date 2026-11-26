import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import notices

NOW = 1_800_000_000.0


def event(session="s1", cwd="/tmp"):
    return {"hook_event_name": "UserPromptSubmit", "session_id": session, "cwd": cwd, "prompt": "hello there"}


class NoticesTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        patcher = mock.patch.dict("os.environ", {"HARNESS_NOTICES": str(self.root / "n"), "HARNESS_DISK_MIN_GB": "0"})
        patcher.start()
        self.addCleanup(patcher.stop)
        notices.os.environ.pop("CLAUDE_PROJECT_DIR", None)

    def context(self, result):
        return result["hookSpecificOutput"]["additionalContext"] if result else ""

    def test_each_session_sees_a_notice_once_including_later_sessions(self):
        notices.add("Build caches moved to the SSD", 14, None, NOW)
        first = self.context(notices.answer(event("s1"), NOW + 1))
        self.assertIn("Build caches moved to the SSD", first)
        self.assertIn("not the user's instructions", first)
        self.assertIsNone(notices.answer(event("s1"), NOW + 2))
        self.assertIn("SSD", self.context(notices.answer(event("s2"), NOW + 3600)))

    def test_expired_notices_are_hidden_and_dropped_on_add(self):
        notices.add("old news", 1, None, NOW)
        self.assertIsNone(notices.answer(event(), NOW + 2 * 86400))
        notices.add("new news", 1, None, NOW + 2 * 86400)
        self.assertEqual([row["text"] for row in notices.load_all()], ["new news"])

    def test_project_notice_reaches_only_sessions_inside_it(self):
        project = self.root / "app"
        (project / "sub").mkdir(parents=True)
        notices.add("app only", 14, str(project), NOW)
        self.assertIsNone(notices.answer(event("s1", str(self.root)), NOW))
        self.assertIn("app only", self.context(notices.answer(event("s2", str(project / "sub")), NOW)))

    def test_disk_warning_below_floor_repeats_hourly(self):
        with mock.patch.dict("os.environ", {"HARNESS_DISK_MIN_GB": "10"}), \
                mock.patch.object(notices, "free_gb", return_value=4.3):
            self.assertIn("4.3 GB, below 10 GB", self.context(notices.answer(event(), NOW)))
            self.assertIsNone(notices.answer(event(), NOW + 60))
            self.assertIn("4.3 GB", self.context(notices.answer(event(), NOW + notices.DISK_REPEAT + 1)))
        with mock.patch.object(notices, "free_gb", return_value=50.0):
            self.assertIsNone(notices.answer(event(), NOW + 3 * notices.DISK_REPEAT))

    def test_bad_session_and_other_events_do_nothing(self):
        notices.add("x", 14, None, NOW)
        self.assertIsNone(notices.answer(dict(event(), session_id="../../etc"), NOW))
        self.assertIsNone(notices.answer(dict(event(), hook_event_name="Stop"), NOW))
        self.assertFalse((self.root / "n" / "seen").exists())

    def test_remove_and_cli_add(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(notices.main(["add", "remove me"]), 0)
        key = json.loads(out.getvalue())["id"]
        self.assertEqual(notices.main(["remove", key]), 0)
        self.assertEqual(notices.load_all(), [])
        self.assertEqual(notices.main(["remove", key]), 1)

    def test_many_notices_are_not_shown_twice(self):
        rows = [{"id": f"n{index:03}", "at": NOW, "until": NOW + 86400, "text": f"notice {index}"} for index in range(205)]
        notices.save_all(rows)
        shown = []
        for step in range(60):
            text = self.context(notices.answer(event(), NOW + step))
            shown += [line for line in text.splitlines() if line.startswith("- ")]
        self.assertEqual(len(shown), 205)
        self.assertEqual(len(set(shown)), 205)

    def test_broken_lines_are_skipped(self):
        folder = self.root / "n"
        folder.mkdir(parents=True)
        (folder / "notices.jsonl").write_text('not json\n{"id": 3}\n' + json.dumps(
            {"id": "ok", "at": NOW, "until": NOW + 10, "text": "fine"}) + "\n")
        self.assertIn("fine", self.context(notices.answer(event(), NOW)))


if __name__ == "__main__":
    unittest.main()
