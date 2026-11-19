import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import registry
import registry_neo4j as graph
import test_registry_scan as fixtures

LIVE = os.environ.get("HARNESS_NEO4J_TEST") == "1"
SPACE = "Ztest"


class OfflineTests(unittest.TestCase):
    def test_search_words_are_escaped(self):
        self.assertEqual(graph.lucene(["a+b", "x:y", " ", "plain two"]), '"a+b" OR "x:y" OR "plain" OR "two"')
        self.assertEqual(graph.lucene(["AND", 'say "hi"', "back\\slash"]), '"AND" OR "say" OR "\\"hi\\"" OR "back\\\\slash"')

    def test_names_that_reach_a_query_string_are_checked(self):
        self.assertEqual(graph.label("skill"), "Skill")
        self.assertEqual(graph.label("REVIEWED_BY"), "REVIEWED_BY")
        for bad in ("a b", "x`y", "1abc", "a-b", ""):
            with self.assertRaises(ValueError):
                graph.label(bad)
        with self.assertRaises(ValueError):
            graph.Store("http://127.0.0.1:1", "u", "p", "N) DETACH DELETE (x")

    def test_files_with_unknown_types_are_rejected_whole(self):
        good = {"kind": "skill", "hash": "h1", "nodes": [{"id": "skill:x", "type": "skill", "name": "x"}],
                "links": [{"from": "app:a", "type": "HAS", "to": "skill:x"}]}
        bad = [{"nodes": [{"id": "NFile:phantom", "type": "NFile", "path": "phantom"}], "links": []},
               {"nodes": [{"id": "app:x", "type": "skill"}], "links": []},
               {"nodes": [{"id": "skill:", "type": "skill"}], "links": []},
               {"nodes": [], "links": [{"from": "app:a", "type": "bad-type", "to": "skill:x"}]},
               {"nodes": [], "links": [{"from": "app:a", "type": "HAS", "to": "N:x"}]},
               {"nodes": [], "links": [{"from": "app:a", "type": "HAS", "to": 5}]},
               {"nodes": "nope", "links": []}]
        files = {"good.md": good, **{f"bad{number}.md": {"kind": "skill", "hash": f"b{number}", **entry}
                                     for number, entry in enumerate(bad)}}
        result = graph.checked(files)
        self.assertEqual(result["good.md"], good)
        for number in range(len(bad)):
            entry = result[f"bad{number}.md"]
            self.assertEqual((entry["nodes"], entry["links"], entry["hash"]), ([], [], f"b{number}"))
            self.assertIn("rejected", entry["error"])

    def test_properties_are_flattened_and_reserved_names_dropped(self):
        flat = graph.flat({"id": "x", "type": "skill", "name": "n", "events": ["Stop"], "odd key": 1, "deep": {"a": 1},
                           "order": 2})
        self.assertEqual(flat, {"name": "n", "events": ["Stop"], "deep": '{"a": 1}', "order": 2})

    def test_node_properties_come_from_every_file_that_states_the_node(self):
        files = {"b.md": {"nodes": [{"id": "skill:x", "type": "skill", "name": "x", "text": "from b"}]},
                 "a.md": {"nodes": [{"id": "skill:x", "type": "skill", "name": "x", "text": "from a", "model": "m"}]}}
        props, kinds, sources = graph.stated(files)
        self.assertEqual(props["skill:x"], {"name": "x", "text": "from b", "model": "m"})
        self.assertEqual(sources["skill:x"], ["a.md", "b.md"])

    def test_unreachable_server_exits_2_without_a_traceback(self):
        errors = io.StringIO()
        with mock.patch.dict(os.environ, {"HARNESS_NEO4J_URL": "http://127.0.0.1:9", "HARNESS_NEO4J_PASSWORD": "x"}):
            with redirect_stderr(errors):
                code = registry.main(["--no-sync", "status"])
        self.assertEqual(code, 2)
        self.assertIn("REGISTRY UNAVAILABLE", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())

    def test_output_lines(self):
        self.assertEqual(registry.show_find([]), ["no match"])
        self.assertEqual(registry.show_find([{"id": "skill:x", "name": "x", "score": 1.5, "path": "/p"},
                                             {"id": "app:shop", "name": "shop", "score": None, "path": None}]),
                         ["skill:x  score 1.5  /p", "app:shop  glossary"])
        self.assertEqual(registry.show_needs([{"id": "tool:mcp:a", "step": 1, "known": False},
                                              {"id": "skill:b", "step": 2, "known": True}]),
                         ["tool:mcp:a  (not found in any scanned file)", "  skill:b"])


