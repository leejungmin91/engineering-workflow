import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import registry_text


class Analyzer(BaseHTTPRequestHandler):
    seen = []
    reply = None
    status = 200
    raw = None

    def do_GET(self):
        Analyzer.seen.append((self.path, None))
        self.send_response(200)
        self.send_header("Content-Length", "13")
        self.end_headers()
        self.wfile.write(b'{"nouns": []}')

    def do_POST(self):
        texts = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["texts"]
        Analyzer.seen.append((self.path, texts))
        nouns = Analyzer.reply if Analyzer.reply is not None else [["창", "돌"] if "창" in text else [] for text in texts]
        body = json.dumps({"nouns": nouns}).encode("utf-8")
        if Analyzer.raw is not None:
            body = Analyzer.raw
        self.send_response(Analyzer.status)
        if Analyzer.status == 302:
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_address[1]}/elsewhere")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


class AnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Analyzer)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.address = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Analyzer.seen, Analyzer.reply, Analyzer.status, Analyzer.raw = [], None, 200, None
        patch = mock.patch.dict(os.environ, {"HARNESS_TOKENIZER_URL": self.address})
        patch.start()
        self.addCleanup(patch.stop)

    def test_analyzer_nouns_replace_the_rule_stems_in_one_request(self):
        terms = registry_text.index_terms_many(["창돌을 깎는다", "English only", "훅을 고친다"])
        self.assertEqual(terms[0].split(), ["창", "돌"])
        self.assertEqual(terms[1], "")
        self.assertEqual(terms[2], "")
        self.assertEqual(len(Analyzer.seen), 1)
        self.assertEqual(Analyzer.seen[0][0], "/nouns")

    def test_query_gets_analyzer_nouns_and_their_english_forms(self):
        Analyzer.reply = [["창", "게임"]]
        words = registry_text.expand(["창게임에서"])
        for expected in ("창게임에서", "창", "게임", "game"):
            self.assertIn(expected, words)
        self.assertNotIn("창게임", words)
        Analyzer.seen = []
        registry_text.expand(["plain", "english"])
        self.assertEqual(Analyzer.seen, [])

    def test_rules_take_over_when_the_analyzer_fails_or_answers_oddly(self):
        expected = registry_text.rule_terms("훅을 고친다", 400)
        for reply, status in (([["x"], ["y"]], 200), ("nope", 200), ([[5, None, "가" * 500]], 200), ([["ok"]], 500)):
            Analyzer.reply, Analyzer.status = reply, status
            self.assertEqual(registry_text.index_terms("훅을 고친다").split(), expected)
        with mock.patch.dict(os.environ, {"HARNESS_TOKENIZER_URL": "http://127.0.0.1:9"}):
            self.assertEqual(registry_text.index_terms("훅을 고친다").split(), expected)
            self.assertIn("훅", registry_text.expand(["훅을"]))

    def test_redirects_bad_addresses_and_deep_or_huge_replies_fall_back_to_rules(self):
        expected = registry_text.rule_terms("훅을 고친다", 400)
        Analyzer.status = 302
        self.assertEqual(registry_text.index_terms("훅을 고친다").split(), expected)
        self.assertEqual([path for path, _ in Analyzer.seen], ["/nouns"])
        Analyzer.status = 200
        Analyzer.raw = b"[" * 200000
        self.assertEqual(registry_text.index_terms("훅을 고친다").split(), expected)
        with mock.patch.object(registry_text, "MAX_REPLY", 10):
            Analyzer.raw = None
            self.assertEqual(registry_text.index_terms("훅을 고친다").split(), expected)
        with mock.patch.dict(os.environ, {"HARNESS_TOKENIZER_URL": "http://["}):
            self.assertEqual(registry_text.index_terms("훅을 고친다").split(), expected)

    def test_text_is_sent_only_to_this_machine(self):
        port = self.server.server_address[1]
        for address in (f"http://localhost.:{port}", f"https://127.0.0.1:{port}", "http://example.invalid", "nonsense"):
            with mock.patch.dict(os.environ, {"HARNESS_TOKENIZER_URL": address}):
                self.assertIsNone(registry_text.analyzer_nouns(["창"], 1))
        self.assertEqual(Analyzer.seen, [])


