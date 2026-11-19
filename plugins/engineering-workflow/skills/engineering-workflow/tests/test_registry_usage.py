import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/registry_usage.py"
SPEC = importlib.util.spec_from_file_location("registry_usage", SCRIPT)
registry_usage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registry_usage)

SECRET = "PROMPT-TEXT-THAT-MUST-NOT-LEAVE"


def line(item):
    return json.dumps(item) + "\n"


def claude_tool(cwd, when, name, given):
    return line({"cwd": cwd, "timestamp": f"{when}T10:00:00Z", "message": {"content": [
        {"type": "tool_use", "name": name, "input": given}]}})


def codex_meta(cwd, when):
    return line({"type": "session_meta", "timestamp": f"{when}T09:00:00Z", "payload": {"cwd": cwd}})


def codex_call(when, text, kind="function_call", field="arguments"):
    return line({"type": "response_item", "timestamp": f"{when}T10:00:00Z", "payload": {"type": kind, field: text}})


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.game, self.shop = str(base / "apps" / "game"), str(base / "apps" / "game-shop")
        self.claude, self.codex = base / "claude", base / "codex"
        self.config = {"apps": [{"name": "game", "path": self.game}, {"name": "shop", "path": self.shop}],
                       "usage": str(base / "out" / "usage.json"),
                       "usage_sources": {"claude": str(self.claude), "codex": str(self.codex)}}
        self.write(self.claude / "p" / "s1.jsonl",
                   claude_tool(self.game, "2026-11-15", "Skill", {"skill": "flow:game-dev", "args": SECRET})
                   + claude_tool(self.game, "2026-11-16", "Read", {"file_path": "/x/skills/game-dev/SKILL.md"}))
        self.write(self.claude / "p" / "s1" / "subagents" / "a1.jsonl",
                   claude_tool(self.game + "/.claude/worktrees/w", "2026-11-15", "Read",
                               {"file_path": "/x/skills/game-dev/SKILL.md"}))
        self.write(self.claude / "p" / "s2.jsonl",
                   claude_tool(self.shop, "2026-11-17", "Bash", {"command": "cat /y/skills/report/SKILL.md"})
                   + line({"cwd": self.shop, "message": {"content": [{"type": "text", "input": {
                       "file_path": "/q/skills/listed/SKILL.md"}}]}})
                   + line({"cwd": self.shop, "message": {"content": [{"type": "text",
                                                                       "text": "skills/listed/SKILL.md " + SECRET}]}}))
        self.write(self.claude / "p" / "s3.jsonl",
                   claude_tool("/somewhere/else", "2026-11-17", "Skill", {"skill": "game-dev"}))
        self.write(self.codex / "2026" / "r1.jsonl",
                   codex_meta(self.game, "2026-11-18")
                   + line({"type": "response_item", "payload": {"type": "message", "input": "skills/listed/SKILL.md"}})
                   + line({"type": "response_item", "payload": {"type": "message", "content": [
                       {"type": "input_text", "text": "available: skills/listed/SKILL.md " + SECRET}]}})
                   + codex_call("2026-11-18", '{"cmd": "sed -n 1,80p /z/skills/game-dev/SKILL.md"}')
                   + codex_call("2026-11-19", "*** read skills/game-dev/SKILL.md", "custom_tool_call", "input"))
        self.write(self.codex / "2026" / "r2.jsonl",
                   codex_meta(self.game, "2026-11-19")
                   + line({"type": "response_item", "timestamp": "2026-11-19T11:00:00Z", "payload": {
                       "type": "local_shell_call", "action": {"command": ["cat", "skills/report/SKILL.md"]}}}))

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def rows(self):
        report = registry_usage.update(self.config)
        data = json.loads(Path(self.config["usage"]).read_text(encoding="utf-8"))
        return report, {(row["app"], row["skill"], row["agent"]): row for row in data["usage"]}

    def test_sessions_per_app_skill_and_agent_from_tool_calls_only(self):
        _, rows = self.rows()
        self.assertEqual(sorted(rows), [("game", "game-dev", "claude"), ("game", "game-dev", "codex"),
                                        ("game", "report", "codex"), ("shop", "report", "claude")])
        claude = rows[("game", "game-dev", "claude")]
        self.assertEqual((claude["sessions"], claude["first"], claude["last"]), (1, "2026-11-15", "2026-11-16"))
        codex = rows[("game", "game-dev", "codex")]
        self.assertEqual((codex["sessions"], codex["first"], codex["last"]), (1, "2026-11-18", "2026-11-19"))

    def test_no_prompt_text_is_kept(self):
        self.rows()
        out = Path(self.config["usage"])
        for path in (out, out.with_name(out.name + ".state.json")):
            self.assertNotIn(SECRET, path.read_text(encoding="utf-8"))

    def test_only_new_bytes_are_read_and_a_half_written_line_waits(self):
        report, _ = self.rows()
        self.assertEqual(report["read"], 6)
        self.assertEqual(self.rows()[0]["read"], 0)
        log = self.codex / "2026" / "r2.jsonl"
        whole = codex_call("2026-11-20", "skills/brand/SKILL.md")
        with log.open("a", encoding="utf-8") as handle:
            handle.write(whole[:-10])
        report, rows = self.rows()
        self.assertEqual(report["read"], 1)
        self.assertNotIn(("game", "brand", "codex"), rows)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(whole[-10:])
        _, rows = self.rows()
        self.assertEqual(rows[("game", "brand", "codex")]["last"], "2026-11-20")

    def test_a_shorter_log_is_read_again_and_a_gone_log_is_dropped(self):
        self.rows()
        self.write(self.codex / "2026" / "r1.jsonl", codex_meta(self.game, "2026-11-18"))
        (self.codex / "2026" / "r2.jsonl").unlink()
        _, rows = self.rows()
        self.assertNotIn(("game", "game-dev", "codex"), rows)
        self.assertNotIn(("game", "report", "codex"), rows)

    def test_a_subagents_folder_above_the_log_root_does_not_merge_sessions(self):
        root = Path(self.tmp.name) / "subagents" / "claude"
        for name in ("s1", "s2"):
            self.write(root / f"{name}.jsonl", claude_tool(self.game, "2026-11-15", "Skill", {"skill": "flow"}))
        self.config["usage_sources"] = {"claude": str(root)}
        self.assertEqual(self.rows()[1][("game", "flow", "claude")]["sessions"], 2)

    def test_long_lines_and_odd_skill_values(self):
        filler = "x" * (3 << 20)
        self.write(self.claude / "p" / "s4.jsonl",
                   line({"cwd": self.game, "filler": filler})
                   + claude_tool(self.game, "2026-11-18", "Skill", {"skill": "x:"})
                   + claude_tool(self.game, "2026-11-18", "Skill", {"skill": "two words " + SECRET})
                   + claude_tool(self.game, "2026-11-18", "Read", {"file_path": "/a/skills/brand/SKILL.md", "pad": filler}))
        _, rows = self.rows()
        self.assertEqual(rows[("game", "brand", "claude")]["sessions"], 1)
        self.assertFalse([key for key in rows if key[1] in ("", "x") or " " in key[1]])
        self.assertNotIn(SECRET, Path(self.config["usage"] + ".state.json").read_text(encoding="utf-8"))

    @unittest.skipIf(registry_usage.zstd is None, "this Python has no zstd")
    def test_compressed_logs_count_as_the_same_session_and_a_broken_one_is_skipped(self):
        plain = self.codex / "2026" / "r1.jsonl"
        packed = plain.with_name("r1.jsonl.zst")
        packed.write_bytes(registry_usage.zstd.compress(plain.read_bytes()))
        self.assertEqual(self.rows()[1][("game", "game-dev", "codex")]["sessions"], 1)
        plain.unlink()
        (self.codex / "2026" / "bad.jsonl.zst").write_bytes(b"not zstd")
        report, rows = self.rows()
        self.assertEqual(rows[("game", "game-dev", "codex")]["sessions"], 1)
        self.assertEqual(rows[("game", "game-dev", "codex")]["last"], "2026-11-19")
        self.assertEqual(report["read"], 0)
        self.assertEqual(self.rows()[0]["read"], 0)

    def test_compressed_logs_are_skipped_without_zstd(self):
        (self.codex / "2026" / "r3.jsonl.zst").write_bytes(b"x")
        with unittest.mock.patch.object(registry_usage, "zstd", None):
            report, _ = self.rows()
        self.assertEqual(report["skipped_packed"], 1)

    def test_usage_sources_must_be_a_mapping_of_known_agents(self):
        for bad in (["/path"], {"other": "/path"}, {"codex": 3}, {"codex": []}, {"codex": ["/a", 3]}):
            self.config["usage_sources"] = bad
            with self.assertRaises(ValueError):
                registry_usage.update(self.config)

    def test_longest_app_path_wins_and_a_missing_usage_path_is_an_error(self):
        self.assertEqual(registry_usage.app_for(self.shop + "/lib", [("game", self.game), ("shop", self.shop)]), "shop")
        self.assertIsNone(registry_usage.app_for(self.game + "-other", [("game", self.game)]))
        self.assertEqual(registry_usage.app_for(self.game + "/sub/x", [("game", self.game), ("sub", self.game + "/sub")]),
                         "sub")
        with self.assertRaises(ValueError):
            registry_usage.update({"apps": []})
        config = Path(self.tmp.name) / "bad.json"
        config.write_text("{}", encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(config)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
