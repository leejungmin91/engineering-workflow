import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "engineering-workflow"
SHELL = shutil.which("sh") or shutil.which("bash")


def board_commands():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    return {event: [hook["command"] for group in groups for hook in group["hooks"] if "board.py" in hook["command"]]
            for event, groups in hooks.items()}


class BoardHookTest(unittest.TestCase):
    def test_board_is_registered_on_three_events(self):
        commands = board_commands()
        for event in ("SessionStart", "PostToolUse", "Stop"):
            self.assertEqual(len(commands[event]), 1, event)

    @unittest.skipIf(SHELL is None or shutil.which("python3") is None, "needs sh and python3 on PATH")
    def test_registered_command_renders_a_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp).resolve() / "app"
            pages = Path(tmp).resolve() / "pages"
            (project / ".harness").mkdir(parents=True)
            (project / ".harness" / "board.json").write_text(
                json.dumps({"tasks": [{"id": "a", "title": "one", "status": "done"}]}), encoding="utf-8")
            env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN), "CLAUDE_PROJECT_DIR": str(project),
                   "HARNESS_BOARD_HOME": str(pages), "HARNESS_BOARD_OPEN": "0"}
            event = json.dumps({"hook_event_name": "SessionStart", "cwd": str(project), "session_id": "s"})
            result = subprocess.run([SHELL, "-c", board_commands()["SessionStart"][0]], input=event, env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("additionalContext", result.stdout)
            self.assertEqual(len(list(pages.glob("app-*.html"))), 1)

    @unittest.skipIf(SHELL is None, "needs sh or bash on PATH")
    def test_registered_command_is_quiet_without_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"PATH": tmp, "CLAUDE_PLUGIN_ROOT": str(PLUGIN)}
            result = subprocess.run([SHELL, "-c", board_commands()["Stop"][0]], input="{}", env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
