import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "codex_usage.py"
THREAD = "01234567-89ab-cdef-0123-456789abcdef"
STAMP = "2026-11-13T15:17:38.495Z"


class CodexUsageTests(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.env = {**os.environ, "CODEX_HOME": home.name, "CODEX_THREAD_ID": THREAD}
        sessions = Path(home.name) / "sessions" / "2026" / "11" / "13"
        sessions.mkdir(parents=True)
        self.rollout = sessions / f"rollout-test-{THREAD}.jsonl"
        self.write("session_meta", id=THREAD)

    def write(self, kind, **payload):
        with self.rollout.open("a", encoding="utf-8") as stream:
            print(json.dumps({"timestamp": STAMP, "type": kind, "payload": payload}), file=stream)

    def snapshot(self):
        result = subprocess.run([sys.executable, SCRIPT], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_context_total_and_quota_are_separate(self):
        self.write("turn_context", model="test-model", effort="high")
        self.write("event_msg", type="token_count", info={
            "last_token_usage": {"total_tokens": 250},
            "total_token_usage": {"total_tokens": 2000},
            "model_context_window": 1000,
        })
        self.write("event_msg", type="token_count", rate_limits={
            "limit_id": "codex",
            "primary": {"used_percent": 14, "window_minutes": 300, "resets_at": 1794599768},
        })
        self.write("event_msg", type="token_count", rate_limits={
            "limit_id": "other", "primary": {"used_percent": 80, "window_minutes": 300},
        })
        snapshot = self.snapshot()
        self.assertEqual(snapshot["model"], "test-model")
        self.assertEqual(snapshot["reasoning_effort"], "high")
        self.assertEqual(snapshot["context"], {
            "observed_at": STAMP, "tokens": 250, "capacity": 1000,
            "used_percent": 25, "remaining_percent": 75,
        })
        self.assertEqual(snapshot["session_total_tokens"], 2000)
        self.assertEqual(snapshot["account_windows"][0]["remaining_percent"], 86)
        self.assertEqual(snapshot["account_windows"][0]["observed_at"], STAMP)
        self.assertEqual(len(snapshot["account_windows"]), 1)

    def test_reroute_and_partial_record(self):
        self.write("turn_context", model="configured")
        self.write("event_msg", type="model_reroute", to_model="routed")
        self.write("event_msg", type="token_count", info={"last_token_usage": {"total_tokens": 0}})
        with self.rollout.open("a", encoding="utf-8") as stream:
            stream.write('{"type":')
        snapshot = self.snapshot()
        self.assertEqual(snapshot["model"], "routed")
        self.assertEqual(snapshot["context"]["tokens"], 0)
        self.assertIsNone(snapshot["context"]["used_percent"])

    def test_rejects_log_for_another_thread(self):
        self.rollout.unlink()
        self.write("session_meta", id="another")
        self.write("turn_context", model="wrong-thread")
        self.assertIsNone(self.snapshot()["model"])

    def test_missing_thread_id_does_not_scan_other_sessions(self):
        self.write("turn_context", model="wrong-thread")
        self.env.pop("CODEX_THREAD_ID")
        self.assertIsNone(self.snapshot()["model"])


if __name__ == "__main__":
    unittest.main()