@unittest.skipUnless(LIVE, "set HARNESS_NEO4J_TEST=1 with a local graph server to run")
class LiveTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.ScanTests("test_glossary")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixtures.write(fixture.game / ".claude" / "skills" / "pay" / "SKILL.md",
                       "---\nname: pay\ndescription: Take payments\nmetadata:\n  requires: \"mcp:app-store\"\n---\n")
        fixtures.write(fixture.shop / ".harness" / "assets" / "hero-v2.md",
                       "---\nid: hero-v2\nfile: \"Assets/Art/hero_old.png\"\nsource: \"Stock site\"\nlicense: \"CC BY 4.0\"\n---\n")
        self.fixture = fixture
        self.config = Path(fixture.tmp.name) / "registry.json"
        fixtures.write(self.config, fixture.config)
        self.store = graph.connect(SPACE)
        graph.drop(self.store)
        self.addCleanup(graph.drop, self.store)
        self.report = registry.refresh(self.store, str(self.config))

    def ids(self, rows):
        return [row["id"] for row in rows]

    def test_sync_writes_only_what_changed(self):
        self.assertEqual(len(self.report["changed"]), self.report["files"])
        again = registry.refresh(self.store, str(self.config))
        self.assertEqual((again["changed"], again["removed"]), ([], []))
        record = self.fixture.shop / ".harness" / "records" / "2026-11-19-refund-rounding.md"
        record.write_text(record.read_text(encoding="utf-8").replace('model: "sonnet"\n', ""), encoding="utf-8")
        after = registry.refresh(self.store, str(self.config))
        self.assertEqual(after["changed"], [str(record)])
        self.assertNotIn("RAN_ON", [row["link"] for row in graph.neighbors(self.store, "record:shop/2026-11-19-refund-rounding")])
        skill = self.fixture.shop / ".claude" / "skills" / "store-release" / "SKILL.md"
        model = f"MATCH (n:{SPACE} {{id: 'skill:store-release'}}) RETURN n.model AS model, n.effort AS effort"
        self.assertEqual(self.store.run(model), [{"model": "sonnet", "effort": "medium"}])
        skill.write_text(skill.read_text(encoding="utf-8").replace('  model: "sonnet"\n', ""), encoding="utf-8")
        registry.refresh(self.store, str(self.config))
        self.assertEqual(self.store.run(model), [{"model": None, "effort": "medium"}])
        record.unlink()
        gone = registry.refresh(self.store, str(self.config))
        self.assertEqual(gone["removed"], [str(record)])
        self.assertEqual(graph.resolve(self.store, "record:shop/2026-11-19-refund-rounding"), [])
        rebuilt = registry.refresh(self.store, str(self.config), rebuild=True)
        self.assertEqual([rebuilt[key] for key in ("nodes", "links", "files")], [gone[key] for key in ("nodes", "links", "files")])

    def test_a_hostile_file_cannot_remove_what_another_file_states(self):
        scanned = registry.registry_scan.scan(json.loads(self.config.read_text(encoding="utf-8")))
        before = graph.counts(self.store)
        scanned["files"]["zz-hostile.md"] = {"kind": "skill", "hash": "evil", "links": [], "nodes": [
            {"id": "skill:pay", "type": f"{SPACE}File", "path": "phantom"}]}
        scanned["files"]["zz-broken-link.md"] = {"kind": "skill", "hash": "evil2", "nodes": [], "links": [
            {"from": "app:shop", "type": "bad-type", "to": "skill:pay"}]}
        report = graph.sync(self.store, scanned)
        self.assertEqual(sorted(Path(path).name for path in report["skipped"]), ["zz-broken-link.md", "zz-hostile.md"])
        self.assertEqual(graph.resolve(self.store, "skill:pay"), ["skill:pay"])
        again = registry.refresh(self.store, str(self.config))
        self.assertEqual(len(again["removed"]), 2)
        self.assertEqual(graph.resolve(self.store, "skill:pay"), ["skill:pay"])
        self.assertEqual({key: again[key] for key in ("nodes", "links")}, {key: before[key] for key in ("nodes", "links")})

    def test_duplicate_alias_lines_do_not_make_a_name_ambiguous(self):
        second = Path(self.fixture.tmp.name) / "glossary2.txt"
        fixtures.write(second, "눈밥 = app:shop\n")
        config = json.loads(self.config.read_text(encoding="utf-8"))
        scanned = registry.registry_scan.scan(config)
        extra = registry.registry_scan.scan({"apps": [], "glossary": str(second)})["files"][str(second)]
        scanned["files"][str(second)] = extra
        graph.sync(self.store, scanned)
        self.assertEqual(graph.resolve(self.store, "눈밥"), ["app:shop"])
        self.assertEqual(self.ids(graph.find(self.store, ["눈밥"])).count("app:shop"), 1)

    def test_find_uses_text_and_the_glossary(self):
        self.assertEqual(self.ids(graph.find(self.store, ["눈밥"]))[0], "app:shop")
        self.assertIn("record:shop/2026-11-19-refund-rounding", self.ids(graph.find(self.store, ["refund", "totals"])))
        self.assertEqual(self.ids(graph.find(self.store, ["store", "release", "notes"], "skill"))[0], "skill:store-release")
        self.assertEqual(graph.find(self.store, ["zzzz-nothing"]), [])
        for words in (["a+b:(c"], ["AND"], ["OR", "NOT"], ['"'], ["refund AND zzzz"]):
            self.assertIsInstance(graph.find(self.store, words), list)
        self.assertEqual(graph.find(self.store, ["a+b:(c"]), [])
        self.assertIn("record:shop/2026-11-19-refund-rounding", self.ids(graph.find(self.store, ["refund AND zzzz"])))

    def test_resolve_accepts_ids_names_and_glossary_words(self):
        self.assertEqual(graph.resolve(self.store, "skill:pay"), ["skill:pay"])
        self.assertEqual(graph.resolve(self.store, "pay"), ["skill:pay"])
        self.assertEqual(graph.resolve(self.store, "눈밥"), ["app:shop"])
        self.assertEqual(graph.resolve(self.store, "T2"), ["task:shop/T2"])
        self.assertEqual(sorted(graph.resolve(self.store, "flow")), ["plugin:flow", "skill:flow"])

    def test_impact_follows_requirements_back_to_apps(self):
        result = graph.impact(self.store, "tool:mcp:app-store")
        self.assertEqual(result["dependents"], ["skill:pay", "skill:store-release"])
        self.assertEqual(self.ids(result["apps"]), ["app:game", "app:shop"])
        self.assertEqual(result["apps"][1]["open_tasks"], 1)
        self.assertEqual(self.ids(result["records"]), ["record:shop/2026-11-19-refund-rounding"])
        self.assertEqual(result["records"][0]["links"], ["CONCERNS", "USED"])
        plugin = graph.impact(self.store, "skill:flow")
        self.assertEqual(self.ids(plugin["apps"]), ["app:game", "app:shop", "checkout:trees/game-wt"])
        self.assertIn("INSTALLED 1.0.0 (project)", plugin["apps"][0]["how"])

    def test_spread_lists_apps_without_a_record_for_the_same_concern(self):
        result = graph.spread(self.store, "record:shop/2026-11-19-refund-rounding")
        self.assertEqual(result["concerns"], ["skill:payments", "tool:mcp:app-store"])
        self.assertEqual(self.ids(result["needs"]), ["app:game"])
        self.assertEqual(self.ids(result["done"]), ["app:shop"])

    def test_lineage_needs_latest_and_unused(self):
        chain = graph.lineage(self.store, "asset:shop/hero-v3")
        self.assertEqual(self.ids(chain), ["asset:shop/hero-v3", "asset:shop/hero-v2"])
        self.assertEqual(chain[0]["approved_by"], ["2026-11-17 portrait review"])
        self.assertEqual((chain[1]["source"], chain[1]["license"]), ("Stock site", "CC BY 4.0"))
        needed = graph.needs(self.store, "skill:store-release")
        self.assertEqual({row["id"]: row["known"] for row in needed},
                         {"tool:mcp:app-store": False, "skill:engineering-workflow": False})
        self.assertEqual(self.ids(graph.latest(self.store, "skill:ios-release")), ["skill:store-release"])
        self.assertEqual(self.ids(graph.latest(self.store, "skill:pay")), ["skill:pay"])
        report = graph.unused(self.store)
        self.assertEqual(report["unreachable"], [])
        self.assertEqual(self.ids(report["never_recorded"]), ["skill:flow", "skill:pay"])

    def test_command_prints_few_lines_and_reports_unknown_names(self):
        base = ["--space", SPACE, "--config", str(self.config)]
        for arguments, expected in ((["neighbors", "T2"], "task:shop/T1"), (["lineage", "hero-v3"], "CC BY 4.0"),
                                    (["spread", "2026-11-19-refund-rounding"], "app:game"), (["status"], "record 1")):
            output = io.BytesIO()
            with mock.patch.object(sys, "stdout", mock.Mock(buffer=output)):
                self.assertEqual(registry.main(base + arguments), 0)
            self.assertIn(expected, output.getvalue().decode("utf-8"))
            self.assertLess(len(output.getvalue().splitlines()), 20)
        with mock.patch("builtins.print") as printed:
            self.assertEqual(registry.main(base + ["needs", "no-such-thing"]), 1)
            self.assertEqual(registry.main(base + ["impact", "flow"]), 1)
        self.assertIn("NOT FOUND", printed.call_args_list[0].args[0])
        self.assertIn("AMBIGUOUS", printed.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
