"""Execute production screenshot setup with failed allocations and real Vulkan types."""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}", "--headers", "{vulkan_headers}"]

ROOT = Path(__file__).resolve().parents[1]


def block(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="g++")
    p.add_argument("--headers", type=Path, required=True)
    p.add_argument("--source", type=Path, default=ROOT)
    a = p.parse_args()
    source = (a.source / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    template = (ROOT / "tests/capture_resources_test.cpp").read_text(encoding="utf-8")
    actual = block(source, "bool shot_dimensions_ready()") + "\n" + block(source, "bool offscreen_init()")
    actual += "\n" + block(source, "bool made_shot_init()")
    actual += "\n" + block(source, "void capture_host_read_barrier(")
    fixture = template.replace("/* ACTUAL_FUNCTION */", actual)
    start = source.index("            if (made_src && !made_shot_init())")
    end = source.index("            if (shot) {", start)
    fixture = fixture.replace("/* ACTUAL_RECORDING */", source[start:end])
    with tempfile.TemporaryDirectory(prefix="capture-resources-") as temp:
        cpp, exe = Path(temp) / "fixture.cpp", Path(temp) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-Wno-missing-field-initializers",
                        "-I" + str(a.headers), str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=30)


if __name__ == "__main__":
    main()
