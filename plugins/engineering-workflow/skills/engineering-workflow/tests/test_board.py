import importlib.util
import json
import os
import shutil
import time
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/board.py"
SPEC = importlib.util.spec_from_file_location("board", SCRIPT)
board = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(board)


def task(id, status="todo", after=None, title=None, owner=None):
    item = {"id": id, "title": title or f"task {id}", "status": status, "after": after or []}
    if owner:
        item["owner"] = owner
    return item


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "app"
        self.home = Path(self.tmp.name).resolve() / "boards"
        (self.root / ".harness").mkdir(parents=True)
        self.path = self.root / ".harness" / "board.json"
        patch = mock.patch.dict(os.environ, {"HARNESS_BOARD_HOME": str(self.home), "HARNESS_BOARD_OPEN": "0",
                                             "CLAUDE_PROJECT_DIR": str(self.root)})
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def save(self, tasks, **extra):
        self.path.write_text(json.dumps({"title": "Demo", "tasks": tasks, **extra}), encoding="utf-8")

    def page(self):
        return board.publish(self.path).read_text(encoding="utf-8")


class BoardTests(Case):
    def test_progress_counts_done_tasks(self):
        self.save([task("a", "done"), task("b", "doing"), task("c"), task("d", "done")])
        content = self.page()
        self.assertIn(">50%<", content)
        self.assertIn("2 of 4 tasks done", content)
        self.assertIn('aria-valuenow="50"', content)

    def test_progress_reaches_100_only_when_everything_is_done(self):
        self.save([task(f"t{n}", "done") for n in range(199)] + [task("last")])
        self.assertIn(">99%<", self.page())

    def test_every_text_field_is_escaped_on_both_pages(self):
        mark = "<script>alert(1)</script>"
        self.root = self.root.parent / "a&b"
        (self.root / ".harness").mkdir(parents=True)
        self.path = self.root / ".harness" / "board.json"
        self.path.write_text(json.dumps({
            "title": f"title {mark}",
            "tasks": [{"id": "a", "title": f"t {mark}", "status": "todo", "owner": f"o {mark}", "note": f"n {mark}"},
                      {"id": "b", "title": "plain", "after": ["a"]}],
            "decisions": [{"ask": f"ask {mark}", "look": f"look {mark}", "default": f"default {mark}"}]}),
            encoding="utf-8")
        content = self.page()
        listing = (self.home / "index.html").read_text(encoding="utf-8")
        for output in (content, listing):
            self.assertNotIn(mark, output)
            self.assertNotIn("a&b", output)
            self.assertIn("a&amp;b", output)
        for field in ("title", "t", "o", "n", "ask", "look", "default"):
            self.assertIn(f"{field} &lt;script&gt;alert(1)&lt;/script&gt;", content)
        self.assertIn("title &lt;script&gt;", listing)

    def test_decisions_come_from_the_board_and_working_file(self):
        self.save([task("a")], decisions=[{"ask": "Pick a store", "look": "docs/a.md", "default": "none"}])
        (self.root / "WORKING.md").write_text(
            "# Who\n\n## Waiting for the user (parked)\n\n- Approve the icon\n- None\n(none)\n```\n- in a fence\n```\n"
            "\n## Sessions\n\n- not this\n", encoding="utf-8")
        content = self.page()
        self.assertIn("Pick a store", content)
        self.assertIn("Approve the icon", content)
        self.assertNotIn("not this", content)
        self.assertNotIn("in a fence", content)
        self.assertEqual(content.count('class="decision"'), 2)

    def test_working_file_bullets_keep_their_wrapped_lines_and_can_be_left_out(self):
        (self.root / "WORKING.md").write_text(
            "## Waiting for the user\n\n- Pick the ground sample:\n  all, some, or none.\n  ```text\n  example only\n  ~~~\n  ```\n"
            "- Second\n", encoding="utf-8")
        self.save([task("a")])
        content = self.page()
        self.assertIn("Pick the ground sample: all, some, or none.</", content)
        self.assertNotIn("example only", content)
        self.assertEqual(content.count('class="decision"'), 2)
        self.save([task("a")], working_decisions=False)
        self.assertEqual(self.page().count('class="decision"'), 0)
        self.save([task("a")], working_decisions="no")
        with self.assertRaises(ValueError):
            board.load(self.root / ".harness" / "board.json")

    def test_a_task_in_progress_spins_and_a_dead_runner_is_shown_as_stalled(self):
        self.save([task("a", "doing"), task("b", "todo")])
        content = self.page()
        self.assertIn('<span class="spin" aria-hidden="true"></span>', content)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        marker = self.root / ".git" / "run_queue.doing"
        marker.write_text(json.dumps({"task": "a", "pid": 999999, "board": str(self.path.resolve())}), encoding="utf-8")
        if os.name != "nt":
            content = self.page()
            self.assertNotIn('<span class="spin" aria-hidden="true"></span>', content)
            self.assertIn('class="chip bad"', content)
        other = self.root / ".harness" / "other.json"
        other.write_text(self.path.read_text(encoding="utf-8"), encoding="utf-8")
        marker.write_text(json.dumps({"task": "a", "pid": 999999, "board": str(self.path.resolve())}), encoding="utf-8")
        if os.name != "nt":
            self.assertIn('<span class="spin" aria-hidden="true"></span>', board.publish(other).read_text(encoding="utf-8"))
        marker.write_text(json.dumps({"task": "a", "pid": 999999, "board": "/elsewhere/board.json"}), encoding="utf-8")
        if os.name != "nt":
            self.assertIn('<span class="spin" aria-hidden="true"></span>', self.page())
        marker.write_text(json.dumps({"task": "a", "pid": os.getpid(), "board": str(self.path.resolve())}), encoding="utf-8")
        self.assertIn('<span class="spin" aria-hidden="true"></span>', self.page())

    def test_tasks_are_grouped_by_state_with_what_is_next(self):
        self.save([task("a", "done"), task("b", "doing"), task("c", after=["b"]), task("d", after=["a"]),
                   task("e", "blocked"), task("f", after=["e"])])
        content = self.page()
        now = content[content.index("<div class=\"top\">"):content.index("id=\"decisions\"")]
        self.assertIn("task b", now.split("<h2>Next</h2>")[0])
        self.assertIn("task d", now.split("<h2>Next</h2>")[1])
        self.assertNotIn("task c", now)
        groups = content[content.index("<h2>Tasks</h2>"):]
        self.assertLess(groups.index("task b"), groups.index("task e"))
        self.assertLess(groups.index("task e"), groups.index("task c"))
        self.assertIn('<details class="fold" id="done">', groups)
        self.assertIn('b after</span>', groups)
        self.assertIn('class="chip bad"', content)
        self.save([task("a", "done"), task("c", after=["b"]), task("b", after=["a"]), task("z", after=["c"])])
        top = self.page().split("<h2>Next</h2>")[1].split("</div>")[0]
        self.assertIn("task b", top)
        self.save([task("c", "todo", after=["b"]), task("b", "doing")])
        top = self.page().split("<h2>Next</h2>")[1].split("</div>")[0]
        self.assertIn("task c", top)
        self.assertIn("b after", top)

    def test_owner_filter_appears_only_with_two_owners_and_records_are_listed(self):
        self.save([task("a", owner="build"), task("b", owner="build")])
        self.assertNotIn('class="filters"', self.page())
        self.save([task("a", owner="build"), task("b", owner="planner"), task("c", "done", owner="old")])
        content = self.page()
        self.assertIn('data-owner="planner"', content)
        self.assertNotIn('<button data-owner="old"', content)
        self.assertIn(".row[hidden]{display:none}", content)
        self.assertIn('.filters button[data-owner="${CSS.escape(saved.owner)}"]', content)
        noted = dict(task("a", owner="build"), note="first note")
        self.save([noted, task("b", owner="planner")])
        self.assertIn('<details id="note-a">', self.page())
        self.save([dict(task("x"), note="x note"), noted, task("b", owner="planner")])
        content = self.page()
        self.assertIn('<details id="note-a"><summary>first note', content)
        self.assertIn('<details id="note-x"><summary>x note', content)
        records = self.root / ".harness" / "records"
        records.mkdir(parents=True)
        for day in range(1, 8):
            (records / f"2026-11-0{day}-r.md").write_text(f"---\nid: x\ntitle: \"Record {day}\"\n---\nbody\n", encoding="utf-8")
        for number, name in enumerate(("z-oldest", "y", "x", "w", "v", "a-newest")):
            path = records / f"2026-11-09-{name}.md"
            path.write_text(f"---\nid: x\ntitle: \"Same day {name}\"\n---\nbody\n", encoding="utf-8")
            os.utime(path, (1_800_000_000 + number, 1_800_000_000 + number))
        (records / "2026-11-08-broken.md").write_bytes(b"\xff\xfe")
        content = self.page()
        self.assertIn("Same day a-newest", content)
        self.assertNotIn("Same day z-oldest", content)
        self.assertNotIn("Record 7", content)

    def test_overview_puts_boards_that_need_the_user_first_and_redraws_stale_ones(self):
        self.save([task("a", "done"), task("b")], title="Calm")
        self.page()
        other = self.root.parent / "other"
        (other / ".harness").mkdir(parents=True)
        (other / ".harness" / "board.json").write_text(json.dumps({"title": "Zoo", "tasks": [task("x", "blocked")]}),
                                                      encoding="utf-8")
        board.publish(other / ".harness" / "board.json")
        listing = (self.home / "index.html").read_text(encoding="utf-8")
        self.assertLess(listing.index("Zoo"), listing.index("Calm"))
        self.assertIn('class="chip bad"', listing)
        self.assertIn("data-at=", listing)
        summary = next(path for path in self.home.glob("other-*.json"))
        time.sleep(0.05)
        (other / ".harness" / "board.json").write_text(json.dumps({"title": "Zoo now", "tasks": [task("x", "done")]}),
                                                      encoding="utf-8")
        os.utime(other / ".harness" / "board.json", (time.time() + 5, time.time() + 5))
        self.page()
        listing = (self.home / "index.html").read_text(encoding="utf-8")
        self.assertIn("Zoo now", listing)
        self.assertIn("Zoo now", next(self.home.glob("other-*.html")).read_text(encoding="utf-8"))
        data = json.loads(summary.read_text(encoding="utf-8"))
        legacy = {key: data[key] for key in ("title", "root", "board", "page", "percent", "done", "total", "doing",
                                              "decisions", "stamp")}
        legacy["title"] = "Legacy"
        summary.write_text(json.dumps(legacy), encoding="utf-8")
        os.utime(summary, (time.time() + 60, time.time() + 60))
        self.page()
        listing = (self.home / "index.html").read_text(encoding="utf-8")
        self.assertIn("Zoo now", listing)
        self.assertNotIn("Legacy", listing)
        data = json.loads(summary.read_text(encoding="utf-8"))
        data["tally"] = {"done": "1;background:url(x)"}
        summary.write_text(json.dumps(data), encoding="utf-8")
        os.utime(summary, (time.time() + 60, time.time() + 60))
        self.page()
        self.assertNotIn("Zoo now", (self.home / "index.html").read_text(encoding="utf-8"))

    def test_decision_pictures_open_in_a_viewer_and_stay_inside_the_project(self):
        pictures = self.root / "docs"
        pictures.mkdir(parents=True)
        (pictures / "a.png").write_bytes(b"png-a")
        (pictures / "b.jpg").write_bytes(b"jpg-b")
        (pictures / "big.png").write_bytes(b"x" * 50)
        (pictures / "my mockup.png").write_bytes(b"spaced")
        (self.root / "mockup.png").write_bytes(b"wrong")
        (pictures / "link.png").symlink_to(self.root.parent / "outside.png")
        (self.root.parent / "outside.png").write_bytes(b"secret")
        self.save([task("a")], decisions=[
            {"ask": "Pick", "look": "docs/a.png or `docs/missing.png`, ../outside.png, docs/big.png, `docs/my mockup.png`, docs/link.png",
             "default": "a",
             "images": ["docs/b.jpg", str(self.root.parent / "outside.png"), "docs/a.png"]},
            {"ask": "No pictures", "look": "docs/notes.md"}])
        with mock.patch.object(board, "PICTURE_BYTES", 10):
            content = self.page()
        assets = sorted(path.read_bytes() for path in (self.home / "assets").iterdir())
        self.assertEqual(assets, [b"jpg-b", b"png-a", b"spaced"])
        self.assertEqual(content.count('class="thumb"'), 3)
        self.assertIn('data-name="docs/b.jpg"', content)
        self.assertIn('<dialog class="viewer"', content)
        self.assertIn("if (document.querySelector('dialog[open]')) return;", content)
        self.assertNotIn("secret", content)
        self.save([task("a")], decisions=[{"ask": "Plain"}])
        self.assertNotIn("<dialog", self.page())
        self.save([task("a")], decisions=[{"ask": "Bad", "images": "docs/a.png"}])
        with self.assertRaises(ValueError):
            board.load(self.path)

    def test_pictures_come_from_folders_and_the_documents_a_decision_points_to(self):
        gallery = self.root / "docs" / "gallery" / "31_ground"
        gallery.mkdir(parents=True)
        for name in ("a.jpg", "b.png", "notes.txt"):
            (gallery / name).write_bytes(name.encode())
        page = self.root / "docs" / "review" / "index.html"
        page.parent.mkdir(parents=True)
        (page.parent / "c.png").write_bytes(b"c")
        page.write_text('<img src="c.png"><img src="../gallery/31_ground/a.jpg"><img src="https://x.org/y.png">'
                        '<img src="../../../outside.png"><a href="c.png">big</a>', encoding="utf-8")
        (self.root.parent / "outside.png").write_bytes(b"secret")
        notes = self.root / "docs" / "plan.md"
        notes.write_text("![sketch](review/c.png) and ![gone](missing.png)", encoding="utf-8")
        many = self.root / "docs" / "many"
        many.mkdir()
        for number in range(12):
            (many / f"{number:02d}.png").write_bytes(bytes([number]))
        self.save([task("a")], decisions=[
            {"ask": "Ground", "look": "docs/gallery/31_ground (now above, sample below)"},
            {"ask": "Page", "look": "docs/review/index.html"},
            {"ask": "Notes", "look": "docs/plan.md (section 2)"},
            {"ask": "Many", "images": ["docs/many"]}])
        content = self.page()
        cards = content.split('class="decision"')[1:]
        self.assertEqual([card.count('class="thumb"') for card in cards], [2, 2, 1, 8])
        self.assertIn('data-name="docs/gallery/31_ground/a.jpg"', cards[0])
        self.assertIn('data-name="docs/review/c.png"', cards[1])
        self.assertNotIn("outside", content)
        self.assertNotIn("x.org", content)

    def test_document_forms_fifos_links_and_heavy_input(self):
        docs = self.root / "docs"
        docs.mkdir(parents=True)
        for name in ("t.png", "my sketch.png", "u.png", "d.png"):
            (docs / name).write_bytes(name.encode())
        (docs / "forms.md").write_text('![a](t.png "Title") ![b](<my sketch.png>) <img src=u.png alt=x> '
                                       '<a href="d.png?download=1">full</a>', encoding="utf-8")
        outside = self.root.parent / "outer.md"
        outside.write_text('![x](t.png)', encoding="utf-8")
        (docs / "linked.md").symlink_to(outside)
        os.mkfifo(docs / "stream.md")
        (docs / "heavy.md").write_text("![" * 300_000, encoding="utf-8")
        self.save([task("a")], decisions=[{"ask": "Forms", "look": "docs/forms.md"},
                                          {"ask": "Odd", "images": ["docs/linked.md", "docs/stream.md", "docs/heavy.md"]}])
        started = time.monotonic()
        content = self.page()
        self.assertLess(time.monotonic() - started, 5)
        cards = content.split('class="decision"')[1:]
        self.assertEqual([card.count('class="thumb"') for card in cards], [4, 0])
        self.assertEqual(board.read_inside(docs / "linked.md", self.root.resolve()), "")

    def test_a_large_folder_keeps_only_the_first_pictures(self):
        folder = self.root / "big"
        folder.mkdir(parents=True)
        for number in range(300):
            (folder / f"{number:04d}.png").write_bytes(b"x")
        self.assertEqual([path.name for path in board.first_pictures(folder)], [f"{n:04d}.png" for n in range(8)])
        with mock.patch.object(board, "FOLDER_ENTRIES", 0):
            self.assertEqual(board.first_pictures(folder), [])

    def gallery(self):
        root = self.root / "docs" / "gallery"
        for folder, names in (("25_ground_sample_G1", ["camp_before_above_after_below.jpg"]),
                              ("31_ground_sample2_G2", ["camp_now_above_sample_below.jpg", "rock_close.jpg"]),
                              ("32_start_branches_G1b", ["branches.jpg"])):
            (root / folder).mkdir(parents=True)
            for name in names:
                (root / folder / name).write_bytes(folder.encode() + name.encode())
        (root / "index.html").write_text(
            "<h2>Ground (G1): sample A became the game's ground</h2>"
            "<figure><img src=\"25_ground_sample_G1/camp_before_above_after_below.jpg\"><figcaption>camp</figcaption></figure>"
            "<h2>Ground sample 2 (G2, waiting) &amp; <b>more</b></h2>"
            "<figure><a href=\"31_ground_sample2_G2/camp_now_above_sample_below.jpg\"><img src=\"31_ground_sample2_G2/camp_now_above_sample_below.jpg\"></a>"
            "<figcaption>Camp: above = now</figcaption></figure>"
            "<figure><img src=\"31_ground_sample2_G2/rock_close.jpg\"><figcaption>위 = 지금, 아래 = 견본 <script>x</script></figcaption></figure>",
            encoding="utf-8")
        return root

    def test_pictures_carry_their_caption_section_and_now_and_draft_labels(self):
        self.gallery()
        self.save([task("a")], lang="ko", decisions=[{"ask": "G2?", "images": ["docs/gallery/31_ground_sample2_G2"]}])
        content = self.page()
        card = content.split('class="decision"')[1]
        self.assertIn("Ground sample 2 (G2, waiting) &amp; more", card)
        self.assertIn("<figcaption>Camp: above = now</figcaption>", card)
        self.assertNotIn("<script>x", content)
        self.assertEqual(card.count('class="thumb rows"'), 2)
        self.assertIn('<span class="tag one">지금</span>', card)
        self.assertIn('<div class="frame">', content)
        self.assertIn("<h2>지금 하는 일</h2>", content)

    def test_why_steps_and_sources_come_first_and_evidence_is_folded(self):
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        self.gallery()
        env = {**os.environ, "GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@a", "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@a"}
        run = lambda *args: subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, env=env)
        run("init", "-q")
        run("add", "docs/gallery/25_ground_sample_G1")
        run("commit", "-q", "-m", "G1 sample")
        run("add", "docs/gallery")
        run("commit", "-q", "-m", "G2 sample")
        self.save([task("a")], lang="ko", decisions=[{
            "ask": "G2?", "images": ["docs/gallery/31_ground_sample2_G2"],
            "why": "문제: 땅이 어색하다는 말\n그래서 <b>세 가지</b>만 넣음", "sources": ["docs/research.md"],
            "history": [{"date": "11-17", "text": "G1을 만듦"}, {"date": "지금", "text": "결정을 기다림"}, "junk"]}])
        card = self.page().split('class="decision"')[1]
        self.assertLess(card.index("왜 이렇게 만들었나"), card.index("지나온 과정"))
        self.assertLess(card.index("지나온 과정"), card.index('class="thumbs"'))
        self.assertIn("<p>그래서 &lt;b&gt;세 가지&lt;/b&gt;만 넣음</p>", card)
        self.assertIn("<code>docs/research.md</code>", card)
        evidence = card[card.index('class="history"'):]
        self.assertNotIn("open>", evidence.split("</summary>")[0])
        self.assertIn("Ground (G1): sample A", evidence)
        self.assertNotIn("branches", evidence)
        self.assertLess(evidence.index("G1 sample"), evidence.index("G2 sample"))
        self.save([task("a")], decisions=[{"ask": "x", "history": [{"date": "1"}]}])
        with self.assertRaises(ValueError):
            board.load(self.path)

    def test_evidence_skips_links_and_later_drafts_and_shares_one_time_budget(self):
        root = self.gallery()
        (root / "35_ground_sample3_G3").mkdir()
        (root / "35_ground_sample3_G3" / "later.jpg").write_bytes(b"later")
        outside = self.root.parent / "elsewhere"
        outside.mkdir()
        (outside / "secret.jpg").write_bytes(b"secret")
        (root / "20_ground_old_G0").symlink_to(outside, target_is_directory=True)
        found = board.family(root / "31_ground_sample2_G2", self.root.resolve())
        self.assertEqual([path.name for path in found], ["25_ground_sample_G1", "31_ground_sample2_G2"])
        with mock.patch.object(board, "EVIDENCE_SECONDS", 0):
            evidence = board.evidence_for({"pictures": [{"name": "docs/gallery/31_ground_sample2_G2/rock_close.jpg"}]},
                                          self.root.resolve(), time.monotonic())
        self.assertEqual(evidence["commits"], [])

    def test_captions_come_from_the_named_page_and_nothing_is_cut_silently(self):
        page = self.root / "docs" / "review.html"
        (self.root / "docs" / "art").mkdir(parents=True)
        for name in ("p.png", "q.png", "r.png"):
            (self.root / "docs" / "art" / name).write_bytes(name.encode())
        page.write_text("<h2>First</h2><figure><img src=\"art/p.png\"><figcaption>cap p</figcaption></figure>"
                        "<h2>Second</h2><figure><img src=\"art/q.png\"></figure><h2>Third</h2><figure><img src=\"art/r.png\"></figure>",
                        encoding="utf-8")
        sources = [f"docs/s{n}.md" for n in range(7)]
        self.save([task("a")], decisions=[{"ask": "x", "images": ["docs/review.html"], "sources": sources}])
        card = self.page().split('class="decision"')[1]
        self.assertIn("<figcaption>cap p</figcaption>", card)
        for heading in ("First", "Second", "Third"):
            self.assertIn(heading, card)
        self.assertIn("docs/s6.md", card)
        self.assertIn("b.closest('.thumbs') || b.closest('ol')", self.page())
        self.save([task("a")], decisions=[{"ask": "x", "sources": [f"s{n}" for n in range(21)]}])
        with self.assertRaises(ValueError):
            board.load(self.path)

    def test_a_picture_swapped_for_a_link_after_the_check_is_not_copied(self):
        inside = self.root / "a.png"
        self.root.mkdir(parents=True, exist_ok=True)
        inside.write_bytes(b"inside")
        outside = self.root.parent / "secret.png"
        outside.write_bytes(b"secret")
        swapped = self.root / "b.png"
        swapped.symlink_to(outside)
        with self.assertRaises(OSError):
            board.copy_inside(swapped, self.root.resolve(), self.home / "assets" / "x.png")
        board.copy_inside(inside, self.root.resolve(), self.home / "assets" / "y.png")
        self.assertEqual((self.home / "assets" / "y.png").read_bytes(), b"inside")
        self.assertFalse((self.home / "assets" / "x.png").exists())

    def test_overview_links_the_registry_page_when_it_exists(self):
        self.save([task("a")])
        self.page()
        self.assertNotIn("registry.html", (self.home / "index.html").read_text(encoding="utf-8"))
        (self.home / "registry.html").write_text("x", encoding="utf-8")
        self.page()
        self.assertIn('href="registry.html"', (self.home / "index.html").read_text(encoding="utf-8"))

    def test_korean_labels_and_unknown_language_falls_back(self):
        self.save([task("a", "done")], lang="ko")
        self.assertIn("전체 진행률", self.page())
        self.save([task("a", "done")], lang=["ko"])
        self.assertIn("Progress", self.page())

    def test_overview_lists_boards_and_drops_removed_ones(self):
        self.save([task("a", "done"), task("b")])
        board.publish(self.path)
        other = self.root.parent / "other"
        (other / ".harness").mkdir(parents=True)
        second = other / ".harness" / "board.json"
        second.write_text(json.dumps({"title": "Second", "tasks": [task("x")]}), encoding="utf-8")
        board.publish(second)
        listing = (self.home / "index.html").read_text(encoding="utf-8")
        self.assertIn("Demo", listing)
        self.assertIn("Second", listing)
        second.unlink()
        board.publish(self.path)
        self.assertNotIn("Second", (self.home / "index.html").read_text(encoding="utf-8"))

    def test_overview_ignores_summaries_it_did_not_write(self):
        self.save([task("a")])
        board.publish(self.path)
        good = json.loads(next(self.home.glob("app-*.json")).read_text(encoding="utf-8"))
        for number, change in enumerate(({"page": "javascript:alert(1)"}, {"percent": "<img src=x>"}, {"title": None},
                                         {"page": "../x.html"})):
            (self.home / f"foreign{number}.json").write_text(json.dumps({**good, "title": "Foreign", **change}),
                                                             encoding="utf-8")
        (self.home / "broken.json").write_text("{", encoding="utf-8")
        board.publish(self.path)
        listing = (self.home / "index.html").read_text(encoding="utf-8")
        self.assertIn("Demo", listing)
        self.assertNotIn("Foreign", listing)
        self.assertNotIn("javascript:", listing)
        self.assertNotIn("<img", listing)

    def test_invalid_boards_are_rejected(self):
        cases = [[], [task("a"), task("a")], [task("a", "finished")], [task("a", after=["missing"])],
                 [{"id": "a", "status": "todo"}], [task("bad id")]]
        for tasks in cases:
            self.save(tasks)
            with self.assertRaises(ValueError):
                board.publish(self.path)

    def test_command_reports_invalid_input_with_exit_2(self):
        for content in (json.dumps({"tasks": [task("a", "finished")]}), "{", "[" * 100000, json.dumps({"tasks": [{"id": ["a"]}]})):
            self.path.write_text(content, encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "render", str(self.path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr[-300:])
            self.assertIn("INVALID", result.stderr)

    def test_out_writes_one_page_and_no_overview(self):
        self.save([task("a")])
        target = self.root.parent / "page.html"
        board.publish(self.path, out=target)
        self.assertTrue(target.is_file())
        self.assertFalse(self.home.exists())

    def test_relative_page_folder_is_ignored(self):
        self.assertTrue(board.home().is_absolute())
        with mock.patch.dict(os.environ, {"HARNESS_BOARD_HOME": "pages"}):
            self.assertTrue(board.home().is_absolute())
            self.assertNotEqual(board.home().name, "pages")


class HookTests(Case):
    def event(self, name, **extra):
        return {"hook_event_name": name, "cwd": str(self.root), "session_id": "s1", **extra}

    def pages(self):
        return list(self.home.glob("app-*.html")) if self.home.exists() else []

    def test_no_board_means_no_output_and_no_files(self):
        self.assertIsNone(board.hook(self.event("SessionStart")))
        self.assertFalse(self.home.exists())

    def test_session_start_renders_and_tells_the_agent(self):
        self.save([task("a")])
        result = board.hook(self.event("SessionStart"))
        self.assertIn("board.json", result["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(len(self.pages()), 1)

    def test_edit_of_the_board_renders_and_other_edits_do_not(self):
        self.save([task("a")])
        board.hook(self.event("PostToolUse", tool_name="Edit", tool_input={"file_path": "README.md"}))
        self.assertEqual(self.pages(), [])
        board.hook(self.event("PostToolUse", tool_name="Edit", tool_input={"file_path": ".harness/board.json"}))
        self.assertEqual(len(self.pages()), 1)
        self.save([task("a", "done")])
        board.hook(self.event("PostToolUse", tool_name="Write", tool_input={"file_path": str(self.path)}))
        self.assertIn(">100%<", self.pages()[0].read_text(encoding="utf-8"))

    def test_relative_paths_are_read_from_the_working_directory(self):
        self.save([task("a")])
        sub = self.root / "sub"
        (sub / ".harness").mkdir(parents=True)
        (sub / ".harness" / "board.json").write_text("{}", encoding="utf-8")
        board.hook(self.event("PostToolUse", cwd=str(sub), tool_input={"file_path": ".harness/board.json"}))
        self.assertEqual(self.pages(), [])
        board.hook(self.event("PostToolUse", cwd=str(sub), tool_input={"file_path": "../.harness/board.json"}))
        self.assertEqual(len(self.pages()), 1)

    def test_root_is_found_from_a_subfolder_without_the_project_variable(self):
        self.save([task("a")])
        sub = self.root / "src" / "deep"
        sub.mkdir(parents=True)
        with mock.patch.dict(os.environ):
            del os.environ["CLAUDE_PROJECT_DIR"]
            board.hook(self.event("Stop", cwd=str(sub)))
        self.assertEqual(len(self.pages()), 1)

    @unittest.skipIf(os.name == "nt", "needs symlinks")
    def test_linked_board_folder_still_matches(self):
        real = self.root.parent / "state"
        self.save([task("a")])
        (self.root / ".harness").rename(real)
        os.symlink(real, self.root / ".harness")
        board.hook(self.event("PostToolUse", tool_input={"file_path": str(real / "board.json")}))
        self.assertEqual(len(self.pages()), 1)

    def test_page_opens_on_the_first_render_and_when_a_task_starts_not_per_session(self):
        self.save([task("a"), task("b")])
        with mock.patch.object(board, "launch") as launch:
            board.hook(self.event("SessionStart"))
            self.assertEqual(launch.call_count, 1)
            for session in ("s2", "s1", "s3"):
                board.hook(self.event("SessionStart", session_id=session))
                board.hook(self.event("Stop", session_id=session))
            self.assertEqual(launch.call_count, 1)
            self.save([task("a", "doing"), task("b")])
            board.hook(self.event("PostToolUse", tool_input={"file_path": str(self.path)}))
            self.assertEqual(launch.call_count, 2)
            board.hook(self.event("SessionStart", session_id="s4"))
            self.assertEqual(launch.call_count, 2)
            self.save([task("a", "done"), task("b")])
            board.hook(self.event("Stop"))
            self.save([task("a", "done"), task("b", "doing")])
            board.hook(self.event("Stop"))
            self.assertEqual(launch.call_count, 3)

    def test_an_old_session_list_marker_does_not_open_the_page_again(self):
        self.save([task("a", "doing")])
        (self.home).mkdir(parents=True, exist_ok=True)
        (self.home / f"{board.slug(self.root.resolve())}.opened").write_text("s1\ns2", encoding="utf-8")
        with mock.patch.object(board, "launch") as launch:
            board.hook(self.event("SessionStart", session_id="s9"))
            self.assertEqual(launch.call_count, 0)
            self.save([task("a", "doing"), task("b", "doing")])
            board.hook(self.event("Stop"))
            self.assertEqual(launch.call_count, 1)
        (self.home / f"{board.slug(self.root.resolve())}.opened").write_text("{", encoding="utf-8")
        with mock.patch.object(board, "launch") as launch:
            board.hook(self.event("Stop"))
            self.save([task("a", "doing"), task("b", "doing"), task("c", "doing")])
            board.hook(self.event("Stop"))
            self.assertEqual(launch.call_count, 1)

    def test_broken_board_reports_and_does_not_raise(self):
        for content in ("{", json.dumps({"tasks": [{"id": ["a"]}]}), "[" * 100000):
            self.path.write_text(content, encoding="utf-8")
            result = board.hook(self.event("Stop"))
            self.assertIn("was not rendered", result["systemMessage"])

    def test_hook_command_never_fails(self):
        payloads = ["", "[]", "{", json.dumps(self.event("Unknown"))]
        for payload in payloads:
            result = subprocess.run([sys.executable, str(SCRIPT), "hook"], input=payload, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
        self.path.write_text("{", encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPT), "hook"], input=json.dumps(self.event("Stop")),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("was not rendered", json.loads(result.stdout)["systemMessage"])

    def test_browser_is_detached_and_can_be_switched_off(self):
        with mock.patch.object(board.subprocess, "Popen") as popen, mock.patch.object(board.sys, "platform", "darwin"):
            board.launch(self.path)
            self.assertEqual(popen.call_count, 0)
            with mock.patch.dict(os.environ, {"HARNESS_BOARD_OPEN": "1"}):
                board.launch(self.path)
            self.assertEqual(popen.call_count, 1)
            options = popen.call_args.kwargs
            self.assertEqual(options["stdout"], subprocess.DEVNULL)
            self.assertEqual(options["stderr"], subprocess.DEVNULL)
            popen.side_effect = OSError("no opener")
            with mock.patch.dict(os.environ, {"HARNESS_BOARD_OPEN": "1"}):
                board.launch(self.path)


if __name__ == "__main__":
    unittest.main()
