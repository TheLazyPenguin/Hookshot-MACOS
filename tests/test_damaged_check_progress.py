"""The damaged-texture check after an unpack says how far it is: nup.damaged_game_files reports each file it opened, and
make_game's file_progress turns that into the builder's @@progress (at most 4 a second, and the last) and a plain line at each
tenth. Without them the build showed "reading it again is skipped" and then nothing for minutes. Game-free."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
sys.path.insert(0, str(ROOT / "third_party/a64-kit/tools"))
import nup  # noqa: E402

spec = importlib.util.spec_from_file_location("make_game_damaged_progress", ROOT / "nx2/make_game.py")
make_game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_game)


class DamagedFilesProgressTests(unittest.TestCase):
    def test_each_file_reported_and_the_damaged_one_found(self):
        with tempfile.TemporaryDirectory(prefix="hookshot-damaged-") as romfs:
            os.makedirs(os.path.join(romfs, "Model"))
            for name in ("a.bfres.zs", "c.bfres.zs"):
                with open(os.path.join(romfs, "Model", name), "wb") as f:
                    f.write(nup.ZSTD + b"rest")
            damaged = os.path.join(romfs, "Model", "b.bfres.zs")
            with open(damaged, "wb") as f:
                f.write(b"\0" * 8)
            with open(os.path.join(romfs, "Model", "not_zs.txt"), "wb") as f:
                f.write(b"\0" * 8)
            calls = []
            self.assertEqual(nup.damaged_game_files(romfs, lambda done, total: calls.append((done, total))), [damaged])
            self.assertEqual(calls, [(1, 3), (2, 3), (3, 3)])
            self.assertEqual(nup.damaged_game_files(romfs), [damaged])   # (no progress: as before)

    def test_file_progress_lines(self):
        t = [0.0]
        def clock():
            return t[0]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            progress = make_game.file_progress("checked", clock)
            for done in range(1, 101):
                t[0] = done / 10   # (10 files a second: every third or so may send @@progress)
                progress(done, 100)
        lines = out.getvalue().splitlines()
        bars = [line for line in lines if line.startswith("@@progress ")]
        said = [line for line in lines if not line.startswith("@@")]
        self.assertEqual(bars[-1], "@@progress 1.000")
        self.assertLessEqual(len(bars), 10 * 4 + 2)   # (10 s of checking: at most 4 a second, the first and the last)
        self.assertGreater(len(bars), 5)
        self.assertEqual([float(b.split()[1]) for b in bars], sorted(float(b.split()[1]) for b in bars))
        self.assertEqual(len(said), 10)
        self.assertEqual(said[3], "checked 40 of 100 files (40%, 4 s)")
        self.assertEqual(said[-1], "checked 100 of 100 files (100%, 10 s)")

    def test_file_progress_large_numbers_and_no_files(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            make_game.file_progress("checked", lambda: 0.0)(102185, 102185)
            make_game.file_progress("checked", lambda: 0.0)(0, 0)
        self.assertIn("checked 102,185 of 102,185 files (100%, 0 s)", out.getvalue().splitlines())
        self.assertEqual(out.getvalue().count("@@progress 1.000"), 2)

    def test_the_check_is_announced_and_reports(self):
        source = (ROOT / "nx2/make_game.py").read_text(encoding="utf-8")
        body = source[source.index("def stand_in_damaged_files("):]
        body = body[:body.index("\ndef ")]
        self.assertIn("checking your game files for damaged textures", body)
        self.assertIn('nup.stand_in_damaged(romfs, file_progress("checked"))', body)


if __name__ == "__main__":
    unittest.main()
