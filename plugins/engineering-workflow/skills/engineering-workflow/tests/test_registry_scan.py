import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/registry_scan.py"
SPEC = importlib.util.spec_from_file_location("registry_scan", SCRIPT)
registry_scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registry_scan)

SKILL = """---
name: store-release
description: >
  Use when preparing a store release:
  build numbers and review notes.
metadata:
  requires: "mcp:app-store, skill:engineering-workflow"
  supersedes: "ios-release"
  model: "sonnet"
  effort: "medium"
  fallback: "opus"
  author: someone
  keywords: "스토어 심사, 출시"
---

# Store release
"""
RECORD = """---
id: 2026-11-19-refund-rounding
title: Round refunds per line item
task: T2
skills: "store-release, engineering-workflow"
model: "sonnet"
commits: "a1b2c3d, e4f5a6b"
review: "codex: no findings"
concerns: "skill:payments, mcp:app-store"
decisions: "Ship behind a flag"
---

Refund totals were off by one unit.
"""
ASSET = """---
id: hero-v3
file: "Assets/Art/hero.png"
version_of: hero-v2
source: "Generated in house"
license: "own work"
made_by: "image-model"
approved_by: "2026-11-17 portrait review"
---
"""


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.shop, self.game, self.user, self.plugin = base / "shop", base / "game", base / "user", base / "plugin"
        write(self.shop / ".harness" / "board.json", {"tasks": [
            {"id": "T1", "title": "Reproduce", "status": "done"},
            {"id": "T2", "title": "Fix rounding", "status": "doing", "after": ["T1"]}],
            "decisions": [{"ask": "Flag or everyone?", "default": "flag"}]})
        write(self.shop / ".harness" / "records" / "2026-11-19-refund-rounding.md", RECORD)
        write(self.shop / ".harness" / "assets" / "hero-v3.md", ASSET)
        write(self.shop / "CLAUDE.md", "# Shop\n\n## Keep going (user, 2026-11-18)\n\ntext\n\n```\n## not a rule\n```\n\n## Commits\n")
        write(self.shop / ".claude" / "settings.json", {"enabledPlugins": {"flow@market": True, "old@market": False}})
        write(self.shop / ".claude" / "skills" / "store-release" / "SKILL.md", SKILL)
        write(self.game / "AGENTS.md", "## Commits\n")
        write(self.user / "CLAUDE.md", "## Keep going\n")
        write(self.user / "settings.json", {"enabledPlugins": {"flow@market": True}})
        write(self.user / "plugins" / "installed_plugins.json", {"plugins": {"flow@market": [
            {"version": "2.0.0", "scope": "user"},
            {"version": "1.0.0", "scope": "project", "projectPath": str(self.game)},
            {"version": "0.9.0", "scope": "project", "projectPath": str(base / "trees" / "game-wt")}]}})
        write(self.plugin / ".claude-plugin" / "plugin.json", {"name": "flow", "version": "2.0.0", "description": "Flow"})
        write(self.plugin / "hooks" / "hooks.json", {"hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "sh \"${ROOT}/scripts/hooks/auto_commit.sh\""}]}],
            "SessionStart": [{"hooks": [{"type": "command", "command": "python3 \"${ROOT}/scripts/board.py\" hook"}]}]}})
        write(self.plugin / "skills" / "flow" / "SKILL.md", "---\nname: flow\ndescription: \"Plan: and verify\"\n---\n")
        self.glossary = base / "glossary.txt"
        write(self.glossary, "레그 = RAG\n눈밥 = app:shop\n# note = skipped\nbroken line\n")
        self.config = {"cache": str(base / "cache"), "apps": [{"name": "shop", "path": str(self.shop)}, {"name": "game", "path": str(self.game)}],
                       "user": str(self.user), "plugins": [str(self.plugin)], "glossary": str(self.glossary)}

    def facts(self):
        files = registry_scan.scan(self.config)["files"]
        nodes = {item["id"]: item for entry in files.values() for item in entry["nodes"]}
        links = {(item["from"], item["type"], item["to"]): item for entry in files.values() for item in entry["links"]}
        return files, nodes, links

    def test_skill_frontmatter_becomes_links(self):
        _, nodes, links = self.facts()
        skill = nodes["skill:store-release"]
        self.assertEqual(skill["text"], "Use when preparing a store release: build numbers and review notes.")
        self.assertEqual(skill["model"], "sonnet")
        self.assertEqual(skill["keywords"], "스토어 심사, 출시")
        self.assertTrue(skill["path"].endswith("SKILL.md"))
        for key in (("app:shop", "HAS", "skill:store-release"), ("skill:store-release", "REQUIRES", "tool:mcp:app-store"),
                    ("skill:store-release", "REQUIRES", "skill:engineering-workflow"),
                    ("skill:store-release", "SUPERSEDES", "skill:ios-release"),
                    ("plugin:flow", "PROVIDES", "skill:flow")):
            self.assertIn(key, links)
        self.assertEqual(links[("skill:store-release", "PREFERS", "model:sonnet")]["effort"], "medium")
        self.assertEqual(links[("skill:store-release", "PREFERS", "model:opus")]["order"], 1)
        self.assertEqual(nodes["skill:flow"]["text"], "Plan: and verify")

    def test_plugins_settings_and_installs(self):
        _, nodes, links = self.facts()
        self.assertEqual(nodes["plugin:flow"]["version"], "2.0.0")
        self.assertEqual(links[("plugin:flow", "PROVIDES", "tool:hook:auto_commit")]["events"], ["Stop"])
        self.assertIn(("plugin:flow", "PROVIDES", "tool:hook:board"), links)
        self.assertEqual(nodes["tool:hook:board"]["text"], "hook board on SessionStart")
        self.assertEqual(links[("app:shop", "USES", "plugin:flow")]["scope"], "user")
        self.assertIn(("app:shop", "DISABLES", "plugin:old"), links)
        self.assertEqual(links[("app:game", "INSTALLED", "plugin:flow")]["version"], "1.0.0")
        self.assertEqual(links[("checkout:trees/game-wt", "INSTALLED", "plugin:flow")]["version"], "0.9.0")
        self.assertIn(("app:shop", "INSTALLED", "plugin:flow"), links)

    def test_board_record_and_asset(self):
        _, nodes, links = self.facts()
        self.assertEqual(nodes["task:shop/T2"]["status"], "doing")
        self.assertEqual(nodes["decision:shop/flag-or-everyone"]["state"], "open")
        self.assertEqual(nodes["record:shop/2026-11-19-refund-rounding"]["date"], "2026-11-19")
        self.assertIn("off by one", nodes["record:shop/2026-11-19-refund-rounding"]["text"])
        record = "record:shop/2026-11-19-refund-rounding"
        for key in (("task:shop/T2", "AFTER", "task:shop/T1"), (record, "FOR", "task:shop/T2"), (record, "IN", "app:shop"),
                    (record, "USED", "skill:store-release"), (record, "RAN_ON", "model:sonnet"),
                    (record, "PRODUCED", "commit:shop/e4f5a6b"), (record, "CONCERNS", "skill:payments"),
                    (record, "CONCERNS", "tool:mcp:app-store"),
                    ("decision:shop/ship-behind-a-flag", "AFFECTS", "task:shop/T2"),
                    ("asset:shop/hero-v3", "VERSION_OF", "asset:shop/hero-v2"),
                    ("asset:shop/hero-v3", "FROM", "source:generated-in-house"),
                    ("asset:shop/hero-v3", "MADE_BY", "model:image-model"),
                    ("decision:shop/2026-11-17-portrait-review", "APPROVED", "asset:shop/hero-v3")):
            self.assertIn(key, links)
        self.assertEqual(links[("commit:shop/a1b2c3d", "REVIEWED_BY", "model:codex")]["result"], "no findings")
        self.assertEqual(nodes["source:generated-in-house"]["license"], "own work")

    def test_rules_are_shared_across_files_and_skip_fenced_headings(self):
        _, nodes, links = self.facts()
        self.assertEqual(nodes["rule:keep-going"]["name"], "Keep going")
        self.assertNotIn("rule:not-a-rule", nodes)
        self.assertEqual(sorted(key for key in nodes if key.startswith("rule:")), ["rule:commits", "rule:keep-going"])
        self.assertEqual(links[("rule:keep-going", "APPLIES_TO", "app:game")]["scope"], "user")
        self.assertIn(("rule:commits", "APPLIES_TO", "app:shop"), links)
        self.assertIn(("rule:commits", "APPLIES_TO", "app:game"), links)

    def test_glossary(self):
        _, nodes, links = self.facts()
        self.assertEqual(nodes["term:레그"]["means"], "RAG")
        self.assertIn(("term:눈밥", "ALIAS_OF", "app:shop"), links)
        self.assertNotIn("term:# note", nodes)

    def test_working_file_gives_sessions_machines_and_lane_work(self):
        write(self.game / "WORKING.md", "# Who\n\n## Sessions\n\n- build: the build pane, session_id=1234abcd-0000\n"
              "- planner: the planner pane\n- Since Monday both run in one workspace: planner left,\n  build right.\n"
              "\n```\n~~~~\n## Lane 9: fenced\n- build: nothing\n```\n\n   ~~~\n## Lane 8: indented fence\n- build: nothing\n   ~~~\n\n"
              "## Lane 1: build (one holder)\n\n- build (pane 2), session_id=1234abcd-0000: the bridge repair\n"
              "- stranger: not listed\n\n## Lane 2: produce\n\n- planner: ground research, `docs/ground/`\n"
              "\n# Archive\n\n- build: old work\n")
        write(self.game / ".harness" / "board.json", {"tasks": [{"id": "~lane1-x", "title": "forged"},
                                                               {"id": "T9", "title": "kept"}]})
        self.config["machine"] = "laptop"
        _, nodes, links = self.facts()
        self.assertEqual(sorted(key for key in nodes if key.startswith("session:")),
                         ["session:game/build", "session:game/planner"])
        self.assertEqual(nodes["session:game/build"]["session_id"], "1234abcd-0000")
        self.assertIn("build right.", nodes["session:game/build"]["text"])
        self.assertNotIn("Since", nodes["session:game/planner"]["name"])
        self.assertIn("task:game/T9", nodes)
        self.assertNotIn("task:game/~lane1-x", nodes)
        self.assertIn(("session:game/planner", "ON", "machine:laptop"), links)
        held = {(key[0], nodes[key[2]]["name"], value["lane"]) for key, value in links.items() if key[1] == "HOLDS"}
        self.assertEqual(held, {("session:game/build", "the bridge repair", "Lane 1: build"),
                                ("session:game/planner", "ground research, `docs/ground/`", "Lane 2: produce")})

    def test_capitalised_session_names_and_lines_that_share_a_start(self):
        same = "x" * 70
        write(self.game / "WORKING.md", f"## Sessions\n\n- Build: compile\n\n## Lane 1\n\n- Build: {same}a\n- Build: {same}b\n")
        _, nodes, links = self.facts()
        held = sorted(nodes[key[2]]["name"] for key in links if key[1] == "HOLDS")
        self.assertEqual(held, [same + "a", same + "b"])

    def credits(self):
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        sounds = self.game / "Assets" / "Audio"
        write(sounds / "CREDITS.md", "# Sound credits\n\nAll recordings are CC0 from https://example.org.\n\n"
              "| Files | Pack | Author | Licence | Source |\n| --- | --- | --- | --- | --- |\n"
              "| `step_*`, `jump_*` | Steps | Ann | CC0 | https://sounds.example.com/steps |\n"
              "| `roar_*` | Roars | Bo | CC BY 4.0 | https://beasts.example.net/roar |\n\n"
              "```\n| File | Licence |\n| --- | --- |\n| `fenced_*` | MIT |\n- `fenced.png`: inside\n```\n")
        write(self.game / "Assets" / "Icons" / "CREDITS.md", "# Icons\n\nIcons from https://icons.example.com, "
              "licence CC BY 3.0.\n\n| File | Icon | Author |\n| --- | --- | --- |\n| `axe.png` | axe | Cy |\n")
        write(self.game / "Assets" / "Art" / "CREDITS.md", "# Art\n\nMade for this project.\n\n"
              "- `hero.png`: drawn by hand\n")
        write(self.game / ".copy" / "Audio" / "CREDITS.md", "| File | Licence |\n| --- | --- |\n| `dup` | CC0 |\n")
        write(self.game / "Old" / "CREDITS.md", "| File | Licence |\n| --- | --- |\n| `old` | CC0 |\n")
        write(self.game / "Loose" / "CREDITS.md", "| File | Licence |\n| --- | --- |\n| `loose` | CC0 |\n")
        subprocess.run(["git", "init", "-q", str(self.game)], check=True)
        subprocess.run(["git", "-C", str(self.game), "add", "Assets", ".copy", "Old", "AGENTS.md"], check=True)
        self.config["apps"][1]["ignore"] = ["Old/*"]
        return self.facts()

    def test_credit_tables_prose_and_bullets_become_assets_with_licenses(self):
        files, nodes, links = self.credits()
        assets = {(item["group"], item["name"]): key for key, item in nodes.items() if key.startswith("asset:game/")}
        self.assertEqual(sorted(assets), [("art", "hero.png"), ("audio", "jump_*"), ("audio", "roar_*"),
                                          ("audio", "step_*"), ("icons", "axe.png")])
        step, roar, axe, hero = (assets[key] for key in (("audio", "step_*"), ("audio", "roar_*"), ("icons", "axe.png"),
                                                         ("art", "hero.png")))
        self.assertEqual(nodes[step]["file"], "Assets/Audio/step_*")
        self.assertIn((step, "UNDER", "license:cc0"), links)
        self.assertIn((roar, "UNDER", "license:cc-by-4-0"), links)
        self.assertEqual(nodes["license:cc-by-4-0"]["attribution"], "credit")
        self.assertEqual(nodes["license:cc0"]["attribution"], "no")
        self.assertEqual(links[(roar, "FROM", "source:beasts.example.net")]["license"], "CC BY 4.0")
        self.assertIn((axe, "UNDER", "license:cc-by-3-0"), links)
        self.assertIn((axe, "FROM", "source:icons.example.com"), links)
        self.assertFalse([key for key in links if key[0] == hero and key[1] in ("UNDER", "FROM")])
        self.assertNotIn(str(self.game / ".copy" / "Audio" / "CREDITS.md"), files)
        self.assertNotIn(str(self.game / "Old" / "CREDITS.md"), files)
        self.assertNotIn(str(self.game / "Loose" / "CREDITS.md"), files)

    def one_credit_file(self, text, folder="Kit"):
        path = self.game / folder / "CREDITS.md"
        write(path, text)
        nodes, links = registry_scan.credits_facts(text, {"app": "app:game", "folder": folder})
        assets = {item["name"]: item["id"] for item in nodes if item["type"] == "asset"}
        return assets, {(item["from"], item["type"], item["to"]) for item in links}

    def test_same_file_name_in_two_credit_folders_stays_two_assets(self):
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        write(self.game / "one" / "Art" / "CREDITS.md", "| File | Licence |\n| --- | --- |\n| `a.png` | CC0 |\n| `a-png` | MIT |\n")
        write(self.game / "two" / "Art" / "CREDITS.md", "| File | Licence |\n| --- | --- |\n| `a.png` | CC BY 4.0 |\n")
        write(self.game / "Art" / "OLD_CREDITS.md", "| File | Licence |\n| --- | --- |\n| `old.png` | CC0 |\n")
        subprocess.run(["git", "init", "-q", str(self.game)], check=True)
        subprocess.run(["git", "-C", str(self.game), "add", "one", "two", "Art"], check=True)
        _, nodes, links = self.facts()
        assets = sorted(key for key in nodes if key.startswith("asset:game/"))
        self.assertEqual(len(assets), 3)
        under = {key[0]: key[2] for key in links if key[1] == "UNDER"}
        self.assertEqual(sorted(under.values()), ["license:cc-by-4-0", "license:cc0", "license:mit"])
        self.assertFalse([key for key in nodes if nodes[key].get("name") == "old.png"])

    def test_credit_rows_in_other_markdown_shapes(self):
        assets, links = self.one_credit_file(
            "Made here, MIT.\n\n- `a.png`, `b.png`: drawn here\n\nFiles | License\n--- | ---\n`axe.png` | CC0\n\n"
            "| File | Title | License |\n| --- | --- | --- |\n| `c.png` | A \\| B | CC BY 4.0 |\n")
        self.assertEqual(sorted(assets), ["a.png", "axe.png", "b.png", "c.png"])
        self.assertIn((assets["axe.png"], "UNDER", "license:cc0"), links)
        self.assertIn((assets["c.png"], "UNDER", "license:cc-by-4-0"), links)
        self.assertIn((assets["a.png"], "UNDER", "license:mit"), links)

    def test_fenced_text_is_not_the_first_paragraph_and_hosts_drop_queries(self):
        assets, links = self.one_credit_file(
            "```\nCC0 https://wrong.example\n```\n\nPictures under MIT.\n\n"
            "| File | Source |\n| --- | --- |\n| `a.png` | https://example.org?download=1 |\n"
            "| `b.png` | https://example.org#license |\n")
        self.assertIn((assets["a.png"], "UNDER", "license:mit"), links)
        self.assertEqual({key[2] for key in links if key[1] == "FROM"}, {"source:example.org"})

    def test_credit_files_need_git_and_never_fail_the_scan(self):
        files, _, _ = self.facts()
        self.assertFalse([path for path in files if path.endswith("CREDITS.md")])
        self.assertEqual(registry_scan.credit_files(self.game / "missing", []), [])

    def repo(self):
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        run = lambda *args, **env: subprocess.run(["git", "-C", str(self.game), *args], check=True, capture_output=True,
                                                  env={**os.environ, "GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@a",
                                                       "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@a", **env})
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.game)], check=True)
        run("add", "AGENTS.md")
        run("commit", "-q", "-m", "First step\n\nWhy it was done.\n\nCo-Authored-By: x <x@x>",
            GIT_AUTHOR_DATE="2026-10-05T10:00:00", GIT_COMMITTER_DATE="2026-10-05T10:00:00")
        run("checkout", "-q", "-b", "side")
        write(self.game / "side.txt", "x")
        run("add", "side.txt")
        run("commit", "-q", "-m", "Side cleanup", GIT_AUTHOR_DATE="2026-11-02T10:00:00",
            GIT_COMMITTER_DATE="2026-11-02T10:00:00")
        run("checkout", "-q", "main")
        return run

    def commits(self):
        files, nodes, _ = self.facts()
        return files, {item["name"]: item for key, item in nodes.items() if key.startswith("commit:game/")}

    def test_git_history_gives_commits_with_branch_and_month_buckets(self):
        self.repo()
        files, commits = self.commits()
        self.assertEqual(sorted(commits), ["First step", "Side cleanup"])
        self.assertEqual(commits["First step"]["text"], "Why it was done.")
        self.assertEqual((commits["First step"]["merged"], commits["First step"].get("branch")), (True, None))
        self.assertEqual((commits["Side cleanup"]["merged"], commits["Side cleanup"]["branch"]), (False, "side"))
        self.assertEqual(sorted(path for path in files if path.startswith("git:game/")), ["git:game/2026-10", "git:game/2026-11"])
        self.assertEqual(len(commits["First step"]["id"]), len("commit:game/") + 7)

    def test_a_new_commit_changes_only_its_month_and_merging_marks_it(self):
        run = self.repo()
        before, _ = self.commits()
        write(self.game / "more.txt", "x")
        run("add", "more.txt")
        run("commit", "-q", "-m", "Later", GIT_AUTHOR_DATE="2026-10-20T10:00:00", GIT_COMMITTER_DATE="2026-10-20T10:00:00")
        after, _ = self.commits()
        self.assertEqual([path for path in after if path.startswith("git:") and after[path]["hash"] != before.get(path, {}).get("hash")],
                         ["git:game/2026-10"])
        run("merge", "-q", "--no-edit", "side")
        _, commits = self.commits()
        self.assertTrue(commits["Side cleanup"]["merged"])

    def test_history_can_be_limited_or_off_and_bad_settings_fall_back(self):
        self.repo()
        self.config["apps"][1]["history"] = {"max": 1}
        self.assertEqual(sorted(self.commits()[1]), ["Side cleanup"])
        self.config["apps"][1]["history"] = {"max": [1], "since": ["x"]}
        self.assertEqual(sorted(self.commits()[1]), ["First step", "Side cleanup"])
        self.config["apps"][1]["history"] = {"max": 2147483648, "since": "nonsense"}
        files, commits = self.commits()
        self.assertEqual(sorted(commits), ["First step", "Side cleanup"])
        self.assertNotIn("git:game", files)
        self.config["apps"][1]["history"] = {"since": "2026-11-01"}
        self.assertEqual(sorted(self.commits()[1]), ["Side cleanup"])
        self.config["apps"][1]["history"] = False
        self.assertEqual(self.commits()[1], {})

    def test_a_failed_read_gives_the_last_good_history(self):
        self.repo()
        good, commits = self.commits()
        self.assertEqual(len(commits), 2)
        failures = (subprocess.TimeoutExpired("git", 5), subprocess.CalledProcessError(128, "git", b"", b"fatal: bad object"))
        for failure in failures:
            with mock.patch.object(registry_scan.subprocess, "run", side_effect=failure):
                files, commits = self.commits()
            self.assertEqual(sorted(commits), ["First step", "Side cleanup"])
            self.assertEqual({path: entry["hash"] for path, entry in files.items() if path.startswith("git:game/")},
                             {path: entry["hash"] for path, entry in good.items() if path.startswith("git:game/")})
            self.assertIn("error", files["git:game"])
        self.config["cache"] = str(Path(self.tmp.name) / "empty-cache")
        with mock.patch.object(registry_scan.subprocess, "run", side_effect=failures[0]):
            files, commits = self.commits()
        self.assertEqual(commits, {})
        self.assertIn("error", files["git:game"])

    def test_history_shares_one_time_budget(self):
        self.repo()
        with mock.patch.object(registry_scan, "GIT_BUDGET", 0):
            files, commits = self.commits()
        self.assertEqual(commits, {})
        self.assertIn("TimeoutExpired", files["git:game"]["error"])

    def test_a_broken_origin_head_uses_the_last_good_read(self):
        self.repo()
        good, _ = self.commits()
        real = subprocess.run

        def broken(command, *args, **kwargs):
            if "symbolic-ref" in command:
                raise subprocess.CalledProcessError(128, command, b"", b"fatal: bad ref")
            return real(command, *args, **kwargs)

        with mock.patch.object(registry_scan.subprocess, "run", side_effect=broken):
            files, commits = self.commits()
        self.assertIn("error", files["git:game"])
        self.assertEqual(len(commits), 2)

    def test_history_is_read_as_utf8_whatever_the_repository_says(self):
        run = self.repo()
        run("config", "i18n.logOutputEncoding", "UTF-16")
        _, commits = self.commits()
        self.assertEqual(sorted(commits), ["First step", "Side cleanup"])

    def test_credit_files_and_history_share_one_budget(self):
        self.repo()
        calls = []
        real = subprocess.run

        def slow(command, *args, **kwargs):
            calls.append(kwargs.get("timeout"))
            return real(command, *args, **kwargs)

        with mock.patch.object(registry_scan.subprocess, "run", side_effect=slow), \
                mock.patch.object(registry_scan.time, "monotonic", side_effect=[0.0] + [1.5] * 3 + [2.5] * 20):
            files, _ = self.commits()
        self.assertTrue(calls and all(timeout <= 2.0 for timeout in calls))
        self.assertIn("TimeoutExpired", files["git:game"]["error"])

    def test_a_commit_body_with_control_characters_is_kept(self):
        run = self.repo()
        write(self.game / "odd.txt", "x")
        run("add", "odd.txt")
        run("commit", "-q", "-m", "Odd body\n\nA\x1fB\x1eC")
        _, commits = self.commits()
        self.assertEqual(commits["Odd body"]["text"], "A\x1fB\x1eC")

    def test_records_name_commits_by_the_same_short_id(self):
        write(self.shop / ".harness" / "records" / "2026-11-19-long.md",
              "---\nid: 2026-11-19-long\ntitle: Long ids\ncommits: \"68d54612, abc1234\"\n---\nText\n")
        _, nodes, links = self.facts()
        self.assertIn(("record:shop/2026-11-19-long", "PRODUCED", "commit:shop/68d5461"), links)
        self.assertIn("commit:shop/abc1234", nodes)

    def test_records_and_assets_can_be_about_another_listed_app(self):
        write(self.shop / ".harness" / "records" / "2026-11-20-borders.md",
              "---\nid: 2026-11-20-borders\ntitle: Borders off\napp: game\ntask: T4\ncommits: \"8f153f9e, 594e3d0, 8f153f9\"\n"
              "decisions: \"No borders on the HUD, No borders on the HUD\"\n---\nWhy.\n")
        write(self.shop / ".harness" / "assets" / "face.md",
              "---\nid: face\napp: game\nfile: Portraits/player.png\nversion_of: face-old\ncommits: \"32126EC9, 32126ec\"\n"
              "approved_by: \"Portrait A\"\n---\n")
        write(self.shop / ".harness" / "records" / "2026-11-20-stray.md",
              "---\nid: 2026-11-20-stray\ntitle: Stray\napp: nowhere\n---\nText\n")
        write(self.shop / ".harness" / "assets" / "stray.md", "---\nid: stray\napp: nowhere\n---\n")
        write(self.shop / ".harness" / "records" / "2026-11-20-blank.md",
              "---\nid: 2026-11-20-blank\ntitle: Blank\napp:\n---\nText\n")
        files, nodes, links = self.facts()
        record = "record:shop/2026-11-20-borders"
        self.assertIn((record, "IN", "app:game"), links)
        self.assertIn((record, "FOR", "task:game/T4"), links)
        self.assertIn((record, "PRODUCED", "commit:game/8f153f9"), links)
        self.assertIn(("decision:game/no-borders-on-the-hud", "AFFECTS", "commit:game/594e3d0"), links)
        self.assertIn(("decision:game/no-borders-on-the-hud", "AFFECTS", "task:game/T4"), links)
        self.assertIn(("asset:shop/face", "IN", "app:game"), links)
        self.assertIn(("asset:shop/face", "VERSION_OF", "asset:shop/face-old"), links)
        self.assertIn(("commit:game/32126ec", "PRODUCED", "asset:shop/face"), links)
        self.assertIn(("decision:game/portrait-a", "APPROVED", "asset:shop/face"), links)
        self.assertIn("error", files[str(self.shop / ".harness" / "records" / "2026-11-20-stray.md")])
        self.assertIn("error", files[str(self.shop / ".harness" / "assets" / "stray.md")])
        self.assertIn(("record:shop/2026-11-20-blank", "IN", "app:shop"), links)
        raw = files[str(self.shop / ".harness" / "records" / "2026-11-20-borders.md")]["links"]
        self.assertEqual(sum(1 for item in raw if item["type"] == "AFFECTS" and item["to"].startswith("commit:")), 2)
        raw = files[str(self.shop / ".harness" / "assets" / "face.md")]["links"]
        self.assertEqual(sum(1 for item in raw if item["type"] == "PRODUCED"), 1)
        self.assertIn(("commit:game/32126ec", "PRODUCED", "asset:shop/face"), links)
        self.assertNotIn(("commit:game/32126EC", "PRODUCED", "asset:shop/face"), links)
        self.assertIn(("record:shop/2026-11-19-refund-rounding", "IN", "app:shop"), links)

    def test_usage_file_gives_invoked_links_for_listed_apps_only(self):
        usage = Path(self.tmp.name) / "usage.json"
        write(usage, {"usage": [{"app": "game", "skill": "flow", "agent": "codex", "sessions": 3, "first": "2026-11-01",
                                 "last": "2026-11-02"},
                                {"app": "gone", "skill": "flow", "agent": "codex", "sessions": 1},
                                {"app": "game", "skill": ["bad"]}, "junk"]})
        self.config["usage"] = str(usage)
        files, _, links = self.facts()
        self.assertEqual(links[("app:game", "INVOKED", "skill:flow")]["sessions"], 3)
        self.assertEqual([key for key in links if key[1] == "INVOKED"], [("app:game", "INVOKED", "skill:flow")])
        write(self.shop / ".claude" / "skills" / "gd" / "SKILL.md", "---\nname: game-dev\ndescription: x\n---\n")
        write(usage, {"usage": [{"app": "game", "skill": "gd", "agent": "codex", "sessions": 2}]})
        files, _, links = self.facts()
        self.assertIn(("app:game", "INVOKED", "skill:game-dev"), links)
        self.assertNotIn(("app:game", "INVOKED", "skill:gd"), links)
        write(usage, "{")
        files, _, _ = self.facts()
        self.assertIn("error", files[str(usage)])

    def test_working_file_without_sessions_states_nothing(self):
        write(self.game / "WORKING.md", "free text\n\n## Lane 1\n\n- build: work\n")
        files, nodes, _ = self.facts()
        self.assertFalse(any(key.startswith(("session:", "machine:")) for key in nodes))
        self.assertNotIn("error", files[str(self.game / "WORKING.md")])

    def test_editing_one_file_changes_one_hash(self):
        before, _, _ = self.facts()
        write(self.shop / ".harness" / "records" / "2026-11-19-refund-rounding.md", RECORD + "\nMore.\n")
        after, _, _ = self.facts()
        self.assertEqual(set(before), set(after))
        changed = [path for path in before if before[path]["hash"] != after[path]["hash"]]
        self.assertEqual(changed, [str(self.shop / ".harness" / "records" / "2026-11-19-refund-rounding.md")])

    def test_adding_an_app_changes_the_files_that_cover_every_app(self):
        before, _, _ = self.facts()
        self.config["apps"].append({"name": "third", "path": str(self.game.parent / "third")})
        after, _, _ = self.facts()
        changed = {path for path in before if before[path]["hash"] != after[path]["hash"]}
        self.assertEqual(changed, {"config:apps", str(self.user / "CLAUDE.md"), str(self.user / "settings.json"),
                                   str(self.user / "plugins" / "installed_plugins.json"),
                                   str(self.shop / ".harness" / "records" / "2026-11-19-refund-rounding.md"),
                                   str(self.shop / ".harness" / "assets" / "hero-v3.md")})

    def test_a_broken_file_is_reported_and_the_rest_is_read(self):
        write(self.shop / ".harness" / "board.json", "{")
        write(self.shop / ".claude" / "skills" / "nameless" / "SKILL.md", "---\ndescription: x\n---\n")
        files, nodes, _ = self.facts()
        self.assertIn("error", files[str(self.shop / ".harness" / "board.json")])
        self.assertIn("error", files[str(self.shop / ".claude" / "skills" / "nameless" / "SKILL.md")])
        self.assertIn("skill:store-release", nodes)

    def test_frontmatter_handles_ordinary_yaml(self):
        fields, body = registry_scan.frontmatter(
            "---\n\"name\": ski # the name\ntitle: \"a: b # kept\"\ndescription: |\n  first line\n\n  second line\n"
            "metadata:\n  routing:\n    tag: lost\n    model: wrong\n  model: sol # pick\n  requires: 'mcp:x, skill:y'\n"
            "license: MIT\n---\nbody text\n")
        self.assertEqual(fields["name"], "ski")
        self.assertEqual(fields["title"], "a: b # kept")
        self.assertEqual(fields["description"], "first line\n\nsecond line")
        self.assertEqual(fields["metadata"], {"model": "sol", "requires": "mcp:x, skill:y"})
        self.assertEqual(fields["license"], "MIT")
        self.assertEqual(body, "body text")

    def test_a_broken_plugin_manifest_is_reported_and_its_skills_are_still_read(self):
        for content in ("{", json.dumps({"name": [[["deep"]]]}), "[" * 100000):
            write(self.plugin / ".claude-plugin" / "plugin.json", content)
            files, nodes, links = self.facts()
            self.assertIn("error", files[str(self.plugin / ".claude-plugin" / "plugin.json")])
            self.assertIn("skill:flow", nodes)
            self.assertNotIn(("plugin:flow", "PROVIDES", "skill:flow"), links)

    def test_a_new_scanner_changes_every_hash(self):
        before, _, _ = self.facts()
        with mock.patch.object(registry_scan, "SCANNER", "another version"):
            after, _, _ = self.facts()
        self.assertFalse([path for path in before if path != "config:apps" and before[path]["hash"] == after[path]["hash"]])

    def test_hash_follows_the_reader_and_ignores_app_order(self):
        before, _, _ = self.facts()
        self.config["apps"].reverse()
        reordered, _, _ = self.facts()
        self.assertEqual({path: entry["hash"] for path, entry in before.items()},
                         {path: entry["hash"] for path, entry in reordered.items()})
        shared = self.user / "skills" / "note" / "SKILL.md"
        write(shared, "---\nname: note\ndescription: x\n---\n")
        as_skill = self.facts()[0][str(shared)]
        self.config["glossary"] = str(shared)
        files = self.facts()[0]
        self.assertEqual(files[str(shared)]["kind"], "glossary")
        self.assertNotEqual(files[str(shared)]["hash"], as_skill["hash"])

    def test_command_writes_json_and_rejects_a_bad_config(self):
        config = Path(self.tmp.name) / "config.json"
        write(config, self.config)
        result = subprocess.run([sys.executable, str(SCRIPT), str(config)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("config:apps", json.loads(result.stdout)["files"])
        write(config, "{")
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), str(config)], capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
