import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/app_template.py"
SPEC = importlib.util.spec_from_file_location("app_template", SCRIPT)
app_template = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app_template)

RULES = """# Project rules: {{app}}

Intro.

## Workflow

Use the skill.

## Commit and push (user, 2026-11-19)

Commit by name for {{app}}.

```
## Not a heading
```
"""


class TemplateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.template = self.root / "template"
        (self.template / ".harness" / "records").mkdir(parents=True)
        (self.template / "CLAUDE.md").write_text(RULES, encoding="utf-8")
        (self.template / ".harness" / "board.json").write_text('{"title": "{{app}}"}', encoding="utf-8")
        (self.template / ".harness" / "records" / ".gitkeep").write_text("", encoding="utf-8")
        (self.template / "logo.bin").write_bytes(b"\xff\xfe{{app}}")
        (self.template / ".DS_Store").write_bytes(b"x")
        self.addCleanup(self.tmp.cleanup)

    def run_tool(self, *args):
        out, err, raw = io.StringIO(), io.StringIO(), io.BytesIO()
        out.buffer = raw
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = app_template.main(["--template", str(self.template), *args])
        return code, raw.getvalue().decode("utf-8"), err.getvalue()

    def app(self, name, rules=None, file="CLAUDE.md"):
        folder = self.root / name
        folder.mkdir()
        if rules is not None:
            (folder / file).write_text(rules, encoding="utf-8")
        return folder

    def test_new_fills_the_name_and_keeps_existing_files(self):
        folder = self.root / "shop"
        folder.mkdir()
        (folder / "CLAUDE.md").write_text("mine\n", encoding="utf-8")
        code, out, _ = self.run_tool("new", str(folder))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["wrote .harness/board.json", "wrote .harness/records/.gitkeep",
                                            "wrote logo.bin", "kept CLAUDE.md (already there)"])
        self.assertEqual(json.loads((folder / ".harness" / "board.json").read_text(encoding="utf-8"))["title"], "shop")
        self.assertEqual((folder / "CLAUDE.md").read_text(encoding="utf-8"), "mine\n")
        self.assertEqual((folder / "logo.bin").read_bytes(), b"\xff\xfe{{app}}")
        other = self.root / "two"
        self.assertEqual(self.run_tool("new", str(other), "--name", "Cafe")[0], 0)
        self.assertIn("# Project rules: Cafe", (other / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_a_changed_rule_lists_the_apps_that_still_have_the_old_one(self):
        fresh = self.root / "fresh"
        self.run_tool("new", str(fresh))
        old = self.app("old", RULES.replace("{{app}}", "old") + "\n## Own rule\n\nOnly here.\n\n## Workflow\n\nLater copy.\n"
                       "\n# Appendix\n\nNot part of a section.\n")
        self.app("agents", RULES.replace("{{app}}", "agents").replace("(user, 2026-11-19)", ""), "AGENTS.md")
        apps = ["--app", str(fresh), "--app", str(old), "--app", str(self.root / "agents")]
        self.assertEqual(self.run_tool("drift", *apps)[:2], (0, "every app matches the template\n"))
        (self.template / "CLAUDE.md").write_text(RULES.replace("Use the skill.", "Use the skill and the board."),
                                                 encoding="utf-8")
        (fresh / "CLAUDE.md").write_text(RULES.replace("Use the skill.", "Use   the skill and\nthe board.")
                                         .replace("{{app}}", "fresh") + "\n# Appendix\n\nNot part of a section.\n",
                                         encoding="utf-8")
        code, out, _ = self.run_tool("drift", *apps)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["old: differs: Workflow  -Use the skill.",
                                            "agents: differs: Workflow  -Use the skill."])

    def test_missing_section_name_difference_and_no_rule_file(self):
        self.app("cut", "# Rules\n\n## Workflow\n\nUse the skill.\n")
        self.app("named", RULES.replace("{{app}}", "someone else"))
        self.app("empty")
        code, out, _ = self.run_tool("drift", "--json", *[f"--app={self.root / name}" for name in ("cut", "named",
                                                                                                   "empty")])
        self.assertEqual(code, 1)
        rows = [(row["app"], row["state"], row["rule"]) for row in json.loads(out)]
        self.assertEqual(rows, [("cut", "missing", "Commit and push"), ("named", "differs", "Commit and push"),
                                ("empty", "no rule file", None)])

    def test_apps_from_the_registry_config(self):
        self.app("one", RULES.replace("{{app}}", "one"))
        self.app("two", "## Workflow\n\nUse the skill.\n")
        config = self.root / "registry.json"
        config.write_text(json.dumps({"apps": [{"name": "one", "path": str(self.root / "one")},
                                               {"name": "two", "path": str(self.root / "two")}]}), encoding="utf-8")
        code, out, _ = self.run_tool("drift", "--config", str(config))
        self.assertEqual((code, out), (1, "two: missing: Commit and push\n"))

    def test_new_never_writes_through_a_link_or_over_a_file(self):
        outside = self.root / "outside"
        outside.mkdir()
        folder = self.root / "linked"
        folder.mkdir()
        try:
            (folder / ".harness").symlink_to(outside, target_is_directory=True)
            (folder / "CLAUDE.md").symlink_to(outside / "rules.md")
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are not available")
        code, out, _ = self.run_tool("new", str(folder))
        self.assertEqual(code, 0)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertIn("kept CLAUDE.md (outside the folder through a link, not written)", out)
        self.assertIn("kept .harness/board.json (outside the folder through a link, not written)", out)
        target = self.root / "race"
        target.mkdir()
        real_open = open

        def late(path, mode="r", *args, **kwargs):
            if "x" in mode and Path(path).name == "CLAUDE.md":
                Path(path).write_text("other process\n", encoding="utf-8")
            return real_open(path, mode, *args, **kwargs)

        with mock.patch("builtins.open", late):
            code, out, _ = self.run_tool("new", str(target))
        self.assertIn("kept CLAUDE.md (already there)", out)
        self.assertEqual((target / "CLAUDE.md").read_text(encoding="utf-8"), "other process\n")

    def test_new_escapes_json_and_makes_empty_folders(self):
        (self.template / "assets").mkdir()
        folder = self.root / "quoted"
        self.assertEqual(self.run_tool("new", str(folder), "--name", 'Shop "EU" \\ 1')[0], 0)
        board = json.loads((folder / ".harness" / "board.json").read_text(encoding="utf-8"))
        self.assertEqual(board["title"], 'Shop "EU" \\ 1')
        self.assertTrue((folder / "assets").is_dir())
        self.assertIn('# Project rules: Shop "EU"', (folder / "CLAUDE.md").read_text(encoding="utf-8"))
        named = self.root / "named-app"
        self.run_tool("new", str(named), "--name", "Shop")
        self.assertEqual(self.run_tool("drift", "--app", f"Shop={named}")[0], 0)
        self.assertEqual(self.run_tool("drift", "--app", str(named))[0], 1)

    def test_fences_code_and_headings_that_look_alike(self):
        rules = ("## Workflow\n\n~~~markdown\n```\n~~~\n\nRun tests.\n\n  ```\n  ## inside\n  ```\n\n"
                 "```sh\npytest\ngit push\n```\n\n## C++\n\nUse safe APIs.\n\n## C#\n\nEnable analyzers.\n")
        (self.template / "CLAUDE.md").write_text(rules, encoding="utf-8")
        self.app("same", rules + "\n#\tAppendix\n\nApp notes.\n")
        self.app("skip", rules.replace("Run tests.", "Skip tests."))
        self.app("joined", rules.replace("pytest\ngit push", "pytest git push"))
        self.app("cut", rules.split("## C#")[0])
        code, out, _ = self.run_tool("drift", *[f"--app={self.root / name}" for name in ("same", "skip", "joined", "cut")])
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["skip: differs: Workflow  -Skip tests.",
                                            "joined: differs: Workflow  -pytest git push",
                                            "cut: missing: C#"])

    def test_fence_rules(self):
        cases = {"## A\n\n~~~\n```\n## B\n~~~\n": ["a"], "## A\n\n````\n```\n## B\n````\n": ["a"],
                 "## A\n\n   ```\n## B\n   ```\n": ["a"], "## A\n\n    ```\n## B\n": ["a", "b"]}
        for content, keys in cases.items():
            self.assertEqual(list(app_template.sections(content)), keys, content)

    def test_registry_config_of_the_wrong_shape_exits_two(self):
        config = self.root / "registry.json"
        for value in ([], None, {"apps": {}}, {"apps": [{"name": "a"}]}, {"apps": ["a"]}):
            config.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(self.run_tool("drift", "--config", str(config))[0], 2, value)

    def test_setup_problems_exit_two(self):
        self.assertEqual(self.run_tool("drift", "--config", str(self.root / "nope.json"))[0], 2)
        (self.template / "CLAUDE.md").unlink()
        code, _, err = self.run_tool("drift", "--app", str(self.app("x", "## A\n")))
        self.assertEqual(code, 2)
        self.assertIn("TEMPLATE CHECK UNAVAILABLE", err)
        self.template = self.root / "missing"
        self.assertEqual(self.run_tool("new", str(self.root / "y"))[0], 2)

    def test_shipped_template_starts_an_app_that_matches_it(self):
        folder = self.root / "real"
        with contextlib.redirect_stdout(io.StringIO()) as out:
            out.buffer = io.BytesIO()
            self.assertEqual(app_template.main(["new", str(folder)]), 0)
        self.assertEqual(app_template.drift(app_template.DEFAULT_TEMPLATE, [{"name": "real", "path": str(folder)}]),
                         [])
        board = json.loads((folder / ".harness" / "board.json").read_text(encoding="utf-8"))
        self.assertEqual((board["title"], board["tasks"]), ("real", []))


if __name__ == "__main__":
    unittest.main()
