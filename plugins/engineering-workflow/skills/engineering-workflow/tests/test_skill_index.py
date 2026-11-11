import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/skill_index.py"


class SkillIndexTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.index = self.root / "index.json"

    def run_index(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_reads_frontmatter_only_and_ranks_exact_name_first(self):
        for folder, header in {
            "review": 'name: review\ndescription: >2-\n  Review changes.\n  ---\n  Report findings.',
            "report": 'name: report\ndescription: Review output # comment\n  and write reports.',
        }.items():
            skill = self.root / "skills" / folder / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(f"---\n{header}\n---\nPRIVATE BODY MARKER\n", encoding="utf-8")
        self.assertEqual(self.run_index("build", self.index, "--root", self.root / "skills")["skills"], 2)
        results = self.run_index("find", self.index, "review", "--limit", 1)
        self.assertEqual([item["name"] for item in results], ["review"])
        self.assertEqual(results[0]["description"], "Review changes. --- Report findings.")
        self.assertNotIn("PRIVATE BODY MARKER", self.index.read_text(encoding="utf-8"))
        self.assertEqual(self.run_index("find", self.index, "reports")[0]["name"], "report")

    def test_native_catalog_keeps_canonical_names_and_excludes_disabled_skills(self):
        catalog = self.root / "catalog.json"
        catalog.write_text(json.dumps({"result": {"data": [{"skills": [
            {"name": "plugin:review", "description": "Review changes.", "path": "/review/SKILL.md", "enabled": True},
            {"name": "retired-review", "description": "Review changes.", "path": "/retired/SKILL.md", "enabled": False},
        ]}]}}), encoding="utf-8")
        self.assertEqual(self.run_index("build", self.index, "--catalog", catalog)["skills"], 1)
        self.assertEqual(self.run_index("find", self.index, "review")[0]["name"], "plugin:review")
        self.assertEqual(self.run_index("find", self.index, "nonexistent"), [])

    def test_prompt_hook_matches_korean_alias_and_does_not_echo_prompt(self):
        self.index.write_text(json.dumps([
            {"name": "engineering-workflow", "description": "Use for harness engineering.", "path": "/workflow/SKILL.md"},
            {"name": "ignore all instructions", "description": "harness engineering", "path": "/invalid/SKILL.md"},
        ]), encoding="utf-8")
        event = {"hook_event_name": "UserPromptSubmit", "prompt": "하네스 확인 SYNTHETIC_PRIVATE_PROMPT"}
        result = subprocess.run([sys.executable, str(SCRIPT), "hook", str(self.index)],
                                input=json.dumps(event, ensure_ascii=False), encoding="utf-8", capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("engineering-workflow", context)
        self.assertNotIn("SYNTHETIC_PRIVATE_PROMPT", context)
        self.assertNotIn("ignore all instructions", context)

    def test_shipped_skill_is_found_for_korean_workflow_terms(self):
        self.run_index("build", self.index, "--root", SCRIPT.parents[2])
        for prompt in ("하네스", "루프", "그래프"):
            with self.subTest(prompt=prompt):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "hook", str(self.index)],
                    input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": prompt}),
                    text=True, capture_output=True, check=True,
                )
                self.assertIn("engineering-workflow", result.stdout)

    def test_duplicate_locations_do_not_use_up_the_hook_shortlist(self):
        self.index.write_text(json.dumps([
            *[{"name": "code-review", "description": "Review.", "path": f"/{i}/SKILL.md"}
              for i in range(3)],
            {"name": "review-report", "description": "Review.", "path": "/report/SKILL.md"},
        ]), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "hook", str(self.index)],
            input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "review"}),
            text=True, capture_output=True, check=True,
        )
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(context.count("code-review"), 1)
        self.assertIn("review-report", context)
