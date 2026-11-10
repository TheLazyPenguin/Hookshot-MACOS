"""Compile real framegen constructors and inject every allocation failure. No GPU or game.

python -I -B tests/test_framegen_resources.py --headers path/to/Vulkan-Headers/include [--cxx g++]
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}", "--headers", "{vulkan_headers}"]

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
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
    p.add_argument("--phase", choices=["all", "samplers", "images"], default="all")
    a = p.parse_args()
    source = (a.source / "gpu/vk/vk_framegen.cpp").read_text(encoding="utf-8")
    structs = source[source.index("struct Img {"):source.index("// Used only by present_image")]
    structs += source[source.index("struct ScaleState {"):source.index("int64_t now_ns()")]
    signatures = ["void drop_pipe(", "bool make_pipe(", "void drop_setup(", "bool init()", "bool init_scale()",
                  "bool make_img(", "void drop_img(", "void drop_size(", "bool ensure_size(",
                  "bool framegen_wanted(", "bool framegen_on()"]
    functions = "\n".join(function(source, x) for x in signatures if x in source)
    template = (ROOT / "tests/framegen_resources_test.cpp").read_text(encoding="utf-8")
    fixture = template.replace("/* ACTUAL_STRUCTS */", structs).replace("/* ACTUAL_FUNCTIONS */", functions)
    with tempfile.TemporaryDirectory(prefix="framegen-resources-") as temp:
        unit, exe = Path(temp) / "fixture.cpp", Path(temp) / "fixture.exe"
        unit.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-missing-field-initializers",
                        "-pthread", "-I" + str(a.headers), str(unit), "-o", str(exe)], check=True)
        subprocess.run([str(exe), a.phase], check=True, timeout=30)


if __name__ == "__main__":
    main()
