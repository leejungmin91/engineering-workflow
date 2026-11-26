import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import time
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import registry
import registry_scan
import registry_neo4j as graph
import test_registry_scan as fixtures

LIVE = os.environ.get("HARNESS_NEO4J_TEST") == "1"
SPACE = "Ztest"


class OfflineTests(unittest.TestCase):
    def test_search_words_are_escaped(self):
        self.assertEqual(graph.lucene(["a+b", "x:y", " ", "plain two"]), '"a+b" OR "x:y" OR "plain" OR "two"')
        self.assertEqual(graph.lucene(["AND", 'say "hi"', "back\\slash"]), '"AND" OR "say" OR "\\"hi\\"" OR "back\\\\slash"')
        self.assertEqual(graph.lucene(["훅을"], ["훅", "hook", "훅을"]), '"훅을"^3 OR "훅" OR "hook"')

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
        commits = {"git:game/2026-11": {"nodes": [{"id": "commit:game/abc1234", "type": "commit", "name": "Real subject"}]},
                   "work/shop/.harness/assets/a.md": {"nodes": [{"id": "commit:game/abc1234", "type": "commit",
                                                                 "name": "abc1234"}]}}
        self.assertEqual(graph.stated(commits)[0]["commit:game/abc1234"]["name"], "Real subject")
        rows = [{"id": "skill:k", "props": {"name": "k", "text": "훅을 고친다", "keywords": "앱에서"}},
                {"id": "skill:e", "props": {"name": "e", "text": "English only"}}]
        with mock.patch.dict(os.environ):
            os.environ.pop("HARNESS_TOKENIZER_URL", None)
            graph.add_terms(rows)
        self.assertEqual(rows[0]["props"]["terms"].split(), ["훅", "앱"])
        self.assertNotIn("terms", rows[1]["props"])

    def test_one_sync_at_a_time(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(registry, "LOCK", Path(folder) / "lock"), \
                mock.patch.object(registry, "LOCK_WAIT", 0.5):
            with registry.held(False):
                with self.assertRaises(registry.Busy):
                    with registry.held(False):
                        pass
                started = time.monotonic()
                with self.assertRaises(registry.Busy):
                    with registry.held(True):
                        pass
                self.assertGreaterEqual(time.monotonic() - started, 0.5)
            with registry.held(False):
                pass
            config = Path(folder) / "registry.json"
            config.write_text('{"apps": []}', encoding="utf-8")
            with mock.patch.object(graph, "sync", return_value={"done": True}) as sync:
                with registry.held(False):
                    with self.assertRaises(registry.Busy):
                        registry.refresh(None, str(config), wait=False)
                self.assertFalse(sync.called)
                self.assertEqual(registry.refresh(None, str(config), wait=False), {"done": True})
            with mock.patch.object(graph, "connect", return_value=mock.Mock()), \
                    mock.patch.object(registry, "refresh", side_effect=registry.Busy("busy")), \
                    mock.patch.object(graph, "status") as status, redirect_stderr(io.StringIO()) as err:
                self.assertEqual(registry.main(["--config", str(config), "status"]), 2)
            self.assertFalse(status.called)
            self.assertIn("REGISTRY UNAVAILABLE: Busy", err.getvalue())

    def test_a_sync_from_the_hook_never_waits_has_no_file_limit_and_logs_what_it_did(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "registry.json"
            config.write_text(json.dumps({"apps": [], "usage": str(Path(folder) / "usage.json")}), encoding="utf-8")
            log = Path(folder) / "log"
            report = {"changed": ["a"] * 140, "removed": [], "held": [], "skipped": [], "nodes": 5, "links": 7, "files": 9}
            with mock.patch.dict(os.environ, {"HARNESS_REGISTRY_LOG": str(log)}), \
                    mock.patch.object(graph, "connect", return_value=mock.Mock()), \
                    mock.patch.object(registry, "refresh", return_value=report) as refresh, \
                    mock.patch.object(registry.registry_usage, "update") as usage:
                self.assertEqual(registry.main(["--config", str(config), "sync", "--from-hook"]), 0)
                refresh.return_value = {**report, "changed": []}
                self.assertEqual(registry.main(["--config", str(config), "sync", "--from-hook"]), 0)
                refresh.side_effect = registry.Busy("busy")
                with redirect_stderr(io.StringIO()):
                    self.assertEqual(registry.main(["--config", str(config), "sync", "--from-hook"]), 2)
            self.assertEqual(refresh.call_args.kwargs, {"wait": False})
            self.assertFalse(usage.called)
            lines = [json.loads(line) for line in (log / "sync.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([(line["changed"], line["links"]) for line in lines], [(140, 7)])

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
        self.assertEqual(registry.show_lineage([{"step": 0, "id": "asset:a/face", "file": "f.png", "source": None,
                                                 "license": None, "made_by": [], "approved_by": ["A"],
                                                 "commits": ["commit:a/abc1234  Subject"]}]),
                         ["asset:a/face  f.png  approved: A", "  made in commit:a/abc1234  Subject"])


@unittest.skipUnless(LIVE, "set HARNESS_NEO4J_TEST=1 with a local graph server to run")
class LiveTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.ScanTests("test_glossary")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixtures.write(fixture.game / ".claude" / "skills" / "pay" / "SKILL.md",
                       "---\nname: pay\ndescription: Take payments\nmetadata:\n  requires: \"mcp:app-store\"\n---\n")
        fixtures.write(fixture.game / ".claude" / "skills" / "korean" / "SKILL.md",
                       "---\nname: hook-care\ndescription: 훅을 고치기 전에 영향을 확인한다\nmetadata:\n  keywords: \"잠금장치, 안전핀\"\n---\n")
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
        self.assertEqual(again["removed"], [])
        self.assertEqual(graph.resolve(self.store, "skill:pay"), ["skill:pay"])
        self.assertEqual({key: again[key] for key in ("nodes", "links")}, {key: before[key] for key in ("nodes", "links")})

    def test_a_file_that_turns_bad_keeps_what_it_stated_before(self):
        scanned = registry.registry_scan.scan(json.loads(self.config.read_text(encoding="utf-8")))
        path = next(key for key, entry in scanned["files"].items() if any(item["id"] == "skill:pay" for item in entry["nodes"]))
        scanned["files"][path] = {**scanned["files"][path], "hash": "newer",
                                  "nodes": scanned["files"][path]["nodes"] + [{"id": "skill:", "type": "skill"}]}
        report = graph.sync(self.store, scanned)
        self.assertIn(path, report["skipped"])
        self.assertNotIn(path, report["changed"])
        self.assertEqual(graph.resolve(self.store, "skill:pay"), ["skill:pay"])

    def test_a_sync_that_would_wipe_many_nodes_is_held_until_a_rebuild(self):
        scanned = registry.registry_scan.scan(json.loads(self.config.read_text(encoding="utf-8")))
        many = [{"id": f"commit:shop/{number:07x}", "type": "commit", "name": f"c{number}"} for number in range(400)]
        scanned["files"]["git:shop/2026-11"] = {"kind": "commits", "hash": "m1", "nodes": many, "links": []}
        graph.sync(self.store, scanned)
        before = graph.counts(self.store)["nodes"]
        scanned["files"]["git:shop/2026-11"] = {"kind": "commits", "hash": "m2", "nodes": many[:3], "links": []}
        held = graph.sync(self.store, scanned)
        self.assertIn("git:shop/2026-11", held["held"])
        self.assertEqual(graph.counts(self.store)["nodes"], before)
        rebuilt = graph.sync(self.store, scanned, rebuild=True)
        self.assertLess(rebuilt["nodes"], before)

    def test_a_hook_sync_with_too_many_changed_files_touches_nothing(self):
        links = graph.counts(self.store)["links"]
        scanned = registry.registry_scan.scan(json.loads(self.config.read_text(encoding="utf-8")))
        for entry in scanned["files"].values():
            entry["hash"] = "new scanner " + entry["hash"]
        held = graph.sync(self.store, scanned, limit=2)
        self.assertEqual(held["changed"], [])
        self.assertEqual(len(held["held"]), len(scanned["files"]))
        self.assertEqual(graph.counts(self.store)["links"], links)
        done = graph.sync(self.store, scanned)
        self.assertEqual(len(done["changed"]), len(scanned["files"]))
        self.assertEqual(done["links"], links)

    def test_a_shared_node_keeps_a_skipped_files_source(self):
        scanned = registry.registry_scan.scan(json.loads(self.config.read_text(encoding="utf-8")))
        shared = {"id": "skill:shared-one", "type": "skill", "name": "shared-one"}
        scanned["files"]["zz-a.md"] = {"kind": "skill", "hash": "a1", "nodes": [shared], "links": []}
        scanned["files"]["zz-b.md"] = {"kind": "skill", "hash": "b1", "nodes": [shared], "links": []}
        graph.sync(self.store, scanned)
        scanned["files"]["zz-a.md"] = {"kind": "skill", "hash": "a2", "nodes": [shared, {"id": "skill:", "type": "skill"}],
                                       "links": []}
        scanned["files"]["zz-b.md"] = {"kind": "skill", "hash": "b2", "nodes": [], "links": []}
        graph.sync(self.store, scanned)
        self.assertEqual(graph.resolve(self.store, "skill:shared-one"), ["skill:shared-one"])
        srcs = self.store.run(f"MATCH (n:{SPACE} {{id: 'skill:shared-one'}}) RETURN n.srcs AS srcs")[0]["srcs"]
        self.assertEqual(srcs, ["zz-a.md"])

    def test_a_skipped_files_properties_stay_on_a_shared_node(self):
        scanned = registry.registry_scan.scan(json.loads(self.config.read_text(encoding="utf-8")))
        scanned["files"]["zz-a.md"] = {"kind": "skill", "hash": "a1", "links": [], "nodes": [
            {"id": "skill:shared-two", "type": "skill", "name": "shared-two", "model": "opus"}]}
        scanned["files"]["zz-b.md"] = {"kind": "skill", "hash": "b1", "links": [], "nodes": [
            {"id": "skill:shared-two", "type": "skill", "name": "shared-two"}]}
        graph.sync(self.store, scanned)
        scanned["files"]["zz-a.md"] = {**scanned["files"]["zz-a.md"], "hash": "a2",
                                       "nodes": scanned["files"]["zz-a.md"]["nodes"] + [{"id": "skill:", "type": "skill"}]}
        scanned["files"]["zz-b.md"] = {"kind": "skill", "hash": "b2", "links": [], "nodes": [
            {"id": "skill:shared-two", "type": "skill", "name": "shared-two", "text": "new"}]}
        graph.sync(self.store, scanned)
        row = self.store.run(f"MATCH (n:{SPACE} {{id: 'skill:shared-two'}}) RETURN n.model AS model, n.text AS text")[0]
        self.assertEqual((row["model"], row["text"]), ("opus", "new"))

    def test_nodes_still_linked_by_another_file_are_not_counted_as_lost(self):
        scanned = registry.registry_scan.scan(json.loads(self.config.read_text(encoding="utf-8")))
        nodes = [{"id": f"skill:kept-{number}", "type": "skill", "name": f"kept-{number}"} for number in range(400)]
        links = [{"from": "app:shop", "type": "HAS", "to": item["id"]} for item in nodes]
        scanned["files"]["zz-decl.md"] = {"kind": "skill", "hash": "d1", "nodes": nodes, "links": []}
        scanned["files"]["zz-link.md"] = {"kind": "skill", "hash": "k1", "nodes": [], "links": links}
        graph.sync(self.store, scanned)
        scanned["files"]["zz-decl.md"] = {"kind": "skill", "hash": "d2", "nodes": [], "links": []}
        report = graph.sync(self.store, scanned)
        self.assertEqual(report["held"], [])
        self.assertEqual(graph.resolve(self.store, "skill:kept-1"), ["skill:kept-1"])

    def test_link_only_nodes_count_toward_the_hold(self):
        scanned = registry.registry_scan.scan(json.loads(self.config.read_text(encoding="utf-8")))
        links = [{"from": "app:shop", "type": "HAS", "to": f"skill:lone-{number}"} for number in range(400)]
        scanned["files"]["zz-links.md"] = {"kind": "skill", "hash": "l1", "nodes": [], "links": links}
        graph.sync(self.store, scanned)
        before = graph.counts(self.store)["nodes"]
        del scanned["files"]["zz-links.md"]
        held = graph.sync(self.store, scanned)
        self.assertIn("zz-links.md", held["held"])
        self.assertEqual(graph.counts(self.store)["nodes"], before)

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

    def test_find_handles_korean_particles_keywords_and_english_text(self):
        self.assertEqual(self.ids(graph.find(self.store, ["훅"], "skill"))[0], "skill:hook-care")
        self.assertEqual(self.ids(graph.find(self.store, ["훅이", "뭐야"], "skill"))[0], "skill:hook-care")
        self.assertEqual(self.ids(graph.find(self.store, ["안전핀"]))[0], "skill:hook-care")
        self.assertIn("record:shop/2026-11-19-refund-rounding", self.ids(graph.find(self.store, ["환불했던", "작업"])))
        self.assertEqual(self.ids(graph.find(self.store, ["스토어", "릴리즈를", "준비"], "skill"))[0], "skill:store-release")
        self.assertEqual(self.ids(graph.find(self.store, ["눈밥에서", "쓰는", "것"]))[0], "app:shop")

    def test_glossary_terms_match_whole_words_and_long_queries_are_capped(self):
        extra = Path(self.fixture.tmp.name) / "glossary3.txt"
        fixtures.write(extra, "app = app:game\n계속 진행 = rule:keep-going\n")
        scanned = registry.registry_scan.scan(json.loads(self.config.read_text(encoding="utf-8")))
        scanned["files"][str(extra)] = registry.registry_scan.scan({"apps": [], "glossary": str(extra)})["files"][str(extra)]
        graph.sync(self.store, scanned)
        self.assertNotIn("app:game", self.ids(graph.find(self.store, ["happy"])))
        self.assertEqual(self.ids(graph.find(self.store, ["app"]))[0], "app:game")
        self.assertEqual(self.ids(graph.find(self.store, ["계속", "진행", "규칙"]))[0], "rule:keep-going")
        many = graph.find(self.store, [f"w{number}" for number in range(5000)] + ["refund"])
        self.assertIsInstance(many, list)
        ids = self.ids(graph.find(self.store, ["refund", "store", "release"], limit=20))
        self.assertEqual(len(ids), len(set(ids)))

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
        self.assertEqual(chain[0]["commits"], [])
        needed = graph.needs(self.store, "skill:store-release")
        self.assertEqual({row["id"]: row["known"] for row in needed},
                         {"tool:mcp:app-store": False, "skill:engineering-workflow": False})
        self.assertEqual(self.ids(graph.latest(self.store, "skill:ios-release")), ["skill:store-release"])
        self.assertEqual(self.ids(graph.latest(self.store, "skill:pay")), ["skill:pay"])
        report = graph.unused(self.store)
        self.assertEqual(report["unreachable"], [])
        self.assertEqual(self.ids(report["never_recorded"]), ["skill:flow", "skill:hook-care", "skill:pay"])

    def test_sessions_list_machine_and_lane_work(self):
        fixtures.write(self.fixture.game / "WORKING.md",
                       "## Sessions\n\n- build: the build pane\n- planner: the planner pane\n\n"
                       "## Lane 1: build\n\n- build: the bridge repair\n")
        registry.refresh(self.store, str(self.config))
        rows = {row["name"]: row for row in graph.sessions(self.store, "app:game")}
        self.assertEqual(sorted(rows), ["build", "planner"])
        self.assertEqual(rows["build"]["holds"], [{"lane": "Lane 1: build", "work": "the bridge repair"}])
        self.assertEqual(rows["planner"]["holds"], [])
        self.assertEqual(graph.sessions(self.store, "app:shop"), [])

    def test_licenses_group_assets_and_filter_what_needs_attribution(self):
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        game = self.fixture.game
        fixtures.write(game / "Audio" / "CREDITS.md", "| File | Licence | Source |\n| --- | --- | --- |\n"
                       "| `a` | CC0 | https://free.example.org/a |\n| `b` | CC0 | https://free.example.org/b |\n")
        fixtures.write(game / "Icons" / "CREDITS.md", "Icons, licence CC BY 3.0.\n\n| File |\n| --- |\n| `axe` |\n")
        fixtures.write(game / "Ui" / "CREDITS.md", "Made here.\n\n| File |\n| --- |\n| `panel` |\n")
        subprocess.run(["git", "init", "-q", str(game)], check=True)
        subprocess.run(["git", "-C", str(game), "add", "Audio", "Icons", "Ui"], check=True)
        registry.refresh(self.store, str(self.config))
        rows = {(row["group"], row["license"]): row for row in graph.licenses(self.store, "app:game")}
        self.assertEqual(sorted(rows), [("audio", "CC0"), ("icons", "CC BY 3.0"), ("ui", "unknown")])
        self.assertEqual((rows[("audio", "CC0")]["assets"], rows[("audio", "CC0")]["sources"]),
                         (2, ["source:free.example.org"]))
        self.assertEqual(rows[("ui", "unknown")]["attribution"], "check")
        needed = graph.licenses(self.store, "app:game", attribution=True)
        self.assertEqual([row["group"] for row in needed], ["icons", "ui"])
        self.assertEqual(graph.licenses(self.store, "app:game", group="audio", attribution=True), [])

    def test_lineage_lists_the_commits_that_made_an_asset(self):
        fixtures.write(self.fixture.shop / ".harness" / "assets" / "face.md",
                       "---\nid: face\napp: game\nfile: Portraits/player.png\ncommits: \"32126ec\"\n---\n")
        registry.refresh(self.store, str(self.config))
        chain = graph.lineage(self.store, "asset:shop/face")
        self.assertEqual(chain[0]["commits"], ["commit:game/32126ec  32126ec"])
        self.assertEqual(self.ids(graph.neighbors(self.store, "app:game", "asset")), ["asset:shop/face"])

    def test_impact_and_unused_count_agent_sessions(self):
        report = graph.unused(self.store)
        self.assertEqual((report["usage_counted"], report["never_used"]), (0, []))
        self.assertIn("no usage file is configured, so agent sessions cannot be counted", registry.show_unused(report))
        report = graph.unused(self.store, True)
        self.assertIn("skill:pay", self.ids(report["never_used"]))
        self.assertIn("no agent session used:", registry.show_unused(report))
        usage = Path(self.fixture.tmp.name) / "usage.json"
        fixtures.write(usage, {"usage": [{"app": "game", "skill": "pay", "agent": "codex", "sessions": 4,
                                          "first": "2026-11-16", "last": "2026-11-19"}]})
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["usage"] = str(usage)
        fixtures.write(self.config, config)
        registry.refresh(self.store, str(self.config))
        used = graph.impact(self.store, "skill:pay")["used"]
        self.assertEqual([(row["id"], row["agent"], row["sessions"]) for row in used], [("app:game", "codex", 4)])
        report = graph.unused(self.store, True)
        self.assertNotIn("skill:pay", self.ids(report["never_used"]))
        self.assertIn("skill:flow", self.ids(report["never_used"]))
        self.assertIn("  app:game  codex  4 sessions  2026-11-16 to 2026-11-19",
                      registry.show_impact(graph.impact(self.store, "skill:pay")))

    def test_sync_counts_usage_first_and_survives_a_bad_usage_config(self):
        logs = Path(self.fixture.tmp.name) / "logs"
        fixtures.write(logs / "s1.jsonl", json.dumps({"cwd": str(self.fixture.game), "timestamp": "2026-11-19T00:00:00Z",
                                                      "message": {"content": [{"type": "tool_use", "name": "Skill",
                                                                               "input": {"skill": "pay"}}]}}) + "\n")
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config.update({"usage": str(Path(self.fixture.tmp.name) / "usage.json"), "usage_sources": {"claude": str(logs)}})
        fixtures.write(self.config, config)
        out = io.StringIO()
        with mock.patch("sys.stdout", new=mock.MagicMock(buffer=io.BytesIO())):
            self.assertEqual(registry.main(["--config", str(self.config), "--space", SPACE, "sync"]), 0)
        used = graph.impact(self.store, "skill:pay")["used"]
        self.assertEqual([(row["id"], row["sessions"], row["first"]) for row in used], [("app:game", 1, "2026-11-19")])
        config["usage_sources"] = ["/not/a/mapping"]
        fixtures.write(self.config, config)
        with redirect_stderr(out), mock.patch("sys.stdout", new=mock.MagicMock(buffer=io.BytesIO())):
            self.assertEqual(registry.main(["--config", str(self.config), "--space", SPACE, "sync"]), 0)
        self.assertIn("usage not counted", out.getvalue())
        self.assertEqual(registry.show_impact({"dependents": [], "apps": [], "records": [], "used": [
            {"id": "app:a", "agent": "claude", "sessions": 2, "first": None, "last": None}]})[-1], "  app:a  claude  2 sessions")

    def test_a_sync_cut_short_is_finished_by_the_next_one(self):
        before = graph.counts(self.store)
        record = self.fixture.shop / ".harness" / "records" / "2026-11-19-refund-rounding.md"
        rules = self.fixture.shop / "CLAUDE.md"
        kept = {path: path.read_text(encoding="utf-8") for path in (record, rules)}
        fixtures.write(record, fixtures.RECORD + "\nMore.\n")
        fixtures.write(rules, "## Commits\n\n## Keep going\n")
        real = graph.load_links
        calls = []

        def cut(store, path, entry):
            calls.append(path)
            if len(calls) > 1:
                raise graph.StoreError("deadline")
            return real(store, path, entry)

        with mock.patch.object(graph, "load_links", side_effect=cut):
            with self.assertRaises(graph.StoreError):
                registry.refresh(self.store, str(self.config))
        for path, text in kept.items():
            path.write_text(text, encoding="utf-8")
        report = registry.refresh(self.store, str(self.config))
        self.assertIn(calls[1], report["changed"])
        after = graph.counts(self.store)
        self.assertEqual(after["links"], before["links"])
        self.assertIn("rule:keep-going", [row["id"] for row in graph.neighbors(self.store, "app:shop", "rule")])

    def test_a_new_file_cut_short_and_then_deleted_leaves_nothing(self):
        before = graph.counts(self.store)
        fresh = self.fixture.shop / ".harness" / "records" / "2026-11-20-new.md"
        fixtures.write(fresh, "---\nid: 2026-11-20-new\ntitle: New\nskills: pay\n---\nText\n")
        real = graph.load_links

        def cut(store, path, entry):
            if path == str(fresh):
                store.run(f"MATCH (a:{store.node} {{id: 'record:shop/2026-11-20-new'}}) "
                          f"MATCH (b:{store.node} {{id: 'skill:pay'}}) CREATE (a)-[r:USED]->(b) SET r.src = $path", path=path)
                raise graph.StoreError("deadline")
            return real(store, path, entry)

        with mock.patch.object(graph, "load_links", side_effect=cut):
            with self.assertRaises(graph.StoreError):
                registry.refresh(self.store, str(self.config))
        fresh.unlink()
        report = registry.refresh(self.store, str(self.config))
        self.assertIn(str(fresh), report["removed"])
        self.assertEqual(graph.counts(self.store), before)

    def test_a_scan_missing_many_files_cannot_empty_the_graph(self):
        before = graph.counts(self.store)
        scanned = registry_scan.scan(json.loads(self.config.read_text(encoding="utf-8")))
        kept = dict(list(scanned["files"].items())[:2])
        changed = {path: dict(entry, hash="other", nodes=entry["nodes"][:0]) for path, entry in kept.items()}
        report = graph.sync(self.store, {"files": changed})
        self.assertEqual((report["removed"], report["changed"]), ([], []))
        self.assertGreater(len(report["held"]), 0)
        self.assertEqual(graph.counts(self.store), before)
        report = graph.sync(self.store, {"files": kept}, rebuild=True)
        self.assertEqual(graph.counts(self.store)["files"], 2)

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
