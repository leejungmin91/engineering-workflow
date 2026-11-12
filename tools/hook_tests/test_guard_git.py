"""Hook tests for guard_git.py. Synthetic hook input only; no Git command is executed
by the hook itself, but test repositories are created fresh for every test."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "plugins" / "engineering-workflow" / "scripts" / "hooks"
GUARD = HOOKS / "guard_git.py"
RECORD = HOOKS / "record_prompt.py"

GIT_IDENTITY = ["-c", "user.name=hook-test", "-c", "user.email=hook-test@example.com"]


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *GIT_IDENTITY, *args], check=True,
                          capture_output=True, text=True)


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ewf-hook-"))
        self.home = self.tmp / "home"
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        (self.repo / "README.md").write_text("hello\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text("ignored.env\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def transcript(self, *messages):
        path = self.tmp / "transcript.jsonl"
        lines = []
        for text in messages:
            lines.append(json.dumps({"type": "user", "message": {"role": "user", "content": text}}, ensure_ascii=False))
            lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "ok"}]}}))
        # A tool result arrives as a user entry but is not a human message.
        lines.append(json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "x", "content": "git commit done"}]}}))
        lines.append(json.dumps({"type": "user", "isMeta": True, "message": {"role": "user", "content": "push now"}}))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path)

    def run_script(self, script, event):
        # No PYTHONIOENCODING on purpose: the hooks must handle UTF-8 input on their own.
        env = {key: value for key, value in os.environ.items() if key not in ("PYTHONIOENCODING", "PYTHONUTF8")}
        env["ENGINEERING_WORKFLOW_HOME"] = str(self.home)
        return subprocess.run([sys.executable, str(script)], input=json.dumps(event, ensure_ascii=False),
                              capture_output=True, text=True, encoding="utf-8", env=env, check=False)

    def decision(self, command, message=None, tool="Bash", codex=False, turn="turn-1",
                 recorded=None, recorded_turn="turn-1", cwd=None, transcript=True):
        event = {"hook_event_name": "PreToolUse", "session_id": "session-1", "tool_name": tool,
                 "tool_input": {"command": command}, "cwd": str(cwd or self.repo)}
        if codex:
            event["turn_id"] = turn
            event["model"] = "gpt-test"
            if recorded is not None:
                result = self.run_script(RECORD, {
                    "hook_event_name": "UserPromptSubmit", "session_id": event["session_id"],
                    "turn_id": recorded_turn, "prompt": recorded,
                })
                self.assertEqual(result.returncode, 0, result.stderr)
        elif transcript:
            event["transcript_path"] = self.transcript(*(message if isinstance(message, list) else [message or "안녕"]))
        result = self.run_script(GUARD, event)
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return "allow"
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.reason = output["permissionDecisionReason"]
        return output["permissionDecision"]


class RequestPhraseTests(HookCase):
    def test_korean_requests_allow_commit(self):
        for message in ("커밋해 줘", "커밋해", "커밋 진행해 줘", "변경사항 커밋", "커밋", "커밋, 푸시 하도록 해",
                        "커밋푸시하도록", "이거 커밋하고 푸시해 줘", "올려 줘"):
            with self.subTest(message=message):
                self.assertEqual(self.decision("git commit -m 'x'", message), "allow")

    def test_korean_requests_allow_push(self):
        for message in ("푸시해", "푸시하세요", "커밋 푸시", "커밋, 푸시 하도록 해", "올려 줘", "푸시"):
            with self.subTest(message=message):
                self.assertEqual(self.decision("git push origin main", message), "allow")

    def test_english_requests_allow(self):
        for command, message in (("git commit -m x", "commit it"), ("git push", "push the changes"),
                                 ("git commit -am x", "please commit this"), ("git push", "commit and push")):
            with self.subTest(message=message):
                self.assertEqual(self.decision(command, message), "allow")

    def test_negation_and_deferral_deny(self):
        for command, message in (("git commit -m x", "커밋하지 마"), ("git push", "푸시는 아직"),
                                 ("git push", "don't push yet"), ("gh pr create --fill", "do not create a PR"),
                                 ("git push", "푸시하기 전에 검토해 줘"), ("git commit -m x", "커밋은 하지 말고 테스트만 돌려"),
                                 ("git push", "커밋하고 푸시는 아직 하지 마")):
            with self.subTest(message=message):
                self.assertEqual(self.decision(command, message), "deny")

    def test_partial_negation_keeps_other_action(self):
        self.assertEqual(self.decision("git commit -m x", "커밋하고 푸시는 아직 하지 마"), "allow")
        self.assertEqual(self.decision("git commit -m x", "commit it but don't push"), "allow")

    def test_other_action_request_does_not_transfer(self):
        self.assertEqual(self.decision("git push", "커밋해 줘"), "deny")
        self.assertEqual(self.decision("gh pr create --fill", "푸시해 줘"), "deny")
        self.assertEqual(self.decision("git commit -m x && git push", "커밋해 줘"), "deny")

    def test_unrelated_message_denies(self):
        self.assertEqual(self.decision("git commit -m x", "테스트 돌려 줘"), "deny")
        self.assertIn("does not request", self.reason)

    def test_read_only_requests_and_negations_do_not_authorize_writes(self):
        for command, message in (
            ("git commit -m x", "Show me the latest commit"),
            ("git commit -m x", "커밋 내용 확인해 줘"),
            ("gh pr create --fill", "Review the PR"),
            ("git push", "Don’t push it"),
            ("git push", "푸시 말고 테스트만 해 줘"),
            ("git push", "Don't commit and push"),
            ("git push", "Do not commit, push, or open a PR"),
            ("git commit -m x", "커밋, 푸시하지 마"),
            ("git commit -m x", "Commit it. Actually, do not commit."),
            ("git push", "Explain `git push`"),
        ):
            with self.subTest(message=message):
                self.assertEqual(self.decision(command, message), "deny")

    def test_attachment_only_user_message_clears_previous_approval(self):
        path = Path(self.transcript("push it"))
        attachment = {"type": "user", "message": {"role": "user", "content": [{"type": "image"}]}}
        with path.open("a", encoding="utf-8") as transcript:
            transcript.write(json.dumps(attachment) + "\n")
        event = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": "git push"}, "transcript_path": str(path)}
        result = self.run_script(GUARD, event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_only_latest_message_counts(self):
        self.assertEqual(self.decision("git push", ["푸시해 줘", "이제 문서만 고쳐"]), "deny")
        self.assertEqual(self.decision("git push", ["문서만 고쳐", "푸시해 줘"]), "allow")

    def test_missing_transcript_denies_with_reason(self):
        self.assertEqual(self.decision("git commit -m x", transcript=False), "deny")
        self.assertIn("could not be read", self.reason)

    def test_pr_requires_its_own_request(self):
        self.assertEqual(self.decision("gh pr create --fill", "PR 만들어 줘"), "allow")
        self.assertEqual(self.decision("gh pr create --fill", "open a pull request"), "allow")
        self.assertEqual(self.decision("gh pr create --fill", "커밋 푸시해 줘"), "deny")


class CommandShapeTests(HookCase):
    def test_command_variants_are_detected(self):
        for command in ("GIT commit -m x", "Git.exe commit -m x", '"C:\\Program Files\\Git\\bin\\git.exe" commit -m x',
                        f"git -C {self.repo} commit -m x", "    git commit -m x", "echo ok && git commit -m x",
                        "git -c core.autocrlf=false commit -m x", "git --no-pager commit -m x",
                        "FOO=1 git commit -m x", "echo a; git commit -m x", "(git commit -m x)",
                        "echo a | git commit -F -", "git commit --amend --no-edit"):
            with self.subTest(command=command):
                self.assertEqual(self.decision(command, "테스트"), "deny")

    def test_text_mentions_pass(self):
        for command in ('grep "git commit" README.md', "echo 'git push --force'", "git log --oneline",
                        "git status", "git add .", "git commit --dry-run", "git push --dry-run", "git push -n",
                        "cat notes.md # git commit later", "gh pr list", "gh pr view 3"):
            with self.subTest(command=command):
                self.assertEqual(self.decision(command, "테스트"), "allow")

    def test_commit_short_option_is_not_a_dry_run(self):
        self.assertEqual(self.decision("git commit -n -m x", "테스트"), "deny")

    def test_powershell_tool_is_checked(self):
        self.assertEqual(self.decision("git commit -m x", "테스트", tool="PowerShell"), "deny")
        self.assertEqual(self.decision("& git push", "테스트", tool="PowerShell"), "deny")

    def test_pr_creation_paths(self):
        for command in ("gh pr create --fill", "glab mr create", "hub pull-request -m x",
                        "git push -o merge_request.create origin HEAD",
                        "curl -X POST https://api.github.com/repos/a/b/pulls -d '{}'",
                        "curl https://api.github.com/repos/a/b/pulls --json '{}'",
                        "Invoke-RestMethod -Method Post -Uri https://api.github.com/repos/a/b/pulls -Body $b"):
            with self.subTest(command=command):
                self.assertEqual(self.decision(command, "테스트"), "deny")
                self.assertIn("PR/MR creation", self.reason)

    def test_pr_reads_pass(self):
        for command in ("curl https://api.github.com/repos/a/b/pulls", "curl -X GET https://api.github.com/repos/a/b/pulls",
                        "curl -G -d state=open https://api.github.com/repos/a/b/pulls",
                        "Invoke-RestMethod -Uri https://api.github.com/repos/a/b/pulls"):
            with self.subTest(command=command):
                self.assertEqual(self.decision(command, "테스트"), "allow")

    def test_non_shell_tools_and_bad_input_pass(self):
        self.assertEqual(self.decision("git commit -m x", "테스트", tool="Read"), "allow")
        result = subprocess.run([sys.executable, str(GUARD)], input="{", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")


class SecretTests(HookCase):
    def write(self, name, text):
        (self.repo / name).write_text(text, encoding="utf-8")

    def test_staged_secret_denies_even_when_requested(self):
        self.write("config.py", 'TOKEN = "ghp_' + "a" * 36 + '"\n')
        git(self.repo, "add", "config.py")
        self.assertEqual(self.decision("git commit -m x", "커밋해 줘"), "deny")
        self.assertIn("GitHub token", self.reason)
        self.assertNotIn("ghp_", self.reason)

    def test_working_tree_secret_denies(self):
        self.write("README.md", "hello\nAuthorization: Bearer " + "b1c2d3e4" * 4 + "\n")
        self.assertEqual(self.decision("git commit -am x", "커밋해 줘"), "deny")
        self.assertIn("bearer token", self.reason)

    def test_untracked_secret_with_git_add_denies(self):
        self.write("new.env", "DB_PASSWORD=supersecretvalue123\n")
        self.assertEqual(self.decision("git add . && git commit -m x", "커밋해 줘"), "deny")
        self.assertIn("unquoted credential", self.reason)
        self.assertEqual(self.decision("git commit -m x", "커밋해 줘"), "allow")

    def test_ignored_and_placeholder_pass(self):
        self.write("ignored.env", "API_KEY=sk-" + "c" * 30 + "\n")
        self.write("settings.py", 'password = "changeme"\nTOKEN = "${GITHUB_TOKEN}"\nsecret="example-secret"\n')
        self.write("ref.js", "const key = process.env.API_KEY;\n")
        self.assertEqual(self.decision("git add . && git commit -m x", "커밋해 줘"), "allow")

    def test_default_value_in_reference_is_checked(self):
        self.write("app.env", "API_TOKEN=${API_TOKEN:-sk-" + "d" * 30 + "}\n")
        self.assertEqual(self.decision("git add . && git commit -m x", "커밋해 줘"), "deny")

    def test_private_key_block_denies(self):
        self.write("key.pem", "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----\n")
        git(self.repo, "add", "key.pem")
        self.assertEqual(self.decision("git commit -m x", "커밋해 줘"), "deny")

    def test_repo_from_leading_cd(self):
        self.write("config.py", 'TOKEN = "glpat-' + "e" * 24 + '"\n')
        git(self.repo, "add", "config.py")
        self.assertEqual(self.decision(f"cd {self.repo} && git commit -m x", "커밋해 줘", cwd=self.tmp), "deny")

    def test_secret_scan_uses_the_commit_repository(self):
        other = self.tmp / "other"
        other.mkdir()
        git(other, "init", "-q")
        self.write("config.py", 'TOKEN = "glpat-' + "e" * 24 + '"\n')
        git(self.repo, "add", "config.py")
        commands = (
            f"git -C {other} status && git commit -m x",
            f"cd {self.tmp} && git -C {self.repo.name} commit -m x",
            f"(cd {other} && git status) && git commit -m x",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.decision(command, "커밋해 줘"), "deny")
                self.assertIn("GitLab token", self.reason)


class CodexTests(HookCase):
    def test_same_turn_prompt_allows(self):
        self.assertEqual(self.decision("git commit -m x", codex=True, recorded="커밋해 줘"), "allow")

    def test_other_turn_prompt_denies(self):
        self.assertEqual(self.decision("git commit -m x", codex=True, recorded="커밋해 줘", recorded_turn="turn-0"), "deny")

    def test_missing_record_denies(self):
        self.assertEqual(self.decision("git commit -m x", codex=True), "deny")
        self.assertIn("could not be read", self.reason)

    def test_negation_denies(self):
        self.assertEqual(self.decision("git push", codex=True, recorded="푸시하지 마"), "deny")

    def test_record_prompt_hook_round_trip(self):
        event = {"hook_event_name": "UserPromptSubmit", "session_id": "session-1", "turn_id": "turn-9",
                 "prompt": "푸시해 줘. private test note", "cwd": str(self.repo)}
        result = self.run_script(RECORD, event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")
        path = self.home / "prompts" / "session-1.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["turn_id"], "turn-9")
        self.assertEqual(saved["actions"], ["push"])
        self.assertNotIn("prompt", saved)
        if os.name == "posix":
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            self.assertEqual(path.parent.stat().st_mode & 0o077, 0)
        self.assertEqual(self.decision("git push", codex=True, turn="turn-9"), "allow")

    def test_record_prompt_ignores_claude_code(self):
        event = {"hook_event_name": "UserPromptSubmit", "session_id": "session-1", "prompt": "푸시해 줘"}
        result = self.run_script(RECORD, event)
        self.assertEqual(result.returncode, 0)
        self.assertFalse((self.home / "prompts").exists())

    def test_record_prompt_prunes_old_files(self):
        folder = self.home / "prompts"
        folder.mkdir(parents=True)
        old = folder / "old.json"
        old.write_text("{}", encoding="utf-8")
        stale = time.time() - 8 * 24 * 60 * 60
        os.utime(old, (stale, stale))
        event = {"hook_event_name": "UserPromptSubmit", "session_id": "session-1", "turn_id": "t", "prompt": "x"}
        self.run_script(RECORD, event)
        self.assertFalse(old.exists())
        self.assertTrue((folder / "session-1.json").exists())


if __name__ == "__main__":
    unittest.main()
