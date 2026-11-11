import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOK = Path(__file__).with_name("guard_git.py")


class GitHookTests(unittest.TestCase):
    def invoke(self, command, tool="Bash"):
        event = {"hook_event_name": "PreToolUse", "tool_name": tool,
                 "tool_input": {"command": command}}
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event),
                              capture_output=True, text=True, check=False)

    def test_destructive_direct_git_commands_are_denied(self):
        for command in ("git reset --hard HEAD", "git clean -xfd", "git clean -f -d -x",
                        "git push --force origin main", "git push -f",
                        "git push --force origin main\nprintf %s -n",
                        "git push -onotify --force origin main", "git clean -fdx -enotes*",
                        "git -C /tmp/repo reset --hard HEAD", "git clean --force -dx"):
            with self.subTest(command=command):
                result = self.invoke(command)
                self.assertEqual(result.returncode, 2)
                self.assertIn("blocked", result.stderr)

    def test_normal_git_commands_and_dry_runs_pass(self):
        for command in ("git status", "git push origin main", "git push --force-with-lease",
                        "git clean -nfdx", "git push --dry-run --force",
                        "git reset HEAD -- --hard", "git push origin main && echo --force",
                        "git push origin main\nprintf %s --force",
                        "git push origin main # note\nprintf %s --force",
                        "git push -oflag origin main", "git push -o --force origin main",
                        "echo 'git reset --hard'"):
            with self.subTest(command=command):
                self.assertEqual(self.invoke(command).returncode, 0)

    def test_ignores_non_bash_and_invalid_payload(self):
        self.assertEqual(self.invoke("git reset --hard", tool="Read").returncode, 0)
        result = subprocess.run([sys.executable, str(HOOK)], input="{",
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
