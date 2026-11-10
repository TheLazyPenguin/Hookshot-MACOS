"""The game's menu font reader (gpu/vk/vk_game_font.h) compiled with the vendored zstd decoder and run on files of its own
making (tests/test_game_font.cpp): the good case, truncated frames, a bad name offset, an inexact name, a wrong size word and
a wrong font tag; and a font with no Latin letters is passed over, so the menu falls back to Libertinus instead of drawing
every letter as an empty box (issue 1279, as #1405 did for the old Linux menu font). No game or system font is read.

    python -I -B tests/test_game_font.py [--cxx g++]
"""
import argparse
import struct
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]
ZSTD = ROOT / "third_party/zstd/lib"
SOURCES = ["common/debug.c", "common/entropy_common.c", "common/error_private.c", "common/fse_decompress.c", "common/xxhash.c",
           "common/zstd_common.c", "decompress/huf_decompress.c", "decompress/zstd_ddict.c", "decompress/zstd_decompress.c",
           "decompress/zstd_decompress_block.c"]


def font(*codepoints):
    """A TrueType font with an empty .notdef and one square glyph, mapped from each codepoint (from tests/test_menu_font_latin.py
    of the old Linux menu font)"""
    square = struct.pack(">hhhhh", 1, 100, 0, 900, 800) + struct.pack(">HH", 3, 0) + bytes([1] * 4)
    square += struct.pack(">hhhh", 100, 800, 0, -800) + struct.pack(">hhhh", 0, 0, 800, 0)   # (x deltas, y deltas)
    square += b"\0" * (-len(square) % 4)
    glyf = square
    loca = struct.pack(">HHH", 0, 0, len(square) // 2)   # (short offsets: halved)
    head = struct.pack(">IIIIHHqqhhhhHHhhh", 0x10000, 0x10000, 0, 0x5F0F3CF5, 0, 1000, 0, 0, 0, 0, 1000, 1000, 0, 8, 2, 0, 0)
    hhea = struct.pack(">IhhhHhhhhhhhhhhhH", 0x10000, 800, -200, 0, 1000, 0, 0, 1000, 1, 0, 0, 0, 0, 0, 0, 0, 2)
    maxp = struct.pack(">IH", 0x5000, 2)
    hmtx = struct.pack(">HhHh", 500, 0, 1000, 100)
    segs = [(c, c, (1 - c) & 0xFFFF) for c in sorted(codepoints)] + [(0xFFFF, 0xFFFF, 1)]
    n = len(segs)
    sel = n.bit_length() - 1
    sub = struct.pack(">HHHHHHH", 4, 16 + 8 * n, 0, 2 * n, 2 << sel, sel, 2 * n - (2 << sel))
    sub += b"".join(struct.pack(">H", s[1]) for s in segs) + b"\0\0"
    sub += b"".join(struct.pack(">H", s[0]) for s in segs)
    sub += b"".join(struct.pack(">H", s[2]) for s in segs) + b"\0\0" * n
    sub = sub[:2] + struct.pack(">H", len(sub)) + sub[4:]
    cmap = struct.pack(">HHHHI", 0, 1, 3, 1, 12) + sub
    tables = sorted({b"cmap": cmap, b"glyf": glyf, b"head": head, b"hhea": hhea, b"hmtx": hmtx, b"loca": loca,
                     b"maxp": maxp}.items())
    out = struct.pack(">IHHHH", 0x10000, len(tables), 0, 0, 0)
    offset = 12 + 16 * len(tables)
    body = b""
    for tag, data in tables:
        out += tag + struct.pack(">III", 0, offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    return out + body


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="g++")
    a = p.parse_args()
    # (the C compiler beside the C++ one: g++ -> gcc, clang++ -> clang, x86_64-...-g++ -> x86_64-...-gcc)
    cc = a.cxx[:-2] if a.cxx.endswith("++") else "cc"
    if Path(cc).name == "g" or cc.endswith("-g"):
        cc += "cc"
    flags = ["-O1", "-DZSTD_DISABLE_ASM", "-DZSTD_LEGACY_SUPPORT=0", "-DZSTD_MULTITHREAD=0", "-I" + str(ZSTD),
             "-I" + str(ROOT / "third_party/imgui")]
    with tempfile.TemporaryDirectory(prefix="game-font-") as tmp:
        objs = []
        for i, f in enumerate(SOURCES):
            o = Path(tmp) / ("z%d.o" % i)
            subprocess.run([cc, "-c", str(ZSTD / f), "-o", str(o), "-w"] + flags, check=True)
            objs.append(str(o))
        exe = Path(tmp) / "game-font"
        # (-D_CRT_SECURE_NO_WARNINGS: clang on the MSVC headers marks fopen deprecated, an error with -Werror)
        subprocess.run([a.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-D_CRT_SECURE_NO_WARNINGS",
                        str(ROOT / "tests/test_game_font.cpp"), "-o", str(exe)]
                       + flags + objs, check=True)
        files = Path(tmp) / "romfs"
        latin, hebrew = Path(tmp) / "latin.ttf", Path(tmp) / "hebrew.ttf"
        latin.write_bytes(font(ord("A"), ord("a")))
        hebrew.write_bytes(font(0x05D0))
        subprocess.run([str(exe), str(files), str(latin), str(hebrew)], check=True)


if __name__ == "__main__":
    main()