class TextTests(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("HARNESS_TOKENIZER_URL", None)

    def test_particles_and_endings_are_removed(self):
        self.assertIn("훅", registry_text.stems("훅을"))
        self.assertIn("앱", registry_text.stems("앱에서는"))
        self.assertIn("환불", registry_text.stems("환불했던"))
        self.assertIn("문서", registry_text.stems("문서를"))
        self.assertEqual(registry_text.stems("를"), [])
        self.assertEqual(registry_text.stems("스킬"), [])

    def test_non_korean_words_are_left_alone(self):
        self.assertEqual(registry_text.variants("refunds"), ["refunds"])
        self.assertEqual(registry_text.variants("pdf"), ["pdf"])

    def test_index_terms_adds_only_new_stems(self):
        terms = registry_text.index_terms("훅을 고치면 앱에서 훅을 다시 본다. Hooks stay.").split()
        self.assertIn("훅", terms)
        self.assertIn("앱", terms)
        self.assertEqual(len(terms), len(set(terms)))
        self.assertNotIn("Hooks", terms)
        self.assertEqual(registry_text.index_terms(""), "")
        self.assertEqual(registry_text.index_terms(None), "")
        self.assertLessEqual(len(registry_text.index_terms("가을 " * 5 + " ".join(f"낱말{n}을" for n in range(900))).split()), 400)

    def test_expand_adds_stems_and_english_words(self):
        words = registry_text.expand(["게임", "밸런스를", "점검"])
        for expected in ("게임", "game", "games", "밸런스를", "밸런스", "balance", "check"):
            self.assertIn(expected, words)
        self.assertEqual(words.index("게임"), 0)
        self.assertEqual(len(words), len(set(words)))

    def test_expand_finds_dictionary_words_inside_longer_words(self):
        self.assertIn("review", registry_text.expand(["교차검토해줘"]))
        compound = registry_text.expand(["게임밸런스표"])
        self.assertIn("game", compound)
        self.assertIn("balance", compound)
        self.assertIn("push", registry_text.expand(["커밋과", "푸시"]))
        self.assertIn("pushes", registry_text.expand(["푸시"]))

    def test_work_is_bounded_for_long_input(self):
        self.assertLessEqual(len(registry_text.expand([f"w{n}" for n in range(10000)])), registry_text.MAX_FORMS)
        self.assertEqual(len(registry_text.query_words(["a b c"] * 100)), registry_text.MAX_WORDS)
        self.assertEqual(len(registry_text.query_words(["x" * 5000])[0]), registry_text.MAX_WORD)
        self.assertEqual(registry_text.index_terms("가" * 1_000_000 + "는"), "")
        self.assertEqual(registry_text.index_terms("게임은 " * 1_000_000), "게임")
        self.assertEqual(registry_text.index_terms("x " * registry_text.MAX_TEXT + "훅을"), "")

    def test_plurals_and_glossary_word_matching(self):
        self.assertEqual([registry_text.plural(word) for word in ("dependency", "push", "key", "task")],
                         ["dependencies", "pushes", "keys", "tasks"])
        self.assertIn("dependencies", registry_text.expand(["의존성"]))
        self.assertTrue(registry_text.names("눈밥에서", "눈밥"))
        self.assertTrue(registry_text.names("app", "app"))
        self.assertFalse(registry_text.names("happy", "app"))
        self.assertFalse(registry_text.names("앱스토어", "앱"))

    def test_expand_takes_extra_pairs_and_keeps_english_queries(self):
        self.assertIn("ledger", registry_text.expand(["장부"], {"장부": "ledger"}))
        self.assertEqual(registry_text.expand(["dependency", "graph"]), ["dependency", "graph"])
        self.assertEqual(registry_text.expand(["a+b", "x:y"]), ["a+b", "x", "y"])
        self.assertEqual(registry_text.expand([]), [])


if __name__ == "__main__":
    unittest.main()
