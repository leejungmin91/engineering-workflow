import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/copy_check.py"
SPEC = importlib.util.spec_from_file_location("copy_check", SCRIPT)
copy_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(copy_check)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / ".harness").mkdir()
        self.before = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(os.chdir, self.before)

    def sheet(self, **values):
        (self.root / ".harness" / "copy-style.json").write_text(json.dumps(values, ensure_ascii=False),
                                                                encoding="utf-8")

    def copy(self, strings, name="ko.json"):
        (self.root / name).write_text(json.dumps(strings, ensure_ascii=False), encoding="utf-8")
        return name

    def run_check(self, *args):
        out, err = io.StringIO(), io.StringIO()
        raw = io.BytesIO()
        out.buffer = raw
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = copy_check.main(list(args))
        return code, raw.getvalue().decode("utf-8"), err.getvalue()

    def rules(self, *args):
        code, out, _ = self.run_check("--json", *args)
        return code, [(item["key"], item["rule"], item["severity"]) for item in json.loads(out)]


class LevelTest(unittest.TestCase):
    def test_endings(self):
        expected = {"저장했습니다.": "hapsyo", "계속하시겠습니까?": "hapsyo", "다시 시도하십시오": "hapsyo",
                    "저장했어요!": "haeyo", "다시 시도해 주세요": "haeyo", "맞죠?": "haeyo", "저장했다.": "plain",
                    "설정": None, "저장하기": None, "권한이 필요": None, "OK": None, "넓은 바다": None, "캐나다": None,
                    "파일이 없다": "plain", "삭제한다": "plain", "오류이다": "plain", "판다": None,
                    "비밀번호가 다르다.": "plain", "저장하다": "plain", "사이다": None}
        for text, level in expected.items():
            self.assertEqual(copy_check.level(text), level, text)


