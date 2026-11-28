import json
import re
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


def layout_step_source():
    page = view.PAGE
    start = page.index("function step() {")
    end = page.index("function size()")
    return page[start:end]


CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def judge_page(rows, picks=(), syncs=()):
    data = {"nodes": [], "links": [], "shape": [], "ran": [], "reviewed": [], "prefers": [], "hidden": view.HIDDEN,
            "judge": {"rows": rows, "days": [["2026-11-28", {"outside": len(rows), "local": 0}]], "total": len(rows),
                      "picks": list(picks), "syncs": list(syncs)},
            "rule": "", "server": {"up": True, "nodes": 10, "links": 20, "files": 3, "url": "http://127.0.0.1:7474", "user": "neo4j",
                       "password_from": "keychain item harness-neo4j", "host": "mac", "version": "neo4j 5"}, "types": view.TYPES["ko"],
            "limits": {"t": 0.5, "l": 3, "ms": 5, "mr": 70, "n": 3}, "at": "2026-11-28 12:00"}
    page = (view.PAGE.replace("__LANG__", "ko").replace("__WORDS__", view.script_json(view.WORDS["ko"]))
            .replace("__DATA__", view.script_json(data)))
    return page.replace("open(tabs.includes(saved.tab) ? saved.tab : 'graph');", "open('judge');")


class LogTableTests(unittest.TestCase):
    def test_the_log_table_has_fixed_columns_that_wrap(self):
        self.assertIn("table.log{table-layout:fixed;min-width:720px}", view.PAGE)
        self.assertIn('<div class="scroll"><table class="log">', view.PAGE)
        self.assertIn('<table class="log"><colgroup>', view.PAGE)
        self.assertIn("table.log td{overflow-wrap:anywhere", view.PAGE)

    @unittest.skipUnless(CHROME.is_file(), "Google Chrome is not installed")
    def test_long_ids_do_not_squeeze_the_other_columns_in_a_real_browser(self):
        import subprocess
        long_id = "record:prehistoric-survival/" + "very-long-record-name-" * 6
        rows = [{"at": "2026-11-28T12:00:00", "judge": "outside", "seconds": 1.5, "judge_seconds": 0.4, "offered": 13,
                 "top": long_id, "top_score": 23.9, "chosen": [long_id, long_id + "-2", "skill:device-build-test"]}]
        probe = ("<script>addEventListener('load',()=>{const w=[...document.querySelectorAll('table.log th')]"
                 ".map(t=>Math.round(t.getBoundingClientRect().width));const s=[...document.querySelectorAll('.fstep')]"
                 ".map(e=>Math.round(e.getBoundingClientRect().height));document.title='W'+JSON.stringify({w,s});});</script>")
        with tempfile.TemporaryDirectory() as folder:
            page = Path(folder) / "judge.html"
            page.write_text(judge_page(rows, picks=[[long_id, 4]]).replace("</body>", probe + "</body>"), encoding="utf-8")
            measured = {}
            for width in (1280, 390):
                result = subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", f"--window-size={width},1200",
                                         "--virtual-time-budget=3000", "--dump-dom", page.as_uri()],
                                        capture_output=True, text=True, timeout=120)
                found = re.search(r"<title>W(\{.*?\})</title>", result.stdout)
                self.assertIsNotNone(found, result.stderr[-500:])
                measured[width] = json.loads(found.group(1))
        for width, sizes in measured.items():
            self.assertEqual(len(sizes["w"]), 4)
            self.assertGreaterEqual(min(sizes["w"]), 140, (width, sizes))
            self.assertEqual(len(sizes["s"]), 4)
        self.assertLess(max(measured[1280]["s"]), 500, measured)


class LayoutTests(unittest.TestCase):
    def test_the_graph_layout_stays_bounded_on_a_dense_graph(self):
        import shutil
        import subprocess
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        script = ("let heat = 1, drag = null;\n"
                  "const nodes = [];\n"
                  "for (let i = 0; i < 300; i++) nodes.push({id: 'n' + i, x: Math.random() * 900 - 450, y: Math.random() * 600 - 300, vx: 0, vy: 0, r: 4});\n"
                  "const byId = {}; nodes.forEach(n => byId[n.id] = n);\n"
                  "const links = []; for (let i = 1; i < 300; i++) links.push({a: nodes[0], b: nodes[i], k: 'x'});\n"
                  "for (let i = 0; i < 600; i++) links.push({a: nodes[i % 300], b: nodes[(i * 7 + 3) % 300], k: 'x'});\n"
                  + layout_step_source() +
                  "for (let i = 0; i < 600; i++) step();\n"
                  "const worst = Math.max(...nodes.map(n => Math.max(Math.abs(n.x), Math.abs(n.y))));\n"
                  "console.log(nodes.every(n => isFinite(n.x) && isFinite(n.y)) ? worst : 'nonfinite');\n")
        result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(result.stdout.strip(), "nonfinite")
        self.assertLess(float(result.stdout.strip()), 5000)


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

    def test_decisions_carry_the_top_candidate_and_the_sync_log(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "hook.jsonl").write_text(json.dumps({"at": "2026-11-28T10:00:00", "judge": "outside", "offered": 9,
                                                                 "top": "talk:game/x", "top_score": 30.5,
                                                                 "chosen": ["skill:a", "skill:a"]}) + "\n", encoding="utf-8")
            (Path(folder) / "sync.jsonl").write_text(
                json.dumps({"at": "2026-11-28T10:00:01", "seconds": 2.1, "changed": 5, "removed": 0, "held": 0,
                            "skipped": 0}) + "\njunk\n" + json.dumps({"at": "2026-11-28T10:05:00", "changed": "x"}) + "\n",
                encoding="utf-8")
            data = view.decisions(folder)
        self.assertEqual((data["rows"][0]["top"], data["rows"][0]["top_score"]), ("talk:game/x", 30.5))
        self.assertEqual(data["picks"], [("skill:a", 2)])
        self.assertEqual([(s["at"], s["changed"]) for s in data["syncs"]],
                         [("2026-11-28T10:05:00", 0), ("2026-11-28T10:00:01", 5)])

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
