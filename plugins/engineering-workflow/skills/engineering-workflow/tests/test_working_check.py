import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import working_check as check

BODY = """# Work

## Waiting for the user (parked decisions)

- **Decided 2026-11-20 (the user: ok):** the grass is settled.
- The bridge look is open. Default: the raft.
- The storage size is open. Default: 40.

## Notes

Something else.
"""


class WorkingCheckTests(unittest.TestCase):
    def test_context_keeps_only_decided_paragraphs(self):
        context = check.decided_context(BODY)
        self.assertIn("grass is settled", context)
        self.assertNotIn("storage size", context)

    def test_fenced_examples_and_resolved_markers_are_handled(self):
        body = ("## Waiting for the user (parked decisions)\n\n"
                "```\n- **Decided:** Choose stone for the bridge\n```\n\n"
                "- [resolved] Storage capacity: use 40 places\n")
        context = check.decided_context(body)
        self.assertNotIn("Choose stone", context)
        self.assertIn("Storage capacity", context)

    def test_longer_fence_and_strikethrough_and_undecided_are_handled(self):
        body = ("## Waiting for the user (parked decisions)\n\n"
                "````\n```\n- **Decided:** Choose stone for the bridge\n```\n````\n\n"
                "- ~~Bridge: use stone~~\n\n"
                "- The night is undecided and unanswered for now.\n")
        context = check.decided_context(body)
        self.assertNotIn("Choose stone", context)
        self.assertIn("Bridge: use stone", context)
        self.assertNotIn("undecided", context)

    def test_a_heading_or_a_language_tag_inside_a_fence_does_not_end_the_section(self):
        body = ("## Waiting for the user (parked decisions)\n\n"
                "```md\n## Example\n```python\n- **Decided:** Choose stone\n```\n\n"
                "- [resolved] Storage capacity: use 40 places\n\n## Notes\n\n- Decided: not in section\n")
        context = check.decided_context(body)
        self.assertNotIn("Choose stone", context)
        self.assertIn("Storage capacity", context)
        self.assertNotIn("not in section", context)

    def test_entries_ignore_fenced_headings_and_keep_real_items(self):
        body = ("## Waiting for the user (parked decisions)\n\n"
                "```\n## Example\n- Example item inside the fence\n```\n\n"
                "- The real open question\n  continues here.\n\n"
                "- ~~Old question~~\n")
        self.assertEqual(check.entries(body), ["The real open question continues here."])

    def test_an_inline_code_span_is_not_a_fence(self):
        body = ("## Waiting for the user (parked decisions)\n\n"
                "- Use ```example``` in the note, then the real open question\n\n"
                "- Second open question\n")
        self.assertEqual(check.entries(body), ["Use ```example``` in the note, then the real open question",
                                               "Second open question"])

    def test_suggestions_are_listed_and_the_file_is_not_written(self):
        def fake_ask(body, seconds):
            item = body["questions"]["q"]["instructions"]
            value = 0.9 if "bridge look" in item else 0.1
            return {"answers": {"q": {"type": "noul", "noul": value}}}

        with mock.patch.object(check.jev, "ask", side_effect=fake_ask):
            root = Path(self.id().replace(".", "_") + "_dir")
            root.mkdir(exist_ok=True)
            (root / "WORKING.md").write_text(BODY, encoding="utf-8")
            before = (root / "WORKING.md").read_text(encoding="utf-8")
            with mock.patch("sys.stdout") as out:
                check.main([str(root)])
            after = (root / "WORKING.md").read_text(encoding="utf-8")
            (root / "WORKING.md").unlink()
            root.rmdir()
        self.assertEqual(before, after)
        self.assertTrue(out.write.called)


if __name__ == "__main__":
    unittest.main()
