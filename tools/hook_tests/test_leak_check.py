import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "leak_check.py"
HOOK = ROOT / "tools" / "githooks" / "pre-commit"
SHELL = shutil.which("sh") or shutil.which("bash")
IDENTITY = ["-c", "user.name=leak-test", "-c", "user.email=leak-test@example.com"]
KEY = "sk-" + "a1B2" * 8
LONG = "q7Zx" * 10
LEAKS = [
    ("access key", "notes.md", "the key is " + KEY, KEY),
    ("access key", "pay.md", "s" + "k_live_" + "a1B2" * 6, "a1B2" * 6),
    ("access key", "maps.md", "AI" + "za" + "b3C4d" * 7, "b3C4d" * 7),
    ("access key", "call.sh", "Authorization: Bea" + "rer " + LONG, LONG),
    ("webhook address", "bot.md", "https://disc" + "ord.com/api/webhooks/123456/" + LONG, LONG),
    ("private key", "id.txt", "-----BEGIN " + "OPENSSH PRIVATE KEY-----", None),
    ("secret assigned in text", "config.json", '{"api_' + 'key": "' + "x9" * 12 + '"}', "x9" * 12),
    ("secret assigned in text", "aws.ini", "aws_sec" + "ret_access_key = " + LONG, LONG),
    ("secret assigned in text", "app.py", "SEC" + "RET_KEY = '" + "0123456789abcdef" * 2 + "'", "0123456789abcdef"),
    ("credentials in a URL", "run.sh", "bolt" + "://neo4j:" + "hunter2x" + "@localhost:7687", "hunter2x"),
    ("credentials in a URL", "pull.sh", "https" + "://" + LONG + "@github.com/a/b.git", LONG),
    ("personal home path", "doc.md", "see /Us" + "ers/alex/Documents/app/readme", None),
    ("personal home path", "doc2.md", 'root = "/Us' + 'ers/alex"', None),
    ("personal home path", "doc3.md", "C:" + "\\Us" + "ers\\alex\\app", None),
    ("file type that holds secrets or a database", "graph.sqlite", "x", None),
    ("file type that holds secrets or a database", "prod.env", "A=1", None),
    ("file type that holds secrets or a database", "id_ed25519", "x", None),
    ("file type that holds secrets or a database", ".npmrc", "x", None),
]
CLEAN = [
    "Set API_KEY in your keychain. Paths look like /Us" + "ers/you/project.",
    "token_budget = remaining_context_tokens_total",
    "https://example.com/home/products/list and /home/ubuntu/app and /Us" + "ers/Shared/x",
    "postgres://user:password@localhost/db",
    "api_key = YOUR_ANTHROPIC_API_KEY_HERE_123",
    "token: integrations/discord/state2/cache",
    "password: ${NEO4J_PASSWORD}",
]


class LeakCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        self.git("init", "-q")

    def git(self, *args, check=True):
        return subprocess.run(["git", "-C", str(self.repo), *IDENTITY, *args], check=check, capture_output=True, text=True)

    def stage(self, name, content):
        target = self.repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        self.git("add", name)

    def unstage_all(self):
        self.git("rm", "-rq", "--cached", "--ignore-unmatch", ".")

    def check(self, mode="--staged", cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), mode], cwd=cwd or self.repo, capture_output=True, text=True)

    def test_clean_text_passes(self):
        self.stage("readme.md", "\n".join(CLEAN) + "\n")
        self.stage(".env.example", "API_KEY=\n")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_each_kind_of_leak_fails_without_printing_the_value(self):
        for label, name, content, secret in LEAKS:
            with self.subTest(name):
                self.unstage_all()
                self.stage(name, content + "\n")
                result = self.check()
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(label, result.stdout)
                if secret:
                    self.assertNotIn(secret, result.stdout + result.stderr)

    def test_staged_content_is_checked_not_the_working_copy(self):
        self.stage("notes.md", "key " + KEY + "\n")
        (self.repo / "notes.md").write_text("clean\n", encoding="utf-8")
        self.assertEqual(self.check().returncode, 1)

    def test_key_in_a_large_file_a_binary_file_and_utf16_is_found(self):
        cases = {"big.log": ("line\n" * 300_000 + KEY + "\n").encode(), "blob.bin": b"\0\1\2 " + KEY.encode() + b"\n",
                 "wide.txt": ("key " + KEY).encode("utf-16")}
        for name, data in cases.items():
            with self.subTest(name):
                self.unstage_all()
                self.stage(name, data)
                self.assertEqual(self.check().returncode, 1)

    def test_file_replaced_in_place_of_a_link_is_checked(self):
        if os.name == "nt":
            self.skipTest("needs symlinks")
        (self.repo / "target.md").write_text("fine\n", encoding="utf-8")
        os.symlink("target.md", self.repo / "link.md")
        self.git("add", "target.md", "link.md")
        self.git("commit", "-qm", "base")
        (self.repo / "link.md").unlink()
        self.stage("link.md", "key " + KEY + "\n")
        self.assertEqual(self.check().returncode, 1)

    def test_odd_names_and_nested_repositories_do_not_break_the_check(self):
        if os.name != "nt":
            self.stage("2:x.md", "fine\n")
        nested = self.repo / "vendor"
        nested.mkdir()
        subprocess.run(["git", "-C", str(nested), "init", "-q"], check=True)
        (nested / "a.md").write_text("fine\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(nested), *IDENTITY, "add", "a.md"], check=True)
        subprocess.run(["git", "-C", str(nested), *IDENTITY, "commit", "-qm", "x"], check=True)
        self.git("add", "vendor", check=False)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_all_mode_checks_the_whole_repository_from_a_subfolder(self):
        self.stage("notes.md", "key " + KEY + "\n")
        self.stage("sub/ok.md", "fine\n")
        self.assertEqual(self.check("--all").returncode, 1)
        self.assertEqual(self.check("--all", cwd=self.repo / "sub").returncode, 1)

    @unittest.skipIf(SHELL is None, "needs sh or bash on PATH")
    def test_pre_commit_hook_blocks_the_commit(self):
        hooks = self.repo / "hooks"
        shutil.copytree(HOOK.parent, hooks)
        shutil.copytree(SCRIPT.parent, self.repo / "tools", ignore=shutil.ignore_patterns("hook_tests", "githooks", "__pycache__"))
        self.git("config", "core.hooksPath", "hooks")
        self.stage("notes.md", "key " + KEY + "\n")
        blocked = self.git("commit", "-qm", "leak", check=False)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("LEAK CHECK FAILED", blocked.stdout + blocked.stderr)
        self.git("rm", "-q", "--cached", "notes.md")
        self.stage("ok.md", "fine\n")
        self.git("add", "tools")
        self.assertEqual(self.git("commit", "-qm", "clean", check=False).returncode, 0)

    def test_this_repository_is_clean(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--all"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
