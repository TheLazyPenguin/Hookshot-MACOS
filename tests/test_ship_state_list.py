"""The pipeline state list a release ships (assets/pipeline_states.bin.xz): the repository's copy reads, and every release path
carries it. v2.0.8 to v2.0.14 shipped none (their app parts' tools/work and the Linux tools part's work/ held only the play
profile), and a new install's first field load was drawn white for seconds while its pipelines compiled in play.

  - the committed list is an xz file of a whole list of this build's format, and holds pipelines;
  - scripts/linux/appimage.sh carries assets/ and stops without the list;
  - scripts/release_parts.py package puts it in the Windows builder's tools/assets, where nx2/make_game.py looks for it,
    and stops when it is missing, damaged or of another format.

Game-free: the list holds shader hashes and draw state, and the rest is synthetic.
    python -I -B tests/test_ship_state_list.py
"""
import argparse
import importlib.util
import lzma
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ShippedList(unittest.TestCase):
    def setUp(self):
        self.tool = load("pipeline_states", ROOT / "nx2" / "pipeline_states.py")
        self.list = ROOT.joinpath(*self.tool.SHIPPED)
        self.tmp = Path(tempfile.mkdtemp(prefix="hookshot-ship-states-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_list(self, n, magic=None):
        return lzma.compress((magic or self.tool.MAGIC) + struct.pack("<I", self.tool.SIZE) + b"".join(
            struct.pack("<Q", i + 1) + bytes(self.tool.SIZE - 8) for i in range(n)))

    def test_committed_list_reads(self):
        self.assertTrue(self.list.is_file(), "assets/pipeline_states.bin.xz is not in the repository")
        self.assertEqual(self.list.read_bytes()[:6], self.tool.XZ_MAGIC, "the shipped list is not xz-compressed")
        recs = self.tool.check_shipped(str(self.list))
        self.assertGreater(len(recs), 0)
        # (the game reads the list unpacked: what make_game writes beside it)
        self.assertEqual(lzma.decompress(self.list.read_bytes())[:8], self.tool.MAGIC)

    @unittest.skipUnless(sys.platform.startswith("linux"), "the AppImage is made on Linux")
    def test_appimage_carries_it(self):
        script = (ROOT / "scripts/linux/appimage.sh").read_text(encoding="utf-8")
        self.assertRegex(script, r"\ncp -a [^\n]*\bassets\b[^\n]*\"\$T/\"\n", "the AppImage no longer carries assets/")
        start = script.index("# (the pipeline state list, assets/pipeline_states.bin.xz")
        end = script.index("\n", script.index("assets/pipeline_states.bin.xz is missing", start)) + 1
        block = script[start:end]

        def run(with_list):
            out = self.tmp / ("tree-%d" % with_list)
            (out / "assets").mkdir(parents=True)
            if with_list:
                shutil.copy(self.list, out / "assets")
            return subprocess.run(["bash", "-eu", "-o", "pipefail", "-c", block], cwd=self.tmp, env=dict(os.environ, T=str(out)),
                                  capture_output=True, text=True)

        r = run(True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(False)
        self.assertNotEqual(r.returncode, 0, "appimage.sh went on without assets/pipeline_states.bin.xz")
        self.assertIn("assets/pipeline_states.bin.xz is missing", r.stdout + r.stderr)

    def release_parts(self, data):
        """release_parts.py with its ROOT a small checkout: nx2/pipeline_states.py and, when data, the shipped list"""
        root = self.tmp / "repo"
        (root / "nx2").mkdir(parents=True)
        (root / "assets").mkdir()
        shutil.copy(ROOT / "nx2" / "pipeline_states.py", root / "nx2")
        (root / "LICENSE").write_text("license")
        if data is not None:
            root.joinpath(*self.tool.SHIPPED).write_bytes(data)
        rp = load("release_parts_under_test", ROOT / "scripts" / "release_parts.py")
        rp.ROOT = str(root)
        rp.tracked = lambda *paths: []   # (git ls-files: none of the sources are needed here)
        return rp, root

    def package(self, rp):
        publish = self.tmp / "publish"
        publish.mkdir(exist_ok=True)
        (publish / "HookshotBuilder.exe").write_bytes(b"MZ")
        setup = self.tmp / "setup.exe"
        setup.write_bytes(b"MZ")
        out = self.tmp / "package"
        a = argparse.Namespace(out=str(out), publish=str(publish), setup=str(setup), list=None, python_packages=None)
        return rp.package(a), out

    def test_windows_package_carries_it(self):
        rp, root = self.release_parts(self.fake_list(3))
        rc, out = self.package(rp)
        self.assertEqual(rc, 0)
        shipped = out.joinpath("tools", *self.tool.SHIPPED)
        self.assertEqual(shipped.read_bytes(), root.joinpath(*self.tool.SHIPPED).read_bytes())
        # (make_game, run from tools/ as the builder runs it, unpacks it beside the game)
        make_game = load("make_game_under_test", ROOT / "nx2" / "make_game.py")
        make_game.ROOT = str(out / "tools")
        game = self.tmp / "game"
        game.mkdir()
        make_game.ship_state_list(str(game))
        self.assertEqual(len(self.tool.read(str(game / "hookshot_pipeline_states_shipped.bin"))), 3)

    def test_windows_package_stops_without_it(self):
        damaged = self.fake_list(3)
        damaged = damaged[:40] + bytes(16) + damaged[56:]
        for why, data in (("missing", None), ("empty", self.fake_list(0)), ("damaged", damaged),
                          ("of another format", self.fake_list(3, magic=b"HKSTATE9"))):
            with self.subTest(why):
                shutil.rmtree(self.tmp / "repo", ignore_errors=True)
                rp, _ = self.release_parts(data)
                rc, _ = self.package(rp)
                self.assertEqual(rc, 1, "the package was made with a list that is %s" % why)


if __name__ == "__main__":
    unittest.main()
