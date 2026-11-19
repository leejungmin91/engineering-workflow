import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import registry_text


class TextTests(unittest.TestCase):
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
