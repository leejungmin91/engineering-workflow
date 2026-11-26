import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import artifacts

OLD = time.time() - 5 * 86400


class ArtifactsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.project = self.root / "app"
        self.archive = self.root / "ssd"
        self.archive.mkdir()
        self.harness = self.project / ".harness"
        self.harness.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        busy = mock.patch.object(artifacts, "busy", return_value=False)
        self.busy = busy.start()
        self.addCleanup(busy.stop)

    def folder(self, name, when=OLD, files=None):
        path = self.harness / name
        (path / "sub").mkdir(parents=True)
        for relative, data in (files or {"a.png": b"picture", "sub/log.txt": b"log"}).items():
            (path / relative).write_bytes(data)
        for current in [path, *path.rglob("*")]:
            os.utime(current, (when, when), follow_symlinks=False)
        return path

    def run_main(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = artifacts.main(list(argv))
        return code, json.loads(out.getvalue())

    def test_old_skips_recent_mentioned_tracked_links_and_other_names(self):
        self.folder("done_checks")
        recent = self.folder("fresh_checks")
        os.utime(recent / "sub" / "log.txt")
        self.folder("named_checks")
        (self.project / "WORKING.md").write_text("see .harness/named_checks/a.png\n")
        self.folder("kept_checks")
        subprocess.run(["git", "-C", str(self.project), "add", ".harness/kept_checks"], check=True)
        self.folder("notes")
        (self.harness / "linked_checks").symlink_to(self.root)
        found = [path.name for path in artifacts.old(self.project, ".harness", artifacts.GLOBS, 2, time.time())]
        self.assertEqual(found, ["done_checks"])

    def test_archive_moves_leaves_link_and_keeps_contents(self):
        self.folder("done_checks")
        code, rows = self.run_main("archive", str(self.project), "--to", str(self.archive))
        self.assertEqual(code, 0)
        self.assertEqual(rows[0]["status"], "moved")
        link = self.harness / "done_checks"
        target = self.archive / "app" / ".harness" / "done_checks"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), target.resolve())
        self.assertEqual((link / "sub" / "log.txt").read_bytes(), b"log")
        self.assertFalse((self.harness / "done_checks.moving").exists())

    def test_dry_run_moves_nothing(self):
        self.folder("done_checks")
        code, rows = self.run_main("archive", str(self.project), "--to", str(self.archive), "--dry-run")
        self.assertEqual((code, rows[0]["status"]), (0, "would move"))
        self.assertFalse((self.harness / "done_checks").is_symlink())
        self.assertEqual(list(self.archive.iterdir()), [])

    def test_folder_in_use_or_target_present_is_left_alone(self):
        self.folder("done_checks")
        self.busy.return_value = True
        code, rows = self.run_main("archive", str(self.project), "--to", str(self.archive))
        self.assertEqual((code, rows[0]["status"]), (1, "in use"))
        self.assertFalse((self.harness / "done_checks").is_symlink())
        self.busy.return_value = False
        (self.archive / "app" / ".harness" / "done_checks").mkdir(parents=True)
        code, rows = self.run_main("archive", str(self.project), "--to", str(self.archive))
        self.assertEqual((code, rows[0]["status"]), (1, "target exists"))
        self.assertEqual((self.harness / "done_checks" / "a.png").read_bytes(), b"picture")

    def test_copy_that_differs_leaves_the_folder_in_place(self):
        self.folder("done_checks")
        with mock.patch.object(artifacts, "same", return_value=False):
            code, rows = self.run_main("archive", str(self.project), "--to", str(self.archive))
        self.assertEqual((code, rows[0]["status"]), (1, "changed during copy; left in place"))
        self.assertFalse((self.harness / "done_checks").is_symlink())
        self.assertEqual((self.harness / "done_checks" / "a.png").read_bytes(), b"picture")
        self.assertFalse((self.archive / "app" / ".harness" / "done_checks").exists())

    def test_file_written_during_the_copy_stops_the_move(self):
        self.folder("done_checks")
        real = artifacts.shutil.copytree

        def copy(source, target, *rest, **options):
            result = real(source, target, *rest, **options)
            (Path(source) / "late.txt").write_bytes(b"late")
            return result

        with mock.patch.object(artifacts.shutil, "copytree", side_effect=copy):
            code, rows = self.run_main("archive", str(self.project), "--to", str(self.archive))
        self.assertEqual((code, rows[0]["status"]), (1, "changed during copy; left in place"))
        self.assertEqual((self.harness / "done_checks" / "late.txt").read_bytes(), b"late")
        self.assertFalse((self.harness / "done_checks").is_symlink())

    def test_write_into_the_original_after_the_switch_keeps_it(self):
        self.folder("done_checks")
        real = artifacts.os.symlink

        def link(aim, where):
            spare = Path(str(where) + ".moving")
            (spare / "a.png").write_bytes(b"held open")
            return real(aim, where)

        with mock.patch.object(artifacts.os, "symlink", side_effect=link):
            code, rows = self.run_main("archive", str(self.project), "--to", str(self.archive))
        self.assertEqual(code, 1)
        self.assertIn("original kept", rows[0]["status"])
        self.assertEqual((self.harness / "done_checks.moving" / "a.png").read_bytes(), b"held open")

    def test_update_through_the_link_is_kept(self):
        self.folder("done_checks")
        real = artifacts.os.symlink

        def link(aim, where):
            result = real(aim, where)
            (Path(where) / "a.png").write_bytes(b"newer picture")
            return result

        with mock.patch.object(artifacts.os, "symlink", side_effect=link):
            code, rows = self.run_main("archive", str(self.project), "--to", str(self.archive))
        self.assertEqual((code, rows[0]["status"]), (0, "moved"))
        self.assertEqual((self.archive / "app" / ".harness" / "done_checks" / "a.png").read_bytes(), b"newer picture")
        self.assertFalse((self.harness / "done_checks.moving").exists())

    def test_relative_link_out_of_the_folder_is_not_moved(self):
        path = self.folder("done_checks")
        (path / "input").symlink_to("../../fixtures/data.json")
        os.utime(path / "input", (OLD, OLD), follow_symlinks=False)
        os.utime(path, (OLD, OLD))
        code, rows = self.run_main("archive", str(self.project), "--to", str(self.archive))
        self.assertEqual((code, rows[0]["status"]), (1, "has relative links that point outside the folder"))
        self.assertFalse((self.harness / "done_checks").is_symlink())

    def test_folder_with_links_inside_is_archived(self):
        path = self.folder("done_checks")
        (path / "latest").symlink_to("sub")
        (path / "out.png").symlink_to("a.png")
        for current in (path, path / "latest", path / "out.png"):
            os.utime(current, (OLD, OLD), follow_symlinks=False)
        code, rows = self.run_main("archive", str(self.project), "--to", str(self.archive))
        self.assertEqual((code, rows[0]["status"]), (0, "moved"))
        target = self.archive / "app" / ".harness" / "done_checks"
        self.assertEqual(os.readlink(target / "latest"), "sub")
        self.assertEqual((target / "out.png").read_bytes(), b"picture")
        self.assertFalse((self.harness / "done_checks.moving").exists())

    def test_link_through_a_sibling_is_not_moved(self):
        path = self.folder("done_checks")
        (self.harness / "alias").symlink_to("done_checks")
        (path / "input").symlink_to("../alias/a.png")
        os.utime(path / "input", (OLD, OLD), follow_symlinks=False)
        os.utime(path, (OLD, OLD))
        code, rows = self.run_main("archive", str(self.project), "--to", str(self.archive))
        self.assertEqual((code, rows[0]["status"]), (1, "has relative links that point outside the folder"))

    def test_failed_link_puts_the_folder_back(self):
        self.folder("done_checks")
        with mock.patch.object(artifacts.os, "symlink", side_effect=OSError("no inodes")):
            code, rows = self.run_main("archive", str(self.project), "--to", str(self.archive))
        self.assertEqual(code, 1)
        self.assertIn("could not link", rows[0]["status"])
        self.assertEqual((self.harness / "done_checks" / "a.png").read_bytes(), b"picture")
        self.assertFalse((self.harness / "done_checks.moving").exists())
        self.assertFalse((self.archive / "app" / ".harness" / "done_checks").exists())

    def test_same_sees_a_changed_byte(self):
        one = self.folder("one_checks", files={"a.bin": b"abc"})
        two = self.folder("two_checks", files={"a.bin": b"abd"})
        self.assertFalse(artifacts.same(one, two))
        (two / "a.bin").write_bytes(b"abc")
        self.assertTrue(artifacts.same(one, two))

    def test_missing_archive_disk_stops(self):
        self.folder("done_checks")
        code = artifacts.main(["archive", str(self.project), "--to", str(self.root / "unplugged")])
        self.assertEqual(code, 2)
        self.assertFalse((self.harness / "done_checks").is_symlink())

    def test_space_fails_below_the_floor(self):
        code, row = self.run_main("space", str(self.root), "--min-gb", "100000000")
        self.assertEqual(code, 1)
        self.assertGreater(row["free_gb"], 0)
        self.assertEqual(self.run_main("space", str(self.root), "--min-gb", "0")[0], 0)


if __name__ == "__main__":
    unittest.main()
