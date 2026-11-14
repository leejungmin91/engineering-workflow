"""Tests for integrations/statusline/claude-usage.sh. Each test pipes a sample
Claude Code status line payload into the script and checks the rendered text."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "integrations" / "statusline" / "claude-usage.sh"
SHELL = shutil.which("sh") or shutil.which("bash")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def render(payload, config=None):
    with tempfile.TemporaryDirectory() as home:
        if config is not None:
            Path(home, ".claude.json").write_text(json.dumps(config))
        out = subprocess.run([SHELL, str(SCRIPT)], input=payload, capture_output=True,
                             env={**os.environ, "HOME": home, "CLAUDE_CONFIG_DIR": home},
                             text=True, encoding="utf-8", check=True).stdout
    return ANSI.sub("", out).strip()


@unittest.skipIf(SHELL is None or shutil.which("jq") is None, "needs sh and jq on PATH")
class ClaudeStatuslineTest(unittest.TestCase):
    def test_full_payload_shows_context_and_limits(self):
        line = render("""{"model":{"display_name":"Opus"},
          "context_window":{"context_window_size":200000,"used_percentage":32,
            "current_usage":{"input_tokens":1000,"cache_creation_input_tokens":3000,
                             "cache_read_input_tokens":60000}},
          "rate_limits":{"five_hour":{"used_percentage":63.4,"resets_at":1794650000},
                         "seven_day":{"used_percentage":88,"resets_at":1795000000}}}""")
        self.assertTrue(line.startswith("Opus │ Context "), line)
        self.assertIn("32% used", line)
        self.assertIn("64k/200k", line)
        self.assertRegex(line, r"All · 5h\s+█+░* 63% used · 37% left")
        self.assertRegex(line, r"All · 7d\s+█+░* 88% used · 12% left")
        self.assertIn("reset", line)
        self.assertEqual(len(line.splitlines()), 3)

    def test_percentage_is_derived_when_missing(self):
        line = render("""{"model":{"display_name":"Sonnet"},
          "context_window":{"context_window_size":200000,
            "current_usage":{"input_tokens":150000}}}""")
        self.assertIn("75% used · 25% left · 150k/200k", line)
        self.assertNotIn("5h", line)

    def test_empty_payload_marks_unknown(self):
        self.assertEqual(render("{}"), "? │ Context ---------- — unavailable · ?/?")

    def test_million_token_window(self):
        line = render("""{"model":{"display_name":"Opus"},
          "context_window":{"context_window_size":1000000,"used_percentage":5,
            "current_usage":{"input_tokens":50000}}}""")
        self.assertIn("5% used · 95% left · 50k/1.0M", line)

    def cache(self):
        return {
            "oauthAccount": {"accountUuid": "account-a"},
            "cachedUsageUtilization": {
                "accountUuid": "account-a", "fetchedAtMs": int((time.time() - 185) * 1000),
                "utilization": {
                    "seven_day": {"utilization": 44, "resets_at": "2099-11-16T04:00:00.338558+00:00"},
                    "limits": [{"kind": "weekly_scoped", "percent": 75,
                                "resets_at": "2099-11-16T04:00:00.338695+00:00",
                                "scope": {"model": {"id": None, "display_name": "Fable"},
                                          "surface": None}}],
                },
            },
        }

    def test_model_quota_is_separate_from_account_and_marks_cache_age(self):
        line = render('{"model":{"display_name":"Fable"},"rate_limits":'
                      '{"seven_day":{"used_percentage":46}}}', self.cache())
        rows = line.splitlines()
        self.assertIn("All · 7d", rows[1])
        self.assertIn("46% used · 54% left", rows[1])
        self.assertNotIn("cached", rows[1])
        self.assertIn("Fable · 7d", rows[2])
        self.assertIn("75% used · 25% left", rows[2])
        self.assertIn("cached 3m", rows[2])

    def test_cache_supplies_account_limit_without_host_rate_limits(self):
        line = render('{}', self.cache())
        self.assertRegex(line, r"All · 7d\s+█+░* 44% used · 56% left.*cached 3m")

    def test_cache_from_another_account_is_not_displayed(self):
        config = self.cache()
        config["cachedUsageUtilization"]["accountUuid"] = "account-b"
        self.assertNotIn("75%", render('{}', config))

    def test_expired_model_limit_is_unavailable_instead_of_zero(self):
        config = self.cache()
        config["cachedUsageUtilization"]["utilization"]["limits"][0]["resets_at"] = "2020-01-01T00:00:00Z"
        line = render('{}', config)
        self.assertRegex(line, r"Fable · 7d\s+---------- — unavailable")
        self.assertNotIn("75%", line)

    def test_missing_fable_data_does_not_relabel_account_usage(self):
        line = render('{"model":{"display_name":"Fable 5"},"rate_limits":'
                      '{"seven_day":{"used_percentage":44}}}')
        self.assertRegex(line, r"Fable · 7d\s+---------- — unavailable")

    def test_partial_limits_do_not_invent_a_missing_window(self):
        line = render('{"rate_limits":{"seven_day":{"used_percentage":0}}}')
        self.assertNotIn("All · 5h", line)
        self.assertIn("0% used · 100% left", line)

    def test_malformed_cache_cannot_hide_valid_live_limits(self):
        for malformed in ([], "invalid", {"limits": "invalid"},
                          {"seven_day": [], "limits": [None, 42, {"scope": []}]}):
            with self.subTest(cache=malformed):
                config = self.cache()
                config["cachedUsageUtilization"]["utilization"] = malformed
                line = render('{"rate_limits":{"seven_day":{"used_percentage":46}}}', config)
                self.assertRegex(line, r"All · 7d\s+█+░* 46% used · 54% left")


if __name__ == "__main__":
    unittest.main()
