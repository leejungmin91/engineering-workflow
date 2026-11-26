import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import claude_usage

SESSION = "01234567-89ab-cdef-0123-456789abcdef"
OWNER = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class ClaudeUsageTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.snapshots = self.root / "usage"
        patcher = mock.patch.dict("os.environ", {"CLAUDE_CONFIG_DIR": str(self.root),
                                                 "HARNESS_USAGE_CACHE": str(self.snapshots)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = time.time()

    def config(self, cached, owner=OWNER):
        (self.root / ".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": owner},
                                                            "cachedUsageUtilization": cached}))

    def transcript(self, *entries):
        folder = self.root / "projects" / "-tmp-app"
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / f"{SESSION}.jsonl", "w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")

    def snapshot(self, at, size=200000, tokens=(1, 9, 990)):
        self.snapshots.mkdir(parents=True, exist_ok=True)
        current = dict(zip(("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"), tokens))
        (self.snapshots / f"{SESSION}.json").write_text(json.dumps({
            "session_id": SESSION, "model": {"id": "claude-opus-5-5"}, "at": at,
            "context_window": {"context_window_size": size, "current_usage": current}}))

    def test_account_windows_from_cached_usage(self):
        fetched = (self.now - 600) * 1000
        self.config({"accountUuid": OWNER, "fetchedAtMs": fetched, "utilization": {
            "five_hour": None, "seven_day": {"utilization": 64, "resets_at": "2026-11-30T04:00:00+00:00"}}})
        result = claude_usage.read_usage("", self.now)
        self.assertEqual(result["account_windows"], [{
            "window": "seven_day", "used_percent": 64, "remaining_percent": 36,
            "resets_at": "2026-11-30T04:00:00+00:00", "observed_at": claude_usage.stamp(fetched / 1000),
            "age_minutes": 10}])
        self.assertIsNone(result["account_note"])

    def test_other_account_cache_is_not_reported(self):
        self.config({"accountUuid": "someone-else", "fetchedAtMs": 1, "utilization": {"seven_day": {"utilization": 5}}})
        result = claude_usage.read_usage("", self.now)
        self.assertEqual(result["account_windows"], [])
        self.assertIn("another account", result["account_note"])

    def test_status_line_snapshot_gives_capacity(self):
        self.snapshot(self.now - 30)
        self.transcript({"type": "assistant", "message": {"model": "claude-opus-5-5", "usage": {"input_tokens": 5}}})
        context = claude_usage.read_usage(SESSION, self.now)["context"]
        self.assertEqual((context["tokens"], context["capacity"], context["used_percent"], context["source"]),
                         (1000, 200000, 0.5, "status line"))

    def test_transcript_fallback_skips_sidechains_and_has_no_capacity(self):
        self.transcript(
            {"type": "assistant", "timestamp": "t1", "message": {"model": "m", "usage": {
                "input_tokens": 2, "cache_creation_input_tokens": 3, "cache_read_input_tokens": 100, "output_tokens": 5}}},
            {"type": "assistant", "isSidechain": True, "message": {"model": "m", "usage": {"input_tokens": 99999}}})
        result = claude_usage.read_usage(SESSION, self.now)
        self.assertEqual((result["context"]["tokens"], result["context"]["capacity"], result["context"]["source"]),
                         (110, None, "transcript"))
        self.assertIsNone(result["context"]["used_percent"])

    def test_stale_snapshot_is_ignored(self):
        self.snapshot(self.now - claude_usage.SNAPSHOT_AGE - 60)
        self.transcript({"type": "assistant", "message": {"model": "m", "usage": {"input_tokens": 7}}})
        self.assertEqual(claude_usage.read_usage(SESSION, self.now)["context"]["source"], "transcript")

    def test_bad_session_id_reads_nothing(self):
        result = claude_usage.read_usage("../../etc", self.now)
        self.assertIsNone(result["session"])
        self.assertIsNone(result["context"]["tokens"])


if __name__ == "__main__":
    unittest.main()