class CheckTest(Case):
    def test_planted_level_fails_against_the_sheet(self):
        self.sheet(level="haeyo")
        name = self.copy({"a": "저장했어요.", "b": "저장에 실패했습니다.", "c": "설정"})
        code, found = self.rules(name)
        self.assertEqual(code, 1)
        self.assertEqual(found, [("b", "speech-level", "error")])

    def test_clean_copy_passes(self):
        self.sheet(level="haeyo")
        code, out, _ = self.run_check(self.copy({"a": "저장했어요.", "b": "다시 시도해 주세요.", "c": "설정"}))
        self.assertEqual((code, out), (0, "0 errors, 0 warnings\n"))

    def test_without_a_sheet_the_minority_is_reported(self):
        name = self.copy({"a": "저장했어요.", "b": "삭제했어요.", "c": "실패했습니다."})
        self.assertEqual(self.rules(name), (1, [("c", "speech-level", "error")]))

    def test_one_text_mixing_levels(self):
        name = self.copy({"a": "저장했습니다. 다시 열어 보세요."})
        self.assertEqual(self.rules(name), (1, [("a", "speech-level", "error")]))

    def test_terms_and_preferred_word_containing_the_avoided_one(self):
        self.sheet(terms={"로그인": ["로그 인", "사인인"], "저장하기": ["저장"]})
        name = self.copy({"a": "로그 인 화면", "b": "저장하기", "c": "저장 완료"})
        self.assertEqual(self.rules(name), (1, [("a", "term", "error"), ("c", "term", "error")]))

    def test_correction_log_keeps_a_fixed_wording_from_returning(self):
        (self.root / ".harness" / "copy-corrections.md").write_text(
            "# Copy corrections\n\n- `로그인 하기` => `로그인하기` | 붙여 쓴다\n- 구매 => 구입\nnot a row\n", encoding="utf-8")
        name = self.copy({"a": "로그인 하기", "b": "로그인하기", "c": "구매 내역", "d": "구입 내역"})
        self.assertEqual(self.rules(name), (1, [("a", "corrected", "error"), ("c", "corrected", "error")]))

    def test_banned_spelling_spacing(self):
        self.sheet(banned=["죄송"])
        name = self.copy({"a": "죄송해요", "b": "안 되요", "c": "저장  완료", "d": "끝났어요 !", "e": "돼요",
                          "f": "남은 횟수: 3 !", "g": "이름: {name} ?", "h": "크기 . 색"})
        self.assertEqual(self.rules(name), (1, [("a", "banned", "error"), ("b", "spelling", "error"),
                                               ("c", "spacing", "error"), ("d", "spacing", "error"),
                                               ("f", "spacing", "error"), ("g", "spacing", "error"),
                                               ("h", "spacing", "error")]))

    def test_period_rule(self):
        self.sheet(period="never")
        name = self.copy({"a": "저장했어요.", "b": "저장했어요", "c": "불러오고 있어요...", "d": "저장 완료.", "e": "설정",
                          "f": "v1.2."})
        self.assertEqual(self.rules(name), (1, [("a", "period", "error"), ("d", "period", "error")]))
        self.sheet(period="always")
        self.assertEqual(self.rules(name), (1, [("b", "period", "error")]))

    def test_length_by_key_pattern(self):
        self.sheet(max_length={"button.*": 4, "steps[0]*": 2})
        name = self.copy({"button": {"ok": "확인", "save": "변경 내용 저장"}, "title": "아주 긴 제목입니다",
                          "steps": ["긴 문구", "다른 긴 문구"]})
        self.assertEqual(self.rules(name), (1, [("button.save", "length", "error"), ("steps[0]", "length", "error")]))

    def test_warnings_pass_unless_strict(self):
        name = self.copy({"a": "파일이 삭제되어집니다", "b": "친구을(를) 초대"})
        code, found = self.rules(name)
        self.assertEqual((code, found), (0, [("a", "translated", "warning"), ("b", "paired-particle", "warning")]))
        self.assertEqual(self.run_check("--strict", name)[0], 1)
        self.sheet(paired_particles="error")
        self.assertEqual(self.rules(name)[0], 1)
        self.sheet(paired_particles="allow")
        self.assertEqual(self.rules(name)[1], [("a", "translated", "warning")])

    def test_placeholders_against_the_base_file(self):
        (self.root / "en.json").write_text(json.dumps({"a": "Hi {name}, %d left", "b": "Done", "c": "{n} items"}),
                                           encoding="utf-8")
        name = self.copy({"a": "{name} 님, %d개 남았어요", "b": "끝났어요 {n}", "c": "항목 개", "x": "기타"})
        self.assertEqual(self.rules("--base", "en.json", name),
                         (1, [("b", "placeholder", "error"), ("c", "placeholder", "error")]))
        self.sheet(allow=["b", "항목 개"])
        self.assertEqual(self.rules("--base", "en.json", name), (0, []))

    def test_placeholders_in_plural_forms_and_format_flags(self):
        (self.root / "en.json").write_text(json.dumps({
            "a": "{count, plural, one{# item} other{{count} items}}", "b": "{count, plural, other{You have items}}",
            "c": "%02d minutes left", "d": "%1$s of %2$.1f", "e": "{count, plural, one{# ride} other{{count} rides}}",
            "f": "{who} sent {count, plural, one{a photo} other{photos}}",
            "g": "{count, plural, other{{total} left}}"}), encoding="utf-8")
        name = self.copy({"a": "{count, plural, other{항목 {count}개}}", "b": "{n, plural, other{항목이 있어요}}",
                          "c": "남은 시간", "d": "%2$.1f 중 %1$s", "e": "{count}회", "f": "{who} 님이 사진을 보냈어요",
                          "g": "{count}개 남았어요"})
        self.assertEqual(self.rules("--base", "en.json", name),
                         (1, [("b", "placeholder", "error"), ("c", "placeholder", "error"),
                              ("f", "placeholder", "error"), ("g", "placeholder", "error")]))

    def test_allow_by_text_and_key(self):
        self.sheet(level="haeyo", allow=["legal.*", "실패했습니다."])
        name = self.copy({"legal": {"a": "동의합니다."}, "b": "실패했습니다.", "c": "취소했습니다."})
        self.assertEqual(self.rules(name), (1, [("c", "speech-level", "error")]))

    def test_other_formats(self):
        self.sheet(level="haeyo", max_length={"save": 8})
        (self.root / "a.strings").write_text('# old = 예전입니다.\n"save" = "저장했습니다.";\n"ok" = "확인";\n', encoding="utf-8")
        (self.root / "a.xml").write_text(
            '<resources><string name="save">저장<b>했습니다</b>.</string>'
            '<string translatable="true" name="late">끝났습니다.</string>'
            '<string name="cdata"><![CDATA[지웠습니다.]]></string>'
            '<!-- <string name="old">예전입니다.</string> --></resources>', encoding="utf-8")
        (self.root / "b.properties").write_text("! 예전입니다.\nsave: 저장했습니다.\nok = 확인\n", encoding="utf-8")
        (self.root / "b.strings").write_text('"two" = "끝났습니다.\\n저장했어요.";\n', encoding="utf-8")
        self.assertEqual(self.rules("b.properties", "b.strings"),
                         (1, [("save", "speech-level", "error"), ("two", "speech-level", "error")]))
        (self.root / "a.arb").write_text(json.dumps({"save": "저장했어요.", "@save": {"description": "저장했습니다."}},
                                                    ensure_ascii=False), encoding="utf-8")
        self.assertEqual(self.rules("a.arb"), (0, []))
        (self.root / "a.md").write_text("# 안내\n\n저장했습니다.\n저장했어요.\n", encoding="utf-8")
        self.assertEqual(self.rules("a.strings", "a.xml", "a.md"),
                         (1, [("save", "speech-level", "error"), ("save", "speech-level", "error"),
                              ("late", "speech-level", "error"), ("cdata", "speech-level", "error"),
                              ("3", "speech-level", "error")]))

    def test_sources_and_log_from_the_sheet(self):
        (self.root / "fixes.md").write_text("- 구매 => 구입\n", encoding="utf-8")
        self.sheet(sources=["ko.json"], log="fixes.md")
        self.copy({"a": "구매 내역"})
        other = self.root / "elsewhere"
        other.mkdir()
        os.chdir(other)
        code, found = self.rules("--style", str(self.root / ".harness" / "copy-style.json"))
        self.assertEqual((code, found), (1, [("a", "corrected", "error")]))

    def test_text_output(self):
        self.sheet(level="haeyo")
        code, out, _ = self.run_check(self.copy({"b": "실패했습니다."}))
        self.assertEqual(code, 1)
        self.assertIn("ko.json:b: error: speech-level: '실패했습니다.' ends in 합니다 style, the sheet says 해요", out)
        self.assertTrue(out.endswith("1 errors, 0 warnings\n"))

    def test_setup_problems_exit_two(self):
        name = self.copy({"a": "저장했어요"})
        self.assertEqual(self.run_check()[0], 2)
        self.assertEqual(self.run_check("missing.json")[0], 2)
        self.assertEqual(self.run_check("--style", "nope.json", name)[0], 2)
        self.assertEqual(self.run_check("--log", "nope.md", name)[0], 2)
        (self.root / "bad.json").write_text("{", encoding="utf-8")
        self.assertEqual(self.run_check("bad.json")[0], 2)
        (self.root / "bad.xml").write_text("<resources><string name='a'>저장", encoding="utf-8")
        self.assertEqual(self.run_check("bad.xml")[0], 2)
        for values in ({"level": "polite"}, {"period": "maybe"}, {"terms": {"a": "b"}}, {"max_length": {"a": 0}},
                       {"banned": "x"}, {"levle": "haeyo"}, {"log": 7}, {"allow": [1]}, {"paired_particles": "no"}):
            self.sheet(**values)
            code, _, err = self.run_check(name)
            self.assertEqual(code, 2, values)
            self.assertIn("COPY CHECK UNAVAILABLE", err)


if __name__ == "__main__":
    unittest.main()
