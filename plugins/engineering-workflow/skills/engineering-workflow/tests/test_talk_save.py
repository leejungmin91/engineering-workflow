import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import registry_scan
import registry_talk
import talk_save

SESSION = "01234567-89ab-cdef-0123-456789abcdef"
NOW = 1_800_000_000.0


def user(text, at="2026-11-26T07:00:00Z", **extra):
    return {"type": "user", "timestamp": at, "message": {"role": "user", "content": text}, **extra}


def reply(text, **extra):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}, **extra}


def tool_result():
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "ls output"}]}}


class TalkSaveTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.project = self.root / "apps" / "game"
        (self.project / "sub").mkdir(parents=True)
        config = self.root / "registry.json"
        config.write_text(json.dumps({"apps": [{"name": "game", "path": str(self.project)}]}))
        patcher = mock.patch.dict("os.environ", {"HARNESS_TALK": str(self.root / "talk"),
                                                 "HARNESS_REGISTRY_CONFIG": str(config)})
        patcher.start()
        self.addCleanup(patcher.stop)
        talk_save.os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.transcript = self.root / "projects" / f"{SESSION}.jsonl"
        self.transcript.parent.mkdir()

    def append(self, *entries):
        with open(self.transcript, "a", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def event(self, name="SessionEnd", **extra):
        return {"hook_event_name": name, "session_id": SESSION, "transcript_path": str(self.transcript),
                "cwd": str(self.project / "sub"), **extra}

    def notes(self):
        return sorted((self.root / "talk" / "game").glob("*.md"))

    def test_saves_user_words_and_final_reply_only(self):
        self.append(user("fable 다썼음 opus 로 돌려줘"), reply("먼저 확인하겠습니다."), tool_result(),
                    reply("Opus로 진행합니다."),
                    user("<system-reminder>secret context</system-reminder>빌드해줘"), reply("빌드했습니다."),
                    user("side question", isSidechain=True), reply("side answer", isSidechain=True),
                    user("summary of earlier talk", isCompactSummary=True),
                    user("<command-name>/usage</command-name>"))
        written = talk_save.save(self.event(), NOW)
        self.assertEqual(len(written), 1)
        text = written[0].read_text(encoding="utf-8")
        self.assertIn("fable 다썼음 opus 로 돌려줘", text)
        self.assertIn("답: Opus로 진행합니다.", text)
        self.assertNotIn("먼저 확인하겠습니다", text)
        self.assertIn("빌드해줘", text)
        for hidden in ("secret context", "side question", "side answer", "summary of earlier", "/usage", "ls output"):
            self.assertNotIn(hidden, text)
        self.assertIn("app: game", text)
        title = [line for line in text.splitlines() if line.startswith("title:")][0]
        self.assertEqual(title, 'title: "fable 다썼음 opus 로 돌려줘"')
        self.assertIn(talk_save.local("2026-11-26T07:00:00Z"), text)
        self.assertNotIn("(2026-11-26 07:00)", text.replace(talk_save.local("2026-11-26T07:00:00Z"), ""))

    def test_second_save_takes_only_what_is_new(self):
        self.append(user("첫 번째 요청"), reply("첫 답"))
        talk_save.save(self.event(), NOW)
        self.append(user("두 번째 요청"), reply("둘째 답"))
        written = talk_save.save(self.event(), NOW + 60)
        self.assertEqual(len(written), 1)
        text = written[0].read_text(encoding="utf-8")
        self.assertIn("두 번째 요청", text)
        self.assertNotIn("첫 번째 요청", text)
        self.assertEqual(talk_save.save(self.event(), NOW + 120), [])

    def test_half_written_last_line_waits_for_the_next_save(self):
        self.append(user("완성된 줄"), reply("답"))
        with open(self.transcript, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(user("아직 쓰는 중"))[:20])
        text = talk_save.save(self.event(), NOW)[0].read_text(encoding="utf-8")
        self.assertNotIn("아직 쓰는 중", text)
        with open(self.transcript, "a", encoding="utf-8") as handle:
            handle.write("\n")
        self.append(user("다음 요청"))
        self.assertIn("다음 요청", talk_save.save(self.event(), NOW + 1)[0].read_text(encoding="utf-8"))

    def test_compaction_keeps_the_open_exchange_for_its_final_reply(self):
        self.append(user("끝난 요청"), reply("끝난 답"), user("진행 중 요청"), reply("중간 답"))
        text = talk_save.save(self.event("PreCompact"), NOW)[0].read_text(encoding="utf-8")
        self.assertIn("끝난 요청", text)
        self.assertNotIn("진행 중 요청", text)
        self.append(reply("최종 답"))
        later = talk_save.save(self.event(), NOW)[0].read_text(encoding="utf-8")
        self.assertIn("진행 중 요청", later)
        self.assertIn("답: 최종 답", later)
        self.assertNotIn("끝난 요청", later)

    def test_saves_in_the_same_second_keep_both_notes(self):
        self.append(user("하나"), reply("답 하나"))
        first = talk_save.save(self.event(), NOW)
        self.append(user("둘"), reply("답 둘"))
        second = talk_save.save(self.event(), NOW)
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.notes()), 2)
        self.assertIn("하나", first[0].read_text(encoding="utf-8"))

    def test_notes_never_go_into_a_repository_or_a_relative_folder(self):
        repo = self.root / "repo"
        (repo / ".git").mkdir(parents=True)
        self.append(user("비밀 대화"))
        for place in (str(repo / "notes" / "talk"), "notes/talk"):
            with mock.patch.dict("os.environ", {"HARNESS_TALK": place}):
                self.assertEqual(talk_save.save(self.event(), NOW), [])
        self.assertFalse((repo / "notes").exists())
        self.assertFalse(talk_save.state_file(SESSION).exists())

    def test_app_names_cannot_lead_out_of_the_notes_folder(self):
        repo = self.root / "repo"
        (repo / ".git").mkdir(parents=True)
        (self.root / "talk").mkdir()
        (self.root / "talk" / "linked").symlink_to(repo)
        self.append(user("비밀 대화"), reply("답"))
        with mock.patch.object(talk_save, "app_for", return_value=str(repo)):
            written = talk_save.save(self.event(), NOW)
        self.assertTrue(all(path.resolve().is_relative_to((self.root / "talk").resolve()) for path in written))
        self.assertFalse(list(repo.rglob("*.md")))
        self.append(user("또 비밀"), reply("답"))
        with mock.patch.object(talk_save, "app_for", return_value="linked"):
            self.assertEqual(talk_save.save(self.event(), NOW + 1), [])
        self.assertFalse(list(repo.rglob("*.md")))
        written = talk_save.save(self.event(), NOW + 2)
        self.assertIn("또 비밀", written[0].read_text(encoding="utf-8"))

    def test_a_request_without_its_reply_is_saved_again_with_it(self):
        self.append(user("답을 기다리는 요청"))
        self.assertIn("답을 기다리는 요청", talk_save.save(self.event(), NOW)[0].read_text(encoding="utf-8"))
        self.append(reply("늦게 온 답"))
        again = talk_save.save(self.event(), NOW + 1)[0].read_text(encoding="utf-8")
        self.assertIn("답을 기다리는 요청", again)
        self.assertIn("답: 늦게 온 답", again)

    def test_a_planted_link_at_a_temporary_name_is_not_followed(self):
        target = self.root / "outside.txt"
        target.write_text("untouched")
        folder = self.root / "talk" / "game"
        folder.mkdir(parents=True)
        for name in (".part", f".x.part"):
            (folder / name).symlink_to(target)
        self.append(user("요청"), reply("답"))
        self.assertEqual(len(talk_save.save(self.event(), NOW)), 1)
        self.assertEqual(target.read_text(), "untouched")
        self.assertFalse([path for path in folder.iterdir() if path.name.endswith(".part") and not path.is_symlink()])

    def test_long_talk_is_split_into_searchable_notes(self):
        for index in range(30):
            self.append(user(f"요청 {index} " + "가" * 400), reply("답 " + "나" * 400))
        written = talk_save.save(self.event(), NOW)
        self.assertGreater(len(written), 1)
        for path in written:
            body = registry_scan.frontmatter(path.read_text(encoding="utf-8"))[1]
            self.assertLessEqual(len(body), registry_scan.BODY_LIMIT)

    def test_refuses_other_files_events_and_ids(self):
        other = self.root / "projects" / "notes.jsonl"
        other.write_text(json.dumps(user("not this")) + "\n")
        self.assertEqual(talk_save.save(dict(self.event(), transcript_path=str(other)), NOW), [])
        self.assertEqual(talk_save.save(dict(self.event(), session_id="../../x"), NOW), [])
        self.append(user("hello"))
        self.assertEqual(talk_save.save(self.event("Stop"), NOW), [])
        self.assertFalse((self.root / "talk").exists())

    def test_unknown_folder_uses_its_name(self):
        self.append(user("밖에서 한 말"))
        written = talk_save.save(dict(self.event(), cwd=str(self.root / "loose dir")), NOW)
        self.assertEqual(written[0].parent.name, "loose-dir")

    def test_registry_reads_notes_as_talk_nodes_for_listed_apps(self):
        self.append(user("저장 서버 필요할까"), reply("Firebase를 권합니다."))
        talk_save.save(self.event(), NOW)
        config = {"apps": [{"name": "game", "path": str(self.project)}], "talk": str(self.root / "talk")}
        found = registry_talk.files(config)
        self.assertEqual(len(found), 1)
        entry = next(iter(found.values()))
        self.assertEqual(entry["kind"], "talk")
        self.assertEqual(entry["nodes"][0]["type"], "talk")
        self.assertTrue(entry["nodes"][0]["id"].startswith("talk:game/"))
        self.assertIn("저장 서버 필요할까", entry["nodes"][0]["text"])
        self.assertEqual(entry["links"], [{"from": entry["nodes"][0]["id"], "type": "IN", "to": "app:game"}])
        self.assertEqual(registry_talk.files(dict(config, talk=None)), {})
        self.assertEqual(registry_talk.files(dict(config, apps=[])), {})

if __name__ == "__main__":
    unittest.main()
