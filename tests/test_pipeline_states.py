"""The pipeline state list: the back end's record (gpu/vk/vk_draw.cpp StateRec) and the tools that merge and ship the lists agree.

A list made by one build is read by another (that is its point): its record size and magic are a file format. nx2/pipeline_states.py
merges lists into assets/pipeline_states.bin.xz, each pipeline once, and nx2/make_game.py unpacks that beside the game. Synthetic data only.
python -I -B tests/test_pipeline_states.py
"""
import importlib.util
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    tool = load("pipeline_states", ROOT / "nx2" / "pipeline_states.py")
    draw = (ROOT / "gpu" / "vk" / "vk_draw.cpp").read_text(encoding="utf-8")
    m = re.search(r"static_assert\(sizeof\(StateRec\) == (\d+)", draw)
    if not m or int(m.group(1)) != tool.SIZE:
        raise SystemExit("the back end's StateRec (%s bytes) and nx2/pipeline_states.py (%d) differ" % (m and m.group(1), tool.SIZE))
    magic = re.search(r"kStateMagic\[8\] = \{([^}]*)\}", draw).group(1)
    if "".join(re.findall(r"'(.)'", magic)).encode() != tool.MAGIC:
        raise SystemExit("the back end's magic and the tool's differ")
    if "hookshot_pipeline_states_shipped.bin" not in draw:
        raise SystemExit("the back end does not read the shipped list")

    def rec(vs, fs, topo):
        r = bytearray(tool.SIZE)
        struct.pack_into("<QQ", r, 0, vs, fs)
        struct.pack_into("<I", r, 44, topo)
        return bytes(r)

    with tempfile.TemporaryDirectory() as d:
        a, b, out = (os.path.join(d, n) for n in ("a.bin", "b.bin", "out.bin"))
        head = tool.MAGIC + struct.pack("<I", tool.SIZE)
        open(a, "wb").write(head + rec(1, 2, 3) + rec(1, 2, 4))
        open(b, "wb").write(head + rec(1, 2, 4) + rec(5, 0, 3))
        ran = subprocess.run([sys.executable, "-I", str(ROOT / "nx2" / "pipeline_states.py"), "--out", out, a, b],
                             capture_output=True, text=True)
        if ran.returncode:
            raise SystemExit(ran.stderr)
        merged = tool.read(out)
        if merged != [rec(1, 2, 3), rec(1, 2, 4), rec(5, 0, 3)]:
            raise SystemExit("merge: %d records, expected the 3 different ones in order" % len(merged))
        # an .xz --out is compressed and reads back the same
        xz = os.path.join(d, "out.bin.xz")
        ran = subprocess.run([sys.executable, "-I", str(ROOT / "nx2" / "pipeline_states.py"), "--out", xz, out],
                             capture_output=True, text=True)
        if ran.returncode or open(xz, "rb").read(6) != tool.XZ_MAGIC or tool.read(xz) != merged:
            raise SystemExit("--out .xz: not an xz file of the same records\n" + ran.stderr)
        # make_game: assets/pipeline_states.bin.xz unpacked beside the game as hookshot_pipeline_states_shipped.bin, none
        # when there is none
        make_game = load("make_game_under_test", ROOT / "nx2" / "make_game.py")
        game = os.path.join(d, "game")
        os.makedirs(game)
        make_game.ROOT = d
        make_game.ship_state_list(game)
        if os.listdir(game):
            raise SystemExit("a list was shipped with none in assets/")
        os.makedirs(os.path.join(d, "assets"))
        os.replace(xz, os.path.join(d, *tool.SHIPPED))
        make_game.ship_state_list(game)
        shipped = os.path.join(game, "hookshot_pipeline_states_shipped.bin")
        if open(shipped, "rb").read(8) != tool.MAGIC or tool.read(shipped) != merged:
            raise SystemExit("make_game did not unpack assets/pipeline_states.bin.xz beside the game")
        # one that does not read (another format, damaged) is left out, and the build goes on
        os.remove(shipped)
        with open(os.path.join(d, *tool.SHIPPED), "wb") as f:
            f.write(b"HKSTATE9" + struct.pack("<I", 600))
        make_game.ship_state_list(game)
        if os.listdir(game):
            raise SystemExit("make_game shipped a list that does not read")
    print("pipeline state list: record, merge and shipping ok")


if __name__ == "__main__":
    main()
