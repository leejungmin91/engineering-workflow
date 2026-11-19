import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("record", SCRIPTS / "record.py")
record = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(record)

import registry_scan


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "shop"
        self.root.mkdir()
        self.addCleanup(self.tmp.cleanup)

    def run_tool(self, *args, stdin=None):
        out, err, raw = io.StringIO(), io.StringIO(), io.BytesIO()
        out.buffer = raw
        source = io.StringIO(stdin or "")
        source.isatty = lambda: stdin is None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), mock.patch.object(sys, "stdin", source):
            code = record.main(["--root", str(self.root), *args])
        return code, out.getvalue() + raw.getvalue().decode("utf-8"), err.getvalue()

    def folder(self):
        return self.root / ".harness" / "records"

    def test_new_writes_a_record_the_scanner_reads(self):
        code, out, _ = self.run_tool("new", '환불 "반올림"을 줄 단위로:\n옮김', "--date", "2026-11-19", "--task", "T2",
                                     "--skills", "engineering-workflow, payments", "--model", "sonnet",
                                     "--review", "codex: no findings", "--concerns", "skill:payments",
                                     "--decisions", "Ship behind a flag", stdin="세율이 섞이면 합계가 1원 어긋났다.\n")
        self.assertEqual(code, 0)
        path = self.folder() / "2026-11-19-환불-반올림-을-줄-단위로-옮김.md"
        self.assertEqual(out.strip(), str(path))
        content = path.read_text(encoding="utf-8")
        self.assertNotIn("\r", content)
        fields, body = registry_scan.frontmatter(content)
        self.assertEqual(fields["title"], "환불 '반올림'을 줄 단위로: 옮김")
        self.assertEqual(fields["id"], path.stem)
        self.assertEqual(body.strip(), "세율이 섞이면 합계가 1원 어긋났다.")
        self.assertNotIn("commits", fields)
        nodes, links = registry_scan.record_facts(content, {"app": "app:shop"})
        self.assertEqual(nodes[0]["date"], "2026-11-19")
        self.assertIn(("record:shop/" + path.stem, "USED", "skill:payments"),
                      [(link["from"], link["type"], link["to"]) for link in links])
        self.assertEqual(self.run_tool("check")[:2], (0, "records ok\n"))

    def test_new_refuses_to_overwrite_or_write_nothing(self):
        self.assertEqual(self.run_tool("new", "Same title", "--date", "2026-11-19", "--body", "first")[0], 0)
        code, _, err = self.run_tool("new", "Same title", "--date", "2026-11-19", "--body", "second")
        self.assertEqual(code, 1)
        self.assertIn("exists", err)
        self.assertIn("first", (self.folder() / "2026-11-19-same-title.md").read_text(encoding="utf-8"))
        self.assertEqual(self.run_tool("new", "No body", "--date", "2026-11-19")[0], 2)
        self.assertEqual(self.run_tool("new", "No body", "--date", "2026-11-19", stdin="  \n")[0], 2)
        self.assertEqual(self.run_tool("new", "  ", "--body", "x")[0], 2)
        self.assertEqual(self.run_tool("new", "Bad date", "--date", "19-11-2026", "--body", "x")[0], 2)
        self.assertEqual(len(list(self.folder().glob("*.md"))), 1)

    def test_new_uses_today_without_a_date(self):
        code, out, _ = self.run_tool("new", "Today", "--body", "x")
        self.assertEqual(code, 0)
        self.assertRegex(Path(out.strip()).name, r"^\d{4}-\d{2}-\d{2}-today\.md$")

    def test_check_reports_each_kind_of_problem(self):
        self.folder().mkdir(parents=True)
        files = {
            "2026-11-19-good.md": "---\nid: 2026-11-19-good\ntitle: Good\n---\n\nDone.\n",
            "2026-11-19-other.md": "---\nid: 2026-11-19-renamed\ntitle: Other\n---\n\nDone.\n",
            "2026-11-19-untitled.md": "---\nid: 2026-11-19-untitled\n---\n\nDone.\n",
            "2026-11-19-blank.md": "---\nid: 2026-11-19-blank\ntitle: \"  \"\n---\n\nDone.\n",
            "2026-11-19-empty.md": "---\nid: 2026-11-19-empty\ntitle: Empty\n---\n\n",
            "2026-11-19-plain.md": "No frontmatter here.\n",
            "2026-11-19-nested.md": "---\nid: 2026-11-19-nested\ntitle: Nested\nskills:\n  a: b\n---\n\nDone.\n",
            "undated.md": "---\nid: undated\ntitle: Undated\n---\n\nDone.\n",
            "2026-11-19-long.md": "---\nid: 2026-11-19-long\ntitle: Long\n---\n\n" + "line\n\n" * 16,
        }
        for name, content in files.items():
            (self.folder() / name).write_text(content, encoding="utf-8")
        code, out, _ = self.run_tool("check")
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), [
            "2026-11-19-blank.md: error: has no title",
            "2026-11-19-empty.md: error: has no body",
            "2026-11-19-long.md: warning: body has 16 lines; keep it under about 15",
            "2026-11-19-nested.md: error: skills must be one line of text",
            "2026-11-19-other.md: error: id is '2026-11-19-renamed', the file name says '2026-11-19-other'",
            "2026-11-19-plain.md: error: has no frontmatter",
            "2026-11-19-untitled.md: error: has no title",
            "undated.md: warning: file name does not start with a date, so it has no place in time",
            "records have errors"])

    def test_check_passes_with_warnings_only_and_with_no_folder(self):
        self.assertEqual(self.run_tool("check")[:2], (0, "records ok\n"))
        self.folder().mkdir(parents=True)
        (self.folder() / "undated.md").write_text("---\nid: undated\ntitle: Undated\n---\n\nDone.\n", encoding="utf-8")
        code, out, _ = self.run_tool("check")
        self.assertEqual(code, 0)
        self.assertTrue(out.endswith("records ok\n"))


if __name__ == "__main__":
    unittest.main()
