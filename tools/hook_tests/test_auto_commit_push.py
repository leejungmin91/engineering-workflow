"""Tests for auto_commit_push.sh. Each test creates a fresh repository with a bare
remote and runs the hook against it. Nothing outside the temp directory is touched."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins" / "engineering-workflow" / "scripts" / "hooks" / "auto_commit_push.sh"
SHELL = shutil.which("sh") or shutil.which("bash")
GIT_IDENTITY = ["-c", "user.name=hook-test", "-c", "user.email=hook-test@example.com"]


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *GIT_IDENTITY, *args], check=True,
                          capture_output=True, text=True).stdout


@unittest.skipIf(SHELL is None, "needs sh or bash on PATH")
class AutoCommitPushTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ewf-hook-"))
        self.remote = self.tmp / "remote.git"
        self.repo = self.tmp / "work"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        (self.repo / "README.md").write_text("start\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-q", "-u", "origin", "main")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_hook(self, *args, env=None):
        full_env = dict(os.environ)
        full_env["CLAUDE_PROJECT_DIR"] = str(self.repo)
        full_env["GIT_AUTHOR_NAME"] = full_env["GIT_COMMITTER_NAME"] = "hook-test"
        full_env["GIT_AUTHOR_EMAIL"] = full_env["GIT_COMMITTER_EMAIL"] = "hook-test@example.com"
        full_env.update(env or {})
        return subprocess.run([SHELL, str(SCRIPT), *args], input="{}", capture_output=True,
                              text=True, env=full_env, cwd=str(self.tmp))

    def remote_rev(self, ref):
        return subprocess.run(["git", "-C", str(self.remote), "rev-parse", ref],
                              check=True, capture_output=True, text=True).stdout.strip()

    def test_clean_tree_does_nothing(self):
        before = git(self.repo, "rev-parse", "HEAD").strip()
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), before)

    def test_commits_and_pushes_changes(self):
        (self.repo / "src").mkdir()
        (self.repo / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
        (self.repo / "README.md").write_text("changed\n", encoding="utf-8")
        result = self.run_hook(env={"AUTO_COMMIT_TRAILER": "Co-Authored-By: Test <t@example.com>"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"systemMessage"', result.stdout)
        self.assertIn("and pushed", result.stdout)
        message = git(self.repo, "log", "-1", "--format=%B")
        self.assertTrue(message.startswith("Update README.md, src\n"), message)
        self.assertIn("A\tsrc/app.py", message)
        self.assertIn("Co-Authored-By: Test <t@example.com>", message)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertEqual(self.remote_rev("main"), git(self.repo, "rev-parse", "HEAD").strip())

    def test_dotfiles_sort_last_and_subject_counts_extras(self):
        for name in (".claude", "a", "b", "c"):
            (self.repo / name).mkdir()
            (self.repo / name / "f").write_text("x\n", encoding="utf-8")
        result = self.run_hook("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Subject: Update a, b, c (+1 more)", result.stdout)
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "")

    def test_sets_upstream_when_missing(self):
        git(self.repo, "checkout", "-q", "-b", "feature")
        (self.repo / "note.txt").write_text("n\n", encoding="utf-8")
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("and pushed", result.stdout)
        self.assertEqual(self.remote_rev("feature"), git(self.repo, "rev-parse", "HEAD").strip())

    def test_dry_run_preserves_staged_content(self):
        path = self.repo / "README.md"
        path.write_text("staged\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        path.write_text("unstaged\n", encoding="utf-8")
        status = git(self.repo, "status", "--porcelain")
        result = self.run_hook("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would commit 1 file", result.stdout)
        self.assertEqual(git(self.repo, "status", "--porcelain"), status)
        self.assertEqual(git(self.repo, "show", ":README.md"), "staged\n")

    def test_pushes_existing_commit_with_clean_tree(self):
        git(self.repo, "commit", "--allow-empty", "-m", "Hand-written commit")
        head = git(self.repo, "rev-parse", "HEAD").strip()
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pushed", result.stdout)
        self.assertEqual(self.remote_rev("main"), head)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(self.run_hook().stdout, "")

    def test_pushes_existing_commit_on_branch_without_upstream(self):
        git(self.repo, "checkout", "-q", "-b", "feature")
        git(self.repo, "commit", "--allow-empty", "-m", "Hand-written commit")
        head = git(self.repo, "rev-parse", "HEAD").strip()
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pushed", result.stdout)
        self.assertEqual(self.remote_rev("feature"), head)
        self.assertEqual(git(self.repo, "rev-parse", "@{upstream}").strip(), head)

    def test_push_failure_is_reported_not_fatal(self):
        git(self.repo, "remote", "set-url", "origin", str(self.tmp / "missing.git"))
        (self.repo / "note.txt").write_text("n\n", encoding="utf-8")
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("push failed", result.stdout)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

        git(self.repo, "remote", "set-url", "origin", str(self.remote))
        head = git(self.repo, "rev-parse", "HEAD").strip()
        retry = self.run_hook()
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertIn("pushed", retry.stdout)
        self.assertEqual(self.remote_rev("main"), head)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), head)


if __name__ == "__main__":
    unittest.main()
