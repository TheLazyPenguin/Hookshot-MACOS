"""Complete PNG publication and concurrent CRC initialization, without a game or GPU."""
import argparse
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]


def block(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def decode(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    at, image, kinds = 8, b"", []
    while at < len(data):
        length = struct.unpack_from(">I", data, at)[0]
        kind, payload = data[at+4:at+8], data[at+8:at+8+length]
        assert length <= 0x7fffffff and len(payload) == length
        assert zlib.crc32(kind + payload) == struct.unpack_from(">I", data, at+8+length)[0]
        kinds.append(kind)
        if kind == b"IHDR":
            w, h, bits, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            assert (w, h, bits, color, compression, filtering, interlace) == (257, 251, 8, 2, 0, 0, 0)
        if kind == b"IDAT":
            image += payload
        at += length + 12
    assert at == len(data) and kinds == [b"IHDR", b"IDAT", b"IEND"]
    raw = zlib.decompress(image)
    stride = 257 * 3 + 1
    assert len(raw) == stride * 251  # More than one 65535-byte stored deflate block.
    seed = raw[1]
    assert 1 <= seed <= 19
    assert raw == (b"\0" + bytes([seed, 73, 211]) * 257) * 251


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="g++")
    args = p.parse_args()
    source = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    code = (ROOT / "tests/png_publication_test.cpp").read_text(encoding="utf-8")
    actual = block(source, "uint32_t crc32(") + "\n" + block(source, "bool write_png(")
    start = source.index("std::thread([px, path, at_present] {")
    body = block(source[start:], "std::thread(")
    body = body[body.index("{")+1:-1]
    announce = "void announce(std::shared_ptr<std::vector<uint8_t>> px,std::string path,long long at_present){" + body + "}"
    code = code.replace("/* PNG */", actual).replace("/* ANNOUNCE */", announce)
    cases = ["healthy", "invalid", "bounded-report", "open-failure", "close-failure", "publish-failure", "cleanup-failure", "collisions", "collision-limit", "parallel", "same-target", "announce-success", "announce-failure"] + ["write-" + str(i) for i in range(1, 13)]
    with tempfile.TemporaryDirectory(prefix="png-publication-") as temp:
        cpp, exe = Path(temp)/"fixture.cpp", Path(temp)/"fixture.exe"
        cpp.write_text(code, encoding="utf-8")
        subprocess.run([args.cxx, "-std=c++20", "-O1", "-pthread", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(exe)], check=True)
        for case in cases:
            output = Path(temp)/case
            output.mkdir()
            subprocess.run([str(exe), case, str(output)], check=True, timeout=30)
            for png in output.glob("*.png"):
                decode(png)
            print(case, "passed", flush=True)


if __name__ == "__main__":
    main()
