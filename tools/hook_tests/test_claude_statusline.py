"""Tests for integrations/statusline/claude-usage.sh. Each test pipes a sample
Claude Code status line payload into the script and checks the rendered text."""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "integrations" / "statusline" / "claude-usage.sh"
SHELL = shutil.which("sh") or shutil.which("bash")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def render(payload):
    out = subprocess.run([SHELL, str(SCRIPT)], input=payload, capture_output=True,
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
        self.assertTrue(line.startswith("Opus │ ctx "), line)
        self.assertIn("32% (64k/200k)", line)
        self.assertRegex(line, r"5h █+░* 63% ↻\d\d:\d\d")
        self.assertRegex(line, r"7d █+░* 88% ↻\d\d/\d\d \d\d:\d\d")

    def test_percentage_is_derived_when_missing(self):
        line = render("""{"model":{"display_name":"Sonnet"},
          "context_window":{"context_window_size":200000,
            "current_usage":{"input_tokens":150000}}}""")
        self.assertIn("75% (150k/200k)", line)
        self.assertNotIn("5h", line)

    def test_empty_payload_marks_unknown(self):
        self.assertEqual(render("{}"), "? │ ctx ---------- ?% (?/?)")

    def test_million_token_window(self):
        line = render("""{"model":{"display_name":"Opus"},
          "context_window":{"context_window_size":1000000,"used_percentage":5,
            "current_usage":{"input_tokens":50000}}}""")
        self.assertIn("5% (50k/1.0M)", line)


if __name__ == "__main__":
    unittest.main()
