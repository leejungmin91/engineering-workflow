import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
HOOK = SKILL / "scripts" / "lane_guard.py"
TEMPLATE = SKILL / "templates" / "multi-session" / "WORKING.md"
BUILD = "286d5004-b548-4429-97a0-19258119cec1"
PLAN = "e602d702-5a5a-4920-893e-bbc8153d054a"

WORKING = """# Who is working

## Waiting for the user

(none)

## Lane 1: build (one holder)

- build, session_id=%s: task 1 (`src/`). Started 2026-11-18 10:00.

## Lane 2: produce

(none)
"""

DENY = [
    'git add -A', 'git add .', 'git add --all', 'cd x && git add -A && git commit -m "m"',
    'git commit -am "msg"', 'git commit -a -m "msg"', 'git commit --all -m x', 'git -C sub add .',
    'git add -v -A', 'git add docs/a.md .', 'if true; then git add -A; fi', '(git add .)',
    'git add -u', 'git add . >/dev/null', 'git add .|cat', 'git add "-A"',
    'echo "it\'s"; git add -A; echo "fine\'s"', 'cat <<END-MSG\nhello\nEND-MSG\ngit add -A', 'cat <<<EOF\ngit add -A',
    'git -C a -C b add -A', 'git stage -A', 'git add *', 'git add :/', 'git -c a=b add -A',
    'bash -c "git add -A"', 'FOO=1 git add --all', 'git commit -qam "m"', 'git add --update',
    'git commit -am"fix: typo"', 'git commit -mtest -a', 'git commit -qa', 'git add -A .',
    'git commit -S0x1234567F -a -m fix', 'git commit -aS0xdeadbeef -m fix',
]
ALLOW = [
    'git add docs/a.md src/b.py', 'git commit -m "use git add -A never"', "git commit -m 'git commit -a is refused'",
    "git commit -q -F - <<'EOF'\nStage by name; git add -A and git commit -a are refused\ngit add .\nEOF\ngit push -q origin main",
    'git commit -F /tmp/msg.txt', 'git commit --amend --no-edit', 'git commit -m "x" --author="a b <a@b>"',
    'echo "git add ."', 'grep -n "git add -A" CLAUDE.md', 'git add ./docs/a.md', 'git add .claude/hooks/lane_guard.py',
    'python3 - <<EOF\nprint("git add -A")\nEOF', 'git status --short; git log --oneline -3',
    'git commit -m "it\'s fine" -m \'git commit -a\'', 'git add -- -A', 'git commit -m --all', 'echo do git add -A',
    'git add named.txt\nprintf -- -A', 'git commit -m "a" 2>&1 | tail -1', 'git add :/docs/a.md', 'git log --all --oneline',
    'git commit -F - <<EOF\ngit add -A\nEOF', 'git diff --stat -- .', 'git checkout -- .gitignore', 'git add a.txt # then git add -A',
    'git commit -mbar', 'git commit -m a', 'git commit -qm "a b"', 'git add -A docs/a.md', 'git add -u docs/a.md', 'git commit -Fa.txt',
    'git commit -S0xdeadbeef -m fix', 'git commit -uall -m fix', 'git commit -S -m fix',
]


class LaneGuardTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="ewf-lane-")))
        (self.root / ".claude").mkdir()
        self.write_working(WORKING % BUILD)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write_working(self, text):
        (self.root / "WORKING.md").write_text(text, encoding="utf-8")

    def write_config(self, config):
        (self.root / ".claude" / "lane-guard.json").write_text(json.dumps(config), encoding="utf-8")

    def raw(self, text):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.root)
        return subprocess.run([sys.executable, "-I", str(HOOK)], input=text, capture_output=True,
                              text=True, env=env)

    def run_hook(self, tool, tool_input, sid=BUILD):
        result = self.raw(json.dumps({"session_id": sid, "tool_name": tool, "tool_input": tool_input,
                                      "cwd": str(self.root)}))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.strip(), "")
        out = result.stdout.strip()
        if not out:
            return "allow"
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        return "deny"

    def edit(self, path, sid, tool="Edit"):
        return self.run_hook(tool, {"file_path": path}, sid)

    def test_staging_everything_is_refused(self):
        for command in DENY:
            with self.subTest(command=command):
                self.assertEqual(self.run_hook("Bash", {"command": command}), "deny")

    def test_staging_by_name_and_quoted_words_pass(self):
        for command in ALLOW:
            with self.subTest(command=command):
                self.assertEqual(self.run_hook("Bash", {"command": command}), "allow")

    def test_only_the_holder_edits_by_default(self):
        self.assertEqual(self.edit("src/x.py", BUILD), "allow")
        self.assertEqual(self.edit("src/x.py", PLAN), "deny")
        self.assertEqual(self.edit("CLAUDE.md", PLAN, "Write"), "deny")
        self.assertEqual(self.edit(str(self.root / "docs" / "a.md"), PLAN), "deny")
        self.assertEqual(self.run_hook("NotebookEdit", {"notebook_path": "nb/a.ipynb"}, PLAN), "deny")
        self.assertEqual(self.edit("src/x.py", ""), "deny")

    def test_working_file_and_outside_paths_are_open(self):
        outside = Path(os.path.realpath(tempfile.mkdtemp(prefix="ewf-out-")))
        try:
            self.assertEqual(self.edit("WORKING.md", PLAN, "Write"), "allow")
            self.assertEqual(self.edit(str(outside / "x.txt"), PLAN, "Write"), "allow")
            self.assertEqual(self.edit("../x.txt", PLAN, "Write"), "allow")
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_open_folders_are_writable_by_any_session(self):
        self.write_config({"open": ["candidates/", "docs/research"]})
        self.assertEqual(self.edit("candidates/a.png", PLAN, "Write"), "allow")
        self.assertEqual(self.edit("docs/research/r.md", PLAN, "Write"), "allow")
        self.assertEqual(self.edit("docs/researching.md", PLAN, "Write"), "deny")
        self.assertEqual(self.edit("src/x.py", PLAN), "deny")

    def test_guarded_list_limits_the_guard(self):
        self.write_config({"guarded": ["src/", "docs/plan.md"], "open": ["src/generated/"]})
        self.assertEqual(self.edit("src/x.py", PLAN), "deny")
        self.assertEqual(self.edit("docs/plan.md", PLAN), "deny")
        self.assertEqual(self.edit("docs/notes.md", PLAN, "Write"), "allow")
        self.assertEqual(self.edit("src/generated/a.txt", PLAN, "Write"), "allow")

    def test_rules_and_settings_stay_guarded(self):
        self.write_config({"guarded": ["src/"], "open": [".claude/", "CLAUDE.md", "AGENTS.md"]})
        self.assertEqual(self.edit(".claude/settings.json", PLAN), "deny")
        self.assertEqual(self.edit(".claude/lane-guard.json", PLAN, "Write"), "deny")
        self.assertEqual(self.edit("CLAUDE.md", PLAN), "deny")
        self.assertEqual(self.edit("AGENTS.md", PLAN), "deny")
        self.assertEqual(self.edit(".claude/settings.json", BUILD), "allow")

    def test_broken_config_keeps_the_default(self):
        (self.root / ".claude" / "lane-guard.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.edit("src/x.py", PLAN), "deny")
        self.write_config({"open": "src/", "guarded": 3})
        self.assertEqual(self.edit("src/x.py", PLAN), "deny")

    def test_free_lane_asks_the_session_to_take_it(self):
        self.write_working(WORKING.replace("- build, session_id=%s: task 1 (`src/`). Started 2026-11-18 10:00.", "(none)"))
        result = self.raw(json.dumps({"session_id": PLAN, "tool_name": "Edit",
                                      "tool_input": {"file_path": "src/x.py"}, "cwd": str(self.root)}))
        reason = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("lane 1 is free", reason)
        self.assertIn(PLAN, reason)

    def test_a_session_id_outside_lane_one_does_not_count(self):
        self.write_working(WORKING % BUILD + "\n## Sessions\n\n- planner, session_id=%s\n" % PLAN)
        self.assertEqual(self.edit("src/x.py", PLAN), "deny")

    def test_template_starts_with_a_free_lane(self):
        self.write_working(TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(self.edit("src/x.py", BUILD), "deny")
        self.assertEqual(self.run_hook("Bash", {"command": "git add -A"}), "deny")

    def test_without_lanes_nothing_is_refused(self):
        self.write_working("# Notes\n")
        self.assertEqual(self.edit("src/x.py", PLAN), "allow")
        self.assertEqual(self.run_hook("Bash", {"command": "git add -A"}), "allow")
        (self.root / "WORKING.md").unlink()
        self.assertEqual(self.edit("src/x.py", PLAN), "allow")
        self.assertEqual(self.run_hook("Bash", {"command": "git add -A"}), "allow")

    def test_malformed_input_is_a_clean_allow(self):
        for text in ('{"tool_name": "Bash", "tool_input": "x"}', "[1, 2]", "not json", '{"tool_name": "Bash"}',
                     '{"tool_name": "Edit", "tool_input": {"file_path": 3}}'):
            with self.subTest(text=text):
                result = self.raw(text)
                self.assertEqual((result.returncode, result.stdout.strip(), result.stderr.strip()), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
