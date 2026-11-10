"""Exercise production capture sizing, allocation entry and PNG output without a GPU."""
import argparse
from pathlib import Path
import os
import struct
import subprocess
import tempfile
import zlib

RUN_ALL_ARGS = ["--cxx", "{cxx}", "--headers", "{vulkan_headers}"]

ROOT = Path(__file__).resolve().parents[1]


def block(source, marker):
    start = source.index(marker)
    at = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[at] == "{") - (source[at] == "}")
        at += 1
    return source[start:at]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=ROOT)
    p.add_argument("--headers", type=Path, required=True)
    p.add_argument("--cxx", default="g++")
    p.add_argument("--case", choices=["all", "invalid", "valid", "png"], default="all")
    a = p.parse_args()
    source = (a.source / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    start = source.index("VkImage off_image =")
    globals_and_setup = source[start:source.index("void image_barrier(", start)]
    gate = "if (src && (dev.offscreen || shots) && offscreen_init())"
    assert gate in source
    tail = "if (dev.offscreen || interpolated) return;\n    present_image(src, sw, sh, crop, direct_view);"
    assert tail in source
    png = block(source, "uint32_t crc32(") + "\n" + block(source, "bool write_png(")
    template = (ROOT / "tests/capture_dimensions_test.cpp").read_text(encoding="utf-8")
    fixture = template.replace("/* SETUP */", globals_and_setup).replace("/* GATE */", gate)
    fixture = fixture.replace("/* PRESENT_TAIL */", tail).replace("/* PNG */", png)
    cases = [
        (None, None, 16384, True), ("3440", "1440", 16384, True), ("5120", "1440", 16384, True),
        ("1439", "701", 16384, True), ("1", "1", 16384, True), ("16384", "1440", 16384, True),
        ("256", "256", 256, True), ("257", "256", 256, False), ("16385", "1440", 16384, False),
        ("0", "720", 16384, False), ("abc", "720", 16384, False), ("", "720", 16384, False),
        ("3440tail", "1440", 16384, False), (" 3440", "1440", 16384, False), ("+3440", "1440", 16384, False),
        ("-1", "-1", 4294967295, False), ("4294967296", "1", 4294967295, False),
        ("999999999999999999999999999999", "1", 4294967295, False),
        ("1", "4294967295", 4294967295, False), ("32768", "32768", 32768, False),
        ("715700000", "1", 4294967295, True), ("715800000", "1", 4294967295, False),
        ("2863303432", "2147489722", 4294967295, False), ("0003440", "1440", 16384, True),
    ]
    with tempfile.TemporaryDirectory(prefix="capture-dimensions-") as temp:
        cpp, exe = Path(temp) / "fixture.cpp", Path(temp) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-missing-field-initializers",
                        "-I" + str(a.headers), str(cpp), "-o", str(exe)], check=True)
        if a.case != "png":
            for width, height, limit, valid in cases:
                if a.case == "valid" and not valid or a.case == "invalid" and valid:
                    continue
                env = os.environ.copy()
                for key, value in [("RX_VK_SHOT_W", width), ("RX_VK_SHOT_H", height)]:
                    env.pop(key, None)
                    if value is not None:
                        env[key] = value
                for headless in ["0", "1"]:
                    subprocess.run([str(exe), str(limit), str(int(valid)), headless], env=env, check=True, timeout=10)
        if a.case in ["all", "png"]:
            path = Path(temp) / "normal.png"
            subprocess.run([str(exe), "png", str(path)], check=True, timeout=10)
            data = path.read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
            at, payload = 8, b""
            while at < len(data):
                size = struct.unpack_from(">I", data, at)[0]
                kind, body = data[at + 4:at + 8], data[at + 8:at + 8 + size]
                assert zlib.crc32(kind + body) == struct.unpack_from(">I", data, at + 8 + size)[0]
                if kind == b"IHDR":
                    assert struct.unpack(">IIBBBBB", body) == (257, 251, 8, 2, 0, 0, 0)
                if kind == b"IDAT":
                    payload += body
                at += size + 12
            raw = zlib.decompress(payload)
            assert raw == (b"\x00" + bytes([17, 73, 211]) * 257) * 251
            assert len(payload) == 2 + len(raw) + 5 * ((len(raw) + 65534) // 65535) + 4
    print("PASS: production capture entry, dimension rejection and PNG consumer controls")


if __name__ == "__main__":
    main()
