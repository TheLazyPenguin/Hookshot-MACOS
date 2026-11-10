"""Game-free: the extraction notes which romfs .zs files do not start as zstd as it writes them, and the build's damaged-
texture step takes that list instead of opening every file again (#1876: ~100,000 opens, minutes under a virus scanner,
and the Builder looked frozen):
python -I -B nx2/test_nup_zstd_heads.py"""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nup

SOURCE = Path(__file__).resolve().parent / "make_game.py"
spec = importlib.util.spec_from_file_location("make_game_heads_under_test", SOURCE)
make_game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_game)

WHOLE = nup.ZSTD + b"authored whole member"
DAMAGED = b"\x00\x00\x00\x00authored damaged member"
MEMBERS = {
    "exefs": {"main": b"NSO0authored"},
    "romfs": {"Model/whole.bntx.zs": WHOLE, "Model/damaged.bntx.zs": DAMAGED, "Model/other.bntx.zs": WHOLE,
              "Data/plain.txt": b"\x00not a zs file"},
}


class Package:
    """Authored members written in two pieces, as a package reader may"""
    def walk(self, part):
        for rel, data in MEMBERS[part].items():
            yield rel, (part, rel, len(data), 0, len(data), 0)

    def copy_to(self, record, output, name):
        data = MEMBERS[record[0]][record[1]]
        output.write(data[:2])
        output.write(memoryview(data)[2:])


class Heads(unittest.TestCase):
    def extract(self, out):
        return nup.extract(Package(), {"exefs": "exefs", "romfs": "romfs"}, out, quiet=True)

    def test_the_extraction_lists_the_damaged_zs_files(self):
        with tempfile.TemporaryDirectory() as out:
            self.extract(out)
            self.assertEqual(nup.read_heads(os.path.join(out, nup.HEADS_NAME)), ["Model/damaged.bntx.zs"])
            self.assertEqual(Path(out, "romfs", "Model", "damaged.bntx.zs").read_bytes(), DAMAGED)

    def test_a_rerun_opens_only_the_files_it_kept(self):
        with tempfile.TemporaryDirectory() as out:
            self.extract(out)
            os.remove(os.path.join(out, nup.HEADS_NAME))
            self.extract(out)   # (every member is there already: each .zs is opened for its head)
            self.assertEqual(nup.read_heads(os.path.join(out, nup.HEADS_NAME)), ["Model/damaged.bntx.zs"])

    def test_no_list_without_the_whole_romfs(self):
        with tempfile.TemporaryDirectory() as out:
            nup.extract(Package(), {"exefs": "exefs", "romfs": "romfs"}, out, only="exefs", quiet=True)
            self.assertIsNone(nup.read_heads(os.path.join(out, nup.HEADS_NAME)))

    def test_the_build_takes_the_list_and_opens_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            out, game = os.path.join(d, "authored game"), os.path.join(d, "authored game", ".game")
            os.makedirs(game)
            self.extract(game)
            romfs = os.path.join(out, "romfs")
            os.replace(os.path.join(game, "romfs"), romfs)
            stamp = "unpacked by this builder: authored.nup 123"
            Path(out, ".hookshot_romfs").write_text(stamp + "\n")
            make_game.keep_heads(out, game, stamp)
            with mock.patch.object(nup, "damaged_game_files", side_effect=AssertionError("every file opened again")):
                make_game.stand_in_damaged_files(out, romfs)
            # (the damaged file now holds its stand-in: a whole one of the same kind)
            self.assertEqual(Path(romfs, "Model", "damaged.bntx.zs").read_bytes(), WHOLE)
            self.assertFalse(os.path.exists(os.path.join(out, make_game.HEADS)))
            self.assertEqual(Path(out, ".hookshot_romfs_checked").read_text(), stamp + "\n")

    def test_a_list_from_another_unpack_is_not_taken(self):
        with tempfile.TemporaryDirectory() as d:
            out, game = os.path.join(d, "authored game"), os.path.join(d, "authored game", ".game")
            os.makedirs(game)
            self.extract(game)
            romfs = os.path.join(out, "romfs")
            os.replace(os.path.join(game, "romfs"), romfs)
            make_game.keep_heads(out, game, "unpacked by this builder: an older.nup 1")
            Path(out, ".hookshot_romfs").write_text("unpacked by this builder: authored.nup 123\n")
            with mock.patch.object(nup, "damaged_game_files", wraps=nup.damaged_game_files) as opened:
                make_game.stand_in_damaged_files(out, romfs)
            opened.assert_called_once()
            self.assertEqual(Path(romfs, "Model", "damaged.bntx.zs").read_bytes(), WHOLE)


if __name__ == "__main__":
    unittest.main()
