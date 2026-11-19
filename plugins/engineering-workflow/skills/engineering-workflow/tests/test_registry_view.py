import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import registry_neo4j as graph
import registry_view as view

LIVE = os.environ.get("HARNESS_NEO4J_TEST") == "1"


class OfflineTests(unittest.TestCase):
    def test_decisions_keep_ids_and_times_only_and_tolerate_junk(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = [{"at": "2026-11-19T10:00:00", "judge": "outside", "seconds": 1.2, "judge_seconds": 0.8,
                     "offered": 4, "chosen": ["skill:a"], "prompt": "SECRET PROMPT"},
                    {"at": "2026-11-19T10:01:00", "judge": "local after judge failure", "seconds": "x", "offered": "y",
                     "chosen": "z"}, "junk", [1]]
            (Path(folder) / "hook.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n{\n", encoding="utf-8")
            data = view.decisions(folder)
        self.assertEqual(data["total"], 2)
        self.assertNotIn("SECRET", json.dumps(data))
        self.assertEqual(data["rows"][1]["judge_seconds"], 0.8)
        self.assertEqual((data["rows"][0]["seconds"], data["rows"][0]["offered"], data["rows"][0]["chosen"]), (None, 0, []))
        self.assertEqual(data["days"], [("2026-11-19", {"outside": 1, "local": 1})])
        self.assertEqual(view.decisions(None)["total"], 0)

    def test_rule_text_comes_from_the_model_selection_section(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "CLAUDE.md").write_text("# x\n\n## Model selection\n\nUse the lightest.\n\n## Other\n\nno\n")
            self.assertEqual(view.rule_text({"user": folder}), "Use the lightest.")
            (Path(folder) / "CLAUDE.md").write_text("## Model selection\nUse the lightest.\n# Credentials\napi_key=SECRET\n")
            self.assertEqual(view.rule_text({"user": folder}), "Use the lightest.")
            self.assertEqual(view.rule_text({"user": str(Path(folder) / "missing")}), "")
        self.assertEqual(view.rule_text({}), "")

    def test_a_server_that_does_not_answer_is_reported_without_a_password(self):
        store = mock.Mock()
        store.run.side_effect = graph.StoreError("down")
        with mock.patch.dict(os.environ, {"HARNESS_NEO4J_PASSWORD": "hunter2"}):
            info = view.server(store)
        self.assertFalse(info["up"])
        self.assertNotIn("hunter2", json.dumps(info))
        self.assertEqual(info["password_from"], "HARNESS_NEO4J_PASSWORD")

    def test_embedded_json_cannot_end_or_bend_the_script(self):
        text = view.script_json({"x": "</script><!--<script>&\u2028", "rank": "<img src=x onerror=alert(1)>"})
        self.assertNotIn("<", text)
        self.assertNotIn(">", text)
        self.assertNotIn("&", text)
        self.assertEqual(json.loads(text)["x"], "</script><!--<script>&\u2028")
        self.assertIn("esc(W.fallback) + ' ' + esc(p.rank)", view.PAGE)


@unittest.skipUnless(LIVE, "set HARNESS_NEO4J_TEST=1 with a local graph server to run")
class LiveTests(unittest.TestCase):
    def test_page_is_written_with_every_tab_and_no_password(self):
        import test_registry_scan as fixtures
        import registry
        fixture = fixtures.ScanTests("test_glossary")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        config = Path(fixture.tmp.name) / "registry.json"
        fixtures.write(config, fixture.config)
        store = graph.connect("Ztest")
        graph.drop(store)
        self.addCleanup(graph.drop, store)
        registry.refresh(store, str(config))
        with tempfile.TemporaryDirectory() as out, mock.patch.dict(os.environ, {"HARNESS_NEO4J_PASSWORD": graph.password()}):
            page = view.build(str(config), None, "ko", "Ztest")
            path = view.write(page, out)
            text = path.read_text(encoding="utf-8")
        self.assertNotIn(graph.password(), text)
        data = json.loads(text.split("const D = ", 1)[1].split(", W = ", 1)[0])
        self.assertTrue(data["server"]["up"])
        self.assertIn("skill:store-release", [node["id"] for node in data["nodes"]])
        self.assertEqual(data["hidden"], ["commit", "asset", "source", "license"])


if __name__ == "__main__":
    unittest.main()
